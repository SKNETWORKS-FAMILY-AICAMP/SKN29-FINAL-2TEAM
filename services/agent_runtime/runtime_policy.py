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

# 업무 Agent에 노출하지 않는 Deep Agents 가상 파일 Tool.
DEFAULT_EXCLUDED_BUILTIN_TOOLS = frozenset({"delete"})

# 외부 시스템을 변경하는 Tool의 운영 정책 메모. 실행을 직접 차단하지는 않는다.
EXTERNAL_WRITE_TOOLS_POLICY_NOTE = (
    "외부 시스템에 실제로 쓰기/삭제/발송하는 Tool은 HITL 구현 전까지 읽기 전용으로 "
    "제한하거나, 사용자 확인 없이는 부수효과가 발생하지 않는 2단계(제안 → 확정) "
    "설계를 쓸 것 (2026-08-13_01 §11)."
)

# 부수효과가 있는 Tool을 사용할 수 있는 계정 역할.
#
# 2026-08-19에는 `leader`만이었다 — 그때는 실행 시점 재검사(`_run()`)가
# **유일한** 방어선이라, member는 도구를 실행하려 하면 곧바로
# `ToolException`(권한 없음)으로 막혔다(`interrupt_on`도 같이 안 걸었다 —
# 승인 카드를 띄우면 부른 사람 본인이 눌러 승인해 버릴 수 있어서, 승인 대기
# 없는 즉시 거부가 그 시점의 유일한 경계였다).
#
# 2026-08-20, 사용자 요청으로 `member`를 추가한다: "팀원이 자기 업무를
# 직접 등록할 수 있게 하고 싶다"는 요구였고, 이 값이 `task_register` 하나만
# 가리키는 게 아니라 부수효과 있는 도구 **전부**(`task_update`,
# `jira_create_issues`, 팀이 연결한 MCP 쓰기 도구까지)에 적용된다는 걸 확인한
# 뒤 "전부 열어도 된다"는 선택을 받았다(도구별 예외를 두려면 `is_tool_allowed_
# for_role()`에 `side_effect: bool` 대신 도구 참조를 받는 구조 변경이 필요해
# 범위가 더 컸다).
#
# **이 변경만으로 안전한 이유**: `factory.py`의 `build()`가 `interrupt_on`을
# 만들 때 이 정책과 **같은 함수**(`is_tool_allowed_for_role()`)를 다시 부른다
# (else 리더/멤버 둘 다 여기 값을 그대로 참조하므로 값이 어긋날 수 없다).
# 그래서 member가 이제 이 도구들을 실행할 수 있게 되는 것과 동시에, 그 실행이
# `HumanInTheLoopMiddleware`의 승인 대기에도 자동으로 걸린다 — leader가
# 예전부터 그래왔던 것과 똑같이, **자기 요청을 자기가 승인**해야 실제로
# 실행된다("등록할까요?" 확인 카드 → 승인 버튼). 방어선이 "역할이 아니면
# 거부"에서 "역할과 무관하게 실행 전에 스스로 승인"으로 바뀐 것이지, 방어선이
# 없어진 게 아니다.
DEFAULT_WRITE_TOOL_ALLOWED_ROLES: frozenset[AccountRole] = frozenset({"leader", "member"})

# 2026-08-21, A-1 재설계 — MCP Tool 호출 하나에 적용하는 timeout(초).
# 정본: `docs/작업기록/Deep_Agents/2026-08-21_01_Tool_timeout_재설계.md`
#
# **2026-08-19의 전역 300초와는 다른 값이고 다른 근거다.** 그때는 모든 도구에
# 같은 300초를 걸었고(`services/harness/runner.py`의 모델 호출 timeout을
# 그대로 재사용), "복잡한 검색처럼 정당하게 오래 걸리는 작업까지 다 끊긴다"는
# 이유로 `17e8c62`에서 되돌려졌다. 이번 값은 "MCP 도구가 보통 이 정도
# 걸린다"는 추측이 아니다 — 그 질문은 자유 연결 MCP에서는 답할 수 없다
# (`2026-08-20_01` §3). 대신 우리가 확실히 아는 값에서 역산한다:
# `Dockerfile`의 gunicorn `--timeout 600`. 이걸 넘기면 우리가 뭘 하든
# 워커가 SIGKILL되고 브라우저엔 `ERR_HTTP2_PROTOCOL_ERROR`만 남아 원인이
# 어디에도 안 남는다(같은 파일 주석, 2026-08-18 QA에서 실제로 겪음).
# 즉 이 값은 "정상 실행시간 추정"이 아니라 "gunicorn이 대신 죽이기 전에
# 우리가 먼저 곱게 끊어서 최소한 에러 메시지는 남긴다"는 방어선이다.
GUNICORN_WORKER_TIMEOUT_SECONDS = 600
DEFAULT_MCP_TOOL_CALL_TIMEOUT_SECONDS = 480

