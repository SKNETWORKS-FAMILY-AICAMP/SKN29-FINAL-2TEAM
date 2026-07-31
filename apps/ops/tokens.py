"""운영자 세션을 나타내는 서명 토큰.

일반 계정 토큰(`apps/accounts/tokens.py`)과 salt를 분리해서, 같은 계정이어도
일반 로그인 토큰으로 운영자 API를, 운영자 토큰으로 일반 API를 호출할 수 없게
막는다. 유효시간도 더 짧게 잡는다 — 고권한 세션일수록 노출 시간을 줄인다.
"""

from django.core import signing

TOKEN_MAX_AGE_SECONDS = 60 * 60 * 2
_TOKEN_SALT = "halil.auth.ops"


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
