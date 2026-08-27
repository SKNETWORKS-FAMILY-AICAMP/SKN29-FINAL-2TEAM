"""§8.2 "평가 케이스 표준 형식" — 질문 생성부터 채점까지 전부 이 타입을 공유한다.

정본: docs/설계 및 구현/3_중간발표 이후/작업기록/Juyeon_Agents_Description/
      03_스킬_검증_등록_설계.md §8.2

`query/context` 단순 쌍 대신 하나의 시나리오(`messages` 전체 + fixture)로
둔다 — "방금 올린 문서에서 뽑아줘" 같은 문맥 의존 질문도 실제로 재생할 수
있어야 하기 때문이다(§8.2 본문).
"""

from __future__ import annotations

from typing import Literal, TypedDict


class EvalMessage(TypedDict):
    role: Literal["user", "assistant"]
    content: str


class DocumentFixture(TypedDict):
    document_id: str
    title: str
    content: str
    indexed: bool


class ToolExpectation(TypedDict):
    tool_ref: str
    min_calls: int
    max_calls: int | None
    argument_rules: list[dict]


class ApprovalFixture(TypedDict):
    tool_ref: str
    decision: Literal["approve", "reject"]


class SkillEvalCase(TypedDict):
    case_id: str
    source: Literal["generated", "platform", "regression"]
    polarity: Literal["positive", "negative"]
    category: str
    messages: list[EvalMessage]
    document_fixtures: list[DocumentFixture]
    tool_fixtures: dict[str, list[dict]]
    should_activate_candidate: bool
    allowed_other_skill_names: list[str]
    required_tools: list[ToolExpectation]
    forbidden_tools: list[str]
    approval_fixtures: list[ApprovalFixture]
    behavior_assertions: list[dict]
    reason: str


class RoutingResult(TypedDict):
    """라우팅 테스트 반복 1회의 결과(§8.11)."""

    case_id: str
    attempt: int
    activated_candidate: bool
    called_tool_refs: list[str]
    error: str | None


class BehaviorResult(TypedDict):
    """행동 테스트 대표 케이스 1건의 결과(§8.11)."""

    case_id: str
    deterministic_tool_failures: list[str]
    assertion_results: list[dict]
    error: str | None


__all__ = [
    "EvalMessage",
    "DocumentFixture",
    "ToolExpectation",
    "ApprovalFixture",
    "SkillEvalCase",
    "RoutingResult",
    "BehaviorResult",
]
