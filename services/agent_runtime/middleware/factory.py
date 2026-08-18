"""호출 상한 정책을 LangChain Middleware로 변환한다."""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain.agents.middleware import ModelCallLimitMiddleware, TodoListMiddleware, ToolCallLimitMiddleware
from langchain.agents.middleware.todo import WRITE_TODOS_TOOL_DESCRIPTION

if TYPE_CHECKING:
    from services.agent_runtime.context import RuntimeContext
    from services.agent_runtime.definitions import AgentDefinition
    from services.agent_runtime.runtime_policy import RuntimeCapabilityPolicy

#: 2026-08-18, Phase 4(§2 "TodoListMiddleware 상세") — LangChain 기본
#: `WRITE_TODOS_TOOL_DESCRIPTION`(3873자, 언제/언제 쓰지 말지는 이미 잘 짜여
#: 있어 그대로 유지)에 이 프로젝트 전용 구분 문단만 추가한다. 목적은 이 앱의
#: `task_register`/`task_update`(DB에 실제로 남는 팀 작업)와 `write_todos`가
#: 이름·개념이 겹쳐 모델이 헷갈리는 걸 막는 것.
#:
#: 2026-08-18 정정: 이 문단이 원래 "실행이 끝나면 사라지고"라고 적었는데,
#: 이건 §5 Phase 1(Checkpointer) 완료 시점의 실제 검증 결과와 안 맞는
#: 얘기였다 — Phase 1의 완료 조건 자체가 "같은 thread_id로 두 번 연속
#: 호출했을 때 Todo 상태가 다음 턴에 유지되는지"였고 그게 통과했다(§5 Phase 1).
#: 즉 `write_todos`의 `todos` 상태(`langchain.agents.middleware.todo.
#: PlanningState`, `AgentState`를 상속)는 다른 상태 필드와 똑같이
#: Checkpointer가 통째로 저장하므로, 같은 세션(thread) 안에서는 다음 턴에도
#: 그대로 남는다 — "실행이 끝나면 사라진다"는 틀린 말이다. 맞는 구분은
#: "팀에 안 보이는가" 여부다: `write_todos`는 이 세션 상태에만 있고(팀
#: 전체가 보는 `task_register`/`task_update` 데이터로 옮겨지지 않는다),
#: `task_register`/`task_update`는 DB에 남아 팀원 전체가 본다. 아래 문단은
#: 그 근거로 다시 썼다.
_TODO_TOOL_DESCRIPTION = (
    WRITE_TODOS_TOOL_DESCRIPTION
    + """
## Distinct from task_register / task_update
This tool tracks your own step-by-step execution plan for this conversation — it may carry over between turns in the same conversation, but it is never visible to teammates and is not a recorded team task. To create or update a real team task that teammates can see, use `task_register` / `task_update` instead. Never treat a write_todos item as a recorded team task, and never treat a task_register/task_update item as merely your own scratch plan.
"""
)


