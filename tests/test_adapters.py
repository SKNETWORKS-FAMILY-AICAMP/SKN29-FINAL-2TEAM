"""tools/adapters.py(adapt_builtin_tools) 테스트.

`services.harness.registry.BUILTIN_TOOLS`를 실제로 import해서(mock 아님) 15개
전부가 정확한 injected_context로 옮겨지는지 확인한다. `EXPECTED_INJECTED_CONTEXT`
표가 유일한 정본이다 — 비교할 레거시 구현(`services/harness/runner.py`의
`_injected()`)이 2026-08-22 레거시 실행기 폐기로 없어졌다(아래 클래스 앞
주석 참고).
"""

from unittest.mock import patch

from django.test import SimpleTestCase

from services.agent_runtime.tools.adapters import adapt_builtin_tools, adapt_mcp_tools
from services.harness.registry import BUILTIN_TOOLS

# services/harness/runner.py의 _injected()를 AST로 직접 파싱해서 얻은 실측값
# (2026-08-13). CONTEXT_VALUES 쪽 이름 기준(project_id, proj_id 아님).
EXPECTED_INJECTED_CONTEXT = {
    # **`account_id` 가 함께 가야 한다**(2026-08-18 QA). 없으면 검색 범위가 팀
    # 문서만이 되어 「내가 켠 내 파일」과 공유분이 빠진다(M④) — 그런데 오류가
    # 아니라 「문서가 없습니다」로 끝난다.
    # 이 표가 `("team_id",)` 로 레거시의 빠뜨림을 그대로 고정하고 있었다.
    #
    # `project_id` 는 2026-08-19(PM 결정 ⓐ). 화면은 「〈프로젝트〉의 문서를
    # 근거로 답합니다」라고 약속하는데 검색이 `proj_id` 를 받지도 않아 팀 문서
    # 전체를 훑고 있었다 — 무관한 문서가 후보로 올라와 읽히기까지 했다.
    "document_search": ("team_id", "account_id", "project_id"),
    "people_list": ("account_id",),
    "workload_report": ("account_id",),
    "task_extraction": ("project_id", "account_id", "team_id"),
    "project_list": ("account_id",),
    "task_list": ("project_id", "account_id"),
    "document_list": ("account_id",),
    "document_sync": ("account_id",),
    "table_export": ("account_id",),
    "task_update": ("project_id", "account_id"),
    "web_search": (),
    "absence_list": ("account_id",),
    "task_register": ("project_id", "account_id"),
    "jira_create_issues": ("project_id", "account_id"),
    "jira_get_issues": ("project_id", "account_id"),
    "skill_register": ("account_id", "team_id", "account_role"),
}

# BUILTIN_TOOLS에 정의된 실제 side_effect 값(registry.py 직접 확인).
EXPECTED_SIDE_EFFECT = {
    "task_update": True,
    "task_register": True,
    "jira_create_issues": True,
    "skill_register": True,
    # 2026-08-25 juyeon 병합. **이 도구만 side_effect=True 의 뜻이 다르다** —
    # 외부 상태를 바꿔서가 아니라, 이 값이 있어야 `factory.py`의 `interrupt_on`
    # 계산에 자동으로 포함되어 사람이 답할 때까지 실행이 멈추기 때문이다
    # (registry.py의 같은 자리 주석 참고). 되묻기는 부작용이 아니라 대기다.
    "skill_creator_ask_followup": True,
    # 2026-08-26. 사용자의 「내 파일」에 파일을 만든다 — 되돌리려면 사람이
    # 지워야 하므로 승인을 받는다.
    "table_export": True,
}


