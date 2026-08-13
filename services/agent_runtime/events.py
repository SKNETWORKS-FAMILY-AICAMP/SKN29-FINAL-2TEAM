"""Deep Agents 내부 이벤트를 애플리케이션 공통 이벤트로 변환한다.

정본: docs/작업기록/jihun_buildingpage/2026-08-13_02_Deep-Agent_런타임_공통_계약_v1.md §14

이벤트 타입 상수는 확정 계약이라 지금 정의한다. 실제 변환 로직(EventMapper)은
deepagents의 실제 이벤트 형식에 의존하므로, §15 스트리밍 스파이크 테스트가
끝나기 전까지는 스텁으로 둔다 — 스파이크 결과에 따라 §15 마지막에 적힌 대로
subagent_started/completed 대신 subagent_invoked/completed 2단계로 낮춰야 할 수도
있다. 그 경우 이 파일의 EVENT_* 상수만 바꾸면 되도록 executor.py는 이 상수를
문자열 리터럴 대신 이 모듈에서 import해서 쓴다.
"""

from __future__ import annotations

from typing import Any

# --- 이벤트 타입(§14.1) -----------------------------------------------------
EVENT_AGENT_STARTED = "agent_started"
EVENT_SUBAGENT_STARTED = "subagent_started"
EVENT_SUBAGENT_COMPLETED = "subagent_completed"
EVENT_TOOL_STARTED = "tool_started"
EVENT_TOOL_COMPLETED = "tool_completed"
EVENT_MESSAGE_DELTA = "message_delta"
EVENT_RESULT = "result"
EVENT_ERROR = "error"

# §15 스파이크가 "실시간 자식 이벤트 못 얻음"으로 나오면 이 두 상수로 낮춘다.
EVENT_SUBAGENT_INVOKED_FALLBACK = "subagent_invoked"
EVENT_SUBAGENT_COMPLETED_FALLBACK = "subagent_completed"


class EventMapper:
    """raw deepagents 이벤트 → 위 EVENT_* 딕셔너리로 변환.

    ⚠ 스파이크 테스트(§15) 완료 전까지 미구현. 실제 이벤트 페이로드 형태를
    모르는 채로 매핑 로직을 짜면 §15가 경고하는 "SDK 버전마다 형식이 다르다"
    문제를 그대로 안고 간다.
    """

    def convert(
        self,
        raw_event: Any,
        *,
        definition: Any,
        context: Any,
    ) -> dict[str, Any] | None:
        raise NotImplementedError(
            "스트리밍 스파이크 테스트(02 §15) 완료 후 실제 이벤트 형식에 맞춰 구현한다. "
            "services/agent_runtime/_spike/streaming_spike.py 결과를 먼저 확인할 것."
        )
