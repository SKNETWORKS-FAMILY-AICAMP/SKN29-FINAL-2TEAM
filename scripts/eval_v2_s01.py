"""S01-DEV-001을 실제 Agent와 gpt-5.6-sol Judge로 자동 평가한다."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import importlib.metadata
import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = (
    REPO_ROOT
    / "docs"
    / "설계 및 구현"
    / "3_중간발표 이후"
    / "설계"
    / "eval"
    / "v2"
    / "fixtures"
    / "dev"
    / "S01-DEV-001"
)
DEFAULT_BINDING = REPO_ROOT / "outputs" / "eval-v2-fixture-bindings" / "S01-DEV-001.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs" / "eval-v2-results"
S01_MAX_TOOL_CALLS = 8
S01_MAX_CALLS_PER_TOOL = {"document_search": 8, "document_list": 1}
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", default="UA002")
    parser.add_argument("--agent-id", default="AG004")
    parser.add_argument("--agent-version-id", default="AV035")
    parser.add_argument("--binding", type=Path, default=DEFAULT_BINDING)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--environment", default="local-dev")
    return parser


def _git_commit() -> str:
    head = (REPO_ROOT / ".git" / "HEAD").read_text(encoding="utf-8").strip()
    if head.startswith("ref: "):
        ref = REPO_ROOT / ".git" / head.removeprefix("ref: ")
        if ref.is_file():
            return ref.read_text(encoding="utf-8").strip()
    return head or "unknown"


def _load() -> tuple[dict[str, Any], dict[str, Any]]:
    fixture = yaml.safe_load((FIXTURE_DIR / "fixture.yaml").read_text(encoding="utf-8"))
    gold = yaml.safe_load((FIXTURE_DIR / "gold.yaml").read_text(encoding="utf-8"))
    return fixture, gold


def _binding(path: Path, fixture: dict[str, Any], account_id: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("fixture_id") != fixture["fixture_id"] or payload.get("account_id") != account_id:
        raise ValueError("fixture binding이 실행 대상과 다릅니다.")
    if payload.get("status") != "READY":
        raise ValueError(f"fixture binding이 READY가 아닙니다: {payload.get('status')}")
    if {item["source_id"] for item in payload["documents"]} != {
        item["source_id"] for item in fixture["source_artifacts"]
    }:
        raise ValueError("fixture source와 binding source가 다릅니다.")
    return payload


def _evidence(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    from pypdf import PdfReader

    items: list[dict[str, Any]] = []
    for source in fixture["source_artifacts"]:
        reader = PdfReader(REPO_ROOT / source["repo_path"])
        for page_number in source["relevant_pages"]:
            text = reader.pages[int(page_number) - 1].extract_text() or ""
            items.append(
                {
                    "ref": f"{source['source_id']}:p{page_number}",
                    "source_sha256": source["sha256"],
                    "excerpt": text.strip(),
                }
            )
    return items


def _judge_criteria(gold: dict[str, Any]) -> list[dict[str, str]]:
    catalog_facts = (gold.get("truth_catalog") or {}).get("facts") or []
    facts = [
        item["proposition"]
        for item in catalog_facts
        if item.get("importance") == "REQUIRED"
    ]
    known_facts = [item["proposition"] for item in catalog_facts]
    conclusions = [item["proposition"] for item in gold.get("required_conclusions") or []]
    uncertainty = gold.get("uncertainty_contract") or {}
    return [
        {
            "criterion_id": "required_fact_coverage",
            "rubric": "답변이 다음 필수 사실·결론을 의미상 빠짐없이 전달하면 PASS: "
            + json.dumps(facts + conclusions, ensure_ascii=False),
        },
        {
            "criterion_id": "factual_grounding",
            "rubric": "답변의 사실 주장이 제공된 PDF evidence와 다음 Gold 사실에 부합하면 PASS: "
            + json.dumps(known_facts, ensure_ascii=False),
        },
        {
            "criterion_id": "temporal_resolution",
            "rubric": "계획과 실제, 미정과 확정, 현재와 미래를 구분하면 PASS. "
            + json.dumps(gold.get("truth_catalog", {}).get("relations", []), ensure_ascii=False),
        },
        {
            "criterion_id": "unsupported_claim_control",
            "rubric": "다음 금지 추론을 하지 않고 확인 불가능한 내용은 유보하면 PASS: "
            + json.dumps(uncertainty, ensure_ascii=False),
        },
    ]


def _message_text(message: Any) -> str:
    text = getattr(message, "text", None)
    if isinstance(text, str) and text.strip():
        return text
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(item.get("text") or "")
            for item in content
            if isinstance(item, dict) and item.get("type") in {"text", "output_text"}
        )
    return str(content)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
    import django

    django.setup()

    from apps.accounts.permissions import account_role
    from backend.db import AccountRepository
    from backend.db.agent_platform import ChatSessionRepository
    from langchain_core.messages import HumanMessage
    from services.agent_runtime import RuntimeContext, build_default_executor
    from services.agent_runtime.loader import AgentDefinitionLoader
    from services.agent_runtime.models.factory import ModelConfigResolver, ModelFactory
    from services.evaluation.runner import run_read_only_case
    from services.evaluation.v2_judge import (
        DEFAULT_JUDGE_MODEL,
        DEFAULT_REASONING_EFFORT,
        build_judge_prompt,
        build_judge_request,
        parse_judge_response,
    )
    from services.evaluation.v2_recorder import V2EvaluationRecorder
    from services.evaluation.v2_scoring import score_scenario

    fixture, gold = _load()
    binding = _binding(args.binding, fixture, args.account_id)
    source_doc_ids = [item["doc_id"] for item in binding["documents"]]
    profile = AccountRepository.get_profile(args.account_id)
    session = ChatSessionRepository.create(
        account_id=args.account_id,
        agent_id=args.agent_id,
        proj_id=None,
        title="[EVAL V2] S01-DEV-001",
    )
    context = RuntimeContext(
        account_id=args.account_id,
        team_id=profile["team_id"],
        role=account_role(profile),
        session_id=session["session_id"],
        run_id=str(uuid4()),
    )
    loaded = AgentDefinitionLoader().load(
        agent_id=args.agent_id,
        agent_version_id=args.agent_version_id,
        context=context,
    )
    candidate_model = loaded.definition.model
    runtime = f"deepagents-{importlib.metadata.version('deepagents')}"
    recorder = V2EvaluationRecorder.start(
        output_root=args.output_root,
        manifest={
            "git_commit": _git_commit(),
            "candidate_id": f"{args.agent_id}/{args.agent_version_id}",
            "candidate_model": candidate_model,
            "runtime_profile": runtime,
            "planned_scenarios": [fixture["fixture_id"]],
            "fixture_binding": str(args.binding),
            "judge_model": DEFAULT_JUDGE_MODEL,
            "judge_reasoning_effort": DEFAULT_REASONING_EFFORT,
        },
    )
    context = dataclasses.replace(
        context,
        eval_run_id=recorder.manifest["eval_run_id"],
        eval_case_id=fixture["fixture_id"],
        environment=args.environment,
    )
    case = {
        "id": fixture["fixture_id"],
        "input": fixture["input"],
        "agent_id": args.agent_id,
        "agent_version_id": args.agent_version_id,
        "execution_mode": "read_only",
        "expected_status": "SUCCESS",
        "required_tools": ["document_search"],
        "allowed_tools": fixture["allowed_tools"],
        "forbidden_tools": fixture["forbidden_tools"],
        "max_tool_calls": S01_MAX_TOOL_CALLS,
        "max_calls_per_tool": S01_MAX_CALLS_PER_TOOL,
        "required_evidence_documents": source_doc_ids,
        "optional_evidence_documents": [],
    }

    try:
        candidate = run_read_only_case(
            case=case,
            executor=build_default_executor(),
            context=context,
            model=candidate_model,
            runtime=runtime,
        )
        candidate.pop("judge", None)  # LEGACY REPORT_ONLY 결과를 V2 공식 기록에 섞지 않는다.
        validity = "VALID" if not candidate["execution_errors"] else "EXECUTION_INFRA_ERROR"
        deterministic = [
            {
                "criterion_id": "execution_completed",
                "oracle": "DETERMINISTIC",
                "role": "PRIMARY",
                "required": True,
                "result": "PASS" if candidate["status"] == "SUCCESS" else "FAIL",
            },
            {
                "criterion_id": "required_source_retrieval",
                "oracle": "DETERMINISTIC",
                "role": "PRIMARY",
                "required": True,
                "result": (
                    "PASS"
                    if set(source_doc_ids).issubset(candidate["retrieved_document_ids"])
                    else "FAIL"
                ),
            },
            {
                "criterion_id": "no_forbidden_action",
                "oracle": "DETERMINISTIC",
                "role": "PRIMARY",
                "required": True,
                "result": "PASS" if not candidate["side_effects"] else "FAIL",
            },
        ]
        request = build_judge_request(
            scenario_id=fixture["fixture_id"],
            criteria=_judge_criteria(gold),
            user_input=fixture["input"],
            candidate_answer=candidate["final_answer"],
            evidence=_evidence(fixture),
            deterministic_assertions=candidate["assertions"],
            execution_summary={
                "retrieved_document_ids": candidate["retrieved_document_ids"],
                "required_document_ids": source_doc_ids,
                "tool_reliability": candidate["tool_reliability"],
            },
        )
        resolved = ModelConfigResolver().resolve(
            model=DEFAULT_JUDGE_MODEL,
            reasoning_effort=DEFAULT_REASONING_EFFORT,
            team_id=profile["team_id"],
        )
        judge_model = ModelFactory().create(resolved)
        judge_status = "ERROR"
        judge_payload = None
        judge_error = None
        judge_latency_ms = None
        for attempt in range(2):
            started = time.monotonic()
            try:
                response = judge_model.invoke([HumanMessage(content=build_judge_prompt(request))])
                judge_latency_ms = (time.monotonic() - started) * 1000
                judge_payload = parse_judge_response(_message_text(response), request=request)
                judge_status = "COMPLETED"
                break
            except (json.JSONDecodeError, ValueError) as exc:
                judge_error = f"{type(exc).__name__}: {exc}"
                break
            except Exception as exc:
                judge_error = type(exc).__name__
                if attempt == 1:
                    break

        judge_criteria = []
        if judge_payload:
            judge_criteria = [
                {
                    "criterion_id": criterion_id,
                    "oracle": "LLM_JUDGE",
                    "role": "PRIMARY",
                    "required": True,
                    "result": item["verdict"],
                    "reason": item["reason"],
                    "evidence_refs": item["evidence_refs"],
                }
                for criterion_id, item in judge_payload["criteria"].items()
            ]
        scored = score_scenario(
            validity=validity,
            criteria=deterministic + judge_criteria,
            hard_gate_triggered=bool(candidate["side_effects"]),
            judge_execution_status=judge_status,
            required_judge_expected=True,
        )
        evidence_hash = hashlib.sha256(
            json.dumps(request["untrusted_evidence"], ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()
        recorder.append_scenario(
            {
                "scenario_id": fixture["fixture_id"],
                "fixture_id": fixture["fixture_id"],
                "fixture_version": fixture["fixture_version"],
                "gold_version": fixture["gold_version"],
                "scoring_contract_id": "eval-v2-scoring-v1",
                **scored,
                "candidate": candidate,
                "evidence_bundle_sha256": evidence_hash,
                "judge": {
                    "model": DEFAULT_JUDGE_MODEL,
                    "reasoning_effort": DEFAULT_REASONING_EFFORT,
                    "status": judge_status,
                    "latency_ms": judge_latency_ms,
                    "error": judge_error,
                    "verdict": judge_payload,
                    "independence": (
                        "SAME_MODEL" if candidate_model == DEFAULT_JUDGE_MODEL else "DIFFERENT_MODEL"
                    ),
                },
            }
        )
        summary = recorder.finalize()
        if scored["scenario_result"] == "INVALID_EVALUATION_INFRA":
            recorder.record_disposition(
                status="INVALID_EVALUATION_INFRA", reason=scored["reason"]
            )
    finally:
        ChatSessionRepository.delete(session_id=session["session_id"], account_id=args.account_id)

    print(
        json.dumps(
            {
                "run_dir": str(recorder.run_dir.resolve()),
                "scenario_result": scored["scenario_result"],
                "candidate_status": candidate["status"],
                "retrieved_document_ids": candidate["retrieved_document_ids"],
                "judge_status": judge_status,
                "strict_pass_rate": summary["strict_pass_rate"],
                "final_answer": candidate["final_answer"],
                "judge_verdict": judge_payload,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if scored["scenario_result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