class RealRegistryShapeTests(SimpleTestCase):
    """실제 BUILTIN_TOOLS(18개)를 그대로 변환했을 때의 모양을 확인한다."""

    def test_real_registry_has_exactly_eighteen_tools(self):
        # 이 숫자가 바뀌면(도구 추가/제거) 아래 EXPECTED_* 표도 같이 갱신해야 한다는
        # 신호다 — 조용히 지나치지 않게 실제 registry.py의 크기를 직접 고정해 둔다.
        #
        # 2026-08-20에 `get_current_datetime`이 추가되며 13 → 14가 됐는데
        # (`tools/adapters.py` 모듈 docstring은 그때 같이 갱신됐다) 이 테스트는
        # 안 고쳐져 실패한 채로 남아 있었다 — 2026-08-21에 맞춘다. 이 신호가
        # 의도대로 동작한 사례이므로 숫자 고정 자체는 그대로 둔다.
        #
        # 2026-08-24 병합 시점에 16이 됐다. 두 브랜치가 각자 하나씩 더했는데
        # 양쪽 다 자기 것만 세어 15로 적었다 — main 은 `document_sync`를,
        # jihun 은 `skill_register`를 더했다. 병합해야만 드러나는 값이라
        # 여기서 실제 registry.py를 세어 16으로 고정한다.
        #
        # 2026-08-25 juyeon 병합에서 17이 됐다 — `skill_creator_ask_followup`.
        # 이번에도 병합해야만 드러났다(브랜치 쪽 테스트는 자기 것만 봤다).
        # 이 신호가 세 번째로 제 역할을 했으므로 숫자 고정은 계속 둔다.
        #
        # 2026-08-26 에 18 이 됐다 — `table_export`. 이번에는 병합이 아니라
        # 도구를 더하면서 그 자리에서 걸렸다(의도대로 동작한 네 번째 사례).
        self.assertEqual(len(BUILTIN_TOOLS), 18)

    def test_adapts_every_real_builtin_tool(self):
        adapted = {tool.ref: tool for tool in adapt_builtin_tools()}
        self.assertEqual(set(adapted.keys()), set(BUILTIN_TOOLS.keys()))

    def test_copies_name_description_schema_side_effect_unchanged(self):
        adapted = {tool.ref: tool for tool in adapt_builtin_tools()}
        for ref, legacy in BUILTIN_TOOLS.items():
            with self.subTest(ref=ref):
                runtime_tool = adapted[ref]
                self.assertEqual(runtime_tool.name, legacy.name)
                self.assertEqual(runtime_tool.description, legacy.description)
                self.assertEqual(runtime_tool.input_schema, legacy.input_schema)
                self.assertEqual(runtime_tool.side_effect, legacy.side_effect)

    def test_side_effect_flags_match_known_write_tools(self):
        adapted = {tool.ref: tool for tool in adapt_builtin_tools()}
        for ref, tool in adapted.items():
            with self.subTest(ref=ref):
                self.assertEqual(tool.side_effect, EXPECTED_SIDE_EFFECT.get(ref, False))

    def test_injected_context_matches_legacy_runner_injected(self):
        """services/harness/runner.py의 _injected()를 실측(AST)한 값과 정확히 같아야 한다."""
        adapted = {tool.ref: tool for tool in adapt_builtin_tools()}
        for ref, expected in EXPECTED_INJECTED_CONTEXT.items():
            with self.subTest(ref=ref):
                self.assertEqual(adapted[ref].injected_context, expected)


# `LegacyInjectionParityTests`가 여기 있었다 — 레거시 `runner._injected()`를
# 실제로 불러 새 런타임의 `injected_context`와 서로 비교하던 테스트다. 손으로
# 관리하는 위 `EXPECTED_INJECTED_CONTEXT` 표가 틀렸을 때 표만으로는 못 잡는다는
# 이유였고, 실제로 한 번 잡았다(2026-08-18 `document_search`의 `account_id`).
#
# 2026-08-22에 레거시 실행기를 걷어내면서 비교 상대가 없어져 지웠다. 표가
# **유일한 정본**이 됐으므로, 내장 도구의 주입 인자를 바꿀 때는 위 표도 같이
# 고쳐야 한다 — 서로 검증해 주던 짝이 이제 없다.


