"""현재 `DB/schema.sql`을 기준으로 한 직접 SQL Repository."""

from typing import Any

from psycopg.types.json import Jsonb

from backend.services import hr

from .audit import log_with
from .codes import next_short_code
from .connection import database_connection
from .errors import DuplicateRecord, PermissionDenied, RecordNotFound, ReferenceNotFound, RepositoryError

# "중복 연결" 판정(계정 1개에 VERIFIED 직원 링크가 2개 이상)은 운영 현황·연결
# 조직 현황·계정 관리·초대 현황 네 곳에서 똑같이 쓰는 정의라 CTE 텍스트를 여기 한 곳에만 둔다.
_DUP_ACCOUNTS_CTE = """
    dup_accounts AS (
        SELECT account_id
        FROM user_person_link
        WHERE mapping_status = 'VERIFIED'
        GROUP BY account_id
        HAVING count(*) > 1
    )
"""

# 계정 1개가 여러 PERSON에 연결될 수 있어(중복 연결), 화면에 대표로 보여줄 1건만
# 고를 때 쓴다 — 가장 먼저 연결된 것을 대표로 삼는다(`_linked_person()`과 같은 규칙).
# 계정 관리·연결 서비스 현황에서 공유한다.
_REPRESENTATIVE_LINK_CTE = """
    representative_link AS (
        SELECT DISTINCT ON (account_id) account_id, person_id
        FROM user_person_link
        WHERE mapping_status = 'VERIFIED'
        ORDER BY account_id, linked_at
    )
"""


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
                    SELECT d.doc_id, d.proj_id, d.src_file_id, d.source_type, d.file_name,
                           d.mime_type, d.doc_role, d.src_modified_at, d.deleted, d.storage_key,
                           EXISTS (
                               SELECT 1 FROM doc_block b
                               JOIN chunk c ON c.block_id = b.block_id AND c.is_active = true
                               JOIN vec_idx v ON v.chunk_id = c.chunk_id AND v.is_active = true
                               WHERE b.doc_id = d.doc_id AND b.revision = d.cur_revision
                           ) AS search_ready
                    FROM doc d
                    WHERE d.proj_id = %s AND d.deleted = false AND d.access_revoked = false
                    ORDER BY d.doc_id
                    """,
                    (proj_id,),
                )
                return list(cursor.fetchall())

    @staticmethod
    def list_pending_download(*, proj_id: str, account_id: str) -> list[dict[str, Any]]:
        """아직 원문을 안 받았거나, 받은 뒤 Drive에서 수정된 문서.

        `src_modified_at`이 저장 시각보다 최신인지를 보지 않고 **리비전이 비었거나
        `storage_key`가 없는 것**만 고른다. 다시 받아야 하는지는 리비전 비교로
        판정하는 것이 맞지만, 그러려면 매번 Drive를 조회해야 해서 여기서는
        "아직 안 받은 것"만 다룬다. 재다운로드는 호출자가 강제할 수 있다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                ProjectSourceRepository._require_owner(cursor, proj_id=proj_id, account_id=account_id)
                cursor.execute(
                    """
                    SELECT doc_id, src_file_id, file_name, mime_type, storage_key, cur_revision
                    FROM doc
                    WHERE proj_id = %s
                      AND deleted = false
                      AND source_type = %s
                      AND src_file_id IS NOT NULL
                    ORDER BY doc_id
                    """,
                    (proj_id, DocumentRepository.DRIVE),
                )
                return list(cursor.fetchall())

    @staticmethod
    def mark_stored(*, doc_id: str, storage_key: str, content_hash: str, revision: str | None) -> None:
        """원문을 저장소에 넣은 결과를 기록한다.

        파일을 먼저 쓰고 이 기록을 나중에 한다. 순서가 반대면 "DB에는 있다는데
        파일이 없는" 상태가 생기고, 그건 파싱이 읽다가 죽는다. 반대로 파일만
        남는 것은 다음 다운로드가 덮어쓰므로 해가 없다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE doc
                       SET storage_key = %s,
                           content_hash = %s,
                           cur_revision = %s
                     WHERE doc_id = %s
                    """,
                    (storage_key, content_hash, revision, doc_id),
                )

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


def _attach_person_display(
    rows: list[dict[str, Any]],
    *,
    person_key: str = "person_id",
    org_key: str | None = None,
) -> list[dict[str, Any]]:
    """플랫폼 행에 HR 표시 정보(사람 이름·조직 이름)를 붙인다.

    예전에는 `LEFT JOIN person/org`로 한 쿼리에 묶었지만, HR을 실제 외부 API로
    바꾸려면 조인이 성립하지 않는다. 필요한 id만 모아 어댑터에서 한 번 읽고
    파이썬에서 붙인다.

    참조 무결성이 FK로 강제되지 않는 구조라(`VARCHAR(5)` 코드 직접 관리) 가리키는
    대상이 사라진 행이 실제로 생긴다. 그 경우 화면을 죽이지 않고 원본 id는 남긴 채
    이름만 `None`으로 둔다 — 운영자 콘솔 전체가 지키는 규칙이다.

    `org_key`를 주면 그 컬럼의 조직 이름도 붙인다(초대처럼 사람과 무관하게 조직을
    가리키는 행). 주지 않으면 사람이 속한 조직 이름을 붙인다.
    """

    person_ids = [row[person_key] for row in rows if row.get(person_key)]
    persons = hr.lookup_persons(person_ids)

    if org_key:
        org_ids = [row[org_key] for row in rows if row.get(org_key)]
    else:
        org_ids = [p["org_id"] for p in persons.values() if p.get("org_id")]
    orgs = hr.lookup_orgs(org_ids)

    for row in rows:
        person = persons.get(row.get(person_key)) if row.get(person_key) else None
        row["person_name"] = person["name"] if person else None
        row["person_email"] = person["email"] if person else None
        if org_key:
            org = orgs.get(row.get(org_key)) if row.get(org_key) else None
        else:
            row["org_id"] = person["org_id"] if person else None
            org = orgs.get(row["org_id"]) if row.get("org_id") else None
        row["org_name"] = org["name"] if org else None
    return rows


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

        이 계정의 회사가 아직 정해지지 않은 시점이라 회사 스코프를 걸 수 없다.
        목업의 알려진 한계이며, 회사는 여기서 사람을 확정한 직후에 정해진다.
        """

        person = hr.discover_person_by_email(email)
        if person is None:
            return None
        # 이미 다른 계정이 가져간 사람에는 연결하지 않는다.
        if _person_already_linked(cursor, person["person_id"]):
            return None
        row = {"person_id": person["person_id"]}

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
                    SELECT account_id, email, password_hash, display_name, account_status, is_admin
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
                    SELECT account_id, email, password_hash, display_name, account_status, is_admin
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
    def team_id(account_id: str) -> str | None:
        """이 계정이 속한 팀(테넌트). 팀을 아직 만들지도 들어가지도 않았으면 None.

        팀은 조직도에서 유도하지 않고 저장된 값을 읽는다 — 조직도만으로는
        "어디까지가 우리 그룹인가"를 알 수 없기 때문이다([[HR_어댑터와_테넌트_경계]]).
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT team_id FROM user_account WHERE account_id = %s",
                    (account_id,),
                )
                row = cursor.fetchone()
        return row["team_id"] if row else None

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
            SELECT account_id, email, display_name, account_status, team_id
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
        person = hr.get_person(person_id)

        account["person"] = person
        # 초대로 들어온 계정만 팀원이다. 그 외(직접 가입)는 팀장으로 본다 —
        # HR 시스템을 연결할 권한이 회사에서 팀장에게만 주어진다는 전제.
        account["invited"] = bool(link and link["match_method"] == "TEAM_INVITATION")
        # 초대 가능 범위 = 본인 소속 조직과 그 하위 전체
        # (`팀원_초대_계정_매핑_정책.md` 핵심 원칙 4). 조직장 여부가 아니라 소속이 기준이다.
        account["scope_org_ids"] = hr.subtree_org_ids(person["org_id"]) if person else []
        return account


