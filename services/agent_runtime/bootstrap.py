"""실제 의존성으로 `AgentExecutor`를 조립하는 합성 루트(composition root).

정본: docs/설계 및 구현/3_중간발표 이후/작업기록/Deep_Agents/2026-08-13_02_Deep-Agent_런타임_공통_계약_v1.md §6(task #10),
      2026-08-13_04_작업자B_실행코어_세부계획.md §9.3(선결 B), §9.5

이 모듈이 하는 일은 "무엇을 실제로 연결하는가" 하나뿐이다 — 각 부품(`ModelFactory`,
`ToolLoader`, `AgentRuntimeFactory` 등)의 조립 로직 자체는 이미 각자의 모듈에
구현·테스트돼 있다. apps/*(Builder Test API, Chat API — §6-12)는 이 모듈이 아니라
`services.agent_runtime`(패키지 최상위)의 `build_default_executor`만 참조한다 —
패키지 `__init__.py`가 이미 "외부는 최소 공개 인터페이스만 참조" 원칙을 선언해
뒀고, 이 파일은 그 원칙을 따른다.

**왜 캐싱(싱글턴)하지 않고 호출마다 새로 조립하는가**: 이 패키지가 대체하려는
`services/harness/runner.py`의 `run_agent()`가 이미 이 코드베이스의 확립된
관례다 — Django `AppConfig.ready()` 훅도, DI 컨테이너도 쓰지 않고 호출마다
필요한 걸 그 자리에서 만든다(INSTALLED_APPS에 `apps.*`가 아예 등록돼 있지 않음 —
이 저장소는 Django를 ORM 없이 라우팅+뷰 계층으로만 쓴다). 아래에서 조립하는
값들은 전부 무상태이고 생성자에서 I/O를 하지 않으므로(DB 연결은 실제 호출
시점에만 열림 — `DependencyGraphSource.load()`, `ModelConfigResolver._team_endpoint()`
참고) 호출마다 새로 만드는 비용이 무시할 만하다. `register_default_harness_profile`은
deepagents 쪽에서 "추가적(additive) 등록 — 같은 key로 다시 불러도 병합만 되고
에러도, 초기화도 안 됨"이라고 명시하므로(`deepagents.profiles.harness.harness_profiles
.register_harness_profile` 문서 확인) 매 호출마다 다시 등록해도 안전하다.
"""

from __future__ import annotations

from services.agent_runtime.checkpoint import CheckpointerProvider
from services.agent_runtime.compat import assert_supported_version, register_default_harness_profile
from services.agent_runtime.executor import AgentExecutor
from services.agent_runtime.factory import AgentRuntimeFactory, DependencyGraphSource
from services.agent_runtime.loader import AgentDefinitionLoader
from services.agent_runtime.memory.provider import MemoryProvider
from services.agent_runtime.middleware.factory import MiddlewareFactory
from services.agent_runtime.models.factory import ModelConfigResolver, ModelFactory
from services.agent_runtime.prompts import RuntimePromptAssembler, TASK_DELEGATION_DESCRIPTION
from services.agent_runtime.runtime_policy import RuntimeCapabilityPolicy
from services.agent_runtime.skills.provider import SkillsProvider
from services.agent_runtime.tools.loader import ToolLoader

# deepagents는 `get_model_provider(model)`이 돌려주는 provider 문자열로만 harness
# profile을 찾는다. `models/factory.py`의 Provider는 셋이지만 `openai_compatible`도
# ChatOpenAI를 쓰므로 `get_model_provider()`는 항상 "openai"를 반환한다 — 그 key로
# 등록해 봐야 조회되지 않는 죽은 코드다. 그래서 등록할 key는 이 둘뿐이다
# (회귀 고정: `tests/test_harness_profile_model_key.py`).
_HARNESS_PROFILE_MODEL_KEYS: tuple[str, ...] = ("anthropic", "openai")


