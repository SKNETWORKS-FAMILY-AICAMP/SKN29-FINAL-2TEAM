"""events.py(EventMapper) 단위 테스트.

실제 langchain_core 메시지 객체(AIMessage/ToolMessage)로 raw_event를 만들고,
Mock 없이 진짜 EventMapper.convert()/_classify()를 돌린다. `convert()`는 항상
리스트를 반환한다(2026-08-14 재설계 — 병렬 tool_calls를 이벤트 여러 개로 펼치기
위해) — 한 이벤트만 기대하는 테스트는 `events[0]`으로 꺼내 검증한다.

부모(Root)가 위임 없이 자기 도구를 직접 호출하는 경로, 그리고 병렬 위임/도구
호출(모델이 한 AIMessage에 tool_calls를 여러 개 담아 내는 경우)을 특히 중점적으로
검증한다 — langgraph의 ToolNode가 루트/서브그래프를 구분하지 않는다는 근거, 그리고
`executor.map()`으로 tool_calls를 동시 실행한다는 근거(§ 모듈 docstring)를 그대로
반영한다.
"""

from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from django.test import SimpleTestCase
from langgraph.types import Interrupt

from services.agent_runtime.definitions import SubagentDefinition
from services.agent_runtime.events import (
    EVENT_AWAITING_CONFIRMATION,
    EVENT_REASONING,
    EVENT_RESULT,
    EVENT_SUBAGENT_COMPLETED,
    EVENT_SUBAGENT_STARTED,
    EVENT_TOOL_COMPLETED,
    EVENT_TOOL_PROGRESS,
    EVENT_TOOL_STARTED,
    RETRIEVED_DOC_IDS_MAX,
    EventMapper,
)


class _Definition:
    agent_id = "AG001"
    agent_version_id = "AV001"
    subagents = ()


def _subagent_definition(**overrides) -> SubagentDefinition:
    fields = {
        "agent_id": "AG011",
        "agent_version_id": "AV023",
        "name": "Jira 등록 에이전트",
        "description": "",
        "system_prompt": "",
        "model": "claude-sonnet-5",
        "reasoning_effort": "low",
        "max_iterations": 6,
        "alias": "jira_writer",
        "delegation_description": "Jira 이슈를 생성한다.",
    }
    fields.update(overrides)
    return SubagentDefinition(**fields)


class _DefinitionWithSubagents:
    """Child 정의(`subagents`)를 실은 루트 정의 — alias→Child 조회 테스트용."""

    agent_id = "AG001"
    agent_version_id = "AV001"

    def __init__(self, *subagents):
        self.subagents = subagents


class _Context:
    run_id = "RUN1"


def _raw(namespace, node_name, message):
    return (namespace, "updates", {node_name: {"messages": [message]}})


def _convert_one(mapper, raw):
    """이번 raw_event에서 이벤트가 정확히 1개 나온다고 기대할 때 쓰는 헬퍼."""
    events = mapper.convert(raw, definition=_Definition(), context=_Context())
    assert len(events) == 1, f"이벤트 1개를 기대했는데 {len(events)}개 나옴: {events}"
    return events[0]


class ConvertMalformedInputTests(SimpleTestCase):
    def test_ignores_non_tuple(self):
        self.assertEqual(EventMapper().convert("not-a-tuple", definition=_Definition(), context=_Context()), [])

    def test_ignores_non_updates_mode(self):
        raw = ((), "messages", {"model": {"messages": []}})
        self.assertEqual(EventMapper().convert(raw, definition=_Definition(), context=_Context()), [])


class ParentDelegationTests(SimpleTestCase):
    def test_delegation_tool_call_becomes_subagent_started(self):
        message = AIMessage(
            content="",
            tool_calls=[{"name": "task", "args": {"subagent_type": "researcher", "description": "조사"}, "id": "1"}],
        )
        raw = _raw((), "model", message)

        event = _convert_one(EventMapper(), raw)

        self.assertEqual(event["type"], EVENT_SUBAGENT_STARTED)
        self.assertEqual(event["subagent_alias"], "researcher")
        self.assertEqual(event["task_summary"], "조사")

    def test_subagent_started_gets_its_own_run_id_distinct_from_parent(self):
        message = AIMessage(
            content="",
            tool_calls=[{"name": "task", "args": {"subagent_type": "researcher", "description": "조사"}, "id": "1"}],
        )
        raw = _raw((), "model", message)

        event = _convert_one(EventMapper(), raw)

        self.assertIsNotNone(event["run_id"])
        self.assertNotEqual(event["run_id"], "RUN1")
        self.assertEqual(event["parent_run_id"], "RUN1")

    def test_delegation_tool_message_becomes_subagent_completed(self):
        mapper = EventMapper()
        start = AIMessage(
            content="",
            tool_calls=[{"name": "task", "args": {"subagent_type": "researcher", "description": "조사"}, "id": "1"}],
        )
        started = _convert_one(mapper, _raw((), "model", start))

        done = ToolMessage(name="task", content="완료", tool_call_id="1")
        event = _convert_one(mapper, _raw((), "tools", done))

        self.assertEqual(event["type"], EVENT_SUBAGENT_COMPLETED)
        self.assertEqual(event["subagent_alias"], "researcher")
        self.assertEqual(event["status"], "DONE")
        self.assertNotIn("error_code", event)
        # completed는 started와 같은 run_id를 이어받는다 — 별개 id가 아니다.
        self.assertEqual(event["run_id"], started["run_id"])
        self.assertEqual(event["parent_run_id"], "RUN1")

    def test_delegation_failure_with_unknown_subagent_type_becomes_failed_not_done(self):
        # deepagents==0.7.5는 존재하지 않는 subagent_type을 예외가 아니라
        # status="success"인 평범한 ToolMessage로 감싸 돌려준다(설치된
        # deepagents/middleware/subagents.py의 task()/atask() 실측). 이걸
        # 걸러내지 않으면 위임 실패가 DONE으로 표시된다 — 회귀 테스트.
        mapper = EventMapper()
        start = AIMessage(
            content="",
            tool_calls=[{"name": "task", "args": {"subagent_type": "no_such_agent", "description": "조사"}, "id": "1"}],
        )
        mapper.convert(_raw((), "model", start), definition=_Definition(), context=_Context())

        failed = ToolMessage(
            name="task",
            content=(
                "We cannot invoke subagent no_such_agent because it does not exist, "
                "the only allowed types are `researcher`, `writer`"
            ),
            tool_call_id="1",
        )
        event = _convert_one(mapper, _raw((), "tools", failed))

        self.assertEqual(event["type"], EVENT_SUBAGENT_COMPLETED)
        self.assertEqual(event["subagent_alias"], "no_such_agent")
        self.assertEqual(event["status"], "FAILED")
        self.assertEqual(event["error_code"], "SUBAGENT_EXECUTION_FAILED")


