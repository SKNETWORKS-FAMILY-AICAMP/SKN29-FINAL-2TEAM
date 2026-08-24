"""현재 `DB/schema.sql`을 기준으로 한 직접 SQL Repository."""

from datetime import datetime
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


def _hr_weekly_hours(profile: dict[str, Any]) -> float | None:
    """HR이 아는 주 근무시간. `services/workload/calculator._weekly_hours`와 같은 규칙.

    두 곳이 다르면 설정 화면이 말하는 기준과 실제 계산이 어긋난다. 계산기는
    순수 함수라 여기서 부를 수 없어(레이어가 반대다) 규칙만 맞춘다.
    """

    wk_hours = profile.get("wk_hours")
    if wk_hours is not None:
        return float(wk_hours)

    default_hours = profile.get("def_wk_hours")
    fte = profile.get("fte")
    if default_hours is None or fte is None:
        return None
    return float(default_hours) * float(fte)


def _team_of(cursor, account_id: str) -> str | None:
    """이 계정이 속한 팀. 테넌트 경계라 거의 모든 조회가 먼저 이걸 묻는다."""

    cursor.execute("SELECT team_id FROM user_account WHERE account_id = %s", (account_id,))
    row = cursor.fetchone()
    return row["team_id"] if row else None


def _require_team(cursor, account_id: str) -> str:
    """쓰기 경로용. 팀이 없으면 저장할 곳이 없다는 뜻이라 거절한다."""

    team_id = _team_of(cursor, account_id)
    if team_id is None:
        raise PermissionDenied("팀에 속하지 않은 계정입니다.")
    return team_id


def _require_team_project(cursor, *, proj_id: str, account_id: str) -> str:
    """이 프로젝트가 내 팀 것인지 확인하고 팀 id를 돌려준다.

    소유자 검사가 아니라 팀 검사다 — 팀원도 팀의 프로젝트를 다룰 수 있어야 한다.
    """

    team_id = _require_team(cursor, account_id)
    cursor.execute("SELECT team_id FROM proj WHERE proj_id = %s", (proj_id,))
    row = cursor.fetchone()
    if row is None:
        raise RecordNotFound(f"존재하지 않는 프로젝트입니다: {proj_id}")
    if row["team_id"] != team_id:
        raise PermissionDenied("이 프로젝트에 접근할 수 없습니다.")
    return team_id


class ProjectRepository:
    @staticmethod
    def list_for_team(account_id: str) -> list[dict[str, Any]]:
        """요청자 팀의 프로젝트.

        소유자 기준이 아니라 **팀 기준**이다(2026-08-04). 테넌트 경계가 팀이므로
        팀원도 팀의 프로젝트를 봐야 한다. 소유자로 거르면 팀장이 등록한 프로젝트가
        팀원 화면에서 통째로 사라진다.

        팀이 없는 계정은 빈 목록이다 — 남의 프로젝트를 보여줄 이유가 없다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _team_of(cursor, account_id)
                if team_id is None:
                    return []

                cursor.execute(
                    """
                    SELECT
                        p.proj_id,
                        p.name,
                        p.description,
                        p.status,
                        p.tz,
                        p.owner_account_id,
                        p.team_id,
                        p.created_at,
                        ua.display_name AS owner_name
                    FROM proj AS p
                    LEFT JOIN user_account AS ua
                      ON ua.account_id = p.owner_account_id
                    WHERE p.team_id = %s
                    ORDER BY p.proj_id
                    """,
                    (team_id,),
                )
                return list(cursor.fetchall())

    @staticmethod
    def get_for_team(*, proj_id: str, account_id: str) -> dict[str, Any]:
        """상세 화면이 쓰는 단건 조회. 내 팀 것이 아니면 막는다."""

        with database_connection() as connection:
            with connection.cursor() as cursor:
                _require_team_project(cursor, proj_id=proj_id, account_id=account_id)
                cursor.execute(
                    """
                    SELECT p.proj_id, p.name, p.description, p.status, p.tz,
                           p.owner_account_id, p.team_id, p.created_at,
                           ua.display_name AS owner_name
                    FROM proj AS p
                    LEFT JOIN user_account AS ua ON ua.account_id = p.owner_account_id
                    WHERE p.proj_id = %s
                    """,
                    (proj_id,),
                )
                return cursor.fetchone()

    @staticmethod
    def sync_status_from_tasks(proj_ids: list[str]) -> dict[str, list[str]]:
        """Jira 를 다시 읽은 뒤 완료 여부를 그 결과에 맞춘다.

        **갱신을 눌렀다는 것은 Jira 상태로 다시 맞춰 달라는 뜻이다**(2026-08-13 PM).
        예전에는 등록 직후 딱 한 번만 판정했는데, 그 한 번을 놓치면 업무가 전부 끝난
        프로젝트가 영영 「진행중」에 남았다 — 실제로 12건이 전부 완료인 프로젝트가
        그렇게 남아 있었다.

        **다만 사람이 정한 것은 안 건드린다.** 한 번만 판정하던 원래 이유가 그거였다
        — 「진행 중으로」 되돌린 것을 다음 갱신이 도로 완료로 만들면 그 버튼이
        무의미해진다. 스키마를 늘리는 대신 **감사 로그를 근거로 쓴다**:
        `set_status` 가 남기는 `PROJECT_STATUS_CHANGE` 행이 하나라도 있으면 그
        프로젝트의 상태는 사람의 결정이므로 자동 판정에서 제외한다.

        양쪽으로 움직인다. 전부 끝났으면 완료로 내리고, **완료였는데 안 끝난 것이
        생겼으면 도로 올린다** — Jira 에서 이슈가 다시 열렸는데 우리 목록만 완료로
        남아 있으면 내려보내지 않은 것과 같은 종류의 거짓말이다.

        업무가 한 건도 없으면 내리지 않는다 — "미완료가 없다"가 참이 되어 빈
        프로젝트가 전부 완료로 떨어진다.
        """

        if not proj_ids:
            return {"archived": [], "reopened": []}

        ids = sorted(set(proj_ids))
        # 사람이 상태를 정한 적이 있는 프로젝트. 자동 판정에서 통째로 뺀다.
        decided = """
            NOT EXISTS (
                SELECT 1 FROM audit_log AS al
                WHERE al.proj_id = proj.proj_id AND al.action = 'PROJECT_STATUS_CHANGE'
            )
        """
        has_tasks = """
            EXISTS (
                SELECT 1 FROM exist_task AS et
                JOIN proj_source AS ps ON ps.proj_source_id = et.proj_source_id
                WHERE ps.proj_id = proj.proj_id
            )
        """
        has_open = """
            EXISTS (
                SELECT 1 FROM exist_task AS et
                JOIN proj_source AS ps ON ps.proj_source_id = et.proj_source_id
                WHERE ps.proj_id = proj.proj_id
                  AND et.status_category IS DISTINCT FROM 'DONE'
            )
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    UPDATE proj SET status = 'ARCHIVED'
                     WHERE proj_id = ANY(%s) AND status = 'ACTIVE'
                       AND {decided} AND {has_tasks} AND NOT {has_open}
                    RETURNING proj_id
                    """,
                    (ids,),
                )
                archived = [row["proj_id"] for row in cursor.fetchall()]

                cursor.execute(
                    f"""
                    UPDATE proj SET status = 'ACTIVE'
                     WHERE proj_id = ANY(%s) AND status = 'ARCHIVED'
                       AND {decided} AND {has_open}
                    RETURNING proj_id
                    """,
                    (ids,),
                )
                reopened = [row["proj_id"] for row in cursor.fetchall()]

        return {"archived": archived, "reopened": reopened}

    @staticmethod
    def set_status(*, proj_id: str, account_id: str, status: str) -> dict[str, Any]:
        """프로젝트 상태를 바꾼다. 「완료 처리」가 쓰는 유일한 경로다.

        진행률 100%를 완료로 자동 판정하지 않는다. 우리가 아는 것은 Jira에 등록된
        업무가 전부 끝났다는 사실뿐이고, 프로젝트가 끝났는지는 사람이 정한다 —
        등록되지 않은 마무리 작업이 남아 있을 수 있다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                _require_team_project(cursor, proj_id=proj_id, account_id=account_id)
                cursor.execute(
                    """
                    UPDATE proj SET status = %s WHERE proj_id = %s
                    RETURNING proj_id, name, status, tz, owner_account_id, team_id, created_at
                    """,
                    (status, proj_id),
                )
                row = cursor.fetchone()
                log_with(
                    cursor,
                    actor_account_id=account_id,
                    action="PROJECT_STATUS_CHANGE",
                    proj_id=proj_id,
                    target_type="PROJECT",
                    target_id=proj_id,
                    payload={"status": status},
                )

        row["owner_name"] = None
        return row

    @staticmethod
    def delete(*, proj_id: str, account_id: str) -> dict[str, int]:
        """프로젝트와 그 프로젝트에만 속한 것을 지운다.

        **문서는 지우지 않는다.** 기준 문서는 팀 문서 풀에서 온 것이라 프로젝트에
        잠깐 묶였을 뿐이고, 프로젝트를 접었다고 원문과 파싱 결과까지 버리면 다시
        등록·처리해야 한다. `proj_id`와 `doc_role`만 풀어 풀로 돌려보낸다.

        **Jira 업무는 함께 지운다.** `exist_task`는 이 프로젝트의 Jira 소스를 읽어
        만든 사본이고, 소스가 사라지면 다시 만들 수 있다. 남겨 두면 어느 프로젝트
        것인지 알 수 없는 고아 행이 되어 팀 부하 계산에 계속 끼어든다.

        감사 로그는 남긴다. 프로젝트가 있었다는 사실과 누가 지웠는지는 프로젝트가
        사라진 뒤에 더 필요하다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                _require_team_project(cursor, proj_id=proj_id, account_id=account_id)
                cursor.execute("SELECT name FROM proj WHERE proj_id = %s", (proj_id,))
                name = (cursor.fetchone() or {}).get("name")

                cursor.execute(
                    """
                    DELETE FROM exist_task_snap WHERE exist_task_id IN (
                        SELECT e.exist_task_id FROM exist_task e
                        JOIN proj_source s ON s.proj_source_id = e.proj_source_id
                        WHERE s.proj_id = %s
                    )
                    """,
                    (proj_id,),
                )
                cursor.execute(
                    """
                    DELETE FROM exist_task WHERE proj_source_id IN (
                        SELECT proj_source_id FROM proj_source WHERE proj_id = %s
                    )
                    """,
                    (proj_id,),
                )
                tasks = cursor.rowcount

                cursor.execute("DELETE FROM proj_source WHERE proj_id = %s", (proj_id,))
                sources = cursor.rowcount

                cursor.execute(
                    "UPDATE doc SET proj_id = NULL, doc_role = NULL WHERE proj_id = %s",
                    (proj_id,),
                )
                documents = cursor.rowcount

                for table in ("proj_member", "ana_snapshot", "know_item", "proj_know_model"):
                    cursor.execute(f"DELETE FROM {table} WHERE proj_id = %s", (proj_id,))

                cursor.execute("DELETE FROM proj WHERE proj_id = %s", (proj_id,))

                log_with(
                    cursor,
                    actor_account_id=account_id,
                    action="PROJECT_DELETE",
                    target_type="PROJECT",
                    target_id=proj_id,
                    payload={
                        "name": name,
                        "tasks": tasks,
                        "sources": sources,
                        "documents_released": documents,
                    },
                )

        return {"tasks": tasks, "sources": sources, "documents_released": documents}

    @staticmethod
    def create(
        *,
        name: str,
        status: str,
        tz: str,
        owner_account_id: str | None,
        description: str | None = None,
    ) -> dict[str, Any]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = None
                if owner_account_id:
                    _require_record(
                        cursor,
                        table="user_account",
                        column="account_id",
                        value=owner_account_id,
                        label="사용자 계정",
                    )
                    team_id = _team_of(cursor, owner_account_id)

                proj_id = next_short_code(
                    cursor,
                    table="proj",
                    column="proj_id",
                    prefix="PJ",
                )
                cursor.execute(
                    """
                    INSERT INTO proj (proj_id, name, description, status, tz,
                                      owner_account_id, team_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING proj_id, name, description, status, tz,
                              owner_account_id, team_id, created_at
                    """,
                    (proj_id, name, description, status, tz, owner_account_id, team_id),
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


def _connected_conn_id(cursor, *, account_id: str, connector_type: str) -> str:
    """이 계정의 살아 있는 커넥터 연결. 요청에서 `conn_id`를 받지 않는 이유는
    남의 연결에 소스를 매달 수 없어야 하기 때문이다."""

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
    row = cursor.fetchone()
    if row is None:
        raise ReferenceNotFound(f"{connector_type} 커넥터가 연결되지 않았습니다.")
    return row["conn_id"]


class ProjectSourceRepository:
    """프로젝트가 대응하는 Jira 프로젝트(`proj_source`). **1:1이다**(2026-08-04).

    Jira 프로젝트 하나에는 프로젝트 하나의 업무가 들어 있다. 여러 개를 한
    프로젝트에 매달면 서로 다른 프로젝트의 업무가 한 진행률로 뭉개진다.

    Drive 폴더는 여기 없다 — 폴더는 파일이 있는 경로일 뿐 프로젝트에 속하지
    않아서 `TeamFolderRepository`로 옮겼다.
    """

    JIRA_PROJECT = "JIRA_PROJECT"
    JIRA_CONNECTOR = "JIRA"

    @staticmethod
    def get_for_project(*, proj_id: str, account_id: str) -> dict[str, Any] | None:
        """이 프로젝트의 Jira 소스. 아직 연결 안 됐으면 `None`."""

        with database_connection() as connection:
            with connection.cursor() as cursor:
                _require_team_project(cursor, proj_id=proj_id, account_id=account_id)
                cursor.execute(
                    """
                    SELECT proj_source_id, proj_id, conn_id, source_type, external_source_id,
                           display_name, sync_status, last_sync_at
                    FROM proj_source
                    WHERE proj_id = %s
                    """,
                    (proj_id,),
                )
                return cursor.fetchone()

    @staticmethod
    def last_sync_by_project(proj_ids: list[str]) -> dict[str, datetime | None]:
        """프로젝트별 Jira 마지막 수집 시각. 목록 화면이 한 번에 받아 간다.

        Jira 소스가 없는 프로젝트는 아예 키가 없다 — 읽을 것이 없는 것과 안 읽은
        것을 화면이 구분할 수 있어야 한다. 아직 한 번도 안 읽었으면 `None`이다.
        """

        if not proj_ids:
            return {}

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT proj_id,
                           count(*) FILTER (WHERE last_sync_at IS NULL) AS never_synced,
                           min(last_sync_at) AS last_sync_at
                    FROM proj_source
                    WHERE proj_id = ANY(%s) AND source_type = %s
                    GROUP BY proj_id
                    """,
                    (sorted(set(proj_ids)), ProjectSourceRepository.JIRA_PROJECT),
                )
                return {
                    row["proj_id"]: None if row["never_synced"] else row["last_sync_at"]
                    for row in cursor.fetchall()
                }

    @staticmethod
    def register_from_jira(
        *,
        account_id: str,
        selections: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        """고른 Jira 프로젝트를 **우리 프로젝트로 등록한다.**

        Jira 프로젝트 하나가 프로젝트 하나이므로, 고르는 행위가 곧 등록이다.
        `selections`는 `[{"project_key": "KAN", "name": "SKN29_Final_2Team"}]`.

        이미 등록된 키는 이름만 갱신하고 프로젝트를 새로 만들지 않는다 — 다시
        저장했다고 같은 Jira 프로젝트가 둘이 되면 업무가 양쪽에 중복된다.

        선택에서 빠진 키는 `proj_source`만 지운다. **프로젝트는 남긴다** —
        문서가 붙어 있을 수 있고, 체크 한 번 푼 것으로 되돌릴 수 없는 삭제를
        하지 않는다. 화면에는 "Jira 연결 없음"으로 보인다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team(cursor, account_id)
                conn_id = _connected_conn_id(
                    cursor,
                    account_id=account_id,
                    connector_type=ProjectSourceRepository.JIRA_CONNECTOR,
                )

                # 같은 키를 두 번 보내도 한 번만 다룬다.
                chosen: dict[str, str] = {}
                for item in selections:
                    chosen.setdefault(item["project_key"], item.get("name") or "")

                cursor.execute(
                    """
                    SELECT ps.proj_source_id, ps.external_source_id, ps.proj_id
                    FROM proj_source AS ps
                    JOIN proj AS p ON p.proj_id = ps.proj_id
                    WHERE p.team_id = %s
                    """,
                    (team_id,),
                )
                registered = {row["external_source_id"]: row for row in cursor.fetchall()}

                for key, existing in registered.items():
                    if key in chosen:
                        continue
                    cursor.execute(
                        "DELETE FROM exist_task WHERE proj_source_id = %s",
                        (existing["proj_source_id"],),
                    )
                    cursor.execute(
                        "DELETE FROM proj_source WHERE proj_source_id = %s",
                        (existing["proj_source_id"],),
                    )

                for key, name in chosen.items():
                    if key in registered:
                        # 이름이 안 왔으면 저장된 값을 지킨다 — 이름만 빠진 요청
                        # 때문에 표시가 키로 되돌아가지 않도록.
                        cursor.execute(
                            """
                            UPDATE proj_source
                               SET display_name = COALESCE(NULLIF(%s, ''), display_name),
                                   conn_id = %s
                             WHERE proj_source_id = %s
                            """,
                            (name, conn_id, registered[key]["proj_source_id"]),
                        )
                        cursor.execute(
                            """
                            UPDATE proj SET name = COALESCE(NULLIF(%s, ''), name)
                             WHERE proj_id = %s
                            """,
                            (name, registered[key]["proj_id"]),
                        )
                        continue

                    proj_id = next_short_code(cursor, table="proj", column="proj_id", prefix="PJ")
                    cursor.execute(
                        """
                        INSERT INTO proj (proj_id, name, status, tz, owner_account_id, team_id)
                        VALUES (%s, %s, 'ACTIVE', 'Asia/Seoul', %s, %s)
                        """,
                        (proj_id, name or key, account_id, team_id),
                    )
                    member_id = next_short_code(
                        cursor, table="proj_member", column="proj_member_id", prefix="PM"
                    )
                    cursor.execute(
                        """
                        INSERT INTO proj_member (proj_member_id, proj_id, account_id, access_role)
                        VALUES (%s, %s, %s, 'OWNER')
                        """,
                        (member_id, proj_id, account_id),
                    )

                    proj_source_id = next_short_code(
                        cursor, table="proj_source", column="proj_source_id", prefix="PS"
                    )
                    cursor.execute(
                        """
                        INSERT INTO proj_source
                            (proj_source_id, proj_id, conn_id, source_type, external_source_id,
                             display_name)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            proj_source_id,
                            proj_id,
                            conn_id,
                            ProjectSourceRepository.JIRA_PROJECT,
                            key,
                            name or None,
                        ),
                    )

                cursor.execute(
                    """
                    SELECT ps.proj_source_id, ps.proj_id, ps.conn_id, ps.source_type,
                           ps.external_source_id, ps.display_name, ps.sync_status, ps.last_sync_at
                    FROM proj_source AS ps
                    JOIN proj AS p ON p.proj_id = ps.proj_id
                    WHERE p.team_id = %s
                    ORDER BY ps.proj_source_id
                    """,
                    (team_id,),
                )
                return list(cursor.fetchall())