class ContextRenamingTests(SimpleTestCase):
    """CONTEXT_VALUES가 주는 project_id를 레거시 핸들러가 기대하는 proj_id로
    실제로 바꿔 넘기는지 확인한다."""

    def test_project_id_becomes_proj_id_for_legacy_handler(self):
        captured = {}

        def fake_handler(*, proj_id, account_id):
            captured["proj_id"] = proj_id
            captured["account_id"] = account_id
            return {"ok": True}

        with patch(
            "services.agent_runtime.tools.adapters.BUILTIN_TOOLS",
            {"task_list": type(BUILTIN_TOOLS["task_list"])(**{
                **BUILTIN_TOOLS["task_list"].__dict__, "handler": fake_handler,
            })},
        ):
            adapted = {tool.ref: tool for tool in adapt_builtin_tools()}
            adapted["task_list"].handler(project_id="PJ1", account_id="AC1")

        self.assertEqual(captured, {"proj_id": "PJ1", "account_id": "AC1"})


class TaskExtractionModelInjectionTests(SimpleTestCase):
    """task_extraction만 agent_model을 핸들러에 고정해 넘긴다."""

    def test_agent_model_is_baked_into_task_extraction_handler(self):
        captured = {}

        def fake_extract(*, proj_id, account_id, team_id, model):
            captured.update(proj_id=proj_id, account_id=account_id, team_id=team_id, model=model)
            return {"tasks": []}

        with patch(
            "services.agent_runtime.tools.adapters.BUILTIN_TOOLS",
            {"task_extraction": type(BUILTIN_TOOLS["task_extraction"])(**{
                **BUILTIN_TOOLS["task_extraction"].__dict__, "handler": fake_extract,
            })},
        ):
            adapted = adapt_builtin_tools(agent_model="claude-sonnet-5")[0]
            adapted.handler(project_id="PJ1", account_id="AC1", team_id="TM1")

        self.assertEqual(
            captured,
            {"proj_id": "PJ1", "account_id": "AC1", "team_id": "TM1", "model": "claude-sonnet-5"},
        )

    def test_other_tools_ignore_agent_model(self):
        """side_effect 없는 도구가 agent_model 때문에 엉뚱한 인자를 받으면 안 된다."""
        captured = {}

        def fake_people_list(*, account_id):
            captured["account_id"] = account_id
            return {"members": []}

        with patch(
            "services.agent_runtime.tools.adapters.BUILTIN_TOOLS",
            {"people_list": type(BUILTIN_TOOLS["people_list"])(**{
                **BUILTIN_TOOLS["people_list"].__dict__, "handler": fake_people_list,
            })},
        ):
            adapted = adapt_builtin_tools(agent_model="claude-sonnet-5")[0]
            adapted.handler(account_id="AC1")  # model을 안 줘도(=받지 않아도) 에러 없어야 함

        self.assertEqual(captured, {"account_id": "AC1"})

    def test_caller_supplied_model_argument_is_overridden_by_agent_model(self):
        """모델이 도구 인자로 model을 보내도(원래 input_schema엔 없지만 방어적으로),
        서버가 정한 agent_model이 항상 이긴다."""
        captured = {}

        def fake_extract(*, proj_id, account_id, team_id, model):
            captured["model"] = model
            return {"tasks": []}

        with patch(
            "services.agent_runtime.tools.adapters.BUILTIN_TOOLS",
            {"task_extraction": type(BUILTIN_TOOLS["task_extraction"])(**{
                **BUILTIN_TOOLS["task_extraction"].__dict__, "handler": fake_extract,
            })},
        ):
            adapted = adapt_builtin_tools(agent_model="server-picked-model")[0]
            adapted.handler(project_id="PJ1", account_id="AC1", team_id="TM1", model="model-from-caller")

        self.assertEqual(captured["model"], "server-picked-model")


