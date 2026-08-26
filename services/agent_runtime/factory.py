"""모델·Tool·Child·Middleware를 조합해 Deep Agent graph를 만든다."""

from __future__ import annotations

import logging
import random
import time
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
from services.agent_runtime.skills.sync import build_skill_register_sync
from services.agent_runtime.skills.visibility import build_skill_visibility_filter
from services.agent_runtime.hitl_warnings import build_confirmation_description
from services.agent_runtime.prompts import GP_DESCRIPTION
from services.agent_runtime.runtime_policy import GUNICORN_WORKER_TIMEOUT_SECONDS
from services.agent_runtime.subagents.builder import build_subagent
from services.agent_runtime.subagents.validation import validate_subagents
from services.agent_runtime.tools.loader import (
    MCP_TOOL_REF_PREFIX,
    Tool,
    inject_runtime_context,
    model_safe_tool_name,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from services.agent_runtime.checkpoint.provider import CheckpointerProvider
    from services.agent_runtime.memory.provider import MemoryProvider
    from services.agent_runtime.middleware.factory import MiddlewareFactory
    from services.agent_runtime.models.factory import ModelConfigResolver, ModelFactory, ResolvedModelConfig
    from services.agent_runtime.prompts import RuntimePromptAssembler
    from services.agent_runtime.runtime_policy import RuntimeCapabilityPolicy
    from services.agent_runtime.skills.provider import SkillsProvider
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


# 외부 Write Tool Idempotency가 `_run(**kwargs)`까지 `tool_call_id`를 실어
# 보내려고 쓰는 예약 키.
#
# 이 프로젝트 도구는 `args_schema`가 Pydantic 모델이 아니라 원본 JSON Schema
# dict라서 LangChain 표준 `InjectedToolCallId`가 안 먹는다 — `_parse_input()`이
# dict 입력은 스캔 없이 그대로 돌려보낸다. 대신 아래 `_IdempotencyAwareTool`이
# `tool_input` 복사본에 이 키를 얹으면, `_to_args_and_kwargs()`가 dict를 그대로
# kwargs화하면서 `_run()`까지 살아남는다.
_TOOL_CALL_ID_KWARG = "__langchain_tool_call_id__"
_SKILL_REGISTER_REF = "skill_register"

# 조회 도구 자동 재시도(`tool_failure_recovery_v0.md` §3.1). 최초 호출을 포함해
# 최대 이 횟수만큼 실행하므로 자동 재시도는 `_MAX_TOOL_CALL_ATTEMPTS - 1`회다.
_MAX_TOOL_CALL_ATTEMPTS = 3
_RETRY_BACKOFF_BASE_SECONDS = 0.2
_TRANSIENT_MCP_ERROR_CODES = frozenset({"timeout", "unreachable", "429"})
_TRANSIENT_HTTP_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
_MAX_TRANSIENT_FAILURE_CHAIN_DEPTH = 5


def _is_transient_tool_failure(exc: BaseException | None, *, _depth: int = 0) -> bool:
    """도구 실패가 자동 재시도 대상인 "일시적 기술 오류"인지 판단한다.

    `exc` 자체뿐 아니라 `__cause__`/`__context__` 체인도 확인한다. Jira·Drive
    커넥터(`apps/connectors/clients.py`)는 `raise OAuthError(...) from exc`처럼
    원인 예외를 감싸 다시 던지므로, 겉보기 타입만으로는 timeout·429·5xx를 가려낼
    수 없다.
    """

    if exc is None or _depth > _MAX_TRANSIENT_FAILURE_CHAIN_DEPTH:
        return False

    from services.mcp import McpError

    if isinstance(exc, McpError):
        if exc.code in _TRANSIENT_MCP_ERROR_CODES:
            return True
    else:
        import requests

        if isinstance(exc, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
            return True
        if isinstance(exc, requests.exceptions.HTTPError):
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if status_code in _TRANSIENT_HTTP_STATUS_CODES:
                return True

    next_exc = exc.__cause__ or exc.__context__
    if next_exc is exc:
        return False
    return _is_transient_tool_failure(next_exc, _depth=_depth + 1)


def _call_tool_handler(tool: Tool, resolved: dict[str, Any]) -> Any:
    """`tool.handler(**resolved)`를 부른다.

    읽기 전용 도구(`side_effect=False`)의 일시적 기술 오류만 최초 호출 포함
    최대 `_MAX_TOOL_CALL_ATTEMPTS`회까지 자동 재시도한다. 쓰기 도구는 재시도하면
    중복 생성·중복 변경이 생길 수 있어 절대 재시도하지 않는다
    (`tool_failure_recovery_v0.md` §3.3). 인증·권한·입력 오류 같은 영구 오류와
    검색 결과 부족도 대상이 아니다 — 다시 불러도 같은 결과이거나 애초에 기술
    장애가 아니다.
    """

    attempt = 0
    while True:
        attempt += 1
        try:
            result = tool.handler(**resolved)
        except Exception as exc:  # noqa: BLE001 - 재시도 가능성만 판단하고 그대로 다시 던진다
            can_retry = (
                not tool.side_effect
                and attempt < _MAX_TOOL_CALL_ATTEMPTS
                and _is_transient_tool_failure(exc)
            )
            if not can_retry:
                raise
            backoff = _RETRY_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
            backoff += random.uniform(0, backoff)
            logger.warning(
                "일시적 도구 실패로 재시도: %s (attempt=%d/%d, error=%s)",
                tool.ref,
                attempt,
                _MAX_TOOL_CALL_ATTEMPTS,
                exc.__class__.__name__,
            )
            time.sleep(backoff)
            continue
        else:
            if attempt > 1:
                logger.info(
                    "재시도 후 복구: %s (attempt=%d/%d)",
                    tool.ref,
                    attempt,
                    _MAX_TOOL_CALL_ATTEMPTS,
                )
            return result


def _tool_description_for_context(tool: Tool, *, context: RuntimeContext) -> str:
    if tool.ref != _SKILL_REGISTER_REF:
        return tool.description
    if context.role == "leader":
        role_rule = "PERSONAL과 TEAM 범위 등록을 요청할 수 있습니다."
    else:
        role_rule = "PERSONAL 범위만 등록할 수 있으므로 TEAM 범위로 호출하지 마세요."
    return f"{tool.description}\n\n현재 요청자 역할은 '{context.role}'입니다. {role_rule}"


def _skill_register_requires_confirmation(request: Any, *, account_role: str) -> bool:
    tool_call = getattr(request, "tool_call", {}) or {}
    arguments = tool_call.get("args") or {}
    scope = str(arguments.get("scope") or "").upper()
    return not (account_role != "leader" and scope == "TEAM")


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

    권한 확인은 **이 도구가 실제로 실행되는 시점**(`_run()` 호출마다)에만 한다.
    모델에게 무엇을 보여줄지는 역할과 무관하므로 이 실행 시점 확인이 **유일한
    방어선**이다 — `is_tool_allowed_for_role()`이 `False`를 돌려주면 `_run()`이
    `ToolException`으로 사유를 말하고 끝낸다(대화는 안 끊긴다).

    **노출 시점에는 거르지 않는다.** 목록에서 지우면 모델이 도구 존재 자체를
    몰라 "그런 기능이 없다"고 답한다 — 실제로는 권한이 없을 뿐인데. 존재를
    숨기는 대신 실행하려 할 때 이유를 알려준다.
    """

    def _run(**kwargs: Any) -> Any:
        # `_IdempotencyAwareTool.run()`이 실어 보낸 값. RBAC 검사보다 먼저 뗀다 —
        # 권한이 없어 막힐 도구라도 이 예약 키가 `tool.handler()`로 흘러들면 안 된다.
        langchain_tool_call_id = kwargs.pop(_TOOL_CALL_ID_KWARG, None)

        if not runtime_policy.is_tool_allowed_for_role(
            side_effect=tool.side_effect, account_role=context.role
        ):
            # 대화를 끊지 않고 말할 수 있는 실패로 돌려준다. 도구가 역할과 무관하게
            # 항상 노출되므로 권한 없는 호출은 이상 상황이 아니라 정상 경로다 —
            # 크래시로 끝내면 "권한이 없다"는 사유가 사라지고 "요청을 끝내지
            # 못했습니다"만 남는다.
            #
            # 기본 정책(`DEFAULT_WRITE_TOOL_ALLOWED_ROLES`)은 leader/member 둘 다
            # 통과시키므로 지금 정의된 두 역할로는 이 분기가 안 걸린다.
            # `write_tool_allowed_roles`를 좁히거나 역할이 늘 때를 위한 방어선이다.
            raise ToolException(
                f"'{context.role}' 역할은 '{tool.ref}' 도구를 실행할 권한이 없습니다. 팀장에게 요청해 주세요."
            )

        # HITL resume이나 checkpoint 재시도로 같은 super-step이 다시 돌아도
        # `jira_create_issues` 같은 side_effect 도구가 두 번 실행되지 않게, 같은
        # (run_id, langchain_tool_call_id)로 이미 성공한 결과가 있는지 먼저 본다.
        # 읽기 도구는 두 번 돌아도 무해하므로 대상이 아니다. 둘 다 있을 때만
        # 확인한다 — run_id 없이 도구를 직접 부르는 호출자(테스트)를 깨지 않는다.
        # 표 설계 근거: DB/migrations/2026-08-19_tool_call_idempotency.sql
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

        # MCP 호출이 "지금 도는 중"이라고 표시한다(`2026-08-21_04` §3.1). 승인
        # 카드가 이 표시를 보고 "같은 서버에 다른 실행이 진행 중"을 알린다.
        # 직렬화가 아니라 경고라서 여기서 기다리는 코드는 없다.
        #
        # 이 자리인 이유: raw MCP handler(`tools/adapters.py`)에는 run_id도
        # tool_call_id도 안 넘어간다. idempotency 기록과 같은 자리를 쓴다.
        active_scope = (
            tool.ref.startswith(MCP_TOOL_REF_PREFIX)
            and langchain_tool_call_id
            and context.run_id
        )
        if active_scope:
            from backend.db.agent_platform import McpCallNoteRepository

            McpCallNoteRepository.begin_active(
                run_id=context.run_id,
                langchain_tool_call_id=langchain_tool_call_id,
                tool_ref=tool.ref,
                team_id=context.team_id,
            )

        resolved = inject_runtime_context(tool, kwargs, context)
        try:
            result = _call_tool_handler(tool, resolved)
        except Exception as exc:  # noqa: BLE001 - 도구 실패로 그래프 실행 전체를 끝내지 않는다
            # `ToolNode`의 기본 `handle_tool_errors`는 `ToolInvocationError`(인자
            # 스키마 검증 실패)만 잡고 나머지는 다시 raise한다. `create_agent()`가
            # 내부에서 만드는 ToolNode라 우리가 값을 넣을 수도 없다. 그대로 두면
            # `ToolInputError`처럼 "모델에게 보여줘도 되는 실패"까지 그래프 실행
            # 전체를 죽여서, 모델이 오류를 보고 스스로 고칠 기회가 사라진다.
            #
            # `SPEAKABLE_ERRORS`(`ToolInputError`/`RepositoryError`/`OAuthError`)는
            # `services/harness/runner.py`가 "이 예외 메시지는 사람에게 그대로 보여도
            # 된다"고 정해 둔 목록이고, `error_code_of()`는 MCP 에러 code와 그 외
            # 클래스 이름을 가르는 자리다. 여기서 새로 판단하지 않고 재사용한다.
            #
            # **어느 쪽이든 정상 반환이 아니라 `ToolException`으로 던진다.** 그냥
            # `return` 하면 `tool_completed.status`가 OK로 남아 진짜 장애가 "도구가
            # 뭐라고 했다"로 둔갑한다. `handle_tool_error=True`와 짝이라
            # `BaseTool.run()`이 문자열로 모델에 넘기면서 `status="error"`는 지킨다.
            #
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
            # 같은 (run_id, langchain_tool_call_id)로 재시도가 들어오면 다시
            # 실행하지 않고 이 결과를 돌려줄 수 있게 남긴다. `BaseTool.run()`도
            # `ToolMessage.content`를 만들 때 결국 문자열로 바꾸므로, `str()`로
            # 통일해도 모델이 보는 최종 내용은 같다.
            if idempotency_scope:
                from backend.db.agent_platform import ToolCallIdempotencyRepository

                ToolCallIdempotencyRepository.record_result(
                    run_id=context.run_id,
                    langchain_tool_call_id=langchain_tool_call_id,
                    tool_ref=tool.ref,
                    result=str(result),
                )
            return result
        finally:
            # 성공이든 실패든 "도는 중" 표시를 지운다. `else`가 아니라 `finally`인
            # 이유: 위 `except`가 다시 raise하므로 실패한 호출의 표시가 영원히
            # 남는다. timeout이 나도 여기까지 온다 — timeout 미들웨어는 기다리기를
            # 포기할 뿐 이 스레드를 죽이지 못한다.
            #
            # 지우기가 실패해도 도구 실행 결과를 뒤집지 않는다 — 경고용 부가
            # 정보지 실행의 일부가 아니다. 남은 행은 조회 시점의 stale 필터가
            # 걸러 낸다.
            if active_scope:
                from backend.db.agent_platform import McpCallNoteRepository

                try:
                    McpCallNoteRepository.end_active(
                        run_id=context.run_id,
                        langchain_tool_call_id=langchain_tool_call_id,
                    )
                except Exception:  # noqa: BLE001 - 경고용 부가 정보다
                    logger.warning(
                        "MCP 실행 중 표시를 지우지 못했다: %s (run_id=%s, tool_call_id=%s)",
                        tool.ref,
                        context.run_id,
                        langchain_tool_call_id,
                        exc_info=True,
                    )

    return _IdempotencyAwareTool.from_function(
        func=_run,
        handle_tool_error=True,
        # `tool.name`이 아니라 `tool.ref`다. `tool.name`은 `harness/registry.py`의
        # BUILTIN_TOOLS가 채우는 한국어 라벨(예: "프로젝트 조회")이라, 모델에 나가는
        # 함수 이름으로 쓰면 OpenAI가 400으로 거절한다 — 함수 이름은
        # `^[a-zA-Z0-9_-]+$`만 허용한다. `model_safe_tool_name()`(tools/loader.py)이
        # 콜론까지 치환한다(`:` → `__`, `agent:`/`mcp:` 접두사 대비). 되돌리는
        # `tool_ref_from_model_name()`은 `events.py`가 모델의 tool_calls에서
        # tool_ref를 다시 읽을 때 쓴다 — 없으면 실행 로그에 `mcp__MT001`처럼
        # 망가진 값이 남는다.
        name=model_safe_tool_name(tool.ref),
        description=_tool_description_for_context(tool, context=context),
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
        skills_provider: "SkillsProvider | None" = None,
    ) -> None:
        self.dependency_graph = dependency_graph
        self.model_config_resolver = model_config_resolver
        self.model_factory = model_factory
        self.tool_loader = tool_loader
        self.middleware_factory = middleware_factory
        self.runtime_policy = runtime_policy
        self.prompt_assembler = prompt_assembler
        # None이면 `build()`가 memory/backend/store 없이 돈다 — 장기 메모리 없이
        # 쓰는 호출자(테스트 등)를 위한 것이다.
        self.memory_provider = memory_provider
        # None이면 `build()`가 checkpointer 없이 돌고, `stream_adapter.py`도 매 턴
        # conversation_messages를 그대로 붙이는 경로를 탄다(그쪽 docstring 참고).
        self.checkpointer_provider = checkpointer_provider
        # memory_provider와 같은 이유로 기본값 None 허용(2026-08-21 추가,
        # 설계 문서 "저장 구조" 절). None이면 build()가 Skill 없이 예전과
        # 동일하게 돈다.
        #
        # 2026-08-25 — memory_provider 유무와 독립적으로 붙는다. Skill이 쓰는
        # backend(라우터 객체)는 memory_provider가 있으면 그게 만든 것에
        # 얹히고, 없으면 `build()`가 Skill 전용 backend를 따로 만든다 —
        # `build()`의 "공유 backend/스토어" 절 참고. Skill이 필요로 하는 건
        # "장기 저장 가능한 backend 하나"뿐이지 메모리 그 자체가 아니다.
        self.skills_provider = skills_provider

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

        `resolved_model`을 밖으로 내보내는 이유: 팀 커스텀 엔드포인트는 같은
        agent_version_id로 실행해도 바뀔 수 있어서, 호출자(`executor.py`)가
        `agent_run.resolved_provider`/`resolved_endpoint_hash`에 실제로 어느
        서버로 나갔는지를 남긴다. 정본: `2026-08-19_01_실행_안정성_설계.md` §1.

        `child_resolved_models`(`{alias: ResolvedModelConfig}`)는 Child별
        resolved_model의 lookup 표다. Child 그래프는 `subagent_started` 이벤트
        시점이 아니라 **이 메서드 호출 시점에 전부 한 번에** 컴파일되므로(아래
        `compiled_children`), 이벤트가 날 때는 이미 늦다. `events.py`의
        `EventMapper.convert()`가 `subagent_type`(=alias)으로 찾아 쓴다.
        Child 자신을 짓는 재귀 호출은 leaf라 항상 빈 딕셔너리를 돌려준다
        (위임 1단계 제한 — `subagents/validation.py`/`loader.py`/
        `subagents/builder.py`가 3중으로 강제).
        """
        # `allow_subagents`는 Root/Child 그래프 중 무엇을 지을지만 가른다 —
        # "이 Child가 이미 서브 에이전트를 갖고 있는가" 검사와는 무관하다.
        # `validate_subagents()`는 그 검사를 항상 켜 둔다.
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
        # **역할로 도구를 숨기지 않는다.** 목록에서 지우면 모델이 그 도구를 받은
        # 적이 없어 "그런 기능이 없다"고 답한다. 실행 허용 여부는
        # `_to_langchain_tool()`의 `_run()`이 호출 시점에
        # `is_tool_allowed_for_role()`로 확인한다.
        langchain_tools = [
            _to_langchain_tool(t, context=context, runtime_policy=self.runtime_policy) for t in tools
        ]

        # `interrupt_on`은 `checkpointer_provider`가 있을 때만 만든다.
        # `HumanInTheLoopMiddleware`의 `interrupt()`는 Checkpointer 없이는 재개가
        # 안 되므로, 없는 배포·테스트에서 승인 대기를 걸면 풀 방법 없이 막힌다.
        #
        # `langchain_tools`는 역할과 무관하게 전부 노출하지만, 승인 대기는
        # `is_tool_allowed_for_role()`을 기준으로 건다. 실행 허용과 승인 대기가
        # 같은 함수를 보므로 "실행은 되는데 승인 카드가 안 뜨는" 조합은 안 생긴다.
        #
        # 도구 목록을 하드코딩하지 않고 매 요청 시점의 실제 목록을 쓴다 — 팀마다
        # 다른 MCP 도구나 나중에 추가될 side_effect 도구도 자동으로 포함된다.
        #
        # MCP 도구만 `True` 대신 `InterruptOnConfig`를 준다. `description` 콜백으로
        # 승인 카드에 "같은 서버에 다른 작업이 도는 중"·"이 도구가 방금 timeout났다"
        # 같은 경고를 붙이기 위해서다(`hitl_warnings.py`). 내장 도구는 우리가 코드를
        # 아는 로컬 도구라 동시 실행을 lock으로 직렬화하지, 경고로 넘기지 않는다.
        #
        # `allowed_decisions`는 `True`가 펼쳐 주는 값과 같게 적는다
        # (`HumanInTheLoopMiddleware.__init__`이 `True`를 이 네 개로 편다) —
        # 좁히면 지금 되던 승인·편집이 조용히 사라진다.
        interrupt_on: dict[str, Any] | None = None
        if self.checkpointer_provider is not None:
            allowed_side_effect = self.runtime_policy.is_tool_allowed_for_role(
                side_effect=True, account_role=context.role
            )
            describe = build_confirmation_description(
                context=context,
                stale_after_seconds=GUNICORN_WORKER_TIMEOUT_SECONDS,
            )
            side_effect_tools: dict[str, Any] = {}
            for tool in tools:
                if not tool.side_effect or not allowed_side_effect:
                    continue
                confirmation: Any = True
                if tool.ref.startswith(MCP_TOOL_REF_PREFIX):
                    confirmation = {
                        "allowed_decisions": ["approve", "edit", "reject", "respond"],
                        "description": describe,
                    }
                elif tool.ref == _SKILL_REGISTER_REF:
                    confirmation = {
                        "allowed_decisions": ["approve", "edit", "reject", "respond"],
                        "when": lambda request, role=context.role: _skill_register_requires_confirmation(
                            request, account_role=role
                        ),
                    }
                side_effect_tools[model_safe_tool_name(tool.ref)] = confirmation
            # `delete`(deepagents 기본 파일시스템 Tool, 2026-08-26 재활성화)는
            # 이 프로젝트가 등록한 `tools` 목록에 없어서 위 루프를 안 탄다 —
            # 여기서 따로 넣어야 다른 부수효과 도구와 똑같이 승인을 거친다.
            if allowed_side_effect and "delete" not in self.runtime_policy.excluded_builtin_tools:
                side_effect_tools["delete"] = True
            if side_effect_tools:
                interrupt_on = side_effect_tools

        custom_middleware = self.middleware_factory.build(definition=definition, context=context)

        # 공통 Runtime Scaffold + Agent별 system_prompt(`agent_versions.
        # system_prompt`)를 실행 시점에 결합한다. 저장 시점이 아니라 여기서
        # 결합해야 공통 정책을 바꿀 때 기존 버전을 다시 발행하지 않아도 된다
        # (`prompts.py` 모듈 docstring).
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
                    # Root와 같은 근거로 Child에도 건다
                    # (`create_child_graph()` docstring 참고).
                    fs_excluded_tools=self.runtime_policy.excluded_builtin_tools,
                    interrupt_on=interrupt_on,
                ),
                resolved_model,
                {},
            )

        # Child 각각의 resolved_model을 alias로 모아 둔다(위 docstring 참고).
        # `build_child_graph` 콜백은 `(AgentDefinition, RuntimeContext)` 두 인자만
        # 받으므로 alias는 람다 기본 인자로 묶는다 — 클로저로 `sub_def.alias`를
        # 참조하면 지연 바인딩으로 모든 람다가 마지막 `sub_def`를 보게 된다.
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
        # GP에게는 `side_effect=True` 도구(쓰기·전송·삭제)를 물려주지 않는다.
        # `tools`/`langchain_tools`는 같은 순서라 `zip()`으로 짝지어 거른다.
        #
        # `"tools"` 키를 비우면 안 된다 — deepagents `graph.py`가
        # `spec.get("tools") if "tools" in spec else tools`로 fallback해서 GP가
        # Root 전체를 그대로 상속한다.
        #
        # GP는 Root마다 항상 붙는다. 조회 도구만 쓸 수 있어 위험하지 않으므로
        # 켜고 끄는 스위치를 두지 않는다.
        gp_read_only_tools = [
            lt for t, lt in zip(tools, langchain_tools) if not t.side_effect
        ]
        # 2026-08-21, Skill 배선 — 2026-08-25부터 memory_provider와 무관하게
        # skills_provider만 있으면 계산한다(아래 "공유 backend/스토어" 절 참고).
        # GP에 여기서 명시적으로 넘기는 이유는 `build_general_purpose_spec()`
        # docstring 참고 — deepagents 기본 GP만 top-level `skills=`를 자동으로
        # 물려받고, 이 저장소는 항상 GP를 직접 만들어 넘기므로 자동 상속 경로를
        # 안 탄다.
        skill_sources = self.skills_provider.sources() if self.skills_provider is not None else []
        gp_spec = build_general_purpose_spec(
            middleware=self.middleware_factory.build_for_general_purpose(),
            system_prompt=self.prompt_assembler.assemble_general_purpose(
                gp_prompt=default_general_purpose_prompt()
            ),
            description=GP_DESCRIPTION,
            tools=gp_read_only_tools,
            skills=skill_sources or None,
        )

        # Root에만 붙는 선택적 협력자들 — Child(위 allow_subagents=False 분기)는
        # 둘 다 안 받는다.
        root_kwargs: dict[str, Any] = {}
        # write_guard(`memory/write_guard.py`)는 Root 전용이다. Child는 진짜
        # `StoreBackend`가 없어(빈 `StateBackend`로 떨어진다) `/memories/users/`에
        # 써도 저장이 안 되므로 막을 대상이 없다. `custom_middleware`는 Root/Child가
        # 공유하는 리스트라 거기 넣지 않고 Root 전용 사본을 따로 만든다.
        root_middleware = custom_middleware

        # 공유 backend/스토어 — Memory와 Skill이 같이 쓴다.
        #
        # deepagents는 에이전트 하나에 파일 경로 라우터(`backend=`)를 하나만
        # 받는다. 그 라우터를 누가 만드느냐가 2026-08-25 전까지는 항상
        # Memory였다(`memory_provider`가 없으면 Skill도 얹을 자리가 없었다).
        # 이제는 **누구든 먼저 필요로 하는 쪽이 만든다**:
        # - memory_provider가 있으면 그게 라우터를 만들고(`/memories/users/`
        #   경로 포함), Skill 라우트는 거기에 병합된다(기존과 동일).
        # - memory_provider가 없고 skills_provider만 있으면, Skill 전용
        #   라우터를 따로 만든다 — `/memories/users/` 경로는 아예 없다.
        skill_extra_routes = (
            self.skills_provider.routes(account_id=context.account_id, team_id=context.team_id)
            if self.skills_provider is not None
            else None
        )
        shared_backend: Any = None
        shared_store: Any = None
        if self.memory_provider is not None:
            shared_backend = self.memory_provider.backend(
                team_id=context.team_id,
                agent_id=definition.agent_id,
                account_id=context.account_id,
                extra_routes=skill_extra_routes,
            )
            shared_store = self.memory_provider.store()
        elif skill_extra_routes:
            # 지연 import — deepagents.backends는 deepagents 전체를 끌고 들어온다.
            from deepagents.backends import CompositeBackend, StateBackend

            shared_backend = CompositeBackend(default=StateBackend(), routes=skill_extra_routes)
            # 같은 프로세스 전역 Postgres Store 싱글턴을 재사용한다 — Memory
            # 전용 인프라가 아니라 이 저장소가 쓰는 장기 저장소 자체다
            # (`skills/provider.py`의 `store()` 참고).
            shared_store = self.skills_provider.store()

        if shared_backend is not None:
            root_kwargs["backend"] = shared_backend
            root_kwargs["store"] = shared_store
            if self.memory_provider is not None:
                root_kwargs["memory"] = self.memory_provider.paths()
                # `MemoryMiddleware.system_prompt`에 라우팅 안내를 이어붙인다.
                # `create_root_graph()`가 이 값으로 커스텀 MemoryMiddleware를
                # 만들어 자동 생성분을 치환한다.
                root_kwargs["memory_system_prompt"] = self.memory_provider.system_prompt()
                # 여기에 `build_filesystem_permissions(project_id=...)`는 배선하지
                # 않는다. 메모리가 개인 전용이 되면서 프로젝트 간 접근 자체가
                # 구조적으로 불가능해졌다(`memory/backend.py` docstring). 함수
                # 자체는 `middleware/permissions.py`에 남아 있다(재사용 대비).
            if self.skills_provider is not None:
                # skills 소스가 없으면 `create_root_graph`가 이 값을 무시한다.
                root_kwargs["skills_system_prompt"] = self.skills_provider.system_prompt()
            if skill_sources:
                root_kwargs["skills"] = skill_sources

        if self.memory_provider is not None:
            # write_guard/write_lock(`memory/write_guard.py`,
            # `memory/write_lock.py`)은 `/memories/users/` 쓰기 전용 안전장치라
            # memory_provider가 있을 때만 의미가 있다 — 스킬 전용 backend에는
            # 그 경로 자체가 없다.
            #
            # **순서가 중요하다** — write_guard가 먼저다. guard가 credential/PII/
            # 권한 서술을 이유로 거부할 내용이면 Postgres 락을 잡을 필요조차 없다.
            # langchain의 `wrap_tool_call` 체이닝은 목록 앞쪽이 바깥쪽이다
            # (`_chain_tool_call_wrappers`: "Request flows: first -> ... -> tool").
            #
            # namespace는 위 `backend(...)` 호출과 같은
            # `(team_id, agent_id, account_id)` 순서를 맞춘다.
            root_middleware = [
                *custom_middleware,
                build_memory_write_guard(),
                build_memory_write_lock(
                    namespace=(context.team_id, definition.agent_id, context.account_id)
                ),
            ]

        # skill_register 직후 재스캔(2026-08-26) — 메모리 유무와 무관하게,
        # 스킬 자체가 실제로 붙어 있을 때만(=root_kwargs에 "skills"가 있을
        # 때만) 의미가 있다. `shared_backend`는 위에서 memory_provider 유무와
        # 무관하게 이미 정해져 있다.
        if shared_backend is not None and skill_sources:
            root_middleware = [
                *root_middleware,
                build_skill_register_sync(backend=shared_backend),
                # 비활성화된 스킬 걸러내기(2026-08-26, §7) — deepagents의
                # SkillsMiddleware(4-9에서 조립)가 먼저 전체를 읽은 뒤,
                # before_agent 체인에서 이 미들웨어가 그 뒤를 잇는다
                # (`skills/visibility.py` docstring의 순서 근거 참고).
                build_skill_visibility_filter(),
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
                # memory_provider 유무와 무관하게 항상 건다 — Filesystem Tool
                # 노출 제한은 메모리 기능과 별개다.
                fs_excluded_tools=self.runtime_policy.excluded_builtin_tools,
                # checkpointer_provider가 없으면 위에서 None으로 남는다.
                interrupt_on=interrupt_on,
                **root_kwargs,
            ),
            resolved_model,
            child_resolved_models,
        )


__all__ = ["AgentRuntimeFactory", "DependencyGraphSource"]
