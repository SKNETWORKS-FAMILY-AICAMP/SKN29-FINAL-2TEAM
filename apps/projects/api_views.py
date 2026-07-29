import psycopg
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.db import AnalysisRunRepository, ProjectRepository, database_status
from backend.db.errors import RecordNotFound, ReferenceNotFound, RepositoryError

from .serializers import (
    AssignmentRunCreateSerializer,
    ProjectCreateSerializer,
    assignment_run_response,
    project_response,
)


def _repository_error_response(exc: Exception) -> Response:
    if isinstance(exc, RecordNotFound):
        return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
    if isinstance(exc, ReferenceNotFound):
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
    if isinstance(exc, RepositoryError):
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(
        {"detail": "데이터베이스 요청을 처리할 수 없습니다.", "error": exc.__class__.__name__},
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


class HealthAPIView(APIView):
    def get(self, request):
        return Response(
            {
                "status": "ok",
                "service": "ai-project-operation-copilot",
                "database": database_status(),
            }
        )


class ProjectListCreateAPIView(APIView):
    def get(self, request):
        try:
            rows = ProjectRepository.list_all()
        except psycopg.Error as exc:
            return _repository_error_response(exc)
        return Response([project_response(row) for row in rows])

    def post(self, request):
        serializer = ProjectCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            row = ProjectRepository.create(**serializer.validated_data)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(project_response(row), status=status.HTTP_201_CREATED)


class ProjectDetailAPIView(APIView):
    def get(self, request, project_id):
        try:
            row = ProjectRepository.get(project_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(project_response(row))


class ProjectAnalysisRunAPIView(APIView):
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


class AnalysisRunDetailAPIView(APIView):
    def get(self, request, run_id):
        try:
            row = AnalysisRunRepository.get(run_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(assignment_run_response(row))
