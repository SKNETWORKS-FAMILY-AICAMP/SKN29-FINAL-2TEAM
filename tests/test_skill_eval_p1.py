from __future__ import annotations

import time
from unittest import TestCase
from unittest.mock import patch

from services.agent_runtime.skills.evaluation.harness import (
    _bounded_call,
    _check_argument_rule,
    _case_input,
    _event_text,
    _run_behavior_case,
    _tool_fixtures,
)
from services.agent_runtime.skills.evaluation.ephemeral_skills import build_ephemeral_skill_store
from services.agent_runtime.skills.evaluation.behavior_reviewer import (
    AssertionVerdict,
    build_behavior_review_payload,
    merge_uncertain_verdicts,
)


class SkillEvalP1HarnessTests(TestCase):
    @patch("services.agent_runtime.executor.AgentExecutor")
    @patch("services.agent_runtime.skills.evaluation.harness._build_eval_factory")
    def test_승인없는_행동평가는_checkpointer없이_임시_draft를_실행한다(
        self, build_factory, executor_class
    ):
        executor = executor_class.return_value
        executor.run.return_value = iter([])
        draft = {
            "name": "skill-evaluation-agent",
            "description": "평가",
            "system_prompt": "평가",
            "model": "test-model",
            "reasoning_effort": "low",
            "max_iterations": 10,
            "tool_refs": [],
            "subagents": [],
        }

        result = _run_behavior_case(
            case={
                "case_id": "case-1",
                "messages": [{"role": "user", "content": "정리해줘"}],
                "approval_fixtures": [],
                "required_tools": [],
                "forbidden_tools": [],
            },
            snapshot=build_ephemeral_skill_store(
                candidate_document={"name": "candidate", "content": "---\nname: candidate\ndescription: 설명\n---\n본문"},
                distractor_documents=[],
            ),
            evaluation_agent_draft=draft,
            account_id="AC001",
            team_id="TM001",
        )

        self.assertIsNone(result.error)
        self.assertIsNone(build_factory.call_args.kwargs["checkpointer_provider"])
        run_kwargs = executor.run.call_args.kwargs
        self.assertEqual(run_kwargs["draft"], draft)
        self.assertIsNone(run_kwargs["agent_id"])
        self.assertIsNone(run_kwargs["context"].session_id)

    @patch("services.agent_runtime.executor.AgentExecutor")
    @patch("services.agent_runtime.skills.evaluation.harness._build_eval_factory")
    def test_승인이_필요한_행동평가는_session과_같은_draft로_재개한다(
        self, build_factory, executor_class
    ):
        executor = executor_class.return_value
        executor.run.return_value = iter(
            [
                {
                    "type": "awaiting_confirmation",
                    "action_requests": [{"name": "task_register"}],
                }
            ]
        )
        executor.resume.return_value = iter([{"type": "result", "text": "등록 완료"}])
        draft = {
            "name": "skill-evaluation-agent",
            "description": "평가",
            "system_prompt": "평가",
            "model": "test-model",
            "reasoning_effort": "low",
            "max_iterations": 10,
            "tool_refs": ["task_register"],
            "subagents": [],
        }

        result = _run_behavior_case(
            case={
                "case_id": "case-approval",
                "messages": [{"role": "user", "content": "업무를 등록해줘"}],
                "approval_fixtures": [{"tool_ref": "task_register", "decision": "approve"}],
                "required_tools": [],
                "forbidden_tools": [],
            },
            snapshot=build_ephemeral_skill_store(
                candidate_document={"name": "candidate", "content": "---\nname: candidate\ndescription: 설명\n---\n본문"},
                distractor_documents=[],
            ),
            evaluation_agent_draft=draft,
            account_id="AC001",
            team_id="TM001",
        )

        self.assertIsNone(result.error)
        self.assertIsNotNone(build_factory.call_args.kwargs["checkpointer_provider"])
        self.assertIsNotNone(executor.run.call_args.kwargs["context"].session_id)
        self.assertEqual(executor.resume.call_args.kwargs["draft"], draft)
        self.assertEqual(executor.resume.call_args.kwargs["decisions"], [{"action_index": 0, "type": "approve"}])

    def test_behavior_reviewer_receives_the_original_input_and_document(self):
        payload = build_behavior_review_payload(
            assertions=[{"criterion": "입력 순서를 유지한다"}],
            input_messages=[{"role": "user", "content": "LISTIFY: A; B"}],
            document_fixtures=[{"title": "첨부", "content": "A; B"}],
            final_response="1. A\n2. B",
            tool_trace=[],
        )
        self.assertEqual(payload["input_messages"][0]["content"], "LISTIFY: A; B")
        self.assertEqual(payload["document_fixtures"][0]["content"], "A; B")

    def test_behavior_reviewer_retries_only_uncertain_verdicts(self):
        first = [
            AssertionVerdict(assertion_index=0, verdict="PASS", reason="명확함"),
            AssertionVerdict(assertion_index=1, verdict="UNCERTAIN", reason="불명확함"),
        ]
        second = [
            AssertionVerdict(assertion_index=0, verdict="FAIL", reason="재검토 대상 아님"),
            AssertionVerdict(assertion_index=1, verdict="PASS", reason="충족함"),
        ]
        merged = merge_uncertain_verdicts(first, second)
        self.assertEqual([item.verdict for item in merged], ["PASS", "PASS"])

    def test_행동_평가는_도구_출력이_아닌_Root_최종_답변을_사용한다(self):
        self.assertEqual(
            _event_text({"type": "result", "text": "영어 번역\n일본어 번역"}),
            "영어 번역\n일본어 번역",
        )
        self.assertEqual(
            _event_text({"type": "tool_completed", "output": "SKILL.md 원문"}),
            "",
        )

    @patch("services.agent_runtime.skills.service.list_builtin_skills", return_value=[])
    def test_격리_스킬은_allowed_tools를_포함한_원본_frontmatter를_보존한다(self, _builtins):
        content = "---\nname: candidate\ndescription: 설명\nallowed-tools:\n- document_search\n---\n\n절차\n"
        snapshot = build_ephemeral_skill_store(
            candidate_document={"name": "candidate", "content": content},
            distractor_documents=[],
        )
        item = snapshot.store.get(("skill", "eval-candidate"), "/candidate/SKILL.md")
        self.assertIsNotNone(item)
        self.assertEqual(item.value["content"], content)

    def test_single_call_timeout_returns_none(self):
        result = _bounded_call(lambda: time.sleep(0.05), 0.005)
        self.assertIsNone(result)

    def test_document_fixture_is_available_to_list_and_search(self):
        case = {
            "tool_fixtures": {},
            "document_fixtures": [
                {"document_id": "doc-1", "title": "회의록", "content": "할 일", "indexed": True}
            ],
        }
        fixtures = _tool_fixtures(case)
        self.assertEqual(fixtures["document_list"][0]["documents"][0]["document_id"], "doc-1")
        self.assertEqual(fixtures["document_search"][0]["results"][0]["content"], "할 일")

    def test_document_fixture_content_is_visible_to_the_eval_agent(self):
        case = {
            "messages": [{"role": "user", "content": "첨부 문서를 번역해줘"}],
            "document_fixtures": [
                {"document_id": "doc-1", "title": "회의록", "content": "할 일을 정한다.", "indexed": True}
            ],
        }
        history, current = _case_input(case)
        self.assertEqual(history, [])
        self.assertIn("[첨부 문서: 회의록]", current)
        self.assertIn("할 일을 정한다.", current)
        self.assertTrue(current.endswith("첨부 문서를 번역해줘"))

    def test_HITL_평가용_체크포인터를_쓸_때도_이전_대화를_현재_입력에_보존한다(self):
        case = {
            "messages": [
                {"role": "user", "content": "점검은 토요일 20시입니다."},
                {"role": "assistant", "content": "확인했습니다."},
                {"role": "user", "content": "앞 내용을 번역해줘"},
            ],
            "document_fixtures": [],
        }
        history, current = _case_input(case, flatten_history=True)
        self.assertEqual(history, [])
        self.assertIn("[이전 대화]", current)
        self.assertIn("점검은 토요일 20시입니다.", current)
        self.assertTrue(current.endswith("앞 내용을 번역해줘"))

    def test_argument_rules_support_nested_value_regex_and_exists(self):
        args = {"task": {"title": "API 문서 작성", "labels": ["docs", "api"]}}
        self.assertTrue(_check_argument_rule(args, {"path": "$.task.title", "operator": "equals", "value": "API 문서 작성"}))
        self.assertTrue(_check_argument_rule(args, {"path": "task.title", "operator": "regex", "pattern": "API.*"}))
        self.assertTrue(_check_argument_rule(args, {"path": "$.task.labels[1]", "operator": "equals", "value": "api"}))
        self.assertFalse(_check_argument_rule(args, {"path": "task.owner", "operator": "exists", "value": True}))
