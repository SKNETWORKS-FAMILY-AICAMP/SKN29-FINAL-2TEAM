"""Agent Platform 테이블(`agent`·`agent_tool`·`mcp_tool`·`agent_run`·`tool_call`)의 직접 SQL.

`repositories.py`가 아니라 여기에 두는 이유는 `document_pipeline.py`와 같다 —
한 도메인의 테이블만 다루고, 그 도메인 코드(`services/harness/`)만 부른다.

Harness 는 `services/` 에 있어서 psycopg 에 직접 붙지 않는다. 이 모듈이 그
경계다.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from psycopg.types.json import Jsonb

from apps.connectors.oauth import decrypt_credential, encrypt_credential

from .codes import next_short_code
from .connection import database_connection
from .errors import PermissionDenied, RecordNotFound, ReferenceNotFound, RepositoryError
from .repositories import _require_team


class AgentRepository:
    @staticmethod
    def get(agent_id: str) -> dict[str, Any]:
        """에이전트 정의 한 건. 없으면 실행할 것이 없으므로 예외다."""

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT agent_id, team_id, name, description, instruction,
                           model, reasoning_effort, max_iterations,
                           is_prebuilt, status
                    FROM agent
                    WHERE agent_id = %s
                    """,
                    (agent_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    raise RecordNotFound(f"존재하지 않는 에이전트입니다: {agent_id}")
                return row

    @staticmethod
    def tool_refs(agent_id: str) -> list[str]:
        """이 에이전트에게 허용된 tool_ref 목록.

        빈 목록은 "도구 없이 대화만"이라는 유효한 설정이다 — 없는 에이전트와
        구분되지 않으니 호출 전에 `get()` 으로 존재를 확인하는 쪽이 낫다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT tool_ref FROM agent_tool WHERE agent_id = %s ORDER BY tool_ref",
                    (agent_id,),
                )
                return [row["tool_ref"] for row in cursor.fetchall()]

    @staticmethod
    def mcp_tools(team_id: str) -> list[dict[str, Any]]:
        """팀이 등록한 MCP tool 중 켜져 있는 것.

        `tool_ref` 를 여기서 조립해 돌려준다 — `mcp:` 접두사 규칙을 Registry 와
        Repository 두 곳에 적으면 한쪽만 바뀌었을 때 조용히 안 맞는다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT 'mcp:' || t.mcp_tool_id AS tool_ref,
                           t.mcp_tool_id, t.name, t.description, t.input_schema,
                           s.mcp_server_id, s.name AS server_name, s.endpoint_url
                    FROM mcp_tool AS t
                    JOIN mcp_server AS s ON s.mcp_server_id = t.server_id
                    WHERE s.team_id = %s AND t.enabled = true
                    ORDER BY s.name, t.name
                    """,
                    (team_id,),
                )
                return list(cursor.fetchall())

    @staticmethod
    def callable_agents(*, team_id: str, exclude_agent_id: str) -> list[dict[str, Any]]:
        """이 팀에서 **다른 에이전트가 도구로 부를 수 있는** 에이전트.

        `tool_ref` 를 여기서 조립한다 — `agent:` 접두사 규칙을 Registry 와
        Repository 두 곳에 적으면 한쪽만 고쳐졌을 때 조용히 안 맞는다
        (`mcp_tools` 와 같은 이유).

        **자기 자신은 뺀다.** 넣으면 모델이 자기를 부르는 고리를 만들 수 있고,
        깊이 상한이 있어도 그 왕복이 전부 토큰이다.

        `description` 이 위임 판단의 유일한 근거다 — 모델은 그 문장만 보고
        누구에게 넘길지 정한다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT 'agent:' || agent_id AS tool_ref,
                           agent_id, name, description
                    FROM agent
                    WHERE team_id = %s AND agent_id <> %s AND status = 'ACTIVE'
                    ORDER BY is_prebuilt DESC, name
                    """,
                    (team_id, exclude_agent_id),
                )
                return list(cursor.fetchall())


class AgentRunRepository:
    """실행 로그. **평가가 읽는 유일한 기록이라 실패해도 남아야 한다.**"""

    @staticmethod
    def start(*, agent_id: str, session_id: str | None, parent_run_id: str | None) -> str:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO agent_run (session_id, agent_id, parent_run_id, status)
                    VALUES (%s, %s, %s, 'RUNNING')
                    RETURNING run_id::text
                    """,
                    (session_id, agent_id, parent_run_id),
                )
                return cursor.fetchone()["run_id"]

    @staticmethod
    def finish(
        *,
        run_id: str,
        status: str,
        iterations: int,
        token_in: int | None = None,
        token_out: int | None = None,
    ) -> None:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE agent_run
                       SET status = %s, iterations = %s,
                           token_in = %s, token_out = %s, ended_at = now()
                     WHERE run_id = %s
                    """,
                    (status, iterations, token_in, token_out, run_id),
                )


class ToolCallRepository:
    """**선기록 패턴.** 실행 전에 PENDING 으로 넣고 끝난 뒤 갱신한다.

    끝나고 나서 한 번에 기록하면 타임아웃·프로세스 종료로 죽은 호출이 로그에서
    통째로 사라진다 — 정작 조사해야 할 것이 그 호출이다.
    """

    @staticmethod
    def begin(*, run_id: str, tool_ref: str, input_summary: str | None) -> str:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO tool_call (run_id, tool_ref, input_summary, status)
                    VALUES (%s, %s, %s, 'PENDING')
                    RETURNING tool_call_id::text
                    """,
                    (run_id, tool_ref, input_summary),
                )
                return cursor.fetchone()["tool_call_id"]

    @staticmethod
    def end(
        *,
        tool_call_id: str,
        status: str,
        duration_ms: int,
        error_code: str | None = None,
    ) -> None:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE tool_call
                       SET status = %s, error_code = %s, duration_ms = %s
                     WHERE tool_call_id = %s
                    """,
                    (status, error_code, duration_ms, tool_call_id),
                )


def _require_session(cursor, *, session_id: str, account_id: str) -> dict[str, Any]:
    """이 대화가 내 팀 것인지 확인하고 대화 행을 돌려준다.

    **소유자 검사가 아니라 팀 검사다.** 대화는 개인이 시작하지만 근거·결과는
    팀의 문서와 Jira 에서 나오므로, 같은 팀이면 서로의 대화를 볼 수 있어야
    한다 — 이 저장소의 다른 테이블과 같은 경계다.

    `session_id` 가 UUID 형식이 아니면 psycopg 가 터진다. 화면이 이상한 값을
    보냈을 때 500 대신 404 가 되도록 여기서 걸러 준다.
    """

    team_id = _require_team(cursor, account_id)
    cursor.execute(
        """
        SELECT session_id::text, team_id, account_id, agent_id, proj_id, title,
               created_at, updated_at
        FROM chat_session
        WHERE session_id::text = %s
        """,
        (session_id,),
    )
    row = cursor.fetchone()
    if row is None:
        raise RecordNotFound(f"존재하지 않는 대화입니다: {session_id}")
    if row["team_id"] != team_id:
        raise PermissionDenied("이 대화에 접근할 수 없습니다.")
    return row


class ChatSessionRepository:
    @staticmethod
    def create(*, account_id: str, agent_id: str, proj_id: str | None, title: str | None) -> dict[str, Any]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team(cursor, account_id)

                # 남의 팀 에이전트로 대화를 열지 못하게 한다. FK 가 없으니
                # 이 검사가 유일한 자물쇠다.
                cursor.execute("SELECT team_id FROM agent WHERE agent_id = %s", (agent_id,))
                agent = cursor.fetchone()
                if agent is None:
                    raise RecordNotFound(f"존재하지 않는 에이전트입니다: {agent_id}")
                if agent["team_id"] != team_id:
                    raise PermissionDenied("이 에이전트를 쓸 수 없습니다.")

                cursor.execute(
                    """
                    INSERT INTO chat_session (team_id, account_id, agent_id, proj_id, title)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING session_id::text, team_id, account_id, agent_id, proj_id,
                              title, created_at, updated_at
                    """,
                    (team_id, account_id, agent_id, proj_id, title),
                )
                return cursor.fetchone()

    @staticmethod
    def list_for_account(account_id: str) -> list[dict[str, Any]]:
        """**내 대화만.** 계층이 `팀 > 프로젝트 > 채팅(개인)` 이다(2026-08-12 확정).

        ⚠ **8/12 까지 `WHERE s.team_id` 였다** — 팀원 전체가 서로의 대화를 보고
        있었다. 사이드바를 「프로젝트 > 대화」로 바꾸면서 화면만 고치고 이 쿼리를
        안 고쳤다. 문서에는 「개인 것만 보인다」로 먼저 적혀 있었는데 코드가
        따라오지 않은 상태였다.

        **읽기 권한 자체는 여전히 팀이다** — `_require_session` 이 팀 검사로
        남는다(대화를 열면 근거·결과가 팀의 문서·Jira 에서 나오므로 같은 팀이면
        열 수 있어야 한다). 바뀌는 것은 **목록에 무엇이 보이는가** 뿐이다.
        링크를 받으면 팀원의 대화를 열 수 있고, 그건 의도한 경계다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                # 팀이 없는 계정은 빈 목록이다. 이 검사는 남긴다 —
                # 계정만으로 거르면 팀 배정 전 계정도 목록을 받는다.
                _require_team(cursor, account_id)
                cursor.execute(
                    """
                    SELECT s.session_id::text, s.agent_id, s.proj_id, s.title,
                           s.created_at, s.updated_at, a.name AS agent_name
                    FROM chat_session AS s
                    LEFT JOIN agent AS a ON a.agent_id = s.agent_id
                    WHERE s.account_id = %s
                    ORDER BY s.updated_at DESC
                    """,
                    (account_id,),
                )
                return list(cursor.fetchall())

    @staticmethod
    def get(*, session_id: str, account_id: str) -> dict[str, Any]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                return _require_session(cursor, session_id=session_id, account_id=account_id)

    @staticmethod
    def rename_if_first_answer(*, session_id: str, account_id: str, title: str) -> bool:
        """**첫 답이 끝났을 때 한 번만** 제목을 바꾼다. 바꿨으면 True.

        대화를 만들 때는 첫 발화를 그대로 제목으로 두는데, 그러면 「업무 뽑기」로
        연 대화들이 글자까지 똑같아진다. 답이 나온 뒤라야 무엇에 대한 대화였는지
        정해지므로 그때 다시 짓는다.

        **두 번째 답부터는 건드리지 않는다.** 대화가 길어질수록 제목이 계속
        바뀌면 사이드바에서 찾던 것이 사라진다. 사람이 직접 고친 제목을 덮는
        일도 없다 — 그건 답이 하나뿐인 시점을 이미 지난 뒤다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                _require_session(cursor, session_id=session_id, account_id=account_id)
                cursor.execute(
                    """
                    SELECT count(*) AS n FROM chat_message
                    WHERE session_id::text = %s AND role = 'agent'
                    """,
                    (session_id,),
                )
                if cursor.fetchone()["n"] != 1:
                    return False
                cursor.execute(
                    "UPDATE chat_session SET title = %s WHERE session_id::text = %s",
                    (title, session_id),
                )
                return True

    @staticmethod
    def delete(*, session_id: str, account_id: str) -> None:
        """대화와 그 메시지를 지운다. agent_run·tool_call 은 남긴다.

        실행 로그를 같이 지우면 평가의 모수가 사용자의 정리 행위에 따라 줄어든다
        — "어제 100건 돌렸는데 오늘 60건"이 되면 아무것도 비교할 수 없다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                _require_session(cursor, session_id=session_id, account_id=account_id)
                cursor.execute(
                    "DELETE FROM chat_message WHERE session_id::text = %s", (session_id,)
                )
                cursor.execute(
                    "DELETE FROM chat_session WHERE session_id::text = %s", (session_id,)
                )


