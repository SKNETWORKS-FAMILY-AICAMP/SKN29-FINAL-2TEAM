from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import LabCase


def _rows(results_root: Path):
    for path in sorted(results_root.rglob("v2_scenario_results.jsonl"), reverse=True):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                yield path, json.loads(line)


def load_recent_v2_cases(results_root: Path, limit: int = 3) -> list[LabCase]:
    """최신 정상 V2 결과를 Phoenix 요약 표시용 case로 바꾼다.

    정확한 검색 chunk와 전체 event tree는 저장돼 있지 않으므로 만들지 않는다.
    """

    if limit < 1:
        raise ValueError("limit은 1 이상이어야 합니다.")

    selected: list[LabCase] = []
    seen_scenarios: set[str] = set()
    for path, row in _rows(results_root):
        candidate: dict[str, Any] = row.get("candidate") or {}
        scenario_id = str(row.get("scenario_id") or "")
        answer = str(candidate.get("final_answer") or "")
        user_input = str(candidate.get("input") or "")
        if not scenario_id or scenario_id in seen_scenarios or not answer or not user_input:
            continue

        seen_scenarios.add(scenario_id)
        selected.append(
            LabCase(
                case_id=scenario_id,
                input=user_input,
                actual_output=answer,
                tools_called=[],
                source="V2_SUMMARY_IMPORT",
                metadata={
                    "source_file": str(path),
                    "eval_run_id": row.get("eval_run_id"),
                    "scenario_result": row.get("scenario_result"),
                    "validity": row.get("validity"),
                    "retrieved_document_ids": candidate.get("retrieved_document_ids") or [],
                    "tool_call_ids": candidate.get("tool_call_ids") or [],
                    "langfuse_trace_id": candidate.get("langfuse_trace_id"),
                    "metrics": candidate.get("metrics") or {},
                    "trace_fidelity": "SUMMARY_ONLY",
                },
            )
        )
        if len(selected) == limit:
            break
    return selected
