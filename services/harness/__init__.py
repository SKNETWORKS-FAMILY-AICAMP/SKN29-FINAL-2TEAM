"""Agent Harness — 에이전트 하나를 돌리는 실행기.

Chat API(단계 3)와 평가 스크립트가 함께 쓴다. 바깥으로 내보내는 것은
`run_agent` 하나와 이벤트 타입 상수뿐이다 — Registry·Trace 는 안쪽 구조라
호출자가 알 필요가 없다.
"""

from .runner import (
    EVENT_AWAITING_CONFIRMATION,
    EVENT_ERROR,
    EVENT_RESULT,
    EVENT_STAGE,
    EVENT_TOOL_CALL_FINISHED,
    EVENT_TOOL_CALL_STARTED,
    ModelDecision,
    run_agent,
)

__all__ = [
    "EVENT_AWAITING_CONFIRMATION",
    "EVENT_ERROR",
    "EVENT_RESULT",
    "EVENT_STAGE",
    "EVENT_TOOL_CALL_FINISHED",
    "EVENT_TOOL_CALL_STARTED",
    "ModelDecision",
    "run_agent",
]