class MiddlewareFactory:
    """Root/Child/GeneralPurpose에 붙일 Middleware 목록을 조립한다.

    2026-08-14: `TodoListMiddleware` 조건부 배선을 시도했다가 계약 문서
    (`2026-08-13_02_Deep-Agent_런타임_공통_계약_v1.md` §2 확정 원칙 8번 — "서비스
    전용 커스텀 Middleware, Memory, TODO, Checkpointer는 MVP에서 비활성화한다")와
    충돌한다는 걸 뒤늦게 발견해 되돌렸다. 그때 사용자 확인: Todo/Memory/Checkpointer는
    지금 전부 뒤로 미룬다 — `runtime_policy.enable_todo`는 계약이 말하는 "확장
    위치"로만 남고(값은 있지만 여기서 읽지 않음).

    **2026-08-15: Memory만 이 결정을 뒤집었다** — 지훈 확인 후 장기 메모리 착수
    (`services/agent_runtime/memory/`, `docs/작업기록/Deep_Agents/2026-08-15_02_장기메모리_설계.md`).
    Memory는 여기(커스텀 middleware 리스트)가 아니라 `factory.py`의 `build()`가
    `create_root_graph(memory=..., backend=..., store=...)`로 별도 배선한다 —
    deepagents의 `MemoryMiddleware`는 `memory=`를 넘기면 자동으로 붙는 내장
    middleware라 여기서 조립할 필요가 없다.

    **2026-08-18, §5 Phase 1 — Checkpointer도 뒤집었다**(`checkpoint/`, `factory.py`/
    `bootstrap.py`). **같은 날 §5 Phase 4 — Todo도 뒤집었다**: `runtime_policy.
    enable_todo`가 여기서 실제로 읽힌다(아래 `build()`). 기본값은 여전히 `False`라
    아무 것도 안 켜진 배포에서는 이전과 동일하게 동작한다 — `RuntimeCapabilityPolicy
    (enable_todo=True)`를 명시적으로 넘겨야 켜진다. `TodoListMiddleware`는
    deepagents가 아니라 langchain 쪽 미들웨어라(`langchain.agents.middleware`)
    Memory/Checkpointer 같은 "자동 부착" 충돌 위험이 없다 — 여기 커스텀 목록에
    그냥 추가하면 된다.

    **2026-08-18, Phase 2 정찰 — 여기서 새로 안 만드는 것들**: 설치된
    `deepagents==0.7.5`의 실제 소스(`deepagents/graph.py`)를 직접 읽어 확인한
    결과, 아래 셋은 `create_deep_agent()`가 이미 자동으로 붙인다 — 여기서
    다시 만들면 중복/오작동:

    - `PatchToolCallsMiddleware()` — Base stack에 무조건 추가됨.
    - `SummarizationMiddleware`(deepagents 자체 버전, `create_summarization_middleware`
      경유) — 마찬가지로 무조건 추가됨. langchain의 동명 미들웨어와는 다른
      클래스이므로 혼동 주의.
    - `SubAgentMiddleware` — `create_root_graph()`가 항상 `subagents=[gp_spec,
      *compiled_children]`(비어있지 않음)을 넘기므로 이미 켜져 있다.
      `backend`/`inline_subagents`/`state_schema`/`private_state_keys` 내부
      배선은 deepagents 자신만 정확히 만들 수 있어, 여기서 별도 인스턴스를
      또 만드는 건 특히 위험하다.

    `_ToolExclusionMiddleware`는 `bootstrap.py`가 `register_default_harness_profile
    (excluded_tools=policy.excluded_builtin_tools)`로 이미 배선돼 있다 — 값은
    `runtime_policy.DEFAULT_EXCLUDED_BUILTIN_TOOLS = frozenset({"delete"})`
    그대로 유지(2026-08-18 확인: `tests/test_runtime_policy.py`의
    `test_does_not_exclude_execute`가 이미 "execute는 SandboxBackend 없이는
    존재하지 않는 도구라 제외할 필요 없다"는 근거로, 지훈이 확인해준 현재 값이
    맞다고 못박아 둔 상태 — 계획서 초안 문구(`{"delete","execute"}`)는 그
    이후 갱신되지 않은 것으로 보고, 기존 결정을 유지한다).
    """

    def __init__(self, *, runtime_policy: "RuntimeCapabilityPolicy") -> None:
        self.runtime_policy = runtime_policy

    def build(self, *, definition: "AgentDefinition", context: "RuntimeContext | None") -> list:
        """Root 또는 Child의 모델·Tool 호출 상한을 만든다.

        `context`가 있으면 그 `account_role`을 정책 조회에 함께 넘긴다(2026-08-18,
        Phase 2 — 역할별 차등 상한의 구조만 열어두는 작업, `runtime_policy.py`의
        `resolve_model_call_limit`/`resolve_tool_call_limit` docstring 참고).
        `context=None`도 계속 지원한다 — 기존 호출부(GP 경로 등)와 테스트가
        이미 그렇게 부른다.
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
        ]
        if self.runtime_policy.enable_todo:
            # 2026-08-18 정정: `system_prompt=""`로 LangChain 기본
            # `WRITE_TODOS_SYSTEM_PROMPT`(1370자)를 지웠던 걸 되돌린다.
            # 처음엔 "`RuntimePromptAssembler`가 이미 조립하는 프롬프트와
            # 중복"이라고 적었는데, 실제로 `RUNTIME_SCAFFOLD`
            # (services/agent_runtime/prompts.py)를 읽어 확인하니 겹치는
            # 내용이 하나도 없었다 — "언제 write_todos를 쓸지"(복잡한
            # 다단계 작업에만, 완료 즉시 표시, 마지막 답은 write_todos
            # 호출과 같은 턴에 쓰지 않기 등)는 RUNTIME_SCAFFOLD 어디에도
            # 없는 내용이다. 근거 없이 실제 제품이 검증한 기본 안내문을
            # 지웠던 것이므로, 인자를 아예 안 넘겨서 LangChain 기본값
            # 그대로 쓰이게 한다.
            middleware.append(TodoListMiddleware(tool_description=_TODO_TOOL_DESCRIPTION))
        return middleware

    def build_for_general_purpose(self) -> list:
        """general-purpose의 모델·Tool 호출 상한을 만든다."""
        limits = self.runtime_policy.limits_for_general_purpose()
        return [
            ModelCallLimitMiddleware(run_limit=limits.max_model_calls, exit_behavior="error"),
            ToolCallLimitMiddleware(run_limit=limits.max_tool_calls, exit_behavior="error"),
        ]
