"""executor.py(AgentExecutor) 단위 테스트.

loader/factory/stream_adapter는 Fake로 주입한다(02 §17.3). raw_event는 실제
스트리밍 스파이크에서 관측된 3-tuple 형태를 그대로 쓰고, events.py의 실제
EventMapper로 변환한다(mock 아님) — "무엇을 조립해 넘기는가"가 아니라 "정말
그 이벤트가 나오는가"까지 확인한다.
"""

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from services.agent_runtime.context import RuntimeContext
from services.agent_runtime.definitions import AgentDefinition, LoadedAgentDefinition
from services.agent_runtime.events import EVENT_AGENT_STARTED, EVENT_ERROR, EVENT_RESULT
from services.agent_runtime.exceptions import AgentBuildError, InvalidExecutionTargetError
from services.agent_runtime.executor import AgentExecutor, _tracing_callbacks, validate_execution_target
from services.agent_runtime.models.factory import ResolvedModelConfig
from services.agent_runtime.runtime_policy import RuntimeCapabilityPolicy

#: `_FakeFactory.build()`의 기본 `resolved_model`(§4순위, Run Snapshot) —
#: 대부분의 executor 테스트는 이 값 자체에 관심이 없어서, 실제 provider
#: 이름을 쓰는 최소 유효값 하나로 통일한다(개별 값을 보는 테스트는
#: `_FakeFactory(resolved_model=...)`로 직접 넘긴다).
_DEFAULT_RESOLVED_MODEL = ResolvedModelConfig(
    provider="anthropic", model_id="claude-sonnet-5", api_key="x", base_url=None, reasoning_effort="low"
)


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
    def __init__(
        self, *, runtime="RUNTIME", resolved_model=None, child_resolved_models=None, error=None
    ):
        self._runtime = runtime
        # 2026-08-19, §4순위(Run Snapshot) — 실제 `AgentRuntimeFactory.build()`가
        # resolved_model을 함께 반환하도록 바뀐 것과 계약을 맞춘다.
        #
        # **2026-08-20에 3-tuple이 됐다**(`17e8c62`, §10 Child Run Snapshot —
        # 세 번째 자리는 Child alias별 resolved_model dict라 `subagent_started`
        # 이벤트에도 provider/endpoint_hash를 채울 수 있다). 이 가짜는 그때 같이
        # 안 고쳐져서 2-tuple을 계속 돌려줬고, `executor.py`가 3개로 언패킹하는
        # 순간 `ValueError: not enough values to unpack`으로 이 파일의 테스트가
        # 통째로 죽어 있었다 — 2026-08-21에 맞춘다. 실제 서명의 정본은
        # `services/agent_runtime/factory.py`의 `build()`다.
        #
        # (jihun·main 두 브랜치가 같은 버그를 각자 찾아 같은 모양으로 고쳤고,
        #  2026-08-21 병합에서 주석만 하나로 합쳤다.)
        #
        # **가짜의 계약이 실물과 어긋나면 테스트는 실물이 아니라 가짜를
        # 검증하게 된다.**
        self._resolved_model = resolved_model or _DEFAULT_RESOLVED_MODEL
        self._child_resolved_models = child_resolved_models or {}
        self._error = error
        self.build_calls = []
        # 2026-08-21, 병렬실행 Phase 1 — `executor.py`가 실행·재개 두 경로에서
        # `self.factory.runtime_policy.max_concurrency`를 읽어
        # `stream_adapter.stream()`에 넘긴다. 실물과 같은 자리에 같은 이름으로
        # 있어야 이 가짜를 쓰는 테스트가 실물의 계약을 검증한다.
        self.runtime_policy = RuntimeCapabilityPolicy()

    def build(self, *, definition, subagent_references, context):
        self.build_calls.append({"definition": definition, "context": context})
        if self._error:
            raise self._error
        return self._runtime, self._resolved_model, self._child_resolved_models


