from __future__ import annotations

from typing import Literal

from django.conf import settings
from openai import OpenAI
from pydantic import BaseModel, Field

from backend.db.document_pipeline import VectorSearchRepository, document_outline
from services.document_pipeline.errors import PipelineConfigurationError
from services.document_pipeline.runpod_client import embed_queries


Intent = Literal[
    "TASK_DISCOVERY", "TASK_CORE", "ASSIGNMENT_REQUIREMENT", "EXECUTION_CONDITION"
]


class QueryPlan(BaseModel):
    intent: Intent
    queries: list[str] = Field(min_length=1, max_length=3)
    # 문서 하나가 수백 청크라 5건은 얇다. 근거는 중복 제거 후 상위 20건만 쓰므로
    # 넉넉히 뽑아도 최종 프롬프트는 커지지 않는다.
    top_k: int = Field(default=10, ge=1, le=20)


class ExtractedTask(BaseModel):
    title: str
    description: str
    required_role: str | None = None
    required_skills: list[str] = Field(default_factory=list)
    effort_hours: float | None = None
    start_date: str | None = None
    due_date: str | None = None
    priority: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    # 모델은 UUID 가 아니라 `E1` 같은 짧은 번호로 인용한다. 36자 UUID 를 옮겨
    # 적게 하면 한 글자만 틀려도 추출 전체가 실패한다 — 실제로 그렇게 죽었다
    # (2026-08-05). 번호는 서버가 chunk_id 로 되돌린다.
    evidence_refs: list[str] = Field(min_length=1)


class ExtractionResult(BaseModel):
    tasks: list[ExtractedTask] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


#: (의도, 에이전트에게 주는 지시, 화면에 띄울 라벨).
#:
#: 지시와 라벨을 가른다. 하나로 쓰다가 프롬프트 문장이 모달에 그대로 떴다
#: (2026-08-05). 에이전트에게는 자세히, 사람에게는 짧게 말해야 한다.
STAGES: list[tuple[Intent, str, str]] = [
    # 제안요청서에서 「할 일」은 사업관리 요구사항이 아니라 과업 절에 있다.
    # 그 자리를 짚어 주지 않으면 보고·산출물·보안 같은 관리 항목만 잡힌다
    # (2026-08-05). 실제로 실행 과업이 한 건도 안 뽑힌 적이 있다.
    (
        "TASK_DISCOVERY",
        "발주자가 만들어 내라고 요구한 결과물과 그것을 만드는 과업. "
        "주요 과제·추진 내용·세부과제·사업 범위·기능 요구사항 쪽을 본다. "
        "보고·검수·산출물 제출·보안 같은 사업관리 절차는 여기서 찾지 않는다",
        "수행할 업무 찾기",
    ),
    ("TASK_CORE", "요구사항, 산출물, 완료 기준", "요구사항·산출물·완료 기준"),
    ("ASSIGNMENT_REQUIREMENT", "담당 역할과 필수 기술 또는 경험", "담당 역할·필수 기술"),
    (
        "EXECUTION_CONDITION",
        "공수, 일정, 우선순위, 의존성, 제약, 위험",
        "공수·일정·제약·위험",
    ),
]


def _client(api_key: str | None = None) -> OpenAI:
    # **모델은 더 이상 `.env` 가 정하지 않는다 (2026-08-12).** 부른 에이전트가
    # 들고 오고, 못 받으면 아래 상수로 떨어진다. 여기서 볼 것은 키뿐이다.
    if not str(api_key or settings.OPENAI_API_KEY).strip():
        raise PipelineConfigurationError("필수 OpenAI 설정이 없습니다: OPENAI_API_KEY")
    # 기본 타임아웃은 10분이고 재시도가 2회라, 응답이 안 오면 30분을 매단다.
    # 시연 중에는 그 전에 실패를 알려 주는 편이 낫다.
    return OpenAI(api_key=api_key or settings.OPENAI_API_KEY, timeout=300, max_retries=1)


#: 이 서비스가 아는 모델. 오타로 엉뚱한 모델이 조용히 쓰이지 않게 막는다.
SUPPORTED_MODELS = {"gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"}
#: **Claude 는 여기 없다.** 이 파이프라인은 `responses.parse`(구조화 출력)로
#: 근거 참조를 강제하는데(`evidence_refs` 최소 1개), Anthropic 의 OpenAI 호환
#: 경로에는 Responses API 가 없다. 부른 에이전트가 Claude 면 추출만 설정된
#: 기본 모델로 떨어지고, 그 사실을 결과에 적어 사람에게 알린다(2026-08-12).

