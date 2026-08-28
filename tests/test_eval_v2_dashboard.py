import json
import tempfile
import unittest
from pathlib import Path

from scripts.eval_v2_dashboard import classify_entry, load_entries, render_dashboard, summarize


class EvalV2DashboardTests(unittest.TestCase):
    def _write_run(
        self,
        root: Path,
        suffix: str,
        *,
        candidate: str = "AG004/AV035",
        fixture: str = "S01-DEV-001",
        version: int = 1,
        result: str = "PASS",
        invalid: bool = False,
        answer: str = "답변",
    ) -> None:
        run = root / f"v2-{suffix}"
        run.mkdir()
        (run / "v2_run_manifest.json").write_text(json.dumps({
            "protocol": "AGENT_EVAL_V2",
            "eval_run_id": f"v2-{suffix}",
            "candidate_id": candidate,
            "planned_scenarios": [fixture],
        }), encoding="utf-8")
        (run / "v2_scenario_results.jsonl").write_text(json.dumps({
            "fixture_id": fixture,
            "fixture_version": version,
            "scenario_result": result,
            "validity": "VALID",
            "criteria": [],
            "candidate": {"final_answer": answer},
        }) + "\n", encoding="utf-8")
        if invalid:
            (run / "v2_disposition.json").write_text(json.dumps({
                "status": "INVALID_EVALUATION_INFRA", "reason": "test fault",
            }), encoding="utf-8")

    def test_classifies_official_diagnostic_and_invalid_separately(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_run(root, "official")
            self._write_run(root, "diagnostic", candidate="AG004/AV071")
            self._write_run(root, "invalid", invalid=True)

            entries = load_entries(root)
            summary = summarize(entries)

            self.assertEqual(summary["groups"], {
                "official": 1, "diagnostic": 1, "invalid": 1,
            })
            self.assertEqual(summary["official_results"]["PASS"], 1)

    def test_old_fixture_version_is_diagnostic(self):
        entry = {
            "manifest": {"candidate_id": "AG004/AV035"},
            "result": {"fixture_id": "S04-DEV-001", "fixture_version": 1},
            "disposition": None,
        }
        self.assertEqual(classify_entry(entry), "diagnostic")

    def test_dashboard_escapes_agent_answer(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_run(root, "escape", answer="<script>alert(1)</script>")
            page = render_dashboard(load_entries(root))
            self.assertNotIn("<script>alert(1)</script>", page)
            self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)


if __name__ == "__main__":
    unittest.main()
