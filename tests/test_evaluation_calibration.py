from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from services.evaluation.calibration import (
    append_calibration,
    build_judge_request,
    compare_verdicts,
    load_evidence_bundle,
    load_human_verdict,
    parse_judge_response,
)


def _case() -> dict:
    return {
        "id": "WF-001",
        "required_evidence_documents": ["DC001"],
        "optional_evidence_documents": ["DC002"],
        "required_facts": ["사실"],
    }


def _verdict(*, grounding: str = "PASS", safety: str = "PASS") -> dict:
    values = {
        "task_success": "PASS",
        "grounding": grounding,
        "side_effect_safety": safety,
        "repetitiveness": "PASS",
        "uncertainty": "PASS",
    }
    return {
        "overall_verdict": "PASS" if all(value == "PASS" for value in values.values()) else "FAIL",
        "dimensions": {
            name: {"verdict": value, "reason": f"{name} 사유", "evidence_refs": []}
            for name, value in values.items()
        },
        "summary": "요약",
    }


class EvaluationCalibrationTests(unittest.TestCase):
    def test_human_verdict_requires_confirmed_human_review(self):
        pending = {
            "case_id": "WF-001",
            "agent_run_id": "RUN1",
            "evaluator": "reference_pending_human_review",
            "review_status": "PENDING",
            **_verdict(),
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "pending.json"
            path.write_text(json.dumps(pending), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "사람 검수 승인"):
                load_human_verdict(path, case_id="WF-001", agent_run_id="RUN1")

    def test_human_verdict_accepts_reviewed_provenance(self):
        reviewed = {
            "case_id": "WF-001",
            "agent_run_id": "RUN1",
            "evaluator": "human",
            "review_status": "APPROVED",
            "reviewed_by": "TEAM_MEMBER_001",
            "reviewed_at": "2026-08-26T08:00:00Z",
            **_verdict(),
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "reviewed.json"
            path.write_text(json.dumps(reviewed), encoding="utf-8")
            loaded = load_human_verdict(path, case_id="WF-001", agent_run_id="RUN1")
        self.assertEqual(loaded["reviewed_by"], "TEAM_MEMBER_001")

    def test_evidence_loader_requires_required_and_optional_union(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "evidence.json"
            path.write_text(
                json.dumps(
                    {
                        "case_id": "WF-001",
                        "documents": {
                            "DC001": {
                                "status": "AVAILABLE",
                                "excerpts": [{"text": "근거"}],
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, r"missing=\['DC002'\]"):
                load_evidence_bundle(path, _case())

    def test_build_request_contains_complete_masked_evidence(self):
        evidence = {
            "DC001": {"status": "AVAILABLE", "excerpts": [{"text": "근거 1"}]},
            "DC002": {"status": "AVAILABLE", "excerpts": [{"text": "근거 2"}]},
        }
        request = build_judge_request(
            case=_case(),
            agent_run_id="RUN1",
            deterministic_assertions=[],
            final_answer="답",
            evidence_bundle=evidence,
        )
        self.assertEqual(request["evidence_scope"], ["DC001", "DC002"])
        self.assertEqual(set(request["evidence_bundle"]), {"DC001", "DC002"})
        self.assertNotIn("human_verdict", request)

    def test_parse_json_code_fence_and_compare_false_pass(self):
        human = _verdict(grounding="FAIL", safety="FAIL")
        judge = _verdict(grounding="PASS", safety="PASS")
        parsed = parse_judge_response(f"```json\n{json.dumps(judge)}\n```")
        comparison = compare_verdicts(human, parsed)
        self.assertEqual(
            comparison["false_pass_dimensions"],
            ["grounding", "side_effect_safety"],
        )
        self.assertTrue(comparison["safety_false_pass"])

    def test_calibration_file_is_append_only_for_same_evaluator(self):
        record = {
            "case_id": "WF-001",
            "agent_run_id": "RUN1",
            "judge": {"model": "judge", "prompt_version": "v0"},
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            (run_dir / "summary.json").write_text("{}", encoding="utf-8")
            output = append_calibration(run_dir, record)
            self.assertTrue(output.is_file())
            with self.assertRaisesRegex(ValueError, "이미"):
                append_calibration(run_dir, record)


if __name__ == "__main__":
    unittest.main()
