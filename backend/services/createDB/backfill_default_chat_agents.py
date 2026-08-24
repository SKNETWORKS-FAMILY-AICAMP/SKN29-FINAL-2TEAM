"""기존 팀에 "기본 챗 에이전트"(새 버전 스키마, tool·MCP만) 백필.

컨테이너 안이 아니라 호스트 Python에서 직접 돌린다 — `backend.db.agent_platform`을
그대로 import하면 Django 설정 부트스트랩이 필요해지므로, raw SQL만 쓴다(repo
모듈 의존 없음).

**2026-08-15부터 새로 만드는 팀은 이 스크립트가 필요 없다** —
`backend/db/repositories.py`의 `TeamRepository.create()`가 팀 생성과 같은
트랜잭션으로 `agent_platform.provision_default_chat_agent()`를 이미 부른다.
이 스크립트는 그 날짜 **이전에 만들어진 팀**만을 위한 1회성 백필이다.

멱등하다 — 이미 `is_default_chat = true`인 행이 있는 팀은 건너뛴다
(`agents_one_default_chat_per_team` 부분 유니크 인덱스가 있어서 중복
INSERT는 어차피 DB가 막지만, 여기서 먼저 걸러 조용히 스킵한다).

사용법:
    DATABASE_URL="postgres://project_copilot:project_copilot@localhost:5432/project_copilot" \\
      python backend/services/createDB/backfill_default_chat_agents.py --all-teams
    python backend/services/createDB/backfill_default_chat_agents.py --team TE001
"""

import argparse
import os
import sys

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgres://project_copilot:project_copilot@localhost:5432/project_copilot",
)

# services/harness/runner.py의 DEFAULT_MODEL/DEFAULT_EFFORT와 반드시 같은 값을
# 써야 한다 — repo 모듈을 import하지 않는 이 스크립트의 전제상 여기 값을
# 직접 베꼈다. runner.py의 값이 바뀌면 여기도 같이 고칠 것.
DEFAULT_MODEL = "gpt-5.6-luna"
DEFAULT_EFFORT = "low"

#: 기본으로 붙이는 **읽기 도구**(2026-08-18 PM 결정). 도구가 0개면 기본 상태에서
#: 제품의 대표 발화가 전부 실패한다 — 「업무 뽑아줘」가 「문서를 대화에 첨부해
#: 주세요」로, 「팀원 누구야?」가 「조회할 수 없다」로 끝났다(QA §B-0).
#:
#: **쓰기 셋은 뺀다** — `task_register`·`task_update`·`jira_create_issues`.
#: 정본은 `services/harness/registry.py` 의 `side_effect` 플래그다(그쪽이 참인
#: 것만 빼면 된다). 이 스크립트는 repo 모듈을 import 하지 않는다는 전제라
#: 여기 베껴 뒀다 — **registry 에 도구를 더하면 여기도 같이 고쳐야 한다.**
READ_ONLY_TOOL_REFS = [
    "document_search",
    "document_list",
    "people_list",
    "workload_report",
    "absence_list",
    "task_extraction",
    "project_list",
    "task_list",
    "web_search",
    "jira_get_issues",
]

DEFAULT_CHAT_SYSTEM_PROMPT = (
    "당신은 팀의 업무를 돕는 기본 어시스턴트입니다. 연결된 도구가 있으면 활용해서 "
    "정확한 정보를 근거로 답하세요."
)


def get_conn():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def _next_code(cur, *, table: str, column: str, prefix: str) -> str:
    """`backend/db/codes.py`의 `next_short_code`와 같은 규칙 — prefix + 세 자리."""

    cur.execute(
        f"SELECT COALESCE(MAX(CAST(SUBSTRING({column} FROM 3) AS INTEGER)), 0) AS n "
        f"FROM {table} WHERE {column} ~ %s",
        (f"^{prefix}[0-9]{{3}}$",),
    )
    number = cur.fetchone()["n"] + 1
    if number > 999:
        raise SystemExit(f"{table} 코드 공간({prefix}000~{prefix}999)이 소진됐습니다.")
    return f"{prefix}{number:03d}"


def _next_agents_id(cur) -> str:
    """`agents.agent_id`를 발급한다. `_next_code()`와 같은 규칙이지만 이 테이블
    전용으로 남겨 둔다 — 호출부가 `table="agents"`를 매번 안 적어도 되게."""
    return _next_code(cur, table="agents", column="agent_id", prefix="AG")


