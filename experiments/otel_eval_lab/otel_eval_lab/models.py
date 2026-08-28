from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LabCase:
    case_id: str
    input: str
    actual_output: str
    retrieval_context: list[str] = field(default_factory=list)
    retrieved_context_ids: list[str] = field(default_factory=list)
    reference_context_ids: list[str] = field(default_factory=list)
    expected_output: str | None = None
    tools_called: list[str] = field(default_factory=list)
    expected_tools: list[str] = field(default_factory=list)
    source: str = "UNKNOWN"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MetricScore:
    evaluator: str
    metric: str
    score: float
    passed: bool | None = None
    reason: str | None = None


def load_cases(path: Path) -> list[LabCase]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("case 파일의 최상위 값은 배열이어야 합니다.")

    cases: list[LabCase] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"case[{index}]는 객체여야 합니다.")
        for required in ("case_id", "input", "actual_output"):
            if not str(item.get(required) or "").strip():
                raise ValueError(f"case[{index}]에 {required}가 없습니다.")
        cases.append(
            LabCase(
                case_id=str(item["case_id"]),
                input=str(item["input"]),
                actual_output=str(item["actual_output"]),
                retrieval_context=[str(value) for value in item.get("retrieval_context", [])],
                retrieved_context_ids=[
                    str(value) for value in item.get("retrieved_context_ids", [])
                ],
                reference_context_ids=[
                    str(value) for value in item.get("reference_context_ids", [])
                ],
                expected_output=item.get("expected_output"),
                tools_called=[str(value) for value in item.get("tools_called", [])],
                expected_tools=[str(value) for value in item.get("expected_tools", [])],
                source=str(item.get("source") or "UNKNOWN"),
                metadata=dict(item.get("metadata") or {}),
            )
        )
    return cases
