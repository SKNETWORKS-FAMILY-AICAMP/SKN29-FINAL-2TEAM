"""Root와 Child의 실행 정의."""

from __future__ import annotations

from dataclasses import dataclass, field

from services.agent_runtime.exceptions import (
    InvalidDelegationDescriptionError,
    InvalidSubagentAliasError,
)


@dataclass(frozen=True)
class SubagentDefinition:
    """Root에 연결할 Child의 실행 설정."""

    agent_id: str
    agent_version_id: str

    name: str
    description: str
    system_prompt: str

    model: str
    reasoning_effort: str
    max_iterations: int

    # Root가 task Tool로 Child를 선택할 때 사용한다.
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
    """Deep Agent graph 하나를 만드는 데 필요한 설정."""

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
    """현재 요청에서 확인한 Child의 상태와 권한."""

    child_agent_id: str
    child_version_id: str

    alias: str
    delegation_description: str

    is_active: bool
    can_execute: bool

    # Child가 다른 Child를 갖는지 나타낸다.
    has_subagents: bool


@dataclass(frozen=True)
class LoadedAgentDefinition:
    """실행 정의와 요청 시점의 Child 검증 정보를 함께 반환한다."""

    definition: AgentDefinition
    subagent_references: tuple[SubagentReference, ...] = field(default_factory=tuple)
