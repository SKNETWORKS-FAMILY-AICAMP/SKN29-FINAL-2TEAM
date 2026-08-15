"""팀·에이전트 단위로 격리된 장기 메모리 backend를 조립한다."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from deepagents.backends import CompositeBackend

#: 메모리 파일이 사는 경로. 팀·에이전트별 격리는 이 경로 문자열이 아니라
#: Store의 namespace로 한다 — 그래서 모든 에이전트가 똑같은 경로를 쓴다
#: (docs.langchain.com/oss/python/deepagents/memory의 "agent-scoped memory" 예시와 같은 모양).
MEMORY_PATH_PREFIX = "/memories/"
MEMORY_FILE = f"{MEMORY_PATH_PREFIX}AGENTS.md"


def memory_paths() -> list[str]:
    """`create_deep_agent(memory=...)`에 그대로 넘길 경로 목록."""
    return [MEMORY_FILE]


def build_memory_backend(*, team_id: str, agent_id: str) -> "CompositeBackend":
    """`/memories/`만 장기 저장(Store)으로 보내고, 나머지 파일 도구는 그대로
    휘발성 `StateBackend`(deepagents 기본값)로 둔다.

    **에이전트 단위 공유 메모리로 정했다(계정 단위 아님)** — namespace를
    `(team_id, agent_id)`로 고정한다. 이 앱은 팀이 같이 쓰는 업무 도구라
    "이 에이전트가 팀과 함께 배운 것"을 모으는 쪽이 "이 사람만 기억하는 것"보다
    맞다고 판단했다(2026-08-15, 지훈 확인 없이 기본값으로 결정 — 나중에 계정
    단위로 바꾸고 싶으면 아래 namespace 튜플에 `account_id`만 추가하면 된다.
    분리할 이유가 생기면 재검토할 것).
    """
    # 지연 import — deepagents.backends는 deepagents 전체를 끌고 들어온다.
    from deepagents.backends import CompositeBackend, StateBackend, StoreBackend

    def _namespace(_runtime: Any) -> tuple[str, str]:
        # deepagents가 넘기는 runtime 객체(`rt.server_info` 등)는 안 쓴다 —
        # team_id/agent_id는 이 backend를 만드는 시점(요청 단위)에 이미
        # 알고 있어서 클로저로 고정한다.
        return (team_id, agent_id)

    return CompositeBackend(
        default=StateBackend(),
        routes={MEMORY_PATH_PREFIX: StoreBackend(namespace=_namespace)},
    )


__all__ = ["MEMORY_FILE", "MEMORY_PATH_PREFIX", "build_memory_backend", "memory_paths"]
