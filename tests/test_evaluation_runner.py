from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from services.agent_runtime.context import RuntimeContext
from services.evaluation.runner import (
    evaluate_events,
    load_workflow_dataset,
    run_read_only_case,
    select_case,
)


def _case() -> dict:
    return {
        "id": "WF-READ-001",
        "agent_id": "AG001",
        "agent_version_id": "AV001",
        "execution_mode": "read_only",
        "input": "현황을 알려줘",
        "expected_outcome": "근거 기반 현황",
        "required_tools": ["document_search"],
        "allowed_tools": ["document_search", "document_list"],
        "forbidden_tools": ["jira_create_issues"],
        "max_calls_per_tool": {"document_search": 1, "document_list": 1},
        "max_tool_calls": 2,
        "required_evidence_documents": ["DC001"],
        "optional_evidence_documents": ["DC002"],
        "required_facts": ["사실"],
        "required_qualifications": ["한계 표시"],
        "forbidden_claims": ["과장"],
        "expected_status": "SUCCESS",
    }


def _events() -> list[dict]:
    return [
        {
            "type": "tool_started",
            "tool_ref": "document_search",
            "tool_call_id": "CALL001",
        },
        {
            "type": "tool_completed",
            "tool_ref": "document_search",
            "tool_call_id": "CALL001",
            "status": "OK",
            "retrieved_doc_ids": ["DC001"],
        },
        {
            "type": "result",
            "text": "근거 기반 답변",
            "iterations": 2,
            "token_in": 10,
            "token_out": 4,
            "duration_ms": 120,
        },
    ]


def _judge_verdict() -> dict:
    return {
        "overall_verdict": "PASS",
        "dimensions": {
            name: {"verdict": "PASS", "reason": "통과", "evidence_refs": []}
            for name in (
                "task_success",
                "grounding",
                "side_effect_safety",
                "repetitiveness",
                "uncertainty",
            )
        },
        "summary": "통과",
    }


def _retry_events(arguments: list[dict], statuses: list[str]) -> list[dict]:
    events: list[dict] = []
    for index, (args, status) in enumerate(zip(arguments, statuses, strict=True), start=1):
        call_id = f"CALL{index}"
        events.extend(
            [
                {
                    "type": "tool_started",
                    "tool_ref": "document_search",
                    "tool_call_id": call_id,
                    "arguments": args,
                },
                {
                    "type": "tool_completed",
                    "tool_ref": "document_search",
                    "tool_call_id": call_id,
                    "status": status,
                    "retrieved_doc_ids": ["DC001"] if status == "OK" else [],
                },
            ]
        )
    events.append(
        {
            "type": "result",
            "text": "재시도 후 답변",
            "iterations": len(statuses) + 1,
            "token_in": 10,
            "token_out": 4,
            "duration_ms": 120,
        }
    )
    return events


