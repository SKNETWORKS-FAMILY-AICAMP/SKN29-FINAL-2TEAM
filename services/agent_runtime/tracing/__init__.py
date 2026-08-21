"""부모·자식·도구 실행을 추적하고 관측하는 영역.

MVP는 기존 관측성 자산(`agent_run`·`tool_call` 테이블, 작업목록.md 작업10)을
그대로 쓴다 — 이 패키지는 그 적재 로직을 Deep Agent 실행 이벤트(events.py)에
연결하는 자리다.

`trace_events()`가 이 연결의 전부다: 이벤트 스트림을 감싸며 지나가는 이벤트를
보고 `agent_run`/`tool_call`에 적재하고, 이벤트 자체는 손대지 않고 그대로
다시 내보낸다. 실제 INSERT/UPDATE는 `backend/db/agent_platform.py`
(`AgentRunRepository`/`ToolCallRepository`)에 있다 — 새로 만들지 않았다.
"언제 무엇을 기록하는가"의 판단(선기록 패턴, 입력 요약, GeneratorExit도
FAILED로 닫기)도 레거시 harness를 위해 이미 만들어진
`services/harness/trace.py`의 `summarize_input()`을 그대로 재사용한다 —
harness 전용 로직이 아니라 순수 로깅 유틸리티라 재사용에 문제가 없다.

## `services/harness/trace.py`의 컨텍스트매니저 패턴과 다르게 만든 이유

레거시는 트레이싱 호출이 실행 로직과 한 몸이다(`with trace.run(...):` 안에서
직접 모델을 부르고 도구를 실행한다) — 트레이싱이 실패하면 실행 자체도
멈춘다. 새 엔진은 이미 완성된 이벤트 스트림(`executor.run()`의 출력)을 옆에서
지켜만 본다 — 실행과 트레이싱이 분리돼 있다. 그래서 `_record()`의 적재 실패는
로그만 남기고 삼킨다(사용자에게 이미 가고 있는 실제 응답을 끊지 않는다) —
평가 로그가 한 줄 비는 것과 사용자가 답을 못 받는 것은 심각도가 다르다는
판단이다.

## 알려진 한계 (정직하게 기록)

- **`iterations`/`token_in`/`token_out`은 2026-08-21에 채웠다.** 예전엔
  `iterations=0`, 토큰은 `None` 고정이었다("아직 안 잰다"를 정직하게 남긴
  것). 이제 `events.py`의 `EventMapper._count_model_call()`이 모델 노드
  update마다 `usage_metadata`를 누적해 끝나는 이벤트에 실어 보내고, 여기
  `_usage_of()`가 옮겨 적는다 — 이 모듈은 변환된 이벤트만 보므로 원시
  `AIMessage`에 직접 닿을 수 없어서 누계를 세는 자리가 저쪽이다.
  ⚠ **`usage_metadata`가 안 오는 경로가 있다**: `openai_compatible`(팀 커스텀
  엔드포인트)은 `base_url`을 넘기는 순간 `langchain_openai`의 `stream_usage`
  자동 활성화 조건에서 빠진다 — 그 경우 `iterations`만 차고 토큰은 `None`으로
  남는다(0으로 채우지 않는다).
- **`tool_call.error_code`가 레거시보다 거칠다.** 레거시(`trace.error_code_of`)는
  실제 예외 객체(클래스 이름, MCP는 `McpError.code`)를 본다. 여기서는
  langgraph `ToolNode`가 예외를 `ToolMessage(status="error")`로 감싸면서
  원본 예외를 지워 버려서, 이벤트 스트림엔 성공/실패 여부만 남는다 — 실패면
  전부 고정값 `"TOOL_EXECUTION_FAILED"`다.
- **`duration_ms`는 이벤트 도착 시각 기준이다.** `tool_started` 이벤트를 본
  시각부터 `tool_completed` 이벤트를 본 시각까지를 잰다 — 실제 도구 실행
  시간과 이벤트가 스트림에 올라오기까지의 지연이 약간 섞일 수 있다(레거시는
  도구 핸들러 호출 직전/직후를 직접 재서 더 정확하다).
- **Builder 화면에서 아직 이 경로를 안 쓴다** — 지금은 Chat(`apps/chat/
  api_views.py`)에서만 `trace_events()`를 감싼다. Builder Test Run이 나중에
  `executor.run()`을 직접 부르게 되면, `draft`에 `agent_id`가 없는 순수
  초안 시험 실행은 `_start_run()`이 `agent_id` 없음을 보고 자동으로 로그를
  건너뛴다(레거시 `run_ephemeral()`과 같은 이유 — `agent_run.agent_id`는
  NOT NULL이고, 저장 전 시험 실행을 평가 로그에 실제 실행처럼 남기면 안
  된다) — 그 경로가 생겨도 이 파일을 다시 손댈 필요는 없다.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from typing import Any

from django.conf import settings

from backend.db.agent_platform import AgentRunRepository, ToolCallRepository
from services.agent_runtime.events import (
    EVENT_AGENT_STARTED,
    EVENT_AWAITING_CONFIRMATION,
    EVENT_ERROR,
    EVENT_RESULT,
    EVENT_SUBAGENT_COMPLETED,
    EVENT_SUBAGENT_STARTED,
    EVENT_TOOL_COMPLETED,
    EVENT_TOOL_STARTED,
)
from services.harness.trace import summarize_input

logger = logging.getLogger(__name__)


def trace_events(
    events: Iterator[dict[str, Any]],
    *,
    context: Any,
    known_run_ids: tuple[str, ...] = (),
) -> Iterator[dict[str, Any]]:
    """이벤트 스트림을 그대로 통과시키며 `agent_run`/`tool_call`에 적재한다.

    `context`는 `RuntimeContext`다 — `session_id`/`parent_run_id`를 읽는다
    (실행 그 자체의 `run_id`/`agent_id`/`agent_version_id`는 이벤트가 이미
    들고 온다, §14 이벤트 계약).

    스트림이 정상적으로 `result`/`error`로 끝나지 않고 중간에 닫히면
    (소비자가 `GeneratorExit`으로 스트림을 닫는 경우 — 브라우저 이탈 등)
    `finally`에서 그때까지 열려 있던 `agent_run`/`tool_call`을 전부
    FAILED로 정리한다. `RUNNING`/`PENDING`으로 영원히 남는 행이 있으면
    평가가 세는 모수가 조용히 틀린다(레거시 `trace.py`와 같은 이유).

    `known_run_ids`(2026-08-19 추가, §0순위 — HITL resume API): 이 스트림이
    **새로 시작하는 게 아니라 이미 시작됐던 실행을 재개하는** 경우에 그
    `run_id`를 미리 채워 넣는다(`AgentExecutor.resume()` 호출을 감쌀 때 씀).
    `open_run_ids`는 이 함수 호출 하나에 국한된 메모리 상태라, 재개 스트림은
    원래 `EVENT_AGENT_STARTED`를 본 적이 없다 — 미리 채워 두지 않으면
    `_finish_root_run()`이 "이 run은 내가 시작한 게 아니다"로 보고 결과
    이벤트가 와도 `agent_run` 행을 닫지 못한다(그 행은 interrupt 시점에
    `_suspend_run()`이 `PENDING`으로 남겨 둔 채 영원히 그 상태로 남는다).

    2026-08-19, §12순위(채팅 응답 시간 계측) — `result`/`error`/
    `subagent_completed`로 실행이 끝나는 이벤트에 `duration_ms`를 실어
    보낸다(아래 `_finish_root_run()`/`_finish_subagent_run()`). 새 DB
    컬럼은 필요 없다 — `agent_run.started_at`/`ended_at`이 이미 있지만,
    "지금 스트리밍 중인 이 이벤트에 값을 바로 실어 화면에 보여준다"는
    목적에는 DB 왕복 없이 `_start_run()`이 처리한 시각부터
    `time.monotonic()`으로 재는 게 더 가깝다(`tool_call.duration_ms`를
    이미 같은 방식으로 재고 있다, 아래 `open_tool_calls`). **재개
    (resume) 스트림은 이 값이 안 붙는다** — `known_run_ids`로 미리 열어
    둔 run은 이 스트림에서 `_start_run()`을 거친 적이 없어 시작 시각을
    모른다(정직한 한계로 남긴다, 아래 `open_run_started_at` 조회부 참고).
    """

    open_run_ids: set[str] = set(known_run_ids)
    # (run_id, tool_call_id) -> (DB tool_call_id, 시작 시각)
    open_tool_calls: dict[tuple[str, str], tuple[str, float]] = {}
    # run_id -> 시작 시각(§12순위). tool_call과 같은 이유로 실제 벽시계
    # 경과 시간을 잰다 — `known_run_ids`로 미리 연 run은 여기 없으므로
    # 재개 스트림에서는 자연히 duration_ms가 안 붙는다(위 docstring).
    open_run_started_at: dict[str, float] = {}

    try:
        for event in events:
            _record(
                event,
                context=context,
                open_run_ids=open_run_ids,
                open_tool_calls=open_tool_calls,
                open_run_started_at=open_run_started_at,
            )
            yield event
    finally:
        _close_orphans(open_run_ids=open_run_ids, open_tool_calls=open_tool_calls)


def _record(
    event: dict[str, Any],
    *,
    context: Any,
    open_run_ids: set[str],
    open_tool_calls: dict[tuple[str, str], tuple[str, float]],
    open_run_started_at: dict[str, float],
) -> None:
    event_type = event.get("type")
    try:
        if event_type == EVENT_AGENT_STARTED:
            _start_run(
                event,
                context=context,
                open_run_ids=open_run_ids,
                open_run_started_at=open_run_started_at,
                parent_run_id=getattr(context, "parent_run_id", None),
            )
        elif event_type == EVENT_SUBAGENT_STARTED:
            _start_run(
                event,
                context=context,
                open_run_ids=open_run_ids,
                open_run_started_at=open_run_started_at,
                parent_run_id=event.get("parent_run_id"),
            )
        elif event_type in (EVENT_RESULT, EVENT_ERROR):
            _finish_root_run(event, open_run_ids=open_run_ids, open_run_started_at=open_run_started_at)
        elif event_type == EVENT_SUBAGENT_COMPLETED:
            _finish_subagent_run(event, open_run_ids=open_run_ids, open_run_started_at=open_run_started_at)
        elif event_type == EVENT_TOOL_STARTED:
            _begin_tool_call(event, open_run_ids=open_run_ids, open_tool_calls=open_tool_calls)
        elif event_type == EVENT_TOOL_COMPLETED:
            _end_tool_call(event, open_tool_calls=open_tool_calls)
        elif event_type == EVENT_AWAITING_CONFIRMATION:
            _suspend_run(event, open_run_ids=open_run_ids)
    except Exception:  # noqa: BLE001 - 로그 적재 실패가 실제 응답 전달을 막으면 안 된다
        logger.exception("실행 로그 적재 실패: event_type=%s", event_type)


def _start_run(
    event: dict[str, Any],
    *,
    context: Any,
    open_run_ids: set[str],
    open_run_started_at: dict[str, float],
    parent_run_id: str | None,
) -> None:
    run_id = event.get("run_id")
    agent_id = event.get("agent_id")
    if not run_id or not agent_id:
        # agent_id가 없으면(순수 draft 시험 실행) 기록하지 않는다 —
        # agent_run.agent_id는 NOT NULL이고, 저장 전 시험 실행을 평가
        # 로그에 실제 실행처럼 남기면 안 된다(harness run_ephemeral()과 같은
        # 이유). open_run_ids에 안 넣어 두면 이 run_id의 tool_started/
        # tool_completed/종료 이벤트도 자동으로 같이 건너뛴다.
        return
    AgentRunRepository.start_with_id(
        run_id=run_id,
        agent_id=agent_id,
        session_id=getattr(context, "session_id", None),
        parent_run_id=parent_run_id,
        agent_version_id=event.get("agent_version_id"),
        runtime_profile_version=settings.RUNTIME_PROFILE_VERSION,
        # 2026-08-19, §4순위(Run Snapshot) — `executor.py`의 `EVENT_AGENT_STARTED`가
        # 이미 실어 보낸 값을 그대로 옮긴다. §10순위부터는 `EVENT_SUBAGENT_STARTED`도
        # `events.py`가 Child(또는 GP는 Root 폴백) 자신의 값을 채워 보내므로,
        # 여기 `.get()`은 Root/Child 둘 다 실제 값을 받는다 — 이 함수 자체는
        # 그때도 고칠 것이 없었다(제네릭하게 이벤트에서 읽기만 한다).
        resolved_provider=event.get("resolved_provider"),
        resolved_endpoint_hash=event.get("resolved_endpoint_hash"),
    )
    open_run_ids.add(run_id)
    # §12순위(채팅 응답 시간 계측) — 이 run의 벽시계 시작 시각을 기억해 둔다.
    # 재개(resume) 스트림은 `_start_run()`을 거치지 않으므로(§0순위,
    # `EVENT_AGENT_STARTED`를 새로 안 냄) 여기 값이 없다 — 그 경우
    # `_finish_root_run()`/`_finish_subagent_run()`이 `duration_ms`를
    # 자연히 생략한다(트레이드오프는 위 `trace_events()` docstring 참고).
    open_run_started_at[run_id] = time.monotonic()


def _finish_root_run(
    event: dict[str, Any], *, open_run_ids: set[str], open_run_started_at: dict[str, float]
) -> None:
    run_id = event.get("run_id")
    if not run_id or run_id not in open_run_ids:
        return
    status = "DONE" if event.get("type") == EVENT_RESULT else "FAILED"
    AgentRunRepository.finish(run_id=run_id, status=status, **_usage_of(event))
    open_run_ids.discard(run_id)
    _attach_duration_ms(event, run_id=run_id, open_run_started_at=open_run_started_at)


def _finish_subagent_run(
    event: dict[str, Any], *, open_run_ids: set[str], open_run_started_at: dict[str, float]
) -> None:
    run_id = event.get("run_id")
    if not run_id or run_id not in open_run_ids:
        return
    status = "FAILED" if event.get("status") == "FAILED" else "DONE"
    AgentRunRepository.finish(run_id=run_id, status=status, **_usage_of(event))
    open_run_ids.discard(run_id)
    _attach_duration_ms(event, run_id=run_id, open_run_started_at=open_run_started_at)


def _usage_of(event: dict[str, Any]) -> dict[str, Any]:
    """끝나는 이벤트가 실어 온 회전 수·토큰(2026-08-21).

    `events.py`의 `EventMapper`가 모델 호출마다 누계를 세어 `result`/
    `subagent_completed`/`error`에 실어 보낸다 — 여기서는 옮겨 적기만 한다
    (이 모듈은 변환된 이벤트만 보므로 원시 `AIMessage`의 `usage_metadata`에
    닿지 못한다). **값이 없으면 `None`을 그대로 넣는다** — 0으로 채우면
    「안 쟀다」와 「안 썼다」가 같은 모양이 된다.

    필드를 안 실어 보내는 호출자(레거시 테스트, 옛 이벤트)도 그대로 동작한다 —
    2026-08-21 이전과 똑같이 `iterations=0`, 토큰은 `None`이 된다.
    """
    return {
        "iterations": event.get("iterations") or 0,
        "token_in": event.get("token_in"),
        "token_out": event.get("token_out"),
    }


def _attach_duration_ms(
    event: dict[str, Any], *, run_id: str, open_run_started_at: dict[str, float]
) -> None:
    """§12순위(채팅 응답 시간 계측) — 실행이 끝나는 이벤트에 경과 시간을 실어 준다.

    `trace_events()`는 `_record()`가 끝난 뒤 **같은 이벤트 객체**를 그대로
    `yield`하므로(제자리 mutate), 여기서 `event["duration_ms"]`를 채워 두면
    `apps/chat/api_views.py`의 `_relay()`가 그 값을 그대로 화면까지
    내보낸다 — 이 함수 밖에서 손댈 곳이 없다. 시작 시각을 못 찾으면(재개
    스트림 — 위 `trace_events()` docstring 참고) 조용히 아무것도 안 붙인다.
    """
    started = open_run_started_at.pop(run_id, None)
    if started is None:
        return
    event["duration_ms"] = int((time.monotonic() - started) * 1000)


def _suspend_run(event: dict[str, Any], *, open_run_ids: set[str]) -> None:
    """HITL interrupt로 멈춘 실행을 `PENDING`으로 표시한다(2026-08-19, §0순위).

    `finish()`와 다르게 `ended_at`을 채우지 않는다 — 실제로 끝난 게 아니라
    사람의 승인/거부를 기다리는 것뿐이다. 재개(`AgentExecutor.resume()`)
    뒤 실제로 끝나면(`EVENT_RESULT`/`EVENT_ERROR`) 그 시점의 `_finish_root_run()`
    이 정상적으로 `ended_at`을 채운다 — 재개 스트림의 `trace_events(...,
    known_run_ids=(run_id,))`가 이 run_id를 그 스트림의 `open_run_ids`에
    미리 채워 두므로, 여기서 `open_run_ids`에서 빼도(아래) 나중에 못 닫는
    게 아니다(빼는 건 "이 스트림 하나" 기준일 뿐이고, 재개는 새 스트림).

    이걸 안 하면(2026-08-19 이전): interrupt로 멈춘 실행은 `EVENT_RESULT`/
    `EVENT_ERROR` 없이 스트림이 그냥 끝나고, `finally`의 `_close_orphans()`가
    이 run을 `FAILED`로 정리해 버린다 — 승인 대기 중일 뿐인 실행이 실패로
    잘못 기록된다.
    """
    run_id = event.get("run_id")
    if not run_id or run_id not in open_run_ids:
        return
    AgentRunRepository.suspend(run_id=run_id)
    open_run_ids.discard(run_id)


def _begin_tool_call(
    event: dict[str, Any],
    *,
    open_run_ids: set[str],
    open_tool_calls: dict[tuple[str, str], tuple[str, float]],
) -> None:
    run_id = event.get("run_id")
    tool_call_id = event.get("tool_call_id")
    tool_ref = event.get("tool_ref")
    if not run_id or run_id not in open_run_ids or not tool_call_id or not tool_ref:
        # run_id가 open_run_ids에 없으면 그 run 자체가 기록 대상이 아니거나
        # (초안 시험 실행), tool_call_id/tool_ref가 비정상적으로 안 실려 온
        # 경우다 — 조용히 건너뛴다. 이벤트 자체는 trace_events()가 그대로
        # 내보내므로 화면에는 영향이 없다, 로그만 스킵된다.
        return
    db_tool_call_id = ToolCallRepository.begin(
        run_id=run_id, tool_ref=tool_ref, input_summary=summarize_input(event.get("arguments") or {})
    )
    open_tool_calls[(run_id, tool_call_id)] = (db_tool_call_id, time.monotonic())


def _end_tool_call(
    event: dict[str, Any], *, open_tool_calls: dict[tuple[str, str], tuple[str, float]]
) -> None:
    run_id = event.get("run_id")
    tool_call_id = event.get("tool_call_id")
    entry = open_tool_calls.pop((run_id, tool_call_id), None)
    if entry is None:
        return
    db_tool_call_id, started = entry
    status = event.get("status") or "OK"
    ToolCallRepository.end(
        tool_call_id=db_tool_call_id,
        status=status,
        duration_ms=int((time.monotonic() - started) * 1000),
        error_code=None if status == "OK" else "TOOL_EXECUTION_FAILED",
    )


def _close_orphans(
    *,
    open_run_ids: set[str],
    open_tool_calls: dict[tuple[str, str], tuple[str, float]],
) -> None:
    """스트림이 `result`/`error` 없이 닫히면(GeneratorExit 등) 남은 행을 정리한다."""

    for (run_id, _tool_call_id), (db_tool_call_id, started) in list(open_tool_calls.items()):
        try:
            ToolCallRepository.end(
                tool_call_id=db_tool_call_id,
                status="FAILED",
                duration_ms=int((time.monotonic() - started) * 1000),
                error_code="STREAM_CLOSED",
            )
        except Exception:  # noqa: BLE001 - 정리 실패도 삼킨다, 위 _record와 같은 이유
            logger.exception("정리 중 tool_call 종료 실패: run_id=%s", run_id)

    for run_id in list(open_run_ids):
        try:
            AgentRunRepository.finish(run_id=run_id, status="FAILED", iterations=0, token_in=None, token_out=None)
        except Exception:  # noqa: BLE001
            logger.exception("정리 중 agent_run 종료 실패: run_id=%s", run_id)


__all__ = ["trace_events"]