class TeamRepository:
    """`team` / `team_member` — 우리 플랫폼을 쓰는 단위.

    HR 조직(`org`)과 다르다. HR에서는 한 회사지만 플랫폼을 쓰는 것은 회사 전체가
    아니라 그 안의 그룹이다. 그래서 팀은 조직도에서 유도하지 않고 팀장이 온보딩에서
    이름을 붙여 만든다 — 조직도만으로는 "어디까지가 우리 그룹인가"에 표시가 없어
    팀원의 소속을 알 수 없기 때문이다.

    `user_account.team_id`가 테넌트 경계다. 업무 배정 대상은 계정이 아니라 사람이라
    팀원 명부(`team_member`)는 PERSON 단위로 둔다 — 아직 가입하지 않은 사람도
    팀원이다.
    """

    @staticmethod
    def add_member(cursor, *, team_id: str, person_id: str) -> None:
        """팀원 명부에 추가한다. 이미 있으면 아무 일도 하지 않는다."""

        team_member_id = next_short_code(
            cursor, table="team_member", column="team_member_id", prefix="TM"
        )
        cursor.execute(
            """
            INSERT INTO team_member (team_member_id, team_id, person_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (team_id, person_id) DO NOTHING
            """,
            (team_member_id, team_id, person_id),
        )

    @staticmethod
    def create(*, owner_account_id: str, name: str, person_ids: list[str]) -> dict[str, Any]:
        """팀장이 팀명을 붙여 팀을 만들고 팀원을 담는다.

        팀장 본인은 고르지 않아도 항상 팀원이다 — 팀장도 업무 배정 대상이다.
        고른 사람이 초대 가능 범위(본인 소속 조직의 하위) 밖이면 거절한다.
        """

        name = name.strip()
        if not name:
            raise RepositoryError("팀 이름을 입력해 주세요.")

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT team_id FROM user_account WHERE account_id = %s",
                    (owner_account_id,),
                )
                account = cursor.fetchone()
                if account is None:
                    raise RecordNotFound("존재하지 않는 계정입니다.")
                if account["team_id"] is not None:
                    raise DuplicateRecord("이미 팀이 있습니다. 팀은 계정당 하나입니다.")

                owner_person_id = _linked_person_id(cursor, owner_account_id)
                if owner_person_id is None:
                    raise PermissionDenied(
                        "HR 시스템에서 본인 확인을 먼저 마쳐야 팀을 만들 수 있습니다."
                    )

                owner = hr.get_person(owner_person_id)
                if owner is None:
                    raise RecordNotFound("HR에서 본인 정보를 찾을 수 없습니다.")

                allowed = set(hr.subtree_org_ids(owner["org_id"]))
                members = hr.list_persons(person_ids=person_ids) if person_ids else []
                found = {p["person_id"] for p in members}
                missing = [pid for pid in person_ids if pid not in found]
                if missing:
                    raise RecordNotFound(f"HR에서 찾을 수 없는 직원이 있습니다: {', '.join(missing)}")

                outside = [p["person_id"] for p in members if p["org_id"] not in allowed]
                if outside:
                    raise PermissionDenied(
                        "본인이 속한 조직과 그 하위 조직의 직원만 팀에 담을 수 있습니다."
                    )

                team_id = next_short_code(cursor, table="team", column="team_id", prefix="TE")
                cursor.execute(
                    """
                    INSERT INTO team (team_id, name, owner_account_id, src_org_id)
                    VALUES (%s, %s, %s, %s)
                    RETURNING team_id, name, owner_account_id, src_org_id, created_at
                    """,
                    (team_id, name, owner_account_id, owner["org_id"]),
                )
                team = cursor.fetchone()

                for person_id in {owner_person_id, *found}:
                    TeamRepository.add_member(cursor, team_id=team_id, person_id=person_id)

                cursor.execute(
                    "UPDATE user_account SET team_id = %s WHERE account_id = %s",
                    (team_id, owner_account_id),
                )

                log_with(
                    cursor,
                    actor_account_id=owner_account_id,
                    action="TEAM_CREATE",
                    target_type="TEAM",
                    target_id=team_id,
                    payload={"name": name, "member_count": len(found) + 1},
                )

        team["member_count"] = len(found) + 1
        return team

    @staticmethod
    def get(team_id: str | None) -> dict[str, Any] | None:
        if team_id is None:
            return None

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT t.team_id, t.name, t.owner_account_id, t.src_org_id, t.created_at,
                           (SELECT count(*) FROM team_member tm WHERE tm.team_id = t.team_id)
                               AS member_count
                    FROM team AS t
                    WHERE t.team_id = %s
                    """,
                    (team_id,),
                )
                return cursor.fetchone()

    @staticmethod
    def member_person_ids(team_id: str | None) -> list[str]:
        """팀에 속한 PERSON id. 팀이 없으면 빈 목록 — 아무도 못 본다는 뜻이다."""

        if team_id is None:
            return []

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT person_id FROM team_member WHERE team_id = %s ORDER BY person_id",
                    (team_id,),
                )
                return [row["person_id"] for row in cursor.fetchall()]


class MemberInviteRepository:
    @staticmethod
    def list_candidates(account_id: str) -> list[dict[str, Any]]:
        """초대 가능한 하위 조직 PERSON 목록(이미 연결·초대된 사람 제외).

        후보 범위는 **HR 기준**(본인 소속 조직의 하위)이다. 팀이 이미 있어도
        아직 팀에 없는 사람을 부르는 것이 초대이므로, 여기서는 팀이 아니라
        조직도를 본다. 팀 경계는 초대를 수락한 뒤부터 적용된다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                person_id = _linked_person_id(cursor, account_id)
                if person_id is None:
                    return []
                # 이미 계정에 연결됐거나 초대가 대기 중인 사람은 후보에서 뺀다.
                cursor.execute(
                    """
                    SELECT person_id FROM user_person_link WHERE mapping_status = 'VERIFIED'
                    UNION
                    SELECT person_id FROM member_invite WHERE status = 'PENDING'
                    """
                )
                taken = {row["person_id"] for row in cursor.fetchall()}

        me = hr.get_person(person_id)
        if me is None:
            return []

        candidates = hr.list_persons(org_ids=hr.subtree_org_ids(me["org_id"]))
        return sorted(
            (p for p in candidates if p["person_id"] not in taken),
            key=lambda p: p["name"],
        )

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
                inviter_person_id = _linked_person_id(cursor, invited_by)
                inviter = hr.get_person(inviter_person_id)
                if inviter is None:
                    raise PermissionDenied("본인이 속한 조직과 그 하위 조직의 직원만 초대할 수 있습니다.")

                target = hr.get_person(person_id)
                if target is None:
                    raise RecordNotFound("직원을 찾을 수 없습니다.")

                # 초대는 초대자의 팀으로 들어온다. 수락하면 이 팀이 그 계정의 테넌트가 된다.
                cursor.execute(
                    "SELECT team_id FROM user_account WHERE account_id = %s", (invited_by,)
                )
                inviter_team_id = cursor.fetchone()["team_id"]
                if inviter_team_id is None:
                    raise PermissionDenied("팀을 먼저 만들어야 팀원을 초대할 수 있습니다.")

                scope = hr.subtree_org_ids(inviter["org_id"])
                person_org_id = target["org_id"]
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
                        (invite_id, team_org_id, team_id, person_id, invited_by, token_hash, expires_at)
                    VALUES (%s, %s, %s, %s, %s, %s, now() + make_interval(days => %s))
                    RETURNING invite_id, team_org_id, team_id, person_id, invited_by, status,
                              expires_at, accepted_at, created_at
                    """,
                    (
                        invite_id,
                        person_org_id,
                        inviter_team_id,
                        person_id,
                        invited_by,
                        token_hash,
                        OpsPolicyRepository.get_invite_ttl_days(),
                    ),
                )
                invite = cursor.fetchone()

        # 조직 이름은 초대가 가리키는 팀 기준이다(위에서 `person_org_id`로 저장한 값).
        return {
            **invite,
            "person_name": target["name"],
            "person_email": target["email"],
            "org_name": target["org_name"],
        }

    @staticmethod
    def list_by_inviter(account_id: str) -> list[dict[str, Any]]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        mi.invite_id,
                        mi.person_id,
                        mi.team_org_id AS org_id,
                        mi.expires_at,
                        mi.accepted_at,
                        mi.created_at,
                        CASE
                            WHEN mi.status = 'PENDING' AND mi.expires_at <= now() THEN 'EXPIRED'
                            ELSE mi.status
                        END AS status
                    FROM member_invite AS mi
                    WHERE mi.invited_by = %s
                    ORDER BY mi.created_at DESC
                    """,
                    (account_id,),
                )
                rows = list(cursor.fetchall())

        return _attach_person_display(rows, org_key="org_id")

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
                        mi.person_id,
                        mi.team_org_id AS org_id,
                        mi.expires_at
                    FROM member_invite AS mi
                    WHERE mi.token_hash = %s
                      AND mi.status = 'PENDING'
                      AND mi.expires_at > now()
                    """,
                    (token_hash,),
                )
                row = cursor.fetchone()

        if row is None:
            raise RecordNotFound("사용할 수 없는 초대 코드입니다. 만료됐거나 이미 사용된 코드인지 확인해 주세요.")
        return _attach_person_display([row], org_key="org_id")[0]

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
            RETURNING invite_id, person_id, team_id
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

        # 수락하는 순간 초대가 실어온 팀이 이 계정의 테넌트가 된다. 팀원 명부에도
        # 넣는다 — 팀장이 고를 때 이미 들어갔을 수 있으므로 중복은 무시한다.
        if invite["team_id"] is not None:
            cursor.execute(
                "UPDATE user_account SET team_id = %s WHERE account_id = %s",
                (invite["team_id"], account_id),
            )
            TeamRepository.add_member(
                cursor, team_id=invite["team_id"], person_id=invite["person_id"]
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

        if not hr.is_available():
            raise ReferenceNotFound(
                "HR 시스템에서 조직·직원 데이터를 찾을 수 없습니다. 운영자에게 문의해 주세요."
            )

        with database_connection() as connection:
            with connection.cursor() as cursor:
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

                # 이미 확인이 끝난 계정이면 회사가 정해져 있으므로 그 안에서 찾는다.
                if person_id is not None:
                    return hr.get_person(person_id)

                # 아직 확인 전이라 이 계정의 회사를 모른다. 목업의 유일한 비스코프
                # 지점이다(어댑터의 `discover_person_by_email` 주석 참고).
                row = hr.discover_person_by_email(email)
                # 이미 다른 계정이 가져간 사람은 후보로 내놓지 않는다.
                if row is not None and _person_already_linked(cursor, row["person_id"]):
                    row = None

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
        """연결 확인 화면에 보여줄 요약.

        `scope_person_count`는 팀을 만들 때 고를 수 있는 범위(본인 소속 조직의
        하위)다. 팀 인원이 아니라 **후보 인원**이라는 뜻이다 — 이 화면은 팀을
        만들기 전에 보이기 때문이다.

        `user_person_link`는 플랫폼 테이블이라 호출자의 커서로 읽는다(연결
        트랜잭션이 방금 만든 링크를 봐야 한다). HR 데이터는 어댑터로 읽는다.
        """

        summary: dict[str, Any] = {
            "org_count": 0,
            "person_count": 0,
            "person": None,
            "my_org_name": None,
            "my_org_person_count": 0,
            "scope_person_count": 0,
        }

        person_id = _linked_person_id(cursor, account_id)
        if person_id is None:
            return summary

        person = hr.get_person(person_id)
        summary["person"] = person
        if person is None:
            return summary
        summary["my_org_name"] = person["org_name"]

        scope = hr.subtree_org_ids(person["org_id"])
        if not scope:
            return summary

        in_scope = hr.list_persons(org_ids=scope)
        summary["org_count"] = len(scope)
        summary["person_count"] = len(in_scope)
        summary["scope_person_count"] = len(in_scope)
        summary["my_org_person_count"] = sum(1 for p in in_scope if p["org_id"] == person["org_id"])
        return summary


class OpsOverviewRepository:
    """운영자 콘솔 `운영 현황`(`GET /api/ops/overview/`) 집계 전용.

    "중복 연결" 판정은 `_DUP_ACCOUNTS_CTE`를 공유해서 계정 관리·계정 연결
    현황과 항상 같은 정의를 쓴다.
    """

    @staticmethod
    def summary() -> dict[str, Any]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    WITH {_DUP_ACCOUNTS_CTE}
                    SELECT
                        (SELECT count(*) FROM team) AS team_total,
                        (SELECT count(*) FROM user_account) AS account_total,
                        (SELECT count(*) FROM user_account WHERE account_status = 'LOCKED') AS account_locked,
                        (SELECT count(*) FROM dup_accounts) AS account_duplicate_mapping,
                        (
                            SELECT count(*) FROM user_account ua
                            WHERE ua.account_status = 'LOCKED'
                               OR ua.account_id IN (SELECT account_id FROM dup_accounts)
                        ) AS account_needs_review,
                        (SELECT count(*) FROM connector_conn) AS connector_total,
                        (SELECT count(*) FROM connector_conn WHERE auth_status = 'CONNECTED') AS connector_connected,
                        (SELECT count(*) FROM connector_conn WHERE auth_status = 'EXPIRED') AS connector_expired,
                        (SELECT count(*) FROM connector_conn WHERE auth_status = 'ERROR') AS connector_error,
                        (
                            SELECT count(*) FROM member_invite
                            WHERE status = 'PENDING' AND expires_at > now()
                        ) AS invite_pending,
                        (
                            SELECT count(*) FROM member_invite
                            WHERE status = 'PENDING' AND expires_at > now()
                              AND expires_at::date = CURRENT_DATE
                        ) AS invite_expiring_today
                    """
                )
                totals = cursor.fetchone()

                cursor.execute(
                    """
                    SELECT
                        al.audit_id, al.action, al.target_type, al.target_id, al.occurred_at,
                        ua.display_name AS actor_display_name, ua.email AS actor_email
                    FROM audit_log AS al
                    LEFT JOIN user_account AS ua ON ua.account_id = al.actor_account_id
                    ORDER BY al.occurred_at DESC
                    LIMIT 5
                    """
                )
                recent_activity = list(cursor.fetchall())

        return {
            "team_count": totals["team_total"],
            "org_count": hr.count_orgs(),
            "accounts": {
                "total": totals["account_total"],
                "locked": totals["account_locked"],
                "duplicate_mapping": totals["account_duplicate_mapping"],
                "needs_review": totals["account_needs_review"],
            },
            "connectors": {
                "total": totals["connector_total"],
                "connected": totals["connector_connected"],
                "expired": totals["connector_expired"],
                "error": totals["connector_error"],
            },
            "invites": {
                "pending": totals["invite_pending"],
                "expiring_today": totals["invite_expiring_today"],
            },
            "recent_activity": recent_activity,
        }


