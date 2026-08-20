"""Agent Builder 신규 API·생명주기·안전 경계 단위 테스트.

CRUD 자체(팀 경계, 기본 제공 에이전트 보호)는 `tests/test_agents.py`가 이미
지킨다(알 수 없는/중복 도구 거부 포함 — `check_definition` 구조 검증이 create/
update/activate 세 곳에서 공통으로 돈다). 이 파일은 Builder 고유의 것만 본다 —
저장 전 시험 실행(ephemeral 기록, 승인 필요 도구 시뮬레이션), 개별 도구 확인,
구조 검증 실패 시 활성화 차단.

위임(`agent:*`) 관련 Registry 동작은 `tests/test_harness.py`가 이미 지키므로
여기서 다시 만들지 않는다.
"""

import json
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.accounts.tokens import issue_token
from services.harness.registry import Tool
from services.harness.runner import ModelDecision, check_tools, run_agent

AGENT = {
    "agent_id": "AG002",
    "name": "회의록 정리",
    "description": "회의록에서 결정사항을 뽑는다",
    "instruction": "결정사항만 뽑는다",
    "model": "gpt-5.6-luna",
    "reasoning_effort": "low",
    "max_iterations": 6,
    "is_prebuilt": False,
    "owner_name": "임준",
    "updated_at": None,
    "tool_refs": ["document_search"],
}


def auth_header(account_id="UA001"):
    return {"authorization": f"Bearer {issue_token(account_id)}"}


def _tool(ref, *, side_effect=False, handler=None):
    return Tool(
        ref=ref,
        name=ref,
        description="",
        input_schema={"type": "object", "properties": {}},
        handler=handler or (lambda **kwargs: {"ok": True, "got": kwargs}),
        side_effect=side_effect,
    )


class FakeModel:
    """미리 정해 둔 결정을 순서대로 돌려준다(`tests/test_harness.py`와 같은 헬퍼)."""

    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.calls = 0

    def __call__(self, system, messages, tools):
        self.calls += 1
        return self.decisions.pop(0)


class AlwaysToolModel:
    """끝내지 않고 계속 도구만 부르는 모델 — 반복 상한 테스트용."""

    def __init__(self, tool_ref="document_search"):
        self.tool_ref = tool_ref
        self.calls = 0

    def __call__(self, system, messages, tools):
        self.calls += 1
        return ModelDecision(
            tool_calls=[{"id": f"c{self.calls}", "tool_ref": self.tool_ref, "arguments": {}}]
        )


# ---------------------------------------------------------------------------
# 초안 대화 테스트 — POST /api/agents/build/test/
# ---------------------------------------------------------------------------


def ndjson(response) -> list[dict]:
    body = b"".join(response.streaming_content).decode("utf-8")
    return [json.loads(line) for line in body.splitlines() if line]


