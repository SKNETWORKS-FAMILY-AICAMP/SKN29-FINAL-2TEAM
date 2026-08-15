"""역할별 Tool 노출, 호출 상한, write Tool 권한을 정의한다."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from services.agent_runtime.tools.loader import Tool

Role = Literal["ROOT", "GENERAL_PURPOSE", "CHILD"]
AccountRole = Literal["leader", "member"]

# 업무 Agent에 노출하지 않는 Deep Agents 가상 파일 Tool.
DEFAULT_EXCLUDED_BUILTIN_TOOLS = frozenset({"delete"})

# 외부 시스템을 변경하는 Tool의 운영 정책 메모. 실행을 직접 차단하지는 않는다.
EXTERNAL_WRITE_TOOLS_POLICY_NOTE = (
    "외부 시스템에 실제로 쓰기/삭제/발송하는 Tool은 HITL 구현 전까지 읽기 전용으로 "
    "제한하거나, 사용자 확인 없이는 부수효과가 발생하지 않는 2단계(제안 → 확정) "
    "설계를 쓸 것 (2026-08-13_01 §11)."
)

# 부수효과가 있는 Tool을 사용할 수 있는 계정 역할.
DEFAULT_WRITE_TOOL_ALLOWED_ROLES: frozenset[AccountRole] = frozenset({"leader"})


@dataclass(frozen=True)
class RoleLimits:
    """한 역할(Root/GP/Child)에 적용될 호출 횟수 상한."""

    max_model_calls: int
    max_tool_calls: int


@dataclass(frozen=True)
class RuntimeCapabilityPolicy:
    """역할별 미들웨어 조립·RBAC 필터링에 쓰이는 정책 값 묶음."""

    excluded_builtin_tools: frozenset[str] = DEFAULT_EXCLUDED_BUILTIN_TOOLS
    # 2026-08-14: 계약 §2-8("Memory, TODO, Checkpointer는 MVP에서 비활성화한다")과
    # 충돌해 배선을 되돌렸다 — 값은 남기되(확장 위치) 이 값을 읽는 코드는 없다.
    enable_todo: bool = False
    write_tool_allowed_roles: frozenset[AccountRole] = field(
        default_factory=lambda: DEFAULT_WRITE_TOOL_ALLOWED_ROLES
    )

    # general-purpose 전용 기본값.
    general_purpose_max_model_calls: int = 6
    general_purpose_max_tool_calls: int = 12

    # 설정값이 비정상적으로 커져도 넘지 못하는 전체 상한.
    max_model_calls_ceiling: int = 20
    max_tool_calls_ceiling: int = 40

    def limits_for_general_purpose(self) -> RoleLimits:
        """general-purpose에 적용할 상한. 방어선도 함께 적용된 최종값."""
        return RoleLimits(
            max_model_calls=min(self.general_purpose_max_model_calls, self.max_model_calls_ceiling),
            max_tool_calls=min(self.general_purpose_max_tool_calls, self.max_tool_calls_ceiling),
        )

    def resolve_model_call_limit(self, *, requested: int) -> int:
        """Root/Child의 `max_iterations`(사용자 설정값)에 방어선을 적용한다."""
        return min(requested, self.max_model_calls_ceiling)

    def resolve_tool_call_limit(self, *, requested: int | None = None) -> int:
        """Root/Child의 tool-call 상한. 사용자 설정 필드가 없으므로 방어선 값 자체를 쓴다."""
        if requested is None:
            return self.max_tool_calls_ceiling
        return min(requested, self.max_tool_calls_ceiling)

    def is_tool_allowed_for_role(self, *, side_effect: bool, account_role: AccountRole) -> bool:
        """부수효과 없는 도구는 항상 허용. 부수효과 있는 도구는 허용 역할만 통과."""
        if not side_effect:
            return True
        return account_role in self.write_tool_allowed_roles

    def filter_tools_for_role(
        self, tools: tuple["Tool", ...], *, account_role: AccountRole
    ) -> tuple["Tool", ...]:
        """허용되지 않은 도구를 조용히 제외한다(예외를 던지지 않음)."""
        return tuple(
            tool
            for tool in tools
            if self.is_tool_allowed_for_role(side_effect=tool.side_effect, account_role=account_role)
        )
