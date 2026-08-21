"""Harness 단위 테스트. DB 는 띄우지 않고 Repository 를 mock 한다.

검증하는 것은 **Loop 의 순서와 로그**다. 모델 품질이 아니라, 같은 입력에
같은 로그가 남는가 — 평가(4_평가_설계.md)가 그 로그를 세기 때문이다.
"""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.connectors.oauth import OAuthError
from services.harness import registry, scaffold, trace
from services.harness.registry import Tool, ToolInputError, ToolNotAllowed
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
    def test_공통_스캐폴드가_지켜야_할_것을_말한다(self):
        text = scaffold.compose(instruction="", max_iterations=10)

        self.assertIn("10회", text)
        self.assertIn("추측하지 않는다", text)
        # 매 답변 앞에 "계획:"이 붙던 것을 막는다(2026-08-11).
        self.assertIn("계획을 먼저 늘어놓지 않는다", text)
        # 도구가 없는 능력(번역·코딩 등)을 나열하던 것을 막는다.
        self.assertIn("가진 도구가 네가 할 수 있는 일", text)

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

    def test_MCP_실패는_왜_실패했는지가_남는다(self, _get, load_tools, runs, calls):
        """클래스 이름만 남기면 전부 「McpError」 하나로 뭉개진다 — 서버가 죽은
        것과 토큰이 만료된 것을 기록만 보고는 못 가른다. 운영자 콘솔의 「실패한
        도구」 열도 이 코드를 그대로 보여준다."""

        from services.mcp import McpError

        def boom(**_kwargs):
            raise McpError("401", "MCP 서버 인증에 실패했습니다.")

        load_tools.return_value = {"mcp:MT001": echo_tool(handler=boom)}
        runs.start.return_value = "RUN-1"
        calls.begin.return_value = "TC-1"
        model = FakeModel(
            [
                ModelDecision(tool_calls=[{"id": "c1", "tool_ref": "mcp:MT001", "arguments": {}}]),
                ModelDecision(text="도구를 쓰지 못했습니다."),
            ]
        )

        events = list(run_agent("AG001", "질문", model=model))
        finished = next(e for e in events if e["type"] == "tool_call_finished")

        self.assertEqual(finished["error_code"], "401")
        self.assertEqual(calls.end.call_args.kwargs["error_code"], "401")

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

    def test_결과는_이벤트로_나가고_모델에는_근거_없이_간다(self, _get, load_tools, runs, calls):
        """근거 문장을 바깥 모델에 다시 넣으면 그것을 한 번 더 요약하며 흔들린다."""

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
        # **근거는 안 간다.** 원래 결정이 막으려던 것은 근거의 재요약이다.
        # 제목·역할·공수는 간다 — 없으면 모델이 등록할 업무를 모른다.
        self.assertNotIn("evidence", tool_turn["output"])

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


SUB_AGENT = AGENT | {"agent_id": "AG002", "name": "Jira 등록 에이전트", "max_iterations": 4}

#: `AgentRepository.callable_agents` 가 주는 모양 그대로.
SUB_ROW = {
    "tool_ref": "agent:AG002",
    "agent_id": "AG002",
    "name": "Jira 등록 에이전트",
    "description": "확인받은 업무를 Jira 에 올립니다.",
}