class ChatMessageRepository:
    @staticmethod
    def list_for_session(*, session_id: str, account_id: str) -> list[dict[str, Any]]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                _require_session(cursor, session_id=session_id, account_id=account_id)
                cursor.execute(
                    """
                    SELECT message_id::text, role, content, created_at
                    FROM chat_message
                    WHERE session_id::text = %s
                    ORDER BY created_at, message_id
                    """,
                    (session_id,),
                )
                return list(cursor.fetchall())

    @staticmethod
    def append(*, session_id: str, account_id: str, role: str, content: dict[str, Any]) -> dict[str, Any]:
        """메시지 한 줄. `content` 는 카드 구조 그대로다.

        평문이 아니라 JSONB 인 이유는 답변에 근거·확인 요청·결과 카드가 함께
        들어가기 때문이다. 화면이 다시 그릴 수 있어야 새로고침에 결과가 사라지지
        않는다(8/11 확정 ④).
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                _require_session(cursor, session_id=session_id, account_id=account_id)
                cursor.execute(
                    """
                    INSERT INTO chat_message (session_id, role, content)
                    VALUES (%s, %s, %s)
                    RETURNING message_id::text, role, content, created_at
                    """,
                    (session_id, role, Jsonb(content)),
                )
                row = cursor.fetchone()
                # 사이드바가 최신순으로 정렬한다. 갱신하지 않으면 방금 답한 대화가
                # 목록 아래에 남는다.
                cursor.execute(
                    "UPDATE chat_session SET updated_at = now() WHERE session_id::text = %s",
                    (session_id,),
                )
                return row

    @staticmethod
    def latest_pending_confirmation(*, session_id: str, account_id: str) -> dict[str, Any] | None:
        """가장 최근 확인 카드. confirm 이 "무엇을 승인하는가"를 여기서 읽는다.

        요청 body 로 받지 않는 이유는, 그러면 화면이 보낸 인자로 외부 시스템이
        바뀌기 때문이다. 승인 대상은 **서버가 저장해 둔 것**이어야 한다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                _require_session(cursor, session_id=session_id, account_id=account_id)
                cursor.execute(
                    """
                    SELECT message_id::text, content
                    FROM chat_message
                    WHERE session_id::text = %s
                      AND content->>'type' = 'awaiting_confirmation'
                    ORDER BY created_at DESC, message_id DESC
                    LIMIT 1
                    """,
                    (session_id,),
                )
                return cursor.fetchone()


