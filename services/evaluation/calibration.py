"""사람 판정과 REPORT_ONLY LLM Judge 판정을 비교해 보관한다."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .judge import (
    DIMENSIONS,
    build_judge_prompt,
    build_judge_request,
    evidence_scope,
    parse_judge_response,
    validate_judge_verdict,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_evidence_bundle(path: Path, case: dict[str, Any]) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("case_id") != case["id"]:
        raise ValueError("evidence bundle의 case_id가 평가 사례와 다릅니다.")
    documents = payload.get("documents")
    if not isinstance(documents, dict):
        raise ValueError("evidence bundle.documents는 객체여야 합니다.")

    scope = evidence_scope(case)
    missing = [doc_id for doc_id in scope if doc_id not in documents]
    extra = [doc_id for doc_id in documents if doc_id not in scope]
    if missing or extra:
        raise ValueError(f"evidence scope 불일치: missing={missing}, extra={extra}")
    for doc_id in scope:
        document = documents[doc_id]
        if not isinstance(document, dict) or document.get("status") != "AVAILABLE":
            raise ValueError(f"{doc_id} 문서를 확인할 수 없어 Judge를 실행할 수 없습니다.")
        excerpts = document.get("excerpts")
        if not isinstance(excerpts, list) or not excerpts:
            raise ValueError(f"{doc_id}.excerpts에는 하나 이상의 마스킹 근거가 필요합니다.")
        for excerpt in excerpts:
            if not isinstance(excerpt, dict) or not str(excerpt.get("text") or "").strip():
                raise ValueError(f"{doc_id}의 근거 문장 형식이 잘못됐습니다.")
    return documents


def load_human_verdict(path: Path, *, case_id: str, agent_run_id: str | None) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("case_id") != case_id:
        raise ValueError("사람 판정의 case_id가 평가 사례와 다릅니다.")
    if payload.get("agent_run_id") != agent_run_id:
        raise ValueError("사람 판정의 agent_run_id가 실행 결과와 다릅니다.")
    validate_judge_verdict(payload, label="human_verdict")
    return payload


def compare_verdicts(human: dict[str, Any], judge: dict[str, Any]) -> dict[str, Any]:
    validate_judge_verdict(human, label="human_verdict")
    validate_judge_verdict(judge, label="judge_verdict")
    agreements: dict[str, bool] = {}
    false_pass: list[str] = []
    false_fail: list[str] = []
    uncertain: list[str] = []
    for name in DIMENSIONS:
        human_value = human["dimensions"][name]["verdict"]
        judge_value = judge["dimensions"][name]["verdict"]
        agreements[name] = human_value == judge_value
        if human_value == "FAIL" and judge_value == "PASS":
            false_pass.append(name)
        if human_value == "PASS" and judge_value == "FAIL":
            false_fail.append(name)
        if judge_value == "UNCERTAIN":
            uncertain.append(name)
    agreement_count = sum(agreements.values())
    return {
        "overall_agreement": human["overall_verdict"] == judge["overall_verdict"],
        "dimension_agreement": agreements,
        "dimension_agreement_rate": agreement_count / len(DIMENSIONS),
        "false_pass_dimensions": false_pass,
        "false_fail_dimensions": false_fail,
        "safety_false_pass": "side_effect_safety" in false_pass,
        "judge_uncertain_dimensions": uncertain,
    }


def make_calibration_record(
    *,
    eval_run_id: str,
    case_result: dict[str, Any],
    evidence_bundle: dict[str, dict[str, Any]],
    human_verdict: dict[str, Any],
    judge_verdict: dict[str, Any],
    judge_model: str,
    prompt_version: str,
    latency_ms: float,
    usage: dict[str, int | None],
) -> dict[str, Any]:
    checked_documents = list(evidence_bundle)
    return {
        "schema_version": 1,
        "calibration_id": str(uuid4()),
        "created_at": _utc_now(),
        "eval_run_id": eval_run_id,
        "case_id": case_result["case_id"],
        "agent_run_id": case_result.get("agent_run_id"),
        "mode": "REPORT_ONLY",
        "evidence_scope": checked_documents,
        "checked_documents": checked_documents,
        "human_verdict": human_verdict,
        "judge": {
            "model": judge_model,
            "prompt_version": prompt_version,
            "latency_ms": round(latency_ms, 3),
            "usage": usage,
            "verdict": judge_verdict,
        },
        "comparison": compare_verdicts(human_verdict, judge_verdict),
    }


@contextmanager
def _calibration_lock(run_dir: Path):
    lock_dir = run_dir / ".judge-calibration.lock"
    try:
        lock_dir.mkdir()
    except FileExistsError as exc:
        raise RuntimeError("다른 Judge 보정 기록 작업이 진행 중입니다.") from exc
    try:
        yield
    finally:
        lock_dir.rmdir()


def append_calibration(run_dir: Path, record: dict[str, Any]) -> Path:
    """완료된 실행 옆에 보정 결과를 append-only로 기록한다."""
    if not (run_dir / "summary.json").is_file():
        raise ValueError("완료된 평가 실행에만 Judge 보정 결과를 기록할 수 있습니다.")
    output = run_dir / "judge_calibration.jsonl"
    with _calibration_lock(run_dir):
        if output.exists():
            for line in output.read_text(encoding="utf-8").splitlines():
                existing = json.loads(line)
                if (
                    existing.get("case_id") == record.get("case_id")
                    and existing.get("agent_run_id") == record.get("agent_run_id")
                    and existing.get("judge", {}).get("model")
                    == record.get("judge", {}).get("model")
                    and existing.get("judge", {}).get("prompt_version")
                    == record.get("judge", {}).get("prompt_version")
                ):
                    raise ValueError("같은 실행·Judge·프롬프트의 보정 결과가 이미 있습니다.")
        serialized = json.dumps(record, ensure_ascii=False, allow_nan=False)
        with output.open("a", encoding="utf-8", newline="\n") as file:
            file.write(serialized + "\n")
            file.flush()
            os.fsync(file.fileno())
    return output


__all__ = [
    "DIMENSIONS",
    "append_calibration",
    "build_judge_prompt",
    "build_judge_request",
    "compare_verdicts",
    "evidence_scope",
    "load_evidence_bundle",
    "load_human_verdict",
    "make_calibration_record",
    "parse_judge_response",
]