@patch("apps.agents.api_views.run_agent")
class BuilderTestRunApiTests(SimpleTestCase):
    def test_NDJSON_스트림으로_초안_설정을_그대로_전달한다(self, run_agent_mock):
        run_agent_mock.return_value = iter([{"type": "result", "text": "네", "complete": True}])

        with patch("apps.agents.api_views.AccountRepository") as account_repo:
            account_repo.team_id.return_value = "TM001"
            response = self.client.post(
                "/api/agents/build/test/",
                {
                    "instruction": "지침",
                    "tool_refs": ["document_search"],
                    "model": "gpt-5.6-terra",
                    "reasoning_effort": "high",
                    "max_iterations": 4,
                    "user_input": "질문",
                },
                content_type="application/json",
                headers=auth_header(),
            )
        events = ndjson(response)

        self.assertEqual(response["Content-Type"], "application/x-ndjson")
        self.assertEqual(events, [{"type": "result", "text": "네", "complete": True}])

        args = run_agent_mock.call_args.args
        kwargs = run_agent_mock.call_args.kwargs
        self.assertIsNone(args[0], "저장 전 초안이라 agent_id 가 없어야 한다")
        self.assertTrue(kwargs["dry_run"])
        draft = kwargs["draft"]
        self.assertEqual(draft["team_id"], "TM001")
        self.assertEqual(draft["instruction"], "지침")
        self.assertEqual(draft["model"], "gpt-5.6-terra")
        self.assertEqual(draft["reasoning_effort"], "high")
        self.assertEqual(draft["max_iterations"], 4)
        self.assertEqual(draft["tool_refs"], ["document_search"])

    def test_스트림_중_예외는_마지막_error_이벤트로_나간다(self, run_agent_mock):
        def boom(*_args, **_kwargs):
            yield {"type": "stage", "step": 1, "total": 3, "label": "생각하는 중"}
            raise TimeoutError("느립니다")

        run_agent_mock.side_effect = boom

        with patch("apps.agents.api_views.AccountRepository") as account_repo:
            account_repo.team_id.return_value = "TM001"
            response = self.client.post(
                "/api/agents/build/test/",
                {"instruction": "지침", "tool_refs": [], "user_input": "질문"},
                content_type="application/json",
                headers=auth_header(),
            )
        events = ndjson(response)

        self.assertEqual(response.status_code, 200, "응답이 이미 시작된 뒤라 500 을 낼 수 없다")
        self.assertEqual(events[-1]["type"], "error")

    @patch("apps.agents.api_views.CustomModelRepository")
    def test_팀이_등록한_커스텀_모델로도_시험_실행한다(self, customs, run_agent_mock):
        """저장은 되는데 시험은 안 되면 짝이 어긋난 화면이 된다."""

        customs.list_for_account.return_value = [{"model": "gemini-3.6-flash"}]
        run_agent_mock.return_value = iter([{"type": "result", "text": "네", "complete": True}])

        with patch("apps.agents.api_views.AccountRepository") as account_repo:
            account_repo.team_id.return_value = "TM001"
            response = self.client.post(
                "/api/agents/build/test/",
                {
                    "instruction": "지침",
                    "tool_refs": [],
                    "model": "gemini-3.6-flash",
                    "user_input": "질문",
                },
                content_type="application/json",
                headers=auth_header(),
            )
        ndjson(response)

        self.assertEqual(run_agent_mock.call_args.kwargs["draft"]["model"], "gemini-3.6-flash")

    @patch("apps.agents.api_views.CustomModelRepository")
    def test_모르는_모델은_스트림을_열기_전에_400(self, customs, run_agent_mock):
        """스트림이 시작되면 상태 코드를 못 바꾼다 — 거절은 그 전에 끝나야 한다."""

        customs.list_for_account.return_value = []

        response = self.client.post(
            "/api/agents/build/test/",
            {"instruction": "지침", "tool_refs": [], "model": "gpt-9", "user_input": "질문"},
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 400)
        run_agent_mock.assert_not_called()


class BuilderTestRunEphemeralTests(SimpleTestCase):
    """`run_agent(draft=...)` 자체의 안전 경계 — API 계층을 거치지 않고 직접 돈다."""

    def _run(self, *, tools, model, tool_refs, max_iterations=6):
        with patch("services.harness.runner.registry.load_for_refs", return_value=tools):
            return list(
                run_agent(
                    None,
                    "질문",
                    {},
                    model=model,
                    draft={"team_id": "TM001", "tool_refs": tool_refs, "max_iterations": max_iterations},
                    dry_run=True,
                )
            )

    @patch("services.harness.trace.ToolCallRepository")
    @patch("services.harness.trace.AgentRunRepository")
    def test_초안_시험은_DB에_기록하지_않는다(self, runs, calls):
        model = FakeModel([ModelDecision(text="답")])

        self._run(tools={}, model=model, tool_refs=[])

        runs.start.assert_not_called()
        calls.begin.assert_not_called()

    def test_승인_필요_도구는_SIMULATED_이고_handler를_안_부른다(self):
        """시험 실행은 승인할 사람이 없어 실제로 안 부르고, Loop 는 다음 회전으로 넘어간다."""

        executed = []
        tool = _tool("mcp:MT001", side_effect=True, handler=lambda **_: executed.append(1))
        model = FakeModel(
            [
                ModelDecision(tool_calls=[{"id": "c1", "tool_ref": "mcp:MT001", "arguments": {"n": 1}}]),
                ModelDecision(text="시뮬레이션했습니다."),
            ]
        )

        events = self._run(tools={"mcp:MT001": tool}, model=model, tool_refs=["mcp:MT001"])

        self.assertEqual(executed, [], "저장 전 시험엔 승인할 사람이 없다")
        finished = next(e for e in events if e["type"] == "tool_call_finished")
        self.assertEqual(finished["status"], "SIMULATED")

    def test_일반_읽기_도구는_실행_가능하다(self):
        executed = []
        tool = _tool("document_search", handler=lambda **kwargs: executed.append(kwargs) or {"ok": True})
        model = FakeModel(
            [
                ModelDecision(
                    tool_calls=[{"id": "c1", "tool_ref": "document_search", "arguments": {"query": "x"}}]
                ),
                ModelDecision(text="찾았습니다."),
            ]
        )

        events = self._run(tools={"document_search": tool}, model=model, tool_refs=["document_search"])

        self.assertEqual(len(executed), 1)
        finished = next(e for e in events if e["type"] == "tool_call_finished")
        self.assertEqual(finished["status"], "OK")

    def test_반복_상한_도달은_complete_false로_끝난다(self):
        tool = _tool("document_search")
        model = AlwaysToolModel("document_search")

        events = self._run(
            tools={"document_search": tool}, model=model, tool_refs=["document_search"], max_iterations=2
        )

        self.assertEqual(model.calls, 2)
        self.assertEqual(events[-1]["type"], "result")
        self.assertFalse(events[-1]["complete"])
        self.assertEqual(events[-1]["stopped_reason"], "max_iterations")