def backfill_team(conn, team_id: str) -> str | None:
    """이 팀에 기본 챗 에이전트가 없으면 만든다. 만들었으면 agent_id, 이미
    있었으면 None을 돌려준다."""

    with conn.cursor() as cur:
        cur.execute("SELECT owner_account_id FROM team WHERE team_id = %s", (team_id,))
        team = cur.fetchone()
        if team is None:
            raise SystemExit(f"존재하지 않는 팀입니다: {team_id}")

        cur.execute(
            "SELECT agent_id FROM agents WHERE team_id = %s AND is_default_chat = true",
            (team_id,),
        )
        if cur.fetchone() is not None:
            return None

        agent_id = _next_agents_id(cur)
        cur.execute(
            """
            INSERT INTO agents
                (agent_id, team_id, name, description, owner_account_id,
                 status, is_default_chat)
            VALUES (%s, %s, %s, %s, %s, 'ACTIVE', true)
            """,
            (
                agent_id,
                team_id,
                "기본 어시스턴트",
                "Chat 화면의 기본 상대입니다. 도구·MCP만 붙일 수 있고 다른 에이전트로 위임하지 않습니다.",
                team["owner_account_id"],
            ),
        )

        agent_version_id = _next_code(
            cur, table="agent_versions", column="agent_version_id", prefix="AV"
        )
        cur.execute(
            """
            INSERT INTO agent_versions
                (agent_version_id, agent_id, version, system_prompt, model,
                 reasoning_effort, created_by)
            VALUES (%s, %s, 1, %s, %s, %s, %s)
            """,
            (
                agent_version_id,
                agent_id,
                DEFAULT_CHAT_SYSTEM_PROMPT,
                DEFAULT_MODEL,
                DEFAULT_EFFORT,
                team["owner_account_id"],
            ),
        )

        _attach_read_only_tools(cur, agent_version_id)

        cur.execute(
            "UPDATE agents SET current_version_id = %s WHERE agent_id = %s",
            (agent_version_id, agent_id),
        )

    return agent_id


def _attach_read_only_tools(cur, agent_version_id: str) -> int:
    """이 버전에 읽기 도구를 붙인다. 이미 있는 것은 건너뛴다(멱등)."""

    cur.execute(
        "SELECT tool_ref FROM agent_version_tools WHERE agent_version_id = %s",
        (agent_version_id,),
    )
    have = {row["tool_ref"] for row in cur.fetchall()}
    added = 0
    for tool_ref in READ_ONLY_TOOL_REFS:
        if tool_ref in have:
            continue
        cur.execute(
            "INSERT INTO agent_version_tools (agent_version_id, tool_ref) VALUES (%s, %s)",
            (agent_version_id, tool_ref),
        )
        added += 1
    return added


def fill_tools_for_existing(conn, team_id: str) -> int:
    """이미 있는 기본 챗 에이전트의 **현재 버전**에 빠진 읽기 도구를 채운다.

    2026-08-18 오후에 만들어진 것들은 도구가 0개다 — 그때는 `provision_default_
    chat_agent()` 가 도구를 안 붙였다. 「발행된 버전은 불변」 원칙과 부딪혀
    보이지만, 이 버전은 **사람이 발행한 것이 아니라 시스템이 만든 것**이고
    사람이 그 위에 새 버전을 낸 적이 없다. 새로 발행하면 `agent_version_id` 가
    바뀌어 그 에이전트로 만든 기존 대화의 고정이 끊긴다.
    """

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT a.agent_id, a.current_version_id
              FROM agents AS a
             WHERE a.team_id = %s AND a.is_default_chat = true
            """,
            (team_id,),
        )
        row = cur.fetchone()
        if row is None or not row["current_version_id"]:
            return 0
        return _attach_read_only_tools(cur, row["current_version_id"])


def main() -> int:
    parser = argparse.ArgumentParser(description="기존 팀에 기본 챗 에이전트를 백필한다.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--team", help="대상 팀 id (예: TE001)")
    group.add_argument("--all-teams", action="store_true", help="모든 팀에 백필")
    args = parser.parse_args()

    with get_conn() as conn:
        if args.all_teams:
            with conn.cursor() as cur:
                cur.execute("SELECT team_id FROM team ORDER BY team_id")
                team_ids = [row["team_id"] for row in cur.fetchall()]
        else:
            team_ids = [args.team]

        if not team_ids:
            print("팀이 하나도 없습니다.")
            return 1

        for team_id in team_ids:
            agent_id = backfill_team(conn, team_id)
            if agent_id:
                print(f"{team_id}  {agent_id} 기본 챗 (신규 · 읽기 도구 {len(READ_ONLY_TOOL_REFS)}종)")
                continue
            # 이미 있어도 **도구가 비었을 수 있다** — 2026-08-18 오후에 만들어진
            # 것들이 그렇다. 그냥 건너뛰면 그 팀은 계속 도구 없이 돈다.
            added = fill_tools_for_existing(conn, team_id)
            if added:
                print(f"{team_id}  이미 있음 · 빠진 읽기 도구 {added}종을 채웠다")
            else:
                print(f"{team_id}  이미 있음, 건너뜀")
        conn.commit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
