"""executor.py(AgentExecutor) 단위 테스트.

loader/factory/stream_adapter는 Fake로 주입한다(02 §17.3). raw_event는 실제
스트리밍 스파이크에서 관측된 3-tuple 형태를 그대로 쓰고, events.py의 실제
EventMapper로 변환한다(mock 아님) — "무엇을 조립해 넘기는가"가 아니라 "정말
그 이벤트가 나오는가"까지 확인한다.
"""

from django.test import SimpleTestCase

from services.agent_runtime.context import RuntimeContext
from services.agent_runtime.definitions import AgentDefinition, LoadedAgentDefinition
from services.agent_runtime.events import EVENT_AGENT_STARTED, EVENT_ERROR, EVENT_RESULT
from services.agent_runtime.exceptions import AgentBuildError, InvalidExecutionTargetError
from services.agent_runtime.executor import AgentExecutor, validate_execution_target


def _definition(**overrides) -> AgentDefinition:
    fields = {
        "agent_id": "AG001",
        "agent_version_id": "AV001",
        "name": "테스트",
        "description": "",
        "system_prompt": "",
        "model": "claude-sonnet-5",
        "reasoning_effort": "low",
        "max_iterations": 6,
    }
    fields.update(overrides)
    return AgentDefinition(**fields)


class _FakeLoader:
    def __init__(self, *, loaded=None, error=None):
        self._loaded = loaded or LoadedAgentDefinition(definition=_definition())
        self._error = error
        self.load_calls = []
        self.from_draft_calls = []

    def load(self, *, agent_id, agent_version_id, context):
        self.load_calls.append({"agent_id": agent_id, "agent_version_id": agent_version_id})
        if self._error:
            raise self._error
        return self._loaded

    def from_draft(self, *, draft, context):
        self.from_draft_calls.append(draft)
        if self._error:
            raise self._error
        return self._loaded


class _FakeFactory:
    def __init__(self, *, runtime="RUNTIME", error=None):
        self._runtime = runtime
        self._error = error
        self.build_calls = []

    def build(self, *, definition, subagent_references, context):
        self.build_calls.append({"definition": definition, "context": context})
        if self._error:
            raise self._error
        return self._runtime


class _FakeStreamAdapter:
    def __init__(self, *, raw_events=(), error=None):
        self._raw_events = list(raw_events)
        self._error = error
        self.stream_calls = []

    def stream(self, *, runtime, user_input, conversation_messages=()):
        self.stream_calls.append(
            {
                "runtime": runtime,
                "user_input": user_input,
                "conversation_messages": conversation_messages,
            }
        )
        yield from self._raw_events
        if self._error:
            raise self._error


def _final_answer_raw_event(text: str):
    from langchain_core.messages import AIMessage

    return ((), "updates", {"model": {"messages": [AIMessage(content=text, tool_calls=[])]}})


def _context() -> RuntimeContext:
    return RuntimeContext(account_id="AC001", team_id="TM001", role="leader", run_id="RUN1")


class ValidateExecutionTargetTests(SimpleTestCase):
    def test_rejects_draft_with_agent_id(self):
        with self.assertRaises(InvalidExecutionTargetError):
            validate_execution_target(agent_id="AG001", agent_version_id=None, draft={})

    def test_rejects_missing_version_id_for_saved_execution(self):
        with self.assertRaises(InvalidExecutionTargetError):
            validate_execution_target(agent_id="AG001", agent_version_id=None, draft=None)

    def test_accepts_draft_only(self):
        validate_execution_target(agent_id=None, agent_version_id=None, draft={})

    def test_accepts_saved_version(self):
        validate_execution_target(agent_id="AG001", agent_version_id="AV001", draft=None)


