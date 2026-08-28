from __future__ import annotations

import ast
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import yaml
from pypdf import PdfReader

from .evaluators import (
    run_deepeval_answer_relevancy,
    run_ragas_faithfulness,
    run_ragas_id_context_metrics,
)
from .models import LabCase, MetricScore
from .telemetry import PhoenixTelemetry, score_as_json


REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = (
    REPO_ROOT / "docs" / "설계 및 구현" / "3_중간발표 이후" / "설계" / "eval"
    / "v2" / "fixtures" / "dev"
)
RESULTS_ROOT = REPO_ROOT / "outputs" / "eval-v2-results"
CORE_COMMIT = "e888d6b05729af24617509cdecd2b4d540d330aa"
EXPANSION_COMMIT = "f8f8b57f9847b594d978703b0139f44a7b4db046"
EXPECTED_COUNTS = {
    "S01-DEV-001": 3,
    "S02-DEV-001": 3,
    "S03-DEV-001": 3,
    "S04-DEV-001": 9,
    "S05A-DEV-001": 3,
    "S05B-DEV-001": 3,
    "S06-DEV-001": 3,
    "S07-DEV-001": 3,
    "S09A-DEV-001": 3,
    "S09B-DEV-001": 3,
    "S10-DEV-001": 3,
    "S10-DEV-002": 3,
    "S11-DEV-001": 3,
    "S11-DEV-002": 3,
}
RAGAS_FIXTURES = {
    "S01-DEV-001",
    "S04-DEV-001",
    "S06-DEV-001",
    "S09A-DEV-001",
    "S11-DEV-001",
}


def _required_tools(candidate: dict[str, Any]) -> list[str]:
    assertion = next(
        (item for item in candidate.get("assertions", []) if item.get("name") == "required_tools_called"),
        None,
    )
    if not assertion:
        return []
    match = re.search(r"required=(\[[^]]*])", str(assertion.get("detail") or ""))
    if not match:
        return []
    return [str(value) for value in ast.literal_eval(match.group(1))]


def _evidence_ids(candidate: dict[str, Any], key: str) -> list[str]:
    assertion = next(
        (
            item
            for item in candidate.get("assertions", [])
            if item.get("name") == "required_evidence_retrieved"
        ),
        None,
    )
    if not assertion:
        return []
    match = re.search(rf"{key}=(\[[^]]*])", str(assertion.get("detail") or ""))
    if not match:
        return []
    return [str(value) for value in ast.literal_eval(match.group(1))]


def _called_tools(candidate: dict[str, Any]) -> list[str]:
    by_tool = (candidate.get("tool_reliability") or {}).get("by_tool") or {}
    tools: list[str] = []
    for tool_ref, counts in by_tool.items():
        tools.extend([str(tool_ref)] * int(counts.get("attempted") or 0))
    return tools


def _contexts(fixture: dict[str, Any]) -> list[str]:
    contexts: list[str] = []
    for source in fixture.get("source_artifacts") or []:
        reader = PdfReader(REPO_ROOT / source["repo_path"])
        for page_number in source.get("relevant_pages") or []:
            text = (reader.pages[int(page_number) - 1].extract_text() or "").strip()
            if text:
                contexts.append(f"[{source['source_id']}:p{page_number}]\n{text}")
    return contexts


def load_frozen_cases() -> list[LabCase]:
    cases: list[LabCase] = []
    counts: Counter[str] = Counter()
    for run_dir in sorted(RESULTS_ROOT.glob("v2-*")):
        manifest_path = run_dir / "v2_run_manifest.json"
        results_path = run_dir / "v2_scenario_results.jsonl"
        if not manifest_path.is_file() or not results_path.is_file():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("candidate_id") != "AG004/AV073":
            continue
        commit = manifest.get("git_commit")
        for line in results_path.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            result = json.loads(line)
            fixture_id = str(result.get("fixture_id") or "")
            expected_commit = EXPANSION_COMMIT if fixture_id.startswith(("S10", "S11")) else CORE_COMMIT
            if fixture_id not in EXPECTED_COUNTS or commit != expected_commit:
                continue
            candidate = result.get("candidate") or {}
            answer = str(candidate.get("final_answer") or "")
            if not answer:
                continue
            fixture = yaml.safe_load(
                (FIXTURE_ROOT / fixture_id / "fixture.yaml").read_text(encoding="utf-8")
            )
            eval_run_id = str(result["eval_run_id"])
            ragas_applicable = fixture_id in RAGAS_FIXTURES
            expected_tools = _required_tools(candidate)
            retrieved_context_ids = _evidence_ids(candidate, "retrieved")
            reference_context_ids = _evidence_ids(candidate, "required")
            cases.append(
                LabCase(
                    case_id=f"AUX-{fixture_id}-{eval_run_id}",
                    input=str(candidate.get("input") or fixture["input"]),
                    actual_output=answer,
                    retrieval_context=_contexts(fixture) if ragas_applicable else [],
                    retrieved_context_ids=retrieved_context_ids,
                    reference_context_ids=reference_context_ids,
                    tools_called=_called_tools(candidate),
                    expected_tools=expected_tools,
                    source="FROZEN_V2_REPLAY",
                    metadata={
                        "fixture_id": fixture_id,
                        "eval_run_id": eval_run_id,
                        "candidate_id": manifest["candidate_id"],
                        "git_commit": commit,
                        "v2_scenario_result": result["scenario_result"],
                        "v2_reason": result.get("reason"),
                        "ragas_applicable": ragas_applicable,
                        "deepeval_applicable": bool(expected_tools),
                        "operational_metrics": candidate.get("metrics") or {},
                        "official_score_eligible": False,
                        "trace_fidelity": "FROZEN_V2_ANSWER_WITH_FIXTURE_SOURCE_PAGES",
                    },
                )
            )
            counts[fixture_id] += 1
    if dict(counts) != EXPECTED_COUNTS:
        raise RuntimeError(f"동결 cohort가 예상과 다릅니다: actual={dict(counts)}")
    return cases


