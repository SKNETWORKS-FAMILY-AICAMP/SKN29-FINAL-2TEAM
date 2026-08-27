"""LEGACY와 섞이지 않는 Agent Eval V2 append-only 산출물 기록기."""

from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .v2_scoring import aggregate_scenario_results


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_exclusive(path: Path, payload: dict[str, Any]) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    with path.open("x", encoding="utf-8", newline="\n", errors="strict") as destination:
        destination.write(text)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_completed_v2_run(run_dir: Path) -> dict[str, Any]:
    """완료된 V2 디렉터리를 DB 동기화 가능한 원본 묶음으로 읽는다."""

    paths = {
        "manifest": run_dir / "v2_run_manifest.json",
        "results": run_dir / "v2_scenario_results.jsonl",
        "summary": run_dir / "v2_summary.json",
        "disposition": run_dir / "v2_disposition.json",
    }
    for name in ("manifest", "results", "summary"):
        if not paths[name].is_file():
            raise RuntimeError(f"완료된 V2 실행 파일이 없습니다: {paths[name]}")

    raw = {name: path.read_bytes() for name, path in paths.items() if path.is_file()}
    manifest = json.loads(raw["manifest"])
    summary = json.loads(raw["summary"])
    result_lines = [line for line in raw["results"].splitlines() if line.strip()]
    results = [json.loads(line) for line in result_lines]
    run_id = manifest.get("eval_run_id")
    if manifest.get("protocol") != "AGENT_EVAL_V2" or not run_id:
        raise ValueError("AGENT_EVAL_V2 manifest가 아닙니다.")
    if summary.get("eval_run_id") != run_id:
        raise ValueError("V2 summary의 eval_run_id가 manifest와 다릅니다.")
    if any(item.get("eval_run_id") != run_id for item in results):
        raise ValueError("V2 scenario result의 eval_run_id가 manifest와 다릅니다.")
    if summary.get("planned") != len(manifest.get("planned_scenarios", [])):
        raise ValueError("V2 summary planned가 manifest와 다릅니다.")
    disposition = json.loads(raw["disposition"]) if "disposition" in raw else None
    if disposition and disposition.get("eval_run_id") != run_id:
        raise ValueError("V2 disposition의 eval_run_id가 manifest와 다릅니다.")
    return {
        "manifest": manifest,
        "results": results,
        "result_line_sha256": [_sha256_bytes(line) for line in result_lines],
        "summary": summary,
        "disposition": disposition,
        "hashes": {name: _sha256_bytes(value) for name, value in raw.items()},
    }


@dataclass(frozen=True)
class V2EvaluationRecorder:
    run_dir: Path
    manifest: dict[str, Any]

    @classmethod
    def start(cls, *, output_root: Path, manifest: dict[str, Any]) -> "V2EvaluationRecorder":
        required = {
            "git_commit",
            "candidate_id",
            "candidate_model",
            "runtime_profile",
            "planned_scenarios",
        }
        missing = sorted(required - manifest.keys())
        if missing:
            raise ValueError(f"V2 manifest 필수 필드가 없습니다: {missing}")
        planned = manifest["planned_scenarios"]
        if not isinstance(planned, list) or not planned or len(set(planned)) != len(planned):
            raise ValueError("planned_scenarios는 중복 없는 비어 있지 않은 목록이어야 합니다.")

        run_id = f"v2-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}"
        run_dir = output_root / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        stored = {
            **manifest,
            "protocol": "AGENT_EVAL_V2",
            "schema_version": 1,
            "eval_run_id": run_id,
            "started_at": _utc_now(),
            "official_human_verdict_enabled": False,
        }
        _write_exclusive(run_dir / "v2_run_manifest.json", stored)
        (run_dir / "v2_scenario_results.jsonl").touch(exist_ok=False)
        return cls(run_dir=run_dir, manifest=stored)

    @classmethod
    def open(cls, run_dir: Path) -> "V2EvaluationRecorder":
        manifest = json.loads((run_dir / "v2_run_manifest.json").read_text(encoding="utf-8"))
        if manifest.get("protocol") != "AGENT_EVAL_V2":
            raise ValueError("V2 manifest가 아닙니다.")
        return cls(run_dir=run_dir, manifest=manifest)

    def append_scenario(self, record: dict[str, Any]) -> None:
        if (self.run_dir / "v2_summary.json").exists():
            raise RuntimeError("종료된 V2 실행에는 결과를 추가할 수 없습니다.")
        required = {
            "scenario_id",
            "fixture_id",
            "fixture_version",
            "gold_version",
            "scoring_contract_id",
            "scenario_result",
            "criteria",
            "hard_gate_triggered",
            "validity",
        }
        missing = sorted(required - record.keys())
        if missing:
            raise ValueError(f"V2 scenario 필수 필드가 없습니다: {missing}")
        if record["scenario_id"] not in self.manifest["planned_scenarios"]:
            raise ValueError("manifest에 계획되지 않은 scenario입니다.")
        existing = self._read_results()
        if any(item["scenario_id"] == record["scenario_id"] for item in existing):
            raise ValueError("같은 V2 run에는 scenario 결과를 한 번만 기록할 수 있습니다.")

        stored = {
            **record,
            "protocol": "AGENT_EVAL_V2",
            "schema_version": 1,
            "eval_run_id": self.manifest["eval_run_id"],
            "recorded_at": _utc_now(),
        }
        serialized = json.dumps(stored, ensure_ascii=False, allow_nan=False)
        with (self.run_dir / "v2_scenario_results.jsonl").open(
            "a", encoding="utf-8", newline="\n"
        ) as destination:
            destination.write(serialized + "\n")

    def finalize(self) -> dict[str, Any]:
        summary_path = self.run_dir / "v2_summary.json"
        if summary_path.exists():
            raise FileExistsError(summary_path)
        results = self._read_results()
        summary = {
            "protocol": "AGENT_EVAL_V2",
            "schema_version": 1,
            "eval_run_id": self.manifest["eval_run_id"],
            "finished_at": _utc_now(),
            **aggregate_scenario_results(
                [item["scenario_result"] for item in results],
                planned=len(self.manifest["planned_scenarios"]),
            ),
        }
        _write_exclusive(summary_path, summary)
        return summary

    def record_disposition(self, *, status: str, reason: str) -> dict[str, Any]:
        """원시 결과를 고치지 않고 run 전체의 공식 사용 가능 여부를 덧붙인다."""

        if status not in {"VALID", "INVALID_EVALUATION_INFRA"}:
            raise ValueError("disposition status가 잘못됐습니다.")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("disposition reason이 필요합니다.")
        payload = {
            "protocol": "AGENT_EVAL_V2",
            "schema_version": 1,
            "eval_run_id": self.manifest["eval_run_id"],
            "status": status,
            "reason": reason,
            "recorded_at": _utc_now(),
        }
        _write_exclusive(self.run_dir / "v2_disposition.json", payload)
        return payload

    def _read_results(self) -> list[dict[str, Any]]:
        path = self.run_dir / "v2_scenario_results.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


__all__ = ["V2EvaluationRecorder", "read_completed_v2_run"]
