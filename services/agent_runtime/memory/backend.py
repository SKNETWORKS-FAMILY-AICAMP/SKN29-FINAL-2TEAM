"""팀·에이전트·계정 단위로 격리된 장기 메모리 backend를 조립한다."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from deepagents.backends import CompositeBackend

#: 메모리 파일이 사는 경로. 팀·에이전트별 격리는 이 경로 문자열이 아니라
#: Store의 namespace로 한다 — 그래서 모든 에이전트가 똑같은 경로를 쓴다
#: (docs.langchain.com/oss/python/deepagents/memory의 "agent-scoped memory" 예시와 같은 모양).
MEMORY_PATH_PREFIX = "/memories/"
MEMORY_FILE = f"{MEMORY_PATH_PREFIX}AGENTS.md"

#: 2026-08-18, Phase 3(§4-8) — 계정 전용(개인) 메모리 route. `MEMORY_PATH_PREFIX`보다
#: 문자열이 길어서 `CompositeBackend`가 이 route를 먼저 매칭한다(routes는 prefix
#: 길이 기준 내림차순으로 정렬돼 매칭된다 — deepagents/backends/composite.py
#: `CompositeBackend.__init__`의 `sorted_routes` 실제 소스로 확인, 순서를 직접
#: 관리할 필요 없음).
MEMORY_USERS_PATH_PREFIX = f"{MEMORY_PATH_PREFIX}users/"

#: MemoryMiddleware의 system_prompt에 이어붙일 라우팅 안내(§4-6). `{agent_memory}`
#: 슬롯은 deepagents 기본 `MEMORY_SYSTEM_PROMPT` 쪽에 이미 있으므로 여기는
#: 순수 안내문만 담는다.
#:
#: 2026-08-18 수정 — `{project_id}`를 `{{project_id}}`로 이스케이프했다.
#: `MemoryMiddleware._format_agent_memory()`(deepagents/middleware/memory.py 실제
#: 소스)는 이 문자열 전체를 `template.format(agent_memory=...)`로 처리한다
#: (Python `str.format()`) — `{agent_memory}` 슬롯만 골라 채우는 게 아니라 문자열에
#: 있는 모든 `{...}`를 format 필드로 취급한다. 이스케이프 없는 `{project_id}`는
#: 값이 채워지지 않는 필드로 잡혀 실제 실행 시 `KeyError: 'project_id'`로
#: 죽는다 — `agent_tool_selection_live_check.py`로 실제
#: `AgentRuntimeFactory.build()` 파이프라인을 처음부터 끝까지 돌려 보다가
#: 재현·확인함(기존 `tests/test_memory_backend.py`는 `MemoryMiddleware(...)` 생성
#: 성공 여부만 확인하고 `_format_agent_memory()`를 실제로 호출해 보지 않아서
#: 이 버그를 못 잡았다).
_MEMORY_ROUTING_PROMPT = """
## Memory routing — decide before you write

1. Is this worth remembering? (Deep Agents' default judgment above already covers this.)
2. Is this SHARED (the whole team/agent should know) or PERSONAL (only this user)?
   - Team rules, project facts, decisions → shared → /memories/AGENTS.md (core, keep short)
     or /memories/projects/{{project_id}}.md (detailed project history)
   - This user's own preferences/habits → personal → /memories/users/preferences.md
3. Classify the content itself as semantic (stable fact) / episodic (event, will be
   superseded) / procedural (behavior rule to keep following) — this only affects
   HOW you phrase and update it, not which file.

Keep /memories/AGENTS.md small — it is injected into every single turn. Put detailed
history in /memories/projects/*.md and read it back with read_file/grep/glob only
when needed.
"""


def memory_paths() -> list[str]:
    """`create_deep_agent(memory=...)`에 그대로 넘길 경로 목록."""
    return [MEMORY_FILE]


def memory_system_prompt() -> str:
    """deepagents 기본 `MEMORY_SYSTEM_PROMPT`에 라우팅 안내(§4-6)를 이어붙인다.

    `MemoryMiddleware.system_prompt`는 `create_deep_agent()`의 공개 파라미터로는
    바꿀 수 없다(`memory=` 목록만 받음 — deepagents==0.7.5 실제 소스,
    `deepagents/graph.py`의 `create_deep_agent` 시그니처로 확인). 대신
    `compat/deepagents_v075.py`의 `create_root_graph(memory_system_prompt=...)`가
    이 값으로 커스텀 `MemoryMiddleware` 인스턴스를 만들어 `middleware=` 목록에
    끼워 넣으면, deepagents가 이름("MemoryMiddleware")이 같은 자동 생성분을
    그 자리에서 치환한다(`_apply_custom_middleware`의 "이름이 같으면 교체" 규칙).
    """
    from deepagents.middleware.memory import MEMORY_SYSTEM_PROMPT

    return MEMORY_SYSTEM_PROMPT + _MEMORY_ROUTING_PROMPT


def build_memory_backend(*, team_id: str, agent_id: str, account_id: str) -> "CompositeBackend":
    """`/memories/`(팀·에이전트 공유)와 `/memories/users/`(계정 전용)를 장기
    저장(Store)으로 보내고, 나머지 파일 도구는 그대로 휘발성 `StateBackend`
    (deepagents 기본값)로 둔다.

    2026-08-15에는 에이전트 단위 공유 메모리만 있었다(계정 분리 없음, namespace
    `(team_id, agent_id)` 고정). 2026-08-18, Phase 3(§4-8)에서 계정 전용
    namespace `(team_id, agent_id, account_id)`를 `/memories/users/` route로
    분리했다 — "이 에이전트가 팀과 함께 배운 것"(공유)과 "이 사람만 기억하는
    것"(개인)을 물리적으로 다른 namespace로 격리해야, 계정 A의 개인 메모리가
    계정 B에게 보이는 사고를 코드 레벨에서 막을 수 있다.
    """
    # 지연 import — deepagents.backends는 deepagents 전체를 끌고 들어온다.
    from deepagents.backends import CompositeBackend, StateBackend, StoreBackend

    def _shared_namespace(_runtime: Any) -> tuple[str, str]:
        # deepagents가 넘기는 runtime 객체(`rt.server_info` 등)는 안 쓴다 —
        # team_id/agent_id는 이 backend를 만드는 시점(요청 단위)에 이미
        # 알고 있어서 클로저로 고정한다.
        return (team_id, agent_id)

    def _personal_namespace(_runtime: Any) -> tuple[str, str, str]:
        return (team_id, agent_id, account_id)

    return CompositeBackend(
        default=StateBackend(),
        routes={
            MEMORY_USERS_PATH_PREFIX: StoreBackend(namespace=_personal_namespace),
            MEMORY_PATH_PREFIX: StoreBackend(namespace=_shared_namespace),
        },
    )


__all__ = [
    "MEMORY_FILE",
    "MEMORY_PATH_PREFIX",
    "MEMORY_USERS_PATH_PREFIX",
    "build_memory_backend",
    "memory_paths",
    "memory_system_prompt",
]