class TeamFolderRepository:
    """팀이 읽어들일 Drive 폴더(`team_folder`).

    **프로젝트가 아니라 팀에 매단다.** 폴더는 파일이 어디 있는지 알려주는 경로일
    뿐이고, 그 안의 파일이 어느 프로젝트 것인지는 열어 봐야 안다. 프로젝트마다
    폴더를 고르게 하면 같은 경로를 프로젝트 수만큼 반복해서 등록하게 된다.
    """

    DRIVE_CONNECTOR = "GOOGLE_DRIVE"

    @staticmethod
    def list_for_team(account_id: str) -> list[dict[str, Any]]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _team_of(cursor, account_id)
                if team_id is None:
                    return []
                cursor.execute(
                    """
                    SELECT team_folder_id, team_id, conn_id, external_folder_id,
                           display_name, default_doc_role, max_depth
                    FROM team_folder
                    WHERE team_id = %s
                    ORDER BY team_folder_id
                    """,
                    (team_id,),
                )
                return list(cursor.fetchall())

    @staticmethod
    def replace(
        *,
        account_id: str,
        external_folder_ids: list[str],
        max_depth: int | None = None,
        display_names: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """팀이 읽을 폴더를 넘겨받은 목록으로 교체한다.

        선택 화면은 항상 전체 선택 상태를 보내므로 교체가 맞다. 덧붙이면 화면에서
        해제한 폴더가 남는다. 계속 선택된 폴더의 `default_doc_role`은 지키고
        넘어간다 — 폴더를 다시 저장했다고 역할 지정을 날릴 이유가 없다.

        해제된 것만 지운다. 전부 지우고 다시 넣으면 `next_short_code`가 같은 id를
        새 순서로 재발급해, 이 id를 참조하는 행이 조용히 다른 폴더에 붙는다.

        `max_depth`는 이번에 저장하는 모든 폴더에 같은 값으로 들어간다. 화면의
        탐색 깊이 설정이 폴더별이 아니라 하나이기 때문이다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team(cursor, account_id)
                conn_id = _connected_conn_id(
                    cursor,
                    account_id=account_id,
                    connector_type=TeamFolderRepository.DRIVE_CONNECTOR,
                )

                selected = list(dict.fromkeys(external_folder_ids))
                names = display_names or {}

                cursor.execute(
                    """
                    DELETE FROM team_folder
                    WHERE team_id = %s AND NOT (external_folder_id = ANY(%s))
                    """,
                    (team_id, selected),
                )

                cursor.execute(
                    "SELECT external_folder_id FROM team_folder WHERE team_id = %s",
                    (team_id,),
                )
                existing = {row["external_folder_id"] for row in cursor.fetchall()}

                for external_folder_id in selected:
                    if external_folder_id in existing:
                        cursor.execute(
                            """
                            UPDATE team_folder
                               SET display_name = COALESCE(%s, display_name),
                                   max_depth = %s,
                                   conn_id = %s
                             WHERE team_id = %s AND external_folder_id = %s
                            """,
                            (
                                names.get(external_folder_id),
                                max_depth,
                                conn_id,
                                team_id,
                                external_folder_id,
                            ),
                        )
                        continue

                    team_folder_id = next_short_code(
                        cursor, table="team_folder", column="team_folder_id", prefix="TF"
                    )
                    cursor.execute(
                        """
                        INSERT INTO team_folder
                            (team_folder_id, team_id, conn_id, external_folder_id,
                             display_name, max_depth)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            team_folder_id,
                            team_id,
                            conn_id,
                            external_folder_id,
                            names.get(external_folder_id),
                            max_depth,
                        ),
                    )

                cursor.execute(
                    """
                    SELECT team_folder_id, team_id, conn_id, external_folder_id,
                           display_name, default_doc_role, max_depth
                    FROM team_folder
                    WHERE team_id = %s
                    ORDER BY team_folder_id
                    """,
                    (team_id,),
                )
                return list(cursor.fetchall())


