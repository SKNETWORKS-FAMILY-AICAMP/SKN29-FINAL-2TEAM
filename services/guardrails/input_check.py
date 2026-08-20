"""사용자 입력에 적용하는 가드레일 — 차단 단어 · 유해 표현 · 민감정보.

세 검사의 순서가 곧 의미다. **차단 단어와 유해 표현은 원문에 대고 본다** —
민감정보를 먼저 가리면 가려진 자리에 있던 말을 못 본다. 민감정보 가리기는
마지막이고, 그 결과만 모델에게 나간다.

**막는 것과 가리는 것을 구분한다.** 차단 단어·유해 표현은 발화를 통째로 막고
(`blocked_reason`), 민감정보는 막지 않고 그 값만 가린다 — 사용자가 자기 주민번호를
적었다고 대화를 끊을 이유가 없다.

출력 측(모델 응답·도구 결과)은 여기서 하지 않는다. LangChain `PIIMiddleware`가
스트리밍 델타까지 덮는 유일한 방법이라 런타임 미들웨어 조립부에 붙는다(위 문서 §6).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from django.conf import settings

from backend.db import GuardrailEventRepository, OpsPolicyRepository
from services.agent_runtime.sensitive_text import mask_sensitive

logger = logging.getLogger(__name__)

#: 유해성 판정 모델. 이 엔드포인트는 무료다(2026-08-20 확인).
MODERATION_MODEL = "omni-moderation-latest"

#: 유해성 호출 timeout(초). 실측 2.2초(위 문서 §4-1)에 여유를 둔 값 —
#: 사용자가 보낸 발화를 붙들고 있는 자리라 `naming.py`의 20초보다 짧게 잡는다.
MODERATION_TIMEOUT_SECONDS = 10

#: 화면에 임계값이 있는 상위 카테고리 ← Moderation API가 주는 세부 이름.
#: API는 `harassment/threatening`처럼 세분화해 돌려주므로 접두사로 묶는다.
_CATEGORY_PREFIXES = {
    "harassment": "harassment",
    "hate": "hate",
    "sexual": "sexual",
    "self_harm": "self-harm",
    "violence": "violence",
    "illicit": "illicit",
}

BLOCKED_WORD_MESSAGE = "차단 단어가 있어 보내지 못했습니다."
MODERATION_MESSAGE = "유해 표현으로 판단되어 보내지 못했습니다."


@dataclass(frozen=True)
class InputGuardOutcome:
    """검사 결과.

    `blocked_reason`이 있으면 발화를 보내지 않는다. 없으면 `model_input`을
    모델에게 보낸다(원문은 부르는 쪽이 그대로 저장한다).
    """

    model_input: str
    blocked_reason: str | None = None

    @property
    def blocked(self) -> bool:
        return self.blocked_reason is not None


def check_user_input(
    text: str,
    *,
    account_id: str | None = None,
    team_id: str | None = None,
    session_id: str | None = None,
    policy: dict[str, Any] | None = None,
) -> InputGuardOutcome:
    """정책을 읽어 세 검사를 적용한다. 정책을 못 읽으면 기본값으로 돈다."""

    resolved = policy if policy is not None else load_policy()
    context = {"account_id": account_id, "team_id": team_id, "session_id": session_id}

    hit = _blocked_word(text, resolved.get("blocked_words") or [])
    if hit is not None:
        _record(stage="INPUT", rule="BLOCKED_WORD", action="BLOCKED", detail={"word": hit}, **context)
        return InputGuardOutcome(model_input=text, blocked_reason=BLOCKED_WORD_MESSAGE)

    moderation = resolved.get("moderation") or {}
    if moderation.get("enabled"):
        flagged = _moderation_hit(text, moderation.get("thresholds") or {})
        if flagged is not None:
            category, score = flagged
            _record(
                stage="INPUT",
                rule="MODERATION",
                action="BLOCKED",
                detail={"category": category, "score": score},
                **context,
            )
            return InputGuardOutcome(model_input=text, blocked_reason=MODERATION_MESSAGE)

    pii = resolved.get("pii") or {}
    if not pii.get("enabled"):
        return InputGuardOutcome(model_input=text)

    masked = mask_sensitive(text)
    if masked != text:
        # 무엇이 걸렸는지는 남기지 않는다 — 원문이 로그로 새는 길이 된다.
        _record(stage="INPUT", rule="PII", action="MASKED", detail={}, **context)
    return InputGuardOutcome(model_input=masked)


def load_policy() -> dict[str, Any]:
    """저장된 정책. 읽지 못하면 기본값 — 설정 조회 실패로 대화가 막히지 않게."""

    try:
        return OpsPolicyRepository.get_guardrail_policy()
    except Exception:  # noqa: BLE001 - 설정 한 줄 때문에 대화를 잃지 않는다
        logger.exception("가드레일 정책을 읽지 못했습니다")
        return OpsPolicyRepository.DEFAULT_GUARDRAIL_POLICY


def _blocked_word(text: str, words: list[str]) -> str | None:
    lowered = text.lower()
    for word in words:
        stripped = str(word).strip()
        if stripped and stripped.lower() in lowered:
            return stripped
    return None


def _moderation_hit(text: str, thresholds: dict[str, Any]) -> tuple[str, float] | None:
    """임계값을 넘은 첫 카테고리와 점수. 판정하지 못하면 `None`.

    **판정에 실패하면 통과시킨다.** 외부 호출 하나가 흔들릴 때마다 채팅이 막히면
    가드레일이 장애 원인이 된다 — 못 잡는 것보다 나쁘다. 실패는 로그로 남는다.
    """

    scores = _category_scores(text)
    if scores is None:
        return None

    for category, limit in thresholds.items():
        prefix = _CATEGORY_PREFIXES.get(category)
        if prefix is None:
            continue
        # `violence`와 `violence/graphic`처럼 세부 항목이 여럿이면 가장 높은 값으로 본다.
        matched = [value for name, value in scores.items() if name.split("/")[0] == prefix]
        if matched and max(matched) >= float(limit):
            return category, round(max(matched), 4)
    return None


def _category_scores(text: str) -> dict[str, float] | None:
    api_key = str(settings.OPENAI_API_KEY or "").strip()
    if not api_key or not text.strip():
        return None

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, timeout=MODERATION_TIMEOUT_SECONDS, max_retries=0)
        result = client.moderations.create(model=MODERATION_MODEL, input=text).results[0]
        raw = result.category_scores.model_dump()
    except Exception:  # noqa: BLE001 - 위 docstring: 판정 실패는 통과다
        logger.exception("유해 표현 검사에 실패했습니다")
        return None

    return {name: float(value) for name, value in raw.items() if isinstance(value, (int, float))}


def _record(**kwargs: Any) -> None:
    """발동 기록. **실패해도 조용히 넘어간다** — 기록 때문에 대화를 끊지 않는다."""

    try:
        GuardrailEventRepository.record(**kwargs)
    except Exception:  # noqa: BLE001
        logger.exception("가드레일 발동 기록에 실패했습니다")
