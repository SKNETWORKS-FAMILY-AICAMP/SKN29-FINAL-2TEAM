"""자식 정의를 실행 가능한 Deep Agent 서브 에이전트(CompiledSubAgent)로 조립한다.

정본: docs/작업기록/Deep_Agents/2026-08-13_02_Deep-Agent_런타임_공통_계약_v1.md §10

⚠ 미구현. deepagents.CompiledSubAgent를 실제로 쓰는 첫 지점이라, §15 스트리밍
스파이크 테스트 전에는 완성하지 않는다. TYPE_CHECKING으로만 타입을 참조해서
이 모듈을 import해도 deepagents가 설치 안 된 환경에서 ImportError가 안 나게
해둔다 — requirements/base.txt에 deepagents==0.7.5는 pin했지만 실제 설치·검증은
아직이다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from services.agent_runtime.context import RuntimeContext
from services.agent_runtime.definitions import AgentDefinition, SubagentDefinition
from services.agent_runtime.exceptions import DelegationDepthError

if TYPE_CHECKING:
    from deepagents import CompiledSubAgent


def build_subagent(
    definition: SubagentDefinition,
    context: RuntimeContext,
) -> "CompiledSubAgent":
    """자식을 독립 그래프로 컴파일하고 CompiledSubAgent로 감싼다(§10).

    name에는 부모가 호출할 alias, description에는 위임 판단용
    delegation_description을 넣는다. allow_subagents=False로 재귀 조립하므로,
    자식이 다시 자식을 포함하면 조용히 무시하지 않고 DelegationDepthError를 낸다
    — 그 검사는 runtime_factory.build()가 subagents/validation.py를 통해 이미
    한 번 하지만, 여기서도(§10 원문 그대로) 방어적으로 다시 확인한다.
    """
    if definition_has_subagents(definition):
        raise DelegationDepthError(
            f"서브 에이전트 '{definition.agent_id}'는 이미 서브 에이전트를 갖고 있어 "
            "MVP의 1단계 위임 제한을 넘어섭니다."
        )

    raise NotImplementedError(
        "deepagents 스트리밍 스파이크(02 §15) 완료 후 구현. 개념:\n"
        "  child_definition = AgentDefinition(agent_id=definition.agent_id, "
        "agent_version_id=definition.agent_version_id, name=definition.name, "
        "description=definition.description, system_prompt=definition.system_prompt, "
        "model=definition.model, reasoning_effort=definition.reasoning_effort, "
        "max_iterations=definition.max_iterations, tool_refs=definition.tool_refs, "
        "subagents=())\n"
        "  child_graph = runtime_factory.build(definition=child_definition, "
        "context=context, allow_subagents=False)\n"
        "  return CompiledSubAgent(name=definition.alias, "
        "description=definition.delegation_description, runnable=child_graph)"
    )


def definition_has_subagents(definition: SubagentDefinition | AgentDefinition) -> bool:
    """이 정의가 (한 단계 더) 서브 에이전트를 갖고 있는지.

    SubagentDefinition에는 subagents 필드가 없다 — 자식 정의는 loader.py가
    include_subagents=False로 로딩하므로 애초에 자식의 자식을 안 담는다. 따라서
    이 함수는 방어적 확인용이며, AgentDefinition에만 실제 의미가 있다.
    """
    return bool(getattr(definition, "subagents", ()))
