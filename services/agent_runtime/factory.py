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
from services.agent_runtime.memory.write_guard import build_memory_write_guard
from services.agent_runtime.memory.write_lock import build_memory_write_lock
from services.agent_runtime.subagents.builder import build_subagent
from services.agent_runtime.subagents.validation import validate_subagents
from services.agent_runtime.tools.loader import Tool, inject_runtime_context, model_safe_tool_name

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from services.agent_runtime.checkpoint.provider import CheckpointerProvider
    from services.agent_runtime.memory.provider import MemoryProvider
    from services.agent_runtime.middleware.factory import MiddlewareFactory
    from services.agent_runtime.models.factory import ModelConfigResolver, ModelFactory, ResolvedModelConfig
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


# §6순위(외부 Write Tool Idempotency)가 `_run(**kwargs)`까지 `tool_call_id`를
# 실어 보내려고 쓰는 예약 키. 이 프로젝트 도구는 전부 `args_schema`가
# Pydantic 모델이 아니라 `tool.input_schema`(원본 JSON Schema dict)라서
# LangChain 표준 `InjectedToolCallId`가 못 먹힌다 — 실측(설치된
# `langchain_core/tools/base.py`의 `_parse_input()`): `args_schema`가 dict면
# `if isinstance(input_args, dict): return tool_input`으로 `InjectedToolCallId`
# 스캔 자체를 건너뛰고 입력을 그대로 돌려준다. 아래 `_IdempotencyAwareTool`이
# `BaseTool.run()`이 받는 `tool_call_id` kwarg를 가로채 `tool_input`(dict)
# 복사본에 이 키로 얹어 두면, `_to_args_and_kwargs()`가 dict 입력을
# `tool_input.copy()`로 그대로 kwargs화하기 때문에(같은 소스 실측) 이 키도
# `_run(**kwargs)`까지 그대로 살아남는다.
_TOOL_CALL_ID_KWARG = "__langchain_tool_call_id__"


class _IdempotencyAwareTool(StructuredTool):
    """`run()`에서 `tool_call_id`를 가로채 `_run()`까지 전달하는 `StructuredTool`.

    표준 `InjectedToolCallId`가 이 프로젝트 도구(dict `args_schema`)에는
    안 먹혀서(위 `_TOOL_CALL_ID_KWARG` 주석 참고) 이 subclass로 대신한다.
    """

    def run(
        self,
        tool_input: str | dict[str, Any],
        *args: Any,
        tool_call_id: str | None = None,
        **kwargs: Any,
    ) -> Any:
        if isinstance(tool_input, dict) and tool_call_id is not None:
            tool_input = {**tool_input, _TOOL_CALL_ID_KWARG: tool_call_id}
        return super().run(tool_input, *args, tool_call_id=tool_call_id, **kwargs)


