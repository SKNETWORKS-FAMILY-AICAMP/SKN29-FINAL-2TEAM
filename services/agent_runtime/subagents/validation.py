"""자기 참조·중복·순환 참조·최대 위임 깊이 검사.

정본: docs/작업기록/jihun_buildingpage/2026-08-13_02_Deep-Agent_런타임_공통_계약_v1.md §7

⚠ 구현체는 이 파일 하나만 둔다(02 §7.1). 저장·발행 API와 런타임 Factory는 같은
validate_subagents()를 import해서 쓴다 — API View나 Factory 안에 자기 참조·중복·
순환 검사를 다시 구현하지 않는다.

deepagents나 DB에 의존하지 않는 순수 함수라 스텁이 아니라 실제로 구현했다
(02 §7.2가 함수 본문 전체를 이미 제공한다).
"""

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
    """parent_agent_id를 이 child_ids에 연결했을 때 순환이 생기는지 확인한다.

    dependency_graph는 "agent_id -> 그 에이전트가 이미 서브 에이전트로 물고 있는
    agent_id 집합"이다(팀 범위, Repository가 조립해서 넘긴다 — MVP는 1단계
    위임이라 그래프 깊이가 얕지만, 순환 자체는 임의 깊이에서 생길 수 있으므로
    DFS로 확인한다).

    parent_agent_id가 None(아직 저장 안 된 초안)이면 이 초안을 가리킬 기존 노드가
    없으므로 순환이 성립하지 않는다 — 검사 없이 통과한다.
    """
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
        # child_id 아래(그 자식의 자식들 …)에 parent_agent_id가 이미 있으면,
        # parent -> child_id 연결을 추가하는 순간 순환이 생긴다.
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
    allow_subagents: bool,
) -> None:
    """서브 에이전트 구성 전체를 검증한다(02 §7.2).

    검증 순서: 자기 참조 → 중복(id) → 중복(alias) → 개별 필드(alias/설명 필수·
    활성·권한·깊이) → 순환. 저장·발행 API와 factory.py의 AgentRuntimeFactory.build()
    양쪽에서 동일하게 호출한다.
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

        if not allow_subagents and ref.has_subagents:
            raise DelegationDepthError(
                f"'{ref.child_agent_id}'는 이미 서브 에이전트를 갖고 있어 "
                "MVP의 1단계 위임 제한을 넘어섭니다."
            )

    validate_no_cycle(
        parent_agent_id=parent_agent_id,
        child_ids=child_ids,
        dependency_graph=dependency_graph,
    )