class DocumentRepository:
    """팀이 읽어들인 문서(`doc`). 역할 지정 화면이 쓰는 유일한 쓰기 경로다.

    **문서는 팀에 속한다**(2026-08-04). 등록 시점에는 어느 프로젝트의 문서인지
    모른다 — 파일을 열어 봐야 알 수 있다. `doc.proj_id`는 그 문서가 프로젝트의
    메인·서브 문서로 지정될 때 채워지고, 그때까지는 NULL이다.
    """

    DRIVE = "DRIVE"
    # 문서 처리 이력을 `audit_log`에서 다시 찾을 때 쓰는 표식.
    AUDIT_TARGET = "DOCUMENT"
    ACTION_REGISTER = "DOCUMENT_REGISTER"
    ACTION_DOWNLOAD = "DOCUMENT_DOWNLOAD"

    @staticmethod
    def list_for_team(account_id: str) -> list[dict[str, Any]]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _team_of(cursor, account_id)
                if team_id is None:
                    return []
                cursor.execute(
                    """
                    SELECT doc_id, team_id, proj_id, src_file_id, source_type, file_name,
                           mime_type, doc_role, src_modified_at, deleted, storage_key
                    FROM doc
                    WHERE team_id = %s AND deleted = false
                    ORDER BY doc_id
                    """,
                    (team_id,),
                )
                return list(cursor.fetchall())

    @staticmethod
    def list_pending_download(account_id: str) -> list[dict[str, Any]]:
        """아직 원문을 안 받았거나, 받은 뒤 Drive에서 수정된 문서.

        `src_modified_at`이 저장 시각보다 최신인지를 보지 않고 **리비전이 비었거나
        `storage_key`가 없는 것**만 고른다. 다시 받아야 하는지는 리비전 비교로
        판정하는 것이 맞지만, 그러려면 매번 Drive를 조회해야 해서 여기서는
        "아직 안 받은 것"만 다룬다. 재다운로드는 호출자가 강제할 수 있다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _team_of(cursor, account_id)
                if team_id is None:
                    return []
                cursor.execute(
                    """
                    SELECT doc_id, src_file_id, file_name, mime_type, storage_key, cur_revision
                    FROM doc
                    WHERE team_id = %s
                      AND deleted = false
                      AND source_type = %s
                      AND src_file_id IS NOT NULL
                    ORDER BY doc_id
                    """,
                    (team_id, DocumentRepository.DRIVE),
                )
                return list(cursor.fetchall())

    @staticmethod
    def registered_file_ids(account_id: str) -> set[str]:
        """이 팀이 이미 아는 Drive 파일 id.

        **`deleted`를 가리지 않는다.** 폴더에서 빠져 `deleted = true`가 된 문서도
        "이미 본 파일"이다 — 가리면 한 번 내린 문서가 스캔할 때마다 신규로 다시
        올라온다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _team_of(cursor, account_id)
                if team_id is None:
                    return set()
                cursor.execute(
                    """
                    SELECT src_file_id FROM doc
                    WHERE team_id = %s AND source_type = %s AND src_file_id IS NOT NULL
                    """,
                    (team_id, DocumentRepository.DRIVE),
                )
                return {row["src_file_id"] for row in cursor.fetchall()}

    @staticmethod
    def list_missing_from_drive(*, account_id: str, live_file_ids: set[str]) -> list[dict[str, Any]]:
        """Drive 스캔에 더 이상 안 잡히는 등록 문서.

        `live_file_ids`는 호출자가 방금 Drive 를 훑어 얻은 파일 id 전부다. 이
        메서드는 DB만 보고 그 여집합을 돌려줄 뿐, **아무것도 지우지 않는다** —
        내리는 것은 사람이 확인한 뒤 `mark_removed_from_drive()`가 한다.

        휴지통으로 옮긴 것, 완전히 지운 것, 폴더 밖으로 옮긴 것이 전부 똑같이
        「안 잡힘」으로 보인다(Drive 질의가 `trashed = false`다). 셋을 구분할 수
        없으니 자동으로 내리지 않는다.

        어느 프로젝트의 기준 문서였는지 함께 준다. 그게 사라졌다는 것은 그
        프로젝트의 업무 추출 근거가 없어졌다는 뜻이라 화면이 따로 알려야 한다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _team_of(cursor, account_id)
                if team_id is None:
                    return []
                cursor.execute(
                    """
                    SELECT d.doc_id, d.src_file_id, d.file_name, d.mime_type,
                           d.proj_id, d.doc_role, p.name AS project_name
                    FROM doc AS d
                    LEFT JOIN proj AS p ON p.proj_id = d.proj_id
                    WHERE d.team_id = %s AND d.source_type = %s
                      AND d.deleted = false AND d.src_file_id IS NOT NULL
                    ORDER BY d.doc_id
                    """,
                    (team_id, DocumentRepository.DRIVE),
                )
                return [
                    row for row in cursor.fetchall() if row["src_file_id"] not in live_file_ids
                ]

    @staticmethod
    def mark_removed_from_drive(*, account_id: str, doc_ids: list[str]) -> dict[str, int]:
        """고른 문서를 내리고 **파싱 산출물을 지운다.**

        `doc` 행은 남기고 `deleted`만 켠다. 그 행이 있어야 같은 파일이 신규로 다시
        올라오지 않고(`registered_file_ids`), 어느 프로젝트가 무엇을 근거로
        만들어졌는지(`proj_id`·`doc_role`)도 남는다.

        반대로 `doc_block`·`chunk`·`vec_idx`는 지운다. **`chunk.search_text`에 원문이
        통째로 들어 있기 때문이다** — 요약이나 임베딩만이 아니라 문서 본문 그대로다.
        사용자가 Drive 에서 파일을 지운 것은 없애려는 의도인데, 우리 DB 에 본문이
        남아 있으면 그 의도를 우회하는 셈이 된다.

        되살릴 때 다시 파싱해야 한다. 그 비용(RunPod 100초 남짓)보다 남은 본문이
        계속 남아 있는 쪽이 나쁘다.
        """

        if not doc_ids:
            return {"removed": 0, "blocks": 0, "chunks": 0, "vectors": 0}

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team(cursor, account_id)
                # 남의 팀 문서를 지우지 않도록 대상을 먼저 좁힌다.
                cursor.execute(
                    """
                    SELECT doc_id FROM doc
                    WHERE doc_id = ANY(%s) AND team_id = %s AND deleted = false
                    """,
                    (doc_ids, team_id),
                )
                targets = [row["doc_id"] for row in cursor.fetchall()]
                if not targets:
                    return {"removed": 0, "blocks": 0, "chunks": 0, "vectors": 0}

                # vec_idx → chunk → doc_block 순. FK 는 없지만 참조하는 쪽부터
                # 지워야 중간에 실패했을 때 고아가 남지 않는다.
                cursor.execute(
                    """
                    DELETE FROM vec_idx WHERE chunk_id IN (
                        SELECT c.chunk_id FROM chunk AS c
                        JOIN doc_block AS b ON b.block_id = c.block_id
                        WHERE b.doc_id = ANY(%s)
                    )
                    """,
                    (targets,),
                )
                vectors = cursor.rowcount
                cursor.execute(
                    """
                    DELETE FROM chunk WHERE block_id IN (
                        SELECT block_id FROM doc_block WHERE doc_id = ANY(%s)
                    )
                    """,
                    (targets,),
                )
                chunks = cursor.rowcount
                cursor.execute("DELETE FROM doc_block WHERE doc_id = ANY(%s)", (targets,))
                blocks = cursor.rowcount

                cursor.execute(
                    "UPDATE doc SET deleted = true WHERE doc_id = ANY(%s)", (targets,)
                )
                return {
                    "removed": cursor.rowcount,
                    "blocks": blocks,
                    "chunks": chunks,
                    "vectors": vectors,
                }

    @staticmethod
    def restore_reappeared(*, account_id: str, live_file_ids: set[str]) -> list[str]:
        """내려 뒀는데 Drive 에 다시 나타난 문서를 되살린다.

        Drive 파일 id 는 옮겨도 유지된다. 폴더 밖으로 뺐다가 되돌리면 같은 id 로
        다시 잡히는데, `registered_file_ids()`가 삭제된 문서까지 「이미 아는 파일」로
        치기 때문에 신규 목록에도 안 올라온다. 되살리지 않으면 **영원히 묻힌다.**

        되살아난 문서는 「처리 필요」 상태다 — 내릴 때 파싱 산출물을 지웠으므로
        기준 문서로 쓰려면 다시 처리해야 한다.
        """

        if not live_file_ids:
            return []

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _team_of(cursor, account_id)
                if team_id is None:
                    return []
                cursor.execute(
                    """
                    UPDATE doc SET deleted = false
                    WHERE team_id = %s AND source_type = %s
                      AND deleted = true AND src_file_id = ANY(%s)
                    RETURNING doc_id
                    """,
                    (team_id, DocumentRepository.DRIVE, sorted(live_file_ids)),
                )
                return [row["doc_id"] for row in cursor.fetchall()]

    @staticmethod
    def add_drive_documents(
        *,
        account_id: str,
        documents: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """고른 파일만 `doc`에 **더한다.**

        폴더 전체를 훑지 않고 고른 것만 더한다는 점이 이 메서드가 따로
        있는 이유다 — **아무것도 지우지 않는다.** 저쪽은 폴더 전체를 동기화하며
        목록에 없는 문서를 `deleted = true`로 내리는데, "새 파일 3개를 추가로
        등록한다"에 그 동작을 쓰면 나머지 문서가 통째로 내려간다.

        이미 있는 `src_file_id`는 건너뛴다(스캔과 등록 사이에 누가 먼저 넣었을
        수 있다). 새로 만든 행만 돌려준다.
        """

        if not documents:
            return []

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team(cursor, account_id)

                created = []
                for document in documents:
                    cursor.execute(
                        "SELECT 1 FROM doc WHERE team_id = %s AND src_file_id = %s",
                        (team_id, document["src_file_id"]),
                    )
                    if cursor.fetchone() is not None:
                        continue

                    doc_id = next_short_code(cursor, table="doc", column="doc_id", prefix="DC")
                    cursor.execute(
                        """
                        INSERT INTO doc
                            (doc_id, team_id, src_file_id, source_type, file_name,
                             mime_type, doc_role, src_modified_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING doc_id, team_id, proj_id, src_file_id, source_type, file_name,
                                  mime_type, doc_role, src_modified_at, storage_key
                        """,
                        (
                            doc_id,
                            team_id,
                            document["src_file_id"],
                            DocumentRepository.DRIVE,
                            document["file_name"],
                            document["mime_type"],
                            document["doc_role"],
                            document["src_modified_at"],
                        ),
                    )
                    created.append(cursor.fetchone())
                return created

    @staticmethod
    def list_history(
        *,
        account_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], bool]:
        """이 팀의 문서 처리 이력 한 페이지와 "더 있는가".

        `audit_log`를 그대로 읽는다 — 등록·다운로드가 언제 몇 건이었는지는
        따로 테이블을 둘 만큼 다른 정보가 아니다.

        `audit_log`에 팀 컬럼이 없어 **행위자의 팀**으로 거른다. 문서 등록은
        프로젝트와 무관해져서 `proj_id`로는 더 이상 찾을 수 없다.

        전체 건수를 세지 않고 **한 행 더 읽어** 더 있는지 판단한다. 화면은 남은
        개수를 쓰지 않고 「더 보기」를 보일지만 정하므로, 매 페이지마다 count(*)로
        전체를 훑을 이유가 없다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _team_of(cursor, account_id)
                if team_id is None:
                    return [], False
                cursor.execute(
                    """
                    SELECT al.audit_id, al.action, al.payload, al.occurred_at,
                           ua.display_name AS actor_display_name
                    FROM audit_log AS al
                    JOIN user_account AS ua ON ua.account_id = al.actor_account_id
                    WHERE ua.team_id = %s AND al.target_type = %s
                    ORDER BY al.occurred_at DESC, al.audit_id DESC
                    LIMIT %s OFFSET %s
                    """,
                    (team_id, DocumentRepository.AUDIT_TARGET, limit + 1, offset),
                )
                rows = list(cursor.fetchall())

        return rows[:limit], len(rows) > limit

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


class ExistTaskRepository:
    """Jira에서 읽어온 기존 업무. 부하 계산의 분자다."""

    JIRA_PROJECT = "JIRA_PROJECT"

    # 부하 계산의 입력. 프로젝트 범위와 팀 범위가 같은 컬럼을 쓴다.
    _TASK_COLUMNS = """
        et.exist_task_id, et.jira_issue_id, et.summary, et.assignee_person_id,
        et.status, et.status_category, et.due_at,
        et.estimate, et.remaining, et.spent,
        ps.proj_id,
        ps.external_source_id AS project_key,
        -- 화면이 키 대신 쓸 이름. 예전에 저장한 소스는 NULL이라
        -- 그때는 호출자가 키로 대체한다.
        COALESCE(NULLIF(ps.display_name, ''), p.name) AS project_name
    """

    @staticmethod
    def list_jira_sources(*, proj_id: str, account_id: str) -> list[dict[str, Any]]:
        """이 프로젝트가 대응하는 Jira 프로젝트. 1:1이라 0개 아니면 1개다."""

        with database_connection() as connection:
            with connection.cursor() as cursor:
                _require_team_project(cursor, proj_id=proj_id, account_id=account_id)
                cursor.execute(
                    """
                    SELECT proj_source_id, external_source_id, display_name
                    FROM proj_source
                    WHERE proj_id = %s AND source_type = %s
                    """,
                    (proj_id, ExistTaskRepository.JIRA_PROJECT),
                )
                return list(cursor.fetchall())

    @staticmethod
    def list_jira_sources_for_team(account_id: str) -> list[dict[str, Any]]:
        """팀의 모든 Jira 소스. 「갱신」이 한 번에 다시 읽을 때 쓴다."""

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _team_of(cursor, account_id)
                if team_id is None:
                    return []
                cursor.execute(
                    """
                    SELECT ps.proj_source_id, ps.proj_id, ps.external_source_id, ps.display_name
                    FROM proj_source AS ps
                    JOIN proj AS p ON p.proj_id = ps.proj_id
                    WHERE p.team_id = %s AND ps.source_type = %s
                    ORDER BY ps.proj_source_id
                    """,
                    (team_id, ExistTaskRepository.JIRA_PROJECT),
                )
                return list(cursor.fetchall())

    @staticmethod
    def list_for_project(*, proj_id: str, account_id: str) -> list[dict[str, Any]]:
        """이 프로젝트가 읽어온 업무 전부."""

        with database_connection() as connection:
            with connection.cursor() as cursor:
                _require_team_project(cursor, proj_id=proj_id, account_id=account_id)
                cursor.execute(
                    f"""
                    SELECT {ExistTaskRepository._TASK_COLUMNS}
                    FROM exist_task AS et
                    JOIN proj_source AS ps ON ps.proj_source_id = et.proj_source_id
                    JOIN proj AS p ON p.proj_id = ps.proj_id
                    WHERE ps.proj_id = %s AND ps.source_type = %s
                    ORDER BY ps.external_source_id, et.jira_issue_id
                    """,
                    (proj_id, ExistTaskRepository.JIRA_PROJECT),
                )
                return list(cursor.fetchall())

    @staticmethod
    def list_for_team(account_id: str) -> list[dict[str, Any]]:
        """팀의 모든 프로젝트에서 읽어온 업무. **부하 계산의 입력이다.**

        사람의 부하는 그 사람이 맡은 모든 프로젝트의 합이다. 프로젝트 하나만 보면
        "SKN29만 90%"가 나오는데 실제로는 다른 프로젝트까지 합쳐 122.5%다 —
        한쪽만 보고 여유가 있다고 판단하면 배정이 틀린다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _team_of(cursor, account_id)
                if team_id is None:
                    return []
                cursor.execute(
                    f"""
                    SELECT {ExistTaskRepository._TASK_COLUMNS}
                    FROM exist_task AS et
                    JOIN proj_source AS ps ON ps.proj_source_id = et.proj_source_id
                    JOIN proj AS p ON p.proj_id = ps.proj_id
                    WHERE p.team_id = %s AND ps.source_type = %s
                    ORDER BY ps.external_source_id, et.jira_issue_id
                    """,
                    (team_id, ExistTaskRepository.JIRA_PROJECT),
                )
                return list(cursor.fetchall())

    @staticmethod
    def progress_by_project(proj_ids: list[str]) -> dict[str, dict[str, Any]]:
        """프로젝트별 공수 기준 진행률. 목록 화면이 한 번에 받아 간다.

        ```
        진행률 = (완료 공수 + 미완료 소진 공수) ÷ 전체 공수
        소진   = estimate − remaining
        ```

        **건수가 아니라 공수 기준이다.** 건수로 세면 20시간짜리와 2시간짜리가
        같아서, 큰 작업이 끝나도 진행률이 거의 안 움직인다.

        `estimate`가 없는 이슈는 분모에서 빠진다 — 크기를 모르는 일을 0으로 치면
        진행률이 부풀고, 전체로 치면 줄어든다. 어느 쪽도 사실이 아니라서 세어서
        따로 알린다(`missing_estimate`).

        프로젝트를 여러 개 받아 한 번에 집계한다. 목록에서 프로젝트마다 부르면
        N+1이 된다.
        """

        if not proj_ids:
            return {}

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        ps.proj_id,
                        count(*) AS task_count,
                        count(*) FILTER (WHERE et.status_category = 'DONE') AS done_count,
                        count(*) FILTER (WHERE et.estimate IS NULL) AS missing_estimate,
                        COALESCE(sum(et.estimate), 0) AS total_hours,
                        COALESCE(sum(et.estimate)
                                 FILTER (WHERE et.status_category = 'DONE'), 0) AS done_hours,
                        -- 미완료분에서 이미 쓴 만큼. remaining 이 없으면 아직 손대지
                        -- 않은 것으로 본다(과대평가하지 않는 쪽).
                        COALESCE(sum(GREATEST(et.estimate - COALESCE(et.remaining, et.estimate), 0))
                                 FILTER (WHERE et.status_category IS DISTINCT FROM 'DONE'), 0)
                            AS burned_hours
                    FROM exist_task AS et
                    JOIN proj_source AS ps ON ps.proj_source_id = et.proj_source_id
                    WHERE ps.proj_id = ANY(%s) AND ps.source_type = %s
                    GROUP BY ps.proj_id
                    """,
                    (sorted(set(proj_ids)), ExistTaskRepository.JIRA_PROJECT),
                )

                result: dict[str, dict[str, Any]] = {}
                for row in cursor.fetchall():
                    total = float(row["total_hours"])
                    completed = float(row["done_hours"]) + float(row["burned_hours"])
                    result[row["proj_id"]] = {
                        "task_count": row["task_count"],
                        "done_count": row["done_count"],
                        "missing_estimate": row["missing_estimate"],
                        "total_hours": round(total, 2),
                        "completed_hours": round(completed, 2),
                        # 추정치가 하나도 없으면 진행률을 만들지 않는다.
                        "progress": round(completed / total * 100, 1) if total > 0 else None,
                    }
                return result

    @staticmethod
    def replace_for_source(*, proj_source_id: str, rows: list[dict[str, Any]]) -> int:
        """한 소스의 업무를 넘겨받은 목록으로 통째로 교체한다.

        `ProjectSourceRepository.replace()`와 같은 delete-then-insert다. 소스 하나가
        재동기화의 단위인 이유는 프로젝트가 Jira 프로젝트를 여러 개 읽을 수 있어서다
        — `proj_id`로 지우면 남의 소스까지 날아간다.

        완료된 이슈도 함께 들어온다(진행률이 완료분을 필요로 한다). Jira에서 삭제된
        이슈만 delete 단계에서 사라진다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM exist_task WHERE proj_source_id = %s",
                    (proj_source_id,),
                )

                inserted = 0
                # 같은 이슈가 응답에 두 번 와도 한 행만 남긴다. UNIQUE가 마지막
                # 방어선이지만 여기서 걸러야 에러 대신 정상 처리가 된다.
                seen: set[str] = set()
                for row in rows:
                    jira_issue_id = row["jira_issue_id"]
                    if jira_issue_id in seen:
                        continue
                    seen.add(jira_issue_id)

                    exist_task_id = next_short_code(
                        cursor,
                        table="exist_task",
                        column="exist_task_id",
                        prefix="ET",
                    )
                    cursor.execute(
                        """
                        INSERT INTO exist_task
                            (exist_task_id, proj_source_id, assignee_person_id, jira_issue_id,
                             summary, status, status_category, priority, start_at, due_at,
                             estimate, remaining, spent)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            exist_task_id,
                            proj_source_id,
                            row.get("assignee_person_id"),
                            jira_issue_id,
                            row.get("summary"),
                            row.get("status"),
                            row.get("status_category"),
                            row.get("priority"),
                            row.get("start_at"),
                            row.get("due_at"),
                            row.get("estimate"),
                            row.get("remaining"),
                            row.get("spent"),
                        ),
                    )
                    inserted += 1

                # 교체와 같은 트랜잭션에서 찍는다. 따로 두면 적재는 됐는데 시각은
                # 옛날인(또는 그 반대인) 조합이 생기고, 화면이 어느 쪽을 믿어야
                # 할지 알 수 없게 된다.
                cursor.execute(
                    "UPDATE proj_source SET last_sync_at = now() WHERE proj_source_id = %s",
                    (proj_source_id,),
                )
                return inserted


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
    def avatar_key(account_id: str) -> str | None:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT avatar_key FROM user_account WHERE account_id = %s",
                    (account_id,),
                )
                row = cursor.fetchone()
        if row is None:
            raise RecordNotFound(f"존재하지 않는 계정입니다: {account_id}")
        return row["avatar_key"]

    @staticmethod
    def set_avatar_key(*, account_id: str, avatar_key: str | None) -> None:
        """프로필 사진 키를 저장한다. `None`이면 지운 것이다.

        파일을 먼저 쓰고 이 기록을 나중에 한다. 순서가 반대면 "DB에는 있다는데
        파일이 없는" 상태가 생겨 화면이 깨진 이미지를 그린다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE user_account SET avatar_key = %s
                     WHERE account_id = %s
                    RETURNING account_id
                    """,
                    (avatar_key, account_id),
                )
                if cursor.fetchone() is None:
                    raise RecordNotFound(f"존재하지 않는 계정입니다: {account_id}")

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
    def email(account_id: str) -> str | None:
        """이 계정의 이메일. 계정이 없으면 None.

        Jira 담당자 기본값(요청자 자신) 조회에 쓴다(2026-08-20,
        `find_jira_account_id_by_email` 호출부) — `get_profile()` 은 HR 연계
        인물 조회까지 같이 하는 무거운 조회라 이메일 하나 때문에 부르기엔
        과하다. `team_id()` 와 같은 최소 조회 패턴이다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT email FROM user_account WHERE account_id = %s",
                    (account_id,),
                )
                row = cursor.fetchone()
        return row["email"] if row else None

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
            SELECT account_id, email, display_name, account_status, team_id, avatar_key
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

    # 팀장이 정하지 않았을 때 쓰는 값. 화면과 계산이 같은 상수를 봐야 "설정 안 함"
    # 상태에서 둘이 다른 숫자를 말하지 않는다.
    DEFAULT_OVERLOAD_PCT = 100
    DEFAULT_WORKLOAD_WEEKS = 4

    @staticmethod
    def settings(account_id: str) -> dict[str, Any]:
        """팀 업무량 기준. 정한 값과 실제로 쓰이는 값을 함께 준다.

        `capacity_wk_hours`가 `None`이면 HR의 사람별 주 근무시간을 그대로 쓴다.
        그때 화면이 "지금 기준이 몇 시간인지"를 보여줄 수 있도록 팀원들의 HR 값을
        같이 계산해 준다 — 사람마다 다르면 범위로 알린다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _team_of(cursor, account_id)
                if team_id is None:
                    raise RecordNotFound("아직 팀이 없습니다.")
                cursor.execute(
                    """
                    SELECT capacity_wk_hours, overload_pct, workload_weeks
                    FROM team WHERE team_id = %s
                    """,
                    (team_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    raise RecordNotFound("팀을 찾을 수 없습니다.")
                person_ids = TeamRepository.member_person_ids(team_id)

        # HR이 아는 주 근무시간. wk_hours 가 없으면 계약시간×FTE 로 유도한다 —
        # 계산기(`_weekly_hours`)와 같은 규칙이라야 화면과 계산이 어긋나지 않는다.
        hr_hours = sorted(
            {
                hours
                for hours in (_hr_weekly_hours(p) for p in hr.list_persons(person_ids=person_ids))
                if hours is not None
            }
        )

        return {
            "capacity_wk_hours": float(row["capacity_wk_hours"]) if row["capacity_wk_hours"] is not None else None,
            "overload_pct": row["overload_pct"],
            "workload_weeks": row["workload_weeks"],
            # 설정을 비웠을 때 실제로 쓰이는 값. 화면이 회색 글씨로 보여준다.
            "hr_wk_hours_min": hr_hours[0] if hr_hours else None,
            "hr_wk_hours_max": hr_hours[-1] if hr_hours else None,
            "default_overload_pct": TeamRepository.DEFAULT_OVERLOAD_PCT,
            "default_workload_weeks": TeamRepository.DEFAULT_WORKLOAD_WEEKS,
        }

    @staticmethod
    def leader_account_id(team_id: str) -> str | None:
        """이 팀을 만든 팀장의 account_id.

        Jira·Drive 자격증명(`connector_conn`)은 **연결한 사람의 계정에만** 있고,
        연결은 팀장만 할 수 있다(`apps/connectors/api_views.py`의 `leader` 검사,
        설정 화면 안내 "팀장만 외부 서비스를 연결할 수 있습니다. 팀원은 팀장이
        연결한 데이터를 그대로 사용합니다") — 그래서 팀원이 실행한 동작(프로젝트
        갱신, Jira 챗 도구)도 **이 계정의** 자격증명을 써야 한다. 실행한 사람의
        `account_id`를 그대로 자격증명 조회에 넘기면, 팀원 자신은 연결한 적이
        없으므로 `연결되지 않은 서비스입니다`로 막힌다(2026-08-19 실측·수정).

        팀장은 `team.owner_account_id`다 — `team`을 만든 계정이 곧 팀장이라는
        전제(가입 경로로 역할이 갈리는 `account_role()`과 같은 전제, MVP는
        팀당 팀장 한 명).
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT owner_account_id FROM team WHERE team_id = %s", (team_id,))
                row = cursor.fetchone()
                return row["owner_account_id"] if row else None

    @staticmethod
    def update_settings(
        *,
        account_id: str,
        capacity_wk_hours: float | None,
        overload_pct: int | None,
        workload_weeks: int | None,
    ) -> dict[str, Any]:
        """업무량 기준을 저장한다. `None`은 "설정 안 함"으로 되돌리는 것이다."""

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team(cursor, account_id)
                cursor.execute(
                    """
                    UPDATE team
                       SET capacity_wk_hours = %s,
                           overload_pct = %s,
                           workload_weeks = %s
                     WHERE team_id = %s
                    RETURNING team_id
                    """,
                    (capacity_wk_hours, overload_pct, workload_weeks, team_id),
                )
                if cursor.fetchone() is None:
                    raise RecordNotFound("팀을 찾을 수 없습니다.")

        return TeamRepository.settings(account_id)

    # ------------------------------------------------------------------
    # 팀 기본 채팅 모델(2026-08-22)
    #
    # 원래 레거시 정문 에이전트(`agent_tool.tool_ref='agent:*'`)의 `agent.model`
    # 에 얹혀 있던 값이다. 레거시 `agent`/`agent_tool` 폐기와 함께 팀 설정
    # 본래 자리로 옮겼다 — 근거는 DB/migrations/2026-08-22_team_default_model.sql
    # 헤더. 두 메서드 다 **`team_id`를 직접 받는다**: 운영자 콘솔이 쓰는데
    # 운영자에게는 자기 팀이 없어 `_require_team()`이 통하지 않는다(커스텀 모델
    # 등록과 같은 모양이다).
    # ------------------------------------------------------------------

    @staticmethod
    def default_model(team_id: str) -> str | None:
        """그 팀의 기본 채팅 모델. `None`이면 **설정 안 함**이다.

        `None`을 코드 기본값으로 바꿔 돌려주지 않는다 — 화면이 「아직 없다」와
        「이 값으로 저장돼 있다」를 구분해 말해야 하기 때문이다. 저장한 적 없는
        값을 저장된 것처럼 보이는 것이 원래 Model 탭의 문제였다.

        팀 자체가 없으면 `RecordNotFound` — "값이 없다"와 "팀이 없다"는 화면이
        다르게 말해야 한다(전자는 안내, 후자는 404).
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT default_model FROM team WHERE team_id = %s", (team_id,)
                )
                row = cursor.fetchone()
                if row is None:
                    raise RecordNotFound(f"존재하지 않는 팀입니다: {team_id}")
                return row["default_model"]

    @staticmethod
    def set_default_model(*, team_id: str, model: str) -> str | None:
        """운영자가 그 팀의 기본 채팅 모델을 정한다(2026-08-18 멘토링).

        **전역 하나로 두지 않는다.** 계약·리전 요건이 다른 회사를 못 받기
        때문이다 — 커스텀 모델을 팀 단위로 붙인 것과 같은 이유다.

        빈 문자열은 `None`으로 저장한다 — 화면의 「고르세요」로 되돌리는 길이
        있어야 잘못 고른 팀을 원래대로 돌려놓을 수 있다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE team SET default_model = %s
                     WHERE team_id = %s
                    RETURNING default_model
                    """,
                    (model or None, team_id),
                )
                row = cursor.fetchone()
                if row is None:
                    raise RecordNotFound(f"존재하지 않는 팀입니다: {team_id}")
                return row["default_model"]

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
    def list_members(account_id: str) -> list[dict[str, Any]]:
        """팀 명부 한 줄에 사람·계정·초대를 함께 담아 준다.

        지금까지 「팀원 관리」가 보낸 초대만 보여 줘서, 직접 가입한 팀장은 목록에
        아예 없고(초대 기록이 없다) 이미 팀원인 사람이 「초대됨」으로만 읽혔다.
        업무 배정 대상은 `team_member`지 초대가 아니다.

        `team_member`는 **사람 단위**다 — 계정이 없어도 팀원이다. 그래서 계정과
        초대는 있으면 붙이고 없으면 비운다.

        초대는 사람마다 **가장 최근 것 하나**만 본다. 취소하고 다시 보낸 이력이
        쌓이는데, 명부에서 알고 싶은 것은 "지금 어떤 상태인가"뿐이다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _team_of(cursor, account_id)
                if team_id is None:
                    return []

                cursor.execute(
                    """
                    SELECT tm.team_member_id, tm.person_id, tm.added_at,
                           ua.account_id, ua.email AS account_email, ua.account_status,
                           t.owner_account_id,
                           mi.invite_id, mi.status AS invite_status, mi.created_at AS invited_at
                    FROM team_member AS tm
                    JOIN team AS t ON t.team_id = tm.team_id
                    LEFT JOIN user_person_link AS upl
                           ON upl.person_id = tm.person_id AND upl.mapping_status = 'VERIFIED'
                    LEFT JOIN user_account AS ua
                           ON ua.account_id = upl.account_id AND ua.team_id = tm.team_id
                    LEFT JOIN LATERAL (
                        SELECT invite_id, status, created_at
                        FROM member_invite
                        WHERE person_id = tm.person_id AND team_id = tm.team_id
                        ORDER BY created_at DESC
                        LIMIT 1
                    ) AS mi ON true
                    WHERE tm.team_id = %s
                    ORDER BY tm.team_member_id
                    """,
                    (team_id,),
                )
                rows = list(cursor.fetchall())

        # 이름·직책은 HR에 있다. 사람마다 부르지 않고 한 번에 모아 붙인다.
        persons = hr.lookup_persons([row["person_id"] for row in rows])
        for row in rows:
            person = persons.get(row["person_id"]) or {}
            row["name"] = person.get("name")
            row["org_name"] = person.get("org_name")
            row["job_role"] = person.get("job_role")
            row["level_rank"] = person.get("level_rank")
            # 팀을 만든 사람은 뺄 수 없다. 화면이 버튼을 감추는 근거다.
            row["is_owner"] = bool(row["account_id"]) and row["account_id"] == row["owner_account_id"]

        # 팀을 만든 사람이 먼저, 그 다음 직급이 높은 순이다. 명부에 들어온 순서
        # (team_member_id)로 두면 나중에 추가한 팀장이 맨 아래에 붙는다.
        #
        # job_role 은 문자열이라 정렬 기준이 못 된다 — level.rank_ord 를 쓴다.
        # 직급을 모르는 사람은 맨 뒤로 보낸다(0으로 치면 사원보다 위로 올라간다).
        rows.sort(
            key=lambda row: (
                0 if row["is_owner"] else 1,
                -(row["level_rank"] or 0),
                row["name"] or "",
            )
        )
        return rows

    @staticmethod
    def add_member_for(*, account_id: str, person_id: str) -> None:
        """팀 명부에 사람을 더한다.

        초대 가능 범위와 같은 기준을 쓴다 — 본인 소속 조직과 그 하위. 팀을 만들 때
        적용한 규칙이 나중에 더할 때만 느슨해질 이유가 없다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team(cursor, account_id)

                owner_person_id = _linked_person_id(cursor, account_id)
                owner = hr.get_person(owner_person_id) if owner_person_id else None
                if owner is None:
                    raise PermissionDenied("HR 시스템에서 본인 확인을 먼저 마쳐야 합니다.")

                person = hr.get_person(person_id)
                if person is None:
                    raise RecordNotFound(f"HR에서 찾을 수 없는 직원입니다: {person_id}")
                if person["org_id"] not in set(hr.subtree_org_ids(owner["org_id"])):
                    raise PermissionDenied(
                        "본인이 속한 조직과 그 하위 조직의 직원만 팀에 담을 수 있습니다."
                    )

                TeamRepository.add_member(cursor, team_id=team_id, person_id=person_id)

    @staticmethod
    def remove_member(*, account_id: str, person_id: str) -> None:
        """팀 명부에서 뺀다. 업무 배정 대상에서 빠진다는 뜻이다.

        **계정이 있는 사람은 뺄 수 없다.** 명부에서만 지우면 그 사람의 계정은
        여전히 이 팀의 데이터를 볼 수 있어, 빠진 것처럼 보이는데 실제로는 접근이
        남는다. 계정 정리가 먼저다.

        팀을 만든 사람도 뺄 수 없다 — 팀 소유자가 배정 대상에서 사라진다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team(cursor, account_id)

                cursor.execute(
                    "SELECT owner_account_id FROM team WHERE team_id = %s",
                    (team_id,),
                )
                team = cursor.fetchone()
                if team is None:
                    raise RecordNotFound("팀을 찾을 수 없습니다.")

                cursor.execute(
                    """
                    SELECT ua.account_id
                    FROM user_person_link AS upl
                    JOIN user_account AS ua ON ua.account_id = upl.account_id
                    WHERE upl.person_id = %s AND upl.mapping_status = 'VERIFIED'
                      AND ua.team_id = %s
                    LIMIT 1
                    """,
                    (person_id, team_id),
                )
                linked = cursor.fetchone()
                if linked is not None:
                    if linked["account_id"] == team["owner_account_id"]:
                        raise PermissionDenied("팀을 만든 사람은 명부에서 뺄 수 없습니다.")
                    raise PermissionDenied(
                        "이 직원은 팀 계정을 쓰고 있어 명부에서 뺄 수 없습니다. "
                        "계정을 먼저 정리해 주세요."
                    )

                cursor.execute(
                    "DELETE FROM team_member WHERE team_id = %s AND person_id = %s RETURNING team_member_id",
                    (team_id, person_id),
                )
                if cursor.fetchone() is None:
                    raise RecordNotFound("이 팀의 팀원이 아닙니다.")

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

                # 지연 import — agent_platform이 이 모듈의 _require_team을
                # 가져다 써서(순환 참조), 모듈 최상단에서는 못 붙인다.
                # Chat의 기본 상대가 없으면 랜딩 화면(/chat)이 비어 보이므로,
                # 팀 생성과 같은 트랜잭션으로 묶어 반쪽 상태를 막는다
                # (2026-08-15, Chat 재설계).
                from .agent_platform import provision_default_chat_agent

                provision_default_chat_agent(
                    cursor, team_id=team_id, owner_account_id=owner_account_id
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

        # 운영자가 끊은 것은 「연결한 적 없음」이 아니다. 자격증명을 지우므로 아래
        # 조건에 먼저 걸리는데, 그 문구로는 무슨 일이 있었는지 알 수가 없다.
        if row is not None and row["auth_status"] == "REVOKED":
            raise RepositoryError("운영자가 이 연결을 해제했습니다. 설정에서 다시 연결해 주세요.")
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


    @staticmethod
    def candidates(team_id: str) -> list[dict[str, Any]]:
        """이 팀에서 소유자가 될 수 있는 계정. **지금 소유자도 포함해 그대로 준다.**

        화면이 「누구로 넘길까」를 고르는 목록이라, 정지된 계정은 뺀다 — 넘겨 봤자
        그 사람은 로그인하지 못한다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT account_id, email, display_name
                    FROM user_account
                    WHERE team_id = %s AND account_status = 'ACTIVE'
                    ORDER BY email
                    """,
                    (team_id,),
                )
                return list(cursor.fetchall())

    @staticmethod
    def transfer_owner(
        *, team_id: str, new_owner_account_id: str, actor_account_id: str, reason: str = ""
    ) -> dict[str, Any]:
        """팀 소유자를 넘긴다.

        **팀장이 나가면 그 팀을 아무도 손댈 수 없었다.** `owner_account_id` 를 바꾸는
        경로가 어디에도 없어서, 퇴사·계정 정지가 곧 그 팀의 막다른 길이었다
        (2026-08-13 PM 지적).

        **그 팀에 등록된 모델도 함께 옮긴다.** `connector_conn` 에는 팀 칸이 없어
        모델을 팀장 계정에 매달아 두는데(`CustomModelRepository.add_for_team`), 옛
        팀장이 팀을 떠나면 `user_account.team_id` 조인이 끊겨 **그 팀 화면에서 모델이
        조용히 사라진다.** 소유자를 넘기는 김에 같은 트랜잭션에서 옮겨 둔다.

        새 소유자는 **그 팀의 살아 있는 계정**이어야 한다. 남의 팀 사람에게 넘기면
        테넌트 경계가 그 자리에서 무너진다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT team_id, name, owner_account_id FROM team WHERE team_id = %s FOR UPDATE",
                    (team_id,),
                )
                team = cursor.fetchone()
                if team is None:
                    raise RecordNotFound(f"존재하지 않는 팀입니다: {team_id}")
                if team["owner_account_id"] == new_owner_account_id:
                    raise RepositoryError("이미 이 계정이 소유자입니다.")

                cursor.execute(
                    "SELECT account_id, team_id, account_status FROM user_account WHERE account_id = %s",
                    (new_owner_account_id,),
                )
                account = cursor.fetchone()
                if account is None:
                    raise RecordNotFound(f"존재하지 않는 계정입니다: {new_owner_account_id}")
                if account["team_id"] != team_id:
                    raise PermissionDenied("이 팀에 속한 계정에게만 넘길 수 있습니다.")
                if account["account_status"] != "ACTIVE":
                    raise RepositoryError("정지된 계정에는 넘길 수 없습니다.")

                cursor.execute(
                    "UPDATE team SET owner_account_id = %s WHERE team_id = %s",
                    (new_owner_account_id, team_id),
                )
                cursor.execute(
                    """
                    UPDATE connector_conn SET account_id = %s
                     WHERE account_id = %s AND connector_type = 'MODEL_API'
                    """,
                    (new_owner_account_id, team["owner_account_id"]),
                )
                moved_models = cursor.rowcount

                log_with(
                    cursor,
                    actor_account_id=actor_account_id,
                    action="OPS_TEAM_OWNER_TRANSFER",
                    target_type="TEAM",
                    target_id=team_id,
                    payload={
                        "before": team["owner_account_id"],
                        "after": new_owner_account_id,
                        "moved_models": moved_models,
                        "reason": reason,
                    },
                )

        return {
            "team_id": team_id,
            "owner_account_id": new_owner_account_id,
            "moved_models": moved_models,
        }


    @staticmethod
    def agents(team_id: str) -> list[dict[str, Any]]:
        """이 팀의 에이전트와 그 구성(`agents`/`agent_versions`/`agent_version_tools`,
        2026-08-22부터 — 레거시 `agent`/`agent_tool` 폐기로 옮겨 왔다).

        **「에이전트가 이상해요」에 답하려면 무엇을 들고 있는지 봐야 한다.** 어떤
        도구가 붙어 있고 어떤 모델로 도는지 모르면, 도구를 안 불렀다는 말이 「없어서」
        인지 「있는데 안 골라서」인지 가릴 수 없다(2026-08-13 PM 요청).

        **지시문도 준다.** 팀이 쓴 글이라 우리가 함부로 볼 것 같지만, 답이 근거
        없이 나온다는 문의는 대개 지시문에서 갈린다 — 그걸 못 보면 운영자가 할 수
        있는 말이 없다. 대화 내용과 문서 원문은 여기서도 안 준다.

        **우리가 자동으로 넣은 것(`is_default_chat`)은 뺀다.** 팀 화면
        (`AgentVersionListPage`)이 `!is_default_chat`으로 걸러서 보여주므로,
        그것까지 여기 섞으면 **고객은 존재도 모르는 줄**을 운영자만 보고
        「이 에이전트가 문제인가요」라고 묻게 된다. 레거시 시절엔 이 경계가
        `is_prebuilt`(전체 도구 + 위임하는 정문 「코파일럿」)였는데, 새 스키마의
        기본 챗은 그 자리를 대신하는 다른 메커니즘(`is_default_chat`)이라 걸러야
        할 조건도 옮겨 왔다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT a.agent_id, a.name, a.description, v.system_prompt AS instruction,
                           v.model, v.reasoning_effort, v.max_iterations, a.status,
                           COALESCE(
                               (SELECT array_agg(t.tool_ref ORDER BY t.tool_ref)
                                FROM agent_version_tools AS t
                                WHERE t.agent_version_id = a.current_version_id),
                               ARRAY[]::varchar[]
                           ) AS tool_refs
                    FROM agents AS a
                    LEFT JOIN agent_versions AS v ON v.agent_version_id = a.current_version_id
                    WHERE a.team_id = %s AND a.status <> 'ARCHIVED'
                      AND a.is_default_chat = false
                    ORDER BY a.name
                    """,
                    (team_id,),
                )
                return list(cursor.fetchall())

    @staticmethod
    def runs(team_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """이 팀 에이전트의 최근 실행.

        **여기에는 고객의 내용이 없다.** `agent_run` 은 상태·반복 수·토큰·시간만
        갖고, `tool_call.input_summary` 는 스키마 주석대로 「원본 인자가 아니라
        요약」이라 자격증명도 대화도 남지 않는다. 그래서 이 표는 운영자가 봐도
        되는 것과 보면 안 되는 것의 경계를 이미 지키고 있다.

        실패한 도구를 함께 준다 — 실행이 왜 실패했는지는 그 줄에 있다.

        **에이전트 표와 같은 기준으로 거른다(`agents`/`agent_versions`,
        2026-08-22부터).** 위에서 기본 챗을 빼 놓고 실행만 남기면, 표에 없는
        이름이 실행 줄에 적혀 더 헷갈린다. 새 엔진은 채팅이든 아니든 실행마다
        `agent_run`을 남기므로(레거시는 채팅을 아예 안 남겼다), 기본 챗을 통해
        오간 채팅은 이 필터로 제외되고, 팀이 직접 골라 쓴 에이전트의 채팅
        실행은 정상적으로 잡힌다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT r.run_id::text AS run_id, r.agent_id, a.name AS agent_name,
                           r.status, r.iterations, r.token_in, r.token_out,
                           r.started_at, r.ended_at,
                           (SELECT count(*) FROM tool_call AS tc WHERE tc.run_id = r.run_id)
                               AS tool_calls,
                           COALESCE(
                               (SELECT array_agg(DISTINCT tc.tool_ref || ' (' || COALESCE(tc.error_code, 'FAILED') || ')')
                                FROM tool_call AS tc
                                WHERE tc.run_id = r.run_id AND tc.status = 'FAILED'),
                               ARRAY[]::text[]
                           ) AS failed_tools
                    FROM agent_run AS r
                    JOIN agents AS a ON a.agent_id = r.agent_id
                    WHERE a.team_id = %s AND a.is_default_chat = false
                    ORDER BY r.started_at DESC
                    LIMIT %s
                    """,
                    (team_id, limit),
                )
                return list(cursor.fetchall())


