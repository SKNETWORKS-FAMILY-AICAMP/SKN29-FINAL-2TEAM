"""`services.harness.registry.BUILTIN_TOOLS`를 실행 코어 Tool 형식으로 변환한다.

컨텍스트 주입표(`tools/loader.py`의 `CONTEXT_VALUES` 키 기준):

  document_search                          -> team_id, account_id, project_id
  people_list / workload_report /
  project_list / document_list /
  document_sync / absence_list             -> account_id
  task_extraction                          -> project_id, account_id, team_id (+model)
  task_register / task_list / task_update /
  jira_create_issues / jira_get_issues     -> project_id, account_id
  web_search / get_current_datetime         -> (없음 — 요청자·팀과 무관하게 같은 답)
  skill_register                            -> account_id, team_id, account_role
                                               (`_SKILL_REGISTER_REF` 근거 참고)

`proj_id`(레거시 핸들러 키워드) vs `project_id`(CONTEXT_VALUES) — 이름 차이는
이 파일 안(`_wrap_handler`)에서만 흡수한다.

`task_extraction`의 `model`은 그 에이전트가 실제로 고른 모델이다(BYOK 대응) —
`CONTEXT_VALUES`가 아니라 `ToolLoader.load(agent_model=...)`가 따로 넘긴다.

제너레이터 도구(`task_extraction`, `jira_get_issues`)는 진행 이벤트를 yield하다가
`return`으로 최종 값을 준다. `inspect.isgenerator()`로 실행 시점에 감지해
`langgraph.config.get_stream_writer()`로 흘려보낸다.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterator
from typing import Any

from services.agent_runtime.tools.loader import Tool as RuntimeTool
from services.harness.registry import BUILTIN_TOOLS

# 아래 import는 새 의존성 무게를 더하지 않는다 — `harness/registry.py`가 이미
# 최상단에서 같은 것들을 import하므로 위 BUILTIN_TOOLS를 통해 이 프로세스에
# 로드돼 있고, 이 모듈 자체도 loader.py의 지연 import 뒤에서만 로드된다.
from backend.db.agent_platform import AgentRepository, McpServerRepository
from services.mcp import client as mcp_client

# --- 컨텍스트 라우팅표 (services/harness/runner.py의 _injected() 실측 이관) ---

#: 팀 경계와 **요청자**가 둘 다 필요하다. `account_id` 를 빠뜨리면 조용히
#: 반쪽이 된다 — 검색 범위가 팀 문서만이 되어 **「내가 켠 내 파일」과 공유분이
#: 통째로 빠진다**(M④). 오류가 아니라 「문서가 없습니다」로 끝나서 기능이 없는
#: 것처럼 보인다.
#: 레거시 `runner.py` 의 같은 자리에서 옮겨 올 때 함께 빠져 있었다(2026-08-18 QA).
_DOCUMENT_SEARCH_REF = "document_search"
_ACCOUNT_SCOPED: frozenset[str] = frozenset(
    {
        "people_list",
        "workload_report",
        "project_list",
        "document_list",
        "document_sync",
        "absence_list",
        "table_export",
        "document_create",
    }
)
_PROJECT_SCOPED: frozenset[str] = frozenset(
    {"task_register", "task_list", "task_update", "jira_create_issues", "jira_get_issues"}
)
_TASK_EXTRACTION_REF = "task_extraction"

#: 2026-08-21, Skill 배선 — `skill_register`는 프로젝트 스코프가 아니라
#: 계정·팀 스코프다. **2026-08-26 갱신** — `scope`(PERSONAL/TEAM) 인자를
#: 없애면서(정본 "스킬 검증·등록 최종 설계.md" §2/§5) 이 도구만 따로
#: `account_role`을 받던 이유(TEAM인데 leader가 아니면 거부)도 같이
#: 사라졌다. 지금은 항상 개인 스킬 검증 job만 만든다.
_SKILL_REGISTER_REF = "skill_register"

#: 레거시 핸들러의 실제 키워드 인자 이름 — CONTEXT_VALUES 쪽 이름(project_id)과 다르다.
_LEGACY_PROJECT_KWARG = "proj_id"


def _injected_context_names(tool_ref: str) -> tuple[str, ...]:
    """`services.agent_runtime.tools.loader.CONTEXT_VALUES` 키 이름 기준으로 돌려준다."""
    if tool_ref == _TASK_EXTRACTION_REF:
        return ("project_id", "account_id", "team_id")
    if tool_ref == _DOCUMENT_SEARCH_REF:
        # `project_id`는 `_call`이 레거시 이름(`proj_id`)으로 바꿔 넘긴다.
        return ("team_id", "account_id", "project_id")
    if tool_ref in _PROJECT_SCOPED:
        return ("project_id", "account_id")
    if tool_ref == _SKILL_REGISTER_REF:
        # 2026-08-26 — `scope`(PERSONAL/TEAM)를 도구 입력에서 없앴다("스킬
        # 검증·등록 최종 설계.md" §2/§5) — 팀 스킬 직접 등록 경로 자체가
        # 없어져서 `account_role`로 TEAM/leader를 가릴 이유가 사라졌다.
        # 대신 `SkillRegistrationJob.source_session_id`(같은 문서 §9)를
        # 채우려면 `session_id`가 필요하다.
        return ("account_id", "team_id", "session_id")
    if tool_ref in _ACCOUNT_SCOPED:
        return ("account_id",)
    return ()


def _safe_stream_writer() -> Callable[[Any], None]:
    """그래프 실행 컨텍스트 밖에서 불려도 죽지 않는 진행 이벤트 writer.

    `get_stream_writer()`는 실행 중인 그래프 컨텍스트가 없으면 `RuntimeError`를
    낸다 — 그래프 밖에서 단독 호출될 가능성을 막는다.
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
    덮어쓴다 — 서버가 정하는 값이 모델이 보낸 인자에 밀리면 안 된다.
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
    """`services.harness.registry.BUILTIN_TOOLS`(15개)를 실행 코어 `Tool`로 바꾼다.

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
    """호출 직전에 서버·토큰을 다시 읽는다 — 토큰을 Tool 객체에 실어 돌아다니게
    하지 않고, 쓰기 직전에만 꺼낸다.
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

    `side_effect=True`로 고정한다 — MCP `tools/list` 응답에 read/write 구분
    필드가 없어서 모르는 것을 안전한 쪽(승인 필요)으로 가정한다. 어떤 역할이
    실제로 통과하는지는 `runtime_policy.py`의 정책 값을 따른다.

    내장 도구와 달리 팀마다 목록이 달라 매개변수가 필요하다.
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
