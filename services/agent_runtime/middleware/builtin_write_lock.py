"""내장 side-effect Tool의 같은 자원 쓰기를 Postgres advisory lock으로 직렬화한다.

정본: `docs/설계 및 구현/3_중간발표 이후/작업기록/Deep_Agents/2026-08-20_02_에이전트_병렬실행_설계.md` §5.2

**막는 경합**: `ProjectTaskRepository.register()`(`backend/db/agent_platform.py`)는
읽고-고쳐-쓰기를 그대로 한다:

1. `SELECT model_id, model_ver FROM proj_know_model`
2. 없으면 `next_short_code()` + `INSERT INTO proj_know_model`
3. `SELECT task_name FROM task WHERE model_id = %s` — **이미 있는 업무 이름**
4. 그 목록에 없는 것만 `INSERT INTO task`

READ COMMITTED에서 같은 프로젝트에 `task_register` 두 개가 겹치면, 둘 다 3번에서
서로의 커밋 안 된 INSERT를 못 보고 같은 이름을 "없다"고 판단해 각자 넣는다 —
4번의 중복 방지가 통째로 샌다. 2번도 `proj_know_model` 행이 두 개 생길 수 있다.
`memory/write_lock.py`와 같은 종류의 문제라 같은 방식으로 막는다.

**MCP 도구는 대상이 아니다.** 그쪽은 직렬화하지 않고 승인 카드에 경고만 띄운다
(`hitl_warnings.py`) — 최대 480초 걸릴 수 있는 호출을 락을 쥔 채 기다리면 대기
호출마다 DB 커넥션을 그만큼 붙잡는다. 내장 도구는 로컬 쓰기라 그 문제가 없다.

**자원 키는 `project_id`다.** 내장 side-effect 도구는 전부 한 프로젝트 밑에서만
쓰고 위 경합도 프로젝트 단위다. 프로젝트가 다르면 공유하는 게 없으므로 병렬로
둔다. `project_id`가 없으면 잠글 대상이 없어 통과시킨다 — 여기서 막으면 도구가
주려던 "프로젝트를 먼저 고르세요"라는 사유가 사라진다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain.agents.middleware.types import AgentMiddleware

from services.agent_runtime.tools.loader import MCP_TOOL_REF_PREFIX, tool_ref_from_model_name

if TYPE_CHECKING:
    from collections.abc import Callable

    from langchain.agents.middleware.types import ToolCallRequest

    from services.agent_runtime.context import RuntimeContext

#: 락을 걸 내장 도구. 지금은 `registry.py`의 `side_effect=True` 목록과 같지만,
#: **목록을 따로 두는 이유는 "부수효과가 있다"와 "같은 자원을 읽고-고쳐-쓴다"가
#: 다른 질문이기 때문**이다. 새 side-effect 도구가 생기면 실제로 경합하는지 보고
#: 여기 넣을지 정한다.
GUARDED_BUILTIN_TOOLS = frozenset({"task_register", "task_update", "jira_create_issues"})


class BuiltinWriteLockMiddleware(AgentMiddleware):
    """같은 `project_id`에 대한 내장 쓰기 도구 호출을 한 번에 하나씩 실행한다.

    실행을 **거부하지 않는다** — 대기시킨다. 앞선 호출이 끝나면 그대로 이어서
    실행된다(설계 문서 §5.2 "직렬화는 실행을 거부하는 것이 아니다").

    Root/Child 둘 다에 붙인다(`middleware/factory.py`) — 어느 쪽이 부르든 같은
    표에 같은 방식으로 쓴다.
    """

    def __init__(
        self,
        *,
        context: "RuntimeContext",
        guarded_tools: frozenset[str] = GUARDED_BUILTIN_TOOLS,
    ) -> None:
        super().__init__()
        self._context = context
        self._guarded_tools = guarded_tools

    def wrap_tool_call(
        self, request: "ToolCallRequest", handler: "Callable[[ToolCallRequest], Any]"
    ) -> Any:
        tool_ref = tool_ref_from_model_name(request.tool_call["name"])
        if tool_ref.startswith(MCP_TOOL_REF_PREFIX) or tool_ref not in self._guarded_tools:
            return handler(request)

        project_id = self._context.project_id
        if not project_id:
            # 잠글 대상이 없다. 도구 자신이 "프로젝트를 먼저 고르세요"로
            # 되돌릴 것이므로 여기서 가로채지 않는다.
            return handler(request)

        # 지연 import — 이 모듈이 항상 DB 연결 의존성을 끌고 들어오지 않게 한다
        # (`memory/write_lock.py`와 같은 이유).
        from backend.db.connection import database_connection

        lock_key = f"builtin-write:{self._context.team_id}:{project_id}"
        with database_connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (lock_key,))
            # handler를 이 락 전용 connection의 `with` 블록 **안에서** 불러야
            # 락을 쥔 채로 실제 쓰기가 끝난다 — 블록을 벗어나야 비로소
            # commit/rollback되며 락이 풀리므로, 여기서 나가기 전에 호출해야
            # 두 번째 동시 호출이 이 호출이 끝날 때까지 대기한다
            # (`memory/write_lock.py`와 같은 구조).
            return handler(request)


def build_builtin_write_lock(*, context: "RuntimeContext") -> BuiltinWriteLockMiddleware:
    return BuiltinWriteLockMiddleware(context=context)


__all__ = [
    "GUARDED_BUILTIN_TOOLS",
    "BuiltinWriteLockMiddleware",
    "build_builtin_write_lock",
]
