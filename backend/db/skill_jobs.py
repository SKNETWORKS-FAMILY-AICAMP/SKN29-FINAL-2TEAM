"""`skill_registration_job` 저장소.

정본: docs/설계 및 구현/3_중간발표 이후/작업기록/Juyeon_Agents_Description/
      03_스킬_검증_등록_설계.md §9-§11 ("검증 job 저장 구조"/"워커 배포와
      운영"/"통과·실패·동시 수정")

`backend/db/repositories.py`의 `MemberInviteRepository`/`ToolCallIdempotencyRepository`
와 같은 패턴이다 — Django ORM을 쓰지 않는 이 저장소의 raw SQL + repository
클래스 관례를 그대로 따른다(`apps/projects/models.py` 참고).

**"열린 job은 하나"라는 제약을 두 층에서 지킨다.** `create()`는 INSERT
전에 먼저 조회해서 있으면 그 job을 그대로 돌려준다(정상 경로 — 채팅
`skill_register` 핸들러가 매번 새 job을 만드는 걸 막는다). `DB/migrations/
2026-08-26_skill_registration_job.sql`의 부분 유니크 인덱스
(`ux_skill_registration_job_open_per_name`)는 그 조회와 INSERT 사이의
경합을 잡는 최종 방어선이다 — 두 요청이 동시에 들어와도 하나만 성공하고,
진 쪽은 `UniqueViolation`을 잡아 방금 이긴 job을 다시 읽어 돌려준다.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import psycopg
from django.conf import settings
from psycopg.types.json import Jsonb

from .connection import database_connection
from .errors import RecordNotFound

#: `DB/migrations/2026-08-26_skill_registration_job.sql`의 CHECK와 정확히 같아야
#: 한다 — 여기서만 값을 만들면 오탈자가 나도 파이썬에서는 안 걸리고 INSERT
#: 시점에야 `CheckViolation`으로 드러난다. 상수로 한 번만 적어 그 위험을 없앤다.
STATUS_QUEUED = "QUEUED"
STATUS_RUNNING = "RUNNING"
STATUS_SUCCEEDED = "SUCCEEDED"
STATUS_FAILED = "FAILED"
STATUS_CANCEL_REQUESTED = "CANCEL_REQUESTED"
STATUS_CANCELED = "CANCELED"

#: "열린" 상태 — 같은 이름에 하나만 허용되는 대상, 그리고 워커가 회수 대상으로
#: 볼 수 있는 상태(CANCEL_REQUESTED는 회수 대상은 아니지만 "열려" 있다).
OPEN_STATUSES = (STATUS_QUEUED, STATUS_RUNNING, STATUS_CANCEL_REQUESTED)
TERMINAL_STATUSES = (STATUS_SUCCEEDED, STATUS_FAILED, STATUS_CANCELED)

STAGE_WAITING = "WAITING"
STAGE_CHECKING = "CHECKING"
STAGE_PREPARING_TESTS = "PREPARING_TESTS"
STAGE_TESTING = "TESTING"
STAGE_PUBLISHING = "PUBLISHING"

#: 화면에 그대로 보여줄 5단계 순서(§7). 워커·API·프런트가 전부 이 순서를
#: 공유해야 진행 카드의 "1-2-3-4-5"가 실제 진행과 어긋나지 않는다.
STAGE_ORDER = (
    STAGE_WAITING,
    STAGE_CHECKING,
    STAGE_PREPARING_TESTS,
    STAGE_TESTING,
    STAGE_PUBLISHING,
)


class SkillJobNotFound(RecordNotFound):
    pass


class SkillJobLeaseLost(RecordNotFound):
    """워커가 heartbeat/stage 갱신을 시도했는데 이미 다른 워커가 lease를 가져갔다.

    lease_expires_at이 지나 다른 워커가 회수한 뒤, 원래 워커가 뒤늦게 자기가
    아직 주인인 줄 알고 쓰기를 시도하는 경우다 — 조용히 덮어쓰면 안 되므로
    호출부가 반드시 실행을 멈추고 빠져나가야 한다는 신호로 예외를 던진다.
    """


class SkillJobLimitExceeded(Exception):
    pass


class SkillEvalBudgetExceeded(Exception):
    pass


class SkillRegistrationJobRepository:
    @staticmethod
    def _find_open_for_name(cursor, *, account_id: str, skill_name: str) -> dict[str, Any] | None:
        cursor.execute(
            """
            SELECT * FROM skill_registration_job
             WHERE account_id = %s AND skill_name = %s AND status = ANY(%s)
             ORDER BY created_at DESC
             LIMIT 1
            """,
            (account_id, skill_name, list(OPEN_STATUSES)),
        )
        return cursor.fetchone()

    @staticmethod
    def create(
        *,
        account_id: str,
        team_id: str | None,
        skill_name: str,
        operation: str,
        candidate_document: dict[str, Any],
        candidate_hash: str,
        base_content_hash: str | None,
        source_session_id: str | None,
        idempotency_key: str | None,
        retry_of_job_id: str | None = None,
        base_catalog_revision: int | None = None,
        runtime_profile_version: str | None = None,
        tool_registry_version: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        """`(job, created)`을 돌려준다. `created=False`면 기존 job을 그대로 반환한 것이다.

        호출부(`SkillRegistrationService.enqueue()`)는 이 값으로 "새로 만들었다"와
        "이미 진행 중이던 걸 돌려줬다"를 구분해 채팅 응답 문구를 다르게 낼 수 있다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                if idempotency_key:
                    cursor.execute(
                        "SELECT * FROM skill_registration_job WHERE idempotency_key = %s",
                        (idempotency_key,),
                    )
                    existing = cursor.fetchone()
                    if existing is not None:
                        return existing, False

                existing = SkillRegistrationJobRepository._find_open_for_name(
                    cursor, account_id=account_id, skill_name=skill_name
                )
                if existing is not None:
                    return existing, False

                # 계정별 생성 경합까지 막기 위해 transaction advisory lock 아래에서 센다.
                cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"skill-job:{account_id}",))
                cursor.execute(
                    "SELECT count(*) AS count FROM skill_registration_job WHERE account_id = %s AND status = ANY(%s)",
                    (account_id, list(OPEN_STATUSES)),
                )
                if int(cursor.fetchone()["count"]) >= settings.SKILL_VALIDATION_ACCOUNT_OPEN_JOB_LIMIT:
                    raise SkillJobLimitExceeded(
                        f"한 번에 진행할 수 있는 스킬 검증은 {settings.SKILL_VALIDATION_ACCOUNT_OPEN_JOB_LIMIT}개입니다."
                    )

                try:
                    cursor.execute(
                        """
                        INSERT INTO skill_registration_job (
                            account_id, team_id, skill_name, operation,
                            candidate_document, candidate_hash, base_content_hash,
                            source_session_id, idempotency_key, retry_of_job_id,
                            attempt, base_catalog_revision, runtime_profile_version,
                            tool_registry_version
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING *
                        """,
                        (
                            account_id,
                            team_id,
                            skill_name,
                            operation,
                            Jsonb(candidate_document),
                            candidate_hash,
                            base_content_hash,
                            source_session_id,
                            idempotency_key,
                            retry_of_job_id,
                            1 if retry_of_job_id is None else _next_attempt(cursor, retry_of_job_id),
                            base_catalog_revision,
                            runtime_profile_version,
                            tool_registry_version,
                        ),
                    )
                    return cursor.fetchone(), True
                except psycopg.errors.UniqueViolation:
                    # 조회와 INSERT 사이에 다른 요청이 먼저 만들었다 — 그 job을 돌려준다.
                    connection.rollback()
                    with connection.cursor() as retry_cursor:
                        existing = SkillRegistrationJobRepository._find_open_for_name(
                            retry_cursor, account_id=account_id, skill_name=skill_name
                        )
                    if existing is None:
                        raise
                    return existing, False

    @staticmethod
    def get(job_id: str, *, account_id: str | None = None) -> dict[str, Any]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                if account_id is None:
                    cursor.execute("SELECT * FROM skill_registration_job WHERE job_id = %s", (job_id,))
                else:
                    cursor.execute(
                        "SELECT * FROM skill_registration_job WHERE job_id = %s AND account_id = %s",
                        (job_id, account_id),
                    )
                row = cursor.fetchone()
        if row is None:
            raise SkillJobNotFound("검증 작업을 찾을 수 없습니다.")
        return row

    @staticmethod
    def list_for_account(account_id: str, *, open_only: bool = False) -> list[dict[str, Any]]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                if open_only:
                    cursor.execute(
                        """
                        SELECT * FROM skill_registration_job
                         WHERE account_id = %s AND status = ANY(%s)
                           AND NOT EXISTS (
                               SELECT 1 FROM skill_registration_job child
                                WHERE child.retry_of_job_id = skill_registration_job.job_id
                           )
                         ORDER BY created_at DESC
                        """,
                        (account_id, list(OPEN_STATUSES)),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT * FROM skill_registration_job
                         WHERE account_id = %s
                           AND NOT EXISTS (
                               SELECT 1 FROM skill_registration_job child
                                WHERE child.retry_of_job_id = skill_registration_job.job_id
                           )
                         ORDER BY created_at DESC
                         LIMIT 100
                        """,
                        (account_id,),
                    )
                return cursor.fetchall()

    # ------------------------------------------------------------------
    # 워커 전용 — `python manage.py skill_validation_worker`만 부른다.
    # ------------------------------------------------------------------

    @staticmethod
    def claim_next(*, lease_owner: str, lease_seconds: int) -> dict[str, Any] | None:
        """`FOR UPDATE SKIP LOCKED`로 다음 job 하나를 가져온다.

        대상은 `QUEUED`이거나, lease가 만료된 `RUNNING`(죽은 워커가 들고 있던
        것 — §10 "워커가 하나도 없을 때"가 아니라 "워커 하나가 죽었을 때"의
        회수다)이다. `SKIP LOCKED`라 여러 워커가 동시에 이 질의를 돌려도 같은
        행을 두 번 집지 않는다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT * FROM skill_registration_job
                    WHERE status = %s
                       AND (
                           team_id IS NULL OR (
                               SELECT count(*) FROM skill_registration_job running
                                WHERE running.team_id = skill_registration_job.team_id
                                  AND running.status = %s
                           ) < %s
                       )
                        OR (status = %s AND lease_expires_at < now())
                     ORDER BY created_at
                     LIMIT 1
                     FOR UPDATE SKIP LOCKED
                    """,
                    (
                        STATUS_QUEUED,
                        STATUS_RUNNING,
                        settings.SKILL_VALIDATION_TEAM_RUNNING_JOB_LIMIT,
                        STATUS_RUNNING,
                    ),
                )
                row = cursor.fetchone()
                if row is None:
                    return None
                cursor.execute(
                    """
                    UPDATE skill_registration_job
                       SET status = %s,
                           lease_owner = %s,
                           lease_expires_at = now() + (%s || ' seconds')::interval,
                           heartbeat_at = now(),
                           started_at = COALESCE(started_at, now()),
                           updated_at = now()
                     WHERE job_id = %s
                     RETURNING *
                    """,
                    (STATUS_RUNNING, lease_owner, lease_seconds, row["job_id"]),
                )
                return cursor.fetchone()

    @staticmethod
    def heartbeat(job_id: str, *, lease_owner: str, lease_seconds: int) -> None:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE skill_registration_job
                       SET heartbeat_at = now(),
                           lease_expires_at = now() + (%s || ' seconds')::interval,
                           updated_at = now()
                     WHERE job_id = %s AND lease_owner = %s AND status = %s
                    """,
                    (lease_seconds, job_id, lease_owner, STATUS_RUNNING),
                )
                if cursor.rowcount == 0:
                    raise SkillJobLeaseLost("이미 다른 워커가 이 작업을 가져갔습니다.")

    @staticmethod
    def advance_stage(job_id: str, stage: str, *, lease_owner: str) -> None:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE skill_registration_job
                       SET stage = %s, updated_at = now()
                     WHERE job_id = %s AND lease_owner = %s AND status = %s
                    """,
                    (stage, job_id, lease_owner, STATUS_RUNNING),
                )
                if cursor.rowcount == 0:
                    raise SkillJobLeaseLost("이미 다른 워커가 이 작업을 가져갔습니다.")

    @staticmethod
    def update_progress(
        job_id: str,
        *,
        lease_owner: str,
        message: str,
        current: int | None = None,
        total: int | None = None,
    ) -> None:
        """현재 세부 작업과 최근 이력을 저장한다.

        LLM의 내부 사고과정은 받지 않는다. 워커가 실제로 시작하거나 완료한
        작업만 짧은 사용자 문장으로 기록한다. 이벤트는 한 job에 수십 건
        수준이라 JSONB 배열로 충분하고, API에서는 최근 항목만 돌려준다.
        """

        event = {
            "message": message,
            "at": datetime.now(timezone.utc).isoformat(),
            "current": current,
            "total": total,
        }
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE skill_registration_job
                       SET progress_message = %s,
                           progress_current = %s,
                           progress_total = %s,
                           progress_events = COALESCE(progress_events, '[]'::jsonb) || %s,
                           updated_at = now()
                     WHERE job_id = %s AND lease_owner = %s AND status = %s
                    """,
                    (
                        message,
                        current,
                        total,
                        Jsonb([event]),
                        job_id,
                        lease_owner,
                        STATUS_RUNNING,
                    ),
                )
                if cursor.rowcount == 0:
                    raise SkillJobLeaseLost("이미 다른 워커가 이 작업을 가져갔습니다.")

    @staticmethod
    def is_cancel_requested(job_id: str) -> bool:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT status FROM skill_registration_job WHERE job_id = %s", (job_id,)
                )
                row = cursor.fetchone()
                return row is not None and row["status"] == STATUS_CANCEL_REQUESTED

    #: `update_eval_fields()`가 건드릴 수 있는 컬럼만 화이트리스트로 둔다 —
    #: 동적으로 SET 절을 만들 때 컬럼명이 사용자 입력에서 오지 않는다는 걸
    #: 이 목록 하나로 보장한다(`DB/migrations/2026-08-26_skill_eval_columns.sql`과
    #: 정확히 같은 이름이어야 한다).
    _EVAL_FIELDS = frozenset(
        {
            "evaluation_agent_id",
            "evaluation_agent_version_id",
            "base_catalog_revision",
            "runtime_profile_version",
            "tool_registry_version",
            "test_case_set",
            "eval_suite_version",
            "generator_prompt_version",
            "semantic_reviewer_prompt_version",
            "behavior_reviewer_prompt_version",
            "evaluator_model_snapshot",
            "platform_probe_version",
            "regression_case_ids",
            "candidate_snapshot_hash",
            "distractor_snapshot_hashes",
            "tool_stub_version",
            "trace_summary",
            "metrics",
        }
    )

    @staticmethod
    def update_eval_fields(job_id: str, *, lease_owner: str, **fields: Any) -> None:
        """§8.13 재현성 컬럼을 부분 갱신한다. `run_preparing_tests`/`run_testing`이
        생성 프롬프트 버전, distractor 해시, 채점 결과 같은 걸 각 단계가 끝날
        때마다 여기로 남긴다 — 한 번에 다 모아 두지 않는 이유는, 중간에 실패해도
        "어디까지는 확정됐는지"가 DB에 남아야 실패 상세에 정확히 보여줄 수
        있어서다.
        """

        unknown = set(fields) - SkillRegistrationJobRepository._EVAL_FIELDS
        if unknown:
            raise ValueError(f"update_eval_fields가 모르는 컬럼입니다: {sorted(unknown)}")
        if not fields:
            return

        json_columns = {
            "test_case_set",
            "distractor_snapshot_hashes",
            "trace_summary",
            "metrics",
        }
        set_clauses = []
        params: list[Any] = []
        for name, value in fields.items():
            set_clauses.append(f"{name} = %s")
            params.append(Jsonb(value) if name in json_columns and value is not None else value)
        params.extend([job_id, lease_owner])

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    UPDATE skill_registration_job
                       SET {', '.join(set_clauses)}, updated_at = now()
                     WHERE job_id = %s AND lease_owner = %s
                    """,
                    params,
                )
                if cursor.rowcount == 0:
                    raise SkillJobLeaseLost("이미 다른 워커가 이 작업을 가져갔습니다.")

    @staticmethod
    def consume_eval_budget(job_id: str, *, lease_owner: str, model_calls: int) -> dict[str, Any]:
        with database_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE skill_registration_job
                   SET model_call_count = model_call_count + %s,
                       estimated_cost_usd = estimated_cost_usd + (%s * %s),
                       updated_at = now()
                 WHERE job_id = %s AND lease_owner = %s AND status = %s
                   AND model_call_count + %s <= %s
                 RETURNING model_call_count, estimated_cost_usd
                """,
                (
                    model_calls,
                    model_calls,
                    settings.SKILL_VALIDATION_ESTIMATED_COST_PER_CALL_USD,
                    job_id,
                    lease_owner,
                    STATUS_RUNNING,
                    model_calls,
                    settings.SKILL_VALIDATION_MAX_MODEL_CALLS,
                ),
            )
            row = cursor.fetchone()
        if row is None:
            raise SkillEvalBudgetExceeded("검증에 허용된 모델 호출 예산을 초과했습니다.")
        return row

    @staticmethod
    def cleanup_expired(*, succeeded_days: int, terminal_days: int, dry_run: bool) -> dict[str, int]:
        with database_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT count(*) AS count FROM skill_registration_job
                    WHERE status = %s AND completed_at < now() - (%s || ' days')::interval
                      AND candidate_document ? 'body'""",
                (STATUS_SUCCEEDED, succeeded_days),
            )
            redact_count = int(cursor.fetchone()["count"])
            cursor.execute(
                """SELECT count(*) AS count FROM skill_registration_job
                    WHERE status = ANY(%s) AND completed_at < now() - (%s || ' days')::interval""",
                ([STATUS_FAILED, STATUS_CANCELED], terminal_days),
            )
            delete_count = int(cursor.fetchone()["count"])
            if dry_run:
                connection.rollback()
                return {"redacted": redact_count, "deleted": delete_count}
            cursor.execute(
                """
                UPDATE skill_registration_job
                   SET candidate_document = candidate_document - 'body', trace_summary = NULL, updated_at = now()
                 WHERE status = %s AND completed_at < now() - (%s || ' days')::interval
                """,
                (STATUS_SUCCEEDED, succeeded_days),
            )
            cursor.execute(
                """DELETE FROM skill_registration_job
                    WHERE status = ANY(%s) AND completed_at < now() - (%s || ' days')::interval""",
                ([STATUS_FAILED, STATUS_CANCELED], terminal_days),
            )
        return {"redacted": redact_count, "deleted": delete_count}

    @staticmethod
    def mark_succeeded(
        job_id: str, *, lease_owner: str, metrics: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE skill_registration_job
                       SET status = %s, stage = %s, completed_at = now(), updated_at = now(),
                           metrics = COALESCE(%s, metrics),
                           progress_message = '검증을 마치고 스킬을 등록했어요.',
                           progress_current = NULL,
                           progress_total = NULL
                     WHERE job_id = %s AND lease_owner = %s
                     RETURNING *
                    """,
                    (
                        STATUS_SUCCEEDED,
                        STAGE_PUBLISHING,
                        Jsonb(metrics) if metrics is not None else None,
                        job_id,
                        lease_owner,
                    ),
                )
                row = cursor.fetchone()
        if row is None:
            raise SkillJobLeaseLost("이미 다른 워커가 이 작업을 가져갔습니다.")
        return row

    @staticmethod
    def mark_failed(
        job_id: str,
        *,
        lease_owner: str,
        failure_code: str,
        failure_summary: str,
        failure_details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE skill_registration_job
                       SET status = %s, failure_code = %s, failure_summary = %s,
                           failure_details = %s, completed_at = now(), updated_at = now(),
                           progress_message = '검증을 완료하지 못했어요.',
                           progress_current = NULL,
                           progress_total = NULL
                     WHERE job_id = %s AND lease_owner = %s
                     RETURNING *
                    """,
                    (
                        STATUS_FAILED,
                        failure_code,
                        failure_summary,
                        Jsonb(failure_details or {}),
                        job_id,
                        lease_owner,
                    ),
                )
                row = cursor.fetchone()
        if row is None:
            raise SkillJobLeaseLost("이미 다른 워커가 이 작업을 가져갔습니다.")
        return row

    @staticmethod
    def mark_canceled(job_id: str, *, lease_owner: str) -> dict[str, Any]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE skill_registration_job
                       SET status = %s, completed_at = now(), updated_at = now(),
                           progress_message = '검증이 취소되었어요.',
                           progress_current = NULL,
                           progress_total = NULL
                     WHERE job_id = %s AND lease_owner = %s
                     RETURNING *
                    """,
                    (STATUS_CANCELED, job_id, lease_owner),
                )
                row = cursor.fetchone()
        if row is None:
            raise SkillJobLeaseLost("이미 다른 워커가 이 작업을 가져갔습니다.")
        return row

    # ------------------------------------------------------------------
    # 사용자 전용 — 취소·삭제 요청(§14 API).
    # ------------------------------------------------------------------

    @staticmethod
    def request_cancel(job_id: str, *, account_id: str) -> dict[str, Any]:
        """`QUEUED`는 그 자리에서 바로 `CANCELED`로 끝낸다 — 아직 아무 워커도
        붙잡지 않았으니 안전하게 즉시 끝낼 수 있다. `RUNNING`은 `CANCEL_REQUESTED`
        로만 표시한다 — 워커가 다음 `advance_stage()`/`heartbeat()` 시점에
        `is_cancel_requested()`로 이 값을 보고 스스로 `CANCELED`로 마무리한다
        (`skill_validation_worker.py`의 `advance()` 참고).

        **`QUEUED`도 `CANCEL_REQUESTED`로만 두면 안 된다.** `claim_next()`는
        `QUEUED`/만료된 `RUNNING`만 집는다 — `CANCEL_REQUESTED`는 그 대상이
        아니라서, 아직 아무도 안 집은 job을 그렇게 두면 어떤 워커도 다시
        건드리지 않아 영원히 `CANCEL_REQUESTED`에 머문다(취소도, 삭제도
        안 되는 상태).
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE skill_registration_job
                       SET status = CASE WHEN status = %s THEN %s ELSE %s END,
                           cancel_requested_at = now(),
                           completed_at = CASE WHEN status = %s THEN now() ELSE completed_at END,
                           progress_message = CASE
                               WHEN status = %s THEN '검증이 취소되었어요.'
                               ELSE '진행 중인 작업을 마치고 검증을 취소하고 있어요.'
                           END,
                           progress_current = NULL,
                           progress_total = NULL,
                           updated_at = now()
                     WHERE job_id = %s AND account_id = %s AND status = ANY(%s)
                     RETURNING *
                    """,
                    (
                        STATUS_QUEUED,
                        STATUS_CANCELED,
                        STATUS_CANCEL_REQUESTED,
                        STATUS_QUEUED,
                        STATUS_QUEUED,
                        job_id,
                        account_id,
                        [STATUS_QUEUED, STATUS_RUNNING],
                    ),
                )
                row = cursor.fetchone()
        if row is None:
            raise SkillJobNotFound("취소할 수 있는 진행 중인 작업이 없습니다.")
        return row

    @staticmethod
    def delete_terminal(job_id: str, *, account_id: str) -> None:
        """실패·취소로 끝난 job만 지운다 — 진행 중인 job은 취소부터 해야 한다."""

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM skill_registration_job
                     WHERE job_id = %s AND account_id = %s AND status = ANY(%s)
                    """,
                    (job_id, account_id, [STATUS_FAILED, STATUS_CANCELED]),
                )
                deleted = cursor.rowcount
        if deleted == 0:
            raise SkillJobNotFound("삭제할 수 있는 종료된 작업이 없습니다.")


def _next_attempt(cursor, retry_of_job_id: str) -> int:
    cursor.execute(
        "SELECT attempt FROM skill_registration_job WHERE job_id = %s", (retry_of_job_id,)
    )
    row = cursor.fetchone()
    return (row["attempt"] + 1) if row else 1


__all__ = [
    "SkillRegistrationJobRepository", "SkillJobNotFound", "SkillJobLeaseLost",
    "SkillJobLimitExceeded", "SkillEvalBudgetExceeded",
]
