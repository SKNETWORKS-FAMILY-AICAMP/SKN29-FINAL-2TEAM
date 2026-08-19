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

from apps.connectors.oauth import OAuthError, decrypt_credential, encrypt_credential

from services.agent_runtime.definitions import SubagentReference
from services.agent_runtime.subagents.validation import validate_subagents

from .codes import next_short_code
from .connection import database_connection
from .errors import (
    IdSpaceExhausted,
    PermissionDenied,
    RecordNotFound,
    ReferenceNotFound,
    RepositoryError,
)
from .repositories import _require_team


def _next_agents_id(cursor) -> str:
    """`agents.agent_id`를 발급하되, 옛 `agent` 테이블과 번호가 안 겹치게 한다.

    두 테이블이 'AG' 접두사를 공유하고(DB/migrations/2026-08-13_agent_versioning.sql
    상단 주석 — 전환 완료 시 `agent`를 대체할 것을 전제로 같은 코드 체계를
    물려받았다) 각자 따로 번호를 매기다 보니, 우연히 같은 값이 나올 수 있다.
    `_resolve_session_agent()`가 옛 테이블을 먼저 보기 때문에, 겹치면 새로
    만든 에이전트가 **조용히**(에러 없이) 옛 에이전트에게 가려진다 — 실제로
    Chat 재설계 검증 중 겪었다(2026-08-15, 지훈 확인 후 여기서 막기로 함).

    옛 `agent` 테이블 자체는 아직 못 지운다 — 지금 운영 중인 Chat이 여전히
    그 테이블에 물려 있다(재설계 완료 후 제거 예정, task #19). 그래서 발급
    시점에 두 테이블의 MAX를 같이 보고 더 큰 쪽 다음 번호를 쓴다.
    `next_short_code()`(`agents` 테이블만 본다)를 그대로 못 쓰는 이유가 이것이다.
    """
    # next_short_code()와 같은 lock 이름 — 재진입 가능한 잠금이라 같은
    # 트랜잭션 안에서 두 번 걸어도 안전하다(pg_advisory_xact_lock 특성).
    cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("id-sequence:agents:agent_id:AG",))

    cursor.execute(
        "SELECT COALESCE(MAX(CAST(SUBSTRING(agent_id FROM 3) AS INTEGER)), 0) AS n "
        "FROM agents WHERE agent_id ~ '^AG[0-9]{3}$'"
    )
    new_max = cursor.fetchone()["n"]
    cursor.execute(
        "SELECT COALESCE(MAX(CAST(SUBSTRING(agent_id FROM 3) AS INTEGER)), 0) AS n "
        "FROM agent WHERE agent_id ~ '^AG[0-9]{3}$'"
    )
    legacy_max = cursor.fetchone()["n"]

    next_number = max(new_max, legacy_max) + 1
    if next_number > 999:
        raise IdSpaceExhausted("agents.agent_id의 AG 코드 공간이 소진됐습니다.")
    return f"AG{next_number:03d}"


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

    #: 정문을 가르는 표식. `is_prebuilt` 로는 못 가른다 — 예시 에이전트도 같은
    #: 플래그를 쓴다. 도구를 안 좁히는 것(= `agent:*` 보유)이 정문이다.
    PLATFORM_TOOL = "agent:*"

    @staticmethod
    def main_model(account_id: str) -> dict[str, Any] | None:
        """이 팀의 **메인 모델** — 오케스트레이션하는 정문 에이전트의 모델.

        팀에 정문이 없으면(시드 전) `None`. 그때는 화면이 「아직 없다」고 말해야
        하고, 임의의 기본값을 보여주면 안 된다 — 저장한 적 없는 값을 저장된
        것처럼 보이는 것이 지금 Model 탭의 문제였다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team(cursor, account_id)
                cursor.execute(
                    """
                    SELECT a.agent_id, a.name, a.model
                    FROM agent AS a
                    JOIN agent_tool AS t ON t.agent_id = a.agent_id
                    WHERE a.team_id = %s AND t.tool_ref = %s AND a.status = 'ACTIVE'
                    LIMIT 1
                    """,
                    (team_id, AgentRepository.PLATFORM_TOOL),
                )
                return cursor.fetchone()

    @staticmethod
    def main_model_for_team(team_id: str) -> dict[str, Any] | None:
        """운영자 콘솔이 쓰는 조회. **`team_id` 를 직접 받는다** — 운영자에게는
        자기 팀이 없어 `_require_team` 이 통하지 않는다(모델 등록·커스텀 도구와
        같은 모양이다)."""

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT a.agent_id, a.name, a.model
                    FROM agent AS a
                    JOIN agent_tool AS t ON t.agent_id = a.agent_id
                    WHERE a.team_id = %s AND t.tool_ref = %s AND a.status = 'ACTIVE'
                    LIMIT 1
                    """,
                    (team_id, AgentRepository.PLATFORM_TOOL),
                )
                return cursor.fetchone()

    @staticmethod
    def set_main_model_for_team(*, team_id: str, model: str) -> dict[str, Any]:
        """운영자가 그 팀의 기본 채팅 모델을 정한다(2026-08-18 멘토링).

        **전역 하나로 두지 않는다.** 계약·리전 요건이 다른 회사를 못 받기
        때문이다 — 8/13 에 커스텀 모델을 팀 단위로 붙인 것과 같은 이유다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE agent SET model = %s
                    WHERE agent_id = (
                        SELECT a.agent_id FROM agent AS a
                        JOIN agent_tool AS t ON t.agent_id = a.agent_id
                        WHERE a.team_id = %s AND t.tool_ref = %s AND a.status = 'ACTIVE'
                        LIMIT 1
                    )
                    RETURNING agent_id, name, model
                    """,
                    (model, team_id, AgentRepository.PLATFORM_TOOL),
                )
                row = cursor.fetchone()
                if row is None:
                    raise RecordNotFound("이 팀에는 아직 기본 에이전트가 없습니다.")
                return row

    @staticmethod
    def set_main_model(*, account_id: str, model: str) -> dict[str, Any]:
        """메인 모델을 바꾼다.

        **`update` 를 쓰지 않고 따로 둔다.** 정문은 `is_prebuilt` 라 그쪽 경로는
        `_writable_agent` 가 막는다 — 그 가드는 옳다(시드가 정의를 소유하므로
        화면에서 고친 이름·도구는 다음 시드에 사라진다). 다만 **모델만은 팀이
        정하는 값**이라, 그 한 칸만 여는 자리를 따로 만든다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team(cursor, account_id)
                cursor.execute(
                    """
                    UPDATE agent SET model = %s
                    WHERE agent_id = (
                        SELECT a.agent_id FROM agent AS a
                        JOIN agent_tool AS t ON t.agent_id = a.agent_id
                        WHERE a.team_id = %s AND t.tool_ref = %s AND a.status = 'ACTIVE'
                        LIMIT 1
                    )
                    RETURNING agent_id, name, model
                    """,
                    (model, team_id, AgentRepository.PLATFORM_TOOL),
                )
                row = cursor.fetchone()
                if row is None:
                    raise RecordNotFound("이 팀에는 아직 기본 에이전트가 없습니다.")
                return row


class AgentVersionRepository:
    """`agents`·`agent_versions`·`agent_version_tools` 조회 전용.

    ⚠ **새 버전 스키마 전용이다.** 지금 살아있는 실행 경로(`services/harness/`,
    `apps/chat`, `apps/agents`)가 쓰는 비버전 `agent`/`agent_tool`은 위
    `AgentRepository`/`AgentCrudRepository`가 그대로 맡는다. 이 클래스는
    `services/agent_runtime/`(신규, 미완성) 전용이고 아직 아무 경로도 이 클래스를
    부르지 않는다 — 테이블 배경은 DB/migrations/2026-08-13_agent_versioning.sql
    상단 주석 참고.

    계약: docs/작업기록/Deep_Agents/2026-08-13_02_Deep-Agent_런타임_공통_계약_v1.md
    §6.1. **이 클래스는 `backend.db.errors`(`RecordNotFound`/`PermissionDenied`)만
    던진다** — `services.agent_runtime.exceptions`의
    `AgentDefinitionNotFound`/`AgentVersionNotFound`로의 번역은 Loader
    (services/agent_runtime/loader.py)의 몫이다. 이 모듈 docstring이 말하는
    "Harness는 psycopg에 직접 붙지 않는다"는 경계를 agent_runtime에도 그대로
    적용한다 — services/ 쪽 코드가 backend.db.errors를 직접 잡지 않게 한다.
    """

    @staticmethod
    def get_definition(
        *, agent_id: str, agent_version_id: str, account_id: str, team_id: str
    ) -> dict[str, Any]:
        """특정 불변 버전의 에이전트 정의를 반환한다(02 §6.1).

        `account_id`는 지금 안 쓴다 — v1은 `agents.visibility`가 항상 'TEAM'
        고정이라(마이그레이션 주석 참고) 개인 단위 권한 분기가 없다. 시그니처에는
        남겨 둔다 — 나중에 PRIVATE 가시성이 생기면 이 함수 안에서만 바꾸면 되게.

        반환 딕셔너리는 `AgentDefinition`(services/agent_runtime/definitions.py)의
        필드와 1:1로 맞춘다 — Loader가 그대로 옮겨 담을 수 있게.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT v.agent_version_id, v.agent_id, v.system_prompt,
                           v.model, v.reasoning_effort, v.max_iterations,
                           a.team_id, a.name, a.description, a.status AS agent_status
                    FROM agent_versions AS v
                    JOIN agents AS a ON a.agent_id = v.agent_id
                    WHERE v.agent_version_id = %s AND v.agent_id = %s
                    """,
                    (agent_version_id, agent_id),
                )
                row = cursor.fetchone()
                if row is None:
                    raise RecordNotFound(
                        f"존재하지 않는 에이전트 버전입니다: {agent_id}/{agent_version_id}"
                    )
                if row["team_id"] != team_id:
                    raise PermissionDenied("이 에이전트 버전에 접근할 수 없습니다.")

                cursor.execute(
                    "SELECT tool_ref FROM agent_version_tools "
                    "WHERE agent_version_id = %s ORDER BY tool_ref",
                    (agent_version_id,),
                )
                tool_refs = [r["tool_ref"] for r in cursor.fetchall()]

        return {
            "agent_id": row["agent_id"],
            "agent_version_id": row["agent_version_id"],
            "name": row["name"],
            "description": row["description"],
            "system_prompt": row["system_prompt"],
            "model": row["model"],
            "reasoning_effort": row["reasoning_effort"],
            "max_iterations": row["max_iterations"],
            "tool_refs": tool_refs,
            # Loader가 "지금도 활성인가"를 다시 물을 때 쓴다(02 §5.6 — 버전은
            # 불변이어도 비활성화는 런타임 차단 수단으로 인정한다). 여기서는
            # 막지 않고 그대로 돌려준다 — 막을지 말지는 Loader/Executor의 판단이다.
            "agent_status": row["agent_status"],
        }

    @staticmethod
    def resolve_live_version_id(*, agent_id: str) -> str | None:
        """기본 챗 에이전트면 **지금** 발행된 최신 버전을, 아니면 `None`을 돌려준다.

        "+" 도구 토글(2026-08-18, ChatPage의 도구·MCP 붙이기)이 그 자리에서
        새 버전을 발행하는데, 이미 열려 있는 대화(`chat_session`)는 만들 때
        고정한 옛 `agent_version_id`를 계속 쓴다 — 다른 에이전트는 이게
        맞다(버전 불변성이 실행 재현성을 지킨다, 02 §5.2). 하지만 기본 챗은
        빌더 화면도 없이 채팅 안에서만 관리되는 팀 공용 도구모음 성격이라
        "방금 켠 도구가 지금 이 대화에도 바로 먹혀야 한다"가 자연스럽다 —
        그래서 이 한 에이전트만 실행 시점마다 최신 버전을 다시 찾는 예외를
        둔다. 호출부(`apps/chat/api_views.py`)는 `None`이면 세션에 이미
        고정된 버전을 그대로 쓴다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT current_version_id FROM agents "
                    "WHERE agent_id = %s AND is_default_chat = true",
                    (agent_id,),
                )
                row = cursor.fetchone()
                return row["current_version_id"] if row else None


