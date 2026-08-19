"""모델·Tool·Child·Middleware를 조합해 Deep Agent graph를 만든다."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from langchain_core.tools import StructuredTool, ToolException

from services.agent_runtime.compat import (
    build_general_purpose_spec,
    create_child_graph,
    create_root_graph,
    default_general_purpose_prompt,
)
from services.agent_runtime.context import RuntimeContext
from services.agent_runtime.definitions import AgentDefinition, SubagentReference
from services.agent_runtime.exceptions import ToolPermissionError
from services.agent_runtime.subagents.builder import build_subagent
from services.agent_runtime.subagents.validation import validate_subagents
from services.agent_runtime.tools.loader import Tool, inject_runtime_context, model_safe_tool_name

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from services.agent_runtime.checkpoint.provider import CheckpointerProvider
    from services.agent_runtime.memory.provider import MemoryProvider
    from services.agent_runtime.middleware.factory import MiddlewareFactory
    from services.agent_runtime.models.factory import ModelConfigResolver, ModelFactory
    from services.agent_runtime.prompts import RuntimePromptAssembler
    from services.agent_runtime.runtime_policy import RuntimeCapabilityPolicy
    from services.agent_runtime.tools.loader import ToolLoader


class DependencyGraphSource:
    """팀의 Agent 의존 그래프를 조회한다."""

    def load(self, team_id: str) -> dict[str, set[str]]:
        # 저장·발행 경로와 같은 의존 그래프 조회를 사용한다.
        from backend.db.agent_platform import _team_dependency_graph
        from backend.db.connection import database_connection

        with database_connection() as connection:
            with connection.cursor() as cursor:
                return _team_dependency_graph(cursor, team_id=team_id)


def _to_langchain_tool(
    tool: Tool, *, context: RuntimeContext, runtime_policy: "RuntimeCapabilityPolicy"
) -> StructuredTool:
    """Tool을 LangChain `StructuredTool`로 변환한다.

    `build()`의 `filter_tools_for_role()`(노출 시점, 1회)과 별개로, 이 도구가 실제
    실행되는 시점(`_run()` 호출마다)에도 같은 정책을 다시 확인한다. 노출 필터
    하나만 유일한 방어선이면 그 필터의 버그·설정 누락(예: 새 Tool을
    `side_effect=True`로 표시하는 걸 빠뜨림)이 곧바로 권한 우회가 된다 — 실행
    직전에도 다시 확인해 두 시점 중 하나만 맞아도 막히게 한다. 노출 필터가 쓰는
    것과 완전히 같은 판단 함수(`is_tool_allowed_for_role`)를 재사용해서 두
    시점의 판단이 서로 갈릴 일이 없게 했다(2026-08-14 추가).
    """

    def _run(**kwargs: Any) -> Any:
        if not runtime_policy.is_tool_allowed_for_role(
            side_effect=tool.side_effect, account_role=context.role
        ):
            # 이건 그대로 둔다 — 노출 필터를 뚫고 여기까지 온 권한 위반은
            # "모델이 고칠 수 있는 실수"가 아니라 방어선 자체의 이상이라 계속
            # 감추지 않고 terminal EVENT_ERROR로 크게 드러낸다(ToolPermissionError
            # 자체 docstring 참고) — 아래 handler 실패와 다른 취급이다.
            raise ToolPermissionError(
                f"'{context.role}' 역할은 '{tool.ref}' 도구를 실행할 권한이 없습니다."
            )
        resolved = inject_runtime_context(tool, kwargs, context)
        try:
            return tool.handler(**resolved)
        except Exception as exc:
            # **도구 하나 실패로 대화 전체를 끊지 않는다 — 단, 말할 수 있는
            # 사유일 때만.**(2026-08-18/19 합의) 실측해 보니(실제 대화에서
            # `jira_get_issues` 재현) 설치된 langgraph 버전의 기본 핸들러
            # (`_default_handle_tool_errors`)는 자기 내부 `ToolInvocationError`만
            # 잡고 나머지는 그대로 다시 던져서, `ToolInputError` 하나가 대화
            # 전체를 끊고 `ErrorCard`까지 만들었다.
            #
            # main(`73bc79c`, `services/harness/runner.SPEAKABLE_ERRORS`)이 같은
            # 버그를 먼저 고쳤는데, 정책이 두 가지였다: 말할 수 있는 예외는
            # 봐주고, 그 밖은 **그대로 크래시** — "삼키면 진짜 장애가 「도구가
            # 뭐라고 했다」로 둔갑한다"는 이유였다. 그 판단은 그대로 가져온다
            # (아래 `if not isinstance(...): raise`). 다만 "봐주는" 방식은
            # 다르다 — main은 정상 반환값(`{"error": ...}`)으로 감싸서
            # `tool_completed.status`가 OK로 마스킹됐다. 여기서는 대신
            # `ToolException`으로 바꿔 던진다(`handle_tool_error=True`와
            # 짝 — `StructuredTool.from_function` 참고): `langchain_core`의
            # `BaseTool.run()`이 `ToolException`만 잡아 `status="error"`를
            # 그대로 유지해 주므로, `tool_completed`는 여전히 FAILED로 뜨고
            # 클릭하면 사유도 그대로 보인다 — 대화가 안 끊기는 것과 FAILED
            # 표시가 정확한 것, 둘 다 챙긴다.
            # 지연 import — `services.harness.runner`의 무거운 의존성 사슬을 이
            # 모듈이 항상 끌고 들어오지 않게 한다(main의 같은 판단 그대로 유지).
            from services.harness.runner import SPEAKABLE_ERRORS

            if not isinstance(exc, SPEAKABLE_ERRORS):
                # 진짜 장애다 — 트레이스백까지 남긴다.
                logger.exception("도구 실행 실패: %s", tool.ref)
                raise
            # **말할 수 있는 사유에는 트레이스백을 남기지 않는다.** 「프로젝트를
            # 먼저 고르세요」는 사람이 고칠 수 있는 정상적인 되돌림이지 장애가
            # 아니다 — `logger.exception`으로 남기면 운영 로그에서 위 진짜
            # 장애와 구분이 안 된다.
            logger.info("도구가 사유를 돌려줬다: %s — %s", tool.ref, exc)
            raise ToolException(str(exc)) from exc

    return StructuredTool.from_function(
        func=_run,
        handle_tool_error=True,
        # `tool.name`이 아니라 `tool.ref`다 — **실측으로 확인한 버그**(2026-08-14):
        # `tool.name`은 `services/harness/registry.py`의 BUILTIN_TOOLS가 사람이
        # 읽는 한국어 라벨로 채운다(예: "프로젝트 조회"). 이걸 LangChain
        # `StructuredTool.name`(=OpenAI/Anthropic에 실제로 나가는 함수 이름)에
        # 그대로 쓰면 OpenAI Responses API가 400으로 거절한다 — 함수 이름은
        # `^[a-zA-Z0-9_-]+$`만 허용하는데 한국어·공백이 그 패턴을 못 넘는다
        # (실제로 겪음: `Invalid 'tools[1].name': string does not match
        # pattern`). 레거시 Harness(`services/harness/runner.py`
        # `model_name_for()`)는 이미 2026-08-12에 같은 문제를 `tool.ref` 사용 +
        # 콜론 치환(`agent:`/`mcp:` 접두사 대비)으로 고쳐 놓았었다 — 그
        # 선례에서 "무엇이 API로 나가는 이름이어야 하는가"만 가져왔다(`ref`).
        # MCP를 실제로 연결하면서(2026-08-14, ⑧) 콜론 치환도 옮겼다 —
        # `model_safe_tool_name()`(tools/loader.py)이 레거시 `model_name_for()`와
        # 같은 규칙(`:` -> `__`)으로 바꾼다. 되돌리는 쪽
        # (`tool_ref_from_model_name()`)은 `events.py`가 모델의 tool_calls에서
        # tool_ref를 다시 읽어낼 때 쓴다 — 안 옮기면 실행 로그
        # (`tool_call.tool_ref`)에 `mcp__MT001`처럼 망가진 값이 남는다.
        name=model_safe_tool_name(tool.ref),
        description=tool.description,
        args_schema=tool.input_schema,
        infer_schema=False,
    )


class AgentRuntimeFactory:
    """실행 정의와 요청 컨텍스트로 Root 또는 Child graph를 만든다."""

    def __init__(
        self,
        *,
        dependency_graph: DependencyGraphSource,
        model_config_resolver: "ModelConfigResolver",
        model_factory: "ModelFactory",
        tool_loader: "ToolLoader",
        middleware_factory: "MiddlewareFactory",
        runtime_policy: "RuntimeCapabilityPolicy",
        prompt_assembler: "RuntimePromptAssembler",
        memory_provider: "MemoryProvider | None" = None,
        checkpointer_provider: "CheckpointerProvider | None" = None,
    ) -> None:
        self.dependency_graph = dependency_graph
        self.model_config_resolver = model_config_resolver
        self.model_factory = model_factory
        self.tool_loader = tool_loader
        self.middleware_factory = middleware_factory
        self.runtime_policy = runtime_policy
        self.prompt_assembler = prompt_assembler
        # 기본값 None 허용 — 장기 메모리 없이 쓰던 기존 호출자(테스트 등)를
        # 깨지 않으려고(2026-08-15 추가). None이면 build()가 memory/backend/store
        # 없이 예전과 동일하게 돈다.
        self.memory_provider = memory_provider
        # memory_provider와 같은 이유로 기본값 None 허용(2026-08-18 추가). None이면
        # build()가 checkpointer 없이 예전과 동일하게 돈다 — 이 경우
        # `stream_adapter.py`도 예전처럼 매 턴 conversation_messages를 그대로
        # 붙이는 경로로 돈다(§5 Phase 1, `stream_adapter.py` docstring 참고).
        self.checkpointer_provider = checkpointer_provider

    def build(
        self,
        *,
        definition: AgentDefinition,
        subagent_references: tuple[SubagentReference, ...] = (),
        context: RuntimeContext,
        allow_subagents: bool = True,
    ) -> Any:
        # `allow_subagents`는 여기서 Root/Child 그래프 중 무엇을 지을지만
        # 가른다(아래) — "이 Child가 이미 서브 에이전트를 갖고 있는가"
        # 검사와는 무관하다. `validate_subagents()`는 그 검사를 항상 켜 둔다
        # (2026-08-14 수정 — 예전에는 이 인자를 그 검사에도 같이 써서, Root를
        # 지을 때(allow_subagents=True) 검사가 통째로 빠졌었다).
        validate_subagents(
            parent_agent_id=definition.agent_id,
            child_refs=subagent_references,
            dependency_graph=self.dependency_graph.load(context.team_id),
        )

        resolved_model = self.model_config_resolver.resolve(
            model=definition.model,
            reasoning_effort=definition.reasoning_effort,
            team_id=context.team_id,
        )
        model = self.model_factory.create(resolved_model)

        tools = self.tool_loader.load(
            tool_refs=definition.tool_refs, context=context, agent_model=definition.model
        )
        tools = self.runtime_policy.filter_tools_for_role(tools, account_role=context.role)
        langchain_tools = [
            _to_langchain_tool(t, context=context, runtime_policy=self.runtime_policy) for t in tools
        ]

        # 2026-08-18, §5 Phase 7 — `interrupt_on`은 `checkpointer_provider`가
        # 있을 때만 만든다. `HumanInTheLoopMiddleware`의 `interrupt()`는
        # Checkpointer 없이는 재개가 안 되므로(계획 문서 §5 Phase 7: "Phase
        # 1(Checkpointer) 완료 전에는 착수 불가"), Checkpointer가 없는 배포·
        # 테스트에서까지 승인 대기를 걸면 재개할 방법이 없는 상태로 막히기만
        # 한다. `tools`(역할 필터까지 끝난 이번 요청의 실제 노출 목록)에서
        # `side_effect=True`인 것만 뽑는다 — Phase 0에서 확인한 값(`task_register`
        # /`task_update`/`jira_create_issues`, MCP 도구 전부)을 하드코딩하지
        # 않고 매 요청 시점의 실제 목록을 그대로 쓴다 — 팀마다 달라지는 MCP
        # 도구나 나중에 추가될 side_effect 도구도 자동으로 포함된다.
        interrupt_on: dict[str, bool] | None = None
        if self.checkpointer_provider is not None:
            side_effect_tools = {model_safe_tool_name(t.ref): True for t in tools if t.side_effect}
            if side_effect_tools:
                interrupt_on = side_effect_tools

        custom_middleware = self.middleware_factory.build(definition=definition, context=context)

        # 공통 Runtime Scaffold + Agent별 system_prompt(DB의 agent_versions.
        # system_prompt, Builder가 작성한 그대로)를 실행 시점에 결합한다
        # (services/agent_runtime/prompts.py 모듈 docstring — 저장 시점이 아니라
        # 여기서 결합해야 공통 정책을 바꿀 때 기존 버전을 다시 발행하지 않아도
        # 된다. 2026-08-14 추가).
        if not allow_subagents:
            return create_child_graph(
                model=model,
                system_prompt=self.prompt_assembler.assemble_child(
                    agent_prompt=definition.system_prompt
                ),
                tools=langchain_tools,
                middleware=custom_middleware,
                # 2026-08-18, §5 Phase 6/7 — Root와 같은 근거로 Child에도
                # 건다(두 근거 모두 create_child_graph() docstring 참고).
                fs_excluded_tools=self.runtime_policy.excluded_builtin_tools,
                interrupt_on=interrupt_on,
            )

        compiled_children = [
            build_subagent(
                sub_def,
                context,
                build_child_graph=lambda d, c: self.build(
                    definition=d, context=c, allow_subagents=False
                ),
            )
            for sub_def in definition.subagents
        ]
        gp_spec = build_general_purpose_spec(
            middleware=self.middleware_factory.build_for_general_purpose(),
            system_prompt=self.prompt_assembler.assemble_general_purpose(
                gp_prompt=default_general_purpose_prompt()
            ),
        )

        # Root에만 붙는 선택적 협력자들 — Child(위 allow_subagents=False 분기)는
        # 둘 다 안 받는다. memory_provider가 None이면 memory/backend/store 없이,
        # checkpointer_provider가 None이면 checkpointer 없이 예전과 동일하게 돈다.
        root_kwargs: dict[str, Any] = {}
        if self.memory_provider is not None:
            root_kwargs.update(
                memory=self.memory_provider.paths(),
                backend=self.memory_provider.backend(
                    team_id=context.team_id,
                    agent_id=definition.agent_id,
                    account_id=context.account_id,
                ),
                store=self.memory_provider.store(),
                # 2026-08-18, Phase 3(§4-8) — MemoryMiddleware.system_prompt에
                # 라우팅 안내를 이어붙인다. create_root_graph()가 이 값으로
                # 커스텀 MemoryMiddleware를 만들어 자동 생성분을 치환한다.
                memory_system_prompt=self.memory_provider.system_prompt(),
            )
        if self.checkpointer_provider is not None:
            root_kwargs["checkpointer"] = self.checkpointer_provider.get()

        return create_root_graph(
            model=model,
            system_prompt=self.prompt_assembler.assemble_root(
                agent_prompt=definition.system_prompt
            ),
            tools=langchain_tools,
            subagents=[gp_spec, *compiled_children],
            middleware=custom_middleware,
            # 2026-08-18, §5 Phase 6 — memory_provider 유무와 무관하게 항상
            # 건다(Filesystem Tool 노출 제한은 메모리 기능과 별개).
            fs_excluded_tools=self.runtime_policy.excluded_builtin_tools,
            # 2026-08-18, §5 Phase 7 — checkpointer_provider가 없으면 위에서
            # None으로 남는다.
            interrupt_on=interrupt_on,
            **root_kwargs,
        )


__all__ = ["AgentRuntimeFactory", "DependencyGraphSource"]
