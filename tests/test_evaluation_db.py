from __future__ import annotations

import unittest
from contextlib import contextmanager
from unittest.mock import patch

from backend.db import evaluation
from backend.db.evaluation import EvaluationResultRepository, V2EvaluationResultRepository


class _Cursor:
    def __init__(self, fetchone_results):
        self._fetchone_results = iter(fetchone_results)
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, params):
        self.executed.append((sql, params))

    def fetchone(self):
        return next(self._fetchone_results)


class _Connection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


def _connection_factory(*cursors):
    remaining = iter(cursors)

    @contextmanager
    def factory():
        yield _Connection(next(remaining))

    return factory


class EvaluationResultRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.manifest = {
            "schema_version": 1,
            "eval_run_id": "20260826T000000Z-12345678",
            "git_commit": "abc123",
            "dataset_id": "agent-workflow-v1",
            "dataset_version": 9,
            "runtime": "deepagents-0.7.5",
            "environment": "local-test",
            "repetitions": 1,
            "started_at": "2026-08-26T00:00:00Z",
            "targets": [{"agent_id": "AG004", "agent_version_id": "AV035"}],
            "models": ["test-model"],
        }
        self.case = {
            "schema_version": 1,
            "eval_run_id": self.manifest["eval_run_id"],
            "case_id": "WF-TEST-001",
            "agent_id": "AG004",
            "agent_version_id": "AV035",
            "model": "test-model",
            "runtime": "deepagents-0.7.5",
            "status": "SUCCESS",
            "started_at": "2026-08-26T00:00:01Z",
            "finished_at": "2026-08-26T00:00:02Z",
            "agent_run_id": None,
            "langfuse_trace_id": None,
            "metrics": {"total_tokens": 10},
        }
        self.summary = {
            "eval_run_id": self.manifest["eval_run_id"],
            "run_status": "COMPLETED",
            "finished_at": "2026-08-26T00:00:03Z",
            "case_count": 1,
        }

    def test_new_run_and_case_are_synced(self):
        run_cursor = _Cursor([{"eval_run_id": self.manifest["eval_run_id"]}])
        case_cursor = _Cursor([{"case_index": 1}])

        with patch.object(
            evaluation,
            "database_connection",
            _connection_factory(run_cursor, case_cursor),
        ):
            result = EvaluationResultRepository.sync_completed_run(
                manifest=self.manifest,
                case_results=[self.case],
                summary=self.summary,
            )

        self.assertEqual(result["sync_status"], "SYNCED")
        self.assertEqual(result["case_count"], 1)
        self.assertEqual(len(run_cursor.executed), 1)
        self.assertEqual(len(case_cursor.executed), 2)
        self.assertIn("SYNCED", case_cursor.executed[-1][0])

    def test_identical_run_can_be_synced_again(self):
        run_cursor = _Cursor(
            [None, {"manifest": self.manifest, "summary": self.summary}]
        )
        case_cursor = _Cursor([None, {"result": self.case}])

        with patch.object(
            evaluation,
            "database_connection",
            _connection_factory(run_cursor, case_cursor),
        ):
            result = EvaluationResultRepository.sync_completed_run(
                manifest=self.manifest,
                case_results=[self.case],
                summary=self.summary,
            )

        self.assertEqual(result["sync_status"], "SYNCED")
        self.assertEqual(len(run_cursor.executed), 2)
        self.assertEqual(len(case_cursor.executed), 3)

    def test_same_run_id_with_different_payload_is_rejected(self):
        run_cursor = _Cursor(
            [None, {"manifest": {**self.manifest, "git_commit": "different"}, "summary": self.summary}]
        )

        with patch.object(
            evaluation,
            "database_connection",
            _connection_factory(run_cursor),
        ):
            with self.assertRaisesRegex(ValueError, "다른 평가 결과"):
                EvaluationResultRepository.sync_completed_run(
                    manifest=self.manifest,
                    case_results=[self.case],
                    summary=self.summary,
                )


