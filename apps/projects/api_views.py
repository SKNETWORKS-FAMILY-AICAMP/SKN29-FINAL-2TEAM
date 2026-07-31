import psycopg
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authentication import BearerTokenAuthentication
from apps.connectors.clients import list_drive_files
from apps.connectors.oauth import OAuthError
from backend.db import (
    AnalysisRunRepository,
    DocumentRepository,
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
