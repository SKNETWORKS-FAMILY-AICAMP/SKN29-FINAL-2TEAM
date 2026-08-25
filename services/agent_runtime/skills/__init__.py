"""Skill(반복 업무 절차 문서) 지원 — deepagents `SkillsMiddleware` 재사용.

정본: docs/설계 및 구현/중간발표 이후/작업기록/Deep_Agents/2026-08-20_16_Skill_Middleware_설계.md

`services.agent_runtime.memory`와 같은 얇은 파사드 구조를 그대로 따른다 —
`backend.py`(경로·namespace 상수), `provider.py`(Factory가 주입받는 파사드).
"""

from __future__ import annotations

__all__: list[str] = []