class OpsTeamRepository:
    """운영자 콘솔 `팀 현황`(`GET /api/ops/teams/`) 전용.

    운영자가 봐야 하는 단위는 HR 조직도가 아니라 **팀**이다. 우리 플랫폼을 쓰는
    것이 팀이기 때문이다(회사 전체가 아니다 — [[HR_어댑터와_테넌트_경계]]).
    조직도는 고객사 내부 사정이라 운영자가 알 필요가 없다.

    HR(팀장·팀원 이름)은 어댑터로, 플랫폼(팀·계정)은 SQL로 읽어 파이썬에서 합친다.
    """

    @staticmethod
    def list_with_stats() -> list[dict[str, Any]]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        t.team_id,
                        t.name,
                        t.owner_account_id,
                        t.src_org_id,
                        t.created_at,
                        owner.email AS owner_email,
                        owner.display_name AS owner_display_name,
                        (SELECT count(*) FROM team_member tm WHERE tm.team_id = t.team_id)
                            AS member_count,
                        (SELECT count(*) FROM user_account ua WHERE ua.team_id = t.team_id)
                            AS account_count,
                        (SELECT count(*) FROM user_account ua
                          WHERE ua.team_id = t.team_id AND ua.account_status = 'LOCKED')
                            AS locked_count,
                        (SELECT count(*) FROM member_invite mi
                          WHERE mi.team_id = t.team_id AND mi.status = 'PENDING'
                            AND mi.expires_at > now())
                            AS pending_invite_count
                    FROM team AS t
                    LEFT JOIN user_account AS owner ON owner.account_id = t.owner_account_id
                    ORDER BY t.created_at DESC
                    """
                )
                rows = list(cursor.fetchall())

        # 팀장이 HR상 누구인지, 팀이 어느 조직에서 출발했는지 이름으로 보여준다.
        org_names = hr.lookup_orgs([r["src_org_id"] for r in rows if r["src_org_id"]])
        for row in rows:
            org = org_names.get(row["src_org_id"]) if row["src_org_id"] else None
            row["src_org_name"] = org["name"] if org else None
            # 아직 계정을 만들지 않은 팀원. 초대 대기이거나 초대 전이다.
            row["unregistered_count"] = max(row["member_count"] - row["account_count"], 0)
        return rows


class OpsAccountRepository:
    """운영자 콘솔 `계정 관리`(`GET/POST /api/ops/accounts/...`) 전용.

    "중복 연결" 판정은 `_DUP_ACCOUNTS_CTE`를 공유해서 운영 현황·계정 연결
    현황과 항상 같은 정의를 쓴다. `mapping_status`(UNMAPPED/LINKED/DUPLICATE)
    는 여기서 계산하지 않고 API 응답 계층(`apps/ops/serializers.py`)에서
    `link_count`로부터 계산한다 — Repository는 원자료만 돌려준다.
    """

    @staticmethod
    def list() -> list[dict[str, Any]]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    WITH link_counts AS (
                        SELECT account_id, count(*) AS link_count
                        FROM user_person_link
                        WHERE mapping_status = 'VERIFIED'
                        GROUP BY account_id
                    ),
                    {_REPRESENTATIVE_LINK_CTE},
                    connected_services AS (
                        -- People DB는 본인 확인용 내부 커넥터라 "연결 서비스"가 아니다
                        -- (연결 서비스 현황과 같은 정의 — OpsConnectorRepository.list() 참고).
                        SELECT account_id, array_agg(DISTINCT connector_type ORDER BY connector_type) AS services
                        FROM connector_conn
                        WHERE auth_status = 'CONNECTED' AND connector_type <> 'PEOPLE_DB'
                        GROUP BY account_id
                    )
                    SELECT
                        ua.account_id,
                        ua.email,
                        ua.display_name,
                        ua.account_status,
                        ua.team_id,
                        t.name AS team_name,
                        COALESCE(lc.link_count, 0) AS link_count,
                        rl.person_id,
                        cs.services
                    FROM user_account AS ua
                    LEFT JOIN team AS t ON t.team_id = ua.team_id
                    LEFT JOIN link_counts AS lc ON lc.account_id = ua.account_id
                    LEFT JOIN representative_link AS rl ON rl.account_id = ua.account_id
                    LEFT JOIN connected_services AS cs ON cs.account_id = ua.account_id
                    ORDER BY ua.account_id
                    """
                )
                rows = list(cursor.fetchall())

        return _attach_person_display(rows)

    @staticmethod
    def lock(*, account_id: str, actor_account_id: str) -> dict[str, Any]:
        return OpsAccountRepository._set_status(
            account_id=account_id,
            actor_account_id=actor_account_id,
            new_status="LOCKED",
            action="ACCOUNT_LOCK",
        )

    @staticmethod
    def unlock(*, account_id: str, actor_account_id: str) -> dict[str, Any]:
        return OpsAccountRepository._set_status(
            account_id=account_id,
            actor_account_id=actor_account_id,
            new_status="ACTIVE",
            action="ACCOUNT_UNLOCK",
        )

    @staticmethod
    def _set_status(*, account_id: str, actor_account_id: str, new_status: str, action: str) -> dict[str, Any]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                # 동시에 들어온 잠금/해제 요청이 서로 낡은 상태를 덮어쓰지 않도록 잠근다.
                cursor.execute(
                    "SELECT account_id, account_status FROM user_account WHERE account_id = %s FOR UPDATE",
                    (account_id,),
                )
                account = cursor.fetchone()
                if account is None:
                    raise RecordNotFound(f"존재하지 않는 계정입니다: {account_id}")
                if account["account_status"] == "WITHDRAWN":
                    raise RepositoryError("탈퇴한 계정은 상태를 변경할 수 없습니다.")
                if new_status == "LOCKED" and account_id == actor_account_id:
                    raise PermissionDenied("본인 계정은 잠글 수 없습니다.")
                if account["account_status"] == new_status:
                    raise RepositoryError("이미 처리된 상태입니다.")

                cursor.execute(
                    "UPDATE user_account SET account_status = %s WHERE account_id = %s",
                    (new_status, account_id),
                )
                log_with(
                    cursor,
                    actor_account_id=actor_account_id,
                    action=action,
                    target_type="ACCOUNT",
                    target_id=account_id,
                    payload={"before": account["account_status"], "after": new_status},
                )

        return {"account_id": account_id, "account_status": new_status}

    @staticmethod
    def unlink_all(*, account_id: str, actor_account_id: str) -> dict[str, Any]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM user_account WHERE account_id = %s", (account_id,))
                if cursor.fetchone() is None:
                    raise RecordNotFound(f"존재하지 않는 계정입니다: {account_id}")

                cursor.execute(
                    """
                    UPDATE user_person_link
                    SET mapping_status = 'REVOKED', revoked_at = now()
                    WHERE account_id = %s AND mapping_status = 'VERIFIED'
                    RETURNING person_id
                    """,
                    (account_id,),
                )
                revoked_person_ids = [row["person_id"] for row in cursor.fetchall()]
                if not revoked_person_ids:
                    raise RecordNotFound("연결된 직원 정보가 없습니다.")

                log_with(
                    cursor,
                    actor_account_id=actor_account_id,
                    action="ACCOUNT_UNLINK_PERSON",
                    target_type="ACCOUNT",
                    target_id=account_id,
                    payload={"revoked_person_ids": revoked_person_ids},
                )

        return {"account_id": account_id, "revoked_person_ids": revoked_person_ids}


