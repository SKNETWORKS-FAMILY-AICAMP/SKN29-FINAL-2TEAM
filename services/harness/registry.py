"""Tool Registry — 에이전트가 부를 수 있는 도구를 모으고 거른다.

`tool_ref` 는 `agent_version_tools.tool_ref` 에 저장되는 값 그대로다. 내장
도구는 식별자 자체(`document_search`), MCP 도구는 `mcp:<mcp_tool_id>` 다
(DB/migrations/2026-08-11_agent_platform.sql 주석).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

from apps.connectors.clients import (
    create_jira_issues,
    find_jira_account_id_by_email,
    list_drive_files,
    search_jira_issues,
)
from backend.db import (
    AccountRepository,
    ExistTaskRepository,
    ProjectRepository,
    ProjectSourceRepository,
    TeamFolderRepository,
    TeamRepository,
)
from backend.db.agent_platform import (
    AgentRepository,
    McpServerRepository,
    ProjectTaskRepository,
)
from backend.db import ConnectorRepository
from backend.db.errors import RecordNotFound
from backend.db.document_pipeline import (
    PersonalDocumentRepository,
    PipelineDocumentRepository,
    VectorSearchRepository,
)
from backend.db.repositories import DocumentRepository
from backend.services import storage
from backend.services.hr import list_absences, list_capacity_profiles, list_person_skills
from services.document_intake import sync_drive_changes
from services.document_export import build_docx, build_xlsx
from services.document_pipeline.runpod_client import embed_queries
from services.mcp import client as mcp_client
from services.task_extraction import extract_tasks_stream
from services.websearch import WebSearchUnavailable, search_web
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
    #: 도구 선택 화면이 묶어 보여줄 단위(예: "Jira", "문서"). 저장·실행에는
    #: 안 쓴다 — 화면 표현 전용(2026-08-18, 도구 선택 그룹화).
    category: str = "기타"


class ToolInputError(ValueError):
    """**사람에게 그대로 보여도 되는 실패.**

    "프로젝트를 먼저 고르세요" 처럼 사람이 고칠 수 있는 사유다. 이 예외의
    메시지만 화면으로 나간다.

    다른 예외(네트워크·DB·라이브러리)는 클래스 이름만 나간다 — 예외 문자열에
    문서 원문이나 토큰이 섞여 있을 수 있고, 그건 화면에도 모델 컨텍스트에도
    실리면 안 된다(runner.py 의 같은 규칙).
    """


# ---------------------------------------------------------------------------
# 내장 도구
# ---------------------------------------------------------------------------


def _document_search(
    *,
    team_id: str,
    query: str,
    account_id: str | None = None,
    proj_id: str | None = None,
    top_k: int = 10,
):
    """팀 문서에서 근거 문장을 찾는다.

    1) 범위 — 이 요청이 볼 수 있는 문서를 정한다(팀 + 내가 켠 내 파일 + 공유분,
       프로젝트 대화면 그 프로젝트로 좁혀서). **순위는 매기지 않는다.**
    2) 근거 — 그 범위 안의 청크 임베딩을 검색한다.

    **요약으로 문서를 먼저 좁히던 단계(coarse)를 걷어냈다**(2026-08-24). 폴더를
    저장하면 그 문서 전부가 본문까지 색인되므로(`services/document_intake`)
    요약으로 좁힐 이유가 없다 — 요약 기반 후보 검색은 전량 색인을 **대신하는
    경로가 아니라** 그 앞단의 보조 수단이고, 순위는 청크 벡터가 문서 요약보다
    정확하게 매긴다. 요약 테이블(`doc_meta`)은 같은 날 통째로 걷어냈다 —
    기준 문서 후보 추천도 본문 청크로 옮겼다.

    범위 안에 있지만 아직 청크가 없는 문서(`search_ready = false`)는 본문 근거를
    낼 수 없다. **그 사실을 결과에 담아 돌려준다** — 조용히 빼면 에이전트가
    "관련 문서가 없다"고 답하는데 실제로는 색인이 아직 안 닿았을 뿐이다.

    **제너레이터다**(2026-08-18 추가) — coarse로 좁힌 뒤 실제로 어느 문서를
    보고 있는지("출처") 실시간으로 보여 달라는 요청. `_extract_tasks`와 같은
    패턴 — `adapters.py`의 `_wrap_handler`가 제너레이터면 자동으로 드레인해
    진행 이벤트로 흘려보내고, 마지막 `return`(아래)이 모델이 실제로 받는
    도구 결과다. 직접 호출하는 테스트(`tests/test_document_meta.py`)는
    `_drain_with_progress`와 같은 방식으로 끝까지 돌려 반환값을 얻는다.
    """

    yield {"type": "stage", "step": 1, "total": 2, "label": "관련 문서 찾는 중"}

    vector = embed_queries([query])[0]
    # `account_id` 를 함께 넘긴다 — 팀 문서에 **내가 켠 내 파일**을 더해 본다
    # (2026-08-18 · M④). 에이전트에 파일을 붙이는 개념은 안 만들었으므로 켠
    # 파일은 모든 에이전트가 쓴다.
    #
    # **프로젝트 대화면 그 프로젝트 문서를 먼저 본다**(2026-08-19 PM 결정 ⓐ).
    # 화면은 「〈프로젝트〉의 문서를 근거로 답합니다」라고 약속하는데
    # (`ChatPage.tsx`), 검색은 `proj_id` 를 받지도 않아 팀 문서 전체를 훑고
    # 있었다 — 무관한 「테스트.pdf」가 후보로 올라와 읽히기까지 했다.
    # 좁혀서 아무것도 없을 때만 팀 전체로 넓힌다: 팀 공용 문서(규정·양식)를
    # 영영 못 보게 하면 「감리 표준양식 보여줘」 같은 요청이 막힌다.
    documents = []
    if proj_id:
        documents = PipelineDocumentRepository.searchable_documents(
            team_id=team_id, account_id=account_id, proj_id=proj_id
        )
    if not documents:
        documents = PipelineDocumentRepository.searchable_documents(
            team_id=team_id, account_id=account_id
        )

    doc_ids = [row["doc_id"] for row in documents if row["search_ready"]]
    # 아직 색인이 안 닿은 문서. **숨기지 않고 답에 담는다** — 조용히 빼면 문서가
    # 있는데도 「관련 문서가 없다」로 읽힌다.
    #
    # 여기서 승격시키지 않는다(2026-08-24). 전에는 요약으로 좁힌 상위 몇 건을
    # 그 자리에서 읽어 올렸는데, 그 「상위」는 요약 유사도 순위였다. 요약으로
    # 좁히는 단계를 걷어낸 지금은 미색인 문서를 **순위 매길 방법이 없어** 앞의
    # 몇 건을 고르는 것이 `doc_id` 순으로 아무거나 집는 것과 같다. 관련도 없는
    # 문서 때문에 대화가 몇 분 멈춘다.
    #
    # 대신 폴더 저장 뒤 도는 전량 색인이 결국 전부 채운다
    # (`services/document_intake` `_index_all`). 그때까지는 「아직 색인 중」이라고
    # 말하는 것이 맞다. 기준 문서처럼 **어느 문서인지 이미 정해진** 경로는
    # 지금도 그 자리에서 승격시킨다(`_extract_tasks`).
    not_indexed = [
        {
            "doc_id": row["doc_id"],
            "file_name": row["file_name"],
            "index_status": row["index_status"],
        }
        for row in documents
        if not row["search_ready"]
    ]

    if not doc_ids:
        return {
            "query": query,
            "evidence": [],
            "not_indexed": not_indexed,
            "note": (
                "문서는 있지만 본문이 아직 색인되지 않아 문장 근거를 낼 수 없습니다. "
                "색인이 끝나면 답할 수 있습니다."
                if not_indexed
                else "검색할 문서가 없습니다."
            ),
        }

    yield {"type": "stage", "step": 2, "total": 2, "label": "본문에서 근거 찾는 중"}

    rows = VectorSearchRepository.search(
        team_id=team_id, document_ids=doc_ids, query_vector=vector, top_k=top_k,
        account_id=account_id,
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
        result["note"] = "아래 문서는 본문이 아직 색인되지 않아 근거에서 빠졌습니다."

    # **출처는 근거가 실제로 나온 문서다**(2026-08-24). 전에는 coarse 가 좁힌
    # 후보 목록을 그대로 냈는데, 좁히는 단계를 걷어낸 지금 그 자리에 넣을 것은
    # 「범위 안의 문서 전부」뿐이라 출처라고 부를 수 없다. 청크가 실제로 걸린
    # 문서만 낸다 — 화면이 말하는 「근거」와 뜻이 같아진다.
    #
    # `id`/`label` 은 `_web_search` 도 같이 쓰는 공통 모양이다(2026-08-18) —
    # 웹 결과는 `url` 도 채운다, 내부 문서는 안 채운다(화면이 그 유무로 링크를
    # 걸지 그냥 텍스트로 보일지 정한다).
    if rows:
        names = {row["doc_id"]: row["file_name"] for row in documents}
        cited: dict[str, str] = {}
        for row in rows:
            cited.setdefault(row["doc_id"], names.get(row["doc_id"]) or row["doc_id"])
        yield {
            "type": "sources",
            "step": 2,
            "documents": [{"id": doc_id, "label": label} for doc_id, label in cited.items()],
        }

    yield {"type": "stage_done", "step": 2, "found": len(doc_ids), "evidence": len(result["evidence"])}
    return result


def _people_list(*, account_id: str) -> dict[str, Any]:
    """우리 팀에 누가 있는가. 이름·직책·보유 스킬을 돌려준다.

    `TeamRepository.list_members` 를 그대로 쓴다 — 「팀원 관리」 화면과 **같은
    명부**여야 한다. 배정 대상은 초대가 아니라 `team_member` 라는 판단이 거기
    들어 있고, 여기서 다시 질의하면 그 판단이 두 벌이 된다.

    스킬은 사람마다 따로 읽는다. 명부는 팀 하나 크기라 이 비용이 문제가 되는
    자리가 아니고, 「이 일은 누가 맡는 게 맞나」는 스킬 없이는 답이 안 된다.
    """

    return {
        "members": [
            {
                "person_id": member["person_id"],
                "name": member["name"],
                "job_role": member["job_role"],
                "org_name": member["org_name"],
                "skills": [
                    {"name": skill["name"], "proficiency": skill["proficiency"]}
                    for skill in list_person_skills(member["person_id"])
                ],
                # 계정이 없어도 팀원이고 배정 대상이다. 다만 이 앱에서 결과를
                # 직접 볼 수는 없다 — 사람에게 알릴 때 그 차이가 필요하다.
                "has_account": bool(member["account_id"]),
            }
            for member in TeamRepository.list_members(account_id)
        ]
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


def _team_model_key(team_id: str | None) -> str | None:
    """팀이 넣어 둔 키. **OpenAI 정품일 때만 쓴다.**

    이 파이프라인은 `responses.parse` 가 필요한데 호환 엔드포인트(OpenRouter·
    Anthropic…)에는 그 API 가 없다. 주소를 따로 넣은 팀의 키를 여기 쓰면 404 로
    죽으므로, 그 경우에는 우리 키로 돈다 — 대신 그 사실이 결과에 남아야 한다.
    """

    if not team_id:
        return None
    # 커스텀 엔드포인트는 쓰지 않는다 — 이 파이프라인은 `responses.parse` 가
    # 필요한데 호환 경로에는 그 API 가 없다. 우리 키로 돈다.
    return None


def _extract_tasks(
    *,
    proj_id: str | None,
    account_id: str,
    team_id: str | None = None,
    model: str | None = None,
):
    """기준 문서에서 업무를 뽑는다. 기존 `services/task_extraction` 을 그대로 쓴다.

    **제너레이터다.** 안쪽 파이프라인이 4단계 검색 + 1단계 정리라 몇 분이 걸리고,
    그동안 무엇을 찾고 있는지 내보내지 않으면 화면이 멈춘 것과 구별되지 않는다.
    기존 `/tasks/extraction` 화면이 이미 그 진행을 보여 주고 있어서, 여기서 삼키면
    Chat 쪽이 명백히 못한 물건이 된다.

    모델에게는 **제목·역할·공수까지만** 돌려준다. 근거 문장과 chunk id 는 넣지
    않는다 — 원래 결정(2026-08-11: "업무 20건과 근거를 통째로 돌려주면 바깥
    모델이 한 번 더 요약하면서 근거가 흔들리고 토큰도 든다")이 막으려던 것은
    **근거의 재요약**이고, 그건 그대로 지킨다.

    ⚠ **건수만 주던 것을 고쳤다(2026-08-11).** 그러면 모델이 등록할 업무를
    모른다 — 실제로 "해당 결과를 프로젝트 업무로 등록해 줘"에 대해 「추출
    결과가 확인되지 않습니다」라고 답했다. `task_register` 도 `jira_create_issues`
    도 업무 목록을 인자로 받는데 그 목록이 모델 컨텍스트에 없었던 것이다.

    사람이 볼 결과(근거 포함)는 여전히 이벤트로 나가 chat_message 에 남는다.

    기준 문서는 사람이 이미 골라 둔 것(`doc_role='PRIMARY'`)을 쓴다. 모델에게
    문서 id 를 고르게 하지 않는다 — 어느 문서로 뽑았는지가 결과 전체의 전제라
    그건 사람의 결정이어야 한다.
    """

    if not proj_id:
        raise ToolInputError("어느 프로젝트의 업무를 뽑을지 정해지지 않았습니다. 프로젝트를 먼저 고르세요.")

    documents = PipelineDocumentRepository.list_ready_for_analysis(
        proj_id=proj_id, account_id=account_id
    )
    # `list_ready_for_analysis` 는 팀 문서를 전부 준다. 다른 프로젝트의 기준
    # 문서도 섞여 있으므로 proj_id 까지 봐야 한다.
    primary = next(
        (d for d in documents if d["proj_id"] == proj_id and d["doc_role"] == "PRIMARY"), None
    )
    if primary is None:
        # **어디서 정하는지까지 말한다**(2026-08-19). 「없다」로만 끝내면 사람이
        # 할 수 있는 일이 없다 — 실제로 팀원이 「그럼 어떻게 하냐」로 되물었다.
        # 화면(`PrimaryDocumentCard`)이 쓰는 말과 똑같이 「기준 문서 선택」이라고
        # 부른다. 같은 동작에 다른 말을 쓰면 사람이 같은 판단을 두 번 한다.
        raise ToolInputError(
            "이 프로젝트의 기준 문서가 아직 지정되지 않았습니다. "
            "프로젝트 화면의 「기준 문서 선택」에서 정한 뒤 다시 요청하세요."
        )

    if not primary["search_ready"]:
        # **여기서 승격시킨다**(2026-08-18 PM 결정). 전에는 「아직 파싱·청킹·
        # 임베딩되지 않았습니다」로 끊었는데, 그러면 사람이 할 수 있는 일이
        # 없다 — 색인을 시작하는 화면은 8/15 에 지웠고(`/files/new`), 승격은
        # `document_search` 만 걸 수 있었다. 그래서 **새로 연결한 팀은 업무를
        # 영영 못 뽑았다.**
        #
        # 추출은 `VectorSearchRepository.search()` 로 근거를 찾으므로 벡터가
        # 없으면 결과가 0건이다. 막는 대신 그 자리에서 만든다 — 검색이 필요할
        # 때 승격시키는 것과 같은 규칙이고, 진입점만 하나 더 는 것이다.
        from services.document_intake import promote_to_searchable

        outcome = promote_to_searchable(account_id=account_id, doc_id=primary["doc_id"])
        if not outcome["ok"]:
            raise ToolInputError(
                f"기준 문서의 본문을 읽지 못해 업무를 뽑을 수 없습니다: {outcome.get('detail') or '알 수 없는 이유'}"
            )
        # 승격 뒤 상태가 바뀌었다 — 다시 읽어야 `ready_ids` 에 이 문서가 들어간다.
        documents = PipelineDocumentRepository.list_ready_for_analysis(
            proj_id=proj_id, account_id=account_id
        )
        primary = next(
            (d for d in documents if d["proj_id"] == proj_id and d["doc_role"] == "PRIMARY"), None
        )
        if primary is None or not primary["search_ready"]:
            raise ToolInputError("기준 문서를 색인했지만 검색에 쓸 수 있는 본문이 없습니다.")

    ready_ids = [d["doc_id"] for d in documents if d["search_ready"]]
    result = None
    for event in extract_tasks_stream(
        team_id=primary["team_id"],
        primary_document=primary,
        document_ids=ready_ids,
        # 부른 에이전트의 모델과, 팀이 자기 키를 넣었으면 그 키로 돈다.
        model=model,
        api_key=_team_model_key(team_id or primary["team_id"]),
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
        "model": result.get("model"),
        # 고른 모델로 못 돌았으면 모델이 그 사실을 사람에게 말해야 한다.
        "model_fallback_from": result.get("model_fallback_from"),
        "primary_document": primary["file_name"],
        # 등록 도구(`task_register`·`jira_create_issues`)에 그대로 넘길 수 있는
        # 최소 형태. **화면 카드의 순서와 같다** — 사람이 확인 카드에서 푼 체크가
        # 인덱스로 오므로 두 목록의 순서가 어긋나면 다른 업무가 빠진다.
        "tasks": [
            {
                "no": index,
                "title": task["title"],
                "required_role": task.get("required_role"),
                "effort_hours": task.get("effort_hours"),
                "due_date": task.get("due_date"),
            }
            for index, task in enumerate(result["tasks"])
        ],
    }


def _task_register(*, proj_id: str | None, account_id: str, tasks: list[dict[str, Any]]):
    """확인받은 업무를 **우리 플랫폼**에 등록한다. Jira 보다 먼저다.

    지금까지 추출 결과는 어디에도 저장되지 않았다 — 대화의 이벤트 배열에만
    남아 그 대화를 떠나면 사라졌고, 유일한 출구가 Jira 였다. 그래서 Jira 를
    안 쓰는 팀은 뽑은 업무를 가질 방법이 없었다.

    **부작용 도구다.** 외부 시스템은 아니지만 우리 데이터를 바꾸고, 사람이
    「이 업무들이 맞다」고 확정하는 지점이라 승인 게이트를 타야 한다 — 확인
    카드가 뜨는 자리가 바로 여기다.
    """

    if not proj_id:
        raise ToolInputError("어느 프로젝트의 업무인지 정해지지 않았습니다. 프로젝트를 먼저 고르세요.")
    return ProjectTaskRepository.register(proj_id=proj_id, account_id=account_id, tasks=tasks)


def _project_list(*, account_id: str) -> dict[str, Any]:
    """우리 팀의 프로젝트와 진행률.

    「무슨 프로젝트가 있지?」·「어느 게 제일 늦었어?」에 답할 수 있게 한다 —
    지금까지는 프로젝트를 **고를** 수는 있었지만 **물어볼** 수는 없었다.

    진행률은 목록 화면과 **같은 계산기**를 부른다(`progress_by_project`).
    여기서 다시 세면 화면이 말하는 숫자와 에이전트가 말하는 숫자가 갈라진다.
    """

    rows = ProjectRepository.list_for_team(account_id)
    progress = ExistTaskRepository.progress_by_project([row["proj_id"] for row in rows])

    return {
        "projects": [
            {
                "proj_id": row["proj_id"],
                "name": row["name"],
                "description": row.get("description"),
                "status": row["status"],
                # 진행률이 없는 것과 0%는 다르다 — Jira 를 아직 안 읽었거나
                # 연결된 프로젝트가 없다는 뜻이다. null 로 둔다.
                "progress": progress.get(row["proj_id"]),
            }
            for row in rows
        ]
    }


def _task_list(*, proj_id: str | None, account_id: str) -> dict[str, Any]:
    """이 프로젝트에 **등록된 우리 업무**. `task_register` 로 넣은 것을 읽는다.

    등록만 하고 읽지 못하면 반쪽이다 — 「아까 등록한 거 뭐였지?」에 답할 방법이
    없었다(2026-08-12 확인). Jira 이슈가 아니라 우리 `task` 테이블이다.
    """

    if not proj_id:
        raise ToolInputError("어느 프로젝트의 업무인지 정해지지 않았습니다. 프로젝트를 먼저 고르세요.")

    rows = ProjectTaskRepository.list_for_project(proj_id=proj_id, account_id=account_id)
    return {
        "tasks": [
            {
                "task_id": row["task_id"],
                "title": row["task_name"],
                "required_role": row["req_role"],
                "effort_hours": float(row["effort"]) if row["effort"] is not None else None,
                "due_at": row["due_at"],
                "priority": row["priority"],
                # PROPOSED / CONFIRMED / REJECTED. 등록됐다고 확정된 것이 아니다.
                "status": row["status"],
            }
            for row in rows
        ]
    }


def _document_sync(*, account_id: str):
    """저장소에서 바뀐 것을 **지금** 확인해 반영한다.

    대화를 열 때 이미 한 번 돈다(`apps/chat/api_views.py` `_start_drive_change_sync`).
    이 도구는 그 뒤에 사용자가 「방금 문서 고쳤어, 다시 봐」라고 할 때 쓴다 —
    **버튼을 만들지 않는 이유**가 이것이다. 사람이 화면을 찾아 누르는 대신
    말하면 되고, 그게 이 제품이 에이전트를 다루는 방식이다.

    검색 직전마다 자동으로 돌리지는 않는다(2026-08-24 판단). 변화가 없어도
    DB 연결 4회 + Drive 호출 1회가 붙고(실측: 연결 하나가 24ms), 변화가 있으면
    재색인이 문서당 최대 240초라 매 검색에 얹을 수 없다. 사용자가 「바뀌었다」를
    아는 순간에만 부르는 것이 값이 가장 크다.

    **오래 걸릴 수 있다.** 실제로 바뀐 문서가 있으면 내려받아 다시 색인하고,
    그 대기가 문서당 몇 분이다(`_extract_tasks` 가 기준 문서를 승격시킬 때와 같은
    성격). 그래서 진행 이벤트를 먼저 흘려보낸다 — 화면이 멈춘 것처럼 보이면 안 된다.
    """

    yield {"type": "stage", "step": 1, "total": 1, "label": "저장소 변경 확인 중"}

    # 연결 여부를 여기서 한 번 더 본다. `sync_drive_changes` 는 「연결이 없다」와
    # 「바뀐 것이 없다」를 똑같이 빈 결과로 돌려주는데, 사람에게는 전혀 다른
    # 말이다 — 연결이 없는데 「변경 없음」이라고 답하면 안 된다.
    if ConnectorRepository.drive_sync_target(account_id) is None:
        return {
            "checked": False,
            "note": "문서 저장소가 연결되어 있지 않거나, 읽을 폴더가 지정되지 않았습니다.",
        }

    result = sync_drive_changes(account_id=account_id)
    if result.storage_error:
        return {
            "checked": False,
            "note": f"저장소를 확인하지 못했습니다({result.storage_error}). 연결이 만료됐을 수 있습니다.",
        }

    changed = bool(result.refreshed or result.removed or result.indexed)
    return {
        "checked": True,
        # 셋을 나눠 준다 — 사람이 확인할 것이 각각 다르다.
        "refreshed": result.refreshed,
        "removed": result.removed,
        "indexed": result.indexed,
        "failed": result.failed,
        "note": (
            "저장소에서 바뀐 내용을 반영했습니다."
            if changed
            else "마지막 확인 이후 바뀐 문서가 없습니다."
        ),
    }


#: 내보낼 수 있는 행 수. 모델이 만든 배열이라 실제로는 출력 토큰이 먼저 막지만,
#: 막히는 자리가 「엑셀이 안 열린다」가 되면 사람이 원인을 못 찾는다.
_EXPORT_MAX_ROWS = 5000

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


#: 파일 이름·시트 이름에 못 쓰는 글자. 제목이 그대로 이름이 되므로 턴다.
_UNSAFE_NAME_CHARS = frozenset(r'\/:*?"<>|')


def _safe_title(title: str, *, fallback: str) -> str:
    """제목에서 파일 이름에 못 쓰는 글자를 턴다. 남는 게 없으면 `fallback`."""

    return "".join(ch for ch in (title or "") if ch not in _UNSAFE_NAME_CHARS).strip() or fallback


def _file_ref(doc_id: str, file_name: str, mime_type: str) -> dict[str, str]:
    """도구가 **만들어 낸 파일**을 가리키는 값. 화면의 받기 단추가 이것으로 그려진다.

    **`doc_id` 를 평평하게 두지 않고 `file` 안에 넣는 것이 계약이다**(2026-08-26).
    읽기 도구의 결과에도 `doc_id` 가 잔뜩 들어 있어서(`document_search` 의 근거·
    `document_list` 의 목록) 평평하게 두면 「본 문서」와 「만든 파일」을 구별할
    방법이 없다. `events.py` 의 `_produced_file()` 이 이 모양만 찾는다.
    """

    return {"doc_id": doc_id, "file_name": file_name, "mime_type": mime_type}


def _store_generated(
    *, account_id: str, title: str, suffix: str, mime_type: str, data: bytes
) -> tuple[str, str]:
    """만든 파일을 「내 파일」에 넣고 `(doc_id, 파일 이름)` 을 돌려준다.

    `table_export` 와 `document_create` 가 같은 자리를 쓴다. 두 번째 도구를
    더하면서 뽑아낸 것이다 — 저장 규칙(개인 키 · 내용 해시를 revision 자리에)이
    양쪽에서 갈리면 한쪽만 조용히 틀린다.
    """

    # 파일 이름이 곧 목록에 보이는 이름이다. 날짜를 붙이는 것은 같은 것을 여러 번
    # 만들었을 때 어느 것이 언제 것인지 목록에서 갈리게 하려는 것이다.
    stamp = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%d")
    file_name = f"{_safe_title(title, fallback='제목 없음')}_{stamp}{suffix}"

    doc_id = PersonalDocumentRepository.create_generated(
        account_id=account_id, file_name=file_name, mime_type=mime_type
    )
    key = storage.build_personal_key(account_id=account_id, doc_id=doc_id, mime_type=mime_type)
    content_hash = storage.save(key, data)
    # 올린 파일과 같은 규칙이다(`apps/personal_files/api_views.py`) — 원천 리비전이
    # 없으므로 내용 해시를 그 자리에 쓴다.
    DocumentRepository.mark_stored(
        doc_id=doc_id,
        storage_key=key,
        content_hash=content_hash,
        revision=content_hash.removeprefix("sha256:")[:16],
    )
    return doc_id, file_name


def _table_export(
    *,
    account_id: str,
    title: str,
    columns: list[str],
    rows: list[list[Any]],
) -> dict[str, Any]:
    """표 하나를 xlsx 로 만들어 **「내 파일」에 넣는다.**

    **표를 모델에게서 받는다**(2026-08-26 결정). 「`task_list` 결과를 내보내라」
    처럼 소스 도구를 지목하게 만들 수도 있었지만, 그러면 소스마다 매핑을
    등록해야 하고 모델이 여러 도구 결과를 합쳐 만든 표는 못 낸다. 대신 값은
    모델이 옮겨 적은 것이므로 **원본과 다를 수 있다** — 그 위험은 사람이 파일을
    열어 확인하는 것으로 갈음한다.

    만들어진 행은 `source_type='GENERATED'` 이고 검색이 꺼진 채로 들어간다
    (`create_generated` 주석에 이유가 있다).
    """

    if not columns:
        raise ToolInputError("표의 머리글이 비어 있습니다. 열 이름을 정해 주세요.")
    if len(rows) > _EXPORT_MAX_ROWS:
        raise ToolInputError(
            f"한 번에 내보낼 수 있는 행은 {_EXPORT_MAX_ROWS}개까지입니다 (요청 {len(rows)}개)."
        )
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, (list, tuple)):
            raise ToolInputError(
                f"{index}번째 행이 목록이 아닙니다. 각 행은 열 순서대로 값을 담은 목록이어야 합니다."
            )

    # 시트 이름은 파일 이름과 같은 글자를 쓴다 — 목록에서 본 이름과 열었을 때의
    # 이름이 다르면 같은 파일인지 사람이 다시 확인해야 한다.
    data = build_xlsx(
        title=_safe_title(title, fallback="표"),
        columns=list(columns),
        rows=[list(r) for r in rows],
    )
    doc_id, file_name = _store_generated(
        account_id=account_id, title=title, suffix=".xlsx", mime_type=_XLSX_MIME, data=data
    )

    # 표 내용을 되돌려주지 않는다 — 모델이 방금 보낸 값이라 컨텍스트만 두 배가 된다.
    return {
        "file": _file_ref(doc_id, file_name, _XLSX_MIME),
        "columns": len(columns),
        "rows": len(rows),
        "note": "「내 파일」에 저장했습니다. 채팅에서 바로 내려받을 수 있습니다.",
    }


def _document_create(*, account_id: str, title: str, body: str) -> dict[str, Any]:
    """글 한 편을 워드 파일(.docx)로 만들어 **「내 파일」에 넣는다.**

    `table_export` 와 같은 자리·같은 규칙이다(`_store_generated`). 다른 것은
    받는 것뿐이다 — 저쪽은 표(열·행), 이쪽은 글(제목·본문)이다.

    **본문의 마크다운을 전부 해석하지 않는다.** 제목·목록·굵게만 그리고 나머지는
    글자 그대로 둔다 — 화면(`AnswerText.tsx`)이 같은 이유로 내린 판단을 그대로
    따른다(`document_export/docx.py` 모듈 주석).
    """

    if not (body or "").strip():
        raise ToolInputError("본문이 비어 있습니다. 문서에 담을 내용을 먼저 정해 주세요.")

    data = build_docx(title=title, body=body)
    doc_id, file_name = _store_generated(
        account_id=account_id, title=title, suffix=".docx", mime_type=_DOCX_MIME, data=data
    )

    # 본문을 되돌려주지 않는다 — 모델이 방금 보낸 값이라 컨텍스트만 두 배가 된다.
    return {
        "file": _file_ref(doc_id, file_name, _DOCX_MIME),
        "note": "「내 파일」에 저장했습니다. 채팅에서 바로 내려받을 수 있습니다.",
    }


def _document_list(*, account_id: str) -> dict[str, Any]:
    """팀에 어떤 문서가 있는가. **내용 검색이 아니라 목록이다.**

    `document_search` 는 「이 내용이 어디 있나」를 답하고, 이 도구는 「무엇이
    있나」를 답한다. 둘을 하나로 두면 "우리 팀에 무슨 문서 있어?"에 대해
    엉뚱한 문장 조각이 근거로 나온다.

    **색인 여부를 숨기지 않는다.** 아직 파싱 전인 문서는 검색에 안 걸리는데,
    목록에만 보이면 사람이 "있는데 왜 못 찾지?"가 된다.
    """

    # 한때 `PipelineDocumentRepository` 에 없는 메서드를 부르고 있어서 이 도구는
    # **한 번도 동작한 적이 없었다** — 「무슨 문서 있어?」가 늘 AttributeError 로
    # 끝났다(2026-08-12 QA 시나리오 B). 2026-08-24 에 `DocMetaRepository` 를
    # 걷어내면서 이 메서드가 실제로 여기로 왔다.
    rows = PipelineDocumentRepository.list_documents(account_id)
    return {
        "documents": [
            {
                "doc_id": row["doc_id"],
                "file_name": row["file_name"],
                # **id 와 열거값을 내보내지 않는다**(2026-08-19). 모델은 받은 것을
                # 그대로 옮겨 적어서, 화면에 「프로젝트 PJ004 의 PRIMARY 기준
                # 문서」가 나왔다 — 사용자는 둘 다 모르는 말이다(§0 원칙 2).
                # 대신 사람이 읽는 이름과 한국어 한 줄로 준다.
                "project": row.get("proj_name"),
                "role": (
                    "이 프로젝트의 기준 문서"
                    if (row.get("doc_role") or "").upper() == "PRIMARY"
                    else "프로젝트에 묶이지 않은 팀 문서"
                ),
                "search_ready": row["search_ready"],
            }
            for row in rows
        ],
        # 수집 전이라도 **저장소에 무엇이 있는지는 말할 수 있어야 한다**(아래).
        **_connected_folder_files(account_id, collected={row["file_name"] for row in rows}),
    }


#: 저장소를 들여다볼 때 한 번에 가져오는 파일 수의 상한.
#:
#: 목록을 말해 주자는 것이지 전부 세자는 것이 아니다. 폴더가 크면 대화 한 번이
#: Drive 호출로 길어지는데, 그때 필요한 답은 「무엇이 있나」이지 「몇 개인가」가
#: 아니다. 잘렸다는 사실은 `truncated` 로 함께 알린다.
_FOLDER_PEEK_LIMIT = 40


def _connected_folder_files(account_id: str, *, collected: set[str]) -> dict[str, Any]:
    """연결된 문서 저장소에 **아직 수집하지 않은** 파일이 무엇이 있는가.

    **연결됐는데 수집이 안 된 상태를 「문서가 없다」로 답하면 안 된다**(PM 지적).
    폴더가 붙어 있으면 그 안에 무엇이 있는지는 저장소에 물어보면 알 수 있고,
    사람에게는 그게 「연결된 문서」다 — 우리가 언제 읽었는지는 우리 사정이다.

    다만 **수집한 것과 섞지 않는다.** 아직 안 읽은 파일은 내용을 근거로 쓸 수
    없으므로 목록을 따로 주고, 도구 설명이 모델에게 그 차이를 말하게 한다.

    저장소를 못 읽어도 이 도구는 실패하지 않는다. 수집된 문서 목록은 이미
    손에 있고, 저장소가 잠깐 안 되는 것 때문에 그것까지 잃을 이유가 없다.
    """

    folders = TeamFolderRepository.list_for_team(account_id)
    if not folders:
        return {"storage_folders": [], "not_collected": [], "storage_error": None}

    names = [folder["display_name"] for folder in folders]
    pending: list[dict[str, Any]] = []
    try:
        for folder in folders:
            for item in list_drive_files(
                account_id=account_id,
                parent_id=folder["external_folder_id"],
                max_depth=folder.get("max_depth") or 1,
            ):
                if item["name"] in collected:
                    continue
                pending.append(
                    {
                        "file_name": item["name"],
                        "folder": folder["display_name"],
                        # 형식이 안 되는 파일도 숨기지 않는다 — 사람이 「내 파일이
                        # 왜 없지」를 묻지 않으려면 빠진 이유가 보여야 한다.
                        "supported": item["supported"],
                    }
                )
                if len(pending) >= _FOLDER_PEEK_LIMIT:
                    return {
                        "storage_folders": names,
                        "not_collected": pending,
                        "truncated": True,
                        "storage_error": None,
                    }
    except Exception as exc:  # noqa: BLE001 — 저장소 사정으로 목록을 잃지 않는다
        return {"storage_folders": names, "not_collected": [], "storage_error": str(exc)}

    return {"storage_folders": names, "not_collected": pending, "storage_error": None}


def _task_update(
    *,
    proj_id: str | None,
    account_id: str,
    task_id: str,
    status: str | None = None,
    due_at: str | None = None,
) -> dict[str, Any]:
    """등록된 업무의 상태·마감을 고친다.

    **등록만 되고 아무것도 못 바꾸던 것을 연다(2026-08-12).** `task.status` 가
    `PROPOSED / CONFIRMED / REJECTED` 인데 바꿀 경로가 없어서 한 번 등록하면
    영원히 `PROPOSED` 였다 — 확정도 반려도 못 하면 목록이 쌓이기만 한다.

    **부작용 도구다.** 외부 시스템은 아니지만 사람이 「이 업무는 하기로 했다」를
    확정하는 지점이고, 그건 승인 카드를 거쳐야 한다.
    """

    if not proj_id:
        raise ToolInputError("어느 프로젝트의 업무인지 정해지지 않았습니다. 프로젝트를 먼저 고르세요.")
    try:
        return ProjectTaskRepository.update(
            proj_id=proj_id,
            account_id=account_id,
            task_id=task_id,
            status=status,
            due_at=due_at,
        )
    except RecordNotFound as exc:
        # 이 프로젝트에 없는 업무 id 는 모델이 지어낸 값일 수 있다. 사람이
        # 고칠 수 있는 사유라 그대로 보인다.
        raise ToolInputError(str(exc)) from exc


def _absence_list(*, account_id: str, weeks: int = 4) -> dict[str, Any]:
    """앞으로 몇 주간 팀원의 **승인된** 부재(휴가·교육 등).

    `workload_report` 가 이미 이 데이터를 계산에 쓴다. 그런데 조회 도구가 없어서
    「왜 이 사람 여유가 없어?」에 "다음 주 휴가 3일이라서"라고 답할 수 없었다 —
    **근거를 계산에만 쓰고 말하지는 못하는 상태**였다.

    `list_absences` 를 그대로 부른다. 승인된 것만 세는 화이트리스트 판단이
    거기 들어 있고, 여기서 다시 질의하면 그 판단이 두 벌이 된다.
    """

    period_start = date.today()
    period_end = period_start + timedelta(weeks=weeks)

    team_id = AccountRepository.team_id(account_id)
    members = {row["person_id"]: row["name"] for row in TeamRepository.list_members(account_id)}
    rows = list_absences(
        person_ids=TeamRepository.member_person_ids(team_id),
        period_start=period_start,
        period_end=period_end,
    )

    return {
        "period": {"start": period_start.isoformat(), "end": period_end.isoformat()},
        "absences": [
            {
                # 이름을 붙여 준다. person_id 만 주면 모델이 사람 이름을 못 말한다.
                "name": members.get(row["person_id"], row["person_id"]),
                "absence_type": row["absence_type"],
                "start_at": row["start_at"],
                "end_at": row["end_at"],
            }
            for row in rows
        ],
    }


def _web_search(*, query: str):
    """웹에서 찾는다. **팀 문서와 다른 종류의 근거다.**

    문서는 사람이 올려 두고 파싱·색인을 거친 것이고, 웹은 아무도 검증하지
    않았다. 그 차이가 답에서 지워지면 「우리 기획서에 그렇게 적혀 있다」와
    「인터넷에 그런 글이 있다」를 구별할 수 없다.

    그래서 결과마다 URL 을 붙이고, 못 쓰는 상태(키 없음·한도 초과)는 빈 결과가
    아니라 **사유로** 올린다 — 빈 결과를 주면 에이전트가 "웹에서 못 찾았습니다"
    라고 답하는데 실제로는 찾아보지도 않은 것이다.

    **제너레이터다**(2026-08-18 추가) — 검색 결과(제목·URL)가 오면 모델의
    최종 답을 기다리지 않고 "출처" 카드로 바로 보여준다(`_document_search`의
    `sources`와 같은 모양 — `services/harness/registry.py` 위쪽 참고). Tavily
    검색은 **단일 API 호출**이라(`services/websearch/client.py`) 그 안에서
    "지금 이 페이지 보는 중"처럼 더 잘게 쪼개 보여줄 수는 없다 — 응답이
    오는 순간 한 번에 보여주는 게 이 API로 낼 수 있는 최선이다.
    """

    yield {"type": "stage", "step": 1, "total": 1, "label": "웹 검색하는 중"}

    try:
        results = search_web(query)
    except WebSearchUnavailable as exc:
        raise ToolInputError(str(exc)) from exc

    if results:
        yield {
            "type": "sources",
            "step": 1,
            "documents": [
                {"id": item["url"], "label": item.get("title") or item["url"], "url": item["url"]}
                for item in results
            ],
        }

    return {
        "query": query,
        "results": results,
        "note": (
            "웹에서 찾은 것이다. 팀 문서가 아니므로 답할 때 출처 URL 을 함께 밝힌다."
            if results
            else "웹에서 관련 결과를 찾지 못했습니다."
        ),
    }


def _resolve_project_key(*, proj_id: str | None, account_id: str, project_key: str | None) -> str:
    """어느 Jira 프로젝트인가.

    **모델에게 묻지 않는다.** 프로젝트 하나에 Jira 프로젝트 하나이고
    (`proj_source` 의 `UNIQUE (proj_id)`, 2026-08-04), 그 대화가 어느 프로젝트의
    것인지는 이미 정해져 있다. 물어보게 두면 실제로 「확인할 Jira 프로젝트 키를
    알려주세요」로 대화가 끊긴다 — 연결은 되어 있는데 화면이 그걸 안 넘긴 것이다.

    모델이 키를 직접 준 경우는 그대로 쓴다. 「KAN 프로젝트 이슈 보여줘」처럼
    다른 프로젝트를 짚는 요청이 있고, 그건 사람의 지시다.
    """

    if project_key:
        return project_key
    if not proj_id:
        raise ToolInputError(
            "어느 Jira 프로젝트인지 정해지지 않았습니다. 프로젝트를 고르고 다시 요청하세요."
        )

    source = ProjectSourceRepository.get_for_project(proj_id=proj_id, account_id=account_id)
    if not source or not source.get("external_source_id"):
        raise ToolInputError("이 프로젝트에 연결된 Jira 프로젝트가 없습니다. 설정에서 먼저 연결하세요.")
    return source["external_source_id"]


def _jira_credential_account_id(account_id: str) -> str:
    """이 계정이 속한 팀의 팀장 account_id — Jira 자격증명은 거기 있다.

    Jira는 팀장만 연결할 수 있고(설정 화면 "팀장만 외부 서비스를 연결할 수
    있습니다") `connector_conn`은 연결한 계정(팀장) 기준으로만 저장된다.
    도구를 **부른 사람**의 `account_id`를 그대로 자격증명 조회에 넘기면,
    팀원 자신은 연결한 적이 없어 `연결되지 않은 서비스입니다`로 막힌다 —
    화면은 "팀원은 팀장이 연결한 데이터를 그대로 쓴다"고 약속하는데 실제로는
    그러지 못했다(2026-08-19 실측·수정, `TeamRepository.leader_account_id()`
    참고). 프로젝트·권한 확인(`_resolve_project_key`)은 여전히 부른 사람의
    `account_id`를 쓴다 — 자격증명만 팀장 것으로 바꾼다.
    """

    team_id = AccountRepository.team_id(account_id)
    leader_account_id = TeamRepository.leader_account_id(team_id) if team_id else None
    if not leader_account_id:
        raise ToolInputError("이 팀에 연결된 팀장 계정을 찾을 수 없습니다.")
    return leader_account_id


def _jira_create_issues(
    *,
    account_id: str,
    proj_id: str | None = None,
    project_key: str | None = None,
    assign_to_requester: bool = False,
    issues: list[dict[str, Any]],
):
    """확인받은 업무를 Jira 에 등록한다.

    **MCP 가 아니라 내장 도구다.** 자체 Jira MCP 서버를 띄우려면 우리 SSRF
    차단(§4-1)이 같은 호스트 주소를 막고, 공식 Atlassian MCP 는 OAuth 액세스
    토큰을 요구해(실측 2026-08-11: 401 `Bearer realm="OAuth"`) 정적 토큰 하나를
    저장하는 우리 모델로는 한 시간 뒤 끊긴다. 데모의 핵심 흐름을 남의 서비스와
    남의 토큰 수명에 매달 이유가 없다 — Jira Connector 는 이미 붙어 있다.

    MCP 는 「사용자가 자기 서버를 추가로 붙이는」 확장 경로로 남는다.

    2026-08-20 — `_fill_default_jira_assignee()`가 담당자 기본값을 찾으려고
    쓰는 자격증명과, 아래 `create_jira_issues()`가 실제 등록에 쓰는
    자격증명은 같다(둘 다 `credential_account_id`). 그래서 자격증명이
    만료·미연결이면 담당자 조회 단계에서 바로 `OAuthError`가 올라오고, 이
    함수는 그걸 따로 잡지 않는다 — `create_jira_issues()`까지 가서 같은
    이유로 또 실패하는 불필요한 호출을 만들지 않기 위함이다(그 함수 docstring
    참고).
    """

    # 쓰기 작업은 채팅에서 선택한 프로젝트 경계를 벗어나면 안 된다. 모델이
    # 프로젝트 이름을 Jira key로 오해하거나 임의의 key를 추측해도, proj_id가
    # 있으면 저장된 프로젝트 연결을 정본으로 사용한다. 프로젝트 문맥이 없는
    # 독립 호출에서만 사용자가 명시한 실제 Jira key를 허용한다.
    key = _resolve_project_key(
        proj_id=proj_id,
        account_id=account_id,
        project_key=None if proj_id else project_key,
    )
    credential_account_id = _jira_credential_account_id(account_id)
    # 기본은 미배정이다. 사용자가 명시적으로 자신에게 배정해 달라고 했을 때만
    # 요청자의 Jira accountId를 찾아 채운다. 이 조회는 실제 요청자를 알고 있는
    # 여기서 해야 한다 — 아래 Jira 호출은 연결 자격증명을 가진 팀장 계정으로
    # 실행되므로 그 안에서 찾으면 요청자가 아니라 팀장에게 배정될 수 있다.
    if assign_to_requester:
        issues = _fill_default_jira_assignee(
            requester_account_id=account_id,
            credential_account_id=credential_account_id,
            issues=issues,
        )
    result = create_jira_issues(
        account_id=credential_account_id,
        project_key=key,
        issues=issues,
    )
    created = list(result.get("created") or [])
    failed = list(result.get("failed") or [])
    if failed and not created:
        reasons = "; ".join(
            str(item.get("reason") or item.get("error_code") or "알 수 없는 오류")
            for item in failed
        )
        raise ToolInputError(f"Jira 이슈를 생성하지 못했습니다: {reasons}")
    return result


def _fill_default_jira_assignee(
    *, requester_account_id: str, credential_account_id: str, issues: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """사용자가 본인 배정을 명시한 이슈를 **요청자 자신**으로 채운다.

    2026-08-20 추가 — 실제로 겪은 문제: 담당자를 정하지 않고 등록을 시켰더니
    "등록하려면 Jira에서 필요한 다음 정보가 부족합니다 — 담당자: 누구에게
    배정할까요?"라고 되물었다. `assignee_account_id` 는 `jira_create_issues`
    의 필수 값이 아니다(`_JIRA_REQUIRED` 에 없음, `apps/connectors/clients.py`)
    — 되물은 건 서버가 막아서가 아니라 모델이 스스로 판단해 물은 것이었다.
    현재 기본 정책은 미배정이며, `_jira_create_issues()`가
    `assign_to_requester=True`를 받은 경우에만 이 함수를 호출한다.

    Jira 는 이메일이 아니라 Atlassian accountId 로만 배정을 받는다
    (`create_jira_issues` 의 GDPR 주석). 우리 계정과 Jira 계정을 잇는 저장된
    매핑이 없어 매번 이메일로 검색해야 하고, 그 검색은 "못 찾았다"로 끝날 수
    있다(계정 설정에 따라 이메일이 검색에 안 걸림, 동명이인으로 여러 건).
    **못 찾았을 뿐이면 억지로 채우지 않는다** — 빈 채로 넘긴다(팀이 이미
    정해 둔 원칙, `docs/설계 및 구현/3_중간발표 이후/설계/5_E2E_시나리오.md`: "막히면 담당자를 이슈
    본문에 적고 assignee는 비운다"). `find_jira_account_id_by_email` 이 이
    원칙대로 "못 찾음"엔 예외 없이 `None`을 돌려준다.

    **단, 자격증명 문제(`OAuthError`)는 여기서 안 삼킨다** — 2026-08-20 수정.
    `find_jira_account_id_by_email`이 쓰는 자격증명은 바로 아래
    `create_jira_issues()`가 쓸 것과 같다(둘 다 `credential_account_id`).
    여기서 만료·재연결 필요로 막혔다면 `create_jira_issues()` 호출도 반드시
    같은 이유로 막힌다 — 그런데도 여기서 삼키고 넘어가면, 실패할 걸 이미 아는
    Jira 요청(이슈 생성)을 한 번 더 보내는 것뿐이다. 그래서
    `find_jira_account_id_by_email`은 `OAuthError`를 그대로 올리도록 고쳤고,
    이 함수는 그걸 따로 잡지 않는다 — 호출한 `_jira_create_issues()`가 그
    자리에서 바로 실패해, `create_jira_issues()`까지 가는 불필요한 API 호출과
    그 결과를 기다리는 모델 턴을 아낀다.

    조회는 최대 한 번만 한다 — 담당자 없는 이슈가 여럿이어도 채울 사람은
    하나(요청자 자신)이므로 이슈마다 API 를 부를 이유가 없다.
    """

    if all(str(issue.get("assignee_account_id") or "").strip() for issue in issues):
        return issues

    email = AccountRepository.email(requester_account_id)
    default_assignee = (
        find_jira_account_id_by_email(account_id=credential_account_id, email=email)
        if email
        else None
    )
    if not default_assignee:
        return issues

    return [
        issue
        if str(issue.get("assignee_account_id") or "").strip()
        else {**issue, "assignee_account_id": default_assignee}
        for issue in issues
    ]


def _jira_get_issues(*, account_id: str, proj_id: str | None = None, project_key: str | None = None):
    """Jira 이슈 현황.

    **제너레이터다** — 결과를 이벤트로 내보내고 모델에게는 요약만 준다
    (`task_extraction` 과 같은 규칙). 이슈 15건을 모델이 문장으로 풀어 쓰면
    숫자를 옮겨 적다 틀릴 수 있고, 사람이 읽기에도 표가 낫다. 화면이 카드로
    그리고, 모델은 그 위에 한두 줄만 얹는다.
    """

    key = _resolve_project_key(proj_id=proj_id, account_id=account_id, project_key=project_key)
    issues = search_jira_issues(account_id=_jira_credential_account_id(account_id), project_key=key)

    counts = {"TO_DO": 0, "IN_PROGRESS": 0, "DONE": 0, "UNKNOWN": 0}
    for issue in issues:
        counts[issue.get("status_category") or "UNKNOWN"] += 1

    # 마감이 있는 미완료 건만, 이른 순으로. 지난 것도 뺀 채로 두지 않는다 —
    # 늦은 일이야말로 사람이 봐야 하는 것이다.
    upcoming = sorted(
        (
            issue
            for issue in issues
            if issue.get("due_at") and issue.get("status_category") != "DONE"
        ),
        key=lambda issue: issue["due_at"],
    )

    yield {
        "type": "jira_status",
        "project_key": key,
        "counts": counts,
        "issues": issues,
    }
    return {
        "project_key": key,
        "total": len(issues),
        "counts": counts,
        # 모델이 말할 거리. 전체 목록은 화면이 그린다.
        "upcoming": [
            {"key": issue["jira_issue_id"], "title": issue.get("summary"), "due": issue["due_at"]}
            for issue in upcoming[:5]
        ],
    }


#: `_get_current_datetime()` 가 요일을 한국어로 바로 주려고 쓰는 표
#: (`date.weekday()` — 0=월요일 ~ 6=일요일). `locale.setlocale()` 로 `%A` 를
#: 한국어로 바꾸는 방법도 있지만, 그건 프로세스 전역 상태라 이 요청과 무관한
#: 다른 코드의 날짜 포맷까지 같이 바뀐다(스레드 세이프하지도 않다) — 그래서
#: 이 튜플로 국지적으로만 옮긴다.
_WEEKDAY_KR = ("월", "화", "수", "목", "금", "토", "일")


def _get_current_datetime() -> dict[str, Any]:
    """지금 몇 시인지(Asia/Seoul 기준)를 있는 그대로 돌려준다. **LLM 을 안 쓴다.**

    2026-08-20 추가 — 실제로 겪은 문제: 사용자가 "이번 주 금요일 마감으로
    업무 등록해줘"라고 했는데, 이 대화가 타는 새 엔진(`services.agent_runtime`)
    의 시스템 프롬프트(`RUNTIME_SCAFFOLD`) 어디에도 오늘이 며칠인지가 없다
    (직접 확인 — `services/agent_runtime/prompts.py` 전체에 날짜 관련 문구가
    전혀 없다). 그래서 모델이 "이번 주 금요일의 정확한 날짜를 알려주세요"라고
    되물은 건 모델이 잘못한 게 아니라, `RUNTIME_SCAFFOLD`의 "확인하지 못한
    내용을 추측해서 채우지 않는다"는 지시를 정직하게 따른 것이다 — 채워 줄
    오늘 날짜 자체가 어디에도 없었다.

    시스템 프롬프트에 오늘 날짜를 미리 박아 넣는 대신 **도구**로 만든 이유:
    프롬프트에 박으면 그 값이 "언제 만들어진 프롬프트인지"에 고정돼, 오래
    떠 있는 세션에서 실제 시각과 어긋날 수 있다. 도구로 두면 모델이 필요한
    바로 그 순간(상대적 날짜 표현을 봤을 때)에 최신 값을 받는다.

    `task_register`/`jira_create_issues`처럼 `start_date`/`due_date`/`duedate`
    가 필요한 도구를 부르기 전, 사용자가 "내일"·"이번 주 금요일"·"다음 주
    월요일"처럼 상대적으로 말하면 **먼저 이 도구로 오늘 날짜를 확인하고,
    그 날짜를 기준으로 `YYYY-MM-DD`를 직접 계산해서 등록 도구에 넘긴다** —
    사용자에게 정확한 날짜를 되묻지 않는다.
    """
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    return {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "timezone": "Asia/Seoul",
        # 영문 요일(모델이 흔히 아는 이름)과 한국어 요일(이 계산에 바로 쓸 수
        # 있는 값)을 둘 다 준다 — 어느 쪽이 더 쓰기 편할지는 모델에게 맡긴다.
        "weekday": now.strftime("%A"),
        "weekday_kr": _WEEKDAY_KR[now.weekday()],
    }


def _skill_register(
    *,
    account_id: str,
    team_id: str,
    session_id: str | None = None,
    name: str,
    description: str,
    body: str,
) -> dict[str, Any]:
    """개인 스킬 검증 job을 만든다. **더 이상 SKILL.md를 바로 쓰지 않는다.**

    정본: docs/설계 및 구현/3_중간발표 이후/작업기록/Juyeon_Agents_Description/
          03_스킬_검증_등록_설계.md §5 ("`skill_register`의 새 계약")

    **2026-08-26 재작성.** 예전엔 `scope`(PERSONAL/TEAM)를 받아 그 자리에서
    바로 SKILL.md를 썼다. 이제는 다음 세 가지가 바뀌었다.

    1. `scope`가 없다 — 팀 스킬 직접 등록 경로 자체를 없앴다(정본 §2). 팀
       카탈로그는 검증을 통과한 개인 스킬을 공유해서만 채워진다
       (`share_personal_skill`, `MySkillShareAPIView`).
    2. 승인해도 즉시 등록되지 않는다 — `SkillRegistrationService.enqueue()`가
       `skill_registration_job`에 검증 요청만 남기고, 실제 SKILL.md 쓰기는
       `python manage.py skill_validation_worker`가 형식 검사(그리고 앞으로는
       트리거 정확도 테스트까지)를 통과시킨 뒤에만 한다.
    3. 반환값에 저장 경로가 없다 — 아직 파일이 없기 때문이다. 모델은 이
       결과를 "등록 완료"가 아니라 "검증을 시작했다"로 알려야 한다(아래
       `message`, 그리고 `skill_register` 도구 설명 자체에도 같은 지시가
       있다).

    **실제 검증·등록 로직은 `services.agent_runtime.skills.registration`에
    있다** — 설정 화면의 생성·수정 REST 뷰도 앞으로 같은 서비스를 쓴다
    (정본 §15 10번). 이름 검증·설명/본문 빈 값 검사·이름 충돌 거부는
    `enqueue()`와 워커의 `run_checking()`이 나눠서 한다(`registration.py`
    docstring 참고).
    """

    # 지연 import — services.agent_runtime과 backend.db는 이 파일(harness
    # 레거시 레이어)이 평소엔 끌고 들어올 이유가 없는 무거운 의존성(langgraph,
    # psycopg 등)을 진다. tools/adapters.py가 정반대 방향(agent_runtime ->
    # harness)으로 이미 지연 import를 쓰는 것과 같은 이유다.
    from services.agent_runtime.skills.service import SkillError

    from services.agent_runtime.skills.registration import SkillRegistrationService

    try:
        result = SkillRegistrationService.enqueue(
            account_id=account_id,
            team_id=team_id,
            name=name,
            description=description,
            body=body,
            source_session_id=session_id,
        )
    except SkillError as exc:
        # `SkillError`(및 그 하위 `SkillNameConflict`)는 이미 사람에게 그대로
        # 보여도 되는 한국어 문구다 — `ToolInputError` 관례(Jira/업무 등록과
        # 같은 자리)로 그대로 옮긴다.
        raise ToolInputError(str(exc)) from exc

    job = result.job
    if result.created:
        message = "스킬 검증을 시작했습니다. 결과는 작업 알림 또는 설정 > 스킬에서 확인해 주세요."
    else:
        # §9 "같은 사용자와 스킬 이름에는 열린 job을 하나만 허용한다" — 이미
        # 진행 중인 검증이 있으면 새로 만들지 않고 그 job을 그대로 돌려준다.
        message = "이미 같은 이름의 스킬 검증이 진행 중입니다. 그 결과를 기다려 주세요."

    return {
        # `job_id`는 DB에서 `uuid.UUID`로 온다 — 도구 결과는 JSON으로 나가야
        # 하므로 문자열로 바꾼다.
        "job_id": str(job["job_id"]),
        "status": job["status"],
        "stage": job["stage"],
        "message": message,
    }


def _skill_creator_ask_followup(*, question: str) -> dict[str, Any]:
    """`skill-creator` 스킬이 스킬 초안을 짓는 데 필요한 정보가 부족할 때,
    사용자에게 한 번에 하나씩 되묻는다(2026-08-24).

    **이 핸들러는 정상 경로에서 실제로 실행되지 않는다.** `side_effect=True`
    라 `HumanInTheLoopMiddleware` 확인이 걸리는데, 화면(ChatCards.tsx)은 이
    도구 이름을 보면 승인/거절 버튼 대신 질문+입력창 카드를 그리고,
    사용자가 입력한 답을 `"respond"` 결정(`{"type": "respond", "message":
    <입력한 답>}`)으로 돌려보낸다 — langchain
    `HumanInTheLoopMiddleware._process_decision()`이 `respond`일 때는 이
    핸들러를 아예 안 부르고, 그 `message`를 이 도구가 반환한 것처럼
    모델에게 그대로 돌려준다(실측: `langchain/agents/middleware/
    human_in_the_loop.py`). 즉 이 함수 본문은 "화면이 다른 이유로 승인
    버튼을 눌러 approve가 들어온" 방어적인 경우에만 돈다 — 그때도 대화가
    깨지지 않게 질문을 그대로 돌려준다.
    """

    return {
        "question": question,
        "note": (
            "이 값은 핸들러의 기본 반환값입니다. 사용자의 실제 답변이 아니라 "
            "이 문장이 보인다면 승인 카드가 예상과 다르게 처리된 것입니다."
        ),
    }


#: 내장 도구. `tool_ref` 는 agent_version_tools 에 저장되는 값과 같아야 한다.
BUILTIN_TOOLS: dict[str, Tool] = {
    "get_current_datetime": Tool(
        ref="get_current_datetime",
        name="현재 날짜/시간 조회",
        description=(
            "지금(Asia/Seoul 기준) 날짜·시간·요일을 돌려준다. 사용자가 "
            "「내일」·「이번 주 금요일」·「다음 주 월요일」처럼 **상대적으로 "
            "날짜를 말하면**, task_register 나 jira_create_issues 를 부르기 "
            "전에 이 도구로 오늘 날짜를 먼저 확인하고 YYYY-MM-DD 로 직접 "
            "계산해서 넘긴다. 정확한 날짜를 사용자에게 되묻지 않는다."
        ),
        input_schema={"type": "object", "properties": {}, "required": []},
        handler=_get_current_datetime,
        category="일반",
    ),
    "document_search": Tool(
        ref="document_search",
        name="문서 검색",
        description=(
            "팀에 등록된 문서에서 질의와 관련된 문장을 찾아 근거로 돌려준다. 일정·범위처럼 "
            "여러 하위 항목을 묻는 질문은 한 번의 넓은 검색으로 끝내지 말고, 확인되지 않은 "
            "하위 항목을 각각 구체적으로 다시 검색한다. 관련 문서 ID만 반환됐다고 그 문서의 "
            "모든 세부 값을 확인한 것은 아니다. WBS나 과업의 세부 일정을 찾을 때는 발견한 "
            "하위 작업 명칭과 `작업 공수 기간`을 한 질의에 함께 넣고 `top_k=20`으로 검색한다. "
            "같은 일반 질의를 반복하지 않는다. 직접 반환된 문장에서 값을 확인한 사실만 답에 쓴다."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "찾고 싶은 내용을 한국어 문장으로"},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 20, "default": 10},
            },
            "required": ["query"],
        },
        handler=_document_search,
        category="문서",
    ),
    "people_list": Tool(
        ref="people_list",
        name="팀원 조회",
        description=(
            "우리 팀 명부를 읽어 팀원의 이름·직책·기술 스택을 돌려준다. "
            "누가 있는지, 누구에게 맡길지 같은 **사람에 대한 질문**은 문서 검색이 아니라 이 도구다."
        ),
        input_schema={"type": "object", "properties": {}, "required": []},
        handler=_people_list,
        # HR로 묶는다(2026-08-18) — workload_report/absence_list와 같이 전부
        # `backend/services/hr`(팀원 명부·역량·부재)가 원본이다. 도구 선택
        # 화면에서 "사람에 관한 도구"를 하나로 보기 쉽게 하려는 것(지훈 요청,
        # "비슷한 커넥터별로 묶자"의 첫 걸음).
        category="HR",
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
        category="HR",
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
        category="업무 추출(AI)",
    ),
    "project_list": Tool(
        ref="project_list",
        name="프로젝트 조회",
        description=(
            "우리 팀의 프로젝트 목록과 진행률을 돌려준다. "
            "「무슨 프로젝트가 있나」·「어느 게 늦었나」처럼 **프로젝트 전반**에 대한 "
            "질문은 문서 검색이 아니라 이 도구다."
        ),
        input_schema={"type": "object", "properties": {}, "required": []},
        handler=_project_list,
        category="프로젝트",
    ),
    "task_list": Tool(
        ref="task_list",
        name="등록된 업무 조회",
        description=(
            "이 프로젝트에 등록된 **우리 업무**를 읽는다(task_register 로 넣은 것). "
            "Jira 이슈가 아니다 — Jira 쪽은 jira_get_issues 다. "
            "**여기가 비어 있다고 해서 일이 없는 것은 아니다** — 「업무 현황」처럼 "
            "출처를 가리지 않는 물음에 이것만 보고 「없습니다」라고 답하지 않는다. "
            "Jira 도 붙어 있으면 그쪽을 확인한 뒤에 답한다."
        ),
        input_schema={"type": "object", "properties": {}, "required": []},
        handler=_task_list,
        category="업무 관리",
    ),
    "document_list": Tool(
        ref="document_list",
        name="문서 목록",
        description=(
            "팀에 어떤 문서가 있는지 목록으로 돌려준다. **내용 검색이 아니다** — "
            "「무슨 문서 있어?」는 이 도구이고, 「이 내용이 어디 있어?」는 document_search 다. "
            "아직 색인되지 않은 문서도 그 사실과 함께 준다. "
            "`documents` 는 읽어 들인 문서이고, `not_collected` 는 **연결된 저장소에는 "
            "있지만 아직 읽지 않은 파일**이다 — 둘 다 사람에게는 「우리 문서」이므로 "
            "함께 말하되, 안 읽은 파일은 내용을 근거로 쓸 수 없다는 것을 밝힌다. "
            "`storage_folders` 가 있는데 양쪽이 다 비었으면 「연결은 됐지만 저장소가 "
            "비어 있다」는 뜻이다 — 「문서가 없다」로 뭉뚱그리지 않는다."
        ),
        input_schema={"type": "object", "properties": {}, "required": []},
        handler=_document_list,
        category="문서",
    ),
    "table_export": Tool(
        ref="table_export",
        name="표 내보내기",
        description=(
            "표 하나를 엑셀 파일(.xlsx)로 만들어 사용자의 「내 파일」에 저장한다. "
            "「엑셀로 뽑아 줘」·「파일로 받고 싶어」처럼 **결과를 파일로 달라고 할 때** 쓴다. "
            "표는 이 도구가 만들어 주지 않는다 — 다른 도구(task_list·workload_report·"
            "jira_get_issues 등)로 먼저 값을 얻은 뒤, 그 값을 `columns` 와 `rows` 로 "
            "직접 옮겨 넘긴다. **값을 지어내거나 바꾸지 않는다** — 모르는 칸은 비운다. "
            "`rows` 의 각 행은 `columns` 와 **같은 순서**의 목록이다."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "표 제목. 시트 이름과 파일 이름에 쓴다(예: 「업무 목록」)",
                },
                "columns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "열 이름. 왼쪽부터의 순서다",
                },
                "rows": {
                    "type": "array",
                    "items": {"type": "array"},
                    "description": "행 목록. 각 행은 columns 와 같은 순서의 값 목록. 모르는 칸은 null",
                },
            },
            "required": ["title", "columns", "rows"],
        },
        handler=_table_export,
        # 사용자의 서재에 파일을 만든다. 되돌리려면 사람이 지워야 하므로 승인을 받는다.
        side_effect=True,
        category="문서",
    ),
    "document_create": Tool(
        ref="document_create",
        name="문서 만들기",
        description=(
            "글 한 편을 워드 파일(.docx)로 만들어 사용자의 「내 파일」에 저장한다. "
            "「워드로 정리해 줘」·「문서로 만들어 줘」·「보고서로 뽑아 줘」처럼 "
            "**결과를 문서 파일로 달라고 할 때** 쓴다. 회의록 정리·요약본·보고서가 이것이다. "
            "`body` 는 마크다운으로 적는다 — `#`~`###` 제목, `- ` 목록, `1. ` 번호 목록, "
            "`**굵게**` 만 문서에 반영되고 나머지 문법은 글자 그대로 남으니 쓰지 않는다. "
            "**표가 주된 내용이면 이 도구가 아니라 table_export 로 엑셀을 만든다.** "
            "문서에 담을 내용을 지어내지 않는다 — 근거가 없는 항목은 비우거나 빼고 쓴다."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "문서 제목. 파일 이름에도 쓴다(예: 「2026-08-26 회의록」)",
                },
                "body": {
                    "type": "string",
                    "description": "본문. 위에 적힌 마크다운 문법만 쓴다",
                },
            },
            "required": ["title", "body"],
        },
        handler=_document_create,
        # 사용자의 서재에 파일을 만든다. `table_export` 와 같은 이유로 승인을 받는다.
        side_effect=True,
        category="문서",
    ),
    "document_sync": Tool(
        ref="document_sync",
        name="문서 변경 확인",
        description=(
            "연결된 문서 저장소에서 **방금 바뀐 것**을 지금 확인해 반영한다. "
            "사용자가 「문서를 수정했다」·「새로 올렸다」·「최신 내용으로 다시 봐 달라」고 "
            "할 때 부른다. 대화를 열 때 이미 한 번 확인하므로, **그냥 문서를 찾는 "
            "질문에는 부르지 않는다** — 그때는 document_search 다. "
            "바뀐 문서가 있으면 다시 읽어 들이느라 **몇 분 걸릴 수 있다.** "
            "`checked` 가 false 면 확인 자체를 못 한 것이니 `note` 를 그대로 전한다."
        ),
        input_schema={"type": "object", "properties": {}, "required": []},
        handler=_document_sync,
        category="문서",
    ),
    "task_update": Tool(
        ref="task_update",
        name="업무 수정",
        description=(
            "등록된 업무의 상태나 마감을 바꾼다. 상태는 PROPOSED(제안) · "
            "CONFIRMED(확정) · REJECTED(반려) 중 하나다. "
            "task_id 는 task_list 가 준 값을 그대로 쓴다 — 지어내지 않는다. "
            "사용자 승인 없이는 실행되지 않는다."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "task_list 가 준 id"},
                "status": {
                    "type": "string",
                    "enum": ["PROPOSED", "CONFIRMED", "REJECTED"],
                },
                "due_at": {"type": "string", "description": "YYYY-MM-DD"},
            },
            "required": ["task_id"],
        },
        handler=_task_update,
        side_effect=True,
        category="업무 관리",
    ),
    "web_search": Tool(
        ref="web_search",
        name="웹 검색",
        description=(
            "인터넷에서 찾아 출처와 함께 돌려준다. **팀 문서에 있을 만한 것은 "
            "document_search 로 먼저 찾는다** — 우리 문서가 우선이고, 웹은 문서에 "
            "없거나 최신 정보가 필요할 때다. "
            "이 결과로 답할 때는 **출처 URL 을 반드시 함께 밝힌다** — 검증된 우리 "
            "문서와 같은 무게로 말하지 않는다."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "찾고 싶은 것을 한 문장으로"},
            },
            "required": ["query"],
        },
        handler=_web_search,
        category="웹 검색",
    ),
    "absence_list": Tool(
        ref="absence_list",
        name="부재 조회",
        description=(
            "앞으로 몇 주간 팀원의 승인된 부재(휴가·교육 등)를 돌려준다. "
            "「누가 언제 자리를 비우나」·「왜 이 사람 여유가 없나」의 근거다."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "weeks": {"type": "integer", "minimum": 1, "maximum": 12, "default": 4},
            },
            "required": [],
        },
        handler=_absence_list,
        category="HR",
    ),
    "task_register": Tool(
        ref="task_register",
        name="업무 등록",
        description=(
            "추출한 업무를 **우리 플랫폼의 프로젝트 업무**로 등록한다. 사용자가 우리 플랫폼의 "
            "업무 등록을 요청했을 때만 사용한다. **Jira 등록의 선행 단계가 아니다.** 사용자가 "
            "Jira만 명시했다면 이 도구를 함께 호출하지 않는다. 두 시스템 모두에 등록하라는 "
            "명시적 요청이 있을 때만 각각의 등록 도구를 사용한다. 사용자 승인 없이는 실행되지 않는다. "
            "날짜는 `YYYY-MM-DD` 만 저장된다 — 「5일 이내」 같은 상대 표현은 비운 채 등록한다. "
            "**모르는 값을 `0` 이나 빈 문자열로 채우지 마라** — 공수 0 은 「0시간짜리 업무」라는 "
            "뜻이 되어 배정과 진행률을 망가뜨린다. 모르면 그 칸을 아예 빼고 보낸다. "
            "그렇게 채워 보낸 값은 저장되지 않고 `dropped_fields` 로 돌아오니, **등록됐다고 "
            "말하지 말고** 그 목록을 사람에게 그대로 알린다. "
            "이 프로젝트에 **이미 같은 제목의 업무가 있으면 건너뛴다** — 그 목록은 "
            "`already_registered` 로 돌아온다. 그것도 사람에게 알린다."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "required_role": {
                                "type": "string",
                                "description": (
                                    "이 업무를 하는 데 필요한 **역할/직무** — 예: "
                                    "'백엔드 개발자', '디자이너'. **사람이 아니다.** "
                                    "이름, '내 담당', '나', '누구누구 배정' 같은 배정 "
                                    "표현을 넣지 않는다 — 지금 이 표에는 담당자(누가 할지)를 "
                                    "적는 칸이 따로 없다. 근거에서 필요한 역할을 확인하지 "
                                    "못했으면 이 칸을 아예 빼고 보낸다."
                                ),
                            },
                            "effort_hours": {"type": "number"},
                            "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                            "due_date": {"type": "string", "description": "YYYY-MM-DD"},
                            "priority": {"type": "string"},
                        },
                        "required": ["title"],
                    },
                },
            },
            "required": ["tasks"],
        },
        handler=_task_register,
        # 우리 데이터를 바꾸고, 사람이 결과를 확정하는 지점이다.
        side_effect=True,
        category="업무 관리",
    ),
    "jira_create_issues": Tool(
        ref="jira_create_issues",
        name="Jira 이슈 생성",
        description=(
            "확인받은 업무를 Jira 프로젝트에 이슈로 등록한다. 여러 건을 한 번에 보내고, "
            "건별 성공·실패를 그대로 돌려준다. 사용자 승인 없이는 실행되지 않는다. "
            "사용자가 Jira 등록을 명시했다면 이 도구를 직접 사용한다. 우리 플랫폼에도 함께 "
            "등록하라는 요청이 없으면 `task_register`를 추가로 호출하지 않는다. "
            "**담당자를 되묻지 마라** — `assignee_account_id` 는 필수가 아니며 기본은 "
            "미배정이다. 사용자가 명시적으로 자신에게 배정해 달라고 했을 때만 "
            "`assign_to_requester=true`로 보낸다. "
            "사용자가 이름이나 이메일로 다른 사람을 짚었을 때만 그 사람을 뜻하는 값을 "
            "고민하되, 우리에게는 그 사람의 Jira accountId 를 알아낼 방법이 아직 없으니 "
            "이 칸은 비워 두고 담당자 이름은 `description` 본문에 적어 사람이 나중에 "
            "Jira 에서 직접 지정하게 한다."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "project_key": {
                    "type": "string",
                    "description": (
                        "등록할 Jira 프로젝트 키. **보통 비워 둔다** — 이 대화가 속한 "
                        "프로젝트의 Jira 를 서버가 찾아 쓴다. 사용자가 다른 프로젝트를 "
                        "명시적으로 짚었을 때만 적는다."
                    ),
                },
                "assign_to_requester": {
                    "type": "boolean",
                    "description": (
                        "사용자가 명시적으로 '나에게 배정'처럼 요청자 본인 배정을 "
                        "요구한 경우에만 true. 별도 지시가 없으면 false로 두어 미배정한다."
                    ),
                },
                "issues": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                            "issuetype": {"type": "string", "description": "Task · Story 등"},
                            "assignee_account_id": {
                                "type": "string",
                                "description": (
                                    "Jira Atlassian accountId (이메일 아님). **보통 비워 둔다** "
                                    "— 비우면 미배정으로 생성한다. 사용자가 이 accountId 값 "
                                    "자체를 알려줬을 때만 적는다."
                                ),
                            },
                            "duedate": {"type": "string", "description": "YYYY-MM-DD"},
                        },
                        "required": ["title", "issuetype"],
                    },
                },
            },
            "required": ["issues"],
        },
        handler=_jira_create_issues,
        # 남의 Jira 에 이슈를 만든다. 승인 게이트를 반드시 탄다(8/11 확정 ③).
        side_effect=True,
        category="Jira",
    ),
    "jira_get_issues": Tool(
        ref="jira_get_issues",
        name="Jira 이슈 조회",
        description=(
            "Jira 프로젝트의 기존 이슈와 진행 상황을 읽는다. "
            "프로젝트 키는 **묻지 않는다** — 이 대화가 속한 프로젝트의 Jira 를 서버가 찾아 쓴다."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "project_key": {
                    "type": "string",
                    "description": "보통 비워 둔다. 사용자가 다른 프로젝트를 짚었을 때만 적는다.",
                }
            },
            "required": [],
        },
        handler=_jira_get_issues,
        category="Jira",
    ),
    "skill_register": Tool(
        ref="skill_register",
        name="스킬 등록",
        description=(
            "반복되는 업무 절차를 개인 스킬 초안으로 만들어 검증 대기열에 올린다. "
            "사용자가 '이 방식을 스킬로 등록해줘'처럼 명시적으로 요청했을 때만 부른다. "
            "**승인된다고 즉시 등록되지 않는다** — 백그라운드 검증을 통과해야 "
            "내 스킬에 등록된다. 이 도구는 항상 요청한 계정 본인의 개인 스킬만 "
            "만든다(팀 스킬은 검증을 통과한 개인 스킬을 설정 화면에서 공유해야만 "
            "생긴다 — 이 도구로는 팀 스킬을 직접 만들 수 없다). "
            "등록에 필요한 값이 충분하면 채팅 답변으로 승인을 따로 묻지 말고 "
            "이 도구를 호출한다 — 실제 검증 시작 여부는 시스템 확인 카드에서 "
            "사용자가 정한다. "
            "name은 소문자·숫자·하이픈만 쓰고(예: "
            "'jira-이슈-생성-절차'가 아니라 'jira-issue-registration'), 64자를 넘지 않게 "
            "짓는다. body는 이 대화에서 실제로 처리한 절차를 일반화한 것이어야 한다 — "
            "한 번의 사례를 그대로 절차라고 우기지 말고, 재사용 가능한 단계로 정리한다. "
            "**이 도구가 돌려주는 결과는 등록 완료가 아니라 검증 시작이다** — "
            "'등록했습니다'라고 말하지 말고, '검증을 시작했으며 결과는 작업 알림이나 "
            "설정 > 스킬에서 확인할 수 있다'고 안내한다."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "소문자·숫자·하이픈만, 64자 이내. 하이픈으로 시작·끝나거나 연달아 쓸 수 없다.",
                },
                "description": {
                    "type": "string",
                    "description": "이 스킬이 무엇을 하는지, 언제 쓰는지. 1024자 이내.",
                },
                "body": {
                    "type": "string",
                    "description": "SKILL.md 본문 — 마크다운으로 적은 절차.",
                },
            },
            "required": ["name", "description", "body"],
        },
        handler=_skill_register,
        # DB나 외부 API는 아니지만 검증 job을 만들고 통과하면 Store에 새 스킬이
        # 생기는 지점이라 승인 게이트를 탄다(task_register와 같은 이유).
        side_effect=True,
        category="Skill",
    ),
    "skill_creator_ask_followup": Tool(
        ref="skill_creator_ask_followup",
        name="스킬 생성 — 되묻기",
        description=(
            "새 스킬(SKILL.md)을 만드는 데 필요한 정보가 부족할 때, 사용자에게 "
            "질문 하나를 되묻는다. **한 번 호출에 질문 하나만** 담는다 — 여러 "
            "질문이 있으면 답을 받은 뒤 다시 부른다. '이대로 등록할까요?' 같은 "
            "승인 확인에는 쓰지 않는다 — 그건 skill_register의 확인 카드가 "
            "이미 한다. 이 도구는 등록 여부가 아니라 등록에 쓸 **내용 자체가 "
            "부족할 때만** 부른다. 사용자에게는 짧고 쉬운 질문 한 가지만 "
            "보여준다. `트리거`, `입력 항목`, `출력 형식`, `절차`, `제약`, "
            "`SKILL.md` 같은 내부 용어와 왜 묻는지에 대한 설명은 쓰지 않는다. "
            "예시가 필요하면 짧은 표현 하나만 덧붙인다. 실제 메일 수신자, "
            "번역할 문장, 요약할 문서처럼 지금 처리할 데이터는 요구하지 않는다."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "maxLength": 160,
                    "description": (
                        "사용자에게 그대로 보여줄 짧고 쉬운 질문 한 문장. 내부 "
                        "용어나 질문 이유는 쓰지 않는다. 예시는 필요할 때만 "
                        "줄을 바꿔 짧게 하나 붙인다. 실행할 실제 데이터는 요구하지 "
                        "않는다."
                    ),
                }
            },
            "required": ["question"],
        },
        handler=_skill_creator_ask_followup,
        # side_effect=True인 이유는 다른 write 도구와 다르다 — 외부 상태를
        # 바꿔서가 아니라, 이 값이 있어야 factory.py의 interrupt_on 계산에
        # 자동으로 포함되어(그 파일 build() 주석 참고) 사람이 답할 때까지
        # 실행이 멈추기 때문이다. `_skill_creator_ask_followup` docstring 참고.
        side_effect=True,
        category="Skill",
    ),
}


#: 고르고 말고가 없는 내장 도구 — 모든 에이전트에 무조건 붙는다(2026-08-22).
#:
#: `skill_register`는 원래 다른 내장 도구(HR·Jira 등)와 같은 자리에서 팀장이
#: 에이전트마다 켜고 끄는 것이었다. 그런데 스킬을 **읽는** 쪽(SkillsMiddleware
#: 배선, `factory.py` `build()` — `skill_sources`)은 애초부터 도구 선택과
#: 무관하게 모든 에이전트에 항상 붙어 있었다 — memory_provider/skills_provider가
#: 있으면 무조건이다. **등록(쓰기)만 골라야 하는 도구로 남아 있는 게 이 둘을
#: 어긋나게 했다** — 에이전트가 이미 등록된 스킬은 항상 읽을 수 있는데,
#: 새 스킬을 등록해 달라는 요청은 이 도구가 꺼져 있으면 못 들어주는 비대칭이
#: 생긴다. GP(General Purpose 서브에이전트)가 같은 이유로 켜고 끄는 스위치
#: 없이 항상 붙는 것(`factory.py`의 "위험하지 않으므로, 있으나 마나 한
#: 선택지를 만들 이유가 없다" 판단)과 같은 논리를 여기도 적용한다 —
#: `skill_register`는 `side_effect=True`라 어차피 사람 승인 없이는 실행되지
#: 않으니, 켜고 끄는 선택 자체가 의미가 없다.
#:
#: 실행 시점엔 `services/agent_runtime/tools/loader.py`의 `ToolLoader.load()`가
#: `agent_version_tools` 저장 여부와 무관하게 넣고, 선택 화면
#: (`apps/agents/serializers.py`의 `builtin_tool_response()`)에서도 뺀다 —
#: 고를 필요 없는 항목이 선택 목록에 남아 있으면 "이건 꺼도 되나?"라는
#: 오해를 만든다. 예전에 이 도구를 선택해 저장해 둔 에이전트가 있어도
#: 막히지 않는다 — `api_views.py`의 `_tool_catalog()`가 검증 카탈로그에는
#: 이 도구를 넣어 둔다(고르는 화면은 좁게, 검증은 넉넉하게).
#: 2026-08-24 — `skill_creator_ask_followup`도 같은 이유로 항상 켠다. 이
#: 도구 혼자서는 아무 것도 못 하고(스킬을 실제로 저장하는 건 여전히
#: `skill_register`), 새 스킬을 만드는 대화 흐름 전체가 이 도구를 쓸 수
#: 있어야만 성립한다 — 하나만 켜고 다른 하나는 꺼져 있으면 스킬 생성
#: 중간에 되물을 방법이 없어 그 자리에서 막힌다.
ALWAYS_ON_TOOL_REFS: frozenset[str] = frozenset({"skill_register", "skill_creator_ask_followup"})

# 레거시 A2A 섹션(`agent:` 위임 도구, `load_for_agent`/`load_for_refs`/`resolve`)과
# MCP 도구 팩토리(`_mcp_tool()`)가 여기 있었다. A2A 는 2026-08-22에, `_mcp_tool()`
# 은 2026-08-25에 걷어냈다 — 둘 다 마지막 호출자가 없어진 뒤였다.
#
# 위임은 새 엔진의 `agent_version_subagents`/`SubagentReference`가 완전히 다른
# 메커니즘으로 대체한다(services/agent_runtime/subagents/). MCP 도구 조립은
# `services/agent_runtime/tools/adapters.py`의 `adapt_mcp_tools()`가 맡는다 —
# "MCP 도구는 부작용이 있다고 본다"(list_tools 응답에 읽기/쓰기 구분이 없으므로
# 안전한 쪽으로 가정)는 판단도 그쪽으로 옮겨 갔다. `ALWAYS_ON_TOOL_REFS`가 하던
# "항상 켜진 도구" 역할은 `services/agent_runtime/tools/loader.py`의
# `ToolLoader.load()`로 옮겼다.



# ---------------------------------------------------------------------------
# 에이전트별 조립
# ---------------------------------------------------------------------------


