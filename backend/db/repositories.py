"""현재 `DB/schema.sql`을 기준으로 한 직접 SQL Repository."""

from typing import Any

from psycopg.types.json import Jsonb

from .codes import next_short_code
from .connection import database_connection
from .errors import DuplicateRecord, PermissionDenied, RecordNotFound, ReferenceNotFound


def _require_record(cursor, *, table: str, column: str, value: str, label: str) -> None:
    allowed = {
        ("user_account", "account_id"),
        ("person", "person_id"),
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
    def list_for_owner(account_id: str) -> list[dict[str, Any]]:
        """내가 소유한 프로젝트. 온보딩 중인 DRAFT를 찾는 데도 쓴다."""

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
                    WHERE p.owner_account_id = %s
                    ORDER BY p.proj_id
                    """,
                    (account_id,),
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


class ProjectSourceRepository:
    """프로젝트가 어느 폴더·어느 Jira 프로젝트를 읽는지(`proj_source`).

    커넥터 연결은 계정 단위지만 소스는 프로젝트 단위다. `conn_id`는 요청에서
    받지 않고 소유자의 연결에서 찾는다 — 남의 연결에 소스를 매달 수 없어야 한다.
    """

    DRIVE_FOLDER = "DRIVE_FOLDER"
    JIRA_PROJECT = "JIRA_PROJECT"

    _CONNECTOR_BY_SOURCE = {
        DRIVE_FOLDER: "GOOGLE_DRIVE",
        JIRA_PROJECT: "JIRA",
    }

    @staticmethod
    def _require_owner(cursor, *, proj_id: str, account_id: str) -> None:
        cursor.execute("SELECT owner_account_id FROM proj WHERE proj_id = %s", (proj_id,))
        row = cursor.fetchone()
        if row is None:
            raise RecordNotFound(f"존재하지 않는 프로젝트입니다: {proj_id}")
        if row["owner_account_id"] != account_id:
            raise PermissionDenied("본인이 소유한 프로젝트만 수정할 수 있습니다.")

    @staticmethod
    def list_for_project(*, proj_id: str, account_id: str) -> list[dict[str, Any]]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                ProjectSourceRepository._require_owner(cursor, proj_id=proj_id, account_id=account_id)
                cursor.execute(
                    """
                    SELECT proj_source_id, proj_id, conn_id, source_type, external_source_id,
                           sync_status, default_doc_role, max_depth
                    FROM proj_source
                    WHERE proj_id = %s
                    ORDER BY proj_source_id
                    """,
                    (proj_id,),
                )
                return list(cursor.fetchall())

    @staticmethod
    def replace(
        *,
        proj_id: str,
        account_id: str,
        source_type: str,
        external_source_ids: list[str],
        max_depth: int | None = None,
    ) -> list[dict[str, Any]]:
        """해당 종류의 소스를 넘겨받은 목록으로 교체한다.

        선택 화면은 항상 전체 선택 상태를 보내므로 교체가 맞다. 덧붙이면 화면에서
        해제한 폴더가 남는다. 계속 선택된 폴더의 `default_doc_role`은 지키고
        넘어간다 — 폴더를 다시 저장했다고 역할 지정을 날릴 이유가 없다.

        `max_depth`는 이번에 저장하는 모든 폴더에 같은 값으로 들어간다. 화면의
        탐색 깊이 설정이 폴더별이 아니라 하나이기 때문이다.
        """

        connector_type = ProjectSourceRepository._CONNECTOR_BY_SOURCE.get(source_type)
        if connector_type is None:
            raise ValueError(f"지원하지 않는 소스 종류입니다: {source_type}")

        with database_connection() as connection:
            with connection.cursor() as cursor:
                ProjectSourceRepository._require_owner(cursor, proj_id=proj_id, account_id=account_id)

                cursor.execute(
                    """
                    SELECT conn_id
                    FROM connector_conn
                    WHERE account_id = %s AND connector_type = %s AND auth_status = 'CONNECTED'
                    ORDER BY connected_at DESC
                    LIMIT 1
                    """,
                    (account_id, connector_type),
                )
                connection_row = cursor.fetchone()
                if connection_row is None:
                    raise ReferenceNotFound(f"{connector_type} 커넥터가 연결되지 않았습니다.")

                cursor.execute(
                    """
                    SELECT external_source_id, default_doc_role
                    FROM proj_source
                    WHERE proj_id = %s AND source_type = %s
                    """,
                    (proj_id, source_type),
                )
                kept_roles = {row["external_source_id"]: row["default_doc_role"] for row in cursor.fetchall()}

                cursor.execute(
                    "DELETE FROM proj_source WHERE proj_id = %s AND source_type = %s",
                    (proj_id, source_type),
                )

                rows = []
                # 같은 폴더를 두 번 보내도 한 행만 남긴다.
                for external_source_id in dict.fromkeys(external_source_ids):
                    proj_source_id = next_short_code(
                        cursor,
                        table="proj_source",
                        column="proj_source_id",
                        prefix="PS",
                    )
                    cursor.execute(
                        """
                        INSERT INTO proj_source
                            (proj_source_id, proj_id, conn_id, source_type, external_source_id,
                             default_doc_role, max_depth)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        RETURNING proj_source_id, proj_id, conn_id, source_type, external_source_id,
                                  sync_status, default_doc_role, max_depth
                        """,
                        (
                            proj_source_id,
                            proj_id,
                            connection_row["conn_id"],
                            source_type,
                            external_source_id,
                            kept_roles.get(external_source_id),
                            max_depth if source_type == ProjectSourceRepository.DRIVE_FOLDER else None,
                        ),
                    )
                    rows.append(cursor.fetchone())

        return rows


class DocumentRepository:
    """프로젝트가 읽을 문서(`doc`). 역할 지정 화면이 쓰는 유일한 쓰기 경로다."""

    DRIVE = "DRIVE"
    DOC_ROLES = ("PLAN", "MEETING_NOTE", "DAILY_REPORT", "OTHER")

    @staticmethod
    def list_for_project(*, proj_id: str, account_id: str) -> list[dict[str, Any]]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                ProjectSourceRepository._require_owner(cursor, proj_id=proj_id, account_id=account_id)
                cursor.execute(
                    """
                    SELECT doc_id, proj_id, src_file_id, source_type, file_name,
                           mime_type, doc_role, src_modified_at, deleted
                    FROM doc
                    WHERE proj_id = %s AND deleted = false
                    ORDER BY doc_id
                    """,
                    (proj_id,),
                )
                return list(cursor.fetchall())

    @staticmethod
    def save_drive_documents(
        *,
        proj_id: str,
        account_id: str,
        folder_roles: dict[str, str],
        documents: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """폴더 역할과 문서 목록을 한 트랜잭션으로 기록한다.

        `doc` 행은 지우고 다시 만들지 않고 `src_file_id`로 갱신한다. 파싱이
        채워 둔 `content_hash`·`cur_revision`을 역할만 바꿨다고 날릴 수 없다.
        목록에서 빠진 문서는 `deleted`로 표시한다(스키마가 이를 위해 둔 컬럼이다).
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                ProjectSourceRepository._require_owner(cursor, proj_id=proj_id, account_id=account_id)

                for external_source_id, role in folder_roles.items():
                    cursor.execute(
                        """
                        UPDATE proj_source
                           SET default_doc_role = %s
                         WHERE proj_id = %s
                           AND source_type = %s
                           AND external_source_id = %s
                        """,
                        (role, proj_id, ProjectSourceRepository.DRIVE_FOLDER, external_source_id),
                    )

                seen = []
                for document in documents:
                    src_file_id = document["src_file_id"]
                    seen.append(src_file_id)
                    cursor.execute(
                        """
                        UPDATE doc
                           SET file_name = %s,
                               mime_type = %s,
                               doc_role = %s,
                               src_modified_at = %s,
                               deleted = false
                         WHERE proj_id = %s AND src_file_id = %s
                        """,
                        (
                            document["file_name"],
                            document["mime_type"],
                            document["doc_role"],
                            document["src_modified_at"],
                            proj_id,
                            src_file_id,
                        ),
                    )
                    if cursor.rowcount:
                        continue

                    doc_id = next_short_code(cursor, table="doc", column="doc_id", prefix="DC")
                    cursor.execute(
                        """
                        INSERT INTO doc
                            (doc_id, proj_id, src_file_id, source_type, file_name,
                             mime_type, doc_role, src_modified_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            doc_id,
                            proj_id,
                            src_file_id,
                            DocumentRepository.DRIVE,
                            document["file_name"],
                            document["mime_type"],
                            document["doc_role"],
                            document["src_modified_at"],
                        ),
                    )

                # 선택이 해제된 폴더의 문서는 더 이상 읽지 않는다.
                cursor.execute(
                    """
                    UPDATE doc
                       SET deleted = true
                     WHERE proj_id = %s
                       AND source_type = %s
                       AND NOT (src_file_id = ANY(%s))
                    """,
                    (proj_id, DocumentRepository.DRIVE, seen),
                )

                cursor.execute(
                    """
                    SELECT doc_id, proj_id, src_file_id, source_type, file_name,
                           mime_type, doc_role, src_modified_at, deleted
                    FROM doc
                    WHERE proj_id = %s AND deleted = false
                    ORDER BY doc_id
                    """,
                    (proj_id,),
                )
                return list(cursor.fetchall())


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


def _linked_person(cursor, account_id: str) -> dict[str, Any] | None:
    """계정에 연결된(VERIFIED) PERSON 링크를 하나 돌려준다.

    한 계정이 여러 팀의 PERSON에 연결되는 것을 정책상 막지 않으므로
    (`팀원_초대_계정_매핑_정책.md`) 가장 먼저 연결된 것을 대표로 쓴다.
    """

    cursor.execute(
        """
        SELECT person_id, match_method
        FROM user_person_link
        WHERE account_id = %s AND mapping_status = 'VERIFIED'
        ORDER BY linked_at
        LIMIT 1
        """,
        (account_id,),
    )
    return cursor.fetchone()


def _linked_person_id(cursor, account_id: str) -> str | None:
    link = _linked_person(cursor, account_id)
    return link["person_id"] if link else None


def _scope_org_ids(cursor, person_id: str | None) -> list[str]:
    """PERSON이 속한 조직과 그 하위 조직 전체를 반환한다.

    초대 가능 범위 정의(`팀원_초대_계정_매핑_정책.md` 핵심 원칙 4):
    "초대자 본인이 연결된 person.org_id부터 org.up_org_id 재귀로 이어지는
    하위 조직 전체". 조직장(`org.mgr_id`) 여부가 아니라 소속이 기준이다.
    """

    if person_id is None:
        return []

    cursor.execute(
        """
        WITH RECURSIVE scope AS (
            SELECT o.org_id
            FROM org AS o
            JOIN person AS p ON p.org_id = o.org_id
            WHERE p.person_id = %s AND o.status = 'ACTIVE'
            UNION
            SELECT child.org_id
            FROM org AS child
            JOIN scope ON child.up_org_id = scope.org_id
            WHERE child.status = 'ACTIVE'
        )
        SELECT org_id FROM scope ORDER BY org_id
        """,
        (person_id,),
    )
    return [row["org_id"] for row in cursor.fetchall()]


def _link_person_to_account(
    cursor,
    *,
    account_id: str,
    person_id: str,
    invite_id: str | None,
    match_method: str,
) -> str:
    link_id = next_short_code(
        cursor,
        table="user_person_link",
        column="link_id",
        prefix="UL",
    )
    cursor.execute(
        """
        INSERT INTO user_person_link
            (link_id, account_id, person_id, invite_id, mapping_status, match_method)
        VALUES (%s, %s, %s, %s, 'VERIFIED', %s)
        """,
        (link_id, account_id, person_id, invite_id, match_method),
    )
    return link_id


def _person_already_linked(cursor, person_id: str) -> bool:
    cursor.execute(
        """
        SELECT 1
        FROM user_person_link
        WHERE person_id = %s AND mapping_status = 'VERIFIED'
        """,
        (person_id,),
    )
    return cursor.fetchone() is not None


class AccountRepository:
    @staticmethod
    def create(
        *,
        email: str,
        password_hash: str,
        display_name: str,
        invite_token_hash: str | None = None,
    ) -> dict[str, Any]:
        """계정을 만들고 PERSON 매핑까지 한 트랜잭션에서 처리한다.

        초대 토큰이 있으면 그 초대를 수락해 PERSON까지 매핑한다.

        초대 없이 가입하는 팀장은 여기서 매핑하지 않는다. HR 시스템을
        연결해야 비로소 본인 PERSON을 조회할 수 있다는 것이 원래 설계이고
        (`팀원_초대_계정_매핑_정책.md` 시나리오 2단계), 그 조회는 People DB
        커넥터를 연결하는 시점에 `link_by_hr_email()`이 수행한다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM user_account WHERE lower(email) = lower(%s)",
                    (email,),
                )
                if cursor.fetchone() is not None:
                    raise DuplicateRecord("이미 가입된 이메일입니다.")

                account_id = next_short_code(
                    cursor,
                    table="user_account",
                    column="account_id",
                    prefix="UA",
                )
                cursor.execute(
                    """
                    INSERT INTO user_account
                        (account_id, email, password_hash, display_name)
                    VALUES (%s, %s, %s, %s)
                    RETURNING account_id, email, display_name, account_status
                    """,
                    (account_id, email, password_hash, display_name),
                )
                account = cursor.fetchone()

                if invite_token_hash:
                    MemberInviteRepository.accept(
                        cursor,
                        token_hash=invite_token_hash,
                        account_id=account_id,
                    )

                return AccountRepository._profile(cursor, account_id) or account

    @staticmethod
    def link_by_hr_email(cursor, *, account_id: str, email: str) -> str | None:
        """HR 이메일이 같은 PERSON에 계정을 연결하고 person_id를 반환한다.

        초대 기반 매핑에서 이메일 비교를 금지한 것과 달리, 팀장이 HR 시스템을
        연결하며 본인 PERSON 레코드를 확인하는 경로는 정책 시나리오 2단계에
        해당한다. 일치하는 PERSON이 없으면 None.
        """

        cursor.execute(
            """
            SELECT p.person_id
            FROM person AS p
            WHERE lower(p.email) = lower(%s)
              AND p.emp_status = 'ACTIVE'
              AND NOT EXISTS (
                  SELECT 1
                  FROM user_person_link AS l
                  WHERE l.person_id = p.person_id AND l.mapping_status = 'VERIFIED'
              )
            """,
            (email,),
        )
        row = cursor.fetchone()
        if row is None:
            return None

        _link_person_to_account(
            cursor,
            account_id=account_id,
            person_id=row["person_id"],
            invite_id=None,
            match_method="SELF_EMAIL",
        )
        return row["person_id"]

    @staticmethod
    def find_credentials(email: str) -> dict[str, Any] | None:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT account_id, email, password_hash, display_name, account_status
                    FROM user_account
                    WHERE lower(email) = lower(%s)
                    """,
                    (email,),
                )
                return cursor.fetchone()

    @staticmethod
    def find_credentials_by_id(account_id: str) -> dict[str, Any] | None:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT account_id, email, password_hash, display_name, account_status
                    FROM user_account
                    WHERE account_id = %s
                    """,
                    (account_id,),
                )
                return cursor.fetchone()

    @staticmethod
    def update_password(*, account_id: str, password_hash: str) -> None:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE user_account
                    SET password_hash = %s
                    WHERE account_id = %s
                    RETURNING account_id
                    """,
                    (password_hash, account_id),
                )
                if cursor.fetchone() is None:
                    raise RecordNotFound(f"존재하지 않는 계정입니다: {account_id}")

    @staticmethod
    def touch_last_login(account_id: str) -> None:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE user_account SET last_login_at = now() WHERE account_id = %s",
                    (account_id,),
                )

    @staticmethod
    def get_profile(account_id: str) -> dict[str, Any]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                profile = AccountRepository._profile(cursor, account_id)

        if profile is None:
            raise RecordNotFound(f"존재하지 않는 계정입니다: {account_id}")
        return profile

    @staticmethod
    def _profile(cursor, account_id: str) -> dict[str, Any] | None:
        cursor.execute(
            """
            SELECT account_id, email, display_name, account_status
            FROM user_account
            WHERE account_id = %s
            """,
            (account_id,),
        )
        account = cursor.fetchone()
        if account is None:
            return None

        link = _linked_person(cursor, account_id)
        person_id = link["person_id"] if link else None
        person = None
        if person_id is not None:
            cursor.execute(
                """
                SELECT p.person_id, p.name, p.email, p.org_id, p.job_role, o.name AS org_name
                FROM person AS p
                LEFT JOIN org AS o ON o.org_id = p.org_id
                WHERE p.person_id = %s
                """,
                (person_id,),
            )
            person = cursor.fetchone()

        account["person"] = person
        # 초대로 들어온 계정만 팀원이다. 그 외(직접 가입)는 팀장으로 본다 —
        # HR 시스템을 연결할 권한이 회사에서 팀장에게만 주어진다는 전제.
        account["invited"] = bool(link and link["match_method"] == "TEAM_INVITATION")
        account["scope_org_ids"] = _scope_org_ids(cursor, person_id)
        return account


class MemberInviteRepository:
    INVITE_TTL_DAYS = 14

    @staticmethod
    def list_candidates(account_id: str) -> list[dict[str, Any]]:
        """초대 가능한 하위 조직 PERSON 목록(이미 연결·초대된 사람 제외)."""

        with database_connection() as connection:
            with connection.cursor() as cursor:
                scope = _scope_org_ids(cursor, _linked_person_id(cursor, account_id))
                if not scope:
                    return []

                cursor.execute(
                    """
                    SELECT p.person_id, p.name, p.email, p.org_id, p.job_role, o.name AS org_name
                    FROM person AS p
                    LEFT JOIN org AS o ON o.org_id = p.org_id
                    WHERE p.org_id = ANY(%s)
                      AND p.emp_status = 'ACTIVE'
                      AND NOT EXISTS (
                          SELECT 1 FROM user_person_link AS l
                          WHERE l.person_id = p.person_id AND l.mapping_status = 'VERIFIED'
                      )
                      AND NOT EXISTS (
                          SELECT 1 FROM member_invite AS mi
                          WHERE mi.person_id = p.person_id AND mi.status = 'PENDING'
                      )
                    ORDER BY p.name
                    """,
                    (scope,),
                )
                return list(cursor.fetchall())

    @staticmethod
    def create(*, invited_by: str, person_id: str, token_hash: str) -> dict[str, Any]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                _require_record(
                    cursor,
                    table="user_account",
                    column="account_id",
                    value=invited_by,
                    label="초대자 계정",
                )
                _require_record(
                    cursor,
                    table="person",
                    column="person_id",
                    value=person_id,
                    label="직원",
                )

                scope = _scope_org_ids(cursor, _linked_person_id(cursor, invited_by))
                cursor.execute("SELECT org_id FROM person WHERE person_id = %s", (person_id,))
                person_org_id = cursor.fetchone()["org_id"]
                if person_org_id is None or person_org_id not in scope:
                    raise PermissionDenied("본인이 속한 조직과 그 하위 조직의 직원만 초대할 수 있습니다.")

                if _person_already_linked(cursor, person_id):
                    raise DuplicateRecord("이미 다른 계정에 연결된 직원입니다.")

                cursor.execute(
                    "SELECT 1 FROM member_invite WHERE person_id = %s AND status = 'PENDING'",
                    (person_id,),
                )
                if cursor.fetchone() is not None:
                    raise DuplicateRecord("이미 발급된 초대가 있습니다. 기존 초대를 취소한 뒤 다시 발급해 주세요.")

                invite_id = next_short_code(
                    cursor,
                    table="member_invite",
                    column="invite_id",
                    prefix="MI",
                )
                cursor.execute(
                    """
                    INSERT INTO member_invite
                        (invite_id, team_org_id, person_id, invited_by, token_hash, expires_at)
                    VALUES (%s, %s, %s, %s, %s, now() + make_interval(days => %s))
                    RETURNING invite_id, team_org_id, person_id, invited_by, status,
                              expires_at, accepted_at, created_at
                    """,
                    (
                        invite_id,
                        person_org_id,
                        person_id,
                        invited_by,
                        token_hash,
                        MemberInviteRepository.INVITE_TTL_DAYS,
                    ),
                )
                invite = cursor.fetchone()

                cursor.execute(
                    """
                    SELECT p.name AS person_name, p.email AS person_email, o.name AS org_name
                    FROM person AS p
                    LEFT JOIN org AS o ON o.org_id = p.org_id
                    WHERE p.person_id = %s
                    """,
                    (person_id,),
                )
                return {**invite, **cursor.fetchone()}

    @staticmethod
    def list_by_inviter(account_id: str) -> list[dict[str, Any]]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        mi.invite_id,
                        mi.person_id,
                        p.name AS person_name,
                        p.email AS person_email,
                        o.name AS org_name,
                        mi.expires_at,
                        mi.accepted_at,
                        mi.created_at,
                        CASE
                            WHEN mi.status = 'PENDING' AND mi.expires_at <= now() THEN 'EXPIRED'
                            ELSE mi.status
                        END AS status
                    FROM member_invite AS mi
                    LEFT JOIN person AS p ON p.person_id = mi.person_id
                    LEFT JOIN org AS o ON o.org_id = mi.team_org_id
                    WHERE mi.invited_by = %s
                    ORDER BY mi.created_at DESC
                    """,
                    (account_id,),
                )
                return list(cursor.fetchall())

    @staticmethod
    def revoke(*, invite_id: str, account_id: str) -> None:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE member_invite
                    SET status = 'REVOKED'
                    WHERE invite_id = %s AND invited_by = %s AND status = 'PENDING'
                    RETURNING invite_id
                    """,
                    (invite_id, account_id),
                )
                if cursor.fetchone() is None:
                    raise RecordNotFound("취소할 수 있는 초대가 아닙니다.")

    @staticmethod
    def preview(token_hash: str) -> dict[str, Any]:
        """가입 전에 코드가 유효한지 확인하고 대상자를 알려준다."""

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        mi.invite_id,
                        p.name AS person_name,
                        p.email AS person_email,
                        o.name AS org_name,
                        mi.expires_at
                    FROM member_invite AS mi
                    LEFT JOIN person AS p ON p.person_id = mi.person_id
                    LEFT JOIN org AS o ON o.org_id = mi.team_org_id
                    WHERE mi.token_hash = %s
                      AND mi.status = 'PENDING'
                      AND mi.expires_at > now()
                    """,
                    (token_hash,),
                )
                row = cursor.fetchone()

        if row is None:
            raise RecordNotFound("사용할 수 없는 초대 코드입니다. 만료됐거나 이미 사용된 코드인지 확인해 주세요.")
        return row

    @staticmethod
    def accept(cursor, *, token_hash: str, account_id: str) -> str:
        """PENDING 초대를 조건부 UPDATE로 1회만 수락시키고 매핑을 만든다.

        가입 트랜잭션 안에서 호출되므로 커서를 인자로 받는다.
        """

        cursor.execute(
            """
            UPDATE member_invite
            SET status = 'ACCEPTED', accepted_at = now()
            WHERE token_hash = %s AND status = 'PENDING' AND expires_at > now()
            RETURNING invite_id, person_id
            """,
            (token_hash,),
        )
        invite = cursor.fetchone()
        if invite is None:
            raise RecordNotFound("사용할 수 없는 초대 코드입니다. 만료됐거나 이미 사용된 코드인지 확인해 주세요.")

        if _person_already_linked(cursor, invite["person_id"]):
            raise DuplicateRecord("이미 다른 계정에 연결된 직원입니다.")

        _link_person_to_account(
            cursor,
            account_id=account_id,
            person_id=invite["person_id"],
            invite_id=invite["invite_id"],
            match_method="TEAM_INVITATION",
        )
        return invite["invite_id"]


