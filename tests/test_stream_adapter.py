"""stream_adapter.py(DeepAgentStreamAdapter) 테스트.

runtime.stream() 호출 인자를 확인하고(단위), 실제 deepagents 그래프 + 스크립트
모델로 진짜 3-tuple 이벤트가 나오는지도 확인한다(네트워크 호출 없음).
"""

from typing import Any

from django.test import SimpleTestCase
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from pydantic import Field

from deepagents import create_deep_agent

from services.agent_runtime.stream_adapter import DeepAgentStreamAdapter


class _ScriptedModel(BaseChatModel):
    responses: list = Field(default_factory=list)
    call_count: int = 0
    model_config = {"arbitrary_types_allowed": True}

    def bind_tools(self, tools: Any, *, tool_choice: str | None = None, **kwargs: Any):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        idx = min(self.call_count, len(self.responses) - 1)
        response = self.responses[idx]
        self.call_count += 1
        return ChatResult(generations=[ChatGeneration(message=response)])

    @property
    def _llm_type(self):
        return "scripted-fake"


class _FakeRuntime:
    def __init__(self):
        self.stream_calls = []

    def stream(self, input_state, **kwargs):
        self.stream_calls.append({"input_state": input_state, "kwargs": kwargs})
        return iter([((), "updates", {"model": {"messages": []}})])


class StreamCallArgumentsTests(SimpleTestCase):
    def test_calls_runtime_stream_with_updates_list_and_subgraphs(self):
        runtime = _FakeRuntime()

        list(DeepAgentStreamAdapter().stream(runtime=runtime, user_input="안녕"))

        call = runtime.stream_calls[0]
        # "custom"도 구독한다 — tools/adapters.py의 제너레이터 도구가
        # get_stream_writer()로 흘려보내는 진행 이벤트를 받으려면 필요하다.
        # "messages"도 구독한다(2026-08-18) — reasoning 실시간 스트리밍용.
        self.assertEqual(call["kwargs"]["stream_mode"], ["updates", "custom", "messages"])
        self.assertTrue(call["kwargs"]["subgraphs"])
        self.assertEqual(
            call["input_state"], {"messages": [{"role": "user", "content": "안녕"}]}
        )


class ConversationMessagesArgumentTests(SimpleTestCase):
    """apps/chat/api_views.py `_history()`가 만든 앞선 턴을 새 발화 앞에 그대로
    붙이는지 — 안 붙이면 매 턴이 콜드 스타트다. `thread_id`가 없을 때(기본값)의
    동작이다 — thread_id가 있을 때는 아래 ThreadIdArgumentTests를 본다."""

    def test_history_is_prepended_before_the_new_user_message(self):
        runtime = _FakeRuntime()
        history = [
            {"role": "user", "content": "이전 질문"},
            {"role": "assistant", "content": "이전 답"},
        ]

        list(
            DeepAgentStreamAdapter().stream(
                runtime=runtime, user_input="새 질문", conversation_messages=history
            )
        )

        call = runtime.stream_calls[0]
        self.assertEqual(
            call["input_state"]["messages"],
            [*history, {"role": "user", "content": "새 질문"}],
        )

    def test_defaults_to_no_history(self):
        runtime = _FakeRuntime()

        list(DeepAgentStreamAdapter().stream(runtime=runtime, user_input="새 질문"))

        self.assertEqual(
            runtime.stream_calls[0]["input_state"]["messages"],
            [{"role": "user", "content": "새 질문"}],
        )


