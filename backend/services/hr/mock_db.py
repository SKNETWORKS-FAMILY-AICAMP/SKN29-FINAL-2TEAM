"""HR 어댑터의 구현 — 실제 HR 시스템의 대역인 `mock_hr.person`/`mock_hr.org`를 읽는다.

`mock_db`라는 이름은 "언젠가 진짜로 바꿀 임시물"이라는 뜻이 아니다. Workday API를
붙일 수 없어(결제한 기업 고객 전용) 같은 모양의 DB로 **대신하는 것**이고, 그 역할은
계속된다.

HR 관련 SQL은 전부 이 파일 안에만 둔다. 바깥(`repositories.py`, `apps/*`)은
`backend.services.hr`의 함수 이름만 알고 dict를 받는다 — HR을 남의 시스템처럼
다룬다는 설정이 코드에서도 유지되게 하기 위함이다.

HR 테이블은 `mock_hr` 스키마에 있고 **항상 스키마명을 붙여 쓴다.** `search_path`에
넣어 생략할 수도 있지만 그러면 분리한 의미가 없다 — 바깥에서 다시 `JOIN person`이
되기 때문이다. `mock_hr.`를 타이핑해야 닿는다는 사실 자체가 경계다.

**여기에 테넌트 개념은 없다.** HR은 회사의 인사 시스템이고, 우리 플랫폼을 쓰는
단위는 그 안의 팀이다. 팀 경계는 플랫폼 쪽(`team`/`team_member`)이 갖고, 이
계층은 "주어진 조직·사람을 읽어주는" 역할만 한다.
"""

from typing import Any

from backend.db.connection import database_connection

_PERSON_FIELDS = """
    p.person_id,
    p.emp_id,
    p.name,
    p.email,
    p.org_id,
    o.name AS org_name,
    p.job_role,
    p.level_id,
    lv.name AS level_name,
    -- 직급의 정렬 가능한 형태(사원 1 ~ 대표이사 8). job_role 은 문자열이라
    -- 순서가 없어서 명부를 직책 순으로 세울 때 이 값을 쓴다.
    lv.rank_ord AS level_rank,
    p.emp_status
"""

_PERSON_FROM = """
    FROM mock_hr.person AS p
    LEFT JOIN mock_hr.org AS o ON o.org_id = p.org_id
    LEFT JOIN mock_hr.level AS lv ON lv.level_id = p.level_id
"""

_SCHEDULE_JOIN = """
    LEFT JOIN LATERAL (
        SELECT s.tz, s.fte, s.wk_hours, s.def_wk_hours
        FROM mock_hr.sched AS s
        WHERE s.person_id = p.person_id
          AND s.eff_from <= CURRENT_DATE
          AND (s.eff_to IS NULL OR s.eff_to >= CURRENT_DATE)
        ORDER BY s.eff_from DESC
        LIMIT 1
    ) AS sc ON true
"""


def is_available() -> bool:
    """HR 원본에 조직·인력 데이터가 있는가.

    실제 HR이라면 "API에 도달하고 인증이 통하는가"에 해당한다. 목업에서는
    시딩이 안 된 빈 DB를 구분하는 용도다.
    """

    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    EXISTS (SELECT 1 FROM mock_hr.org WHERE status = 'ACTIVE') AS has_org,
                    EXISTS (SELECT 1 FROM mock_hr.person WHERE emp_status = 'ACTIVE') AS has_person
                """
            )
            row = cursor.fetchone()
            return bool(row["has_org"] and row["has_person"])


def subtree_org_ids(root_org_id: str | None) -> list[str]:
    """어떤 조직과 그 하위 조직 전체.

    팀장이 팀을 만들 때 고를 수 있는 사람의 범위(본인 소속 조직의 하위)를
    정하는 데 쓴다. `UNION`(ALL 아님)이 같은 조직을 걸러내므로 `up_org_id`에
    순환 참조가 있는 비정상 데이터에서도 무한 루프에 빠지지 않는다.
    """

    if root_org_id is None:
        return []

    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                WITH RECURSIVE scope AS (
                    SELECT org_id FROM mock_hr.org WHERE org_id = %s AND status = 'ACTIVE'
                    UNION
                    SELECT child.org_id
                    FROM mock_hr.org AS child
                    JOIN scope ON child.up_org_id = scope.org_id
                    WHERE child.status = 'ACTIVE'
                )
                SELECT org_id FROM scope ORDER BY org_id
                """,
                (root_org_id,),
            )
            return [row["org_id"] for row in cursor.fetchall()]


