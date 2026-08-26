from __future__ import annotations

import unittest
from contextlib import contextmanager
from unittest.mock import patch

from backend.db import evaluation
from backend.db.evaluation import EvaluationResultRepository


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


if __name__ == "__main__":
    unittest.main()
