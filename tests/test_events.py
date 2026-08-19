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


class _Interrupt:
    """LangGraph `Interrupt`의 최소 대역. 필요한 건 `.value` 하나뿐이다.

    실제 값 모양은 RDS의 `checkpoint_writes`에 저장된 실물에서 확인했다
    (2026-08-18): `{"action_requests": [{"name","args"}], "review_configs": [...]}`.
    """

    def __init__(self, value):
        self.value = value


def _hitl_raw_event(*, name="task_register", args=None, extra=()):
    """승인 게이트가 멈췄을 때 LangGraph가 내보내는 `updates` 이벤트."""
    requests = [{"name": name, "args": args if args is not None else {"tasks": [{"title": "감리"}]}}]
    requests.extend(extra)
    return (
        (),
        "updates",
        {"__interrupt__": (_Interrupt({"action_requests": requests, "review_configs": []}),)},
    )


class AwaitingConfirmationTests(SimpleTestCase):
    """`__interrupt__` → `awaiting_confirmation`.

    회귀 방지: 예전에는 `updates` 페이로드를 `node_name -> dict`로만 순회해서
    (`isinstance(node_output, dict)`) 값이 tuple인 `__interrupt__`가 조용히
    버려졌다 — 그래프는 멈췄는데 화면엔 아무것도 안 나와 대화가 끊긴 것처럼
    보였다(2026-08-18 QA에서 발견).
    """

    def test_인터럽트를_승인대기_이벤트로_바꾼다(self):
        events = EventMapper().convert(
            _hitl_raw_event(), definition=_Definition(), context=_Context()
        )

        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["type"], EVENT_AWAITING_CONFIRMATION)
        self.assertEqual(event["tool_ref"], "task_register")
        # 화면이 읽는 필드(`liveChat.ts`의 awaiting_confirmation 분기)
        self.assertEqual(event["arguments"], {"tasks": [{"title": "감리"}]})
        self.assertEqual(event["run_id"], _Context().run_id)

    def test_사람이_읽는_도구_이름을_붙인다(self):
        events = EventMapper().convert(
            _hitl_raw_event(), definition=_Definition(), context=_Context()
        )

        # 레지스트리의 라벨. 대화 기록 한 줄(`_history`)에 쓰인다.
        self.assertEqual(events[0]["tool_name"], "업무 등록")

    def test_모델용_이름을_저장소_tool_ref로_되돌린다(self):
        events = EventMapper().convert(
            _hitl_raw_event(name="mcp__abc123"), definition=_Definition(), context=_Context()
        )

        self.assertEqual(events[0]["tool_ref"], "mcp:abc123")

    def test_재개에_필요한_호출을_전부_담는다(self):
        """카드는 첫 호출만 그리지만, 재개는 요구된 수만큼 결정을 돌려줘야 한다."""
        events = EventMapper().convert(
            _hitl_raw_event(extra=[{"name": "jira_create_issues", "args": {"issues": []}}]),
            definition=_Definition(),
            context=_Context(),
        )

        resume = events[0]["resume"]
        self.assertEqual(resume["engine"], "agent_runtime")
        self.assertEqual(
            [item["name"] for item in resume["action_requests"]],
            ["task_register", "jira_create_issues"],
        )

    def test_인터럽트가_아니면_그대로_지나간다(self):
        events = EventMapper().convert(
            ((), "updates", {"__interrupt__": ()}), definition=_Definition(), context=_Context()
        )

        self.assertEqual(events, [])