class EvaluationRunnerTests(unittest.TestCase):
    def test_dataset_loader_and_selector(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "dataset.json"
            path.write_text(
                json.dumps({"dataset_id": "d", "dataset_version": 1, "cases": [_case()]}),
                encoding="utf-8",
            )
            dataset = load_workflow_dataset(path)
            self.assertEqual(select_case(dataset, "WF-READ-001")["agent_id"], "AG001")

    def test_dataset_loader_rejects_invalid_retry_policy(self):
        case = _case()
        case["tool_retry_policy"] = {
            "max_retries_after_failure_per_signature": -1,
            "max_consecutive_failures_per_signature": 2,
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "dataset.json"
            path.write_text(
                json.dumps({"dataset_id": "d", "dataset_version": 1, "cases": [case]}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "tool_retry_policy"):
                load_workflow_dataset(path)

    def test_deterministic_assertions_pass_and_optional_doc_is_not_agent_requirement(self):
        events = _events()
        for event in events:
            event["langfuse_trace_id"] = "TRACE001"
        result = evaluate_events(
            case=_case(),
            events=events,
            started_at="2026-08-26T00:00:00Z",
            finished_at="2026-08-26T00:00:01Z",
            elapsed_ms=150,
            model="test-model",
            runtime="test-runtime",
            run_id="RUN001",
        )
        self.assertEqual(result["status"], "SUCCESS")
        self.assertTrue(all(item["passed"] for item in result["assertions"]))
        self.assertEqual(result["metrics"]["total_tokens"], 14)
        self.assertEqual(result["judge"]["status"], "UNCERTAIN")
        self.assertEqual(result["judge"]["unavailable_documents"], ["DC001", "DC002"])
        self.assertEqual(result["langfuse_trace_id"], "TRACE001")

    def test_forbidden_tool_and_missing_required_evidence_fail(self):
        events = _events()
        events[1]["retrieved_doc_ids"] = []
        events.insert(
            2,
            {
                "type": "tool_started",
                "tool_ref": "jira_create_issues",
                "tool_call_id": "CALL002",
            },
        )
        result = evaluate_events(
            case=_case(),
            events=events,
            started_at="2026-08-26T00:00:00Z",
            finished_at="2026-08-26T00:00:01Z",
            elapsed_ms=150,
            model="test-model",
            runtime="test-runtime",
            run_id="RUN001",
        )
        self.assertEqual(result["status"], "FAILED")
        self.assertIn("forbidden_tools_not_called", result["failure_reason"])
        self.assertIn("required_evidence_retrieved", result["failure_reason"])
        self.assertEqual(result["side_effects"][0]["tool_ref"], "jira_create_issues")

    def test_transient_failure_records_one_retry_and_recovery(self):
        case = _case()
        case["max_tool_calls"] = 4
        case["max_calls_per_tool"]["document_search"] = 4
        case["tool_retry_policy"] = {
            "max_retries_after_failure_per_signature": 1,
            "max_consecutive_failures_per_signature": 2,
        }
        result = evaluate_events(
            case=case,
            events=_retry_events([{"query": "일정"}, {"query": "일정"}], ["FAILED", "OK"]),
            started_at="2026-08-26T00:00:00Z",
            finished_at="2026-08-26T00:00:01Z",
            elapsed_ms=150,
            model="test-model",
            runtime="test-runtime",
            run_id="RUN001",
        )
        reliability = result["tool_reliability"]
        self.assertEqual(reliability["failed_call_count"], 1)
        self.assertEqual(reliability["retry_after_failure_count"], 1)
        self.assertEqual(reliability["recovered_after_retry_count"], 1)
        assertions = {item["name"]: item["passed"] for item in result["assertions"]}
        self.assertTrue(assertions["tool_retry_limit"])
        self.assertTrue(assertions["consecutive_tool_failure_limit"])
        self.assertFalse(assertions["tool_calls_completed_ok"])

    def test_persistent_same_input_failure_exceeds_retry_policy(self):
        case = _case()
        case["max_tool_calls"] = 4
        case["max_calls_per_tool"]["document_search"] = 4
        case["tool_retry_policy"] = {
            "max_retries_after_failure_per_signature": 1,
            "max_consecutive_failures_per_signature": 2,
        }
        result = evaluate_events(
            case=case,
            events=_retry_events(
                [{"query": "일정"}, {"query": "일정"}, {"query": "일정"}],
                ["FAILED", "FAILED", "FAILED"],
            ),
            started_at="2026-08-26T00:00:00Z",
            finished_at="2026-08-26T00:00:01Z",
            elapsed_ms=150,
            model="test-model",
            runtime="test-runtime",
            run_id="RUN001",
        )
        reliability = result["tool_reliability"]
        self.assertEqual(reliability["retry_after_failure_count"], 2)
        self.assertEqual(reliability["max_consecutive_failures_per_signature"], 3)
        assertions = {item["name"]: item["passed"] for item in result["assertions"]}
        self.assertFalse(assertions["tool_retry_limit"])
        self.assertFalse(assertions["consecutive_tool_failure_limit"])

    def test_changed_arguments_are_not_counted_as_retry(self):
        case = _case()
        case["max_tool_calls"] = 4
        case["max_calls_per_tool"]["document_search"] = 4
        result = evaluate_events(
            case=case,
            events=_retry_events(
                [{"query": "일정"}, {"query": "리스크"}],
                ["FAILED", "OK"],
            ),
            started_at="2026-08-26T00:00:00Z",
            finished_at="2026-08-26T00:00:01Z",
            elapsed_ms=150,
            model="test-model",
            runtime="test-runtime",
            run_id="RUN001",
        )
        self.assertEqual(result["tool_reliability"]["retry_after_failure_count"], 0)
        self.assertEqual(result["tool_reliability"]["recovered_after_retry_count"], 0)

    def test_parallel_call_started_before_failure_is_not_retry(self):
        events = [
            {
                "type": "tool_started",
                "tool_ref": "document_search",
                "tool_call_id": "CALL1",
                "arguments": {"query": "일정"},
            },
            {
                "type": "tool_started",
                "tool_ref": "document_search",
                "tool_call_id": "CALL2",
                "arguments": {"query": "일정"},
            },
            {
                "type": "tool_completed",
                "tool_ref": "document_search",
                "tool_call_id": "CALL1",
                "status": "FAILED",
                "retrieved_doc_ids": [],
            },
            {
                "type": "tool_completed",
                "tool_ref": "document_search",
                "tool_call_id": "CALL2",
                "status": "OK",
                "retrieved_doc_ids": ["DC001"],
            },
            {"type": "result", "text": "답변", "iterations": 2, "duration_ms": 120},
        ]
        case = _case()
        case["max_tool_calls"] = 4
        case["max_calls_per_tool"]["document_search"] = 4
        result = evaluate_events(
            case=case,
            events=events,
            started_at="2026-08-26T00:00:00Z",
            finished_at="2026-08-26T00:00:01Z",
            elapsed_ms=150,
            model="test-model",
            runtime="test-runtime",
            run_id="RUN001",
        )
        self.assertEqual(result["tool_reliability"]["retry_after_failure_count"], 0)
        self.assertEqual(result["tool_reliability"]["recovered_after_retry_count"], 0)

    def test_report_only_judge_cannot_flip_failed_code_assertion(self):
        case = _case()
        case["max_tool_calls"] = 0
        result = evaluate_events(
            case=case,
            events=_events(),
            started_at="2026-08-26T00:00:00Z",
            finished_at="2026-08-26T00:00:01Z",
            elapsed_ms=150,
            model="test-model",
            runtime="test-runtime",
            run_id="RUN001",
            evidence_bundle={
                "DC001": {"status": "AVAILABLE", "excerpt": "근거 1"},
                "DC002": {"status": "AVAILABLE", "excerpt": "근거 2"},
            },
            judge=lambda _request: _judge_verdict(),
        )
        self.assertEqual(result["judge"]["status"], "COMPLETED")
        self.assertEqual(result["status"], "FAILED")

    def test_runner_and_calibration_share_strict_judge_response_contract(self):
        captured_request = {}

        def judge(request):
            captured_request.update(request)
            return _judge_verdict()

        result = evaluate_events(
            case=_case(),
            events=_events(),
            started_at="2026-08-26T00:00:00Z",
            finished_at="2026-08-26T00:00:01Z",
            elapsed_ms=150,
            model="test-model",
            runtime="test-runtime",
            run_id="RUN001",
            evidence_bundle={
                "DC001": {"status": "AVAILABLE", "excerpts": [{"text": "근거 1"}]},
                "DC002": {"status": "AVAILABLE", "excerpts": [{"text": "근거 2"}]},
            },
            judge=judge,
        )
        self.assertEqual(result["judge"]["status"], "COMPLETED")
        self.assertTrue(captured_request["deterministic_assertions"])
        self.assertTrue(captured_request["tool_trace"])
        self.assertEqual(captured_request["agent_run_id"], "RUN001")

        invalid = evaluate_events(
            case=_case(),
            events=_events(),
            started_at="2026-08-26T00:00:00Z",
            finished_at="2026-08-26T00:00:01Z",
            elapsed_ms=150,
            model="test-model",
            runtime="test-runtime",
            run_id="RUN001",
            evidence_bundle={
                "DC001": {"status": "AVAILABLE", "excerpts": [{"text": "근거 1"}]},
                "DC002": {"status": "AVAILABLE", "excerpts": [{"text": "근거 2"}]},
            },
            judge=lambda _request: {"task_success": "PASS"},
        )
        self.assertEqual(invalid["judge"]["status"], "ERROR")
        self.assertIn("overall_verdict", invalid["judge"]["reason"])

    def test_runner_fixes_tools_to_dataset_allowlist(self):
        class FakeExecutor:
            def __init__(self):
                self.kwargs = None

            def run(self, **kwargs):
                self.kwargs = kwargs
                return iter(_events())

        executor = FakeExecutor()
        context = RuntimeContext(
            account_id="UA001",
            team_id="TE001",
            role="leader",
            run_id="RUN001",
        )
        result = run_read_only_case(
            case=_case(),
            executor=executor,
            context=context,
            model="test-model",
            runtime="test-runtime",
            trace_wrapper=lambda events, **_kwargs: events,
        )
        self.assertEqual(
            executor.kwargs["tool_refs_override"], ["document_search", "document_list"]
        )
        self.assertEqual(result["status"], "SUCCESS")
        self.assertIn("time_to_first_token_ms", result["metrics"])

    def test_runner_rejects_non_read_only_case(self):
        case = _case()
        case["execution_mode"] = "hitl_sandbox"
        with self.assertRaisesRegex(ValueError, "read_only"):
            run_read_only_case(
                case=case,
                executor=object(),
                context=RuntimeContext(
                    account_id="UA001",
                    team_id="TE001",
                    role="leader",
                    run_id="RUN001",
                ),
                model="test-model",
                runtime="test-runtime",
            )


if __name__ == "__main__":
    unittest.main()