class SubagentIdentityTests(SimpleTestCase):
    """subagent_started/subagent_completed의 agent_id/agent_version_id/
    subagent_name은 루트가 아니라 Child 자신의 값이어야 한다(§14.2/§14.3).
    `definition.subagents`에서 alias로 찾는다(2026-08-14 추가)."""

    def test_subagent_started_uses_the_childs_own_identity_not_the_roots(self):
        definition = _DefinitionWithSubagents(_subagent_definition())
        message = AIMessage(
            content="",
            tool_calls=[{"name": "task", "args": {"subagent_type": "jira_writer", "description": "이슈 생성"}, "id": "1"}],
        )
        raw = _raw((), "model", message)

        events = EventMapper().convert(raw, definition=definition, context=_Context())

        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["agent_id"], "AG011")
        self.assertEqual(event["agent_version_id"], "AV023")
        self.assertEqual(event["subagent_name"], "Jira 등록 에이전트")
        # 루트(AG001/AV001)가 아니어야 한다 — 이게 이번에 고친 버그다.
        self.assertNotEqual(event["agent_id"], definition.agent_id)

    def test_subagent_completed_carries_the_same_childs_identity_as_started(self):
        mapper = EventMapper()
        definition = _DefinitionWithSubagents(_subagent_definition())
        start = AIMessage(
            content="",
            tool_calls=[{"name": "task", "args": {"subagent_type": "jira_writer", "description": "이슈 생성"}, "id": "1"}],
        )
        mapper.convert(_raw((), "model", start), definition=definition, context=_Context())

        done = ToolMessage(name="task", content="완료", tool_call_id="1")
        events = mapper.convert(_raw((), "tools", done), definition=definition, context=_Context())

        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["agent_id"], "AG011")
        self.assertEqual(event["agent_version_id"], "AV023")
        self.assertEqual(event["subagent_name"], "Jira 등록 에이전트")

    def test_two_subagents_each_get_their_own_identity_not_swapped(self):
        definition = _DefinitionWithSubagents(
            _subagent_definition(agent_id="AG011", agent_version_id="AV023", name="Jira 등록 에이전트", alias="jira_writer"),
            _subagent_definition(agent_id="AG012", agent_version_id="AV024", name="문서 검색 에이전트", alias="researcher"),
        )
        message = AIMessage(
            content="",
            tool_calls=[
                {"name": "task", "args": {"subagent_type": "jira_writer", "description": "이슈 생성"}, "id": "1"},
                {"name": "task", "args": {"subagent_type": "researcher", "description": "조사"}, "id": "2"},
            ],
        )
        raw = _raw((), "model", message)

        events = EventMapper().convert(raw, definition=definition, context=_Context())
        by_alias = {e["subagent_alias"]: e for e in events}

        self.assertEqual(by_alias["jira_writer"]["agent_id"], "AG011")
        self.assertEqual(by_alias["researcher"]["agent_id"], "AG012")

    def test_missing_subagent_definition_falls_back_to_root_identity_without_crashing(self):
        """`definition.subagents`가 비어 있거나 못 찾는 경우(방어적 폴백) —
        기존 테스트 다수가 쓰는 `_Definition`(subagents=())도 이 경로를 탄다."""
        message = AIMessage(
            content="",
            tool_calls=[{"name": "task", "args": {"subagent_type": "researcher", "description": "조사"}, "id": "1"}],
        )
        raw = _raw((), "model", message)

        event = _convert_one(EventMapper(), raw)

        self.assertEqual(event["agent_id"], "AG001")
        self.assertEqual(event["agent_version_id"], "AV001")
        self.assertIsNone(event["subagent_name"])


class ParallelDelegationTests(SimpleTestCase):
    """모델이 한 AIMessage에 위임 tool_calls를 여러 개 담아 내는 경우
    (2026-08-14 재설계 전에는 tool_calls[0]만 보고 나머지는 조용히 버려졌다)."""

    def test_two_delegations_in_one_message_both_become_subagent_started(self):
        message = AIMessage(
            content="",
            tool_calls=[
                {"name": "task", "args": {"subagent_type": "researcher", "description": "조사"}, "id": "1"},
                {"name": "task", "args": {"subagent_type": "writer", "description": "작성"}, "id": "2"},
            ],
        )
        raw = _raw((), "model", message)

        events = EventMapper().convert(raw, definition=_Definition(), context=_Context())

        self.assertEqual(len(events), 2)
        types = {e["type"] for e in events}
        self.assertEqual(types, {EVENT_SUBAGENT_STARTED})
        aliases = {e["subagent_alias"] for e in events}
        self.assertEqual(aliases, {"researcher", "writer"})
        # 서로 다른 위임이니 run_id도 서로 달라야 한다.
        self.assertNotEqual(events[0]["run_id"], events[1]["run_id"])

    def test_out_of_order_completion_matches_by_tool_call_id_not_start_order(self):
        """실측(langgraph ToolNode._func가 executor.map()으로 tool_calls를 동시
        실행)대로, 나중에 시작한 위임(writer)이 먼저 끝나도 정확히 매칭돼야 한다
        — FIFO였다면 이 경우 researcher의 완료로 잘못 표시됐을 것이다."""
        mapper = EventMapper()
        start = AIMessage(
            content="",
            tool_calls=[
                {"name": "task", "args": {"subagent_type": "researcher", "description": "조사"}, "id": "1"},
                {"name": "task", "args": {"subagent_type": "writer", "description": "작성"}, "id": "2"},
            ],
        )
        started = mapper.convert(_raw((), "model", start), definition=_Definition(), context=_Context())
        started_by_alias = {e["subagent_alias"]: e for e in started}

        # writer(나중에 시작, id=2)가 researcher(먼저 시작, id=1)보다 먼저 끝난다.
        writer_done = ToolMessage(name="task", content="완료", tool_call_id="2")
        event = _convert_one(mapper, _raw((), "tools", writer_done))

        self.assertEqual(event["subagent_alias"], "writer")
        self.assertEqual(event["run_id"], started_by_alias["writer"]["run_id"])

        researcher_done = ToolMessage(name="task", content="완료", tool_call_id="1")
        event2 = _convert_one(mapper, _raw((), "tools", researcher_done))

        self.assertEqual(event2["subagent_alias"], "researcher")
        self.assertEqual(event2["run_id"], started_by_alias["researcher"]["run_id"])


