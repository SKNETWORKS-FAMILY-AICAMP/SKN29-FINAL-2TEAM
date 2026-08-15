"""호출 상한 정책을 LangChain Middleware로 변환한다."""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain.agents.middleware import ModelCallLimitMiddleware, ToolCallLimitMiddleware

if TYPE_CHECKING:
    from services.agent_runtime.context import RuntimeContext
    from services.agent_runtime.definitions import AgentDefinition
    from services.agent_runtime.runtime_policy import RuntimeCapabilityPolicy


class MiddlewareFactory:
    """Root/Child/GeneralPurpose에 붙일 Middleware 목록을 조립한다.

    2026-08-14: `TodoListMiddleware` 조건부 배선을 시도했다가 계약 문서
    (`2026-08-13_02_Deep-Agent_런타임_공통_계약_v1.md` §2 확정 원칙 8번 — "서비스
    전용 커스텀 Middleware, Memory, TODO, Checkpointer는 MVP에서 비활성화한다")와
    충돌한다는 걸 뒤늦게 발견해 되돌렸다. 사용자 확인: Todo/Memory/Checkpointer는
    지금 전부 뒤로 미룬다 — `runtime_policy.enable_todo`는 계약이 말하는 "확장
    위치"로만 남고(값은 있지만 여기서 읽지 않음), 다시 켤 때는 이 결정을 뒤집는
    것이므로 새로 확인이 필요하다.
    """

    def __init__(self, *, runtime_policy: "RuntimeCapabilityPolicy") -> None:
        self.runtime_policy = runtime_policy

    def build(self, *, definition: "AgentDefinition", context: "RuntimeContext") -> list:
        """Root 또는 Child의 모델·Tool 호출 상한을 만든다."""
        return [
            ModelCallLimitMiddleware(
                run_limit=self.runtime_policy.resolve_model_call_limit(
                    requested=definition.max_iterations
                ),
                exit_behavior="error",
            ),
            ToolCallLimitMiddleware(
                run_limit=self.runtime_policy.resolve_tool_call_limit(),
                exit_behavior="error",
            ),
        ]

    def build_for_general_purpose(self) -> list:
        """general-purpose의 모델·Tool 호출 상한을 만든다."""
        limits = self.runtime_policy.limits_for_general_purpose()
        return [
            ModelCallLimitMiddleware(run_limit=limits.max_model_calls, exit_behavior="error"),
            ToolCallLimitMiddleware(run_limit=limits.max_tool_calls, exit_behavior="error"),
        ]