class GeneratorDrainingTests(SimpleTestCase):
    """제너레이터 핸들러(task_extraction/jira_get_issues 패턴)를 감지해서 drain하는지."""

    def test_generator_handler_final_value_is_returned(self):
        def fake_generator_handler(*, account_id):
            yield {"type": "stage", "stage": "1/2"}
            yield {"type": "stage", "stage": "2/2"}
            return {"result": "완료", "account_id": account_id}

        with patch(
            "services.agent_runtime.tools.adapters.BUILTIN_TOOLS",
            {"jira_get_issues": type(BUILTIN_TOOLS["jira_get_issues"])(**{
                **BUILTIN_TOOLS["jira_get_issues"].__dict__, "handler": fake_generator_handler,
            })},
        ):
            adapted = adapt_builtin_tools()[0]
            result = adapted.handler(account_id="AC1")

        self.assertEqual(result, {"result": "완료", "account_id": "AC1"})

    def test_non_generator_handler_result_passes_through_unchanged(self):
        def fake_plain_handler(*, query):
            return {"results": [query]}

        with patch(
            "services.agent_runtime.tools.adapters.BUILTIN_TOOLS",
            {"web_search": type(BUILTIN_TOOLS["web_search"])(**{
                **BUILTIN_TOOLS["web_search"].__dict__, "handler": fake_plain_handler,
            })},
        ):
            adapted = adapt_builtin_tools()[0]
            result = adapted.handler(query="테스트")

        self.assertEqual(result, {"results": ["테스트"]})

    def test_generator_progress_events_are_forwarded_via_stream_writer_when_available(self):
        """그래프 실행 컨텍스트 밖(단위 테스트)에서는 get_stream_writer()가
        RuntimeError를 내므로 no-op으로 안전하게 넘어가는지 — 그리고 writer가
        있을 때는 실제로 호출되는지 둘 다 확인한다."""
        forwarded = []

        def fake_generator_handler(*, account_id):
            yield {"type": "stage", "stage": "1/1", "message": "진행중"}
            return {"result": "완료"}

        with patch(
            "services.agent_runtime.tools.adapters.BUILTIN_TOOLS",
            {"jira_get_issues": type(BUILTIN_TOOLS["jira_get_issues"])(**{
                **BUILTIN_TOOLS["jira_get_issues"].__dict__, "handler": fake_generator_handler,
            })},
        ):
            with patch(
                "services.agent_runtime.tools.adapters._safe_stream_writer",
                return_value=forwarded.append,
            ):
                adapted = adapt_builtin_tools()[0]
                result = adapted.handler(account_id="AC1")

        self.assertEqual(result, {"result": "완료"})
        self.assertEqual(
            forwarded,
            [{"type": "stage", "stage": "1/1", "message": "진행중", "tool_ref": "jira_get_issues"}],
        )

    def test_stream_writer_unavailable_outside_graph_context_is_a_safe_noop(self):
        """실제 그래프 밖(예: 이 테스트 자체)에서 그대로 호출해도 죽지 않아야 한다
        — _safe_stream_writer()를 patch하지 않고 진짜 동작을 그대로 확인."""

        def fake_generator_handler(*, account_id):
            yield {"type": "stage", "stage": "1/1"}
            return {"result": "완료"}

        with patch(
            "services.agent_runtime.tools.adapters.BUILTIN_TOOLS",
            {"jira_get_issues": type(BUILTIN_TOOLS["jira_get_issues"])(**{
                **BUILTIN_TOOLS["jira_get_issues"].__dict__, "handler": fake_generator_handler,
            })},
        ):
            adapted = adapt_builtin_tools()[0]
            result = adapted.handler(account_id="AC1")  # 그래프 컨텍스트 없음 — 에러 없어야 함

        self.assertEqual(result, {"result": "완료"})


