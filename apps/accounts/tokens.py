"""세션 테이블 없이 계정을 식별하는 서명 토큰과 초대 코드 생성기.

`django.contrib.sessions`와 ORM을 쓰지 않는 구조라 로그인 상태는 서버에
저장하지 않고, `SECRET_KEY`로 서명한 토큰을 클라이언트가 들고 다닌다.
서버에 상태가 없으므로 강제 로그아웃은 불가능하고 만료로만 끊긴다.
"""

import hashlib
import secrets

from django.core import signing

TOKEN_MAX_AGE_SECONDS = 60 * 60 * 12
_TOKEN_SALT = "halil.auth.account"

PASSWORD_RESET_MAX_AGE_SECONDS = 60 * 60
_PASSWORD_RESET_SALT = "halil.auth.password-reset"


class InvalidToken(Exception):
    """서명이 깨졌거나 만료된 토큰."""


def issue_token(account_id: str) -> str:
    return signing.TimestampSigner(salt=_TOKEN_SALT).sign_object({"account_id": account_id})


def read_token(token: str) -> str:
    try:
        payload = signing.TimestampSigner(salt=_TOKEN_SALT).unsign_object(
            token,
            max_age=TOKEN_MAX_AGE_SECONDS,
        )
    except signing.SignatureExpired as exc:
        raise InvalidToken("로그인이 만료됐습니다. 다시 로그인해 주세요.") from exc
    except signing.BadSignature as exc:
        raise InvalidToken("유효하지 않은 인증 정보입니다.") from exc

    return payload["account_id"]


def password_fingerprint(password_hash: str) -> str:
    """재설정 토큰에 실어 보낼 현재 비밀번호의 지문."""

    return hashlib.sha256(password_hash.encode("utf-8")).hexdigest()[:16]


def issue_password_reset_token(*, account_id: str, password_hash: str) -> str:
    """메일로 보낼 재설정 토큰.

    현재 비밀번호의 지문을 함께 서명하므로, 비밀번호가 한 번 바뀌면 같은
    토큰이 자동으로 무효가 된다. 덕분에 발급 이력을 저장하는 테이블 없이도
    1회용이 보장된다(Django `PasswordResetTokenGenerator`와 같은 방식).
    """

    return signing.TimestampSigner(salt=_PASSWORD_RESET_SALT).sign_object(
        {"account_id": account_id, "fingerprint": password_fingerprint(password_hash)}
    )


def read_password_reset_token(token: str) -> dict[str, str]:
    """서명과 만료만 확인한다. 지문 대조는 계정을 읽어 온 뒤 호출자가 한다."""

    try:
        payload = signing.TimestampSigner(salt=_PASSWORD_RESET_SALT).unsign_object(
            token,
            max_age=PASSWORD_RESET_MAX_AGE_SECONDS,
        )
    except signing.SignatureExpired as exc:
        raise InvalidToken("재설정 링크가 만료됐습니다. 다시 요청해 주세요.") from exc
    except signing.BadSignature as exc:
        raise InvalidToken("유효하지 않은 재설정 링크입니다.") from exc

    return payload


def generate_invite_code() -> str:
    """팀장에게 1회만 노출되는 초대 코드 원문."""

    return secrets.token_urlsafe(9)


def hash_invite_code(code: str) -> str:
    """`member_invite.token_hash`에 저장할 값.

    코드 자체가 고엔트로피 난수라 비밀번호처럼 느린 KDF를 쓸 이유가 없다.
    """

    return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()