#: 근거를 정리해 업무로 쓰는 단계. **이 파이프라인의 품질이 여기서 갈린다.**
#: 에이전트가 아는 모델을 주면 그것을 쓰고, 아니면 이 값이다.
DEFAULT_WRITE_MODEL = "gpt-5.6-sol"

#: 그 단계의 추론 강도. 낮추면 근거 연결이 눈에 띄게 흐트러져 고정한다 —
#: 예전에는 `.env` 가 xhigh 가 아니면 아예 거절했다.
WRITE_EFFORT = "xhigh"

#: 검색어를 만드는 단계의 모델. 짧은 판단이라 싼 것으로 충분하다.
PLAN_MODEL = "gpt-5.6-luna"

#: 검색어를 만드는 단계의 추론 강도.
#:
#: 최종 정리는 `WRITE_EFFORT`(xhigh)를 쓰지만, 이 단계는 한국어
#: 검색 질의 1~3개를 뽑는 일이다. 2026-08-05 실측에서 low 2.9초 / xhigh 5.6초였고
#: **xhigh 쪽 결과가 오히려 나빴다** — 세 번째 질의가 여러 문장이 이어 붙은 덩어리로
#: 나와 임베딩 검색에 불리했다. 판단이 필요한 곳에만 추론을 쓴다.
#:
#: 모델도 이 단계만 따로 둔다(`PLAN_MODEL`). 같은 프롬프트로 잰 결과다:
#:
#:   luna   2.8초   출력 192 토큰
#:   terra  2.9초   출력 135 토큰
#:   sol   53.3초   출력 4,883 토큰   ← 질의 3개에 이만큼 쓰고 품질도 나빴다
#:
#: Sol 은 출력 단가가 Luna 의 25배라, 이 단계를 Sol 로 돌리면 한 번 추출에
#: 검색어 만드는 값만 $0.6 가 나간다.
PLAN_EFFORT = "low"

#: 프롬프트에 넣고 화면에 돌려줄 근거 필드.
#:
#: `vec_idx.metadata` 를 통째로 넣던 것을 걷어냈다(2026-08-05). bbox 좌표·binary_hash·
#: 임시 파일명이 들어 있어 평균 927자, 최대 7,622자였고 근거 20건이면 프롬프트의
#: 대부분이 그것이었다. 모델이 쓸 수 없는 값이고 화면도 안 쓴다.
EVIDENCE_FIELDS = ("chunk_id", "doc_id", "heading_path", "text", "intent", "query", "retrieval_score")


def _evidence_view(row: dict) -> dict:
    return {key: row[key] for key in EVIDENCE_FIELDS if key in row}


#: 최종 정리에 넘길 근거 수와, 그중 기준 문서가 아닌 문서에 내줄 최대 자리.
#:
#: 팀 문서 전체를 뒤지므로 관련 없는 문서가 근거를 잠식할 수 있다. 실제로 다른
#: 사업의 감리 과업지시서가 20자리 중 8자리를 가져가면서 기준 문서의 실제 과업
#: 청크를 밀어냈다(2026-08-05). 프로젝트를 정의하는 것은 기준 문서이므로 대부분의
#: 자리를 거기에 두고, 나머지 문서는 보조 근거로만 들어온다.
EVIDENCE_LIMIT = 20
SUPPORT_LIMIT = 6


def _rank_evidence(rows: list[dict], primary_doc_id: str) -> list[dict]:
    def score(row: dict) -> float:
        return float(row.get("retrieval_score") or 0)

    ranked = sorted(rows, key=score, reverse=True)
    primary = [row for row in ranked if row.get("doc_id") == primary_doc_id]
    support = [row for row in ranked if row.get("doc_id") != primary_doc_id][:SUPPORT_LIMIT]
    selected = primary[: EVIDENCE_LIMIT - len(support)] + support
    return sorted(selected, key=score, reverse=True)[:EVIDENCE_LIMIT]


