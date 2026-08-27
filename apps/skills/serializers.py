"""「스킬」 API 표현.

`services.agent_runtime.skills.service`가 이미 프론트 계약(`api/skills.ts`의
`Skill` 인터페이스)과 같은 모양의 dict를 돌려주므로, 여기서는 그대로
내보낸다 — 다시 만들면 두 곳이 어긋날 수 있는 값을 하나 더 만드는 셈이다.
"""

from datetime import datetime, timezone
from typing import Any


def skill_response(row: dict[str, Any], *, account_id: str | None = None) -> dict[str, Any]:
    response = {
        "skill_id": row["skill_id"],
        "name": row["name"],
        "description": row["description"],
        "updated_at": row.get("updated_at"),
        "enabled": row.get("enabled", True),
        "shared_by_me": bool(
            account_id and row.get("shared_by_account_id") == account_id
        ),
        "imported_from_team": bool(row.get("imported_from_team_id")),
        "imported_by_me": bool(row.get("imported_by_me", False)),
        "can_delete": bool(row.get("can_delete", False)),
        "validation_state": row.get("validation_state"),
        "requires_validation": row.get("validation_state") != "VERIFIED",
    }
    if "body" in row:
        response["body"] = row["body"]
    return response


#: `backend/db/skill_jobs.py`에 저장된 5단계 순서와 정확히 같아야 한다 — 프런트
#: `SkillJobCenter`가 "1-2-3-4-5" 중 몇 번째인지 계산할 때 이 순서를 그대로 쓴다.
JOB_STAGE_ORDER = ["WAITING", "CHECKING", "PREPARING_TESTS", "TESTING", "PUBLISHING"]


def job_response(
    job: dict[str, Any], *, include_candidate: bool = False,
    worker_available: bool | None = None,
) -> dict[str, Any]:
    """`skill_registration_job` 한 행을 `frontend/src/api/skillJobs.ts` 계약으로 바꾼다.

    `job_id`는 DB에서 `uuid.UUID`로, 타임스탬프는 `datetime`으로 온다 — 전부
    JSON으로 나갈 수 있는 문자열로 바꾼다(DRF `Response`가 자동으로 하긴
    하지만, 프런트가 기대하는 필드 이름과 존재 여부는 여기서 명시적으로
    고정한다).
    """

    def _iso(value: Any) -> str | None:
        return value.isoformat() if value is not None else None

    progress_events = job.get("progress_events") or []
    from django.conf import settings

    created_at = job.get("created_at")
    queue_age_seconds = (
        max(0, int((datetime.now(timezone.utc) - created_at).total_seconds()))
        if job.get("status") == "QUEUED" and created_at is not None else 0
    )
    queue_delayed = queue_age_seconds >= settings.SKILL_VALIDATION_QUEUE_DELAY_SECONDS
    waiting_reason = None
    if job.get("status") == "QUEUED" and worker_available is False:
        waiting_reason = "검증 작업을 처리할 서버가 연결되기를 기다리고 있어요."
    elif queue_delayed:
        waiting_reason = "앞선 검증 작업이 끝나기를 기다리고 있어요."

    failure_details = _failure_details_with_examples(job)
    response = {
        "job_id": str(job["job_id"]),
        "skill_name": job["skill_name"],
        "operation": job["operation"],
        "attempt": job.get("attempt", 1),
        "retry_of_job_id": str(job["retry_of_job_id"]) if job.get("retry_of_job_id") else None,
        "status": job["status"],
        "stage": job["stage"],
        "stage_index": JOB_STAGE_ORDER.index(job["stage"]) if job["stage"] in JOB_STAGE_ORDER else 0,
        "stage_count": len(JOB_STAGE_ORDER),
        "failure_code": job.get("failure_code"),
        "failure_summary": job.get("failure_summary"),
        "failure_details": failure_details,
        "failure_category": _failure_category(job.get("failure_code")),
        "progress_message": job.get("progress_message") or _default_progress_message(job),
        "progress_current": job.get("progress_current"),
        "progress_total": job.get("progress_total"),
        # 목록 polling 응답이 계속 커지지 않게 최근 작업만 전달한다.
        "progress_events": progress_events[-8:],
        "created_at": _iso(job.get("created_at")),
        "started_at": _iso(job.get("started_at")),
        "updated_at": _iso(job.get("updated_at")),
        "completed_at": _iso(job.get("completed_at")),
        "worker_available": worker_available,
        "queue_delayed": queue_delayed,
        "queue_age_seconds": queue_age_seconds,
        "waiting_reason": waiting_reason,
        "model_call_count": job.get("model_call_count", 0),
        "estimated_cost_usd": float(job.get("estimated_cost_usd") or 0),
    }
    # 목록에서 본문까지 100건을 싣지 않는다. 실패 상세의 「수정」을 열 때
    # 단건 조회에서만 검증했던 초안을 돌려준다.
    if include_candidate:
        response["candidate_document"] = job.get("candidate_document")
    return response