class _FakeStreamAdapter:
    def __init__(self, *, raw_events=(), error=None):
        self._raw_events = list(raw_events)
        self._error = error
        self.stream_calls = []

    def stream(
        self,
        *,
        runtime,
        user_input="",
        conversation_messages=(),
        thread_id=None,
        resume=None,
        callbacks=(),
        trace_metadata=None,
        max_concurrency=None,
    ):
        # `callbacks`/`trace_metadata`는 2026-08-19 Langfuse 연동으로 늘었다
        # (`executor.py`가 항상 넘긴다 — 키가 없으면 각각 빈 시퀀스/`None`).
        # `max_concurrency`는 2026-08-21 병렬실행 Phase 1로 늘었다(같은 이유로
        # `executor.py`가 실행·재개 두 경로 모두에서 항상 넘긴다).
        # `user_input`은 재개(`resume()`) 호출에서는 안 넘어온다(§0순위 HITL
        # resume API). 실제 `DeepAgentStreamAdapter.stream()`과 시그니처를
        # 맞추지 않으면 `TypeError: unexpected keyword argument`로 이 테스트
        # 더블을 쓰는 테스트 전부가 깨진다.
        self.stream_calls.append(
            {
                "runtime": runtime,
                "user_input": user_input,
                "conversation_messages": conversation_messages,
                "thread_id": thread_id,
                "resume": resume,
                "callbacks": callbacks,
                "trace_metadata": trace_metadata,
                "max_concurrency": max_concurrency,
            }
        )
        yield from self._raw_events
        if self._error:
            raise self._error


def _final_answer_raw_event(text: str):
    from langchain_core.messages import AIMessage

    return ((), "updates", {"model": {"messages": [AIMessage(content=text, tool_calls=[])]}})


def _context(**overrides) -> RuntimeContext:
    fields = {"account_id": "AC001", "team_id": "TM001", "role": "leader", "run_id": "RUN1"}
    fields.update(overrides)
    return RuntimeContext(**fields)


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


class TracingCallbackTests(SimpleTestCase):
    @patch("services.agent_runtime.tracing.callbacks.get_langfuse_callback")
    def test_only_langfuse_callback_is_loaded(self, get_langfuse):
        from services.agent_runtime.tracing import callbacks as tracing_callbacks

        langfuse_callback = object()
        get_langfuse.return_value = langfuse_callback

        self.assertEqual(_tracing_callbacks(), [langfuse_callback])
        self.assertFalse(hasattr(tracing_callbacks, "get_langsmith_callback"))

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

    def test_agent_started_carries_resolved_provider_and_endpoint_hash(self):
        """2026-08-19, §4순위(Run Snapshot) — `factory.build()`가 반환한
        `resolved_model`이 `EVENT_AGENT_STARTED`에 실려야 `tracing/__init__.py`가
        `agent_run.resolved_provider`/`resolved_endpoint_hash`로 적재할 수
        있다."""
        loader = _FakeLoader()
        resolved_model = ResolvedModelConfig(
            provider="openai_compatible",
            model_id="claude-x",
            api_key="k",
            base_url="https://team-custom.example.com/v1",
            reasoning_effort="low",
        )
        factory = _FakeFactory(resolved_model=resolved_model)
        stream_adapter = _FakeStreamAdapter(raw_events=[_final_answer_raw_event("ok")])
        executor = AgentExecutor(loader=loader, factory=factory, stream_adapter=stream_adapter)

        events = list(
            executor.run(
                agent_id="AG001", agent_version_id="AV001", user_input="hi", context=_context()
            )
        )

        started = events[0]
        self.assertEqual(started["resolved_provider"], "openai_compatible")
        self.assertIsNotNone(started["resolved_endpoint_hash"])
        # base_url 원문이 이벤트에 그대로 실리면 안 된다(사내망 주소 노출 방지).
        self.assertNotIn("team-custom.example.com", started["resolved_endpoint_hash"])

    def test_agent_started_endpoint_hash_is_none_without_a_custom_base_url(self):
        loader = _FakeLoader()
        resolved_model = ResolvedModelConfig(
            provider="anthropic", model_id="claude-sonnet-5", api_key="k", base_url=None, reasoning_effort="low"
        )
        factory = _FakeFactory(resolved_model=resolved_model)
        stream_adapter = _FakeStreamAdapter(raw_events=[_final_answer_raw_event("ok")])
        executor = AgentExecutor(loader=loader, factory=factory, stream_adapter=stream_adapter)

        events = list(
            executor.run(
                agent_id="AG001", agent_version_id="AV001", user_input="hi", context=_context()
            )
        )

        self.assertIsNone(events[0]["resolved_endpoint_hash"])

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


