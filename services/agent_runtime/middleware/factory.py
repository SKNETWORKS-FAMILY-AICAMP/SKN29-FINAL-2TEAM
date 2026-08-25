"""호출 상한 정책을 LangChain Middleware로 변환한다."""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    PIIMiddleware,
    TodoListMiddleware,
    ToolCallLimitMiddleware,
)
from langchain.agents.middleware.todo import WRITE_TODOS_TOOL_DESCRIPTION

from services.agent_runtime.middleware.builtin_write_lock import build_builtin_write_lock
from services.agent_runtime.middleware.tool_timeout import build_mcp_tool_call_timeout_middleware

if TYPE_CHECKING:
    from services.agent_runtime.context import RuntimeContext
    from services.agent_runtime.definitions import AgentDefinition
    from services.agent_runtime.runtime_policy import RuntimeCapabilityPolicy

#: 2026-08-24, PIIMiddleware 도입 — 탐지 대상은 `credit_card`/`ip`/
#: `mac_address` 세 가지만 켠다. `email`/`url`은 뺀다(요청에 따른 결정 —
#: 이 프로젝트 채팅에는 정상 업무 메일 주소·문서 링크가 늘 섞여 있어, 이
#: 둘까지 켜면 오탐이 훨씬 잦다). `PIIMiddleware`는 langchain 실측 결과
#: **타입 하나당 인스턴스 하나**라 여러 개를 리스트로 묶어 만든다
#: (`langchain/agents/middleware/pii.py` `__init__` — `pii_type`이 단일
#: 값만 받는다). 흐름은 `docs/설계 및 구현/3_중간발표 이후/작업기록/Jihun_Deep_Agents/13_7단계_05_미들웨어_조립.md`,
#: 세부 설계는 `docs/설계 및 구현/3_중간발표 이후/작업기록/Deep_Agents/2026-08-18_06_미들웨어_전체_설계_정리.md`.
_PII_TYPES: tuple[str, ...] = ("credit_card", "ip", "mac_address")


def _build_pii_middleware() -> list[PIIMiddleware]:
    """`_PII_TYPES` 각각을 `redact` 전략으로 감지하는 미들웨어 목록.

    `apply_to_input`은 기본값(`True`) 그대로 둔다 — 사용자가 채팅에 직접
    입력한 내용만 본다. `apply_to_output`/`apply_to_tool_results`는 켜지
    않는다(기본값 `False`) — 모델 답변·도구 결과까지 검사 범위를 넓히는
    것은 이번 요청 범위 밖이라, 필요해지면 그때 다시 판단한다.
    """

    return [PIIMiddleware(pii_type, strategy="redact") for pii_type in _PII_TYPES]

#: LangChain 기본 `WRITE_TODOS_TOOL_DESCRIPTION`(언제 쓸지/말지가 이미 잘 짜여
#: 있어 그대로 유지)에 이 프로젝트 전용 구분 문단만 덧붙인다. `write_todos`와
#: `task_register`/`task_update`가 이름·개념이 겹쳐 모델이 헷갈리는 걸 막는다.
#:
#: 구분 기준은 **"팀에 보이는가"**지 수명이 아니다. `write_todos`의 `todos`
#: 상태(`PlanningState`)도 다른 상태 필드처럼 Checkpointer가 저장하므로 같은
#: 세션 안에서는 다음 턴에도 남는다. 차이는 그 내용이 세션 상태에만 있고 팀
#: 전체가 보는 DB 데이터로는 옮겨지지 않는다는 점이다.
_TODO_TOOL_DESCRIPTION = (
    WRITE_TODOS_TOOL_DESCRIPTION
    + """
## Distinct from task_register / task_update
This tool tracks your own step-by-step execution plan for this conversation — it may carry over between turns in the same conversation, but it is never visible to teammates and is not a recorded team task. To create or update a real team task that teammates can see, use `task_register` / `task_update` instead. Never treat a write_todos item as a recorded team task, and never treat a task_register/task_update item as merely your own scratch plan.
"""
)