def _failure_details_with_examples(job: dict[str, Any]) -> dict[str, Any] | None:
    """기존 job도 다시 돌리지 않고 실제 실패 질문을 이해할 수 있게 보강한다.

    평가 질문은 합성 데이터이며 React가 일반 문자열로 렌더링한다. 원래 사용자
    대화를 복사하지 않고 job에 이미 저장된 suite와 trace만 결합한다.
    """

    raw_details = job.get("failure_details")
    details = dict(raw_details) if isinstance(raw_details, dict) else {}
    if job.get("failure_code") != "TRIGGER_ACCURACY_TOO_LOW":
        return details or None

    suite = job.get("test_case_set") or []
    trace = job.get("trace_summary") or {}
    cases_by_id = {case.get("case_id"): case for case in suite if case.get("case_id")}

    false_counts: dict[str, int] = {}
    valid_counts: dict[str, int] = {}
    for result in trace.get("routing") or []:
        case_id = result.get("case_id")
        case = cases_by_id.get(case_id)
        if not case or case.get("polarity") != "negative" or result.get("error") is not None:
            continue
        valid_counts[case_id] = valid_counts.get(case_id, 0) + 1
        if result.get("activated") is True:
            false_counts[case_id] = false_counts.get(case_id, 0) + 1

    false_examples = []
    for case_id, count in sorted(false_counts.items(), key=lambda item: (-item[1], item[0])):
        case = cases_by_id[case_id]
        messages = case.get("messages") or []
        request = next(
            (str(message.get("content") or "") for message in reversed(messages) if message.get("role") == "user"),
            "",
        )
        false_examples.append(
            {
                "request": request,
                "reason": str(case.get("reason") or ""),
                "selected_count": count,
                "attempt_count": valid_counts.get(case_id, count),
            }
        )
    if false_examples:
        details["false_activation_examples"] = false_examples[:4]

    behavior_examples = []
    for result in trace.get("behavior") or []:
        failures = result.get("semantic_failures") or [
            failure for failure in (result.get("failures") or [])
            if str(failure).startswith("BEHAVIOR_ASSERTION_")
        ]
        if not failures:
            continue
        case = cases_by_id.get(result.get("case_id")) or {}
        assertions = case.get("behavior_assertions") or []
        failed_criteria = []
        for failure in failures:
            try:
                index = int(str(failure).rsplit(":", 1)[1])
            except (IndexError, ValueError):
                continue
            if 0 <= index < len(assertions):
                failed_criteria.append(str(assertions[index].get("criterion") or ""))
        if failed_criteria:
            behavior_examples.append({"failed_criteria": failed_criteria})
    if behavior_examples:
        details["behavior_failure_examples"] = behavior_examples[:3]

    return details or None


def _failure_category(code: str | None) -> str | None:
    if not code:
        return None
    if code in {
        "EVAL_INFRA_ERROR", "EVAL_JOB_TIMEOUT", "WORKER_INTERNAL_ERROR",
        "EVAL_BUDGET_EXCEEDED", "EVAL_PROVIDER_CAPACITY_TIMEOUT",
    }:
        return "SYSTEM"
    if code in {"STALE_CANDIDATE", "STALE_EVAL_CONTEXT"}:
        return "CHANGED_CONTEXT"
    if code in {"SKILL_NAME_CONFLICT", "INVALID_SKILL_FORMAT"}:
        return "BASIC_INFO"
    return "SKILL_QUALITY"


def _default_progress_message(job: dict[str, Any]) -> str:
    """마이그레이션 전 fixture·테스트 행에도 안정적인 기본 문구를 준다."""

    return {
        "WAITING": "검증을 시작할 차례를 기다리고 있어요.",
        "CHECKING": "스킬의 기본 정보를 확인하고 있어요.",
        "PREPARING_TESTS": "검증에 사용할 상황을 준비하고 있어요.",
        "TESTING": "준비한 상황에서 스킬을 반복해서 확인하고 있어요.",
        "PUBLISHING": "검증을 통과한 스킬을 등록하고 있어요.",
    }.get(job.get("stage"), "스킬을 검증하고 있어요.")
