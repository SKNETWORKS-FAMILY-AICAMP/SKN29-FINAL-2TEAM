import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from scripts.eval_v2_summary import main


class EvalV2SummaryScriptTests(unittest.TestCase):
    def test_fixture_filter_excludes_other_fixture_infra_attempt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            invalid = root / "v2-invalid"
            invalid.mkdir()
            (invalid / "v2_run_manifest.json").write_text(
                json.dumps({
                    "protocol": "AGENT_EVAL_V2", "eval_run_id": "v2-invalid",
                    "candidate_id": "C1", "planned_scenarios": ["S01-DEV-001"],
                }), encoding="utf-8"
            )
            (invalid / "v2_scenario_results.jsonl").write_text("", encoding="utf-8")
            (invalid / "v2_disposition.json").write_text(
                json.dumps({"status": "INVALID_EVALUATION_INFRA", "reason": "migration"}),
                encoding="utf-8",
            )
            valid = root / "v2-valid"
            valid.mkdir()
            (valid / "v2_run_manifest.json").write_text(
                json.dumps({
                    "protocol": "AGENT_EVAL_V2", "eval_run_id": "v2-valid",
                    "candidate_id": "C1", "planned_scenarios": ["S04-DEV-001"],
                }), encoding="utf-8"
            )
            result = {
                "fixture_id": "S04-DEV-001", "scenario_result": "PASS", "criteria": []
            }
            (valid / "v2_scenario_results.jsonl").write_text(
                json.dumps(result) + "\n", encoding="utf-8"
            )

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = main([
                    "--results-root", str(root), "--fixture-id", "S04-DEV-001",
                    "--candidate-id", "C1", "--planned", "1",
                ])
            payload = json.loads(output.getvalue())

            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["aggregate"]["counts"]["PASS"], 1)
            self.assertEqual(payload["infra_attempt_count"], 0)


if __name__ == "__main__":
    unittest.main()