class OpsAccountRepository:
    """운영자 콘솔 `계정 관리`(`GET/POST /api/ops/accounts/...`) 전용.

    "중복 연결" 판정은 `_DUP_ACCOUNTS_CTE`를 공유해서 운영 현황·계정 연결
    현황과 항상 같은 정의를 쓴다. `mapping_status`(UNMAPPED/LINKED/DUPLICATE)
    는 여기서 계산하지 않고 API 응답 계층(`apps/ops/serializers.py`)에서
    `link_count`로부터 계산한다 — Repository는 원자료만 돌려준다.
    """

    @staticmethod
    def list(account_id: str | None = None) -> list[dict[str, Any]]:
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
                        --
                        -- MODEL_API 도 뺀다. 같은 표를 쓸 뿐 **데이터를 가져오는
                        -- 연결이 아니라 모델을 부르는 열쇠**다(2026-08-13). 안 빼면
                        -- 계정 화면의 「연결 서비스」에 모델이 섞여 나온다.
                        SELECT account_id, array_agg(DISTINCT connector_type ORDER BY connector_type) AS services
                        FROM connector_conn
                        WHERE auth_status = 'CONNECTED'
                          AND connector_type NOT IN ('PEOPLE_DB', 'MODEL_API')
                        GROUP BY account_id
                    )
                    SELECT
                        ua.account_id,
                        ua.email,
                        ua.display_name,
                        ua.account_status,
                        ua.is_admin,
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
                    WHERE %(account_id)s::text IS NULL OR ua.account_id = %(account_id)s
                    ORDER BY ua.account_id
                    """,
                    {"account_id": account_id},
                )
                rows = list(cursor.fetchall())

        return _attach_person_display(rows)

    @staticmethod
    def get(account_id: str) -> dict[str, Any]:
        """계정 한 건. 상세 화면이 쓴다.

        목록과 **같은 SQL 을 쓴다.** 상세용 쿼리를 따로 쓰면 중복 연결 판정 같은
        계산이 두 벌이 되고, 언젠가 한쪽만 고쳐져 목록과 상세가 다른 말을 한다.
        """

        rows = OpsAccountRepository.list(account_id=account_id)
        if not rows:
            raise RecordNotFound(f"존재하지 않는 계정입니다: {account_id}")
        return rows[0]

    @staticmethod
    def lock(*, account_id: str, actor_account_id: str, reason: str = "") -> dict[str, Any]:
        return OpsAccountRepository._set_status(
            account_id=account_id,
            actor_account_id=actor_account_id,
            new_status="LOCKED",
            action="ACCOUNT_LOCK",
            reason=reason,
        )

    @staticmethod
    def unlock(*, account_id: str, actor_account_id: str, reason: str = "") -> dict[str, Any]:
        return OpsAccountRepository._set_status(
            account_id=account_id,
            actor_account_id=actor_account_id,
            new_status="ACTIVE",
            action="ACCOUNT_UNLOCK",
            reason=reason,
        )

    @staticmethod
    def _set_status(
        *, account_id: str, actor_account_id: str, new_status: str, action: str, reason: str = ""
    ) -> dict[str, Any]:
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
                    payload={"before": account["account_status"], "after": new_status, "reason": reason},
                )

        return {"account_id": account_id, "account_status": new_status}

    @staticmethod
    def set_admin(*, account_id: str, actor_account_id: str, is_admin: bool, reason: str = "") -> dict[str, Any]:
        """운영자 권한을 켜고 끈다.

        **원래는 API 에 이 경로를 두지 않았다.** `grant_admin.py` 가 「승격 경로를
        API 표면에 아예 두지 않는다」고 적어 두었고, 그 취지는 운영자 계정 하나가
        털렸을 때 운영자를 더 만들지 못하게 하는 것이었다. 다만 그 대가로 **콘솔이
        자기 자신을 관리하지 못했다** — 운영자를 늘리려면 서버에 들어가 스크립트를
        돌려야 했다(2026-08-13 PM 지적).

        열되 취지는 지킨다.

        - **최초 운영자는 여전히 CLI 로만 만든다.** 운영자가 하나도 없는 상태에서
          이 경로를 부를 수 있는 사람도 없으므로 부트스트랩은 그대로다.
        - **자기 권한은 못 내린다.** 실수로 스스로를 잠그면 되돌릴 방법이 없다.
        - **마지막 운영자는 못 내린다.** 콘솔에 아무도 못 들어가는 상태를 화면에서
          만들 수 있으면 안 된다.
        - 누가 누구에게 왜 줬는지 감사 로그에 남는다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT account_id, account_status, is_admin FROM user_account WHERE account_id = %s FOR UPDATE",
                    (account_id,),
                )
                account = cursor.fetchone()
                if account is None:
                    raise RecordNotFound(f"존재하지 않는 계정입니다: {account_id}")
                if account["account_status"] == "WITHDRAWN":
                    raise RepositoryError("탈퇴한 계정에는 운영자 권한을 줄 수 없습니다.")
                if account["is_admin"] == is_admin:
                    raise RepositoryError("이미 처리된 상태입니다.")

                if not is_admin:
                    if account_id == actor_account_id:
                        raise PermissionDenied(
                            "본인의 운영자 권한은 내릴 수 없습니다. 다른 운영자에게 요청하세요."
                        )
                    # **마지막 한 명을 세는 것이 아니라 「나 말고 또 있는가」를 본다.**
                    # 지금 내리려는 대상 말고 남는 운영자가 없으면 콘솔이 잠긴다.
                    cursor.execute(
                        """
                        SELECT count(*) AS n FROM user_account
                        WHERE is_admin = true AND account_status = 'ACTIVE' AND account_id <> %s
                        """,
                        (account_id,),
                    )
                    if cursor.fetchone()["n"] == 0:
                        raise RepositoryError(
                            "마지막 운영자입니다. 권한을 내리면 콘솔에 아무도 들어갈 수 없습니다."
                        )

                cursor.execute(
                    "UPDATE user_account SET is_admin = %s WHERE account_id = %s", (is_admin, account_id)
                )
                log_with(
                    cursor,
                    actor_account_id=actor_account_id,
                    action="OPS_ADMIN_GRANT" if is_admin else "OPS_ADMIN_REVOKE",
                    target_type="ACCOUNT",
                    target_id=account_id,
                    payload={"before": account["is_admin"], "after": is_admin, "reason": reason},
                )

        return {"account_id": account_id, "is_admin": is_admin}

    @staticmethod
    def unlink_all(*, account_id: str, actor_account_id: str, reason: str = "") -> dict[str, Any]:
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
                    payload={"revoked_person_ids": revoked_person_ids, "reason": reason},
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
    def list(invite_id: str | None = None) -> list[dict[str, Any]]:
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
                    WHERE %(invite_id)s::text IS NULL OR mi.invite_id = %(invite_id)s
                    ORDER BY mi.created_at DESC
                    """,
                    {"invite_id": invite_id},
                )
                rows = list(cursor.fetchall())

        # 조직은 초대가 가리키는 팀(`team_org_id`)이지 사람의 현재 소속이 아니다.
        return _attach_person_display(rows, org_key="org_id")

    @staticmethod
    def get(invite_id: str) -> dict[str, Any]:
        """초대 한 건. 상세 화면이 쓴다.

        목록과 **같은 SQL 을 쓴다** — 만료 판정(`PENDING` 인데 기한이 지났으면
        `EXPIRED`)과 중복 연결 판정이 두 벌이 되면 언젠가 한쪽만 고쳐진다.
        """

        rows = OpsInviteRepository.list(invite_id=invite_id)
        if not rows:
            raise RecordNotFound(f"존재하지 않는 초대입니다: {invite_id}")
        return rows[0]

    @staticmethod
    def discard(*, invite_id: str, actor_account_id: str, reason: str = "") -> dict[str, Any]:
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
                    payload={"person_id": row["person_id"], "reason": reason},
                )

        return {"invite_id": invite_id, "status": "REVOKED"}

    @staticmethod
    def unlink_by_invite(*, invite_id: str, actor_account_id: str, reason: str = "") -> dict[str, Any]:
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

        result = OpsAccountRepository.unlink_all(
            account_id=account_id, actor_account_id=actor_account_id, reason=reason
        )
        return {"invite_id": invite_id, **result}


class OpsConnectorRepository:
    """운영자 콘솔 `연결 서비스 현황`(`GET/POST /api/ops/connectors/...`) 전용.

    People DB는 제외한다 — Drive/Jira처럼 프로젝트가 의존하는 외부 데이터 소스가
    아니라, 가입 계정을 본인 PERSON에 연결하는 본인 확인 절차의 부산물일 뿐이다
    (`역할별_권한_정책.md` 핵심 원칙 1). "연결 서비스"라는 화면 개념과 섞이면
    운영자가 실제 점검해야 할 외부 연동 상태를 파악하기 어려워진다.

    **등록 모델(`MODEL_API`)도 제외한다.** 팀에 등록한 모델은 스키마를 안 바꾸려고
    같은 표를 빌려 쓴 것이지 「연결 서비스」가 아니다. 걸러지지 않아 이 화면에
    `MODEL_API` 행으로 새어 나오고 있었다 — 아래 강제 해제까지 붙으면 운영자가
    모델 화면이 아닌 곳에서 모델을 지우게 된다(2026-08-13 PM).

    대표 직원(`person`)은 `_REPRESENTATIVE_LINK_CTE`를 공유해서 계정 관리와 항상
    같은 규칙(가장 먼저 연결된 것)을 쓴다. `auth_status`에 대응하는 진단·다음 조치
    문구는 저장된 컬럼이 아니라 API 응답 계층(`apps/ops/serializers.py`)에서
    상태값으로부터 만든다 — Repository는 원자료만 돌려준다.
    """

    #: 이 화면이 다루는 것. 나머지 `connector_conn` 행은 다른 화면의 것이다.
    EXTERNAL_TYPES = ("GOOGLE_DRIVE", "JIRA")

    @staticmethod
    def list(conn_id: str | None = None) -> list[dict[str, Any]]:
        """목록과 상세가 **한 SQL을 쓴다.** 따로 쓰면 언젠가 한쪽만 고쳐진다."""

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
                    WHERE cc.connector_type = ANY(%(types)s)
                      AND (%(conn_id)s::text IS NULL OR cc.conn_id = %(conn_id)s)
                    ORDER BY cc.connected_at DESC
                    """,
                    {"types": list(OpsConnectorRepository.EXTERNAL_TYPES), "conn_id": conn_id},
                )
                rows = list(cursor.fetchall())

        return _attach_person_display(rows)

    @staticmethod
    def get(conn_id: str) -> dict[str, Any]:
        rows = OpsConnectorRepository.list(conn_id=conn_id)
        if not rows:
            raise RecordNotFound(f"존재하지 않는 연결입니다: {conn_id}")
        return rows[0]

    @staticmethod
    def revoke(*, conn_id: str, actor_account_id: str, reason: str = "") -> dict[str, Any]:
        """연결을 **끊는다 — 행을 지우지 않는다.**

        토큰이 샜거나 엉뚱한 계정으로 연결된 것을 운영자가 즉시 끊어야 할 때가
        있는데, 여태 그 방법이 제품 어디에도 없었다(고객도 못 끊는다). 그것을
        여는 것이 이 함수다(2026-08-13 PM 요청).

        **지우지 않는 이유는 재연결이 같은 행을 다시 쓰기 때문이다.**
        `ConnectorRepository._upsert` 는 (account_id, connector_type) 로 UPDATE 를
        먼저 시도하므로 `conn_id` 가 유지된다. 반면 행을 지우면 재연결이 새 `conn_id`
        를 받고, 그 conn_id 를 가리키던 `team_folder`·`proj_source` 는 FK 가 없어
        조용히 죽은 값을 든 채 남는다 — 고객이 폴더와 Jira 연결을 전부 다시 고르게
        된다. 목적은 **자격증명을 못 쓰게 하는 것**이지 배선을 끊는 것이 아니다.

        그래서 자격증명만 지우고 상태를 `REVOKED` 로 둔다. 만료(`EXPIRED`)와 굳이
        가르는 이유는, 고객이 「토큰이 만료됐나 보다」와 「운영자가 끊었다」를
        구별할 수 있어야 하기 때문이다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT cc.conn_id, cc.account_id, cc.connector_type, cc.auth_status,
                           ua.email AS owner_email
                    FROM connector_conn AS cc
                    LEFT JOIN user_account AS ua ON ua.account_id = cc.account_id
                    WHERE cc.conn_id = %s
                    FOR UPDATE OF cc
                    """,
                    (conn_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    raise RecordNotFound(f"존재하지 않는 연결입니다: {conn_id}")
                # 화면이 이미 걸러 주지만 규칙은 여기 있어야 규칙이다. People DB 를
                # 끊으면 본인 확인이 풀리고, MODEL_API 는 모델 화면의 것이다.
                if row["connector_type"] not in OpsConnectorRepository.EXTERNAL_TYPES:
                    raise RepositoryError("구글 드라이브·Jira 연결만 해제할 수 있습니다.")
                if row["auth_status"] == "REVOKED":
                    raise RepositoryError("이미 해제된 연결입니다.")

                cursor.execute(
                    """
                    UPDATE connector_conn
                    SET encrypted_credential_ref = NULL, auth_status = 'REVOKED'
                    WHERE conn_id = %s
                    """,
                    (conn_id,),
                )

                # **무엇이 멈추는지 함께 돌려준다.** 끊는 것은 쉽지만 그 팀의 문서
                # 수집이나 Jira 동기화가 같이 선다 — 알고 끊는 것과 모르고 끊는
                # 것은 다르다.
                if row["connector_type"] == "GOOGLE_DRIVE":
                    cursor.execute(
                        "SELECT count(*) AS n FROM team_folder WHERE conn_id = %s", (conn_id,)
                    )
                else:
                    cursor.execute(
                        "SELECT count(*) AS n FROM proj_source WHERE conn_id = %s", (conn_id,)
                    )
                affected = cursor.fetchone()["n"]

                log_with(
                    cursor,
                    actor_account_id=actor_account_id,
                    action="OPS_CONNECTOR_REVOKE",
                    target_type="CONNECTOR",
                    target_id=conn_id,
                    payload={
                        "connector_type": row["connector_type"],
                        "owner_account_id": row["account_id"],
                        "before": row["auth_status"],
                        "affected_sources": affected,
                        "reason": reason,
                    },
                )

        return {
            "conn_id": conn_id,
            "connector_type": row["connector_type"],
            "auth_status": "REVOKED",
            "affected_sources": affected,
        }


class OpsAuditRepository:
    """운영자 콘솔 `감사 로그`(`GET /api/ops/audit/operations/`) 전용. 읽기 전용이다.

    **한 번은 다섯이었다.** 「분석·결정 기록」 4종(`assign_run`/`reco_result`/
    `valid_result`/`decision_rec`)을 함께 읽었는데, 그 테이블에 쓰는 추천
    파이프라인이 이 저장소에 없어 **넷 다 항상 빈 목록**이었다. "나중에
    파이프라인이 쓰기 시작하면 코드 변경 없이 채워진다"고 두었지만 제품이 업무
    배정 추천에서 물러나면서 그 나중이 오지 않는다 — 화면과 함께 걷었다
    (2026-08-13). 되살릴 일이 생기면 git 이력에 있다.

    남은 `list_operations`는 이 콘솔 자체의 조치(계정 정지·초대 폐기·연결 강제
    해제 등)와 일반 사용자의 로그인·가입·커넥터 연결이 실제로 쌓이는 유일한 곳이다.
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


def _notice_snapshot(notice: dict[str, Any]) -> dict[str, Any]:
    """감사 로그 payload에 남길 공지 스냅샷. `schedule_at`은 JSONB 저장을 위해 문자열로 바꾼다."""

    schedule_at = notice["schedule_at"]
    return {
        "title": notice["title"],
        "status": notice["status"],
        "schedule_at": schedule_at.isoformat() if schedule_at else None,
        "schedule_mode": notice["schedule_mode"],
    }


class OpsUsageRepository:
    """운영자 콘솔 `사용 현황`(`GET /api/ops/usage/`) 전용. 읽기 전용이다.

    **왜 새로 만들었나**(2026-08-21). 실행 이력(`agent_run`·`tool_call`)은
    2026-08-13 부터 쌓이고 있었는데 그것을 **집계해서 보여주는 자리가 없었다.**
    팀 상세의 「최근 실행」 표가 유일한 노출인데 그쪽은 한 팀의 최근 몇 건을
    나열할 뿐이고, 「이번 달에 얼마나 썼나」에는 답하지 못했다.

    시중 제품이 관측성을 **요약 → 목록 → 상세** 세 층으로 나눠 보여주는데
    (Copilot Studio Analytics · watsonx Orchestrate Agent analytics, 2026-08-21
    조사) 우리에게는 그 첫 층이 통째로 없었다. 세 번째 층(실행 하나를 따라가는
    트레이스)은 Langfuse 에 맡긴다 — watsonx 도 같은 구성이다. 그래서 이
    저장소는 **첫 층만** 담당한다.

    ## 기간을 30일로 고정한다

    고르게 하지 않는다. 「지금 얼마나 쓰고 있나」 하나에 답하는 화면이고,
    기간 선택기를 붙이면 그 답이 「무엇을 골랐느냐에 따라 다르다」가 된다.
    필요해지면 그때 넓힌다.
    """

    WINDOW_DAYS = 30

    #: 실행 하나가 **어느 팀 것인가**. 2026-08-22까지는 에이전트 명부가 둘이라
    #: (새 `agents`, 옛 `agent`) 양쪽을 다 봐야 했다 — 안 그러면 팀 상세의
    #: 「최근 실행」 표처럼 한쪽만 조인해서 행이 안 잡히는 사고가 났다
    #: (2026-08-21 프로덕션에서 실측: 실행 114건, 표 0건). 레거시 `agent` 폐기로
    #: 이제 `agents` 하나만 보면 된다 — 조인 조각을 상수로 남겨 두는 이유는
    #: 그대로다(쓰는 곳마다 따로 적으면 한쪽만 고쳐질 수 있다).
    _TEAM_OF_RUN = "LEFT JOIN agents AS ag ON ag.agent_id = r.agent_id"
    _TEAM_ID = "ag.team_id"

    @staticmethod
    def _since_clause(column: str) -> str:
        return f"{column} >= now() - interval '{OpsUsageRepository.WINDOW_DAYS} days'"

    @staticmethod
    def summary() -> dict[str, Any]:
        """네 장의 카드 + 세 개의 표. 한 번의 왕복으로 받는다."""

        since_run = OpsUsageRepository._since_clause("r.started_at")
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT count(*) AS runs,
                           count(*) FILTER (WHERE r.status = 'DONE') AS runs_done,
                           count(*) FILTER (WHERE r.status = 'FAILED') AS runs_failed,
                           COALESCE(sum(r.token_in), 0) AS token_in,
                           COALESCE(sum(r.token_out), 0) AS token_out,
                           -- **토큰을 못 잰 실행이 몇 건인가.** 합계만 보이면
                           -- 「적게 썼다」와 「못 쟀다」가 같은 모양이 된다
                           -- (2026-08-21 이전 실행은 전부 NULL 이다).
                           count(*) FILTER (WHERE r.token_in IS NULL) AS runs_without_tokens
                    FROM agent_run AS r
                    WHERE {since_run}
                    """
                )
                runs = dict(cursor.fetchone())

                cursor.execute(
                    f"""
                    SELECT count(*) AS calls,
                           count(*) FILTER (WHERE tc.status = 'OK') AS calls_ok,
                           count(*) FILTER (WHERE tc.status = 'FAILED') AS calls_failed
                    FROM tool_call AS tc
                    JOIN agent_run AS r ON r.run_id = tc.run_id
                    WHERE {since_run}
                    """
                )
                tools = dict(cursor.fetchone())

                cursor.execute(
                    f"""
                    SELECT count(*) AS events,
                           count(*) FILTER (WHERE action = 'BLOCKED') AS blocked
                    FROM guardrail_event
                    WHERE {OpsUsageRepository._since_clause("occurred_at")}
                    """
                )
                guardrail = dict(cursor.fetchone())

                cursor.execute(
                    f"""
                    SELECT {OpsUsageRepository._TEAM_ID} AS team_id,
                           t.name AS team_name,
                           count(*) AS runs,
                           count(*) FILTER (WHERE r.status = 'DONE') AS runs_done,
                           COALESCE(sum(r.token_in), 0) AS token_in,
                           COALESCE(sum(r.token_out), 0) AS token_out
                    FROM agent_run AS r
                    {OpsUsageRepository._TEAM_OF_RUN}
                    LEFT JOIN team AS t ON t.team_id = {OpsUsageRepository._TEAM_ID}
                    WHERE {since_run}
                    GROUP BY 1, 2
                    ORDER BY runs DESC
                    """
                )
                by_team = [dict(row) for row in cursor.fetchall()]

                cursor.execute(
                    f"""
                    SELECT COALESCE(av.model, '(모름)') AS model,
                           r.resolved_provider,
                           count(*) AS runs,
                           COALESCE(sum(r.token_in), 0) AS token_in,
                           COALESCE(sum(r.token_out), 0) AS token_out
                    FROM agent_run AS r
                    LEFT JOIN agent_versions AS av
                           ON av.agent_version_id = r.agent_version_id
                    WHERE {since_run}
                    GROUP BY 1, 2
                    ORDER BY (COALESCE(sum(r.token_in), 0) + COALESCE(sum(r.token_out), 0)) DESC
                    """
                )
                by_model = [dict(row) for row in cursor.fetchall()]

                cursor.execute(
                    f"""
                    SELECT tc.tool_ref,
                           count(*) AS calls,
                           count(*) FILTER (WHERE tc.status = 'OK') AS calls_ok,
                           -- PENDING 은 성공도 실패도 아니다. 스트림이 끊겨
                           -- 영영 안 닫힌 행이라 따로 센다(있으면 배선 문제다).
                           count(*) FILTER (WHERE tc.status = 'PENDING') AS calls_pending,
                           round(avg(tc.duration_ms))::int AS avg_ms
                    FROM tool_call AS tc
                    JOIN agent_run AS r ON r.run_id = tc.run_id
                    WHERE {since_run}
                    GROUP BY 1
                    ORDER BY calls DESC
                    """
                )
                by_tool = [dict(row) for row in cursor.fetchall()]

        return {
            "window_days": OpsUsageRepository.WINDOW_DAYS,
            "runs": runs,
            "tools": tools,
            "guardrail": guardrail,
            "by_team": by_team,
            "by_model": by_model,
            "by_tool": by_tool,
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


class GuardrailEventRepository:
    """가드레일이 실제로 발동한 기록(`guardrail_event`).

    쓰는 쪽은 런타임이고 읽는 쪽은 운영자 콘솔이다. `audit_log`(사람의 조치)와
    나눠 두는 이유는 `DB/schema.sql`의 테이블 주석에 있다.

    **원문은 어디에도 담지 않는다** — `detail`에는 건수·카테고리·점수처럼 임계값을
    조정할 때 필요한 것만 넣는다. 가려진 값이 로그에 남으면 가드레일을 두는 의미가
    없다(`services/agent_runtime/sensitive_text.py`의 `MASK_PLACEHOLDER`와 같은 원칙).
    """

    STAGES = ("INPUT", "OUTPUT", "TOOL_RESULT")
    RULES = ("PII", "MODERATION", "BLOCKED_WORD")
    ACTIONS = ("MASKED", "BLOCKED")

    @staticmethod
    def record(
        *,
        stage: str,
        rule: str,
        action: str,
        detail: dict[str, Any] | None = None,
        run_id: str | None = None,
        session_id: str | None = None,
        account_id: str | None = None,
        team_id: str | None = None,
    ) -> None:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO guardrail_event
                        (run_id, session_id, account_id, team_id, stage, rule, action, detail)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (run_id, session_id, account_id, team_id, stage, rule, action, Jsonb(detail or {})),
                )

    @staticmethod
    def list_recent(*, limit: int = 100) -> list[dict[str, Any]]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        ge.event_id, ge.run_id, ge.session_id, ge.stage, ge.rule,
                        ge.action, ge.detail, ge.occurred_at,
                        ge.account_id, ua.display_name AS account_display_name,
                        ge.team_id, t.name AS team_name
                    FROM guardrail_event AS ge
                    LEFT JOIN user_account AS ua ON ua.account_id = ge.account_id
                    LEFT JOIN team AS t ON t.team_id = ge.team_id
                    ORDER BY ge.occurred_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                return list(cursor.fetchall())