def _query_plan(
    client: OpenAI, *, intent: Intent, need: str, title: str, outline: str, used: list[str]
) -> QueryPlan:
    response = client.responses.parse(
        model=PLAN_MODEL,
        service_tier=settings.OPENAI_SERVICE_TIER,
        reasoning={"effort": PLAN_EFFORT},
        input=[
            {
                "role": "system",
                "content": (
                    "VectorDB 업무 근거 검색어 생성 전담 에이전트다. 업무를 만들거나 답하지 말고 "
                    "부족 정보를 찾는 한국어 검색 질의만 만든다. 이미 사용한 질의를 반복하지 않는다.\n"
                    # 제목을 질의에 넣으면 검색 대상이 그 문서인데도 변별력이 0이고,
                    # 벡터가 「제목처럼 생긴 텍스트」로 끌려간다. 실제로 목차 줄과
                    # 제안서 양식 표가 근거 1·2위로 올라왔다(2026-08-05).
                    "문서 제목·파일명·날짜를 질의에 넣지 않는다. 이미 그 문서 안에서 찾으므로 "
                    "구분에 도움이 되지 않고, 목차나 표지 같은 제목성 텍스트가 대신 검색된다.\n"
                    "따옴표·불리언 연산자를 쓰지 않는다. 키워드 검색이 아니라 의미 검색이다.\n"
                    "찾으려는 내용이 본문에 적혀 있을 법한 자연스러운 어구로 쓴다. "
                    "예: '투입 인력의 역할과 자격 요건', '단계별 산출물과 검수 기준'."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"intent={intent}\n필요 정보={need}\n"
                    # 제목만 주면 주제를 모른 채 일반 사업관리 문장을 만든다.
                    # 문서가 무엇에 대한 것인지는 첫머리에 적혀 있다.
                    f"기준 문서={title}\n기준 문서 첫머리:\n{outline}\n"
                    f"기존 질의={used}"
                ),
            },
        ],
        text_format=QueryPlan,
    )
    plan = response.output_parsed
    if plan is None or plan.intent != intent:
        raise ValueError("Query Agent가 요청 intent와 다른 결과를 반환했습니다.")
    normalized_used = {q.strip().casefold() for q in used}
    queries = [q.strip() for q in plan.queries if q.strip() and q.strip().casefold() not in normalized_used]
    if not queries:
        raise ValueError(f"Query Agent가 {intent} 단계에서 새로운 질의를 만들지 못했습니다.")
    return plan.model_copy(update={"queries": queries})


#: 검색 4단계 + 정리 1단계. 진행률의 분모다.
TOTAL_STEPS = len(STAGES) + 1


def extract_tasks(*, team_id: str, primary_document: dict, document_ids: list[str]) -> dict:
    """진행을 볼 필요가 없을 때 쓰는 형태. 끝까지 돌려 결과만 준다."""

    result = None
    for event in extract_tasks_stream(
        team_id=team_id, primary_document=primary_document, document_ids=document_ids
    ):
        if event["type"] == "result":
            result = event["result"]
    if result is None:
        raise ValueError("Extraction 스트림이 결과 없이 끝났습니다.")
    return result


