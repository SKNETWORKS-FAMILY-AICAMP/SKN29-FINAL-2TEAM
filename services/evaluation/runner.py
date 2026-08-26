"""조회 전용 Agent workflow를 실행하고 결정론적 규칙으로 판정한다."""

from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from services.agent_runtime.context import RuntimeContext
from services.evaluation.judge import (
    build_judge_request,
    evidence_scope,
    validate_judge_verdict,
)


class ReportOnlyJudge(Protocol):
    """사람과 교차검증되기 전까지 결과를 뒤집지 않는 의미 평가기."""

    def __call__(self, request: dict[str, Any]) -> dict[str, Any]: ...


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_workflow_dataset(path: Path) -> dict[str, Any]:
    """workflow 데이터셋을 읽고 실행에 필요한 최소 구조를 검증한다."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        raise ValueError("workflow 데이터셋에는 cases 목록이 필요합니다.")
    if not payload.get("dataset_id") or not isinstance(payload.get("dataset_version"), int):
        raise ValueError("workflow 데이터셋의 id와 정수 version이 필요합니다.")

    ids: set[str] = set()
    for index, case in enumerate(payload["cases"]):
        if not isinstance(case, dict):
            raise ValueError(f"cases[{index}]는 객체여야 합니다.")
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError(f"cases[{index}].id가 필요합니다.")
        if case_id in ids:
            raise ValueError(f"중복된 case id입니다: {case_id}")
        ids.add(case_id)
        retry_policy = case.get("tool_retry_policy")
        if retry_policy is not None:
            if not isinstance(retry_policy, dict):
                raise ValueError(f"{case_id}.tool_retry_policy는 객체여야 합니다.")
            for field in (
                "max_retries_after_failure_per_signature",
                "max_consecutive_failures_per_signature",
            ):
                value = retry_policy.get(field)
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    raise ValueError(f"{case_id}.tool_retry_policy.{field}가 잘못됐습니다.")
    return payload


def select_case(dataset: dict[str, Any], case_id: str) -> dict[str, Any]:
    for case in dataset["cases"]:
        if case["id"] == case_id:
            return case
    raise KeyError(f"평가 사례를 찾을 수 없습니다: {case_id}")


def _assertion(name: str, passed: bool, *, detail: str, category: str) -> dict[str, Any]:
    return {"name": name, "passed": passed, "detail": detail, "category": category}


def _tool_reliability(events: list[dict[str, Any]]) -> dict[str, Any]:
    """도구 실패 뒤 같은 입력 재시도와 복구 여부를 정량화한다."""
    signature_states: dict[str, dict[str, int | bool]] = {}
    pending: dict[str, tuple[str, str, bool]] = {}
    by_tool: dict[str, dict[str, int]] = {}
    failed_count = 0
    retry_count = 0
    recovered_count = 0
    unmatched_count = 0
    max_consecutive_failures = 0
    max_retries_per_signature = 0

    for event in events:
        event_type = event.get("type")
        if event_type == "tool_started":
            tool_ref = str(event.get("tool_ref") or "unknown")
            arguments = event.get("arguments")
            canonical_arguments = json.dumps(
                arguments if isinstance(arguments, dict) else {},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            )
            signature = hashlib.sha256(
                f"{tool_ref}\0{canonical_arguments}".encode("utf-8")
            ).hexdigest()
            state = signature_states.setdefault(
                signature,
                {"failure_open": False, "consecutive_failures": 0, "retries": 0},
            )
            tool = by_tool.setdefault(
                tool_ref,
                {"attempted": 0, "failed": 0, "retried_after_failure": 0, "recovered": 0},
            )
            tool["attempted"] += 1
            is_retry = bool(state["failure_open"])
            if is_retry:
                retry_count += 1
                tool["retried_after_failure"] += 1
                state["retries"] = int(state["retries"]) + 1
                max_retries_per_signature = max(
                    max_retries_per_signature, int(state["retries"])
                )
            call_id = event.get("tool_call_id")
            if call_id:
                pending[str(call_id)] = (signature, tool_ref, is_retry)
            else:
                unmatched_count += 1
            continue

        if event_type != "tool_completed" or not event.get("tool_call_id"):
            continue
        attempt = pending.pop(str(event["tool_call_id"]), None)
        if attempt is None:
            continue
        signature, tool_ref, is_retry = attempt
        state = signature_states[signature]
        tool = by_tool[tool_ref]

        if event.get("status") == "OK":
            if is_retry:
                recovered_count += 1
                tool["recovered"] += 1
            state["failure_open"] = False
            state["consecutive_failures"] = 0
            state["retries"] = 0
            continue

        failed_count += 1
        tool["failed"] += 1
        state["failure_open"] = True
        state["consecutive_failures"] = int(state["consecutive_failures"]) + 1
        max_consecutive_failures = max(
            max_consecutive_failures, int(state["consecutive_failures"])
        )

    unmatched_count += len(pending)

    return {
        "failed_call_count": failed_count,
        "retry_after_failure_count": retry_count,
        "recovered_after_retry_count": recovered_count,
        "max_consecutive_failures_per_signature": max_consecutive_failures,
        "max_retries_after_failure_per_signature": max_retries_per_signature,
        "unmatched_started_call_count": unmatched_count,
        "by_tool": by_tool,
        "argument_storage": "sha256-only-in-memory",
    }


def _judge_report(
    *,
    case: dict[str, Any],
    final_answer: str,
    events: list[dict[str, Any]],
    assertions: list[dict[str, Any]],
    agent_run_id: str | None,
    evidence_bundle: dict[str, dict[str, Any]] | None,
    judge: ReportOnlyJudge | None,
) -> dict[str, Any]:
    """공통 근거 계약을 지키며 Judge를 REPORT_ONLY로 실행한다."""
    scope = evidence_scope(case)
    bundle = evidence_bundle or {}
    unavailable = [doc_id for doc_id in scope if bundle.get(doc_id, {}).get("status") != "AVAILABLE"]
    base = {
        "mode": "REPORT_ONLY",
        "evidence_scope": scope,
        "checked_documents": [doc_id for doc_id in scope if doc_id not in unavailable],
    }
    if unavailable:
        return {
            **base,
            "status": "UNCERTAIN",
            "reason": "Judge 판정에 필요한 문서를 모두 확인하지 못했습니다.",
            "unavailable_documents": unavailable,
        }
    if judge is None:
        return {
            **base,
            "status": "NOT_RUN",
            "reason": "Judge adapter가 설정되지 않았습니다.",
        }

    tool_trace = [
        {
            key: event.get(key)
            for key in ("type", "tool_ref", "status", "retrieved_doc_ids")
            if event.get(key) is not None
        }
        for event in events
        if event.get("type") in {"tool_started", "tool_completed"}
    ]
    try:
        request = build_judge_request(
            case=case,
            final_answer=final_answer,
            evidence_bundle=bundle,
            deterministic_assertions=assertions,
            tool_trace=tool_trace,
            agent_run_id=agent_run_id,
        )
        result = judge(request)
        if not isinstance(result, dict):
            raise ValueError("Judge 결과가 객체가 아닙니다.")
        validate_judge_verdict(result, label="judge_verdict")
    except Exception as exc:  # Judge 장애가 실제 실행 결과를 잃게 해서는 안 된다.
        return {**base, "status": "ERROR", "reason": str(exc)}
    return {**base, "status": "COMPLETED", "result": result}


def evaluate_events(
    *,
    case: dict[str, Any],
    events: list[dict[str, Any]],
    started_at: str,
    finished_at: str,
    elapsed_ms: float,
    model: str,
    runtime: str,
    run_id: str | None,
    time_to_first_token_ms: float | None = None,
    judge: ReportOnlyJudge | None = None,
    evidence_bundle: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """이벤트만으로 검증 가능한 항목을 판정하고 recorder payload를 만든다."""
    started_tools = [event for event in events if event.get("type") == "tool_started"]
    completed_tools = [event for event in events if event.get("type") == "tool_completed"]
    tool_refs = [str(event.get("tool_ref")) for event in started_tools if event.get("tool_ref")]
    tool_counts = Counter(tool_refs)
    allowed = set(case.get("allowed_tools", []))
    forbidden = set(case.get("forbidden_tools", []))
    required = set(case.get("required_tools", []))
    retrieved = {
        str(doc_id)
        for event in completed_tools
        for doc_id in event.get("retrieved_doc_ids", [])
    }
    required_docs = set(case.get("required_evidence_documents", []))
    results = [event for event in events if event.get("type") == "result"]
    errors = [event for event in events if event.get("type") == "error"]
    approvals = [event for event in events if event.get("type") == "awaiting_confirmation"]
    final_answer = str(results[-1].get("text") or "") if results else ""
    terminal_status = "FAILED" if errors or not results else "SUCCESS"
    tool_reliability = _tool_reliability(events)
    retry_policy = case.get("tool_retry_policy") or {}

    assertions = [
        _assertion(
            "terminal_status",
            terminal_status == case.get("expected_status", "SUCCESS"),
            detail=f"actual={terminal_status}, expected={case.get('expected_status', 'SUCCESS')}",
            category="execution",
        ),
        _assertion(
            "final_answer_present",
            bool(final_answer.strip()),
            detail="최종 답변 존재 여부",
            category="execution",
        ),
        _assertion(
            "required_tools_called",
            required.issubset(tool_counts),
            detail=f"required={sorted(required)}, called={sorted(tool_counts)}",
            category="tooling",
        ),
        _assertion(
            "only_allowed_tools_called",
            set(tool_counts).issubset(allowed),
            detail=f"allowed={sorted(allowed)}, called={sorted(tool_counts)}",
            category="safety",
        ),
        _assertion(
            "forbidden_tools_not_called",
            forbidden.isdisjoint(tool_counts),
            detail=f"forbidden_called={sorted(forbidden.intersection(tool_counts))}",
            category="safety",
        ),
        _assertion(
            "tool_call_limit",
            len(started_tools) <= int(case.get("max_tool_calls", 0)),
            detail=f"actual={len(started_tools)}, max={case.get('max_tool_calls', 0)}",
            category="budget",
        ),
        _assertion(
            "per_tool_call_limits",
            all(
                tool_counts[tool_ref] <= int(limit)
                for tool_ref, limit in case.get("max_calls_per_tool", {}).items()
            ),
            detail=f"actual={dict(tool_counts)}, max={case.get('max_calls_per_tool', {})}",
            category="budget",
        ),
        _assertion(
            "required_evidence_retrieved",
            required_docs.issubset(retrieved),
            detail=f"required={sorted(required_docs)}, retrieved={sorted(retrieved)}",
            category="grounding",
        ),
        _assertion(
            "tool_calls_completed_ok",
            len(completed_tools) == len(started_tools)
            and all(event.get("status") == "OK" for event in completed_tools),
            detail=f"started={len(started_tools)}, completed={len(completed_tools)}",
            category="execution",
        ),
        _assertion(
            "no_approval_requested",
            not approvals,
            detail=f"approval_events={len(approvals)}",
            category="safety",
        ),
    ]
    if retry_policy:
        max_retries = int(retry_policy["max_retries_after_failure_per_signature"])
        max_failures = int(retry_policy["max_consecutive_failures_per_signature"])
        assertions.extend(
            [
                _assertion(
                    "tool_retry_limit",
                    tool_reliability["max_retries_after_failure_per_signature"]
                    <= max_retries,
                    detail=(
                        "actual_max_retries_per_signature="
                        f"{tool_reliability['max_retries_after_failure_per_signature']}, "
                        f"max={max_retries}"
                    ),
                    category="reliability",
                ),
                _assertion(
                    "consecutive_tool_failure_limit",
                    tool_reliability["max_consecutive_failures_per_signature"]
                    <= max_failures,
                    detail=(
                        "actual_max_consecutive_failures="
                        f"{tool_reliability['max_consecutive_failures_per_signature']}, "
                        f"max={max_failures}"
                    ),
                    category="reliability",
                ),
            ]
        )
    failed = [item["name"] for item in assertions if not item["passed"]]
    status = "FAILED" if failed else terminal_status
    terminal = results[-1] if results else (errors[-1] if errors else {})
    input_tokens = terminal.get("token_in")
    output_tokens = terminal.get("token_out")
    metrics: dict[str, int | float] = {
        "end_to_end_latency_ms": round(elapsed_ms, 3),
        "active_execution_latency_ms": round(
            float(terminal.get("duration_ms", elapsed_ms)), 3
        ),
        "tool_call_count": len(started_tools),
        "model_calls": int(terminal.get("iterations") or 0),
        "failed_tool_call_count": tool_reliability["failed_call_count"],
        "retry_after_failure_count": tool_reliability["retry_after_failure_count"],
        "recovered_after_retry_count": tool_reliability["recovered_after_retry_count"],
        "max_consecutive_tool_failures": tool_reliability[
            "max_consecutive_failures_per_signature"
        ],
        "max_tool_retries_per_signature": tool_reliability[
            "max_retries_after_failure_per_signature"
        ],
    }
    if time_to_first_token_ms is not None:
        metrics["time_to_first_token_ms"] = round(time_to_first_token_ms, 3)
    for name, value in (("input_tokens", input_tokens), ("output_tokens", output_tokens)):
        if isinstance(value, int):
            metrics[name] = value
    if isinstance(input_tokens, int) and isinstance(output_tokens, int):
        metrics["total_tokens"] = input_tokens + output_tokens

    tool_call_ids = list(
        dict.fromkeys(
            str(event["tool_call_id"])
            for event in started_tools
            if event.get("tool_call_id")
        )
    )
    violating_tools = sorted(set(tool_counts) - allowed | (set(tool_counts) & forbidden))
    return {
        "case_id": case["id"],
        "agent_id": case["agent_id"],
        "agent_version_id": case["agent_version_id"],
        "model": model,
        "runtime": runtime,
        "started_at": started_at,
        "finished_at": finished_at,
        "status": status,
        "assertions": assertions,
        "failure_reason": ", ".join(failed) if failed else None,
        "agent_run_id": run_id,
        "tool_call_ids": tool_call_ids,
        "langfuse_trace_id": None,
        "metrics": metrics,
        "approval": {"count": len(approvals)} if approvals else None,
        "side_effects": [
            {"tool_ref": tool_ref, "violation": True} for tool_ref in violating_tools
        ],
        "cleanup": {"status": "NOT_REQUIRED"},
        "final_answer": final_answer,
        "retrieved_document_ids": sorted(retrieved),
        "tool_reliability": tool_reliability,
        "judge": _judge_report(
            case=case,
            final_answer=final_answer,
            events=events,
            assertions=assertions,
            agent_run_id=run_id,
            evidence_bundle=evidence_bundle,
            judge=judge,
        ),
    }


def run_read_only_case(
    *,
    case: dict[str, Any],
    executor: Any,
    context: RuntimeContext,
    model: str,
    runtime: str,
    trace_wrapper: Callable[..., Iterable[dict[str, Any]]] | None = None,
    judge: ReportOnlyJudge | None = None,
    evidence_bundle: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """한 조회 전용 사례를 운영 Executor로 실행한다."""
    if case.get("execution_mode") != "read_only":
        raise ValueError("v0 runner는 read_only 사례만 실행합니다.")
    if not context.run_id:
        raise ValueError("평가 실행에는 context.run_id가 필요합니다.")

    started_at = _utc_now()
    started_clock = time.monotonic()
    raw_events = executor.run(
        agent_id=case["agent_id"],
        agent_version_id=case["agent_version_id"],
        user_input=case["input"],
        context=context,
        conversation_messages=(),
        # 데이터셋이 허용한 도구만 노출해 수동 UI 설정 차이를 제거한다.
        tool_refs_override=list(case.get("allowed_tools", [])),
    )
    if trace_wrapper is None:
        from services.agent_runtime.tracing import trace_events

        trace_wrapper = trace_events
    events: list[dict[str, Any]] = []
    time_to_first_token_ms: float | None = None
    for event in trace_wrapper(raw_events, context=context):
        events.append(event)
        if time_to_first_token_ms is None and event.get("type") in {"message_delta", "result"}:
            time_to_first_token_ms = (time.monotonic() - started_clock) * 1000
    elapsed_ms = (time.monotonic() - started_clock) * 1000
    return evaluate_events(
        case=case,
        events=events,
        started_at=started_at,
        finished_at=_utc_now(),
        elapsed_ms=elapsed_ms,
        model=model,
        runtime=runtime,
        run_id=context.run_id,
        time_to_first_token_ms=time_to_first_token_ms,
        judge=judge,
        evidence_bundle=evidence_bundle,
    )
