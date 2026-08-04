from __future__ import annotations

from typing import Literal

from django.conf import settings
from openai import OpenAI
from pydantic import BaseModel, Field

from backend.db.document_pipeline import VectorSearchRepository
from services.document_pipeline.errors import PipelineConfigurationError
from services.document_pipeline.runpod_client import embed_queries


Intent = Literal[
    "TASK_DISCOVERY", "TASK_CORE", "ASSIGNMENT_REQUIREMENT", "EXECUTION_CONDITION"
]


class QueryPlan(BaseModel):
    intent: Intent
    queries: list[str] = Field(min_length=1, max_length=3)
    top_k: int = Field(default=5, ge=1, le=10)


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
    evidence_chunk_ids: list[str] = Field(min_length=1)


class ExtractionResult(BaseModel):
    tasks: list[ExtractedTask] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


STAGES: list[tuple[Intent, str]] = [
    ("TASK_DISCOVERY", "명시된 수행 업무 후보와 직접 근거"),
    ("TASK_CORE", "요구사항, 산출물, 완료 기준"),
    ("ASSIGNMENT_REQUIREMENT", "담당 역할과 필수 기술 또는 경험"),
    ("EXECUTION_CONDITION", "공수, 일정, 우선순위, 의존성, 제약, 위험"),
]


def _client() -> OpenAI:
    missing = [
        name
        for name, value in (
            ("OPENAI_API_KEY", settings.OPENAI_API_KEY),
            ("OPENAI_MODEL", settings.OPENAI_MODEL),
            ("OPENAI_REASONING_EFFORT", settings.OPENAI_REASONING_EFFORT),
        )
        if not str(value).strip()
    ]
    if missing:
        raise PipelineConfigurationError(f"필수 OpenAI 설정이 없습니다: {', '.join(missing)}")
    if settings.OPENAI_MODEL != "gpt-5.6-sol":
        raise PipelineConfigurationError("OPENAI_MODEL은 gpt-5.6-sol이어야 합니다.")
    if settings.OPENAI_REASONING_EFFORT != "xhigh":
        raise PipelineConfigurationError("OPENAI_REASONING_EFFORT는 xhigh여야 합니다.")
    return OpenAI(api_key=settings.OPENAI_API_KEY)


def _query_plan(client: OpenAI, *, intent: Intent, need: str, title: str, used: list[str]) -> QueryPlan:
    response = client.responses.parse(
        model=settings.OPENAI_MODEL,
        reasoning={"effort": settings.OPENAI_REASONING_EFFORT},
        input=[
            {
                "role": "system",
                "content": (
                    "VectorDB 업무 근거 검색어 생성 전담 에이전트다. 업무를 만들거나 답하지 말고 "
                    "부족 정보를 찾는 한국어 검색 질의만 만든다. 이미 사용한 질의를 반복하지 않는다."
                ),
            },
            {
                "role": "user",
                "content": f"intent={intent}\n필요 정보={need}\n기준 문서={title}\n기존 질의={used}",
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


def extract_tasks(
    *, project_id: str, primary_document: dict, document_ids: list[str]
) -> dict:
    client = _client()
    evidence: dict[str, dict] = {}
    used_queries: list[str] = []
    trace: list[str] = []
    for intent, need in STAGES:
        plan = _query_plan(
            client,
            intent=intent,
            need=need,
            title=primary_document["file_name"],
            used=used_queries,
        )
        used_queries.extend(plan.queries)
        vectors = embed_queries(plan.queries)
        scope = [primary_document["doc_id"]] if intent == "TASK_DISCOVERY" else document_ids
        found = 0
        for query, vector in zip(plan.queries, vectors, strict=True):
            rows = VectorSearchRepository.search(
                proj_id=project_id,
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

    evidence_rows = sorted(
        evidence.values(), key=lambda item: float(item.get("retrieval_score") or 0), reverse=True
    )[:20]
    response = client.responses.parse(
        model=settings.OPENAI_MODEL,
        reasoning={"effort": settings.OPENAI_REASONING_EFFORT},
        input=[
            {
                "role": "system",
                "content": (
                    "근거 기반 프로젝트 업무 추출 에이전트다. 제공된 Chunk에 직접 근거가 있는 업무만 "
                    "추출한다. 역할, 기술, 공수, 날짜를 추정하지 않는다. 근거가 없는 필드는 null 또는 "
                    "빈 배열로 두고 missing_fields에 기록한다. 모든 업무에 직접 근거 chunk id를 넣는다."
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
    valid_ids = set(evidence)
    for task in result.tasks:
        if not set(task.evidence_chunk_ids).issubset(valid_ids):
            raise ValueError(f"Agent가 검색되지 않은 근거 ID를 반환했습니다: {task.title}")
    return {
        "tasks": [task.model_dump() for task in result.tasks],
        "warnings": result.warnings,
        "evidence": evidence_rows,
        "trace": trace,
        "model": settings.OPENAI_MODEL,
        "reasoning_effort": settings.OPENAI_REASONING_EFFORT,
    }