class MiddlewareFactory:
    """Root/Child/GeneralPurpose에 붙일 Middleware 목록을 조립한다.

    **여기서 조립하지 않는 것들.** `create_deep_agent()`가 이미 자동으로 붙이므로
    다시 만들면 중복·오작동한다(`deepagents==0.7.5`의 `graph.py` 기준):

    - `PatchToolCallsMiddleware` — Base stack에 무조건 추가된다.
    - `SummarizationMiddleware` — 무조건 추가된다. deepagents 자체 버전이라
      langchain의 동명 클래스와 다르다.
    - `SubAgentMiddleware` — `create_root_graph()`가 항상 비어 있지 않은
      `subagents`를 넘기므로 이미 켜져 있다. `backend`/`inline_subagents`/
      `state_schema`/`private_state_keys` 내부 배선은 deepagents만 정확히
      만들 수 있어 별도 인스턴스를 만드는 게 특히 위험하다.

    Memory도 여기가 아니라 `factory.py`의 `build()`가
    `create_root_graph(memory=..., backend=..., store=...)`로 배선한다 —
    `MemoryMiddleware`는 `memory=`만 넘기면 자동으로 붙는다.

    `_ToolExclusionMiddleware`는 `bootstrap.py`가
    `register_default_harness_profile(excluded_tools=...)`로 배선한다.
    """

    def __init__(self, *, runtime_policy: "RuntimeCapabilityPolicy") -> None:
        self.runtime_policy = runtime_policy

    def build(self, *, definition: "AgentDefinition", context: "RuntimeContext | None") -> list:
        """Root 또는 Child의 모델·Tool 호출 상한을 만든다.

        `context`가 있으면 그 `account_role`을 정책 조회에 함께 넘긴다
        (`runtime_policy.py`의 `resolve_model_call_limit` docstring 참고).
        `context=None`도 지원한다 — GP 경로와 테스트가 그렇게 부른다.
        """
        account_role = context.role if context is not None else None
        middleware: list = [
            ModelCallLimitMiddleware(
                run_limit=self.runtime_policy.resolve_model_call_limit(
                    requested=definition.max_iterations,
                    account_role=account_role,
                ),
                exit_behavior="error",
            ),
            ToolCallLimitMiddleware(
                run_limit=self.runtime_policy.resolve_tool_call_limit(account_role=account_role),
                exit_behavior="error",
            ),
            # 2026-08-24 — PIIMiddleware. Root/Child 둘 다 이 build()를
            # 거치므로 여기 한 곳이면 양쪽에 다 적용된다(위 `_build_pii_middleware`
            # 주석 참고). GP는 별도 build_for_general_purpose()를 쓰므로 아직
            # 안 붙는다 — GP가 사용자 원문을 직접 보는 경로가 생기면 그때
            # 같은 줄을 추가한다.
            *_build_pii_middleware(),
        ]
        if self.runtime_policy.enable_todo:
            # `system_prompt`를 넘기지 않아 LangChain 기본
            # `WRITE_TODOS_SYSTEM_PROMPT`가 그대로 쓰이게 둔다. "언제 write_todos를
            # 쓸지"(다단계 작업에만, 완료 즉시 표시 등)는 `RUNTIME_SCAFFOLD`에
            # 없는 내용이라 겹치지 않는다.
            middleware.append(TodoListMiddleware(tool_description=_TODO_TOOL_DESCRIPTION))
        # MCP 도구에는 timeout 개념이 없어서 우리가 건다
        # (`2026-08-21_01_Tool_timeout_재설계.md`). Root/Child 둘 다 이 `build()`를
        # 거치므로 여기 한 곳이면 양쪽에 적용된다. 내장 도구는 이 미들웨어가
        # MCP 접두사 검사로 스스로 건너뛴다.
        middleware.append(
            build_mcp_tool_call_timeout_middleware(
                runtime_policy=self.runtime_policy, context=context
            )
        )
        # 같은 프로젝트에 대한 내장 쓰기 도구 호출을 직렬화한다(경합 지점은
        # `builtin_write_lock.py` 모듈 docstring).
        #
        # **timeout 미들웨어보다 뒤(=안쪽)에 둔다.** langchain의 `wrap_tool_call`
        # 체이닝은 목록 앞쪽이 바깥쪽이라, 이 순서라야 "락을 쥔 채 timeout을
        # 기다리는" 조합이 안 생긴다.
        #
        # `context`가 없으면 잠글 팀·프로젝트를 특정할 수 없어 건너뛴다.
        if context is not None:
            middleware.append(build_builtin_write_lock(context=context))
        return middleware

    def build_for_general_purpose(self) -> list:
        """general-purpose의 모델·Tool 호출 상한을 만든다.

        **MCP timeout 미들웨어를 여기엔 안 붙인다.** GP는 `side_effect=False`
        도구만 물려받는데(`factory.py`의 `gp_read_only_tools`) MCP 도구는
        `tools/adapters.py`가 전부 `side_effect=True`로 고정하므로, GP에는 MCP
        도구가 하나도 안 들어간다 — 붙여 봐야 죽은 미들웨어다. GP가 MCP를 쓰게
        되면 그때 `build()`와 같은 줄을 추가하면 된다.
        """
        limits = self.runtime_policy.limits_for_general_purpose()
        return [
            ModelCallLimitMiddleware(run_limit=limits.max_model_calls, exit_behavior="error"),
            ToolCallLimitMiddleware(run_limit=limits.max_tool_calls, exit_behavior="error"),
        ]
