"""역할별 호출 상한과 write Tool 실행 권한을 정의한다.

**노출은 안 건드린다** — 모델에게 어떤 도구를 보여줄지는 역할과 무관하다
(`factory.py`의 `build()`). 여기 있는 `is_tool_allowed_for_role()`은 그 도구를
**실행**해도 되는지만 판단한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Role = Literal["ROOT", "GENERAL_PURPOSE", "CHILD"]
AccountRole = Literal["leader", "member"]

# 업무 Agent에 노출하지 않는 Deep Agents 가상 파일 Tool.
#
# 2026-08-26 — `delete`를 다시 켰다. 노출만 켜는 게 아니라 `factory.py`의
# `build()`가 이 목록에서 `delete`가 빠진 걸 보고 `interrupt_on`에도 같이
# 넣는다 — 부수효과 있는 다른 도구와 똑같이 승인 카드를 거치게 하기
# 위해서다(`EXTERNAL_WRITE_TOOLS_POLICY_NOTE` 참고 — "HITL 구현 전까지"
# 조건이 이제 풀렸다). 다만 이 승인은 "사람이 한 번 더 확인한다"는 것이지
# "팀장만 팀 스킬을 지울 수 있다" 같은 역할별 접근 제어는 아니다 — 이 도구는
# `skills/service.py`의 권한 검사를 거치지 않는 별개 경로라서, 팀원도 채팅으로
# 팀 스킬 파일을 지우자고 요청하고 스스로 승인할 수 있다. 이 간극은 아직 안
# 막혀 있다.
#
# ⚠ **2026-08-26 병합에서 다시 막았다(PM 결정).** 위 문단이 스스로 밝힌 그
# 간극 때문이다 — 팀 스킬은 `/skills/team/`(`skills/backend.py`의
# `SKILLS_TEAM_PATH_PREFIX`)에 있는 가상 파일이고, `delete`는 그 파일을 바로
# 지운다. `skills/service.py`의 `_require_leader`는 API·`skill_register` 경로에만
# 걸려 있어서, **팀 스킬 등록은 팀장 전용인데 삭제는 팀원도 되는** 비대칭이
# 생긴다. 승인 카드는 "사람이 한 번 더 본다"일 뿐 역할 검사가 아니다.
#
# 서비스가 이미 공개 주소(halil-ai.site)로 나가 있어 그 상태로 둘 수 없었다.
# **`delete` 자체를 반대하는 것이 아니다** — 위 경로에 역할 검사가 붙으면 이
# 줄을 `frozenset()`으로 되돌리는 것이 맞다. 그때까지만 막는다.
DEFAULT_EXCLUDED_BUILTIN_TOOLS: frozenset[str] = frozenset({"delete"})

# 외부 시스템을 변경하는 Tool의 운영 정책 메모. 실행을 직접 차단하지는 않는다.
EXTERNAL_WRITE_TOOLS_POLICY_NOTE = (
    "외부 시스템에 실제로 쓰기/삭제/발송하는 Tool은 HITL 구현 전까지 읽기 전용으로 "
    "제한하거나, 사용자 확인 없이는 부수효과가 발생하지 않는 2단계(제안 → 확정) "
    "설계를 쓸 것 (2026-08-13_01 §11)."
)

# 부수효과가 있는 Tool을 실행할 수 있는 계정 역할. `task_register` 하나가 아니라
# 부수효과 있는 도구 전부(`task_update`, `jira_create_issues`, 팀이 연결한 MCP
# 쓰기 도구 포함)에 적용된다.
#
# 여기서 역할을 넓혀도 무방한 이유: `factory.py`의 `build()`가 `interrupt_on`을
# 만들 때 같은 `is_tool_allowed_for_role()`을 쓴다. 실행 권한이 열리는 것과 동시에
# HITL 승인 대기에도 걸리므로, 경계는 "역할 거부"가 아니라 "실행 전 본인 승인"이다.
DEFAULT_WRITE_TOOL_ALLOWED_ROLES: frozenset[AccountRole] = frozenset({"leader", "member"})

# MCP Tool 호출 하나에 적용하는 timeout(초).
# 정본: `docs/설계 및 구현/3_중간발표 이후/작업기록/Deep_Agents/2026-08-21_01_Tool_timeout_재설계.md`
#
# 자유 연결 MCP는 정상 실행시간을 추정할 수 없으므로(`2026-08-20_01` §3) 확실히
# 아는 값에서 역산한다 — `Dockerfile`의 gunicorn `--timeout 600`을 넘기면 워커가
# SIGKILL되고 브라우저엔 `ERR_HTTP2_PROTOCOL_ERROR`만 남아 원인이 사라진다.
# 성능 추정이 아니라 "gunicorn보다 먼저 곱게 끊어 에러 메시지라도 남긴다"는
# 방어선이다. 모든 도구에 같은 값을 거는 전역 timeout은 쓰지 않는다 — 정당하게
# 오래 걸리는 작업까지 끊긴다.
GUNICORN_WORKER_TIMEOUT_SECONDS = 600
DEFAULT_MCP_TOOL_CALL_TIMEOUT_SECONDS = 480

# 한 super-step에서 동시에 실행할 tool call 수. LangGraph `RunnableConfig`의
# `max_concurrency`로 전달되며, 초과분은 버리지 않고 대기시킨다.
# 정본: `docs/설계 및 구현/3_중간발표 이후/작업기록/Deep_Agents/2026-08-20_02_에이전트_병렬실행_설계.md` §5.1
#
# 부하 테스트 전 잠정값 — "최적"이 아니라 "무제한을 유한하게"가 근거다. 중첩
# Child에도 전파되므로 위임 깊이가 1단계인 지금(`BuildDelegationDepthTests`)
# 한 요청의 최악은 4×4=16개다.
DEFAULT_MAX_CONCURRENCY = 4

# override로도 넘을 수 없는 상한. gunicorn 한도에 60초 여유를 남긴다 — 정확히
# 600으로 잡으면 미들웨어가 끊기 전에 워커가 먼저 죽어 있으나 마나가 된다.
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
    # True면 Root/Child/GP 전부에 `write_todos`가 붙는다.
    # `middleware/factory.py`의 `build()`가 읽는다.
    enable_todo: bool = True
    write_tool_allowed_roles: frozenset[AccountRole] = field(
        default_factory=lambda: DEFAULT_WRITE_TOOL_ALLOWED_ROLES
    )

    # `..._overrides`는 특정 tool_ref만 다른 값을 쓰는 탈출구다. 미리 분류하지 않고,
    # 기본값 때문에 정상 작업이 끊긴 게 확인된 도구만 넣는다.
    mcp_tool_call_timeout_seconds: float = DEFAULT_MCP_TOOL_CALL_TIMEOUT_SECONDS
    mcp_tool_call_timeout_overrides: dict[str, float] = field(default_factory=dict)

    # `executor.py`가 `stream_adapter.stream(max_concurrency=...)`로 넘긴다.
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY

    # GP에는 `agent_versions.max_iterations` 같은 에이전트별 필드가 없어서
    # 이 값이 곧 GP의 실제 상한이다.
    general_purpose_max_model_calls: int = 50
    general_purpose_max_tool_calls: int = 100

    # 설정값이 아무리 커져도 넘지 못하는 전체 상한.
    #
    # tool 상한은 Root/Child에 설정 필드가 없어 이 값이 그대로 실제 상한이 된다.
    # 반면 모델 상한은 `min(agent_versions.max_iterations, ceiling)`이라, DB
    # 기본값(10, `DB/schema.sql` — 2026-08-25 이전에는 6이었다)에 여전히 갇힌다.
    # 실제로 늘리려면 Builder에서 그 에이전트의 max_iterations를 올려야 한다.
    max_model_calls_ceiling: int = 50
    max_tool_calls_ceiling: int = 100

    def timeout_for_mcp_tool(self, tool_ref: str) -> float:
        """이 MCP `tool_ref`에 적용할 timeout(초).

        `mcp_tool_call_timeout_overrides`에 값이 있으면 그 값, 없으면 기본값.
        어느 쪽이든 `MAX_MCP_TOOL_CALL_TIMEOUT_SECONDS`를 넘지 못한다.

        **MCP 도구 전용이다.** 내장 도구는 필요하면 자기 timeout을 직접 갖는다
        (`FilesystemMiddleware`의 `execute`). 호출 측
        (`middleware/tool_timeout.py`)이 MCP일 때만 이 메서드를 부른다.
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

        `account_role`은 역할별 차등 상한을 위해 구조만 열어둔 파라미터다.
        확정된 값이 없어 지금은 역할과 무관하게 동일하게 동작한다.
        """
        return min(requested, self.max_model_calls_ceiling)

    def resolve_tool_call_limit(
        self, *, requested: int | None = None, account_role: AccountRole | None = None
    ) -> int:
        """Root/Child의 tool-call 상한. 사용자 설정 필드가 없으므로 방어선 값 자체를 쓴다.

        `account_role`은 `resolve_model_call_limit`과 같은 이유로 구조만 열어둔
        파라미터다.
        """
        if requested is None:
            return self.max_tool_calls_ceiling
        return min(requested, self.max_tool_calls_ceiling)

    def is_tool_allowed_for_role(self, *, side_effect: bool, account_role: AccountRole) -> bool:
        """부수효과 없는 도구는 항상 허용. 부수효과 있는 도구는 허용 역할만 통과.

        **노출이 아니라 실행만 막는다.** 목록에서 지우면 모델이 그 도구를 아예
        모르게 되어 "그런 기능이 없다"고 답한다. 노출은 `factory.py`의 `build()`가
        역할과 무관하게 항상 하고, `_to_langchain_tool()`의 `_run()`이 실행 직전에
        이 함수로 "왜 안 되는지"를 말로 돌려준다.

        `write_tool_allowed_roles`를 그대로 읽으므로, 배포별로 좁히려면
        `RuntimeCapabilityPolicy(write_tool_allowed_roles=...)`로 생성하면 된다.
        """
        if not side_effect:
            return True
        return account_role in self.write_tool_allowed_roles
