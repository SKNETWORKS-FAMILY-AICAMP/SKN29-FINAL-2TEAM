from datetime import UTC, datetime

import psycopg
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authentication import BearerTokenAuthentication
from apps.connectors.clients import download_drive_file, list_drive_files, search_jira_issues
from apps.connectors.oauth import OAuthError
from backend.services.hr import lookup_person_ids_by_external_email
from backend.services.storage import build_key
from backend.services.storage import save as save_document
from backend.db import (
    AnalysisRunRepository,
    DocumentRepository,
    ExistTaskRepository,
    ProjectRepository,
    ProjectSourceRepository,
    database_status,
)
from backend.db.errors import (
    PermissionDenied,
    RecordNotFound,
    ReferenceNotFound,
    RepositoryError,
)

from .serializers import (
    AssignmentRunCreateSerializer,
    DocumentRoleSaveSerializer,
    ProjectCreateSerializer,
    ProjectSourceReplaceSerializer,
    assignment_run_response,
    document_response,
    project_response,
    project_source_response,
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
            rows = ProjectRepository.list_for_owner(request.user.account_id)
        except psycopg.Error as exc:
            return _repository_error_response(exc)
        return Response([project_response(row) for row in rows])

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
    def get(self, request, project_id):
        try:
            row = ProjectRepository.get(project_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(project_response(row))


class ProjectSourceAPIView(AuthenticatedAPIView):
    """이 프로젝트가 읽을 Drive 폴더·Jira 프로젝트(`proj_source`)."""

    def get(self, request, project_id):
        try:
            rows = ProjectSourceRepository.list_for_project(
                proj_id=project_id,
                account_id=request.user.account_id,
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response([project_source_response(row) for row in rows])

    def put(self, request, project_id):
        serializer = ProjectSourceReplaceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            rows = ProjectSourceRepository.replace(
                proj_id=project_id,
                account_id=request.user.account_id,
                **serializer.validated_data,
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response([project_source_response(row) for row in rows])


class ProjectDocumentAPIView(AuthenticatedAPIView):
    """역할 지정 화면의 저장. 폴더 역할과 그것을 물려받은 `doc` 행을 함께 쓴다."""

    def get(self, request, project_id):
        try:
            rows = DocumentRepository.list_for_project(
                proj_id=project_id,
                account_id=request.user.account_id,
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response([document_response(row) for row in rows])

    def put(self, request, project_id):
        serializer = DocumentRoleSaveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        folder_roles = serializer.validated_data["folder_roles"]
        file_roles = serializer.validated_data["file_roles"]
        account_id = request.user.account_id

        try:
            sources = ProjectSourceRepository.list_for_project(proj_id=project_id, account_id=account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        # 파일 목록은 Drive에서 직접 읽는다. 파싱할 수 없는 형식은 등록하지 않는다.
        documents = []
        for source in sources:
            if source["source_type"] != ProjectSourceRepository.DRIVE_FOLDER:
                continue
            folder_id = source["external_source_id"]
            try:
                # 폴더를 저장할 때 정한 탐색 깊이를 그대로 쓴다.
                files = list_drive_files(
                    account_id=account_id,
                    parent_id=folder_id,
                    max_depth=source["max_depth"],
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
                proj_id=project_id,
                account_id=account_id,
                folder_roles=folder_roles,
                documents=documents,
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response([document_response(row) for row in rows])


class ProjectDocumentDownloadAPIView(AuthenticatedAPIView):
    """선택된 문서의 원문을 Drive에서 받아 문서 저장소에 넣는다.

    파싱은 이 저장소를 입력으로 삼는다. 파싱이 Drive를 직접 읽지 않는 이유는,
    사용자 OAuth 토큰이 파싱 쪽으로 넘어가면 안 되기 때문이다 — 토큰 하나로
    그 사람의 드라이브 전체를 읽을 수 있다.

    한 건이 실패해도 나머지는 계속 받는다. Drive에서 지워졌거나 권한이 빠진
    문서 하나 때문에 전체가 멈추면, 무엇이 문제인지 알 수 없는 채로 아무것도
    안 받은 상태가 된다.
    """

    def post(self, request, project_id):
        account_id = request.user.account_id
        force = request.data.get("force") is True

        try:
            targets = DocumentRepository.list_pending_download(
                proj_id=project_id,
                account_id=account_id,
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

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
                proj_id=project_id,
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

        return Response(
            {
                "downloaded": downloaded,
                "skipped": skipped,
                "failed": failed,
            }
        )


class ProjectTaskSyncAPIView(AuthenticatedAPIView):
    """이 프로젝트가 읽기로 한 Jira 프로젝트들의 미완료 이슈를 `exist_task`로 가져온다.

    부하 계산의 분자가 되는 데이터다. 소스 하나가 실패해도 나머지는 반영한다 —
    Jira 프로젝트 두 개 중 하나가 권한 문제로 막혔다고 나머지 하나까지 못 읽으면,
    보여줄 수 있었던 부하까지 사라진다.

    담당자 매핑에 실패한 이슈도 **버리지 않는다.** `assignee_person_id`를 NULL로
    넣고 건수를 응답에 담는다. 버리면 부하 총량이 조용히 줄어들어, 틀린 숫자가
    맞는 숫자처럼 보인다.
    """

    def post(self, request, project_id):
        account_id = request.user.account_id

        try:
            sources = ExistTaskRepository.list_jira_sources(
                proj_id=project_id,
                account_id=account_id,
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

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

            try:
                fetched = ExistTaskRepository.replace_for_source(
                    proj_source_id=source["proj_source_id"],
                    rows=rows,
                )
            except (RepositoryError, psycopg.Error) as exc:
                return _repository_error_response(exc)

            synced.append(
                {
                    "proj_source_id": source["proj_source_id"],
                    "project_key": project_key,
                    "fetched": fetched,
                }
            )

        return Response(
            {
                "sources": synced,
                "failed": failed,
                "unmapped_assignees": unmapped_assignees,
                "missing_estimate": missing_estimate,
                "synced_at": datetime.now(UTC).isoformat(),
            }
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