def extract_tasks_stream(
    *,
    team_id: str,
    primary_document: dict,
    document_ids: list[str],
    model: str | None = None,
    api_key: str | None = None,
):
    """기준 문서에서 업무를 뽑고, 근거는 팀 문서 전체에서 검색으로 찾는다.

    1단계(`TASK_DISCOVERY`)만 기준 문서 안에서 찾는다. 무엇을 하는 프로젝트인지는
    기준 문서가 정하기 때문이다. 나머지 세 단계는 팀 문서 전체를 본다 — 공수나
    담당 역할은 기획서가 아니라 회의록이나 산정 자료에 적혀 있는 것이 보통이고,
    그것이 어느 문서에 있는지 사람이 미리 알 수 없다.

    **단계마다 진행을 내보낸다.** 몇 분이 걸리는 일이고, 그동안 화면이 도는 원만
    보여주면 사용자는 이게 되고 있는지 멈춘 건지 알 수 없다. 특히 에이전트가 만든
    검색어를 그대로 내보낸다 — 그게 이 단계에서 실제로 한 판단이다.
    """

    # **부른 에이전트의 모델을 쓴다.** 도구 안에 `.env` 모델이 박혀 있으면,
    # 에이전트에서 고른 모델과 실제로 도는 모델이 달라진다. 다만 이 파이프라인은
    # `responses.parse` 가 필요해서 아는 모델만 받는다 — Claude 처럼 못 받는
    # 것이면 조용히 떨어지지 않고 **무엇으로 돌았는지 결과에 적는다.**
    fallback = None
    if model and model not in SUPPORTED_MODELS:
        fallback = model
        model = None
    write_model = model or DEFAULT_WRITE_MODEL

    client = _client(api_key)
    # 이 문서가 무엇에 관한 것인지. 질의를 주제 위에 올려 놓는 앵커다.
    outline = document_outline(primary_document["doc_id"])
    evidence: dict[str, dict] = {}
    used_queries: list[str] = []
    trace: list[str] = []
    for index, (intent, need, label) in enumerate(STAGES):
        yield {
            "type": "stage",
            "step": index + 1,
            "total": TOTAL_STEPS,
            "intent": intent,
            # 화면에는 라벨만 보낸다. `need` 는 에이전트에게 주는 지시라 사람이
            # 읽을 문장이 아니다.
            "label": label,
        }
        plan = _query_plan(
            client,
            intent=intent,
            need=need,
            title=primary_document["file_name"],
            outline=outline,
            used=used_queries,
        )
        # 에이전트가 무엇을 찾기로 했는지. 화면이 보여주는 「생각」이 이것이다.
        yield {"type": "queries", "step": index + 1, "queries": plan.queries}
        used_queries.extend(plan.queries)
        vectors = embed_queries(plan.queries)
        scope = [primary_document["doc_id"]] if intent == "TASK_DISCOVERY" else document_ids
        found = 0
        for query, vector in zip(plan.queries, vectors, strict=True):
            rows = VectorSearchRepository.search(
                team_id=team_id,
                document_ids=scope,
                query_vector=vector,
                top_k=plan.top_k,
            )
            for row in rows:
                item = dict(row)
                item["chunk_id"] = str(item["chunk_id"])
                item["intent"] = intent
                item["query"] = query
                evidence[item["chunk_id"]] = item
            found += len(rows)
        trace.append(f"{intent}:{found}")
        yield {
            "type": "stage_done",
            "step": index + 1,
            "found": found,
            "evidence": len(evidence),
        }

    yield {
        "type": "stage",
        "step": TOTAL_STEPS,
        "total": TOTAL_STEPS,
        "intent": "SYNTHESIS",
        "label": "근거에서 업무 정리",
    }
    evidence_rows = [
        _evidence_view(row) | {"ref": f"E{number}"}
        for number, row in enumerate(
            _rank_evidence(list(evidence.values()), primary_document["doc_id"]),
            start=1,
        )
    ]
    by_ref = {row["ref"]: row["chunk_id"] for row in evidence_rows}
    response = client.responses.parse(
        model=write_model,
        service_tier=settings.OPENAI_SERVICE_TIER,
        reasoning={"effort": WRITE_EFFORT},
        input=[
            {
                "role": "system",
                "content": (
                    "근거 기반 프로젝트 업무 추출 에이전트다. 제공된 Chunk에 직접 근거가 있는 업무만 "
                    "추출한다. 역할, 기술, 공수, 날짜를 추정하지 않는다. 근거가 없는 필드는 null 또는 "
                    "빈 배열로 두고 missing_fields에 기록한다.\n"
                    "모든 업무에 근거를 단다. 근거는 제공된 항목의 ref 값(E1, E2 …)으로만 적고, "
                    "제공되지 않은 번호를 만들지 않는다."
                ),
            },
            {
                "role": "user",
                "content": f"기준 문서={primary_document['file_name']}\n검색 근거={evidence_rows}",
            },
        ],
        text_format=ExtractionResult,
    )
    result = response.output_parsed
    if result is None:
        raise ValueError("Extraction Agent가 구조화 결과를 반환하지 않았습니다.")
    # 모르는 번호를 단 업무는 그것만 떨어뜨린다. 예전에는 하나만 어긋나도 추출
    # 전체를 실패시켰는데, 몇 분을 기다린 결과를 인용 오타 하나로 버리는 셈이었다.
    # 다만 근거가 하나도 안 남은 업무는 뺀다 — 근거 없는 업무를 만들지 않는다.
    tasks: list[dict] = []
    warnings = list(result.warnings)
    for task in result.tasks:
        resolved = [by_ref[ref] for ref in task.evidence_refs if ref in by_ref]
        unknown = [ref for ref in task.evidence_refs if ref not in by_ref]
        if unknown:
            warnings.append(
                f"'{task.title}'에서 제공되지 않은 근거 번호를 빼냈다: {', '.join(unknown)}"
            )
        if not resolved:
            warnings.append(f"'{task.title}'은 근거가 하나도 확인되지 않아 제외했다.")
            continue
        tasks.append(task.model_dump(exclude={"evidence_refs"}) | {"evidence_chunk_ids": resolved})

    yield {
        "type": "result",
        "result": {
            "tasks": tasks,
            "warnings": warnings,
            "evidence": evidence_rows,
            "trace": trace,
            "model": write_model,
            "reasoning_effort": WRITE_EFFORT,
            # 에이전트가 고른 모델로 못 돈 경우. 화면과 모델이 그 사실을 알아야
            # 「Claude 로 골랐는데 왜 OpenAI 로 돌았나」를 설명할 수 있다.
            "model_fallback_from": fallback,
        },
    }