# --- 완전 삭제 (2026-08-19) -------------------------------------------------
#
# **이 저장소에는 외래키 제약이 하나도 없다**(2026-08-19 실측: information_schema
# 기준 0개). 그래서 `DELETE FROM team` 은 막히지도, 딸려 지워지지도 않는다 —
# 그냥 지워지고 나머지가 전부 고아가 된다. 오류가 안 나서 어디가 깨졌는지도
# 안 보인다.
#
# 그래서 지울 것을 **손으로 전부 적는다.** 아래 두 표가 정본이다. 표에 없는
# 테이블은 안 지운다는 뜻이고, 새 테이블이 team_id/account_id 를 갖게 되면
# 여기에 줄을 더해야 한다.
#
# 순서가 곧 정확성이다 — 잎에서 뿌리로 간다. 중간에 실패하면 트랜잭션이 통째로
# 되돌아간다.

#: 팀을 지울 때 함께 지우는 것. (설명, SQL) 순서대로 실행한다.
#:
#: **계정(user_account)은 안 지운다**(PM 결정 2026-08-19) — 팀만 없애고 사람은
#: 무소속으로 남긴다. 그 사람은 다시 로그인해 다른 팀에 들어갈 수 있다.
#: **감사 기록(audit_log)도 안 지운다** — 대상이 사라져도 「누가 무엇을 했는가」가
#: 남는 것이 감사의 뜻이다.
_TEAM_PURGE_STEPS: tuple[tuple[str, str], ...] = (
    ("문서 벡터", "DELETE FROM vec_idx WHERE chunk_id IN (SELECT c.chunk_id FROM chunk c JOIN doc_block b ON b.block_id = c.block_id JOIN doc d ON d.doc_id = b.doc_id WHERE d.team_id = %(team_id)s)"),
    ("문서 근거 연결", "DELETE FROM know_item_src WHERE block_id IN (SELECT b.block_id FROM doc_block b JOIN doc d ON d.doc_id = b.doc_id WHERE d.team_id = %(team_id)s)"),
    ("문서 청크", "DELETE FROM chunk WHERE block_id IN (SELECT b.block_id FROM doc_block b JOIN doc d ON d.doc_id = b.doc_id WHERE d.team_id = %(team_id)s)"),
    ("문서 블록", "DELETE FROM doc_block WHERE doc_id IN (SELECT doc_id FROM doc WHERE team_id = %(team_id)s)"),
    ("문서 메타", "DELETE FROM doc_meta WHERE doc_id IN (SELECT doc_id FROM doc WHERE team_id = %(team_id)s)"),
    ("문서 동기화 기록", "DELETE FROM doc_sync WHERE doc_id IN (SELECT doc_id FROM doc WHERE team_id = %(team_id)s)"),
    ("문서", "DELETE FROM doc WHERE team_id = %(team_id)s"),
    ("등록된 업무", "DELETE FROM task WHERE model_id IN (SELECT m.model_id FROM proj_know_model m JOIN proj p ON p.proj_id = m.proj_id WHERE p.team_id = %(team_id)s)"),
    ("분석 스냅샷", "DELETE FROM ana_snapshot WHERE proj_id IN (SELECT proj_id FROM proj WHERE team_id = %(team_id)s)"),
    ("지식모델 항목", "DELETE FROM model_know_item WHERE model_id IN (SELECT m.model_id FROM proj_know_model m JOIN proj p ON p.proj_id = m.proj_id WHERE p.team_id = %(team_id)s)"),
    ("특성 군집 항목", "DELETE FROM feat_cluster_item WHERE cluster_id IN (SELECT f.cluster_id FROM feat_cluster f JOIN proj_know_model m ON m.model_id = f.model_id JOIN proj p ON p.proj_id = m.proj_id WHERE p.team_id = %(team_id)s)"),
    ("특성 군집", "DELETE FROM feat_cluster WHERE model_id IN (SELECT m.model_id FROM proj_know_model m JOIN proj p ON p.proj_id = m.proj_id WHERE p.team_id = %(team_id)s)"),
    ("지식모델", "DELETE FROM proj_know_model WHERE proj_id IN (SELECT proj_id FROM proj WHERE team_id = %(team_id)s)"),
    ("외부 업무 스냅샷", "DELETE FROM exist_task_snap WHERE exist_task_id IN (SELECT e.exist_task_id FROM exist_task e JOIN proj_source s ON s.proj_source_id = e.proj_source_id JOIN proj p ON p.proj_id = s.proj_id WHERE p.team_id = %(team_id)s)"),
    ("외부 업무", "DELETE FROM exist_task WHERE proj_source_id IN (SELECT s.proj_source_id FROM proj_source s JOIN proj p ON p.proj_id = s.proj_id WHERE p.team_id = %(team_id)s)"),
    ("프로젝트 연결원", "DELETE FROM proj_source WHERE proj_id IN (SELECT proj_id FROM proj WHERE team_id = %(team_id)s)"),
    ("프로젝트 참여자", "DELETE FROM proj_member WHERE proj_id IN (SELECT proj_id FROM proj WHERE team_id = %(team_id)s)"),
    ("프로젝트 지식항목", "DELETE FROM know_item WHERE proj_id IN (SELECT proj_id FROM proj WHERE team_id = %(team_id)s)"),
    ("프로젝트", "DELETE FROM proj WHERE team_id = %(team_id)s"),
    # 대화 — LangGraph 체크포인트까지 지운다. thread_id 가 곧 대화 id 라
    # 안 지우면 승인 대기 상태가 유령으로 남는다(2026-08-18 승인 게이트 참고).
    #
    # ⚠ `session_id::text` 로 캐스트한다. 체크포인트 3종은 **langgraph 가 만든
    # 테이블**이라 `thread_id` 가 `text` 인데 우리 `chat_session.session_id` 는
    # `uuid` 다 — 캐스트 없이 비교하면 `operator does not exist: text = uuid` 로
    # 실패한다(2026-08-19 실측). 화면에는 「데이터베이스 요청을 처리할 수
    # 없습니다」로만 보여서 원인이 안 드러난다.
    # 가드레일 발동 기록은 `audit_log`(안 지움)가 아니라 `tool_call`·`agent_run`과
    # 같은 편이다 — 그 팀의 대화에서 나온 실행 기록이고, 대화가 사라지면 같이
    # 사라지는 게 맞다. `team_id`를 직접 들고 있어 조인이 필요 없다.
    ("가드레일 발동 기록", "DELETE FROM guardrail_event WHERE team_id = %(team_id)s"),
    ("도구 호출 기록", "DELETE FROM tool_call WHERE run_id IN (SELECT r.run_id FROM agent_run r JOIN chat_session s ON s.session_id = r.session_id WHERE s.team_id = %(team_id)s)"),
    ("실행 기록", "DELETE FROM agent_run WHERE session_id IN (SELECT session_id FROM chat_session WHERE team_id = %(team_id)s)"),
    ("대화 메시지", "DELETE FROM chat_message WHERE session_id IN (SELECT session_id FROM chat_session WHERE team_id = %(team_id)s)"),
    ("체크포인트 쓰기", "DELETE FROM checkpoint_writes WHERE thread_id IN (SELECT session_id::text FROM chat_session WHERE team_id = %(team_id)s)"),
    ("체크포인트 값", "DELETE FROM checkpoint_blobs WHERE thread_id IN (SELECT session_id::text FROM chat_session WHERE team_id = %(team_id)s)"),
    ("체크포인트", "DELETE FROM checkpoints WHERE thread_id IN (SELECT session_id::text FROM chat_session WHERE team_id = %(team_id)s)"),
    ("대화", "DELETE FROM chat_session WHERE team_id = %(team_id)s"),
    # 에이전트(agents/agent_versions, 2026-08-22부터 이 스키마 하나뿐 —
    # 레거시 agent/agent_tool은 폐기됐다).
    ("에이전트 하위위임", "DELETE FROM agent_version_subagents WHERE parent_version_id IN (SELECT v.agent_version_id FROM agent_versions v JOIN agents a ON a.agent_id = v.agent_id WHERE a.team_id = %(team_id)s)"),
    ("에이전트 버전 도구", "DELETE FROM agent_version_tools WHERE agent_version_id IN (SELECT v.agent_version_id FROM agent_versions v JOIN agents a ON a.agent_id = v.agent_id WHERE a.team_id = %(team_id)s)"),
    ("에이전트 버전", "DELETE FROM agent_versions WHERE agent_id IN (SELECT agent_id FROM agents WHERE team_id = %(team_id)s)"),
    ("에이전트 즐겨찾기", "DELETE FROM agent_favorites WHERE agent_id IN (SELECT agent_id FROM agents WHERE team_id = %(team_id)s)"),
    ("에이전트", "DELETE FROM agents WHERE team_id = %(team_id)s"),
    ("커스텀 도구", "DELETE FROM mcp_tool WHERE server_id IN (SELECT server_id FROM mcp_server WHERE team_id = %(team_id)s)"),
    ("커스텀 도구 서버", "DELETE FROM mcp_server WHERE team_id = %(team_id)s"),
    ("연결 폴더", "DELETE FROM team_folder WHERE team_id = %(team_id)s"),
    ("팀 구성원(HR)", "DELETE FROM team_member WHERE team_id = %(team_id)s"),
    ("초대 사용 기록", "DELETE FROM user_person_link WHERE invite_id IN (SELECT invite_id FROM member_invite WHERE team_id = %(team_id)s)"),
    ("초대", "DELETE FROM member_invite WHERE team_id = %(team_id)s"),
    ("계정 소속 해제", "UPDATE user_account SET team_id = NULL WHERE team_id = %(team_id)s"),
    ("팀", "DELETE FROM team WHERE team_id = %(team_id)s"),
)