class AgentSubagentRepository:
    """`agent_version_subagents` 조회 전용. 계약: 02 §6.1."""

    @staticmethod
    def list_for_parent_version(
        *, parent_version_id: str, account_id: str, team_id: str
    ) -> list[dict[str, Any]]:
        """부모 버전의 자식 관계와 현재 접근 정보를 반환한다.

        **비활성·권한 없는 자식도 목록에서 빼지 않는다**(02 §6.1) — `is_active`,
        `can_execute`로 표시해서 그대로 돌려준다. 여기서 지워 버리면
        `subagents/validation.py`가 "왜 안 되는지" 정확한 사유를 못 만든다.

        `has_subagents`는 그 자식 버전 자신이 다시 부모 노릇을 하는지(즉 더
        아래 자식을 두는지)를 본다 — MVP는 1단계 위임까지만 허용하므로
        (`DelegationDepthError`), 이 값이 True인 자식을 선택하면 검증에서
        걸린다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT s.child_agent_id, s.child_version_id, s.alias,
                           s.delegation_description,
                           a.team_id AS child_team_id, a.status AS child_status,
                           EXISTS (
                               SELECT 1 FROM agent_version_subagents AS g
                               WHERE g.parent_version_id = s.child_version_id
                           ) AS has_subagents
                    FROM agent_version_subagents AS s
                    JOIN agents AS a ON a.agent_id = s.child_agent_id
                    WHERE s.parent_version_id = %s
                    ORDER BY s.alias
                    """,
                    (parent_version_id,),
                )
                rows = cursor.fetchall()

        return [
            {
                "child_agent_id": row["child_agent_id"],
                "child_version_id": row["child_version_id"],
                "alias": row["alias"],
                "delegation_description": row["delegation_description"],
                # v1: visibility가 항상 'TEAM' 고정이라(마이그레이션 주석 참고)
                # 팀 소속 일치만 본다. PRIVATE가 생기면 여기만 바꾼다.
                "is_active": row["child_status"] == "ACTIVE",
                "can_execute": row["child_team_id"] == team_id,
                "has_subagents": row["has_subagents"],
            }
            for row in rows
        ]


def _writable_agent_version(
    cursor, *, agent_id: str, team_id: str, account_id: str, enforce_draft_privacy: bool = True
) -> None:
    """조회·수정(=새 버전 발행)해도 되는 논리적 에이전트인가.

    `_writable_agent`(비버전 `agent` 테이블용)와 같은 목적, 새 `agents` 테이블용.
    지금은 `is_prebuilt` 가드를 안 둔다 — 새 스키마용 시드 데이터가 아직 없어서
    (2026-08-13 시점) 막을 대상이 없다. 시드가 생기면 여기도 같이 막을 것.

    **DRAFT는 만든 사람만 접근한다**(2026-08-18, "개인/팀 공유" 분리 결정).
    `list_for_team()`이 목록에서 남의 DRAFT를 빼는 것과 같은 규칙을 여기서도
    지킨다 — 안 그러면 목록엔 안 보여도 URL을 직접 알면(agent_id를 추측하거나
    옛 링크로) 조회·수정이 그대로 통과해 "개인"이라는 말이 무색해진다.
    ACTIVE·DISABLED는 한 번이라도 팀에 공유된 것이라 이 제한이 없다.

    `delete()`는 `enforce_draft_privacy=False`로 부른다 — "만든 사람이거나
    팀장이면 지울 수 있다"(`require_owner_or_leader`, 뷰 레이어)가 이미 그
    자리에서 더 정확한 권한을 확인했다. 여기서 또 DRAFT를 막으면 팀장이 남의
    DRAFT를 못 지우게 돼서 그 규칙과 충돌한다 — 삭제는 내용을 보여주지도,
    바꾸지도 않는 관리 동작이라 조회·수정과 같은 잣대를 안 쓴다.
    """

    cursor.execute(
        "SELECT team_id, status, owner_account_id FROM agents WHERE agent_id = %s", (agent_id,)
    )
    row = cursor.fetchone()
    if row is None:
        raise RecordNotFound(f"존재하지 않는 에이전트입니다: {agent_id}")
    if row["team_id"] != team_id:
        raise PermissionDenied("이 에이전트에 접근할 수 없습니다.")
    if (
        enforce_draft_privacy
        and row["status"] == "DRAFT"
        and row["owner_account_id"] != account_id
    ):
        raise PermissionDenied("이 에이전트에 접근할 수 없습니다.")


