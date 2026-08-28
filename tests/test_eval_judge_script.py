import unittest
from pathlib import Path

from scripts.eval_judge import DEFAULT_JUDGE_MODEL, DEFAULT_REASONING_EFFORT, _parser


class EvalJudgeScriptTests(unittest.TestCase):
    def test_judge_model_defaults_to_sol(self):
        args = _parser().parse_args(
            [
                "--run-dir",
                "run",
                "--case-id",
                "S01",
                "--evidence",
                "evidence.json",
                "--account-id",
                "UA001",
            ]
        )

        self.assertEqual(DEFAULT_JUDGE_MODEL, "gpt-5.6-sol")
        self.assertEqual(args.judge_model, "gpt-5.6-sol")
        self.assertEqual(DEFAULT_REASONING_EFFORT, "medium")
        self.assertEqual(args.reasoning_effort, "medium")
        self.assertEqual(args.run_dir, Path("run"))

    def test_judge_model_can_be_explicitly_overridden(self):
        args = _parser().parse_args(
            [
                "--run-dir",
                "run",
                "--case-id",
                "S01",
                "--evidence",
                "evidence.json",
                "--account-id",
                "UA001",
                "--judge-model",
                "gpt-5.6-terra",
            ]
        )

        self.assertEqual(args.judge_model, "gpt-5.6-terra")


if __name__ == "__main__":
    unittest.main()
