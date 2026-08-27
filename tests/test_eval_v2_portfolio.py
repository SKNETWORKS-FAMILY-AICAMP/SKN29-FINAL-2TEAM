import json
import tempfile
import unittest
from pathlib import Path

from scripts.eval_v2_portfolio import CORE_DEV_COHORT, build_portfolio


class EvalV2PortfolioTests(unittest.TestCase):
    def _write_run(
        self,
        root: Path,
        suffix: str,
        fixture_id: str,
        version: int,
        result: str = "PASS",
        invalid: bool = False,
    ) -> None:
        run = root / f"v2-{suffix}"
        run.mkdir()
        (run / "v2_run_manifest.json").write_text(json.dumps({
            "protocol": "AGENT_EVAL_V2",
            "eval_run_id": f"v2-{suffix}",
            "candidate_id": "AG004/AV035",
            "planned_scenarios": [fixture_id],
        }), encoding="utf-8")
        (run / "v2_scenario_results.jsonl").write_text(json.dumps({
            "fixture_id": fixture_id,
            "fixture_version": version,
            "scenario_result": result,
            "criteria": [],
        }) + "\n", encoding="utf-8")
        if invalid:
            (run / "v2_disposition.json").write_text(json.dumps({
                "status": "INVALID_EVALUATION_INFRA",
                "reason": "test fault",
            }), encoding="utf-8")

    def test_complete_cohort_uses_frozen_versions_and_excludes_invalid(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            counter = 0
            for fixture_id, specification in CORE_DEV_COHORT.items():
                for _ in range(specification["planned"]):
                    counter += 1
                    self._write_run(
                        root, str(counter), fixture_id,
                        specification["fixture_version"],
                    )
            self._write_run(root, "old", "S04-DEV-001", 1)
            self._write_run(root, "invalid", "S01-DEV-001", 1, invalid=True)

            payload = build_portfolio(root, "AG004/AV035")

            self.assertTrue(payload["complete"])
            self.assertEqual(payload["observed_run_count"], 36)
            self.assertEqual(payload["counts"], {"PASS": 36})
            self.assertEqual(payload["invalid_evaluation_infra_attempt_count"], 1)
            self.assertEqual(payload["variants"]["S04-DEV-001"]["observed"], 9)

    def test_missing_run_makes_cohort_incomplete(self):
        with tempfile.TemporaryDirectory() as temporary:
            payload = build_portfolio(Path(temporary), "AG004/AV035")
            self.assertFalse(payload["complete"])
            self.assertEqual(payload["observed_run_count"], 0)


if __name__ == "__main__":
    unittest.main()
