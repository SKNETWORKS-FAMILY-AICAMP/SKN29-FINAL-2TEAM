"""deepagents==0.7.5 전용 그래프 조립 함수."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
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

# `FilesystemMiddleware`가 만들 수 있는 가상 파일시스템 Tool 전체(2026-08-18,
# §5 Phase 6 — `deepagents/middleware/filesystem.py`의 공개 타입
# `FsToolName = Literal["ls", "read_file", "write_file", "edit_file", "delete",
# "glob", "grep", "execute"]`로 실측 확인). deepagents 내부의 `_ALL_FS_TOOL_NAMES`는
# private(밑줄 접두)라 여기서 새로 import하지 않고, 같은 소스로 확인한 값만
# 이 모듈에 둔다(compat 모듈의 책임 — deepagents 버전별 차이는 여기서만 안다).
_ALL_FS_TOOL_NAMES: tuple[str, ...] = (
    "ls",
    "read_file",
    "write_file",
    "edit_file",
    "delete",
    "glob",
    "grep",
    "execute",
)


def _filesystem_tools_allowlist(excluded: frozenset[str]) -> list[str]:
    """`excluded`를 뺀 나머지 FS Tool 이름 목록을 만든다.

    `FilesystemMiddleware(tools=[...])`에 그대로 넘긴다 — `read_file`은
    `FilesystemMiddleware` 자체가 필수로 요구해서(그 생성자가 없으면
    `ValueError`) `excluded`에 넣을 일이 없다는 전제다(지금 유일한 값인
    `runtime_policy.DEFAULT_EXCLUDED_BUILTIN_TOOLS = frozenset({"delete"})`가
    이 전제를 지킨다).
    """
    return [name for name in _ALL_FS_TOOL_NAMES if name not in excluded]


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
    tool_description_overrides: Mapping[str, str] | None = None,
) -> None:
    """자동 general-purpose 삽입을 끄는 프로필을 등록한다.

    `tool_description_overrides`(2026-08-20 추가)는 그대로
    `HarnessProfile.tool_description_overrides`에 실린다 — `create_deep_agent()`가
    이 값으로 도구 스키마 설명을 덮어쓰고(`"task"` 키는 `SubAgentMiddleware`의
    `task_description=`으로도 같이 전달돼 위임 도구 자체의 설명을 바꾼다). 안
    넘기면(`None`) 빈 dict로 떨어져 deepagents 기본 설명을 그대로 쓴다(하위 호환).
    """
    register_harness_profile(
        model_key,
        HarnessProfile(
            general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
            excluded_tools=excluded_tools,
            tool_description_overrides=tool_description_overrides or {},
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
    description: str | None = None,
    tools: Sequence[Any] | None = None,
    skills: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Root에 명시적으로 연결할 general-purpose 설정을 만든다.

    `system_prompt`를 넘기면 deepagents 기본값 대신 그 값을 쓴다 — Factory가
    `RuntimePromptAssembler.assemble_general_purpose()`로 조립한 값을 넘긴다.
    안 넘기면(`None`) deepagents 기본값을 그대로 쓴다(하위 호환).

    `description`(2026-08-20 추가)도 같은 패턴이다 — Root가 `task` 도구의
    `{available_agents}` 목록에서 실제로 읽는, GP 자신의 설명이다. **주의**:
    `GeneralPurposeSubagentProfile.description`(deepagents `HarnessProfile` 쪽
    설정)이 아니라 여기여야 한다 — 그 설정은 "호출자가 GP를 명시적으로 안 넘겼을
    때 deepagents가 자동으로 끼워 넣는 기본 GP"에만 적용되는데, 이 저장소는
    `factory.py`가 항상 이 함수로 GP를 직접 만들어 넘기므로 그 경로를 안 탄다.
    안 넘기면(`None`) deepagents 기본값을 그대로 쓴다(하위 호환).

    `tools`(2026-08-20 추가)를 넘기면 GP가 그 목록만 쓴다. **안 넘기면**
    (`None`) deepagents `graph.py`의 fallback(`raw_subagent_tools =
    spec.get("tools") if "tools" in spec else tools` — 즉 `"tools"` 키
    자체가 없으면 Root의 전체 도구를 그대로 물려받는다)이 그대로 적용된다
    (하위 호환). `factory.py`는 항상 `side_effect=False`인 도구만 걸러
    넘긴다 — GP가 쓰기·전송·삭제 도구를 상속하지 않게 하려는 목적이라
    빈 리스트(`[]`)를 넘기는 것과 아예 안 넘기는 것(`None`)은 의미가 다르다.

    `skills`(2026-08-21 추가, Skill 배선): 서브에이전트 spec dict의 `skills` 키에
    그대로 채운다. **deepagents는 이 GP에 자동으로 상속시켜 주지 않는다** —
    deepagents 자체 기본 general-purpose만 top-level `skills=`를 자동으로
    물려받고(`create_deep_agent()`가 caller가 GP를 안 넘겼을 때만 타는 경로,
    `deepagents/graph.py` 실측), 이 저장소는 `factory.py`가 항상 이 함수로 GP를
    직접 만들어 넘기므로 그 자동 상속 경로를 안 탄다 — 그래서 여기서 명시적으로
    같은 목록을 채워 그 기본 동작을 재현한다(설계 문서 "Root/GP/Child" 절).
    안 넘기면(`None`) Skill을 안 붙인다(하위 호환).
    """
    spec: dict[str, Any] = {**GENERAL_PURPOSE_SUBAGENT}
    if middleware:
        spec["middleware"] = list(middleware)
    if system_prompt is not None:
        spec["system_prompt"] = system_prompt
    if description is not None:
        spec["description"] = description
    if tools is not None:
        spec["tools"] = list(tools)
    if skills:
        spec["skills"] = list(skills)
    return spec


