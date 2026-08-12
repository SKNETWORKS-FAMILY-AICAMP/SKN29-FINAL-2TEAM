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

#: 위임 도구. 이 값을 가진 행이 **플랫폼의 정문**이다.
#:
#: 에이전트의 본질은 **좁히는 것**이다 — 「회의록 정리」는 문서만 보고 Jira 를
#: 안 건드린다. 그 좁힘이 정체성이다. 그런데 정문은 도구를 다 들고 다른
#: 에이전트까지 부른다. **아무것도 안 좁히므로 에이전트가 아니다** — 우리가
#: `agent` 행 하나로 표현했을 뿐 개념적으로는 대화 그 자체다(2026-08-12 PM).
#:
#: **식별을 이 값으로 한다.** `is_prebuilt` 로는 못 가른다 — 우리가 예시
#: 에이전트를 넣으면 그것도 같은 플래그를 쓰기 때문이다(실제로 잠깐 넣었다가
#: 되돌렸다). `agent:*` 는 Builder 의 도구 목록에 없으므로
#: (`AgentToolCatalogAPIView` 는 내장+MCP 만 준다) 팀이 실수로 만들 수도 없다.
#: 스키마를 안 바꾸고 구조로 가르는 길이다.
PLATFORM_TOOL = "agent:*"

