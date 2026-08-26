from __future__ import annotations

import unittest

from scripts.eval_run import _append_result_after_cleanup_attempt


class _Recorder:
    def __init__(self):
        self.results: list[dict] = []

    def append_case(self, result: dict) -> None:
        self.results.append(dict(result))


class EvalRunCleanupTests(unittest.TestCase):
    def test_cleanup_failure_still_appends_completed_agent_result(self):
        recorder = _Recorder()
        result = {"case_id": "WF-001", "status": "SUCCESS"}

        def fail_cleanup() -> None:
            raise ConnectionError("database unavailable")

        error = _append_result_after_cleanup_attempt(
            recorder=recorder,
            result=result,
            cleanup=fail_cleanup,
        )

        self.assertIsInstance(error, ConnectionError)
        self.assertEqual(len(recorder.results), 1)
        self.assertEqual(recorder.results[0]["status"], "SUCCESS")
        self.assertEqual(recorder.results[0]["cleanup"]["status"], "FAILED")
        self.assertEqual(recorder.results[0]["cleanup"]["error_type"], "ConnectionError")

    def test_cleanup_success_appends_completed_cleanup(self):
        recorder = _Recorder()
        result = {"case_id": "WF-001", "status": "SUCCESS"}

        error = _append_result_after_cleanup_attempt(
            recorder=recorder,
            result=result,
            cleanup=lambda: None,
        )

        self.assertIsNone(error)
        self.assertEqual(recorder.results[0]["cleanup"]["status"], "COMPLETED")


if __name__ == "__main__":
    unittest.main()