class OpsInviteRepository:
    """운영자 콘솔 `계정 연결·초대 현황`(`GET/POST /api/ops/invites/...`) 전용.

    `MemberInviteRepository.list_by_inviter()`와 EXPIRED 계산 규칙은 같지만
    특정 초대자로 좁히지 않고 전 조직 초대를 대상으로 한다(운영자 권한).
    "중복 연결" 판정은 `_DUP_ACCOUNTS_CTE`를 공유해서 다른 섹션과 항상 같은
    정의를 쓴다.
    """

    @staticmethod
    def list() -> list[dict[str, Any]]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    WITH {_DUP_ACCOUNTS_CTE}
                    SELECT
                        mi.invite_id,
                        mi.person_id,
                        mi.team_org_id AS org_id,
                        mi.invited_by,
                        inviter.email AS inviter_email,
                        CASE
                            WHEN mi.status = 'PENDING' AND mi.expires_at <= now() THEN 'EXPIRED'
                            ELSE mi.status
                        END AS status,
                        mi.expires_at,
                        mi.accepted_at,
                        mi.created_at,
                        upl.account_id AS linked_account_id,
                        linked.email AS linked_account_email,
                        (
                            upl.account_id IS NOT NULL
                            AND upl.account_id IN (SELECT account_id FROM dup_accounts)
                        ) AS linked_account_duplicate
                    FROM member_invite AS mi
                    LEFT JOIN user_account AS inviter ON inviter.account_id = mi.invited_by
                    LEFT JOIN user_person_link AS upl
                        ON upl.person_id = mi.person_id AND upl.mapping_status = 'VERIFIED'
                    LEFT JOIN user_account AS linked ON linked.account_id = upl.account_id
                    ORDER BY mi.created_at DESC
                    """
                )
                rows = list(cursor.fetchall())

        # 조직은 초대가 가리키는 팀(`team_org_id`)이지 사람의 현재 소속이 아니다.
        return _attach_person_display(rows, org_key="org_id")

    @staticmethod
    def discard(*, invite_id: str, actor_account_id: str) -> dict[str, Any]:
        """대기 중(`PENDING`)인 초대만 폐기(`REVOKED`)한다.

        존재하지 않는 초대와, 존재하지만 이미 수락·만료 처리·취소된 초대를
        구분하지 않고 같은 메시지로 응답한다 — `MemberInviteRepository.revoke()`
        와 같은 방식.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE member_invite
                    SET status = 'REVOKED'
                    WHERE invite_id = %s AND status = 'PENDING'
                    RETURNING invite_id, person_id
                    """,
                    (invite_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    raise RecordNotFound("폐기할 수 있는 초대가 아닙니다.")

                log_with(
                    cursor,
                    actor_account_id=actor_account_id,
                    action="INVITE_DISCARD",
                    target_type="MEMBER_INVITE",
                    target_id=invite_id,
                    payload={"person_id": row["person_id"]},
                )

        return {"invite_id": invite_id, "status": "REVOKED"}

    @staticmethod
    def unlink_by_invite(*, invite_id: str, actor_account_id: str) -> dict[str, Any]:
        """이 초대로 연결된 계정의 직원 링크를 전부 해제한다.

        해제 자체는 `OpsAccountRepository.unlink_all()`을 그대로 재사용한다
        (계정 1개가 여러 직원에 연결돼 있으면 전부 해제 — 계정 관리 화면과
        동일한 동작).
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT person_id FROM member_invite WHERE invite_id = %s",
                    (invite_id,),
                )
                invite = cursor.fetchone()
                if invite is None:
                    raise RecordNotFound(f"존재하지 않는 초대입니다: {invite_id}")

                cursor.execute(
                    """
                    SELECT account_id FROM user_person_link
                    WHERE person_id = %s AND mapping_status = 'VERIFIED'
                    """,
                    (invite["person_id"],),
                )
                link = cursor.fetchone()
                if link is None:
                    raise RecordNotFound("이미 연결이 해제됐거나 연결된 적이 없는 초대입니다.")
                account_id = link["account_id"]

        result = OpsAccountRepository.unlink_all(account_id=account_id, actor_account_id=actor_account_id)
        return {"invite_id": invite_id, **result}


