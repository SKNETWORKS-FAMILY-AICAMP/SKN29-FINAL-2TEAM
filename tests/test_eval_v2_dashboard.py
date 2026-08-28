import json
import tempfile
import unittest
from pathlib import Path

from scripts.eval_v2_dashboard import (
    EXPANSION_DEV_COMMIT,
    EXPANSION_DEV_PROMPT_ID,
    EXPANSION_DEV_RUN_IDS,
    classify_entry,
    load_entries,
    render_dashboard,
    summarize,
)
from scripts.eval_v2_portfolio import DEFAULT_CANDIDATE, DEFAULT_GIT_COMMIT


class EvalV2DashboardTests(unittest.TestCase):
    def _write_run(
        self,
        root: Path,
        suffix: str,
        *,
        candidate: str = DEFAULT_CANDIDATE,
        git_commit: str = DEFAULT_GIT_COMMIT,
        fixture: str = "S01-DEV-001",
        version: int = 1,
        gold_version: int = 1,
        result: str = "PASS",
        invalid: bool = False,
        answer: str = "답변",
        prompt_id: str | None = None,
        eval_run_id: str | None = None,
    ) -> None:
        resolved_run_id = eval_run_id or f"v2-{suffix}"
        run = root / resolved_run_id
        run.mkdir()
        (run / "v2_run_manifest.json").write_text(json.dumps({
            "protocol": "AGENT_EVAL_V2",
            "eval_run_id": resolved_run_id,
            "candidate_id": candidate,
            "git_commit": git_commit,
            "judge_prompt_id": prompt_id,
            "planned_scenarios": [fixture],
        }), encoding="utf-8")
        (run / "v2_scenario_results.jsonl").write_text(json.dumps({
            "fixture_id": fixture,
            "fixture_version": version,
            "gold_version": gold_version,
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
            "manifest": {
                "candidate_id": DEFAULT_CANDIDATE,
                "git_commit": DEFAULT_GIT_COMMIT,
            },
            "result": {"fixture_id": "S04-DEV-001", "fixture_version": 1},
            "disposition": None,
        }
        self.assertEqual(classify_entry(entry), "diagnostic")

    def test_frozen_s10_s11_run_is_separate_expansion_group(self):
        run_id = sorted(EXPANSION_DEV_RUN_IDS)[0]
        entry = {
            "manifest": {
                "eval_run_id": run_id,
                "candidate_id": DEFAULT_CANDIDATE,
                "git_commit": EXPANSION_DEV_COMMIT,
                "judge_prompt_id": EXPANSION_DEV_PROMPT_ID,
            },
            "result": {
                "fixture_id": "S10-DEV-001",
                "fixture_version": 1,
                "gold_version": 1,
                "validity": "VALID",
            },
            "disposition": None,
        }
        self.assertEqual(classify_entry(entry), "expansion")

        entry["manifest"]["eval_run_id"] = "v2-unfrozen-rerun"
        self.assertEqual(classify_entry(entry), "diagnostic")

    def test_same_candidate_from_other_git_commit_is_diagnostic(self):
        entry = {
            "manifest": {
                "candidate_id": DEFAULT_CANDIDATE,
                "git_commit": "other-commit",
            },
            "result": {"fixture_id": "S01-DEV-001", "fixture_version": 1},
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

    def test_dashboard_renders_expansion_summary(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_run(
                root,
                "expansion",
                candidate=DEFAULT_CANDIDATE,
                git_commit=EXPANSION_DEV_COMMIT,
                fixture="S10-DEV-001",
                gold_version=1,
                prompt_id=EXPANSION_DEV_PROMPT_ID,
                eval_run_id=sorted(EXPANSION_DEV_RUN_IDS)[0],
            )
            page = render_dashboard(load_entries(root))
            self.assertIn("S10·S11 Expansion DEV 종합", page)
            self.assertIn("Expansion PASS / FAIL</span><b>1 / 0", page)


if __name__ == "__main__":
    unittest.main()
