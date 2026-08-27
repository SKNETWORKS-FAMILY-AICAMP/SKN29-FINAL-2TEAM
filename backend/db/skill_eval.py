"""스킬 사용 피드백과 승인된 회귀 평가 사례 저장소.

채팅의 피드백 버튼은 원문 대신 메시지 참조와 trace hash만 남긴다. 운영자가
식별정보를 제거한 실행 가능한 사례로 전환하고 승인해야 평가 suite에 들어간다.
`APPROVED` 상태만 `EvalSuiteComposer`가 가져다 쓴다(`evaluation/suite.py`).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .connection import database_connection
from .errors import RecordNotFound


class SkillEvalRegressionCaseNotFound(RecordNotFound):
    pass


class SkillEvalFeedbackNotFound(RecordNotFound):
    pass


class SkillEvalFeedbackRepository:
    @staticmethod
    def create(
        *, message_id: str, account_id: str, feedback_kind: str,
        expected_skill: str | None, note: str | None,
    ) -> tuple[dict[str, Any], bool]:
        """에이전트 답변 소유권을 확인하고 원문 대신 참조와 hash만 저장한다."""

        with database_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT m.message_id, m.session_id, m.content, s.team_id
                     FROM chat_message m
                     JOIN chat_session s ON s.session_id = m.session_id
                    WHERE m.message_id::text = %s AND m.role = 'agent' AND s.account_id = %s""",
                (message_id, account_id),
            )
            source = cursor.fetchone()
            if source is None:
                raise SkillEvalFeedbackNotFound("신고할 답변을 찾을 수 없습니다.")
            events = (source.get("content") or {}).get("events") or []
            observed = sorted({
                str(event.get("skill_name")) for event in events
                if isinstance(event, dict) and event.get("type") == "skill_applied" and event.get("skill_name")
            })
            trace_hash = hashlib.sha256(
                json.dumps(source.get("content") or {}, sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest()
            cursor.execute(
                """INSERT INTO skill_eval_feedback (
                       message_id, session_id, account_id, team_id, feedback_kind,
                       observed_skills, expected_skill, note, source_trace_hash
                   ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (message_id, account_id, feedback_kind) DO NOTHING
                   RETURNING *""",
                (
                    message_id, source["session_id"], account_id, source["team_id"],
                    feedback_kind, observed, expected_skill, note, trace_hash,
                ),
            )
            row = cursor.fetchone()
            if row is not None:
                return row, True
            cursor.execute(
                """SELECT * FROM skill_eval_feedback
                    WHERE message_id::text = %s AND account_id = %s AND feedback_kind = %s""",
                (message_id, account_id, feedback_kind),
            )
            return cursor.fetchone(), False

    @staticmethod
    def list_for_review(*, status: str | None = None) -> list[dict[str, Any]]:
        with database_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT * FROM skill_eval_feedback
                    WHERE (%s IS NULL OR review_status = %s)
                    ORDER BY created_at DESC""",
                (status, status),
            )
            return cursor.fetchall()

    @staticmethod
    def get(feedback_id: str) -> dict[str, Any]:
        with database_connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM skill_eval_feedback WHERE feedback_id::text = %s", (feedback_id,))
            row = cursor.fetchone()
        if row is None:
            raise SkillEvalFeedbackNotFound("스킬 사용 피드백을 찾을 수 없습니다.")
        return row

    @staticmethod
    def dismiss(feedback_id: str, *, reviewed_by: str) -> dict[str, Any]:
        with database_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """UPDATE skill_eval_feedback
                      SET review_status = 'DISMISSED', reviewed_by = %s, updated_at = now()
                    WHERE feedback_id::text = %s AND review_status = 'PENDING'
                    RETURNING *""",
                (reviewed_by, feedback_id),
            )
            row = cursor.fetchone()
        if row is None:
            raise SkillEvalFeedbackNotFound("검토할 피드백을 찾을 수 없습니다.")
        return row

    @staticmethod
    def cleanup_expired(*, feedback_days: int, unapproved_case_days: int, dry_run: bool) -> dict[str, int]:
        """오래된 신고와 승인되지 않은 초안을 지운다. 승인 dataset은 보존한다."""

        with database_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT count(*) AS count FROM skill_eval_feedback
                    WHERE created_at < now() - make_interval(days => %s)""",
                (feedback_days,),
            )
            feedback_count = cursor.fetchone()["count"]
            cursor.execute(
                """SELECT count(*) AS count FROM skill_eval_regression_case
                    WHERE review_status IN ('DRAFT', 'REJECTED')
                      AND updated_at < now() - make_interval(days => %s)""",
                (unapproved_case_days,),
            )
            case_count = cursor.fetchone()["count"]
            if not dry_run:
                cursor.execute(
                    """DELETE FROM skill_eval_regression_case
                        WHERE review_status IN ('DRAFT', 'REJECTED')
                          AND updated_at < now() - make_interval(days => %s)""",
                    (unapproved_case_days,),
                )
                cursor.execute(
                    """DELETE FROM skill_eval_feedback
                        WHERE created_at < now() - make_interval(days => %s)""",
                    (feedback_days,),
                )
        return {"feedback_deleted": feedback_count, "case_deleted": case_count}


class SkillEvalRegressionCaseRepository:
    @staticmethod
    def get(case_id: str) -> dict[str, Any]:
        with database_connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM skill_eval_regression_case WHERE case_id = %s", (case_id,))
            row = cursor.fetchone()
        if row is None:
            raise SkillEvalRegressionCaseNotFound("회귀 케이스를 찾을 수 없습니다.")
        return row

    @staticmethod
    def create_draft(
        *,
        case_id: str,
        scope: str,
        team_id: str | None,
        skill_name: str | None,
        capability_tags: list[str],
        polarity: str,
        case_document: dict[str, Any],
        source_trace_hash: str | None,
        dataset_version: str = "v1",
        source_feedback_id: str | None = None,
    ) -> dict[str, Any]:
        from psycopg.types.json import Jsonb

        with database_connection() as connection:
            with connection.cursor() as cursor:
                if source_feedback_id:
                    cursor.execute(
                        """UPDATE skill_eval_feedback
                              SET review_status = 'CONVERTED', updated_at = now()
                            WHERE feedback_id::text = %s AND review_status = 'PENDING'
                            RETURNING feedback_id""",
                        (source_feedback_id,),
                    )
                    if cursor.fetchone() is None:
                        raise SkillEvalFeedbackNotFound("전환할 수 있는 피드백을 찾을 수 없습니다.")
                cursor.execute(
                    """
                    INSERT INTO skill_eval_regression_case (
                        case_id, scope, team_id, skill_name, capability_tags,
                        polarity, case_document, source_trace_hash, dataset_version,
                        source_feedback_id
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING *
                    """,
                    (
                        case_id,
                        scope,
                        team_id,
                        skill_name,
                        capability_tags,
                        polarity,
                        Jsonb(case_document),
                        source_trace_hash,
                        dataset_version,
                        source_feedback_id,
                    ),
                )
                row = cursor.fetchone()
                return row

    @staticmethod
    def review(case_id: str, *, reviewed_by: str, approve: bool) -> dict[str, Any]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE skill_eval_regression_case
                       SET review_status = %s, reviewed_by = %s, updated_at = now()
                     WHERE case_id = %s AND review_status = 'DRAFT'
                     RETURNING *
                    """,
                    ("APPROVED" if approve else "REJECTED", reviewed_by, case_id),
                )
                row = cursor.fetchone()
        if row is None:
            raise SkillEvalRegressionCaseNotFound("회귀 케이스를 찾을 수 없습니다.")
        return row

    @staticmethod
    def list_approved_for(
        *, team_id: str | None, skill_name: str, capability_tags: list[str]
    ) -> list[dict[str, Any]]:
        """§8.8 "연결 우선순위: exact skill_name → 같은 팀의 승인된
        capability_tags → GLOBAL". 셋을 한 질의로 모으고 우선순위는
        호출부(`EvalSuiteComposer`)가 정렬한다 — 이 저장소는 후보만 돌려준다."""

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT * FROM skill_eval_regression_case
                     WHERE review_status = 'APPROVED'
                       AND (
                            (scope = 'SKILL' AND skill_name = %s AND (team_id IS NULL OR team_id = %s))
                         OR (scope = 'TEAM' AND team_id = %s AND capability_tags && %s)
                         OR scope = 'GLOBAL'
                       )
                     ORDER BY created_at DESC
                    """,
                    (skill_name, team_id, team_id, capability_tags),
                )
                return cursor.fetchall()

    @staticmethod
    def get_many(case_ids: list[str]) -> list[dict[str, Any]]:
        if not case_ids:
            return []
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM skill_eval_regression_case WHERE case_id = ANY(%s)",
                    (case_ids,),
                )
                return cursor.fetchall()

    @staticmethod
    def list_all(*, review_status: str | None = None) -> list[dict[str, Any]]:
        with database_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT * FROM skill_eval_regression_case
                    WHERE (%s IS NULL OR review_status = %s)
                    ORDER BY created_at DESC""",
                (review_status, review_status),
            )
            return cursor.fetchall()

    @staticmethod
    def update_draft(
        case_id: str, *, scope: str | None = None, team_id: str | None = None,
        skill_name: str | None = None, case_document: dict[str, Any] | None = None,
        capability_tags: list[str] | None = None, polarity: str | None = None,
        dataset_version: str | None = None,
    ) -> dict[str, Any]:
        from psycopg.types.json import Jsonb

        with database_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """UPDATE skill_eval_regression_case
                      SET scope = COALESCE(%s, scope),
                          team_id = %s,
                          skill_name = %s,
                          case_document = COALESCE(%s, case_document),
                          capability_tags = COALESCE(%s, capability_tags),
                          polarity = COALESCE(%s, polarity),
                          dataset_version = COALESCE(%s, dataset_version),
                          updated_at = now()
                    WHERE case_id = %s AND review_status = 'DRAFT'
                    RETURNING *""",
                (
                    scope, team_id, skill_name,
                    Jsonb(case_document) if case_document is not None else None,
                    capability_tags, polarity, dataset_version, case_id,
                ),
            )
            row = cursor.fetchone()
        if row is None:
            raise SkillEvalRegressionCaseNotFound("수정할 회귀 케이스 초안을 찾을 수 없습니다.")
        return row


__all__ = [
    "SkillEvalFeedbackRepository", "SkillEvalFeedbackNotFound",
    "SkillEvalRegressionCaseRepository", "SkillEvalRegressionCaseNotFound",
]
