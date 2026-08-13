"""tool_ref를 기준으로 내장 도구와 MCP 도구를 선택적으로 로딩한다.

정본: docs/작업기록/Deep_Agents/2026-08-13_02_Deep-Agent_런타임_공통_계약_v1.md §8, §9

Tool 데이터 구조와 컨텍스트 주입(inject_runtime_context)은 deepagents에 의존하지
않는 순수 로직이라 지금 구현한다. 실제 도구 목록을 채우는 ToolLoader.load()는
기존 services/harness/registry.py(BUILTIN_TOOLS)·MCP 클라이언트 연결이 필요해서
스텁으로 둔다.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from services.agent_runtime.context import RuntimeContext
from services.agent_runtime.exceptions import ToolContextConfigurationError, ToolUnavailableError


@dataclass(frozen=True)
class Tool:
    """도구 하나의 런타임 표현(§8.1).

    injected_context에 선언된 이름만 서버가 강제로 채운다 — 선언 안 한 인자가
    전달돼 핸들러에서 TypeError가 나는 경로를 막는다(§8.2).
    """

    ref: str
    name: str
    description: str
    input_schema: dict
    handler: Callable[..., Any]

    side_effect: bool = False
    injected_context: tuple[str, ...] = ()


# 도구가 선언할 수 있는 주입 가능 컨텍스트 이름 → RuntimeContext에서 값을 뽑는 함수.
# 새 이름을 추가할 때는 RuntimeContext(context.py)에 해당 필드가 있는지 먼저 확인할 것.
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
    """모델/사용자가 보낸 인자에 서버 컨텍스트 값을 덮어써서 반환한다(§8.2).

    서버 값이 항상 우선한다 — 모델이 같은 키로 다른 값을 보내도 무시한다.
    """
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


class ToolLoader:
    """tool_refs를 실제 Tool 목록으로 변환한다.

    ⚠ 미구현. 완성하려면:
    - 내장 도구: services/harness/registry.py의 BUILTIN_TOOLS를 tools/adapters.py로
      감싸 injected_context를 명시한 Tool로 변환(§8.3 — 레거시 inspect.signature()
      자동 추론은 마이그레이션 기간에만 허용, deprecation warning 필수).
    - MCP 도구: services/mcp/client.py 연결. MVP는 팀 공용 자격 증명만(§9) —
      개인 MCP 자격 증명 요청이 오면 명시적으로 거부할 것(조용히 팀 자격으로
      fallback하지 않는다. fallback 여부는 별도 제품 정책으로 결정 전까지 보류).
    """

    def load(self, *, tool_refs: tuple[str, ...], context: RuntimeContext) -> tuple[Tool, ...]:
        raise NotImplementedError(
            "harness.registry.BUILTIN_TOOLS 어댑터(tools/adapters.py)와 MCP 클라이언트 "
            "연결 후 구현. 없는 tool_ref는 ToolUnavailableError를 낸다."
        )


__all__ = ["Tool", "ToolLoader", "CONTEXT_VALUES", "inject_runtime_context", "ToolUnavailableError"]