class ParentFinalAnswerTests(SimpleTestCase):
    def test_tool_call_with_preamble_attaches_korean_user_update(self):
        message = AIMessage(
            content="현재 자료를 검색해 확인하겠습니다.",
            tool_calls=[{"name": "document_search", "args": {"query": "q"}, "id": "1"}],
        )

        events = EventMapper().convert(_raw((), "model", message), definition=_Definition(), context=_Context())

        self.assertEqual([event["type"] for event in events], [EVENT_TOOL_STARTED])
        self.assertEqual(events[0]["user_update"], "현재 자료를 검색해 확인하겠습니다.")
        self.assertEqual(events[0]["user_update_source"], "model")

    def test_tool_call_without_preamble_emits_korean_fallback(self):
        message = AIMessage(
            content="",
            tool_calls=[{"name": "document_search", "args": {"query": "q"}, "id": "1"}],
        )

        events = EventMapper().convert(_raw((), "model", message), definition=_Definition(), context=_Context())

        self.assertEqual([event["type"] for event in events], [EVENT_TOOL_STARTED])
        self.assertEqual(events[0]["user_update_source"], "application_fallback")
        self.assertIn("도구", events[0]["user_update"])

    def test_no_tool_calls_with_content_becomes_result(self):
        message = AIMessage(content="안녕하세요", tool_calls=[])
        raw = _raw((), "model", message)

        event = _convert_one(EventMapper(), raw)

        self.assertEqual(event["type"], EVENT_RESULT)
        self.assertEqual(event["text"], "안녕하세요")
        self.assertTrue(event["complete"])

    def test_openai_responses_reasoning_content_blocks_yield_plain_text_not_raw_list(self):
        """2026-08-14 실측 발견 — OpenAI Responses API 경로(추론 모델, 예:
        gpt-5.6-luna)는 `AIMessage.content`를 평문이 아니라 `[{'type':
        'reasoning', ...}, {'type': 'text', ...}]` 콘텐츠 블록 리스트로 채운다.
        `scripts/team_status_agent.py`로 라이브 실행해 `result.text`에 그 원시
        리스트(`[{'id': 'rs_...', ...`)가 그대로 새는 걸 재현했다 — `.content`가
        아니라 `.text`(langchain-core `BaseMessage.text`)를 써야 텍스트 블록만
        골라 평문으로 합친다."""
        message = AIMessage(
            content=[
                {"type": "reasoning", "id": "rs_048655f9aa657068", "summary": []},
                {"type": "text", "text": "이번 달 팀원별 업무 부하는 아래와 같습니다."},
            ],
            tool_calls=[],
        )
        raw = _raw((), "model", message)

        event = _convert_one(EventMapper(), raw)

        self.assertEqual(event["type"], EVENT_RESULT)
        self.assertEqual(event["text"], "이번 달 팀원별 업무 부하는 아래와 같습니다.")
        self.assertIsInstance(event["text"], str)


def _delta(namespace, content_blocks, *, node_name="model"):
    """`stream_mode="messages"`의 raw_event 모양 — (namespace, "messages",
    (AIMessageChunk, metadata)). 실측(2026-08-18)으로 확인한 그대로다."""
    return (namespace, "messages", (AIMessageChunk(content=content_blocks), {"langgraph_node": node_name}))


def _reasoning_block(*, block_index, summary_index, text):
    return {
        "type": "reasoning",
        "index": block_index,
        "summary": [{"index": summary_index, "type": "summary_text", "text": text}],
    }


class ReasoningEventTests(SimpleTestCase):
    """`_classify_reasoning_delta()` — `stream_mode="messages"`의 조각 단위
    reasoning 델타를 읽는 경로(2026-08-18 재설계). 완성된 `AIMessage`가
    아니라 `AIMessageChunk` 하나하나가 입력이다 — 실측으로 확인한 실제 raw
    모양(`services/agent_runtime/events.py` 모듈 docstring "reasoning 실시간
    스트리밍" 절)을 그대로 재현한다."""

    def test_delta_yields_reasoning_event_with_append_false_first_time(self):
        raw = _delta((), [_reasoning_block(block_index=0, summary_index=0, text="사용자가 요청한 범위부터 좁혀야 한다.")])

        event = _convert_one(EventMapper(), raw)

        self.assertEqual(event["type"], EVENT_REASONING)
        self.assertEqual(event["text"], "사용자가 요청한 범위부터 좁혀야 한다.")
        self.assertFalse(event["append"])
        self.assertIsNone(event["subagent_alias"])

    def test_same_paragraph_second_delta_sets_append_true(self):
        mapper = EventMapper()
        mapper.convert(
            _delta((), [_reasoning_block(block_index=0, summary_index=0, text="첫")]),
            definition=_Definition(),
            context=_Context(),
        )

        event = _convert_one(
            mapper, _delta((), [_reasoning_block(block_index=0, summary_index=0, text="째,")])
        )

        self.assertTrue(event["append"])
        self.assertEqual(event["text"], "째,")

    def test_new_summary_index_starts_a_new_step(self):
        """OpenAI가 reasoning을 여러 문단으로 나눠 내면 문단마다 summary_index가
        다르다 — 이어붙이지 않고 새 단계로 띄운다."""
        mapper = EventMapper()
        mapper.convert(
            _delta((), [_reasoning_block(block_index=0, summary_index=0, text="첫째 문단.")]),
            definition=_Definition(),
            context=_Context(),
        )

        event = _convert_one(
            mapper, _delta((), [_reasoning_block(block_index=0, summary_index=1, text="둘째 문단.")])
        )

        self.assertFalse(event["append"])
        self.assertEqual(event["text"], "둘째 문단.")

    def test_updates_mode_model_completion_resets_cursor_for_next_call(self):
        """모델 호출이 끝나면("updates" 모드) reasoning을 더는 안 내고
        (중복 방지), 커서만 지운다 — 다음 호출의 첫 조각이 우연히 같은
        (block_index, summary_index)를 받아도 이전 호출 끝에 안 이어붙는다."""
        mapper = EventMapper()
        mapper.convert(
            _delta((), [_reasoning_block(block_index=0, summary_index=0, text="첫 호출 생각.")]),
            definition=_Definition(),
            context=_Context(),
        )
        # 첫 호출이 도구 호출로 끝난다 — "updates" 모드, reasoning 이벤트 없이
        # tool_started만 나와야 한다(완성본 중복 방지).
        finish = AIMessage(
            content="", tool_calls=[{"name": "document_search", "args": {"query": "q"}, "id": "1"}]
        )
        finish_events = mapper.convert(_raw((), "model", finish), definition=_Definition(), context=_Context())
        self.assertEqual([e["type"] for e in finish_events], [EVENT_TOOL_STARTED])

        # 두 번째 호출의 첫 조각 — 커서가 지워졌으니 (0, 0)이 같아도 새 단계.
        event = _convert_one(
            mapper, _delta((), [_reasoning_block(block_index=0, summary_index=0, text="두 번째 호출 생각.")])
        )
        self.assertFalse(event["append"])

    def test_child_namespace_delta_carries_subagent_alias(self):
        mapper = EventMapper()
        # 위임을 먼저 시작해서 네임스페이스가 알려진 위임에 묶이게 한다
        # (`_resolve_subagent_info`의 순서 휴리스틱 — 다른 자식 네임스페이스
        # 테스트와 같은 준비 절차).
        start = AIMessage(
            content="", tool_calls=[{"name": "task", "args": {"subagent_type": "researcher"}, "id": "d1"}]
        )
        mapper.convert(_raw((), "model", start), definition=_Definition(), context=_Context())

        raw = _delta(
            ("tools:child-1",), [_reasoning_block(block_index=0, summary_index=0, text="자식이 생각하는 중.")]
        )

        event = _convert_one(mapper, raw)

        self.assertEqual(event["type"], EVENT_REASONING)
        self.assertEqual(event["subagent_alias"], "researcher")

    def test_empty_text_placeholder_yields_no_event(self):
        """문단이 막 시작될 때(`response.reasoning_summary_part.added`)의 빈
        문자열 placeholder — 보여줄 게 없으니 이벤트 자체를 안 낸다."""
        raw = _delta((), [_reasoning_block(block_index=0, summary_index=0, text="")])

        events = EventMapper().convert(raw, definition=_Definition(), context=_Context())

        self.assertEqual(events, [])

    def test_non_model_node_is_ignored(self):
        """"messages" 모드는 model 노드 것만 쓴다 — 다른 노드가 낼 일은
        실제로 없지만(deepagents의 LLM 호출은 model 노드뿐), 방어적으로 확인."""
        raw = _delta((), [_reasoning_block(block_index=0, summary_index=0, text="딴 노드")], node_name="tools")

        events = EventMapper().convert(raw, definition=_Definition(), context=_Context())

        self.assertEqual(events, [])


