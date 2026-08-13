"""부모·서브 에이전트의 런타임 데이터 구조 정의.

정본: docs/작업기록/Deep_Agents/2026-08-13_02_Deep-Agent_런타임_공통_계약_v1.md §3

02 §20 체크리스트 1번: "AgentDefinition, SubagentDefinition이 한 곳에만 정의되어
있다" — 이 파일이 그 한 곳이다. 다른 모듈에서 유사 타입을 다시 정의하지 않는다.

deepagents를 import하지 않는다. 이 파일은 순수 데이터 구조만 담는다 — Loader나
Factory가 이 정의를 실제 Deep Agent 객체로 조립하는 책임을 진다(factory.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from services.agent_runtime.exceptions import (
    InvalidDelegationDescriptionError,
    InvalidSubagentAliasError,
)


@dataclass(frozen=True)
class SubagentDefinition:
    """부모 버전에 고정된 독립 실행형 서브 에이전트(§3.1)."""

    agent_id: str
    agent_version_id: str

    name: str
    description: str
    system_prompt: str

    model: str
    reasoning_effort: str
    max_iterations: int

    # 부모가 자식을 호출할 때 사용하는 필수 정보
    alias: str
    delegation_description: str

    tool_refs: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.alias.strip():
            raise InvalidSubagentAliasError("서브 에이전트 alias는 필수입니다.")

        if not self.delegation_description.strip():
            raise InvalidDelegationDescriptionError(
                "서브 에이전트 위임 설명은 필수입니다."
            )


@dataclass(frozen=True)
class AgentDefinition:
    """Deep Agent 하나를 생성하기 위한 완전한 런타임 정의(§3.2).

    ID 규칙(§3.2):
    - 저장된 부모/자식은 agent_id·agent_version_id가 모두 필수다.
    - 저장되지 않은 부모 초안 테스트만 두 값을 모두 None으로 둘 수 있다.
    - 저장되지 않은 초안을 서브 에이전트로 쓰는 것은 허용하지 않는다
      (이 조건은 dataclass 레벨이 아니라 subagents/validation.py가 검증한다 — 초안
      자체가 여기 subagents 필드에 들어올 일이 없도록 loader.py가 막는다).
    """

    agent_id: str | None
    agent_version_id: str | None

    name: str
    description: str
    system_prompt: str

    model: str
    reasoning_effort: str
    max_iterations: int

    tool_refs: tuple[str, ...] = field(default_factory=tuple)
    subagents: tuple[SubagentDefinition, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SubagentReference:
    """요청 단위 서브 에이전트 검증 정보(§3.3).

    불변 실행 정의(SubagentDefinition)와 현재 요청자의 권한 상태를 분리한다.
    is_active/can_execute는 요청 시점마다 다시 계산한다 — agent_version_id 기준
    전역 캐시에 저장하지 않는다(사용자마다 can_execute가 다를 수 있어서).
    """

    child_agent_id: str
    child_version_id: str

    alias: str
    delegation_description: str

    is_active: bool
    can_execute: bool

    # 고정된 자식 버전이 다시 자식을 포함하는가 — True면 MVP(1단계 위임)에서
    # DelegationDepthError 대상이다.
    has_subagents: bool


@dataclass(frozen=True)
class LoadedAgentDefinition:
    """Loader의 반환 타입(§3.4).

    definition.subagents와 subagent_references는 agent_id·agent_version_id
    기준으로 일대일 대응해야 한다 — 이 불변 조건은 Loader가 보장한다
    (loader.py 구현 시 assert 또는 생성자에서 검사할 것).
    """

    definition: AgentDefinition
    subagent_references: tuple[SubagentReference, ...] = field(default_factory=tuple)
