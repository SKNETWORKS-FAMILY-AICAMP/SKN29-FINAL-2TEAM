"""Agent Platform 테이블(`agents`·`agent_versions`·`mcp_tool`·`agent_run`·`tool_call`)의 직접 SQL.

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
    DuplicateRecord,
    PermissionDenied,
    RecordNotFound,
    ReferenceNotFound,
    RepositoryError,
)
from .repositories import _require_team


def _next_shared_agent_id(cursor) -> str:
    """`agents.agent_id`를 발급한다. `next_short_code()`의 얇은 래퍼다."""
    return next_short_code(cursor, table="agents", column="agent_id", prefix="AG")


class AgentRepository:
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

class AgentVersionRepository:
    """`agents`·`agent_versions`·`agent_version_tools` 조회 전용.

    계약: docs/설계 및 구현/3_중간발표 이후/작업기록/Deep_Agents/2026-08-13_02_Deep-Agent_런타임_공통_계약_v1.md
    §6.1. `backend.db.errors`(`RecordNotFound`/`PermissionDenied`)만 던진다 —
    `services.agent_runtime.exceptions`로의 번역은 Loader
    (services/agent_runtime/loader.py)의 몫이다.
    """

    @staticmethod
    def get_definition(
        *, agent_id: str, agent_version_id: str, account_id: str, team_id: str
    ) -> dict[str, Any]:
        """특정 불변 버전의 에이전트 정의를 반환한다(02 §6.1).

        `account_id`는 지금 안 쓴다 — v1은 `agents.visibility`가 항상 'TEAM'
        고정이라 개인 단위 권한 분기가 없다. 반환 딕셔너리는 `AgentDefinition`
        (services/agent_runtime/definitions.py) 필드와 1:1로 맞춘다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT v.agent_version_id, v.agent_id, v.system_prompt,
                           v.model, v.reasoning_effort, v.max_iterations,
                           a.team_id, a.name, a.description, a.status AS agent_status,
                           a.owner_account_id AS agent_owner_account_id
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
        """기본 챗 에이전트면 지금 발행된 최신 버전을, 아니면 `None`을 돌려준다.

        다른 에이전트는 세션이 만들 때 고정한 버전을 계속 쓴다(버전 불변성,
        02 §5.2). 기본 챗만 예외다 — Chat "+" 버튼으로 도구를 붙이면 그 자리에서
        새 버전이 발행되는데, 이미 연 대화에도 바로 반영돼야 한다. 호출부
        (`apps/chat/api_views.py`)는 `None`이면 세션의 고정 버전을 그대로 쓴다.
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

        비활성·권한 없는 자식도 목록에서 빼지 않는다(02 §6.1) — `is_active`,
        `can_execute`로 표시해서 그대로 돌려준다. `has_subagents`는 그 자식이
        다시 부모 노릇을 하는지 본다(MVP는 1단계 위임까지만 허용,
        `DelegationDepthError`).

        `is_active`는 "ACTIVE 상태"가 아니라 "서브 에이전트로 참조해도 되는가"다
        — ACTIVE거나 본인 소유 DRAFT면 true다(`_build_subagent_refs()`와 같은
        계산).
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT s.child_agent_id, s.child_version_id, s.alias,
                           s.delegation_description,
                           a.team_id AS child_team_id, a.status AS child_status,
                           a.owner_account_id AS child_owner_account_id,
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
                "is_active": row["child_status"] == "ACTIVE"
                or (row["child_status"] == "DRAFT" and row["child_owner_account_id"] == account_id),
                "can_execute": row["child_team_id"] == team_id,
                "has_subagents": row["has_subagents"],
            }
            for row in rows
        ]


def _writable_agent_version(
    cursor, *, agent_id: str, team_id: str, account_id: str, enforce_draft_privacy: bool = True
) -> None:
    """조회·수정(=새 버전 발행)해도 되는 논리적 에이전트인가.

    DRAFT는 만든 사람만 접근한다(2026-08-18) — 남의 DRAFT는 URL을 직접 알아도
    막는다. ACTIVE·DISABLED는 한 번이라도 팀에 공유된 것이라 제한이 없다.

    `delete()`는 `enforce_draft_privacy=False`로 부른다 — 삭제 권한은 뷰 레이어
    (`require_owner_or_leader`)가 이미 확인했고, 여기서 또 막으면 팀장이 남의
    DRAFT를 못 지우게 된다.
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

    `child_version_id`가 실제로 `child_agent_id`의 버전인지 여기서 확인한다.
    `is_active`는 ACTIVE거나 본인 소유 DRAFT면 true다(2026-08-18) — 부모를
    활성화하면 그 DRAFT 자식도 같이 활성화된다(`_cascade_activate_draft_subagents`,
    `api_views.py`). 남의 DRAFT는 여전히 막는다.
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
    """이 팀에서 지금 발행 중인(`agents.current_version_id`) 관계로 그래프를
    만든다. `validate_no_cycle`이 이 그래프로 순환을 판단한다 — 옛 버전의
    관계는 포함하지 않는다.
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
    바로 ACTIVE로 발행한다(2026-08-15).

    Chat 화면 드롭다운이 이 에이전트를 포함한 팀의 활성 에이전트 목록을 보여
    주고, 아무것도 안 고르면 여기로 떨어진다. `is_default_chat`은 팀당 최대
    1개만 true다(유니크 인덱스).

    호출자가 트랜잭션을 쥔다 — 자체 `database_connection()`을 열지 않고 넘겨
    받은 커서를 그대로 쓴다. `TeamRepository.create()`가 이미 연 트랜잭션에
    얹혀서, 기본 챗 에이전트 없이 팀만 만들어지는 반쪽 상태가 생기지 않는다.

    model을 명시적으로 채운다 — NULL이면 `models/factory.py`의 `resolve()`가
    필수 인자로 받아 그대로 깨진다.
    """
    # 지연 import — services.harness의 무거운 의존성 사슬을 이 모듈이 항상
    # 끌고 들어오지 않게 한다.
    from services.harness.runner import DEFAULT_EFFORT, DEFAULT_MODEL

    agent_id = _next_shared_agent_id(cursor)
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
            "기본 어시스턴트",
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

    # 기본 도구 목록은 `DEFAULT_CHAT_TOOL_REFS` 가 정본이다(2026-08-29). 예전에는
    # `side_effect=False` 만 붙였는데, "엑셀로 만들어줘" 같은 쓰기 도구가 빠져서
    # 기본 어시스턴트가 못 하는 일이 많았다. 쓰기 도구도 실행 전 승인(HITL)이
    # 걸리므로 켜 둔다. 팀장이 Builder 에서 개별로 끌 수 있다.
    from services.harness.registry import DEFAULT_CHAT_TOOL_REFS

    for tool_ref in sorted(DEFAULT_CHAT_TOOL_REFS):
        cursor.execute(
            "INSERT INTO agent_version_tools (agent_version_id, tool_ref) VALUES (%s, %s)",
            (agent_version_id, tool_ref),
        )

    cursor.execute(
        "UPDATE agents SET current_version_id = %s WHERE agent_id = %s",
        (agent_version_id, agent_id),
    )

    return agent_id