#: 우리가 넣는 에이전트 — **정문 하나뿐이다.**
#:
#: 예시 에이전트 4종을 잠깐 넣었다가 되돌렸다(2026-08-12). 넷 다 정문 도구의
#: **부분집합**이라 할 수 있는 일이 하나도 안 늘었고, Builder 의 설계(복제
#: 버튼·프리셋·테스트 루프, 작업목록 작업 5)가 정해지기 전에 견본부터 넣은
#: 것이라 순서가 뒤였다. **먼저 늘릴 것은 도구다** — 도구가 플랫폼이 할 수
#: 있는 일의 전부이고, 에이전트는 그것을 좁힌 것에 불과하다.
#:
#: `instruction` 은 공통 스캐폴드(`services/harness/scaffold.py`) **뒤에** 붙는다.
#: 그래서 여기에 "근거 없이 추측하지 말라" 같은 공통 규칙을 다시 적지 않는다 —
#: 두 곳에 적으면 한쪽만 고쳐졌을 때 어느 쪽이 진짜인지 알 수 없다.
PREBUILT_AGENTS = [
    {
        "name": "코파일럿",
        "description": "무엇이든 말하면 됩니다. 필요하면 알맞은 에이전트에게 넘깁니다.",
        "instruction": (
            "사용자가 업무를 정리해 달라고 하면 task_extraction 도구를 부른다.\n"
            "기준 문서는 사람이 미리 골라 둔 것을 쓴다 — 어느 문서로 뽑을지 네가 정하지 않는다.\n"
            "추출이 끝나면 몇 건이 나왔는지만 한 줄로 말한다. "
            "업무 목록 자체는 화면이 카드로 보여주므로 다시 나열하지 않는다.\n"
            "근거가 확인되지 않아 빠진 업무가 있으면 그 사실을 숨기지 않고 함께 말한다.\n"
            # 추출 직후 바로 등록 게이트를 띄운다. 「등록할까요?」를 말로 묻고
            # 답을 기다리면 회전만 쓰고 끝나 버린다 — 확인 카드가 그 물음이다.
            "추출이 끝나면 **곧바로 task_register 를 부른다.** 말로 다시 묻지 않는다 — "
            "그 도구가 확인 카드를 띄우고 사람이 거기서 승인한다. 도구가 돌려준 "
            "`tasks` 를 그대로 넘긴다(제목·역할·공수·마감일). 목록을 새로 지어내지 "
            "않고 순서도 바꾸지 않는다.\n"
            "Jira 는 그 다음이다 — 우리 것으로 남아야 나중에 다시 볼 수 있고, Jira 를 "
            "쓰지 않는 팀도 결과를 갖는다.\n"
            "사용자가 Jira 등록을 요청하면 jira_create_issues 를 부른다. 등록 결과는 "
            "성공 건수만 말하지 말고 실패한 건과 그 사유를 함께 말한다 — 부분 실패를 "
            "성공처럼 뭉개지 않는다.\n"
            # 이슈 유형 이름은 사이트마다 다르고, 도구는 받은 이름을 그대로
            # Jira 에 넘긴다(apps/connectors/clients.py `create_jira_issues`).
            # 영어 관례대로 'Task' 를 보내면 한국어 사이트에서는 전건 실패한다.
            "Jira 이슈 유형은 대상 사이트에 실재하는 이름을 쓴다 — 이 사이트는 한국어다"
            "(작업 · 스토리 · 버그 · 에픽). 영어 이름을 지어내지 않는다.\n"
            # 「AIP」·「AIP-12」는 내부 식별자다. 사람은 이미 그 프로젝트의 대화에
            # 있고, 화면이 이름으로 그린다. 답에 키를 넣으면 화면과 어긋난다.
            "Jira 프로젝트 키(AIP 등)와 이슈 키(AIP-12 등)를 답에 쓰지 않는다 — "
            "프로젝트는 이름으로, 업무는 제목으로 부른다.\n"
            "업무 현황을 물으면 jira_get_issues 를 부르고, 건수 표와 목록은 화면이 "
            "카드로 보여주므로 다시 나열하지 않는다. 눈에 띄는 것 한두 가지만 말한다 "
            "— 마감이 지난 일이 있으면 그것부터.\n"
            # 팀 구성 질문에 document_search 를 돌려 "문서에 없다"고 접던 것을
            # 막는다(5차 단계 1). 명부는 문서가 아니라 DB에 있다.
            "팀에 누가 있는지 · 누가 무엇을 할 줄 아는지는 people_list 로 답한다 — "
            "사람에 대한 질문을 문서에서 찾지 않는다.\n"
            # 웹은 우리 문서가 아니다. 그 차이가 답에서 지워지면 「기획서에 그렇게
            # 적혀 있다」와 「인터넷에 그런 글이 있다」를 구별할 수 없다.
            "우리 문서에 있을 만한 것은 document_search 로 **먼저** 찾는다. "
            "문서에 없거나 최신 정보가 필요하면 web_search 를 쓴다.\n"
            "웹에서 온 것은 **출처 URL 을 함께 밝히고**, 우리 문서와 같은 무게로 "
            "말하지 않는다 — 어느 쪽 근거인지 사람이 알아야 한다.\n"
            "팀이 얼마나 바쁜지 · 누구에게 여유가 있는지 물으면 workload_report 를 부른다.\n"
            # 계산기가 주 단위로 도는데 기간을 빼고 말하면 「20시간」이 한 주치인지
            # 넉 달치인지 사람이 알 수 없다.
            "시간을 말할 때는 몇 주치를 본 숫자인지 함께 말한다.\n"
            "여유가 있어 보인다고 배정을 단정하지 않는다 — 이 계산에 안 잡힌 일이 "
            "있을 수 있고, 그건 사람이 판단할 몫이다.\n"
            # 위임. 팀이 Builder 로 만든 에이전트가 `agent:` 도구로 붙는다.
            "팀이 만들어 둔 에이전트가 도구 목록에 있으면(이름이 그 에이전트다), "
            "그 일에 더 맞는 에이전트가 있을 때 직접 하지 말고 넘긴다. "
            "넘길 때는 맡길 일을 한 문장으로 적는다 — 그 에이전트는 이 대화를 보지 "
            "못하므로 필요한 배경을 문장에 담는다.\n"
            "넘겼으면 돌아온 답을 네 말로 다시 쓰지 말고 그대로 전한다. 누가 한 "
            "일인지도 함께 말한다."
        ),
        # 최종 정리 단계가 긴 추론을 쓴다. 안쪽 파이프라인은 자기 모델을 따로
        # 쓰므로(services/task_extraction), 여기 값은 바깥 대화용이다.
        "model": "gpt-5.6-luna",
        "reasoning_effort": "low",
        # 가장 긴 정상 흐름이 task_extraction → people_list → workload_report →
        # jira_create_issues → 답변이라 5회전이다. 상한은 폭주를 막는 값이지 정상
        # 흐름을 자르는 값이 아니라서 여유를 더 둔다. 크게 잡을 이유도 없다 —
        # 실패할 때 그만큼 오래 헛돈다.
        "max_iterations": 8,
        "tool_refs": [
            "task_extraction",
            "task_register",
            "task_list",
            "task_update",
            "document_search",
            "document_list",
            "web_search",
            "project_list",
            "people_list",
            "workload_report",
            "absence_list",
            "jira_create_issues",
            "jira_get_issues",
            # 팀의 다른 ACTIVE 에이전트 전부를 도구로 받는다(services/harness/
            # registry.py `AGENT_TOOL_WILDCARD`). 목록을 id 로 박지 않는 이유는
            # Builder 로 만든 에이전트를 시드가 알 수 없기 때문이다 — 박으면
            # 「빌더에서 만든 에이전트를 쓸 수 있다」가 성립하지 않는다.
            PLATFORM_TOOL,
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

        # 정의에서 빠진 기본 제공 에이전트는 **지우지 않고 ARCHIVED 로 내린다.**
        # 목록 조회가 status='ACTIVE' 로 거르므로 화면에서는 사라지고, 그 에이전트로
        # 만들어진 옛 대화는 agent_id 를 그대로 풀 수 있다 — 지우면 그 대화들이
        # 이름 없는 기록이 된다(FK 가 없어 DB 가 막아 주지도 않는다).
        cur.execute(
            """
            UPDATE agent
               SET status = 'ARCHIVED', updated_at = now()
             WHERE team_id = %s AND is_prebuilt = true
               AND status = 'ACTIVE' AND name <> ALL(%s)
         RETURNING agent_id, name
            """,
            (team_id, [spec["name"] for spec in PREBUILT_AGENTS]),
        )
        for archived in cur.fetchall():
            touched.append(f"{archived['agent_id']} {archived['name']} (보관 처리)")
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