class ToolRefsOverrideTests(SimpleTestCase):
    """`tool_refs_override`(2026-08-18, Chat "+" 버튼) — 세션이 도구를
    커스터마이즈했으면 로드된 정의의 `tool_refs`를 그 자리에서 갈아 끼운다.
    저장된 정의(`loaded.definition`)는 원본 그대로 두고 `factory.build()`에
    넘기는 사본만 바꾼다."""

    def test_none_leaves_loaded_definition_untouched(self):
        loaded = LoadedAgentDefinition(definition=_definition(tool_refs=("document_search",)))
        loader = _FakeLoader(loaded=loaded)
        factory = _FakeFactory()
        stream_adapter = _FakeStreamAdapter(raw_events=[_final_answer_raw_event("ok")])
        executor = AgentExecutor(loader=loader, factory=factory, stream_adapter=stream_adapter)

        list(
            executor.run(
                agent_id="AG001", agent_version_id="AV001", user_input="hi", context=_context()
            )
        )

        self.assertEqual(factory.build_calls[0]["definition"].tool_refs, ("document_search",))

    def test_override_replaces_tool_refs_for_this_run_only(self):
        loaded = LoadedAgentDefinition(definition=_definition(tool_refs=("document_search",)))
        loader = _FakeLoader(loaded=loaded)
        factory = _FakeFactory()
        stream_adapter = _FakeStreamAdapter(raw_events=[_final_answer_raw_event("ok")])
        executor = AgentExecutor(loader=loader, factory=factory, stream_adapter=stream_adapter)

        list(
            executor.run(
                agent_id="AG001",
                agent_version_id="AV001",
                user_input="hi",
                context=_context(),
                tool_refs_override=["people_list", "web_search"],
            )
        )

        self.assertEqual(
            factory.build_calls[0]["definition"].tool_refs, ("people_list", "web_search")
        )
        # 원본 정의 객체는 안 바뀐다 — 불변 dataclass라 dataclasses.replace()가
        # 사본을 만든다는 것의 확인.
        self.assertEqual(loaded.definition.tool_refs, ("document_search",))

    def test_empty_override_turns_off_all_tools(self):
        """빈 리스트는 "이 대화에서 도구를 전부 껐다"는 실제 선택이라 `None`과
        다르게 다뤄야 한다 — `if tool_refs_override is not None` 분기 확인."""
        loaded = LoadedAgentDefinition(definition=_definition(tool_refs=("document_search",)))
        loader = _FakeLoader(loaded=loaded)
        factory = _FakeFactory()
        stream_adapter = _FakeStreamAdapter(raw_events=[_final_answer_raw_event("ok")])
        executor = AgentExecutor(loader=loader, factory=factory, stream_adapter=stream_adapter)

        list(
            executor.run(
                agent_id="AG001",
                agent_version_id="AV001",
                user_input="hi",
                context=_context(),
                tool_refs_override=[],
            )
        )

        self.assertEqual(factory.build_calls[0]["definition"].tool_refs, ())