#: 계정을 지울 때 함께 지우는 것.
#:
#: **팀 자산(문서·프로젝트·에이전트)은 안 지운다**(PM 결정) — 팀 것이라
#: `owner_account_id` 만 팀 소유자에게 넘긴다. 사람이 나가도 팀이 일을 잃지 않는다.
#: `connector_conn` 은 **그 사람의 자격증명**이라 반드시 지운다. 그 연결로 지정해
#: 둔 폴더·연결원도 함께 지운다 — 연결이 없으면 그 지정은 죽은 값이고, 남겨 두면
#: 동기화가 조용히 실패한다. 이미 수집된 문서 자체는 남는다.
_ACCOUNT_PURGE_STEPS: tuple[tuple[str, str], ...] = (
    ("에이전트 즐겨찾기", "DELETE FROM agent_favorites WHERE account_id = %(account_id)s"),
    ("가드레일 발동 기록", "DELETE FROM guardrail_event WHERE account_id = %(account_id)s"),
    ("도구 호출 기록", "DELETE FROM tool_call WHERE run_id IN (SELECT r.run_id FROM agent_run r JOIN chat_session s ON s.session_id = r.session_id WHERE s.account_id = %(account_id)s)"),
    ("실행 기록", "DELETE FROM agent_run WHERE session_id IN (SELECT session_id FROM chat_session WHERE account_id = %(account_id)s)"),
    ("대화 메시지", "DELETE FROM chat_message WHERE session_id IN (SELECT session_id FROM chat_session WHERE account_id = %(account_id)s)"),
    ("체크포인트 쓰기", "DELETE FROM checkpoint_writes WHERE thread_id IN (SELECT session_id::text FROM chat_session WHERE account_id = %(account_id)s)"),
    ("체크포인트 값", "DELETE FROM checkpoint_blobs WHERE thread_id IN (SELECT session_id::text FROM chat_session WHERE account_id = %(account_id)s)"),
    ("체크포인트", "DELETE FROM checkpoints WHERE thread_id IN (SELECT session_id::text FROM chat_session WHERE account_id = %(account_id)s)"),
    ("대화", "DELETE FROM chat_session WHERE account_id = %(account_id)s"),
    ("연결 폴더", "DELETE FROM team_folder WHERE conn_id IN (SELECT conn_id FROM connector_conn WHERE account_id = %(account_id)s)"),
    ("프로젝트 연결원", "DELETE FROM proj_source WHERE conn_id IN (SELECT conn_id FROM connector_conn WHERE account_id = %(account_id)s)"),
    ("연결 서비스", "DELETE FROM connector_conn WHERE account_id = %(account_id)s"),
    ("프로젝트 참여", "DELETE FROM proj_member WHERE account_id = %(account_id)s"),
    ("사람 연결", "DELETE FROM user_person_link WHERE account_id = %(account_id)s"),
    ("계정", "DELETE FROM user_account WHERE account_id = %(account_id)s"),
)

