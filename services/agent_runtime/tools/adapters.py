"""기존 Harness Tool을 실행 코어의 Tool 형식으로 변환한다.

정본: docs/작업기록/Deep_Agents/2026-08-13_02_Deep-Agent_런타임_공통_계약_v1.md §17.1
(원래 작업자 A 담당, 착수 전이라 작업자 B가 대신 작성 — 2026-08-13)

`services.harness.registry.BUILTIN_TOOLS`(13개, AST로 직접 확인 — 아래 각 상수의
근거)를 `services.agent_runtime.tools.loader.Tool`로 바꾼다. 어떤 컨텍스트를
주입할지는 `services/harness/runner.py`의 `_injected()`를 실제로 읽어서 그대로
옮겼다 — 추측이 아니라 실측이다:

  document_search                          -> team_id
  people_list / workload_report /
  project_list / document_list /
  absence_list                             -> account_id
  task_extraction                          -> project_id, account_id, team_id
                                               (+ model — CONTEXT_VALUES가 아니라
                                               아래 별도 설명)
  task_register / task_list / task_update /
  jira_create_issues / jira_get_issues     -> project_id, account_id
  web_search                                -> (없음)

**proj_id 대 project_id**: 레거시 핸들러의 실제 키워드 인자 이름은 `proj_id`다
(services/harness/registry.py 함수 시그니처 AST로 확인, 2026-08-13).
`services.agent_runtime.tools.loader.CONTEXT_VALUES`는 `RuntimeContext.project_id`
필드명을 그대로 쓴다(`project_id`). `CONTEXT_VALUES`에 별칭을 추가하지 않는
이유는 그러면 어느 이름이 정본인지 헷갈리기 때문이다 — 이름 차이는 이 파일
안에서만(`_wrap_handler`) 흡수한다.

**task_extraction의 model**: "부른 에이전트가 실제로 고른 모델로 돈다"(BYOK 팀은
자기 키로 추출까지 돌아야 한다 — registry.py 주석 근거). `RuntimeContext`엔 없는
값이라 `ToolLoader.load(agent_model=...)`가 받아 이 함수로 넘기고, 여기서 핸들러
호출부에 직접 고정한다 — `CONTEXT_VALUES` 메커니즘을 거치지 않는다. 이건 "누가
요청했는가"(컨텍스트)가 아니라 "이 에이전트가 무엇으로 설정됐는가"(에이전트
설정값)라 성격이 다르다.

**제너레이터 도구(task_extraction, jira_get_issues)**: 진행 이벤트를 yield하다가
`return`으로 최종 값을 준다(레거시 `services/harness/runner.py`의 `_drain`/
`_forward`와 같은 모양 — Tool.handler 자체의 계약이다). 특정 두 개로 하드코딩해
분기하지 않고 `inspect.isgenerator()`로 실행 시점에 그대로 감지한다 — 나중에
새 내장 도구가 같은 패턴을 쓰게 되어도 이 파일을 안 고쳐도 된다.

여기서는 진행 이벤트를 버리지 않고 `langgraph.config.get_stream_writer()`로 그대로
흘려보낸다 — 2026-08-13 실제 `deepagents.create_deep_agent()` +
`stream_mode=["updates", "custom"]`로 직접 실행해 확인했다:
  1) `StructuredTool`로 감싼 함수 안에서 호출해도 진행 이벤트가 `mode="custom"`
     으로 정확히 나온다(ToolNode 실행 컨텍스트 안이라 contextvar가 살아 있다).
  2) `stream_mode`에 `"custom"`이 없거나 `.invoke()`만 쓰는 경우에도
     `get_stream_writer()` 호출 자체는 에러 없이 통과한다(no-op).
  3) 다만 그래프 실행 **밖**에서(예: 앞으로 생길 수 있는 "도구 직접 테스트"
     경로) 호출하면 `RuntimeError: Called get_config outside of a runnable
     context`가 난다 — `_safe_stream_writer()`가 그 경우를 조용한 no-op으로
     막는다.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterator
from typing import Any

from services.agent_runtime.tools.loader import Tool as RuntimeTool
from services.harness.registry import BUILTIN_TOOLS

# AgentRepository/McpServerRepository/mcp_client는 이미 위 BUILTIN_TOOLS를 통해
# 이 프로세스에 로드된다 — services/harness/registry.py가 최상단에서
# `from backend.db.agent_platform import (AgentRepository, McpServerRepository,
# ...)`·`from services.mcp import client as mcp_client`를 직접 import한다
# (2026-08-14 확인, registry.py 1~35줄). 그래서 아래 import는 새 의존성
# 무게를 더하지 않는다 — 이 모듈 자체가 loader.py의 지연 import 뒤에서만
# 로드되므로, 정본 위치를 명확히 하는 것 외엔 비용이 없다.
from backend.db.agent_platform import AgentRepository, McpServerRepository
from services.mcp import client as mcp_client

# --- 컨텍스트 라우팅표 (services/harness/runner.py의 _injected() 실측 이관) ---

_TEAM_SCOPED: frozenset[str] = frozenset({"document_search"})
_ACCOUNT_SCOPED: frozenset[str] = frozenset(
    {"people_list", "workload_report", "project_list", "document_list", "absence_list"}
)
_PROJECT_SCOPED: frozenset[str] = frozenset(
    {"task_register", "task_list", "task_update", "jira_create_issues", "jira_get_issues"}
)
_TASK_EXTRACTION_REF = "task_extraction"

#: 레거시 핸들러의 실제 키워드 인자 이름 — CONTEXT_VALUES 쪽 이름(project_id)과 다르다.
_LEGACY_PROJECT_KWARG = "proj_id"


def _injected_context_names(tool_ref: str) -> tuple[str, ...]:
    """`services.agent_runtime.tools.loader.CONTEXT_VALUES` 키 이름 기준으로 돌려준다."""
    if tool_ref == _TASK_EXTRACTION_REF:
        return ("project_id", "account_id", "team_id")
    if tool_ref in _TEAM_SCOPED:
        return ("team_id",)
    if tool_ref in _PROJECT_SCOPED:
        return ("project_id", "account_id")
    if tool_ref in _ACCOUNT_SCOPED:
        return ("account_id",)
    return ()


def _safe_stream_writer() -> Callable[[Any], None]:
    """그래프 실행 컨텍스트 밖에서 불려도 죽지 않는 진행 이벤트 writer.

    `get_stream_writer()`는 실행 중인 그래프 컨텍스트가 없으면
    `RuntimeError: Called get_config outside of a runnable context`를 낸다
    (2026-08-13 직접 실행으로 확인). 도구 핸들러가 그래프 밖에서 단독으로
    불릴 가능성(예: 앞으로 생길 도구 직접 테스트 경로)을 막아 둔다.
    """
    from langgraph.config import get_stream_writer

    try:
        return get_stream_writer()
    except RuntimeError:
        return lambda _event: None


def _drain_with_progress(events: Iterator[dict[str, Any]], *, tool_ref: str) -> Any:
    """레거시 runner.py의 `_drain`/`_forward`와 같은 모양이지만, 버리지 않고
    `get_stream_writer()`로 흘려보낸다."""
    writer = _safe_stream_writer()
    try:
        while True:
            event = next(events)
            writer({**event, "tool_ref": tool_ref})
    except StopIteration as stop:
        return stop.value


def _wrap_handler(
    handler: Callable[..., Any], *, tool_ref: str, static_kwargs: dict[str, Any]
) -> Callable[..., Any]:
    """CONTEXT_VALUES 이름 -> 레거시 키워드 이름으로 옮기고, 제너레이터면 drain한다.

    `static_kwargs`(예: task_extraction의 `model`)는 호출자가 준 값을 항상
    덮어쓴다 — 서버가 정하는 값이 모델이 보낸 인자에 밀려서는 안 된다는 이
    저장소의 일관된 원칙(runner.py `_injected` 주석)과 같다.
    """

    def _call(**kwargs: Any) -> Any:
        resolved = dict(kwargs)
        if "project_id" in resolved:
            resolved[_LEGACY_PROJECT_KWARG] = resolved.pop("project_id")
        resolved.update(static_kwargs)

        raw = handler(**resolved)
        if inspect.isgenerator(raw):
            return _drain_with_progress(raw, tool_ref=tool_ref)
        return raw

    return _call


def adapt_builtin_tools(*, agent_model: str | None = None) -> tuple[RuntimeTool, ...]:
    """`services.harness.registry.BUILTIN_TOOLS`(13개)를 실행 코어 `Tool`로 바꾼다.

    `agent_model`은 `task_extraction`에만 쓰인다(위 모듈 docstring 참고) — 다른
    도구는 이 값을 무시한다.
    """
    tools: list[RuntimeTool] = []
    for ref, legacy_tool in BUILTIN_TOOLS.items():
        static_kwargs: dict[str, Any] = {}
        if ref == _TASK_EXTRACTION_REF:
            static_kwargs["model"] = agent_model

        tools.append(
            RuntimeTool(
                ref=legacy_tool.ref,
                name=legacy_tool.name,
                description=legacy_tool.description,
                input_schema=legacy_tool.input_schema,
                handler=_wrap_handler(legacy_tool.handler, tool_ref=ref, static_kwargs=static_kwargs),
                side_effect=legacy_tool.side_effect,
                injected_context=_injected_context_names(ref),
            )
        )
    return tuple(tools)


def _mcp_handler(tool_ref: str) -> Callable[..., Any]:
    """호출 직전에 서버·토큰을 다시 읽는다.

    `services.harness.registry._mcp_tool()`과 같은 이유다 — 토큰을 Tool
    객체에 실어 Loop 안을 돌아다니게 하지 않고, 쓰기 직전에만 꺼낸다(§4-2).
    """

    def handler(*, team_id: str, **arguments: Any) -> dict[str, Any]:
        server = McpServerRepository.credentials_for_tool(tool_ref, team_id=team_id)
        return mcp_client.call_tool(
            endpoint_url=server["endpoint_url"],
            auth_token=server["auth_token"],
            name=server["tool_name"],
            arguments=arguments,
        )

    return handler


def adapt_mcp_tools(*, team_id: str) -> tuple[RuntimeTool, ...]:
    """팀이 등록하고 켜 둔 MCP 도구를 실행 코어 Tool로 바꾼다(2026-08-14 연결).

    `services.harness.registry._mcp_tool()`과 같은 근거로 `side_effect=True`를
    고정한다 — MCP `tools/list` 응답에 read/write를 구분하는 필드가 없어서,
    모르는 것을 안전한 쪽(팀장만 실행 가능·승인 필요, runtime_policy.py의
    write_tool_allowed_roles)으로 가정한다.

    내장 도구와 달리 팀마다 목록이 달라 매개변수가 필요하다 — 이 함수는
    `ToolLoader.load()`가 요청된 tool_refs 중 `mcp:` 접두사가 있을 때만
    부른다(tools/loader.py — 불필요한 DB 왕복을 피하려고).
    """
    tools: list[RuntimeTool] = []
    for row in AgentRepository.mcp_tools(team_id):
        tool_ref = row["tool_ref"]
        tools.append(
            RuntimeTool(
                ref=tool_ref,
                name=row["name"],
                description=row.get("description") or "",
                input_schema=row.get("input_schema") or {"type": "object", "properties": {}},
                handler=_mcp_handler(tool_ref),
                side_effect=True,
                injected_context=("team_id",),
            )
        )
    return tuple(tools)


__all__ = ["adapt_builtin_tools", "adapt_mcp_tools"]
