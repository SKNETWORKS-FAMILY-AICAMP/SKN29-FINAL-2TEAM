"""Agent Platform 테이블(`agent`·`agent_tool`·`mcp_tool`·`agent_run`·`tool_call`)의 직접 SQL.

`repositories.py`가 아니라 여기에 두는 이유는 `document_pipeline.py`와 같다 —
한 도메인의 테이블만 다루고, 그 도메인 코드(`services/harness/`)만 부른다.

Harness 는 `services/` 에 있어서 psycopg 에 직접 붙지 않는다. 이 모듈이 그
경계다.
"""

from __future__ import annotations

from typing import Any

from .connection import database_connection
from .errors import RecordNotFound


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