def list_orgs(*, org_ids: list[str] | None = None) -> list[dict[str, Any]]:
    """활성 조직. `org_ids`를 주면 그 안으로 좁힌다.

    `org_ids=[]`는 "아무 조직도 아님"이라 빈 목록을 준다(전체가 아니다).
    """

    if org_ids is not None and not org_ids:
        return []

    where = "WHERE status = 'ACTIVE'"
    params: tuple[Any, ...] = ()
    if org_ids is not None:
        where += " AND org_id = ANY(%s)"
        params = (sorted(set(org_ids)),)

    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT org_id, up_org_id, mgr_id, name, org_type, status
                FROM mock_hr.org
                {where}
                ORDER BY org_id
                """,
                params,
            )
            return list(cursor.fetchall())


def list_persons(
    *,
    org_ids: list[str] | None = None,
    person_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """재직 중인 인력. 조직으로 좁히거나(초대 후보) 사람으로 좁힌다(팀원 조회).

    빈 리스트를 주면 빈 결과다 — 조건을 안 준 것과 구분한다. 이 구분이 없으면
    "팀원이 아직 없는 팀"이 전 직원을 보게 된다.
    """

    if org_ids is not None and not org_ids:
        return []
    if person_ids is not None and not person_ids:
        return []

    conditions = ["p.emp_status = 'ACTIVE'"]
    params: list[Any] = []
    if org_ids is not None:
        conditions.append("p.org_id = ANY(%s)")
        params.append(sorted(set(org_ids)))
    if person_ids is not None:
        conditions.append("p.person_id = ANY(%s)")
        params.append(sorted(set(person_ids)))

    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT {_PERSON_FIELDS}, sc.tz, sc.fte, sc.wk_hours, sc.def_wk_hours
                {_PERSON_FROM}
                {_SCHEDULE_JOIN}
                WHERE {' AND '.join(conditions)}
                ORDER BY p.person_id
                """,
                tuple(params),
            )
            return list(cursor.fetchall())


def get_person(person_id: str | None) -> dict[str, Any] | None:
    """PERSON 한 명. 팀 경계 검사는 호출자(플랫폼) 몫이다."""

    if person_id is None:
        return None

    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT {_PERSON_FIELDS}
                {_PERSON_FROM}
                WHERE p.person_id = %s
                """,
                (person_id,),
            )
            return cursor.fetchone()


def lookup_persons(person_ids: list[str]) -> dict[str, dict[str, Any]]:
    """`person_id → PERSON` 표시용 조회표.

    **재직 상태를 가리지 않는다.** 퇴사자에게 연결된 계정도 운영자 화면에서는
    이름이 보여야 하기 때문이다(가리면 "이름 없는 계정"으로 나온다).
    """

    if not person_ids:
        return {}

    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT {_PERSON_FIELDS}
                {_PERSON_FROM}
                WHERE p.person_id = ANY(%s)
                """,
                (sorted(set(person_ids)),),
            )
            return {row["person_id"]: row for row in cursor.fetchall()}


def list_person_skills(person_id: str | None) -> list[dict[str, Any]]:
    """이 사람의 보유 스킬. 숙련도가 높은 것부터.

    `source`를 같이 준다 — HR이 등록한 것과 이력서에서 뽑은 것, AI가 추정한 것은
    신뢰도가 다르고, 배정 근거를 설명할 때 그 차이가 필요하다.
    """

    if not person_id:
        return []

    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT s.skill_id, s.name, s.category,
                       ps.proficiency, ps.source, ps.confidence
                FROM mock_hr.person_skill AS ps
                JOIN mock_hr.skill AS s ON s.skill_id = ps.skill_id
                WHERE ps.person_id = %s
                ORDER BY ps.proficiency DESC, s.name
                """,
                (person_id,),
            )
            return list(cursor.fetchall())


def lookup_orgs(org_ids: list[str]) -> dict[str, dict[str, Any]]:
    """`org_id → ORG` 표시용 조회표. 비활성 조직도 포함한다(위와 같은 이유)."""

    if not org_ids:
        return {}

    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT org_id, up_org_id, mgr_id, name, org_type, status
                FROM mock_hr.org
                WHERE org_id = ANY(%s)
                """,
                (sorted(set(org_ids)),),
            )
            return {row["org_id"]: row for row in cursor.fetchall()}


def count_orgs() -> int:
    """**운영자 전용** — HR 전체 활성 조직 수."""

    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) AS n FROM mock_hr.org WHERE status = 'ACTIVE'")
            return cursor.fetchone()["n"]


