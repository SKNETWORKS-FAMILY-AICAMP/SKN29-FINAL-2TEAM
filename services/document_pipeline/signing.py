from __future__ import annotations

from urllib.parse import urljoin

from django.conf import settings
from django.core import signing

from .errors import PipelineConfigurationError


SALT = "halil.runpod.document-download.v1"


def signed_download_url(*, doc_id: str, revision: str) -> str:
    """RunPod 가 원문을 받아 갈 만료형 HTTPS 주소.

    `project_id`는 서명하지 않는다(2026-08-04). 문서 처리는 팀 단위라 이 시점에
    문서가 어느 프로젝트에 속할지 아직 정해지지 않았고(`doc.proj_id`가 NULL),
    없는 값을 서명에 넣으면 검증할 수 없는 항목이 하나 늘 뿐이다. 실제로 지켜야
    하는 것은 "이 문서의, 이 revision 원문만"이다.

    URL 에는 저장 경로도 DB 정보도 들어가지 않는다.
    """

    base = str(settings.PUBLIC_BACKEND_BASE_URL).strip()
    if not base.startswith("https://"):
        raise PipelineConfigurationError(
            "PUBLIC_BACKEND_BASE_URL은 Cloudflare Tunnel의 HTTPS 주소여야 합니다."
        )
    token = signing.dumps(
        {"doc_id": doc_id, "revision": revision},
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
    required = {"doc_id", "revision"}
    if not isinstance(payload, dict) or set(payload) != required:
        raise signing.BadSignature("서명 payload가 올바르지 않습니다.")
    return {key: str(payload[key]) for key in required}
