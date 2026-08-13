"""실행 컨텍스트 — 누가 어떤 환경에서 요청했는지만 표현한다.

정본: docs/작업기록/jihun_buildingpage/2026-08-13_02_Deep-Agent_런타임_공통_계약_v1.md §4

무엇을 실행하는지는 여기 담지 않는다 — 그건 run_agent()의 인자와
AgentDefinition(definitions.py)의 몫이다.

⚠ 02 §20 체크리스트 3번: "RuntimeContext에 agent_version_id가 없다." 여기 필드에
agent_version_id를 추가하지 말 것 — run_agent()와 Context에 같은 값이 이중으로
존재하면 두 값이 서로 달라지는 경로가 생긴다. 이벤트의 agent_id/agent_version_id는
AgentDefinition에서 읽는다(events.py).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeContext:
    account_id: str
    team_id: str

    session_id: str | None = None
    project_id: str | None = None

    run_id: str | None = None
    parent_run_id: str | None = None
