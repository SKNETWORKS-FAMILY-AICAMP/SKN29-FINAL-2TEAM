"""문서 메타 파이프라인 — A안(8/11 확정 ⑥).

문서 하나당 **LLM 1회 + 임베딩 1개**. 이 값이 싸야 팀 문서 전부에 돌릴 수 있고,
전부에 돌아야 `document_search` 의 coarse 단계가 미처리 문서까지 후보로 볼 수
있다. 청크 단위 임베딩(무거운 RunPod 경로)은 coarse 가 고른 문서에만 든다.

⚠ 8/12 멘토링 민감: 요약만으로 coarse 가 부족하다는 결론이 나오면 A′ 로 간다
(tsvector 전문 인덱스 추가 — 12_문서처리_방식_비교.md §5). 그래서 **추출한 원문을
버리지 않고 `doc_meta.extracted_text` 에 넣는다** — A′ 전환이 인덱스 추가만으로
끝난다. 지금 버리면 전 문서를 다시 내려받아 다시 추출해야 한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.conf import settings
from openai import OpenAI
from pydantic import BaseModel, Field

from services.document_pipeline.errors import PipelineConfigurationError
from services.document_pipeline.runpod_client import embed_queries

from . import extractor

#: 문서 유형. 화면 필터와 프롬프트가 같은 목록을 봐야 해서 한 곳에만 둔다.
DOC_TYPES = ("제안요청서", "기획서", "요구사항정의서", "회의록", "보고서", "계약·행정", "기타")

#: 요약 모델. `naming.TITLE_MODEL`·`agent_builder.PLAN_MODEL` 과 같은 규칙으로
#: 코드에 둔다 — `.env` 로 고정하면 화면에서 고른 값과 어긋난다(2026-08-12).
#: `_summarize` 의 docstring 이 말하는 "가장 싼 모델"이 이 값이다.
SUMMARY_MODEL = "gpt-5.6-luna"


class DocumentSummary(BaseModel):
    summary: str = Field(max_length=600)
    doc_type: str
    keywords: list[str] = Field(default_factory=list, max_length=8)


@dataclass(frozen=True)
class DocMeta:
    doc_id: str
    extract_status: str
    summary: str | None = None
    doc_type: str | None = None
    keywords: list[str] | None = None
    summary_vec: list[float] | None = None
    extracted_text: str | None = None
    detail: str = ""


def build(*, doc_id: str, content: bytes, mime_type: str | None, file_name: str | None) -> DocMeta:
    """원문 → 추출 → 요약 → 임베딩. 실패는 예외가 아니라 상태로 돌려준다.

    추출이 안 된 문서도 **행을 남긴다.** 안 남기면 다음 스캔에서 또 시도하고,
    스캔 PDF 는 몇 번을 돌려도 결과가 같다 — 왜 이 문서가 검색에 안 걸리는지
    화면이 말해 줄 수도 없다.
    """

    result = extractor.extract(content=content, mime_type=mime_type, file_name=file_name)
    if result.status != extractor.OK:
        return DocMeta(doc_id=doc_id, extract_status=result.status, detail=result.detail)

    summary = _summarize(text=extractor.for_summary(result.text), file_name=file_name)
    # 임베딩은 요약 하나뿐이다. 원문을 통째로 임베딩하면 청크 경로와 다를 게
    # 없어지고, 값도 그만큼 든다.
    vector = embed_queries([summary.summary])[0]

    return DocMeta(
        doc_id=doc_id,
        extract_status=extractor.OK,
        summary=summary.summary,
        doc_type=summary.doc_type,
        keywords=summary.keywords,
        summary_vec=vector,
        extracted_text=result.text,
    )


def _summarize(*, text: str, file_name: str | None) -> DocumentSummary:
    """요약·유형·키워드를 한 번에 받는다.

    가장 싼 모델을 쓴다. 이 단계의 판단은 "무엇에 대한 문서인가" 한 줄이라
    긴 추론이 필요 없고, 팀 문서 전부에 도는 일이라 단가가 그대로 총액이 된다
    (services/task_extraction 의 실측: sol 은 luna 의 25배).
    """

    if not str(settings.OPENAI_API_KEY).strip():
        raise PipelineConfigurationError("필수 OpenAI 설정이 없습니다: OPENAI_API_KEY")

    client = OpenAI(api_key=settings.OPENAI_API_KEY, timeout=120, max_retries=1)
    response = client.responses.parse(
        model=SUMMARY_MODEL,
        service_tier=settings.OPENAI_SERVICE_TIER,
        reasoning={"effort": "low"},
        input=[
            {
                "role": "system",
                "content": (
                    "문서 색인용 요약 담당이다. 주어진 문서 앞부분을 읽고 "
                    "(1) 이 문서가 무엇에 대한 것인지 3~5문장 요약 "
                    "(2) 문서 유형 (3) 검색 키워드 최대 8개를 만든다.\n"
                    # 요약이 곧 검색 대상이다. 파일명이나 목차 제목만 되풀이하면
                    # 어떤 질의에도 비슷하게 걸려 변별력이 사라진다.
                    "요약에는 이 문서에만 있는 고유한 내용(사업명·대상 업무·핵심 요구사항)을 "
                    "담는다. '본 문서는 ~에 관한 문서이다' 같은 형식 문장으로 채우지 않는다.\n"
                    "본문에 없는 내용을 지어내지 않는다. 앞부분만 보고 판단할 수 없으면 "
                    "보이는 범위만 적는다.\n"
                    f"문서 유형은 다음 중 하나로만 답한다: {' / '.join(DOC_TYPES)}"
                ),
            },
            {"role": "user", "content": f"파일명={file_name or '알 수 없음'}\n\n{text}"},
        ],
        text_format=DocumentSummary,
    )
    parsed = response.output_parsed
    if parsed is None:
        raise ValueError("요약 모델이 구조화 결과를 반환하지 않았습니다.")
    if parsed.doc_type not in DOC_TYPES:
        # 목록 밖 값이 오면 화면 필터가 조용히 못 잡는다. 지어내지 말고 기타로.
        parsed = parsed.model_copy(update={"doc_type": "기타"})
    return parsed


def as_row(meta: DocMeta) -> dict[str, Any]:
    """Repository 가 받는 모양."""

    return {
        "doc_id": meta.doc_id,
        "summary": meta.summary,
        "doc_type": meta.doc_type,
        "keywords": meta.keywords or [],
        "summary_vec": meta.summary_vec,
        "extracted_text": meta.extracted_text,
        "extract_status": meta.extract_status,
        # **왜 실패했는지.** 추출기가 이미 사람이 읽을 문구로 만들어 두는데
        # (extractor.py 의 `detail`) 여기서 안 실으면 그대로 버려진다 —
        # 화면은 「읽지 못했습니다」까지만 말할 수 있고, 사람은 암호를 풀면
        # 되는 문서인지 스캔본이라 소용없는지 구분하지 못한다(2026-08-19).
        "extract_detail": meta.detail or None,
    }
