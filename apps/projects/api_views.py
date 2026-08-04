from datetime import UTC, date, datetime, timedelta
from typing import Any

import psycopg
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
from backend.services.storage import save as save_document
from backend.db import (
    AccountRepository,
    AnalysisRunRepository,
    DocumentRepository,
    ExistTaskRepository,
    ProjectRepository,
    ProjectSourceRepository,
    TeamFolderRepository,
    TeamRepository,
    database_status,
    log_audit,
)
from services.workload import calculator
from backend.db.errors import (
    PermissionDenied,
    RecordNotFound,
    ReferenceNotFound,
    RepositoryError,
)

from .serializers import (
    AssignmentRunCreateSerializer,
    DocumentRegisterSerializer,
    DocumentRoleSaveSerializer,
    JiraProjectRegisterSerializer,
    ProjectCreateSerializer,
    ProjectStatusSerializer,
    TeamFolderReplaceSerializer,
    assignment_run_response,
    document_history_response,
    document_response,
    exist_task_response,
    project_response,
    project_source_response,
    team_folder_response,
)


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


class ProjectDetailAPIView(AuthenticatedAPIView):
    """상세 화면이 한 번에 받아 가는 프로젝트 한 건.

    진행률·업무 목록·담당자별 배분을 같이 준다. 화면이 세 번 부르면 세 번 모두
    같은 `exist_task`를 훑게 되고, 그 사이 「갱신」이 끼면 서로 다른 시점의 숫자가
    한 화면에 섞인다.
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
            | {"tasks": [exist_task_response(task, persons) for task in tasks]}
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

            # 읽어 보니 이미 끝나 있던 프로젝트는 완료 구획에서 시작한다. 판정은
            # 여기 한 번뿐이다 — 매번 하면 사람이 되돌린 것을 다시 완료로 만든다.
            archived = ProjectRepository.archive_if_all_done([row["proj_id"] for row in fresh])

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
    """역할 지정 화면의 저장. 폴더 역할과 그것을 물려받은 `doc` 행을 함께 쓴다."""

    def get(self, request):
        try:
            rows = DocumentRepository.list_for_team(request.user.account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response([document_response(row) for row in rows])

    def put(self, request):
        serializer = DocumentRoleSaveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        folder_roles = serializer.validated_data["folder_roles"]
        file_roles = serializer.validated_data["file_roles"]
        account_id = request.user.account_id

        try:
            folders = TeamFolderRepository.list_for_team(account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        # 파일 목록은 Drive에서 직접 읽는다. 파싱할 수 없는 형식은 등록하지 않는다.
        documents = []
        for folder in folders:
            folder_id = folder["external_folder_id"]
            try:
                # 폴더를 저장할 때 정한 탐색 깊이를 그대로 쓴다.
                files = list_drive_files(
                    account_id=account_id,
                    parent_id=folder_id,
                    max_depth=folder["max_depth"],
                )
            except OAuthError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
            except (RepositoryError, psycopg.Error) as exc:
                return _repository_error_response(exc)

            inherited = folder_roles.get(folder_id)
            for item in files:
                if not item["supported"]:
                    continue
                doc_role = file_roles.get(item["file_id"]) or inherited
                if doc_role is None:
                    continue
                documents.append(
                    {
                        "src_file_id": item["file_id"],
                        "file_name": item["name"],
                        "mime_type": item["mime_type"],
                        "doc_role": doc_role,
                        "src_modified_at": item["modified_at"],
                    }
                )

        try:
            rows = DocumentRepository.save_drive_documents(
                account_id=account_id,
                folder_roles=folder_roles,
                documents=documents,
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response([document_response(row) for row in rows])


def _scan_drive_candidates(account_id: str) -> list[dict[str, Any]]:
    """설정된 폴더 안에서 **아직 `doc`에 없는** 파일.

    파일 목록은 항상 Drive에서 직접 읽는다. 화면이 보내온 이름·형식을 믿고 저장하면
    사용자가 무엇이든 등록시킬 수 있고, 스캔과 등록 사이에 파일이 바뀌었을 때도
    옛 값이 들어간다.

    미지원 형식도 목록에는 넣는다 — 빠진 이유를 보여주지 않으면 "내 파일이 왜
    없지"가 된다. 등록 대상에서 거르는 것은 호출자 몫이다.
    """

    folders = TeamFolderRepository.list_for_team(account_id)
    known = DocumentRepository.registered_file_ids(account_id)

    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
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
                    # 폴더에 지정된 역할을 물려받는다. 화면에서 행마다 바꿀 수 있다.
                    "suggested_role": folder.get("default_doc_role"),
                }
            )
    return candidates


class TeamNewDocumentAPIView(AuthenticatedAPIView):
    """설정된 Drive 폴더에 새로 생긴 파일.

    "새 파일"은 **Drive에는 있는데 이 팀의 `doc`에 없는 것**이다. 폴더에서
    빠져 `deleted = true`가 된 문서도 이미 아는 파일로 친다 — 안 그러면 한 번 내린
    문서가 스캔할 때마다 다시 올라온다.
    """

    def get(self, request):
        try:
            candidates = _scan_drive_candidates(request.user.account_id)
        except OAuthError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(candidates)


class TeamDocumentRegisterAPIView(AuthenticatedAPIView):
    """고른 파일만 `doc`에 추가 등록한다.

    온보딩의 `PUT /documents/`는 폴더 전체를 동기화하며 목록에 없는 문서를 내리는데,
    "새 파일 몇 개를 더한다"에 그것을 쓰면 나머지가 통째로 사라진다. 그래서 여기서는
    **더하기만** 한다.

    원문 다운로드는 하지 않는다 — 온보딩 역할 지정과 같은 범위(`doc` 행 생성까지)다.
    """

    def post(self, request):
        serializer = DocumentRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        requested = serializer.validated_data["files"]
        account_id = request.user.account_id

        try:
            candidates = _scan_drive_candidates(account_id)
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
            doc_role = entry.get("doc_role") or candidate["suggested_role"]
            if doc_role is None:
                skipped.append({"file_id": entry["file_id"], "reason": "NO_ROLE"})
                continue
            documents.append(
                {
                    "src_file_id": candidate["file_id"],
                    "file_name": candidate["file_name"],
                    "mime_type": candidate["mime_type"],
                    "doc_role": doc_role,
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
    """

    def post(self, request):
        account_id = request.user.account_id
        force = request.data.get("force") is True

        try:
            team_id = AccountRepository.team_id(account_id)
            targets = DocumentRepository.list_pending_download(account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

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
            return Response(_sync_jira_sources(account_id=account_id, sources=sources))
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)


