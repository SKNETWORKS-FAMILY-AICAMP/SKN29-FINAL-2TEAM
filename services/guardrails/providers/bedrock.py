"""AWS Bedrock Guardrails — `ApplyGuardrail`.

**정책은 우리가 들지 않는다.** 금지 주제·필터 강도는 고객이 AWS 콘솔에서 만들고,
우리는 그것을 가리키는 좌표(guardrail ID·버전·리전)와 자격증명만 받는다.

REST 로 직접 부르려면 SigV4 서명이 필요해 `boto3` 를 쓴다 — 서명을 손으로 만드는
것보다 의존성 하나가 싸다.

    client.apply_guardrail(
        guardrailIdentifier=..., guardrailVersion=..., source="INPUT",
        content=[{"text": {"text": "..."}}],
    )
    → {"action": "GUARDRAIL_INTERVENED" | "NONE", "assessments": [...], ...}

판정은 `action` 하나로 끝난다. 어떤 정책에 걸렸는지는 `assessments` 에 있고,
우리는 **어느 종류에 걸렸는지만** 기록한다(원문은 담지 않는다).
"""

from __future__ import annotations

from typing import Any

from .base import GuardrailVerdict, ProviderError

#: 버전을 안 적으면 초안을 쓴다 — 콘솔에서 만든 직후의 기본 상태다.
DEFAULT_VERSION = "DRAFT"
DEFAULT_REGION = "ap-northeast-2"
TIMEOUT_SECONDS = 10


def check(
    *, text: str, config: dict[str, Any], credential: dict[str, Any] | None
) -> GuardrailVerdict:
    guardrail_id = str((config or {}).get("guardrail_id") or "").strip()
    if not guardrail_id:
        raise ProviderError("Guardrail ID 가 없습니다.")

    version = str((config or {}).get("guardrail_version") or "").strip() or DEFAULT_VERSION
    region = str((config or {}).get("region") or "").strip() or DEFAULT_REGION
    access_key = str((credential or {}).get("access_key_id") or "").strip()
    secret_key = str((credential or {}).get("secret_access_key") or "").strip()
    if not access_key or not secret_key:
        raise ProviderError("자격증명이 없습니다.")

    try:
        import boto3
        from botocore.config import Config
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError as exc:  # pragma: no cover - 배포에는 항상 있다
        raise ProviderError("이 서버에 boto3 가 설치돼 있지 않습니다.") from exc

    client = boto3.client(
        "bedrock-runtime",
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(connect_timeout=TIMEOUT_SECONDS, read_timeout=TIMEOUT_SECONDS, retries={"max_attempts": 0}),
    )

    try:
        response = client.apply_guardrail(
            guardrailIdentifier=guardrail_id,
            guardrailVersion=version,
            source="INPUT",
            content=[{"text": {"text": text}}],
        )
    except (BotoCoreError, ClientError) as exc:
        # 자격증명이 섞일 수 있어 클래스 이름과 AWS 오류 코드만 남긴다.
        code = getattr(exc, "response", {}).get("Error", {}).get("Code") if hasattr(exc, "response") else None
        raise ProviderError(f"호출하지 못했습니다: {code or exc.__class__.__name__}") from exc

    if response.get("action") != "GUARDRAIL_INTERVENED":
        return GuardrailVerdict(blocked=False)
    return GuardrailVerdict(blocked=True, detail={"policies": _policies(response)})


def _policies(response: dict[str, Any]) -> list[str]:
    """어떤 정책 종류에 걸렸는지 이름만 모은다 — 걸린 문구는 담지 않는다."""

    found: list[str] = []
    for assessment in response.get("assessments") or []:
        for key in assessment:
            name = str(key).replace("Policy", "")
            if name and name not in found:
                found.append(name)
    return found
