"""실제 S01 에이전트 실행을 평가 실험실용 case JSON으로 캡처한다.

공식 Eval V2 recorder와 Judge는 호출하지 않는다.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml
from pypdf import PdfReader


LAB_ROOT = Path(__file__).resolve().parent
REPO_ROOT = LAB_ROOT.parents[1]
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
DEFAULT_OUTPUT = LAB_ROOT / "artifacts" / "project_s01_case.json"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", default="UA002")
    parser.add_argument("--agent-id", default="AG004")
    parser.add_argument("--agent-version-id", default="AV073")
    parser.add_argument("--binding", type=Path, default=DEFAULT_BINDING)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def _load_fixture() -> dict[str, Any]:
    return yaml.safe_load((FIXTURE_DIR / "fixture.yaml").read_text(encoding="utf-8"))


def _load_binding(path: Path, fixture: dict[str, Any], account_id: str) -> dict[str, Any]:
    binding = json.loads(path.read_text(encoding="utf-8"))
    if binding.get("fixture_id") != fixture["fixture_id"]:
        raise ValueError("fixture와 binding의 fixture_id가 다릅니다.")
    if binding.get("account_id") != account_id or binding.get("status") != "READY":
        raise ValueError("실행 계정의 READY binding이 아닙니다.")
    return binding


def _source_contexts(
    fixture: dict[str, Any], binding: dict[str, Any], retrieved_doc_ids: list[str]
) -> list[str]:
    source_by_doc = {str(item["doc_id"]): str(item["source_id"]) for item in binding["documents"]}
    retrieved_sources = {
        source_by_doc[doc_id] for doc_id in retrieved_doc_ids if doc_id in source_by_doc
    }
    contexts: list[str] = []
    for source in fixture["source_artifacts"]:
        if source["source_id"] not in retrieved_sources:
            continue
        reader = PdfReader(REPO_ROOT / source["repo_path"])
        for page_number in source["relevant_pages"]:
            text = (reader.pages[int(page_number) - 1].extract_text() or "").strip()
            if text:
                contexts.append(f"[{source['source_id']}:p{page_number}]\n{text}")
    return contexts


def main() -> int:
    args = _parser().parse_args()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
    import django

    django.setup()

    from apps.accounts.permissions import account_role
    from backend.db import AccountRepository
    from backend.db.agent_platform import ChatSessionRepository
    from services.agent_runtime import RuntimeContext, build_default_executor
    from services.agent_runtime.loader import AgentDefinitionLoader
    from services.evaluation.runner import run_read_only_case

    fixture = _load_fixture()
    binding = _load_binding(args.binding, fixture, args.account_id)
    required_doc_ids = [str(item["doc_id"]) for item in binding["documents"]]
    profile = AccountRepository.get_profile(args.account_id)
    session = ChatSessionRepository.create(
        account_id=args.account_id,
        agent_id=args.agent_id,
        proj_id=None,
        title="[OTEL EVAL LAB] S01 실제 에이전트 재실행",
    )
    context = RuntimeContext(
        account_id=args.account_id,
        team_id=profile["team_id"],
        role=account_role(profile),
        session_id=session["session_id"],
        run_id=str(uuid4()),
        eval_run_id=f"otel-lab-{uuid4()}",
        eval_case_id="OTEL-LAB-S01-001",
        environment="otel-eval-lab",
    )
    observed_events: list[dict[str, Any]] = []
    try:
        loaded = AgentDefinitionLoader().load(
            agent_id=args.agent_id,
            agent_version_id=args.agent_version_id,
            context=context,
        )
        case = {
            "id": "OTEL-LAB-S01-001",
            "input": fixture["input"],
            "agent_id": args.agent_id,
            "agent_version_id": args.agent_version_id,
            "execution_mode": "read_only",
            "expected_status": "SUCCESS",
            "required_tools": ["document_search"],
            "allowed_tools": fixture["allowed_tools"],
            "forbidden_tools": fixture["forbidden_tools"],
            "max_tool_calls": 8,
            "max_calls_per_tool": {"document_search": 7, "document_list": 1},
            "required_evidence_documents": required_doc_ids,
            "optional_evidence_documents": [],
        }
        candidate = run_read_only_case(
            case=case,
            executor=build_default_executor(),
            context=context,
            model=loaded.definition.model,
            runtime=f"deepagents-{importlib.metadata.version('deepagents')}",
            event_observer=observed_events.append,
        )
        tool_calls = [
            str(event["tool_ref"])
            for event in observed_events
            if event.get("type") == "tool_started" and event.get("tool_ref")
        ]
        payload = [
            {
                "case_id": "OTEL-LAB-S01-001",
                "input": fixture["input"],
                "actual_output": candidate["final_answer"],
                "retrieval_context": _source_contexts(
                    fixture, binding, candidate["retrieved_document_ids"]
                ),
                "retrieved_context_ids": candidate["retrieved_document_ids"],
                "reference_context_ids": required_doc_ids,
                "tools_called": tool_calls,
                "expected_tools": ["document_search"],
                "source": "PROJECT_AGENT_REEXECUTION",
                "metadata": {
                    "official_score_eligible": False,
                    "candidate_id": f"{args.agent_id}/{args.agent_version_id}",
                    "candidate_model": loaded.definition.model,
                    "agent_run_id": candidate["agent_run_id"],
                    "status": candidate["status"],
                    "retrieved_document_ids": candidate["retrieved_document_ids"],
                    "required_document_ids": required_doc_ids,
                    "metrics": candidate["metrics"],
                    "trace_fidelity": "FULL_ANSWER_WITH_BOUND_SOURCE_PAGES",
                },
            }
        ]
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        ChatSessionRepository.delete(session_id=session["session_id"], account_id=args.account_id)

    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "status": candidate["status"],
                "retrieved_document_ids": candidate["retrieved_document_ids"],
                "tools_called": tool_calls,
                "answer_chars": len(candidate["final_answer"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
