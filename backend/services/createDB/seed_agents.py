"""기본 제공 에이전트 시드.

`grant_admin.py`·`vec_idx_setup.py`와 같이 컨테이너 안이 아니라 호스트 Python에서
직접 실행한다. API로 만들지 않는 이유는 이 행들이 **우리가 제공하는 것**이지
팀이 만든 것이 아니기 때문이다 — `is_prebuilt = true`인 행을 API로 만들 수 있으면
그 구분이 무의미해진다.

팀마다 한 벌씩 필요하다. 에이전트는 팀 소유(`agent.team_id`)라서, 새 팀이
생기면 그 팀 앞으로 다시 돌려야 한다.

멱등하다. 여러 번 돌려도 같은 팀에 두 개가 생기지 않고, 이미 있으면 정의(지시·
모델·도구)를 최신으로 맞춘다 — 사람이 화면에서 고친 값도 같이 덮어쓰므로
기본 제공 에이전트는 팀이 편집하지 않는다는 전제 위에서만 안전하다.

사용법:
    DATABASE_URL="postgres://project_copilot:project_copilot@localhost:5432/project_copilot" \\
      python backend/services/createDB/seed_agents.py --team TM001
    python backend/services/createDB/seed_agents.py --all-teams
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

#: 기본 제공 에이전트 정의.
#:
#: `instruction` 은 공통 스캐폴드(`services/harness/scaffold.py`) **뒤에** 붙는다.
#: 그래서 여기에 "근거 없이 추측하지 말라" 같은 공통 규칙을 다시 적지 않는다 —
#: 두 곳에 적으면 한쪽만 고쳐졌을 때 어느 쪽이 진짜인지 알 수 없다.
#:
#: `tool_refs` 는 `agent_tool.tool_ref` 값 그대로다.
PREBUILT_AGENTS = [
    {
        "name": "업무 추출 에이전트",
        "description": "기준 문서를 읽고 업무 후보를 뽑아 근거와 함께 정리합니다.",
        "instruction": (
            "사용자가 업무를 정리해 달라고 하면 task_extraction 도구를 부른다.\n"
            "기준 문서는 사람이 미리 골라 둔 것을 쓴다 — 어느 문서로 뽑을지 네가 정하지 않는다.\n"
            "추출이 끝나면 몇 건이 나왔는지와 주의할 점(경고)만 짧게 말한다. "
            "업무 목록 자체는 화면이 카드로 보여주므로 다시 나열하지 않는다.\n"
            "근거가 확인되지 않아 빠진 업무가 있으면 그 사실을 숨기지 않고 함께 말한다.\n"
            "사용자가 Jira 등록을 요청하면 jira_create_issues 를 부른다. 등록 결과는 "
            "성공 건수만 말하지 말고 실패한 건과 그 사유를 함께 말한다 — 부분 실패를 "
            "성공처럼 뭉개지 않는다."
        ),
        # 최종 정리 단계가 긴 추론을 쓴다. 안쪽 파이프라인은 자기 모델을 따로
        # 쓰므로(services/task_extraction), 여기 값은 바깥 대화용이다.
        "model": "gpt-5.6-luna",
        "reasoning_effort": "low",
        # 가장 긴 정상 흐름이 document_search → task_extraction →
        # jira_create_issues → 답변이라 4회전이 필요하다. 상한은 폭주를 막는
        # 값이지 정상 흐름을 자르는 값이 아니라서 한 번의 여유를 더 둔다.
        # 크게 잡을 이유도 없다 — 실패할 때 그만큼 오래 헛돈다.
        "max_iterations": 6,
        "tool_refs": [
            "task_extraction",
            "document_search",
            "jira_create_issues",
            "jira_get_issues",
        ],
    },
]


def get_conn():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def _next_agent_id(cur) -> str:
    """`backend/db/codes.py`와 같은 규칙 — 'AG' + 세 자리."""

    cur.execute(
        "SELECT COALESCE(MAX(CAST(SUBSTRING(agent_id FROM 3) AS INTEGER)), 0) AS n "
        "FROM agent WHERE agent_id ~ '^AG[0-9]{3}$'"
    )
    number = cur.fetchone()["n"] + 1
    if number > 999:
        raise SystemExit("agent 코드 공간(AG000~AG999)이 소진됐습니다.")
    return f"AG{number:03d}"


def seed_team(conn, team_id: str) -> list[str]:
    """한 팀에 기본 제공 에이전트를 맞춘다. 손댄 에이전트 이름을 돌려준다."""

    touched = []
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM team WHERE team_id = %s", (team_id,))
        if cur.fetchone() is None:
            raise SystemExit(f"존재하지 않는 팀입니다: {team_id}")

        cur.execute("SELECT owner_account_id FROM team WHERE team_id = %s", (team_id,))
        created_by = cur.fetchone()["owner_account_id"]

        for spec in PREBUILT_AGENTS:
            # 이름으로 찾는다. 기본 제공 에이전트는 팀당 이름이 유일하다는 전제다
            # (DB 제약은 없다 — 팀이 만든 에이전트와 이름이 겹칠 수 있어서
            #  is_prebuilt 까지 함께 본다).
            cur.execute(
                "SELECT agent_id FROM agent WHERE team_id = %s AND name = %s AND is_prebuilt = true",
                (team_id, spec["name"]),
            )
            row = cur.fetchone()
            agent_id = row["agent_id"] if row else _next_agent_id(cur)

            if row:
                cur.execute(
                    """
                    UPDATE agent
                       SET description = %s, instruction = %s, model = %s,
                           reasoning_effort = %s, max_iterations = %s,
                           status = 'ACTIVE', updated_at = now()
                     WHERE agent_id = %s
                    """,
                    (
                        spec["description"], spec["instruction"], spec["model"],
                        spec["reasoning_effort"], spec["max_iterations"], agent_id,
                    ),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO agent (agent_id, team_id, name, description, instruction,
                                       model, reasoning_effort, max_iterations,
                                       is_prebuilt, status, created_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, true, 'ACTIVE', %s)
                    """,
                    (
                        agent_id, team_id, spec["name"], spec["description"],
                        spec["instruction"], spec["model"], spec["reasoning_effort"],
                        spec["max_iterations"], created_by,
                    ),
                )

            # 도구는 정의를 그대로 반영한다. 지운 도구가 남아 있으면 기본 제공
            # 에이전트가 우리가 아는 것과 다르게 동작한다.
            cur.execute(
                "DELETE FROM agent_tool WHERE agent_id = %s AND tool_ref <> ALL(%s)",
                (agent_id, spec["tool_refs"]),
            )
            for tool_ref in spec["tool_refs"]:
                cur.execute(
                    "INSERT INTO agent_tool (agent_id, tool_ref) VALUES (%s, %s) "
                    "ON CONFLICT (agent_id, tool_ref) DO NOTHING",
                    (agent_id, tool_ref),
                )

            touched.append(f"{agent_id} {spec['name']}{'' if row else ' (신규)'}")
    return touched


def main() -> int:
    parser = argparse.ArgumentParser(description="기본 제공 에이전트를 팀에 시드한다.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--team", help="대상 팀 id (예: TM001)")
    group.add_argument("--all-teams", action="store_true", help="모든 팀에 시드")
    args = parser.parse_args()

    with get_conn() as conn:
        if args.all_teams:
            with conn.cursor() as cur:
                cur.execute("SELECT team_id FROM team ORDER BY team_id")
                team_ids = [row["team_id"] for row in cur.fetchall()]
        else:
            team_ids = [args.team]

        if not team_ids:
            print("팀이 하나도 없습니다. 온보딩으로 팀을 먼저 만드세요.")
            return 1

        for team_id in team_ids:
            for line in seed_team(conn, team_id):
                print(f"{team_id}  {line}")
        conn.commit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