#: 「업무 추출 에이전트」(prebuilt)의 시스템 프롬프트. `provision_task_extraction_agent`
#: 와 `DB/migrations/2026-08-30_task_extraction_agent.sql` 이 **같은 문구**를 써야 한다
#: — 한쪽만 고치면 신규 팀과 기존 팀의 에이전트가 달라진다.
TASK_EXTRACTION_AGENT_PROMPT = (
    "너는 프로젝트 문서에서 해야 할 업무를 뽑아 정리하는 전담 에이전트다.\n\n"
    "사용자가 「이 프로젝트 문서에서 업무를 뽑아 줘」·「할 일 정리해 줘」처럼 요청하면 "
    "`task_extraction` 을 **인자 없이** 부른다. 기준 문서는 사람이 프로젝트 화면에서 "
    "미리 골라 둔 것을 쓰므로 네가 문서를 고르거나 id 를 넘기지 않는다. "
    "몇 분 걸리는 작업이니 시작 전에 그 사실을 한 줄로 알린다.\n\n"
    "추출이 끝나면 결과를 제목·담당 역할·예상 공수·근거 요약이 보이는 표로 정리해 "
    "보여 준다. 사용자가 등록을 원하면 `task_register` 로 넘긴다(실행 전 승인 카드가 "
    "뜬다). 같은 제목이 이미 있는지 궁금하면 먼저 `task_list` 로 확인한다.\n\n"
    "추출 결과에 `model_fallback_from` 값이 있으면, 답변에 「요청하신 모델("
    "<그 값>)로는 이 추출을 돌릴 수 없어 gpt-5.6-sol 로 대체했습니다」를 반드시 "
    "명시한다.\n\n"
    "「기준 문서가 지정되지 않았다」는 오류가 나면, 프로젝트 화면의 「기준 문서 "
    "선택」에서 문서를 정한 뒤 다시 요청하라고 안내한다."
)

#: 이 에이전트가 붙이는 도구. 추출 + 등록 + (중복 확인용) 조회.
TASK_EXTRACTION_AGENT_TOOLS = (
    "task_extraction",
    "task_register",
    "task_list",
    "document_list",
)


def provision_task_extraction_agent(cursor, *, team_id: str, owner_account_id: str) -> str:
    """팀에 「업무 추출 에이전트」(prebuilt) 하나를 만들고 바로 ACTIVE 로 발행한다
    (2026-08-30).

    `task_extraction` 은 원래 채팅 도구 하나였다. 이걸 독립 선택 가능한 에이전트로
    올려, 채팅 상단 드롭다운에서 고를 수도 있고 기본 어시스턴트가 위임할 수도 있게
    한다. 파이프라인(`services/task_extraction/service.py`) 자체는 그대로다 — 이
    에이전트는 그 도구를 부르는 얇은 껍데기이며, 종합 단계 모델은 이 에이전트에
    설정된 모델(`agent_versions.model`)을 그대로 쓴다.

    `provision_default_chat_agent` 와 같은 규칙 — 넘겨받은 커서에 얹혀 돌고
    (`TeamRepository.create()` 트랜잭션), model 을 NULL 로 두지 않는다.
    """

    agent_id = _next_shared_agent_id(cursor)
    cursor.execute(
        """
        INSERT INTO agents
            (agent_id, team_id, name, description, owner_account_id,
             status, is_prebuilt, is_default_chat)
        VALUES (%s, %s, %s, %s, %s, 'ACTIVE', true, false)
        """,
        (
            agent_id,
            team_id,
            "업무 추출 에이전트",
            "프로젝트 기준 문서에서 업무 후보를 뽑아 근거와 함께 정리하고, "
            "원하면 플랫폼 업무로 등록합니다.",
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
            TASK_EXTRACTION_AGENT_PROMPT,
            # 파이프라인의 기본 종합 모델과 같은 값. 팀장이 Builder 에서 바꾸면
            # 그 모델로 종합한다(Claude 면 sol 로 fallback + 답변에 고지).
            "gpt-5.6-sol",
            "medium",
            owner_account_id,
        ),
    )

    for tool_ref in TASK_EXTRACTION_AGENT_TOOLS:
        cursor.execute(
            "INSERT INTO agent_version_tools (agent_version_id, tool_ref) VALUES (%s, %s)",
            (agent_version_id, tool_ref),
        )

    cursor.execute(
        "UPDATE agents SET current_version_id = %s WHERE agent_id = %s",
        (agent_version_id, agent_id),
    )

    return agent_id


