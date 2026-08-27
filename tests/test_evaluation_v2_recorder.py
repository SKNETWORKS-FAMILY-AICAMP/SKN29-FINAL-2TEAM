import json
import tempfile
import unittest
from pathlib import Path

from services.evaluation.v2_recorder import V2EvaluationRecorder, read_completed_v2_run


def _record(scenario_id="S01", result="PASS"):
    return {
        "scenario_id": scenario_id,
        "fixture_id": f"{scenario_id}-DEV-001",
        "fixture_version": 1,
        "gold_version": 1,
        "scoring_contract_id": "eval-v2-scoring-v1",
        "scenario_result": result,
        "criteria": [],
        "hard_gate_triggered": False,
        "validity": "VALID",
    }


class EvaluationV2RecorderTests(unittest.TestCase):
    def test_records_v2_without_human_verdict_and_aggregates(self):
        with tempfile.TemporaryDirectory() as temporary:
            recorder = V2EvaluationRecorder.start(
                output_root=Path(temporary),
                manifest={
                    "git_commit": "abc123",
                    "candidate_id": "candidate-1",
                    "candidate_model": "gpt-5.6-sol",
                    "runtime_profile": "test",
                    "planned_scenarios": ["S01", "S04"],
                },
            )
            recorder.append_scenario(_record("S01", "PASS"))
            recorder.append_scenario(_record("S04", "INCONCLUSIVE"))
            summary = recorder.finalize()

            manifest = json.loads(
                (recorder.run_dir / "v2_run_manifest.json").read_text(encoding="utf-8")
            )
            self.assertFalse(manifest["official_human_verdict_enabled"])
            self.assertEqual(summary["strict_pass_rate"], 0.5)
            self.assertEqual(summary["counts"]["INCONCLUSIVE"], 1)

    def test_rejects_unplanned_or_duplicate_scenario(self):
        with tempfile.TemporaryDirectory() as temporary:
            recorder = V2EvaluationRecorder.start(
                output_root=Path(temporary),
                manifest={
                    "git_commit": "abc123",
                    "candidate_id": "candidate-1",
                    "candidate_model": "model",
                    "runtime_profile": "test",
                    "planned_scenarios": ["S01"],
                },
            )
            with self.assertRaisesRegex(ValueError, "계획되지 않은"):
                recorder.append_scenario(_record("S04"))
            recorder.append_scenario(_record("S01"))
            with self.assertRaisesRegex(ValueError, "한 번만"):
                recorder.append_scenario(_record("S01"))

    def test_infra_disposition_is_append_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            recorder = V2EvaluationRecorder.start(
                output_root=Path(temporary),
                manifest={
                    "git_commit": "abc123",
                    "candidate_id": "candidate-1",
                    "candidate_model": "model",
                    "runtime_profile": "test",
                    "planned_scenarios": ["S01"],
                },
            )
            disposition = recorder.record_disposition(
                status="INVALID_EVALUATION_INFRA", reason="DB migration 누락"
            )
            self.assertEqual(disposition["status"], "INVALID_EVALUATION_INFRA")
            with self.assertRaises(FileExistsError):
                recorder.record_disposition(status="VALID", reason="덮어쓰기 시도")

    def test_completed_run_bundle_has_file_and_line_hashes(self):
        with tempfile.TemporaryDirectory() as temporary:
            recorder = V2EvaluationRecorder.start(
                output_root=Path(temporary),
                manifest={
                    "git_commit": "abc123",
                    "candidate_id": "AG004/AV035",
                    "candidate_model": "model",
                    "runtime_profile": "test",
                    "planned_scenarios": ["S01"],
                },
            )
            recorder.append_scenario(_record("S01"))
            recorder.finalize()

            bundle = read_completed_v2_run(recorder.run_dir)

            self.assertEqual(bundle["manifest"]["eval_run_id"], recorder.manifest["eval_run_id"])
            self.assertEqual(len(bundle["results"]), 1)
            self.assertEqual(len(bundle["result_line_sha256"]), 1)
            self.assertEqual(set(bundle["hashes"]), {"manifest", "results", "summary"})
            self.assertTrue(all(len(value) == 64 for value in bundle["hashes"].values()))


if __name__ == "__main__":
    unittest.main()
