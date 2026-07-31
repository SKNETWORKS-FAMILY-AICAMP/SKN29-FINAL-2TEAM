"""외부 커넥터의 OAuth 인가 코드 흐름 공통 기반.

콜백은 Google이 브라우저로 호출하므로 로그인 Bearer 토큰을 받을 수 없다.
대신 짧게 만료되는 서명 state로 인가를 시작한 계정과 커넥터 종류를 검증한다.
"""

import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import requests
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core import signing

GOOGLE_DRIVE = "GOOGLE_DRIVE"
JIRA = "JIRA"
GOOGLE_DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/drive.metadata.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]
JIRA_SCOPES = ["read:jira-work", "read:jira-user", "offline_access"]
STATE_MAX_AGE_SECONDS = 60 * 10
_STATE_SALT = "halil.connector.state"


class OAuthError(Exception):
    """사용자에게 provider 응답 원문을 노출하지 않는 OAuth 실패."""


class OAuthConfigurationError(OAuthError):
    """OAuth 콘솔 자격증명이 로컬 환경에 설정되지 않았다."""


def issue_state(*, account_id: str, connector_type: str) -> str:
    return signing.TimestampSigner(salt=_STATE_SALT).sign_object(
        {"account_id": account_id, "connector_type": connector_type}
    )


def read_state(*, state: str, connector_type: str) -> str:
    try:
        payload = signing.TimestampSigner(salt=_STATE_SALT).unsign_object(
            state,
            max_age=STATE_MAX_AGE_SECONDS,
        )
    except signing.SignatureExpired as exc:
        raise OAuthError("연결 요청이 만료됐습니다.") from exc
    except signing.BadSignature as exc:
        raise OAuthError("유효하지 않은 연결 요청입니다.") from exc

    account_id = payload.get("account_id")
    if payload.get("connector_type") != connector_type or not isinstance(account_id, str):
        raise OAuthError("유효하지 않은 연결 요청입니다.")
    return account_id


def _fernet() -> Fernet:
    # SECRET_KEY를 바로 쓰지 않고 길이가 고정된 Fernet 키로만 파생한다.
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_credential(payload: dict[str, Any]) -> str:
    plaintext = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return _fernet().encrypt(plaintext).decode("ascii")


def decrypt_credential(ciphertext: str) -> dict[str, Any]:
    try:
        plaintext = _fernet().decrypt(ciphertext.encode("ascii"))
        payload = json.loads(plaintext.decode("utf-8"))
    except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OAuthError("저장된 연결 정보를 읽을 수 없습니다. 다시 연결해 주세요.") from exc
    if not isinstance(payload, dict):
        raise OAuthError("저장된 연결 정보 형식이 올바르지 않습니다.")
    return payload


class GoogleDriveOAuth:
    """Google OAuth 웹 애플리케이션 설정과 토큰 교환."""

    authorization_endpoint = "https://accounts.google.com/o/oauth2/v2/auth"
    token_endpoint = "https://oauth2.googleapis.com/token"

    @staticmethod
    def _credentials() -> tuple[str, str]:
        client_id = settings.GOOGLE_DRIVE_CLIENT_ID
        client_secret = settings.GOOGLE_DRIVE_CLIENT_SECRET
        if not client_id or not client_secret:
            raise OAuthConfigurationError("Google Drive OAuth 자격증명이 설정되지 않았습니다.")
        return client_id, client_secret

    @classmethod
    def authorization_url(cls, *, account_id: str) -> str:
        client_id, _ = cls._credentials()
        query = urlencode(
            {
                "client_id": client_id,
                "redirect_uri": settings.GOOGLE_DRIVE_REDIRECT_URI,
                "response_type": "code",
                "scope": " ".join(GOOGLE_DRIVE_SCOPES),
                "access_type": "offline",
                "include_granted_scopes": "true",
                # 재연결 때도 refresh_token을 받는다.
                "prompt": "consent",
                "state": issue_state(account_id=account_id, connector_type=GOOGLE_DRIVE),
            }
        )
        return f"{cls.authorization_endpoint}?{query}"

    @classmethod
    def exchange_code(cls, *, code: str) -> dict[str, Any]:
        client_id, client_secret = cls._credentials()
        try:
            response = requests.post(
                cls.token_endpoint,
                data={
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": settings.GOOGLE_DRIVE_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
                timeout=10,
            )
            response.raise_for_status()
            token = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise OAuthError("Google Drive 연결에 실패했습니다.") from exc

        access_token = token.get("access_token")
        refresh_token = token.get("refresh_token")
        expires_in = token.get("expires_in")
        if not isinstance(access_token, str) or not isinstance(refresh_token, str) or not isinstance(expires_in, int):
            raise OAuthError("Google Drive가 필요한 연결 정보를 반환하지 않았습니다.")

        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires_at.isoformat(),
        }

    @classmethod
    def refresh(cls, credential: dict[str, Any]) -> dict[str, Any]:
        """액세스 토큰을 새로 받는다.

        Google은 갱신 응답에 refresh_token을 다시 주지 않으므로 기존 값을
        유지한다. 테스트 상태의 앱은 refresh_token 자체가 7일 후 만료되며,
        그때는 갱신도 실패하므로 재연결이 필요하다.
        """

        client_id, client_secret = cls._credentials()
        refresh_token = credential.get("refresh_token")
        if not isinstance(refresh_token, str):
            raise OAuthError("저장된 연결 정보에 갱신 토큰이 없습니다. 다시 연결해 주세요.")

        try:
            response = requests.post(
                cls.token_endpoint,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
                timeout=10,
            )
            response.raise_for_status()
            token = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise OAuthError("Google Drive 연결이 만료됐습니다. 다시 연결해 주세요.") from exc

        access_token = token.get("access_token")
        expires_in = token.get("expires_in")
        if not isinstance(access_token, str) or not isinstance(expires_in, int):
            raise OAuthError("Google Drive가 갱신된 연결 정보를 반환하지 않았습니다.")

        return {
            **credential,
            "access_token": access_token,
            "expires_at": (datetime.now(UTC) + timedelta(seconds=expires_in)).isoformat(),
        }


