"""MCP 서버 등록·연결 테스트 API — 설정 > MCP (11_MCP_설계 §3·§7-1)."""

import logging

import psycopg
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authentication import BearerTokenAuthentication
from backend.db.agent_platform import McpServerRepository
from backend.db.errors import (
    PermissionDenied,
    RecordNotFound,
    ReferenceNotFound,
    RepositoryError,
)
from services.mcp import McpError, UnsafeEndpoint, initialize_and_list_tools, validate

from .serializers import McpServerCreateSerializer, server_response

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


class McpServerListCreateAPIView(AuthenticatedAPIView):
    def get(self, request):
        try:
            rows = McpServerRepository.list_for_team(request.user.account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response([server_response(row) for row in rows])

    def post(self, request):
        """등록. **주소 검사가 저장보다 먼저다**(11_MCP_설계 §4-1).

        저장한 뒤에 검사하면 위험한 주소가 DB 에 남는다 — 나중에 검사가 느슨해지면
        그 행들이 그대로 살아난다.
        """

        serializer = McpServerCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            endpoint_url = validate(data["endpoint_url"])
        except UnsafeEndpoint as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            row = McpServerRepository.create(
                account_id=request.user.account_id,
                name=data["name"],
                endpoint_url=endpoint_url,
                auth_token=(data.get("auth_token") or "").strip() or None,
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(server_response(row), status=status.HTTP_201_CREATED)


class McpServerDetailAPIView(AuthenticatedAPIView):
    def delete(self, request, server_id):
        try:
            McpServerRepository.delete(
                server_id=server_id, account_id=request.user.account_id
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)


class McpServerTestAPIView(AuthenticatedAPIView):
    """연결 테스트 — initialize + tools/list 로 도구 목록을 받아 저장한다.

    **실패해도 등록은 남기고 ERROR 로 표시한다**(설계 §3). 주소나 토큰을 고쳐
    다시 시도할 값이고, 상태를 보여 줘야 왜 편집 화면에서 이 서버의 도구를
    못 고르는지 사용자가 안다.
    """

    def post(self, request, server_id):
        account_id = request.user.account_id
        try:
            server = McpServerRepository.credentials(
                server_id=server_id, account_id=account_id
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        try:
            tools = initialize_and_list_tools(
                endpoint_url=server["endpoint_url"], auth_token=server["auth_token"]
            )
        except (McpError, UnsafeEndpoint) as exc:
            # 토큰이 섞여 들어갈 수 있는 자리라 예외 문자열을 그대로 로그에
            # 남기지 않는다(§4-2 — 로그에 토큰 금지).
            logger.warning("MCP 연결 테스트 실패: server=%s (%s)", server_id, exc.__class__.__name__)
            try:
                McpServerRepository.mark_error(server_id=server_id, account_id=account_id)
            except (RepositoryError, psycopg.Error) as db_exc:
                return _repository_error_response(db_exc)
            return Response(
                {
                    "status": "ERROR",
                    "error_code": getattr(exc, "code", "unreachable"),
                    "detail": str(exc),
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        try:
            saved = McpServerRepository.save_tools(
                server_id=server_id, account_id=account_id, tools=tools
            )
            rows = McpServerRepository.list_for_team(account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        current = next(
            (row for row in rows if row["mcp_server_id"] == server_id), None
        )
        return Response(
            {"status": "CONNECTED", "tool_count": saved}
            | ({"server": server_response(current)} if current else {})
        )
