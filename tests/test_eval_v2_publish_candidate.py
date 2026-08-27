import unittest

from scripts.eval_v2_publish_candidate import PROMPT_MARKER, build_candidate_prompt


class EvalV2PublishCandidateTests(unittest.TestCase):
    def test_adds_general_completeness_without_fixture_answer(self):
        prompt = build_candidate_prompt("기본 지시")

        self.assertIn(PROMPT_MARKER, prompt)
        self.assertIn("사용자가 명시적으로 요청한 항목", prompt)
        self.assertIn("요청 범위를 벗어난", prompt)
        self.assertNotIn("2026-09-22", prompt)
        self.assertNotIn("주요 경로 5종", prompt)

    def test_does_not_duplicate_marker(self):
        once = build_candidate_prompt("기본 지시")
        twice = build_candidate_prompt(once)

        self.assertEqual(once, twice)


if __name__ == "__main__":
    unittest.main()