def list_capacity_profiles(
    *,
    person_ids: list[str],
    period_start: Any,
    period_end: Any,
) -> list[dict[str, Any]]:
    """부하 계산의 분모가 되는 근무조건. 재직 중인 사람만 준다.

    `sched`는 이력 테이블이라 사람마다 여러 행이 있을 수 있다. 기간과 겹치는 행
    중 가장 최근에 시작한 것 하나만 고른다 — 안 그러면 과거 근무조건까지 합산돼
    `wk_hours`가 부풀려진다.

    `wk_hours`가 NULL인 사람은 그 필드가 비어 온다. **여기서 40시간 같은 값을
    채우지 않는다** — 무엇이 없는지는 계산기가 알아야 `NO_SCHEDULE`로 판정할 수
    있고, 조용히 채우면 없는 근무조건이 있는 것처럼 보인다.
    """

    if not person_ids:
        return []

    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT p.person_id, p.name, p.job_role,
                       sc.wk_hours, sc.def_wk_hours, sc.fte, sc.tz
                FROM mock_hr.person AS p
                LEFT JOIN LATERAL (
                    SELECT s.tz, s.fte, s.wk_hours, s.def_wk_hours
                    FROM mock_hr.sched AS s
                    WHERE s.person_id = p.person_id
                      AND s.eff_from <= %s
                      AND (s.eff_to IS NULL OR s.eff_to >= %s)
                    ORDER BY s.eff_from DESC
                    LIMIT 1
                ) AS sc ON true
                WHERE p.person_id = ANY(%s) AND p.emp_status = 'ACTIVE'
                ORDER BY p.person_id
                """,
                (period_end, period_start, sorted(set(person_ids))),
            )
            return list(cursor.fetchall())


def list_absences(
    *,
    person_ids: list[str],
    period_start: Any,
    period_end: Any,
) -> list[dict[str, Any]]:
    """기간과 겹치는 **승인된** 부재.

    `status = 'APPROVED'` 화이트리스트다. "REQUESTED만 제외" 같은 블랙리스트로
    짜면 나중에 반려·취소 상태가 생겼을 때 승인 휴가처럼 차감된다.

    기간을 넘어가는 부재(육아휴직 214일)도 그대로 준다. 창으로 자르는 것은
    계산기 몫이다 — 자르지 않고 통째로 빼면 가용용량이 음수가 된다.
    """

    if not person_ids:
        return []

    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT person_id, absence_type, start_at, end_at
                FROM mock_hr.absence
                WHERE person_id = ANY(%s)
                  AND status = 'APPROVED'
                  AND start_at < %s
                  AND end_at >= %s
                ORDER BY person_id, start_at
                """,
                (sorted(set(person_ids)), period_end, period_start),
            )
            return list(cursor.fetchall())


def lookup_person_ids_by_external_email(*, sys_type: str, emails: list[str]) -> dict[str, str]:
    """외부 시스템 이메일 → `person_id` 조회표. 키는 소문자다.

    Jira 이슈의 담당자는 `accountId`와 이메일로만 오므로, 그 사람이 우리 쪽
    누구인지 알려면 이 표가 필요하다. `person_link`도 HR 테이블이라 여기 둔다.

    이슈마다 조회하지 않고 한 번에 받는다 — 35건이면 35번 왕복할 이유가 없다.
    **찾지 못한 이메일은 그냥 표에 없다.** 호출자가 그것을 미매핑으로 세고
    행은 버리지 않는다(버리면 부하 총량이 조용히 줄어든다).
    """

    if not emails:
        return {}

    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT lower(ext_email) AS ext_email, person_id
                FROM mock_hr.person_link
                WHERE sys_type = %s AND lower(ext_email) = ANY(%s)
                """,
                (sys_type, sorted({email.lower() for email in emails})),
            )
            return {row["ext_email"]: row["person_id"] for row in cursor.fetchall()}


def discover_person_by_email(email: str) -> dict[str, Any] | None:
    """이메일로 찾은 PERSON 후보. 온보딩의 본인 확인 한 곳에서만 쓴다.

    아직 이 계정이 어느 팀인지 정해지기 전 단계라 범위를 좁힐 근거가 없다.
    실제 HR이라면 연결 자격증명이 회사를 좁혀주지만 목업에는 자격증명이 없다.
    여기서 사람을 확정한 뒤 팀장이 팀을 만들고, 그 뒤 모든 조회는 팀 기준이다.
    """

    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT {_PERSON_FIELDS}
                {_PERSON_FROM}
                WHERE lower(p.email) = lower(%s) AND p.emp_status = 'ACTIVE'
                """,
                (email,),
            )
            return cursor.fetchone()
