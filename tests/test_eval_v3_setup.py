from __future__ import annotations

import unittest

from scripts.eval_v3 import build_plan, validate_setup


class EvalV3SetupTests(unittest.TestCase):
    def test_setup_has_22_variants_and_66_runs(self):
        result = validate_setup()
        self.assertEqual(result["status"], "READY")
        self.assertEqual(result["variants"], 22)
        self.assertEqual(result["legacy_variants"], 16)
        self.assertEqual(result["delta_variants"], 6)
        self.assertEqual(result["official_runs"], 66)
        self.assertEqual(result["corpus_pdf_count"], 101)

    def test_full_plan_repeats_every_variant_three_times(self):
        plan = build_plan(
            variant_id=None,
            cohort="all",
            repeats=3,
            account_id="UA002",
            agent_id="AG004",
            agent_version_id="AV073",
        )
        self.assertEqual(plan["planned_runs"], 66)
        self.assertEqual(len({row["variant_id"] for row in plan["runs"]}), 22)
        self.assertTrue(all(1 <= row["repeat"] <= 3 for row in plan["runs"]))

    def test_delta_plan_uses_v3_fixture_and_binding_paths(self):
        plan = build_plan(
            variant_id="D01",
            cohort="all",
            repeats=1,
            account_id="UA002",
            agent_id="AG004",
            agent_version_id="AV073",
        )
        command = plan["runs"][0]["command"]
        self.assertIn("--fixture-dir", command)
        self.assertIn("--binding", command)
        self.assertIn("eval-v3-results", command[-1])


if __name__ == "__main__":
    unittest.main()
