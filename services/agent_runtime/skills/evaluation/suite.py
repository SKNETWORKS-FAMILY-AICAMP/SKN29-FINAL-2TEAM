"""§8.9 "최종 suite 조합" — 구조·의미 검토를 통과한 후보만으로 최종 12개
(긍정 6·부정 6)를 만든다.

정본: 03_스킬_검증_등록_설계.md §8.9. 우선순위: 승인 회귀 케이스(polarity당
최대 2개) → 부정에는 플랫폼 고정 probe(최대 2개) → 나머지는 생성 후보로
채운다. `candidate_hash + dataset_version`을 seed로 써서 같은 입력이면 같은
12개가 나오게 한다(§8.3 "고정 질문을 '추가'해 실행 횟수가 무한히 늘어나는
방식은 사용하지 않는다").
"""

from __future__ import annotations

import hashlib
import random
from typing import Any

from .generator import GeneratedCase
from .types import SkillEvalCase

POSITIVE_TARGET = 6
NEGATIVE_TARGET = 6
MAX_REGRESSION_PER_POLARITY = 2
MAX_PLATFORM_PROBES = 2


def _seed_from(candidate_hash: str, dataset_version: str) -> random.Random:
    digest = hashlib.sha256(f"{candidate_hash}:{dataset_version}".encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


def _generated_to_eval_case(case: GeneratedCase, *, index: int, polarity: str) -> SkillEvalCase:
    messages = [{"role": m.role, "content": m.content} for m in case.context]
    # 생성 모델이 현재 query를 context의 마지막 user 메시지에도 복제하는
    # 경우가 있다. 그대로 두면 동일한 요청을 연속 두 번 보낸 비현실적인
    # 대화가 되므로, 정확히 같은 마지막 메시지만 제거한다.
    while messages and messages[-1]["role"] == "user" and messages[-1]["content"].strip() == case.query.strip():
        messages.pop()
    messages.append({"role": "user", "content": case.query})
    return SkillEvalCase(
        case_id=f"generated-{polarity}-{index}",
        source="generated",
        polarity=polarity,  # type: ignore[typeddict-item]
        category=case.category,
        messages=messages,
        document_fixtures=[
            {"document_id": f.document_id, "title": f.title, "content": f.content, "indexed": True}
            for f in case.document_fixtures
        ],
        tool_fixtures={},
        should_activate_candidate=case.should_activate_candidate,
        allowed_other_skill_names=case.allowed_other_skill_names,
        required_tools=[
            {"tool_ref": ref, "min_calls": 1, "max_calls": None, "argument_rules": []}
            for ref in case.required_tools
        ],
        forbidden_tools=case.forbidden_tools,
        approval_fixtures=[],
        behavior_assertions=[item.model_dump() for item in case.behavior_assertions],
        reason=case.reason,
    )


def _regression_to_eval_case(row: dict[str, Any]) -> SkillEvalCase:
    document = dict(row["case_document"])
    document.setdefault("case_id", row["case_id"])
    document["source"] = "regression"
    return document  # type: ignore[return-value]


def _probe_to_eval_case(probe: dict[str, Any]) -> SkillEvalCase:
    # `platform_probes.v1.yaml`은 `query`/`context`로 안 쪼개고 `messages`를
    # 그대로 담는다(다중 턴을 자연스럽게 표현하려는 선택) — 생성기 출력
    # (`GeneratedCase`, query+context로 나뉨)과는 원본 형식이 다르지만, 최종
    # `SkillEvalCase.messages`로 모이는 지점은 같다.
    messages = list(probe["messages"])
    return SkillEvalCase(
        case_id=probe["case_id"],
        source="platform",
        polarity="negative",
        category=probe["category"],
        messages=messages,
        document_fixtures=[
            {**f, "indexed": True} for f in probe.get("document_fixtures", [])
        ],
        tool_fixtures={},
        should_activate_candidate=False,
        allowed_other_skill_names=[],
        required_tools=[],
        forbidden_tools=[],
        approval_fixtures=[],
        behavior_assertions=[],
        reason=probe.get("reason", ""),
    )


def compose_suite(
    *,
    candidate_hash: str,
    dataset_version: str,
    positive_candidates: list[GeneratedCase],
    negative_candidates: list[GeneratedCase],
    approved_regression_rows: list[dict[str, Any]],
    platform_probes: list[dict[str, Any]],
) -> tuple[list[SkillEvalCase], str]:
    """`(최종 12개, eval_suite_version)`을 돌려준다."""

    rng = _seed_from(candidate_hash, dataset_version)

    positive_regression = [r for r in approved_regression_rows if r["polarity"] == "positive"]
    negative_regression = [r for r in approved_regression_rows if r["polarity"] == "negative"]
    # `list(...)`로 복사한 뒤 섞는다 — 호출자의 `platform_probes` 리스트를 그
    # 자리에서 섞으면(원래 코드) 같은 리스트 객체를 여러 job에 재사용할 때
    # 두 번째 호출부터는 이미 한 번 섞인 순서에서 다시 섞여, 같은
    # `candidate_hash`인데도 실행마다 다른 12개가 나왔다(실측으로 발견한 버그
    # — "재현 가능해야 한다"는 §8.3 요구를 실제로 어기고 있었다).
    platform_probes = list(platform_probes)
    rng.shuffle(positive_regression)
    rng.shuffle(negative_regression)
    rng.shuffle(platform_probes)

    positive: list[SkillEvalCase] = [
        _regression_to_eval_case(r) for r in positive_regression[:MAX_REGRESSION_PER_POLARITY]
    ]
    negative: list[SkillEvalCase] = [
        _regression_to_eval_case(r) for r in negative_regression[:MAX_REGRESSION_PER_POLARITY]
    ]
    negative.extend(_probe_to_eval_case(p) for p in platform_probes[:MAX_PLATFORM_PROBES])

    gen_positive = list(positive_candidates)
    gen_negative = list(negative_candidates)
    rng.shuffle(gen_positive)
    rng.shuffle(gen_negative)

    for index, case in enumerate(gen_positive):
        if len(positive) >= POSITIVE_TARGET:
            break
        positive.append(_generated_to_eval_case(case, index=index, polarity="positive"))
    for index, case in enumerate(gen_negative):
        if len(negative) >= NEGATIVE_TARGET:
            break
        negative.append(_generated_to_eval_case(case, index=index, polarity="negative"))

    if len(positive) < POSITIVE_TARGET or len(negative) < NEGATIVE_TARGET:
        raise ValueError(
            f"최종 suite를 못 채웠습니다 (긍정 {len(positive)}/{POSITIVE_TARGET}, "
            f"부정 {len(negative)}/{NEGATIVE_TARGET})."
        )

    positive = positive[:POSITIVE_TARGET]
    negative = negative[:NEGATIVE_TARGET]

    suite_version = hashlib.sha256(
        (candidate_hash + dataset_version + "".join(c["case_id"] for c in [*positive, *negative])).encode(
            "utf-8"
        )
    ).hexdigest()[:16]

    return [*positive, *negative], suite_version


__all__ = ["compose_suite", "POSITIVE_TARGET", "NEGATIVE_TARGET"]
