"""Smoke 전 수동 평가 결과를 append-only 산출물로 남기는 최소 기록기."""

from __future__ import annotations

import json
import math
import os
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


_MANIFEST_FIELDS = {
    "git_commit",
    "dataset_id",
    "dataset_version",
    "targets",
    "models",
    "runtime",
    "environment",
    "repetitions",
}
_CASE_FIELDS = {
    "case_id",
    "agent_id",
    "agent_version_id",
    "model",
    "runtime",
    "started_at",
    "finished_at",
    "status",
    "assertions",
    "failure_reason",
    "agent_run_id",
    "tool_call_ids",
    "langfuse_trace_id",
    "metrics",
    "approval",
    "side_effects",
    "cleanup",
}
_NON_FAILURE_CASE_STATUSES = {"SUCCESS", "REJECTED", "NEEDS_CLARIFICATION"}
_PROGRESS_MILESTONE_STATUSES = {"COMPLETED", "FAILED", "NOT_REACHED"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_json_exclusive(path: Path, payload: dict[str, Any]) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    _write_text_atomic_exclusive(path, text)


def _write_text_atomic_exclusive(path: Path, text: str) -> None:
    if path.exists():
        raise FileExistsError(path)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8", newline="\n")
        if path.exists():
            raise FileExistsError(path)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _require_fields(payload: dict[str, Any], required: set[str], label: str) -> None:
    missing = sorted(required - payload.keys())
    if missing:
        raise ValueError(f"{label} 필수 필드가 없습니다: {', '.join(missing)}")


def _require_nonempty_string(value: Any, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field}는 비어 있지 않은 문자열이어야 합니다.")


def _validate_manifest(manifest: dict[str, Any]) -> None:
    _require_fields(manifest, _MANIFEST_FIELDS, "run_manifest")
    for field in ("git_commit", "dataset_id", "runtime", "environment"):
        _require_nonempty_string(manifest[field], field)
    if not isinstance(manifest["dataset_version"], (int, str)) or isinstance(
        manifest["dataset_version"], bool
    ):
        raise ValueError("dataset_version은 정수 또는 문자열이어야 합니다.")
    if not isinstance(manifest["repetitions"], int) or isinstance(
        manifest["repetitions"], bool
    ) or manifest["repetitions"] < 1:
        raise ValueError("repetitions는 1 이상의 정수여야 합니다.")
    targets = manifest["targets"]
    if not isinstance(targets, list) or not targets:
        raise ValueError("targets는 하나 이상의 대상 목록이어야 합니다.")
    for index, target in enumerate(targets):
        if not isinstance(target, dict):
            raise ValueError(f"targets[{index}]는 객체여야 합니다.")
        for field in ("agent_id", "agent_version_id"):
            _require_nonempty_string(target.get(field), f"targets[{index}].{field}")
    models = manifest["models"]
    if not isinstance(models, list) or not models:
        raise ValueError("models는 하나 이상의 모델 목록이어야 합니다.")
    for index, model in enumerate(models):
        _require_nonempty_string(model, f"models[{index}]")


def _validate_case_result(case_result: dict[str, Any]) -> None:
    _require_fields(case_result, _CASE_FIELDS, "case_result")
    for field in (
        "case_id",
        "agent_id",
        "agent_version_id",
        "model",
        "runtime",
        "started_at",
        "finished_at",
        "status",
    ):
        _require_nonempty_string(case_result[field], field)
    for field in ("failure_reason", "agent_run_id", "langfuse_trace_id"):
        value = case_result[field]
        if value is not None and not isinstance(value, str):
            raise ValueError(f"{field}는 문자열 또는 null이어야 합니다.")

    assertions = case_result["assertions"]
    if not isinstance(assertions, list):
        raise ValueError("assertions는 목록이어야 합니다.")
    for index, assertion in enumerate(assertions):
        if not isinstance(assertion, dict):
            raise ValueError(f"assertions[{index}]는 객체여야 합니다.")
        _require_nonempty_string(assertion.get("name"), f"assertions[{index}].name")
        if not isinstance(assertion.get("passed"), bool):
            raise ValueError(f"assertions[{index}].passed는 boolean이어야 합니다.")

    tool_call_ids = case_result["tool_call_ids"]
    if not isinstance(tool_call_ids, list) or not all(
        isinstance(item, str) for item in tool_call_ids
    ):
        raise ValueError("tool_call_ids는 문자열 목록이어야 합니다.")
    metrics = case_result["metrics"]
    if not isinstance(metrics, dict):
        raise ValueError("metrics는 객체여야 합니다.")
    for name, value in metrics.items():
        if not isinstance(name, str) or not isinstance(value, (int, float)) or isinstance(
            value, bool
        ):
            raise ValueError("metrics는 문자열 키와 숫자 값만 허용합니다.")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("metrics 값은 유한한 숫자여야 합니다.")
    approval = case_result["approval"]
    if approval is not None and not isinstance(approval, dict):
        raise ValueError("approval은 객체 또는 null이어야 합니다.")
    side_effects = case_result["side_effects"]
    if not isinstance(side_effects, list) or not all(
        isinstance(item, dict) for item in side_effects
    ):
        raise ValueError("side_effects는 객체 목록이어야 합니다.")
    cleanup = case_result["cleanup"]
    if not isinstance(cleanup, dict):
        raise ValueError("cleanup은 객체여야 합니다.")
    _require_nonempty_string(cleanup.get("status"), "cleanup.status")
    if "tool_reliability" in case_result:
        _validate_tool_reliability(case_result["tool_reliability"])
    if "progress" in case_result:
        _validate_progress(case_result["progress"])


def _validate_tool_reliability(reliability: Any) -> None:
    if not isinstance(reliability, dict):
        raise ValueError("tool_reliability는 객체여야 합니다.")
    for field in (
        "failed_call_count",
        "retry_after_failure_count",
        "recovered_after_retry_count",
        "max_consecutive_failures_per_signature",
        "max_retries_after_failure_per_signature",
        "unmatched_started_call_count",
    ):
        value = reliability.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"tool_reliability.{field}는 0 이상의 정수여야 합니다.")
    by_tool = reliability.get("by_tool")
    if not isinstance(by_tool, dict):
        raise ValueError("tool_reliability.by_tool은 객체여야 합니다.")
    for tool_ref, values in by_tool.items():
        if not isinstance(tool_ref, str) or not isinstance(values, dict):
            raise ValueError("tool_reliability.by_tool 형식이 잘못됐습니다.")
        for field in ("attempted", "failed", "retried_after_failure", "recovered"):
            value = values.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(
                    f"tool_reliability.by_tool.{tool_ref}.{field}가 잘못됐습니다."
                )


