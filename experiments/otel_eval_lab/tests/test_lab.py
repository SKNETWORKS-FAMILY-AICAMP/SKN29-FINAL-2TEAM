from __future__ import annotations

import json
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

LAB_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(LAB_ROOT))

from otel_eval_lab.garak_report import summarize_garak_report
from otel_eval_lab.models import load_cases
from otel_eval_lab.v2_batch import EXPECTED_COUNTS, RAGAS_FIXTURES, load_frozen_cases
from otel_eval_lab.v2_import import load_recent_v2_cases
from garak_agent_smoke import _is_pass, _load_prompts


class LabTests(unittest.TestCase):
    def test_sample_cases_are_valid(self) -> None:
        cases = load_cases(LAB_ROOT / "sample_cases.json")
        self.assertEqual(2, len(cases))
        self.assertTrue(all(case.actual_output for case in cases))

    def test_v2_import_reads_nested_candidate_without_inventing_context(self) -> None:
        row = {
            "scenario_id": "S01-DEV-001",
            "scenario_result": "PASS",
            "validity": "VALID",
            "eval_run_id": "run-1",
            "candidate": {
                "input": "질문",
                "final_answer": "답변",
                "retrieved_document_ids": ["DOC-1"],
                "tool_call_ids": ["CALL-1"],
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run" / "v2_scenario_results.jsonl"
            path.parent.mkdir()
            path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
            cases = load_recent_v2_cases(Path(directory), limit=1)

        self.assertEqual("답변", cases[0].actual_output)
        self.assertEqual([], cases[0].retrieval_context)
        self.assertEqual("SUMMARY_ONLY", cases[0].metadata["trace_fidelity"])

    def test_garak_eval_rows_become_scores(self) -> None:
        rows = [
            {"entry_type": "attempt", "status": 2},
            {"entry_type": "eval", "probe": "promptinject.X", "detector": "D", "passed": 8, "total_evaluated": 10},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.jsonl"
            path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
            summary, scores = summarize_garak_report(path)

        self.assertEqual(2, summary["rows"])
        self.assertEqual(0.8, scores[0].score)
        self.assertFalse(scores[0].passed)

    def test_agent_garak_requires_successful_nonempty_execution(self) -> None:
        self.assertFalse(
            _is_pass(status="FAILED", answer="", attacked=False, tools_called=[])
        )
        self.assertTrue(
            _is_pass(status="SUCCESS", answer="거부했습니다.", attacked=False, tools_called=[])
        )

    def test_agent_garak_loads_only_initial_attempt_rows(self) -> None:
        prompt = {
            "entry_type": "attempt",
            "status": 1,
            "seq": 2,
            "prompt": {"turns": [{"content": {"text": "공격 입력"}}]},
            "notes": {"triggers": ["공격 문자열"]},
        }
        completed = {**prompt, "status": 2}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.jsonl"
            path.write_text(
                "\n".join(json.dumps(row, ensure_ascii=False) for row in (prompt, completed)),
                encoding="utf-8",
            )
            loaded = _load_prompts(path)

        self.assertEqual([{"seq": 2, "prompt": "공격 입력", "trigger": "공격 문자열"}], loaded)

    @unittest.skipUnless(importlib.util.find_spec("ragas"), "Ragas 전용 환경만 실행")
    def test_ragas_id_context_metrics_are_deterministic(self) -> None:
        from otel_eval_lab.evaluators import run_ragas_id_context_metrics

        case = load_cases(LAB_ROOT / "sample_cases.json")[1]
        scores = run_ragas_id_context_metrics(case)
        self.assertEqual([0.5, 1.0], [score.score for score in scores])
        self.assertTrue(all(score.passed is None for score in scores))

    def test_frozen_v2_batch_is_complete_and_excludes_sensitive_ragas_cases(self) -> None:
        cases = load_frozen_cases()

        self.assertEqual(48, len(cases))
        self.assertEqual(48, sum(EXPECTED_COUNTS.values()))
        self.assertEqual(
            RAGAS_FIXTURES,
            {case.metadata["fixture_id"] for case in cases if case.metadata["ragas_applicable"]},
        )
        self.assertFalse(
            any(
                case.metadata["ragas_applicable"]
                for case in cases
                if case.metadata["fixture_id"] in {"S05A-DEV-001", "S05B-DEV-001"}
            )
        )
        s01 = next(case for case in cases if case.metadata["fixture_id"] == "S01-DEV-001")
        self.assertTrue(s01.reference_context_ids)
        self.assertTrue(s01.retrieved_context_ids)


if __name__ == "__main__":
    unittest.main()
