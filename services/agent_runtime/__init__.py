"""Deep Agent의 조립·실행·확장 기능을 모으는 런타임 패키지.

설계 정본:
- docs/작업기록/Deep_Agents/2026-08-13_01_Deep-Agent형_에이전트_빌더_개편_설계.md
- docs/작업기록/Deep_Agents/2026-08-13_02_Deep-Agent_런타임_공통_계약_v1.md
  (구현 계약 정본 — 두 문서가 충돌하면 이 문서가 우선)

⚠ 2026-08-13 착수. 이 패키지는 아직 apps/chat·apps/agents 어디에서도 import되지
않는다 — 지금 Chat/Agent 실행은 여전히 services/harness/를 그대로 쓴다
(apps/chat/api_views.py, apps/agents/api_views.py 참고). 전환 시점은
docs/TO-BE/작업목록.md "2026-08-13 착수" 절에 기록한다.

공개 인터페이스는 최소로 유지한다 — 외부(apps/*)는 아래만 참조하고, 패키지
내부 모듈 경로에 직접 의존하지 않는다. 지금은 대부분이 미구현 스텁이라 실제
export할 게 거의 없다.
"""

from services.agent_runtime.context import RuntimeContext
from services.agent_runtime.definitions import (
    AgentDefinition,
    LoadedAgentDefinition,
    SubagentDefinition,
    SubagentReference,
)
from services.agent_runtime.executor import AgentExecutor, validate_execution_target

__all__ = [
    "RuntimeContext",
    "AgentDefinition",
    "SubagentDefinition",
    "SubagentReference",
    "LoadedAgentDefinition",
    "AgentExecutor",
    "validate_execution_target",
]
