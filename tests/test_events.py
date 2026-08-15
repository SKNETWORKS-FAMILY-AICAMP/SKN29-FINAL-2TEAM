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

from langchain_core.messages import AIMessage, ToolMessage
from django.test import SimpleTestCase

from services.agent_runtime.definitions import SubagentDefinition
from services.agent_runtime.events import (
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
