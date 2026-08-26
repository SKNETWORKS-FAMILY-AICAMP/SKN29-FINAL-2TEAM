"""완료된 평가 한 건을 사람 판정과 독립 LLM Judge 판정으로 교차검증한다."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any


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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument(
        "--human-verdict",
        type=Path,
        required=True,
        help="사람이 검수·승인하고 검수자와 시각을 기록한 기준 판정 JSON",
    )
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--judge-model", help="생략하면 평가 실행에 기록된 모델 사용")
    parser.add_argument("--reasoning-effort", default="low")
    parser.add_argument("--prompt-version", default="judge-calibration-v0")
    return parser


def _read_case_result(run_dir: Path, case_id: str) -> dict[str, Any]:
    matches = [
        json.loads(line)
        for line in (run_dir / "case_results.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip() and json.loads(line).get("case_id") == case_id
    ]
    if len(matches) != 1:
        raise ValueError(f"case_results에서 {case_id} 한 건을 찾지 못했습니다: {len(matches)}건")
    return matches[0]


def _message_text(message: Any) -> str:
    text = getattr(message, "text", None)
    if isinstance(text, str) and text.strip():
        return text
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            str(item.get("text"))
            for item in content
            if isinstance(item, dict) and item.get("type") in {"text", "output_text"}
        ]
        return "".join(parts)
    return str(content)


def _usage(message: Any) -> dict[str, int | None]:
    usage = getattr(message, "usage_metadata", None) or {}
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    return {
        "input_tokens": input_tokens if isinstance(input_tokens, int) else None,
        "output_tokens": output_tokens if isinstance(output_tokens, int) else None,
        "total_tokens": (
            input_tokens + output_tokens
            if isinstance(input_tokens, int) and isinstance(output_tokens, int)
            else None
        ),
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
    import django

    django.setup()

    from langchain_core.messages import HumanMessage

    from backend.db import AccountRepository
    from services.agent_runtime.models.factory import ModelConfigResolver, ModelFactory
    from services.evaluation import load_workflow_dataset, select_case
    from services.evaluation.calibration import (
        append_calibration,
        build_judge_prompt,
        build_judge_request,
        load_evidence_bundle,
        load_human_verdict,
        make_calibration_record,
        parse_judge_response,
    )

    dataset = load_workflow_dataset(args.dataset)
    case = select_case(dataset, args.case_id)
    case_result = _read_case_result(args.run_dir, args.case_id)
    evidence = load_evidence_bundle(args.evidence, case)
    human = load_human_verdict(
        args.human_verdict,
        case_id=args.case_id,
        agent_run_id=case_result.get("agent_run_id"),
    )
    request = build_judge_request(
        case=case,
        final_answer=case_result.get("final_answer", ""),
        evidence_bundle=evidence,
        deterministic_assertions=case_result.get("assertions", []),
        agent_run_id=case_result.get("agent_run_id"),
    )

    profile = AccountRepository.get_profile(args.account_id)
    judge_model = args.judge_model or case_result["model"]
    resolved = ModelConfigResolver().resolve(
        model=judge_model,
        reasoning_effort=args.reasoning_effort,
        team_id=profile["team_id"],
    )
    model = ModelFactory().create(resolved)
    started = time.monotonic()
    try:
        response = model.invoke([HumanMessage(content=build_judge_prompt(request))])
    except Exception as exc:  # 모델 장애 세부 응답에는 endpoint 정보가 있을 수 있다.
        print(f"Judge 모델 호출 실패: {type(exc).__name__}", file=sys.stderr)
        return 2
    elapsed_ms = (time.monotonic() - started) * 1000
    try:
        judge_verdict = parse_judge_response(_message_text(response))
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"Judge 응답 검증 실패: {exc}", file=sys.stderr)
        return 3

    manifest = json.loads((args.run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    record = make_calibration_record(
        eval_run_id=manifest["eval_run_id"],
        case_result=case_result,
        evidence_bundle=evidence,
        human_verdict=human,
        judge_verdict=judge_verdict,
        judge_model=judge_model,
        prompt_version=args.prompt_version,
        latency_ms=elapsed_ms,
        usage=_usage(response),
    )
    path = append_calibration(args.run_dir, record)
    print(path.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
