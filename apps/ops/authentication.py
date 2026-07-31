"""`Authorization: Bearer <ops 토큰>` 인증.

일반 계정 인증(`apps/accounts/authentication.py`)은 서명만 확인하고 끝나지만,
운영자 권한은 즉시 회수 가능해야 한다(계정 잠금, 운영자 플래그 해제). 그래서
매 요청마다 DB를 다시 조회해 `is_admin`과 계정 상태를 재확인한다 — 토큰이
아직 유효 기간 안이어도 권한이 사라졌으면 그 순간부터 막힌다.
"""

from dataclasses import dataclass

import psycopg
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from backend.api_errors import ServiceUnavailable
from backend.db import AccountRepository

from .tokens import InvalidToken, read_token

REVOKED_DETAIL = "운영자 권한이 해제됐거나 계정을 사용할 수 없습니다. 다시 로그인해 주세요."


@dataclass(frozen=True)
class Admin:
    account_id: str
    email: str
    display_name: str

    @property
    def is_authenticated(self) -> bool:
        return True


class OpsBearerTokenAuthentication(BaseAuthentication):
    keyword = b"bearer"

    def authenticate(self, request):
        parts = get_authorization_header(request).split()
        if not parts or parts[0].lower() != self.keyword:
            return None
        if len(parts) != 2:
            raise AuthenticationFailed("인증 헤더 형식이 올바르지 않습니다.")

        try:
            account_id = read_token(parts[1].decode("utf-8"))
        except (UnicodeDecodeError, InvalidToken) as exc:
            raise AuthenticationFailed(str(exc) or "유효하지 않은 인증 정보입니다.") from exc

        try:
            account = AccountRepository.find_credentials_by_id(account_id)
        except psycopg.Error as exc:
            raise ServiceUnavailable() from exc

        if account is None or not account["is_admin"] or account["account_status"] != "ACTIVE":
            raise AuthenticationFailed(REVOKED_DETAIL)

        admin = Admin(
            account_id=account["account_id"],
            email=account["email"],
            display_name=account["display_name"],
        )
        return admin, None

    def authenticate_header(self, request):
        return "Bearer"


class AdminView(APIView):
    """운영자 인증이 필요한 모든 Ops API의 공통 베이스."""

    authentication_classes = [OpsBearerTokenAuthentication]
    permission_classes = [IsAuthenticated]
