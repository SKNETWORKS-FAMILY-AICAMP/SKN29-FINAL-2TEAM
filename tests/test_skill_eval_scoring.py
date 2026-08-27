"""§8.12 "점수와 통과 기준" — `evaluate()`."""

from django.test import SimpleTestCase

from services.agent_runtime.skills.evaluation.harness import BehaviorRunResult, CaseRunResult
from services.agent_runtime.skills.evaluation.scoring import evaluate


def _routing(case_id, activated, *, attempt=1, error=None):
    return CaseRunResult(case_id=case_id, attempt=attempt, activated_candidate=activated, called_tool_refs=[], error=error)


class EvaluateTests(SimpleTestCase):
    def _polarity(self, positive_ids, negative_ids):
        return {**{i: "positive" for i in positive_ids}, **{i: "negative" for i in negative_ids}}

    def test_전부_기준을_넘으면_통과한다(self):
        polarity = self._polarity(["p1", "p2"], ["n1", "n2"])
        routing = [
            *[_routing("p1", True, attempt=a) for a in (1, 2, 3)],
            *[_routing("p2", True, attempt=a) for a in (1, 2, 3)],
            *[_routing("n1", False, attempt=a) for a in (1, 2, 3)],
            *[_routing("n2", False, attempt=a) for a in (1, 2, 3)],
        ]
        result = evaluate(routing_results=routing, behavior_results=[], case_polarity=polarity)
        self.assertTrue(result.passed)
        self.assertEqual(result.routing.recall, 1.0)
        self.assertEqual(result.routing.false_activation_rate, 0.0)

    def test_재현율이_기준_미달이면_실패한다(self):
        """정본 §8.12의 정확한 예시 — 실제로 겪은 시나리오(2026-08-26): 설명과
        거의 같은 질문인데도 후보 스킬을 한 번도 안 읽었다."""

        polarity = self._polarity(["p1"], ["n1"])
        routing = [
            *[_routing("p1", False, attempt=a) for a in (1, 2, 3)],  # 한 번도 안 켜짐
            *[_routing("n1", False, attempt=a) for a in (1, 2, 3)],
        ]
        result = evaluate(routing_results=routing, behavior_results=[], case_polarity=polarity)
        self.assertFalse(result.passed)
        self.assertEqual(result.routing.recall, 0.0)
        self.assertTrue(any("재현율" in r for r in result.reasons))

    def test_오발동률이_기준_초과면_실패한다(self):
        polarity = self._polarity(["p1"], ["n1"])
        routing = [
            *[_routing("p1", True, attempt=a) for a in (1, 2, 3)],
            *[_routing("n1", True, attempt=a) for a in (1, 2, 3)],  # 항상 잘못 켜짐
        ]
        result = evaluate(routing_results=routing, behavior_results=[], case_polarity=polarity)
        self.assertFalse(result.passed)
        self.assertGreater(result.routing.false_activation_rate, 0.20)

    def test_질문별_세번중_두번의_결과로_라우팅을_채점한다(self):
        polarity = self._polarity(["p1"], ["n1"])
        routing = [
            _routing("p1", True, attempt=1),
            _routing("p1", True, attempt=2),
            _routing("p1", False, attempt=3),
            _routing("n1", False, attempt=1),
            _routing("n1", False, attempt=2),
            _routing("n1", True, attempt=3),
        ]

        result = evaluate(routing_results=routing, behavior_results=[], case_polarity=polarity)

        self.assertTrue(result.passed)
        self.assertEqual(result.routing.positive_total, 1)
        self.assertEqual(result.routing.positive_valid, 1)
        self.assertEqual(result.routing.negative_total, 1)
        self.assertEqual(result.routing.negative_valid, 1)
        self.assertEqual(result.routing.recall, 1.0)
        self.assertEqual(result.routing.false_activation_rate, 0.0)

    def test_유효_실행_비율이_낮으면_인프라_오류로_구분한다(self):
        """§8.12 "인프라 오류로 유효 실행 수가 polarity별 80% 미만이면
        EVAL_INFRA_ERROR로 실패하고 품질 점수는 확정하지 않는다"."""

        polarity = self._polarity(["p1"], ["n1"])
        routing = [
            _routing("p1", True, attempt=1),
            _routing("p1", None, attempt=2, error="TimeoutError"),
            _routing("p1", None, attempt=3, error="TimeoutError"),
            *[_routing("n1", False, attempt=a) for a in (1, 2, 3)],
        ]
        result = evaluate(routing_results=routing, behavior_results=[], case_polarity=polarity)
        self.assertTrue(result.infra_error)
        self.assertFalse(result.passed)

    def test_결정적_도구_실패는_행동_통과율을_깎는다(self):
        polarity = self._polarity(["p1"], ["n1"])
        routing = [
            *[_routing("p1", True, attempt=a) for a in (1, 2, 3)],
            *[_routing("n1", False, attempt=a) for a in (1, 2, 3)],
        ]
        behavior = [
            BehaviorRunResult(case_id="p1", activated_candidate=True, called_tool_refs=[], deterministic_tool_failures=["FORBIDDEN_TOOL_CALLED:x"]),
        ]
        result = evaluate(routing_results=routing, behavior_results=behavior, case_polarity=polarity)
        self.assertFalse(result.passed)
        self.assertEqual(result.behavior_pass_rate, 0.0)

    def test_행동_실행_오류는_스킬_실패가_아니라_인프라_오류다(self):
        polarity = self._polarity(["p1"], ["n1"])
        routing = [
            *[_routing("p1", True, attempt=a) for a in (1, 2, 3)],
            *[_routing("n1", False, attempt=a) for a in (1, 2, 3)],
        ]
        behavior = [
            BehaviorRunResult(
                case_id=f"p{index}",
                activated_candidate=None,
                called_tool_refs=[],
                error="Checkpointer requires thread_id",
            )
            for index in range(1, 4)
        ]

        result = evaluate(
            routing_results=routing,
            behavior_results=behavior,
            case_polarity=polarity,
        )

        self.assertTrue(result.infra_error)
        self.assertFalse(result.passed)
        self.assertTrue(any("행동 검증 실행" in reason for reason in result.reasons))

    def test_행동_결과는_대표요청이_아닌_개별_assertion_단위로_채점한다(self):
        polarity = self._polarity(["p1"], ["n1"])
        routing = [
            *[_routing("p1", True, attempt=a) for a in (1, 2, 3)],
            *[_routing("n1", False, attempt=a) for a in (1, 2, 3)],
        ]
        behavior = [
            BehaviorRunResult(
                case_id="p1",
                activated_candidate=True,
                called_tool_refs=[],
                semantic_assertion_total=3,
                semantic_assertion_passed=2,
                semantic_assertion_failures=["BEHAVIOR_ASSERTION_FAIL:2"],
            ),
            BehaviorRunResult(
                case_id="p2",
                activated_candidate=True,
                called_tool_refs=[],
                semantic_assertion_total=3,
                semantic_assertion_passed=3,
            ),
            BehaviorRunResult(
                case_id="p3",
                activated_candidate=True,
                called_tool_refs=[],
                semantic_assertion_total=3,
                semantic_assertion_passed=3,
            ),
        ]

        result = evaluate(
            routing_results=routing,
            behavior_results=behavior,
            case_polarity=polarity,
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.behavior_assertion_total, 9)
        self.assertEqual(result.behavior_assertion_passed, 8)
        self.assertAlmostEqual(result.behavior_pass_rate, 8 / 9)
