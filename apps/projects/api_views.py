from datetime import UTC, date, datetime, timedelta
from io import BytesIO
import json
import logging
import re
from typing import Any

import psycopg
from django.conf import settings
from django.core import signing
from django.http import FileResponse, StreamingHttpResponse
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authentication import BearerTokenAuthentication
from apps.connectors.clients import download_drive_file, list_drive_files, search_jira_issues
from apps.connectors.oauth import OAuthError
from backend.services.hr import (
    list_absences,
    list_capacity_profiles,
    lookup_person_ids_by_external_email,
    lookup_persons,
)
from backend.services.storage import build_key
from backend.services.storage import exists as document_exists
from backend.services.storage import load as load_document
from backend.services.storage import save as save_document
from backend.db.document_pipeline import DocMetaRepository, PipelineDocumentRepository
from services.document_meta import as_row as doc_meta_row
from services.document_meta import build as build_doc_meta
from services.document_pipeline.errors import (
    DocumentPipelineError,
    PipelineConfigurationError,
    RunPodRequestError,
)
from services.document_pipeline.runpod_client import embed_queries, job_status, submit_document_job
from services.document_pipeline.signing import read_download_token, signed_download_url
from services.task_extraction import extract_tasks_stream
from backend.db import (
    AccountRepository,
    DocumentRepository,
    ExistTaskRepository,
    ProjectRepository,
    ProjectSourceRepository,
    TeamFolderRepository,
    TeamRepository,
    database_status,
    log_audit,
)
from backend.db.agent_platform import ProjectTaskRepository
from services.workload import calculator
from backend.db.errors import (
    PermissionDenied,
    RecordNotFound,
    ReferenceNotFound,
    RepositoryError,
)

from .serializers import (
    DocumentRegisterSerializer,
    JiraProjectRegisterSerializer,
    PrimaryCandidateSerializer,
    ProjectCreateSerializer,
    ProjectSourceDocumentSerializer,
    DocumentRemoveSerializer,
    ProjectStatusSerializer,
    TaskExtractionCreateSerializer,
    TeamFolderReplaceSerializer,
    deadline_response,
    missing_document_response,
    pipeline_document_response,
    document_history_response,
    document_response,
    exist_task_response,
    extracted_task_response,
    project_response,
    project_source_response,
    team_folder_response,
)


logger = logging.getLogger(__name__)


def _repository_error_response(exc: Exception) -> Response:
    if isinstance(exc, RecordNotFound):
        return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
    if isinstance(exc, PermissionDenied):
        return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
    if isinstance(exc, ReferenceNotFound):
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
    if isinstance(exc, RepositoryError):
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(
        {"detail": "데이터베이스 요청을 처리할 수 없습니다.", "error": exc.__class__.__name__},
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


class AuthenticatedAPIView(APIView):
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsAuthenticated]


class HealthAPIView(APIView):
    def get(self, request):
        return Response(
            {
                "status": "ok",
                "service": "ai-project-operation-copilot",
                "database": database_status(),
            }
        )