# ---------------------------------------------------------------------------
# 개별 도구 확인 — check_tools() (POST /api/agents/build/check-tools/ 의 본체)
# ---------------------------------------------------------------------------


class CheckToolsTests(SimpleTestCase):
    def _check(self, *, tools, tool_refs, arguments_by_ref=None, team_id="TM001", account_id="UA001"):
        with patch("services.harness.runner.registry.load_for_refs", return_value=tools):
            return check_tools(
                team_id=team_id,
                account_id=account_id,
                tool_refs=tool_refs,
                arguments_by_ref=arguments_by_ref,
            )

    def test_일반_도구_성공(self):
        tool = _tool("document_search", handler=lambda **_: {"hits": 3})

        results = self._check(tools={"document_search": tool}, tool_refs=["document_search"])

        self.assertEqual(results[0]["status"], "OK")
        self.assertEqual(results[0]["output"], {"hits": 3})

    def test_도구_하나가_실패해도_다음_도구를_계속_확인한다(self):
        def boom(**_kwargs):
            raise TimeoutError("느립니다")

        failing = _tool("document_search", handler=boom)
        ok = _tool("workload_report", handler=lambda **_: {"n": 1})

        results = self._check(
            tools={"document_search": failing, "workload_report": ok},
            tool_refs=["document_search", "workload_report"],
        )

        self.assertEqual(results[0]["status"], "FAILED")
        self.assertEqual(results[0]["error_code"], "TimeoutError")
        self.assertEqual(results[1]["status"], "OK")

    def test_승인_필요_도구는_SIMULATED(self):
        executed = []
        tool = _tool("mcp:MT001", side_effect=True, handler=lambda **_: executed.append(1))

        results = self._check(tools={"mcp:MT001": tool}, tool_refs=["mcp:MT001"])

        self.assertEqual(results[0]["status"], "SIMULATED")
        self.assertEqual(executed, [])

    def test_task_extraction은_SKIPPED(self):
        results = self._check(tools={}, tool_refs=["task_extraction"])

        self.assertEqual(results[0]["status"], "SKIPPED")

    def test_알수없는_도구는_실패로_반환한다(self):
        results = self._check(tools={}, tool_refs=["document_search"])

        self.assertEqual(results[0]["status"], "FAILED")
        self.assertEqual(results[0]["error_code"], "ToolNotAllowed")

    def test_서버가_주입하는_team_id가_사용자_arguments보다_우선한다(self):
        seen = {}
        tool = _tool("document_search", handler=lambda **kwargs: seen.update(kwargs) or {})

        self._check(
            tools={"document_search": tool},
            tool_refs=["document_search"],
            arguments_by_ref={"document_search": {"query": "x", "team_id": "TM999"}},
            team_id="TM001",
        )

        self.assertEqual(seen["team_id"], "TM001")

    @patch("services.harness.trace.ToolCallRepository")
    def test_시험_실행_로그를_DB에_남기지_않는다(self, calls):
        tool = _tool("document_search", handler=lambda **_: {"ok": True})

        self._check(tools={"document_search": tool}, tool_refs=["document_search"])

        calls.begin.assert_not_called()


class BuilderToolCheckApiTests(SimpleTestCase):
    def test_로그인_없이는_401(self):
        response = self.client.post(
            "/api/agents/build/check-tools/",
            {"tool_refs": ["document_search"]},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)

    @patch("apps.agents.api_views.check_tools")
    @patch("apps.agents.api_views.AccountRepository")
    def test_팀_id로_check_tools를_부른다(self, account_repo, check_tools_mock):
        account_repo.team_id.return_value = "TM001"
        check_tools_mock.return_value = [
            {"tool_ref": "document_search", "tool_name": "문서 검색", "status": "OK"}
        ]

        response = self.client.post(
            "/api/agents/build/check-tools/",
            {"tool_refs": ["document_search"], "arguments": {"document_search": {"query": "x"}}},
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["status"], "OK")
        self.assertEqual(check_tools_mock.call_args.kwargs["team_id"], "TM001")
        self.assertEqual(check_tools_mock.call_args.kwargs["tool_refs"], ["document_search"])


