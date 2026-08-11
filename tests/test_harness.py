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

    def test_멈출_때_재개_정보를_함께_내보낸다(self, _get, load_tools, runs, calls):
        load_tools.return_value = {"mcp:MT001": echo_tool("mcp:MT001", side_effect=True)}
        runs.start.return_value = "RUN-1"
        call = {"id": "c1", "tool_ref": "mcp:MT001", "arguments": {"issues": ["A"]}}
        model = FakeModel([ModelDecision(tool_calls=[call])])

        events = list(run_agent("AG001", "올려줘", model=model))
        resume = events[-1]["resume"]

        self.assertEqual(resume["tool_call"], call)
        # 멈춘 시점의 대화가 그대로 들어 있어야 재개가 이어진다.
        self.assertEqual(resume["messages"][0], {"role": "user", "content": "올려줘"})
        self.assertEqual(len(resume["messages"]), 2)

    def test_재개는_모델을_다시_묻지_않는다(self, _get, load_tools, runs, calls):
        """승인한 것과 실제로 실행되는 것이 달라지지 않게 한다."""

        executed = []
        load_tools.return_value = {
            "mcp:MT001": echo_tool(
                "mcp:MT001",
                side_effect=True,
                handler=lambda **kwargs: executed.append(kwargs) or {"created": 3},
            )
        }
        runs.start.return_value = "RUN-1"
        calls.begin.return_value = "TC-1"
        approved = {"id": "c1", "tool_ref": "mcp:MT001", "arguments": {"issues": ["A", "C"]}}
        # 재개 턴에서는 모델을 부르지 않으므로, 모델은 그 뒤 한 번만 답한다.
        model = FakeModel([ModelDecision(text="2건 등록했습니다.")])

        events = list(
            run_agent(
                "AG001",
                "",
                {
                    "messages": [
                        {"role": "user", "content": "올려줘"},
                        # 실제로는 모델이 준 reasoning + function_call 원본이 그대로
                        # 들어 있다. 그 짝이 깨지면 API 가 400 을 낸다.
                        {"type": "reasoning", "id": "rs_1", "summary": []},
                        {
                            "type": "function_call",
                            "call_id": "c1",
                            "name": "mcp:MT001",
                            "arguments": '{"issues": ["A", "C"]}',
                        },
                    ],
                    "resume_tool_call": approved,
                    "approved_tool_calls": ["mcp:MT001"],
                },
                model=model,
            )
        )

        self.assertEqual(executed[0]["issues"], ["A", "C"])
        self.assertEqual(model.calls, 1, "재개 턴에서 모델을 다시 부르면 안 된다")
        self.assertEqual(events[-1]["type"], "result")
        self.assertNotIn("awaiting_confirmation", [e["type"] for e in events])

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


