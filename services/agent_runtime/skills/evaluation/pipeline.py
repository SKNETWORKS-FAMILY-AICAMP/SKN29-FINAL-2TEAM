"""§8 전체를 묶는 오케스트레이션 — `registration.py`의 `run_preparing_tests`/
`run_testing`이 이 모듈의 함수 둘만 부른다.

실제 오발동 회귀 케이스는 저장·승인 구조만 있고 자동 수집 UI는 별도 범위다.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import queue
import threading
from typing import Any, Callable

from backend.db.skill_eval import SkillEvalRegressionCaseRepository
from backend.db.skill_jobs import SkillEvalBudgetExceeded, SkillRegistrationJobRepository

from .config import EVAL_CONCURRENCY, EVAL_JOB_TIMEOUT_SECONDS, SKILL_EVAL_AUTHOR_MODEL, SKILL_EVAL_REVIEWER_MODEL
from .behavior_reviewer import review_behavior
from .ephemeral_skills import build_ephemeral_skill_store
from .generator import EVAL_CASE_GENERATOR_PROMPT_VERSION, EvalGenerationError, generate_valid_candidates
from .generator import MAX_REGENERATION_ATTEMPTS
from .harness import run_behavior_case, run_routing_case
from .platform_probes import load_platform_probes
from .prompts import BEHAVIOR_SEMANTIC_REVIEWER_PROMPT_VERSION, EVAL_CASE_SEMANTIC_REVIEWER_PROMPT_VERSION
from .scoring import evaluate
from .semantic_reviewer import review_cases
from .stub_tools import TOOL_STUB_VERSION
from .suite import compose_suite
from .rate_limit import ProviderCapacityTimeout, provider_limiter

MAX_SEMANTIC_RETRIES = 2
#: 행동 테스트 대표 케이스 수(§8.11) — 직접 요청 1 + 문맥·문서 요청 1 + 가장
#: 복잡한(도구 필요) 요청 1.
BEHAVIOR_SAMPLE_SIZE = 3
ProgressReporter = Callable[[str, int | None, int | None], None]


def _report(
    progress: ProgressReporter | None,
    message: str,
    current: int | None = None,
    total: int | None = None,
) -> None:
    if progress is not None:
        progress(message, current, total)


def _reserve_model_calls(job: dict[str, Any], count: int) -> None:
    try:
        SkillRegistrationJobRepository.consume_eval_budget(
            job["job_id"], lease_owner=job["lease_owner"], model_calls=count
        )
    except SkillEvalBudgetExceeded as exc:
        raise EvalPipelineError("EVAL_BUDGET_EXCEEDED", str(exc), {"retryable": False}) from exc


def _ensure_deadline(deadline: float | None) -> None:
    if deadline is not None and time.monotonic() >= deadline:
        raise EvalPipelineError("EVAL_JOB_TIMEOUT", "전체 검증 제한 시간 5분을 초과했습니다.")


def _call_until_deadline(fn, deadline: float):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        _ensure_deadline(deadline)
    output: queue.Queue = queue.Queue(maxsize=1)

    def invoke() -> None:
        try:
            output.put((True, fn()))
        except BaseException as exc:  # noqa: BLE001
            output.put((False, exc))

    threading.Thread(target=invoke, daemon=True, name="skill-eval-job-call").start()
    try:
        ok, value = output.get(timeout=remaining)
    except queue.Empty as exc:
        raise EvalPipelineError("EVAL_JOB_TIMEOUT", "전체 검증 제한 시간 5분을 초과했습니다.") from exc
    if not ok:
        raise value
    return value


class EvalPipelineError(Exception):
    def __init__(self, code: str, summary: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(summary)
        self.code = code
        self.summary = summary
        self.details = details or {}


def _available_tools_for(account_id: str, team_id: str) -> list[dict[str, Any]]:  # noqa: ARG001
    """플랫폼에서 스킬이 참조할 수 있는 전체 내장 도구를 생성기에 넘긴다.

    스킬은 특정 에이전트에 종속되지 않으므로 작성 시점에는 전체 도구를 본다.
    실제 에이전트에 도구가 없으면 런타임의 가용성 규칙에 따라 해당 절차를
    건너뛴다. 계정·팀 인자는 이후 커넥터 도구를 합칠 계약을 위해 유지한다.
    """

    from services.agent_runtime.tools.adapters import adapt_builtin_tools

    return [{"tool_ref": t.ref, "name": t.name, "description": t.description} for t in adapt_builtin_tools()]


def _other_skills_for(account_id: str) -> list[dict[str, Any]]:
    from services.agent_runtime.skills.service import list_personal_skills

    return [
        {"name": skill["name"], "description": skill["description"]}
        for skill in list_personal_skills(account_id)
        if skill.get("enabled", True)
    ]


def _select_behavior_sample(positive_cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """우선순위가 겹쳐도 서로 다른 대표 긍정 사례 세 개를 고른다."""

    preferred = (
        [case for case in positive_cases if case["category"] == "direct"][:1]
        + [case for case in positive_cases if case.get("document_fixtures")][:1]
        + sorted(positive_cases, key=lambda case: -len(case.get("required_tools", [])))[:1]
        + positive_cases
    )
    selected = []
    seen_ids: set[str] = set()
    for case in preferred:
        if case["case_id"] in seen_ids:
            continue
        seen_ids.add(case["case_id"])
        selected.append(case)
        if len(selected) == BEHAVIOR_SAMPLE_SIZE:
            break
    return selected


def _default_chat_agent(team_id: str) -> tuple[str, str, str]:
    from backend.db.connection import database_connection

    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT a.agent_id, a.current_version_id, v.model, v.reasoning_effort
                     FROM agents a JOIN agent_versions v ON v.agent_version_id = a.current_version_id
                    WHERE a.team_id = %s AND a.is_default_chat = true LIMIT 1""",
                (team_id,),
            )
            row = cursor.fetchone()
    if row is None or not row["current_version_id"]:
        raise EvalPipelineError(
            "EVAL_INFRA_ERROR", "이 팀에 기본 채팅 에이전트가 없어 검증을 실행할 수 없습니다."
        )
    from services.agent_runtime.models.factory import ModelConfigResolver
    resolved = ModelConfigResolver().resolve(
        model=row["model"], reasoning_effort=row["reasoning_effort"], team_id=team_id
    )
    return row["agent_id"], row["current_version_id"], resolved.provider


