"""조회 전용 workflow 한 건을 실제 Agent 런타임으로 자동 평가한다."""

from __future__ import annotations

import argparse
import dataclasses
import importlib.metadata
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = (
    REPO_ROOT
    / "docs"
    / "설계 및 구현"
    / "3_중간발표 이후"
    / "설계"
    / "eval"
    / "agent_workflow_v1.json"
)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class CleanupAfterEvaluationError(RuntimeError):
    """Agent 결과는 기록됐지만 임시 세션 정리가 실패한 경우."""


def _append_result_after_cleanup_attempt(
    *,
    recorder: Any,
    result: dict[str, Any],
    cleanup: Callable[[], None],
) -> Exception | None:
    """cleanup 성공 여부와 무관하게 이미 계산한 case 결과를 보존한다."""
    cleanup_error: Exception | None = None
    try:
        cleanup()
    except Exception as exc:  # 결과 유실 대신 cleanup 실패를 case에 남긴다.
        cleanup_error = exc
        result["cleanup"] = {
            "status": "FAILED",
            "resource": "temporary_chat_session_and_checkpoints",
            "error_type": type(exc).__name__,
        }
    else:
        result["cleanup"] = {
            "status": "COMPLETED",
            "resource": "temporary_chat_session_and_checkpoints",
        }
    recorder.append_case(result)
    return cleanup_error


def _git_commit() -> str:
    configured = os.getenv("RUNTIME_PROFILE_VERSION") or os.getenv("GIT_COMMIT_SHA")
    if configured:
        return configured
    head_path = REPO_ROOT / ".git" / "HEAD"
    if head_path.is_file():
        head = head_path.read_text(encoding="utf-8").strip()
        if head.startswith("ref: "):
            ref_path = REPO_ROOT / ".git" / head.removeprefix("ref: ")
            if ref_path.is_file():
                return ref_path.read_text(encoding="utf-8").strip()
        elif head:
            return head
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--case-id", default="WF-PROJECT-STATUS-001")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--project-id")
    parser.add_argument("--output-root", type=Path, default=REPO_ROOT / "outputs" / "eval-results")
    parser.add_argument("--environment", default="local")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
    import django

    django.setup()

    from apps.accounts.permissions import account_role
    from backend.db import AccountRepository
    from backend.db.agent_platform import ChatSessionRepository
    from services.agent_runtime import RuntimeContext, build_default_executor
    from services.agent_runtime.loader import AgentDefinitionLoader
    from services.evaluation import (
        EvaluationRecorder,
        load_workflow_dataset,
        run_read_only_case,
        select_case,
    )

    dataset = load_workflow_dataset(args.dataset)
    case = select_case(dataset, args.case_id)
    profile = AccountRepository.get_profile(args.account_id)
    temporary_session = ChatSessionRepository.create(
        account_id=args.account_id,
        agent_id=case["agent_id"],
        proj_id=args.project_id,
        title=f"[EVAL] {case['id']}",
    )
    context = RuntimeContext(
        account_id=args.account_id,
        team_id=profile["team_id"],
        role=account_role(profile),
        session_id=temporary_session["session_id"],
        project_id=args.project_id,
        run_id=str(uuid4()),
    )
    loaded = AgentDefinitionLoader().load(
        agent_id=case["agent_id"],
        agent_version_id=case["agent_version_id"],
        context=context,
    )
    model = loaded.definition.model
    runtime = f"deepagents-{importlib.metadata.version('deepagents')}"
    recorder = EvaluationRecorder.start(
        output_root=args.output_root,
        manifest={
            "git_commit": _git_commit(),
            "dataset_id": dataset["dataset_id"],
            "dataset_version": dataset["dataset_version"],
            "targets": [
                {"agent_id": case["agent_id"], "agent_version_id": case["agent_version_id"]}
            ],
            "models": [model],
            "runtime": runtime,
            "environment": args.environment,
            "repetitions": 1,
            "account_id": args.account_id,
            "team_id": profile["team_id"],
            "memory_mode": "UNKNOWN",
            "session_policy": "temporary-isolated-delete-after-run",
            "memory_namespace": None,
        },
    )
    context = dataclasses.replace(
        context,
        eval_run_id=recorder.manifest["eval_run_id"],
        eval_case_id=case["id"],
        environment=args.environment,
    )
    cleanup_attempted = False
    try:
        result = run_read_only_case(
            case=case,
            executor=build_default_executor(),
            context=context,
            model=model,
            runtime=runtime,
        )
        cleanup_attempted = True
        cleanup_error = _append_result_after_cleanup_attempt(
            recorder=recorder,
            result=result,
            cleanup=lambda: ChatSessionRepository.delete(
                session_id=temporary_session["session_id"], account_id=args.account_id
            ),
        )
        if cleanup_error is not None:
            recorder.finalize(
                status="ABORTED",
                limitations=[
                    f"Agent 결과 기록 후 임시 세션 정리 실패: {type(cleanup_error).__name__}"
                ],
            )
            raise CleanupAfterEvaluationError(
                "Agent 평가 결과는 보존했지만 임시 세션 정리에 실패했습니다."
            ) from cleanup_error
        recorder.finalize(
            status="COMPLETED",
            limitations=[
                "LLM Judge는 REPORT_ONLY이며 evidence bundle 미연결 상태에서는 실행하지 않음",
            ],
        )
    except CleanupAfterEvaluationError:
        raise
    except Exception as exc:
        if not cleanup_attempted:
            try:
                ChatSessionRepository.delete(
                    session_id=temporary_session["session_id"], account_id=args.account_id
                )
            except Exception as cleanup_exc:
                exc = RuntimeError(f"{exc}; 임시 세션 정리 실패: {cleanup_exc}")
        recorder.finalize(status="ABORTED", limitations=[f"실행 중단: {exc}"])
        raise
    print(recorder.run_dir.resolve())
    return 0 if result["status"] == "SUCCESS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