@patch("services.harness.registry.create_jira_issues")
@patch("services.harness.registry.find_jira_account_id_by_email")
@patch("services.harness.registry.TeamRepository")
@patch("services.harness.registry.AccountRepository")
class JiraIssueRegistrationShortCircuitTests(SimpleTestCase):
    """`_jira_create_issues()` 내부에서, 담당자 기본값 조회가 자격증명
    문제(`OAuthError`)로 실패하면 이슈 생성 API(`create_jira_issues`)까지
    가면 안 된다(2026-08-20) — 둘 다 같은 자격증명을 쓰므로 뒤쪽도 반드시
    같은 이유로 실패한다. 여기서 미리 멈추지 않으면 실패할 걸 이미 아는
    Jira 요청을 한 번 더 보내는 것뿐이고, 그 결과를 기다리는 모델 턴도
    낭비된다.
    """

    def _wire(self, accounts, teams):
        accounts.team_id.return_value = "TM001"
        accounts.email.return_value = "member@example.com"
        teams.leader_account_id.return_value = "LEADER1"

    def test_담당자_조회가_인증오류면_등록_API를_부르지_않는다(
        self, accounts, teams, find_email, create_issues
    ):
        self._wire(accounts, teams)
        find_email.side_effect = OAuthError("Jira 인증이 만료되었습니다. 설정에서 다시 연결해 주세요.")

        with self.assertRaises(OAuthError):
            registry._jira_create_issues(
                account_id="UA001",
                project_key="KAN",
                issues=[{"title": "회의록 정리", "issuetype": "작업"}],
            )

        create_issues.assert_not_called()

    def test_담당자를_못_찾았을_뿐이면_등록은_그대로_진행한다(
        self, accounts, teams, find_email, create_issues
    ):
        self._wire(accounts, teams)
        find_email.return_value = None  # 0건/다건 — 자격증명 문제가 아니다
        create_issues.return_value = {"created": [{"key": "KAN-1"}], "failed": [], "project_key": "KAN"}

        registry._jira_create_issues(
            account_id="UA001",
            project_key="KAN",
            issues=[{"title": "회의록 정리", "issuetype": "작업"}],
        )

        create_issues.assert_called_once()
        sent_issues = create_issues.call_args.kwargs["issues"]
        self.assertNotIn("assignee_account_id", sent_issues[0])

    def test_담당자를_이미_지정했으면_조회_자체를_안_한다(
        self, accounts, teams, find_email, create_issues
    ):
        self._wire(accounts, teams)
        create_issues.return_value = {"created": [{"key": "KAN-1"}], "failed": [], "project_key": "KAN"}

        registry._jira_create_issues(
            account_id="UA001",
            project_key="KAN",
            issues=[{"title": "회의록 정리", "issuetype": "작업", "assignee_account_id": "acc-9"}],
        )

        find_email.assert_not_called()
        create_issues.assert_called_once()


class _FakeStore:
    """`get_memory_store()`(services/agent_runtime/memory/store.py)를 대신한다.

    `_skill_register`가 실제로 필요한 건 `store.put(namespace, key, value)`
    하나뿐이다 — 실제 `PostgresStore`를 안 띄우고 호출 인자만 기록한다.
    """

    def __init__(self):
        self.put_calls: list[dict] = []

    def put(self, namespace, key, value):
        self.put_calls.append({"namespace": namespace, "key": key, "value": value})


