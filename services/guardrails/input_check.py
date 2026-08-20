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

BLOCKED_MESSAGE = "등록된 가드레일이 이 발화를 막았습니다."


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
    except ProviderError:
        # **부르지 못하면 통과시킨다.** 외부 검사기가 흔들릴 때마다 채팅이 막히면
        # 가드레일이 장애 원인이 된다 — 못 잡는 것보다 나쁘다. 사유는 로그로 남기고
        # 키가 섞일 수 있어 예외 문자열은 그대로 찍지 않는다.
        logger.warning("가드레일 호출 실패: provider=%s", provider["provider_id"])
        return InputGuardOutcome()

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
    return InputGuardOutcome(blocked_reason=BLOCKED_MESSAGE)


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
