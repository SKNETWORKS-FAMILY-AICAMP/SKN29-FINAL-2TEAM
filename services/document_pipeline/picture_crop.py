"""검색된 Picture block을 원본 PDF crop URL로 연결한다."""

from __future__ import annotations

from urllib.parse import urljoin

from django.conf import settings
from django.core import signing

from .errors import PipelineConfigurationError


SALT = "halil.document-picture-crop.v1"


def signed_picture_crop_url(*, block_id: str, doc_id: str, revision: str) -> str:
    base = str(settings.PUBLIC_BACKEND_BASE_URL).strip()
    if not base.startswith("https://"):
        raise PipelineConfigurationError(
            "PUBLIC_BACKEND_BASE_URL은 이미지 모델이 접근 가능한 HTTPS 주소여야 합니다."
        )
    token = signing.dumps(
        {"block_id": block_id, "doc_id": doc_id, "revision": revision},
        salt=SALT,
        compress=True,
    )
    path = f"api/internal/document-picture-crops/{block_id}/?token={token}"
    return urljoin(base.rstrip("/") + "/", path)


def read_picture_crop_token(token: str) -> dict[str, str]:
    payload = signing.loads(
        token,
        salt=SALT,
        max_age=settings.DOCUMENT_PICTURE_CROP_TOKEN_MAX_AGE_SECONDS,
    )
    required = {"block_id", "doc_id", "revision"}
    if not isinstance(payload, dict) or set(payload) != required:
        raise signing.BadSignature("이미지 crop 서명 payload가 올바르지 않습니다.")
    return {key: str(payload[key]) for key in required}


__all__ = ["read_picture_crop_token", "signed_picture_crop_url"]
