"""동결된 PLATFORM_BEHAVIOR_V3 결과를 로컬 정적 HTML로 시각화한다."""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import eval_v2_dashboard as v2_dashboard


DEFAULT_RESULTS_ROOT = REPO_ROOT / "outputs" / "eval-v3-results"
DEFAULT_OUTPUT = REPO_ROOT / "outputs" / "eval-v3-dashboard" / "index.html"
OFFICIAL_CANDIDATE = "AG004/AV073"
OFFICIAL_COMMIT = "3311f90aa3ef960818ac93c3dc768d68e1535a12"
OFFICIAL_STARTED_AFTER = "2026-08-31T02:49:00Z"
OFFICIAL_STARTED_BEFORE = "2026-08-31T03:29:00Z"
INVALID_RUN_ID = "v2-20260831T031722Z-d6fa0c86"
REPLACEMENT_RUN_ID = "v2-20260831T032810Z-425dba89"

GROUP_LABELS = {
    "core": "Core 회귀 · S10/S11 포함",
    "delta": "문서 검색 Delta",
    "invalid": "평가 인프라 무효",
}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_result(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            return json.loads(line)
    return None


def _cohort(fixture_id: str) -> str:
    if fixture_id.startswith("D"):
        return "delta"
    return "core"


def load_entries(results_root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for run_dir in sorted(results_root.glob("v2-*")):
        manifest_path = run_dir / "v2_run_manifest.json"
        summary_path = run_dir / "v2_summary.json"
        if not manifest_path.is_file() or not summary_path.is_file():
            continue
        manifest = _read_json(manifest_path)
        started_at = str(manifest.get("started_at") or "")
        if (
            manifest.get("candidate_id") != OFFICIAL_CANDIDATE
            or manifest.get("git_commit") != OFFICIAL_COMMIT
            or not (OFFICIAL_STARTED_AFTER <= started_at < OFFICIAL_STARTED_BEFORE)
        ):
            continue
        result = _read_result(run_dir / "v2_scenario_results.jsonl")
        if result is None:
            continue
        run_id = str(manifest.get("eval_run_id") or run_dir.name)
        fixture_id = str(result.get("fixture_id") or "UNKNOWN")
        group = "invalid" if run_id == INVALID_RUN_ID else _cohort(fixture_id)
        entries.append(
            {
                "run_dir": run_dir.name,
                "manifest": manifest,
                "result": result,
                "group": group,
                "is_replacement": run_id == REPLACEMENT_RUN_ID,
            }
        )
    entries.sort(key=lambda item: item["manifest"].get("started_at") or "")
    return entries


def scored_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [entry for entry in entries if entry["group"] != "invalid"]


def summarize(entries: list[dict[str, Any]]) -> dict[str, Any]:
    scored = scored_entries(entries)
    results = Counter(entry["result"].get("scenario_result", "UNKNOWN") for entry in scored)
    cohorts: dict[str, Counter[str]] = {}
    fixtures: dict[str, Counter[str]] = {}
    assertion_failures: Counter[str] = Counter()
    tool_calls = 0
    duplicate_signatures = 0
    hard_gates = 0
    candidate_statuses: Counter[str] = Counter()
    judge_results: Counter[str] = Counter()
    latencies: list[float] = []
    tokens = 0

    for entry in scored:
        result = entry["result"]
        candidate = result.get("candidate") or {}
        metrics = candidate.get("metrics") or {}
        scenario_result = result.get("scenario_result", "UNKNOWN")
        fixture_id = result.get("fixture_id", "UNKNOWN")
        cohorts.setdefault(entry["group"], Counter())[scenario_result] += 1
        fixtures.setdefault(fixture_id, Counter())[scenario_result] += 1
        hard_gates += int(bool(result.get("hard_gate_triggered")))
        tool_calls += int(metrics.get("tool_call_count") or 0)
        duplicate_signatures += int(metrics.get("duplicate_tool_signature_count") or 0)
        tokens += int(metrics.get("total_tokens") or 0)
        if isinstance(metrics.get("end_to_end_latency_ms"), (int, float)):
            latencies.append(float(metrics["end_to_end_latency_ms"]))
        status = candidate.get("status")
        if status:
            candidate_statuses[str(status)] += 1
        judge_verdict = ((result.get("judge") or {}).get("verdict") or {}).get("overall_verdict")
        if judge_verdict:
            judge_results[str(judge_verdict)] += 1
        for assertion in candidate.get("assertions") or []:
            if assertion.get("passed") is False:
                assertion_failures[str(assertion.get("name") or "UNKNOWN")] += 1

    latencies.sort()
    p50 = 0.0
    if latencies:
        middle = len(latencies) // 2
        p50 = latencies[middle] if len(latencies) % 2 else (latencies[middle - 1] + latencies[middle]) / 2
    return {
        "physical_runs": len(entries),
        "scored_runs": len(scored),
        "invalid_runs": len(entries) - len(scored),
        "results": results,
        "cohorts": cohorts,
        "fixtures": fixtures,
        "assertion_failures": assertion_failures,
        "tool_calls": tool_calls,
        "duplicate_signatures": duplicate_signatures,
        "hard_gates": hard_gates,
        "candidate_statuses": candidate_statuses,
        "judge_results": judge_results,
        "latency_count": len(latencies),
        "latency_mean_ms": sum(latencies) / len(latencies) if latencies else 0.0,
        "latency_p50_ms": p50,
        "tokens": tokens,
    }


def _bar(label: str, passed: int, failed: int, total: int) -> str:
    pass_width = passed / total * 100 if total else 0
    fail_width = failed / total * 100 if total else 0
    return (
        '<div class="cohort-row">'
        f'<div><b>{v2_dashboard._e(label)}</b><span>{passed} PASS · {failed} FAIL · {total}회</span></div>'
        '<div class="stack">'
        f'<span class="stack-pass" style="width:{pass_width:.2f}%"></span>'
        f'<span class="stack-fail" style="width:{fail_width:.2f}%"></span>'
        "</div></div>"
    )


def _entry_html(entry: dict[str, Any], index: int) -> str:
    manifest = entry["manifest"]
    result = entry["result"]
    candidate = result.get("candidate") or {}
    metrics = candidate.get("metrics") or {}
    fixture_id = result.get("fixture_id", "UNKNOWN")
    scenario_result = result.get("scenario_result", "UNKNOWN")
    user_input = v2_dashboard._user_input(result)
    search = " ".join(
        [fixture_id, str(manifest.get("eval_run_id") or ""), user_input, str(candidate.get("final_answer") or "")]
    ).lower()
    replacement = '<span class="pill replacement">대체 실행</span>' if entry["is_replacement"] else ""
    evidence = {
        "agent_run_id": candidate.get("agent_run_id"),
        "langfuse_trace_id": candidate.get("langfuse_trace_id"),
        "tool_call_ids": candidate.get("tool_call_ids"),
        "retrieved_document_ids": candidate.get("retrieved_document_ids"),
        "metrics": metrics,
        "security_observation": result.get("security_observation"),
    }
    evidence = {key: value for key, value in evidence.items() if value not in (None, [], {})}
    return f"""
    <article class="run-card" data-group="{entry['group']}" data-result="{str(scenario_result).lower()}"
      data-scenario="{v2_dashboard._e(fixture_id)}" data-search="{v2_dashboard._e(search)}">
      <details id="run-{index}"><summary>
        <span class="pill group-{entry['group']}">{GROUP_LABELS[entry['group']]}</span>
        <b>{v2_dashboard._e(fixture_id)}</b>
        <span class="pill {v2_dashboard._result_class(str(scenario_result))}">{v2_dashboard._e(scenario_result)}</span>
        {replacement}<span class="summary-meta">{v2_dashboard._e(manifest.get('eval_run_id'))}</span>
      </summary><div class="run-body">
        <div class="meta-grid">
          <div><span>시작 시각</span><b>{v2_dashboard._e(manifest.get('started_at'))}</b></div>
          <div><span>Candidate 상태</span><b>{v2_dashboard._e(candidate.get('status') or 'S07 전용 상태')}</b></div>
          <div><span>도구 호출</span><b>{v2_dashboard._e(metrics.get('tool_call_count', 0))}</b></div>
          <div><span>총 토큰</span><b>{int(metrics.get('total_tokens') or 0):,}</b></div>
        </div>
        <section><h3>평가 사용자 입력</h3><div class="user-input">{v2_dashboard._e(user_input)}</div></section>
        <section><h3>실제 에이전트 답변</h3><div class="answer">{v2_dashboard._e(candidate.get('final_answer') or '전용 runner 결과')}</div></section>
        <section><h3>결정론적·계약 판정</h3>{v2_dashboard._criteria_html(result.get('criteria') or [])}</section>
        <section><h3>LLM as Judge</h3>{v2_dashboard._judge_html(result.get('judge'))}</section>
        <section><h3>실행 증거</h3><pre>{v2_dashboard._json(evidence)}</pre></section>
        <details class="raw"><summary>원시 manifest와 scenario result</summary><pre>{v2_dashboard._json({'manifest': manifest, 'result': result})}</pre></details>
      </div></details>
    </article>"""


def render_dashboard(entries: list[dict[str, Any]]) -> str:
    summary = summarize(entries)
    results = summary["results"]
    total = summary["scored_runs"]
    pass_rate = results["PASS"] / total * 100 if total else 0
    tool_boundary_violations = summary["assertion_failures"]["only_allowed_tools_called"]
    cohort_rows = []
    for key in ("core", "delta"):
        counts = summary["cohorts"].get(key, Counter())
        cohort_rows.append(_bar(GROUP_LABELS[key], counts["PASS"], counts["FAIL"], sum(counts.values())))
    fixture_cards = []
    for fixture_id, counts in sorted(summary["fixtures"].items()):
        fixture_cards.append(
            '<div class="scenario"><b>' + v2_dashboard._e(fixture_id) + '</b>'
            f'<span>{counts["PASS"]} PASS · {counts["FAIL"]} FAIL</span></div>'
        )
    assertion_rows = "".join(
        f'<tr><td class="mono">{v2_dashboard._e(name)}</td><td><b>{count}/66</b></td></tr>'
        for name, count in summary["assertion_failures"].most_common()
    )
    scenario_options = "".join(
        f'<option value="{v2_dashboard._e(value)}">{v2_dashboard._e(value)}</option>'
        for value in sorted(summary["fixtures"])
    )
    entry_html = "".join(_entry_html(entry, index) for index, entry in enumerate(reversed(entries)))
    extra_css = r"""
.group-core{background:var(--blue-bg);color:var(--blue)}.group-expansion{background:var(--good-bg);color:var(--good)}
.group-delta{background:var(--warn-bg);color:var(--warn)}.replacement{background:#eee7fb;color:#67459a}
.cohort-panel{background:var(--paper);border:1px solid var(--line);border-radius:10px;padding:20px;margin-bottom:24px;box-shadow:var(--shadow)}
.cohort-row{display:grid;grid-template-columns:260px 1fr;align-items:center;gap:18px;margin:12px 0}.cohort-row b,.cohort-row span{display:block}.cohort-row div>span{font-size:12px;color:var(--muted)}
.stack{height:16px;display:flex!important;background:#ececea;border-radius:999px;overflow:hidden}.stack-pass{background:var(--good)}.stack-fail{background:var(--bad)}
.split{display:grid;grid-template-columns:2fr 1fr;gap:12px}.callout{background:var(--warn-bg);color:var(--warn);padding:16px 18px;border-radius:9px;margin:12px 0 24px}
@media(max-width:900px){.cohort-row,.split{grid-template-columns:1fr}}
"""
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Platform Behavior V3 대시보드</title>
<style>{v2_dashboard.CSS}{extra_css}</style></head><body><main class="wrap">
<header class="hero"><div><span class="eyebrow">PLATFORM BEHAVIOR V3 · FROZEN REPORT</span>
<h1>에이전트 플랫폼 동작 평가 대시보드</h1><p>공식 66회와 인프라 무효 대체 이력을 분리한 로컬 읽기 전용 화면</p></div>
<span class="gate">AG004/AV073 · 3311f90</span></header>
<div class="cards">
  <div class="metric"><span>최종 유효 실행</span><b>{total}</b><small>물리 실행 {summary['physical_runs']}회</small></div>
  <div class="metric"><span>Scenario PASS / FAIL</span><b>{results['PASS']} / {results['FAIL']}</b></div>
  <div class="metric"><span>Strict 통과율</span><b>{pass_rate:.1f}%</b></div>
  <div class="metric"><span>계약상 Hard Gate</span><b>{summary['hard_gates']}</b><small>도구 경계 위반 {tool_boundary_violations}건 별도</small></div>
  <div class="metric"><span>중복 signature</span><b>{summary['duplicate_signatures']}</b></div>
</div>
<div class="cohort-panel"><h2>코호트별 결과</h2>{''.join(cohort_rows)}</div>
<div class="cards">
  <div class="metric"><span>기록된 도구 호출</span><b>{summary['tool_calls']}</b></div>
  <div class="metric"><span>Candidate SUCCESS / FAILED</span><b>{summary['candidate_statuses']['SUCCESS']} / {summary['candidate_statuses']['FAILED']}</b><small>S07 전용 상태 3회 제외</small></div>
  <div class="metric"><span>Judge PASS / FAIL</span><b>{summary['judge_results']['PASS']} / {summary['judge_results']['FAIL']}</b></div>
  <div class="metric"><span>평균 / 중앙 응답시간</span><b>{summary['latency_mean_ms']/1000:.1f}s / {summary['latency_p50_ms']/1000:.1f}s</b><small>{summary['latency_count']}회 측정</small></div>
  <div class="metric"><span>총 토큰</span><b>{summary['tokens']:,}</b></div>
</div>
<div class="callout"><b>Core 승급 기준</b> S10·S11 12회는 핵심 기능으로 판단해 현재 Core에 포함합니다. 원본 orchestration의 Expansion 이력은 유지합니다. 이 12/12 PASS는 안전성 Primary 통과이며 운영 품질 전체 통과를 뜻하지 않습니다. Delta 0/18은 필수 문서 회수 실패가 아니라 사실 복원과 호출 예산 문제입니다.</div>
<h2 class="section-title">V2 비교 가능성과 Hard Gate 해석</h2>
<div class="decision">
  <div><b>V2 ↔ V3 실행조건: 부분 확인</b><p>V2 manifest에는 Candidate reasoning과 max_iterations snapshot이 없어, V3 freeze 값(reasoning low, max_iterations 6)과 동일했는지는 간접 근거로만 판단할 수 있습니다. 같은 불변 AV073이라는 점은 동일 설정이었다는 강한 근거지만, iteration 숫자는 V2 실행 artifact만으로 독립 검증할 수 없습니다. S09A·S06 변화의 원인을 제품 회귀로 단정하지 않습니다.</p></div>
  <div><b>Hard Gate 0/66은 계약 판정</b><p>공식 S10-DEV-002 3회에서 허용 목록 밖 builtin ls 호출이 있었지만 S10 계약상 Hard Gate로 승격되지 않아 Scenario PASS였습니다. 따라서 Hard Gate 0건과 도구 경계 위반 3건을 함께 보고합니다. 공식 전 D01 smoke의 Hard Gate 1건은 점수에서 제외되지만 감사 이력에는 유지됩니다.</p></div>
</div>
<div class="split"><div><h2 class="section-title">시나리오별 결과</h2><div class="scenario-grid">{''.join(fixture_cards)}</div></div>
<div><h2 class="section-title">실패 assertion</h2><div class="table-wrap"><table><thead><tr><th>Assertion</th><th>실패 실행</th></tr></thead><tbody>{assertion_rows}</tbody></table></div></div></div>
<div class="filters">
  <input data-filter="search" placeholder="시나리오·run ID·사용자 입력·답변 검색">
  <select data-filter="group"><option value="">모든 코호트</option><option value="core">Core · S10/S11 포함</option><option value="delta">Delta</option><option value="invalid">인프라 무효</option></select>
  <select data-filter="result"><option value="">모든 결과</option><option value="pass">PASS</option><option value="fail">FAIL</option></select>
  <select data-filter="scenario"><option value="">모든 시나리오</option>{scenario_options}</select>
</div><p class="shown" id="shown-count"></p><div id="runs">{entry_html}</div>
</main><script>{v2_dashboard.JS}</script></body></html>"""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=DEFAULT_RESULTS_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--open", action="store_true", help="생성 후 기본 브라우저로 연다.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    entries = load_entries(args.results_root)
    summary = summarize(entries)
    if summary["physical_runs"] != 67 or summary["scored_runs"] != 66:
        raise RuntimeError(
            f"동결 집합 불일치: physical={summary['physical_runs']}, scored={summary['scored_runs']}"
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_dashboard(entries), encoding="utf-8")
    print(
        f"생성 완료: {args.output.resolve()}\n"
        f"유효 {summary['scored_runs']}회 · PASS {summary['results']['PASS']} · "
        f"FAIL {summary['results']['FAIL']} · 무효 {summary['invalid_runs']}회"
    )
    if args.open:
        webbrowser.open(args.output.resolve().as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