class ProjectListCreateAPIView(AuthenticatedAPIView):
    """내가 소유한 프로젝트. 온보딩은 여기서 DRAFT를 찾거나 만든다."""

    def get(self, request):
        try:
            rows = ProjectRepository.list_for_team(request.user.account_id)
            # 프로젝트마다 부르면 N+1이라 한 번에 집계해 붙인다.
            proj_ids = [row["proj_id"] for row in rows]
            progress = ExistTaskRepository.progress_by_project(proj_ids)
            last_sync = ProjectSourceRepository.last_sync_by_project(proj_ids)
        except psycopg.Error as exc:
            return _repository_error_response(exc)
        return Response(
            [
                project_response(
                    row,
                    progress.get(row["proj_id"]),
                    last_sync=last_sync.get(row["proj_id"]),
                    has_jira_source=row["proj_id"] in last_sync,
                )
                for row in rows
            ]
        )

    def post(self, request):
        serializer = ProjectCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            row = ProjectRepository.create(
                **serializer.validated_data,
                owner_account_id=request.user.account_id,
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(project_response(row), status=status.HTTP_201_CREATED)


#: 기준 문서 후보로 보여 줄 최대 건수.
#:
#: 사람이 한눈에 고를 수 있는 수다. 요약 임베딩은 문서를 **좁히는** 단계라
#: 여기서 많이 뽑아 봐야 아래쪽은 주제가 다른 문서가 채운다.
PRIMARY_CANDIDATE_LIMIT = 5

#: 1등 대비 이 비율 아래는 후보로 올리지 않는다.
#:
#: **절대 임계값을 쓰지 않는 이유**가 있다. 코사인 유사도의 절대값은 임베딩
#: 모델마다 분포가 달라서 "0.4 미만은 무관"이 모델을 바꾸면 그대로 틀린다.
#: 1등 대비 비율은 그 분포에 안 흔들린다.
#:
#: 자르는 목적은 목록을 짧게 하는 것이 아니라 **「없다」를 말할 수 있게** 하는
#: 것이다. 팀 문서가 3건이면 무엇을 물어도 3건이 다 나오고, 그러면 후보 목록이
#: 아무 정보도 주지 않는다(2026-08-11 실측: 회사소개서가 8% 로 3등에 올라왔다).
RELATIVE_CUTOFF = 0.55

#: 두 신호가 **모두** 이보다 약하면 후보로 올리지 않는다.
#:
#: 상대 컷오프는 「1등 대비」라서 **후보가 하나면 아무 일도 하지 않는다** — 자기
#: 자신이 기준이라 무조건 통과한다. 실제로 AI Platform 프로젝트에 아무 상관 없는
#: 정보시스템 구축 제안요청서가 요약 21%·파일명 0% 로 유일 후보에 올랐고, 그걸로
#: 업무를 뽑아 감리 업무 7건이 등록됐다(2026-08-12 QA 시나리오 B).
#:
#: **한쪽만 넘으면 통과시킨다.** 파일명이 밋밋해도 내용이 닮았으면 후보이고,
#: 요약이 부실해도 이름이 걸리면 후보다 — 어느 한 신호의 절대값에 기대지 않는
#: 원래 의도는 그대로다. 둘 다 바닥일 때만 「없다」고 말한다.
SUMMARY_FLOOR = 0.35
NAME_FLOOR = 0.34

#: 파일명 토큰. 영문·숫자·한글 덩어리만 본다.
_TOKEN_RE = re.compile(r"[0-9a-z가-힣]+")


def _tokens(text: str) -> set[str]:
    """비교용 토큰. 한 글자는 버린다 — 조사·연결자가 우연히 겹친다."""

    return {token for token in _TOKEN_RE.findall(text.lower()) if len(token) >= 2}


def _name_match(query_name: str, file_name: str) -> float:
    """프로젝트 이름이 파일명에 얼마나 들어 있는가 (0~1).

    **요약 임베딩은 파일명을 보지 않는다.** `doc_meta.summary_vec` 은 요약문만
    벡터로 만든 것이라, 프로젝트 이름이 파일명에 통째로 들어 있어도 점수가
    오르지 않는다(2026-08-11 실측: 이름이 그대로 든 제안요청서가 0.52).
    사람은 그걸 「이게 왜 이것밖에 안 나오나」로 읽는다.

    파일명은 사람이 붙인 가장 강한 단서다. 따로 센다.
    """

    wanted = _tokens(query_name)
    if not wanted:
        return 0.0
    return len(wanted & _tokens(file_name)) / len(wanted)


def _rank(rows: list[dict[str, Any]], *, name: str) -> list[dict[str, Any]]:
    """요약 유사도와 파일명 일치를 합쳐 다시 세우고, 무관한 것을 자른다.

    가중치는 요약 6 : 파일명 4 다. 파일명이 더 확실한 단서지만 그것만으로
    정하면 「2021년_제안요청서.pdf」처럼 이름이 밋밋한 문서가 영영 밀린다.

    합친 점수는 **정렬과 컷에만** 쓴다. 화면에는 두 값을 따로 보여 준다 —
    합친 수를 「닮은 정도」라고 하나로 보여주면 그 숫자가 무엇인지 아무도 모른다.
    """

    scored = []
    for row in rows:
        summary_score = float(row["summary_score"])
        name_score = _name_match(name, row["file_name"] or "")
        # 둘 다 바닥이면 이 문서는 이 프로젝트와 무관하다. 1등이든 아니든 뺀다.
        if summary_score < SUMMARY_FLOOR and name_score < NAME_FLOOR:
            continue
        scored.append(
            {**row, "name_score": name_score, "rank_score": summary_score * 0.6 + name_score * 0.4}
        )

    scored.sort(key=lambda row: row["rank_score"], reverse=True)
    if not scored:
        return []
    floor = scored[0]["rank_score"] * RELATIVE_CUTOFF
    return [row for row in scored if row["rank_score"] >= floor]


class ProjectPrimaryCandidateAPIView(AuthenticatedAPIView):
    """프로젝트 이름·설명으로 팀 문서 풀에서 **기준 문서 후보**를 찾는다.

    새 도구가 아니라 `document_search` 의 앞단(coarse)을 그대로 쓴다 —
    `doc_meta.summary_vec` 은 문서당 하나뿐이라 팀 문서 전부를 훑어도 싸다.

    **고르는 것은 사람이다.** 여기서 자동으로 묶지 않는다. 어느 문서로 업무를
    뽑았는지는 결과 전체의 전제이고, 그 결정은 사람의 것이라는 규칙이 이미 있다
    (`services/harness/registry.py` `task_extraction`). 이 API 는 후보와 그
    닮은 정도만 주고, 묶는 것은 `PUT .../source-documents/` 다.

    후보가 없으면 **빈 목록을 준다.** 억지로 가장 비슷한 하나를 올리지 않는다 —
    문서 풀이 비었거나 주제가 전혀 다르면 「없다」가 정답이고, 그걸 감추면
    사람이 엉뚱한 문서로 업무를 뽑는다.
    """

    def post(self, request):
        serializer = PrimaryCandidateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        name = serializer.validated_data["name"]
        description = (serializer.validated_data.get("description") or "").strip()

        # 이름만으로는 질의가 너무 짧다. 설명이 있으면 붙여 주제 위에 올린다.
        query = f"{name}\n{description}".strip()

        try:
            team_id = AccountRepository.team_id(request.user.account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        if not team_id:
            return Response({"query": query, "candidates": []})

        try:
            vector = embed_queries([query])[0]
            rows = DocMetaRepository.coarse_search(
                team_id=team_id, query_vector=vector, top_n=PRIMARY_CANDIDATE_LIMIT
            )
        except Exception as exc:  # noqa: BLE001 - 임베딩·검색 실패로 생성을 막지 않는다
            logger.exception("기준 문서 후보 검색에 실패했습니다: team=%s", team_id)
            # 프로젝트는 이미 만들어졌거나 만들 수 있다. 후보를 못 찾은 것과
            # 후보가 없는 것을 화면이 구분해야 해서 사유를 함께 준다.
            return Response(
                {
                    "query": query,
                    "candidates": [],
                    "error": f"문서 후보를 찾지 못했습니다: {exc.__class__.__name__}",
                }
            )

        return Response(
            {
                "query": query,
                "candidates": [
                    {
                        "doc_id": row["doc_id"],
                        "file_name": row["file_name"],
                        "summary": row["summary"],
                        "doc_type": row.get("doc_type"),
                        # 두 근거를 따로 준다. 화면이 "확실합니다"라고 말하지
                        # 않도록 숫자를 그대로 보여 주고, 왜 올라왔는지도 말한다.
                        "summary_score": round(float(row["summary_score"]), 3),
                        "name_score": round(float(row["name_score"]), 3),
                        # 본문이 아직 색인되지 않은 문서는 기준으로 골라도 업무
                        # 추출이 거절한다. 고르기 전에 알아야 한다.
                        "search_ready": row["search_ready"],
                    }
                    for row in _rank(rows, name=name)
                ],
            }
        )


class ProjectDetailAPIView(AuthenticatedAPIView):
    """상세 화면이 한 번에 받아 가는 프로젝트 한 건.

    진행률·업무 목록·담당자별 배분을 같이 준다. 화면이 세 번 부르면 세 번 모두
    같은 `exist_task`를 훑게 되고, 그 사이 「갱신」이 끼면 서로 다른 시점의 숫자가
    한 화면에 섞인다.

    **`task`(추출해서 등록한 우리 업무)는 `tasks` 와 따로 준다.** 이것들은
    `PROPOSED` 이고 담당자도 공수도 없다 — Jira 이슈와 한 목록에 섞으면 진행률과
    남은 공수가 아무도 합의하지 않은 업무로 부풀려진다. 어제 `task` 를 만들고
    등록까지 이었는데 **읽는 곳을 화면에 안 붙여서**, 등록했다는 말을 듣고
    프로젝트에 와도 아무것도 없었다(2026-08-12 QA 시나리오 B).
    """

    def get(self, request, project_id):
        account_id = request.user.account_id
        try:
            row = ProjectRepository.get_for_team(proj_id=project_id, account_id=account_id)
            progress = ExistTaskRepository.progress_by_project([project_id]).get(project_id)
            last_sync = ProjectSourceRepository.last_sync_by_project([project_id])
            tasks = ExistTaskRepository.list_for_project(
                proj_id=project_id,
                account_id=account_id,
            )
            extracted = ProjectTaskRepository.list_for_project(
                proj_id=project_id,
                account_id=account_id,
            )
            # 담당자 이름은 HR에 있다. 이슈마다 부르지 않고 한 번에 모아 온다.
            persons = lookup_persons([t["assignee_person_id"] for t in tasks if t["assignee_person_id"]])
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        return Response(
            project_response(
                row,
                progress,
                last_sync=last_sync.get(project_id),
                has_jira_source=project_id in last_sync,
            )
            | {
                "tasks": [exist_task_response(task, persons) for task in tasks],
                "extracted_tasks": [extracted_task_response(task) for task in extracted],
            }
        )

    def patch(self, request, project_id):
        """상태 변경. 지금은 「완료 처리」와 그 되돌리기뿐이다."""

        serializer = ProjectStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            row = ProjectRepository.set_status(
                proj_id=project_id,
                account_id=request.user.account_id,
                status=serializer.validated_data["status"],
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(project_response(row))

    def delete(self, request, project_id):
        """프로젝트를 지운다. 문서는 팀 문서 풀로 돌려보내고 Jira 업무는 함께 지운다.

        화면이 무엇이 사라지는지 먼저 보여주고 한 번 묻는다. 여기서는 확인된
        요청만 받으므로 다시 묻지 않는다.
        """

        try:
            removed = ProjectRepository.delete(
                proj_id=project_id,
                account_id=request.user.account_id,
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(removed)


class ProjectSourceAPIView(AuthenticatedAPIView):
    """이 프로젝트가 대응하는 Jira 프로젝트. 1:1이라 0개 아니면 1개다.

    읽기 전용이다 — 쓰기는 `PUT /projects/jira/`가 한다. 그 요청은 프로젝트를
    **만들기도** 하므로 특정 프로젝트 하위에 둘 수 없다.
    """

    def get(self, request, project_id):
        try:
            row = ProjectSourceRepository.get_for_project(
                proj_id=project_id,
                account_id=request.user.account_id,
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response([project_source_response(row)] if row else [])


class TeamFolderAPIView(AuthenticatedAPIView):
    """팀이 읽을 Drive 폴더(`team_folder`).

    프로젝트 하위가 아닌 이유는 폴더가 프로젝트에 속하지 않기 때문이다 —
    폴더는 파일이 있는 경로일 뿐이고, 그 안의 파일이 어느 프로젝트 것인지는
    열어 봐야 안다.
    """

    def get(self, request):
        try:
            rows = TeamFolderRepository.list_for_team(request.user.account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response([team_folder_response(row) for row in rows])

    def put(self, request):
        serializer = TeamFolderReplaceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            rows = TeamFolderRepository.replace(
                account_id=request.user.account_id,
                **serializer.validated_data,
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response([team_folder_response(row) for row in rows])


class ProjectJiraRegisterAPIView(AuthenticatedAPIView):
    """고른 Jira 프로젝트를 우리 프로젝트로 등록한다.

    Jira 프로젝트 하나가 프로젝트 하나이므로(1:1), 고르는 행위가 곧 등록이다.
    프로젝트 하위 경로가 아닌 이유는 **이 요청이 프로젝트를 만들기 때문**이다.
    """

    def get(self, request):
        try:
            rows = ExistTaskRepository.list_jira_sources_for_team(request.user.account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response([{"proj_id": row["proj_id"],
                          "project_key": row["external_source_id"],
                          "name": row["display_name"]} for row in rows])

    def put(self, request):
        serializer = JiraProjectRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        account_id = request.user.account_id

        try:
            rows = ProjectSourceRepository.register_from_jira(
                account_id=account_id,
                selections=serializer.validated_data["projects"],
            )

            # 방금 등록한 것(한 번도 안 읽은 소스)은 바로 읽는다. 안 읽으면 목록이
            # "아직 읽지 않았습니다"로 시작하고, 무엇을 가져왔는지 볼 수 없다.
            fresh = [row for row in rows if row["last_sync_at"] is None]
            sync = _sync_jira_sources(account_id=account_id, sources=fresh) if fresh else None

            # 읽어 보니 이미 끝나 있던 프로젝트는 완료 구획에서 시작한다.
            archived = ProjectRepository.sync_status_from_tasks(
                [row["proj_id"] for row in fresh]
            )["archived"]

            rows = ExistTaskRepository.list_jira_sources_for_team(account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        return Response(
            {
                "sources": [
                    {
                        "proj_id": row["proj_id"],
                        "project_key": row["external_source_id"],
                        "name": row["display_name"],
                    }
                    for row in rows
                ],
                "archived": archived,
                # 수집이 일부 실패해도 등록은 유지한다. 무엇이 안 읽혔는지는 알려준다.
                "failed": (sync or {}).get("failed", []),
            }
        )


class TeamDocumentAPIView(AuthenticatedAPIView):
    """팀이 등록한 문서 목록.

    PUT(역할 지정 저장)은 없앴다(2026-08-04). 폴더에 준 역할을 안의 파일이 그대로
    물려받는 화면이었는데, 그 값으로 분기하는 코드가 한 줄도 없었고 정확하지도
    않았다. 어느 문서가 업무의 근거인지는 기준 문서 선택 화면에서 사람이 고른다.
    """

    def get(self, request):
        try:
            rows = DocumentRepository.list_for_team(request.user.account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response([document_response(row) for row in rows])


def _scan_drive_candidates(account_id: str) -> tuple[list[dict[str, Any]], set[str]]:
    """설정된 폴더 안에서 **아직 `doc`에 없는** 파일과, 훑은 파일 id 전부.

    파일 목록은 항상 Drive에서 직접 읽는다. 화면이 보내온 이름·형식을 믿고 저장하면
    사용자가 무엇이든 등록시킬 수 있고, 스캔과 등록 사이에 파일이 바뀌었을 때도
    옛 값이 들어간다.

    미지원 형식도 목록에는 넣는다 — 빠진 이유를 보여주지 않으면 "내 파일이 왜
    없지"가 된다. 등록 대상에서 거르는 것은 호출자 몫이다.

    두 번째 반환값은 이번 스캔에서 Drive 가 준 파일 id 전부다(이미 등록된 것
    포함). 「Drive 에서 사라진 문서」를 이 여집합으로 구한다 — 그것 때문에 Drive 를
    한 번 더 훑을 이유가 없다.
    """

    folders = TeamFolderRepository.list_for_team(account_id)
    known = DocumentRepository.registered_file_ids(account_id)

    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    live: set[str] = set()
    for folder in folders:
        folder_id = folder["external_folder_id"]
        folder_name = folder.get("display_name") or folder_id
        # 폴더를 저장할 때 정한 탐색 깊이를 그대로 쓴다.
        files = list_drive_files(
            account_id=account_id,
            parent_id=folder_id,
            max_depth=folder["max_depth"],
        )
        for item in files:
            file_id = item["file_id"]
            live.add(file_id)
            if file_id in known or file_id in seen:
                continue
            seen.add(file_id)
            candidates.append(
                {
                    "file_id": file_id,
                    "file_name": item["name"],
                    "mime_type": item["mime_type"],
                    "modified_at": item["modified_at"],
                    "supported": item["supported"],
                    # 하위 폴더에서 왔으면 그 경로를, 아니면 고른 폴더 이름을 쓴다.
                    "folder_name": item["folder_path"] or folder_name,
                    "folder_id": folder_id,
                }
            )
    return candidates, live


class TeamNewDocumentAPIView(AuthenticatedAPIView):
    """설정된 Drive 폴더에 새로 생긴 파일.

    "새 파일"은 **Drive에는 있는데 이 팀의 `doc`에 없는 것**이다. 폴더에서
    빠져 `deleted = true`가 된 문서도 이미 아는 파일로 친다 — 안 그러면 한 번 내린
    문서가 스캔할 때마다 다시 올라온다.
    """

    def get(self, request):
        account_id = request.user.account_id
        try:
            candidates, live_file_ids = _scan_drive_candidates(account_id)
            # 폴더 밖으로 뺐다가 되돌린 문서를 되살린다. 이건 사용자 확인이 필요
            # 없다 — 「Drive 에 있는 것을 있다고 표시」하는 복원이라 잃는 것이 없다.
            DocumentRepository.restore_reappeared(
                account_id=account_id, live_file_ids=live_file_ids
            )
            missing = DocumentRepository.list_missing_from_drive(
                account_id=account_id, live_file_ids=live_file_ids
            )
        except OAuthError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(
            {
                "candidates": candidates,
                # 내리지 않고 보여만 준다. 휴지통·완전삭제·폴더 밖 이동이 전부
                # 똑같이 「안 잡힘」으로 보여서 사람이 판단해야 한다.
                "missing": [missing_document_response(row) for row in missing],
            }
        )


class TeamDocumentRemoveAPIView(AuthenticatedAPIView):
    """Drive 에서 삭제된 문서를 정리한다.

    `doc` 행은 남기고 `deleted`만 켜지만, 파싱 산출물(`doc_block`·`chunk`·`vec_idx`)은
    지운다. `chunk.search_text`에 원문이 통째로 들어 있어서, Drive 에서 지운 문서의
    본문을 우리가 계속 들고 있으면 안 된다.
    """

    def post(self, request):
        serializer = DocumentRemoveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        doc_ids = serializer.validated_data["doc_ids"]
        account_id = request.user.account_id

        try:
            result = DocumentRepository.mark_removed_from_drive(
                account_id=account_id, doc_ids=doc_ids
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        # 삭제가 커밋된 **뒤에** 남긴다. 기록이 실패했다고 이미 지운 것을 없던
        # 일로 만들 수는 없으므로, 여기서 터져도 응답은 성공이어야 한다.
        # 예전에는 이 호출이 위 try 안에 있어서, 인자명을 틀렸을 때 화면에는
        # 「실패」가 뜨고 데이터는 지워진 채로 남았다(2026-08-04).
        try:
            log_audit(
                actor_account_id=account_id,
                action="DOCUMENT_REMOVE",
                target_type=DocumentRepository.AUDIT_TARGET,
                payload={"doc_ids": doc_ids, **result},
            )
        except Exception:
            logger.exception("문서 정리 감사 로그를 남기지 못했습니다: %s", doc_ids)

        return Response(result)


class TeamDocumentRegisterAPIView(AuthenticatedAPIView):
    """고른 파일만 `doc`에 추가 등록한다.

    온보딩의 `PUT /documents/`는 폴더 전체를 동기화하며 목록에 없는 문서를 내리는데,
    "새 파일 몇 개를 더한다"에 그것을 쓰면 나머지가 통째로 사라진다. 그래서 여기서는
    **더하기만** 한다.

    원문 다운로드와 파싱은 하지 않는다. **등록된 문서는 전부 검색 가능해야 하지만**,
    그것을 이 요청 하나에 몰면 문서 수만큼 길어지는 동안 사용자에게 아무것도
    말해 줄 수 없다. 화면이 이 응답을 받아 문서마다 다운로드·처리를 이어 부르며
    진행을 보여준다.
    """

    def post(self, request):
        serializer = DocumentRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        requested = serializer.validated_data["files"]
        account_id = request.user.account_id

        try:
            candidates, _live = _scan_drive_candidates(account_id)
        except OAuthError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        by_file_id = {item["file_id"]: item for item in candidates}

        documents = []
        skipped: list[dict[str, str]] = []
        for entry in requested:
            candidate = by_file_id.get(entry["file_id"])
            if candidate is None:
                # 스캔 이후 이미 등록됐거나 폴더에서 사라졌다.
                skipped.append({"file_id": entry["file_id"], "reason": "NOT_FOUND"})
                continue
            if not candidate["supported"]:
                skipped.append({"file_id": entry["file_id"], "reason": "UNSUPPORTED"})
                continue
            documents.append(
                {
                    "src_file_id": candidate["file_id"],
                    "file_name": candidate["file_name"],
                    "mime_type": candidate["mime_type"],
                    # 등록 시점에는 이 문서가 어느 프로젝트의 무엇인지 모른다.
                    # `doc_role`은 기준 문서로 선택될 때 PRIMARY/SUB 로 채워진다.
                    "doc_role": None,
                    "src_modified_at": candidate["modified_at"],
                }
            )

        try:
            created = DocumentRepository.add_drive_documents(
                account_id=account_id,
                documents=documents,
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        # 무엇이 언제 들어왔는지 남긴다. 이게 없어서 예전에 `doc` 건수가 바뀐
        # 경위를 추적하지 못했다. **실제로 들어온 것이 있을 때만** 남긴다 —
        # 미지원 파일을 골랐다가 전부 걸러진 것은 바뀐 게 없어서 이력이 아니다.
        if created:
            log_audit(
                actor_account_id=account_id,
                action=DocumentRepository.ACTION_REGISTER,
                target_type=DocumentRepository.AUDIT_TARGET,
                payload={
                    "registered": len(created),
                    "skipped": len(skipped),
                    "file_names": [row["file_name"] for row in created],
                },
            )

        return Response(
            {
                "registered": [document_response(row) for row in created],
                "skipped": skipped,
            }
        )


class TeamDocumentHistoryAPIView(AuthenticatedAPIView):
    """이 팀의 문서 등록·다운로드 이력. `offset`으로 「더 보기」를 이어 받는다."""

    PAGE_SIZE = 20

    def get(self, request):
        try:
            offset = max(0, int(request.query_params.get("offset", 0)))
        except ValueError:
            offset = 0

        try:
            rows, has_more = DocumentRepository.list_history(
                account_id=request.user.account_id,
                limit=self.PAGE_SIZE,
                offset=offset,
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        return Response(
            {
                "entries": [document_history_response(row) for row in rows],
                # 화면이 「더 보기」를 보일지만 정하면 되므로 남은 개수는 주지 않는다.
                "has_more": has_more,
            }
        )


class TeamDocumentDownloadAPIView(AuthenticatedAPIView):
    """선택된 문서의 원문을 Drive에서 받아 문서 저장소에 넣는다.

    파싱은 이 저장소를 입력으로 삼는다. 파싱이 Drive를 직접 읽지 않는 이유는,
    사용자 OAuth 토큰이 파싱 쪽으로 넘어가면 안 되기 때문이다 — 토큰 하나로
    그 사람의 드라이브 전체를 읽을 수 있다.

    한 건이 실패해도 나머지는 계속 받는다. Drive에서 지워졌거나 권한이 빠진
    문서 하나 때문에 전체가 멈추면, 무엇이 문제인지 알 수 없는 채로 아무것도
    안 받은 상태가 된다.

    `doc_ids`를 주면 그것만 받는다. 화면은 등록한 문서를 한 건씩 받아 파싱까지
    이어 가며 진행을 보여주므로, 한 번에 하나만 지정해서 부른다. 주지 않으면
    팀의 미수신 문서를 전부 받는다.
    """

    def post(self, request):
        account_id = request.user.account_id
        force = request.data.get("force") is True
        only = request.data.get("doc_ids") or None

        try:
            team_id = AccountRepository.team_id(account_id)
            targets = DocumentRepository.list_pending_download(account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        if only is not None:
            wanted = set(only)
            targets = [target for target in targets if target["doc_id"] in wanted]

        if team_id is None:
            return Response(
                {"detail": "팀에 속하지 않은 계정입니다."},
                status=status.HTTP_403_FORBIDDEN,
            )

        downloaded, skipped, failed = [], [], []
        for target in targets:
            if target["storage_key"] and not force:
                skipped.append(target["file_name"])
                continue

            try:
                fetched = download_drive_file(
                    account_id=account_id,
                    file_id=target["src_file_id"],
                    mime_type=target["mime_type"],
                )
            except OAuthError as exc:
                failed.append({"file_name": target["file_name"], "detail": str(exc)})
                continue

            key = build_key(
                team_id=team_id,
                doc_id=target["doc_id"],
                mime_type=fetched["mime_type"],
            )
            try:
                # 파일을 먼저 쓰고 DB에 기록한다. 반대 순서면 "DB에는 있는데 파일이
                # 없는" 상태가 생기고, 파싱이 그걸 읽다가 죽는다.
                content_hash = save_document(key, fetched["content"])
                DocumentRepository.mark_stored(
                    doc_id=target["doc_id"],
                    storage_key=key,
                    content_hash=content_hash,
                    revision=fetched["revision"],
                )
            except OSError as exc:
                failed.append({"file_name": target["file_name"], "detail": f"저장 실패: {exc}"})
                continue
            except (RepositoryError, psycopg.Error) as exc:
                return _repository_error_response(exc)

            downloaded.append({"file_name": target["file_name"], "bytes": len(fetched["content"])})

        if downloaded or failed:
            log_audit(
                actor_account_id=account_id,
                action=DocumentRepository.ACTION_DOWNLOAD,
                target_type=DocumentRepository.AUDIT_TARGET,
                payload={
                    "downloaded": len(downloaded),
                    "failed": len(failed),
                    "file_names": [item["file_name"] for item in downloaded],
                },
            )

        return Response(
            {
                "downloaded": downloaded,
                "skipped": skipped,
                "failed": failed,
            }
        )


def _sync_jira_sources(*, account_id: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
    """넘겨받은 Jira 소스를 다시 읽어 `exist_task`를 교체한다.

    소스 하나가 실패해도 나머지는 반영한다 — Jira 프로젝트 두 개 중 하나가 권한
    문제로 막혔다고 나머지 하나까지 못 읽으면, 보여줄 수 있었던 부하까지 사라진다.

    담당자 매핑에 실패한 이슈도 **버리지 않는다.** `assignee_person_id`를 NULL로
    넣고 건수를 응답에 담는다. 버리면 부하 총량이 조용히 줄어들어, 틀린 숫자가
    맞는 숫자처럼 보인다.
    """

    synced, failed = [], []
    unmapped_assignees = 0
    missing_estimate = 0

    for source in sources:
        project_key = source["external_source_id"]
        try:
            issues = search_jira_issues(account_id=account_id, project_key=project_key)
        except OAuthError as exc:
            failed.append({"project_key": project_key, "detail": str(exc)})
            continue

        # 이슈마다 조회하지 않고 이메일을 모아 한 번에 매핑한다.
        person_by_email = lookup_person_ids_by_external_email(
            sys_type="JIRA",
            emails=[issue["assignee_email"] for issue in issues if issue["assignee_email"]],
        )

        rows = []
        for issue in issues:
            email = issue["assignee_email"]
            person_id = person_by_email.get(email.lower()) if email else None
            if person_id is None:
                unmapped_assignees += 1
            # 공수가 없으면 정량 합계에 못 넣는다. 0으로 간주하지 않고 세어서
            # 노출한다 — Readiness의 PARTIAL_RESULT 입력이 된다.
            if issue["remaining"] is None:
                missing_estimate += 1
            rows.append({**issue, "assignee_person_id": person_id})

        fetched = ExistTaskRepository.replace_for_source(
            proj_source_id=source["proj_source_id"],
            rows=rows,
        )
        synced.append(
            {
                "proj_source_id": source["proj_source_id"],
                "project_key": project_key,
                "fetched": fetched,
            }
        )

    return {
        "sources": synced,
        "failed": failed,
        "unmapped_assignees": unmapped_assignees,
        "missing_estimate": missing_estimate,
        "synced_at": datetime.now(UTC).isoformat(),
    }


class ProjectTaskSyncAPIView(AuthenticatedAPIView):
    """이 프로젝트의 Jira 이슈를 `exist_task`로 다시 읽는다."""

    def post(self, request, project_id):
        account_id = request.user.account_id

        try:
            sources = ExistTaskRepository.list_jira_sources(
                proj_id=project_id,
                account_id=account_id,
            )
            result = _sync_jira_sources(account_id=account_id, sources=sources)
            # **갱신은 Jira 상태로 다시 맞춰 달라는 뜻이다.** 진행률만 바꾸고
            # 완료 여부를 안 건드리면, 업무가 전부 끝난 프로젝트가 계속
            # 「진행중」에 남는다. 사람이 정한 상태는 안 건드린다.
            result["status_changed"] = ProjectRepository.sync_status_from_tasks([project_id])
            return Response(result)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)


class TeamTaskSyncAPIView(AuthenticatedAPIView):
    """팀의 모든 프로젝트를 한 번에 다시 읽는다. 목록 화면의 「갱신」이 쓴다."""

    def post(self, request):
        account_id = request.user.account_id

        try:
            sources = ExistTaskRepository.list_jira_sources_for_team(account_id)
            result = _sync_jira_sources(account_id=account_id, sources=sources)
            result["status_changed"] = ProjectRepository.sync_status_from_tasks(
                sorted({source["proj_id"] for source in sources})
            )
            return Response(result)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)


def _parse_date(raw: str | None, fallback: date) -> date | None:
    if not raw:
        return fallback
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


class TeamWorkloadAPIView(AuthenticatedAPIView):
    """기간별 사람 부하. 계산은 `services/workload/calculator.py`가 한다.

    **팀 전체가 범위다**(2026-08-04). 사람의 부하는 그가 맡은 모든 프로젝트의
    합이다. 프로젝트 하나만 보면 "SKN29만 90%"가 나오는데 실제로는 다른
    프로젝트까지 합쳐 122.5%다 — 한쪽만 보고 여유가 있다고 판단하면 배정이 틀린다.
    어느 프로젝트에서 온 부하인지는 `by_project`가 분해해 준다.

    **결과를 저장하지 않는다.** `workload_result.run_id`가 `assign_run` →
    `ana_snapshot` 체인을 요구하는데 그쪽(P6 Snapshot)이 아직 없다. 지금 억지로
    저장하면 어느 실행의 값인지 모르는 행이 쌓인다.
    """

    def get(self, request):
        account_id = request.user.account_id

        try:
            settings = TeamRepository.settings(account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        # 조회 기간은 팀장이 정한다. Sprint 기간을 아직 수집하지 않아 기본은 4주지만,
        # 팀마다 리듬이 달라 고정할 값이 아니다. `from`·`to`가 오면 그것이 이긴다.
        weeks = settings["workload_weeks"] or settings["default_workload_weeks"]
        today = datetime.now(UTC).date()
        period_start = _parse_date(request.query_params.get("from"), today)
        default_end = (period_start or today) + timedelta(weeks=weeks)
        period_end = _parse_date(request.query_params.get("to"), default_end)

        if period_start is None or period_end is None or period_end <= period_start:
            return Response(
                {"detail": "기간이 올바르지 않습니다. from < to 형식의 날짜여야 합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            tasks = ExistTaskRepository.list_for_team(account_id)
            # 대상자는 요청자의 팀이다. 부하는 남의 팀 사람까지 볼 일이 아니다.
            person_ids = TeamRepository.member_person_ids(AccountRepository.team_id(account_id))
            profiles = list_capacity_profiles(
                person_ids=person_ids,
                period_start=period_start,
                period_end=period_end,
            )
            absences = list_absences(
                person_ids=person_ids,
                period_start=period_start,
                period_end=period_end,
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        # 팀 공통 주 근무시간을 정했으면 HR의 사람별 값을 덮어쓴다. HR 쪽을 고치지
        # 않고 여기서 갈아 끼우는 이유는 HR이 남의 시스템이기 때문이다 — 우리가
        # 정한 기준을 그쪽에 쓸 수는 없다.
        #
        # 사람마다 다른 값을 하나로 뭉개는 것이 맞다. 팀장이 명시적으로 정한
        # 기준이고, 비우면 다시 HR 값으로 돌아간다.
        capacity = settings["capacity_wk_hours"]
        if capacity is not None:
            profiles = [
                {**profile, "wk_hours": capacity, "def_wk_hours": capacity, "fte": 1}
                for profile in profiles
            ]

        return Response(
            calculator.calculate(
                period_start=period_start,
                period_end=period_end,
                profiles=profiles,
                absences=absences,
                tasks=tasks,
            )
            | {
                "as_of": datetime.now(UTC).isoformat(),
                # 화면이 100%를 하드코딩하지 않도록 기준선을 함께 준다.
                "overload_pct": settings["overload_pct"] or settings["default_overload_pct"],
                "workload_weeks": weeks,
            }
        )


class TeamDeadlineAPIView(AuthenticatedAPIView):
    """지연된 업무와 곧 마감인 업무.

    부하와 나누어 둔다. 부하는 **사람**이 단위지만 여기는 **업무**가 단위고, 팀장이
    보고 할 행동도 다르다 — 부하는 배정을 옮기는 판단이고, 지연은 그 이슈를 지금
    찌르는 판단이다. 한 응답에 섞으면 부하 계약(`업무량_계산_MVP_계약`)에 관계없는
    필드가 얹힌다.

    `DONE`은 뺀다. 이미 끝난 일은 마감이 지났어도 할 일이 없다.
    """

    #: 「이번 주」의 길이. 오늘을 포함해 7일이다. 주 경계(월요일)로 자르지 않는
    #: 이유는 금요일에 열었을 때 남은 이틀만 보이면 쓸모가 없기 때문이다.
    SOON_DAYS = 7

    def get(self, request):
        try:
            tasks = ExistTaskRepository.list_for_team(request.user.account_id)
            persons = lookup_persons(
                [t["assignee_person_id"] for t in tasks if t["assignee_person_id"]]
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        today = datetime.now(UTC).date()
        overdue: list[dict[str, Any]] = []
        soon: list[dict[str, Any]] = []

        for task in tasks:
            due = task.get("due_at")
            if due is None or task.get("status_category") == "DONE":
                continue
            days = (due.date() - today).days
            if days < 0:
                overdue.append(deadline_response(task, persons, days=days))
            elif days < self.SOON_DAYS:
                soon.append(deadline_response(task, persons, days=days))

        # 급한 것부터. 지연은 오래된 것이, 예정은 가까운 것이 위다.
        overdue.sort(key=lambda row: (row["days"], row["jira_issue_id"]))
        soon.sort(key=lambda row: (row["days"], row["jira_issue_id"]))

        return Response(
            {
                "as_of": today.isoformat(),
                "soon_days": self.SOON_DAYS,
                "overdue": overdue,
                "soon": soon,
            }
        )


def _pipeline_error_response(exc: Exception) -> Response:
    if isinstance(exc, PipelineConfigurationError):
        return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    if isinstance(exc, RunPodRequestError):
        return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
    return Response(
        {"detail": str(exc) or exc.__class__.__name__},
        status=status.HTTP_409_CONFLICT,
    )


class TeamPipelineDocumentAPIView(AuthenticatedAPIView):
    """기준 문서 선택 화면이 고를 수 있는 후보 — 팀 문서 전부.

    프로젝트 하위가 아니라 `team/` 아래인 이유는 문서가 팀에 속하기 때문이다.
    아직 어느 프로젝트에도 안 묶인 문서를 골라 **묶는** 것이 이 화면의 일이라,
    프로젝트로 걸러 오면 후보가 언제나 0건이 된다.
    """

    def get(self, request):
        try:
            rows = PipelineDocumentRepository.list_team_documents(request.user.account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response([pipeline_document_response(row) for row in rows])


def _document_meta_response(row: dict[str, Any]) -> dict[str, Any]:
    """`state` 매핑 — 개발지시_3차 단계 5.

      준비됨      본문까지 색인됨. 근거로 쓸 수 있다
      메타만      요약은 있지만 본문 색인이 없다. coarse 후보로만 잡힌다
      대기        원문은 받았는데 메타를 아직 안 만들었다
      실패        추출이 안 됐다(스캔본·깨진 글자). 다시 시도할 수 있다
      미지원 형식  파서가 없다(hwp·docx). 다시 시도해도 같다

    「실패」와 「미지원 형식」을 가르는 이유는 사람이 할 행동이 달라서다 —
    앞은 재시도, 뒤는 포기다.
    """

    status_value = row.get("extract_status")
    if status_value == "UNSUPPORTED":
        state = "미지원 형식"
    elif status_value == "FAILED":
        state = "실패"
    elif status_value == "OK":
        state = "준비됨" if row.get("search_ready") else "메타만"
    else:
        state = "대기"

    return {
        "doc_id": row["doc_id"],
        "file_name": row["file_name"],
        "mime_type": row.get("mime_type"),
        "proj_id": row.get("proj_id"),
        "doc_role": row.get("doc_role"),
        "src_modified_at": row.get("src_modified_at"),
        "summary": row.get("summary"),
        "doc_type": row.get("doc_type"),
        "keywords": row.get("keywords") or [],
        "state": state,
        "extract_status": status_value,
        "search_ready": bool(row.get("search_ready")),
        # 원문이 없으면 메타를 만들 수 없다. 화면이 「다시 처리」를 못 누르게 한다.
        "has_source": bool(row.get("storage_key")),
    }


class TeamDocumentMetaAPIView(AuthenticatedAPIView):
    """문서 메타(요약·유형·키워드·요약 임베딩)를 만든다 — A안, 8/11 확정 ⑥.

    **다운로드 다음 단계다.** 폴더 스캔 시점에는 원문 바이트가 없어 CPU 추출을
    할 수 없고, 다운로드 응답 안에서 처리하면 요약 임베딩의 RunPod 콜드 스타트
    (최대 10분)가 다운로드를 통째로 붙잡는다. 등록 → 다운로드 → 처리와 같은
    모양으로 화면이 문서마다 이어 부르며 진행을 보여준다.

    RunPod 문서 처리(`documents/<id>/processing/`)와 다른 일이다. 그쪽은 청크
    단위 임베딩까지 하는 무거운 GPU 경로고, 여기는 문서 하나당 LLM 1회 +
    임베딩 1개다. 싸야 팀 문서 전부에 돌릴 수 있고, 전부에 돌아야 coarse 검색이
    미처리 문서까지 후보로 볼 수 있다.
    """

    def get(self, request):
        """문서 목록 — 상태 칩이 읽는 값까지 함께 준다.

        `state` 를 서버가 정한다. 화면이 extract_status·search_ready 조합을
        해석하면 같은 규칙이 두 곳에 생기고, 한쪽만 고쳐졌을 때 목록과 검색이
        다른 말을 한다.
        """

        try:
            rows = DocMetaRepository.list_with_meta(request.user.account_id)
            removed = DocMetaRepository.list_removed(request.user.account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(
            {
                "documents": [_document_meta_response(row) for row in rows],
                "removed": [
                    {"doc_id": row["doc_id"], "file_name": row["file_name"]} for row in removed
                ],
            }
        )

    def post(self, request):
        account_id = request.user.account_id
        only = request.data.get("doc_ids") or None

        try:
            team_id = AccountRepository.team_id(account_id)
            if team_id is None:
                return Response(
                    {"detail": "팀에 속하지 않은 계정입니다."}, status=status.HTTP_403_FORBIDDEN
                )
            targets = DocMetaRepository.pending_doc_ids(team_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        if only is not None:
            wanted = set(only)
            targets = [doc_id for doc_id in targets if doc_id in wanted]

        built: list[dict[str, Any]] = []
        failed: list[dict[str, str]] = []
        for doc_id in targets:
            try:
                document = PipelineDocumentRepository.get_for_processing(
                    doc_id=doc_id, account_id=account_id
                )
                content = load_document(document["storage_key"])
                meta = build_doc_meta(
                    doc_id=doc_id,
                    content=content,
                    mime_type=document["mime_type"],
                    file_name=document["file_name"],
                )
                DocMetaRepository.upsert(doc_meta_row(meta))
            except (RepositoryError, psycopg.Error) as exc:
                return _repository_error_response(exc)
            except (ValueError, OSError, DocumentPipelineError) as exc:
                # 한 문서가 이상하다고 나머지를 멈추지 않는다. 팀 문서 전부에
                # 도는 일이라 한 건의 실패는 그 한 건으로 끝나야 한다.
                logger.exception("문서 메타 생성 실패: %s", doc_id)
                failed.append({"doc_id": doc_id, "detail": exc.__class__.__name__})
                continue
            built.append(
                {"doc_id": doc_id, "extract_status": meta.extract_status, "detail": meta.detail}
            )

        return Response(
            {
                "built": built,
                "failed": failed,
                # 화면이 "몇 건이 왜 검색 대상이 아닌가"를 말할 수 있게.
                "status_counts": DocMetaRepository.status_counts(team_id),
            }
        )


class DocumentProcessingRunAPIView(AuthenticatedAPIView):
    """RunPod 문서 처리 작업 하나를 제출하고(POST) 상태를 확인한다(GET).

    **팀 문서 단위다.** 파싱·임베딩은 기준 문서로 뽑히기 전에 끝나 있어야 한다.
    """

    def post(self, request, doc_id):
        try:
            document = PipelineDocumentRepository.get_for_processing(
                doc_id=doc_id, account_id=request.user.account_id
            )
            if not document_exists(document["storage_key"]):
                return Response(
                    {"detail": "로컬 문서 저장소에 원문 파일이 없습니다."},
                    status=status.HTTP_409_CONFLICT,
                )
            source_url = signed_download_url(
                doc_id=doc_id, revision=document["cur_revision"]
            )
            result = submit_document_job(
                {
                    "doc_id": doc_id,
                    "revision": document["cur_revision"],
                    "mime_type": document["mime_type"],
                    "source_url": source_url,
                    "max_tokens": settings.CHUNKING_MAX_TOKENS,
                    "merge_peers": settings.CHUNKING_MERGE_PEERS,
                }
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        except (ValueError, OSError, DocumentPipelineError) as exc:
            return _pipeline_error_response(exc)
        return Response(
            {"job_id": result["id"], "status": result.get("status", "IN_QUEUE")},
            status=status.HTTP_202_ACCEPTED,
        )

    def get(self, request, doc_id, job_id):
        try:
            document = PipelineDocumentRepository.get_for_processing(
                doc_id=doc_id, account_id=request.user.account_id
            )
            result = job_status(job_id)
            runpod_status = result.get("status")
            payload = {"job_id": job_id, "status": runpod_status}
            if runpod_status == "COMPLETED":
                output = result.get("output")
                if not isinstance(output, dict):
                    raise ValueError("완료된 RunPod 작업에 output 객체가 없습니다.")
                # 완료 시점에 바로 적재한다. RunPod는 완료 결과를 제한된 시간만
                # 보관해서, 나중에 다시 받아 오면 되겠지 하고 미룰 수 없다.
                payload["ingested"] = PipelineDocumentRepository.ingest(
                    expected_doc=document, result=output
                )
            elif runpod_status in {"FAILED", "CANCELLED", "TIMED_OUT"}:
                payload["error"] = result.get("error") or "RunPod 문서 처리 실패"
            return Response(payload)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        except (ValueError, OSError, DocumentPipelineError) as exc:
            return _pipeline_error_response(exc)


class RunPodDocumentDownloadAPIView(APIView):
    """RunPod Worker가 원문을 받아 가는 유일한 경로.

    로그인 세션이 없다 — 남의 인프라에서 오는 요청이라 Bearer 토큰을 줄 수 없다.
    대신 만료형 서명이 `doc_id`와 `revision`을 묶어 증명한다.

    없는 문서·삭제된 문서·revision 불일치를 **전부 같은 404로** 답한다. 어느
    쪽인지 알려 주면 바깥에서 문서 상태를 캐낼 수 있다.
    """

    authentication_classes = []
    permission_classes = []

    def get(self, request, doc_id):
        try:
            payload = read_download_token(request.query_params.get("token", ""))
            if payload["doc_id"] != doc_id:
                raise signing.BadSignature("URL과 서명 문서 ID가 다릅니다.")
            document = PipelineDocumentRepository.get_signed_download(
                doc_id=doc_id, revision=payload["revision"]
            )
            if not document_exists(document["storage_key"]):
                raise RecordNotFound("로컬 저장소에 문서 원문이 없습니다.")
            stream = BytesIO(load_document(document["storage_key"]))
        except signing.SignatureExpired:
            return Response({"detail": "문서 다운로드 서명이 만료되었습니다."}, status=403)
        except signing.BadSignature:
            return Response({"detail": "문서 다운로드 서명이 올바르지 않습니다."}, status=403)
        except (RecordNotFound, PermissionDenied):
            return Response({"detail": "문서를 찾을 수 없습니다."}, status=404)
        return FileResponse(
            stream,
            content_type=document["mime_type"] or "application/octet-stream",
            as_attachment=True,
            filename=document["file_name"] or f"{doc_id}.bin",
        )


class ProjectSourceDocumentAPIView(AuthenticatedAPIView):
    """이 프로젝트의 기준 문서.

    **PUT이 프로젝트에 문서를 묶는 행위다.** 폴더를 고르는 것도, 문서를 등록하는
    것도 아니고, "이 프로젝트는 이 문서에서 시작한다"라고 정하는 순간이 여기다.

    묶이는 것은 기준 문서 하나뿐이다. 근거 문서는 에이전트가 검색으로 찾는다.
    """

    def get(self, request, project_id):
        try:
            rows = PipelineDocumentRepository.list_ready_for_analysis(
                proj_id=project_id, account_id=request.user.account_id
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response([pipeline_document_response(row) for row in rows])

    def put(self, request, project_id):
        serializer = ProjectSourceDocumentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            PipelineDocumentRepository.set_primary_document(
                proj_id=project_id,
                account_id=request.user.account_id,
                primary_doc_id=serializer.validated_data["primary_document_id"],
            )
            rows = PipelineDocumentRepository.list_ready_for_analysis(
                proj_id=project_id, account_id=request.user.account_id
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response([pipeline_document_response(row) for row in rows])


def _extraction_events(*, team_id: str, primary: dict, ready_ids: list[str]):
    """추출 진행을 NDJSON 한 줄씩 내보낸다.

    응답이 이미 시작됐으므로 예외를 상태 코드로 알릴 수 없다. 마지막 줄에
    `error` 를 실어 보내고, 서버 로그에는 원래 예외를 남긴다 — 화면에 스택을
    보내지 않되 우리는 무엇이 터졌는지 알아야 한다.
    """

    try:
        for event in extract_tasks_stream(
            team_id=team_id, primary_document=primary, document_ids=ready_ids
        ):
            yield json.dumps(event, ensure_ascii=False, default=str) + "\n"
    except (ValueError, OSError, DocumentPipelineError) as exc:
        logger.exception("업무 추출에 실패했습니다: %s", primary.get("doc_id"))
        detail = _pipeline_error_response(exc).data.get("detail") or str(exc)
        yield json.dumps({"type": "error", "detail": detail}, ensure_ascii=False) + "\n"
    except Exception as exc:  # noqa: BLE001 - 스트림 중에는 500을 낼 수 없다
        logger.exception("업무 추출 중 예상치 못한 오류: %s", primary.get("doc_id"))
        yield json.dumps(
            {"type": "error", "detail": f"업무 추출에 실패했습니다: {exc.__class__.__name__}"},
            ensure_ascii=False,
        ) + "\n"


class TaskExtractionRunAPIView(AuthenticatedAPIView):
    """기준 문서에서 업무를 뽑는다.

    사람이 고르는 것은 기준 문서 하나다. 근거 문서는 **에이전트가 팀 문서에서
    검색으로 찾는다**. 검색 경계는 팀이다 — 근거를 프로젝트 안으로 좁히면
    공수·역할이 적힌 회의록이 그 프로젝트에 묶여 있지 않아 영영 안 잡힌다.
    """

    def post(self, request, project_id):
        serializer = TaskExtractionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            documents = PipelineDocumentRepository.list_ready_for_analysis(
                proj_id=project_id, account_id=request.user.account_id
            )
            selected_id = serializer.validated_data["primary_document_id"]
            primary = next((d for d in documents if d["doc_id"] == selected_id), None)
            if primary is None:
                return Response(
                    {"detail": "선택한 문서를 팀 문서에서 찾을 수 없습니다."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            if not primary["search_ready"]:
                return Response(
                    {"detail": "문서가 아직 파싱·청킹·임베딩되지 않았습니다."},
                    status=status.HTTP_409_CONFLICT,
                )
            ready_ids = [d["doc_id"] for d in documents if d["search_ready"]]
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        # 여기서부터 스트림이다. 응답이 시작된 뒤에는 상태 코드를 바꿀 수 없으므로
        # 위의 검사를 전부 끝낸 다음에 연다. 실패는 마지막 줄로 알린다.
        return StreamingHttpResponse(
            _extraction_events(team_id=primary["team_id"], primary=primary, ready_ids=ready_ids),
            # NDJSON. 한 줄이 한 사건이라 프론트가 줄 단위로 읽으면 된다.
            content_type="application/x-ndjson",
        )