class ConnectorRepository:
    """`connector_conn` — 계정별 외부 서비스 연결 상태.

    People DB는 지금 같은 PostgreSQL 안에 있어서 주고받을 자격증명이 없다
    (`encrypted_credential_ref`는 NULL). 원래 기획은 외부 HR 시스템이었고,
    부트캠프 범위상 DB로 대체한 것이라 "연결"은 곧 HR 데이터를 조회해
    본인 PERSON을 확인하는 행위를 뜻한다.
    """

    PEOPLE_DB = "PEOPLE_DB"
    GOOGLE_DRIVE = "GOOGLE_DRIVE"
    JIRA = "JIRA"
    PEOPLE_DB_SCOPES = ["org:read", "person:read"]

    @staticmethod
    def list_for_account(account_id: str) -> list[dict[str, Any]]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT conn_id, connector_type, granted_scopes, auth_status, connected_at
                    FROM connector_conn
                    WHERE account_id = %s
                    ORDER BY connected_at
                    """,
                    (account_id,),
                )
                return list(cursor.fetchall())

    @staticmethod
    def connect_people_db(*, account_id: str, email: str) -> dict[str, Any]:
        """HR 데이터를 확인하고 본인 PERSON에 연결한 뒤 연결 상태를 기록한다.

        HR에서 본인을 못 찾으면 연결 자체가 실패한다. 조직을 모르면 팀원
        초대도 업무 배정도 할 수 없어서, 연결됐다고 표시하는 것이 거짓이 된다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        (SELECT count(*) FROM org WHERE status = 'ACTIVE') AS org_count,
                        (SELECT count(*) FROM person WHERE emp_status = 'ACTIVE') AS person_count
                    """
                )
                totals = cursor.fetchone()
                if not totals["org_count"] or not totals["person_count"]:
                    raise ReferenceNotFound(
                        "HR 시스템에서 조직·직원 데이터를 찾을 수 없습니다. 관리자에게 문의해 주세요."
                    )

                person_id = _linked_person_id(cursor, account_id)
                if person_id is None:
                    person_id = AccountRepository.link_by_hr_email(
                        cursor,
                        account_id=account_id,
                        email=email,
                    )
                if person_id is None:
                    raise RecordNotFound(
                        "가입한 이메일과 일치하는 직원 정보가 HR 시스템에 없습니다. "
                        "회사 이메일로 가입했는지 확인해 주세요."
                    )

                ConnectorRepository._upsert(
                    cursor,
                    account_id=account_id,
                    connector_type=ConnectorRepository.PEOPLE_DB,
                    granted_scopes=ConnectorRepository.PEOPLE_DB_SCOPES,
                )
                return ConnectorRepository._people_db_summary(cursor, account_id)

    @staticmethod
    def find_identity(*, account_id: str, email: str) -> dict[str, Any]:
        """가입 이메일로 찾은 본인 후보. 확인 전이므로 링크를 만들지 않는다.

        정책 시나리오 2단계의 "본인 이메일로 자신의 PERSON 레코드를 찾아
        확인한다"에서 '찾아'에 해당한다. '확인'은 사용자가 모달에서 누른다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                person_id = _linked_person_id(cursor, account_id)
                if person_id is not None:
                    cursor.execute(
                        """
                        SELECT p.person_id, p.name, p.email, p.org_id, p.job_role,
                               o.name AS org_name
                        FROM person AS p
                        LEFT JOIN org AS o ON o.org_id = p.org_id
                        WHERE p.person_id = %s
                        """,
                        (person_id,),
                    )
                    return cursor.fetchone()

                cursor.execute(
                    """
                    SELECT p.person_id, p.name, p.email, p.org_id, p.job_role,
                           o.name AS org_name
                    FROM person AS p
                    LEFT JOIN org AS o ON o.org_id = p.org_id
                    WHERE lower(p.email) = lower(%s)
                      AND p.emp_status = 'ACTIVE'
                      AND NOT EXISTS (
                          SELECT 1
                          FROM user_person_link AS l
                          WHERE l.person_id = p.person_id AND l.mapping_status = 'VERIFIED'
                      )
                    """,
                    (email,),
                )
                row = cursor.fetchone()

        if row is None:
            raise RecordNotFound(
                "가입한 이메일과 일치하는 직원 정보가 HR 시스템에 없습니다. "
                "회사 이메일로 가입했는지 확인해 주세요."
            )
        return row

    @staticmethod
    def people_db_summary(account_id: str) -> dict[str, Any]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                return ConnectorRepository._people_db_summary(cursor, account_id)

    @staticmethod
    def connect_oauth(
        *,
        account_id: str,
        connector_type: str,
        granted_scopes: list[str],
        encrypted_credential: str,
    ) -> None:
        """외부 OAuth 연결을 암호문과 함께 한 행으로 기록한다."""

        if connector_type not in {ConnectorRepository.GOOGLE_DRIVE, ConnectorRepository.JIRA}:
            raise RepositoryError("지원하지 않는 OAuth 커넥터입니다.")

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE connector_conn
                    SET granted_scopes = %s,
                        encrypted_credential_ref = %s,
                        auth_status = 'CONNECTED',
                        connected_at = now()
                    WHERE account_id = %s AND connector_type = %s
                    RETURNING conn_id
                    """,
                    (Jsonb(granted_scopes), encrypted_credential, account_id, connector_type),
                )
                if cursor.fetchone() is not None:
                    return

                conn_id = next_short_code(cursor, table="connector_conn", column="conn_id", prefix="CN")
                cursor.execute(
                    """
                    INSERT INTO connector_conn
                        (conn_id, account_id, connector_type, granted_scopes,
                         encrypted_credential_ref, auth_status)
                    VALUES (%s, %s, %s, %s, %s, 'CONNECTED')
                    """,
                    (
                        conn_id,
                        account_id,
                        connector_type,
                        Jsonb(granted_scopes),
                        encrypted_credential,
                    ),
                )

    @staticmethod
    def get_credential(*, account_id: str, connector_type: str) -> str:
        """저장된 암호문을 돌려준다. 연결이 없거나 끊겼으면 재연결을 요구한다."""

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT auth_status, encrypted_credential_ref
                    FROM connector_conn
                    WHERE account_id = %s AND connector_type = %s
                    """,
                    (account_id, connector_type),
                )
                row = cursor.fetchone()

        if row is None or not row["encrypted_credential_ref"]:
            raise RecordNotFound("연결되지 않은 서비스입니다. 먼저 연결해 주세요.")
        if row["auth_status"] != "CONNECTED":
            raise RepositoryError("연결이 만료됐습니다. 다시 연결해 주세요.")
        return row["encrypted_credential_ref"]

    @staticmethod
    def update_credential(*, account_id: str, connector_type: str, encrypted_credential: str) -> None:
        """토큰 갱신 결과를 덮어쓴다. connected_at은 최초 연결 시각으로 남긴다."""

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE connector_conn
                    SET encrypted_credential_ref = %s, auth_status = 'CONNECTED'
                    WHERE account_id = %s AND connector_type = %s
                    """,
                    (encrypted_credential, account_id, connector_type),
                )

    @staticmethod
    def mark_expired(*, account_id: str, connector_type: str) -> None:
        """갱신이 실패하면 화면이 재연결을 유도할 수 있도록 상태만 바꾼다."""

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE connector_conn
                    SET auth_status = 'EXPIRED'
                    WHERE account_id = %s AND connector_type = %s
                    """,
                    (account_id, connector_type),
                )

    @staticmethod
    def _upsert(cursor, *, account_id: str, connector_type: str, granted_scopes: list[str]) -> None:
        """(account_id, connector_type)에 유니크 제약이 없어 직접 확인한다."""

        cursor.execute(
            """
            UPDATE connector_conn
            SET granted_scopes = %s, auth_status = 'CONNECTED', connected_at = now()
            WHERE account_id = %s AND connector_type = %s
            RETURNING conn_id
            """,
            (Jsonb(granted_scopes), account_id, connector_type),
        )
        if cursor.fetchone() is not None:
            return

        conn_id = next_short_code(cursor, table="connector_conn", column="conn_id", prefix="CN")
        cursor.execute(
            """
            INSERT INTO connector_conn
                (conn_id, account_id, connector_type, granted_scopes, auth_status)
            VALUES (%s, %s, %s, %s, 'CONNECTED')
            """,
            (conn_id, account_id, connector_type, Jsonb(granted_scopes)),
        )

    @staticmethod
    def _people_db_summary(cursor, account_id: str) -> dict[str, Any]:
        """연결 확인 화면에 보여줄 요약. 전체 규모와 본인 조직 기준 인원."""

        cursor.execute(
            """
            SELECT
                (SELECT count(*) FROM org WHERE status = 'ACTIVE') AS org_count,
                (SELECT count(*) FROM person WHERE emp_status = 'ACTIVE') AS person_count
            """
        )
        summary = dict(cursor.fetchone())

        person_id = _linked_person_id(cursor, account_id)
        summary["person"] = None
        summary["my_org_name"] = None
        summary["my_org_person_count"] = 0
        summary["scope_person_count"] = 0

        if person_id is None:
            return summary

        cursor.execute(
            """
            SELECT p.person_id, p.name, p.email, p.org_id, p.job_role, o.name AS org_name
            FROM person AS p
            LEFT JOIN org AS o ON o.org_id = p.org_id
            WHERE p.person_id = %s
            """,
            (person_id,),
        )
        person = cursor.fetchone()
        summary["person"] = person
        summary["my_org_name"] = person["org_name"] if person else None

        scope = _scope_org_ids(cursor, person_id)
        if not scope:
            return summary

        cursor.execute(
            """
            SELECT
                count(*) FILTER (WHERE org_id = %s) AS my_org_count,
                count(*) AS scope_count
            FROM person
            WHERE org_id = ANY(%s) AND emp_status = 'ACTIVE'
            """,
            (person["org_id"], scope),
        )
        counts = cursor.fetchone()
        summary["my_org_person_count"] = counts["my_org_count"]
        summary["scope_person_count"] = counts["scope_count"]
        return summary