class OpsConnectorRepository:
    """운영자 콘솔 `연결 서비스 현황`(`GET /api/ops/connectors/`) 전용. 읽기 전용이다
    (실제 재연결은 계정 소유자가 설정 화면에서 하고, 운영자 콘솔에는 쓰기 작업이 없음).

    People DB는 제외한다 — Drive/Jira처럼 프로젝트가 의존하는 외부 데이터 소스가
    아니라, 가입 계정을 본인 PERSON에 연결하는 본인 확인 절차의 부산물일 뿐이다
    (`역할별_권한_정책.md` 핵심 원칙 1). "연결 서비스"라는 화면 개념과 섞이면
    운영자가 실제 점검해야 할 외부 연동 상태를 파악하기 어려워진다.

    대표 직원(`person`)은 `_REPRESENTATIVE_LINK_CTE`를 공유해서 계정 관리와 항상
    같은 규칙(가장 먼저 연결된 것)을 쓴다. `auth_status`에 대응하는 진단·다음 조치
    문구는 저장된 컬럼이 아니라 API 응답 계층(`apps/ops/serializers.py`)에서
    상태값으로부터 만든다 — Repository는 원자료만 돌려준다.
    """

    @staticmethod
    def list() -> list[dict[str, Any]]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    WITH {_REPRESENTATIVE_LINK_CTE}
                    SELECT
                        cc.conn_id,
                        cc.account_id,
                        ua.email AS owner_email,
                        cc.connector_type,
                        cc.auth_status,
                        cc.connected_at,
                        rl.person_id
                    FROM connector_conn AS cc
                    LEFT JOIN user_account AS ua ON ua.account_id = cc.account_id
                    LEFT JOIN representative_link AS rl ON rl.account_id = cc.account_id
                    WHERE cc.connector_type <> 'PEOPLE_DB'
                    ORDER BY cc.connected_at DESC
                    """
                )
                rows = list(cursor.fetchall())

        return _attach_person_display(rows)


class OpsAuditRepository:
    """운영자 콘솔 `감사 로그`(`GET /api/ops/audit/...`) 전용. 전부 읽기 전용이다.

    "운영 활동" 탭(`list_operations`)은 지금 바로 데이터가 쌓이지만(계정 잠금·
    초대 폐기 등 이 콘솔 자체의 조치 기록), "분석·결정 기록" 탭 4개
    (`list_assignment_runs`/`list_recommendations`/`list_validations`/
    `list_decisions`)가 조회하는 `reco_result`/`valid_result`/`decision_rec`는
    이 저장소에 아직 그 테이블에 쓰는 추천 파이프라인이 없어 항상 빈 목록을
    반환한다(`assign_run`만 `AnalysisRunRepository.create()`로 실제로 쓰임).
    파이프라인이 나중에 이 테이블에 쓰기 시작하면 이 API들은 코드 변경 없이
    바로 채워진다.
    """

    OPERATIONS_LIMIT = 200

    @staticmethod
    def list_operations() -> list[dict[str, Any]]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        al.audit_id,
                        al.actor_account_id,
                        ua.display_name AS actor_display_name,
                        ua.email AS actor_email,
                        al.action,
                        al.proj_id,
                        al.target_type,
                        al.target_id,
                        al.payload,
                        al.occurred_at
                    FROM audit_log AS al
                    LEFT JOIN user_account AS ua ON ua.account_id = al.actor_account_id
                    ORDER BY al.occurred_at DESC
                    LIMIT %s
                    """,
                    (OpsAuditRepository.OPERATIONS_LIMIT,),
                )
                return list(cursor.fetchall())

    @staticmethod
    def list_assignment_runs() -> list[dict[str, Any]]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        ar.run_id,
                        ar.snapshot_id,
                        sn.proj_id,
                        ar.readiness_id,
                        ar.model_version,
                        ar.policy_version,
                        ar.status,
                        ar.requested_by,
                        ua.display_name AS requester_display_name,
                        ua.email AS requester_email
                    FROM assign_run AS ar
                    LEFT JOIN ana_snapshot AS sn ON sn.snap_id = ar.snapshot_id
                    LEFT JOIN user_account AS ua ON ua.account_id = ar.requested_by
                    ORDER BY ar.run_id DESC
                    """
                )
                return list(cursor.fetchall())

    @staticmethod
    def list_recommendations() -> list[dict[str, Any]]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        rr.reco_id,
                        rr.run_id,
                        rr.task_id,
                        t.task_name,
                        rr.status,
                        rr.confidence,
                        rr.missing_data,
                        rr.limitations,
                        rr.assumptions
                    FROM reco_result AS rr
                    LEFT JOIN task AS t ON t.task_id = rr.task_id
                    ORDER BY rr.reco_id DESC
                    """
                )
                return list(cursor.fetchall())

    @staticmethod
    def list_validations() -> list[dict[str, Any]]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        vr.valid_id,
                        vr.reco_id,
                        rr.run_id,
                        rr.task_id,
                        vr.status,
                        vr.confidence,
                        vr.missing_data
                    FROM valid_result AS vr
                    LEFT JOIN reco_result AS rr ON rr.reco_id = vr.reco_id
                    ORDER BY vr.valid_id DESC
                    """
                )
                return list(cursor.fetchall())

    @staticmethod
    def list_decisions() -> list[dict[str, Any]]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        dr.decision_id,
                        dr.reco_id,
                        dr.valid_id,
                        dr.pm_action,
                        dr.reason,
                        dr.modified_cand_id,
                        dr.decided_by,
                        ua.display_name AS decider_display_name,
                        ua.email AS decider_email,
                        dr.decided_at
                    FROM decision_rec AS dr
                    LEFT JOIN user_account AS ua ON ua.account_id = dr.decided_by
                    ORDER BY dr.decided_at DESC
                    """
                )
                return list(cursor.fetchall())