#: 지우기 전에 「무엇이 몇 건」인지 보여줄 목록. 이름 입력 확인 화면이 이걸 그린다.
_TEAM_PREVIEW: tuple[tuple[str, str], ...] = (
    ("구성원", "SELECT count(*) AS n FROM user_account WHERE team_id = %(team_id)s"),
    ("프로젝트", "SELECT count(*) AS n FROM proj WHERE team_id = %(team_id)s"),
    ("문서", "SELECT count(*) AS n FROM doc WHERE team_id = %(team_id)s"),
    ("대화", "SELECT count(*) AS n FROM chat_session WHERE team_id = %(team_id)s"),
    ("에이전트", "SELECT count(*) AS n FROM agents WHERE team_id = %(team_id)s"),
    ("등록된 업무", "SELECT count(*) AS n FROM task WHERE model_id IN (SELECT m.model_id FROM proj_know_model m JOIN proj p ON p.proj_id = m.proj_id WHERE p.team_id = %(team_id)s)"),
    ("커스텀 도구 서버", "SELECT count(*) AS n FROM mcp_server WHERE team_id = %(team_id)s"),
)

_ACCOUNT_PREVIEW: tuple[tuple[str, str], ...] = (
    ("대화", "SELECT count(*) AS n FROM chat_session WHERE account_id = %(account_id)s"),
    ("연결 서비스", "SELECT count(*) AS n FROM connector_conn WHERE account_id = %(account_id)s"),
    ("프로젝트 참여", "SELECT count(*) AS n FROM proj_member WHERE account_id = %(account_id)s"),
    ("즐겨찾기", "SELECT count(*) AS n FROM agent_favorites WHERE account_id = %(account_id)s"),
)