class SkillRegisterTests(SimpleTestCase):
    """`_skill_register()` — 정본: 2026-08-20_16_Skill_Middleware_설계.md."""

    def _fake_store(self):
        return patch("services.agent_runtime.memory.store.get_memory_store")

    def test_scope가_아니면_사유를_말하며_거부한다(self):
        with self.assertRaises(ToolInputError):
            registry._skill_register(
                account_id="AC001",
                team_id="TM001",
                account_role="leader",
                scope="ORG",
                name="foo",
                description="d",
                body="b",
            )

    def test_팀원이_팀_스킬을_요청하면_거부한다(self):
        with self.assertRaises(ToolInputError) as ctx:
            registry._skill_register(
                account_id="AC001",
                team_id="TM001",
                account_role="member",
                scope="TEAM",
                name="foo",
                description="d",
                body="b",
            )
        self.assertIn("팀장", str(ctx.exception))

    def test_팀장은_팀_스킬을_등록할_수_있다(self):
        with self._fake_store() as mock_get_store:
            store = _FakeStore()
            mock_get_store.return_value = store

            result = registry._skill_register(
                account_id="AC001",
                team_id="TM001",
                account_role="leader",
                scope="TEAM",
                name="jira-issue-registration",
                description="Jira 이슈 등록 절차",
                body="1. 프로젝트 키를 확인한다\n2. 이슈를 만든다",
            )

        self.assertEqual(result["scope"], "TEAM")
        self.assertEqual(result["path"], "/skills/team/jira-issue-registration/SKILL.md")
        self.assertEqual(len(store.put_calls), 1)
        self.assertEqual(store.put_calls[0]["namespace"], ("skill", "team", "TM001"))
        self.assertEqual(store.put_calls[0]["key"], "/skills/team/jira-issue-registration/SKILL.md")

    def test_개인_스킬은_역할과_무관하게_등록된다(self):
        with self._fake_store() as mock_get_store:
            store = _FakeStore()
            mock_get_store.return_value = store

            result = registry._skill_register(
                account_id="AC001",
                team_id="TM001",
                account_role="member",
                scope="PERSONAL",
                name="my-note-taking",
                description="회의록 정리 절차",
                body="회의록을 이렇게 정리한다",
            )

        self.assertEqual(result["scope"], "PERSONAL")
        self.assertEqual(store.put_calls[0]["namespace"], ("skill", "personal", "AC001"))

    def test_잘못된_이름은_거부한다(self):
        for bad_name in ("Foo-Bar", "-foo", "foo-", "foo--bar", "a" * 65, ""):
            with self.subTest(bad_name=bad_name):
                with self.assertRaises(ToolInputError):
                    registry._skill_register(
                        account_id="AC001",
                        team_id="TM001",
                        account_role="leader",
                        scope="PERSONAL",
                        name=bad_name,
                        description="d",
                        body="b",
                    )

    def test_빈_설명이나_본문은_거부한다(self):
        with self.assertRaises(ToolInputError):
            registry._skill_register(
                account_id="AC001", team_id="TM001", account_role="leader",
                scope="PERSONAL", name="foo", description="  ", body="b",
            )
        with self.assertRaises(ToolInputError):
            registry._skill_register(
                account_id="AC001", team_id="TM001", account_role="leader",
                scope="PERSONAL", name="foo", description="d", body="   ",
            )

    def test_저장한_내용은_이름_설명이_있는_frontmatter다(self):
        with self._fake_store() as mock_get_store:
            store = _FakeStore()
            mock_get_store.return_value = store

            registry._skill_register(
                account_id="AC001",
                team_id="TM001",
                account_role="leader",
                scope="PERSONAL",
                name="my-skill",
                description="설명입니다",
                body="본문 절차",
            )

        content = store.put_calls[0]["value"]["content"]
        self.assertTrue(content.startswith("---\n"))
        self.assertIn("name: my-skill", content)
        self.assertIn("description:", content)
        self.assertIn("본문 절차", content)