def _notice_snapshot(notice: dict[str, Any]) -> dict[str, Any]:
    """감사 로그 payload에 남길 공지 스냅샷. `schedule_at`은 JSONB 저장을 위해 문자열로 바꾼다."""

    schedule_at = notice["schedule_at"]
    return {
        "title": notice["title"],
        "status": notice["status"],
        "schedule_at": schedule_at.isoformat() if schedule_at else None,
        "schedule_mode": notice["schedule_mode"],
    }


class OpsPolicyRepository:
    """운영자 콘솔 `전역 정책`(`GET/PUT/POST/DELETE /api/ops/policies/...`) 전용.

    초대 만료 기간은 `sys_setting`의 단일 행을 키-값으로 쓰고(첫 사용처가
    `MemberInviteRepository.create()`), 시스템 공지는 `sys_notice` CRUD,
    정책 변경 이력은 새 테이블 없이 기존 `audit_log`를 `action`으로 필터링해
    재사용한다.
    """

    INVITE_TTL_KEY = "INVITE_EXPIRE_DAYS"
    INVITE_TTL_MIN_DAYS = 1
    INVITE_TTL_MAX_DAYS = 90
    # `sys_setting` 시드 행이 없거나(볼륨을 비우지 않고 수동 반영한 경우) 값이
    # 손상돼도 초대 발급 전체가 막히지 않도록 두는 안전망 기본값. schema.sql의
    # 시드값과 같다.
    DEFAULT_INVITE_TTL_DAYS = 14

    POLICY_ACTIONS = (
        "POLICY_INVITE_TTL_CHANGE",
        "NOTICE_CREATE",
        "NOTICE_UPDATE",
        "NOTICE_DELETE",
    )

    @staticmethod
    def get_invite_ttl_days() -> int:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT setting_value FROM sys_setting WHERE setting_key = %s",
                    (OpsPolicyRepository.INVITE_TTL_KEY,),
                )
                row = cursor.fetchone()

        if row is None:
            return OpsPolicyRepository.DEFAULT_INVITE_TTL_DAYS
        try:
            return int(row["setting_value"])
        except (TypeError, ValueError):
            return OpsPolicyRepository.DEFAULT_INVITE_TTL_DAYS

    @staticmethod
    def set_invite_ttl_days(*, days: int, actor_account_id: str, reason: str = "") -> dict[str, Any]:
        if not (OpsPolicyRepository.INVITE_TTL_MIN_DAYS <= days <= OpsPolicyRepository.INVITE_TTL_MAX_DAYS):
            raise RepositoryError("초대 만료 기간은 1일에서 90일 사이로 입력해 주세요.")

        with database_connection() as connection:
            with connection.cursor() as cursor:
                # 동시에 들어온 저장 요청이 서로 낡은 "변경 없음" 판정을 내리지
                # 않도록 이 설정 행을 잠근다(계정 잠금/해제와 같은 패턴).
                cursor.execute(
                    "SELECT setting_value FROM sys_setting WHERE setting_key = %s FOR UPDATE",
                    (OpsPolicyRepository.INVITE_TTL_KEY,),
                )
                row = cursor.fetchone()
                current: int | None = None
                if row is not None:
                    try:
                        current = int(row["setting_value"])
                    except (TypeError, ValueError):
                        current = None

                if current == days:
                    raise RepositoryError("변경된 초대 정책이 없습니다.")

                if row is None:
                    cursor.execute(
                        "INSERT INTO sys_setting (setting_key, setting_value, updated_by) VALUES (%s, %s, %s)",
                        (OpsPolicyRepository.INVITE_TTL_KEY, str(days), actor_account_id),
                    )
                else:
                    cursor.execute(
                        """
                        UPDATE sys_setting
                        SET setting_value = %s, updated_by = %s, updated_at = now()
                        WHERE setting_key = %s
                        """,
                        (str(days), actor_account_id, OpsPolicyRepository.INVITE_TTL_KEY),
                    )

                log_with(
                    cursor,
                    actor_account_id=actor_account_id,
                    action="POLICY_INVITE_TTL_CHANGE",
                    target_type="SYS_SETTING",
                    # `audit_log.target_id`는 VARCHAR(5)라 "INVITE_EXPIRE_DAYS" 키를
                    # 그대로 담을 수 없다 — 어차피 이 action은 이 설정 하나뿐이라
                    # target_type만으로 식별 가능하므로 비워둔다.
                    target_id=None,
                    payload={"before": current, "after": days, "reason": reason.strip() or None},
                )

        return {"days": days}

    @staticmethod
    def list_notices() -> list[dict[str, Any]]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        n.notice_id, n.title, n.content, n.status,
                        n.schedule_at, n.schedule_mode,
                        n.created_by, ua.display_name AS created_by_name,
                        n.created_at, n.updated_at
                    FROM sys_notice AS n
                    LEFT JOIN user_account AS ua ON ua.account_id = n.created_by
                    ORDER BY n.created_at DESC
                    """
                )
                return list(cursor.fetchall())

    @staticmethod
    def create_notice(
        *,
        title: str,
        content: str,
        status: str,
        schedule_at: Any,
        schedule_mode: str,
        actor_account_id: str,
        reason: str = "",
    ) -> dict[str, Any]:
        title = (title or "").strip()
        content = (content or "").strip()
        if not title or not content:
            raise RepositoryError("공지 제목과 내용을 입력해 주세요.")
        if schedule_at is None:
            raise RepositoryError("공지 날짜와 시간을 선택해 주세요.")

        with database_connection() as connection:
            with connection.cursor() as cursor:
                notice_id = next_short_code(cursor, table="sys_notice", column="notice_id", prefix="NT")
                cursor.execute(
                    """
                    INSERT INTO sys_notice
                        (notice_id, title, content, status, schedule_at, schedule_mode, created_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING notice_id, title, content, status, schedule_at, schedule_mode,
                              created_by, created_at, updated_at
                    """,
                    (notice_id, title, content, status, schedule_at, schedule_mode, actor_account_id),
                )
                notice = cursor.fetchone()

                log_with(
                    cursor,
                    actor_account_id=actor_account_id,
                    action="NOTICE_CREATE",
                    target_type="SYS_NOTICE",
                    target_id=notice_id,
                    payload={"after": _notice_snapshot(notice), "reason": reason.strip() or None},
                )

        notice["created_by_name"] = None
        return notice

    @staticmethod
    def update_notice(
        *,
        notice_id: str,
        title: str,
        content: str,
        status: str,
        schedule_at: Any,
        schedule_mode: str,
        actor_account_id: str,
        reason: str = "",
    ) -> dict[str, Any]:
        title = (title or "").strip()
        content = (content or "").strip()
        if not title or not content:
            raise RepositoryError("공지 제목과 내용을 입력해 주세요.")
        if schedule_at is None:
            raise RepositoryError("공지 날짜와 시간을 선택해 주세요.")

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM sys_notice WHERE notice_id = %s FOR UPDATE", (notice_id,))
                before = cursor.fetchone()
                if before is None:
                    raise RecordNotFound("존재하지 않는 공지입니다.")

                cursor.execute(
                    """
                    UPDATE sys_notice
                    SET title = %s, content = %s, status = %s,
                        schedule_at = %s, schedule_mode = %s, updated_at = now()
                    WHERE notice_id = %s
                    RETURNING notice_id, title, content, status, schedule_at, schedule_mode,
                              created_by, created_at, updated_at
                    """,
                    (title, content, status, schedule_at, schedule_mode, notice_id),
                )
                notice = cursor.fetchone()

                log_with(
                    cursor,
                    actor_account_id=actor_account_id,
                    action="NOTICE_UPDATE",
                    target_type="SYS_NOTICE",
                    target_id=notice_id,
                    payload={
                        "before": _notice_snapshot(before),
                        "after": _notice_snapshot(notice),
                        "reason": reason.strip() or None,
                    },
                )

        notice["created_by_name"] = None
        return notice

    @staticmethod
    def delete_notice(*, notice_id: str, actor_account_id: str, reason: str = "") -> None:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM sys_notice WHERE notice_id = %s RETURNING *", (notice_id,))
                before = cursor.fetchone()
                if before is None:
                    raise RecordNotFound("존재하지 않는 공지입니다.")

                log_with(
                    cursor,
                    actor_account_id=actor_account_id,
                    action="NOTICE_DELETE",
                    target_type="SYS_NOTICE",
                    target_id=notice_id,
                    payload={"before": _notice_snapshot(before), "reason": reason.strip() or None},
                )

    @staticmethod
    def list_policy_changes() -> list[dict[str, Any]]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        al.audit_id, al.action, al.target_type, al.target_id, al.payload,
                        al.actor_account_id, ua.display_name AS actor_display_name,
                        ua.email AS actor_email, al.occurred_at
                    FROM audit_log AS al
                    LEFT JOIN user_account AS ua ON ua.account_id = al.actor_account_id
                    WHERE al.action = ANY(%s)
                    ORDER BY al.occurred_at DESC
                    """,
                    (list(OpsPolicyRepository.POLICY_ACTIONS),),
                )
                return list(cursor.fetchall())
