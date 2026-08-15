"""Child 정의를 실행 가능한 `CompiledSubAgent`로 변환한다."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from services.agent_runtime.context import RuntimeContext
from services.agent_runtime.definitions import AgentDefinition, SubagentDefinition
from services.agent_runtime.exceptions import DelegationDepthError

if TYPE_CHECKING:
    from deepagents import CompiledSubAgent


def build_subagent(
    definition: SubagentDefinition,
    context: RuntimeContext,
    *,
    build_child_graph: Callable[[AgentDefinition, RuntimeContext], Any],
) -> "CompiledSubAgent":
    """Child graph를 만들고 위임용 이름과 설명을 연결한다."""
    if definition_has_subagents(definition):
        raise DelegationDepthError(
            f"서브 에이전트 '{definition.agent_id}'는 이미 서브 에이전트를 갖고 있어 "
            "MVP의 1단계 위임 제한을 넘어섭니다."
        )

    child_definition = AgentDefinition(
        agent_id=definition.agent_id,
        agent_version_id=definition.agent_version_id,
        name=definition.name,
        description=definition.description,
        system_prompt=definition.system_prompt,
        model=definition.model,
        reasoning_effort=definition.reasoning_effort,
        max_iterations=definition.max_iterations,
        tool_refs=definition.tool_refs,
        subagents=(),
    )
    child_graph = build_child_graph(child_definition, context)

    from deepagents import CompiledSubAgent  # noqa: PLC0415 - 호출 시점에만 필요

    return CompiledSubAgent(
        name=definition.alias,
        description=definition.delegation_description,
        runnable=child_graph,
    )


def definition_has_subagents(definition: SubagentDefinition | AgentDefinition) -> bool:
    """정의에 다른 Child가 포함됐는지 확인한다."""
    return bool(getattr(definition, "subagents", ()))