class JiraOAuth:
    """Atlassian OAuth 2.0 (3LO) 인가 코드 흐름과 site(cloudId) 조회."""

    authorization_endpoint = "https://auth.atlassian.com/authorize"
    token_endpoint = "https://auth.atlassian.com/oauth/token"
    accessible_resources_endpoint = "https://api.atlassian.com/oauth/token/accessible-resources"

    @staticmethod
    def _credentials() -> tuple[str, str]:
        client_id = settings.JIRA_CLIENT_ID
        client_secret = settings.JIRA_CLIENT_SECRET
        if not client_id or not client_secret:
            raise OAuthConfigurationError("Jira OAuth 자격증명이 설정되지 않았습니다.")
        return client_id, client_secret

    @classmethod
    def authorization_url(cls, *, account_id: str) -> str:
        client_id, _ = cls._credentials()
        query = urlencode(
            {
                "audience": "api.atlassian.com",
                "client_id": client_id,
                "scope": " ".join(JIRA_SCOPES),
                "redirect_uri": settings.JIRA_REDIRECT_URI,
                "state": issue_state(account_id=account_id, connector_type=JIRA),
                "response_type": "code",
                "prompt": "consent",
            }
        )
        return f"{cls.authorization_endpoint}?{query}"

    @classmethod
    def exchange_code(cls, *, code: str) -> dict[str, Any]:
        client_id, client_secret = cls._credentials()
        try:
            response = requests.post(
                cls.token_endpoint,
                json={
                    "grant_type": "authorization_code",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "redirect_uri": settings.JIRA_REDIRECT_URI,
                },
                timeout=10,
            )
            response.raise_for_status()
            token = response.json()
            access_token = token.get("access_token")
            refresh_token = token.get("refresh_token")
            expires_in = token.get("expires_in")
            if not isinstance(access_token, str) or not isinstance(refresh_token, str) or not isinstance(expires_in, int):
                raise OAuthError("Atlassian이 필요한 연결 정보를 반환하지 않았습니다.")

            resources_response = requests.get(
                cls.accessible_resources_endpoint,
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
                timeout=10,
            )
            resources_response.raise_for_status()
            resources = resources_response.json()
        except (requests.RequestException, ValueError) as exc:
            raise OAuthError("Jira 연결에 실패했습니다.") from exc

        if not isinstance(resources, list):
            raise OAuthError("Atlassian 사이트 목록을 읽지 못했습니다.")
        resource = next((item for item in resources if isinstance(item, dict) and isinstance(item.get("id"), str)), None)
        if resource is None:
            raise OAuthError("연결할 수 있는 Jira 사이트가 없습니다.")

        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires_at.isoformat(),
            "cloud_id": resource["id"],
        }

    @classmethod
    def refresh(cls, credential: dict[str, Any]) -> dict[str, Any]:
        """액세스 토큰을 새로 받는다.

        Atlassian은 갱신마다 refresh_token을 회전시키므로 새로 받은 값으로
        반드시 교체해야 한다. 옛 값을 그대로 두면 다음 갱신이 실패한다.
        """

        client_id, client_secret = cls._credentials()
        refresh_token = credential.get("refresh_token")
        if not isinstance(refresh_token, str):
            raise OAuthError("저장된 연결 정보에 갱신 토큰이 없습니다. 다시 연결해 주세요.")

        try:
            response = requests.post(
                cls.token_endpoint,
                json={
                    "grant_type": "refresh_token",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token,
                },
                timeout=10,
            )
            response.raise_for_status()
            token = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise OAuthError("Jira 연결이 만료됐습니다. 다시 연결해 주세요.") from exc

        access_token = token.get("access_token")
        expires_in = token.get("expires_in")
        if not isinstance(access_token, str) or not isinstance(expires_in, int):
            raise OAuthError("Atlassian이 갱신된 연결 정보를 반환하지 않았습니다.")

        rotated = token.get("refresh_token")
        return {
            **credential,
            "access_token": access_token,
            "refresh_token": rotated if isinstance(rotated, str) else refresh_token,
            "expires_at": (datetime.now(UTC) + timedelta(seconds=expires_in)).isoformat(),
        }
