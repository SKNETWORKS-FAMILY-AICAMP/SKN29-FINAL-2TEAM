from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from services.agent_runtime.skills.evaluation.pipeline import (
    EvalPipelineError,
    _available_tools_for,
    _evaluation_agent,
    _other_skills_for,
    _select_behavior_sample,
    run_preparing_tests,
)


class PreparingPipelineEdgeTests(SimpleTestCase):
    @patch("services.agent_runtime.tools.adapters.adapt_mcp_tools")
    @patch("services.agent_runtime.tools.adapters.adapt_builtin_tools")
    def test_평가_도구_카탈로그는_내장과_팀_MCP를_함께_사용한다(self, builtins, mcp):
        builtins.return_value = [
            MagicMock(ref="document_search", name="문서 검색", description="검색", side_effect=False)
        ]
        mcp.return_value = [
            MagicMock(ref="mcp:mail", name="메일", description="전송", side_effect=True)
        ]

        result = _available_tools_for("AC001", "TM001")

        self.assertEqual([tool["tool_ref"] for tool in result], ["document_search", "mcp:mail"])
        mcp.assert_called_once_with(team_id="TM001")

    @patch("services.agent_runtime.models.factory.ModelConfigResolver")
    def test_평가_에이전트는_DB_에이전트가_아닌_전체도구_draft다(self, resolver):
        resolver.return_value.resolve.return_value = MagicMock(provider="openai")
        draft, provider = _evaluation_agent(
            "TM001",
            [
                {"tool_ref": "document_search"},
                {"tool_ref": "mcp:mail"},
            ],
        )

        self.assertEqual(provider, "openai")
        self.assertEqual(draft["tool_refs"], ["document_search", "mcp:mail"])
        self.assertEqual(draft["subagents"], [])
        self.assertNotIn("agent_id", draft)
        self.assertNotIn("agent_version_id", draft)

    @patch("services.agent_runtime.skills.service.list_personal_skills")
    def test_비활성_스킬은_평가_경쟁_목록에서_뺀다(self, list_skills):
        list_skills.return_value = [
            {"name": "active", "description": "사용", "enabled": True},
            {"name": "inactive", "description": "중지", "enabled": False},
        ]
        self.assertEqual(_other_skills_for("AC001"), [{"name": "active", "description": "사용"}])

    def test_우선순위_사례가_겹쳐도_행동_테스트를_세_건_고른다(self):
        cases = [
            {"case_id": "one", "category": "direct", "document_fixtures": [], "required_tools": []},
            {"case_id": "two", "category": "paraphrase", "document_fixtures": [], "required_tools": []},
            {"case_id": "three", "category": "contextual", "document_fixtures": [], "required_tools": []},
        ]
        self.assertEqual(
            [case["case_id"] for case in _select_behavior_sample(cases)],
            ["one", "two", "three"],
        )

    @patch("services.agent_runtime.skills.evaluation.pipeline._reserve_model_calls")
    @patch("services.agent_runtime.skills.evaluation.pipeline._provider_for_model", return_value="provider")
    @patch("services.agent_runtime.skills.evaluation.pipeline._other_skills_for", return_value=[])
    @patch("services.agent_runtime.skills.evaluation.pipeline._available_tools_for", return_value=[])
    @patch("services.agent_runtime.skills.evaluation.pipeline.review_cases")
    @patch("services.agent_runtime.skills.evaluation.pipeline.generate_valid_candidates")
    @patch("services.agent_runtime.skills.evaluation.pipeline._run_with_provider_slot")
    @patch("services.agent_runtime.skills.evaluation.pipeline._call_until_deadline")
    def test_마지막_의미검토_실패_뒤에는_사용하지_않을_질문을_재생성하지_않는다(
        self, bounded, provider_slot, generate, review, _tools, _skills, _provider, reserve
    ):
        positive = [MagicMock(query=f"positive-{index}", should_activate_candidate=True) for index in range(8)]
        negative = [MagicMock(query=f"negative-{index}", should_activate_candidate=False) for index in range(8)]
        generate.return_value = (positive, negative, "author")

        def failed_reviews(cases, **_kwargs):
            rows = []
            for index, _case in enumerate(cases):
                row = MagicMock(case_index=index)
                row.overall.return_value = "FAIL"
                rows.append(row)
            return rows, "reviewer"

        review.side_effect = failed_reviews
        provider_slot.side_effect = lambda _provider, _deadline, fn: fn()
        bounded.side_effect = lambda fn, _deadline: fn()
        job = {
            "job_id": "job-1", "lease_owner": "worker-1", "account_id": "AC001",
            "team_id": "TM001", "candidate_hash": "hash",
            "candidate_document": {"name": "sample-skill", "description": "description", "body": "body"},
        }

        with self.assertRaises(EvalPipelineError) as context:
            run_preparing_tests(job)

        self.assertEqual(context.exception.code, "TEST_CASE_REVIEW_FAILED")
        # 최초 생성 1회 + 다음 검토가 남은 두 번만 재생성한다.
        self.assertEqual(generate.call_count, 3)
        reserve.assert_called_once_with(job, 12)