class ThreadIdArgumentTests(SimpleTestCase):
    """thread_id(2026-08-18, §5 Phase 1: Checkpointer) — `config`로 넘어가는지,
    그리고 conversation_messages를 붙이지 않는지(중복 방지, docstring 참고)."""

    def test_thread_id_present_sets_configurable_thread_id(self):
        runtime = _FakeRuntime()

        list(
            DeepAgentStreamAdapter().stream(
                runtime=runtime, user_input="새 질문", thread_id="SESSION001"
            )
        )

        call = runtime.stream_calls[0]
        self.assertEqual(call["kwargs"]["config"], {"configurable": {"thread_id": "SESSION001"}})

    def test_thread_id_present_ignores_conversation_messages_to_avoid_duplication(self):
        """Checkpointer가 이전 턴을 이미 갖고 있으므로 여기서 conversation_messages를
        또 붙이면 매 턴 중복이 누적된다 — 이번 발화만 보내야 한다."""
        runtime = _FakeRuntime()
        history = [
            {"role": "user", "content": "이전 질문"},
            {"role": "assistant", "content": "이전 답"},
        ]

        list(
            DeepAgentStreamAdapter().stream(
                runtime=runtime,
                user_input="새 질문",
                conversation_messages=history,
                thread_id="SESSION001",
            )
        )

        call = runtime.stream_calls[0]
        self.assertEqual(
            call["input_state"]["messages"], [{"role": "user", "content": "새 질문"}]
        )

    def test_no_thread_id_omits_config_kwarg_entirely(self):
        """thread_id가 없으면(기본값) config 키 자체를 안 보낸다 — `config=None`을
        명시적으로 보내는 것과 구분한다(실제 deepagents/LangGraph 쪽 동작 차이를
        만들지 않기 위해, 조건부로 아예 빼는 compat/deepagents_v075.py의
        backend/store/checkpointer 패턴과 동일하게 맞춘다)."""
        runtime = _FakeRuntime()

        list(DeepAgentStreamAdapter().stream(runtime=runtime, user_input="새 질문"))

        self.assertNotIn("config", runtime.stream_calls[0]["kwargs"])


@tool
def _get_server_time() -> str:
    """서버 시각."""
    return "2026-08-13T12:00:00"


class RealGraphIntegrationTests(SimpleTestCase):
    def test_yields_three_tuples_from_a_real_compiled_graph(self):
        model = _ScriptedModel(responses=[AIMessage(content="안녕하세요")])
        graph = create_deep_agent(model=model, system_prompt="test", tools=[], subagents=[])

        events = list(DeepAgentStreamAdapter().stream(runtime=graph, user_input="hi"))

        self.assertTrue(events)
        for event in events:
            self.assertIsInstance(event, tuple)
            self.assertEqual(len(event), 3)
            namespace, mode, payload = event
            self.assertIsInstance(namespace, tuple)
            self.assertIn(mode, ("updates", "custom", "messages"))
            # "messages"는 (AIMessageChunk, metadata) 2-tuple로 온다 — 그 외
            # 모드만 dict("updates"의 노드별 결과, "custom"의 writer 값)다.
            if mode == "messages":
                self.assertIsInstance(payload, tuple)
                self.assertEqual(len(payload), 2)
            else:
                self.assertIsInstance(payload, dict)


@tool
def _progress_tool(query: str) -> dict:
    """진행 이벤트를 흘리는 도구 — get_stream_writer() 경로가 실제로 살아 있는지 확인용."""
    from langgraph.config import get_stream_writer

    writer = get_stream_writer()
    writer({"type": "stage", "stage": "1/1", "tool_ref": "_progress_tool"})
    return {"result": query}


class CustomModeIntegrationTests(SimpleTestCase):
    """stream_mode에 "custom"이 실제로 켜져서 도구 진행 이벤트가 나오는지 확인한다
    (tools/adapters.py가 쓰는 것과 같은 get_stream_writer() 경로)."""

    def test_custom_progress_event_is_yielded_between_tool_call_and_result(self):
        call1 = AIMessage(content="", tool_calls=[{"name": "_progress_tool", "args": {"query": "q"}, "id": "1"}])
        call2 = AIMessage(content="done")
        model = _ScriptedModel(responses=[call1, call2])
        graph = create_deep_agent(model=model, system_prompt="test", tools=[_progress_tool], subagents=[])

        events = list(DeepAgentStreamAdapter().stream(runtime=graph, user_input="hi"))

        custom_events = [payload for _, mode, payload in events if mode == "custom"]
        self.assertEqual(custom_events, [{"type": "stage", "stage": "1/1", "tool_ref": "_progress_tool"}])
