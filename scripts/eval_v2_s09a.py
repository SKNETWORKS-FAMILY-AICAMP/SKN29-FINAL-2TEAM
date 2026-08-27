"""S09A-DEV-001의 통제된 timeout 재시도와 답변 품질을 자동 평가한다."""

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
FIXTURE_DIR = REPO_ROOT / "docs" / "설계 및 구현" / "3_중간발표 이후" / "설계" / "eval" / "v2" / "fixtures" / "dev" / "S09A-DEV-001"
DEFAULT_OUTPUT = REPO_ROOT / "outputs" / "eval-v2-results"
SYNTHETIC_DOC_ID = "EVAL-S09A-PDF-IMPROVEMENT"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", default="UA002")
    parser.add_argument("--agent-id", default="AG004")
    parser.add_argument("--agent-version-id", default="AV035")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    return parser


def _git_commit() -> str:
    head = (REPO_ROOT / ".git" / "HEAD").read_text(encoding="utf-8").strip()
    if head.startswith("ref: "):
        ref = REPO_ROOT / ".git" / head.removeprefix("ref: ")
        if ref.is_file():
            return ref.read_text(encoding="utf-8").strip()
    return head or "unknown"


def _load() -> tuple[dict[str, Any], dict[str, Any]]:
    return (
        yaml.safe_load((FIXTURE_DIR / "fixture.yaml").read_text(encoding="utf-8")),
        yaml.safe_load((FIXTURE_DIR / "gold.yaml").read_text(encoding="utf-8")),
    )


def _pages(fixture: dict[str, Any]) -> list[dict[str, str]]:
    from pypdf import PdfReader

    source = fixture["source_artifacts"][0]
    reader = PdfReader(REPO_ROOT / source["repo_path"])
    return [{
        "ref": f"{source['source_id']}:p{number}",
        "text": (reader.pages[number - 1].extract_text() or "").strip(),
    } for number in source["relevant_pages"]]


def _fixtures(fixture: dict[str, Any], pages: list[dict[str, str]]) -> dict[str, list[dict[str, Any]]]:
    from services.agent_runtime.skills.evaluation.stub_tools import EVAL_FAULT_KEY

    evidence = [{
        "chunk_id": f"S09A-P{index}", "doc_id": SYNTHETIC_DOC_ID,
        "heading_path": f"개선요청 접수내역 {index}쪽", "text": page["text"],
        "retrieval_score": 0.99 - index * 0.01,
    } for index, page in enumerate(pages, start=1)]
    success = {"query": "2026년 현황과 2027년 우선 반영", "evidence": evidence}
    listed = {"documents": [{
        "doc_id": SYNTHETIC_DOC_ID,
        "file_name": Path(fixture["source_artifacts"][0]["repo_path"]).name,
    }]}
    return {
        "document_search": [{EVAL_FAULT_KEY: "RETRYABLE_TIMEOUT"}, success, success, success],
        "document_list": [listed, listed],
    }


def _build_executor(tool_fixtures, recorder):
    from services.agent_runtime.bootstrap import bootstrap_harness_profiles
    from services.agent_runtime.executor import AgentExecutor
    from services.agent_runtime.factory import AgentRuntimeFactory, DependencyGraphSource
    from services.agent_runtime.loader import AgentDefinitionLoader
    from services.agent_runtime.middleware.factory import MiddlewareFactory
    from services.agent_runtime.models.factory import ModelConfigResolver, ModelFactory
    from services.agent_runtime.prompts import RuntimePromptAssembler
    from services.agent_runtime.runtime_policy import RuntimeCapabilityPolicy
    from services.agent_runtime.skills.evaluation.harness import EvalCheckpointerProvider
    from services.agent_runtime.skills.evaluation.stub_tools import EvalToolLoader
    from services.agent_runtime.skills.provider import SkillsProvider

    policy = RuntimeCapabilityPolicy()
    bootstrap_harness_profiles(excluded_tools=policy.excluded_builtin_tools)
    factory = AgentRuntimeFactory(
        dependency_graph=DependencyGraphSource(), model_config_resolver=ModelConfigResolver(),
        model_factory=ModelFactory(), tool_loader=EvalToolLoader(tool_fixtures=tool_fixtures, recorder=recorder),
        middleware_factory=MiddlewareFactory(runtime_policy=policy), runtime_policy=policy,
        prompt_assembler=RuntimePromptAssembler(), memory_provider=None,
        checkpointer_provider=EvalCheckpointerProvider(), skills_provider=SkillsProvider(),
    )
    return AgentExecutor(loader=AgentDefinitionLoader(), factory=factory)


def _message_text(message: Any) -> str:
    value = getattr(message, "text", None) or getattr(message, "content", "")
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(str(item.get("text") or "") for item in value if isinstance(item, dict))
    return str(value)


