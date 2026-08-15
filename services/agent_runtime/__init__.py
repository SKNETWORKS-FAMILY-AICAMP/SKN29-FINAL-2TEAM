"""Deep Agent 실행 코어의 공개 인터페이스."""

from __future__ import annotations

from typing import TYPE_CHECKING

from services.agent_runtime.context import RuntimeContext
from services.agent_runtime.definitions import (
    AgentDefinition,
    LoadedAgentDefinition,
    SubagentDefinition,
    SubagentReference,
)
from services.agent_runtime.executor import AgentExecutor, validate_execution_target

if TYPE_CHECKING:
    from services.agent_runtime.bootstrap import build_default_executor as build_default_executor

__all__ = [
    "RuntimeContext",
    "AgentDefinition",
    "SubagentDefinition",
    "SubagentReference",
    "LoadedAgentDefinition",
    "AgentExecutor",
    "validate_execution_target",
    "build_default_executor",
]


def __getattr__(name: str):
    """`build_default_executor`만 지연 import한다(PEP 562).

    Python은 이 패키지의 어떤 서브모듈을 import하든(예: `backend/db/agent_platform.py`가
    Deep Agent와 무관하게 `services.agent_runtime.definitions`만 쓸 때도) 이 파일을 먼저
    실행한다. `bootstrap.py`는 `compat/deepagents_v075.py`를 거쳐 `deepagents`를 무조건
    import하므로, 여기서 `bootstrap`을 최상단에서 그대로 import하면 Deep Agent를 전혀
    안 쓰는 코드까지 `deepagents` 설치 여부에 발목 잡힌다 — 2026-08-14 이 문제로 백엔드
    전체가 부팅 실패했다(`deepagents`가 이미지에 없는 상태에서 로그인 API조차 못 뜸).
    `build_default_executor`를 실제로 호출하는 시점(Deep Agent를 진짜 실행하는 시점)에만
    `deepagents`를 요구하도록 여기서 늦춘다.
    """
    if name == "build_default_executor":
        from services.agent_runtime.bootstrap import build_default_executor

        return build_default_executor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