def create_root_graph(
    *,
    model: Any,
    system_prompt: str,
    tools: Sequence[Any] = (),
    subagents: Sequence[Any] = (),
    middleware: Sequence[Any] = (),
    memory: Sequence[str] = (),
    skills: Sequence[str] = (),
    backend: Any = None,
    store: Any = None,
    checkpointer: Any = None,
    memory_system_prompt: str | None = None,
    skills_system_prompt: str | None = None,
    fs_excluded_tools: frozenset[str] = frozenset(),
    interrupt_on: dict[str, bool] | None = None,
    permissions: Sequence[Any] = (),
) -> Any:
    """Root용 Deep Agent 그래프를 조립한다.

    `memory`/`backend`/`store`는 장기 메모리용(2026-08-15,
    `services/agent_runtime/memory/` 참고), `checkpointer`는 실행 중단·재개 및
    턴 간 상태 유지용(2026-08-18, `services/agent_runtime/checkpoint/` 참고) —
    Child에는 안 넘긴다(`create_child_graph`에는 이 네 파라미터가 없다.
    checkpointer는 LangGraph가 상위 그래프에 붙인 것을 서브그래프 실행에도 그대로
    적용하므로 Child가 따로 받을 이유도 없다). 넷 다 안 넘기면(기본값) deepagents
    기본 동작 그대로다(하위 호환) — `kwargs`에서 아예 뺀다, `None`/빈 값을 그대로
    넘기면 deepagents가 "명시적으로 지정한 것"과 "안 지정한 것"을 구분 못 할 수
    있어서.

    `memory_system_prompt`(2026-08-18, Phase 3, §4-8): `MemoryMiddleware`의
    system_prompt를 바꿀 공개 파라미터가 `create_deep_agent()`에 없다(`memory=`
    경로 목록만 받는다 — deepagents==0.7.5 실제 소스, `deepagents/graph.py`의
    `create_deep_agent` 시그니처로 확인). 대신 deepagents는 `middleware=`로 받은
    커스텀 middleware의 `.name`이 자동 생성된 것과 같으면(둘 다 클래스명
    `"MemoryMiddleware"`) **그 자리에서 치환**한다(`_apply_custom_middleware`,
    같은 소스 파일). 그래서 여기서 같은 `backend` 인스턴스를 공유하는 커스텀
    `MemoryMiddleware`를 만들어 `middleware` 목록 끝에 끼워 넣는 방식으로 처리한다
    — `FilesystemMiddleware`/`SubAgentMiddleware`와 backend 인스턴스를 공유해야
    한다는 기존 제약(§4-4)을 그대로 지킨다. `backend`가 없으면(메모리 자체를 안
    쓰면) 무시한다.

    `fs_excluded_tools`(2026-08-18, Phase 6): `create_deep_agent()`는
    `FilesystemMiddleware`의 `tools=` allowlist를 바꿀 공개 파라미터가 없다
    (`deepagents/graph.py`가 내부에서 `FilesystemMiddleware(backend=backend,
    custom_tool_descriptions=..., _permissions=...)`로 고정 생성 — 실측 확인).
    `memory_system_prompt`와 같은 이유로, 같은 `.name`("FilesystemMiddleware")을
    갖는 커스텀 인스턴스를 `middleware` 목록에 끼워 넣어 자동 생성분을
    치환한다 — **같은 `backend` 인스턴스**를 넘겨서 Memory/Filesystem 간 backend
    공유 제약(§4-4)을 그대로 지킨다. 빈 집합이면(기본값) 손대지 않는다(하위
    호환) — `runtime_policy.excluded_builtin_tools`(지금 `{"delete"}`)가
    `bootstrap.py`의 `_ToolExclusionMiddleware`로 이미 한 번 걸러내므로, 이건
    같은 값을 쓰는 **이중 방어**다(§5 Phase 6 계획 — 한쪽이 빠지거나 프로필
    설정이 틀려도 다른 쪽이 남는다). `tool_token_limit_before_evict`는 여기서
    건드리지 않는다 — 계측 없이 하향하면 근거 없는 임의 조정이라 계측이
    선행조건(같은 계획 문서).

    `interrupt_on`(2026-08-18, Phase 7): `create_deep_agent()`가 공개
    파라미터로 직접 받는다(`interrupt_on: dict[str, bool | InterruptOnConfig]
    | None` — `deepagents/graph.py` 시그니처 실측). 넘기면 내부에서
    `HumanInTheLoopMiddleware(interrupt_on=...)`를 **자동으로** 이어붙이므로
    (같은 소스, `_merge_fs_interrupt_on`/`general_purpose_spec["interrupt_on"]`
    처리까지 general-purpose에도 자동 전파됨을 확인) Memory/Filesystem처럼
    이름 치환 트릭이 필요 없다 — 그대로 통과만 시킨다. `None`이면(기본값)
    deepagents 기본 동작 그대로다.

    `permissions`(2026-08-19, `middleware/permissions.py` — `docs/작업기록/
    Deep_Agents/2026-08-18_06_미들웨어_전체_설계_정리.md` §5): `create_deep_agent()`가
    공개 파라미터로 직접 받는 `list[FilesystemPermission] | None`(실제 소스
    시그니처 확인)이지만, **여기 최상위 `kwargs`에 넣는 것만으로는 부족하다.**
    `fs_excluded_tools`가 비어있지 않으면(이 프로젝트는 `delete` 제외가 기본값이라
    항상 그렇다) 아래에서 이름 치환용 커스텀 `FilesystemMiddleware(**fs_kwargs)`를
    새로 만드는데, 이 커스텀 인스턴스가 자동 생성분(원래 `_permissions=permissions`를
    받았을 인스턴스)을 치환해 버린다 — `fs_kwargs`에 `_permissions`를 같이 안 넘기면
    Root 자신에게는 규칙이 에러 없이 조용히 적용 안 된다(§5에서 `deepagents/graph.py`
    실제 소스로 확인한 내용). 그래서 아래 두 곳에 모두 채운다: 최상위
    `kwargs["permissions"]`(general-purpose 서브에이전트가 자기 몫
    `FilesystemMiddleware`를 만들 때 `spec.get("permissions", permissions)`로
    부모 값을 자동 상속받는 경로에 필요)와 `fs_kwargs["_permissions"]`(Root 자신에게
    실제로 적용되는 경로). 빈 시퀀스면(기본값) 둘 다 안 건드려 기존 동작과 동일하다.

    `skills`(2026-08-21 추가, Skill 배선): `create_deep_agent()`가 공개
    파라미터로 직접 받는 `skills: list[str] | None`(`deepagents/graph.py`
    시그니처 실측) — `memory_system_prompt`/`fs_excluded_tools`와 달리 이름
    치환 트릭이 필요 없다, 그대로 통과만 시킨다. 빈 시퀀스면(기본값) 안
    건드려 하위 호환.

    `skills_system_prompt`(2026-08-22 추가, Skill 우선순위 규칙 — `2026-08-22_05`
    문서 참고): `SkillsMiddleware`의 system_prompt를 바꿀 공개 파라미터가
    `create_deep_agent()`에 없다(`skills=` 경로 목록만 받는다 — `memory_system_prompt`
    와 같은 제약). `memory_system_prompt`와 똑같은 이름 치환 트릭을 쓴다 —
    `SkillsMiddleware(system_prompt=...)`가 그 인자를 공개로 받으므로
    (`deepagents/middleware/skills.py` 실측), 같은 `backend` 인스턴스를 공유하는
    커스텀 인스턴스를 만들어 `middleware` 목록 끝에 끼워 넣으면 이름
    ("SkillsMiddleware")이 같은 자동 생성분을 그 자리에서 치환한다. `skills`가
    비어 있거나 `backend`가 없으면(스킬 자체를 안 쓰면) 무시한다 — 하위 호환.
    """
    kwargs: dict[str, Any] = dict(
        model=model,
        system_prompt=system_prompt,
        tools=list(tools),
        subagents=list(subagents),
    )
    resolved_middleware = list(middleware)
    if memory:
        kwargs["memory"] = list(memory)
    if skills:
        kwargs["skills"] = list(skills)
    if backend is not None:
        kwargs["backend"] = backend
    if store is not None:
        kwargs["store"] = store
    if checkpointer is not None:
        kwargs["checkpointer"] = checkpointer
    if interrupt_on:
        kwargs["interrupt_on"] = interrupt_on
    resolved_permissions = list(permissions)
    if resolved_permissions:
        kwargs["permissions"] = resolved_permissions
    if memory_system_prompt is not None and backend is not None:
        from deepagents import MemoryMiddleware

        resolved_middleware.append(
            MemoryMiddleware(
                backend=backend,
                sources=list(memory),
                add_cache_control=True,
                system_prompt=memory_system_prompt,
            )
        )
    if skills_system_prompt is not None and skills and backend is not None:
        from deepagents.middleware.skills import SkillsMiddleware

        resolved_middleware.append(
            SkillsMiddleware(
                backend=backend,
                sources=list(skills),
                system_prompt=skills_system_prompt,
            )
        )
    if fs_excluded_tools:
        from deepagents.middleware.filesystem import FilesystemMiddleware

        fs_kwargs: dict[str, Any] = {"tools": _filesystem_tools_allowlist(fs_excluded_tools)}
        if backend is not None:
            fs_kwargs["backend"] = backend
        if resolved_permissions:
            fs_kwargs["_permissions"] = resolved_permissions
        resolved_middleware.append(FilesystemMiddleware(**fs_kwargs))
    kwargs["middleware"] = resolved_middleware
    return create_deep_agent(**kwargs)