# override로도 넘을 수 없는 상한. gunicorn 한도(600초)에 최소 60초 여유를
# 남긴다 — 정확히 600으로 잡으면 이 미들웨어가 끊기 전에 워커가 먼저 죽어서
# 있으나 마나가 된다(위 주석의 실패 모드 그대로).
MAX_MCP_TOOL_CALL_TIMEOUT_SECONDS = GUNICORN_WORKER_TIMEOUT_SECONDS - 60


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
    # 없음). 2026-08-18, §5 Phase 4에서 `middleware/factory.py.build()`가
    # 실제로 읽게 배선까지는 끝냈지만, 그때는 "배선만 해두고 기본값은 계속
    # False로 둔다"는 보수적 선택이었다(실제로 값을 True로 바꾸는 별도 결정은
    # 없었다 — `_hitl_structural_check.py`가 True로 켠 적은 있지만 이건 구조
    # 검증용 스크립트지 운영 기본값을 바꾸자는 결정이 아니었다).
    # 2026-08-19: 사용자 요청으로 기본값을 True로 바꾼다 — Root/Child/GP
    # 전부에 `write_todos` 도구가 기본으로 붙는다.
    enable_todo: bool = True
    write_tool_allowed_roles: frozenset[AccountRole] = field(
        default_factory=lambda: DEFAULT_WRITE_TOOL_ALLOWED_ROLES
    )

    # 2026-08-21, A-1 — MCP Tool 호출 timeout. 값의 근거는 위 상수 정의부
    # 주석 참고. `mcp_tool_call_timeout_overrides`는 특정 MCP tool_ref만
    # 다른 값을 쓰는 탈출구다 — 빈 dict(전부 기본값)로 시작한다. 미리 모든
    # MCP 도구를 "빠름/느림"으로 분류하지 않고, 실제로 기본값 때문에 정상
    # 작업이 끊긴다는 게 확인된 것만 나중에 여기 넣는다.
    mcp_tool_call_timeout_seconds: float = DEFAULT_MCP_TOOL_CALL_TIMEOUT_SECONDS
    mcp_tool_call_timeout_overrides: dict[str, float] = field(default_factory=dict)

    # general-purpose 전용 기본값.
    # 2026-08-19: 사용자 요청으로 50/100으로 올렸다(기존 6/12) — GP는
    # Root/Child와 달리 `agent_versions.max_iterations` 같은 에이전트별 설정
    # 필드가 없어서, 이 값 자체가 GP의 실제 실행 상한이다(아래
    # `limits_for_general_purpose()` 참고).
    general_purpose_max_model_calls: int = 50
    general_purpose_max_tool_calls: int = 100

    # 설정값이 비정상적으로 커져도 넘지 못하는 전체 상한.
    # 2026-08-19: 사용자 요청으로 50/100으로 올렸다(기존 20/40).
    # Tool 호출 상한(`resolve_tool_call_limit`)은 Root/Child에 별도 설정 필드가
    # 없어 이 값을 그대로 쓰므로, 이 변경만으로 Root/Child의 실제 tool 호출
    # 상한도 즉시 100으로 바뀐다. 반면 모델 호출 상한(`resolve_model_call_limit`)은
    # `min(agent_versions.max_iterations, max_model_calls_ceiling)`이라 —
    # 이 ceiling을 올려도 DB의 `agent_versions.max_iterations` 기본값(6,
    # `DB/schema.sql`)이 그대로면 새로 만드는 에이전트의 실제 모델 호출 상한은
    # 여전히 6이다. 이 ceiling은 "최대 몇까지 허용할지"만 올린 것이고, 개별
    # 에이전트가 실제로 50까지 쓰게 하려면 Builder에서 그 에이전트의
    # max_iterations 값 자체를 올려야 한다(또는 DB 기본값 자체를 바꾸는 건
    # 별도 결정 — 이번 변경 범위 밖).
    max_model_calls_ceiling: int = 50
    max_tool_calls_ceiling: int = 100

    def timeout_for_mcp_tool(self, tool_ref: str) -> float:
        """이 MCP `tool_ref`에 적용할 timeout(초).

        `mcp_tool_call_timeout_overrides`에 등록된 값이 있으면 그 값,
        없으면 `mcp_tool_call_timeout_seconds`(기본값)를 쓴다. 어느 쪽이든
        `MAX_MCP_TOOL_CALL_TIMEOUT_SECONDS`를 넘지 못한다 — 그 위로 올리면
        gunicorn이 먼저 워커를 죽여서 이 timeout이 무의미해지기 때문이다
        (상수 정의부 주석).

        **MCP 도구 전용이다.** 내장 도구는 이 값을 쓰지 않는다 — 우리가 코드를
        직접 쓰는 도구라 필요하면 도구 자신이 자기 timeout을 갖는 게 맞고
        (`FilesystemMiddleware`의 `execute`가 이미 그렇다), 플랫폼이 또 다른
        값을 얹으면 두 값이 어긋날 뿐이다(`2026-08-21_01` §3). 호출 측
        (`middleware/tool_timeout.py`)이 MCP 여부를 판단해서 이 메서드를
        MCP일 때만 부른다.
        """
        requested = self.mcp_tool_call_timeout_overrides.get(
            tool_ref, self.mcp_tool_call_timeout_seconds
        )
        return min(requested, MAX_MCP_TOOL_CALL_TIMEOUT_SECONDS)

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

        기본값(`DEFAULT_WRITE_TOOL_ALLOWED_ROLES`)은 2026-08-20부터
        `leader`/`member` 둘 다를 통과시킨다 — 위 상수 정의부 주석 참고. 이
        함수 자체는 여전히 `write_tool_allowed_roles`를 그대로 읽으므로, 특정
        배포에서 역할을 더 제한하고 싶으면 `RuntimeCapabilityPolicy(
        write_tool_allowed_roles=frozenset({"leader"}))`처럼 인스턴스 생성
        시점에 좁힐 수 있다 — 이 메서드는 그 값을 신뢰할 뿐 하드코딩하지
        않는다.
        """
        if not side_effect:
            return True
        return account_role in self.write_tool_allowed_roles
