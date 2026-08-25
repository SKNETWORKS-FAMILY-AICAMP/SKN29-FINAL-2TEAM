"""등록된 외부 가드레일을 실제 대화에 적용하는 자리.

무엇을 막을지는 **고객이 등록한 가드레일**이 정한다 — 우리가 만든 검사는 없다.
등록·연결 확인은 운영자 콘솔 「가드레일」(`/ops/guardrails`)이다.

정본: `docs/설계 및 구현/3_중간발표 이후/작업기록/2026-08-20_가드레일_조사와_실측.md` §8
"""

from .input_check import InputGuardOutcome, check_user_input, on_check_timeout

__all__ = ["InputGuardOutcome", "check_user_input", "on_check_timeout"]