def _build_subagent_refs(
    cursor, *, team_id: str, account_id: str, subagents: list[dict[str, Any]]
) -> tuple[SubagentReference, ...]:
    """요청으로 들어온 서브 에이전트 후보를 `validate_subagents()`가 받는
    `SubagentReference`로 바꾼다.

    `child_version_id`가 실제로 `child_agent_id`의 버전인지부터 여기서 확인한다
    — 없는 조합을 넘기면 그건 구조 검증(alias 중복·순환 등)이 아니라 데이터
    정합성 문제라 `validate_subagents()`가 아니라 여기서 걸러야 한다.

    **`is_active`는 "ACTIVE 상태"가 아니라 "서브 에이전트로 참조해도 되는가"다**
    (2026-08-18 완화, 지훈 확인) — ACTIVE는 항상 되고, **본인 소유의 DRAFT도**
    이제 된다. 개인 에이전트를 만들면서 아직 활성화 안 한 다른 개인 에이전트를
    서브 에이전트로 미리 붙여 두고, 나중에 부모를 활성화하면 그 자리에서 같이
    활성화되게 하려는 것(`_cascade_activate_draft_subagents`, `api_views.py`)이라
    "내가 만든 DRAFT"까지만 허용한다 — 남의 DRAFT는 여전히 막는다(그 사람이
    활성화하기 전까지 내 부모가 그걸 실행에 못 쓰는 게 맞다).
    """

    refs: list[SubagentReference] = []
    for item in subagents:
        cursor.execute(
            """
            SELECT a.status, a.team_id, a.owner_account_id,
                   EXISTS (
                       SELECT 1 FROM agent_version_subagents AS g
                       WHERE g.parent_version_id = v.agent_version_id
                   ) AS has_subagents
            FROM agent_versions AS v
            JOIN agents AS a ON a.agent_id = v.agent_id
            WHERE v.agent_version_id = %s AND v.agent_id = %s
            """,
            (item["child_version_id"], item["child_agent_id"]),
        )
        row = cursor.fetchone()
        if row is None:
            raise RecordNotFound(
                "존재하지 않는 서브 에이전트 버전입니다: "
                f"{item['child_agent_id']}/{item['child_version_id']}"
            )
        is_own_draft = row["status"] == "DRAFT" and row["owner_account_id"] == account_id
        refs.append(
            SubagentReference(
                child_agent_id=item["child_agent_id"],
                child_version_id=item["child_version_id"],
                alias=item["alias"],
                delegation_description=item["delegation_description"],
                # v1: visibility가 항상 'TEAM' 고정(마이그레이션 주석 참고) —
                # AgentSubagentRepository.list_for_parent_version과 같은 계산.
                is_active=row["status"] == "ACTIVE" or is_own_draft,
                can_execute=row["team_id"] == team_id,
                has_subagents=row["has_subagents"],
            )
        )
    return tuple(refs)


def _team_dependency_graph(cursor, *, team_id: str) -> dict[str, set[str]]:
    """이 팀에서 **지금 발행 중인**(`agents.current_version_id`) 관계만으로 그래프를
    만든다. `validate_no_cycle`이 이 그래프로 순환을 판단한다.

    지나간 옛 버전의 관계까지 넣으면, 이미 안 쓰는 연결 때문에 순환이 아닌
    구성이 순환으로 잘못 걸린다 — "지금 실제로 살아있는 연결"만 봐야 한다.
    """

    cursor.execute(
        """
        SELECT a.agent_id, s.child_agent_id
        FROM agents AS a
        JOIN agent_version_subagents AS s ON s.parent_version_id = a.current_version_id
        WHERE a.team_id = %s
        """,
        (team_id,),
    )
    graph: dict[str, set[str]] = {}
    for row in cursor.fetchall():
        graph.setdefault(row["agent_id"], set()).add(row["child_agent_id"])
    return graph


def provision_default_chat_agent(cursor, *, team_id: str, owner_account_id: str) -> str:
    """팀에 "기본 챗 에이전트"(tool·MCP만, 서브에이전트 없음) 하나를 만들고
    바로 ACTIVE로 발행한다(2026-08-15, Chat 재설계 — 지훈 확인).

    Chat 화면 드롭다운은 이 에이전트를 포함해 팀의 활성 에이전트 목록을
    보여주고, 사용자가 아무것도 안 고르면 여기로 떨어진다. `is_default_chat`
    은 팀당 최대 1개만 true(`agents_one_default_chat_per_team` 부분 유니크
    인덱스, DB/migrations/2026-08-15_agent_default_chat.sql) — 이 함수를
    같은 팀에 두 번 부르면 그 인덱스가 막는다.

    **호출자가 트랜잭션을 쥔다.** 다른 Repository 메서드와 달리 이 함수는
    자체 `database_connection()`을 열지 않고 넘겨받은 커서를 그대로 쓴다 —
    `TeamRepository.create()`가 이미 연 트랜잭션에 얹혀서, 기본 챗 에이전트
    없이 팀만 만들어지는 반쪽 상태가 생기지 않게 한다(실패하면 팀 생성 전체가
    롤백된다).

    model을 명시적으로 채워 넣는다 — `agent_versions.model`이 NULL이면
    `services/agent_runtime/loader.py`가 그대로 `AgentDefinition.model`에
    실어 보내고, `models/factory.py`의 `resolve(model: str, ...)`가 이를
    필수 인자로 받아 NULL에서 그대로 깨진다(legacy_bridge.py처럼 새 엔진
    호출 전에 기본값으로 떨어뜨려 주는 경로가 없다 — 순수 새 스키마 실행엔
    그런 안전망이 아직 없다는 뜻이라 task #17/#18에 별도로 남겨 둠). 여기서는
    같은 상황을 만들지 않으려고 `services.harness.runner`의 실제 기본값을
    그대로 재사용한다.
    """
    # 지연 import — services.harness의 무거운 의존성 사슬을 이 모듈이 항상
    # 끌고 들어오지 않게 한다(legacy_bridge.py의 draft_from_legacy_agent와
    # 같은 이유).
    from services.harness.runner import DEFAULT_EFFORT, DEFAULT_MODEL

    agent_id = _next_agents_id(cursor)
    cursor.execute(
        """
        INSERT INTO agents
            (agent_id, team_id, name, description, owner_account_id,
             status, is_default_chat)
        VALUES (%s, %s, %s, %s, %s, 'ACTIVE', true)
        """,
        (
            agent_id,
            team_id,
            "기본 챗",
            "Chat 화면의 기본 상대입니다. 도구·MCP만 붙일 수 있고 다른 에이전트로 위임하지 않습니다.",
            owner_account_id,
        ),
    )

    agent_version_id = next_short_code(
        cursor, table="agent_versions", column="agent_version_id", prefix="AV"
    )
    cursor.execute(
        """
        INSERT INTO agent_versions
            (agent_version_id, agent_id, version, system_prompt, model,
             reasoning_effort, created_by)
        VALUES (%s, %s, 1, %s, %s, %s, %s)
        """,
        (
            agent_version_id,
            agent_id,
            "당신은 팀의 업무를 돕는 기본 어시스턴트입니다. 연결된 도구가 있으면 활용해서 "
            "정확한 정보를 근거로 답하세요.",
            DEFAULT_MODEL,
            DEFAULT_EFFORT,
            owner_account_id,
        ),
    )

    cursor.execute(
        "UPDATE agents SET current_version_id = %s WHERE agent_id = %s",
        (agent_version_id, agent_id),
    )

    return agent_id


