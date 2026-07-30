"""`Authorization: Bearer <token>` 헤더를 읽는 DRF 인증 클래스.

Django User 모델이 없으므로 `request.user`에는 계정 ID만 들고 있는 최소
객체를 넣는다. `IsAuthenticated`가 보는 것은 `is_authenticated` 뿐이다.
"""

from dataclasses import dataclass

from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from .tokens import InvalidToken, read_token


@dataclass(frozen=True)
class AuthenticatedAccount:
    account_id: str

    @property
    def is_authenticated(self) -> bool:
        return True


class BearerTokenAuthentication(BaseAuthentication):
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

        return AuthenticatedAccount(account_id=account_id), None

    def authenticate_header(self, request):
        return "Bearer"
