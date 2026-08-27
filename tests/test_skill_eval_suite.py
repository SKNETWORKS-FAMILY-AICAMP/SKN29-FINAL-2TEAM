"""§8.9 "최종 suite 조합" — `compose_suite()`."""

from django.test import SimpleTestCase

from services.agent_runtime.skills.evaluation.generator import GeneratedCase
from services.agent_runtime.skills.evaluation.suite import (
    NEGATIVE_TARGET,
    POSITIVE_TARGET,
    _generated_to_eval_case,
    compose_suite,
)


def _cases(n: int, *, activate: bool, prefix: str) -> list[GeneratedCase]:
    return [
        GeneratedCase(category="direct", query=f"{prefix} 질문 {i}", should_activate_candidate=activate,
                      behavior_assertions=[{"criterion": "결과가 있다"}] if activate else [], reason="r")
        for i in range(n)
    ]


class ComposeSuiteTests(SimpleTestCase):
    def test_generated_case_does_not_repeat_current_query_from_context(self):
        case = GeneratedCase(
            category="contextual",
            query="앞 문서를 번역해줘",
            context=[
                {"role": "user", "content": "문서 내용"},
                {"role": "assistant", "content": "확인했습니다."},
                {"role": "user", "content": "앞 문서를 번역해줘"},
            ],
            should_activate_candidate=True,
            behavior_assertions=[{"criterion": "번역한다"}],
            reason="문맥 요청",
        )
        converted = _generated_to_eval_case(case, index=0, polarity="positive")
        messages = [message["content"] for message in converted["messages"]]
        self.assertEqual(messages, ["문서 내용", "확인했습니다.", "앞 문서를 번역해줘"])

    def test_긍정_6_부정_6으로_구성된다(self):
        suite, _version = compose_suite(
            candidate_hash="h1", dataset_version="v1",
            positive_candidates=_cases(8, activate=True, prefix="긍정"),
            negative_candidates=_cases(8, activate=False, prefix="부정"),
            approved_regression_rows=[], platform_probes=[],
        )
        self.assertEqual(len(suite), POSITIVE_TARGET + NEGATIVE_TARGET)
        self.assertEqual(sum(1 for c in suite if c["polarity"] == "positive"), POSITIVE_TARGET)
        self.assertEqual(sum(1 for c in suite if c["polarity"] == "negative"), NEGATIVE_TARGET)

    def test_같은_입력이면_같은_결과다(self):
        pos = _cases(8, activate=True, prefix="긍정")
        neg = _cases(8, activate=False, prefix="부정")
        first, v1 = compose_suite(
            candidate_hash="h1", dataset_version="v1",
            positive_candidates=pos, negative_candidates=neg,
            approved_regression_rows=[], platform_probes=[],
        )
        second, v2 = compose_suite(
            candidate_hash="h1", dataset_version="v1",
            positive_candidates=pos, negative_candidates=neg,
            approved_regression_rows=[], platform_probes=[],
        )
        self.assertEqual([c["case_id"] for c in first], [c["case_id"] for c in second])
        self.assertEqual(v1, v2)

    def test_다른_candidate_hash면_다른_결과다(self):
        pos = _cases(8, activate=True, prefix="긍정")
        neg = _cases(8, activate=False, prefix="부정")
        _first, v1 = compose_suite(
            candidate_hash="h1", dataset_version="v1",
            positive_candidates=pos, negative_candidates=neg,
            approved_regression_rows=[], platform_probes=[],
        )
        _second, v2 = compose_suite(
            candidate_hash="h2", dataset_version="v1",
            positive_candidates=pos, negative_candidates=neg,
            approved_regression_rows=[], platform_probes=[],
        )
        self.assertNotEqual(v1, v2)

    def test_호출자의_platform_probes_리스트를_바꾸지_않는다(self):
        """2026-08-26 실측으로 잡은 버그 — 원래 코드는 `platform_probes`를 그
        자리에서 섞어서, 같은 리스트 객체를 여러 job에 재사용하면 두 번째
        호출부터 재현성이 깨졌다."""

        probes = [
            {"case_id": f"probe-{i}", "category": "c", "reason": "r", "messages": [{"role": "user", "content": f"probe {i}"}]}
            for i in range(5)
        ]
        original_order = list(probes)
        compose_suite(
            candidate_hash="h1", dataset_version="v1",
            positive_candidates=_cases(8, activate=True, prefix="긍정"),
            negative_candidates=_cases(8, activate=False, prefix="부정"),
            approved_regression_rows=[], platform_probes=probes,
        )
        self.assertEqual(probes, original_order)

    def test_후보가_부족하면_예외를_던진다(self):
        with self.assertRaises(ValueError):
            compose_suite(
                candidate_hash="h1", dataset_version="v1",
                positive_candidates=_cases(2, activate=True, prefix="긍정"),
                negative_candidates=_cases(8, activate=False, prefix="부정"),
                approved_regression_rows=[], platform_probes=[],
            )

    def test_아이디가_전부_유일하다(self):
        suite, _ = compose_suite(
            candidate_hash="h1", dataset_version="v1",
            positive_candidates=_cases(8, activate=True, prefix="긍정"),
            negative_candidates=_cases(8, activate=False, prefix="부정"),
            approved_regression_rows=[], platform_probes=[],
        )
        ids = [c["case_id"] for c in suite]
        self.assertEqual(len(ids), len(set(ids)))
