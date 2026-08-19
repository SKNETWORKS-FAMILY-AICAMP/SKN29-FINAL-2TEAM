"""`/memories/users/`(StoreBackend) 쓰기를 Postgres advisory lock으로 직렬화한다.

정본: `docs/작업기록/Deep_Agents/2026-08-19_01_실행_안정성_설계.md` §4
("병렬 Tool 호출의 동시 쓰기"). 실제 설치된 `deepagents==0.7.5`의
`StoreBackend.write()`/`edit()`(`deepagents/backends/store.py` 실제
소스로 확인)는 `store.get()`으로 읽고 → 파이썬에서 새 내용을 계산하고 →
`store.put()`으로 쓰는 읽기-수정-쓰기를 그대로 한다 — 락도 버전 체크(CAS)도
없다. `ToolNode`가 한 super-step 안의 여러 tool_call을 스레드풀로 동시에
실행하는 것까지 겹치면, 같은 파일을 두 `edit_file`이 동시에 건드릴 때
나중에 `put()`한 쪽이 먼저 쓴 내용을 조용히 덮어쓴다 — "기다린다"가 아니라
"진다"에 가깝다. Postgres `store` 테이블 자체에도 버전 컬럼이 없어
낙관적 동시성 제어를 얹을 자리가 없고, deepagents를 patch하는 건 이
프로젝트 원칙(근거 없는 vendored 코드 수정 금지)에 어긋나 프레임워크
밖에서 직렬화한다.

**적용 범위**: `StateBackend`(그 외 모든 파일 경로)는 대상이 아니다 —
그래프 State는 LangGraph 자신이 super-step 끝에 한 번에 반영해서, 여기서
겨냥하는 `StoreBackend.put()` 경쟁과는 다른 메커니즘이다. 지금 이
프로젝트에 남은 StoreBackend 경로는 `/memories/users/` 하나뿐이다
(`memory/backend.py` 모듈 docstring — 팀 공유 메모리 제거 이후).
`guarded_prefix`를 넘기면 그 기준으로 바뀐다(`write_guard.py`와 같은
패턴).

`delete`도 대상에 포함한다(설계 문서 §4의 명시적 언급) — 지금은
`runtime_policy.DEFAULT_EXCLUDED_BUILTIN_TOOLS`가 `delete` 자체를 아예
노출하지 않아 사실상 호출될 일이 없지만, `_to_langchain_tool`의 역할
재검사(factory.py)와 같은 이유로 그 정책이 나중에 바뀌어도 안전하도록
남겨 둔다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from deepagents.backends.utils import validate_path
from langchain.agents.middleware.types import AgentMiddleware

from services.agent_runtime.memory.backend import MEMORY_USERS_PATH_PREFIX

if TYPE_CHECKING:
    from collections.abc import Callable

    from langchain.agents.middleware.types import ToolCallRequest

#: 락을 걸 대상 도구. read_file/ls 등 조회 도구는 아무것도 안 바꾸므로 대상이
#: 아니다.
_GUARDED_TOOLS = {"write_file", "edit_file", "delete"}


class MemoryWriteLockMiddleware(AgentMiddleware):
    """`namespace`+`file_path`로 Postgres advisory transaction lock을 잡고
    실제 handler를 부른다.

    `pg_advisory_xact_lock(hashtext(...))`는 이 저장소가 이미 쓰는 패턴을
    그대로 재사용한다(`backend/db/codes.py::next_short_code`). 같은
    트랜잭션 안에서 잡는 락이라 handler가 끝나면(성공이든 예외든) 이 락
    전용 연결이 commit/rollback되며 트랜잭션이 끝나 락도 함께 풀린다 —
    별도 해제 로직이 필요 없다.

    Root에만 붙인다 — `write_guard.py`와 같은 이유(Child는 진짜
    `StoreBackend`가 없어 `/memories/users/`에 뭘 써도 실제 저장이 안
    된다, `memory/backend.py` 모듈 docstring 참고). 배선은 `factory.py`의
    `memory_provider is not None` 분기.
    """

    def __init__(
        self,
        *,
        namespace: tuple[str, str, str],
        guarded_prefix: str = MEMORY_USERS_PATH_PREFIX,
    ) -> None:
        super().__init__()
        self._namespace = namespace
        self._guarded_prefix = guarded_prefix

    def wrap_tool_call(
        self, request: "ToolCallRequest", handler: "Callable[[ToolCallRequest], Any]"
    ) -> Any:
        name = request.tool_call["name"]
        if name not in _GUARDED_TOOLS:
            return handler(request)

        args = request.tool_call["args"]
        raw_path = args.get("file_path", "")
        try:
            # `write_guard.py`와 같은 이유로 같은 정규화 함수를 재사용한다 —
            # 표기만 다르고 실제로는 guarded_prefix로 떨어지는 경로
            # (`"memories/users/..."`, `"/memories//users/..."` 등)를
            # 놓치지 않기 위해서다.
            normalized_path = validate_path(raw_path)
        except ValueError:
            # 경로 자체가 무효하면 이 미들웨어의 관심사가 아니다 — 도구
            # 본문이 어차피 같은 오류를 낼 것이므로 그대로 넘긴다.
            return handler(request)

        if not normalized_path.startswith(self._guarded_prefix):
            return handler(request)

        # 지연 import — 이 모듈이 항상 DB 연결 의존성을 끌고 들어오지 않게 한다
        # (write_guard.py에는 없는 의존성이라 더더욱 top-level에 안 둔다).
        from backend.db.connection import database_connection

        lock_key = "memory-write:" + ":".join((*self._namespace, normalized_path))
        with database_connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (lock_key,))
            # handler를 이 락 전용 connection의 `with` 블록 **안에서** 불러야
            # 락을 쥔 채로 실제 쓰기가 끝난다 — 블록을 벗어나야 비로소
            # commit/rollback되어 락이 풀리므로, 여기서 나가기 전에 호출해야
            # 두 번째 동시 호출이 이 호출이 끝날 때까지 대기한다.
            return handler(request)


def build_memory_write_lock(
    *, namespace: tuple[str, str, str], guarded_prefix: str = MEMORY_USERS_PATH_PREFIX
) -> MemoryWriteLockMiddleware:
    return MemoryWriteLockMiddleware(namespace=namespace, guarded_prefix=guarded_prefix)


__all__ = ["MemoryWriteLockMiddleware", "build_memory_write_lock"]