@patch("services.harness.trace.ToolCallRepository")
@patch("services.harness.trace.AgentRunRepository")
@patch("services.harness.runner.registry.load_for_agent")
@patch("services.harness.runner.AgentRepository.get")
class DelegationTests(SimpleTestCase):
    """에이전트가 에이전트를 부른다(A2A).

    **여기서 지키는 것은 중첩된 승인 게이트다.** 하위가 외부를 바꾸려 멈추면 두
    층이 함께 멈추고, 사람이 한 번 승인하면 두 층이 같은 순서로 이어 돈다.
    그리고 그 사이에 **어떤 run 도 FAILED 로 적히지 않는다** — 승인 대기는
    실패가 아닌데, 예외로 신호하면 안쪽 제너레이터가 닫히면서 GeneratorExit 이
    들어가 그렇게 기록된다(trace.py:72).
    """

    def _wire(self, get, load_tools, runs, *, inner_model, executed=None):
        get.side_effect = lambda agent_id: SUB_AGENT if agent_id == "AG002" else AGENT
        inner_tool = echo_tool(
            "jira_create_issues",
            side_effect=True,
            handler=lambda **kwargs: (executed if executed is not None else []).append(kwargs)
            or {"created": 2},
        )
        load_tools.side_effect = lambda *, agent_id, team_id, depth=1: (
            {"jira_create_issues": inner_tool}
            if agent_id == "AG002"
            else {"agent:AG002": registry._agent_tool(SUB_ROW)}
        )
        runs.start.side_effect = ["RUN-OUT", "RUN-IN"]
        # 하위 실행은 자기 모델을 쓴다(호출자가 넘긴 모델을 물려받지 않는다).
        return patch("services.harness.runner._default_model", return_value=inner_model)

    def test_하위가_승인에서_멈추면_스택으로_올라온다(self, get, load_tools, runs, calls):
        calls.begin.return_value = "TC-1"
        inner_model = FakeModel(
            [ModelDecision(tool_calls=[{"id": "c2", "tool_ref": "jira_create_issues", "arguments": {"issues": ["A"]}}])]
        )
        outer_model = FakeModel(
            [ModelDecision(tool_calls=[{"id": "c1", "tool_ref": "agent:AG002", "arguments": {"task": "올려줘"}}])]
        )

        with self._wire(get, load_tools, runs, inner_model=inner_model):
            events = list(run_agent("AG001", "Jira 에 올려줘", model=outer_model))

        final = events[-1]
        self.assertEqual(final["type"], "awaiting_confirmation")
        # 카드가 말하는 것은 **실제로 외부를 바꾸는 그 호출**이지 위임이 아니다.
        self.assertEqual(final["tool_ref"], "jira_create_issues")
        self.assertEqual(final["via_agent"], "Jira 등록 에이전트")
        # 재개 정보는 두 겹이다 — 바깥은 위임 호출, 안쪽은 Jira 호출.
        self.assertEqual(final["resume"]["tool_call"]["tool_ref"], "agent:AG002")
        self.assertEqual(final["resume"]["inner"]["tool_call"]["tool_ref"], "jira_create_issues")

        statuses = [call.kwargs["status"] for call in runs.finish.call_args_list]
        self.assertNotIn("FAILED", statuses, "승인 대기는 실패가 아니다")
        self.assertEqual(len(statuses), 2, "두 층 모두 닫혀야 한다")
        # 어느 실행이 어느 실행을 불렀는지가 남는다.
        self.assertEqual(runs.start.call_args_list[1].kwargs["parent_run_id"], "RUN-OUT")

    def test_승인하면_두_층이_이어서_재개된다(self, get, load_tools, runs, calls):
        calls.begin.return_value = "TC-1"
        executed = []
        # 재개 턴에서는 어느 층도 모델을 다시 묻지 않는다. 하위는 마지막에 한 번
        # 답하고, 상위도 그 결과를 받아 한 번 답한다.
        inner_model = FakeModel([ModelDecision(text="2건 등록했습니다.")])
        outer_model = FakeModel([ModelDecision(text="등록을 마쳤습니다.")])
        approved_call = {"id": "c2", "tool_ref": "jira_create_issues", "arguments": {"issues": ["A"]}}

        with self._wire(get, load_tools, runs, inner_model=inner_model, executed=executed):
            events = list(
                run_agent(
                    "AG001",
                    "",
                    {
                        # 요청자는 위임을 타고 그대로 내려간다 — 하위도 같은
                        # 사람의 자격으로 돈다(위임이 권한을 넓히지 않는다).
                        "account_id": "AC001",
                        "messages": [{"role": "user", "content": "올려줘"}],
                        "resume_tool_call": {
                            "id": "c1",
                            "tool_ref": "agent:AG002",
                            "arguments": {"task": "올려줘"},
                        },
                        "resume_inner": {
                            "messages": [{"role": "user", "content": "올려줘"}],
                            "tool_call": approved_call,
                            "inner": None,
                        },
                        # 승인은 **가장 안쪽** 호출에만 준다.
                        "approved_tool_calls": ["jira_create_issues"],
                    },
                    model=outer_model,
                )
            )

        self.assertEqual(executed[0]["issues"], ["A"], "승인한 그 호출이 그대로 실행돼야 한다")
        self.assertNotIn("awaiting_confirmation", [e["type"] for e in events])
        self.assertEqual(events[-1]["type"], "result")
        self.assertNotIn("FAILED", [call.kwargs["status"] for call in runs.finish.call_args_list])