class ParentDirectToolCallTests(SimpleTestCase):
    """루트가 서브 에이전트 위임 없이 자기 도구를 직접 부르는 경로."""

    def test_direct_tool_call_becomes_tool_started_with_no_alias(self):
        message = AIMessage(
            content="",
            tool_calls=[{"name": "get_server_time", "args": {}, "id": "1"}],
        )
        raw = _raw((), "model", message)

        event = _convert_one(EventMapper(), raw)

        self.assertEqual(event["type"], EVENT_TOOL_STARTED)
        self.assertIsNone(event["subagent_alias"])
        self.assertEqual(event["tool_ref"], "get_server_time")

    def test_direct_tool_completion_becomes_tool_completed_with_no_alias(self):
        message = ToolMessage(name="get_server_time", content="12:00", tool_call_id="1")
        raw = _raw((), "tools", message)

        event = _convert_one(EventMapper(), raw)

        self.assertEqual(event["type"], EVENT_TOOL_COMPLETED)
        self.assertIsNone(event["subagent_alias"])
        self.assertEqual(event["tool_ref"], "get_server_time")

    def test_full_direct_call_sequence_from_real_execution_shape(self):
        """부모가 도구를 직접 부르는 실제 시나리오: model(tool_started) -> tools(tool_completed) ->
        model(result). 이전에는 앞의 두 이벤트가 전혀 안 나왔었다(발견된 갭)."""
        mapper = EventMapper()
        events = []

        start = AIMessage(content="", tool_calls=[{"name": "get_server_time", "args": {}, "id": "1"}])
        events.extend(mapper.convert(_raw((), "model", start), definition=_Definition(), context=_Context()))

        done = ToolMessage(name="get_server_time", content="12:00", tool_call_id="1")
        events.extend(mapper.convert(_raw((), "tools", done), definition=_Definition(), context=_Context()))

        final = AIMessage(content="지금은 12시입니다", tool_calls=[])
        events.extend(mapper.convert(_raw((), "model", final), definition=_Definition(), context=_Context()))

        types = [e["type"] for e in events]
        self.assertEqual(types, [EVENT_TOOL_STARTED, EVENT_TOOL_COMPLETED, EVENT_RESULT])

    def test_two_direct_tool_calls_in_one_message_both_become_tool_started(self):
        message = AIMessage(
            content="",
            tool_calls=[
                {"name": "get_server_time", "args": {}, "id": "1"},
                {"name": "people_list", "args": {}, "id": "2"},
            ],
        )
        raw = _raw((), "model", message)

        events = EventMapper().convert(raw, definition=_Definition(), context=_Context())

        self.assertEqual(len(events), 2)
        self.assertEqual({e["tool_ref"] for e in events}, {"get_server_time", "people_list"})
        self.assertTrue(all(e["type"] == EVENT_TOOL_STARTED for e in events))
        self.assertTrue(all(e["subagent_alias"] is None for e in events))


class ChildNamespaceToolCallTests(SimpleTestCase):
    def test_child_tool_call_still_carries_subagent_alias(self):
        mapper = EventMapper()
        delegate = AIMessage(
            content="",
            tool_calls=[{"name": "task", "args": {"subagent_type": "researcher", "description": "조사"}, "id": "1"}],
        )
        started = mapper.convert(_raw((), "model", delegate), definition=_Definition(), context=_Context())

        child_call = AIMessage(content="", tool_calls=[{"name": "document_search", "args": {}, "id": "2"}])
        event = _convert_one(mapper, _raw(("tools:child-1",), "model", child_call))

        self.assertEqual(event["type"], EVENT_TOOL_STARTED)
        self.assertEqual(event["subagent_alias"], "researcher")
        self.assertEqual(event["tool_ref"], "document_search")
        # 자식 네임스페이스의 이벤트는 그 위임의 run_id/parent_run_id를 이어받는다.
        self.assertEqual(event["run_id"], started[0]["run_id"])
        self.assertEqual(event["parent_run_id"], "RUN1")

    def test_child_tool_completion_still_carries_subagent_alias(self):
        mapper = EventMapper()
        delegate = AIMessage(
            content="",
            tool_calls=[{"name": "task", "args": {"subagent_type": "researcher", "description": "조사"}, "id": "1"}],
        )
        mapper.convert(_raw((), "model", delegate), definition=_Definition(), context=_Context())

        child_done = ToolMessage(name="document_search", content="결과", tool_call_id="2")
        event = _convert_one(mapper, _raw(("tools:child-1",), "tools", child_done))

        self.assertEqual(event["type"], EVENT_TOOL_COMPLETED)
        self.assertEqual(event["subagent_alias"], "researcher")
        self.assertEqual(event["tool_ref"], "document_search")


