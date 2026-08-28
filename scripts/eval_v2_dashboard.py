"""저장된 Agent Eval V2 결과를 로컬 정적 HTML 대시보드로 만든다.

제품 프론트엔드나 DB를 사용하지 않는다. ``outputs/eval-v2-results``의 append-only
원본만 읽으며, 공식 Core cohort와 진단용·평가 인프라 무효 실행을 섞지 않는다.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
import webbrowser
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.eval_v2_portfolio import (
    CORE_DEV_COHORT,
    DEFAULT_CANDIDATE,
    DEFAULT_GIT_COMMIT,
)


DEFAULT_RESULTS_ROOT = REPO_ROOT / "outputs" / "eval-v2-results"
DEFAULT_OUTPUT = REPO_ROOT / "outputs" / "eval-v2-dashboard" / "index.html"
CURRENT_CANDIDATE = DEFAULT_CANDIDATE

GROUP_LABELS = {
    "official": "공식 Core DEV",
    "expansion": "S10·S11 Expansion DEV",
    "diagnostic": "진단·실험용",
    "invalid": "평가 인프라 무효",
}
EXPANSION_DEV_COMMIT = "f8f8b57f9847b594d978703b0139f44a7b4db046"
EXPANSION_DEV_PROMPT_ID = "eval-v2-judge-v3"
EXPANSION_DEV_COHORT = {
    "S10-DEV-001": {"fixture_version": 1, "gold_version": 1, "planned": 3},
    "S10-DEV-002": {"fixture_version": 1, "gold_version": 1, "planned": 3},
    "S11-DEV-001": {"fixture_version": 1, "gold_version": 2, "planned": 3},
    "S11-DEV-002": {"fixture_version": 1, "gold_version": 2, "planned": 3},
}
EXPANSION_DEV_RUN_IDS = {
    "v2-20260828T031234Z-20542f88",
    "v2-20260828T031300Z-bf9e9bce",
    "v2-20260828T031324Z-a378b749",
    "v2-20260828T031351Z-16511da6",
    "v2-20260828T031419Z-0b36831e",
    "v2-20260828T031444Z-1069b7ac",
    "v2-20260828T031509Z-54abd71b",
    "v2-20260828T031554Z-c19c7e22",
    "v2-20260828T031642Z-50000dbd",
    "v2-20260828T031727Z-401afbbc",
    "v2-20260828T031817Z-a26cc9c3",
    "v2-20260828T031901Z-9e0af423",
}
SCENARIO_NOTES = {
    "S01-DEV-001": "현재 미해결 · 문서 전처리 고도화 후 재평가",
    "S07-DEV-001": "평가용 도구 설명 수정 유지",
}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def classify_entry(entry: dict[str, Any]) -> str:
    disposition = entry.get("disposition") or {}
    if disposition.get("status") == "INVALID_EVALUATION_INFRA":
        return "invalid"

    manifest = entry["manifest"]
    result = entry.get("result") or {}
    fixture_id = result.get("fixture_id")
    specification = CORE_DEV_COHORT.get(fixture_id)
    if (
        manifest.get("candidate_id") == DEFAULT_CANDIDATE
        and manifest.get("git_commit") == DEFAULT_GIT_COMMIT
        and specification
        and result.get("fixture_version") == specification["fixture_version"]
        and result.get("validity", "VALID") == "VALID"
    ):
        return "official"
    expansion = EXPANSION_DEV_COHORT.get(fixture_id)
    if (
        manifest.get("eval_run_id") in EXPANSION_DEV_RUN_IDS
        and manifest.get("candidate_id") == DEFAULT_CANDIDATE
        and manifest.get("git_commit") == EXPANSION_DEV_COMMIT
        and manifest.get("judge_prompt_id") == EXPANSION_DEV_PROMPT_ID
        and expansion
        and result.get("fixture_version") == expansion["fixture_version"]
        and result.get("gold_version") == expansion["gold_version"]
        and result.get("validity", "VALID") == "VALID"
    ):
        return "expansion"
    return "diagnostic"


def load_entries(results_root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for run_dir in sorted(results_root.glob("v2-*")):
        manifest_path = run_dir / "v2_run_manifest.json"
        if not manifest_path.is_file():
            continue
        manifest = _read_json(manifest_path)
        disposition_path = run_dir / "v2_disposition.json"
        disposition = _read_json(disposition_path) if disposition_path.is_file() else None
        results = _read_jsonl(run_dir / "v2_scenario_results.jsonl")
        if not results:
            results = [{
                "fixture_id": (manifest.get("planned_scenarios") or ["UNKNOWN"])[0],
                "scenario_result": "NO_RESULT",
                "criteria": [],
            }]
        for result in results:
            entry = {
                "run_dir": run_dir.name,
                "manifest": manifest,
                "result": result,
                "disposition": disposition,
            }
            entry["group"] = classify_entry(entry)
            entries.append(entry)
    return entries


def summarize(entries: list[dict[str, Any]]) -> dict[str, Any]:
    groups = Counter(entry["group"] for entry in entries)
    official = [entry for entry in entries if entry["group"] == "official"]
    expansion = [entry for entry in entries if entry["group"] == "expansion"]
    results = Counter(entry["result"].get("scenario_result", "UNKNOWN") for entry in official)
    expansion_results = Counter(
        entry["result"].get("scenario_result", "UNKNOWN") for entry in expansion
    )
    by_scenario: dict[str, Counter] = {}
    for entry in official:
        fixture_id = entry["result"].get("fixture_id", "UNKNOWN")
        by_scenario.setdefault(fixture_id, Counter())[entry["result"].get("scenario_result", "UNKNOWN")] += 1
    expansion_by_scenario: dict[str, Counter] = {}
    for entry in expansion:
        fixture_id = entry["result"].get("fixture_id", "UNKNOWN")
        expansion_by_scenario.setdefault(fixture_id, Counter())[
            entry["result"].get("scenario_result", "UNKNOWN")
        ] += 1
    return {
        "groups": groups,
        "official_results": results,
        "official_by_scenario": by_scenario,
        "expansion_results": expansion_results,
        "expansion_by_scenario": expansion_by_scenario,
    }


def _e(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _json(value: Any) -> str:
    return _e(json.dumps(value, ensure_ascii=False, indent=2))


def _result_class(value: str) -> str:
    return {"PASS": "pass", "FAIL": "fail"}.get(value, "neutral")


def _criteria_html(criteria: list[dict[str, Any]]) -> str:
    if not criteria:
        return '<p class="empty">기록된 판정 항목이 없습니다.</p>'
    rows = []
    for criterion in criteria:
        result = criterion.get("result", "UNKNOWN")
        evidence = ", ".join(criterion.get("evidence_refs") or []) or "—"
        rows.append(
            "<tr>"
            f'<td class="mono">{_e(criterion.get("criterion_id"))}</td>'
            f'<td>{_e(criterion.get("role"))}</td>'
            f'<td>{_e(criterion.get("oracle"))}</td>'
            f'<td><span class="pill {_result_class(result)}">{_e(result)}</span></td>'
            f'<td>{_e(criterion.get("reason") or "—")}</td>'
            f'<td class="mono small">{_e(evidence)}</td>'
            "</tr>"
        )
    return (
        '<div class="table-wrap"><table><thead><tr><th>평가 항목</th><th>역할</th>'
        "<th>판정 방식</th><th>결과</th><th>이유</th><th>근거</th></tr></thead>"
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    )


def _judge_html(judge: dict[str, Any] | None) -> str:
    if not judge:
        return '<p class="empty">LLM Judge 결과가 없습니다.</p>'
    verdict = judge.get("verdict") or {}
    criteria = verdict.get("criteria") or {}
    criterion_rows = "".join(
        '<div class="judge-criterion">'
        f'<b>{_e(name)}</b> · <span class="pill {_result_class(item.get("verdict", ""))}">'
        f'{_e(item.get("verdict"))}</span><p>{_e(item.get("reason"))}</p>'
        f'<span class="mono small">근거: {_e(", ".join(item.get("evidence_refs") or []) or "—")}</span>'
        "</div>"
        for name, item in criteria.items()
    )
    return (
        '<div class="judge-head">'
        f'<span>{_e(judge.get("model"))} · reasoning {_e(judge.get("reasoning_effort"))}</span>'
        f'<span class="pill {_result_class(verdict.get("overall_verdict", ""))}">'
        f'{_e(verdict.get("overall_verdict") or judge.get("status"))}</span></div>'
        f'<p>{_e(verdict.get("summary") or judge.get("error") or "요약 없음")}</p>'
        f'<div class="judge-grid">{criterion_rows}</div>'
    )


def _entry_html(entry: dict[str, Any], index: int) -> str:
    manifest = entry["manifest"]
    result = entry["result"]
    disposition = entry.get("disposition") or {}
    candidate = result.get("candidate") or {}
    fixture_id = result.get("fixture_id", "UNKNOWN")
    scenario_result = result.get("scenario_result", "UNKNOWN")
    search = " ".join([
        fixture_id,
        manifest.get("candidate_id", ""),
        manifest.get("eval_run_id", ""),
        scenario_result,
        candidate.get("final_answer", ""),
    ]).lower()
    note = SCENARIO_NOTES.get(fixture_id)
    note_html = f'<p class="scenario-note">{_e(note)}</p>' if note else ""
    invalid_html = ""
    if disposition:
        invalid_html = (
            '<div class="warning"><b>무효 처리 사유</b>'
            f'<p>{_e(disposition.get("reason") or disposition.get("status"))}</p></div>'
        )
    evidence = {
        "hitl_observation": result.get("hitl_observation"),
        "retry_observation": result.get("retry_observation"),
        "retrieved_document_ids": candidate.get("retrieved_document_ids"),
        "called_stub_handlers": candidate.get("called_stub_handlers"),
        "execution_errors": candidate.get("execution_errors"),
    }
    evidence = {key: value for key, value in evidence.items() if value not in (None, [], {})}
    return f"""
    <article class="run-card" data-group="{_e(entry['group'])}" data-result="{_e(scenario_result)}"
      data-scenario="{_e(fixture_id)}" data-candidate="{_e(manifest.get('candidate_id'))}"
      data-search="{_e(search)}">
      <details id="run-{index}">
        <summary>
          <span class="pill group-{_e(entry['group'])}">{_e(GROUP_LABELS[entry['group']])}</span>
          <b>{_e(fixture_id)}</b>
          <span class="pill {_result_class(scenario_result)}">{_e(scenario_result)}</span>
          <span class="summary-meta">{_e(manifest.get('candidate_id'))} · {_e(manifest.get('started_at'))}</span>
        </summary>
        <div class="run-body">
          {note_html}{invalid_html}
          <div class="meta-grid">
            <div><span>평가 실행</span><b class="mono">{_e(manifest.get('eval_run_id'))}</b></div>
            <div><span>Git commit</span><b class="mono">{_e(manifest.get('git_commit'))}</b></div>
            <div><span>Candidate 모델</span><b>{_e(manifest.get('candidate_model'))}</b></div>
            <div><span>Fixture / Gold</span><b>v{_e(result.get('fixture_version'))} / v{_e(result.get('gold_version'))}</b></div>
          </div>
          <section><h3>실제 에이전트 답변</h3><div class="answer">{_e(candidate.get('final_answer') or '기록된 최종 답변이 없습니다.')}</div></section>
          <section><h3>결정론적·계약 판정</h3>{_criteria_html(result.get('criteria') or [])}</section>
          <section><h3>LLM as Judge</h3>{_judge_html(result.get('judge'))}</section>
          <section><h3>실행 증거</h3><pre>{_json(evidence) if evidence else '기록된 추가 증거가 없습니다.'}</pre></section>
          <details class="raw"><summary>원시 manifest와 scenario result</summary><pre>{_json({'manifest': manifest, 'result': result, 'disposition': entry.get('disposition')})}</pre></details>
        </div>
      </details>
    </article>
    """


CSS = r"""
:root{--bg:#f5f3ee;--paper:#fffdfa;--ink:#1d2529;--muted:#68747a;--line:#d9d7d0;--good:#18724a;--good-bg:#e4f3ea;--bad:#a83434;--bad-bg:#f8e5e2;--warn:#8a6420;--warn-bg:#f7edd6;--blue:#285c78;--blue-bg:#e2eef4;--shadow:0 8px 30px rgba(40,48,52,.08)}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:system-ui,-apple-system,"Noto Sans KR",sans-serif;line-height:1.55}.wrap{max-width:1380px;margin:auto;padding:36px 28px 80px}.eyebrow{font-size:12px;letter-spacing:.12em;color:var(--blue);font-weight:800}.hero{display:flex;justify-content:space-between;gap:30px;align-items:flex-end;border-bottom:1px solid var(--line);padding-bottom:24px}.hero h1{margin:5px 0 8px;font-size:34px}.hero p{margin:0;color:var(--muted)}.gate{background:var(--warn-bg);color:var(--warn);padding:11px 16px;border-radius:999px;font-weight:800;white-space:nowrap}.cards{display:grid;grid-template-columns:repeat(5,minmax(150px,1fr));gap:12px;margin:24px 0}.metric{background:var(--paper);border:1px solid var(--line);padding:18px;border-radius:10px;box-shadow:var(--shadow)}.metric span{display:block;color:var(--muted);font-size:13px}.metric b{display:block;font-size:28px;margin-top:4px}.section-title{margin:28px 0 10px}.decision{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:0 0 24px}.decision>div{padding:16px 18px;border-radius:9px;background:var(--paper);border:1px solid var(--line)}.decision b{display:block;margin-bottom:4px}.decision p{margin:0;color:var(--muted)}.scenario-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin:0 0 24px}.scenario{background:var(--paper);border:1px solid var(--line);border-radius:8px;padding:13px}.scenario b,.scenario span{display:block}.scenario span{color:var(--muted);font-size:13px;margin-top:3px}.filters{position:sticky;top:0;z-index:3;background:rgba(245,243,238,.95);backdrop-filter:blur(8px);display:grid;grid-template-columns:2fr repeat(3,1fr);gap:10px;padding:14px 0}.filters input,.filters select{width:100%;padding:11px 12px;border:1px solid var(--line);border-radius:7px;background:var(--paper);color:var(--ink)}.shown{color:var(--muted);font-size:13px;margin:4px 0 10px}.run-card{background:var(--paper);border:1px solid var(--line);border-radius:9px;margin-bottom:9px;box-shadow:0 2px 10px rgba(40,48,52,.04)}.run-card>details>summary{display:flex;align-items:center;gap:11px;cursor:pointer;padding:15px 17px;list-style:none}.run-card>details>summary::-webkit-details-marker{display:none}.summary-meta{margin-left:auto;color:var(--muted);font-size:13px}.run-body{border-top:1px solid var(--line);padding:18px}.pill{display:inline-block;padding:3px 8px;border-radius:999px;font-size:11px;font-weight:800}.pass{background:var(--good-bg);color:var(--good)}.fail{background:var(--bad-bg);color:var(--bad)}.neutral{background:#ececea;color:#596267}.group-official{background:var(--blue-bg);color:var(--blue)}.group-expansion{background:var(--good-bg);color:var(--good)}.group-diagnostic{background:var(--warn-bg);color:var(--warn)}.group-invalid{background:var(--bad-bg);color:var(--bad)}.scenario-note,.warning{padding:11px 14px;border-radius:7px;background:var(--warn-bg);color:var(--warn)}.warning{background:var(--bad-bg);color:var(--bad)}.warning p{margin:4px 0 0}.meta-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:14px 0}.meta-grid>div{background:#f4f3ef;padding:10px;border-radius:6px;min-width:0}.meta-grid span,.meta-grid b{display:block}.meta-grid span{font-size:11px;color:var(--muted)}.meta-grid b{font-size:12px;overflow-wrap:anywhere}section h3{font-size:15px;margin:22px 0 8px}.answer{white-space:pre-wrap;background:#f4f3ef;border-left:3px solid var(--blue);padding:15px;border-radius:5px}.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;font-size:12px}th,td{border-bottom:1px solid var(--line);padding:9px;text-align:left;vertical-align:top}th{color:var(--muted);font-size:11px}.judge-head{display:flex;justify-content:space-between}.judge-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}.judge-criterion{background:#f4f3ef;padding:11px;border-radius:6px}.judge-criterion p{margin:6px 0}.mono{font-family:ui-monospace,SFMono-Regular,Consolas,monospace}.small{font-size:11px}.empty{color:var(--muted)}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#20282c;color:#e9eeef;padding:14px;border-radius:7px;font-size:11px}.raw{margin-top:18px}.raw>summary{cursor:pointer;color:var(--muted)}
@media(max-width:900px){.cards,.scenario-grid{grid-template-columns:repeat(2,1fr)}.decision,.meta-grid,.judge-grid{grid-template-columns:1fr}.filters{grid-template-columns:1fr 1fr}.hero{display:block}.gate{display:inline-block;margin-top:15px}.summary-meta{display:none}}
"""


JS = r"""
const controls=[...document.querySelectorAll('[data-filter]')];
const cards=[...document.querySelectorAll('.run-card')];
function applyFilters(){
  const values=Object.fromEntries(controls.map(x=>[x.dataset.filter,x.value.toLowerCase()]));
  let shown=0;
  cards.forEach(card=>{
    const ok=(!values.group||card.dataset.group===values.group)&&
      (!values.result||card.dataset.result.toLowerCase()===values.result)&&
      (!values.scenario||card.dataset.scenario===values.scenario)&&
      (!values.search||card.dataset.search.includes(values.search));
    card.hidden=!ok;if(ok)shown++;
  });
  document.getElementById('shown-count').textContent=`${shown}건 표시 / 전체 ${cards.length}건`;
}
controls.forEach(x=>x.addEventListener(x.tagName==='INPUT'?'input':'change',applyFilters));
applyFilters();
"""


def render_dashboard(entries: list[dict[str, Any]]) -> str:
    summary = summarize(entries)
    official_results = summary["official_results"]
    official_total = sum(official_results.values())
    pass_rate = official_results["PASS"] / official_total * 100 if official_total else 0
    expansion_results = summary["expansion_results"]
    expansion_total = sum(expansion_results.values())
    expansion_pass_rate = (
        expansion_results["PASS"] / expansion_total * 100 if expansion_total else 0
    )
    scenario_cards = []
    for fixture_id, specification in CORE_DEV_COHORT.items():
        counts = summary["official_by_scenario"].get(fixture_id, Counter())
        note = SCENARIO_NOTES.get(fixture_id, "")
        scenario_cards.append(
            '<div class="scenario">'
            f'<b>{_e(fixture_id.replace("-DEV-001", ""))}</b>'
            f'<span>{counts["PASS"]} PASS · {counts["FAIL"]} FAIL · 계획 {specification["planned"]}</span>'
            f'<span>{_e(note)}</span></div>'
        )
    expansion_cards = []
    for fixture_id, specification in EXPANSION_DEV_COHORT.items():
        counts = summary["expansion_by_scenario"].get(fixture_id, Counter())
        expansion_cards.append(
            '<div class="scenario">'
            f'<b>{_e(fixture_id)}</b>'
            f'<span>{counts["PASS"]} PASS · {counts["FAIL"]} FAIL · 계획 {specification["planned"]}</span>'
            '</div>'
        )
    scenarios = sorted({entry["result"].get("fixture_id", "UNKNOWN") for entry in entries})
    scenario_options = "".join(f'<option value="{_e(value)}">{_e(value)}</option>' for value in scenarios)
    entry_html = "".join(_entry_html(entry, index) for index, entry in enumerate(reversed(entries)))
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Agent Eval V2 대시보드</title><style>{CSS}</style></head><body><main class="wrap">
  <header class="hero"><div><span class="eyebrow">AGENT EVAL V2 · LOCAL REPORT</span>
    <h1>에이전트 평가 대시보드</h1><p>공식 점수와 실험·무효 실행을 분리한 로컬 읽기 전용 화면</p></div>
    <span class="gate">STOP BEFORE PHASE 9</span></header>
  <div class="cards">
    <div class="metric"><span>공식 Core 실행</span><b>{summary['groups']['official']}</b></div>
    <div class="metric"><span>공식 PASS / FAIL</span><b>{official_results['PASS']} / {official_results['FAIL']}</b></div>
    <div class="metric"><span>공식 통과율</span><b>{pass_rate:.1f}%</b></div>
    <div class="metric"><span>진단·실험용</span><b>{summary['groups']['diagnostic']}</b></div>
    <div class="metric"><span>평가 인프라 무효</span><b>{summary['groups']['invalid']}</b></div>
  </div>
  <div class="decision"><div><b>S01 · 보류</b><p>현재 통과시키지 않음. 문서 전처리와 표 구조 검색을 고도화한 뒤 재평가합니다.</p></div>
    <div><b>S07 · 수정 유지</b><p>평가용 도구 설명을 바로잡은 상태를 유지합니다. 다음 freeze 검토 Candidate는 {CURRENT_CANDIDATE}입니다.</p></div></div>
  <h2 class="section-title">S10·S11 Expansion DEV 종합</h2>
  <div class="cards">
    <div class="metric"><span>동결 Expansion 실행</span><b>{summary['groups']['expansion']}</b></div>
    <div class="metric"><span>Expansion PASS / FAIL</span><b>{expansion_results['PASS']} / {expansion_results['FAIL']}</b></div>
    <div class="metric"><span>Expansion 통과율</span><b>{expansion_pass_rate:.1f}%</b></div>
  </div>
  <div class="scenario-grid">{"".join(expansion_cards)}</div>
  <h2 class="section-title">공식 Core DEV 시나리오</h2>
  <div class="scenario-grid">{"".join(scenario_cards)}</div>
  <div class="filters">
    <input data-filter="search" placeholder="시나리오·Candidate·답변 검색">
    <select data-filter="group"><option value="">모든 분류</option><option value="official">공식 Core DEV</option><option value="expansion">S10·S11 Expansion DEV</option><option value="diagnostic">진단·실험용</option><option value="invalid">평가 인프라 무효</option></select>
    <select data-filter="result"><option value="">모든 결과</option><option value="pass">PASS</option><option value="fail">FAIL</option><option value="no_result">결과 없음</option></select>
    <select data-filter="scenario"><option value="">모든 시나리오</option>{scenario_options}</select>
  </div>
  <p class="shown" id="shown-count"></p><div id="runs">{entry_html}</div>
</main><script>{JS}</script></body></html>"""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=DEFAULT_RESULTS_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--open", action="store_true", help="생성 후 기본 브라우저로 연다.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    entries = load_entries(args.results_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_dashboard(entries), encoding="utf-8")
    summary = summarize(entries)
    print(
        f"생성 완료: {args.output.resolve()}\n"
        f"공식 {summary['groups']['official']}건 · 진단 {summary['groups']['diagnostic']}건 · "
        f"Expansion {summary['groups']['expansion']}건 · 무효 {summary['groups']['invalid']}건"
    )
    if args.open:
        webbrowser.open(args.output.resolve().as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
