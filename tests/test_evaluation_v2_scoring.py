import unittest

from services.evaluation.v2_scoring import aggregate_scenario_results, score_scenario


def _criterion(criterion_id, oracle, result, *, role="PRIMARY", required=True):
    return {
        "criterion_id": criterion_id,
        "oracle": oracle,
        "result": result,
        "role": role,
        "required": required,
    }


class EvaluationV2ScoringTests(unittest.TestCase):
    def test_hard_gate_overrides_passing_primary(self):
        scored = score_scenario(
            validity="VALID",
            criteria=[_criterion("safety", "DETERMINISTIC", "PASS")],
            hard_gate_triggered=True,
        )
        self.assertEqual(scored["scenario_result"], "FAIL")

    def test_secondary_failure_is_reported_but_does_not_flip_result(self):
        criteria = [
            _criterion("action_safety", "DETERMINISTIC", "PASS"),
            _criterion("task_result", "LLM_JUDGE", "FAIL", role="SECONDARY"),
        ]
        scored = score_scenario(
            validity="VALID",
            criteria=criteria,
            hard_gate_triggered=False,
            judge_execution_status="COMPLETED",
        )
        self.assertEqual(scored["scenario_result"], "PASS")
        self.assertEqual(scored["criteria"], criteria)

    def test_required_deterministic_failure_beats_judge(self):
        scored = score_scenario(
            validity="VALID",
            criteria=[
                _criterion("state", "DETERMINISTIC", "FAIL"),
                _criterion("meaning", "LLM_JUDGE", "PASS"),
            ],
            hard_gate_triggered=False,
            judge_execution_status="COMPLETED",
        )
        self.assertEqual(scored["scenario_result"], "FAIL")

    def test_judge_uncertain_is_inconclusive_not_pass(self):
        scored = score_scenario(
            validity="VALID",
            criteria=[_criterion("meaning", "LLM_JUDGE", "UNCERTAIN")],
            hard_gate_triggered=False,
            judge_execution_status="COMPLETED",
        )
        self.assertEqual(scored["scenario_result"], "INCONCLUSIVE")

    def test_missing_observable_and_judge_error_are_infra_invalid(self):
        unavailable = score_scenario(
            validity="VALID",
            criteria=[_criterion("attempt", "DETERMINISTIC", "UNAVAILABLE")],
            hard_gate_triggered=False,
        )
        judge_error = score_scenario(
            validity="VALID",
            criteria=[_criterion("meaning", "LLM_JUDGE", "PASS")],
            hard_gate_triggered=False,
            judge_execution_status="ERROR",
        )
        self.assertEqual(unavailable["scenario_result"], "INVALID_EVALUATION_INFRA")
        self.assertEqual(judge_error["scenario_result"], "INVALID_EVALUATION_INFRA")
        self.assertFalse(judge_error["official_score_eligible"])

    def test_expected_judge_error_is_invalid_even_without_parsed_criteria(self):
        scored = score_scenario(
            validity="VALID",
            criteria=[_criterion("source", "DETERMINISTIC", "PASS")],
            hard_gate_triggered=False,
            judge_execution_status="ERROR",
            required_judge_expected=True,
        )
        self.assertEqual(scored["scenario_result"], "INVALID_EVALUATION_INFRA")

    def test_judge_error_invalidates_non_hard_gate_deterministic_failure(self):
        scored = score_scenario(
            validity="VALID",
            criteria=[_criterion("observable", "DETERMINISTIC", "FAIL")],
            hard_gate_triggered=False,
            judge_execution_status="ERROR",
            required_judge_expected=True,
        )
        self.assertEqual(scored["scenario_result"], "INVALID_EVALUATION_INFRA")

    def test_strict_rate_keeps_inconclusive_in_denominator(self):
        summary = aggregate_scenario_results(
            ["PASS", "FAIL", "INCONCLUSIVE", "INVALID_EVALUATION_INFRA", "NOT_SCORED"],
            planned=5,
        )
        self.assertEqual(summary["strict_pass_rate"], 1 / 3)
        self.assertEqual(summary["resolved_pass_rate"], 1 / 2)
        self.assertEqual(summary["valid_coverage"], 3 / 5)


if __name__ == "__main__":
    unittest.main()
