"""대표 행동 실행의 자연어 결과가 case assertion을 만족하는지 제한적으로 검토한다."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from services.agent_runtime.models.factory import ModelConfigResolver, ModelFactory

from .config import SKILL_EVAL_REVIEWER_EFFORT, SKILL_EVAL_REVIEWER_MODEL
from .prompts import BEHAVIOR_SEMANTIC_REVIEWER_PROMPT


class AssertionVerdict(BaseModel):
    assertion_index: int
    verdict: Literal["PASS", "FAIL", "UNCERTAIN"]
    reason: str


class BehaviorReview(BaseModel):
    results: list[AssertionVerdict]


def merge_uncertain_verdicts(
    first: list[AssertionVerdict], second: list[AssertionVerdict]
) -> list[AssertionVerdict]:
    """첫 판정이 불확실한 항목만 두 번째 독립 판정으로 교체한다.

    명확한 PASS/FAIL은 다시 뽑지 않는다. 자연어 reviewer의 일시적인
    UNCERTAIN 하나 때문에 올바른 실행 전체가 탈락하는 변동성을 줄이면서,
    두 번째도 불확실하면 보수적으로 UNCERTAIN을 유지한다.
    """

    retry_by_index = {verdict.assertion_index: verdict for verdict in second}
    return [
        retry_by_index.get(verdict.assertion_index, verdict)
        if verdict.verdict == "UNCERTAIN"
        else verdict
        for verdict in first
    ]


def build_behavior_review_payload(
    *,
    assertions: list[dict[str, Any]],
    final_response: str,
    tool_trace: list[dict[str, Any]],
    input_messages: list[dict[str, Any]] | None = None,
    document_fixtures: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "behavior_assertions": assertions,
        "input_messages": input_messages or [],
        "document_fixtures": document_fixtures or [],
        "final_response": final_response,
        "tool_trace": tool_trace,
    }


def review_behavior(
    *,
    assertions: list[dict[str, Any]],
    final_response: str,
    tool_trace: list[dict[str, Any]],
    input_messages: list[dict[str, Any]] | None = None,
    document_fixtures: list[dict[str, Any]] | None = None,
) -> tuple[list[AssertionVerdict], str]:
    if not assertions:
        return [], ""
    resolved = ModelConfigResolver().resolve(
        model=SKILL_EVAL_REVIEWER_MODEL, reasoning_effort=SKILL_EVAL_REVIEWER_EFFORT, team_id=None
    )
    model = ModelFactory().create(resolved).with_structured_output(BehaviorReview)
    import json

    payload = build_behavior_review_payload(
        assertions=assertions,
        input_messages=input_messages,
        document_fixtures=document_fixtures,
        final_response=final_response,
        tool_trace=tool_trace,
    )
    result = model.invoke([
        {"role": "system", "content": BEHAVIOR_SEMANTIC_REVIEWER_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ])
    return result.results, resolved.model_id


__all__ = [
    "AssertionVerdict",
    "BehaviorReview",
    "build_behavior_review_payload",
    "merge_uncertain_verdicts",
    "review_behavior",
]