class RunHappyPathTests(SimpleTestCase):
    def test_first_event_is_agent_started_then_result(self):
        loader = _FakeLoader()
        factory = _FakeFactory()
        stream_adapter = _FakeStreamAdapter(raw_events=[_final_answer_raw_event("안녕하세요")])
        executor = AgentExecutor(loader=loader, factory=factory, stream_adapter=stream_adapter)

        events = list(
            executor.run(
                agent_id="AG001", agent_version_id="AV001", user_input="hi", context=_context()
            )
        )

        self.assertEqual(events[0]["type"], EVENT_AGENT_STARTED)
        self.assertEqual(events[0]["run_id"], "RUN1")
        self.assertEqual(events[-1]["type"], EVENT_RESULT)
        self.assertEqual(events[-1]["text"], "안녕하세요")
        self.assertTrue(events[-1]["complete"])

    def test_draft_execution_uses_from_draft(self):
        loader = _FakeLoader()
        factory = _FakeFactory()
        stream_adapter = _FakeStreamAdapter(raw_events=[_final_answer_raw_event("ok")])
        executor = AgentExecutor(loader=loader, factory=factory, stream_adapter=stream_adapter)

        list(
            executor.run(
                agent_id=None,
                agent_version_id=None,
                user_input="hi",
                context=_context(),
                draft={"name": "초안"},
            )
        )

        self.assertEqual(loader.from_draft_calls, [{"name": "초안"}])
        self.assertEqual(loader.load_calls, [])

    def test_uses_fresh_event_mapper_per_run(self):
        """EventMapper는 run마다 새로 만든다 — 위임 추적 상태가 실행 간 안 섞이게."""

        created = []

        def factory_fn():
            from services.agent_runtime.events import EventMapper

            mapper = EventMapper()
            created.append(mapper)
            return mapper

        loader = _FakeLoader()
        factory = _FakeFactory()
        stream_adapter = _FakeStreamAdapter(raw_events=[_final_answer_raw_event("a")])
        executor = AgentExecutor(
            loader=loader, factory=factory, stream_adapter=stream_adapter, event_mapper_factory=factory_fn
        )

        list(executor.run(agent_id="AG001", agent_version_id="AV001", user_input="hi", context=_context()))
        list(executor.run(agent_id="AG001", agent_version_id="AV001", user_input="hi", context=_context()))

        self.assertEqual(len(created), 2)
        self.assertIsNot(created[0], created[1])


class ConversationMessagesThreadingTests(SimpleTestCase):
    """apps/chat/api_views.py의 `_history()`가 만든 앞선 턴을 stream_adapter까지
    그대로 전달하는지 — 이게 없으면 새 엔진은 매 턴이 콜드 스타트다."""

    def test_conversation_messages_reaches_the_stream_adapter(self):
        loader = _FakeLoader()
        factory = _FakeFactory()
        stream_adapter = _FakeStreamAdapter(raw_events=[_final_answer_raw_event("ok")])
        executor = AgentExecutor(loader=loader, factory=factory, stream_adapter=stream_adapter)
        history = ({"role": "user", "content": "이전 질문"}, {"role": "assistant", "content": "이전 답"})

        list(
            executor.run(
                agent_id="AG001",
                agent_version_id="AV001",
                user_input="hi",
                context=_context(),
                conversation_messages=history,
            )
        )

        self.assertEqual(stream_adapter.stream_calls[0]["conversation_messages"], history)

    def test_defaults_to_empty_tuple(self):
        loader = _FakeLoader()
        factory = _FakeFactory()
        stream_adapter = _FakeStreamAdapter(raw_events=[_final_answer_raw_event("ok")])
        executor = AgentExecutor(loader=loader, factory=factory, stream_adapter=stream_adapter)

        list(
            executor.run(
                agent_id="AG001", agent_version_id="AV001", user_input="hi", context=_context()
            )
        )

        self.assertEqual(stream_adapter.stream_calls[0]["conversation_messages"], ())


class RunBuildFailureTests(SimpleTestCase):
    def test_loader_failure_becomes_agent_build_error_before_any_event(self):
        loader = _FakeLoader(error=RuntimeError("DB 다운"))
        factory = _FakeFactory()
        executor = AgentExecutor(loader=loader, factory=factory, stream_adapter=_FakeStreamAdapter())

        with self.assertRaises(AgentBuildError):
            list(
                executor.run(
                    agent_id="AG001", agent_version_id="AV001", user_input="hi", context=_context()
                )
            )

    def test_factory_failure_becomes_agent_build_error(self):
        loader = _FakeLoader()
        factory = _FakeFactory(error=RuntimeError("조립 실패"))
        executor = AgentExecutor(loader=loader, factory=factory, stream_adapter=_FakeStreamAdapter())

        with self.assertRaises(AgentBuildError):
            list(
                executor.run(
                    agent_id="AG001", agent_version_id="AV001", user_input="hi", context=_context()
                )
            )


class RunMidStreamFailureTests(SimpleTestCase):
    def test_exception_during_stream_yields_terminal_error_event_not_raise(self):
        loader = _FakeLoader()
        factory = _FakeFactory()
        stream_adapter = _FakeStreamAdapter(error=RuntimeError("스트림 중 실패"))
        executor = AgentExecutor(loader=loader, factory=factory, stream_adapter=stream_adapter)

        events = list(
            executor.run(
                agent_id="AG001", agent_version_id="AV001", user_input="hi", context=_context()
            )
        )

        self.assertEqual(events[0]["type"], EVENT_AGENT_STARTED)
        self.assertEqual(events[-1]["type"], EVENT_ERROR)
        self.assertTrue(events[-1]["complete"])
        self.assertNotIn("스트림 중 실패", str(events[-1]))
