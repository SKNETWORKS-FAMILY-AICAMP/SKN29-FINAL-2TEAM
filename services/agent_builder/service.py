"""빌더 에이전트 — 로컬/DB로 확정할 수 있는 구조 검증만 한다.

LLM으로 설명·지시문의 "품질"을 판정하던 로직은 걷어냈다(2026-08-13, Deep Agent형
빌더 개편). 여기 남은 `check_definition`은 도구 참조가 실제로 존재하는지, 중복
선택은 없는지만 본다 — 실행 가능한 구성인지 보장하는 구조 검증이다.
"""

from __future__ import annotations

from typing import Any


def check_definition(*, tool_refs: list[str], catalog: dict[str, dict[str, Any]]) -> str | None:
    """로컬/DB로 확정할 수 있는 항목만 본다 — 라이브 외부 호출은 안 한다.

    막힘이 있으면 사용자에게 보여줄 한 문장을 돌려주고, 없으면 `None`이다.
    """

    if not tool_refs:
        return None

    seen: set[str] = set()
    duplicates: list[str] = []
    unknown: list[str] = []
    for ref in tool_refs:
        if ref in seen:
            duplicates.append(ref)
        seen.add(ref)
        if ref not in catalog:
            unknown.append(ref)

    reasons: list[str] = []
    if unknown:
        reasons.append(f"더 이상 쓸 수 없는 도구가 선택돼 있습니다: {', '.join(sorted(set(unknown)))}")
    if duplicates:
        reasons.append(f"같은 도구가 중복 선택돼 있습니다: {', '.join(sorted(set(duplicates)))}")
    return " ".join(reasons) if reasons else None
