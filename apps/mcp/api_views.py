"""Customizing Tool 목록 조회 API — 설정 > Customizing Tool (11_MCP_설계 §3).

**팀은 보기만 한다**(2026-08-18 멘토링). 등록·수정·삭제·연결 확인은 운영자
콘솔로 옮겼다(`apps/ops/views/mcp.py`) — 주소와 토큰을 넣는 일은 「코딩 없이」를
내세운 제품이 비개발자에게 시킬 일이 아니다. 8/13 에 모델로 이미 밟은 길이다.

**화면에서만 감추지 않고 쓰기 경로를 걷어냈다.** 폼만 없애면 API 를 그대로
부를 수 있어서 그건 규칙이 아니라 장식이다(모델 이관 때와 같은 판단).
"""

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

from .serializers import server_response

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


class McpServerListAPIView(AuthenticatedAPIView):
    """우리 팀에 붙어 있는 서버와 그 도구들. **팀원도 본다** — 에이전트 편집에서
    고를 수 있는 도구가 무엇인지 알아야 하기 때문이다."""

    def get(self, request):
        try:
            rows = McpServerRepository.list_for_team(request.user.account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response([server_response(row) for row in rows])
