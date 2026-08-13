"""Deep Agents 내부 이벤트를 애플리케이션 공통 이벤트로 변환한다.

정본: docs/작업기록/Deep_Agents/2026-08-13_02_Deep-Agent_런타임_공통_계약_v1.md §14

⚠ 스파이크 결론(2026-08-13, §15 실행 완료): fallback 불필요. `stream_mode="updates"`
하나만으로 부모/자식/도구 실행을 실시간·정확하게 구분할 수 있다. 관찰한 신호:

- 네임스페이스 튜플이 부모/자식을 가른다 — 부모는 `()`, 자식은
  `('tools:<run-uuid>', ...)`로 시작한다.
- 부모가 서브 에이전트를 부르는 순간은 `{'model': {'messages': [AIMessage(
  tool_calls=[{'name': 'task', 'args': {'subagent_type': <alias>,
  'description': <task_summary>}}])]}}`로 나온다 — `subagent_type`이 alias,
  `description`이 task_summary와 정확히 대응한다(deepagents 내장 `task` 도구
  계약).
- 자식 네임스페이스 안에서 도구 호출은 `{'model': {'messages': [AIMessage(
  tool_calls=[{'name': <tool_ref>, ...}])]}}` → `{'tools': {'messages':
  [ToolMessage(name=<tool_ref>, ...)]}}` 순서로 온다.
- 자식이 끝나면 **부모 네임스페이스**로 돌아와 `{'tools': {'messages':
  [ToolMessage(name='task', content=<자식의 최종 답변>)]}}`이 온다.
- 부모의 최종 응답은 부모 네임스페이스의 `{'model': {'messages': [AIMessage(
  content=<텍스트>, tool_calls=[])]}}`(tool_calls가 비어 있음)다.

`"messages"`(토큰 단위 델타)·`"custom"` 모드는 이 6단계 분류에는 필요 없다 —
Chat 화면에 타이핑 효과를 낼 때만 별도로 `EVENT_MESSAGE_DELTA`용으로 추가한다.

MVP(1단계 위임)에서는 "부모가 한 번에 하나의 서브 에이전트만 부르고 그것이 끝나야
다음으로 넘어간다"는 전제가 실측과 일치했다 — `_pending_subagents`를 FIFO로 써서
네임스페이스와 서브 에이전트를 대응시킨다. 여러 서브 에이전트를 **동시에**
병렬 호출하는 경우(모델이 한 AIMessage에서 tool_calls를 여러 개 내는 경우)는
아직 관측하지 못했다 — 그 케이스가 실제로 나오면 네임스페이스 접두사와
tool_call_id를 직접 대응시키는 방식으로 다시 검증해야 한다(아래 TODO).
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

# deepagents가 서브 에이전트 위임에 쓰는 내장 도구 이름. 이 이름의 tool_call은
# "실제 도구 호출"이 아니라 "위임"으로 분류한다.
DELEGATION_TOOL_NAME = "task"


class EventMapper:
    """raw deepagents 'updates' 이벤트 스트림 → 위 EVENT_* 딕셔너리로 변환.

    무상태로 쓸 수 없다 — 부모의 위임 결정(subagent_started)과 자식 네임스페이스를
    대응시키려면 "아직 안 끝난 위임"을 기억해야 한다. 실행(run) 하나당
    인스턴스 하나를 새로 만들 것 — executor.py가 run_agent() 호출마다 새
    EventMapper()를 생성해야 한다(재사용하면 이전 실행의 상태가 남는다).
    """

    def __init__(self) -> None:
        # 아직 subagent_completed로 안 닫힌 위임들. FIFO — MVP는 순차 위임만
        # 관측했다(위 모듈 docstring TODO 참고).
        self._pending: list[dict[str, str]] = []
        # 네임스페이스 접두사(예: 'tools:94cc782c-...') -> 그 안에서 도는 서브
        # 에이전트 정보. 같은 네임스페이스에서 여러 이벤트가 나오므로 캐시한다.
        self._namespace_subagent: dict[str, dict[str, str]] = {}

    def convert(
        self,
        raw_event: Any,
        *,
        definition: Any,
        context: Any,
    ) -> dict[str, Any] | None:
        """raw_event는 `(namespace_tuple, mode, payload)` 형태를 기대한다.

        `mode != "updates"`인 이벤트(예: "messages" 토큰 델타)는 지금 None을
        반환한다 — 6단계 분류에 안 쓴다는 뜻이지, 버린다는 뜻이 아니다. 나중에
        `EVENT_MESSAGE_DELTA`를 추가할 때 이 분기만 넓히면 된다.
        """
        if not isinstance(raw_event, tuple) or len(raw_event) != 3:
            return None

        namespace, mode, payload = raw_event
        if mode != "updates" or not isinstance(payload, dict):
            return None

        ns_prefix = namespace[0] if namespace else None
        run_id = getattr(context, "run_id", None)

        for node_name, node_output in payload.items():
            if not isinstance(node_output, dict):
                continue
            messages = node_output.get("messages")
            if not messages:
                continue

            for message in messages:
                event = self._classify(
                    node_name=node_name,
                    ns_prefix=ns_prefix,
                    message=message,
                    definition=definition,
                    run_id=run_id,
                )
                if event is not None:
                    return event

        return None

    def _classify(
        self,
        *,
        node_name: str,
        ns_prefix: str | None,
        message: Any,
        definition: Any,
        run_id: str | None,
    ) -> dict[str, Any] | None:
        tool_calls = list(getattr(message, "tool_calls", None) or [])
        msg_name = getattr(message, "name", None)
        content = getattr(message, "content", "") or ""

        agent_id = getattr(definition, "agent_id", None)
        agent_version_id = getattr(definition, "agent_version_id", None)

        if ns_prefix is None:
            # --- 부모 네임스페이스 -------------------------------------------
            if node_name == "model":
                delegations = [tc for tc in tool_calls if tc.get("name") == DELEGATION_TOOL_NAME]
                if delegations:
                    call = delegations[0]
                    args = call.get("args") or {}
                    alias = args.get("subagent_type")
                    task_summary = args.get("description", "")
                    self._pending.append({"alias": alias, "task_summary": task_summary})
                    return {
                        "type": EVENT_SUBAGENT_STARTED,
                        "run_id": run_id,
                        "agent_id": agent_id,
                        "agent_version_id": agent_version_id,
                        "subagent_alias": alias,
                        "task_summary": task_summary,
                        "complete": False,
                    }
                if not tool_calls and content:
                    # 도구 호출 없이 텍스트만 낸 최종 응답.
                    return {
                        "type": EVENT_RESULT,
                        "text": content,
                        "run_id": run_id,
                        "agent_id": agent_id,
                        "agent_version_id": agent_version_id,
                        "complete": True,
                    }
                return None

            if node_name == "tools" and msg_name == DELEGATION_TOOL_NAME:
                info = self._pending.pop(0) if self._pending else {}
                return {
                    "type": EVENT_SUBAGENT_COMPLETED,
                    "run_id": run_id,
                    "agent_id": agent_id,
                    "agent_version_id": agent_version_id,
                    "subagent_alias": info.get("alias"),
                    "status": "DONE",
                    "complete": False,
                }
            return None

        # --- 자식(서브 에이전트) 네임스페이스 -----------------------------------
        info = self._namespace_subagent.get(ns_prefix)
        if info is None and self._pending:
            # 이 네임스페이스에서 처음 보는 이벤트다 — 아직 자식 쪽에 매핑 안 된
            # 가장 오래된 pending 위임과 연결한다(FIFO, 순차 위임 전제).
            info = self._pending[0]
            self._namespace_subagent[ns_prefix] = info

        alias = info.get("alias") if info else None

        if node_name == "model" and tool_calls:
            tool_ref = tool_calls[0].get("name")
            if tool_ref and tool_ref != DELEGATION_TOOL_NAME:
                return {
                    "type": EVENT_TOOL_STARTED,
                    "run_id": run_id,
                    "subagent_alias": alias,
                    "tool_ref": tool_ref,
                    "complete": False,
                }
            return None

        if node_name == "tools" and msg_name and msg_name != DELEGATION_TOOL_NAME:
            return {
                "type": EVENT_TOOL_COMPLETED,
                "run_id": run_id,
                "subagent_alias": alias,
                "tool_ref": msg_name,
                "complete": False,
            }

        return None
