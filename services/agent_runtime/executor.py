"""Deep Agent 실행과 스트리밍의 단일 진입점.

정본: docs/작업기록/Deep_Agents/2026-08-13_02_Deep-Agent_런타임_공통_계약_v1.md §13

빌더 테스트 실행과 실제 Chat은 반드시 이 모듈(정확히는 AgentExecutor 하나의
인스턴스)을 거친다 — 두 경로가 서로 다른 조립 코드를 쓰면 테스트에서는 성공하고
실제 대화에서는 실패하는 괴리가 생긴다(01 §15 "테스트 실행과 실제 실행의 차이
방지").

validate_execution_target()은 deepagents·DB에 의존하지 않는 순수 검사라 지금
구현했다. AgentExecutor.run()은 loader/factory/stream_adapter가 전부 미구현이라
구조만 잡아뒀다 — §13.3의 "실행 전 오류(AgentBuildError로 변환해 raise)"와
"스트림 중 오류(terminal error 이벤트로 yield, 예외를 밖으로 던지지 않음)" 구분은
이미 정확히 반영돼 있다. 내부 예외 문자열·스택트레이스를 이벤트에 포함하지
않는 원칙도 지켰다.

⚠ 스파이크 완료(2026-08-13): `EventMapper`는 이제 실제로 동작한다(events.py).
단 **실행(run)마다 새 인스턴스가 필요하다** — 위임을 추적하는 상태(`_pending`,
`_namespace_subagent`)를 갖고 있어서, 여러 run이 인스턴스를 공유하면 상태가
섞인다. 그래서 생성자 주입이 아니라 `event_mapper_factory`(기본값
`EventMapper`)를 받아 `run()` 안에서 매번 새로 만든다. `stream_adapter`가
`runtime.stream(...)`을 호출할 때는 `stream_mode="updates"`만 쓸 것 — 스파이크
결과 그것만으로 6단계 전부 실시간 분류가 됐다(events.py 모듈 docstring 참고).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any

from services.agent_runtime.context import RuntimeContext
from services.agent_runtime.events import EVENT_ERROR, EventMapper
from services.agent_runtime.exceptions import AgentBuildError, AgentRuntimeError, InvalidExecutionTargetError

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
    """초안과 저장된 버전을 동시에 실행하려는 요청을 막는다(§13.2).

    Loader나 Factory를 호출하기 전에 실행한다 — I/O 전에 걸러내는 가장 싼 검사다.
    """
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
    """run_agent()의 실제 구현을 담는 클래스.

    모듈 최상위 함수가 아니라 클래스로 둔 이유: loader/factory/stream_adapter/
    event_mapper를 생성자 주입으로 받아야 테스트에서 각각을 Mock으로 바꿀 수
    있다(02 §17.3 "B는 시그니처를 변경하지 않고 Mock으로 Factory 개발을 먼저
    진행할 수 있다"와 같은 이유).
    """

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
        self.stream_adapter = stream_adapter

    def run(
        self,
        *,
        agent_id: str | None,
        agent_version_id: str | None,
        user_input: str,
        context: RuntimeContext,
        draft: dict | None = None,
    ) -> Iterator[dict[str, Any]]:
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

            runtime = self.factory.build(
                definition=loaded.definition,
                subagent_references=loaded.subagent_references,
                context=context,
            )
        except AgentRuntimeError:
            raise
        except Exception as exc:  # noqa: BLE001 — 의도된 포괄 캐치(§13.3)
            logger.exception("Deep Agent 조립 실패")
            raise AgentBuildError("에이전트를 준비하지 못했습니다.") from exc

        if self.stream_adapter is None:
            raise NotImplementedError(
                "stream_adapter 미구현 — deepagents 스트리밍 스파이크(02 §15) 완료 후 "
                "runtime.stream(...)을 감싸는 어댑터를 만든다."
            )

        event_mapper = self.event_mapper_factory()

        try:
            for raw_event in self.stream_adapter.stream(runtime=runtime, user_input=user_input):
                converted = event_mapper.convert(
                    raw_event, definition=loaded.definition, context=context
                )
                if converted is not None:
                    yield converted
        except Exception:  # noqa: BLE001 — 의도된 포괄 캐치(§13.3)
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