def run_frozen_batch(output: Path) -> dict[str, Any]:
    telemetry = PhoenixTelemetry()
    rows: list[dict[str, Any]] = []
    for case in load_frozen_cases():
        scores = [
            MetricScore(
                evaluator="v2",
                metric="scenario_verdict",
                score=1.0 if case.metadata["v2_scenario_result"] == "PASS" else 0.0,
                passed=case.metadata["v2_scenario_result"] == "PASS",
                reason=str(case.metadata.get("v2_reason") or ""),
            )
        ]
        errors: list[dict[str, str]] = []
        if case.reference_context_ids:
            try:
                scores.extend(run_ragas_id_context_metrics(case))
            except Exception as exc:
                errors.append({"evaluator": "ragas_id", "error": type(exc).__name__})
        if case.metadata["ragas_applicable"]:
            try:
                scores.append(run_ragas_faithfulness(case))
            except Exception as exc:
                errors.append({"evaluator": "ragas", "error": type(exc).__name__})
        try:
            scores.append(run_deepeval_answer_relevancy(case))
        except Exception as exc:
            errors.append({"evaluator": "deepeval", "error": type(exc).__name__})
        with telemetry.case_span(case) as span:
            for score in scores:
                telemetry.add_score(span, score)
        telemetry.flush()
        rows.append(
            {
                "case_id": case.case_id,
                "fixture_id": case.metadata["fixture_id"],
                "eval_run_id": case.metadata["eval_run_id"],
                "scores": [score_as_json(score) for score in scores],
                "operational_metrics": case.metadata["operational_metrics"],
                "not_available": [
                    "task_completion: 전체 순서 Trace 없음",
                    "step_efficiency: 전체 순서 Trace 없음",
                    "strict_tool_correctness: 도구 인자·순서·결과 원문 없음",
                    "cost: 실행별 통화 비용 기록 없음",
                ],
                "errors": errors,
            }
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    score_counts = Counter(score["evaluator"] for row in rows for score in row["scores"])
    score_groups: dict[str, list[float]] = {}
    for row in rows:
        for score in row["scores"]:
            key = f"{score['evaluator']}.{score['metric']}"
            score_groups.setdefault(key, []).append(float(score["score"]))

    stability: dict[str, dict[str, Any]] = {}
    for fixture_id in EXPECTED_COUNTS:
        fixture_rows = [row for row in rows if row["fixture_id"] == fixture_id]
        verdicts = [
            score["passed"]
            for row in fixture_rows
            for score in row["scores"]
            if score["evaluator"] == "v2"
        ]
        pass_count = sum(value is True for value in verdicts)
        stability[fixture_id] = {
            "runs": len(verdicts),
            "pass_count": pass_count,
            "pass_rate": pass_count / len(verdicts),
            "observed_variance": len(set(verdicts)) > 1,
        }

    operation_keys = (
        "end_to_end_latency_ms",
        "active_execution_latency_ms",
        "tool_call_count",
        "model_calls",
        "failed_tool_call_count",
        "total_tokens",
    )
    operational_summary: dict[str, dict[str, float | int]] = {}
    for key in operation_keys:
        values = [
            float(row["operational_metrics"][key])
            for row in rows
            if isinstance(row["operational_metrics"].get(key), (int, float))
        ]
        if values:
            operational_summary[key] = {
                "count": len(values),
                "average": sum(values) / len(values),
                "minimum": min(values),
                "maximum": max(values),
            }

    return {
        "protocol": "OTEL_EVAL_LAB_V2",
        "run_count": len(rows),
        "score_counts": dict(sorted(score_counts.items())),
        "score_summary": {
            key: {"count": len(values), "average": sum(values) / len(values)}
            for key, values in sorted(score_groups.items())
        },
        "stability_by_fixture": stability,
        "operational_summary": operational_summary,
        "separate_suites": {
            "official_verdict": "V2 scenario PASS/FAIL + Hard Gate",
            "security": "Garak report는 import-garak으로 별도 집계",
            "unavailable_until_full_trace": [
                "DeepEval Task Completion",
                "DeepEval Step Efficiency",
                "도구명·인자·순서·결과 엄격 평가",
            ],
        },
        "error_count": sum(len(row["errors"]) for row in rows),
        "output": str(output.resolve()),
    }
