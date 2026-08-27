"""개인 스킬 검증·등록 — `skill_register` 도구와 설정 화면이 부르는 단일 진입점.

정본: docs/설계 및 구현/3_중간발표 이후/작업기록/Juyeon_Agents_Description/
      03_스킬_검증_등록_설계.md

**여기서부터는 `service.py`의 `create_personal_skill`/`update_personal_skill`을
직접 부르지 않는다.** 그 둘은 여전히 존재하고 여전히 옳지만(개인 Store에
SKILL.md를 실제로 쓰는 마지막 단계는 지금도 그 함수들이 한다), 호출 순서가
바뀌었다 — 승인 직후 즉시 쓰는 대신 `skill_registration_job`에 검증 요청만
남기고, 실제 쓰기는 `python manage.py skill_validation_worker`가 검증을 통과시킨
뒤에만 한다(정본 §6).

`CHECKING`은 형식·충돌을 코드로 검사하고, `PREPARING_TESTS`/`TESTING`은
`skills/evaluation/`의 질문 생성·의미 검토·격리 라우팅·행동 채점 파이프라인을
실행한다. 모든 단계를 통과한 뒤에만 `PUBLISHING`이 개인 SKILL.md를 쓴다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from backend.db.skill_jobs import (
    STAGE_CHECKING,
    STAGE_PREPARING_TESTS,
    STAGE_PUBLISHING,
    STAGE_TESTING,
    SkillRegistrationJobRepository,
    SkillJobLimitExceeded,
)

from .service import (
    SkillError,
    SkillNameConflict,
    SkillNotFound,
    _validate_body,
    _validate_description,
    create_personal_skill,
    get_personal_skill,
    update_personal_skill_and_shared_copy,
    update_personal_skill,
    validate_skill_name,
)
from .versioning import catalog_revision, runtime_profile_version, tool_registry_version, validation_hash


def _evaluation_context(account_id: str) -> tuple[int, str, str]:
    """검증 시작 시점의 개인 카탈로그·런타임·도구 레지스트리 지문."""
    return catalog_revision(account_id), runtime_profile_version(), tool_registry_version()


def _canonical_hash(document: dict[str, Any]) -> str:
    """`SkillDocument` 초안의 해시. 키 순서에 안 흔들리게 `sort_keys=True`로 고정한다.

    `candidate_hash`(통과 직전 재확인, §11 1번)와 `base_content_hash`(동시
    수정 감지, §11 2번)가 둘 다 이 함수 하나를 쓴다 — 계산 방식이 갈리면
    "같은 내용인데 해시가 다르다"는 조용한 버그가 생긴다.
    """

    payload = json.dumps(document, sort_keys=True, ensure_ascii=False)
    import hashlib
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _current_personal_hash(account_id: str, name: str) -> str | None:
    """현재 스킬의 실행 의미 해시. 저장 상태 메타데이터는 제외한다."""

    try:
        current = get_personal_skill(account_id, name)
    except SkillNotFound:
        return None
    return validation_hash(current)


@dataclass(frozen=True)
class EnqueueResult:
    job: dict[str, Any]
    created: bool
    """`False`면 이미 진행 중이던 job을 그대로 돌려준 것이다(§9 "열린 job은 하나")."""


class SkillRegistrationService:
    """`skill_register` 핸들러와 설정 화면 REST 뷰가 공유하는 등록 진입점."""

    @staticmethod
    def enqueue(
        *,
        account_id: str,
        team_id: str | None,
        name: str,
        description: str,
        body: str,
        frontmatter: dict[str, Any] | None = None,
        source_session_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> EnqueueResult:
        """형식이 명백히 틀린 요청은 job조차 만들지 않고 그 자리에서 거부한다.

        이름 규칙·예약어·빈 설명·용량 초과는 워커까지 갈 필요 없이 지금
        이 순간 알 수 있는 문제라 — job 목록에 태어나자마자 실패할 게
        뻔한 항목을 쌓지 않는다. `service.py`가 이미 가진 검사 함수를
        그대로 재사용한다(같은 규칙을 두 곳에 다시 적지 않는다는 원칙,
        `service.py` 모듈 docstring과 같다).

        이름 충돌처럼 **워커가 집는 시점에 다시 확인해야 하는 것**(그
        사이 다른 경로로 같은 이름이 생겼을 수 있다)은 여기서 안 막고
        `run_checking()`에 맡긴다.
        """

        name = name.strip()
        description = description.strip()

        name_error = validate_skill_name(name)
        if name_error:
            raise SkillError(name_error)
        _validate_description(description)
        _validate_body(body)

        candidate_document = {
            "name": name,
            "description": description,
            "body": body,
            "enabled": True,
            **({"frontmatter": frontmatter} if frontmatter is not None else {}),
        }
        candidate_hash = _canonical_hash(candidate_document)
        base_content_hash = _current_personal_hash(account_id, name)
        operation = "UPDATE" if base_content_hash is not None else "CREATE"
        catalog_revision, runtime_profile_version, tool_registry_version = _evaluation_context(account_id)

        try:
            job, created = SkillRegistrationJobRepository.create(
                account_id=account_id, team_id=team_id, skill_name=name, operation=operation,
                candidate_document=candidate_document, candidate_hash=candidate_hash,
                base_content_hash=base_content_hash, source_session_id=source_session_id,
                idempotency_key=idempotency_key, base_catalog_revision=catalog_revision,
                runtime_profile_version=runtime_profile_version, tool_registry_version=tool_registry_version,
            )
        except SkillJobLimitExceeded as exc:
            raise SkillError(str(exc)) from exc
        return EnqueueResult(job=job, created=created)

    @staticmethod
    def retry(
        *, job_id: str, account_id: str, team_id: str | None,
        candidate_document: dict[str, Any] | None = None,
    ) -> EnqueueResult:
        original = SkillRegistrationJobRepository.get(job_id, account_id=account_id)
        if original["status"] not in {"FAILED", "CANCELED"}:
            raise SkillError("실패하거나 취소된 검증만 다시 시작할 수 있습니다.")
        original_document = original["candidate_document"]
        document = dict(candidate_document or original_document)
        # 보완 UI는 사용자가 편집할 수 있는 name/description/body만 보낸다.
        # 업로드 원본의 license·compatibility·allowed-tools·metadata는 화면에
        # 편집란이 없으므로, 새 후보에 명시적으로 들어오지 않은 경우 기존
        # 검증 후보에서 이어 받아야 한다. 그렇지 않으면 "수정" 한 번으로
        # 보이지 않는 frontmatter가 조용히 사라진다.
        if candidate_document is not None:
            if "frontmatter" not in document and "frontmatter" in original_document:
                document["frontmatter"] = original_document["frontmatter"]
            if "enabled" not in document and "enabled" in original_document:
                document["enabled"] = original_document["enabled"]
        document["name"] = str(document.get("name", "")).strip()
        document["description"] = str(document.get("description", "")).strip()
        name_error = validate_skill_name(document["name"])
        if name_error:
            raise SkillError(name_error)
        _validate_description(document["description"])
        _validate_body(document.get("body", ""))
        document.setdefault("enabled", True)
        original_is_create = original["operation"] == "CREATE" or (
            original["operation"] == "RETRY" and original.get("base_content_hash") is None
        )
        if not original_is_create and document["name"] != original["skill_name"]:
            raise SkillError("기존 스킬을 수정하는 검증에서는 이름을 바꿀 수 없습니다. 새 이름은 새 스킬로 만들어 주세요.")
        # 신규 등록의 RETRY가 우연히 기존 이름을 가리켜도 UPDATE로 승격하지
        # 않는다. CHECKING에서 이름 충돌로 멈춰 기존 스킬을 보호해야 한다.
        base_content_hash = (
            None if original_is_create
            else _current_personal_hash(account_id, original["skill_name"])
        )
        catalog_revision, runtime_profile_version, tool_registry_version = _evaluation_context(account_id)
        try:
            job, created = SkillRegistrationJobRepository.create(
                account_id=account_id, team_id=team_id, skill_name=document["name"], operation="RETRY",
                candidate_document=document, candidate_hash=_canonical_hash(document),
                base_content_hash=base_content_hash,
                source_session_id=original.get("source_session_id"), idempotency_key=None,
                retry_of_job_id=str(original["job_id"]), base_catalog_revision=catalog_revision,
                runtime_profile_version=runtime_profile_version, tool_registry_version=tool_registry_version,
            )
        except SkillJobLimitExceeded as exc:
            raise SkillError(str(exc)) from exc
        return EnqueueResult(job=job, created=created)


class CheckingFailure(Exception):
    """CHECKING 단계 실패. `failure_code`/`failure_summary`/`failure_details`를
    그대로 `SkillRegistrationJobRepository.mark_failed()`에 넘긴다."""

    def __init__(self, code: str, summary: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(summary)
        self.code = code
        self.summary = summary
        self.details = details or {}


def _suggest_names(document: dict[str, Any], job: dict[str, Any]) -> list[str]:
    """후보 내용에 맞는 대안을 모델로 만들되, 충돌 이름을 자동 변경하지 않는다."""

    from .evaluation.name_suggester import suggest_names
    from .evaluation.config import EVAL_JOB_TIMEOUT_SECONDS, SKILL_EVAL_AUTHOR_MODEL
    from .evaluation.pipeline import _provider_for_model, _reserve_model_calls, _run_with_provider_slot
    import time

    try:
        _reserve_model_calls(job, 1)
        deadline = job.get("_eval_deadline") or (time.monotonic() + EVAL_JOB_TIMEOUT_SECONDS)
        provider = _provider_for_model(SKILL_EVAL_AUTHOR_MODEL, job["team_id"])
        return _run_with_provider_slot(provider, deadline, lambda: suggest_names(document))
    except Exception:
        # 추천 실패는 이름 충돌이라는 본래 검사 결과를 가리면 안 된다.
        return []


def run_checking(job: dict[str, Any]) -> None:
    """CHECKING 단계. 실패하면 `CheckingFailure`를 던진다 — 호출부(워커)가 잡아
    `mark_failed()`로 옮긴다."""

    document = job["candidate_document"]
    name = document["name"]

    expected_context = (
        job.get("base_catalog_revision"), job.get("runtime_profile_version"), job.get("tool_registry_version")
    )
    if all(value is not None for value in expected_context) and _evaluation_context(job["account_id"]) != expected_context:
        raise CheckingFailure(
            "STALE_EVAL_CONTEXT",
            "검증 중 스킬 목록이나 실행 환경이 변경되었습니다. 현재 환경에서 다시 검증해 주세요.",
            {"retryable": True},
        )
    description = document["description"]
    body = document["body"]

    name_error = validate_skill_name(name)
    if name_error:
        raise CheckingFailure("INVALID_SKILL_FORMAT", name_error)
    try:
        _validate_description(description)
        _validate_body(body)
    except SkillError as exc:
        raise CheckingFailure("INVALID_SKILL_FORMAT", str(exc)) from exc

    is_create = job["operation"] == "CREATE" or (
        job["operation"] == "RETRY" and job.get("base_content_hash") is None
    )
    if is_create:
        try:
            get_personal_skill(job["account_id"], name)
        except SkillNotFound:
            pass
        else:
            raise CheckingFailure(
                "SKILL_NAME_CONFLICT",
                f"이미 '{name}' 이름의 스킬이 있습니다.",
                {"suggested_names": _suggest_names(document, job)},
            )
    else:  # UPDATE
        current_hash = _current_personal_hash(job["account_id"], name)
        if current_hash != job["base_content_hash"]:
            raise CheckingFailure(
                "STALE_CANDIDATE",
                "검증 중 다른 곳에서 같은 스킬이 먼저 바뀌었습니다. 최신 내용으로 다시 검증해 주세요.",
            )


def run_preparing_tests(
    job: dict[str, Any],
    *,
    progress: Callable[[str, int | None, int | None], None] | None = None,
    deadline: float | None = None,
) -> None:
    """정본 §7의 `PREPARING_TESTS` 단계 — §8.3-§8.9(질문 생성·구조/의미 검토·
    플랫폼 고정 probe·회귀 케이스 혼합·최종 12개 구성)를 전부 수행한다.

    2026-08-26 연결 — `evaluation/pipeline.py`가 실제 구현이고, 여기서는
    `EvalPipelineError`를 이 모듈의 공통 실패 타입(`CheckingFailure`)으로
    옮기기만 한다.
    """

    from .evaluation.pipeline import EvalPipelineError
    from .evaluation.pipeline import run_preparing_tests as _run_preparing_tests

    try:
        _run_preparing_tests(job, progress=progress, deadline=deadline or job.get("_eval_deadline"))
    except EvalPipelineError as exc:
        raise CheckingFailure(exc.code, exc.summary, exc.details) from exc


def run_testing(
    job: dict[str, Any],
    *,
    progress: Callable[[str, int | None, int | None], None] | None = None,
    deadline: float | None = None,
) -> None:
    """정본 §7의 `TESTING` 단계 — §8.10-§8.12(격리 미니 에이전트, distractor,
    도구 stub, HITL 재생, recall/precision 판정)를 전부 수행한다.

    통과 기준을 못 넘으면 `TRIGGER_ACCURACY_TOO_LOW`로 실패한다 — CHECKING이
    잡는 형식 문제와 달리, 이 단계는 "실제 상황에서 이 스킬이 골라지는가"
    자체를 재는 단계다(정본 §8.12).
    """

    from .evaluation.pipeline import EvalPipelineError
    from .evaluation.pipeline import run_testing as _run_testing

    try:
        _run_testing(job, progress=progress, deadline=deadline or job.get("_eval_deadline"))
    except EvalPipelineError as exc:
        raise CheckingFailure(exc.code, exc.summary, exc.details) from exc


def run_publishing(job: dict[str, Any]) -> dict[str, Any]:
    """PUBLISHING 단계. 통과 절차(§11)를 그대로 따른다.

    1. `candidate_hash` 재확인(§11 1) — CHECKING과 PUBLISHING 사이에 워커가
       바뀌거나 재시작됐어도 job 행에 저장된 해시가 그대로면 안전하다.
    2. UPDATE면 `base_content_hash` 재확인(§11 2) — CHECKING과 PUBLISHING
       사이의 아주 짧은 창에서도 동시 수정이 있을 수 있다.
    3. UPDATE는 수정 전 활성 상태를 유지한 채 쓴다(§11 5).
    """

    document = job["candidate_document"]
    name = document["name"]

    expected_context = (
        job.get("base_catalog_revision"), job.get("runtime_profile_version"), job.get("tool_registry_version")
    )
    if all(value is not None for value in expected_context) and _evaluation_context(job["account_id"]) != expected_context:
        raise CheckingFailure(
            "STALE_EVAL_CONTEXT",
            "검증 중 스킬 목록이나 실행 환경이 변경되었습니다. 현재 환경에서 다시 검증해 주세요.",
            {"retryable": True},
        )

    current_hash = _canonical_hash(document)
    if current_hash != job["candidate_hash"]:
        raise CheckingFailure("STALE_CANDIDATE", "검증한 초안과 지금 등록하려는 내용이 다릅니다.")

    is_create = job["operation"] == "CREATE" or (
        job["operation"] == "RETRY" and job.get("base_content_hash") is None
    )
    if is_create:
        try:
            get_personal_skill(job["account_id"], name)
        except SkillNotFound:
            pass
        else:
            raise CheckingFailure(
                "SKILL_NAME_CONFLICT",
                f"검증하는 동안 '{name}' 이름의 스킬이 새로 만들어졌습니다.",
                {"suggested_names": _suggest_names(document, job)},
            )
        receipt = {
            "validation_state": "VERIFIED",
            "validated_hash": validation_hash(document),
            "source_job_id": str(job["job_id"]),
            "runtime_profile_version": job.get("runtime_profile_version"),
            "tool_registry_version": job.get("tool_registry_version"),
        }
        frontmatter = document.get("frontmatter") or {}
        metadata = frontmatter.get("metadata") if isinstance(frontmatter.get("metadata"), dict) else {}
        return create_personal_skill(
            job["account_id"],
            team_id=job["team_id"],
            name=name,
            description=document["description"],
            body=document["body"],
            frontmatter=document.get("frontmatter"),
            validation_receipt=receipt,
            imported_from_team_id=metadata.get("imported_from_team_id"),
            imported_from_skill_name=metadata.get("imported_from_skill_name"),
        )

    try:
        current = get_personal_skill(job["account_id"], name)
    except SkillNotFound as exc:
        raise CheckingFailure("STALE_CANDIDATE", "수정하려던 스킬이 그 사이 삭제됐습니다.") from exc
    current_content_hash = validation_hash(current)
    if current_content_hash != job["base_content_hash"]:
        raise CheckingFailure("STALE_CANDIDATE", "검증 중 다른 곳에서 같은 스킬이 먼저 바뀌었습니다.")

    receipt = {
        "validation_state": "VERIFIED",
        "validated_hash": validation_hash(document),
        "source_job_id": str(job["job_id"]),
        "runtime_profile_version": job.get("runtime_profile_version"),
        "tool_registry_version": job.get("tool_registry_version"),
    }
    return update_personal_skill_and_shared_copy(
        job["account_id"],
        team_id=job["team_id"], name=name,
        description=document["description"],
        body=document["body"],
        enabled=current["enabled"],  # 수정 전 활성 상태를 유지한다(§11 5) — 자동 활성화하지 않는다.
        frontmatter=document.get("frontmatter"),
        validation_receipt=receipt,
    )


__all__ = [
    "EnqueueResult",
    "SkillRegistrationService",
    "CheckingFailure",
    "STAGE_CHECKING",
    "STAGE_PREPARING_TESTS",
    "STAGE_TESTING",
    "STAGE_PUBLISHING",
    "run_checking",
    "run_preparing_tests",
    "run_testing",
    "run_publishing",
]