class ToolCallIdArgumentsStatusTests(SimpleTestCase):
    """tool_started/tool_completed의 tool_call_id·arguments·status(2026-08-14 추가).

    `agent_run`/`tool_call` 로깅(tracing/__init__.py)이 이 필드들로 시작-종료를
    정확히 묶고 성공/실패를 가른다 — §14 계약엔 없는, 기존 이벤트에 얹은 필드.
    """

    def test_parent_direct_tool_started_carries_tool_call_id_and_arguments(self):
        message = AIMessage(
            content="",
            tool_calls=[{"name": "document_search", "args": {"query": "일정"}, "id": "call-1"}],
        )
        event = _convert_one(EventMapper(), _raw((), "model", message))

        self.assertEqual(event["tool_call_id"], "call-1")
        self.assertEqual(event["arguments"], {"query": "일정"})

    def test_parent_direct_tool_completed_success_becomes_ok(self):
        message = ToolMessage(name="document_search", content="결과", tool_call_id="call-1")
        event = _convert_one(EventMapper(), _raw((), "tools", message))

        self.assertEqual(event["tool_call_id"], "call-1")
        self.assertEqual(event["status"], "OK")

    def test_parent_direct_tool_completed_error_becomes_failed(self):
        message = ToolMessage(
            name="document_search", content="에러", tool_call_id="call-1", status="error"
        )
        event = _convert_one(EventMapper(), _raw((), "tools", message))

        self.assertEqual(event["status"], "FAILED")

    def test_child_tool_started_carries_tool_call_id_and_arguments(self):
        mapper = EventMapper()
        delegate = AIMessage(
            content="",
            tool_calls=[{"name": "task", "args": {"subagent_type": "researcher", "description": "조사"}, "id": "1"}],
        )
        mapper.convert(_raw((), "model", delegate), definition=_Definition(), context=_Context())

        child_call = AIMessage(
            content="", tool_calls=[{"name": "document_search", "args": {"query": "일정"}, "id": "2"}]
        )
        event = _convert_one(mapper, _raw(("tools:child-1",), "model", child_call))

        self.assertEqual(event["tool_call_id"], "2")
        self.assertEqual(event["arguments"], {"query": "일정"})

    def test_child_tool_completed_error_becomes_failed(self):
        mapper = EventMapper()
        delegate = AIMessage(
            content="",
            tool_calls=[{"name": "task", "args": {"subagent_type": "researcher", "description": "조사"}, "id": "1"}],
        )
        mapper.convert(_raw((), "model", delegate), definition=_Definition(), context=_Context())

        child_done = ToolMessage(
            name="document_search", content="에러", tool_call_id="2", status="error"
        )
        event = _convert_one(mapper, _raw(("tools:child-1",), "tools", child_done))

        self.assertEqual(event["tool_call_id"], "2")
        self.assertEqual(event["status"], "FAILED")


class ParallelSideEffectPartialFailureTests(SimpleTestCase):
    """병렬 side-effect 호출 중 일부만 실패했을 때 결과가 **뭉개지지 않는지**.

    정본: `docs/설계 및 구현/3_중간발표 이후/작업기록/Deep_Agents/2026-08-21_05_병렬_side-effect_부분실패_보고.md`

    이미 성공한 호출을 자동으로 되돌리지 않는 대신(사용자가 연결하는 임의의
    MCP 도구는 되돌리는 방법을 우리가 알 수 없고, 이메일 발송처럼 원천적으로
    못 되돌리는 것도 있다), **무엇이 실제로 일어났는지를 항목별로 정확히
    전달하는 것**을 보장한다. "일부 실패했습니다" 같은 한 문장으로 대체할 수
    없다는 게 이 파일이 지키는 규칙이다.

    새 장치가 아니라 이미 있는 `tool_call_id` 기반 추적(§9)을 규칙으로
    고정하는 테스트다 — 나중에 누가 결과를 하나로 합치면 여기서 깨진다.
    """

    def test_three_parallel_calls_each_get_their_own_started_event(self):
        message = AIMessage(
            content="",
            tool_calls=[
                {"name": "jira_create_issues", "args": {"n": 1}, "id": "call-a"},
                {"name": "jira_create_issues", "args": {"n": 2}, "id": "call-b"},
                {"name": "task_register", "args": {"n": 3}, "id": "call-c"},
            ],
        )

        events = EventMapper().convert(
            _raw((), "model", message), definition=_Definition(), context=_Context()
        )

        started = [e for e in events if e["type"] == EVENT_TOOL_STARTED]
        self.assertEqual([e["tool_call_id"] for e in started], ["call-a", "call-b", "call-c"])

    def test_same_tool_called_twice_stays_two_separate_units(self):
        """같은 도구를 두 번 불러도 tool_call_id가 다르면 다른 실행이다(§9) —
        이름으로 묶으면 둘 중 하나의 결과가 사라진다."""
        message = AIMessage(
            content="",
            tool_calls=[
                {"name": "jira_create_issues", "args": {"n": 1}, "id": "call-a"},
                {"name": "jira_create_issues", "args": {"n": 2}, "id": "call-b"},
            ],
        )

        events = EventMapper().convert(
            _raw((), "model", message), definition=_Definition(), context=_Context()
        )

        started = [e for e in events if e["type"] == EVENT_TOOL_STARTED]
        self.assertEqual(len({e["tool_call_id"] for e in started}), 2)

    def test_one_failure_does_not_change_the_others_status(self):
        """성공한 호출은 성공으로 남는다 — 되돌리지도, 실패로 물들이지도
        않는다. 부분 결과 허용(fail-late)의 실제 모습이다."""
        mapper = EventMapper()
        results = [
            ToolMessage(name="jira_create_issues", content="이슈 생성됨", tool_call_id="call-a"),
            ToolMessage(
                name="send_email", content="발송 실패", tool_call_id="call-b", status="error"
            ),
            ToolMessage(name="task_register", content="등록됨", tool_call_id="call-c"),
        ]

        statuses = {}
        for message in results:
            event = _convert_one(mapper, _raw((), "tools", message))
            statuses[event["tool_call_id"]] = event["status"]

        self.assertEqual(statuses, {"call-a": "OK", "call-b": "FAILED", "call-c": "OK"})

    def test_each_result_keeps_its_own_output(self):
        """항목별 출력이 그대로 남아야 화면이 "무엇이 됐고 무엇이 안 됐는지"를
        적을 수 있다 — 하나로 합치면 그 정보가 사라진다."""
        mapper = EventMapper()

        first = _convert_one(
            mapper,
            _raw((), "tools", ToolMessage(name="task_register", content="A 등록", tool_call_id="1")),
        )
        second = _convert_one(
            mapper,
            _raw((), "tools", ToolMessage(name="task_register", content="B 등록", tool_call_id="2")),
        )

        self.assertIn("A 등록", first["output"])
        self.assertIn("B 등록", second["output"])


