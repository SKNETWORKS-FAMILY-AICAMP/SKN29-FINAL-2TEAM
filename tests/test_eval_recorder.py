from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.evaluation import recorder as recorder_module
from services.evaluation.recorder import EvaluationRecorder, _writer_lock


REPO_ROOT = Path(__file__).resolve().parents[1]


class EvaluationRecorderTests(unittest.TestCase):
    def _start_recorder(self, output_root: Path) -> EvaluationRecorder:
        return EvaluationRecorder.start(
            output_root=output_root,
            manifest={
                "git_commit": "abc1234",
                "dataset_id": "agent-poc-v1",
                "dataset_version": 1,
                "targets": [{"agent_id": "AG004", "agent_version_id": "AV035"}],
                "models": ["test-model"],
                "runtime": "deepagents-0.7.5",
                "environment": "local-sandbox",
                "repetitions": 1,
            },
        )

    def _case_result(self, **overrides):
        result = {
            "case_id": "EVAL-NOTOOL-001",
            "agent_id": "AG004",
            "agent_version_id": "AV035",
            "model": "test-model",
            "runtime": "deepagents-0.7.5",
            "started_at": "2026-08-25T00:00:00Z",
            "finished_at": "2026-08-25T00:00:01Z",
            "status": "SUCCESS",
            "assertions": [],
            "failure_reason": None,
            "agent_run_id": "RUN001",
            "tool_call_ids": [],
            "langfuse_trace_id": "TRACE001",
            "metrics": {},
            "approval": None,
            "side_effects": [],
            "cleanup": {"status": "NOT_REQUIRED"},
        }
        result.update(overrides)
        return result

    def test_manifest_accepts_multiple_agent_targets(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = EvaluationRecorder.start(
                output_root=Path(temp_dir),
                manifest={
                    "git_commit": "abc1234",
                    "dataset_id": "agent-poc-v1",
                    "dataset_version": 1,
                    "targets": [
                        {"agent_id": "AG004", "agent_version_id": "AV035"},
                        {"agent_id": "AG006", "agent_version_id": "AV006"},
                    ],
                    "models": ["test-model"],
                    "runtime": "deepagents-0.7.5",
                    "environment": "local-sandbox",
                    "repetitions": 1,
                },
            )

            self.assertEqual(len(recorder.manifest["targets"]), 2)

    def test_manifest_cannot_override_generated_run_identity(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = EvaluationRecorder.start(
                output_root=Path(temp_dir),
                manifest={
                    "schema_version": 999,
                    "eval_run_id": "spoofed-run",
                    "started_at": "1900-01-01T00:00:00Z",
                    "git_commit": "abc1234",
                    "dataset_id": "agent-poc-v1",
                    "dataset_version": 1,
                    "targets": [{"agent_id": "AG004", "agent_version_id": "AV035"}],
                    "models": ["test-model"],
                    "runtime": "deepagents-0.7.5",
                    "environment": "local-sandbox",
                    "repetitions": 1,
                },
            )

            self.assertEqual(recorder.manifest["schema_version"], 1)
            self.assertNotEqual(recorder.eval_run_id, "spoofed-run")
            self.assertNotEqual(recorder.manifest["started_at"], "1900-01-01T00:00:00Z")

    def test_run_lifecycle_creates_four_readable_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = EvaluationRecorder.start(
                output_root=Path(temp_dir),
                manifest={
                    "git_commit": "abc1234",
                    "dataset_id": "agent-poc-v1",
                    "dataset_version": 1,
                    "targets": [{"agent_id": "AG004", "agent_version_id": "AV035"}],
                    "models": ["test-model"],
                    "runtime": "deepagents-0.7.5",
                    "environment": "local-sandbox",
                    "repetitions": 1,
                },
            )
            recorder.append_case(
                {
                    "case_id": "EVAL-NOTOOL-001",
                    "agent_id": "AG004",
                    "agent_version_id": "AV035",
                    "model": "test-model",
                    "runtime": "deepagents-0.7.5",
                    "started_at": "2026-08-25T00:00:00Z",
                    "finished_at": "2026-08-25T00:00:01Z",
                    "status": "SUCCESS",
                    "assertions": [{"name": "tool_calls", "passed": True}],
                    "failure_reason": None,
                    "agent_run_id": "RUN001",
                    "tool_call_ids": [],
                    "langfuse_trace_id": "TRACE001",
                    "metrics": {
                        "end_to_end_latency_ms": 1000,
                        "input_tokens": 10,
                        "output_tokens": 5,
                        "tool_call_count": 0,
                    },
                    "approval": None,
                    "side_effects": [],
                    "cleanup": {"status": "NOT_REQUIRED"},
                }
            )
            recorder.finalize(status="COMPLETED", limitations=["수동 실행 예시"])

            self.assertEqual(
                {path.name for path in recorder.run_dir.iterdir()},
                {"run_manifest.json", "case_results.jsonl", "summary.json", "report.md"},
            )

            manifest = json.loads(
                (recorder.run_dir / "run_manifest.json").read_text(encoding="utf-8")
            )
            case_result = json.loads(
                (recorder.run_dir / "case_results.jsonl")
                .read_text(encoding="utf-8")
                .strip()
            )
            summary = json.loads(
                (recorder.run_dir / "summary.json").read_text(encoding="utf-8")
            )
            report = (recorder.run_dir / "report.md").read_text(encoding="utf-8")

            self.assertEqual(manifest["eval_run_id"], recorder.eval_run_id)
            self.assertEqual(case_result["eval_run_id"], recorder.eval_run_id)
            self.assertEqual(case_result["git_commit"], "abc1234")
            self.assertEqual(summary["case_count"], 1)
            self.assertEqual(summary["status_counts"], {"SUCCESS": 1})
            self.assertEqual(summary["metrics"]["total_tokens"], 15)
            self.assertIn(recorder.eval_run_id, report)
            self.assertIn("수동 실행 예시", report)

    def test_existing_run_can_be_reopened_before_finalize(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            started = EvaluationRecorder.start(
                output_root=Path(temp_dir),
                manifest={
                    "git_commit": "abc1234",
                    "dataset_id": "agent-poc-v1",
                    "dataset_version": 1,
                    "targets": [{"agent_id": "AG004", "agent_version_id": "AV035"}],
                    "models": ["test-model"],
                    "runtime": "deepagents-0.7.5",
                    "environment": "local-sandbox",
                    "repetitions": 1,
                },
            )

            reopened = EvaluationRecorder.open(started.run_dir)

            self.assertEqual(reopened.eval_run_id, started.eval_run_id)
            self.assertEqual(reopened.manifest, started.manifest)

    def test_aborted_run_is_preserved_and_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = EvaluationRecorder.start(
                output_root=Path(temp_dir),
                manifest={
                    "git_commit": "abc1234",
                    "dataset_id": "agent-poc-v1",
                    "dataset_version": 1,
                    "targets": [{"agent_id": "AG004", "agent_version_id": "AV035"}],
                    "models": ["test-model"],
                    "runtime": "deepagents-0.7.5",
                    "environment": "local-sandbox",
                    "repetitions": 1,
                },
            )
            recorder.finalize(status="ABORTED", limitations=["사용자가 실행을 중단함"])
            original_summary = (recorder.run_dir / "summary.json").read_bytes()

            with self.assertRaises(FileExistsError):
                recorder.finalize(status="COMPLETED", limitations=[])
            with self.assertRaises(RuntimeError):
                recorder.append_case({})

            self.assertEqual(
                (recorder.run_dir / "summary.json").read_bytes(), original_summary
            )

    def test_case_cannot_override_run_identity(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = EvaluationRecorder.start(
                output_root=Path(temp_dir),
                manifest={
                    "git_commit": "abc1234",
                    "dataset_id": "agent-poc-v1",
                    "dataset_version": 1,
                    "targets": [{"agent_id": "AG004", "agent_version_id": "AV035"}],
                    "models": ["test-model"],
                    "runtime": "deepagents-0.7.5",
                    "environment": "local-sandbox",
                    "repetitions": 1,
                },
            )
            recorder.append_case(
                {
                    "schema_version": 999,
                    "eval_run_id": "spoofed-run",
                    "git_commit": "spoofed-commit",
                    "dataset_id": "spoofed-dataset",
                    "dataset_version": 999,
                    "case_id": "EVAL-NOTOOL-001",
                    "agent_id": "AG004",
                    "agent_version_id": "AV035",
                    "model": "test-model",
                    "runtime": "deepagents-0.7.5",
                    "started_at": "2026-08-25T00:00:00Z",
                    "finished_at": "2026-08-25T00:00:01Z",
                    "status": "SUCCESS",
                    "assertions": [],
                    "failure_reason": None,
                    "agent_run_id": "RUN001",
                    "tool_call_ids": [],
                    "langfuse_trace_id": "TRACE001",
                    "metrics": {},
                    "approval": None,
                    "side_effects": [],
                    "cleanup": {"status": "NOT_REQUIRED"},
                }
            )

            stored = json.loads(
                (recorder.run_dir / "case_results.jsonl").read_text(encoding="utf-8")
            )
            self.assertEqual(stored["schema_version"], 1)
            self.assertEqual(stored["eval_run_id"], recorder.eval_run_id)
            self.assertEqual(stored["git_commit"], "abc1234")
            self.assertEqual(stored["dataset_id"], "agent-poc-v1")
            self.assertEqual(stored["dataset_version"], 1)

    def test_active_writer_lock_rejects_concurrent_append(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = EvaluationRecorder.start(
                output_root=Path(temp_dir),
                manifest={
                    "git_commit": "abc1234",
                    "dataset_id": "agent-poc-v1",
                    "dataset_version": 1,
                    "targets": [{"agent_id": "AG004", "agent_version_id": "AV035"}],
                    "models": ["test-model"],
                    "runtime": "deepagents-0.7.5",
                    "environment": "local-sandbox",
                    "repetitions": 1,
                },
            )
            (recorder.run_dir / ".recording.lock").mkdir()

            with self.assertRaisesRegex(RuntimeError, "다른 기록 작업"):
                recorder.append_case(
                    {
                        "case_id": "EVAL-NOTOOL-001",
                        "agent_id": "AG004",
                        "agent_version_id": "AV035",
                        "model": "test-model",
                        "runtime": "deepagents-0.7.5",
                        "started_at": "2026-08-25T00:00:00Z",
                        "finished_at": "2026-08-25T00:00:01Z",
                        "status": "SUCCESS",
                        "assertions": [],
                        "failure_reason": None,
                        "agent_run_id": "RUN001",
                        "tool_call_ids": [],
                        "langfuse_trace_id": "TRACE001",
                        "metrics": {},
                        "approval": None,
                        "side_effects": [],
                        "cleanup": {"status": "NOT_REQUIRED"},
                    }
                )

            self.assertEqual(
                (recorder.run_dir / "case_results.jsonl").read_text(encoding="utf-8"),
                "",
            )

    def test_invalid_case_is_rejected_before_jsonl_changes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = self._start_recorder(Path(temp_dir))

            with self.assertRaisesRegex(ValueError, "metrics"):
                recorder.append_case(self._case_result(metrics=None))

            self.assertEqual(
                (recorder.run_dir / "case_results.jsonl").read_text(encoding="utf-8"),
                "",
            )

    def test_report_failure_does_not_publish_completion_marker(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = self._start_recorder(Path(temp_dir))
            recorder.append_case(self._case_result())

            with patch.object(
                EvaluationRecorder,
                "_write_report",
                side_effect=OSError("disk full"),
            ):
                with self.assertRaisesRegex(OSError, "disk full"):
                    recorder.finalize(status="COMPLETED", limitations=[])

            self.assertFalse((recorder.run_dir / "summary.json").exists())
            recorder.finalize(status="COMPLETED", limitations=[])
            self.assertTrue((recorder.run_dir / "summary.json").is_file())

    def test_summary_failure_blocks_append_and_finalize_can_retry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = self._start_recorder(Path(temp_dir))
            recorder.append_case(self._case_result())

            def fail_summary(path, payload):
                if path.name == "summary.json":
                    raise OSError("disk full")
                return original_write(path, payload)

            original_write = recorder_module._write_json_exclusive

            with patch(
                "services.evaluation.recorder._write_json_exclusive",
                side_effect=fail_summary,
            ):
                with self.assertRaisesRegex(OSError, "disk full"):
                    recorder.finalize(status="COMPLETED", limitations=[])

            self.assertTrue((recorder.run_dir / "report.md").is_file())
            self.assertFalse((recorder.run_dir / "summary.json").exists())
            with self.assertRaisesRegex(RuntimeError, "종료"):
                recorder.append_case(self._case_result(case_id="LATE-CASE"))

            recorder.finalize(status="COMPLETED", limitations=[])
            self.assertTrue((recorder.run_dir / "summary.json").is_file())

    def test_non_finite_metric_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = self._start_recorder(Path(temp_dir))

            with self.assertRaisesRegex(ValueError, "유한"):
                recorder.append_case(self._case_result(metrics={"latency_ms": float("nan")}))

    def test_invalid_progress_milestone_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = self._start_recorder(Path(temp_dir))

            with self.assertRaisesRegex(ValueError, r"progress.milestones\[0\].status"):
                recorder.append_case(
                    self._case_result(
                        progress={
                            "milestones": [
                                {"name": "근거 확보", "status": "UNKNOWN"},
                            ]
                        }
                    )
                )

    def test_summary_and_report_include_progress_rate_and_failed_milestone(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = self._start_recorder(Path(temp_dir))
            recorder.append_case(
                self._case_result(
                    case_id="EVAL-PROGRESS-001",
                    status="FAILED",
                    failure_reason="외부 반영 실패",
                    progress={
                        "milestones": [
                            {"name": "근거 확보", "status": "COMPLETED"},
                            {"name": "초안 생성", "status": "COMPLETED"},
                            {"name": "외부 반영", "status": "FAILED"},
                            {"name": "사후 검증", "status": "NOT_REACHED"},
                        ]
                    },
                )
            )

            recorder.finalize(status="COMPLETED", limitations=[])

            summary = json.loads(
                (recorder.run_dir / "summary.json").read_text(encoding="utf-8")
            )
            report = (recorder.run_dir / "report.md").read_text(encoding="utf-8")
            self.assertEqual(
                summary["progress"],
                {
                    "case_count": 1,
                    "average_rate": 0.5,
                    "milestone_status_counts": {
                        "COMPLETED": 2,
                        "FAILED": 1,
                        "NOT_REACHED": 1,
                    },
                    "cases": [
                        {
                            "case_id": "EVAL-PROGRESS-001",
                            "completed": 2,
                            "total": 4,
                            "rate": 0.5,
                            "failed_milestones": ["외부 반영"],
                        }
                    ],
                },
            )
            self.assertIn("평균 진행률: 50.0%", report)
            self.assertIn("외부 반영", report)

    def test_writer_lock_records_owner_for_stale_lock_recovery(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)

            with _writer_lock(run_dir):
                owner = json.loads(
                    (run_dir / ".recording.lock" / "owner.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertIsInstance(owner["pid"], int)
                self.assertTrue(owner["acquired_at"].endswith("Z"))

            self.assertFalse((run_dir / ".recording.lock").exists())

    def test_summary_and_report_expose_failures_safety_and_operational_metrics(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = self._start_recorder(Path(temp_dir))
            recorder.append_case(
                self._case_result(
                    case_id="EVAL-SAFETY-001",
                    status="FAILED",
                    assertions=[
                        {
                            "name": "no_duplicate_write",
                            "passed": False,
                            "category": "safety",
                        }
                    ],
                    failure_reason="중복 쓰기 발견",
                    metrics={
                        "active_execution_latency_ms": 1200,
                        "input_tokens": 10,
                        "output_tokens": 5,
                        "tool_call_count": 2,
                    },
                    approval={"decision": "approve"},
                    side_effects=[{"name": "skill", "violation": True}],
                    cleanup={"status": "FAILED"},
                )
            )

            recorder.finalize(status="COMPLETED", limitations=[])

            summary = json.loads(
                (recorder.run_dir / "summary.json").read_text(encoding="utf-8")
            )
            report = (recorder.run_dir / "report.md").read_text(encoding="utf-8")
            self.assertEqual(summary["safety_violation_count"], 1)
            self.assertEqual(summary["cleanup_status_counts"], {"FAILED": 1})
            self.assertEqual(summary["approval_decision_counts"], {"approve": 1})
            self.assertEqual(summary["failed_cases"][0]["case_id"], "EVAL-SAFETY-001")
            self.assertEqual(summary["metrics"]["total_tokens"], 15)
            self.assertEqual(
                summary["latency_ms"]["active_execution_latency_ms"],
                {"count": 1, "p50": 1200, "p95": 1200},
            )
            self.assertIn("EVAL-SAFETY-001", report)
            self.assertIn("중복 쓰기 발견", report)
            self.assertIn("안전 위반: 1", report)
            self.assertIn("active_execution_latency_ms", report)
            self.assertIn("tool_call_count", report)

    def test_expected_non_success_outcomes_are_not_reported_as_failures(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = self._start_recorder(Path(temp_dir))
            recorder.append_case(
                self._case_result(
                    case_id="EVAL-HITL-002",
                    status="REJECTED",
                )
            )
            recorder.append_case(
                self._case_result(
                    case_id="EVAL-CLARIFY-001",
                    status="NEEDS_CLARIFICATION",
                )
            )

            recorder.finalize(status="COMPLETED", limitations=[])

            summary = json.loads(
                (recorder.run_dir / "summary.json").read_text(encoding="utf-8")
            )
            self.assertEqual(summary["failed_cases"], [])

    def test_cli_records_a_manual_run_across_separate_commands(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output_root = temp_path / "results"
            manifest_path = temp_path / "manifest.json"
            case_path = temp_path / "case.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "git_commit": "abc1234",
                        "dataset_id": "agent-poc-v1",
                        "dataset_version": 1,
                        "targets": [
                            {"agent_id": "AG004", "agent_version_id": "AV035"}
                        ],
                        "models": ["test-model"],
                        "runtime": "deepagents-0.7.5",
                        "environment": "local-sandbox",
                        "repetitions": 1,
                    }
                ),
                encoding="utf-8",
            )
            case_path.write_text(
                json.dumps(
                    {
                        "case_id": "EVAL-NOTOOL-001",
                        "agent_id": "AG004",
                        "agent_version_id": "AV035",
                        "model": "test-model",
                        "runtime": "deepagents-0.7.5",
                        "started_at": "2026-08-25T00:00:00Z",
                        "finished_at": "2026-08-25T00:00:01Z",
                        "status": "SUCCESS",
                        "assertions": [{"name": "tool_calls", "passed": True}],
                        "failure_reason": None,
                        "agent_run_id": "RUN001",
                        "tool_call_ids": [],
                        "langfuse_trace_id": "TRACE001",
                        "metrics": {"input_tokens": 10, "output_tokens": 5},
                        "approval": None,
                        "side_effects": [],
                        "cleanup": {"status": "NOT_REQUIRED"},
                    }
                ),
                encoding="utf-8",
            )
            cli = REPO_ROOT / "scripts" / "eval_record.py"

            started = subprocess.run(
                [
                    sys.executable,
                    str(cli),
                    "start",
                    "--output-root",
                    str(output_root),
                    "--manifest",
                    str(manifest_path),
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(started.returncode, 0, started.stderr)
            run_dir = Path(started.stdout.strip())

            appended = subprocess.run(
                [
                    sys.executable,
                    str(cli),
                    "append-case",
                    "--run-dir",
                    str(run_dir),
                    "--case-result",
                    str(case_path),
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(appended.returncode, 0, appended.stderr)

            finalized = subprocess.run(
                [
                    sys.executable,
                    str(cli),
                    "finalize",
                    "--run-dir",
                    str(run_dir),
                    "--status",
                    "COMPLETED",
                    "--limitation",
                    "수동 실행 예시",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(finalized.returncode, 0, finalized.stderr)
            self.assertTrue((run_dir / "report.md").is_file())


if __name__ == "__main__":
    unittest.main()
