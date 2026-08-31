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
    approval_when: Callable[[dict[str, Any]], bool] | None = None
    injected_context: tuple[str, ...] = ()


# Tool에 서버가 주입할 수 있는 컨텍스트 값.
CONTEXT_VALUES: dict[str, Callable[[RuntimeContext], Any]] = {
    "team_id": lambda context: context.team_id,
    "account_id": lambda context: context.account_id,
    "session_id": lambda context: context.session_id,
    "project_id": lambda context: context.project_id,
    "run_id": lambda context: context.run_id,
    "parent_run_id": lambda context: context.parent_run_id,
    # 2026-08-21, `skill_register` 전용(설계 문서 "skill_register가 담당하는
    # 것" 절) — `scope=TEAM`인데 요청자가 `leader`가 아니면 그 자리에서
    # 거부해야 하는데, 이건 `is_tool_allowed_for_role()`의 side_effect 기준
    # RBAC(모든 write 도구에 공통)보다 더 좁은, 이 도구만의 규칙이라 handler
    # 안에서 직접 판단해야 한다 — 그러려면 handler가 역할값을 받아야 한다.
    "account_role": lambda context: context.role,
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


#: MCP 도구 tool_ref 접두사. 세 곳(여기, DB 마이그레이션, harness registry)이
#: 같은 규칙을 공유하니 바뀌면 같이 고친다.
MCP_TOOL_REF_PREFIX = "mcp:"


def model_safe_tool_name(tool_ref: str) -> str:
    """모델(LLM 함수 호출 API)에게 실제로 보낼 함수 이름.

    OpenAI 함수 이름은 `^[a-zA-Z0-9_-]+$`만 허용해 `mcp:<id>`의 콜론을 못 쓴다.
    저장소 규칙(tool_ref엔 콜론)은 그대로 두고 모델에게 나가는 이름만 바꾼다
    — 되돌리는 쪽은 `tool_ref_from_model_name()`.
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
        """요청된 tool_refs를 실제 `Tool` 목록으로 바꾼다.

        `agent_model`은 그 에이전트가 실제로 고른 모델 문자열이다
        (`AgentDefinition.model`) — `tools/adapters.py`의 `task_extraction`만
        이 값을 쓴다. `mcp:` 접두사가 하나라도 있을 때만 팀의 MCP 도구를
        조회한다(불필요한 DB 왕복을 피한다).

        `services.harness.registry.ALWAYS_ON_TOOL_REFS`(예: `skill_register`)는
        `tool_refs`에 없어도 `available`에 있으면 항상 포함한다 — 골라야 하는
        도구가 아니다. 옛 레거시 엔진의 `load_for_agent()`/`load_for_refs()`가
        하던 일을 여기로 옮겼다(2026-08-22, 레거시 엔진 폐기와 함께) — 지금은
        도구 로딩 경로가 여기 하나뿐이다. **`missing`(아래) 판정에는 안 넣는다**
        — always-on은 요청이 아니라 "있으면 딸려온다"이지 "반드시 있어야 한다"가
        아니다. 없으면 조용히 빠질 뿐, `ToolUnavailableError`감이 아니다.
        """
        # 지연 import — `services.harness.registry`의 무거운 의존성 사슬
        # (apps.connectors, backend.services.hr, services.mcp 등)을 이 모듈이
        # import되기만 해도 끌고 들어오지 않게 한다.
        from services.agent_runtime.tools.adapters import adapt_builtin_tools, adapt_mcp_tools
        from services.harness.registry import ALWAYS_ON_TOOL_REFS
        from services.agent_runtime.models.capabilities import (
            IMAGE_DOCUMENT_SEARCH_TOOL_REF,
            supports_image_input,
        )

        if (
            IMAGE_DOCUMENT_SEARCH_TOOL_REF in tool_refs
            and not supports_image_input(model=agent_model, team_id=context.team_id)
        ):
            raise ToolUnavailableError(
                "'문서 검색 · 원본 이미지' 도구는 이미지 입력을 지원하는 모델에서만 사용할 수 있습니다."
            )

        available = {tool.ref: tool for tool in adapt_builtin_tools(agent_model=agent_model)}

        if any(ref.startswith(MCP_TOOL_REF_PREFIX) for ref in tool_refs):
            for mcp_tool in adapt_mcp_tools(team_id=context.team_id):
                available[mcp_tool.ref] = mcp_tool

        missing = [ref for ref in tool_refs if ref not in available]

        # 없는 MCP 도구는 건너뛴다 — `agent_versions`가 불변이라 발행된 참조를
        # 지울 자리가 없다(운영자가 서버를 지운 것뿐, 정의 잘못이 아니다).
        # 내장 도구는 정의가 틀린 것(오타·삭제된 id)이라 그대로 막는다.
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

        # 순서 보존 dedup — tool_refs가 먼저, 아직 없는 always-on 도구는 뒤에.
        # always-on은 `available`에 있을 때만 딸려온다(위 docstring 참고).
        resolved_refs = tuple(dict.fromkeys((*tool_refs, *ALWAYS_ON_TOOL_REFS)))
        return tuple(available[ref] for ref in resolved_refs if ref in available)


__all__ = [
    "Tool",
    "ToolLoader",
    "CONTEXT_VALUES",
    "inject_runtime_context",
    "ToolUnavailableError",
    "model_safe_tool_name",
    "tool_ref_from_model_name",
]