class McpServerRepository:
    """MCP 서버 등록. **토큰은 암호화해서만 저장한다**(11_MCP_설계 §4-2).

    `apps/connectors` 의 Fernet 을 그대로 쓴다 — 키 파생을 두 곳에 두면 한쪽만
    바뀌었을 때 조용히 복호화가 안 된다.
    """

    @staticmethod
    def list_for_team(account_id: str) -> list[dict[str, Any]]:
        """목록. **토큰은 내보내지 않는다** — 있는지 여부만 준다(화면은 마스킹)."""

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team(cursor, account_id)
                cursor.execute(
                    """
                    SELECT s.mcp_server_id, s.name, s.endpoint_url, s.status,
                           s.last_checked_at, s.created_by,
                           (s.auth_token_enc IS NOT NULL) AS has_token,
                           COALESCE(
                               (SELECT json_agg(json_build_object(
                                    'mcp_tool_id', t.mcp_tool_id, 'name', t.name,
                                    'description', t.description, 'enabled', t.enabled)
                                    ORDER BY t.name)
                                FROM mcp_tool t WHERE t.server_id = s.mcp_server_id),
                               '[]'::json) AS tools
                    FROM mcp_server AS s
                    WHERE s.team_id = %s
                    ORDER BY s.name
                    """,
                    (team_id,),
                )
                return list(cursor.fetchall())

    @staticmethod
    def create(
        *, account_id: str, name: str, endpoint_url: str, auth_token: str | None
    ) -> dict[str, Any]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team(cursor, account_id)
                server_id = next_short_code(
                    cursor, table="mcp_server", column="mcp_server_id", prefix="MS"
                )
                cursor.execute(
                    """
                    INSERT INTO mcp_server (mcp_server_id, team_id, name, endpoint_url,
                                            auth_token_enc, status, created_by)
                    VALUES (%s, %s, %s, %s, %s, 'UNCHECKED', %s)
                    RETURNING mcp_server_id, name, endpoint_url, status, last_checked_at
                    """,
                    (
                        server_id,
                        team_id,
                        name,
                        endpoint_url,
                        encrypt_credential({"auth_token": auth_token}) if auth_token else None,
                        account_id,
                    ),
                )
                return cursor.fetchone()

    @staticmethod
    def credentials(*, server_id: str, account_id: str) -> dict[str, Any]:
        """연결 테스트에 필요한 것만. **복호화한 토큰은 여기서만 나온다.**"""

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team(cursor, account_id)
                row = _server_row(cursor, server_id=server_id, team_id=team_id)
        return {
            "mcp_server_id": row["mcp_server_id"],
            "endpoint_url": row["endpoint_url"],
            "auth_token": _auth_token(row["auth_token_enc"]),
        }

    @staticmethod
    def credentials_for_tool(tool_ref: str, *, team_id: str) -> dict[str, Any]:
        """`mcp:<mcp_tool_id>` 로 서버와 도구 이름을 함께 찾는다.

        Registry 가 실행 직전에 부른다. 팀을 함께 거는 것은, tool_ref 가 어떤
        경로로든 오염됐을 때 남의 팀 서버를 부르지 않게 하는 두 번째 자물쇠다.
        """

        mcp_tool_id = tool_ref.removeprefix("mcp:")
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT t.name AS tool_name, s.mcp_server_id, s.endpoint_url,
                           s.auth_token_enc, t.enabled
                    FROM mcp_tool AS t
                    JOIN mcp_server AS s ON s.mcp_server_id = t.server_id
                    WHERE t.mcp_tool_id = %s AND s.team_id = %s
                    """,
                    (mcp_tool_id, team_id),
                )
                row = cursor.fetchone()
        if row is None:
            raise RecordNotFound(f"등록되지 않은 MCP 도구입니다: {tool_ref}")
        if not row["enabled"]:
            raise PermissionDenied(f"꺼져 있는 MCP 도구입니다: {tool_ref}")
        return {
            "tool_name": row["tool_name"],
            "endpoint_url": row["endpoint_url"],
            "auth_token": _auth_token(row["auth_token_enc"]),
        }

    @staticmethod
    def save_tools(*, server_id: str, account_id: str, tools: list[dict[str, Any]]) -> int:
        """연결 테스트 결과를 반영하고 status 를 CONNECTED 로 올린다.

        서버에서 사라진 도구는 지운다. 남겨 두면 에이전트 허용 목록에 붙어 있는
        도구가 실제로는 없는 상태가 되고, 부를 때야 실패한다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team(cursor, account_id)
                _server_row(cursor, server_id=server_id, team_id=team_id)

                names = [tool["name"] for tool in tools]
                cursor.execute(
                    "DELETE FROM mcp_tool WHERE server_id = %s AND name <> ALL(%s)",
                    (server_id, names),
                )
                for tool in tools:
                    cursor.execute(
                        """
                        INSERT INTO mcp_tool (mcp_tool_id, server_id, name, description,
                                              input_schema, enabled)
                        VALUES (%s, %s, %s, %s, %s, true)
                        ON CONFLICT (server_id, name) DO UPDATE SET
                            description = EXCLUDED.description,
                            input_schema = EXCLUDED.input_schema,
                            discovered_at = now()
                        """,
                        (
                            next_short_code(
                                cursor, table="mcp_tool", column="mcp_tool_id", prefix="MT"
                            ),
                            server_id,
                            tool["name"],
                            tool["description"],
                            Jsonb(tool["input_schema"]),
                        ),
                    )
                cursor.execute(
                    "UPDATE mcp_server SET status = 'CONNECTED', last_checked_at = now() "
                    "WHERE mcp_server_id = %s",
                    (server_id,),
                )
                return len(tools)

    @staticmethod
    def mark_error(*, server_id: str, account_id: str) -> None:
        """연결 테스트 실패. **행은 지우지 않는다** — 사용자가 고쳐 쓸 값이고,
        ERROR 상태를 보여 줘야 왜 편집 화면에서 이 도구를 못 고르는지 안다."""

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team(cursor, account_id)
                _server_row(cursor, server_id=server_id, team_id=team_id)
                cursor.execute(
                    "UPDATE mcp_server SET status = 'ERROR', last_checked_at = now() "
                    "WHERE mcp_server_id = %s",
                    (server_id,),
                )

    @staticmethod
    def delete(*, server_id: str, account_id: str) -> None:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team(cursor, account_id)
                _server_row(cursor, server_id=server_id, team_id=team_id)
                # 에이전트 허용 목록에서도 뺀다. 안 빼면 없는 서버의 도구가
                # agent_tool 에 남아 부를 때마다 실패한다.
                cursor.execute(
                    """
                    DELETE FROM agent_tool WHERE tool_ref IN (
                        SELECT 'mcp:' || mcp_tool_id FROM mcp_tool WHERE server_id = %s
                    )
                    """,
                    (server_id,),
                )
                cursor.execute("DELETE FROM mcp_tool WHERE server_id = %s", (server_id,))
                cursor.execute("DELETE FROM mcp_server WHERE mcp_server_id = %s", (server_id,))


