"""deepagents==0.7.5 전용 그래프 조립 함수."""

from __future__ import annotations

from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from deepagents import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    create_deep_agent,
    register_harness_profile,
)
from deepagents.middleware.subagents import GENERAL_PURPOSE_SUBAGENT

SUPPORTED_VERSION = "0.7.5"

# 서브 에이전트 위임 Tool 이름.
DELEGATION_TOOL_NAME = "task"


def assert_supported_version() -> None:
    """설치된 deepagents 버전이 검증된 버전과 다르면 부팅을 막는다."""
    try:
        installed = version("deepagents")
    except PackageNotFoundError as exc:
        raise RuntimeError("deepagents가 설치되어 있지 않습니다.") from exc

    if installed != SUPPORTED_VERSION:
        raise RuntimeError(
            f"이 모듈은 deepagents=={SUPPORTED_VERSION} 기준으로 검증됐습니다. "
            f"현재 설치된 버전: {installed}. compat/deepagents_v075.py의 조립 규칙을 "
            "새 버전 소스로 다시 확인한 뒤 SUPPORTED_VERSION을 올리세요."
        )


def register_default_harness_profile(
    *,
    model_key: str,
    excluded_tools: frozenset[str] = frozenset(),
) -> None:
    """자동 general-purpose 삽입을 끄는 프로필을 등록한다."""
    register_harness_profile(
        model_key,
        HarnessProfile(
            general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
            excluded_tools=excluded_tools,
        ),
    )


def default_general_purpose_prompt() -> str:
    """deepagents가 내장한 general-purpose 서브 에이전트의 기본 system_prompt.

    `services.agent_runtime.prompts.RuntimePromptAssembler.assemble_general_purpose()`가
    이 값 위에 팀 공통 Scaffold를 붙인다 — deepagents 쪽 값을 아는 건 이 compat
    모듈의 책임이고(파일 docstring: deepagents 버전 차이를 격리하는 곳), 그 위에
    무엇을 더 붙일지는 `prompts.py`의 책임이라 여기서는 값만 꺼내 준다.
    """
    return GENERAL_PURPOSE_SUBAGENT["system_prompt"]


def build_general_purpose_spec(
    *,
    middleware: Sequence[Any] = (),
    system_prompt: str | None = None,
) -> dict[str, Any]:
    """Root에 명시적으로 연결할 general-purpose 설정을 만든다.

    `system_prompt`를 넘기면 deepagents 기본값 대신 그 값을 쓴다 — Factory가
    `RuntimePromptAssembler.assemble_general_purpose()`로 조립한 값을 넘긴다.
    안 넘기면(`None`) deepagents 기본값을 그대로 쓴다(하위 호환).
    """
    spec: dict[str, Any] = {**GENERAL_PURPOSE_SUBAGENT}
    if middleware:
        spec["middleware"] = list(middleware)
    if system_prompt is not None:
        spec["system_prompt"] = system_prompt
    return spec


def create_root_graph(
    *,
    model: Any,
    system_prompt: str,
    tools: Sequence[Any] = (),
    subagents: Sequence[Any] = (),
    middleware: Sequence[Any] = (),
    memory: Sequence[str] = (),
    backend: Any = None,
    store: Any = None,
) -> Any:
    """Root용 Deep Agent 그래프를 조립한다.

    `memory`/`backend`/`store`는 장기 메모리용(2026-08-15,
    `services/agent_runtime/memory/` 참고) — Child에는 안 넘긴다
    (`create_child_graph`에는 이 세 파라미터가 없다). 셋 다 안 넘기면
    (기본값) deepagents 기본 동작 그대로다(하위 호환) — `kwargs`에서 아예
    뺀다, `None`/빈 값을 그대로 넘기면 deepagents가 "명시적으로 지정한 것"과
    "안 지정한 것"을 구분 못 할 수 있어서.
    """
    kwargs: dict[str, Any] = dict(
        model=model,
        system_prompt=system_prompt,
        tools=list(tools),
        subagents=list(subagents),
        middleware=list(middleware),
    )
    if memory:
        kwargs["memory"] = list(memory)
    if backend is not None:
        kwargs["backend"] = backend
    if store is not None:
        kwargs["store"] = store
    return create_deep_agent(**kwargs)


def create_child_graph(
    *,
    model: Any,
    system_prompt: str,
    tools: Sequence[Any] = (),
    middleware: Sequence[Any] = (),
) -> Any:
    """재위임 기능이 없는 Child 그래프를 조립한다."""
    return create_deep_agent(
        model=model,
        system_prompt=system_prompt,
        tools=list(tools),
        subagents=[],
        middleware=list(middleware),
    )