class AgentToolLoadTests(SimpleTestCase):
    """`agent:*` 가 팀의 다른 에이전트로 펼쳐지는가, 그리고 어디서 멈추는가.

    `load_for_agent` 를 mock 하지 않으므로 `DelegationTests` 와 클래스를 나눈다.
    """

    def _load(self, *, depth, tool_refs=("agent:*",)):
        with patch.object(registry.AgentRepository, "tool_refs", return_value=list(tool_refs)), patch.object(
            registry.AgentRepository, "mcp_tools", return_value=[]
        ), patch.object(registry.AgentRepository, "callable_agents", return_value=[SUB_ROW]):
            return registry.load_for_agent(agent_id="AG001", team_id="TM001", depth=depth)

    def test_와일드카드가_팀_에이전트로_펼쳐진다(self):
        """id 를 시드에 박으면 Builder 로 만든 에이전트를 영영 못 부른다."""

        self.assertIn("agent:AG002", self._load(depth=1))

    def test_깊이_상한에_닿으면_위임_도구를_주지_않는다(self):
        """줘 놓고 거절하면 모델이 그것을 고치려고 회전을 태운다."""

        self.assertNotIn("agent:AG002", self._load(depth=registry.MAX_AGENT_DEPTH))

    def test_와일드카드가_없으면_위임할_수_없다(self):
        self.assertNotIn("agent:AG002", self._load(depth=1, tool_refs=("document_search",)))


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


class ToolNameTests(SimpleTestCase):
    """모델에게 보내는 함수 이름은 `^[a-zA-Z0-9_-]+$` 를 지켜야 한다.

    우리 `tool_ref` 는 `agent:AG005`·`mcp:MT001` 처럼 콜론을 쓰는데, 그대로 넘기면
    OpenAI 가 400 을 낸다(2026-08-12 실측 —
    `Invalid 'tools[7].name': string does not match pattern`).

    **MCP 도구도 같은 문제였다.** 아무도 MCP 서버를 안 붙여서 안 드러났을 뿐이다.
    """

    import re as _re

    PATTERN = _re.compile(r"^[a-zA-Z0-9_-]+$")

    def test_콜론이_들어간_ref_도_안전한_이름이_된다(self):
        from services.harness.runner import model_name_for

        for ref in ("agent:AG005", "mcp:MT001", "document_search"):
            with self.subTest(ref=ref):
                self.assertRegex(model_name_for(ref), self.PATTERN)

    def test_되돌리면_원래_ref_다(self):
        """되돌리지 못하면 Registry 가 그 도구를 못 찾아 ToolNotAllowed 가 된다."""

        from services.harness.runner import model_name_for, tool_ref_for

        for ref in ("agent:AG005", "mcp:MT001", "document_search", "task_update"):
            with self.subTest(ref=ref):
                self.assertEqual(tool_ref_for(model_name_for(ref)), ref)

    def test_내장_도구_전부가_패턴을_지킨다(self):
        from services.harness.runner import model_name_for

        for ref in registry.BUILTIN_TOOLS:
            with self.subTest(ref=ref):
                self.assertRegex(model_name_for(ref), self.PATTERN)