class MangledMcpToolNameDemangledTests(SimpleTestCase):
    """factory.py의 model_safe_tool_name()이 mcp: 콜론을 __로 바꿔 모델에
    보내므로, 여기서 되돌리지 않으면 tool_ref가 mcp__MT001처럼 새어 나간다
    (2026-08-14 MCP 연결과 함께 추가)."""

    def test_parent_direct_mcp_tool_call_demangles_tool_ref(self):
        message = AIMessage(content="", tool_calls=[{"name": "mcp__MT001", "args": {}, "id": "1"}])
        event = _convert_one(EventMapper(), _raw((), "model", message))

        self.assertEqual(event["tool_ref"], "mcp:MT001")

    def test_parent_direct_mcp_tool_completion_demangles_tool_ref(self):
        message = ToolMessage(name="mcp__MT001", content="완료", tool_call_id="1")
        event = _convert_one(EventMapper(), _raw((), "tools", message))

        self.assertEqual(event["tool_ref"], "mcp:MT001")

    def test_child_namespace_mcp_tool_call_demangles_tool_ref(self):
        mapper = EventMapper()
        delegate = AIMessage(
            content="",
            tool_calls=[{"name": "task", "args": {"subagent_type": "researcher", "description": "조사"}, "id": "1"}],
        )
        mapper.convert(_raw((), "model", delegate), definition=_Definition(), context=_Context())

        child_call = AIMessage(content="", tool_calls=[{"name": "mcp__MT001", "args": {}, "id": "2"}])
        event = _convert_one(mapper, _raw(("tools:child-1",), "model", child_call))

        self.assertEqual(event["tool_ref"], "mcp:MT001")

    def test_child_namespace_mcp_tool_completion_demangles_tool_ref(self):
        mapper = EventMapper()
        delegate = AIMessage(
            content="",
            tool_calls=[{"name": "task", "args": {"subagent_type": "researcher", "description": "조사"}, "id": "1"}],
        )
        mapper.convert(_raw((), "model", delegate), definition=_Definition(), context=_Context())

        child_done = ToolMessage(name="mcp__MT001", content="완료", tool_call_id="2")
        event = _convert_one(mapper, _raw(("tools:child-1",), "tools", child_done))

        self.assertEqual(event["tool_ref"], "mcp:MT001")

    def test_refs_without_colon_are_unaffected_by_demangling(self):
        """__를 포함하지 않는 보통 tool_ref(내장 도구)는 그대로 통과해야 한다 —
        회귀 방지."""
        message = AIMessage(content="", tool_calls=[{"name": "document_search", "args": {}, "id": "1"}])
        event = _convert_one(EventMapper(), _raw((), "model", message))

        self.assertEqual(event["tool_ref"], "document_search")


class ToolProgressEventTests(SimpleTestCase):
    """`mode="custom"` — tools/adapters.py의 제너레이터 도구가 get_stream_writer()로
    직접 흘려보내는 진행 이벤트."""

    def test_root_level_progress_event_has_no_subagent_alias(self):
        raw = ((), "custom", {"type": "stage", "stage": "1/3", "message": "문서 찾는 중", "tool_ref": "task_extraction"})

        event = _convert_one(EventMapper(), raw)

        self.assertEqual(event["type"], EVENT_TOOL_PROGRESS)
        self.assertIsNone(event["subagent_alias"])
        self.assertEqual(event["tool_ref"], "task_extraction")
        self.assertEqual(event["detail"], {"type": "stage", "stage": "1/3", "message": "문서 찾는 중"})
        self.assertFalse(event["complete"])
        self.assertNotIn("parent_run_id", event)

    def test_child_namespace_progress_event_carries_subagent_alias(self):
        mapper = EventMapper()
        delegate = AIMessage(
            content="",
            tool_calls=[{"name": "task", "args": {"subagent_type": "researcher", "description": "조사"}, "id": "1"}],
        )
        started = mapper.convert(_raw((), "model", delegate), definition=_Definition(), context=_Context())

        raw = (("tools:child-1",), "custom", {"type": "stage", "tool_ref": "jira_get_issues"})
        event = _convert_one(mapper, raw)

        self.assertEqual(event["type"], EVENT_TOOL_PROGRESS)
        self.assertEqual(event["subagent_alias"], "researcher")
        self.assertEqual(event["tool_ref"], "jira_get_issues")
        self.assertEqual(event["run_id"], started[0]["run_id"])
        self.assertEqual(event["parent_run_id"], "RUN1")

    def test_progress_event_without_tool_ref_is_ignored(self):
        """이 런타임의 어댑터가 낸 게 아닐 수 있는 custom 이벤트 — 무시한다."""
        raw = ((), "custom", {"type": "something_else"})

        events = EventMapper().convert(raw, definition=_Definition(), context=_Context())

        self.assertEqual(events, [])

    def test_non_dict_custom_payload_is_ignored(self):
        raw = ((), "custom", "not-a-dict")

        events = EventMapper().convert(raw, definition=_Definition(), context=_Context())

        self.assertEqual(events, [])


