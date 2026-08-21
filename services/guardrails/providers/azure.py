"""Azure AI Content Safety — `text:analyze`.

순수 REST 라 새 의존성이 없다(`httpx` 는 이미 있다). 규격은 2026-08-20 에 확인한
`2024-09-01` 버전이다:

    POST {endpoint}/contentsafety/text:analyze?api-version=2024-09-01
    Ocp-Apim-Subscription-Key: <키>
    {"text": "...", "outputType": "FourSeverityLevels"}

    → {"blocklistsMatch": [...],
       "categoriesAnalysis": [{"category": "Hate", "severity": 0}, ...]}

카테고리는 Hate·SelfHarm·Sexual·Violence 넷이고, 심각도는 기본 출력에서
**0·2·4·6** 이다(여덟 단계로 바꾸면 0~7). 그래서 임계값도 그 눈금으로 받는다 —
0~1 점수를 쓰는 다른 공급자와 섞으면 안 된다.
"""

from __future__ import annotations

from typing import Any

from .base import GuardrailVerdict, ProviderError

API_VERSION = "2024-09-01"

#: 심각도가 이 값 **이상**이면 막는다. 네 단계 눈금에서 2 는 「낮음」이라
#: 기본값을 4(「중간」)로 둔다 — 2 로 잡으면 업무 대화가 자주 걸린다
#: (한국어 오탐은 위 문서 §4-1 에서 실제로 겪었다).
DEFAULT_SEVERITY_THRESHOLD = 4

#: Azure 가 받는 최대 길이. 넘으면 400 이라 우리가 먼저 자른다.
MAX_TEXT_LENGTH = 10_000

#: 호출 timeout(초). 사용자 발화를 붙들고 있는 자리라 짧게 잡는다.
TIMEOUT_SECONDS = 10


def check(
    *, text: str, config: dict[str, Any], credential: dict[str, Any] | None
) -> GuardrailVerdict:
    endpoint = str((config or {}).get("endpoint") or "").strip().rstrip("/")
    api_key = str((credential or {}).get("api_key") or "").strip()
    if not endpoint:
        raise ProviderError("엔드포인트가 없습니다.")
    if not api_key:
        raise ProviderError("키가 없습니다.")

    threshold = _threshold(config)
    body: dict[str, Any] = {"text": text[:MAX_TEXT_LENGTH], "outputType": "FourSeverityLevels"}
    # 차단 목록은 Azure 리소스 쪽에 만들어 두고 이름만 넘긴다 — 목록 자체는
    # 고객 콘솔에 있고 우리가 들지 않는다.
    blocklists = [str(name) for name in (config or {}).get("blocklists") or [] if str(name).strip()]
    if blocklists:
        body["blocklistNames"] = blocklists

    import httpx

    url = f"{endpoint}/contentsafety/text:analyze?api-version={API_VERSION}"
    try:
        response = httpx.post(
            url,
            json=body,
            headers={"Ocp-Apim-Subscription-Key": api_key},
            timeout=TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        # 예외 문자열에 키가 섞일 수 있는 자리라 클래스 이름만 남긴다(MCP §4-2 와 같은 규칙).
        raise ProviderError(f"연결하지 못했습니다: {exc.__class__.__name__}") from exc

    if response.status_code != 200:
        raise ProviderError(f"응답이 정상이 아닙니다({response.status_code}). 주소와 키를 확인해 주세요.")

    payload = response.json()

    matched = payload.get("blocklistsMatch") or []
    if matched:
        return GuardrailVerdict(
            blocked=True,
            detail={"rule": "blocklist", "blocklist": matched[0].get("blocklistName")},
        )

    worst_category, worst_severity = None, 0
    for item in payload.get("categoriesAnalysis") or []:
        severity = item.get("severity")
        if isinstance(severity, int) and severity > worst_severity:
            worst_category, worst_severity = item.get("category"), severity

    if worst_category is not None and worst_severity >= threshold:
        return GuardrailVerdict(
            blocked=True,
            detail={"category": worst_category, "severity": worst_severity, "threshold": threshold},
        )
    return GuardrailVerdict(blocked=False)


def _threshold(config: dict[str, Any]) -> int:
    raw = (config or {}).get("severity_threshold")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_SEVERITY_THRESHOLD
    # 눈금 밖 값은 기본값으로 돌린다 — 0 을 넣으면 모든 발화가 막힌다.
    return value if 1 <= value <= 7 else DEFAULT_SEVERITY_THRESHOLD
