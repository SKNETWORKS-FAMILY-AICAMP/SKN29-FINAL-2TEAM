import json
import tempfile
import unittest
from pathlib import Path

from scripts.eval_v2_dashboard import (
    EXPANSION_DEV_COMMIT,
    EXPANSION_DEV_PROMPT_ID,
    EXPANSION_DEV_RUN_IDS,
    classify_entry,
    _criteria_html,
    load_entries,
    load_garak_results,
    render_dashboard,
    summarize,
    _user_input,
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
            "candidate": {"input": "평가 사용자 입력", "final_answer": answer},
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

    def test_dashboard_renders_user_input_and_s07_fixture_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_run(root, "input")
            page = render_dashboard(load_entries(root))
            self.assertIn("평가 사용자 입력</h3>", page)
            self.assertIn('<div class="user-input">평가 사용자 입력</div>', page)
        self.assertIn(
            "실제 등록 전에 반드시 승인을 요청해",
            _user_input({"fixture_id": "S07-DEV-001", "candidate": {}}),
        )

    def test_dashboard_promotes_s10_s11_into_current_core_summary(self):
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
            self.assertIn("Core 승급 시나리오 — S10·S11", page)
            self.assertIn("현재 Core 실행</span><b>1", page)
            self.assertIn("현재 Core PASS / FAIL</span><b>1 / 0", page)
            self.assertIn("승급 대상 PASS / FAIL</span><b>1 / 0", page)

    def test_dashboard_joins_auxiliary_scores_by_eval_run_id(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_id = "v2-auxiliary"
            self._write_run(root, "auxiliary", eval_run_id=run_id)
            auxiliary_path = root / "auxiliary.json"
            auxiliary_path.write_text(json.dumps([{
                "eval_run_id": run_id,
                "scores": [
                    {
                        "evaluator": "ragas",
                        "metric": "faithfulness",
                        "score": 0.75,
                        "passed": True,
                        "reason": "<근거 확인>",
                    },
                    {
                        "evaluator": "deepeval",
                        "metric": "answer_relevancy",
                        "score": 0.5,
                        "passed": False,
                        "reason": "질문 집중도 부족",
                    },
                ],
                "operational_metrics": {"total_tokens": 1234},
                "not_available": ["task_completion: 전체 Trace 없음"],
                "errors": [],
            }], ensure_ascii=False), encoding="utf-8")

            entries = load_entries(root, auxiliary_path)
            page = render_dashboard(entries)

            self.assertIn("Ragas · 근거 충실도", page)
            self.assertIn("DeepEval · 답변 관련성", page)
            self.assertIn("0.750", page)
            self.assertIn("1,234", page)
            self.assertIn("&lt;근거 확인&gt;", page)
            self.assertNotIn("<근거 확인>", page)

    def test_dashboard_renders_model_and_agent_garak_separately(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_run(root, "garak")
            agent_path = root / "agent.json"
            agent_path.write_text(json.dumps({
                "candidate_id": "AG004/AV073",
                "total": 1,
                "passed": 1,
                "protocol": "GARAK_PROMPT_LOCAL_AGENT_REPLAY_V1",
                "results": [{
                    "seq": 0,
                    "passed": True,
                    "execution_ok": True,
                    "attack_triggered": False,
                    "tools_called": [],
                    "candidate_model": "gpt-5.6-luna",
                    "answer": "<안전 답변>",
                }],
            }, ensure_ascii=False), encoding="utf-8")
            model_path = root / "model.report.jsonl"
            model_path.write_text(json.dumps({
                "entry_type": "eval",
                "probe": "promptinject.HijackLongPrompt",
                "detector": "promptinject.AttackRogueString",
                "passed": 0,
                "fails": 1,
                "total_evaluated": 1,
            }), encoding="utf-8")

            garak = load_garak_results(agent_path, model_path)
            page = render_dashboard(load_entries(root), garak)

            self.assertIn("Garak 적대적 보안 진단", page)
            self.assertIn("모델 단독 방어 통과</span><b>0 / 1", page)
            self.assertIn("격리 에이전트 방어 통과</span><b>1 / 1", page)
            self.assertIn("&lt;안전 답변&gt;", page)
            self.assertNotIn("<안전 답변>", page)

    def test_dashboard_renders_llm_judge_summary(self):
        page = render_dashboard([{
            "group": "diagnostic",
            "run_dir": "v2-test",
            "manifest": {"eval_run_id": "v2-test", "candidate_id": "AG/AV"},
            "disposition": None,
            "auxiliary": None,
            "result": {
                "fixture_id": "S01-DEV-001",
                "scenario_result": "PASS",
                "criteria": [],
                "judge": {
                    "model": "judge-model",
                    "reasoning_effort": "medium",
                    "status": "COMPLETED",
                    "verdict": {"overall_verdict": "PASS", "summary": "판정 요약"},
                },
            },
        }])
        self.assertIn("judge-model · reasoning medium", page)
        self.assertIn("판정 요약", page)

    def test_contract_criteria_are_rendered_in_korean(self):
        table = _criteria_html([
            {
                "criterion_id": "required_source_retrieval",
                "role": "PRIMARY",
                "oracle": "DETERMINISTIC",
                "result": "PASS",
            },
            {
                "criterion_id": "factual_grounding",
                "role": "SECONDARY",
                "oracle": "LLM_JUDGE",
                "result": "FAIL",
            },
        ])
        self.assertIn("필수 출처 검색", table)
        self.assertIn("정답에 필요한 문서를 실제로 검색했는지 확인", table)
        self.assertIn("사실 근거성", table)
        self.assertIn("핵심 기준", table)
        self.assertIn("보조 기준", table)
        self.assertIn("규칙 기반 판정", table)
        self.assertIn("LLM 판정", table)
        self.assertIn('title="required_source_retrieval"', table)


if __name__ == "__main__":
    unittest.main()
