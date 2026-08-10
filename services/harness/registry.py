"""Tool Registry — 에이전트가 부를 수 있는 도구를 모으고 거른다.

`tool_ref` 는 `agent_tool.tool_ref` 에 저장되는 값 그대로다. 내장 도구는
식별자 자체(`document_search`), MCP 도구는 `mcp:<mcp_tool_id>` 다
(DB/migrations/2026-08-11_agent_platform.sql 주석).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Callable

from backend.db import AccountRepository, ExistTaskRepository, TeamRepository
from backend.db.agent_platform import AgentRepository
from backend.db.document_pipeline import PipelineDocumentRepository, VectorSearchRepository
from backend.services.hr import list_absences, list_capacity_profiles
from services.document_pipeline.runpod_client import embed_queries
from services.workload import calculator


@dataclass(frozen=True)
class Tool:
    ref: str
    name: str
    description: str
    #: JSON Schema. 모델에게 그대로 넘긴다.
    input_schema: dict[str, Any]
    handler: Callable[..., Any]
    #: 외부 시스템을 바꾸는가. True 면 Runner 가 승인 전에 실행하지 않는다
    #: (8/11 확정 ③).
    side_effect: bool = False


class ToolNotAllowed(Exception):
    """에이전트에게 허용되지 않은 도구를 부르려 함."""


# ---------------------------------------------------------------------------
# 내장 도구 2종
# ---------------------------------------------------------------------------


def _document_search(*, team_id: str, query: str, top_k: int = 10) -> dict[str, Any]:
    """팀 문서에서 근거 문장을 찾는다.

    지금은 기존 청크 임베딩 경로(`vec_idx`)를 그대로 쓴다. 단계 5 에서 앞단에
    `doc_meta.summary_vec` 로 문서를 먼저 좁히는 coarse 단계가 붙는다 — 이
    함수의 입출력 모양은 그대로 두고 안쪽만 바뀐다.
    """

    doc_ids = PipelineDocumentRepository.searchable_doc_ids(team_id)
    if not doc_ids:
        return {"query": query, "evidence": [], "note": "팀에 검색할 문서가 없습니다."}

    vector = embed_queries([query])[0]
    rows = VectorSearchRepository.search(
        team_id=team_id, document_ids=doc_ids, query_vector=vector, top_k=top_k
    )
    return {
        "query": query,
        "evidence": [
            {
                "chunk_id": str(row["chunk_id"]),
                "doc_id": row["doc_id"],
                "heading_path": row["heading_path"],
                "text": row["text"],
                "retrieval_score": float(row["retrieval_score"]),
            }
            for row in rows
        ],
    }


def _workload_report(*, account_id: str, weeks: int = 4) -> dict[str, Any]:
    """팀원별 주간 부하. 계산은 `services/workload/calculator` 가 한다.

    `/api/teams/workload` 화면과 **같은 계산기**를 부른다. 여기서 다시 구현하면
    화면이 말하는 숫자와 에이전트가 말하는 숫자가 갈라진다.
    """

    period_start = date.today()
    period_end = period_start + timedelta(weeks=weeks)

    team_id = AccountRepository.team_id(account_id)
    person_ids = TeamRepository.member_person_ids(team_id)
    profiles = list_capacity_profiles(
        person_ids=person_ids, period_start=period_start, period_end=period_end
    )
    absences = list_absences(
        person_ids=person_ids, period_start=period_start, period_end=period_end
    )
    tasks = ExistTaskRepository.list_for_team(account_id)

    return calculator.calculate(
        period_start=period_start,
        period_end=period_end,
        profiles=profiles,
        absences=absences,
        tasks=tasks,
    ) | {"as_of": datetime.now(UTC).isoformat(), "workload_weeks": weeks}


#: 내장 도구. `tool_ref` 는 agent_tool 에 저장되는 값과 같아야 한다.
BUILTIN_TOOLS: dict[str, Tool] = {
    "document_search": Tool(
        ref="document_search",
        name="문서 검색",
        description="팀에 등록된 문서에서 질의와 관련된 문장을 찾아 근거로 돌려준다.",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "찾고 싶은 내용을 한국어 문장으로"},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 20, "default": 10},
            },
            "required": ["query"],
        },
        handler=_document_search,
    ),
    "workload_report": Tool(
        ref="workload_report",
        name="부하 리포트",
        description="팀원별 주간 업무 시간과 남은 여유를 계산한다.",
        input_schema={
            "type": "object",
            "properties": {
                "weeks": {"type": "integer", "minimum": 1, "maximum": 12, "default": 4},
            },
            "required": [],
        },
        handler=_workload_report,
    ),
}


# ---------------------------------------------------------------------------
# 에이전트별 조립
# ---------------------------------------------------------------------------


def _mcp_tool(row: dict[str, Any]) -> Tool:
    """MCP 도구는 **부작용이 있다고 본다.**

    list_tools 응답에는 그 도구가 읽기만 하는지 쓰는지를 말해 주는 필드가 없다.
    모르는 것을 안전한 쪽으로 가정한다 — 읽기 전용 도구가 확인을 한 번 더 받는
    것은 성가신 정도지만, 쓰기 도구가 승인 없이 도는 것은 남의 Jira 에 이슈를
    만든다. 단계 6 에서 서버별로 표시할 수 있게 되면 그때 좁힌다.
    """

    return Tool(
        ref=row["tool_ref"],
        name=row["name"],
        description=row.get("description") or "",
        input_schema=row.get("input_schema") or {"type": "object", "properties": {}},
        handler=_mcp_not_wired,
        side_effect=True,
    )


def _mcp_not_wired(**_kwargs: Any) -> dict[str, Any]:
    """MCP Client 는 단계 6 이다. 그 전까지 부르면 조용히 성공하지 않고 실패한다."""

    raise NotImplementedError("MCP 도구 호출은 아직 연결되지 않았습니다(단계 6).")


def load_for_agent(*, agent_id: str, team_id: str) -> dict[str, Tool]:
    """이 에이전트가 부를 수 있는 도구.

    `agent_tool` 에 있는 것만 남긴다. 목록에 있는데 실체가 없는 `tool_ref`(예:
    지워진 MCP 도구)는 **조용히 버린다** — 에이전트 하나가 못 쓰는 도구 하나
    때문에 실행 전체가 막힐 이유는 없다. 대신 부르려고 하면 ToolNotAllowed 다.
    """

    allowed = set(AgentRepository.tool_refs(agent_id))
    available: dict[str, Tool] = {
        ref: tool for ref, tool in BUILTIN_TOOLS.items() if ref in allowed
    }
    for row in AgentRepository.mcp_tools(team_id):
        if row["tool_ref"] in allowed:
            available[row["tool_ref"]] = _mcp_tool(row)
    return available


def resolve(tools: dict[str, Tool], tool_ref: str) -> Tool:
    tool = tools.get(tool_ref)
    if tool is None:
        raise ToolNotAllowed(f"이 에이전트에게 허용되지 않은 도구입니다: {tool_ref}")
    return tool
