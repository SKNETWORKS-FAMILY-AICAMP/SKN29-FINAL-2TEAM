"""역할별 호출 상한과 write Tool 실행 권한을 정의한다.

**노출은 안 건드린다**(2026-08-19) — 모델에게 어떤 도구를 보여줄지는 역할과
무관하다(`factory.py`의 `build()`). 여기 있는 `is_tool_allowed_for_role()`은
그 도구를 **실행**해도 되는지만 판단한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Role = Literal["ROOT", "GENERAL_PURPOSE", "CHILD"]
AccountRole = Literal["leader", "member"]

#: 업무 Agent에 노출하지 않는 Deep Agents 가상 파일 Tool.
#:
#: **여기 있는 파일 Tool은 사용자의 디스크를 건드리지 않는다**(2026-08-18 실측).
#: `factory.build()`가 넘기는 backend는 `CompositeBackend(default=StateBackend(),
#: routes={"/memories/...": StoreBackend})` 뿐이라(`memory/backend.py`), 쓰는
#: 곳은 그래프 상태(휘발) 아니면 장기 메모리 Store다 — `FilesystemBackend`도
#: `LocalShellBackend`도 쓰지 않는다. `execute`는 두 backend 어느 쪽에도
#: `execute` 속성이 없어 **호출 자체가 성립하지 않는다.**
#:
#: 그래서 `delete`만 뺀다. 나머지를 더 막을 이유가 없다 — 프롬프트가
#: 「네가 일하는 동안 쓰는 임시 작업 공간」이라고 말하는 것이 정확한 설명이고,
#: 그 말대로 쓰는 데 필요한 도구들이다.
DEFAULT_EXCLUDED_BUILTIN_TOOLS = frozenset({"delete"})

#: 외부 시스템을 변경하는 Tool의 운영 정책 메모. 실행을 직접 차단하지는 않는다.
#:
#: 2026-08-18에 앞부분을 고쳤다 — 「HITL 구현 전까지」라는 전제가 사라졌다.
#: 승인 게이트가 실제로 붙었다(`factory.py`의 `interrupt_on` → `events.py`의
#: `awaiting_confirmation` → `apps/chat/api_views.py`의 재개). 이제 `side_effect`
#: Tool은 사람이 확인 카드에서 승인하기 전까지 실행되지 않는다.
EXTERNAL_WRITE_TOOLS_POLICY_NOTE = (
    "외부 시스템에 실제로 쓰기/삭제/발송하는 Tool(side_effect=True)은 승인 게이트를 "
    "지난 뒤에만 실행된다 — 모델이 부르면 그래프가 멈추고 사람에게 확인 카드가 뜬다 "
    "(2026-08-18). 새 Tool을 더할 때 부수효과가 있으면 side_effect=True로 선언할 것 "
    "— 게이트가 그 플래그 하나만 보고 판단한다."
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
    # 2026-08-14에는 계약 §2-8과 충돌해 배선을 되돌렸었다(값만 남기고 읽는 코드
    # 없음). 2026-08-18, §5 Phase 4에서 `middleware/factory.py.build()`가 이제
    # 실제로 읽는다 — 기본값 False라 명시적으로 켜지 않으면 이전과 동일하게 돈다.
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

    def is_tool_allowed_for_role(self, *, side_effect: bool, account_role: AccountRole) -> bool:
        """부수효과 없는 도구는 항상 허용. 부수효과 있는 도구는 허용 역할만 통과.

        **노출이 아니라 실행만 막는다**(2026-08-19 정책 변경). 예전엔 이
        판단으로 `filter_tools_for_role()`이 모델에게 보여줄 도구 목록에서
        허용 안 된 것을 통째로 지웠다 — 그러면 모델이 그 도구를 아예 모르게
        되어 "그런 기능이 없다"고 답했는데, 실제로는 권한이 없을 뿐이었다
        (버그 리포트: 「승인 필요가 붙어있는 툴에 대해서 에이전트가 툴이
        존재하지 않는다고 판단」). 이제 노출은 역할과 무관하게 항상 하고
        (`services/agent_runtime/factory.py`의 `build()`), 이 함수는
        `_to_langchain_tool()`의 `_run()`이 실행 직전에만 써서 "왜 안 되는지"를
        말로 돌려준다.
        """
        if not side_effect:
            return True
        return account_role in self.write_tool_allowed_roles
