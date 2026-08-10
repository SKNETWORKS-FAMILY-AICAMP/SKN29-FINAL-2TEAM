"""Harness 단위 테스트. DB 는 띄우지 않고 Repository 를 mock 한다.

검증하는 것은 **Loop 의 순서와 로그**다. 모델 품질이 아니라, 같은 입력에
같은 로그가 남는가 — 평가(4_평가_설계.md)가 그 로그를 세기 때문이다.
"""

from unittest.mock import patch

from django.test import SimpleTestCase

from services.harness import registry, scaffold, trace
from services.harness.registry import Tool, ToolNotAllowed
from services.harness.runner import ModelDecision, run_agent

AGENT = {
    "agent_id": "AG001",
    "team_id": "TM001",
    "name": "업무 추출 에이전트",
    "description": "",
    "instruction": "근거는 원문에서만 가져온다.",
    "model": "gpt-5.6-luna",
    "reasoning_effort": "low",
    "max_iterations": 10,
    "is_prebuilt": True,
    "status": "ACTIVE",
}


def echo_tool(ref="document_search", *, side_effect=False, handler=None):
    return Tool(
        ref=ref,
        name="문서 검색",
        description="",
        input_schema={"type": "object", "properties": {}},
        handler=handler or (lambda **kwargs: {"evidence": ["E1"], "got": kwargs}),
        side_effect=side_effect,
    )


class ScaffoldTests(SimpleTestCase):
    def test_공통_스캐폴드가_세_가지를_말한다(self):
        text = scaffold.compose(instruction="", max_iterations=10)

        self.assertIn("계획", text)
        self.assertIn("10회", text)
        self.assertIn("추측하지 않는다", text)

    def test_에이전트_지시는_스캐폴드_뒤에_붙는다(self):
        """순서가 바뀌면 '추측 금지'가 개별 지시를 덮어쓴다."""

        text = scaffold.compose(instruction="표만 읽어라", max_iterations=3)

        self.assertLess(text.index("추측하지 않는다"), text.index("표만 읽어라"))

    def test_지시가_비어도_스캐폴드는_나온다(self):
        text = scaffold.compose(instruction="   ", max_iterations=5)

        self.assertIn("추측하지 않는다", text)
        self.assertNotIn("[이 에이전트의 지시]", text)


class InputSummaryTests(SimpleTestCase):
    def test_긴_값은_잘라서_남긴다(self):
        summary = trace.summarize_input({"query": "가" * 500})

        self.assertLessEqual(len(summary), trace.INPUT_SUMMARY_MAX)
        self.assertIn("query=", summary)


class RegistryTests(SimpleTestCase):
    @patch("services.harness.registry.AgentRepository.mcp_tools", return_value=[])
    @patch("services.harness.registry.AgentRepository.tool_refs", return_value=["document_search"])
    def test_허용_목록에_없는_내장_도구는_빠진다(self, _refs, _mcp):
        tools = registry.load_for_agent(agent_id="AG001", team_id="TM001")

        self.assertEqual(set(tools), {"document_search"})
        self.assertNotIn("workload_report", tools)

    @patch("services.harness.registry.AgentRepository.tool_refs", return_value=["mcp:MT001"])
    @patch("services.harness.registry.AgentRepository.mcp_tools")
    def test_MCP_도구는_부작용이_있다고_본다(self, mcp_tools, _refs):
        """list_tools 응답은 읽기 전용인지 알려 주지 않는다. 안전한 쪽으로 가정한다."""

        mcp_tools.return_value = [
            {
                "tool_ref": "mcp:MT001",
                "mcp_tool_id": "MT001",
                "name": "jira_create_issues",
                "description": "이슈 벌크 생성",
                "input_schema": {"type": "object"},
            }
        ]

        tools = registry.load_for_agent(agent_id="AG001", team_id="TM001")

        self.assertTrue(tools["mcp:MT001"].side_effect)

    def test_허용되지_않은_도구를_부르면_거부한다(self):
        with self.assertRaises(ToolNotAllowed):
            registry.resolve({"document_search": echo_tool()}, "workload_report")


