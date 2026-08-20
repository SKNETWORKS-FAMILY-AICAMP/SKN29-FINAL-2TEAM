"""운영자가 정한 가드레일 정책을 실제로 집행하는 자리.

정책은 `sys_setting.GUARDRAIL_POLICY`에 있고 화면은 운영자 콘솔 「전역 정책」이다
(정본: `docs/작업기록/2026-08-20_가드레일_조사와_실측.md`).
"""

from .input_check import InputGuardOutcome, check_user_input, load_policy

__all__ = ["InputGuardOutcome", "check_user_input", "load_policy"]
