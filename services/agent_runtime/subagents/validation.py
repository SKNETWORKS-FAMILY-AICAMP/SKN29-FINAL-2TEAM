"""Child 구성의 중복, 권한, 깊이, 순환을 검증한다."""

from __future__ import annotations

from services.agent_runtime.definitions import SubagentReference
from services.agent_runtime.exceptions import (
    DelegationDepthError,
    DuplicateSubagentAliasError,
    DuplicateSubagentError,
    InactiveSubagentError,
    InvalidDelegationDescriptionError,
    InvalidSubagentAliasError,
    SelfReferenceError,
    SubagentCycleError,
    SubagentPermissionError,
)


def validate_no_cycle(
    *,
    parent_agent_id: str | None,
    child_ids: list[str],
    dependency_graph: dict[str, set[str]],
) -> None:
    """Parent와 Child를 연결했을 때 순환 경로가 생기는지 확인한다."""
    if parent_agent_id is None:
        return

    visited: set[str] = set()

    def has_path(start: str, target: str) -> bool:
        if start == target:
            return True
        if start in visited:
            return False
        visited.add(start)
        for neighbor in dependency_graph.get(start, ()):  # pragma: no branch
            if has_path(neighbor, target):
                return True
        return False

    for child_id in child_ids:
        # Child에서 Parent로 가는 기존 경로가 있으면 새 연결은 순환을 만든다.
        visited.clear()
        if has_path(child_id, parent_agent_id):
            raise SubagentCycleError(
                f"'{child_id}'를 서브 에이전트로 추가하면 순환 참조가 됩니다."
            )


def validate_subagents(
    *,
    parent_agent_id: str | None,
    child_refs: tuple[SubagentReference, ...],
    dependency_graph: dict[str, set[str]],
) -> None:
    """Child 구성을 정해진 순서로 검증하고 첫 오류를 발생시킨다.

    **`has_subagents` 검사는 항상 켜져 있다(무조건).** MVP는 1단계 위임만
    허용한다는 규칙 자체가 맥락에 따라 달라지지 않는다 — "지금은 검사해도
    되고 안 해도 된다"는 경우가 없다. 예전에는 이 함수가 `allow_subagents`
    플래그로 이 검사를 껐다 켰다 했는데, 호출부마다 그 플래그의 의미가
    갈렸다: 저장 경로(`backend/db/agent_platform.py` `publish()`)는
    "항상 검사"를 뜻하려고 `False`를 고정값으로 넘겼지만, 런타임 Factory
    (`factory.py`)는 "지금 짓는 노드가 Root라 서브 에이전트를 가질 수
    있는가"라는 **다른 질문**에 같은 이름의 인자를 썼다 — 그 결과 Root를
    지을 때(`allow_subagents=True`)는 이 검사가 통째로 건너뛰어졌다.
    저장은 막혀도 저장 없이 도는 Builder Test Run(`from_draft()`)은 이
    구멍으로 2단계 위임을 그대로 실행할 수 있었다(2026-08-14 발견·수정).
    이제 이 함수에는 그 플래그가 없다 — 넘어온 `child_refs`는 항상
    `has_subagents`를 확인한다.
    """
    child_ids = [ref.child_agent_id for ref in child_refs]
    aliases = [ref.alias for ref in child_refs]

    if parent_agent_id is not None and parent_agent_id in child_ids:
        raise SelfReferenceError(
            f"'{parent_agent_id}'는 자기 자신을 서브 에이전트로 선택할 수 없습니다."
        )

    if len(child_ids) != len(set(child_ids)):
        raise DuplicateSubagentError("동일한 서브 에이전트를 중복 선택했습니다.")

    if len(aliases) != len(set(aliases)):
        raise DuplicateSubagentAliasError("동일한 alias를 중복 사용했습니다.")

    for ref in child_refs:
        if not ref.alias.strip():
            raise InvalidSubagentAliasError("서브 에이전트 alias는 필수입니다.")

        if not ref.delegation_description.strip():
            raise InvalidDelegationDescriptionError(
                "서브 에이전트 위임 설명은 필수입니다."
            )

        if not ref.is_active:
            raise InactiveSubagentError(
                f"'{ref.child_agent_id}'는 비활성 상태라 서브 에이전트로 쓸 수 없습니다."
            )

        if not ref.can_execute:
            raise SubagentPermissionError(
                f"'{ref.child_agent_id}'를 실행할 권한이 없습니다."
            )

        if ref.has_subagents:
            raise DelegationDepthError(
                f"'{ref.child_agent_id}'는 이미 서브 에이전트를 갖고 있어 "
                "MVP의 1단계 위임 제한을 넘어섭니다."
            )

    validate_no_cycle(
        parent_agent_id=parent_agent_id,
        child_ids=child_ids,
        dependency_graph=dependency_graph,
    )
