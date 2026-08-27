"""Agent 로딩, graph 조립, event stream의 단일 진입점."""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Callable, Iterator, Sequence
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from services.agent_runtime.context import RuntimeContext
from services.agent_runtime.events import (
    EVENT_AGENT_STARTED,
    EVENT_AWAITING_CONFIRMATION,
    EVENT_ERROR,
    EventMapper,
)
from services.agent_runtime.exceptions import AgentBuildError, AgentRuntimeError, InvalidExecutionTargetError
from services.agent_runtime.stream_adapter import DeepAgentStreamAdapter

if TYPE_CHECKING:
    from services.agent_runtime.factory import AgentRuntimeFactory
    from services.agent_runtime.loader import AgentDefinitionLoader

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _agent_execution_failure_event(
    exc: Exception,
    *,
    agent_id: str | None,
    agent_version_id: str | None,
    run_id: str | None,
    usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """그래프 실행(`run()`/`resume()`) 중 예외 → `EVENT_ERROR` 이벤트.

    `factory.py`의 `_to_langchain_tool()._run()`과 같은 기준
    (`SPEAKABLE_ERRORS`/`error_code_of()`)을 쓴다 — 같은 판단을 두 곳에서 따로
    하지 않는다.

    말할 수 있는 사유(`ToolInputError`/`RepositoryError`/`OAuthError`)는 원문
    메시지를 그대로 준다. 이걸 일반 문구로 뭉개면 "프로젝트를 못 골랐다"처럼
    사람이 그 자리에서 고칠 수 있는 사유까지 화면에서 사라진다.

    호출 한도 초과(`ModelCallLimitExceededError`/`ToolCallLimitExceededError`)는
    별도로 다룬다 — `exit_behavior="error"`가 그대로 던지는 원문은 영어이고
    "run limit (6/6)"처럼 내부 카운터를 그대로 노출한다. `exit_behavior="end"`로
    바꾸는 대신(모델을 다시 안 부르고 고정 문구만 넣는 방식이라 "지금까지 결과
    정리"가 안 된다) 예외는 그대로 두고 여기서 사람이 읽을 문구로만 바꾼다.

    그 밖은 일반 문구를 쓰고 클래스 이름(또는 MCP 에러 코드)만 `error_code`에
    남긴다 — 문서 원문·토큰이 섞여 있을 수 있는 메시지를 화면에 내보내지 않는다.
    """

    from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
    from langchain.agents.middleware.tool_call_limit import ToolCallLimitExceededError

    from services.harness.runner import SPEAKABLE_ERRORS
    from services.harness.trace import error_code_of

    if isinstance(exc, ModelCallLimitExceededError):
        message = "모델 호출 한도에 도달해 실행이 중단되었습니다. 요청을 더 작은 단위로 나눠 다시 시도해 주세요."
    elif isinstance(exc, ToolCallLimitExceededError):
        message = "도구 호출 한도에 도달해 실행이 중단되었습니다. 요청을 더 작은 단위로 나눠 다시 시도해 주세요."
    elif isinstance(exc, SPEAKABLE_ERRORS):
        message = str(exc)
    else:
        message = "에이전트 실행 중 오류가 발생했습니다."
    return {
        "type": EVENT_ERROR,
        "error_code": error_code_of(exc),
        "message": message,
        "agent_id": agent_id,
        "agent_version_id": agent_version_id,
        "run_id": run_id,
        # 여기까지 쓴 회전 수·토큰. **실패해도 비용은 이미 나갔다** — 실패한
        # 실행만 비워 두면 Usage 합계가 조용히 실제보다 작아진다.
        **(usage or {"iterations": 0, "token_in": None, "token_out": None}),
        "complete": True,
    }


def validate_execution_target(
    *,
    agent_id: str | None,
    agent_version_id: str | None,
    draft: dict | None,
) -> None:
    """draft 또는 저장된 Agent version 중 하나만 선택됐는지 확인한다."""
    has_draft = draft is not None
    has_agent_id = agent_id is not None
    has_version_id = agent_version_id is not None

    if has_draft and (has_agent_id or has_version_id):
        raise InvalidExecutionTargetError(
            "초안과 저장된 에이전트 버전을 동시에 실행할 수 없습니다."
        )

    if not has_draft and not (has_agent_id and has_version_id):
        raise InvalidExecutionTargetError(
            "저장된 실행에는 agent_id와 agent_version_id가 모두 필요합니다."
        )


def _tracing_callbacks() -> list[Any]:
    """Langfuse 콜백을 돌려준다. 키가 없으면 빈 리스트다.

    **지연 import다** — 모듈 맨 위에서 `tracing.callbacks`를 import하면
    `services.agent_runtime.tracing` 패키지(`tracing/__init__.py`)가 먼저
    초기화되는데, 그 파일이 `backend.db.agent_platform`을 끌어온다.
    `agent_platform.py`는 자기 자신이 `services.agent_runtime.subagents.
    validation`을 import하다가(그 결과 이 패키지 `__init__.py` → 이 모듈 →
    여기까지 연쇄로 로드된다) 아직 다 안 만들어진 채로 다시 자기 자신을
    요구받아 `ImportError: cannot import name ... from partially initialized
    module`로 서버 자체가 못 뜨는 걸 실제로 재현·확인했다. 호출 시점으로
    미루면 그때는 두 모듈 다 이미 완전히 로드돼 있어 순환이 안 생긴다.
    """
    from services.agent_runtime.tracing.callbacks import get_langfuse_callback

    callback = get_langfuse_callback()
    return [callback] if callback is not None else []


def _langfuse_trace(
    *,
    context: RuntimeContext,
    agent_id: str,
    agent_version_id: str | None,
    resume_state: dict[str, Any] | None = None,
) -> Any | None:
    from services.agent_runtime.tracing.callbacks import get_langfuse_trace

    metadata = {
        "team_id": context.team_id,
        "account_id": context.account_id,
        "session_id": context.session_id,
        "agent_id": agent_id,
        "agent_version_id": agent_version_id,
        "eval_run_id": context.eval_run_id,
        "case_id": context.eval_case_id,
        "environment": context.environment,
    }
    return get_langfuse_trace(
        run_id=str(context.run_id or ""),
        metadata={key: value for key, value in metadata.items() if value is not None},
        resume_state=resume_state,
    )


def _langfuse_metadata(*, context: RuntimeContext, agent_id: str) -> dict[str, Any]:
    tags = [f"team:{context.team_id}", f"agent:{agent_id}"]
    if context.eval_run_id:
        tags.append(f"eval-run:{context.eval_run_id}")
    if context.eval_case_id:
        tags.append(f"eval-case:{context.eval_case_id}")
    metadata = {
        "langfuse_session_id": context.session_id,
        "langfuse_user_id": context.account_id,
        "langfuse_tags": tags,
        "agent_run_id": context.run_id,
        "eval_run_id": context.eval_run_id,
        "case_id": context.eval_case_id,
        "environment": context.environment,
    }
    return {key: value for key, value in metadata.items() if value is not None}


def _attach_langfuse_trace(event: dict[str, Any], trace_handle: Any | None) -> None:
    if trace_handle is None:
        return
    event["langfuse_trace_id"] = trace_handle.trace_id
    if event.get("type") == EVENT_AWAITING_CONFIRMATION:
        resume_state = event.setdefault("trace_resume_state", {})
        resume_state["langfuse_trace_id"] = trace_handle.trace_id
        resume_state["langfuse_root_observation_id"] = trace_handle.root_observation_id
        resume_state["langfuse_interrupted_at"] = _utc_now()


class AgentExecutor:
    """실행 의존성을 조합하고 공통 이벤트를 순서대로 반환한다."""

    def __init__(
        self,
        *,
        loader: "AgentDefinitionLoader",
        factory: "AgentRuntimeFactory",
        event_mapper_factory: Callable[[], EventMapper] = EventMapper,
        stream_adapter: Any = None,
    ) -> None:
        self.loader = loader
        self.factory = factory
        self.event_mapper_factory = event_mapper_factory
        self.stream_adapter = stream_adapter if stream_adapter is not None else DeepAgentStreamAdapter()

    def run(
        self,
        *,
        agent_id: str | None,
        agent_version_id: str | None,
        user_input: str,
        context: RuntimeContext,
        draft: dict | None = None,
        conversation_messages: Sequence[dict[str, Any]] = (),
        tool_refs_override: Sequence[str] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """`tool_refs_override`: 이 대화(chat_session)가 저장해 둔 도구
        커스터마이즈(2026-08-18, Chat "+" 버튼). `None`이면 로드된 정의의
        `tool_refs`를 그대로 쓴다 — 값이 있으면(빈 시퀀스 포함) 루트
        에이전트의 `tool_refs`만 통째로 갈아 끼운다. 저장된 `agent_versions`
        행은 안 건드린다 — DB에 남는 건 여전히 원래 값이고, 이 자리에서
        메모리 위의 정의만 바꾼다. 서브 에이전트의 도구는 영향 없다(이
        대화가 직접 부르는 루트만 대상 — 위임 내부까지 커스터마이즈하는 건
        범위 밖).
        """

        validate_execution_target(
            agent_id=agent_id, agent_version_id=agent_version_id, draft=draft
        )

        try:
            loaded = (
                self.loader.from_draft(draft=draft, context=context)
                if draft is not None
                else self.loader.load(
                    agent_id=agent_id,
                    agent_version_id=agent_version_id,
                    context=context,
                )
            )
            if tool_refs_override is not None:
                loaded = dataclasses.replace(
                    loaded,
                    definition=dataclasses.replace(
                        loaded.definition, tool_refs=tuple(tool_refs_override)
                    ),
                )

            runtime, resolved_model, child_resolved_models = self.factory.build(
                definition=loaded.definition,
                subagent_references=loaded.subagent_references,
                context=context,
            )
        except AgentRuntimeError:
            raise
        except Exception as exc:  # noqa: BLE001 - 예상 밖 조립 오류를 공통 예외로 변환
            logger.exception("Deep Agent 조립 실패")
            raise AgentBuildError("에이전트를 준비하지 못했습니다.") from exc

        # **모듈 최상단이 아니라 함수 본문에서 import한다.** `agent_platform.py`가
        # 이 패키지를 부르는데, `models.factory`가 다시
        # `agent_platform.CustomModelRepository`를 import해서 순환이 생긴다 —
        # `agent_platform.py`가 초기화되던 중에 자기 자신으로 되돌아온다.
        # 실제 부팅에서만 드러나고 테스트는 이 import 순서를 안 태워 못 잡는다.
        # `factory.py`가 같은 이유로 `TYPE_CHECKING` + 생성자 주입을 쓴다.
        from services.agent_runtime.models.factory import resolved_endpoint_hash

        langfuse_trace = _langfuse_trace(
            context=context,
            agent_id=loaded.definition.agent_id,
            agent_version_id=loaded.definition.agent_version_id,
        )

        yield {
            "type": EVENT_AGENT_STARTED,
            "run_id": context.run_id,
            "agent_id": loaded.definition.agent_id,
            "agent_version_id": loaded.definition.agent_version_id,
            # 이 실행이 실제로 사용한 provider/엔드포인트.
            # `tracing/__init__.py`의 `_start_run()`이 읽어 `agent_run`에 적재한다.
            "resolved_provider": resolved_model.provider,
            "resolved_endpoint_hash": resolved_endpoint_hash(resolved_model),
            "langfuse_trace_id": (
                langfuse_trace.trace_id if langfuse_trace is not None else None
            ),
            "complete": False,
        }

        event_mapper = self.event_mapper_factory()

        # Langfuse 콜백(`tracing/callbacks.py`) — 키가 없으면 빈
        # 리스트라 stream_adapter가 config에 아무것도 안 붙인다.
        # 지연 import 이유는 `_tracing_callbacks()` docstring 참고.
        callbacks = (
            [langfuse_trace.callback]
            if langfuse_trace is not None
            else _tracing_callbacks()
        )

        try:
            for raw_event in self.stream_adapter.stream(
                runtime=runtime,
                user_input=user_input,
                conversation_messages=conversation_messages,
                # `context.session_id`를 LangGraph thread_id로 그대로 쓴다. None이면
                # (세션 없는 스크립트 실행 등) stream_adapter가 conversation_messages를
                # 그대로 붙이는 경로로 돈다 — 그쪽 docstring의 결합 전제 참고.
                thread_id=context.session_id,
                callbacks=callbacks,
                # Langfuse 대시보드에서 세션/계정/팀 단위로 걸러 보기 위한
                # 메타데이터. 콜백이 없으면 아무도 쓰지 않으므로 `None`으로 둔다.
                trace_metadata=(
                    _langfuse_metadata(
                        context=context, agent_id=loaded.definition.agent_id
                    )
                    if callbacks
                    else None
                ),
                # 한 super-step 동시 실행 상한. 정책 값을 그대로 넘긴다.
                max_concurrency=self.factory.runtime_policy.max_concurrency,
            ):
                # `convert()`는 항상 리스트를 반환한다 — 모델이 한 AIMessage에
                # tool_calls를 여러 개 담으면 원시 이벤트 1개가 공통 이벤트
                # 여러 개로 펼쳐진다.
                for converted in event_mapper.convert(
                    raw_event,
                    definition=loaded.definition,
                    context=context,
                    # `factory.build()`가 계산해 둔 Root와 Child별 resolved_model.
                    # `events.py`가 `subagent_started`를 만들 때 alias로 찾아
                    # `resolved_provider`/`resolved_endpoint_hash`를 채운다.
                    root_resolved_model=resolved_model,
                    child_resolved_models=child_resolved_models,
                ):
                    _attach_langfuse_trace(converted, langfuse_trace)
                    yield converted
        except Exception as exc:  # noqa: BLE001 - 열린 stream은 error 이벤트로 종료
            # 여기서는 사유를 가리지 않고 항상 `exception`으로 남긴다. 그래프 실행
            # 자체가 멈춘 드문 경로라, 말할 수 있는 사유였더라도 "왜 여기까지
            # 왔는지"가 운영 로그에 있어야 한다. 화면에 보낼 메시지 분기는
            # `_agent_execution_failure_event()`가 이미 한다.
            logger.exception(
                "Deep Agent 실행 실패: agent=%s version=%s",
                loaded.definition.agent_id,
                loaded.definition.agent_version_id,
            )
            yield _agent_execution_failure_event(
                exc,
                agent_id=loaded.definition.agent_id,
                agent_version_id=loaded.definition.agent_version_id,
                run_id=context.run_id,
                usage=event_mapper.usage_for(context.run_id, close=True),
            )
        finally:
            if langfuse_trace is not None:
                langfuse_trace.finish()

    def resume(
        self,
        *,
        agent_id: str | None,
        agent_version_id: str | None,
        context: RuntimeContext,
        decisions: Sequence[dict[str, Any]],
        trace_resume_state: dict[str, Any] | None = None,
        draft: dict | None = None,
        tool_refs_override: Sequence[str] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """`HumanInTheLoopMiddleware`의 interrupt로 멈춘 실행을 재개한다
        (2026-08-19, §0순위 — 새 엔진 HITL resume API).

        `context.run_id`는 **멈췄던 그 실행의 run_id를 그대로** 받아야 한다
        (호출자 — `apps/chat/api_views.py` — 가 확인 카드에 저장해 둔
        값). 여기서 새로 발급하지 않는다: 새로 발급하면 `agent_run` 행이
        하나 더 느는 게 아니라, interrupt 시점에 이미 `PENDING`으로 남겨 둔
        원래 행을 영영 못 닫는다 — `trace_events()`의 열린 run 추적은 스트림
        하나에 국한된 메모리 상태라(`tracing/__init__.py`), 새 스트림은
        원래 run_id를 모른 채 시작한다. 호출자가 `trace_events(...,
        known_run_ids=(run_id,))`로 그 상태를 미리 채워 넣는 것과 짝을
        이룬다.

        `agent_id`/`agent_version_id`/`draft`/`tool_refs_override`는
        `run()`과 완전히 같은 규칙이다 — 멈췄던 그 실행과 같은 에이전트
        정의로 그래프를 다시 조립해야 재개가 그 실행의 연속으로 보인다
        (checkpointer가 대화 상태를 들고 있지, 그래프 구조 자체를 들고
        있지는 않다 — `stream_adapter.py`의 `resume` 처리 docstring 참고).

        `EVENT_AGENT_STARTED`는 내지 않는다 — 이건 "새로 시작"이 아니라
        "이어서 진행"이라 `trace_events()`가 새 `agent_run` 행을 만들 필요가
        없다(만들면 `run_id` PK 충돌).
        """
        validate_execution_target(agent_id=agent_id, agent_version_id=agent_version_id, draft=draft)
        if context.run_id is None:
            msg = "resume()에는 context.run_id(멈췄던 실행의 run_id)가 있어야 합니다."
            raise ValueError(msg)

        try:
            loaded = (
                self.loader.from_draft(draft=draft, context=context)
                if draft is not None
                else self.loader.load(
                    agent_id=agent_id, agent_version_id=agent_version_id, context=context
                )
            )
            if tool_refs_override is not None:
                loaded = dataclasses.replace(
                    loaded,
                    definition=dataclasses.replace(
                        loaded.definition, tool_refs=tuple(tool_refs_override)
                    ),
                )
            # 재개는 `EVENT_AGENT_STARTED`를 새로 내지 않으므로 Root의
            # `resolved_model`을 다시 기록할 자리가 없다 — 멈추기 전
            # `_start_run()`이 적어 둔 값을 그대로 둔다. 그래도 두 값을 버리지는
            # 않는다: 재개 뒤에 새 위임이 날 수 있고, 그 `subagent_started`의
            # resolved_provider/endpoint_hash를 채우려면 필요하다.
            runtime, resolved_model, child_resolved_models = self.factory.build(
                definition=loaded.definition,
                subagent_references=loaded.subagent_references,
                context=context,
            )
        except AgentRuntimeError:
            raise
        except Exception as exc:  # noqa: BLE001 - 예상 밖 조립 오류를 공통 예외로 변환
            logger.exception("Deep Agent 재개 조립 실패")
            raise AgentBuildError("에이전트를 준비하지 못했습니다.") from exc

        event_mapper = self.event_mapper_factory()
        # interrupt 전 EventMapper가 기억하던 child run/tool_call 상관관계는
        # Python 스트림과 함께 사라진다. 승인 카드에 저장한 최소 상태를 복원해야
        # 서브에이전트 안에서 재개된 ToolMessage도 원래 run/tool 행으로 돌아간다.
        restore_hitl_state = getattr(event_mapper, "restore_hitl_state", None)
        if callable(restore_hitl_state):
            restore_hitl_state(trace_resume_state)

        # Langfuse 콜백 — 승인을 기다리다 재개된 실행도
        # 실제 모델·도구 호출이라 트레이싱에서 뺄 이유가 없다 —
        # `stream_adapter.py`의 `resume` 분기도 이 값을 받게 이미 맞춰 뒀다.
        langfuse_trace = _langfuse_trace(
            context=context,
            agent_id=loaded.definition.agent_id,
            agent_version_id=loaded.definition.agent_version_id,
            resume_state=trace_resume_state,
        )
        callbacks = (
            [langfuse_trace.callback]
            if langfuse_trace is not None
            else _tracing_callbacks()
        )

        try:
            for raw_event in self.stream_adapter.stream(
                runtime=runtime,
                resume={"decisions": list(decisions)},
                thread_id=context.session_id,
                callbacks=callbacks,
                trace_metadata=(
                    _langfuse_metadata(
                        context=context, agent_id=loaded.definition.agent_id
                    )
                    if callbacks
                    else None
                ),
                # 2026-08-21, 병렬실행 Phase 1 — 재개 경로에도 같은 상한을
                # 건다. 승인 후 한꺼번에 풀리는 복수 side-effect 호출이야말로
                # 상한이 필요한 자리다(`2026-08-20_02` §5.1·§8).
                max_concurrency=self.factory.runtime_policy.max_concurrency,
            ):
                for converted in event_mapper.convert(
                    raw_event,
                    definition=loaded.definition,
                    context=context,
                    root_resolved_model=resolved_model,
                    child_resolved_models=child_resolved_models,
                ):
                    _attach_langfuse_trace(converted, langfuse_trace)
                    yield converted
        except Exception as exc:  # noqa: BLE001 - 열린 stream은 error 이벤트로 종료
            logger.exception(
                "Deep Agent 재개 실패: agent=%s version=%s",
                loaded.definition.agent_id,
                loaded.definition.agent_version_id,
            )
            yield _agent_execution_failure_event(
                exc,
                agent_id=loaded.definition.agent_id,
                agent_version_id=loaded.definition.agent_version_id,
                run_id=context.run_id,
                usage=event_mapper.usage_for(context.run_id, close=True),
            )
        finally:
            if langfuse_trace is not None:
                langfuse_trace.finish()