def _run_with_provider_slot(provider: str, deadline: float, fn):
    try:
        with provider_limiter.slot(provider, deadline=deadline):
            return fn()
    except ProviderCapacityTimeout as exc:
        raise EvalPipelineError("EVAL_PROVIDER_CAPACITY_TIMEOUT", str(exc), {"retryable": True}) from exc


def _provider_for_model(model: str, team_id: str) -> str:
    from services.agent_runtime.models.factory import ModelConfigResolver

    return ModelConfigResolver().resolve(
        model=model, reasoning_effort="none", team_id=team_id
    ).provider


def run_preparing_tests(job: dict[str, Any], *, progress: ProgressReporter | None = None, deadline: float | None = None) -> None:
    """§8.3-§8.9 — 질문 생성 → 구조 검증(생성기 내부) → 의미 검토 → 최종 12개 구성.

    끝나면 `test_case_set`/`eval_suite_version`/프롬프트 버전들을 job에 남긴다
    — `run_testing()`이 이걸 그대로 읽어서 실행한다(중간에 워커가 죽어도
    다시 만들지 않는다, §8.9 "job이 재시작되거나 lease가 회수돼도 이미 고정된
    suite를 다시 생성하지 않는다").
    """

    document = job["candidate_document"]
    account_id = job["account_id"]
    team_id = job["team_id"]
    deadline = deadline or (time.monotonic() + EVAL_JOB_TIMEOUT_SECONDS)
    _ensure_deadline(deadline)

    _report(progress, "검증에 사용할 도구와 비교할 다른 스킬을 확인하고 있어요.")
    available_tools = _available_tools_for(account_id, team_id)
    other_skills = _other_skills_for(account_id)
    author_provider = _provider_for_model(SKILL_EVAL_AUTHOR_MODEL, team_id)
    reviewer_provider = _provider_for_model(SKILL_EVAL_REVIEWER_MODEL, team_id)

    _report(progress, "스킬이 필요한 상황과 필요하지 않은 상황을 만들고 있어요.")
    # 생성기 한 번도 구조 검증 실패에 따라 내부에서 재호출될 수 있고, 의미
    # 검토가 부족하면 생성기 자체를 다시 부른다. 두 재시도 축의 곱까지 포함한
    # 최악 경로를 예약해야 job별 호출 상한을 우회하지 않는다.
    generation_call_budget = (MAX_REGENERATION_ATTEMPTS + 1) * (MAX_SEMANTIC_RETRIES + 1)
    semantic_review_call_budget = MAX_SEMANTIC_RETRIES + 1
    _reserve_model_calls(job, generation_call_budget + semantic_review_call_budget)
    try:
        positive, negative, author_model_id = _call_until_deadline(
            lambda: _run_with_provider_slot(
                author_provider, deadline,
                lambda: generate_valid_candidates(
                    skill_document=document, available_tools=available_tools, other_skills=other_skills
                ),
            ), deadline
        )
        _ensure_deadline(deadline)
    except EvalGenerationError as exc:
        raise EvalPipelineError(
            "TEST_GENERATION_FAILED",
            str(exc),
            {"failures": [f.__dict__ for f in exc.failures]},
        ) from exc

    # §8.6 의미 검토 — FAIL/UNCERTAIN은 suite에 넣지 않고, 반복 호출에서
    # 통과한 후보를 누적한다. 최종 suite는 polarity별 6개만 필요하므로 생성한
    # 8개 전부가 동시에 PASS일 것을 요구하면 정상 후보가 충분한데도 job이
    # 불필요하게 실패한다.
    reviewer_model_id = ""
    approved_positive = []
    approved_negative = []
    review_failures: list[dict[str, Any]] = []

    def append_unique(target: list, candidates: list) -> None:
        seen = {case.query.strip().lower() for case in target}
        for case in candidates:
            key = case.query.strip().lower()
            if key not in seen:
                target.append(case)
                seen.add(key)

    for review_attempt in range(MAX_SEMANTIC_RETRIES + 1):
        _report(
            progress,
            "만든 상황이 실제 요청처럼 자연스러운지 검토하고 있어요.",
            review_attempt + 1,
            MAX_SEMANTIC_RETRIES + 1,
        )
        merged_cases = positive + negative
        reviews, reviewer_model_id = _call_until_deadline(
            lambda: _run_with_provider_slot(
                reviewer_provider, deadline,
                lambda: review_cases(merged_cases, skill_description=document["description"]),
            ), deadline
        )
        _ensure_deadline(deadline)
        # `review_cases()`는 reviewer가 case_index를 빠뜨리면 그 인덱스를 그냥
        # 건너뛴다(`ordered`가 `cases`보다 짧아질 수 있다) — 그런 인덱스도
        # "검토를 못 받았다"는 뜻이니 교체 대상(bad)으로 취급한다.
        reviews_by_case_index = {r.case_index: r for r in reviews}
        # §8.6 rubric 정의(설계 md) — `intended_skill_match`는 긍정 케이스에만
        # 적용한다(`CaseReview.overall()` docstring 참고). `positive + negative`
        # 순서 그대로 넘겼으므로 앞 `len(positive)`개가 긍정이다.
        passed_positive = []
        passed_negative = []
        review_failures = []
        for index, case in enumerate(merged_cases):
            review = reviews_by_case_index.get(index)
            verdict = (
                review.overall(is_positive=case.should_activate_candidate)
                if review is not None
                else "MISSING"
            )
            if verdict == "PASS":
                (passed_positive if case.should_activate_candidate else passed_negative).append(case)
            else:
                review_failures.append(
                    {"index": index, "polarity": "positive" if case.should_activate_candidate else "negative", "verdict": verdict}
                )

        append_unique(approved_positive, passed_positive)
        append_unique(approved_negative, passed_negative)
        if len(approved_positive) >= 6 and len(approved_negative) >= 6:
            positive = approved_positive
            negative = approved_negative
            break

        # 마지막 검토까지 부족하면 곧바로 실패한다. 여기서 새 질문을 만들어도
        # 다음 검토 반복이 없어 사용되지 않으므로 호출·비용만 낭비하게 된다.
        if review_attempt < MAX_SEMANTIC_RETRIES:
            positive, negative, _ = _run_with_provider_slot(
                author_provider, deadline,
                lambda: generate_valid_candidates(
                    skill_document=document, available_tools=available_tools, other_skills=other_skills
                ),
            )
    else:
        raise EvalPipelineError(
            "TEST_CASE_REVIEW_FAILED",
            "의미 검토를 반복해도 유효한 평가 질문을 충분히 못 만들었습니다.",
            {
                "approved_positive": len(approved_positive),
                "approved_negative": len(approved_negative),
                "required_each": 6,
                "last_failures": review_failures,
            },
        )

    _report(progress, "공통 오발동 사례와 이전 검증 사례를 함께 확인하고 있어요.")
    probe_version, probes = load_platform_probes()
    frontmatter = document.get("frontmatter") if isinstance(document.get("frontmatter"), dict) else {}
    metadata = frontmatter.get("metadata") if isinstance(frontmatter.get("metadata"), dict) else {}
    raw_tags = metadata.get("capability_tags")
    capability_tags = list(dict.fromkeys(
        tag.strip() for tag in raw_tags
        if isinstance(tag, str) and tag.strip()
    )) if isinstance(raw_tags, list) else []
    regression_rows = SkillEvalRegressionCaseRepository.list_approved_for(
        team_id=team_id, skill_name=document["name"], capability_tags=capability_tags
    )

    try:
        suite, suite_version = compose_suite(
            candidate_hash=job["candidate_hash"],
            dataset_version=probe_version,
            positive_candidates=positive,
            negative_candidates=negative,
            approved_regression_rows=regression_rows,
            platform_probes=probes,
        )
    except ValueError as exc:
        raise EvalPipelineError("TEST_GENERATION_FAILED", str(exc)) from exc

    SkillRegistrationJobRepository.update_eval_fields(
        job["job_id"],
        lease_owner=job["lease_owner"],
        test_case_set=suite,
        eval_suite_version=suite_version,
        generator_prompt_version=EVAL_CASE_GENERATOR_PROMPT_VERSION,
        semantic_reviewer_prompt_version=EVAL_CASE_SEMANTIC_REVIEWER_PROMPT_VERSION,
        platform_probe_version=probe_version,
        regression_case_ids=[r["case_id"] for r in regression_rows],
        evaluator_model_snapshot=f"author={author_model_id};reviewer={reviewer_model_id}",
    )
    _report(progress, f"실행할 검증 상황 {len(suite)}개를 확정했어요.", len(suite), len(suite))