class ToolWiringTests(SimpleTestCase):
    """도구가 부르는 저장소 메서드가 실제로 있는가.

    `document_list` 이 `PipelineDocumentRepository.list_with_meta` 를 불렀는데
    그 메서드는 `DocMetaRepository` 에 있었다 — **한 번도 동작한 적이 없고**,
    「무슨 문서 있어?」가 늘 AttributeError 로 끝났다(2026-08-12 QA 시나리오 B).

    도구가 13종이라 사람이 다 눌러 보지 않으면 이런 것이 조용히 남는다. 실행
    없이 이름만 맞춰 보는 것으로도 이 부류는 잡힌다.
    """

    def test_모든_저장소_호출이_실재한다(self):
        import inspect
        import re as _re

        source = inspect.getsource(registry)
        missing = []
        for cls_name, method in sorted(set(_re.findall(r"\b([A-Z]\w*Repository)\.(\w+)\(", source))):
            repository = getattr(registry, cls_name, None)
            if repository is None or not hasattr(repository, method):
                missing.append(f"{cls_name}.{method}")

        self.assertEqual(missing, [])

    def test_document_search_에_요청자_계정이_주입된다(self):
        """빠뜨려도 **오류가 안 난다** — 그래서 조용히 반쪽이 된다.

        `_document_search(account_id=None)` 이면 `coarse_search` 가 팀 문서만 보고
        **내가 켠 내 파일이 안 잡히며**(M④), `registry` 의
        `not_indexed[:PROMOTE_TOP_N] if account_id else []` 때문에 **온디맨드
        승격이 통째로 꺼진다.** 화면에는 「확인할 수 있는 문서가 없습니다」로만
        보여서 기능이 없는 것처럼 읽힌다.

        실제로 승격은 2026-08-15 에 이 값이 온다는 전제로 만들어졌는데 주입하는
        자리가 그때 같이 안 고쳐졌고, 2026-08-18 브라우저 QA 전까지 안 드러났다.
        """

        from services.harness.runner import _injected

        tool = registry.BUILTIN_TOOLS["document_search"]
        injected = _injected(tool, {"team_id": "TE001"}, {"account_id": "UA002"})

        self.assertEqual(injected["team_id"], "TE001")
        self.assertEqual(injected["account_id"], "UA002")

    def test_mcp_도구에는_계정을_넘기지_않는다(self):
        """MCP 핸들러는 `account_id` 를 받지 않는다 — 같이 넘기면 TypeError 다."""

        from services.harness.runner import _injected

        tool = SimpleNamespace(ref="mcp:MS001:search")
        self.assertEqual(
            _injected(tool, {"team_id": "TE001"}, {"account_id": "UA002"}),
            {"team_id": "TE001"},
        )


