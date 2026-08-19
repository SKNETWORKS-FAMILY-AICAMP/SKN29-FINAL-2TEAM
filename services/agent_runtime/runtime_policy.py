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

# 2026-08-19, §5순위 — Tool 호출 하나(외부 I/O)에 적용하는 기본 timeout(초).
# `services/harness/runner.py`가 이미 이 harness 안에서 쓰는 모델 호출
# timeout(`OpenAI(timeout=300)`)과 같은 값을 재사용한다 — 개별 tool 호출도
# 같은 실행 경로 안에서 일어나는 같은 성격의 외부 I/O라 새 숫자를 만들 근거가
# 없다(정본: `2026-08-19_01_실행_안정성_설계.md` §3).
DEFAULT_TOOL_CALL_TIMEOUT_SECONDS = 300


@dataclass(frozen=True)
class RoleLimits:
    """한 역할(Root/GP/Child)에 적용될 호출 횟수 상한."""

    max_model_calls: int
    max_tool_calls: int


@dataclass(frozen=True)
class RuntimeCapabilityPolicy:
    """역할별 미들웨어 조립·RBAC 필터링에 쓰이는 정책 값 묶음."""

    excluded_builtin_tools: frozenset[str] = DEFAULT_EXCLUDED_BUILTIN_TOOLS
    # 2026-08-14에는 계약 §2-8과 충돌해 배선을 되돌렸었다(값만 남기고 읽는 코드
    # 없음). 2026-08-18, §5 Phase 4에서 `middleware/factory.py.build()`가 이제
    # 실제로 읽는다 — 기본값 False라 명시적으로 켜지 않으면 이전과 동일하게 돈다.
    enable_todo: bool = False
    write_tool_allowed_roles: frozenset[AccountRole] = field(
        default_factory=lambda: DEFAULT_WRITE_TOOL_ALLOWED_ROLES
    )

    # 2026-08-19, §5순위 — 개별 tool 호출 timeout. `tool_call_timeout_overrides`는
    # 특정 tool_ref만 다른 값을 쓰고 싶을 때 쓰는 탈출구다 — 지금은 근거가 될
    # 실측값이 없어 빈 dict(전부 기본값)로 시작한다. 필요해지면 여기 값만
    # 채우면 되고, `timeout_for_tool()` 호출부는 바뀌지 않는다.
    tool_call_timeout_seconds: int = DEFAULT_TOOL_CALL_TIMEOUT_SECONDS
    tool_call_timeout_overrides: dict[str, int] = field(default_factory=dict)

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

    def resolve_model_call_limit(
        self, *, requested: int, account_role: AccountRole | None = None
    ) -> int:
        """Root/Child의 `max_iterations`(사용자 설정값)에 방어선을 적용한다.

        `account_role`(2026-08-18, Phase 2): 역할별로 다른 상한을 걸 수 있도록
        **구조만** 열어둔 파라미터다 — 아직 역할별 실제 값이 정해진 바 없어서(그런
        값을 요구·승인받은 적이 없음) 지금은 값을 만들어내지 않고 어떤 역할이
        와도 동일하게 `max_model_calls_ceiling` 방어선만 적용한다. 실제 차등
        값이 확정되면 이 메서드 안에서만 분기를 추가하면 되고, 호출부
        (`middleware/factory.py`)는 이미 `account_role`을 넘기고 있으므로 안 바뀐다.
        "요금제별" 분기는 넣지 않았다 — 이 코드베이스 어디에도 pricing/tier
        개념이 없어(`DB/schema.sql` 등 전수 확인) 근거 없이 파라미터조차 만들지
        않았다.
        """
        return min(requested, self.max_model_calls_ceiling)

    def resolve_tool_call_limit(
        self, *, requested: int | None = None, account_role: AccountRole | None = None
    ) -> int:
        """Root/Child의 tool-call 상한. 사용자 설정 필드가 없으므로 방어선 값 자체를 쓴다.

        `account_role`은 `resolve_model_call_limit`과 같은 이유로 구조만 열어둔
        파라미터 — 위 docstring 참고.
        """
        if requested is None:
            return self.max_tool_calls_ceiling
        return min(requested, self.max_tool_calls_ceiling)

    def timeout_for_tool(self, tool_ref: str) -> int:
        """이 `tool_ref`에 적용할 timeout(초). `tool_call_timeout_overrides`에
        등록된 값이 있으면 그 값, 없으면 `tool_call_timeout_seconds`(기본값)를
        쓴다."""
        return self.tool_call_timeout_overrides.get(tool_ref, self.tool_call_timeout_seconds)

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