class TeamTaskSyncAPIView(AuthenticatedAPIView):
    """팀의 모든 프로젝트를 한 번에 다시 읽는다. 목록 화면의 「갱신」이 쓴다."""

    def post(self, request):
        account_id = request.user.account_id

        try:
            sources = ExistTaskRepository.list_jira_sources_for_team(account_id)
            return Response(_sync_jira_sources(account_id=account_id, sources=sources))
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)


# Sprint 기간을 아직 수집하지 않아 기본 조회 창을 4주로 둔다. 과학적 상수가 아니라
# 비교 가능한 화면을 위한 정책값이라 `from`·`to`로 바꿀 수 있게 열어 둔다.
_DEFAULT_WORKLOAD_DAYS = 28


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

        today = datetime.now(UTC).date()
        period_start = _parse_date(request.query_params.get("from"), today)
        default_end = (period_start or today) + timedelta(days=_DEFAULT_WORKLOAD_DAYS)
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

        return Response(
            calculator.calculate(
                period_start=period_start,
                period_end=period_end,
                profiles=profiles,
                absences=absences,
                tasks=tasks,
            )
            | {"as_of": datetime.now(UTC).isoformat()}
        )


class ProjectAnalysisRunAPIView(AuthenticatedAPIView):
    """현재 `assign_run` 테이블에 배정 실행을 생성한다."""

    def post(self, request, project_id):
        serializer = AssignmentRunCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            row = AnalysisRunRepository.create(
                proj_id=project_id,
                **serializer.validated_data,
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        row["proj_id"] = project_id
        return Response(assignment_run_response(row), status=status.HTTP_201_CREATED)


class AnalysisRunDetailAPIView(AuthenticatedAPIView):
    def get(self, request, run_id):
        try:
            row = AnalysisRunRepository.get(run_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(assignment_run_response(row))
