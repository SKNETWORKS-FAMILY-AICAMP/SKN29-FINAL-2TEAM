"""Agent Platform 테이블(`agent`·`agent_tool`·`mcp_tool`·`agent_run`·`tool_call`)의 직접 SQL.

`repositories.py`가 아니라 여기에 두는 이유는 `document_pipeline.py`와 같다 —
한 도메인의 테이블만 다루고, 그 도메인 코드(`services/harness/`)만 부른다.

Harness 는 `services/` 에 있어서 psycopg 에 직접 붙지 않는다. 이 모듈이 그
경계다.
"""

from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .connection import database_connection
from .errors import PermissionDenied, RecordNotFound
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
    def list_for_team(account_id: str) -> list[dict[str, Any]]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team(cursor, account_id)
                cursor.execute(
                    """
                    SELECT s.session_id::text, s.agent_id, s.proj_id, s.title,
                           s.created_at, s.updated_at, a.name AS agent_name
                    FROM chat_session AS s
                    LEFT JOIN agent AS a ON a.agent_id = s.agent_id
                    WHERE s.team_id = %s
                    ORDER BY s.updated_at DESC
                    """,
                    (team_id,),
                )
                return list(cursor.fetchall())

    @staticmethod
    def get(*, session_id: str, account_id: str) -> dict[str, Any]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                return _require_session(cursor, session_id=session_id, account_id=account_id)

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
