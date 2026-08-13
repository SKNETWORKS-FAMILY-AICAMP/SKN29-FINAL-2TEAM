"""모델·도구·서브 에이전트·확장 기능을 조합해 Deep Agent를 생성한다.

정본: docs/작업기록/jihun_buildingpage/2026-08-13_02_Deep-Agent_런타임_공통_계약_v1.md §11

Builder Test API와 Chat API 양쪽 모두 이 Factory(정확히는 executor.py를 거쳐)를
통해서만 Deep Agent를 조립한다 — apps/agents·apps/chat이 create_deep_agent()를
직접 호출하지 않는다(01 §7).

⚠ 미구현. deepagents.create_deep_agent 호출부라 §15 스트리밍 스파이크 전에는
완성하지 않는다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from services.agent_runtime.context import RuntimeContext
from services.agent_runtime.definitions import AgentDefinition, SubagentReference
from services.agent_runtime.subagents.validation import validate_subagents

if TYPE_CHECKING:
    from services.agent_runtime.middleware.factory import MiddlewareFactory
    from services.agent_runtime.models.factory import ModelFactory
    from services.agent_runtime.subagents.builder import build_subagent
    from services.agent_runtime.tools.loader import ToolLoader


class DependencyGraphSource:
    """팀 범위의 "agent_id -> 그 에이전트가 물고 있는 서브 에이전트 agent_id 집합"을
    돌려준다. subagents/validation.py의 validate_no_cycle에 넘길 그래프를 만드는
    책임이다.

    ⚠ 미구현 — backend/db/agent_platform.py의 AgentSubagentRepository 완성 후
    거기서 팀 전체 관계를 한 번에 긁어와 조립한다.
    """

    def load(self, team_id: str) -> dict[str, set[str]]:
        raise NotImplementedError(
            "AgentSubagentRepository로 팀 전체 parent->child 관계를 읽어 "
            "dict[str, set[str]]로 조립한다."
        )


class AgentRuntimeFactory:
    """definition + subagent_references + context → 실행 가능한 Deep Agent.

    §11의 조립 순서를 그대로 따른다: 검증 → 모델 → 도구 → 서브 에이전트 →
    미들웨어 → create_deep_agent(). 순서를 바꾸지 않는다 — 검증이 가장 먼저인
    이유는, 뒤 단계(모델 생성·도구 로딩)가 비용이 드는 I/O라 구조가 잘못된
    요청을 그 전에 걸러야 해서다.
    """

    def __init__(
        self,
        *,
        dependency_graph: DependencyGraphSource,
        model_factory: "ModelFactory",
        tool_loader: "ToolLoader",
        middleware_factory: "MiddlewareFactory",
    ) -> None:
        self.dependency_graph = dependency_graph
        self.model_factory = model_factory
        self.tool_loader = tool_loader
        self.middleware_factory = middleware_factory

    def build(
        self,
        *,
        definition: AgentDefinition,
        subagent_references: tuple[SubagentReference, ...] = (),
        context: RuntimeContext,
        allow_subagents: bool = True,
    ) -> Any:
        validate_subagents(
            parent_agent_id=definition.agent_id,
            child_refs=subagent_references,
            dependency_graph=self.dependency_graph.load(context.team_id),
            allow_subagents=allow_subagents,
        )

        raise NotImplementedError(
            "검증까지는 실제로 동작한다(subagents/validation.py 완성됨). "
            "모델 생성(models/factory.py)·도구 로딩(tools/loader.py)·서브 에이전트 "
            "조립(subagents/builder.py)이 전부 스텁이라 여기서 멈춘다. "
            "완성 순서는 02 §17.2 작업자 B 트랙: Model -> Definition Loader 연결부 "
            "-> Subagent Builder -> Factory -> Executor -> Events."
        )