def run_testing(job: dict[str, Any], *, progress: ProgressReporter | None = None, deadline: float | None = None) -> None:
    """§8.10-§8.12 — 고정된 12개 suite로 격리 실행하고 채점한다.

    통과 기준을 못 넘으면 `EvalPipelineError(TRIGGER_ACCURACY_TOO_LOW, ...)`를
    던진다 — 호출부(`registration.py`)가 이를 `CheckingFailure`로 옮겨
    `mark_failed()`로 이어간다.
    """

    if not job.get("test_case_set"):
        raise EvalPipelineError("EVAL_INFRA_ERROR", "검증 질문이 준비되지 않았습니다.")
    deadline = deadline or (time.monotonic() + EVAL_JOB_TIMEOUT_SECONDS)
    _ensure_deadline(deadline)

    document = job["candidate_document"]
    account_id = job["account_id"]
    team_id = job["team_id"]
    suite: list[dict[str, Any]] = job["test_case_set"]
    case_polarity = {c["case_id"]: c["polarity"] for c in suite}

    from services.agent_runtime.skills.service import _render_skill_md, get_personal_skill, list_personal_skills

    _report(progress, "후보 스킬과 함께 비교할 스킬을 준비하고 있어요.")
    candidate_rendered = {
        "name": document["name"],
        "content": _render_skill_md(
            name=document["name"], description=document["description"], body=document["body"],
            frontmatter=document.get("frontmatter"),
        ),
    }
    distractor_rows = [
        skill for skill in list_personal_skills(account_id)
        if skill["name"] != document["name"] and skill.get("enabled", True)
    ]
    distractors = []
    for row in distractor_rows:
        full = get_personal_skill(account_id, row["name"])
        distractors.append(
            {
                "name": full["name"],
                "content": _render_skill_md(
                    name=full["name"], description=full["description"], body=full["body"],
                    frontmatter=full.get("frontmatter"),
                ),
            }
        )

    snapshot = build_ephemeral_skill_store(candidate_document=candidate_rendered, distractor_documents=distractors)
    agent_id, agent_version_id, provider = _default_chat_agent(team_id)

    # 실행 하나마다 ToolLoader/recorder/checkpointer가 독립적이므로 안전하게
    # 병렬화할 수 있다. future는 제출 순서대로 읽어 trace 순서를 결정적으로
    # 유지한다(완료 순서로 모으면 같은 suite도 trace JSON 순서가 달라진다).
    routing_work = [(case, attempt) for case in suite for attempt in range(1, 4)]
    routing_total = len(routing_work)
    # 라우팅 1회가 모델 호출 1회 이상을 사용하므로 제출 전에 전체 예산을 확보한다.
    _reserve_model_calls(job, routing_total)
    _report(progress, "여러 요청에서 스킬이 알맞게 선택되는지 반복 확인하고 있어요.", 0, routing_total)
    with ThreadPoolExecutor(max_workers=EVAL_CONCURRENCY, thread_name_prefix="skill-eval") as pool:
        routing_futures = [
            pool.submit(
                _run_with_provider_slot, provider, deadline,
                lambda case=case, attempt=attempt: run_routing_case(
                    case=case, snapshot=snapshot, agent_id=agent_id,
                    agent_version_id=agent_version_id, account_id=account_id,
                    team_id=team_id, attempts=1, attempt_offset=attempt - 1,
                ),
            )
            for case, attempt in routing_work
        ]
        # 완료 개수는 실제 future 완료 순서로 갱신하되, 최종 결과 배열은 제출
        # 순서로 다시 조립해 trace의 재현성을 유지한다.
        routing_by_index: list[list[Any] | None] = [None] * routing_total
        future_indexes = {future: index for index, future in enumerate(routing_futures)}
        completed = 0
        report_every = max(1, routing_total // 12)
        for future in as_completed(routing_futures):
            _ensure_deadline(deadline)
            routing_by_index[future_indexes[future]] = future.result()
            completed += 1
            if completed == routing_total or completed % report_every == 0:
                _report(
                    progress,
                    "여러 요청에서 스킬이 알맞게 선택되는지 반복 확인하고 있어요.",
                    completed,
                    routing_total,
                )
        routing_results = [result for group in routing_by_index if group is not None for result in group]

    # §8.11 대표 3개 — 직접 요청 1, 문맥·문서 요청 1, 가장 복잡한(도구 필요) 요청 1.
    positive_cases = [c for c in suite if c["polarity"] == "positive"]
    behavior_sample = _select_behavior_sample(positive_cases)

    behavior_total = len(behavior_sample)
    _reserve_model_calls(job, behavior_total)
    _report(progress, "대표 요청에서 결과와 도구 사용이 올바른지 확인하고 있어요.", 0, behavior_total)
    with ThreadPoolExecutor(
        max_workers=min(EVAL_CONCURRENCY, max(1, len(behavior_sample))),
        thread_name_prefix="skill-behavior-eval",
    ) as pool:
        behavior_futures = [
            pool.submit(
                _run_with_provider_slot, provider, deadline,
                lambda case=case: run_behavior_case(
                    case=case, snapshot=snapshot, agent_id=agent_id,
                    agent_version_id=agent_version_id, account_id=account_id, team_id=team_id,
                ),
            )
            for case in behavior_sample
        ]
        behavior_results_by_index: list[Any | None] = [None] * behavior_total
        behavior_future_indexes = {future: index for index, future in enumerate(behavior_futures)}
        behavior_completed = 0
        for future in as_completed(behavior_futures):
            _ensure_deadline(deadline)
            behavior_results_by_index[behavior_future_indexes[future]] = future.result()
            behavior_completed += 1
            _report(
                progress,
                "대표 요청에서 결과와 도구 사용이 올바른지 확인하고 있어요.",
                behavior_completed,
                behavior_total,
            )
        behavior_results = [result for result in behavior_results_by_index if result is not None]

    behavior_reviewer_model_id = ""
    reviewer_provider = _provider_for_model(SKILL_EVAL_REVIEWER_MODEL, team_id)
    case_by_id = {case["case_id"]: case for case in behavior_sample}
    for result in behavior_results:
        assertions = case_by_id[result.case_id].get("behavior_assertions") or []
        if not assertions or result.error or result.deterministic_tool_failures:
            continue
        _reserve_model_calls(job, 1)
        _ensure_deadline(deadline)
        verdicts, behavior_reviewer_model_id = _call_until_deadline(
            lambda: _run_with_provider_slot(
                reviewer_provider, deadline,
                lambda: review_behavior(
                    assertions=assertions,
                    input_messages=case_by_id[result.case_id].get("messages") or [],
                    document_fixtures=case_by_id[result.case_id].get("document_fixtures") or [],
                    final_response=result.final_response,
                    tool_trace=result.tool_calls,
                ),
            ), deadline
        )
        if any(verdict.verdict == "UNCERTAIN" for verdict in verdicts):
            from .behavior_reviewer import merge_uncertain_verdicts

            _reserve_model_calls(job, 1)
            _ensure_deadline(deadline)
            retry_verdicts, behavior_reviewer_model_id = _call_until_deadline(
                lambda: _run_with_provider_slot(
                    reviewer_provider, deadline,
                    lambda: review_behavior(
                        assertions=assertions,
                        input_messages=case_by_id[result.case_id].get("messages") or [],
                        document_fixtures=case_by_id[result.case_id].get("document_fixtures") or [],
                        final_response=result.final_response,
                        tool_trace=result.tool_calls,
                    ),
                ),
                deadline,
            )
            verdicts = merge_uncertain_verdicts(verdicts, retry_verdicts)
        for verdict in verdicts:
            if verdict.verdict != "PASS":
                result.deterministic_tool_failures.append(
                    f"BEHAVIOR_ASSERTION_{verdict.verdict}:{verdict.assertion_index}"
                )

    _report(progress, "실행 결과를 비교해 등록 기준을 만족하는지 확인하고 있어요.")
    score = evaluate(routing_results=routing_results, behavior_results=behavior_results, case_polarity=case_polarity)

    trace_summary = {
        "routing": [
            {"case_id": r.case_id, "attempt": r.attempt, "activated": r.activated_candidate, "error": r.error}
            for r in routing_results
        ],
        "behavior": [
            {"case_id": r.case_id, "activated": r.activated_candidate, "failures": r.deterministic_tool_failures,
             "tool_calls": r.tool_calls, "final_response": r.final_response, "error": r.error}
            for r in behavior_results
        ],
    }
    SkillRegistrationJobRepository.update_eval_fields(
        job["job_id"],
        lease_owner=job["lease_owner"],
        candidate_snapshot_hash=snapshot.candidate_snapshot_hash,
        distractor_snapshot_hashes=snapshot.distractor_snapshot_hashes,
        tool_stub_version=TOOL_STUB_VERSION,
        behavior_reviewer_prompt_version=BEHAVIOR_SEMANTIC_REVIEWER_PROMPT_VERSION,
        evaluator_model_snapshot=(job.get("evaluator_model_snapshot") or "") + (
            f";behavior_reviewer={behavior_reviewer_model_id}" if behavior_reviewer_model_id else ""
        ),
        evaluation_agent_id=agent_id,
        evaluation_agent_version_id=agent_version_id,
        trace_summary=trace_summary,
        metrics=score.to_metrics_dict(),
    )

    if score.infra_error:
        raise EvalPipelineError("EVAL_INFRA_ERROR", "; ".join(score.reasons), score.to_metrics_dict())
    if not score.passed:
        raise EvalPipelineError(
            "TRIGGER_ACCURACY_TOO_LOW", "; ".join(score.reasons) or "트리거 정확도가 기준에 미달했습니다.", score.to_metrics_dict()
        )


__all__ = ["EvalPipelineError", "run_preparing_tests", "run_testing"]
