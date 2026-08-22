"""tool_ref 로딩과 서버 컨텍스트 주입을 담당한다."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from services.agent_runtime.context import RuntimeContext
from services.agent_runtime.exceptions import ToolContextConfigurationError, ToolUnavailableError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Tool:
    """Factory가 LangChain Tool로 변환하기 전의 Tool 설정."""

    ref: str
    name: str
    description: str
    input_schema: dict
    handler: Callable[..., Any]

    side_effect: bool = False
    injected_context: tuple[str, ...] = ()


# Tool에 서버가 주입할 수 있는 컨텍스트 값.
CONTEXT_VALUES: dict[str, Callable[[RuntimeContext], Any]] = {
    "team_id": lambda context: context.team_id,
    "account_id": lambda context: context.account_id,
    "session_id": lambda context: context.session_id,
    "project_id": lambda context: context.project_id,
    "run_id": lambda context: context.run_id,
    "parent_run_id": lambda context: context.parent_run_id,
}


def inject_runtime_context(
    tool: Tool,
    arguments: Mapping[str, Any],
    context: RuntimeContext,
) -> dict[str, Any]:
    """Tool이 선언한 컨텍스트 인자를 서버 값으로 덮어쓴다."""
    resolved = dict(arguments)

    for name in tool.injected_context:
        try:
            resolved[name] = CONTEXT_VALUES[name](context)
        except KeyError as exc:
            raise ToolContextConfigurationError(
                f"도구 '{tool.ref}'가 선언한 injected_context '{name}'을 "
                "CONTEXT_VALUES에서 찾을 수 없습니다."
            ) from exc

    return resolved


#: MCP 도구 tool_ref 접두사. `DB/migrations/2026-08-11_agent_platform.sql`,
#: `services/harness/registry.py`와 같은 규칙이라 바뀌면 세 곳을 같이 고쳐야 한다.
#:
#: "이 호출이 MCP인가"를 판단하는 곳(`middleware/tool_timeout.py` 등)은 문자열을
#: 다시 적지 않고 이 상수를 import해서 쓴다.
MCP_TOOL_REF_PREFIX = "mcp:"


def model_safe_tool_name(tool_ref: str) -> str:
    """모델(LLM 함수 호출 API)에게 실제로 보낼 함수 이름.

    OpenAI 함수 이름은 `^[a-zA-Z0-9_-]+$`만 허용해 `mcp:<id>` 처럼 콜론이 든
    tool_ref를 그대로 못 쓴다 — 레거시 `services/harness/runner.py`의
    `model_name_for()`와 동일 근거(2026-08-12 실측: `Invalid 'tools[N].name':
    string does not match pattern`). 저장소 규칙(tool_ref엔 콜론)은 바꾸지
    않고, 모델에게 나가는 이름만 여기서 바꾼다 — 되돌리는 쪽은
    `tool_ref_from_model_name()`.
    """
    return tool_ref.replace(":", "__")


def tool_ref_from_model_name(model_name: str) -> str:
    """모델이 실제로 부른 함수 이름을 저장소 tool_ref로 되돌린다.

    `model_safe_tool_name()`의 역변환. 콜론이 없던 이름(내장 도구, `task`
    위임 등)은 그대로 통과한다.
    """
    return model_name.replace("__", ":")


class ToolLoader:
    """내장 Tool과 MCP Tool ref를 실제 `Tool` 목록으로 변환한다."""

    def load(
        self,
        *,
        tool_refs: tuple[str, ...],
        context: RuntimeContext,
        agent_model: str | None = None,
    ) -> tuple[Tool, ...]:
        """`agent_model`은 이 요청을 부른 에이전트가 실제로 고른 모델 문자열이다
        (`AgentDefinition.model`) — `RuntimeContext`엔 없는 값이라 별도 인자로
        받는다. 지금은 `tools/adapters.py`의 `task_extraction` 하나만 이 값을
        쓴다(레거시 `services/harness/runner.py`의 `_injected()`가 같은 이유로
        `agent.get("model")`을 넘기는 것과 동일한 근거).

        MCP tool_ref(`mcp:<id>` 접두사, 2026-08-14 연결)는 요청된 tool_refs 중
        하나라도 그 접두사면 팀의 등록된 MCP 도구를 함께 조회한다 — 내장
        도구만 쓰는 에이전트가 매 실행마다 불필요한 DB 왕복을 하지 않도록,
        실제로 필요할 때만 조회한다.
        """
        # 지연 import — `services.harness.registry`의 무거운 의존성 사슬
        # (apps.connectors, backend.services.hr, services.mcp 등)을 이 모듈이
        # import되기만 해도 끌고 들어오지 않게 한다.
        from services.agent_runtime.tools.adapters import adapt_builtin_tools, adapt_mcp_tools

        available = {tool.ref: tool for tool in adapt_builtin_tools(agent_model=agent_model)}

        if any(ref.startswith(MCP_TOOL_REF_PREFIX) for ref in tool_refs):
            for mcp_tool in adapt_mcp_tools(team_id=context.team_id):
                available[mcp_tool.ref] = mcp_tool

        missing = [ref for ref in tool_refs if ref not in available]

        # **없는 MCP 도구는 건너뛴다**(2026-08-22). 운영자가 MCP 서버를 지우거나
        # 옮기면 그 서버의 `mcp:<id>` 참조가 이미 발행된 `agent_versions`에 남는데,
        # `agent_versions`는 불변이라 그 자리에서 지울 수가 없다(02 §5.2). 예전에는
        # 레거시 `agent_tool`에서 참조를 같이 지워 줘서 이 상황이 안 생겼지만,
        # 2026-08-22에 레거시 스키마를 폐기하면서 그 청소부가 없어졌다.
        #
        # 그래서 정리를 저장 시점이 아니라 **실행 시점**에 한다. 없는 서버의 도구
        # 하나 때문에 에이전트 전체가 못 도는 것보다, 그 도구만 빼고 도는 편이 낫다
        # — 사라진 것은 관리자가 내린 서버지 에이전트 정의의 잘못이 아니다.
        #
        # **내장 도구는 그대로 막는다.** 그건 운영 변경이 아니라 정의가 틀린
        # 것이고(오타·삭제된 tool id), 조용히 빼면 에이전트가 이유 없이 다르게
        # 행동한다.
        missing_mcp = [ref for ref in missing if ref.startswith(MCP_TOOL_REF_PREFIX)]
        missing_builtin = [ref for ref in missing if not ref.startswith(MCP_TOOL_REF_PREFIX)]

        if missing_builtin:
            raise ToolUnavailableError(
                f"다음 도구를 불러올 수 없습니다: {', '.join(missing_builtin)}. "
                "등록되지 않았거나, 비활성화됐거나, 이 팀 소속이 아닙니다."
            )
        if missing_mcp:
            # 조용히 넘기지 않는다 — 왜 그 도구를 안 쓰는지 물었을 때 답할
            # 근거가 로그에는 남아야 한다.
            logger.warning(
                "없는 MCP 도구를 건너뛴다(team_id=%s): %s", context.team_id, ", ".join(missing_mcp)
            )
        return tuple(available[ref] for ref in tool_refs if ref in available)


__all__ = [
    "Tool",
    "ToolLoader",
    "CONTEXT_VALUES",
    "inject_runtime_context",
    "ToolUnavailableError",
    "model_safe_tool_name",
    "tool_ref_from_model_name",
]