@patch("services.harness.trace.ToolCallRepository")
@patch("services.harness.trace.AgentRunRepository")
@patch("services.harness.runner.registry.load_for_agent")
@patch("services.harness.runner.AgentRepository.get", return_value=AGENT)
class RunAgentTests(SimpleTestCase):
    """완료 기준 — 입력 → 내장 tool 1회 → 응답 Loop 가 돌고 로그 행이 남는다."""

    def test_도구_한_번_부르고_답한다(self, _get, load_tools, runs, calls):
        load_tools.return_value = {"document_search": echo_tool()}
        runs.start.return_value = "RUN-1"
        calls.begin.return_value = "TC-1"
        model = FakeModel(
            [
                ModelDecision(
                    tool_calls=[{"id": "c1", "tool_ref": "document_search", "arguments": {"query": "일정"}}],
                    token_in=100,
                    token_out=20,
                ),
                ModelDecision(text="일정은 8월 20일입니다.", token_in=300, token_out=40),
            ]
        )

        events = list(run_agent("AG001", "일정 알려줘", model=model))
        types = [event["type"] for event in events]

        self.assertEqual(
            types,
            ["stage", "tool_call_started", "tool_call_finished", "stage", "result"],
        )
        self.assertEqual(events[-1]["text"], "일정은 8월 20일입니다.")
        self.assertTrue(events[-1]["complete"])

    def test_agent_run_과_tool_call_행이_남는다(self, _get, load_tools, runs, calls):
        load_tools.return_value = {"document_search": echo_tool()}
        runs.start.return_value = "RUN-1"
        calls.begin.return_value = "TC-1"
        model = FakeModel(
            [
                ModelDecision(
                    tool_calls=[{"id": "c1", "tool_ref": "document_search", "arguments": {"query": "일정"}}],
                    token_in=100,
                    token_out=20,
                ),
                ModelDecision(text="끝", token_in=300, token_out=40),
            ]
        )

        list(run_agent("AG001", "일정 알려줘", model=model))

        runs.start.assert_called_once_with(
            agent_id="AG001", session_id=None, parent_run_id=None
        )
        runs.finish.assert_called_once_with(
            run_id="RUN-1", status="DONE", iterations=2, token_in=400, token_out=60
        )
        calls.begin.assert_called_once_with(
            run_id="RUN-1", tool_ref="document_search", input_summary="query=일정"
        )
        self.assertEqual(calls.end.call_args.kwargs["status"], "OK")

    def test_선기록_먼저_실행_나중이다(self, _get, load_tools, runs, calls):
        """PENDING INSERT 가 handler 보다 앞서야 죽은 호출이 로그에 남는다."""

        order = []
        calls.begin.side_effect = lambda **_: order.append("begin") or "TC-1"
        calls.end.side_effect = lambda **_: order.append("end")
        runs.start.return_value = "RUN-1"

        def handler(**_kwargs):
            order.append("handler")
            return {}

        load_tools.return_value = {"document_search": echo_tool(handler=handler)}
        model = FakeModel(
            [
                ModelDecision(tool_calls=[{"id": "c1", "tool_ref": "document_search", "arguments": {}}]),
                ModelDecision(text="끝"),
            ]
        )

        list(run_agent("AG001", "질문", model=model))

        self.assertEqual(order, ["begin", "handler", "end"])

    def test_도구가_터져도_run_은_계속되고_FAILED_로_남는다(self, _get, load_tools, runs, calls):
        def boom(**_kwargs):
            raise TimeoutError("느립니다")

        load_tools.return_value = {"document_search": echo_tool(handler=boom)}
        runs.start.return_value = "RUN-1"
        calls.begin.return_value = "TC-1"
        model = FakeModel(
            [
                ModelDecision(tool_calls=[{"id": "c1", "tool_ref": "document_search", "arguments": {}}]),
                ModelDecision(text="검색에 실패해서 답할 수 없습니다."),
            ]
        )

        events = list(run_agent("AG001", "질문", model=model))
        finished = next(e for e in events if e["type"] == "tool_call_finished")

        self.assertEqual(finished["status"], "FAILED")
        self.assertEqual(finished["error_code"], "TimeoutError")
        self.assertEqual(calls.end.call_args.kwargs["error_code"], "TimeoutError")
        # run 자체는 정상 종료다 — 도구 하나가 실패한 것과 실행이 실패한 것은 다르다.
        self.assertEqual(runs.finish.call_args.kwargs["status"], "DONE")
        self.assertEqual(events[-1]["type"], "result")

    def test_상한을_넘기면_코드가_멈춘다(self, _get, load_tools, runs, calls):
        """모델이 계속 도구만 부르는 경우. 권고가 아니라 코드가 끊는다."""

        load_tools.return_value = {"document_search": echo_tool()}
        runs.start.return_value = "RUN-1"
        calls.begin.return_value = "TC-1"
        model = AlwaysToolModel()

        with patch(
            "services.harness.runner.AgentRepository.get", return_value={**AGENT, "max_iterations": 3}
        ):
            events = list(run_agent("AG001", "질문", model=model))

        self.assertEqual(model.calls, 3)
        self.assertEqual(events[-1]["type"], "result")
        self.assertFalse(events[-1]["complete"])
        self.assertEqual(events[-1]["stopped_reason"], "max_iterations")
        self.assertEqual(runs.finish.call_args.kwargs["iterations"], 3)

    def test_부작용_도구는_승인_전에_실행하지_않는다(self, _get, load_tools, runs, calls):
        executed = []
        load_tools.return_value = {
            "mcp:MT001": echo_tool(
                "mcp:MT001", side_effect=True, handler=lambda **_: executed.append(1)
            )
        }
        runs.start.return_value = "RUN-1"
        model = FakeModel(
            [ModelDecision(tool_calls=[{"id": "c1", "tool_ref": "mcp:MT001", "arguments": {"n": 20}}])]
        )

        events = list(run_agent("AG001", "Jira에 올려줘", model=model))

        self.assertEqual(events[-1]["type"], "awaiting_confirmation")
        self.assertEqual(events[-1]["tool_ref"], "mcp:MT001")
        self.assertEqual(executed, [], "승인 전에 실행되면 안 된다")
        calls.begin.assert_not_called()

    def test_승인된_뒤에는_실행한다(self, _get, load_tools, runs, calls):
        executed = []
        load_tools.return_value = {
            "mcp:MT001": echo_tool(
                "mcp:MT001", side_effect=True, handler=lambda **_: executed.append(1) or {"ok": True}
            )
        }
        runs.start.return_value = "RUN-1"
        calls.begin.return_value = "TC-1"
        model = FakeModel(
            [
                ModelDecision(tool_calls=[{"id": "c1", "tool_ref": "mcp:MT001", "arguments": {}}]),
                ModelDecision(text="20건 등록했습니다."),
            ]
        )

        events = list(
            run_agent(
                "AG001", "Jira에 올려줘", {"approved_tool_calls": ["mcp:MT001"]}, model=model
            )
        )

        self.assertEqual(executed, [1])
        self.assertEqual(events[-1]["type"], "result")

    def test_허용되지_않은_도구를_부르면_모델에게_돌려준다(self, _get, load_tools, runs, calls):
        load_tools.return_value = {"document_search": echo_tool()}
        runs.start.return_value = "RUN-1"
        model = FakeModel(
            [
                ModelDecision(tool_calls=[{"id": "c1", "tool_ref": "workload_report", "arguments": {}}]),
                ModelDecision(text="그 도구는 못 씁니다."),
            ]
        )

        events = list(run_agent("AG001", "부하 알려줘", model=model))

        calls.begin.assert_not_called()
        self.assertEqual(events[-1]["type"], "result")

    def test_스트림을_중간에_닫으면_run_이_FAILED_로_닫힌다(self, _get, load_tools, runs, calls):
        """브라우저 이탈. 안 닫으면 그 run 이 영원히 RUNNING 으로 남는다."""

        load_tools.return_value = {"document_search": echo_tool()}
        runs.start.return_value = "RUN-1"
        model = FakeModel([ModelDecision(text="답")])

        events = run_agent("AG001", "질문", model=model)
        next(events)
        events.close()

        self.assertEqual(runs.finish.call_args.kwargs["status"], "FAILED")

    def test_team_id_는_모델이_아니라_서버가_넣는다(self, _get, load_tools, runs, calls):
        """프롬프트로 남의 팀 문서를 읽어 내지 못하게 한다."""

        seen = {}
        load_tools.return_value = {
            "document_search": echo_tool(handler=lambda **kwargs: seen.update(kwargs) or {})
        }
        runs.start.return_value = "RUN-1"
        calls.begin.return_value = "TC-1"
        model = FakeModel(
            [
                ModelDecision(
                    tool_calls=[
                        {
                            "id": "c1",
                            "tool_ref": "document_search",
                            "arguments": {"query": "일정", "team_id": "TM999"},
                        }
                    ]
                ),
                ModelDecision(text="끝"),
            ]
        )

        list(run_agent("AG001", "질문", model=model))

        self.assertEqual(seen["team_id"], "TM001")

    def test_요청자가_없으면_부하_도구만_실패한다(self, _get, load_tools, runs, calls):
        """평가·A2A 경로에는 계정이 없다. 남의 팀 값을 쓰는 대신 이 도구만 죽인다."""

        load_tools.return_value = {"workload_report": echo_tool("workload_report")}
        runs.start.return_value = "RUN-1"
        calls.begin.return_value = "TC-1"
        model = FakeModel(
            [
                ModelDecision(tool_calls=[{"id": "c1", "tool_ref": "workload_report", "arguments": {}}]),
                ModelDecision(text="부하는 확인하지 못했습니다."),
            ]
        )

        events = list(run_agent("AG001", "부하 알려줘", model=model))
        finished = next(e for e in events if e["type"] == "tool_call_finished")

        self.assertEqual(finished["status"], "FAILED")
        self.assertEqual(finished["error_code"], "ValueError")
        self.assertEqual(runs.finish.call_args.kwargs["status"], "DONE")


class FakeModel:
    """미리 정해 둔 결정을 순서대로 돌려준다."""

    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.calls = 0

    def __call__(self, system, messages, tools):
        self.calls += 1
        return self.decisions.pop(0)


class AlwaysToolModel:
    """끝내지 않고 계속 도구만 부르는 모델."""

    def __init__(self):
        self.calls = 0

    def __call__(self, system, messages, tools):
        self.calls += 1
        return ModelDecision(
            tool_calls=[{"id": f"c{self.calls}", "tool_ref": "document_search", "arguments": {}}]
        )