def _server_row(cursor, *, server_id: str, team_id: str) -> dict[str, Any]:
    cursor.execute(
        "SELECT mcp_server_id, team_id, endpoint_url, auth_token_enc FROM mcp_server "
        "WHERE mcp_server_id = %s",
        (server_id,),
    )
    row = cursor.fetchone()
    if row is None:
        raise RecordNotFound(f"존재하지 않는 MCP 서버입니다: {server_id}")
    if row["team_id"] != team_id:
        raise PermissionDenied("이 MCP 서버에 접근할 수 없습니다.")
    return row


def _auth_token(ciphertext: str | None) -> str | None:
    if not ciphertext:
        return None
    return decrypt_credential(ciphertext).get("auth_token")


class AgentCrudRepository:
    """Builder 가 쓰는 에이전트 CRUD.

    조회 전용인 `AgentRepository` 와 나눠 둔다 — 그쪽은 Harness 가 실행 중에
    부르는 경로라 팀 검사가 없다(실행 시점에는 이미 대화가 팀을 확인했다).
    여기는 사람이 요청하는 경로라 매번 팀을 묻는다.
    """

    @staticmethod
    def list_for_team(account_id: str) -> list[dict[str, Any]]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team(cursor, account_id)
                cursor.execute(
                    """
                    SELECT a.agent_id, a.name, a.description, a.instruction, a.model,
                           a.reasoning_effort, a.max_iterations, a.is_prebuilt, a.status,
                           a.created_by, a.created_at, a.updated_at,
                           ua.display_name AS owner_name,
                           COALESCE(
                               (SELECT json_agg(t.tool_ref ORDER BY t.tool_ref)
                                FROM agent_tool t WHERE t.agent_id = a.agent_id),
                               '[]'::json) AS tool_refs
                    FROM agent AS a
                    LEFT JOIN user_account AS ua ON ua.account_id = a.created_by
                    WHERE a.team_id = %s AND a.status = 'ACTIVE'
                    ORDER BY a.is_prebuilt DESC, a.name
                    """,
                    (team_id,),
                )
                return list(cursor.fetchall())

    @staticmethod
    def get(*, agent_id: str, account_id: str) -> dict[str, Any]:
        rows = AgentCrudRepository.list_for_team(account_id)
        for row in rows:
            if row["agent_id"] == agent_id:
                return row
        raise RecordNotFound(f"존재하지 않는 에이전트입니다: {agent_id}")

    @staticmethod
    def create(*, account_id: str, fields: dict[str, Any], tool_refs: list[str]) -> dict[str, Any]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team(cursor, account_id)
                _check_tool_refs(cursor, team_id=team_id, tool_refs=tool_refs)
                agent_id = next_short_code(
                    cursor, table="agent", column="agent_id", prefix="AG"
                )
                cursor.execute(
                    """
                    INSERT INTO agent (agent_id, team_id, name, description, instruction,
                                       model, reasoning_effort, max_iterations,
                                       is_prebuilt, status, created_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, false, 'ACTIVE', %s)
                    """,
                    (
                        agent_id, team_id, fields["name"], fields["description"],
                        fields["instruction"], fields["model"], fields["reasoning_effort"],
                        fields["max_iterations"], account_id,
                    ),
                )
                _replace_tools(cursor, agent_id=agent_id, tool_refs=tool_refs)
        return AgentCrudRepository.get(agent_id=agent_id, account_id=account_id)

    @staticmethod
    def update(
        *, agent_id: str, account_id: str, fields: dict[str, Any], tool_refs: list[str]
    ) -> dict[str, Any]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team(cursor, account_id)
                _writable_agent(cursor, agent_id=agent_id, team_id=team_id)
                _check_tool_refs(cursor, team_id=team_id, tool_refs=tool_refs)
                cursor.execute(
                    """
                    UPDATE agent
                       SET name = %s, description = %s, instruction = %s, model = %s,
                           reasoning_effort = %s, max_iterations = %s, updated_at = now()
                     WHERE agent_id = %s
                    """,
                    (
                        fields["name"], fields["description"], fields["instruction"],
                        fields["model"], fields["reasoning_effort"],
                        fields["max_iterations"], agent_id,
                    ),
                )
                # 도구는 전체 교체다. 부분 갱신으로 두면 화면에서 체크를 푼 도구가
                # 남아 에이전트가 계속 쓸 수 있다.
                _replace_tools(cursor, agent_id=agent_id, tool_refs=tool_refs)
        return AgentCrudRepository.get(agent_id=agent_id, account_id=account_id)

    @staticmethod
    def delete(*, agent_id: str, account_id: str) -> None:
        """ARCHIVED 로 내린다. 행을 지우지 않는 이유는 `agent_run` 이 이 id 를
        가리키고 있어서다 — 지우면 평가가 어느 에이전트의 실행이었는지 잃는다."""

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team(cursor, account_id)
                _writable_agent(cursor, agent_id=agent_id, team_id=team_id)
                cursor.execute(
                    "UPDATE agent SET status = 'ARCHIVED', updated_at = now() WHERE agent_id = %s",
                    (agent_id,),
                )
                cursor.execute("DELETE FROM agent_tool WHERE agent_id = %s", (agent_id,))

    @staticmethod
    def team_tool_refs(account_id: str) -> list[dict[str, Any]]:
        """편집 화면이 고를 수 있는 MCP 도구. 내장 도구는 코드 상수라 여기 없다."""

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team(cursor, account_id)
                cursor.execute(
                    """
                    SELECT 'mcp:' || t.mcp_tool_id AS tool_ref, t.name, t.description,
                           s.name AS server_name, s.status AS server_status
                    FROM mcp_tool AS t
                    JOIN mcp_server AS s ON s.mcp_server_id = t.server_id
                    WHERE s.team_id = %s AND t.enabled = true
                    ORDER BY s.name, t.name
                    """,
                    (team_id,),
                )
                return list(cursor.fetchall())


