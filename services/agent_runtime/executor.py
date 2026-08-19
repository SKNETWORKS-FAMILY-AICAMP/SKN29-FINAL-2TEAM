"""Agent 로딩, graph 조립, event stream의 단일 진입점."""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Callable, Iterator, Sequence
from typing import TYPE_CHECKING, Any

from services.agent_runtime.context import RuntimeContext
from services.agent_runtime.events import EVENT_AGENT_STARTED, EVENT_ERROR, EventMapper
from services.agent_runtime.exceptions import AgentBuildError, AgentRuntimeError, InvalidExecutionTargetError
from services.agent_runtime.stream_adapter import DeepAgentStreamAdapter

if TYPE_CHECKING:
    from services.agent_runtime.factory import AgentRuntimeFactory
    from services.agent_runtime.loader import AgentDefinitionLoader

logger = logging.getLogger(__name__)


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
        resume_decisions: Sequence[dict[str, Any]] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """`tool_refs_override`: 이 대화(chat_session)가 저장해 둔 도구
        커스터마이즈(2026-08-18, Chat "+" 버튼). `None`이면 로드된 정의의
        `tool_refs`를 그대로 쓴다 — 값이 있으면(빈 시퀀스 포함) 루트
        에이전트의 `tool_refs`만 통째로 갈아 끼운다. 저장된 `agent_versions`
        행은 안 건드린다 — DB에 남는 건 여전히 원래 값이고, 이 자리에서
        메모리 위의 정의만 바꾼다. 서브 에이전트의 도구는 영향 없다(이
        대화가 직접 부르는 루트만 대상 — 위임 내부까지 커스터마이즈하는 건
        범위 밖).

        `resume_decisions`: 승인 게이트에서 멈춰 있던 실행을 잇는다(2026-08-18).
        값이 있으면 `user_input`은 쓰지 않는다 — 멈춘 자리의 대화는
        Checkpointer에 있고, 이 호출이 하는 일은 보류 중인 `interrupt()`에
        사람의 결정을 돌려주는 것뿐이다. 결정의 **개수는 인터럽트가 요구한
        호출 수와 같아야 한다**(다르면 `HumanInTheLoopMiddleware`가
        `ValueError`) — 그 목록은 `awaiting_confirmation` 이벤트의
        `resume.action_requests`에 담아 두었다.
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

            runtime = self.factory.build(
                definition=loaded.definition,
                subagent_references=loaded.subagent_references,
                context=context,
            )
        except AgentRuntimeError:
            raise
        except Exception as exc:  # noqa: BLE001 - 예상 밖 조립 오류를 공통 예외로 변환
            logger.exception("Deep Agent 조립 실패")
            raise AgentBuildError("에이전트를 준비하지 못했습니다.") from exc

        yield {
            "type": EVENT_AGENT_STARTED,
            "run_id": context.run_id,
            "agent_id": loaded.definition.agent_id,
            "agent_version_id": loaded.definition.agent_version_id,
            "complete": False,
        }

        event_mapper = self.event_mapper_factory()

        try:
            for raw_event in self.stream_adapter.stream(
                runtime=runtime,
                user_input=user_input,
                conversation_messages=conversation_messages,
                # `context.session_id`를 LangGraph의 thread_id로 그대로 쓴다
                # (2026-08-18, §5 Phase 1: Checkpointer 도입). None이면(session_id
                # 없는 호출 — 예: 세션이 없는 스크립트 실행) stream_adapter가
                # 예전과 동일하게 conversation_messages를 그대로 붙이는 경로로
                # 돈다 — `stream_adapter.py` docstring의 결합 전제 참고.
                thread_id=context.session_id,
                # 승인 재개면 새 입력 대신 이 결정을 흘려 넣는다.
                resume=(
                    {"decisions": list(resume_decisions)}
                    if resume_decisions is not None
                    else None
                ),
            ):
                # convert()는 항상 리스트를 반환한다(2026-08-14 재설계) — 모델이
                # 한 AIMessage에 tool_calls를 여러 개 담아 내면(병렬 위임/도구
                # 호출) 원시 이벤트 1개가 공통 이벤트 여러 개로 펼쳐질 수 있다.
                for converted in event_mapper.convert(
                    raw_event, definition=loaded.definition, context=context
                ):
                    yield converted
        except Exception:  # noqa: BLE001 - 열린 stream은 error 이벤트로 종료
            logger.exception(
                "Deep Agent 실행 실패: agent=%s version=%s",
                loaded.definition.agent_id,
                loaded.definition.agent_version_id,
            )
            yield {
                "type": EVENT_ERROR,
                "error_code": "AGENT_EXECUTION_FAILED",
                "message": "에이전트 실행 중 오류가 발생했습니다.",
                "agent_id": loaded.definition.agent_id,
                "agent_version_id": loaded.definition.agent_version_id,
                "run_id": context.run_id,
                "complete": True,
            }

    def resume(
        self,
        *,
        agent_id: str | None,
        agent_version_id: str | None,
        context: RuntimeContext,
        decisions: Sequence[dict[str, Any]],
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
            runtime = self.factory.build(
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

        try:
            for raw_event in self.stream_adapter.stream(
                runtime=runtime,
                resume={"decisions": list(decisions)},
                thread_id=context.session_id,
            ):
                for converted in event_mapper.convert(
                    raw_event, definition=loaded.definition, context=context
                ):
                    yield converted
        except Exception:  # noqa: BLE001 - 열린 stream은 error 이벤트로 종료
            logger.exception(
                "Deep Agent 재개 실패: agent=%s version=%s",
                loaded.definition.agent_id,
                loaded.definition.agent_version_id,
            )
            yield {
                "type": EVENT_ERROR,
                "error_code": "AGENT_EXECUTION_FAILED",
                "message": "에이전트 실행 중 오류가 발생했습니다.",
                "agent_id": loaded.definition.agent_id,
                "agent_version_id": loaded.definition.agent_version_id,
                "run_id": context.run_id,
                "complete": True,
            }