class InterruptEventTests(SimpleTestCase):
    """`HumanInTheLoopMiddleware`의 interrupt → `EVENT_AWAITING_CONFIRMATION`
    (2026-08-19, §0순위 — 새 엔진 HITL resume API).

    실제 `langgraph.types.Interrupt` 인스턴스를 쓴다(mock 아님) — `output_writes()`가
    "updates" 청크로 `{"__interrupt__": (Interrupt(...), ...)}`를 낸다는 실제
    소스 확인 그대로 raw_event를 만든다."""

    def test_interrupt_payload_becomes_awaiting_confirmation_event(self):
        hitl_request = {
            "action_requests": [
                {"name": "task_register", "args": {"tasks": [{"title": "더미"}]}}
            ],
            "review_configs": [{"action_name": "task_register"}],
        }
        interrupt = Interrupt(value=hitl_request, id="intr-1")
        raw = ((), "updates", {"__interrupt__": (interrupt,)})

        events = EventMapper().convert(raw, definition=_Definition(), context=_Context())

        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["type"], EVENT_AWAITING_CONFIRMATION)
        self.assertEqual(event["run_id"], "RUN1")
        self.assertEqual(event["agent_id"], "AG001")
        self.assertEqual(event["agent_version_id"], "AV001")
        self.assertEqual(event["interrupt_id"], "intr-1")
        self.assertEqual(event["action_requests"], hitl_request["action_requests"])
        self.assertFalse(event["complete"])

    def test_same_interrupt_id_from_root_and_subgraph_is_emitted_once(self):
        mapper = EventMapper()
        interrupt = Interrupt(
            value={"action_requests": [{"name": "skill_register", "args": {}}]},
            id="intr-duplicate",
        )

        first = mapper.convert(
            (("tools:child",), "updates", {"__interrupt__": (interrupt,)}),
            definition=_Definition(),
            context=_Context(),
        )
        duplicate = mapper.convert(
            ((), "updates", {"__interrupt__": (interrupt,)}),
            definition=_Definition(),
            context=_Context(),
        )

        self.assertEqual(len(first), 1)
        self.assertEqual(duplicate, [])

    def test_interrupt_key_short_circuits_even_with_sibling_node_keys(self):
        """`__interrupt__`는 그 턴의 다른 node_name과 구조적으로 섞이지 않는다
        (`map_output_updates()`가 INTERRUPT 채널 write를 걸러내고 별도
        `_emit()`으로 낸다는 실제 소스 근거) — 그래도 같은 payload dict에
        다른 키가 섞여 들어오는 방어적인 경우, interrupt를 우선 처리하고
        그 키는 통상적인 node_output 루프로 건너가지 않는다."""
        interrupt = Interrupt(value={"action_requests": []}, id="intr-2")
        raw = (
            (),
            "updates",
            {
                "__interrupt__": (interrupt,),
                "model": {"messages": [AIMessage(content="이건 안 쓰인다")]},
            },
        )

        events = EventMapper().convert(raw, definition=_Definition(), context=_Context())

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], EVENT_AWAITING_CONFIRMATION)

    def test_empty_interrupt_tuple_yields_no_events(self):
        raw = ((), "updates", {"__interrupt__": ()})

        events = EventMapper().convert(raw, definition=_Definition(), context=_Context())

        self.assertEqual(events, [])

    def test_interrupt_value_missing_action_requests_defaults_to_empty_list(self):
        interrupt = Interrupt(value={"review_configs": []}, id="intr-3")
        raw = ((), "updates", {"__interrupt__": (interrupt,)})

        events = EventMapper().convert(raw, definition=_Definition(), context=_Context())

        self.assertEqual(events[0]["action_requests"], [])

    def test_non_dict_interrupt_value_defaults_to_empty_action_requests(self):
        """`Interrupt.value`는 `interrupt()`에 넘긴 그 값 그대로라 이론상 dict가
        아닐 수도 있다 — 방어적으로 빈 목록으로 처리하고 죽지 않는다."""
        interrupt = Interrupt(value="not-a-dict", id="intr-4")
        raw = ((), "updates", {"__interrupt__": (interrupt,)})

        events = EventMapper().convert(raw, definition=_Definition(), context=_Context())

        self.assertEqual(events[0]["action_requests"], [])

    def test_interrupt_persists_tool_call_correlation_for_resume(self):
        mapper = EventMapper()
        tool_call = {
            "name": "task_register",
            "args": {"tasks": [{"title": "더미"}]},
            "id": "call-1",
        }
        mapper.convert(
            _raw((), "model", AIMessage(content="", tool_calls=[tool_call])),
            definition=_Definition(),
            context=_Context(),
        )
        interrupt = Interrupt(
            value={"action_requests": [{"name": tool_call["name"], "args": tool_call["args"]}]},
            id="intr-correlated",
        )

        event = mapper.convert(
            ((), "updates", {"__interrupt__": (interrupt,)}),
            definition=_Definition(),
            context=_Context(),
        )[0]

        state = event["trace_resume_state"]
        self.assertEqual(
            state["interrupted_tool_calls"],
            [{"action_index": 0, "run_id": "RUN1", "tool_call_id": "call-1"}],
        )
        self.assertEqual(state["pending_tool_calls"][0]["tool_call_id"], "call-1")

    def test_identical_parallel_calls_are_correlated_in_original_order(self):
        mapper = EventMapper()
        calls = [
            {"name": "task_register", "args": {"tasks": []}, "id": "call-1"},
            {"name": "task_register", "args": {"tasks": []}, "id": "call-2"},
        ]
        mapper.convert(
            _raw((), "model", AIMessage(content="", tool_calls=calls)),
            definition=_Definition(),
            context=_Context(),
        )
        action_requests = [{"name": call["name"], "args": call["args"]} for call in calls]
        interrupt = Interrupt(value={"action_requests": action_requests}, id="intr-parallel")

        event = mapper.convert(
            ((), "updates", {"__interrupt__": (interrupt,)}),
            definition=_Definition(),
            context=_Context(),
        )[0]

        self.assertEqual(
            event["trace_resume_state"]["interrupted_tool_calls"],
            [
                {"action_index": 0, "run_id": "RUN1", "tool_call_id": "call-1"},
                {"action_index": 1, "run_id": "RUN1", "tool_call_id": "call-2"},
            ],
        )

    def test_restore_hitl_state_keeps_child_tool_run_mapping(self):
        mapper = EventMapper()
        mapper.restore_hitl_state(
            {
                "pending_subagents": {
                    "delegate-1": {
                        "alias": "jira_writer",
                        "run_id": "RUN-CHILD",
                        "agent_id": "AG011",
                        "agent_version_id": "AV023",
                    }
                },
                "namespace_subagents": {
                    "tools:child-1": {
                        "alias": "jira_writer",
                        "run_id": "RUN-CHILD",
                        "agent_id": "AG011",
                        "agent_version_id": "AV023",
                    }
                },
                "pending_tool_calls": [
                    {
                        "run_id": "RUN-CHILD",
                        "tool_call_id": "call-child",
                        "name": "task_register",
                        "args": {},
                    }
                ],
            }
        )

        event = mapper.convert(
            _raw(
                ("tools:child-1",),
                "tools",
                ToolMessage(
                    content="완료",
                    name="task_register",
                    tool_call_id="call-child",
                    status="success",
                ),
            ),
            definition=_Definition(),
            context=_Context(),
        )[0]

        self.assertEqual(event["type"], EVENT_TOOL_COMPLETED)
        self.assertEqual(event["run_id"], "RUN-CHILD")
        self.assertEqual(event["tool_call_id"], "call-child")