class AgentVersionCrudRepository:
    """Builder가 쓰는 새 버전 스키마 CRUD — "저장" 은 곧 "발행" 이다.

    조회 전용인 `AgentVersionRepository`와 나눠 둔 이유는 `AgentRepository`/
    `AgentCrudRepository`가 나뉜 이유와 같다 — 그쪽은 실행 경로(Loader)가 부르는
    read-only 계약이고, 여기는 사람이 저장·발행을 요청하는 쓰기 경로다.

    **`agent_versions`는 불변이라(02 §5.2) "임시 저장 후 나중에 발행"이라는
    중간 상태가 없다.** 발행 버튼을 누르는 순간 바로 새 불변 버전을 만든다.
    저장 없이 먼저 시도해 보고 싶으면 `services/agent_runtime/loader.py`의
    `from_draft()`(발행 안 함, DB에 안 남음)를 쓰는 별도 "테스트 실행" 경로를
    쓴다 — 옛 시스템의 `AgentBuilderTestRunAPIView`와 같은 자리.

    구조 검증은 **저장·발행 API와 런타임 Factory가 같은 `validate_subagents()`를
    쓴다**(02 §7.1) — 여기서 자체적으로 자기 참조·중복·순환을 다시 구현하지 않는다.
    """

    @staticmethod
    def list_for_team(account_id: str) -> list[dict[str, Any]]:
        """팀 안에서 이 계정이 볼 수 있는 에이전트.

        **DRAFT는 만든 사람에게만 보인다.** ACTIVE·DISABLED는 한 번이라도
        팀에 공유된 적이 있다는 뜻이라 팀 전체가 계속 본다(2026-08-18,
        "개인/팀 공유" 화면 분리 결정) — 화면(`AgentVersionListPage`)의 "개인"
        탭은 이 조건 덕분에 실제로 본인 것만 모인다. `owner_account_id`가
        NULL인 행(시드 등)은 아무도의 소유가 아니므로 이 조건에서 항상
        제외된다 — 필요해지면 그때 다룬다.

        `is_favorite`는 **이 계정 기준**이다(2026-08-18, `agent_favorites`) —
        같은 에이전트라도 계정마다 다른 값일 수 있다. 팀 전체가 보는 값이
        아니라서 `agents`에는 안 두고 별도 표에서 EXISTS로 붙인다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team(cursor, account_id)
                cursor.execute(
                    """
                    SELECT a.agent_id, a.name, a.description, a.status, a.is_prebuilt,
                           a.is_default_chat, a.current_version_id, a.updated_at,
                           a.owner_account_id,
                           v.version, v.model, v.reasoning_effort, v.max_iterations,
                           COALESCE(
                               (SELECT json_agg(child.name ORDER BY child.name)
                                FROM agent_version_subagents AS s
                                JOIN agents AS child ON child.agent_id = s.child_agent_id
                                WHERE s.parent_version_id = a.current_version_id),
                               '[]'::json
                           ) AS subagent_names,
                           EXISTS (
                               SELECT 1 FROM agent_favorites AS f
                               WHERE f.account_id = %s AND f.agent_id = a.agent_id
                           ) AS is_favorite
                    FROM agents AS a
                    LEFT JOIN agent_versions AS v ON v.agent_version_id = a.current_version_id
                    WHERE a.team_id = %s AND a.status <> 'ARCHIVED'
                      AND (a.status <> 'DRAFT' OR a.owner_account_id = %s)
                    ORDER BY a.is_default_chat DESC, a.is_prebuilt DESC, a.name
                    """,
                    (account_id, team_id, account_id),
                )
                return list(cursor.fetchall())

    @staticmethod
    def get(*, agent_id: str, account_id: str) -> dict[str, Any]:
        """편집 화면 프리필용. 아직 한 번도 발행 안 한 논리적 에이전트도 조회는
        된다 — 그때는 버전 관련 필드가 빈 기본값으로 채워진다."""

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team(cursor, account_id)
                _writable_agent_version(cursor, agent_id=agent_id, team_id=team_id, account_id=account_id)

                cursor.execute(
                    """
                    SELECT agent_id, name, description, status, current_version_id,
                           owner_account_id, is_default_chat,
                           EXISTS (
                               SELECT 1 FROM agent_favorites AS f
                               WHERE f.account_id = %s AND f.agent_id = agents.agent_id
                           ) AS is_favorite
                    FROM agents WHERE agent_id = %s
                    """,
                    (account_id, agent_id),
                )
                agent = cursor.fetchone()

                if agent["current_version_id"] is None:
                    return {
                        **agent,
                        "version": None,
                        "system_prompt": "",
                        "model": None,
                        "reasoning_effort": None,
                        "max_iterations": 6,
                        "tool_refs": [],
                        "subagents": [],
                    }

                cursor.execute(
                    """
                    SELECT version, system_prompt, model, reasoning_effort, max_iterations
                    FROM agent_versions WHERE agent_version_id = %s
                    """,
                    (agent["current_version_id"],),
                )
                version_row = cursor.fetchone()

                cursor.execute(
                    "SELECT tool_ref FROM agent_version_tools "
                    "WHERE agent_version_id = %s ORDER BY tool_ref",
                    (agent["current_version_id"],),
                )
                tool_refs = [r["tool_ref"] for r in cursor.fetchall()]

                cursor.execute(
                    """
                    SELECT child_agent_id, child_version_id, alias, delegation_description
                    FROM agent_version_subagents
                    WHERE parent_version_id = %s ORDER BY alias
                    """,
                    (agent["current_version_id"],),
                )
                subagents = list(cursor.fetchall())

        return {**agent, **version_row, "tool_refs": tool_refs, "subagents": subagents}

    @staticmethod
    def publish(
        *,
        agent_id: str | None,
        account_id: str,
        fields: dict[str, Any],
        tool_refs: list[str],
        subagents: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """새 불변 버전을 발행한다. `agent_id`가 없으면 논리적 에이전트도 함께 만든다.

        **여기서 실패하면 아무것도 안 남는다** — 논리적 에이전트 생성이든 검증
        이든 버전 INSERT든, 전부 한 트랜잭션 안에서 일어난다(`database_connection`
        컨텍스트가 예외 시 롤백한다).
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team(cursor, account_id)

                if agent_id is None:
                    agent_id = _next_agents_id(cursor)
                    cursor.execute(
                        """
                        INSERT INTO agents (agent_id, team_id, name, description, owner_account_id)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (agent_id, team_id, fields["name"], fields["description"], account_id),
                    )
                else:
                    _writable_agent_version(cursor, agent_id=agent_id, team_id=team_id, account_id=account_id)
                    cursor.execute(
                        "UPDATE agents SET name = %s, description = %s, updated_at = now() "
                        "WHERE agent_id = %s",
                        (fields["name"], fields["description"], agent_id),
                    )

                # 구조 검증 — API와 Factory(services/agent_runtime/factory.py)가
                # 같은 함수를 쓴다(02 §7.1). MVP는 1단계 위임만 허용하므로, 고른
                # 자식이 이미 자기 자식을 갖고 있으면(has_subagents=True) 여기서
                # 막는다 — `validate_subagents()`가 이 검사를 항상 켜 둔다.
                child_refs = _build_subagent_refs(
                    cursor, team_id=team_id, account_id=account_id, subagents=subagents
                )
                dependency_graph = _team_dependency_graph(cursor, team_id=team_id)
                validate_subagents(
                    parent_agent_id=agent_id,
                    child_refs=child_refs,
                    dependency_graph=dependency_graph,
                )

                cursor.execute(
                    "SELECT count(*) AS n FROM agent_versions WHERE agent_id = %s", (agent_id,)
                )
                version = cursor.fetchone()["n"] + 1
                agent_version_id = next_short_code(
                    cursor, table="agent_versions", column="agent_version_id", prefix="AV"
                )

                cursor.execute(
                    """
                    INSERT INTO agent_versions
                        (agent_version_id, agent_id, version, system_prompt, model,
                         reasoning_effort, max_iterations, created_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        agent_version_id,
                        agent_id,
                        version,
                        fields["system_prompt"],
                        fields.get("model"),
                        fields.get("reasoning_effort"),
                        fields.get("max_iterations", 6),
                        account_id,
                    ),
                )

                for tool_ref in dict.fromkeys(tool_refs):
                    cursor.execute(
                        "INSERT INTO agent_version_tools (agent_version_id, tool_ref) "
                        "VALUES (%s, %s)",
                        (agent_version_id, tool_ref),
                    )

                for sub in subagents:
                    cursor.execute(
                        """
                        INSERT INTO agent_version_subagents
                            (parent_version_id, child_agent_id, child_version_id,
                             alias, delegation_description)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (
                            agent_version_id,
                            sub["child_agent_id"],
                            sub["child_version_id"],
                            sub["alias"],
                            sub["delegation_description"],
                        ),
                    )

                # 새로 발행한 버전을 "지금 도는 버전"으로 옮긴다. 옛 버전 행은
                # 손대지 않는다 — 이미 그 버전을 고정 참조하는 세션·부모가 있을 수
                # 있어서다(02 §5.4·§5.5).
                cursor.execute(
                    "UPDATE agents SET current_version_id = %s, updated_at = now() "
                    "WHERE agent_id = %s",
                    (agent_version_id, agent_id),
                )

        return AgentVersionCrudRepository.get(agent_id=agent_id, account_id=account_id)

    @staticmethod
    def set_status(*, agent_id: str, account_id: str, status: str) -> dict[str, Any]:
        """DRAFT/ACTIVE/DISABLED 사이 전이. `AgentCrudRepository.set_status`와 같은
        얇은 쓰기 레이어 — 어떤 전이가 허용되는지는 API 뷰가 정한다.

        **`is_default_chat=true`인 행은 ACTIVE 밖으로 못 뺀다.** `AgentVersionDisableAPIView`
        docstring은 "끄는 쪽은 항상 안전하다"고 전제하는데, 팀의 기본 챗
        에이전트에는 그 전제가 깨진다 — 꺼지면 Chat 랜딩(`/chat`)이 대화
        상대 없이 빈 화면이 된다(2026-08-15, Chat 재설계 — provision_default_chat_agent
        참고). 삭제 API는 아직 없어 여기서만 막으면 된다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team(cursor, account_id)
                _writable_agent_version(cursor, agent_id=agent_id, team_id=team_id, account_id=account_id)

                if status != "ACTIVE":
                    cursor.execute(
                        "SELECT is_default_chat FROM agents WHERE agent_id = %s", (agent_id,)
                    )
                    if cursor.fetchone()["is_default_chat"]:
                        raise RepositoryError("기본 챗 에이전트는 비활성화할 수 없습니다.")

                cursor.execute(
                    "UPDATE agents SET status = %s, updated_at = now() WHERE agent_id = %s",
                    (status, agent_id),
                )
        return AgentVersionCrudRepository.get(agent_id=agent_id, account_id=account_id)

    @staticmethod
    def set_favorite(*, agent_id: str, account_id: str, favorite: bool) -> dict[str, Any]:
        """즐겨찾기 별 토글(2026-08-18). **계정별 개인 설정이라 팀 전체에 안
        보인다** — `agents`가 아니라 `agent_favorites`(계정, 에이전트) 표에
        따로 둔다. `_writable_agent_version()`을 그대로 쓴다 — 이 계정이
        `list_for_team()`에서 애초에 못 보는 에이전트(남의 DRAFT)는 즐겨찾기도
        못 한다. `enforce_draft_privacy` 관리 동작이 아니라(활성화·중지·삭제와
        달리 소유자·팀장만 하는 게 아니다) 팀 안의 누구든 자기 시야에 있는
        에이전트는 즐겨찾기할 수 있다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team(cursor, account_id)
                _writable_agent_version(cursor, agent_id=agent_id, team_id=team_id, account_id=account_id)

                if favorite:
                    cursor.execute(
                        """
                        INSERT INTO agent_favorites (account_id, agent_id) VALUES (%s, %s)
                        ON CONFLICT (account_id, agent_id) DO NOTHING
                        """,
                        (account_id, agent_id),
                    )
                else:
                    cursor.execute(
                        "DELETE FROM agent_favorites WHERE account_id = %s AND agent_id = %s",
                        (account_id, agent_id),
                    )
        return AgentVersionCrudRepository.get(agent_id=agent_id, account_id=account_id)

    @staticmethod
    def list_dependent_draft_children(*, agent_id: str) -> list[dict[str, Any]]:
        """이 에이전트의 **지금 버전**이 서브 에이전트로 참조하는 것 중 아직
        DRAFT인 것들(2026-08-18, 활성화 연쇄용). 부모를 활성화(또는 이미
        활성 상태에서 재발행)할 때 `apps/agents/api_views.py`의
        `_cascade_activate_draft_subagents()`가 이 목록을 모델·도구
        재검증(활성화와 같은 검증)에 돌려 통과한 것만 활성화한다 —
        그래서 활성화 재검증에 필요한 `model`·`tool_refs`까지 같이 준다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT DISTINCT child.agent_id, child.name, cv.model,
                           COALESCE(
                               (SELECT array_agg(t.tool_ref) FROM agent_version_tools AS t
                                WHERE t.agent_version_id = child.current_version_id),
                               ARRAY[]::text[]
                           ) AS tool_refs
                    FROM agents AS parent
                    JOIN agent_version_subagents AS s
                        ON s.parent_version_id = parent.current_version_id
                    JOIN agents AS child ON child.agent_id = s.child_agent_id
                    LEFT JOIN agent_versions AS cv ON cv.agent_version_id = child.current_version_id
                    WHERE parent.agent_id = %s AND child.status = 'DRAFT'
                    """,
                    (agent_id,),
                )
                return list(cursor.fetchall())

    @staticmethod
    def activate_cascaded_child(*, agent_id: str) -> None:
        """활성화 연쇄로 서브 에이전트를 켠다(2026-08-18). 부모 소유자와
        이 자식 소유자가 다를 수 있어(팀장이 남의 부모를 활성화하는 경우)
        `set_status()`처럼 요청 계정 기준 소유자 확인을 안 한다 — 이미
        `list_dependent_draft_children()`가 "지금 활성화되는 부모의 버전이
        실제로 참조하는 자식"만 골라 왔으므로 그 자체가 권한 근거다(그
        참조 자체는 그 자식의 소유자만 만들 수 있었다, `_build_subagent_refs`
        참고). `status = 'DRAFT'` 조건으로 그 사이 이미 바뀐 행은 조용히
        건너뛴다(경합 대비)."""

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE agents SET status = 'ACTIVE', updated_at = now() "
                    "WHERE agent_id = %s AND status = 'DRAFT'",
                    (agent_id,),
                )

    @staticmethod
    def list_dependents(*, agent_id: str, account_id: str) -> list[str]:
        """이 에이전트를 서브 에이전트로 참조하는, 살아있는(ARCHIVED 아닌)
        다른 에이전트의 이름 목록. 삭제 버튼을 누른 시점에 화면이 먼저
        물어봐서, 막힐 걸 미리 알려주는 데 쓴다 — `delete()`도 같은 조회를
        한 번 더 해서 그 사이 생긴 새 참조까지 막는다(경합 대비, 여기 결과를
        그대로 믿고 삭제를 진행하지 않는다).

        버전은 몇 개든 지날 수 있으니 parent_version_id가 아니라 그 버전이
        속한 논리적 에이전트(agents) 단위로 묶는다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team(cursor, account_id)
                _writable_agent_version(cursor, agent_id=agent_id, team_id=team_id, account_id=account_id)
                return AgentVersionCrudRepository._dependent_parent_names(cursor, agent_id=agent_id)

    @staticmethod
    def _dependent_parent_names(cursor, *, agent_id: str) -> list[str]:
        cursor.execute(
            """
            SELECT DISTINCT pa.name
            FROM agent_version_subagents AS s
            JOIN agent_versions AS pv ON pv.agent_version_id = s.parent_version_id
            JOIN agents AS pa ON pa.agent_id = pv.agent_id
            WHERE s.child_agent_id = %s AND pa.status <> 'ARCHIVED'
            ORDER BY pa.name
            """,
            (agent_id,),
        )
        return [row["name"] for row in cursor.fetchall()]

    @staticmethod
    def delete(*, agent_id: str, account_id: str) -> None:
        """ARCHIVED로 내린다. `AgentCrudRepository.delete`와 같은 이유로 행은
        지우지 않는다 — `agent_run`·`chat_session`이 이 버전들을 가리키고
        있어서, 지우면 그 실행이 어느 에이전트였는지 잃는다.

        소유자·팀장 권한 검사는 뷰(`AgentVersionDetailAPIView.delete`)가
        한다 — 여기는 `set_status`와 같은 얇은 쓰기 레이어다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team(cursor, account_id)
                _writable_agent_version(
                    cursor,
                    agent_id=agent_id,
                    team_id=team_id,
                    account_id=account_id,
                    enforce_draft_privacy=False,
                )

                cursor.execute(
                    "SELECT is_default_chat FROM agents WHERE agent_id = %s", (agent_id,)
                )
                if cursor.fetchone()["is_default_chat"]:
                    raise RepositoryError("기본 챗 에이전트는 지울 수 없습니다.")

                # 다른(살아있는) 에이전트가 이 에이전트를 서브 에이전트로 참조하면
                # 막는다 — 그대로 지우면 그 부모는 다음 실행에서 InactiveSubagentError로
                # 통째로 실패한다(services/agent_runtime/subagents/validation.py).
                parent_names = AgentVersionCrudRepository._dependent_parent_names(
                    cursor, agent_id=agent_id
                )
                if parent_names:
                    raise RepositoryError(
                        "다른 에이전트가 서브 에이전트로 쓰고 있어 지울 수 없습니다: "
                        + ", ".join(parent_names)
                    )

                cursor.execute(
                    "UPDATE agents SET status = 'ARCHIVED', updated_at = now() WHERE agent_id = %s",
                    (agent_id,),
                )


def _decrypt_or_none(ciphertext: str | None) -> dict[str, Any] | None:
    """복호화한 payload. **못 읽으면 예외 대신 `None`.**

    `decrypt_credential` 은 `OAuthError` 를 던지는데 그건 `RepositoryError` 도
    `psycopg.Error` 도 아니다. 목록을 만드는 도중에 터지면 뷰의 except 를 지나쳐
    처리되지 않은 500 이 되고, 쓰기 뒤에 목록을 다시 만드는 자리에서 터지면
    **이미 성공한 쓰기가 실패로 보고된다**(2026-08-13 검토).
    """

    if not ciphertext:
        return {}
    try:
        return decrypt_credential(ciphertext)
    except OAuthError:
        return None


class CustomModelRepository:
    """팀이 직접 등록한 **커스텀 모델 API**. 여러 개를 목록으로 관리한다.

    기본은 우리가 제공하는 모델이다 — 타깃이 비개발자라 「키를 발급받아
    넣으세요」를 첫 화면에 둘 수 없다. 다만 자기 계약으로만 데이터를 흘려야 하는
    팀, 사용량이 우리 플랜을 넘는 팀, 사내 vLLM 을 쓰는 팀이 있다. 그런 곳을
    **필요한 만큼 여러 개** 붙일 수 있게 한다(2026-08-12 PM 결정).

    `connector_conn` 을 그대로 쓴다. 스키마를 바꾸면 팀원 전원이 ALTER 를 돌려야
    하는데, 이 테이블이 이미 「팀의 암호화된 자격증명」이라 새 칸을 만들 이유가
    없다. **Connector 탭에는 보이지 않는다** — 그 탭은 「데이터를 가져오는 자리」
    이고 이건 데이터가 아니라 모델을 부르는 열쇠다.
    """

    TYPE = "MODEL_API"

    @staticmethod
    def _rows(cursor, team_id: str) -> list[dict[str, Any]]:
        cursor.execute(
            """
            SELECT c.conn_id, c.connected_at, c.encrypted_credential_ref
            FROM connector_conn AS c
            -- **팀은 `user_account.team_id` 로 잇는다.** `team_member` 에는
            -- account_id 가 없다 — 거기는 person_id 로 사람을 묶는 표다
            -- (2026-08-12: 그 컬럼이 있다고 가정해 조인했다가 503 이 났다).
            JOIN user_account AS u ON u.account_id = c.account_id
            WHERE c.connector_type = %s AND u.team_id = %s
            ORDER BY c.connected_at
            """,
            (CustomModelRepository.TYPE, team_id),
        )
        rows = []
        for row in cursor.fetchall():
            payload = _decrypt_or_none(row["encrypted_credential_ref"])
            # **못 읽는 행 하나가 목록 전체를 죽이지 않는다.** 키가 바뀌었거나
            # 암호문이 깨지면 `decrypt_credential` 이 `OAuthError` 를 던지는데,
            # 그건 `RepositoryError` 도 `psycopg.Error` 도 아니라 뷰의 except 를
            # 그냥 지나쳐 500 이 된다(2026-08-13). 팀 쪽에서는 어차피 못 쓰는
            # 행이므로 건너뛴다 — 치우는 것은 운영자 콘솔의 일이다.
            if payload is None:
                continue
            rows.append({**row, "payload": payload})
        return rows

    @staticmethod
    def list_for_account(account_id: str) -> list[dict[str, Any]]:
        """등록한 것들. **키는 절대 나가지 않는다** — 이름·주소·모델만."""

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team(cursor, account_id)
                return [
                    {
                        "conn_id": row["conn_id"],
                        "label": row["payload"].get("label") or row["payload"].get("base_url") or "",
                        "base_url": row["payload"].get("base_url") or "",
                        "model": row["payload"].get("model") or "",
                        "connected_at": row["connected_at"],
                    }
                    for row in CustomModelRepository._rows(cursor, team_id)
                ]

    @staticmethod
    def for_model(team_id: str, model: str) -> dict[str, Any] | None:
        """이 모델 이름을 감당하는 커스텀 엔드포인트. 없으면 `None`.

        **모델 이름 하나로 경로가 정해진다.** `agent.model` 에 별도 표식을 넣지
        않으므로 러너·도구가 지금 쓰는 문자열 그대로 돈다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                for row in CustomModelRepository._rows(cursor, team_id):
                    if row["payload"].get("model") == model:
                        return row["payload"]
        return None

    @staticmethod
    def list_all() -> list[dict[str, Any]]:
        """모든 팀의 등록분. **운영자 콘솔만 쓴다** — 팀은 자기 것만 본다.

        **키는 여기서도 안 나간다.** 등록한 사람이 운영자여도 마찬가지다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT c.conn_id, c.connected_at, c.encrypted_credential_ref,
                           u.team_id, t.name AS team_name
                    FROM connector_conn AS c
                    JOIN user_account AS u ON u.account_id = c.account_id
                    LEFT JOIN team AS t ON t.team_id = u.team_id
                    WHERE c.connector_type = %s
                    ORDER BY u.team_id, c.connected_at
                    """,
                    (CustomModelRepository.TYPE,),
                )
                rows = []
                for row in cursor.fetchall():
                    payload = _decrypt_or_none(row["encrypted_credential_ref"])
                    # 팀 쪽 목록과 달리 **못 읽는 행도 보여준다.** 치울 사람이
                    # 운영자라, 숨기면 아무도 모르는 채로 영영 남는다.
                    broken = payload is None
                    payload = payload or {}
                    rows.append(
                        {
                            "conn_id": row["conn_id"],
                            "team_id": row["team_id"],
                            "team_name": row["team_name"],
                            "label": "읽을 수 없음" if broken else (payload.get("label") or payload.get("base_url") or ""),
                            "base_url": payload.get("base_url") or "",
                            "model": payload.get("model") or "",
                            "connected_at": row["connected_at"],
                        }
                    )
                return rows

    @staticmethod
    def models_for_team(team_id: str) -> set[str]:
        """이 팀에 이미 등록된 모델 이름. 중복 등록을 막는 쪽이 쓴다."""

        with database_connection() as connection:
            with connection.cursor() as cursor:
                return {
                    row["payload"].get("model")
                    for row in CustomModelRepository._rows(cursor, team_id)
                }

    @staticmethod
    def add_for_team(
        *, team_id: str, label: str, base_url: str, api_key: str, model: str, registered_by: str
    ) -> None:
        """운영자가 **그 팀에** 등록한다.

        `connector_conn` 에는 팀 칸이 없고 소속은 `user_account.team_id` 로만
        나온다. 그래서 **그 팀의 팀장 계정에** 매단다 — 운영자 자기 계정에 매달면
        운영자의 팀(대개 없다)에 매달려 정작 그 팀에서는 안 보인다.

        스키마에 `team_id` 를 새로 다는 방법도 있지만, 컬럼 하나 때문에 팀원
        전원이 ALTER 를 돌려야 한다(메인 모델을 정문 에이전트의 칸에 둔 것과 같은
        판단이다). 대신 **누가 등록했는지는 payload 에 남긴다** — 소유 계정만 보면
        팀장이 직접 등록한 것처럼 보이기 때문이다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT owner_account_id FROM team WHERE team_id = %s", (team_id,)
                )
                row = cursor.fetchone()
                if row is None:
                    raise RecordNotFound(f"없는 팀입니다: {team_id}")

                # **같은 트랜잭션에서 한 번 더 본다.** 뷰의 중복 검사와 이 INSERT
                # 사이에는 최대 25초짜리 외부 호출(`_verify`)이 있어서, 그 사이에
                # 들어온 다른 요청과 겹치면 같은 이름이 두 벌 남는다. 경로가 모델
                # 이름 하나로 정해지므로 그건 곧 「어느 것으로 도는지 모른다」다.
                if any(
                    r["payload"].get("model") == model
                    for r in CustomModelRepository._rows(cursor, team_id)
                ):
                    raise ReferenceNotFound(f"{model} 은 이 팀에 이미 등록돼 있습니다.")

                conn_id = next_short_code(
                    cursor, table="connector_conn", column="conn_id", prefix="CN"
                )
                cursor.execute(
                    """
                    INSERT INTO connector_conn
                        (conn_id, account_id, connector_type, encrypted_credential_ref)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        conn_id,
                        row["owner_account_id"],
                        CustomModelRepository.TYPE,
                        encrypt_credential(
                            {
                                "label": label,
                                "base_url": base_url,
                                "api_key": api_key,
                                "model": model,
                                "registered_by": registered_by,
                            }
                        ),
                    ),
                )

    @staticmethod
    def remove_by_conn_id(conn_id: str) -> dict[str, Any]:
        """운영자용 삭제. **팀 경계를 안 본다** — 콘솔은 모든 팀을 다루는 자리다.

        팀 쪽 삭제 경로는 없다(등록이 운영자 몫이라 삭제도 그렇다).

        **지운 내용을 돌려준다.** 행을 지우고 나면 `conn_id` 는 아무것도 가리키지
        않아서, 감사 로그에 그 값만 남기면 나중에 「어느 팀의 무슨 모델이 없어졌나」
        를 아무도 복원할 수 없다(2026-08-13 검토).

        **그 모델을 쓰는 에이전트가 있으면 지우지 않는다.** 지우면 그 에이전트는
        실행 시점에 우리 키로 없는 모델을 부르다 죽는다 — 저장은 멀쩡해 보이는데
        대화만 실패하는, 이 프로젝트가 계속 겪어 온 모양이다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT c.encrypted_credential_ref, u.team_id
                    FROM connector_conn AS c
                    JOIN user_account AS u ON u.account_id = c.account_id
                    WHERE c.conn_id = %s AND c.connector_type = %s
                    """,
                    (conn_id, CustomModelRepository.TYPE),
                )
                row = cursor.fetchone()
                if row is None:
                    raise RecordNotFound(f"등록되지 않은 모델 API 입니다: {conn_id}")

                payload = _decrypt_or_none(row["encrypted_credential_ref"]) or {}
                model = payload.get("model") or ""
                # 못 읽는 행은 어차피 아무도 못 쓴다 — 쓰는 곳을 물을 것도 없이 지운다.
                if model:
                    cursor.execute(
                        "SELECT name FROM agent WHERE team_id = %s AND model = %s AND status <> 'ARCHIVED' ORDER BY name",
                        (row["team_id"], model),
                    )
                    users = [r["name"] for r in cursor.fetchall()]
                    if users:
                        raise ReferenceNotFound(
                            f"이 모델을 쓰는 에이전트가 있습니다: {', '.join(users)}. "
                            "그 에이전트의 모델을 먼저 바꿔 주세요."
                        )

                cursor.execute("DELETE FROM connector_conn WHERE conn_id = %s", (conn_id,))
                return {
                    "team_id": row["team_id"],
                    "model": model,
                    "label": payload.get("label") or "",
                    "base_url": payload.get("base_url") or "",
                }


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
    def start_with_id(
        *,
        run_id: str,
        agent_id: str,
        session_id: str | None,
        parent_run_id: str | None,
        agent_version_id: str | None = None,
        runtime_profile_version: str | None = None,
        resolved_provider: str | None = None,
        resolved_endpoint_hash: str | None = None,
    ) -> str:
        """`start()`의 짝 — 호출자가 `run_id`를 이미 정해서 부를 때 쓴다.

        새 엔진(`services.agent_runtime`)은 이벤트 스트림에 `run_id`를 먼저
        실어 내보낸다(공통 계약 §14 — `agent_started`/`subagent_started`가
        `run_id`를 담고, 그 값이 화면·로그 양쪽에서 같은 실행을 가리키는
        유일한 키다). `start()`처럼 Postgres가 새로 생성하게 두면 스트림에
        이미 나간 `run_id`와 DB 행의 실제 `run_id`가 어긋난다 — 화면에 보인
        `run_id`로 이 행을 못 찾게 된다.

        `agent_version_id`/`runtime_profile_version`은 레거시 `start()`엔
        없는 값이다(레거시 harness 경로는 이 컬럼들을 모른다 — 계속 NULL로
        쌓인다, `DB/migrations/2026-08-13_agent_versioning.sql` 주석). 새
        엔진만 채운다.

        `resolved_provider`/`resolved_endpoint_hash`(2026-08-19 추가, §4순위
        Run Snapshot — 정본: `2026-08-19_01_실행_안정성_설계.md` §1)도 같은
        이유로 새 엔진만 채운다 — 이 실행이 실제로 사용한 모델 provider와
        (팀 커스텀 엔드포인트라면) 그 `base_url`의 해시값이다. 원문
        `base_url`은 저장하지 않는다(사내망 주소 노출 방지).
        """
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO agent_run
                        (run_id, session_id, agent_id, parent_run_id,
                         agent_version_id, runtime_profile_version,
                         resolved_provider, resolved_endpoint_hash, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'RUNNING')
                    RETURNING run_id::text
                    """,
                    (
                        run_id,
                        session_id,
                        agent_id,
                        parent_run_id,
                        agent_version_id,
                        runtime_profile_version,
                        resolved_provider,
                        resolved_endpoint_hash,
                    ),
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

    @staticmethod
    def suspend(*, run_id: str) -> None:
        """HITL 승인 대기로 멈춘 실행을 `PENDING`으로 표시한다(2026-08-19,
        §0순위 — 새 엔진 HITL resume API).

        `finish()`와 다르게 `ended_at`을 안 채운다 — 실제로 끝난 게 아니라
        재개를 기다리는 것뿐이다. `status`는 CHECK 제약 없는 `VARCHAR(20)`
        라(`DB/schema.sql` 실제 스키마 확인) 새 값을 추가하는 데 마이그레이션이
        필요 없다. `tool_call.status`가 이미 같은 뜻으로 `'PENDING'`을 쓰고
        있어(선기록 패턴) 그 값을 그대로 재사용했다 — 새 어휘를 안 만든다.
        재개 뒤 실제로 끝나면 `finish()`가 `ended_at`을 채운다.
        """
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE agent_run SET status = 'PENDING' WHERE run_id = %s",
                    (run_id,),
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


def _resolve_session_agent(cursor, *, agent_id: str, team_id: str, account_id: str) -> str | None:
    """대화를 열 에이전트가 레거시(`agent`)인지 신규 버전(`agents`)인지 가려내고,
    신규면 **지금 발행 중인** 버전(`agents.current_version_id`)을 돌려준다.
    레거시는 버전이 없으므로 `None`.

    **레거시 테이블을 먼저 본다.** 두 테이블이 같은 "AG" 접두어를 쓰는 건
    실수가 아니라 의도된 설계다(DB/migrations/2026-08-13_agent_versioning.sql
    상단 주석 — 신규 테이블이 결국 `agent`를 대체할 것을 전제로 같은 코드
    체계를 물려받았다). `next_short_code()`가 테이블마다 따로 유일성을 매기므로
    같은 값이 두 테이블에 동시에 존재할 수 있지만, 그렇더라도 레거시 우선
    조회가 "레거시로 만든 에이전트는 레거시 실행 경로를 그대로 쓴다"는 지금의
    보수적인 기본값과 맞는다 — 전환이 끝나 `agent`가 폐기되면 이 분기 자체가
    없어진다.

    **DRAFT는 만든 사람 본인만 대화를 열 수 있다**(2026-08-18 추가 — "개인"
    탭에 있는 걸 활성화 없이 스스로 테스트할 방법이 없다는 문제를 이걸로
    닫는다). 남의 DRAFT는 team_id가 같아도 막는다 — `_writable_agent_version`이
    조회·수정에 거는 것과 같은 프라이버시 경계를 실행에도 건다.
    """

    cursor.execute("SELECT team_id FROM agent WHERE agent_id = %s", (agent_id,))
    legacy = cursor.fetchone()
    if legacy is not None:
        if legacy["team_id"] != team_id:
            raise PermissionDenied("이 에이전트를 쓸 수 없습니다.")
        return None

    cursor.execute(
        "SELECT team_id, status, current_version_id, owner_account_id FROM agents WHERE agent_id = %s",
        (agent_id,),
    )
    agent = cursor.fetchone()
    if agent is None:
        raise RecordNotFound(f"존재하지 않는 에이전트입니다: {agent_id}")
    if agent["team_id"] != team_id:
        raise PermissionDenied("이 에이전트를 쓸 수 없습니다.")

    is_own_draft = agent["status"] == "DRAFT" and agent["owner_account_id"] == account_id
    if agent["current_version_id"] is None or not (agent["status"] == "ACTIVE" or is_own_draft):
        # ACTIVE도 아니고 본인 DRAFT도 아니면(비활성화됐거나, 아직 한 번도
        # 발행 안 했거나, 남의 DRAFT면) 대화를 열 수 없다 —
        # AgentVersionActivateAPIView의 ACTIVE 게이팅과 같은 경계
        # ("Chat 위임과 관리 화면의 'Chat에서 사용' 노출").
        raise ReferenceNotFound(f"대화를 열 수 없는 에이전트입니다: {agent_id}")
    return agent["current_version_id"]


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
        SELECT session_id::text, team_id, account_id, agent_id, agent_version_id,
               proj_id, title, tool_refs_override, created_at, updated_at
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

                agent_version_id = _resolve_session_agent(
                    cursor, agent_id=agent_id, team_id=team_id, account_id=account_id
                )

                cursor.execute(
                    """
                    INSERT INTO chat_session
                        (team_id, account_id, agent_id, agent_version_id, proj_id, title)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING session_id::text, team_id, account_id, agent_id,
                              agent_version_id, proj_id, title, tool_refs_override,
                              created_at, updated_at
                    """,
                    (team_id, account_id, agent_id, agent_version_id, proj_id, title),
                )
                row = cursor.fetchone()

                # `list_for_account()`와 같은 이유로 이름을 채운다 — RETURNING은
                # 방금 넣은 chat_session 행만 주고 다른 테이블은 못 붙인다.
                # 화면(대화 목록의 에이전트별 묶음, 2026-08-18)이 방금 만든
                # 대화도 바로 이름으로 보여줘야 해서, 여기서 한 번 더 찾는다.
                cursor.execute(
                    """
                    SELECT COALESCE(
                        (SELECT name FROM agent WHERE agent_id = %s),
                        (SELECT name FROM agents WHERE agent_id = %s)
                    ) AS agent_name
                    """,
                    (agent_id, agent_id),
                )
                row["agent_name"] = cursor.fetchone()["agent_name"]
                return row

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
                    SELECT s.session_id::text, s.agent_id, s.agent_version_id, s.proj_id,
                           s.title, s.created_at, s.updated_at,
                           -- 레거시(agent)와 신규(agents) 어느 쪽으로 만든 대화든
                           -- 이름이 뜨게 둘 다 본다 — 세션은 생성 시 어느 테이블
                           -- 것인지 이미 agent_version_id 유무로 갈라져 있어서
                           -- (_resolve_session_agent) 겹칠 일이 없다.
                           COALESCE(a.name, av.name) AS agent_name
                    FROM chat_session AS s
                    LEFT JOIN agent AS a ON a.agent_id = s.agent_id
                    LEFT JOIN agents AS av ON av.agent_id = s.agent_id
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
    def set_tool_refs_override(
        *, session_id: str, account_id: str, tool_refs: list[str] | None
    ) -> dict[str, Any]:
        """이 대화에서만 쓸 도구 목록을 저장한다(2026-08-18, Chat "+" 버튼).

        에이전트 원본 `tool_refs`는 안 건드린다 — 실행 시점에
        `apps/chat/api_views.py`가 이 값이 있으면 로드된 정의의 tool_refs를
        통째로 갈아 끼운다(`executor.py`의 `tool_refs_override` 인자).
        `tool_refs=None`을 주면 커스터마이즈를 지우고 에이전트 원래 값으로
        되돌린다 — 빈 리스트(`[]`)는 "이 대화에서 도구를 전부 껐다"는 다른
        뜻이라 구분해서 받는다.

        **소유자만** 바꿀 수 있다 — 대화는 개인 것이고(`_require_session`은
        팀 검사라 남의 대화도 열리지만), 도구 구성은 그 대화를 실제로 쓰는
        사람의 선택이어야 한다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                _require_team(cursor, account_id)
                cursor.execute(
                    "SELECT account_id FROM chat_session WHERE session_id::text = %s",
                    (session_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    raise RecordNotFound(f"존재하지 않는 대화입니다: {session_id}")
                if row["account_id"] != account_id:
                    raise PermissionDenied("이 대화에 접근할 수 없습니다.")

                cursor.execute(
                    """
                    UPDATE chat_session SET tool_refs_override = %s, updated_at = now()
                    WHERE session_id::text = %s
                    RETURNING session_id::text, team_id, account_id, agent_id,
                              agent_version_id, proj_id, title, tool_refs_override,
                              created_at, updated_at
                    """,
                    (tool_refs, session_id),
                )
                return cursor.fetchone()

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

    **읽기는 팀이, 쓰기는 운영자가 부른다**(2026-08-18 멘토링). 그래서 읽기만
    `account_id` 로 팀을 찾고, 쓰기는 `team_id` 를 직접 받는다 — 운영자에게는
    자기 팀이 없어서 `_require_team` 이 통하지 않는다. 모델 쪽
    (`CustomModelRepository.add_for_team`)과 같은 모양이다.
    """

    @staticmethod
    def list_all() -> list[dict[str, Any]]:
        """모든 팀의 등록분. **운영자 콘솔만 쓴다** — 팀은 자기 것만 본다."""

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT s.mcp_server_id, s.name, s.endpoint_url, s.status,
                           s.last_checked_at, s.team_id, t.name AS team_name,
                           (s.auth_token_enc IS NOT NULL) AS has_token,
                           (SELECT count(*) FROM mcp_tool WHERE server_id = s.mcp_server_id)
                               AS tool_count
                    FROM mcp_server AS s
                    LEFT JOIN team AS t ON t.team_id = s.team_id
                    ORDER BY s.team_id, s.name
                    """
                )
                return list(cursor.fetchall())

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
        *, team_id: str, name: str, endpoint_url: str, auth_token: str | None,
        registered_by: str,
    ) -> dict[str, Any]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
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
                        registered_by,
                    ),
                )
                # `has_token` 을 붙여서 돌려준다. RETURNING 에 없다고 빼면
                # `server_response` 가 기본값 False 로 채워, **토큰을 넣고 등록했는데
                # 화면은 「토큰 없음」이라고 말한다**(2026-08-13 실제로 그랬다).
                return {**cursor.fetchone(), "has_token": auth_token is not None, "tools": []}

    @staticmethod
    def update(
        *,
        server_id: str,
        team_id: str,
        name: str,
        endpoint_url: str,
        auth_token: str | None,
        replace_token: bool,
    ) -> dict[str, Any]:
        """등록한 서버를 고친다.

        **주소가 바뀌면 이전에 읽은 도구는 다른 서버의 것이다.** 이름만 같을 뿐
        같은 도구라는 보장이 없으므로 도구 목록을 지우고 상태를 `UNCHECKED` 로
        되돌린다 — 「연결 확인」을 다시 눌러야 에이전트가 고를 수 있다. 지우지
        않으면 화면은 도구 5종을 보여주는데 실제로는 없는 것을 부르게 된다.

        에이전트에 붙어 있던 `mcp:<tool_id>` 도 함께 뺀다. `delete` 와 같은
        이유다 — 없는 도구가 허용 목록에 남으면 부를 때마다 실패한다.

        **토큰은 안 보내면 그대로 둔다.** 화면이 저장된 토큰을 다시 보여주지
        않으므로(`server_response` 가 `has_token` 만 준다), 안 보낸 것을 「지우라」로
        읽으면 이름만 고쳐도 토큰이 날아간다. 지우려면 `replace_token=True` 와
        빈 값을 함께 보낸다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                before = _server_row(cursor, server_id=server_id, team_id=team_id)

                moved = before["endpoint_url"] != endpoint_url
                if moved:
                    cursor.execute(
                        """
                        DELETE FROM agent_tool WHERE tool_ref IN (
                            SELECT 'mcp:' || mcp_tool_id FROM mcp_tool WHERE server_id = %s
                        )
                        """,
                        (server_id,),
                    )
                    cursor.execute("DELETE FROM mcp_tool WHERE server_id = %s", (server_id,))

                if replace_token:
                    token_enc = encrypt_credential({"auth_token": auth_token}) if auth_token else None
                else:
                    token_enc = before["auth_token_enc"]

                cursor.execute(
                    """
                    UPDATE mcp_server
                    SET name = %s,
                        endpoint_url = %s,
                        auth_token_enc = %s,
                        status = CASE WHEN %s THEN 'UNCHECKED' ELSE status END,
                        last_checked_at = CASE WHEN %s THEN NULL ELSE last_checked_at END
                    WHERE mcp_server_id = %s
                    RETURNING mcp_server_id, name, endpoint_url, status, last_checked_at
                    """,
                    (name, endpoint_url, token_enc, moved, moved, server_id),
                )
                row = cursor.fetchone()
                return {**row, "has_token": token_enc is not None, "tools": []}

    @staticmethod
    def credentials(*, server_id: str, team_id: str) -> dict[str, Any]:
        """연결 테스트에 필요한 것만. **복호화한 토큰은 여기서만 나온다.**"""

        with database_connection() as connection:
            with connection.cursor() as cursor:
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
    def save_tools(*, server_id: str, team_id: str, tools: list[dict[str, Any]]) -> int:
        """연결 테스트 결과를 반영하고 status 를 CONNECTED 로 올린다.

        서버에서 사라진 도구는 지운다. 남겨 두면 에이전트 허용 목록에 붙어 있는
        도구가 실제로는 없는 상태가 되고, 부를 때야 실패한다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
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
    def mark_error(*, server_id: str, team_id: str) -> None:
        """연결 테스트 실패. **행은 지우지 않는다** — 사용자가 고쳐 쓸 값이고,
        ERROR 상태를 보여 줘야 왜 편집 화면에서 이 도구를 못 고르는지 안다."""

        with database_connection() as connection:
            with connection.cursor() as cursor:
                _server_row(cursor, server_id=server_id, team_id=team_id)
                cursor.execute(
                    "UPDATE mcp_server SET status = 'ERROR', last_checked_at = now() "
                    "WHERE mcp_server_id = %s",
                    (server_id,),
                )

    @staticmethod
    def delete(*, server_id: str, team_id: str) -> None:
        with database_connection() as connection:
            with connection.cursor() as cursor:
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
                    -- ARCHIVED(삭제)만 뺀다. DRAFT·DISABLED 도 보여야 소유자가
                    -- 관리 목록에서 초안을 찾아 이어 쓰거나 비활성 상태를 볼 수 있다.
                    -- Chat 쪽에서 ACTIVE 만 골라 쓰는 건 프런트(`ChatPage.tsx`) 책임이다.
                    WHERE a.team_id = %s AND a.status <> 'ARCHIVED'
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
    def create(
        *, account_id: str, fields: dict[str, Any], tool_refs: list[str], status: str = "DRAFT"
    ) -> dict[str, Any]:
        """생성 = 게시가 아니다. 기본값은 `DRAFT` — Chat 에 노출되거나 위임
        대상이 되려면 별도로 활성화(`AgentActivateAPIView`)해야 한다. 검증에
        걸리거나 중간에 나가도 여기까지는 저장돼 있어야 작성한 내용을 잃지
        않는다."""

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
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, false, %s, %s)
                    """,
                    (
                        agent_id, team_id, fields["name"], fields["description"],
                        fields["instruction"], fields["model"], fields["reasoning_effort"],
                        fields["max_iterations"], status, account_id,
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
    def set_status(*, agent_id: str, account_id: str, status: str) -> dict[str, Any]:
        """DRAFT/ACTIVE/DISABLED 사이 전이. 어떤 전이가 허용되는지는 API 뷰가
        정한다 — 여기는 `update`/`delete`와 같은 얇은 쓰기 레이어로 남긴다."""

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team(cursor, account_id)
                _writable_agent(cursor, agent_id=agent_id, team_id=team_id)
                cursor.execute(
                    "UPDATE agent SET status = %s, updated_at = now() WHERE agent_id = %s",
                    (status, agent_id),
                )
        return AgentCrudRepository.get(agent_id=agent_id, account_id=account_id)

    @staticmethod
    def team_tool_refs(account_id: str) -> list[dict[str, Any]]:
        """편집 화면이 고를 수 있는 MCP 도구. 내장 도구는 코드 상수라 여기 없다."""

        with database_connection() as connection:
            with connection.cursor() as cursor:
                team_id = _require_team(cursor, account_id)
                cursor.execute(
                    """
                    SELECT 'mcp:' || t.mcp_tool_id AS tool_ref, t.name, t.description,
                           t.input_schema, s.name AS server_name, s.status AS server_status
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