# ---------------------------------------------------------------------------
# 생명주기 — DRAFT/ACTIVE/DISABLED
# ---------------------------------------------------------------------------


@patch("apps.agents.api_views.AgentCrudRepository")
class AgentLifecycleApiTests(SimpleTestCase):
    """기본 제공 에이전트 보호·팀 경계는 `tests/test_agents.py`가 이미 지킨다."""

    def test_생성_시_status를_직접_주지_않는다(self, repo):
        """DRAFT 는 DB 기본값이 정한다 — API 가 status 를 넘기면 안 된다."""

        repo.create.return_value = {**AGENT, "status": "DRAFT"}

        self.client.post(
            "/api/agents/",
            {"name": "새 에이전트", "tool_refs": []},
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertNotIn("status", repo.create.call_args.kwargs["fields"])

    def test_DRAFT_활성화_성공(self, repo):
        repo.get.return_value = {**AGENT, "status": "DRAFT"}
        repo.set_status.return_value = {**AGENT, "status": "ACTIVE"}

        response = self.client.post("/api/agents/AG002/activate/", headers=auth_header())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ACTIVE")
        self.assertEqual(repo.set_status.call_args.kwargs["status"], "ACTIVE")

    @patch("apps.agents.api_views.CustomModelRepository")
    def test_사라진_커스텀_모델은_활성화를_막는다(self, customs, repo):
        """**활성화 뒤 첫 대화에서 죽는 것을 여기서 끊는다.**

        저장할 때는 있던 커스텀 모델을 팀이 Model 탭에서 지우면, 그걸 쓰던 초안은
        아무 표시 없이 남는다. 화면은 활성화할 때 본문을 다시 보내지 않으므로
        여기서 안 보면 아무도 안 본다.

        에이전트가 기본 6종만 고르던 시절에는 있을 수 없던 경로다 — 저장된 모델이
        나중에 사라질 수 있게 되면서 생겼다(2026-08-12).
        """

        repo.get.return_value = {**AGENT, "status": "DRAFT", "model": "models/gemini-3.6-flash"}
        customs.list_for_account.return_value = []

        response = self.client.post("/api/agents/AG002/activate/", headers=auth_header())

        self.assertEqual(response.status_code, 400)
        repo.set_status.assert_not_called()

    @patch("apps.agents.api_views.CustomModelRepository")
    def test_살아있는_커스텀_모델은_활성화된다(self, customs, repo):
        repo.get.return_value = {**AGENT, "status": "DRAFT", "model": "models/gemini-3.6-flash"}
        customs.list_for_account.return_value = [{"model": "models/gemini-3.6-flash"}]
        repo.set_status.return_value = {**AGENT, "status": "ACTIVE"}

        response = self.client.post("/api/agents/AG002/activate/", headers=auth_header())

        self.assertEqual(response.status_code, 200)

    def test_없는_도구가_남아있으면_409이며_DRAFT를_유지한다(self, repo):
        """저장 뒤 팀이 MCP 서버 연결을 끊는 등, DB에 저장된 도구가 그 사이
        사라질 수 있다 — 활성화 시점에 DB 값으로 다시 구조 검증한다."""

        repo.get.return_value = {**AGENT, "status": "DRAFT", "tool_refs": ["mcp:MT999"]}
        repo.team_tool_refs.return_value = []

        response = self.client.post("/api/agents/AG002/activate/", headers=auth_header())

        self.assertEqual(response.status_code, 409)
        repo.set_status.assert_not_called()

    def test_DISABLED_에서도_다시_활성화된다(self, repo):
        repo.get.return_value = {**AGENT, "status": "DISABLED"}
        repo.set_status.return_value = {**AGENT, "status": "ACTIVE"}

        response = self.client.post("/api/agents/AG002/activate/", headers=auth_header())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ACTIVE")

    def test_ACTIVE에서_DISABLED로(self, repo):
        repo.set_status.return_value = {**AGENT, "status": "DISABLED"}

        response = self.client.post("/api/agents/AG002/disable/", headers=auth_header())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "DISABLED")
        self.assertEqual(repo.set_status.call_args.kwargs["status"], "DISABLED")