class AdaptMcpToolsTests(SimpleTestCase):
    """tools/adapters.py(adapt_mcp_tools) 테스트 — 2026-08-14 MCP 연결.

    `services.harness.registry._mcp_tool()`과 같은 근거(항상 side_effect=True,
    team_id 주입, 호출 직전에 서버/토큰 재조회)를 그대로 옮겼는지 확인한다.
    """

    def _mcp_row(self, **overrides) -> dict:
        row = {
            "tool_ref": "mcp:MT001",
            "mcp_tool_id": "MT001",
            "name": "Jira 이슈 생성",
            "description": "Jira에 이슈를 만든다.",
            "input_schema": {"type": "object", "properties": {"title": {"type": "string"}}},
            "mcp_server_id": "MS001",
            "server_name": "Jira",
            "endpoint_url": "https://mcp.example.com/rpc",
        }
        row.update(overrides)
        return row

    def test_returns_one_tool_per_registered_mcp_tool(self):
        with patch(
            "services.agent_runtime.tools.adapters.AgentRepository.mcp_tools",
            return_value=[self._mcp_row(), self._mcp_row(tool_ref="mcp:MT002", mcp_tool_id="MT002")],
        ):
            tools = adapt_mcp_tools(team_id="TM1")

        self.assertEqual({t.ref for t in tools}, {"mcp:MT001", "mcp:MT002"})

    def test_mcp_tools_are_always_side_effect_true(self):
        """MCP list_tools엔 read/write 구분 필드가 없다 — 모르는 것을 안전한
        쪽으로 가정한다(레거시 registry.py의 _mcp_tool() 주석과 동일 근거)."""
        with patch(
            "services.agent_runtime.tools.adapters.AgentRepository.mcp_tools",
            return_value=[self._mcp_row()],
        ):
            tool = adapt_mcp_tools(team_id="TM1")[0]

        self.assertTrue(tool.side_effect)

    def test_mcp_tools_inject_team_id(self):
        with patch(
            "services.agent_runtime.tools.adapters.AgentRepository.mcp_tools",
            return_value=[self._mcp_row()],
        ):
            tool = adapt_mcp_tools(team_id="TM1")[0]

        self.assertEqual(tool.injected_context, ("team_id",))

    def test_name_description_schema_copied_from_row(self):
        with patch(
            "services.agent_runtime.tools.adapters.AgentRepository.mcp_tools",
            return_value=[self._mcp_row()],
        ):
            tool = adapt_mcp_tools(team_id="TM1")[0]

        self.assertEqual(tool.name, "Jira 이슈 생성")
        self.assertEqual(tool.description, "Jira에 이슈를 만든다.")
        self.assertEqual(tool.input_schema, {"type": "object", "properties": {"title": {"type": "string"}}})

    def test_missing_description_and_schema_fall_back_to_safe_defaults(self):
        row = self._mcp_row(description=None, input_schema=None)
        with patch("services.agent_runtime.tools.adapters.AgentRepository.mcp_tools", return_value=[row]):
            tool = adapt_mcp_tools(team_id="TM1")[0]

        self.assertEqual(tool.description, "")
        self.assertEqual(tool.input_schema, {"type": "object", "properties": {}})

    def test_no_registered_tools_returns_empty_tuple(self):
        with patch("services.agent_runtime.tools.adapters.AgentRepository.mcp_tools", return_value=[]):
            self.assertEqual(adapt_mcp_tools(team_id="TM1"), ())


class McpHandlerExecutionTests(SimpleTestCase):
    """MCP 도구 handler가 호출 직전에 서버/토큰을 재조회하고 mcp_client.call_tool로
    넘기는지(§4-2 — 토큰을 Tool 객체에 실어 Loop를 돌아다니게 하지 않는다)."""

    def test_handler_looks_up_credentials_and_calls_mcp_client(self):
        row = {
            "tool_ref": "mcp:MT001",
            "mcp_tool_id": "MT001",
            "name": "Jira 이슈 생성",
            "description": "",
            "input_schema": {},
            "mcp_server_id": "MS001",
            "server_name": "Jira",
            "endpoint_url": "https://mcp.example.com/rpc",
        }
        credentials = {
            "tool_name": "create_issue",
            "endpoint_url": "https://mcp.example.com/rpc",
            "auth_token": "secret-token",
        }
        with patch("services.agent_runtime.tools.adapters.AgentRepository.mcp_tools", return_value=[row]):
            tool = adapt_mcp_tools(team_id="TM1")[0]

        with patch(
            "services.agent_runtime.tools.adapters.McpServerRepository.credentials_for_tool",
            return_value=credentials,
        ) as mock_credentials:
            with patch(
                "services.agent_runtime.tools.adapters.mcp_client.call_tool",
                return_value={"content": "완료"},
            ) as mock_call:
                result = tool.handler(team_id="TM1", title="버그 수정")

        mock_credentials.assert_called_once_with("mcp:MT001", team_id="TM1")
        mock_call.assert_called_once_with(
            endpoint_url="https://mcp.example.com/rpc",
            auth_token="secret-token",
            name="create_issue",
            arguments={"title": "버그 수정"},
        )
        self.assertEqual(result, {"content": "완료"})
