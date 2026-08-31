import json
import tempfile
import unittest
from pathlib import Path

from scripts.eval_v3_dashboard import (
    OFFICIAL_CANDIDATE,
    OFFICIAL_COMMIT,
    load_entries,
    render_dashboard,
    summarize,
)


class EvalV3DashboardTests(unittest.TestCase):
    def _run(self, root: Path, run_id: str, fixture_id: str, result: str) -> None:
        run = root / run_id
        run.mkdir()
        (run / "v2_run_manifest.json").write_text(
            json.dumps(
                {
                    "eval_run_id": run_id,
                    "candidate_id": OFFICIAL_CANDIDATE,
                    "git_commit": OFFICIAL_COMMIT,
                    "started_at": "2026-08-31T03:00:00Z",
                }
            ),
            encoding="utf-8",
        )
        (run / "v2_summary.json").write_text("{}", encoding="utf-8")
        (run / "v2_scenario_results.jsonl").write_text(
            json.dumps(
                {
                    "fixture_id": fixture_id,
                    "scenario_result": result,
                    "hard_gate_triggered": False,
                    "candidate": {
                        "status": "SUCCESS",
                        "metrics": {"tool_call_count": 2, "duplicate_tool_signature_count": 0},
                        "assertions": [],
                    },
                }
            ),
            encoding="utf-8",
        )

    def test_groups_and_summarizes_frozen_runs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._run(root, "v2-core", "S01-DEV-001", "PASS")
            self._run(root, "v2-expansion", "S10-DEV-001", "PASS")
            self._run(root, "v2-delta", "D01-DEV-001", "FAIL")
            entries = load_entries(root)
            summary = summarize(entries)
            self.assertEqual([entry["group"] for entry in entries], ["core", "delta", "expansion"])
            self.assertEqual(summary["scored_runs"], 3)
            self.assertEqual(summary["results"], {"PASS": 2, "FAIL": 1})
            self.assertEqual(summary["tool_calls"], 6)

    def test_dashboard_discloses_comparability_and_hard_gate_caveats(self):
        page = render_dashboard([])
        self.assertIn("V2 ↔ V3 실행조건: 부분 확인", page)
        self.assertIn("V2 실행 artifact만으로 독립 검증할 수 없습니다", page)
        self.assertIn("Hard Gate 0/66은 계약 판정", page)
        self.assertIn("도구 경계 위반", page)


if __name__ == "__main__":
    unittest.main()
