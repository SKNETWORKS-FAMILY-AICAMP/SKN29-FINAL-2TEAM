"""레거시 Agent Harness가 남긴 공유 조각들.

실행기(`run_agent`)는 2026-08-22에 없어졌다 — 챗은 전부
`services/agent_runtime/`(Deep Agent 엔진)로 돈다. 여기 남은 것은 두 엔진이
같이 보는 이벤트 타입 상수와, 안쪽 모듈(`registry`의 내장 도구 정본,
`trace`의 실행 적재, `naming`의 대화 제목)이다.
"""

from .runner import (
    EVENT_AWAITING_CONFIRMATION,
    EVENT_ERROR,
    EVENT_RESULT,
    EVENT_STAGE,
    EVENT_TOOL_CALL_FINISHED,
    EVENT_TOOL_CALL_STARTED,
)

__all__ = [
    "EVENT_AWAITING_CONFIRMATION",
    "EVENT_ERROR",
    "EVENT_RESULT",
    "EVENT_STAGE",
    "EVENT_TOOL_CALL_FINISHED",
    "EVENT_TOOL_CALL_STARTED",
]