def bootstrap_harness_profiles(*, excluded_tools: frozenset[str]) -> None:
    """설치된 deepagents 버전을 확인하고 기본 harness profile을 등록한다.

    `excluded_tools`는 호출자가 넘긴다(내부에서 `RuntimeCapabilityPolicy`를 직접
    만들지 않음) — 어떤 도구를 숨길지의 단일 진실 공급원은 `runtime_policy.py`
    하나로 유지하고, 이 함수는 "그 값을 실제로 deepagents에 등록한다"는 배선
    역할만 한다.

    `task` 도구 설명(2026-08-20 추가, `prompts.TASK_DELEGATION_DESCRIPTION`)도
    여기서 같이 등록한다 — Root가 도구를 직접 부를지 서브 에이전트에게 위임할지
    판단하는 자리라, 이 텍스트의 단일 진실 공급원도 `prompts.py` 하나로 유지한다.
    """
    assert_supported_version()
    for model_key in _HARNESS_PROFILE_MODEL_KEYS:
        register_default_harness_profile(
            model_key=model_key,
            excluded_tools=excluded_tools,
            tool_description_overrides={"task": TASK_DELEGATION_DESCRIPTION},
        )


def build_default_executor(*, runtime_policy: RuntimeCapabilityPolicy | None = None) -> AgentExecutor:
    """실제 의존성으로 조립한 `AgentExecutor`를 반환한다.

    `runtime_policy`를 넘기지 않으면 `RuntimeCapabilityPolicy()`의 기본값(운영
    기본 정책)을 쓴다. 운영 설정을 바꿔야 하는 자리(예: 커맨드라인 도구, 운영
    스크립트)에서만 명시적으로 다른 정책 인스턴스를 넘긴다 — 코드에 숫자를 다시
    박지 않는다.

    (2026-08-19 정정) 아래 줄은 §6-11 착수 전(2026-08-13) 기준으로 남아 있던
    경고다 — `tools/adapters.py`는 그 뒤 구현이 끝났고(`services/harness/registry.py`의
    `BUILTIN_TOOLS`를 감싼다), 지금은 실제로 도구를 쓰는 Agent도 정상 실행된다.
    이 함수가 Fake로 감싸지 않고 실제 프로덕션 배선을 그대로 반영한다는 설명
    자체는 여전히 유효해서 문단은 남기고 경고 문구만 정정한다.
    """
    policy = runtime_policy or RuntimeCapabilityPolicy()
    bootstrap_harness_profiles(excluded_tools=policy.excluded_builtin_tools)

    factory = AgentRuntimeFactory(
        dependency_graph=DependencyGraphSource(),
        model_config_resolver=ModelConfigResolver(),
        model_factory=ModelFactory(),
        tool_loader=ToolLoader(),
        middleware_factory=MiddlewareFactory(runtime_policy=policy),
        runtime_policy=policy,
        prompt_assembler=RuntimePromptAssembler(),
        # 둘 다 Root graph에만 붙는다(`factory.py`의 `build()`). 생성 자체는 I/O가
        # 없어서 "호출마다 새로 조립" 원칙과 어긋나지 않는다 — Postgres 연결은
        # 실제로 메모리·체크포인트를 쓰는 첫 호출에서 열린다.
        memory_provider=MemoryProvider(),
        checkpointer_provider=CheckpointerProvider(),
        # Skill(2026-08-21, services/agent_runtime/skills/). Memory와 같은
        # 공유 backend에 라우트만 얹는다 — memory_provider가 켜져 있을 때만
        # 실제로 붙는다(factory.py `__init__`/`build()` 주석 참고).
        # SkillsProvider() 생성 자체도 I/O가 없다(경로·namespace 계산뿐).
        skills_provider=SkillsProvider(),
    )
    return AgentExecutor(loader=AgentDefinitionLoader(), factory=factory)


__all__ = ["bootstrap_harness_profiles", "build_default_executor"]
