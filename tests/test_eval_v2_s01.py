import unittest

from scripts.eval_v2_s01 import (
    S01_MAX_CALLS_PER_TOOL,
    S01_MAX_TOOL_CALLS,
    _judge_criteria,
    _load,
)


class EvalV2S01ContractTests(unittest.TestCase):
    def test_required_search_can_use_the_entire_total_tool_budget(self):
        self.assertEqual(S01_MAX_TOOL_CALLS, 8)
        self.assertEqual(S01_MAX_CALLS_PER_TOOL["document_search"], S01_MAX_TOOL_CALLS)

    def test_fixture_explicitly_requests_each_detailed_schedule(self):
        fixture, _gold = _load()

        self.assertEqual(fixture["fixture_version"], 2)
        self.assertIn("각각의 세부 계획 일정", fixture["input"])
        wbs = next(
            item for item in fixture["source_artifacts"]
            if item["source_id"] == "PDF-WBS"
        )
        self.assertIn(2, wbs["relevant_pages"])

    def test_grounding_rubric_includes_optional_known_facts(self):
        _fixture, gold = _load()
        criteria = {item["criterion_id"]: item for item in _judge_criteria(gold)}

        self.assertIn("선행 과업은 없고 우선순위는 중", criteria["factual_grounding"]["rubric"])
        self.assertNotIn("선행 과업은 없고 우선순위는 중", criteria["required_fact_coverage"]["rubric"])


if __name__ == "__main__":
    unittest.main()