class MaxConcurrencyThreadingTests(SimpleTestCase):
    """2026-08-21, 병렬실행 Phase 1 — 정책의 동시 실행 상한이 stream_adapter까지
    실제로 도달하는지(`2026-08-20_02` §5.1).

    여기서 끊기면 상한을 정해 놓고도 LangGraph는 무제한으로 돈다 — 값이
    정책에 있다는 것만으로는 아무것도 보장되지 않는다.
    """

    def test_run_passes_the_policy_value_to_the_stream_adapter(self):
        factory = _FakeFactory()
        factory.runtime_policy = RuntimeCapabilityPolicy(max_concurrency=7)
        stream_adapter = _FakeStreamAdapter(raw_events=[_final_answer_raw_event("ok")])
        executor = AgentExecutor(
            loader=_FakeLoader(), factory=factory, stream_adapter=stream_adapter
        )

        list(
            executor.run(
                agent_id="AG001", agent_version_id="AV001", user_input="hi", context=_context()
            )
        )

        self.assertEqual(stream_adapter.stream_calls[0]["max_concurrency"], 7)

    def test_resume_also_passes_it(self):
        """승인 후 한꺼번에 풀리는 복수 side-effect 호출이야말로 상한이 필요한
        자리다(§5.1·§8) — 재개 경로가 빠지면 안 된다."""
        factory = _FakeFactory()
        factory.runtime_policy = RuntimeCapabilityPolicy(max_concurrency=5)
        stream_adapter = _FakeStreamAdapter(raw_events=[_final_answer_raw_event("ok")])
        executor = AgentExecutor(
            loader=_FakeLoader(), factory=factory, stream_adapter=stream_adapter
        )

        list(
            executor.resume(
                agent_id="AG001",
                agent_version_id="AV001",
                decisions=[{"type": "approve"}],
                context=_context(session_id="SESSION001"),
            )
        )

        self.assertEqual(stream_adapter.stream_calls[0]["max_concurrency"], 5)


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


class ThreadIdThreadingTests(SimpleTestCase):
    """context.session_id가 stream_adapter까지 thread_id로 그대로 전달되는지
    (2026-08-18, §5 Phase 1: Checkpointer) — Checkpointer가 이 값으로 상태를
    저장/재개하므로 여기서 빠지면 Phase 1 전체가 동작하지 않는다."""

    def test_context_session_id_reaches_the_stream_adapter_as_thread_id(self):
        loader = _FakeLoader()
        factory = _FakeFactory()
        stream_adapter = _FakeStreamAdapter(raw_events=[_final_answer_raw_event("ok")])
        executor = AgentExecutor(loader=loader, factory=factory, stream_adapter=stream_adapter)

        list(
            executor.run(
                agent_id="AG001",
                agent_version_id="AV001",
                user_input="hi",
                context=_context(session_id="SESSION001"),
            )
        )

        self.assertEqual(stream_adapter.stream_calls[0]["thread_id"], "SESSION001")

    def test_missing_session_id_passes_none_through(self):
        """session_id 없는 context(예: 세션이 없는 스크립트 실행)는 thread_id로
        None을 그대로 넘긴다 — stream_adapter가 예전과 동일하게 동작하는
        분기(콜드 스타트, conversation_messages 그대로 붙임)를 타게 된다."""
        loader = _FakeLoader()
        factory = _FakeFactory()
        stream_adapter = _FakeStreamAdapter(raw_events=[_final_answer_raw_event("ok")])
        executor = AgentExecutor(loader=loader, factory=factory, stream_adapter=stream_adapter)

        list(
            executor.run(
                agent_id="AG001", agent_version_id="AV001", user_input="hi", context=_context()
            )
        )

        self.assertIsNone(stream_adapter.stream_calls[0]["thread_id"])


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

    def test_error_event_carries_the_usage_spent_before_the_failure(self):
        """실패해도 비용은 이미 나갔다(2026-08-21).

        `error` 이벤트가 누계를 안 실으면 `tracing/`이 그 실행의 토큰을
        `None`으로 닫아, 실패한 실행만 Usage 합계에서 조용히 빠진다.
        """
        loader = _FakeLoader()
        factory = _FakeFactory()
        stream_adapter = _FakeStreamAdapter(error=RuntimeError("스트림 중 실패"))
        executor = AgentExecutor(loader=loader, factory=factory, stream_adapter=stream_adapter)

        events = list(
            executor.run(
                agent_id="AG001", agent_version_id="AV001", user_input="hi", context=_context()
            )
        )

        # 모델을 한 번도 못 부르고 죽은 실행이라 누계는 비어 있다 — 그래도
        # 칸 자체는 실려야 `tracing/`이 같은 규칙으로 적는다.
        self.assertEqual(events[-1]["iterations"], 0)
        self.assertIsNone(events[-1]["token_in"])
        self.assertIsNone(events[-1]["token_out"])