def _preview_counts(cursor, steps, params) -> list[dict[str, Any]]:
    """확인 화면에 그릴 「무엇이 몇 건」. 0 건은 빼고 준다 — 지워질 것만 보인다."""

    rows = []
    for label, sql in steps:
        cursor.execute(sql, params)
        count = cursor.fetchone()["n"]
        if count:
            rows.append({"label": label, "count": count})
    return rows


def _run_purge(cursor, steps, params) -> list[dict[str, Any]]:
    """표대로 지우고 **무엇을 몇 건 지웠는지** 돌려준다.

    지운 뒤에 세지 않고 `rowcount` 를 그대로 쓴다 — 지운 다음에 세면 언제나 0 이다.
    """

    done = []
    for label, sql in steps:
        cursor.execute(sql, params)
        if cursor.rowcount:
            done.append({"label": label, "count": cursor.rowcount})
    return done


class OpsPurgeRepository:
    """운영자 콘솔의 **완전 삭제**. 되돌릴 수 없다.

    이름을 그대로 입력해야만 실행된다(`confirm_name`) — 확인 모달 한 번으로는
    실수로 누른 것과 정말 지우려는 것이 구분되지 않는다. 서버에서도 검사한다:
    화면만 막으면 API 를 직접 부르는 경로가 열린 채로 남는다.
    """

    @staticmethod
    def team_preview(*, team_id: str) -> dict[str, Any]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT team_id, name FROM team WHERE team_id = %s", (team_id,))
                team = cursor.fetchone()
                if team is None:
                    raise RecordNotFound(f"존재하지 않는 팀입니다: {team_id}")
                return {
                    "team_id": team["team_id"],
                    "name": team["name"],
                    "items": _preview_counts(cursor, _TEAM_PREVIEW, {"team_id": team_id}),
                }

    @staticmethod
    def purge_team(*, team_id: str, actor_account_id: str, confirm_name: str) -> dict[str, Any]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT team_id, name FROM team WHERE team_id = %s FOR UPDATE", (team_id,)
                )
                team = cursor.fetchone()
                if team is None:
                    raise RecordNotFound(f"존재하지 않는 팀입니다: {team_id}")
                if (confirm_name or "").strip() != team["name"]:
                    raise PermissionDenied("팀 이름이 일치하지 않습니다.")
                # 운영자가 자기가 속한 팀을 지우면 자기 계정이 무소속이 된다.
                # 콘솔에서 자기 발밑을 파는 셈이라 막는다.
                cursor.execute(
                    "SELECT team_id FROM user_account WHERE account_id = %s", (actor_account_id,)
                )
                actor = cursor.fetchone()
                if actor is not None and actor["team_id"] == team_id:
                    raise PermissionDenied("본인이 속한 팀은 삭제할 수 없습니다.")

                # 감사 기록은 지우기 **전에** 남긴다 — 지운 뒤에는 무엇을 지웠는지
                # 세어 볼 대상이 없다.
                removed = _run_purge(cursor, _TEAM_PURGE_STEPS, {"team_id": team_id})
                log_with(
                    cursor,
                    actor_account_id=actor_account_id,
                    action="TEAM_PURGE",
                    target_type="TEAM",
                    target_id=team_id,
                    payload={"name": team["name"], "removed": removed},
                )

        return {"team_id": team_id, "name": team["name"], "removed": removed}

    @staticmethod
    def account_preview(*, account_id: str) -> dict[str, Any]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT account_id, email, display_name FROM user_account WHERE account_id = %s",
                    (account_id,),
                )
                account = cursor.fetchone()
                if account is None:
                    raise RecordNotFound(f"존재하지 않는 계정입니다: {account_id}")
                return {
                    "account_id": account["account_id"],
                    "email": account["email"],
                    "display_name": account["display_name"],
                    "items": _preview_counts(cursor, _ACCOUNT_PREVIEW, {"account_id": account_id}),
                }

    @staticmethod
    def purge_account(
        *, account_id: str, actor_account_id: str, confirm_name: str
    ) -> dict[str, Any]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT account_id, email, display_name, team_id, is_admin
                    FROM user_account WHERE account_id = %s FOR UPDATE
                    """,
                    (account_id,),
                )
                account = cursor.fetchone()
                if account is None:
                    raise RecordNotFound(f"존재하지 않는 계정입니다: {account_id}")
                # 이메일로 확인받는다 — 이름은 겹칠 수 있고, 겹친 이름으로
                # 확인시키면 확인이 확인 구실을 못 한다.
                if (confirm_name or "").strip().lower() != (account["email"] or "").lower():
                    raise PermissionDenied("이메일이 일치하지 않습니다.")
                if account_id == actor_account_id:
                    raise PermissionDenied("본인 계정은 삭제할 수 없습니다.")

                # 팀 소유자는 못 지운다. `team.owner_account_id` 가 NOT NULL 이라
                # 지우면 그 팀이 **주인 없는 채로** 남는다 — 소유자를 먼저 넘겨야
                # 한다. 규칙이 아니라 스키마 제약이다.
                cursor.execute(
                    "SELECT team_id, name FROM team WHERE owner_account_id = %s", (account_id,)
                )
                owned = cursor.fetchall()
                if owned:
                    names = " · ".join(row["name"] for row in owned)
                    raise PermissionDenied(
                        f"이 계정이 소유한 팀이 있습니다({names}). 소유자를 먼저 변경하세요."
                    )

                # 마지막 운영자를 지우면 아무도 콘솔에 못 들어온다.
                if account["is_admin"]:
                    cursor.execute(
                        "SELECT count(*) AS n FROM user_account WHERE is_admin = true AND account_id <> %s",
                        (account_id,),
                    )
                    if cursor.fetchone()["n"] == 0:
                        raise PermissionDenied("마지막 운영자 계정은 삭제할 수 없습니다.")

                # 팀 자산은 지우지 않고 소유자만 팀 소유자에게 넘긴다(PM 결정).
                # 팀이 없는 계정(무소속)이면 넘길 곳이 없어 비운다.
                cursor.execute(
                    "SELECT owner_account_id FROM team WHERE team_id = %s", (account["team_id"],)
                )
                team_owner_row = cursor.fetchone()
                new_owner = team_owner_row["owner_account_id"] if team_owner_row else None
                handed = []
                for label, table in (("문서", "doc"), ("프로젝트", "proj"), ("에이전트", "agents")):
                    cursor.execute(
                        f"UPDATE {table} SET owner_account_id = %s WHERE owner_account_id = %s",
                        (new_owner, account_id),
                    )
                    if cursor.rowcount:
                        handed.append({"label": label, "count": cursor.rowcount})

                removed = _run_purge(cursor, _ACCOUNT_PURGE_STEPS, {"account_id": account_id})
                log_with(
                    cursor,
                    actor_account_id=actor_account_id,
                    action="ACCOUNT_PURGE",
                    target_type="ACCOUNT",
                    target_id=account_id,
                    payload={
                        "email": account["email"],
                        "removed": removed,
                        "handed_over_to": new_owner,
                        "handed_over": handed,
                    },
                )

        return {
            "account_id": account_id,
            "email": account["email"],
            "removed": removed,
            "handed_over": handed,
        }
