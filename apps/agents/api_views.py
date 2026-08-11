"""Agent CRUD API — Builder 가 쓴다 (개발지시_3차 단계 2)."""

import psycopg
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authentication import BearerTokenAuthentication
from backend.db.agent_platform import AgentCrudRepository
from backend.db.errors import (
    PermissionDenied,
    RecordNotFound,
    ReferenceNotFound,
    RepositoryError,
)

from .serializers import (
    AgentWriteSerializer,
    agent_response,
    builtin_tool_response,
    mcp_tool_response,
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


def _split(data: dict) -> tuple[dict, list[str]]:
    fields = dict(data)
    return fields, fields.pop("tool_refs")


class AgentListCreateAPIView(AuthenticatedAPIView):
    def get(self, request):
        try:
            rows = AgentCrudRepository.list_for_team(request.user.account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response([agent_response(row) for row in rows])

    def post(self, request):
        serializer = AgentWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        fields, tool_refs = _split(serializer.validated_data)
        try:
            row = AgentCrudRepository.create(
                account_id=request.user.account_id, fields=fields, tool_refs=tool_refs
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(agent_response(row), status=status.HTTP_201_CREATED)


class AgentDetailAPIView(AuthenticatedAPIView):
    def get(self, request, agent_id):
        try:
            row = AgentCrudRepository.get(agent_id=agent_id, account_id=request.user.account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(agent_response(row))

    def put(self, request, agent_id):
        serializer = AgentWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        fields, tool_refs = _split(serializer.validated_data)
        try:
            row = AgentCrudRepository.update(
                agent_id=agent_id,
                account_id=request.user.account_id,
                fields=fields,
                tool_refs=tool_refs,
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(agent_response(row))

    def delete(self, request, agent_id):
        try:
            AgentCrudRepository.delete(agent_id=agent_id, account_id=request.user.account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AgentToolCatalogAPIView(AuthenticatedAPIView):
    """편집 화면의 도구 체크 목록 — 내장 + 팀의 MCP 도구.

    화면이 내장 목록을 따로 적어 두지 않게 서버가 준다. 적어 두면 Registry 가
    바뀔 때 화면만 옛 목록으로 남는다(실제로 tool id 계약이 두 번 바뀌었다).
    """

    def get(self, request):
        try:
            mcp = AgentCrudRepository.team_tool_refs(request.user.account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(builtin_tool_response() + mcp_tool_response(mcp))