def _to_langchain_tool(
    tool: Tool, *, context: RuntimeContext, runtime_policy: "RuntimeCapabilityPolicy"
) -> StructuredTool:
    """Tool을 LangChain `StructuredTool`로 변환한다.

    권한 확인은 **이 도구가 실제로 실행되는 시점**(`_run()` 호출마다)에만
    한다 — 모델에게 무엇을 보여줄지(`build()`가 만드는 `langchain_tools`)는
    2026-08-19부터 역할과 무관하다(아래 "왜 노출 시점엔 안 거르는가" 참고).
    그래서 이 실행 시점 확인이 **유일한 방어선**이다 — `is_tool_allowed_for_role()`
    가 여기서 `False`를 돌려주면 아래 `_run()`이 `ToolException`으로 사유를
    말하고 끝낸다(대화는 안 끊긴다 — `_run()`의 그 분기 주석 참고).

    **왜 노출 시점엔 안 거르는가**: 예전에는 `build()`가 `filter_tools_for_role()`
    로 `side_effect=True` 도구를 `member`에게서 통째로 지워, 모델이 그 도구
    존재 자체를 몰라 "그런 기능이 없다"고 답했다(버그 리포트, 2026-08-19) —
    실제로는 권한이 없을 뿐인데 화면엔 "승인 필요"라고만 적혀 있어 팀장은
    "팀원이 쓰면 승인 카드가 뜨겠지"라고 오해했다. 이제 모델은 도구 존재를
    항상 알고, 실행하려 하면 이 함수의 `_run()`이 그 자리에서 사유를 말해
    준다 — 존재를 숨기는 대신 이유를 알려주는 쪽으로 바꿨다.
    """

    def _run(**kwargs: Any) -> Any:
        # §6순위(외부 Write Tool Idempotency) — `_IdempotencyAwareTool.run()`이
        # 실어 보낸 값. RBAC 검사보다 먼저 뗀다 — 권한이 없어 막힐 도구라도
        # `tool.handler(**resolved)`에 이 예약 키가 그대로 흘러들면 안 된다.
        langchain_tool_call_id = kwargs.pop(_TOOL_CALL_ID_KWARG, None)

        if not runtime_policy.is_tool_allowed_for_role(
            side_effect=tool.side_effect, account_role=context.role
        ):
            # **말할 수 있는 실패로 바꿨다**(2026-08-19, 위 함수 docstring
            # "왜 노출 시점엔 안 거르는가" 참고). 이 도구는 이제 역할과 무관하게
            # 항상 모델에게 노출되므로, member가 승인 필요 도구를 부르는 건
            # 방어선이 뚫린 이상 상황이 아니라 흔히 일어나는 정상 경로다.
            # 예전처럼 대화를 통째로 끊으면(`ToolPermissionError` → 크래시)
            # "권한이 없다"는 사유가 사라진 채 "요청을 끝내지 못했습니다"만
            # 남는다 — 아래 handler 실패(`ToolInputError` 등)와 같은 방식으로
            # `ToolException`을 던져 모델이 사유를 그대로 사람에게 전하게 한다.
            # 2026-08-20 — 기본 정책(`DEFAULT_WRITE_TOOL_ALLOWED_ROLES`)은
            # `leader`/`member` 둘 다 통과시키므로, 지금 정의된 두 역할로는
            # 이 분기가 평소엔 안 걸린다. `write_tool_allowed_roles`를 배포
            # 시점에 좁히거나(예: `frozenset({"leader"})`) 나중에 세 번째
            # 역할이 추가될 때를 위한 방어선으로 남겨 둔다 — 지운 적 없다.
            raise ToolException(
                f"'{context.role}' 역할은 '{tool.ref}' 도구를 실행할 권한이 없습니다. 팀장에게 요청해 주세요."
            )

        # §6순위(외부 Write Tool Idempotency) — HITL resume(§0순위)이나 checkpoint
        # 재시도로 같은 super-step이 다시 돌아도, jira_create_issues 같은
        # side_effect 도구가 진짜로 두 번 실행되지 않게 실행 직전에 이미 성공한
        # 같은 (run_id, langchain_tool_call_id) 결과가 있는지 먼저 본다.
        # side_effect가 아닌(읽기) 도구는 두 번 실행돼도 부작용이 없으므로
        # 대상이 아니다. `context.run_id`/`langchain_tool_call_id` 둘 다 있어야
        # 확인한다 — 테스트처럼 run_id 없이 도구를 직접 부르는 호출자를 깨지
        # 않으려고(그런 호출은 애초에 idempotency가 필요한 실행 경로가 아니다).
        # run_id로 스코프를 잡는 이유, tool_call과 별도 표를 쓰는 이유는
        # DB/migrations/2026-08-19_tool_call_idempotency.sql 참고.
        idempotency_scope = (
            tool.side_effect and langchain_tool_call_id and context.run_id
        )
        if idempotency_scope:
            from backend.db.agent_platform import ToolCallIdempotencyRepository

            cached = ToolCallIdempotencyRepository.find_result(
                run_id=context.run_id, langchain_tool_call_id=langchain_tool_call_id
            )
            if cached is not None:
                logger.info(
                    "idempotent 재생: %s (run_id=%s, tool_call_id=%s) — "
                    "다시 실행하지 않고 이전 결과를 그대로 돌려준다.",
                    tool.ref,
                    context.run_id,
                    langchain_tool_call_id,
                )
                return cached

        resolved = inject_runtime_context(tool, kwargs, context)
        try:
            result = tool.handler(**resolved)
        except Exception as exc:  # noqa: BLE001 - 도구 실패로 그래프 실행 전체를 끝내지 않는다
            # 2026-08-18 추가 — 실측으로 드러난 문제: `langgraph.prebuilt.ToolNode`의
            # 기본 `handle_tool_errors`(langchain.agents.factory.create_agent()가
            # 내부적으로 만드는 ToolNode라 우리가 값을 못 넣는다, 실측: langchain/
            # deepagents 소스 어디에도 `handle_tool_errors` 파라미터 자체가 없음)는
            # `langchain_core`의 `ToolInvocationError`(인자 스키마 검증 실패)만
            # 잡고, 그 외 예외는 전부 다시 raise한다 — `ToolInputError`/
            # `PermissionDenied`처럼 이 저장소가 "모델에게 그대로 보여줘도 되는
            # 실패"로 설계해 둔 예외까지 그래프 실행 전체를 죽인다(실제 사용자
            # 질의로 재현: `agent_user_query_tool_check.py` 시나리오 1/4/5가
            # `project_id`를 아직 못 정한 채 `task_list`/`task_extraction`을
            # 부르자 `ToolInputError`로 전체 실행이 즉시 크래시했다 — 모델이 이
            # 오류를 보고 "그럼 project_list부터 부르자"로 스스로 고칠 기회 자체가
            # 없었다).
            #
            # 레거시 `services/harness/runner.py`가 이미 같은 문제를 겪고 정한
            # 답을 그대로 재사용한다 — 새로 판단하지 않는다. `SPEAKABLE_ERRORS`
            # (`ToolInputError`/`RepositoryError`/`OAuthError`)는 그 모듈이 "이
            # 예외의 메시지는 사람에게 그대로 보여도 된다"고 이미 결정해 둔
            # 목록이고(`ToolInputError`의 클래스 docstring도 동일하게 말한다:
            # "사람에게 그대로 보여도 되는 실패... 이 예외의 메시지만 화면으로
            # 나간다"), `error_code_of()`도 MCP 에러의 code vs 그 외 클래스 이름을
            # 가르는 판단이 이미 있던 자리다("같은 판단을 하던 자리가 셋이었다.
            # 여기 하나로 둔다" — trace.py).
            #
            # **어느 쪽이든 정상 반환이 아니라 `ToolException`으로 던진다**
            # (2026-08-19 병합 정리). 그냥 `return` 하면 `tool_completed.status`가
            # OK로 남아 진짜 장애가 "도구가 뭐라고 했다"로 둔갑한다. `ToolException`은
            # `handle_tool_error=True`와 짝이라(아래 `from_function` 참고)
            # `BaseTool.run()`이 잡아 문자열로 모델에 넘기면서 `status="error"`는
            # 그대로 지킨다 — 대화가 안 끊기는 것과 FAILED 표시가 정확한 것, 둘 다
            # 챙긴다.
            # 지연 import — `services.harness.runner`의 무거운 의존성 사슬을 이
            # 모듈이 항상 끌고 들어오지 않게 한다.
            from services.harness.runner import SPEAKABLE_ERRORS
            from services.harness.trace import error_code_of

            if isinstance(exc, SPEAKABLE_ERRORS):
                # **말할 수 있는 사유에는 트레이스백을 남기지 않는다.** 「프로젝트를
                # 먼저 고르세요」는 사람이 고칠 수 있는 정상적인 되돌림이지 장애가
                # 아니다 — `logger.exception`으로 남기면 운영 로그에서 아래 진짜
                # 장애와 구분이 안 된다.
                logger.info("도구가 사유를 돌려줬다: %s — %s", tool.ref, exc)
                raise ToolException(str(exc)) from exc

            # 진짜 장애다 — 트레이스백까지 남기고, 모델에게는 원문 대신 코드만
            # 준다(문서 원문·토큰이 섞여 있을 수 있다).
            logger.exception("도구 실행 실패: %s", tool.ref)
            raise ToolException(f"도구 실행 실패: {error_code_of(exc)}") from exc
        else:
            # §6순위 — 방금 실행이 성공했다. 나중에 같은 (run_id,
            # langchain_tool_call_id)로 재시도가 들어오면 다시 실행하지 않고
            # 이 결과를 그대로 돌려줄 수 있게 남겨 둔다. 결과가 문자열이
            # 아닐 수도 있어(dict 등) `str()`로 통일한다 — 어차피
            # `BaseTool.run()`도 `ToolMessage.content`를 만들 때 결국 문자열로
            # 바꾸므로, 재생 시점에 원래 타입 그대로 못 돌려줘도 모델이 보는
            # 최종 내용은 같다.
            if idempotency_scope:
                from backend.db.agent_platform import ToolCallIdempotencyRepository

                ToolCallIdempotencyRepository.record_result(
                    run_id=context.run_id,
                    langchain_tool_call_id=langchain_tool_call_id,
                    tool_ref=tool.ref,
                    result=str(result),
                )
            return result

    return _IdempotencyAwareTool.from_function(
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
    ) -> tuple[Any, "ResolvedModelConfig", dict[str, "ResolvedModelConfig"]]:
        """`(컴파일된 graph, 이 실행이 실제로 사용한 모델 설정, Child별 resolved_model)`을
        반환한다.

        2026-08-19, §4순위(Run Snapshot) 추가 — 이전에는 graph만 반환하고
        `resolved_model`(아래)은 이 메서드 안에서만 쓰고 버렸다. 호출자
        (`executor.py`)가 `agent_run.resolved_provider`/`resolved_endpoint_hash`
        로 남기려면 이 값이 밖으로 나가야 한다(정본:
        `2026-08-19_01_실행_안정성_설계.md` §1 — "팀 커스텀 엔드포인트는
        같은 agent_version_id로 실행해도 언제든 바뀔 수 있는데, 실제로
        어느 서버로 요청이 나갔는지가 지금까지 실행 로그에 안 남았다").

        2026-08-19, §10순위(Child Run Snapshot) 추가 — 세 번째 반환값
        `child_resolved_models`(`{alias: ResolvedModelConfig}`)는 §4순위가
        `[0]`으로 버렸던 Child 자신의 resolved_model을 Root `build()` 호출
        시점에 alias별로 모아 둔 것이다. Child 그래프는 `subagent_started`
        런타임 이벤트 시점이 아니라 **이 메서드 호출 시점에 전부 한 번에**
        컴파일된다(아래 `compiled_children` — Child는 자기 model을 Root와
        다르게 가질 수 있다, `SubagentDefinition.model`) — 그래서 이벤트가
        나올 때는 이미 늦고, 이렇게 미리 만들어 둔 lookup 표를
        `events.py`의 `EventMapper.convert()`에 넘겨 `subagent_type`(=alias)
        으로 찾아 쓰게 한다(`events.py`가 Child의 agent_id/agent_version_id/
        subagent_name을 `definition.subagents`에서 alias로 찾는 것과
        정확히 같은 패턴 — 모듈 docstring 참고). Child 자신을 짓는 재귀
        호출(`self.build(..., allow_subagents=False)`)은 leaf라 항상 빈
        딕셔너리를 돌려준다(MVP는 위임 1단계로 제한된다 —
        `subagents/validation.py`/`loader.py`/`subagents/builder.py`가 3중
        강제).
        """
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
        # **역할로 도구를 숨기지 않는다**(2026-08-19 정책 변경 — 지훈 확인).
        # 예전엔 여기서 `filter_tools_for_role()`로 `side_effect=True` 도구를
        # `member`에게서 통째로 지웠다 — 그러면 모델이 그 도구를 아예 받은 적이
        # 없어서 "그런 기능이 없다"고 답했는데, 실제로는 권한이 없을 뿐이었다
        # (버그 리포트: 「승인 필요가 붙어있는 툴에 대해서 에이전트가 툴이
        # 존재하지 않는다고 판단」). 실행 허용 여부는 여전히
        # `_to_langchain_tool()`의 `_run()`이 호출 시점에 `is_tool_allowed_for_role()`
        # 로 확인한다 — 2026-08-20부터 기본 정책(`DEFAULT_WRITE_TOOL_ALLOWED_
        # ROLES`)이 `leader`/`member` 둘 다 통과시키므로 지금은 통과하지만,
        # 그 판단이 사라진 게 아니라 값이 바뀐 것뿐이다. 배포에서
        # `write_tool_allowed_roles`를 좁히면(예: `frozenset({"leader"})`)
        # 이 자리는 그대로 다시 막는다.
        langchain_tools = [
            _to_langchain_tool(t, context=context, runtime_policy=self.runtime_policy) for t in tools
        ]

        # 2026-08-18, §5 Phase 7 — `interrupt_on`은 `checkpointer_provider`가
        # 있을 때만 만든다. `HumanInTheLoopMiddleware`의 `interrupt()`는
        # Checkpointer 없이는 재개가 안 되므로(계획 문서 §5 Phase 7: "Phase
        # 1(Checkpointer) 완료 전에는 착수 불가"), Checkpointer가 없는 배포·
        # 테스트에서까지 승인 대기를 걸면 재개할 방법이 없는 상태로 막히기만
        # 한다. `tools`에서 `side_effect=True`고 **이 역할이 실행할 수 있는**
        # 것만 뽑는다 — `langchain_tools`는 역할과 무관하게 전부 보여주지만,
        # 승인 대기는 여전히 `is_tool_allowed_for_role()`을 기준으로 건다.
        #
        # 2026-08-20, 사용자 요청("팀원이 자기 업무를 직접 등록할 수 있게") —
        # 예전엔 이 판단이 `member`에서 항상 `False`라 승인 카드 자체가 안
        # 떴다(팀원이 부르면 위 `_run()`에서 곧바로 `ToolException`으로 거부되니
        # 승인 대기를 걸 이유가 없었다 — "승인 카드를 띄우면 부른 사람 본인이
        # 눌러 승인해 버릴 수 있다"가 그때의 이유였다). 이제 `member`도
        # `write_tool_allowed_roles`에 들어 있어 실행 자체가 허용되므로, **바로
        # 그 이유로** 이 자리가 `member`의 호출도 자동으로 승인 대기에 넣는다 —
        # `leader`가 원래 해 오던 자기 승인(HITL, "등록할까요?" 확인 카드 →
        # 승인 버튼)과 같은 경로를 `member`도 그대로 탄다. 실행 허용과 승인
        # 대기가 같은 함수 하나(`is_tool_allowed_for_role()`)를 보므로 둘이
        # 어긋날 일이 없다 — "실행은 되는데 승인 카드가 안 뜨는" 조합은 이
        # 구조에서 애초에 안 생긴다.
        #
        # Phase 0에서 확인한 값(`task_register`/`task_update`/
        # `jira_create_issues`, MCP 도구 전부)을 하드코딩하지 않고 매 요청
        # 시점의 실제 목록을 그대로 쓴다 — 팀마다 달라지는 MCP 도구나 나중에
        # 추가될 side_effect 도구도 자동으로 포함된다.
        interrupt_on: dict[str, bool] | None = None
        if self.checkpointer_provider is not None:
            side_effect_tools = {
                model_safe_tool_name(t.ref): True
                for t in tools
                if t.side_effect
                and self.runtime_policy.is_tool_allowed_for_role(side_effect=True, account_role=context.role)
            }
            if side_effect_tools:
                interrupt_on = side_effect_tools

        custom_middleware = self.middleware_factory.build(definition=definition, context=context)

        # 공통 Runtime Scaffold + Agent별 system_prompt(DB의 agent_versions.
        # system_prompt, Builder가 작성한 그대로)를 실행 시점에 결합한다
        # (services/agent_runtime/prompts.py 모듈 docstring — 저장 시점이 아니라
        # 여기서 결합해야 공통 정책을 바꿀 때 기존 버전을 다시 발행하지 않아도
        # 된다. 2026-08-14 추가).
        if not allow_subagents:
            # Child는 leaf다(1단계 위임 제한) — 자기 Child를 더 지을 수
            # 없으므로 `child_resolved_models`는 항상 빈 딕셔너리다.
            return (
                create_child_graph(
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
                ),
                resolved_model,
                {},
            )

        # 2026-08-19, §10순위 — Child 각각의 resolved_model을 alias로 모아
        # 둔다(위 build() docstring 참고). `build_subagent()`가 요구하는
        # `build_child_graph` 콜백은 `(AgentDefinition, RuntimeContext) -> Any`
        # 두 인자만 받으므로, alias는 람다의 기본 인자로 미리 묶어 둔다 —
        # 그냥 클로저로 `sub_def.alias`를 참조하면 파이썬의 흔한 반복문
        # 클로저 지연 바인딩 문제(모든 람다가 마지막 `sub_def`를 보게 됨)에
        # 걸린다.
        child_resolved_models: dict[str, "ResolvedModelConfig"] = {}

        def _build_child_graph(d: AgentDefinition, c: RuntimeContext, alias: str) -> Any:
            child_graph, child_resolved, _grandchild_models = self.build(
                definition=d, context=c, allow_subagents=False
            )
            child_resolved_models[alias] = child_resolved
            return child_graph

        compiled_children = [
            build_subagent(
                sub_def,
                context,
                build_child_graph=lambda d, c, _alias=sub_def.alias: _build_child_graph(d, c, _alias),
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
        # 2026-08-19, §1순위 — write_guard(`memory/write_guard.py`)는
        # Root에만 붙는다. Child는 진짜 `StoreBackend`가 없어서(빈
        # `StateBackend`로 떨어진다, `2026-08-15_02_장기메모리_설계.md` §2)
        # `/memories/users/`에 뭘 써도 실제 저장이 안 되므로 필요 없다.
        # `custom_middleware`는 Root/Child가 같은 리스트를 공유하므로(위
        # `self.middleware_factory.build(...)` 결과) 거기 넣지 않고, 이미
        # "memory_provider가 있을 때만 Root에 메모리 관련 값을 채우는" 이
        # 조건 안에서 Root 전용 사본(`root_middleware`)을 따로 만든다 —
        # memory_provider가 없으면 write_guard도 붙일 이유가 없다(막을
        # 개인 장기 메모리 자체가 없다).
        root_middleware = custom_middleware
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
                # 2026-08-19 — 팀 공유 메모리(`/memories/AGENTS.md`,
                # `/memories/projects/*.md`)를 없애기로 하면서
                # `build_filesystem_permissions(project_id=...)` 배선을 여기서
                # 뺐다(정본: 2026-08-19_03_장기메모리_개인전용_최종구조.md §4).
                # 그 규칙이 막던 "같은 팀 안에서 프로젝트 간 메모리 파일 접근"은
                # 그 파일들 자체가 더 이상 팀·에이전트 공유 namespace(장기
                # Store)에 안 가므로 애초에 발생할 수 없다 — 스레드마다 독립된
                # State/checkpoint로 떨어져서, 다른 프로젝트 대화(=다른 스레드)
                # 에서는 구조적으로 안 보인다(그 데이터 자체가 사라진다는
                # 뜻은 아니다 — `memory/backend.py` 모듈 docstring 참고). 격리할
                # 대상이 없어졌으니 이 규칙도 필요 없다.
                # `services/agent_runtime/middleware/permissions.py`의
                # `build_filesystem_permissions()` 자체는 코드로 남겨뒀다(다른
                # 경로별 권한 제어가 필요해지면 재사용).
            )
            # 2026-08-19, §5순위 — write_lock(`memory/write_lock.py`)도 같은
            # 이유로 Root 전용이다(Child는 StoreBackend가 없어 락을 걸
            # 대상이 없다). write_guard 다음에 둔다 — write_guard가 credential/
            # PII/권한 서술을 이유로 이미 거부할 내용이면 Postgres 락을 잡을
            # 필요조차 없다(거부는 handler 호출 전에 끝나므로, write_guard가
            # write_lock보다 바깥쪽에 있어야 한다 — langchain의 wrap_tool_call
            # 체이닝은 middleware 목록 앞쪽이 바깥쪽이다: `_chain_tool_call_wrappers`
            # 실제 소스, "Request flows: first -> ... -> last -> tool"). namespace는
            # 위 `self.memory_provider.backend(...)`가 쓰는 것과 같은
            # `(team_id, agent_id, account_id)` 순서를 그대로 맞춘다 — 같은
            # 계정이 다른 팀/에이전트로 옮기면 다른 namespace여야 하는 이유도
            # 위 backend 호출과 동일하다.
            root_middleware = [
                *custom_middleware,
                build_memory_write_guard(),
                build_memory_write_lock(
                    namespace=(context.team_id, definition.agent_id, context.account_id)
                ),
            ]
        if self.checkpointer_provider is not None:
            root_kwargs["checkpointer"] = self.checkpointer_provider.get()

        return (
            create_root_graph(
                model=model,
                system_prompt=self.prompt_assembler.assemble_root(
                    agent_prompt=definition.system_prompt
                ),
                tools=langchain_tools,
                subagents=[gp_spec, *compiled_children],
                middleware=root_middleware,
                # 2026-08-18, §5 Phase 6 — memory_provider 유무와 무관하게 항상
                # 건다(Filesystem Tool 노출 제한은 메모리 기능과 별개).
                fs_excluded_tools=self.runtime_policy.excluded_builtin_tools,
                # 2026-08-18, §5 Phase 7 — checkpointer_provider가 없으면 위에서
                # None으로 남는다.
                interrupt_on=interrupt_on,
                **root_kwargs,
            ),
            resolved_model,
            child_resolved_models,
        )


__all__ = ["AgentRuntimeFactory", "DependencyGraphSource"]