class TaskRegisterDateTests(SimpleTestCase):
    """등록 직전에 날짜를 거른다.

    문서에는 절대 날짜가 잘 없어서 「조치내역 확인 요청 후 5일 이내」 같은 상대
    표현이 뽑혀 나온다. 그게 `timestamptz` 컬럼까지 내려가 `InvalidDatetimeFormat`
    으로 죽었고, 한 트랜잭션이라 **승인한 18건이 전부 롤백됐다**(2026-08-12 QA
    시나리오 B — 그때 `task` 는 0 건이었다).
    """

    def test_상대_표현은_비운다(self):
        from backend.db.agent_platform import _date_or_none

        for text in ("조치내역 확인 요청 후 5일 이내", "종료단계(최종) 감리 종료 후 15일 이내", "미정", ""):
            with self.subTest(text=text):
                self.assertIsNone(_date_or_none(text))

    def test_절대_날짜는_그대로_둔다(self):
        from backend.db.agent_platform import _date_or_none

        self.assertEqual(_date_or_none("2026-08-20"), "2026-08-20")
        self.assertEqual(_date_or_none("2026-08-20T09:00:00"), "2026-08-20T09:00:00")
        self.assertIsNone(_date_or_none(None))

    def test_0_공수는_모른다는_뜻이다(self):
        """스키마가 `number` 면 모델은 모르는 값도 0 으로 채운다.

        실제로 문서에 공수가 없던 업무 7건이 전부 `effort = 0.00` 으로 들어갔다.
        0 시간짜리 업무는 없고, 그대로 두면 배정이 「공수 0 인 업무」로 계산한다.
        """

        from backend.db.agent_platform import _positive_or_none

        self.assertIsNone(_positive_or_none(0))
        self.assertIsNone(_positive_or_none(0.0))
        self.assertIsNone(_positive_or_none(""))
        self.assertIsNone(_positive_or_none("  "))
        self.assertIsNone(_positive_or_none(None))
        self.assertEqual(_positive_or_none(16), 16)
        self.assertEqual(_positive_or_none("백엔드"), "백엔드")

    def test_비운_것을_돌려줘야_사람이_안다(self):
        """조용히 버리면 「마감이 없는 업무」와 「마감을 못 읽은 업무」가 구별되지 않는다."""

        from backend.db import agent_platform

        cursor = _RegisterCursor()
        with patch.object(agent_platform, "database_connection", _fake_connection(cursor)), \
                patch.object(agent_platform, "_require_team", return_value="TM001"), \
                patch.object(agent_platform, "next_short_code", side_effect=["KM001", "TK001", "TK002"]):
            result = agent_platform.ProjectTaskRepository.register(
                proj_id="PJ001",
                account_id="UA001",
                tasks=[
                    {"title": "감리보고서 제출", "due_date": "조치내역 확인 요청 후 5일 이내"},
                    {"title": "착수 회의", "due_date": "2026-08-20"},
                ],
            )

        self.assertEqual(len(result["tasks"]), 2)
        self.assertEqual(result["dropped_fields"], [{"title": "감리보고서 제출", "fields": ["마감일"]}])
        self.assertEqual([row[6] for row in cursor.inserted], [None, "2026-08-20"])

    def test_모르는_값을_0으로_채워_보내면_비웠다고_알린다(self):
        """**모델이 모르는 공수를 채우는 값이 하필 `0`** 이다(`_positive_or_none`).

        회귀 방지: 예전엔 날짜만 돌려줬고 판정도 `if given` 이라, `0` 은 거짓이라
        두 번 걸러졌다. 그 결과 15건 전부 `effort_hours: 0` 으로 와서 전부 NULL 로
        저장됐는데 모델은 「0시간으로 등록했습니다」라고 답했다(2026-08-18 QA).
        """

        from backend.db import agent_platform

        cursor = _RegisterCursor()
        with patch.object(agent_platform, "database_connection", _fake_connection(cursor)),                 patch.object(agent_platform, "_require_team", return_value="TM001"),                 patch.object(agent_platform, "next_short_code", side_effect=["KM001", "TK001"]):
            result = agent_platform.ProjectTaskRepository.register(
                proj_id="PJ001",
                account_id="UA001",
                tasks=[{"title": "감리 착수", "effort_hours": 0, "required_role": "", "priority": "높음"}],
            )

        self.assertEqual(
            result["dropped_fields"],
            [{"title": "감리 착수", "fields": ["공수"]}],
            "0 으로 채워 보낸 공수를 비웠다고 알려야 한다",
        )
        # 빈 문자열은 「준 적 없음」이라 알릴 것이 없고, 준 값은 그대로 남는다.
        self.assertIsNone(cursor.inserted[0][3], "빈 역할은 NULL")
        self.assertIsNone(cursor.inserted[0][4], "0 공수는 NULL")
        self.assertEqual(cursor.inserted[0][7], "높음", "준 우선순위는 그대로")


class _RegisterCursor:
    """`register` 가 부르는 SQL 만 흉내낸다.

    쿼리를 구분한다 — 2026-08-19 에 `register` 가 「현재 판을 찾고」·「그 판에
    이미 있는 제목을 읽는」 두 조회를 더 하게 됐다. 전부 같은 행을 돌려주면
    판을 찾았는지 못 찾았는지가 구분되지 않는다.
    """

    def __init__(self):
        self.inserted = []
        #: 이 프로젝트에 이미 있는 판. None 이면 첫 등록이라 새로 만든다.
        self.existing_model = None
        #: 그 판에 이미 들어 있는 업무 제목.
        self.existing_titles = []
        self._last = ""

    def execute(self, sql, params=None):
        self._last = sql
        if "INSERT INTO task " in sql:
            self.inserted.append(params)

    def fetchone(self):
        if "FROM proj_know_model" in self._last:
            return self.existing_model
        return {"team_id": "TM001", "n": 0}

    def fetchall(self):
        if "SELECT task_name FROM task" in self._last:
            return [{"task_name": title} for title in self.existing_titles]
        return []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _fake_connection(cursor):
    class _Connection:
        def cursor(self):
            return cursor

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    return lambda: _Connection()


