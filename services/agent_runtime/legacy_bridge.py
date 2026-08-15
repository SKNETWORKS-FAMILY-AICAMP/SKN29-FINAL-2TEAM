"""레거시 `agent`/`agent_tool`을 새 엔진의 Builder draft 모양으로 옮긴다.

**왜 필요한가**: `services.agent_runtime`(새 엔진)은 저장된 실행을 `agent_id`+
`agent_version_id`(새 `agents`/`agent_versions` 스키마) 또는 순수 `draft` 중
하나로만 받는다(`executor.validate_execution_target()`). 그런데 지금 Chat
화면(frontend)이 만드는 대화는 전부 레거시 `agent` 테이블을 가리킨다
(`_resolve_session_agent()` — 레거시 테이블을 먼저 보고, 있으면
`agent_version_id=None`). Builder 화면·저장 API를 새 스키마로 바꾸는 건
작업자 A 영역(분업 계약 §17)이고 아직 착수 전이다.

이 다리는 그 사이를 잇는다 — **레거시 `agent` 행 하나를 읽어서, 저장 없이**
새 엔진이 이미 지원하는 `AgentDefinitionLoader.from_draft()`가 기대하는 dict
모양으로 바꿔 준다. 새 스키마 테이블(`agents`/`agent_versions`)은 전혀
건드리지 않는다 — 읽기 전용이고, 레거시 `AgentRepository`만 쓴다.
"""

from __future__ import annotations

from typing import Any

from backend.db.agent_platform import AgentRepository
from backend.db.errors import RecordNotFound

from services.agent_runtime.exceptions import AgentDefinitionNotFound


def draft_from_legacy_agent(*, agent_id: str, team_id: str) -> dict[str, Any]:
    """레거시 `agent` 행을 `AgentDefinitionLoader.from_draft()`용 draft로 바꾼다.

    - `instruction` → `system_prompt`(새 엔진의 필드 이름).
    - `model`/`reasoning_effort`가 비어 있으면(NULL) 레거시 harness와 같은
      기본값(`services.harness.runner.DEFAULT_MODEL`/`DEFAULT_EFFORT`)으로
      떨어뜨린다 — 두 엔진이 같은 에이전트를 다른 모델로 돌리면 안 된다.
    - `max_iterations`는 레거시 `agent.max_iterations`를 그대로 쓴다 — 이
      컬럼은 `NOT NULL DEFAULT 10`이라(레거시 마이그레이션) 항상 값이 있다.
      새 스키마(`agent_versions.max_iterations`)의 기본값 6은 여기 쓰지
      않는다 — 서로 다른 기본값이라고 마이그레이션 주석에 명시돼 있다.
    - `subagents`는 항상 빈 목록이다. 레거시 A2A 위임(`agent:<id>` tool_ref,
      `AgentRepository.callable_agents()`)은 새 엔진의
      `agent_version_subagents`/`SubagentDefinition`과 다른 메커니즘이라 여기서
      번역하지 않는다 — 그런 tool_ref가 있으면 `ToolLoader.load()`가
      `ToolUnavailableError`로 명확히 막는다(조용히 빠지지 않음).
    - `draft["agent_id"]`에 실제 `agent_id`를 실어 보낸다 — `from_draft()`가
      이 값을 그대로 `AgentDefinition.agent_id`에 쓴다(2026-08-14 수정).
      `agent_run.agent_id`가 `NOT NULL`이라 이게 없으면 실행 로그 적재가
      깨진다.

    팀이 다르거나 존재하지 않으면 `AgentDefinitionNotFound`(404) — 다른 팀
    에이전트의 존재 자체를 노출하지 않는다(레거시 `_resolve_session_agent()`의
    `PermissionDenied` 처리와 같은 이유로, 여기서는 404로 통일해 새 엔진의
    `HTTP_STATUS_BY_EXCEPTION` 규칙을 그대로 따른다).
    """
    # 지연 import — services.harness는 이 함수가 실제로 불릴 때만 그 무거운
    # 의존성 사슬을 끌고 온다(tools/adapters.py와 같은 이유).
    from services.harness.runner import DEFAULT_EFFORT, DEFAULT_MODEL

    try:
        agent = AgentRepository.get(agent_id)
    except RecordNotFound as exc:
        raise AgentDefinitionNotFound(f"에이전트를 찾을 수 없습니다: {agent_id}") from exc

    if agent["team_id"] != team_id:
        raise AgentDefinitionNotFound(f"에이전트를 찾을 수 없습니다: {agent_id}")

    return {
        "agent_id": agent_id,
        "name": agent["name"],
        "description": agent.get("description") or "",
        "system_prompt": agent["instruction"],
        "model": agent.get("model") or DEFAULT_MODEL,
        "reasoning_effort": agent.get("reasoning_effort") or DEFAULT_EFFORT,
        "max_iterations": agent["max_iterations"],
        "tool_refs": tuple(AgentRepository.tool_refs(agent_id)),
        "subagents": [],
    }


__all__ = ["draft_from_legacy_agent"]