class AgentVersionCrudRepository:
    """Builder가 쓰는 새 버전 스키마 CRUD — "저장"은 곧 "발행"이다.

    `agent_versions`는 불변이라(02 §5.2) 저장과 동시에 새 불변 버전을 만든다
    — "임시 저장 후 나중에 발행" 같은 중간 상태가 없다. 저장 없이 시험 실행
    하려면 `services/agent_runtime/loader.py`의 `from_draft()`를 쓴다.

    구조 검증은 저장·발행 API와 런타임 Factory가 같은 `validate_subagents()`를
    쓴다(02 §7.1).
    """

    @staticmethod
    def list_for_team(account_id: str) -> list[dict[str, Any]]:
        """팀 안에서 이 계정이 볼 수 있는 에이전트.

        DRAFT는 만든 사람에게만 보인다. ACTIVE·DISABLED는 한 번이라도 팀에
        공유된 적이 있다는 뜻이라 팀 전체가 계속 본다(2026-08-18). `is_favorite`
        는 이 계정 기준이다 — 팀 전체가 보는 값이 아니라서 `agents`가 아니라
        `agent_favorites`에서 EXISTS로 붙인다.
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
                        "max_iterations": 10,
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
                    agent_id = _next_shared_agent_id(cursor)
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

                # 구조 검증 — API와 Factory가 같은 함수를 쓴다(02 §7.1).
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
                        fields.get("max_iterations", 10),
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
        """DRAFT/ACTIVE/DISABLED 사이 전이. 어떤 전이가 허용되는지는 API 뷰가 정한다.

        `is_default_chat=true`인 행은 ACTIVE 밖으로 못 뺀다 — 꺼지면 Chat 랜딩이
        대화 상대 없이 빈 화면이 된다.
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
        """즐겨찾기 별 토글(2026-08-18). 계정별 개인 설정이라 `agents`가 아니라
        `agent_favorites`(계정, 에이전트) 표에 따로 둔다. `list_for_team()`에서
        못 보는 에이전트(남의 DRAFT)는 즐겨찾기도 못 한다.
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
        """이 에이전트의 지금 버전이 서브 에이전트로 참조하는 것 중 아직
        DRAFT인 것들(2026-08-18). 활성화 연쇄(`_cascade_activate_draft_subagents`,
        `apps/agents/api_views.py`)가 이 목록을 모델·도구 재검증에 쓰므로
        그 필드까지 같이 준다.
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
        """활성화 연쇄로 서브 에이전트를 켠다(2026-08-18). 부모 버전이 실제로
        참조하는 자식만 골라 오므로(`list_dependent_draft_children()`) 그 자체가
        권한 근거다. `status='DRAFT'` 조건으로 경합 시 이미 바뀐 행은 건너뛴다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE agents SET status = 'ACTIVE', updated_at = now() "
                    "WHERE agent_id = %s AND status = 'DRAFT'",
                    (agent_id,),
                )

    @staticmethod
    def list_dependents(*, agent_id: str, account_id: str) -> list[str]:
        """이 에이전트를 서브 에이전트로 참조하는, 살아있는 다른 에이전트의
        이름 목록. 삭제 전 확인용 — `delete()`가 같은 조회를 한 번 더 해서
        그 사이 생긴 새 참조까지 막는다.
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
        """ARCHIVED로 내린다 — 행은 지우지 않는다(`agent_run`·`chat_session`이
        이 버전들을 가리킨다). 권한 검사는 뷰가 한다.
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

                # 다른(살아있는) 에이전트가 이걸 서브 에이전트로 참조하면 막는다.
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
                        "supports_image_input": row["payload"].get("supports_image_input") is True,
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
                            "supports_image_input": payload.get("supports_image_input") is True,
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
        *, team_id: str, label: str, base_url: str, api_key: str, model: str,
        supports_image_input: bool, registered_by: str
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
                                "supports_image_input": supports_image_input,
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
                    # 지금 발행 중인 버전(`current_version_id`)만 본다. 옛 버전은
                    # 불변이라 어차피 고칠 수 없고, 실제로 실행에 쓰이는 것은
                    # 발행 중인 버전이다(2026-08-22 — 레거시 `agent.model`을 보던
                    # 검사를 신규 스키마로 옮겼다).
                    cursor.execute(
                        """
                        SELECT a.name
                        FROM agents AS a
                        JOIN agent_versions AS v ON v.agent_version_id = a.current_version_id
                        WHERE a.team_id = %s AND v.model = %s AND a.status <> 'ARCHIVED'
                        ORDER BY a.name
                        """,
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
    def begin(
        *,
        run_id: str,
        tool_ref: str,
        input_summary: str | None,
        langchain_tool_call_id: str | None = None,
    ) -> str:
        """호출을 PENDING으로 선기록하고 같은 LangChain 호출이면 기존 행을 돌려준다.

        HITL resume는 새 Python 스트림이라 메모리의 DB UUID 매핑을 잃는다.
        `(run_id, langchain_tool_call_id)`를 DB의 영속 correlation key로 사용하면
        checkpoint 재처리나 중복 resume에서도 행을 하나만 유지할 수 있다.
        레거시 harness는 LangChain 호출 ID가 없으므로 `None`을 허용하고 예전처럼
        매 실행마다 새 행을 만든다(부분 UNIQUE 인덱스는 NULL을 제외한다).
        """
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO tool_call
                        (run_id, langchain_tool_call_id, tool_ref, input_summary, status)
                    VALUES (%s, %s, %s, %s, 'PENDING')
                    ON CONFLICT (run_id, langchain_tool_call_id)
                        WHERE langchain_tool_call_id IS NOT NULL
                    DO UPDATE SET tool_ref = EXCLUDED.tool_ref
                    RETURNING tool_call_id::text
                    """,
                    (run_id, langchain_tool_call_id, tool_ref, input_summary),
                )
                return cursor.fetchone()["tool_call_id"]

    @staticmethod
    def end(
        *,
        tool_call_id: str,
        status: str,
        duration_ms: int,
        error_code: str | None = None,
        retrieved_doc_ids: list[str] | None = None,
    ) -> None:
        """`retrieved_doc_ids`(2026-08-21): 이 호출이 건드린 문서 식별자.

        **빈 목록과 `None` 을 같게 다룬다** — 둘 다 NULL 로 남긴다. 문서와
        무관한 도구(`people_list` 등)에 빈 배열을 채워 두면 "문서를 찾았는데
        하나도 없었다"와 "애초에 문서를 안 보는 도구다"가 같은 모양이 된다.
        """
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE tool_call
                       SET status = %s, error_code = %s, duration_ms = %s,
                           retrieved_doc_ids = %s
                     WHERE tool_call_id = %s AND status = 'PENDING'
                    """,
                    (status, error_code, duration_ms, retrieved_doc_ids or None, tool_call_id),
                )

    @staticmethod
    def end_by_langchain_id(
        *,
        run_id: str,
        langchain_tool_call_id: str,
        status: str,
        duration_ms: int | None,
        error_code: str | None = None,
        retrieved_doc_ids: list[str] | None = None,
    ) -> None:
        """resume 스트림의 완료를 원래 PENDING 행에 반영한다.

        `status = 'PENDING'` 조건은 중복 resume가 OK/FAILED/REJECTED 최종 상태를
        다시 덮지 못하게 하는 마지막 방어선이다. resume에서 실제 실행 시작
        시각을 모르면 승인 대기 시간을 latency로 오인하지 않도록 duration_ms는
        NULL로 둘 수 있다.
        """
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE tool_call
                       SET status = %s, error_code = %s, duration_ms = %s,
                           retrieved_doc_ids = %s
                     WHERE run_id = %s
                       AND langchain_tool_call_id = %s
                       AND status = 'PENDING'
                    """,
                    (
                        status,
                        error_code,
                        duration_ms,
                        retrieved_doc_ids or None,
                        run_id,
                        langchain_tool_call_id,
                    ),
                )

    @staticmethod
    def reject(*, run_id: str, langchain_tool_call_ids: list[str]) -> None:
        """사용자가 거부한 호출을 실행 실패와 구분해 REJECTED로 닫는다."""
        if not langchain_tool_call_ids:
            return
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE tool_call
                       SET status = 'REJECTED', error_code = 'HITL_REJECTED',
                           duration_ms = NULL
                     WHERE run_id = %s
                       AND langchain_tool_call_id = ANY(%s)
                       AND status = 'PENDING'
                    """,
                    (run_id, langchain_tool_call_ids),
                )


# 재실행 대신 그대로 돌려줄 결과의 폭주 방지용 상한. tool_call_idempotency.result_text
# 는 화면 요약(events.py의 TOOL_OUTPUT_SUMMARY_MAX=500)과 달리 "모델이 실제로
# 봤던 값을 그대로 다시 준다"가 목적이라 자르지 않는 게 원칙이지만, 도구가
# 비정상적으로 큰 결과를 낼 가능성까지 무제한으로 열어 두면 안 되므로
# 애플리케이션 레벨에서만 넉넉한 상한을 건다(DB 컬럼 자체는 TEXT로 무제한).
IDEMPOTENCY_RESULT_MAX_CHARS = 50_000
IDEMPOTENCY_LEASE_SECONDS = 180


class ToolCallIdempotencyRepository:
    """§6순위(외부 Write Tool Idempotency). HITL resume·checkpoint 재시도로 같은
    super-step이 다시 실행돼도 같은 (run_id, langchain_tool_call_id) 조합의
    side_effect 도구는 실제로 한 번만 실행되게 한다.

    tool_call 표와 별도인 이유는 DB/schema.sql의 tool_call_idempotency 주석,
    쓰는 시점(도구 실행 **직전**)은 services/agent_runtime/factory.py의
    _to_langchain_tool()._run() 참고.
    """

    @staticmethod
    def find_result(*, run_id: str, langchain_tool_call_id: str) -> str | None:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT result_text
                      FROM tool_call_idempotency
                     WHERE run_id = %s AND langchain_tool_call_id = %s
                       AND status = 'SUCCEEDED'
                    """,
                    (run_id, langchain_tool_call_id),
                )
                row = cursor.fetchone()
                return row["result_text"] if row else None

    @staticmethod
    def claim_or_get(*, run_id: str, langchain_tool_call_id: str, tool_ref: str) -> tuple[str, str | None]:
        """한 호출의 실행권을 원자적으로 확보한다.

        ``CLAIMED``면 호출자가 실행하고, ``SUCCEEDED``면 저장 결과를 재생하며,
        ``RUNNING``이면 다른 요청이 같은 호출을 실행 중이다. 만료된 lease는
        현재 호출이 가져가므로 프로세스가 죽어도 영구 대기가 생기지 않는다.
        """
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO tool_call_idempotency
                        (run_id, langchain_tool_call_id, tool_ref, status,
                         result_text, lease_until, updated_at)
                    VALUES (%s, %s, %s, 'RUNNING', NULL,
                            now() + make_interval(secs => %s), now())
                    ON CONFLICT (run_id, langchain_tool_call_id) DO NOTHING
                    RETURNING status
                    """,
                    (run_id, langchain_tool_call_id, tool_ref, IDEMPOTENCY_LEASE_SECONDS),
                )
                if cursor.fetchone():
                    return "CLAIMED", None

                cursor.execute(
                    """
                    SELECT status, result_text, lease_until
                      FROM tool_call_idempotency
                     WHERE run_id = %s AND langchain_tool_call_id = %s
                     FOR UPDATE
                    """,
                    (run_id, langchain_tool_call_id),
                )
                row = cursor.fetchone()
                if row and row["status"] == "SUCCEEDED":
                    return "SUCCEEDED", row["result_text"]
                cursor.execute(
                    """
                    UPDATE tool_call_idempotency
                       SET tool_ref = %s, status = 'RUNNING', result_text = NULL,
                           lease_until = now() + make_interval(secs => %s),
                           updated_at = now()
                     WHERE run_id = %s AND langchain_tool_call_id = %s
                       AND (status <> 'RUNNING' OR lease_until IS NULL OR lease_until <= now())
                    RETURNING status
                    """,
                    (tool_ref, IDEMPOTENCY_LEASE_SECONDS, run_id, langchain_tool_call_id),
                )
                return ("CLAIMED", None) if cursor.fetchone() else ("RUNNING", None)

    @staticmethod
    def abandon_claim(*, run_id: str, langchain_tool_call_id: str) -> None:
        """실패한 실행의 RUNNING claim만 지워 즉시 재시도할 수 있게 한다."""
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM tool_call_idempotency
                     WHERE run_id = %s AND langchain_tool_call_id = %s
                       AND status = 'RUNNING'
                    """,
                    (run_id, langchain_tool_call_id),
                )

    @staticmethod
    def record_result(
        *, run_id: str, langchain_tool_call_id: str, tool_ref: str, result: str
    ) -> None:
        """이미 있으면 아무것도 하지 않는다(`DO NOTHING`) — 처음 성공한 실행의
        결과가 기준이다. 동시에 두 실행이 같은 tool_call_id로 경합해도(이론상
        같은 run_id 안에서는 재개가 순차적이라 실제로는 거의 일어나지 않는다)
        나중에 쓰는 쪽이 먼저 쓴 값을 덮어써서 모델이 서로 다른 두 시점에
        다른 결과를 보는 일은 없다.
        """
        text = result[:IDEMPOTENCY_RESULT_MAX_CHARS]
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO tool_call_idempotency
                        (run_id, langchain_tool_call_id, tool_ref, status,
                         result_text, lease_until, updated_at)
                    VALUES (%s, %s, %s, 'SUCCEEDED', %s, NULL, now())
                    ON CONFLICT (run_id, langchain_tool_call_id) DO UPDATE
                       SET status = 'SUCCEEDED', result_text = EXCLUDED.result_text,
                           lease_until = NULL, updated_at = now()
                     WHERE tool_call_idempotency.status = 'RUNNING'
                    """,
                    (run_id, langchain_tool_call_id, tool_ref, text),
                )


#: `mcp_call_note.kind` 값. 표 주석(DB/schema.sql)과 같은 뜻이다.
MCP_CALL_ACTIVE = "ACTIVE"
MCP_CALL_TIMED_OUT = "TIMED_OUT"


class McpCallNoteRepository:
    """승인 카드 경고의 재료(2026-08-21, 병렬실행 Phase 3).

    정본: `docs/설계 및 구현/3_중간발표 이후/작업기록/Deep_Agents/2026-08-21_04_MCP_동시_쓰기_경고_설계.md`,
    `..._03_외부_Write_Tool_재시도_안전성.md` §4.2.

    **여기서 하는 일은 전부 "짧게 쓰고 바로 끝"이다.** 락을 쥔 채 기다리는
    코드가 하나도 없다 — 그게 이 설계가 advisory lock 직렬화를 대체한
    이유다(표 주석 참고). 오래 도는 MCP 호출이 DB 커넥션을 붙잡지 않는다.
    """

    @staticmethod
    def begin_active(
        *, run_id: str, langchain_tool_call_id: str, tool_ref: str, team_id: str
    ) -> None:
        """MCP 호출이 시작됐다고 표시한다.

        `mcp_server_id`는 별도 왕복 없이 같은 INSERT 안에서 찾는다. 못 찾으면
        (등록이 지워진 도구 등) `mcp_server_id`가 NULL인 행이 들어간다 —
        경고 조회는 서버가 같을 때만 걸리므로 NULL 행은 아무에게도 경고를
        띄우지 않고, 실행 자체를 막지도 않는다.

        같은 (run_id, tool_call_id)가 다시 오면(HITL resume 등) 아무것도 하지
        않는다 — 이미 표시된 것이다.
        """
        mcp_tool_id = tool_ref.removeprefix("mcp:")
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO mcp_call_note
                        (run_id, langchain_tool_call_id, kind, tool_ref, mcp_server_id, team_id)
                    SELECT %s, %s, %s, %s,
                           (SELECT t.server_id FROM mcp_tool AS t WHERE t.mcp_tool_id = %s),
                           %s
                    ON CONFLICT (run_id, langchain_tool_call_id, kind) DO NOTHING
                    """,
                    (
                        run_id,
                        langchain_tool_call_id,
                        MCP_CALL_ACTIVE,
                        tool_ref,
                        mcp_tool_id,
                        team_id,
                    ),
                )

    @staticmethod
    def end_active(*, run_id: str, langchain_tool_call_id: str) -> None:
        """MCP 호출이 끝났다고 표시한다(성공·실패 무관).

        **timeout이 나도 이 함수는 그 호출의 진짜 끝에 불린다** — 우리
        timeout 미들웨어는 기다리기를 포기할 뿐 스레드를 못 죽이므로, 백그라운드
        에서 계속 돌던 handler가 실제로 끝날 때 자기 ACTIVE 행을 지운다. 그래야
        우리가 포기한 뒤에도 "지금 도는 중" 표시가 정확하게 유지된다.
        `TIMED_OUT` 행은 건드리지 않는다(kind로 갈라져 있다).
        """
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM mcp_call_note
                     WHERE run_id = %s AND langchain_tool_call_id = %s AND kind = %s
                    """,
                    (run_id, langchain_tool_call_id, MCP_CALL_ACTIVE),
                )

    @staticmethod
    def record_timeout(
        *, run_id: str, langchain_tool_call_id: str, tool_ref: str, team_id: str
    ) -> None:
        """timeout으로 **결과를 확인하지 못한** 호출을 남긴다. 안 지운다.

        timeout은 "실패했다"가 아니라 "결과를 모른다"는 뜻이라(스레드가 계속
        돌고 있어 뒤늦게 성공할 수 있다), 모델이 같은 작업을 새 tool_call_id로
        재시도하면 중복 실행이 날 수 있다. 그 재시도의 승인 카드에 경고를
        띄우는 게 이 행의 용도다(`2026-08-21_03` §4.2).
        """
        mcp_tool_id = tool_ref.removeprefix("mcp:")
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO mcp_call_note
                        (run_id, langchain_tool_call_id, kind, tool_ref, mcp_server_id, team_id)
                    SELECT %s, %s, %s, %s,
                           (SELECT t.server_id FROM mcp_tool AS t WHERE t.mcp_tool_id = %s),
                           %s
                    ON CONFLICT (run_id, langchain_tool_call_id, kind) DO NOTHING
                    """,
                    (
                        run_id,
                        langchain_tool_call_id,
                        MCP_CALL_TIMED_OUT,
                        tool_ref,
                        mcp_tool_id,
                        team_id,
                    ),
                )

    @staticmethod
    def has_other_active_on_same_server(
        *,
        tool_ref: str,
        team_id: str,
        exclude_tool_call_ids: tuple[str, ...] = (),
        stale_after_seconds: int,
    ) -> bool:
        """이 도구가 쓸 MCP 서버에 **지금 도는 다른 호출**이 있는지.

        `stale_after_seconds`보다 오래된 행은 무시한다 — 프로세스가 죽는 등으로
        `end_active()`가 못 돌면 ACTIVE 행이 영원히 남는데, 별도 정리 작업을
        두지 않고 조회 시점에 거른다. 기준값은 호출부가 gunicorn worker
        timeout을 그대로 넘긴다(그보다 오래 "실행 중"인 건 실제로는 이미 죽은
        실행이 남긴 찌꺼기다).

        `exclude_tool_call_ids`로 자기 자신(과 같은 배치의 형제)을 뺀다.

        같은 팀 안에서만 본다 — 남의 팀 실행을 보고 경고하지 않는다.
        """
        mcp_tool_id = tool_ref.removeprefix("mcp:")
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT 1
                      FROM mcp_call_note AS n
                     WHERE n.kind = %s
                       AND n.team_id = %s
                       AND n.mcp_server_id IS NOT NULL
                       AND n.mcp_server_id = (
                             SELECT t.server_id FROM mcp_tool AS t WHERE t.mcp_tool_id = %s
                           )
                       AND n.started_at > now() - make_interval(secs => %s)
                       AND NOT (n.langchain_tool_call_id = ANY(%s))
                     LIMIT 1
                    """,
                    (
                        MCP_CALL_ACTIVE,
                        team_id,
                        mcp_tool_id,
                        stale_after_seconds,
                        list(exclude_tool_call_ids),
                    ),
                )
                return cursor.fetchone() is not None

    @staticmethod
    def server_ids_for_tool_refs(tool_refs: tuple[str, ...]) -> dict[str, str]:
        """`mcp:<tool_id>` 목록 → `{tool_ref: mcp_server_id}`.

        **한 번의 왕복으로 여러 개를 푼다** — 같은 배치(한 AIMessage)에 걸린
        MCP 호출들이 서로 같은 서버를 쓰는지 보려면 전부의 서버를 알아야
        하는데, 하나씩 조회하면 승인 카드를 그릴 때마다 왕복이 호출 수만큼
        늘어난다(`2026-08-21_04` §3.2).

        못 찾은 tool_ref는 결과에 아예 안 들어간다(KeyError로 터뜨리지 않고
        호출부가 "서버를 모른다"로 다루게 한다).
        """
        if not tool_refs:
            return {}
        by_tool_id = {ref.removeprefix("mcp:"): ref for ref in tool_refs}
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT mcp_tool_id, server_id
                      FROM mcp_tool
                     WHERE mcp_tool_id = ANY(%s)
                    """,
                    (list(by_tool_id),),
                )
                rows = cursor.fetchall()
        return {by_tool_id[row["mcp_tool_id"]]: row["server_id"] for row in rows}

    @staticmethod
    def has_timeout_in_run(*, run_id: str, tool_ref: str) -> bool:
        """이 run에서 같은 `tool_ref`가 timeout으로 끝난 적 있는지.

        판단 기준을 `tool_ref` 하나로 좁힌 이유(입력값 유사도까지 비교하지
        않는 이유)는 `2026-08-21_03` §4.2 — args 비교는 "제목이 한 글자만
        달라도 다른 요청인가" 같은 모호한 판단이 필요해 오탐·누락이 쉽다.
        거칠지만 확실한 사실만 보여주고 판단은 사람이 한다.
        """
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT 1 FROM mcp_call_note
                     WHERE run_id = %s AND tool_ref = %s AND kind = %s
                     LIMIT 1
                    """,
                    (run_id, tool_ref, MCP_CALL_TIMED_OUT),
                )
                return cursor.fetchone() is not None


def _resolve_session_agent(cursor, *, agent_id: str, team_id: str, account_id: str) -> str:
    """대화를 열 에이전트의 지금 발행 중인 버전(`agents.current_version_id`)을
    돌려준다.

    DRAFT는 만든 사람 본인만 대화를 열 수 있다(2026-08-18) — 남의 DRAFT는
    team_id가 같아도 막는다.
    """

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
        # ACTIVE도 아니고 본인 DRAFT도 아니면 대화를 열 수 없다.
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
                    "SELECT name AS agent_name FROM agents WHERE agent_id = %s", (agent_id,)
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
                           -- LEFT JOIN 이다 — 에이전트가 지워져도 대화 목록은
                           -- 떠야 한다(그때 이름은 NULL, 화면이 agent_id를 보여준다).
                           av.name AS agent_name
                    FROM chat_session AS s
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
    def rename(*, session_id: str, account_id: str, title: str) -> dict[str, Any]:
        """개인 대화의 제목을 바꾼다.

        같은 팀은 링크로 대화를 읽을 수 있지만 목록과 사용자 설정은 개인
        영역이다. 따라서 도구 override와 마찬가지로 소유자만 수정한다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                _require_team(cursor, account_id)
                cursor.execute(
                    "SELECT account_id FROM chat_session WHERE session_id::text = %s",
                    (session_id,),
                )
                owner = cursor.fetchone()
                if owner is None:
                    raise RecordNotFound(f"존재하지 않는 대화입니다: {session_id}")
                if owner["account_id"] != account_id:
                    raise PermissionDenied("이 대화를 수정할 수 없습니다.")

                cursor.execute(
                    """
                    UPDATE chat_session SET title = %s, updated_at = now()
                    WHERE session_id::text = %s
                    RETURNING session_id::text, team_id, account_id, agent_id,
                              agent_version_id, proj_id, title, tool_refs_override,
                              created_at, updated_at
                    """,
                    (title, session_id),
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

        **LangGraph 체크포인트는 반대로 같이 지운다**(2026-08-19). 새 엔진은
        `thread_id` 를 이 `session_id` 로 쓰고, `checkpoint_blobs` 에는 그 대화의
        메시지·도구 호출·승인 대기 상태가 그대로 들어 있다 — 안 지우면 사용자가
        「대화를 지웠다」고 생각하는 동안 본문이 DB 에 남는다. 실행 로그와 성격이
        다르다: 그쪽은 "무엇을 몇 번 돌렸나"라 남길 이유가 있지만, 이쪽은 대화
        내용 자체다.

        **`chat_session` 보다 먼저 지운다.** 순서가 이 함수의 정확성이다 — 운영자
        콘솔의 완전 삭제(`_TEAM_PURGE_STEPS`)도 `chat_session` 을 타고 thread_id 를
        찾으므로, 여기서 남긴 행은 팀을 통째로 지워도 사라지지 않는다. 실제로
        그렇게 고아가 된 행이 282개 있었다(2026-08-19 실측, 대화 7개분).

        완전 삭제 쪽과 달리 `::text` 캐스트가 없다 — 거기는 `chat_session` 의
        `uuid` 컬럼을 골라 `text` 인 `thread_id` 와 맞춰야 하지만, 여기서는
        `session_id` 가 URL 에서 온 문자열이라 그대로 맞는다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                _require_session(cursor, session_id=session_id, account_id=account_id)
                cursor.execute(
                    "DELETE FROM chat_message WHERE session_id::text = %s", (session_id,)
                )
                # 세 문장을 풀어 쓴다 — `DELETE FROM checkpoint` 로 grep 했을 때
                # 이 자리가 안 걸려서 결함을 못 봤다.
                cursor.execute(
                    "DELETE FROM checkpoint_writes WHERE thread_id = %s", (session_id,)
                )
                cursor.execute(
                    "DELETE FROM checkpoint_blobs WHERE thread_id = %s", (session_id,)
                )
                cursor.execute("DELETE FROM checkpoints WHERE thread_id = %s", (session_id,))
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
                      AND EXISTS (
                          SELECT 1
                            FROM agent_run
                           WHERE run_id::text = content->>'run_id'
                             AND status = 'PENDING'
                      )
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
                    # 에이전트 허용 목록에서 빼 주던 DELETE가 여기 있었다(레거시
                    # `agent_tool`). 2026-08-22에 레거시 스키마를 폐기하면서
                    # 지웠다 — 신규 `agent_version_tools`는 발행된 버전의 일부라
                    # 불변이고(02 §5.2), 그 자리에서 지울 수 없다. 대신 실행
                    # 시점에 없는 MCP 도구를 건너뛴다
                    # (`services/agent_runtime/tools/loader.py`).
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
                # 에이전트 허용 목록에서 빼 주던 DELETE가 여기 있었다(레거시
                # `agent_tool`). `update()`와 같은 이유로 2026-08-22에 지웠다 —
                # 없는 도구는 실행 시점에 걸러진다.
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
    """빌더 편집 화면이 쓰는 도구 카탈로그 조회."""

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

    #: `task.src_type` 허용값(스키마 주석). 추출-승인 흐름은 `EXTRACTED`,
    #: 사용자가 새 업무를 직접 등록하면 `USER_ADDED`.
    _SRC_TYPES = frozenset({"EXTRACTED", "USER_ADDED", "AI_SUGGESTED_MISSING_TASK"})

    @staticmethod
    def register(
        *,
        proj_id: str,
        account_id: str,
        tasks: list[dict[str, Any]],
        src_type: str = "EXTRACTED",
    ) -> dict[str, Any]:
        if not tasks:
            raise RepositoryError("등록할 업무가 없습니다.")
        if src_type not in ProjectTaskRepository._SRC_TYPES:
            src_type = "EXTRACTED"

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

                # **이 프로젝트의 판에 덧붙인다.** 판을 매번 새로 만들지 않는다
                # (2026-08-19 PM 결정 ⓐ) — `list_for_project`가 가장 최근 판만
                # 보여주기 때문에, 「3건만 추가로 등록해줘」에 새 판이 생기면 앞서
                # 등록한 15건이 통째로 화면에서 사라졌다. 데이터는 남아 있는데
                # 보이지 않는 것이라 더 나빴다.
                cursor.execute(
                    """
                    SELECT model_id, model_ver FROM proj_know_model
                    WHERE proj_id = %s ORDER BY generated_at DESC NULLS LAST LIMIT 1
                    """,
                    (proj_id,),
                )
                current = cursor.fetchone()
                if current is None:
                    model_id = next_short_code(
                        cursor, table="proj_know_model", column="model_id", prefix="KM"
                    )
                    cursor.execute(
                        """
                        INSERT INTO proj_know_model (model_id, proj_id, model_ver, status, generated_at)
                        VALUES (%s, %s, 'v1', 'READY', now())
                        """,
                        (model_id, proj_id),
                    )
                else:
                    model_id = current["model_id"]

                # 덧붙이는 이상 **같은 업무가 두 번 들어올 수 있다** — 다시 뽑아
                # 다시 등록하면 제목이 겹친다. 제목으로 거르고, 거른 사실을
                # 돌려준다(`dropped_fields`와 같은 원칙: 조용히 넘기지 않는다).
                cursor.execute(
                    "SELECT task_name FROM task WHERE model_id = %s", (model_id,)
                )
                existing = {row["task_name"] for row in cursor.fetchall()}

                created = []
                dropped_fields = []
                already = []
                for task in tasks:
                    if task["title"] in existing:
                        already.append(task["title"])
                        continue
                    existing.add(task["title"])
                    task_id = next_short_code(
                        cursor, table="task", column="task_id", prefix="TK"
                    )
                    # 저장할 값을 먼저 만든 다음, 「모델이 준 것」과 「실제로 남은
                    # 것」을 나란히 놓고 비운 칸을 센다.
                    start_at = _date_or_none(task.get("start_date"))
                    due_at = _date_or_none(task.get("due_date"))
                    effort = _positive_or_none(task.get("effort_hours"))
                    req_role = _positive_or_none(task.get("required_role"))
                    priority = _positive_or_none(task.get("priority"))
                    # `given not in (None, "")` 이지 `if given` 이 아니다 —
                    # **모델이 모르는 공수를 채워 넣는 값이 하필 `0`** 이라
                    # (`_positive_or_none` docstring), 거짓으로 판정하면 정작
                    # 알려야 할 그 경우가 통째로 빠진다. 2026-08-18 에 실제로
                    # 그랬다: 15건 전부 `effort_hours: 0` 으로 왔고 전부 NULL 로
                    # 저장됐는데, 모델은 「0시간으로 등록했습니다」라고 답했다.
                    blank = [
                        label
                        for label, given, kept in (
                            ("시작일", task.get("start_date"), start_at),
                            ("마감일", task.get("due_date"), due_at),
                            ("공수", task.get("effort_hours"), effort),
                            ("담당 역할", task.get("required_role"), req_role),
                            ("우선순위", task.get("priority"), priority),
                        )
                        if given not in (None, "") and kept is None
                    ]
                    if blank:
                        dropped_fields.append({"title": task["title"], "fields": blank})
                    cursor.execute(
                        """
                        INSERT INTO task (task_id, model_id, task_name, req_role, effort,
                                          start_at, due_at, priority, src_type, status)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'PROPOSED')
                        """,
                        (
                            task_id, model_id, task["title"], req_role,
                            effort, start_at, due_at, priority, src_type,
                        ),
                    )
                    created.append({"task_id": task_id, "title": task["title"]})

        return {
            "model_id": model_id,
            "tasks": created,
            # 비운 것을 조용히 넘기지 않는다. 모델이 이것을 사람에게 옮겨 적는다.
            #
            # 예전 이름은 `dropped_dates` 였고 **날짜만** 담았다. 같은 이유로
            # 비우는 칸이 셋 더 있는데(공수·역할·우선순위 — `_positive_or_none`)
            # 그쪽은 조용히 넘어갔다. 2026-08-18 에 그 대가를 봤다.
            "dropped_fields": dropped_fields,
            # 이미 있어서 건너뛴 것. 사람에게 「등록했다」고만 말하면 안 된다.
            "already_registered": already,
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


class GuardrailProviderRepository:
    """외부 가드레일 공급자 등록(`guardrail_provider`).

    **`McpServerRepository` 와 같은 모양이다** — 팀 소유이고, 비밀값은 Fernet 으로
    암호화해서만 저장하며(`apps/connectors` 의 것을 그대로 쓴다), 등록 직후는
    `UNCHECKED` 라 「연결 확인」을 눌러야 `CONNECTED` 가 된다.

    **읽기는 팀이, 쓰기는 운영자가 부른다**(2026-08-18 멘토링, MCP 와 같은 판단) —
    붙이려면 주소와 키를 알아야 하는데 「코딩 없이」를 내세운 제품이 비개발자에게
    요구할 일이 아니다.

    **여러 개 등록하고 그중 하나만 쓴다**(2026-08-20). 합치는 게 아니라 **고르는**
    것이라 「어느 것이 먼저 도는가」를 정할 필요가 없다. 「팀당 활성 하나」는
    부분 UNIQUE(`ux_guardrail_provider_active`)가 DB 에서 강제한다 — 코드에서만
    지키면 동시에 두 번 활성화했을 때 둘 다 활성이 된다.
    """

    KINDS = ("OPENAI_GUARDRAILS", "BEDROCK_GUARDRAILS", "AZURE_CONTENT_SAFETY")
    STATUSES = ("UNCHECKED", "CONNECTED", "ERROR")
    #: 가드레일에 닿지 못했을 때 **그 팀이** 무엇을 할지(화면: 「연결 실패 시」 →
    #: 「대화 계속」·「대화 차단」). 우리가 일괄로 정하지
    #: 않는다 — 사내 도구면 통과가 맞고, 규제 고객에게는 「검사 못 했는데 그냥
    #: 보냈다」가 계약 위반이 된다.
    ON_FAILURE = ("OPEN", "CLOSED")

    @staticmethod
    def list_all() -> list[dict[str, Any]]:
        """모든 팀의 등록분. **운영자 콘솔만 쓴다.**"""

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT g.provider_id, g.team_id, t.name AS team_name, g.name, g.kind,
                           g.config, g.status, g.is_active, g.last_checked_at,
                           g.created_by, g.created_at,
                           (g.credential_enc IS NOT NULL) AS has_credential
                    FROM guardrail_provider AS g
                    LEFT JOIN team AS t ON t.team_id = g.team_id
                    ORDER BY g.team_id, g.is_active DESC, g.created_at
                    """
                )
                return list(cursor.fetchall())

    @staticmethod
    def for_team(team_id: str) -> dict[str, Any] | None:
        """그 팀이 쓸 공급자. 런타임이 부른다 — 없으면 `None`(검사 없이 돈다).

        **활성인 것만 돌려준다.** 등록만 해 둔 것(보관·교체 대기)을 부르면 그 팀의
        대화가 쓰지 않기로 한 가드레일을 거친다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT g.provider_id, g.team_id, g.name, g.kind, g.config, g.status,
                           g.last_checked_at,
                           -- **팀의 정책이지 등록물의 속성이 아니다**(2026-08-24).
                           -- 등록에 붙여 뒀더니 공급자를 갈아탈 때 조용히 바뀌었다.
                           COALESCE(t.guardrail_on_failure, 'OPEN') AS on_failure
                    FROM guardrail_provider AS g
                    LEFT JOIN team AS t ON t.team_id = g.team_id
                    WHERE g.team_id = %s AND g.is_active
                    """,
                    (team_id,),
                )
                return cursor.fetchone()

    @staticmethod
    def credential(provider_id: str) -> dict[str, Any] | None:
        """복호화한 비밀값. **호출 직전에만 부른다** — 목록·응답에는 절대 안 실린다."""

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT credential_enc FROM guardrail_provider WHERE provider_id = %s",
                    (provider_id,),
                )
                row = cursor.fetchone()

        if row is None or not row["credential_enc"]:
            return None
        try:
            return decrypt_credential(row["credential_enc"])
        except OAuthError:
            # 키가 바뀌어 복호화가 안 되는 경우. 부르는 쪽이 「자격증명 없음」으로
            # 다루도록 None 을 준다 — 여기서 예외를 내면 대화가 끊긴다.
            return None

    @staticmethod
    def create(
        *,
        team_id: str,
        name: str,
        kind: str,
        config: dict[str, Any],
        credential: dict[str, Any] | None,
        registered_by: str,
        status: str = "UNCHECKED",
    ) -> dict[str, Any]:
        """등록한다.

        `status` 는 **부르는 쪽이 실제로 확인한 결과**여야 한다. 화면이 「확인했다」고
        말한 것을 그대로 믿으면, 확인 없이 CONNECTED 인 행이 생기고 그 팀의 대화는
        안 되는 가드레일을 계속 부른다 — 뷰가 저장 직전에 다시 확인한다.
        """

        if kind not in GuardrailProviderRepository.KINDS:
            raise RepositoryError(f"알 수 없는 가드레일 종류입니다: {kind}")
        if status not in GuardrailProviderRepository.STATUSES:
            raise RepositoryError(f"알 수 없는 상태입니다: {status}")
        with database_connection() as connection:
            with connection.cursor() as cursor:
                # 활성인 것이 아직 없고 이번 등록이 붙는 것이면 바로 활성으로 둔다.
                # 등록했는데 아무 일도 안 일어나면 「등록했으니 도는 것」이라는
                # 기대와 어긋난다 — 두 번째부터는 사람이 골라야 한다.
                cursor.execute(
                    "SELECT 1 FROM guardrail_provider WHERE team_id = %s AND is_active",
                    (team_id,),
                )
                activate = cursor.fetchone() is None and status == "CONNECTED"

                provider_id = next_short_code(
                    cursor, table="guardrail_provider", column="provider_id", prefix="GP"
                )
                cursor.execute(
                    """
                    INSERT INTO guardrail_provider
                        (provider_id, team_id, name, kind, config, credential_enc,
                         status, is_active, last_checked_at, created_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                            CASE WHEN %s = 'UNCHECKED' THEN NULL ELSE now() END, %s)
                    RETURNING provider_id, team_id, name, kind, config, status, is_active,
                              last_checked_at, created_by, created_at
                    """,
                    (
                        provider_id,
                        team_id,
                        name,
                        kind,
                        Jsonb(config or {}),
                        encrypt_credential(credential) if credential else None,
                        status,
                        activate,
                        status,
                        registered_by,
                    ),
                )
                # `has_credential` 을 붙여 돌려준다 — RETURNING 에 없다고 빼면 화면이
                # 「자격증명 없음」으로 그린다(MCP 에서 실제로 그랬다).
                return {**cursor.fetchone(), "has_credential": credential is not None}

    @staticmethod
    def update(
        *,
        provider_id: str,
        name: str,
        kind: str,
        config: dict[str, Any],
        credential: dict[str, Any] | None,
        replace_credential: bool,
        status: str = "UNCHECKED",
    ) -> dict[str, Any]:
        """고친다.

        **자격증명은 안 보내면 그대로 둔다.** 화면이 저장된 값을 다시 보여주지
        않으므로, 안 보낸 것을 「지우라」로 읽으면 이름만 고쳐도 키가 날아간다
        (MCP 의 `replace_token` 과 같은 규칙). 지우려면 `replace_credential=True`
        와 빈 값을 함께 보낸다.

        **내용이 바뀌면 상태를 `UNCHECKED` 로 되돌린다.** 주소·키가 달라졌는데
        이전 「연결 확인」 결과를 그대로 두면, 화면은 CONNECTED 인데 실제로는 안
        붙는다(MCP 가 주소를 바꿀 때 도구 목록을 비우는 것과 같은 이유).
        """

        if kind not in GuardrailProviderRepository.KINDS:
            raise RepositoryError(f"알 수 없는 가드레일 종류입니다: {kind}")
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT kind, config FROM guardrail_provider WHERE provider_id = %s FOR UPDATE",
                    (provider_id,),
                )
                before = cursor.fetchone()
                if before is None:
                    raise RecordNotFound("등록되지 않은 가드레일입니다.")

                changed = (
                    before["kind"] != kind
                    or before["config"] != (config or {})
                    or replace_credential
                )

                if replace_credential:
                    cursor.execute(
                        """
                        UPDATE guardrail_provider
                        SET name = %s, kind = %s, config = %s, credential_enc = %s,
                            status = %s,
                            last_checked_at = CASE WHEN %s = 'UNCHECKED' THEN NULL ELSE now() END
                        WHERE provider_id = %s
                        RETURNING provider_id, team_id, name, kind, config, status, is_active,
                                  last_checked_at, created_by, created_at,
                                  (credential_enc IS NOT NULL) AS has_credential
                        """,
                        (
                            name,
                            kind,
                            Jsonb(config or {}),
                            encrypt_credential(credential) if credential else None,
                            status,
                            status,
                            provider_id,
                        ),
                    )
                else:
                    cursor.execute(
                        """
                        UPDATE guardrail_provider
                        SET name = %s, kind = %s, config = %s,
                            status = CASE WHEN %s THEN %s ELSE status END,
                            last_checked_at = CASE WHEN %s THEN
                                (CASE WHEN %s = 'UNCHECKED' THEN NULL ELSE now() END)
                                ELSE last_checked_at END
                        WHERE provider_id = %s
                        RETURNING provider_id, team_id, name, kind, config, status, is_active,
                                  last_checked_at, created_by, created_at,
                                  (credential_enc IS NOT NULL) AS has_credential
                        """,
                        (name, kind, Jsonb(config or {}), changed, status, changed, status, provider_id),
                    )
                return cursor.fetchone()

    @staticmethod
    def set_status(*, provider_id: str, status: str) -> dict[str, Any]:
        """「연결 확인」 결과를 남긴다."""

        if status not in GuardrailProviderRepository.STATUSES:
            raise RepositoryError(f"알 수 없는 상태입니다: {status}")

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE guardrail_provider
                    SET status = %s, last_checked_at = now()
                    WHERE provider_id = %s
                    RETURNING provider_id, team_id, name, kind, config, status, is_active,
                              last_checked_at, created_by, created_at,
                              (credential_enc IS NOT NULL) AS has_credential
                    """,
                    (status, provider_id),
                )
                row = cursor.fetchone()
                if row is None:
                    raise RecordNotFound("등록되지 않은 가드레일입니다.")
                return row

    @staticmethod
    def on_failure_for_team(team_id: str) -> str:
        """가드레일에 닿지 못했을 때 이 팀이 무엇을 할지. 등록이 없어도 답이 있다."""

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT guardrail_on_failure FROM team WHERE team_id = %s",
                    (team_id,),
                )
                row = cursor.fetchone()
        return (row or {}).get("guardrail_on_failure") or "OPEN"

    @staticmethod
    def set_on_failure(*, team_id: str, on_failure: str) -> dict[str, Any]:
        """그 팀의 정책을 바꾼다.

        **등록물이 아니라 팀에 붙인다**(2026-08-24). 등록에 붙여 뒀더니 공급자를
        갈아탈 때(키 교체·비교·시연) 정책이 조용히 함께 바뀌었다.
        """

        if on_failure not in GuardrailProviderRepository.ON_FAILURE:
            raise RepositoryError(f"알 수 없는 미응답 처리 방식입니다: {on_failure}")

        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE team SET guardrail_on_failure = %s WHERE team_id = %s
                    RETURNING team_id, guardrail_on_failure AS on_failure
                    """,
                    (on_failure, team_id),
                )
                row = cursor.fetchone()
                if row is None:
                    raise RecordNotFound("없는 팀입니다.")
                return row

    @staticmethod
    def set_active_for_team(*, team_id: str, provider_id: str | None) -> dict[str, Any] | None:
        """그 팀이 **무엇을 쓸지** 정한다. `None` 이면 아무것도 안 쓴다.

        **팀 단위로 받는다** — 「이 등록을 켠다」가 아니라 「이 팀은 이것을 쓴다」다.
        기본 채팅 모델(`AgentRepository.main_model_for_team`)과 같은 모양이고, 그래서
        고르는 자리도 같다(팀 상세).

        **붙지 않는 것은 고를 수 없다.** 「연결 확인」을 통과하지 않은 것을 쓰게 두면
        그 팀의 대화가 매번 실패하는 검사를 거치고, 화면만 「사용 중」이라고 말한다.

        한 트랜잭션에서 내리고 올린다 — 부분 UNIQUE 가 「팀당 활성 하나」를 강제하므로
        나눠서 하면 중간에 둘 다 활성인 순간이 생겨 실패한다.
        """

        with database_connection() as connection:
            with connection.cursor() as cursor:
                if provider_id is not None:
                    cursor.execute(
                        """
                        SELECT team_id, status FROM guardrail_provider
                        WHERE provider_id = %s FOR UPDATE
                        """,
                        (provider_id,),
                    )
                    row = cursor.fetchone()
                    if row is None:
                        raise RecordNotFound("등록되지 않은 가드레일입니다.")
                    if row["team_id"] != team_id:
                        raise RecordNotFound("이 팀에 등록된 가드레일이 아닙니다.")
                    if row["status"] != "CONNECTED":
                        raise RepositoryError("연결 확인을 통과한 가드레일만 사용할 수 있습니다.")

                cursor.execute(
                    "UPDATE guardrail_provider SET is_active = FALSE WHERE team_id = %s AND is_active",
                    (team_id,),
                )
                if provider_id is None:
                    return None

                cursor.execute(
                    """
                    UPDATE guardrail_provider SET is_active = TRUE WHERE provider_id = %s
                    RETURNING provider_id, team_id, name, kind, config, status, is_active,
                              last_checked_at, created_by, created_at,
                              (credential_enc IS NOT NULL) AS has_credential
                    """,
                    (provider_id,),
                )
                return cursor.fetchone()

    @staticmethod
    def delete(*, provider_id: str) -> dict[str, Any]:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM guardrail_provider WHERE provider_id = %s
                    RETURNING provider_id, team_id, name, kind, is_active
                    """,
                    (provider_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    raise RecordNotFound("등록되지 않은 가드레일입니다.")
                return row