class ToolTurnStyleTests(SimpleTestCase):
    """도구 결과는 **답을 만든 API 의 형식**으로 되돌린다.

    Responses API 는 `function_call_output`, OpenAI 호환(`/chat/completions`)은
    `role: tool` 이다. 섞으면 그 다음 호출이 400 으로 죽는다 — 우리가 제공하는
    Claude 가 호환 경로로 가므로 한 실행 안에서 두 형식이 만날 수 있다.
    """

    CALL = {"id": "call_1", "tool_ref": "people_list", "arguments": {}}

    def test_기본은_responses_형식이다(self):
        from services.harness.runner import _tool_turn

        turn = _tool_turn(self.CALL, {"ok": True})

        self.assertEqual(turn["type"], "function_call_output")
        self.assertEqual(turn["call_id"], "call_1")

    def test_호환_엔드포인트는_role_tool_이다(self):
        from services.harness.runner import _tool_turn

        turn = _tool_turn(self.CALL, {"ok": True}, "chat")

        self.assertEqual(turn["role"], "tool")
        self.assertEqual(turn["tool_call_id"], "call_1")
        self.assertNotIn("type", turn)

    def test_claude_는_호환_경로로_간다(self):
        """모델 이름으로 갈린다 — 팀이 주소를 넣지 않아도 Claude 는 chat 이다."""

        from services.harness import runner

        with patch.object(runner.settings, "ANTHROPIC_API_KEY", "sk-ant-test"):
            call = runner._default_model({"model": "claude-sonnet-4-5", "team_id": None})

        # 어댑터가 붙었는지만 본다(실제 호출은 하지 않는다).
        self.assertEqual(call.__qualname__.split(".")[0], "_chat_completions_model")

    def test_anthropic_키가_없으면_분명히_말한다(self):
        from services.harness import runner

        with patch.object(runner.settings, "ANTHROPIC_API_KEY", ""):
            with self.assertRaises(RuntimeError) as caught:
                runner._default_model({"model": "claude-sonnet-4-5", "team_id": None})

        self.assertIn("ANTHROPIC_API_KEY", str(caught.exception))

    def test_추가_등록은_현재_판에_덧붙인다(self):
        """판을 매번 새로 만들면 앞서 등록한 업무가 화면에서 사라진다.

        `list_for_project` 가 가장 최근 판만 보여주기 때문이다 — 「3건만 추가로
        등록해줘」에 새 판이 생겨 앞의 15건이 통째로 안 보였다(2026-08-19 QA).
        """

        from backend.db import agent_platform

        cursor = _RegisterCursor()
        # 이 프로젝트엔 이미 판이 하나 있고, 그 판에 「감리 착수」가 들어 있다.
        cursor.existing_model = {"model_id": "KM001", "model_ver": "v1"}
        cursor.existing_titles = ["감리 착수"]

        with patch.object(agent_platform, "database_connection", _fake_connection(cursor)),                 patch.object(agent_platform, "_require_team", return_value="TM001"),                 patch.object(agent_platform, "next_short_code", side_effect=["TK002"]):
            result = agent_platform.ProjectTaskRepository.register(
                proj_id="PJ001",
                account_id="UA001",
                tasks=[{"title": "감리 착수"}, {"title": "종료회의"}],
            )

        self.assertEqual(result["model_id"], "KM001", "새 판을 만들지 않는다")
        self.assertEqual([t["title"] for t in result["tasks"]], ["종료회의"])
        self.assertEqual(
            result["already_registered"], ["감리 착수"], "건너뛴 것을 조용히 넘기지 않는다"
        )
