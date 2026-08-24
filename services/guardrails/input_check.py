"""사용자 입력에 등록된 외부 가드레일을 적용한다.

**등록된 게 없으면 아무 일도 안 한다.** 우리가 만든 검사는 없다 — 무엇을 막을지는
고객이 등록한 가드레일이 정한다(정본:
`docs/작업기록/2026-08-20_가드레일_조사와_실측.md` §8).

**「연결 확인」을 통과한 것만 부른다.** `UNCHECKED`·`ERROR` 인 등록을 부르면 매
발화가 실패로 끝나고, 그 팀은 이유를 모른 채 대화가 느려진 것만 겪는다.

민감정보 가리기(`sensitive_text.mask_sensitive`)는 여기 없다 — 그건 우리 것이고
`apps/chat` 이 무조건 적용한다. 이 모듈은 **외부 가드레일 몫**만 맡는다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from backend.db import GuardrailEventRepository
from backend.db.agent_platform import GuardrailProviderRepository

from .providers import ProviderError, check

logger = logging.getLogger(__name__)

#: 무엇에 걸렸는지 **종류만** 말한다. 점수·임계값·내부 규칙명까지 알려주면
#: 우회 힌트가 된다 — 사용자가 다시 쓸 수 있을 만큼만 알린다.
BLOCKED_MESSAGE = "등록된 가드레일이 이 발화를 막았습니다."
#: 가드레일에 닿지 못했는데 그 팀이 「대화 차단」을 골랐을 때. **왜 막혔는지
#: 사람 말로 말한다** — 사용자가 자기 발화를 고쳐도 소용없는 상황이라, 표현을
#: 바꾸라고 하면 안 된다. 화면이 쓰는 말(「연결 실패」)에 맞춘다.
UNAVAILABLE_MESSAGE = "가드레일에 연결하지 못했습니다. 잠시 뒤 다시 보내 주세요."
_REASON_LABELS = {
    "Moderation": "유해 표현으로 판단됐습니다",
    "Jailbreak": "지시를 바꾸려는 시도로 판단됐습니다",
    "Contains PII": "개인정보가 포함된 것으로 판단됐습니다",
    "Mask PII": "개인정보가 포함된 것으로 판단됐습니다",
    "NSFW Text": "부적절한 표현으로 판단됐습니다",
    "Off Topic Prompts": "업무 범위를 벗어난 것으로 판단됐습니다",
    "blocklist": "차단 목록에 있는 표현이 포함됐습니다",
}


def _blocked_message(detail: dict[str, Any]) -> str:
    """사용자에게 보여줄 사유. 못 알아보면 뭉뚱그린 문장으로 돌아간다."""

    key = detail.get("guardrail") or detail.get("rule") or detail.get("category")
    label = _REASON_LABELS.get(str(key)) if key else None
    if label is None:
        return BLOCKED_MESSAGE
    return f"{label}. 표현을 바꿔 다시 보내 주세요."


@dataclass(frozen=True)
class InputGuardOutcome:
    """검사 결과. `blocked_reason` 이 있으면 발화를 보내지 않는다."""

    blocked_reason: str | None = None

    @property
    def blocked(self) -> bool:
        return self.blocked_reason is not None


def check_user_input(
    text: str,
    *,
    team_id: str,
    account_id: str | None = None,
    session_id: str | None = None,
) -> InputGuardOutcome:
    provider = _connected_provider(team_id)
    if provider is None:
        return InputGuardOutcome()

    credential = _credential(provider["provider_id"])

    try:
        verdict = check(
            kind=provider["kind"],
            text=text,
            config=provider.get("config") or {},
            credential=credential,
        )
    except ProviderError as exc:
        # **못 불렀을 때 무엇을 할지는 그 팀이 정한다**(`on_failure`). 사내 도구면
        # 통과가 맞지만, 규제 고객에게는 「검사 못 했는데 그냥 보냈다」가 계약
        # 위반이 된다. 우리가 임시 검사를 대신 돌리지는 않는다 — 고객이 동의한
        # 적 없는 기준으로 막는 것이고, 「왜 막혔나」에 답할 수 없다.
        #
        # **어느 쪽이든 기록은 남긴다.** 지금까지는 로그 한 줄이 전부라, 검사가
        # 통째로 빠져도 운영자 콘솔은 마지막 「연결 확인」 결과인 「연결됨」을
        # 계속 보여줬다(2026-08-20 PM 지적).
        logger.warning("가드레일 호출 실패: provider=%s", provider["provider_id"])
        return _unavailable(provider, exc, account_id=account_id, team_id=team_id, session_id=session_id)

    if not verdict.blocked:
        return InputGuardOutcome()

    _record(
        stage="INPUT",
        rule="PROVIDER",
        action="BLOCKED",
        detail={"kind": provider["kind"], **(verdict.detail or {})},
        account_id=account_id,
        team_id=team_id,
        session_id=session_id,
    )
    return InputGuardOutcome(blocked_reason=_blocked_message(verdict.detail or {}))


def on_check_timeout(
    *,
    team_id: str,
    account_id: str | None = None,
    session_id: str | None = None,
) -> InputGuardOutcome:
    """검사를 **기다리다 포기했다.** 부르는 쪽(`apps/chat`)이 상한을 넘겼을 때.

    못 부른 것과 같은 판단을 한다 — 그 팀이 「막음」을 골랐으면 막는다. 여기서
    통과로 고정해 버리면 「대화 차단」을 켠 팀에 구멍이 생긴다: 가드레일이 죽는 대신
    **응답을 안 하면** 그냥 통과한다.
    """

    provider = _connected_provider(team_id)
    if provider is None:
        return InputGuardOutcome()
    return _unavailable(
        provider,
        ProviderError("제한 시간 안에 응답이 없었습니다."),
        account_id=account_id,
        team_id=team_id,
        session_id=session_id,
    )


def _unavailable(
    provider: dict[str, Any],
    exc: ProviderError,
    *,
    account_id: str | None,
    team_id: str,
    session_id: str | None,
) -> InputGuardOutcome:
    """가드레일에 닿지 못했다. 기록을 남기고, 그 팀이 정한 대로 한다."""

    closed = provider.get("on_failure") == "CLOSED"
    _record(
        stage="INPUT",
        rule="PROVIDER",
        action="SKIPPED",
        # 사유는 우리가 쓴 문구뿐이다(`providers/*.py` 의 `raise ProviderError`) —
        # 예외 문자열을 그대로 담지 않으므로 키 조각이 섞이지 않는다.
        detail={"kind": provider["kind"], "reason": str(exc), "blocked": closed},
        account_id=account_id,
        team_id=team_id,
        session_id=session_id,
    )
    if closed:
        return InputGuardOutcome(blocked_reason=UNAVAILABLE_MESSAGE)
    return InputGuardOutcome()


def _connected_provider(team_id: str) -> dict[str, Any] | None:
    try:
        provider = GuardrailProviderRepository.for_team(team_id)
    except Exception:  # noqa: BLE001 - 설정 조회 실패로 대화를 잃지 않는다
        logger.exception("가드레일 등록을 읽지 못했습니다")
        return None
    if provider is None or provider.get("status") != "CONNECTED":
        return None
    return provider


def _credential(provider_id: str) -> dict[str, Any] | None:
    try:
        return GuardrailProviderRepository.credential(provider_id)
    except Exception:  # noqa: BLE001
        logger.exception("가드레일 자격증명을 읽지 못했습니다")
        return None


def _record(**kwargs: Any) -> None:
    """발동 기록. **실패해도 조용히 넘어간다** — 기록 때문에 대화를 끊지 않는다."""

    try:
        GuardrailEventRepository.record(**kwargs)
    except Exception:  # noqa: BLE001
        logger.exception("가드레일 발동 기록에 실패했습니다")
