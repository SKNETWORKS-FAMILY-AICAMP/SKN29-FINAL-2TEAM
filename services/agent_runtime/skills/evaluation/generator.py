"""§8.3-§8.5 — 질문 후보 생성(긍정 8·부정 8), 구조 검증, 부분 재생성.

정본: 03_스킬_검증_등록_설계.md §8.3("질문 생성 수와 최종 12개 구성"),
      §8.4("질문 생성 프롬프트"), §8.5("구조 검증과 재생성")
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field

from services.agent_runtime.models.factory import ModelConfigResolver, ModelFactory

from .config import SKILL_EVAL_AUTHOR_EFFORT, SKILL_EVAL_AUTHOR_MODEL
from .prompts import (
    EVAL_CASE_GENERATOR_PROMPT_VERSION,
    EVAL_CASE_GENERATOR_SYSTEM_PROMPT,
    build_generator_user_message,
)

#: 정본 §8.5 "질문·fixture 크기" 상한. 사람이 실제로 입력할 법한 길이를
#: 넉넉히 웃돈다 — 이보다 길면 십중팔구 모델이 여러 문장을 욱여넣은 것이다.
MAX_QUERY_LENGTH = 300
#: §8.5 "중복 — 정규화 완전일치와 문자열 유사도 0.9 이상".
DUPLICATE_SIMILARITY_THRESHOLD = 0.9
#: §8.5 재생성 최대 횟수.
MAX_REGENERATION_ATTEMPTS = 2


class GeneratedContextMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class GeneratedDocumentFixture(BaseModel):
    document_id: str
    title: str
    content: str


class GeneratedBehaviorAssertion(BaseModel):
    criterion: str


class GeneratedCase(BaseModel):
    category: str
    query: str
    context: list[GeneratedContextMessage] = Field(default_factory=list)
    document_fixtures: list[GeneratedDocumentFixture] = Field(default_factory=list)
    should_activate_candidate: bool
    allowed_other_skill_names: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    behavior_assertions: list[GeneratedBehaviorAssertion] = Field(default_factory=list)
    reason: str


class GeneratedCaseSet(BaseModel):
    positive: list[GeneratedCase] = Field(min_length=8, max_length=8)
    negative: list[GeneratedCase] = Field(min_length=8, max_length=8)


@dataclass(frozen=True)
class StructuralFailure:
    index: int
    polarity: str
    rule: str
    detail: str


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _name_leak_patterns(skill_name: str) -> list[str]:
    return [skill_name.lower(), skill_name.replace("-", " ").lower()]


def validate_structural(
    cases: list[GeneratedCase],
    *,
    polarity: str,
    skill_name: str,
    available_tool_refs: set[str],
    other_skill_names: set[str],
) -> list[StructuralFailure]:
    """§8.5 표 — 의미가 아니라 코드로 확정할 수 있는 항목만 검사한다."""

    failures: list[StructuralFailure] = []
    leak_patterns = _name_leak_patterns(skill_name)
    seen_normalized: list[str] = []

    for index, case in enumerate(cases):
        if not case.query.strip():
            failures.append(StructuralFailure(index, polarity, "empty_query", "질문이 비어 있습니다."))
            continue
        if len(case.query) > MAX_QUERY_LENGTH:
            failures.append(
                StructuralFailure(index, polarity, "query_too_long", f"{len(case.query)}자 — 상한 {MAX_QUERY_LENGTH}자")
            )

        normalized = _normalize(case.query)
        if normalized in seen_normalized:
            failures.append(StructuralFailure(index, polarity, "duplicate", "다른 질문과 완전히 같습니다."))
        else:
            for prior in seen_normalized:
                if difflib.SequenceMatcher(None, normalized, prior).ratio() >= DUPLICATE_SIMILARITY_THRESHOLD:
                    failures.append(
                        StructuralFailure(index, polarity, "near_duplicate", "다른 질문과 표현만 다르고 사실상 같습니다.")
                    )
                    break
        seen_normalized.append(normalized)

        expected_activation = polarity == "positive"
        if case.should_activate_candidate is not expected_activation:
            failures.append(
                StructuralFailure(
                    index,
                    polarity,
                    "polarity_mismatch",
                    "긍정/부정 질문과 should_activate_candidate 값이 일치하지 않습니다.",
                )
            )
        if polarity == "positive" and not case.behavior_assertions:
            failures.append(StructuralFailure(index, polarity, "missing_behavior_assertion", "결과 품질 기준이 없습니다."))
        if polarity == "negative" and case.behavior_assertions:
            failures.append(StructuralFailure(index, polarity, "unexpected_behavior_assertion", "부정 질문에 결과 품질 기준이 있습니다."))

        if any(pattern in case.query.lower() for pattern in leak_patterns):
            failures.append(StructuralFailure(index, polarity, "name_leak", "질문에 스킬 이름이 노출됩니다."))

        for tool_ref in (*case.required_tools, *case.forbidden_tools):
            if tool_ref not in available_tool_refs:
                failures.append(
                    StructuralFailure(index, polarity, "unknown_tool", f"'{tool_ref}'는 사용 가능한 도구가 아닙니다.")
                )

        for name in case.allowed_other_skill_names:
            if name not in other_skill_names:
                failures.append(
                    StructuralFailure(index, polarity, "unknown_other_skill", f"'{name}'은 제공된 other_skills에 없습니다.")
                )

        referenced_doc_ids = {
            match for match in re.findall(r"doc-[a-zA-Z0-9_-]+", case.query)
        }
        available_doc_ids = {f.document_id for f in case.document_fixtures}
        missing_refs = referenced_doc_ids - available_doc_ids
        if missing_refs:
            failures.append(
                StructuralFailure(index, polarity, "missing_fixture", f"참조한 문서 fixture가 없습니다: {missing_refs}")
            )

    return failures


def _build_model():
    resolved = ModelConfigResolver().resolve(
        model=SKILL_EVAL_AUTHOR_MODEL, reasoning_effort=SKILL_EVAL_AUTHOR_EFFORT, team_id=None
    )
    model = ModelFactory().create(resolved)
    return model.with_structured_output(GeneratedCaseSet), resolved


def generate_candidate_cases(
    *,
    skill_document: dict[str, Any],
    available_tools: list[dict[str, Any]],
    other_skills: list[dict[str, Any]],
) -> tuple[GeneratedCaseSet, str]:
    """LLM 한 번 호출. `(결과, 실제 사용한 model_id)`를 돌려준다."""

    structured_model, resolved = _build_model()
    user_message = build_generator_user_message(
        skill_candidate=skill_document, available_tools=available_tools, other_skills=other_skills
    )
    result = structured_model.invoke(
        [
            {"role": "system", "content": EVAL_CASE_GENERATOR_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]
    )
    return result, resolved.model_id


class EvalGenerationError(Exception):
    """§8.5 "2회 후에도 유효한 후보가 부족하면 TEST_GENERATION_FAILED"."""

    def __init__(self, message: str, failures: list[StructuralFailure]) -> None:
        super().__init__(message)
        self.failures = failures


def generate_valid_candidates(
    *,
    skill_document: dict[str, Any],
    available_tools: list[dict[str, Any]],
    other_skills: list[dict[str, Any]],
) -> tuple[list[GeneratedCase], list[GeneratedCase], str]:
    """생성 → 구조 검증 → 실패한 것만 골라 최대 `MAX_REGENERATION_ATTEMPTS`회
    재생성한다. `(긍정 8개, 부정 8개, model_id)`를 돌려준다 — 전부 구조 검증을
    통과한 상태다.

    §8.5 자체는 "실패한 케이스만" 재생성하라고 하지만, 이 생성 모델은 긍정/
    부정을 한 번에 8+8로 묶어 내는 구조라 부분(일부 인덱스만) 재생성을 구현하기
    까다롭다 — 대신 실패가 있으면 그 **극성(positive/negative) 전체**를 다시
    만든다. 최대 시도 횟수는 그대로 지킨다.
    """

    skill_name = skill_document["name"]
    available_tool_refs = {t["tool_ref"] for t in available_tools}
    other_skill_names = {s["name"] for s in other_skills}

    positive: list[GeneratedCase] = []
    negative: list[GeneratedCase] = []
    model_id = ""
    last_failures: list[StructuralFailure] = []

    for attempt in range(MAX_REGENERATION_ATTEMPTS + 1):
        result, model_id = generate_candidate_cases(
            skill_document=skill_document, available_tools=available_tools, other_skills=other_skills
        )
        pos_failures = validate_structural(
            result.positive,
            polarity="positive",
            skill_name=skill_name,
            available_tool_refs=available_tool_refs,
            other_skill_names=other_skill_names,
        )
        neg_failures = validate_structural(
            result.negative,
            polarity="negative",
            skill_name=skill_name,
            available_tool_refs=available_tool_refs,
            other_skill_names=other_skill_names,
        )
        last_failures = [*pos_failures, *neg_failures]

        if not pos_failures:
            positive = result.positive
        if not neg_failures:
            negative = result.negative
        if positive and negative:
            return positive, negative, model_id

    raise EvalGenerationError(
        f"{MAX_REGENERATION_ATTEMPTS + 1}회 시도해도 유효한 질문을 못 만들었습니다.", last_failures
    )


__all__ = [
    "GeneratedBehaviorAssertion",
    "GeneratedCase",
    "GeneratedCaseSet",
    "StructuralFailure",
    "EvalGenerationError",
    "validate_structural",
    "generate_candidate_cases",
    "generate_valid_candidates",
    "EVAL_CASE_GENERATOR_PROMPT_VERSION",
]