class V2EvaluationResultRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.result = {
            "eval_run_id": "v2-20260827T000000Z-12345678",
            "scenario_id": "S01-DEV-001", "fixture_id": "S01-DEV-001",
            "fixture_version": 1, "gold_version": 1,
            "scenario_result": "PASS", "validity": "VALID",
        }
        self.bundle = {
            "manifest": {
                "protocol": "AGENT_EVAL_V2", "schema_version": 1,
                "eval_run_id": self.result["eval_run_id"], "git_commit": "abc123",
                "candidate_id": "AG004/AV035", "candidate_model": "model",
                "runtime_profile": "runtime", "started_at": "2026-08-27T00:00:00Z",
            },
            "results": [self.result], "result_line_sha256": ["d" * 64],
            "summary": {"eval_run_id": self.result["eval_run_id"], "finished_at": "2026-08-27T00:00:01Z"},
            "disposition": None,
            "hashes": {"manifest": "a" * 64, "results": "b" * 64, "summary": "c" * 64},
        }

    def test_new_v2_run_is_synced(self):
        cursor = _Cursor([{"eval_run_id": self.result["eval_run_id"]}, {"scenario_index": 1}])
        with patch.object(evaluation, "database_connection", _connection_factory(cursor)):
            synced = V2EvaluationResultRepository.sync_completed_run(self.bundle)
        self.assertEqual(synced["sync_status"], "SYNCED")
        self.assertEqual(synced["scenario_count"], 1)

    def test_v2_reconciliation_compares_payload_and_hashes(self):
        expected_run = {
            "manifest": self.bundle["manifest"], "summary": self.bundle["summary"],
            "disposition": None, "manifest_sha256": "a" * 64,
            "results_sha256": "b" * 64, "summary_sha256": "c" * 64,
            "disposition_sha256": None,
        }
        cursor = _Cursor([expected_run])
        cursor.fetchall = lambda: [{"scenario_index": 1, "result": self.result, "record_sha256": "d" * 64}]
        with patch.object(evaluation, "database_connection", _connection_factory(cursor)):
            checked = V2EvaluationResultRepository.reconcile_completed_run(self.bundle)
        self.assertTrue(checked["matched"])


class EvaluationJudgeResultRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.record = {
            "schema_version": 1,
            "calibration_id": "cal-1",
            "eval_run_id": "20260826T000000Z-12345678",
            "case_id": "WF-TEST-001",
            "agent_run_id": "agent-run-uuid-1",
            "mode": "REPORT_ONLY",
            "human_verdict": {"overall_verdict": "FAIL", "dimensions": {}},
            "judge": {
                "model": "gpt-5.6-luna",
                "prompt_version": "judge-calibration-v0",
                "latency_ms": 123.456,
                "usage": {"total_tokens": 50},
                "verdict": {"overall_verdict": "FAIL", "dimensions": {}},
            },
            "comparison": {"overall_agreement": True},
        }

    def test_new_judge_result_is_synced(self):
        cursor = _Cursor([{"case_index": 1}, {"case_index": 1}])

        with patch.object(evaluation, "database_connection", _connection_factory(cursor)):
            result = EvaluationResultRepository.sync_judge_result(self.record)

        self.assertEqual(result["sync_status"], "SYNCED")
        self.assertEqual(result["case_index"], 1)
        self.assertEqual(len(cursor.executed), 2)
        self.assertIn("INSERT INTO eval_judge_result", cursor.executed[1][0])

    def test_missing_case_index_raises(self):
        cursor = _Cursor([None])

        with patch.object(evaluation, "database_connection", _connection_factory(cursor)):
            with self.assertRaisesRegex(ValueError, "case_index를 찾지 못"):
                EvaluationResultRepository.sync_judge_result(self.record)

    def test_identical_judge_result_can_be_synced_again(self):
        cursor = _Cursor(
            [
                {"case_index": 1},
                None,
                {"verdict": self.record["judge"]["verdict"]},
            ]
        )

        with patch.object(evaluation, "database_connection", _connection_factory(cursor)):
            result = EvaluationResultRepository.sync_judge_result(self.record)

        self.assertEqual(result["sync_status"], "SYNCED")
        self.assertEqual(len(cursor.executed), 3)

    def test_conflicting_judge_result_is_rejected(self):
        cursor = _Cursor(
            [
                {"case_index": 1},
                None,
                {"verdict": {"overall_verdict": "PASS", "dimensions": {}}},
            ]
        )

        with patch.object(evaluation, "database_connection", _connection_factory(cursor)):
            with self.assertRaisesRegex(ValueError, "다른 결과가 이미"):
                EvaluationResultRepository.sync_judge_result(self.record)


class FetchAgentExecutionSummaryTests(unittest.TestCase):
    def test_recovers_final_answer_and_tool_call_ids(self):
        cursor = _Cursor([{"session_id": "session-1"}])
        cursor.fetchall_results = iter(
            [
                [
                    {"content": {"type": "text", "text": "첫 번째 안내"}},
                    {"content": {"type": "text", "text": "최종 답변"}},
                ],
                [{"tool_call_id": "tc-1"}, {"tool_call_id": "tc-2"}],
            ]
        )
        cursor.fetchall = lambda: next(cursor.fetchall_results)

        with patch.object(evaluation, "database_connection", _connection_factory(cursor)):
            result = evaluation.EvaluationResultRepository.fetch_agent_execution_summary(
                "agent-run-1"
            )

        self.assertEqual(result["final_answer"], "최종 답변")
        self.assertEqual(result["tool_call_ids"], ["tc-1", "tc-2"])

    def test_missing_session_returns_empty_answer(self):
        cursor = _Cursor([None])
        cursor.fetchall = lambda: []

        with patch.object(evaluation, "database_connection", _connection_factory(cursor)):
            result = evaluation.EvaluationResultRepository.fetch_agent_execution_summary(
                "agent-run-missing"
            )

        self.assertIsNone(result["final_answer"])
        self.assertEqual(result["tool_call_ids"], [])


if __name__ == "__main__":
    unittest.main()
