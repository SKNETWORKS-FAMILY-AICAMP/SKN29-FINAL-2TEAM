"""Tool Registry — 에이전트가 부를 수 있는 도구를 모으고 거른다.

`tool_ref` 는 `agent_tool.tool_ref` 에 저장되는 값 그대로다. 내장 도구는
식별자 자체(`document_search`), MCP 도구는 `mcp:<mcp_tool_id>` 다
(DB/migrations/2026-08-11_agent_platform.sql 주석).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Callable

from apps.connectors.clients import create_jira_issues, search_jira_issues
from backend.db import AccountRepository, ExistTaskRepository, TeamRepository
from backend.db.agent_platform import AgentRepository, McpServerRepository
from backend.db.document_pipeline import (
    DocMetaRepository,
    PipelineDocumentRepository,
    VectorSearchRepository,
)
from backend.services.hr import list_absences, list_capacity_profiles
from services.document_pipeline.runpod_client import embed_queries
from services.mcp import client as mcp_client
from services.task_extraction import extract_tasks_stream
from services.workload import calculator


@dataclass(frozen=True)
class Tool:
    ref: str
    name: str
    description: str
    #: JSON Schema. 모델에게 그대로 넘긴다.
    input_schema: dict[str, Any]
    #: 값을 돌려주거나, **제너레이터면 진행 이벤트를 흘리고 `return` 으로 결과를
    #: 준다.** 몇 분이 걸리는 도구는 후자여야 한다 — 그동안 화면에 보낼 것이
    #: 없으면 사용자는 이게 도는 건지 멈춘 건지 알 수 없다.
    handler: Callable[..., Any]
    #: 외부 시스템을 바꾸는가. True 면 Runner 가 승인 전에 실행하지 않는다
    #: (8/11 확정 ③).
    side_effect: bool = False


class ToolNotAllowed(Exception):
    """에이전트에게 허용되지 않은 도구를 부르려 함."""


# ---------------------------------------------------------------------------
# 내장 도구 2종
# ---------------------------------------------------------------------------


#: coarse 가 남길 문서 수. 이만큼만 청크 검색을 돈다.
#:
#: 팀 문서가 수백 건이 되면 전 문서 청크를 한 벌로 훑는 것이 비싸지고, 관련
#: 없는 문서의 문장이 근거 자리를 잠식한다(업무 추출에서 실제로 겪은 문제 —
#: 다른 사업의 감리 과업지시서가 20자리 중 8자리를 가져갔다).
COARSE_TOP_N = 5


def _document_search(*, team_id: str, query: str, top_k: int = 10) -> dict[str, Any]:
    """팀 문서에서 근거 문장을 찾는다. **두 단계다**(A안 — 8/11 확정 ⑥).

    1) coarse — `doc_meta.summary_vec` 으로 문서를 먼저 좁힌다. 요약 임베딩은
       문서당 하나뿐이라 팀 문서 전부를 훑어도 싸다.
    2) fine — 좁혀진 문서 안에서만 청크 임베딩을 검색한다.

    coarse 가 고른 문서 중 아직 청크가 없는 것(`search_ready = false`)은 본문
    근거를 낼 수 없다. **그 사실을 결과에 담아 돌려준다** — 조용히 빼면
    에이전트가 "관련 문서가 없다"고 답하는데 실제로는 있는 상태가 된다.

    메타가 아직 없는 팀(파이프라인을 안 돌린 경우)은 예전처럼 팀 문서 전체를
    훑는다. coarse 를 켰다고 기존 동작이 죽으면 안 된다.
    """

    vector = embed_queries([query])[0]
    candidates = DocMetaRepository.coarse_search(
        team_id=team_id, query_vector=vector, top_n=COARSE_TOP_N
    )

    if candidates:
        doc_ids = [row["doc_id"] for row in candidates if row["search_ready"]]
        not_indexed = [
            {"doc_id": row["doc_id"], "file_name": row["file_name"], "summary": row["summary"]}
            for row in candidates
            if not row["search_ready"]
        ]
    else:
        doc_ids = PipelineDocumentRepository.searchable_doc_ids(team_id)
        not_indexed = []

    if not doc_ids:
        return {
            "query": query,
            "evidence": [],
            "candidate_documents": [
                {"doc_id": row["doc_id"], "file_name": row["file_name"], "summary": row["summary"]}
                for row in candidates
            ],
            "not_indexed": not_indexed,
            "note": (
                "요약으로는 관련 있어 보이는 문서를 찾았지만 본문이 아직 색인되지 않아 "
                "문장 근거를 낼 수 없습니다."
                if candidates
                else "팀에 검색할 문서가 없습니다."
            ),
        }

    rows = VectorSearchRepository.search(
        team_id=team_id, document_ids=doc_ids, query_vector=vector, top_k=top_k
    )
    result = {
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
    if not_indexed:
        result["not_indexed"] = not_indexed
        result["note"] = "아래 문서도 관련 있어 보이지만 본문이 아직 색인되지 않았습니다."
    return result


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


def _extract_tasks(*, proj_id: str | None, account_id: str):
    """기준 문서에서 업무를 뽑는다. 기존 `services/task_extraction` 을 그대로 쓴다.

    **제너레이터다.** 안쪽 파이프라인이 4단계 검색 + 1단계 정리라 몇 분이 걸리고,
    그동안 무엇을 찾고 있는지 내보내지 않으면 화면이 멈춘 것과 구별되지 않는다.
    기존 `/tasks/extraction` 화면이 이미 그 진행을 보여 주고 있어서, 여기서 삼키면
    Chat 쪽이 명백히 못한 물건이 된다.

    모델에게 돌려주는 것은 **건수와 경고뿐**이다. 업무 20건과 근거를 통째로
    돌려주면 바깥 모델이 그것을 한 번 더 요약하면서 근거가 흔들리고, 토큰도
    그만큼 든다. 사람이 볼 결과는 이벤트로 나가 chat_message 에 구조화되어
    남는다(8/11 확정 ④).

    기준 문서는 사람이 이미 골라 둔 것(`doc_role='PRIMARY'`)을 쓴다. 모델에게
    문서 id 를 고르게 하지 않는다 — 어느 문서로 뽑았는지가 결과 전체의 전제라
    그건 사람의 결정이어야 한다.
    """

    if not proj_id:
        raise ValueError("어느 프로젝트의 업무를 뽑을지 정해지지 않았습니다. 프로젝트를 먼저 고르세요.")

    documents = PipelineDocumentRepository.list_ready_for_analysis(
        proj_id=proj_id, account_id=account_id
    )
    # `list_ready_for_analysis` 는 팀 문서를 전부 준다. 다른 프로젝트의 기준
    # 문서도 섞여 있으므로 proj_id 까지 봐야 한다.
    primary = next(
        (d for d in documents if d["proj_id"] == proj_id and d["doc_role"] == "PRIMARY"), None
    )
    if primary is None:
        raise ValueError("이 프로젝트의 기준 문서가 아직 지정되지 않았습니다.")
    if not primary["search_ready"]:
        raise ValueError("기준 문서가 아직 파싱·청킹·임베딩되지 않았습니다.")

    ready_ids = [d["doc_id"] for d in documents if d["search_ready"]]
    result = None
    for event in extract_tasks_stream(
        team_id=primary["team_id"], primary_document=primary, document_ids=ready_ids
    ):
        if event["type"] == "result":
            result = event["result"]
        else:
            yield event

    if result is None:
        raise ValueError("업무 추출이 결과 없이 끝났습니다.")

    # 화면이 결과 카드를 그리고, 새로고침 뒤에도 다시 그릴 수 있게 통째로 내보낸다.
    yield {"type": "task_extraction_result", "proj_id": proj_id, "result": result}
    return {
        "task_count": len(result["tasks"]),
        "warnings": result["warnings"],
        "primary_document": primary["file_name"],
    }


def _jira_create_issues(*, account_id: str, project_key: str, issues: list[dict[str, Any]]):
    """확인받은 업무를 Jira 에 등록한다.

    **MCP 가 아니라 내장 도구다.** 자체 Jira MCP 서버를 띄우려면 우리 SSRF
    차단(§4-1)이 같은 호스트 주소를 막고, 공식 Atlassian MCP 는 OAuth 액세스
    토큰을 요구해(실측 2026-08-11: 401 `Bearer realm="OAuth"`) 정적 토큰 하나를
    저장하는 우리 모델로는 한 시간 뒤 끊긴다. 데모의 핵심 흐름을 남의 서비스와
    남의 토큰 수명에 매달 이유가 없다 — Jira Connector 는 이미 붙어 있다.

    MCP 는 「사용자가 자기 서버를 추가로 붙이는」 확장 경로로 남는다.
    """

    return create_jira_issues(account_id=account_id, project_key=project_key, issues=issues)


def _jira_get_issues(*, account_id: str, project_key: str) -> dict[str, Any]:
    return {
        "project_key": project_key,
        "issues": search_jira_issues(account_id=account_id, project_key=project_key),
    }


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
    "task_extraction": Tool(
        ref="task_extraction",
        name="업무 추출",
        description=(
            "이 프로젝트의 기준 문서에서 업무 후보를 뽑고 각 업무에 원문 근거를 붙인다. "
            "문서 id 는 받지 않는다 — 기준 문서는 사람이 미리 골라 둔 것을 쓴다. "
            "몇 분이 걸리므로 사용자가 업무 정리를 요청했을 때만 부른다."
        ),
        input_schema={"type": "object", "properties": {}, "required": []},
        handler=_extract_tasks,
    ),
    "jira_create_issues": Tool(
        ref="jira_create_issues",
        name="Jira 이슈 생성",
        description=(
            "확인받은 업무를 Jira 프로젝트에 이슈로 등록한다. 여러 건을 한 번에 보내고, "
            "건별 성공·실패를 그대로 돌려준다. 사용자 승인 없이는 실행되지 않는다."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "project_key": {"type": "string", "description": "등록할 Jira 프로젝트 키"},
                "issues": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                            "issuetype": {"type": "string", "description": "Task · Story 등"},
                            "assignee_account_id": {"type": "string"},
                            "duedate": {"type": "string", "description": "YYYY-MM-DD"},
                        },
                        "required": ["title", "issuetype"],
                    },
                },
            },
            "required": ["project_key", "issues"],
        },
        handler=_jira_create_issues,
        # 남의 Jira 에 이슈를 만든다. 승인 게이트를 반드시 탄다(8/11 확정 ③).
        side_effect=True,
    ),
    "jira_get_issues": Tool(
        ref="jira_get_issues",
        name="Jira 이슈 조회",
        description="Jira 프로젝트의 기존 이슈와 진행 상황을 읽는다.",
        input_schema={
            "type": "object",
            "properties": {"project_key": {"type": "string"}},
            "required": ["project_key"],
        },
        handler=_jira_get_issues,
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

    tool_ref = row["tool_ref"]

    def handler(*, team_id: str, **arguments: Any) -> dict[str, Any]:
        """호출 직전에 서버·토큰을 다시 읽는다.

        Registry 를 만들 때 토큰을 들고 있지 않는 이유는, 그 값이 Tool 객체와
        함께 Loop 안을 돌아다니게 되기 때문이다 — 예외 문자열이나 디버그 출력에
        섞여 나갈 자리가 그만큼 늘어난다. 쓰기 직전에만 꺼낸다(§4-2).
        """

        server = McpServerRepository.credentials_for_tool(tool_ref, team_id=team_id)
        return mcp_client.call_tool(
            endpoint_url=server["endpoint_url"],
            auth_token=server["auth_token"],
            name=server["tool_name"],
            arguments=arguments,
        )

    return Tool(
        ref=tool_ref,
        name=row["name"],
        description=row.get("description") or "",
        input_schema=row.get("input_schema") or {"type": "object", "properties": {}},
        handler=handler,
        side_effect=True,
    )


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