def create_child_graph(
    *,
    model: Any,
    system_prompt: str,
    tools: Sequence[Any] = (),
    middleware: Sequence[Any] = (),
    fs_excluded_tools: frozenset[str] = frozenset(),
    interrupt_on: dict[str, bool] | None = None,
) -> Any:
    """재위임 기능이 없는 Child 그래프를 조립한다.

    `fs_excluded_tools`/`interrupt_on`은 `create_root_graph`와 같은 근거로
    받는다(위 docstring 참고) — Child는 `backend`를 따로 안 받으므로(장기
    메모리는 Root 전용, 파일 docstring 상단 참고) `FilesystemMiddleware`
    치환 시에도 backend를 안 넘긴다 — deepagents 기본값(`StateBackend()`,
    스레드 한정)과 동일하게 동작해 공유할 인스턴스 자체가 없다.
    """
    resolved_middleware = list(middleware)
    if fs_excluded_tools:
        from deepagents.middleware.filesystem import FilesystemMiddleware

        resolved_middleware.append(
            FilesystemMiddleware(tools=_filesystem_tools_allowlist(fs_excluded_tools))
        )
    kwargs: dict[str, Any] = dict(
        model=model,
        system_prompt=system_prompt,
        tools=list(tools),
        subagents=[],
        middleware=resolved_middleware,
    )
    if interrupt_on:
        kwargs["interrupt_on"] = interrupt_on
    return create_deep_agent(**kwargs)