class ModelUsageTests(SimpleTestCase):
    """모델 호출마다 회전 수·토큰을 세어 끝나는 이벤트에 싣는가(2026-08-21).

    `agent_run.iterations`/`token_in`/`token_out`을 채우는 유일한 경로다 —
    `tracing/`은 변환된 이벤트만 보므로 원시 `AIMessage.usage_metadata`에
    닿지 못한다.
    """

    @staticmethod
    def _ai(text="", *, tool_calls=None, usage=None):
        return AIMessage(
            content=text,
            tool_calls=tool_calls or [],
            usage_metadata=usage,
        )

    def test_result_carries_summed_tokens_and_iteration_count(self):
        mapper = EventMapper()
        # 1회전: 도구를 부른다. 이 호출의 토큰도 합계에 들어가야 한다.
        mapper.convert(
            _raw((), "model", self._ai(tool_calls=[{"name": "people_list", "args": {}, "id": "1"}],
                                       usage={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120})),
            definition=_Definition(),
            context=_Context(),
        )
        # 2회전: 최종 답.
        event = _convert_one(
            mapper,
            _raw((), "model", self._ai("답", usage={"input_tokens": 300, "output_tokens": 50, "total_tokens": 350})),
        )

        self.assertEqual(event["type"], EVENT_RESULT)
        self.assertEqual(event["iterations"], 2)
        self.assertEqual(event["token_in"], 400)
        self.assertEqual(event["token_out"], 70)

    def test_missing_usage_metadata_leaves_tokens_none_not_zero(self):
        """usage를 안 주는 경로(openai_compatible)에서 0으로 채우면 안 된다.

        0이면 「토큰을 안 쓴 실행」과 구분이 사라진다. 회전 수는 usage와
        무관하게 세므로 그대로 찬다.
        """
        event = _convert_one(EventMapper(), _raw((), "model", self._ai("답")))

        self.assertEqual(event["iterations"], 1)
        self.assertIsNone(event["token_in"])
        self.assertIsNone(event["token_out"])

    def test_thinking_tokens_hidden_in_total_are_counted_as_output(self):
        """Gemini OpenAI 호환 주소 실측(2026-08-21): prompt 6 · completion 1 ·
        total 149. 있는 그대로 적으면 Usage 합계가 149 대신 7이 된다."""
        event = _convert_one(
            EventMapper(),
            _raw((), "model", self._ai("답", usage={"input_tokens": 6, "output_tokens": 1, "total_tokens": 149})),
        )

        self.assertEqual(event["token_in"], 6)
        self.assertEqual(event["token_out"], 143)

    def test_provider_whose_total_already_adds_up_is_left_alone(self):
        """OpenAI 실측: 11 + 5 = 16. 나머지가 0이라 손대지 않는다."""
        event = _convert_one(
            EventMapper(),
            _raw((), "model", self._ai("답", usage={"input_tokens": 11, "output_tokens": 5, "total_tokens": 16})),
        )

        self.assertEqual(event["token_in"], 11)
        self.assertEqual(event["token_out"], 5)

    def test_child_tokens_go_to_the_child_run_not_the_parent(self):
        mapper = EventMapper()
        start = self._ai(
            tool_calls=[{"name": "task", "args": {"subagent_type": "researcher", "description": "조사"}, "id": "1"}],
            usage={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
        )
        started = _convert_one(mapper, _raw((), "model", start))
        child_ns = ("tools:abc",)
        # 자식 네임스페이스의 모델 호출 — 자식 run 누계로 가야 한다.
        mapper.convert(
            _raw(child_ns, "model", self._ai("자식 생각",
                                             usage={"input_tokens": 900, "output_tokens": 80, "total_tokens": 980})),
            definition=_Definition(),
            context=_Context(),
        )

        done = ToolMessage(name="task", content="완료", tool_call_id="1")
        completed = _convert_one(mapper, _raw((), "tools", done))

        self.assertEqual(completed["type"], EVENT_SUBAGENT_COMPLETED)
        self.assertEqual(completed["run_id"], started["run_id"])
        self.assertEqual(completed["token_in"], 900)
        self.assertEqual(completed["token_out"], 80)

        # 부모 누계에는 자식 몫이 안 섞인다 — 부모는 자기 위임 호출 1회뿐이다.
        final = _convert_one(mapper, _raw((), "model", self._ai("최종")))
        self.assertEqual(final["iterations"], 2)
        self.assertEqual(final["token_in"], 10)

    def test_usage_for_is_empty_after_the_run_is_closed(self):
        """끝난 실행의 누계는 버린다 — 같은 mapper 를 계속 들고 있어도 안 샌다."""
        mapper = EventMapper()
        _convert_one(
            mapper,
            _raw((), "model", self._ai("답", usage={"input_tokens": 7, "output_tokens": 1, "total_tokens": 8})),
        )

        self.assertEqual(
            mapper.usage_for("RUN1"),
            {"iterations": 0, "token_in": None, "token_out": None},
        )


class RetrievedDocumentTests(SimpleTestCase):
    """도구 결과에서 조회한 문서 식별자를 뽑아내는가(2026-08-21).

    멘토링 전달 "Tool 호출 결과 어떤 문서/데이터가 조회되었는지". 지금까지
    `tool_call` 에는 질의문만 남아 무엇을 봤는지 되물을 수 없었다.
    """

    @staticmethod
    def _completed(payload):
        """도구가 dict 를 돌려주면 langchain-core 가 json.dumps 로 문자열을 만든다."""
        import json

        message = ToolMessage(
            name="document_search", content=json.dumps(payload, ensure_ascii=False), tool_call_id="1"
        )
        return _convert_one(EventMapper(), _raw((), "tools", message))

    def test_evidence_and_candidates_and_not_indexed_are_all_collected(self):
        event = self._completed(
            {
                "query": "휴가 규정",
                "evidence": [
                    {"chunk_id": "c1", "doc_id": "DC001", "text": "..."},
                    {"chunk_id": "c2", "doc_id": "DC004", "text": "..."},
                ],
                "not_indexed": [{"doc_id": "DC009", "file_name": "x.pdf"}],
            }
        )

        self.assertEqual(event["type"], EVENT_TOOL_COMPLETED)
        self.assertEqual(event["retrieved_doc_ids"], ["DC001", "DC004", "DC009"])

    def test_same_document_in_several_chunks_is_recorded_once(self):
        event = self._completed(
            {"evidence": [{"doc_id": "DC001"}, {"doc_id": "DC001"}, {"doc_id": "DC002"}]}
        )

        self.assertEqual(event["retrieved_doc_ids"], ["DC001", "DC002"])

    def test_tool_that_returns_no_documents_gets_an_empty_list(self):
        """문서와 무관한 도구. 저장소가 이 빈 목록을 NULL 로 낮춘다."""
        message = ToolMessage(name="people_list", content='[{"name": "임준"}]', tool_call_id="1")
        event = _convert_one(EventMapper(), _raw((), "tools", message))

        self.assertEqual(event["retrieved_doc_ids"], [])

    def test_plain_text_output_does_not_break_the_event(self):
        """JSON 이 아닌 결과(MCP 도구 등)는 조용히 빈 목록이다."""
        message = ToolMessage(name="mcp:something", content="그냥 문장입니다", tool_call_id="1")
        event = _convert_one(EventMapper(), _raw((), "tools", message))

        self.assertEqual(event["retrieved_doc_ids"], [])

    def test_absurdly_long_result_is_capped(self):
        payload = {"evidence": [{"doc_id": f"DC{i:03d}"} for i in range(200)]}
        event = self._completed(payload)

        self.assertEqual(len(event["retrieved_doc_ids"]), RETRIEVED_DOC_IDS_MAX)