def _validate_progress(progress: Any) -> None:
    if not isinstance(progress, dict):
        raise ValueError("progress는 객체여야 합니다.")
    milestones = progress.get("milestones")
    if not isinstance(milestones, list) or not milestones:
        raise ValueError("progress.milestones는 하나 이상의 목록이어야 합니다.")
    names: set[str] = set()
    for index, milestone in enumerate(milestones):
        if not isinstance(milestone, dict):
            raise ValueError(f"progress.milestones[{index}]는 객체여야 합니다.")
        name = milestone.get("name")
        _require_nonempty_string(name, f"progress.milestones[{index}].name")
        if name in names:
            raise ValueError(f"progress.milestones[{index}].name이 중복됐습니다: {name}")
        names.add(name)
        status = milestone.get("status")
        if status not in _PROGRESS_MILESTONE_STATUSES:
            allowed = ", ".join(sorted(_PROGRESS_MILESTONE_STATUSES))
            raise ValueError(
                f"progress.milestones[{index}].status는 {allowed} 중 하나여야 합니다."
            )


def _nearest_rank(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


@contextmanager
def _writer_lock(run_dir: Path):
    lock_dir = run_dir / ".recording.lock"
    owner_path = lock_dir / "owner.json"
    try:
        lock_dir.mkdir()
    except FileExistsError as exc:
        raise RuntimeError("다른 기록 작업이 이 평가 실행을 수정 중입니다.") from exc
    try:
        _write_json_exclusive(
            owner_path,
            {"pid": os.getpid(), "acquired_at": _utc_now()},
        )
        yield
    finally:
        owner_path.unlink(missing_ok=True)
        lock_dir.rmdir()


@dataclass(frozen=True)
class EvaluationRecorder:
    """평가 실행 하나의 네 산출물을 생성한다."""

    run_dir: Path
    manifest: dict[str, Any]

    @property
    def eval_run_id(self) -> str:
        return str(self.manifest["eval_run_id"])

    @classmethod
    def start(
        cls, *, output_root: Path, manifest: dict[str, Any]
    ) -> "EvaluationRecorder":
        _validate_manifest(manifest)
        output_root.mkdir(parents=True, exist_ok=True)

        eval_run_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}"
        run_dir = output_root / eval_run_id
        run_dir.mkdir(exist_ok=False)

        stored_manifest = {
            **manifest,
            "schema_version": 1,
            "eval_run_id": eval_run_id,
            "started_at": _utc_now(),
        }
        _write_json_exclusive(run_dir / "run_manifest.json", stored_manifest)
        (run_dir / "case_results.jsonl").touch(exist_ok=False)
        return cls(run_dir=run_dir, manifest=stored_manifest)

    @classmethod
    def open(cls, run_dir: Path) -> "EvaluationRecorder":
        manifest = json.loads(
            (run_dir / "run_manifest.json").read_text(encoding="utf-8")
        )
        _require_fields(
            manifest,
            _MANIFEST_FIELDS | {"eval_run_id", "started_at", "schema_version"},
            "run_manifest",
        )
        _validate_manifest(manifest)
        return cls(run_dir=run_dir, manifest=manifest)

    def append_case(self, case_result: dict[str, Any]) -> None:
        with _writer_lock(self.run_dir):
            if (self.run_dir / "summary.json").exists() or (
                self.run_dir / "report.md"
            ).exists():
                raise RuntimeError(
                    "이미 종료 중이거나 종료된 평가 실행에는 사례를 추가할 수 없습니다."
                )
            _validate_case_result(case_result)

            inherited = {
                key: self.manifest[key]
                for key in (
                    "git_commit",
                    "dataset_id",
                    "dataset_version",
                )
            }
            stored_result = {
                **case_result,
                "schema_version": 1,
                "eval_run_id": self.eval_run_id,
                **inherited,
            }
            serialized = json.dumps(
                stored_result, ensure_ascii=False, allow_nan=False
            )
            with (self.run_dir / "case_results.jsonl").open(
                "a", encoding="utf-8", newline="\n"
            ) as file:
                file.write(serialized)
                file.write("\n")

    def finalize(self, *, status: str, limitations: list[str]) -> None:
        with _writer_lock(self.run_dir):
            _require_nonempty_string(status, "status")
            if not isinstance(limitations, list) or not all(
                isinstance(item, str) for item in limitations
            ):
                raise ValueError("limitations는 문자열 목록이어야 합니다.")
            if (self.run_dir / "summary.json").exists():
                raise FileExistsError(self.run_dir / "summary.json")
            case_results = self._read_case_results()
            status_counts = Counter(result["status"] for result in case_results)
            assertion_counts = Counter(
                "passed" if assertion.get("passed") else "failed"
                for result in case_results
                for assertion in result.get("assertions", [])
            )
            metric_totals: Counter[str] = Counter()
            latency_values: dict[str, list[float]] = {}
            for result in case_results:
                for name, value in result.get("metrics", {}).items():
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        metric_totals[name] += value
                        if name.endswith("_latency_ms") or name == "time_to_first_token_ms":
                            latency_values.setdefault(name, []).append(value)
            metric_totals["total_tokens"] = (
                metric_totals.get("input_tokens", 0)
                + metric_totals.get("output_tokens", 0)
            )
            latency_ms = {
                name: {
                    "count": len(values),
                    "p50": _nearest_rank(values, 0.50),
                    "p95": _nearest_rank(values, 0.95),
                }
                for name, values in sorted(latency_values.items())
            }
            cleanup_status_counts = Counter(
                result["cleanup"]["status"] for result in case_results
            )
            approval_decision_counts = Counter(
                result["approval"].get("decision")
                for result in case_results
                if result["approval"] is not None
                and result["approval"].get("decision") is not None
            )
            safety_violation_count = sum(
                1
                for result in case_results
                for side_effect in result["side_effects"]
                if side_effect.get("violation") is True
            )
            progress_cases = []
            progress_status_counts: Counter[str] = Counter()
            for result in case_results:
                progress = result.get("progress")
                if progress is None:
                    continue
                milestones = progress["milestones"]
                progress_status_counts.update(
                    milestone["status"] for milestone in milestones
                )
                completed = sum(
                    milestone["status"] == "COMPLETED" for milestone in milestones
                )
                total = len(milestones)
                progress_cases.append(
                    {
                        "case_id": result["case_id"],
                        "completed": completed,
                        "total": total,
                        "rate": completed / total,
                        "failed_milestones": [
                            milestone["name"]
                            for milestone in milestones
                            if milestone["status"] == "FAILED"
                        ],
                    }
                )
            progress_summary = {
                "case_count": len(progress_cases),
                "average_rate": (
                    sum(case["rate"] for case in progress_cases) / len(progress_cases)
                    if progress_cases
                    else None
                ),
                "milestone_status_counts": dict(progress_status_counts),
                "cases": progress_cases,
            }
            failed_cases = []
            for result in case_results:
                failed_assertions = [
                    assertion["name"]
                    for assertion in result["assertions"]
                    if not assertion["passed"]
                ]
                if (
                    result["status"] not in _NON_FAILURE_CASE_STATUSES
                    or result["failure_reason"]
                    or failed_assertions
                ):
                    failed_cases.append(
                        {
                            "case_id": result["case_id"],
                            "status": result["status"],
                            "failure_reason": result["failure_reason"],
                            "failed_assertions": failed_assertions,
                        }
                    )

            summary = {
                "schema_version": 1,
                "eval_run_id": self.eval_run_id,
                "run_status": status,
                "finished_at": _utc_now(),
                "case_count": len(case_results),
                "status_counts": dict(status_counts),
                "assertion_counts": dict(assertion_counts),
                "safety_violation_count": safety_violation_count,
                "cleanup_status_counts": dict(cleanup_status_counts),
                "approval_decision_counts": dict(approval_decision_counts),
                "progress": progress_summary,
                "failed_cases": failed_cases,
                "metrics": dict(metric_totals),
                "latency_ms": latency_ms,
                "limitations": limitations,
            }
            self._write_report(summary)
            _write_json_exclusive(self.run_dir / "summary.json", summary)

    def _read_case_results(self) -> list[dict[str, Any]]:
        lines = (self.run_dir / "case_results.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        return [json.loads(line) for line in lines if line.strip()]

    def _write_report(self, summary: dict[str, Any]) -> None:
        statuses = summary["status_counts"]
        status_lines = [f"- {name}: {count}" for name, count in sorted(statuses.items())]
        limitation_lines = [f"- {item}" for item in summary["limitations"]]
        metric_lines = [
            f"- {name}: {value}"
            for name, value in sorted(summary["metrics"].items())
        ]
        latency_lines = [
            f"- {name}: count={values['count']}, p50={values['p50']}, p95={values['p95']}"
            for name, values in sorted(summary["latency_ms"].items())
        ]
        approval_lines = [
            f"- {name}: {count}"
            for name, count in sorted(summary["approval_decision_counts"].items())
        ]
        cleanup_lines = [
            f"- {name}: {count}"
            for name, count in sorted(summary["cleanup_status_counts"].items())
        ]
        failed_case_lines = []
        for case in summary["failed_cases"]:
            reason = case["failure_reason"] or "명시된 실패 사유 없음"
            assertions = ", ".join(case["failed_assertions"]) or "없음"
            failed_case_lines.append(
                f"- {case['case_id']} ({case['status']}): {reason}; 실패 assertion: {assertions}"
            )
        progress = summary["progress"]
        progress_lines = []
        for case in progress["cases"]:
            failed = ", ".join(case["failed_milestones"]) or "없음"
            progress_lines.append(
                f"- {case['case_id']}: {case['completed']}/{case['total']} "
                f"({case['rate'] * 100:.1f}%); 실패 마일스톤: {failed}"
            )
        average_progress = (
            f"{progress['average_rate'] * 100:.1f}%"
            if progress["average_rate"] is not None
            else "기록 없음"
        )
        report = "\n".join(
            [
                f"# 평가 실행 {self.eval_run_id}",
                "",
                f"- 실행 상태: {summary['run_status']}",
                f"- Git commit: {self.manifest['git_commit']}",
                f"- Dataset: {self.manifest['dataset_id']} v{self.manifest['dataset_version']}",
                f"- 사례 수: {summary['case_count']}",
                "",
                "## 사례 상태",
                "",
                *(status_lines or ["- 기록된 사례 없음"]),
                "",
                "## 안전·승인·정리",
                "",
                f"- 안전 위반: {summary['safety_violation_count']}",
                "- 승인 결정:",
                *(approval_lines or ["  - 기록 없음"]),
                "- 정리 상태:",
                *(cleanup_lines or ["  - 기록 없음"]),
                "",
                "## 성능 지표 합계",
                "",
                *(metric_lines or ["- 기록 없음"]),
                "",
                "## Latency 분포 (ms)",
                "",
                *(latency_lines or ["- 기록 없음"]),
                "",
                "## 단계별 진행률",
                "",
                f"- 평균 진행률: {average_progress}",
                *(progress_lines or ["- 마일스톤 기록 없음"]),
                "",
                "## 실패 사례",
                "",
                *(failed_case_lines or ["- 없음"]),
                "",
                "## 한계",
                "",
                *(limitation_lines or ["- 없음"]),
                "",
                "## 원시 결과",
                "",
                "- `run_manifest.json`",
                "- `case_results.jsonl`",
                "- `summary.json`",
                "",
            ]
        )
        report_path = self.run_dir / "report.md"
        if report_path.exists():
            if report_path.read_text(encoding="utf-8") == report:
                return
            raise FileExistsError(report_path)
        _write_text_atomic_exclusive(report_path, report)


def read_completed_run(
    run_dir: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    """종료된 로컬 실행을 DB 동기화용으로 읽고 식별자 일관성을 확인한다."""

    recorder = EvaluationRecorder.open(run_dir)
    summary_path = run_dir / "summary.json"
    if not summary_path.is_file():
        raise RuntimeError("종료되지 않은 평가 실행은 DB에 동기화할 수 없습니다.")

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if not isinstance(summary, dict):
        raise ValueError("summary.json은 JSON 객체여야 합니다.")
    _require_fields(
        summary,
        {"eval_run_id", "run_status", "finished_at"},
        "summary",
    )
    if summary["eval_run_id"] != recorder.eval_run_id:
        raise ValueError("summary.json의 eval_run_id가 manifest와 다릅니다.")

    case_results = recorder._read_case_results()
    for index, case_result in enumerate(case_results, start=1):
        _validate_case_result(case_result)
        if case_result.get("eval_run_id") != recorder.eval_run_id:
            raise ValueError(
                f"case_results.jsonl {index}번째 eval_run_id가 manifest와 다릅니다."
            )
    return recorder.manifest, case_results, summary