@patch("services.harness.trace.ToolCallRepository")
@patch("services.harness.trace.AgentRunRepository")
@patch("services.harness.runner.registry.load_for_agent")
@patch("services.harness.runner.AgentRepository.get", return_value=AGENT)
class StreamingToolTests(SimpleTestCase):
    """오래 걸리는 도구는 진행을 흘리고, 모델에게는 요약만 준다(단계 4)."""

    @staticmethod
    def _streaming_handler(**_kwargs):
        yield {"type": "stage", "step": 1, "total": 5, "label": "수행할 업무 찾기"}
        yield {"type": "task_extraction_result", "result": {"tasks": [1, 2, 3], "warnings": []}}
        return {"task_count": 3, "warnings": []}

    def test_도구의_진행이_그대로_중계된다(self, _get, load_tools, runs, calls):
        load_tools.return_value = {
            "task_extraction": echo_tool("task_extraction", handler=self._streaming_handler)
        }
        runs.start.return_value = "RUN-1"
        calls.begin.return_value = "TC-1"
        model = FakeModel(
            [
                ModelDecision(tool_calls=[{"id": "c1", "tool_ref": "task_extraction", "arguments": {}}]),
                ModelDecision(text="3건 뽑았습니다."),
            ]
        )

        events = list(run_agent("AG001", "업무 정리해줘", model=model))
        types = [event["type"] for event in events]

        self.assertEqual(
            types,
            [
                "stage",
                "tool_call_started",
                "stage",
                "task_extraction_result",
                "tool_call_finished",
                "stage",
                "result",
            ],
        )

    def test_도구가_흘린_stage_는_Loop_의_stage_와_구별된다(self, _get, load_tools, runs, calls):
        """둘 다 `stage` 라 표시가 없으면 진행 카드가 1/4 → 1/5 → 2/4 로 튄다."""

        load_tools.return_value = {
            "task_extraction": echo_tool("task_extraction", handler=self._streaming_handler)
        }
        runs.start.return_value = "RUN-1"
        calls.begin.return_value = "TC-1"
        model = FakeModel(
            [
                ModelDecision(tool_calls=[{"id": "c1", "tool_ref": "task_extraction", "arguments": {}}]),
                ModelDecision(text="3건 뽑았습니다."),
            ]
        )

        events = list(run_agent("AG001", "업무 정리해줘", model=model))
        stages = [e for e in events if e["type"] == "stage"]

        loop_stages = [e for e in stages if "tool_ref" not in e]
        tool_stages = [e for e in stages if e.get("tool_ref") == "task_extraction"]
        self.assertEqual(len(loop_stages), 2)
        self.assertEqual(len(tool_stages), 1)
        self.assertEqual(tool_stages[0]["tool_call_id"], "TC-1")
        # 도구가 흘린 결과 이벤트도 같은 표시를 달고 나간다.
        payload = next(e for e in events if e["type"] == "task_extraction_result")
        self.assertEqual(payload["tool_ref"], "task_extraction")

    def test_결과는_이벤트로_나가고_모델에는_요약만_간다(self, _get, load_tools, runs, calls):
        """업무 20건을 바깥 모델에 다시 넣으면 근거가 흔들리고 토큰도 그만큼 든다."""

        seen = {}

        class Recorder(FakeModel):
            def __call__(self, system, messages, tools):
                seen["messages"] = list(messages)
                return super().__call__(system, messages, tools)

        load_tools.return_value = {
            "task_extraction": echo_tool("task_extraction", handler=self._streaming_handler)
        }
        runs.start.return_value = "RUN-1"
        calls.begin.return_value = "TC-1"
        model = Recorder(
            [
                ModelDecision(tool_calls=[{"id": "c1", "tool_ref": "task_extraction", "arguments": {}}]),
                ModelDecision(text="3건 뽑았습니다."),
            ]
        )

        events = list(run_agent("AG001", "업무 정리해줘", model=model))

        # 화면이 그릴 결과는 이벤트에 통째로 있다.
        payload = next(e for e in events if e["type"] == "task_extraction_result")
        self.assertEqual(payload["result"]["tasks"], [1, 2, 3])
        # 모델에게 돌아간 것은 건수뿐이다.
        tool_turn = seen["messages"][-1]
        self.assertEqual(tool_turn["type"], "function_call_output")
        self.assertIn('"task_count": 3', tool_turn["output"])
        self.assertNotIn("tasks", tool_turn["output"])

    def test_도구가_중간에_터져도_FAILED_로_남는다(self, _get, load_tools, runs, calls):
        def half_way(**_kwargs):
            yield {"type": "stage", "step": 1, "total": 5, "label": "수행할 업무 찾기"}
            raise ValueError("기준 문서가 아직 지정되지 않았습니다.")

        load_tools.return_value = {
            "task_extraction": echo_tool("task_extraction", handler=half_way)
        }
        runs.start.return_value = "RUN-1"
        calls.begin.return_value = "TC-1"
        model = FakeModel(
            [
                ModelDecision(tool_calls=[{"id": "c1", "tool_ref": "task_extraction", "arguments": {}}]),
                ModelDecision(text="기준 문서를 먼저 골라 주세요."),
            ]
        )

        events = list(run_agent("AG001", "업무 정리해줘", model=model))
        finished = next(e for e in events if e["type"] == "tool_call_finished")

        self.assertEqual(finished["status"], "FAILED")
        self.assertEqual(calls.end.call_args.kwargs["error_code"], "ValueError")
        # 진행 이벤트는 이미 나갔다 — 터지기 전까지 한 일은 화면에 남는다.
        self.assertIn("stage", [e["type"] for e in events])

    def test_프로젝트_문맥은_모델이_아니라_세션이_정한다(self, _get, load_tools, runs, calls):
        seen = {}
        load_tools.return_value = {
            "task_extraction": echo_tool(
                "task_extraction", handler=lambda **kwargs: seen.update(kwargs) or {}
            )
        }
        runs.start.return_value = "RUN-1"
        calls.begin.return_value = "TC-1"
        model = FakeModel(
            [
                ModelDecision(
                    tool_calls=[
                        {
                            "id": "c1",
                            "tool_ref": "task_extraction",
                            "arguments": {"proj_id": "PJ999"},
                        }
                    ]
                ),
                ModelDecision(text="끝"),
            ]
        )

        list(
            run_agent(
                "AG001", "업무 정리해줘", {"proj_id": "PJ001", "account_id": "UA001"}, model=model
            )
        )

        self.assertEqual(seen["proj_id"], "PJ001")


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