def _writable_agent(cursor, *, agent_id: str, team_id: str) -> None:
    """수정·삭제해도 되는 에이전트인가.

    **기본 제공 에이전트는 거절한다.** 시드 스크립트가 정의를 소유하고 다시
    돌릴 때 덮어쓰므로, 화면에서 고친 값은 어차피 다음 실행에 사라진다 —
    고칠 수 있는 것처럼 보이는 편이 더 나쁘다(1차 단계 4 「우리가 제공하는 것」).
    """

    cursor.execute("SELECT team_id, is_prebuilt FROM agent WHERE agent_id = %s", (agent_id,))
    row = cursor.fetchone()
    if row is None:
        raise RecordNotFound(f"존재하지 않는 에이전트입니다: {agent_id}")
    if row["team_id"] != team_id:
        raise PermissionDenied("이 에이전트에 접근할 수 없습니다.")
    if row["is_prebuilt"]:
        raise PermissionDenied("기본 제공 에이전트는 수정하거나 지울 수 없습니다.")


def _check_tool_refs(cursor, *, team_id: str, tool_refs: list[str]) -> None:
    """실존하는 도구만 붙인다.

    없는 `tool_ref` 를 저장하면 Registry 가 조용히 걸러서, 사용자는 체크했는데
    에이전트는 그 도구를 못 쓰는 상태가 된다 — 화면과 실제가 어긋난다.
    """

    from services.harness.registry import BUILTIN_TOOLS

    unknown: list[str] = []
    for tool_ref in tool_refs:
        if tool_ref in BUILTIN_TOOLS:
            continue
        if not tool_ref.startswith("mcp:"):
            unknown.append(tool_ref)
            continue
        cursor.execute(
            """
            SELECT 1 FROM mcp_tool AS t
            JOIN mcp_server AS s ON s.mcp_server_id = t.server_id
            WHERE t.mcp_tool_id = %s AND s.team_id = %s AND t.enabled = true
            """,
            (tool_ref.removeprefix("mcp:"), team_id),
        )
        if cursor.fetchone() is None:
            unknown.append(tool_ref)

    if unknown:
        raise ReferenceNotFound(f"등록되지 않은 도구입니다: {', '.join(unknown)}")