class ResumeTests(SimpleTestCase):
    """`AgentExecutor.resume()`(2026-08-19 추가, §0순위 — HITL resume API) —
    `run()`과 조립 규칙은 같지만 `EVENT_AGENT_STARTED`를 안 내고, 멈췄던
    실행의 `run_id`를 반드시 이미 갖고 있어야 하며, `stream_adapter.stream()`을
    `resume=`으로 부른다."""

    def test_requires_context_run_id(self):
        loader = _FakeLoader()
        factory = _FakeFactory()
        executor = AgentExecutor(loader=loader, factory=factory, stream_adapter=_FakeStreamAdapter())

        with self.assertRaises(ValueError):
            list(
                executor.resume(
                    agent_id="AG001",
                    agent_version_id="AV001",
                    context=_context(run_id=None),
                    decisions=[{"type": "approve"}],
                )
            )

    def test_does_not_emit_agent_started(self):
        """재개는 '새로 시작'이 아니라 '이어서 진행'이다 — trace_events()가 새
        agent_run 행을 또 만들면(run_id PK 충돌) 안 된다."""
        loader = _FakeLoader()
        factory = _FakeFactory()
        stream_adapter = _FakeStreamAdapter(raw_events=[_final_answer_raw_event("등록했습니다")])
        executor = AgentExecutor(loader=loader, factory=factory, stream_adapter=stream_adapter)

        events = list(
            executor.resume(
                agent_id="AG001",
                agent_version_id="AV001",
                context=_context(run_id="RUN1"),
                decisions=[{"type": "approve"}],
            )
        )

        self.assertNotIn(EVENT_AGENT_STARTED, [e["type"] for e in events])
        self.assertEqual(events[-1]["type"], EVENT_RESULT)

    def test_decisions_reach_stream_adapter_as_resume_dict(self):
        loader = _FakeLoader()
        factory = _FakeFactory()
        stream_adapter = _FakeStreamAdapter(raw_events=[_final_answer_raw_event("ok")])
        executor = AgentExecutor(loader=loader, factory=factory, stream_adapter=stream_adapter)

        list(
            executor.resume(
                agent_id="AG001",
                agent_version_id="AV001",
                context=_context(run_id="RUN1"),
                decisions=[{"type": "reject", "message": "지금은 안 돼요"}],
            )
        )

        self.assertEqual(
            stream_adapter.stream_calls[0]["resume"],
            {"decisions": [{"type": "reject", "message": "지금은 안 돼요"}]},
        )

    def test_trace_resume_state_is_restored_before_stream_conversion(self):
        loader = _FakeLoader()
        factory = _FakeFactory()
        stream_adapter = _FakeStreamAdapter(raw_events=[_final_answer_raw_event("ok")])
        mapper = MagicMock()
        mapper.convert.return_value = []
        executor = AgentExecutor(
            loader=loader,
            factory=factory,
            stream_adapter=stream_adapter,
            event_mapper_factory=lambda: mapper,
        )
        state = {
            "pending_subagents": {"delegate-1": {"run_id": "RUN-CHILD"}},
            "pending_tool_calls": [{"tool_call_id": "call-1", "run_id": "RUN1"}],
        }

        list(
            executor.resume(
                agent_id="AG001",
                agent_version_id="AV001",
                context=_context(run_id="RUN1"),
                decisions=[{"type": "approve"}],
                trace_resume_state=state,
            )
        )

        mapper.restore_hitl_state.assert_called_once_with(state)
        mapper.convert.assert_called_once()

    def test_context_session_id_reaches_the_stream_adapter_as_thread_id(self):
        loader = _FakeLoader()
        factory = _FakeFactory()
        stream_adapter = _FakeStreamAdapter(raw_events=[_final_answer_raw_event("ok")])
        executor = AgentExecutor(loader=loader, factory=factory, stream_adapter=stream_adapter)

        list(
            executor.resume(
                agent_id="AG001",
                agent_version_id="AV001",
                context=_context(run_id="RUN1", session_id="SESSION001"),
                decisions=[{"type": "approve"}],
            )
        )

        self.assertEqual(stream_adapter.stream_calls[0]["thread_id"], "SESSION001")

    def test_draft_resume_uses_from_draft(self):
        loader = _FakeLoader()
        factory = _FakeFactory()
        stream_adapter = _FakeStreamAdapter(raw_events=[_final_answer_raw_event("ok")])
        executor = AgentExecutor(loader=loader, factory=factory, stream_adapter=stream_adapter)

        list(
            executor.resume(
                agent_id=None,
                agent_version_id=None,
                context=_context(run_id="RUN1"),
                decisions=[{"type": "approve"}],
                draft={"name": "초안"},
            )
        )

        self.assertEqual(loader.from_draft_calls, [{"name": "초안"}])
        self.assertEqual(loader.load_calls, [])

    def test_tool_refs_override_replaces_definition_for_rebuild(self):
        """멈췄던 실행과 같은 도구 구성으로 다시 조립해야 재개가 그 실행의
        연속으로 보인다."""
        loaded = LoadedAgentDefinition(definition=_definition(tool_refs=("document_search",)))
        loader = _FakeLoader(loaded=loaded)
        factory = _FakeFactory()
        stream_adapter = _FakeStreamAdapter(raw_events=[_final_answer_raw_event("ok")])
        executor = AgentExecutor(loader=loader, factory=factory, stream_adapter=stream_adapter)

        list(
            executor.resume(
                agent_id="AG001",
                agent_version_id="AV001",
                context=_context(run_id="RUN1"),
                decisions=[{"type": "approve"}],
                tool_refs_override=["people_list"],
            )
        )

        self.assertEqual(factory.build_calls[0]["definition"].tool_refs, ("people_list",))

    def test_loader_failure_becomes_agent_build_error(self):
        loader = _FakeLoader(error=RuntimeError("DB 다운"))
        factory = _FakeFactory()
        executor = AgentExecutor(loader=loader, factory=factory, stream_adapter=_FakeStreamAdapter())

        with self.assertRaises(AgentBuildError):
            list(
                executor.resume(
                    agent_id="AG001",
                    agent_version_id="AV001",
                    context=_context(run_id="RUN1"),
                    decisions=[{"type": "approve"}],
                )
            )

    def test_mid_stream_failure_yields_terminal_error_event_not_raise(self):
        loader = _FakeLoader()
        factory = _FakeFactory()
        stream_adapter = _FakeStreamAdapter(error=RuntimeError("재개 중 실패"))
        executor = AgentExecutor(loader=loader, factory=factory, stream_adapter=stream_adapter)

        events = list(
            executor.resume(
                agent_id="AG001",
                agent_version_id="AV001",
                context=_context(run_id="RUN1"),
                decisions=[{"type": "approve"}],
            )
        )

        self.assertEqual(events[-1]["type"], EVENT_ERROR)
        self.assertTrue(events[-1]["complete"])
        self.assertEqual(events[-1]["run_id"], "RUN1")
        self.assertNotIn("재개 중 실패", str(events[-1]))
