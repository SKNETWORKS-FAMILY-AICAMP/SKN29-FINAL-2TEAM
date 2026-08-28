from __future__ import annotations

import unittest

from scripts.eval_v2_remaining import _judge_role


class EvalV2RemainingTests(unittest.TestCase):
    def test_s05_semantic_judge_is_secondary(self):
        self.assertEqual(_judge_role("S05A"), "SECONDARY")
        self.assertEqual(_judge_role("S05B"), "SECONDARY")

    def test_other_remaining_scenarios_use_primary_judge(self):
        for scenario in ("S02", "S03", "S06", "S09B"):
            self.assertEqual(_judge_role(scenario), "PRIMARY")


if __name__ == "__main__":
    unittest.main()