def _replace_tools(cursor, *, agent_id: str, tool_refs: list[str]) -> None:
    cursor.execute("DELETE FROM agent_tool WHERE agent_id = %s", (agent_id,))
    for tool_ref in dict.fromkeys(tool_refs):
        cursor.execute(
            "INSERT INTO agent_tool (agent_id, tool_ref) VALUES (%s, %s)", (agent_id, tool_ref)
        )


def _date_or_none(value: Any) -> str | None:
    """`YYYY-MM-DD`(또는 ISO 일시)면 그대로, 아니면 None.

    **문서에는 절대 날짜가 잘 없다.** 실제로 「조치내역 확인 요청 후 5일 이내」,
    「종료단계(최종) 감리 종료 후 15일 이내」처럼 상대 표현이 뽑혀 나온다. 도구
    스키마가 `YYYY-MM-DD` 라고 설명은 하지만 강제하지는 않아서, 그 문자열이
    `timestamptz` 컬럼까지 그대로 내려가 `InvalidDatetimeFormat` 으로 죽었다 —
    한 트랜잭션이라 **승인한 18건이 통째로 롤백됐다**(2026-08-12 QA 시나리오 B).

    몇 건 때문에 전부를 잃는 것이 잘못이지, 날짜를 모르는 것 자체는 잘못이
    아니다. 비워 두고 **무엇을 비웠는지 말한다** — 이미 추출 결과가 「근거 없어
    비움」으로 쓰는 방식과 같다. 여기서 오늘 기준 절대 날짜를 지어내면 문서에
    없는 마감이 생기고, 그걸 근거로 배정하면 틀린 계획이 된다.
    """

    if value is None or isinstance(value, (date, datetime)):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        datetime.fromisoformat(text)
    except ValueError:
        return None
    return text