def _controlled_retry_sequence(search_events: list[dict[str, Any]], outcomes: list[str]) -> bool:
    return (
        len(search_events) == 1
        and bool(search_events[0].get("tool_call_id"))
        and outcomes == ["RETRYABLE_TIMEOUT", "SUCCESS"]
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
    import django
    django.setup()

    from apps.accounts.permissions import account_role
    from backend.db import AccountRepository
    from backend.db.agent_platform import ChatSessionRepository
    from langchain_core.messages import HumanMessage
    from services.agent_runtime import RuntimeContext
    from services.agent_runtime.loader import AgentDefinitionLoader
    from services.agent_runtime.models.factory import ModelConfigResolver, ModelFactory
    from services.agent_runtime.skills.evaluation.stub_tools import TOOL_STUB_VERSION, ToolCallRecorder
    from services.evaluation.runner import run_read_only_case
    from services.evaluation.v2_judge import DEFAULT_JUDGE_MODEL, DEFAULT_REASONING_EFFORT, build_judge_prompt, build_judge_request, parse_judge_response
    from services.evaluation.v2_recorder import V2EvaluationRecorder
    from services.evaluation.v2_scoring import score_scenario

    fixture, gold = _load()
    pages = _pages(fixture)
    tool_recorder = ToolCallRecorder()
    executor = _build_executor(_fixtures(fixture, pages), tool_recorder)
    profile = AccountRepository.get_profile(args.account_id)
    session = ChatSessionRepository.create(
        account_id=args.account_id, agent_id=args.agent_id, proj_id=None,
        title="[EVAL V2] S09A-DEV-001 controlled timeout",
    )
    context = RuntimeContext(
        account_id=args.account_id, team_id=profile["team_id"], role=account_role(profile),
        session_id=session["session_id"], run_id=str(uuid4()),
    )
    loaded = AgentDefinitionLoader().load(
        agent_id=args.agent_id, agent_version_id=args.agent_version_id, context=context
    )
    candidate_model = loaded.definition.model
    runtime = f"deepagents-{importlib.metadata.version('deepagents')}"
    recorder = V2EvaluationRecorder.start(output_root=args.output_root, manifest={
        "git_commit": _git_commit(), "candidate_id": f"{args.agent_id}/{args.agent_version_id}",
        "candidate_model": candidate_model, "runtime_profile": runtime,
        "planned_scenarios": [fixture["fixture_id"]], "judge_model": DEFAULT_JUDGE_MODEL,
        "judge_reasoning_effort": DEFAULT_REASONING_EFFORT,
        "isolation": "CONTROLLED_TIMEOUT_ALL_BUSINESS_TOOLS_STUBBED",
        "tool_stub_version": TOOL_STUB_VERSION,
    })
    context = dataclasses.replace(
        context, eval_run_id=recorder.manifest["eval_run_id"], eval_case_id=fixture["fixture_id"],
        environment="local-dev-isolated",
    )
    case = {
        "id": fixture["fixture_id"], "input": fixture["input"],
        "agent_id": args.agent_id, "agent_version_id": args.agent_version_id,
        "execution_mode": "read_only", "expected_status": "SUCCESS",
        "required_tools": ["document_search"], "allowed_tools": fixture["allowed_tools"],
        "forbidden_tools": fixture["forbidden_tools"], "max_tool_calls": 4,
        "max_calls_per_tool": {"document_search": 2, "document_list": 2},
        "required_evidence_documents": [SYNTHETIC_DOC_ID], "optional_evidence_documents": [],
    }
    observed_events: list[dict[str, Any]] = []

    try:
        candidate = run_read_only_case(
            case=case, executor=executor, context=context, model=candidate_model, runtime=runtime,
            event_observer=observed_events.append,
        )
        candidate.pop("judge", None)
        search_events = [
            event for event in observed_events
            if event.get("type") == "tool_started" and event.get("tool_ref") == "document_search"
        ]
        physical = [call for call in tool_recorder.calls if call.tool_ref == "document_search"]
        physical_outcomes = [call.outcome for call in physical]
        logical_call_id = str(search_events[0].get("tool_call_id") or "") if len(search_events) == 1 else ""
        controlled_sequence = _controlled_retry_sequence(search_events, physical_outcomes)
        validity = "VALID" if not candidate["execution_errors"] else "EXECUTION_INFRA_ERROR"
        deterministic = [
            {"criterion_id": "controlled_retry_sequence", "oracle": "DETERMINISTIC", "role": "PRIMARY", "required": True,
             "result": "PASS" if controlled_sequence else "FAIL"},
            {"criterion_id": "retry_budget_respected", "oracle": "DETERMINISTIC", "role": "PRIMARY", "required": True,
             "result": "PASS" if len(physical) <= fixture["fault_schedule"]["max_physical_attempts"] else "FAIL"},
            {"criterion_id": "required_source_retrieval", "oracle": "DETERMINISTIC", "role": "PRIMARY", "required": True,
             "result": "PASS" if SYNTHETIC_DOC_ID in candidate["retrieved_document_ids"] else "FAIL"},
        ]
        facts = [item["proposition"] for item in gold["truth_catalog"]["facts"] if item["importance"] == "REQUIRED"]
        criteria = [
            {"criterion_id": "required_fact_coverage", "rubric": "다음 필수 사실을 빠짐없이 전달하면 PASS: " + json.dumps(facts, ensure_ascii=False)},
            {"criterion_id": "factual_grounding", "rubric": "답변의 사실 주장이 제공된 PDF evidence와 일치하면 PASS."},
            {"criterion_id": "unsupported_claim_control", "rubric": "PDF evidence에 없는 상태·원인·우선순위를 사실처럼 추가하지 않으면 PASS."},
        ]
        request = build_judge_request(
            scenario_id=fixture["fixture_id"], criteria=criteria,
            user_input=fixture["input"], candidate_answer=candidate["final_answer"],
            evidence=[{"ref": page["ref"], "excerpt": page["text"]} for page in pages],
            deterministic_assertions=deterministic,
            execution_summary={
                "logical_document_search_calls": len(search_events),
                "physical_attempt_outcomes": physical_outcomes,
                "physical_attempts_bound_by_single_logical_call": len(search_events) == 1,
            },
        )
        resolved = ModelConfigResolver().resolve(
            model=DEFAULT_JUDGE_MODEL, reasoning_effort=DEFAULT_REASONING_EFFORT,
            team_id=profile["team_id"],
        )
        judge_model = ModelFactory().create(resolved)
        judge_status, judge_payload, judge_error, judge_latency_ms = "ERROR", None, None, None
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
                if attempt == 1:
                    break
            except Exception as exc:
                judge_error = type(exc).__name__
                if attempt == 1:
                    break
        judge_criteria = []
        if judge_payload:
            judge_criteria = [{
                "criterion_id": criterion_id, "oracle": "LLM_JUDGE", "role": "PRIMARY",
                "required": True, "result": item["verdict"], "reason": item["reason"],
                "evidence_refs": item["evidence_refs"],
            } for criterion_id, item in judge_payload["criteria"].items()]
        scored = score_scenario(
            validity=validity, criteria=deterministic + judge_criteria,
            hard_gate_triggered=bool(candidate["side_effects"]),
            judge_execution_status=judge_status, required_judge_expected=True,
        )
        evidence_hash = hashlib.sha256(json.dumps(
            request["untrusted_evidence"], ensure_ascii=False, sort_keys=True
        ).encode()).hexdigest()
        recorder.append_scenario({
            "scenario_id": fixture["fixture_id"], "fixture_id": fixture["fixture_id"],
            "fixture_version": fixture["fixture_version"], "gold_version": fixture["gold_version"],
            "scoring_contract_id": "eval-v2-scoring-v1", **scored,
            "evidence_bundle_sha256": evidence_hash,
            "retry_observation": {
                "logical_call_count": len(search_events), "physical_attempt_count": len(physical),
                "physical_attempt_outcomes": physical_outcomes,
                "logical_call_id_sha256": hashlib.sha256(logical_call_id.encode()).hexdigest(),
                "physical_attempts": [
                    {"attempt": index, "outcome": call.outcome}
                    for index, call in enumerate(physical, start=1)
                ],
            },
            "candidate": candidate,
            "judge": {"model": DEFAULT_JUDGE_MODEL, "reasoning_effort": DEFAULT_REASONING_EFFORT,
                      "status": judge_status, "latency_ms": judge_latency_ms, "error": judge_error,
                      "verdict": judge_payload,
                      "independence": "SAME_MODEL" if candidate_model == DEFAULT_JUDGE_MODEL else "DIFFERENT_MODEL"},
        })
        summary = recorder.finalize()
        if scored["scenario_result"] == "INVALID_EVALUATION_INFRA":
            recorder.record_disposition(status="INVALID_EVALUATION_INFRA", reason=scored["reason"])
    finally:
        ChatSessionRepository.delete(session_id=session["session_id"], account_id=args.account_id)

    print(json.dumps({
        "run_dir": str(recorder.run_dir.resolve()), "scenario_result": scored["scenario_result"],
        "logical_call_count": len(search_events), "physical_attempt_outcomes": physical_outcomes,
        "judge_status": judge_status, "strict_pass_rate": summary["strict_pass_rate"],
        "final_answer": candidate["final_answer"], "judge_verdict": judge_payload,
    }, ensure_ascii=False, indent=2))
    return 0 if scored["scenario_result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
