"""현재 `DB/schema.sql`을 기준으로 한 직접 SQL Repository."""

from typing import Any

from .codes import next_short_code
from .connection import database_connection
from .errors import RecordNotFound, ReferenceNotFound


def _require_record(cursor, *, table: str, column: str, value: str, label: str) -> None:
    allowed = {
        ("user_account", "account_id"),
        ("proj", "proj_id"),
        ("ana_snapshot", "snap_id"),
        ("feat_ready_result", "readiness_id"),
    }
    if (table, column) not in allowed:
        raise ValueError("허용되지 않은 참조 검사입니다.")

    cursor.execute(f"SELECT 1 FROM {table} WHERE {column} = %s", (value,))
    if cursor.fetchone() is None:
        raise ReferenceNotFound(f"존재하지 않는 {label}입니다: {value}")


class OrganizationRepository:
    @staticmethod
    def list_active() -> list[dict[str, Any]]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT org_id, up_org_id, mgr_id, name, org_type, status
                    FROM org
                    WHERE status = 'ACTIVE'
                    ORDER BY org_id
                    """
                )
                return list(cursor.fetchall())


class PersonRepository:
    @staticmethod
    def list_active() -> list[dict[str, Any]]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        p.person_id,
                        p.emp_id,
                        p.name,
                        p.email,
                        p.org_id,
                        o.name AS org_name,
                        p.job_role,
                        p.level_id,
                        lv.name AS level_name,
                        p.emp_status,
                        sc.tz,
                        sc.fte,
                        sc.wk_hours,
                        sc.def_wk_hours
                    FROM person AS p
                    LEFT JOIN org AS o ON o.org_id = p.org_id
                    LEFT JOIN level AS lv ON lv.level_id = p.level_id
                    LEFT JOIN LATERAL (
                        SELECT s.tz, s.fte, s.wk_hours, s.def_wk_hours
                        FROM sched AS s
                        WHERE s.person_id = p.person_id
                          AND s.eff_from <= CURRENT_DATE
                          AND (s.eff_to IS NULL OR s.eff_to >= CURRENT_DATE)
                        ORDER BY s.eff_from DESC
                        LIMIT 1
                    ) AS sc ON true
                    WHERE p.emp_status = 'ACTIVE'
                    ORDER BY p.person_id
                    """
                )
                return list(cursor.fetchall())


class ProjectRepository:
    @staticmethod
    def list_all() -> list[dict[str, Any]]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        p.proj_id,
                        p.name,
                        p.status,
                        p.tz,
                        p.owner_account_id,
                        ua.display_name AS owner_name
                    FROM proj AS p
                    LEFT JOIN user_account AS ua
                      ON ua.account_id = p.owner_account_id
                    ORDER BY p.proj_id
                    """
                )
                return list(cursor.fetchall())

    @staticmethod
    def get(proj_id: str) -> dict[str, Any]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        p.proj_id,
                        p.name,
                        p.status,
                        p.tz,
                        p.owner_account_id,
                        ua.display_name AS owner_name
                    FROM proj AS p
                    LEFT JOIN user_account AS ua
                      ON ua.account_id = p.owner_account_id
                    WHERE p.proj_id = %s
                    """,
                    (proj_id,),
                )
                row = cursor.fetchone()

        if row is None:
            raise RecordNotFound(f"존재하지 않는 프로젝트입니다: {proj_id}")
        return row

    @staticmethod
    def create(*, name: str, status: str, tz: str, owner_account_id: str | None) -> dict[str, Any]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                if owner_account_id:
                    _require_record(
                        cursor,
                        table="user_account",
                        column="account_id",
                        value=owner_account_id,
                        label="사용자 계정",
                    )

                proj_id = next_short_code(
                    cursor,
                    table="proj",
                    column="proj_id",
                    prefix="PJ",
                )
                cursor.execute(
                    """
                    INSERT INTO proj (proj_id, name, status, tz, owner_account_id)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING proj_id, name, status, tz, owner_account_id
                    """,
                    (proj_id, name, status, tz, owner_account_id),
                )
                project = cursor.fetchone()

                if owner_account_id:
                    member_id = next_short_code(
                        cursor,
                        table="proj_member",
                        column="proj_member_id",
                        prefix="PM",
                    )
                    cursor.execute(
                        """
                        INSERT INTO proj_member
                            (proj_member_id, proj_id, account_id, access_role)
                        VALUES (%s, %s, %s, 'OWNER')
                        """,
                        (member_id, proj_id, owner_account_id),
                    )

        project["owner_name"] = None
        return project


class AnalysisRunRepository:
    @staticmethod
    def create(
        *,
        proj_id: str,
        snapshot_id: str,
        readiness_id: str | None,
        requested_by: str | None,
        model_version: str | None,
        policy_version: str | None,
    ) -> dict[str, Any]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                _require_record(
                    cursor,
                    table="proj",
                    column="proj_id",
                    value=proj_id,
                    label="프로젝트",
                )
                _require_record(
                    cursor,
                    table="ana_snapshot",
                    column="snap_id",
                    value=snapshot_id,
                    label="분석 Snapshot",
                )
                cursor.execute(
                    "SELECT 1 FROM ana_snapshot WHERE snap_id = %s AND proj_id = %s",
                    (snapshot_id, proj_id),
                )
                if cursor.fetchone() is None:
                    raise ReferenceNotFound("Snapshot이 요청 프로젝트에 속하지 않습니다.")

                if readiness_id:
                    _require_record(
                        cursor,
                        table="feat_ready_result",
                        column="readiness_id",
                        value=readiness_id,
                        label="Feature Readiness 결과",
                    )
                if requested_by:
                    _require_record(
                        cursor,
                        table="user_account",
                        column="account_id",
                        value=requested_by,
                        label="요청자 계정",
                    )

                run_id = next_short_code(
                    cursor,
                    table="assign_run",
                    column="run_id",
                    prefix="RN",
                )
                cursor.execute(
                    """
                    INSERT INTO assign_run (
                        run_id, snapshot_id, readiness_id, model_version,
                        policy_version, status, requested_by
                    )
                    VALUES (%s, %s, %s, %s, %s, 'RUNNING', %s)
                    RETURNING run_id, snapshot_id, readiness_id, model_version,
                              policy_version, status, requested_by
                    """,
                    (
                        run_id,
                        snapshot_id,
                        readiness_id,
                        model_version,
                        policy_version,
                        requested_by,
                    ),
                )
                return cursor.fetchone()

    @staticmethod
    def get(run_id: str) -> dict[str, Any]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        ar.run_id,
                        ar.snapshot_id,
                        ar.readiness_id,
                        ar.model_version,
                        ar.policy_version,
                        ar.status,
                        ar.requested_by,
                        sn.proj_id
                    FROM assign_run AS ar
                    LEFT JOIN ana_snapshot AS sn
                      ON sn.snap_id = ar.snapshot_id
                    WHERE ar.run_id = %s
                    """,
                    (run_id,),
                )
                row = cursor.fetchone()

        if row is None:
            raise RecordNotFound(f"존재하지 않는 배정 실행입니다: {run_id}")
        return row