def _positive_or_none(value: Any) -> Any:
    """0·빈 문자열은 「모른다」로 본다.

    모델은 스키마에 `number` 라고 적혀 있으면 **모르는 값도 0 으로 채운다**.
    실제로 문서에 공수가 없던 업무 7건이 전부 `effort = 0.00` 으로 들어갔다 —
    화면은 「근거에서 확인하지 못해 비워 두었습니다」라고 말하는데 DB 에는 0 이
    있었다(2026-08-12 QA 시나리오 B).

    **0 시간짜리 업무는 없다.** 그대로 두면 배정과 진행률이 「공수 0 인 업무」로
    계산되고, 그건 「공수를 모르는 업무」와 정반대의 결론을 낸다.
    """

    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    try:
        return value if float(value) > 0 else None
    except (TypeError, ValueError):
        return None


class ProjectTaskRepository:
    """추출된 업무를 **우리 플랫폼**에 적재한다.

    지금까지 추출 결과는 어디에도 저장되지 않았다 — 화면 이벤트로 흐르고
    `chat_message` 의 이벤트 배열에만 남아, 그 대화를 떠나면 사라졌다. 저장소
    전체에 `INSERT INTO task` 가 한 건도 없었다(2026-08-11 확인).

    그래서 Jira 등록이 유일한 출구였고, Jira 를 안 쓰는 팀은 뽑은 업무를
    가질 방법이 없었다. **먼저 우리 것으로 만들고, Jira 는 그 다음이다.**

    `task` 는 `proj_know_model` 을 거쳐 프로젝트에 붙는다(schema.sql:474·409).
    추출 한 번이 지식 모델 한 판이라 **적재할 때마다 새 모델 행을 만든다** —
    덮어쓰면 어제 뽑은 것과 오늘 뽑은 것을 가릴 수 없고, 어느 것을 승인했는지도
    잃는다.
    """

    @staticmethod
    def register(*, proj_id: str, account_id: str, tasks: list[dict[str, Any]]) -> dict[str, Any]:
        if not tasks:
            raise RepositoryError("등록할 업무가 없습니다.")

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team(cursor, account_id)
                cursor.execute(
                    "SELECT team_id FROM proj WHERE proj_id = %s", (proj_id,)
                )
                row = cursor.fetchone()
                if row is None:
                    raise RecordNotFound(f"존재하지 않는 프로젝트입니다: {proj_id}")
                if row["team_id"] != team_id:
                    raise PermissionDenied("이 프로젝트에 접근할 수 없습니다.")

                # 이번 추출분을 담을 판. 버전은 이 프로젝트의 몇 번째인가다.
                cursor.execute(
                    "SELECT count(*) AS n FROM proj_know_model WHERE proj_id = %s", (proj_id,)
                )
                version = cursor.fetchone()["n"] + 1
                model_id = next_short_code(
                    cursor, table="proj_know_model", column="model_id", prefix="KM"
                )
                cursor.execute(
                    """
                    INSERT INTO proj_know_model (model_id, proj_id, model_ver, status, generated_at)
                    VALUES (%s, %s, %s, 'READY', now())
                    """,
                    (model_id, proj_id, f"v{version}"),
                )

                created = []
                dropped_dates = []
                for task in tasks:
                    task_id = next_short_code(
                        cursor, table="task", column="task_id", prefix="TK"
                    )
                    start_at = _date_or_none(task.get("start_date"))
                    due_at = _date_or_none(task.get("due_date"))
                    blank = [
                        label
                        for label, given, kept in (
                            ("시작", task.get("start_date"), start_at),
                            ("마감", task.get("due_date"), due_at),
                        )
                        if given and kept is None
                    ]
                    if blank:
                        dropped_dates.append({"title": task["title"], "fields": blank})
                    cursor.execute(
                        """
                        INSERT INTO task (task_id, model_id, task_name, req_role, effort,
                                          start_at, due_at, priority, src_type, status)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'EXTRACTED', 'PROPOSED')
                        """,
                        (
                            task_id, model_id, task["title"],
                            _positive_or_none(task.get("required_role")),
                            _positive_or_none(task.get("effort_hours")), start_at,
                            due_at, _positive_or_none(task.get("priority")),
                        ),
                    )
                    created.append({"task_id": task_id, "title": task["title"]})

        return {
            "model_id": model_id,
            "model_ver": f"v{version}",
            "tasks": created,
            # 비운 것을 조용히 넘기지 않는다. 모델이 이것을 사람에게 옮겨 적는다.
            "dropped_dates": dropped_dates,
        }

    @staticmethod
    def list_for_project(*, proj_id: str, account_id: str) -> list[dict[str, Any]]:
        """가장 최근 판의 업무. 옛 판은 남기되 화면에는 지금 것만 보인다."""

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team(cursor, account_id)
                cursor.execute(
                    """
                    SELECT t.task_id, t.task_name, t.req_role, t.effort, t.start_at,
                           t.due_at, t.priority, t.status, m.model_ver, m.generated_at
                    FROM task AS t
                    JOIN proj_know_model AS m ON m.model_id = t.model_id
                    JOIN proj AS p ON p.proj_id = m.proj_id
                    WHERE m.proj_id = %s AND p.team_id = %s
                      AND m.model_id = (
                          SELECT model_id FROM proj_know_model
                          WHERE proj_id = %s ORDER BY generated_at DESC NULLS LAST LIMIT 1
                      )
                    ORDER BY t.task_id
                    """,
                    (proj_id, team_id, proj_id),
                )
                return list(cursor.fetchall())

    @staticmethod
    def update(
        *,
        proj_id: str,
        account_id: str,
        task_id: str,
        status: str | None = None,
        assignee_name: str | None = None,
        due_at: str | None = None,
    ) -> dict[str, Any]:
        """등록된 업무 한 건을 고친다.

        **등록만 되고 아무것도 못 바꾸던 것을 연다(2026-08-12).** `task.status` 는
        `PROPOSED / CONFIRMED / REJECTED` 인데 저장소 전체에 `UPDATE task` 가 한 건도
        없어서, 한 번 등록하면 영원히 `PROPOSED` 였다 — 확정도 반려도 못 하면
        `task` 는 쓰레기통이 된다.

        **담당자는 이름 문자열로 받는다.** `task` 에는 담당자 컬럼이 없어서
        `task_name` 옆에 두는 대신 `req_role` 을 쓰지 않는다 — 역할과 사람은 다른
        것이다. 지금은 이름을 받아 두는 자리가 없으므로 **담당자 지정은 받지
        않는다**(인자만 두면 조용히 버려진다). 필요해지면 컬럼을 먼저 만든다.
        """

        if status is None and due_at is None:
            raise RepositoryError("바꿀 값이 없습니다.")
        if status is not None and status not in ("PROPOSED", "CONFIRMED", "REJECTED"):
            raise RepositoryError(f"알 수 없는 상태입니다: {status}")

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team(cursor, account_id)
                # **팀 소유를 SQL 에서 직접 확인한다.** FK 가 없는 테이블이라
                # task_id 만 믿으면 남의 팀 업무를 고칠 수 있다.
                cursor.execute(
                    """
                    SELECT t.task_id
                    FROM task AS t
                    JOIN proj_know_model AS m ON m.model_id = t.model_id
                    JOIN proj AS p ON p.proj_id = m.proj_id
                    WHERE t.task_id = %s AND m.proj_id = %s AND p.team_id = %s
                    """,
                    (task_id, proj_id, team_id),
                )
                if cursor.fetchone() is None:
                    raise RecordNotFound(f"이 프로젝트에 없는 업무입니다: {task_id}")

                sets, values = [], []
                if status is not None:
                    sets.append("status = %s")
                    values.append(status)
                if due_at is not None:
                    sets.append("due_at = %s")
                    values.append(due_at)
                values.append(task_id)

                cursor.execute(
                    f"UPDATE task SET {', '.join(sets)} WHERE task_id = %s "
                    "RETURNING task_id, task_name, status, due_at",
                    values,
                )
                return cursor.fetchone()
