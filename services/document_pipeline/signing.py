from __future__ import annotations

from urllib.parse import urljoin

from django.conf import settings
from django.core import signing

from .errors import PipelineConfigurationError


SALT = "halil.runpod.document-download.v1"


def signed_download_url(*, project_id: str, doc_id: str, revision: str) -> str:
    base = str(settings.PUBLIC_BACKEND_BASE_URL).strip()
    if not base.startswith("https://"):
        raise PipelineConfigurationError(
            "PUBLIC_BACKEND_BASE_URL은 Cloudflare Tunnel의 HTTPS 주소여야 합니다."
        )
    token = signing.dumps(
        {"project_id": project_id, "doc_id": doc_id, "revision": revision},
        salt=SALT,
        compress=True,
    )
    path = f"api/internal/runpod/documents/{doc_id}/?token={token}"
    return urljoin(base.rstrip("/") + "/", path)


def read_download_token(token: str) -> dict[str, str]:
    payload = signing.loads(
        token,
        salt=SALT,
        max_age=settings.DOCUMENT_DOWNLOAD_TOKEN_MAX_AGE_SECONDS,
    )
    required = {"project_id", "doc_id", "revision"}
    if not isinstance(payload, dict) or set(payload) != required:
        raise signing.BadSignature("서명 payload가 올바르지 않습니다.")
    return {key: str(payload[key]) for key in required}
