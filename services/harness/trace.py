"""실행 로그의 **선기록** 순서.

SQL 은 `backend/db/agent_platform.py` 에 있다. 이 모듈은 "언제 무엇을 기록하는가"
만 정한다 — 로그가 남는 조건이 호출자마다 다르면 평가가 세는 모수가 흔들린다.

핵심 규칙 하나: **실행 전에 남기고 끝난 뒤 갱신한다.** 끝나고 한 번에 쓰면
타임아웃이나 프로세스 종료로 죽은 호출이 로그에서 통째로 사라진다. 정작
조사해야 할 것이 그 호출이다.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Iterator

from backend.db.agent_platform import AgentRunRepository, ToolCallRepository

#: 인자 요약의 최대 길이. tool_call.input_summary 는 TEXT 라 길이 제한은 없지만,
#: 원본 인자를 통째로 남기면 자격증명·문서 원문이 로그에 흘러든다.
INPUT_SUMMARY_MAX = 200


def summarize_input(arguments: dict[str, Any]) -> str:
    """무엇을 넣었는지 알아볼 정도만 남긴다.

    값이 아니라 키와 짧은 값만 적는다 — 나중에 "이 호출이 뭘 물어봤나"를
    되짚을 수 있으면 충분하고, 그 이상은 로그가 아니라 유출이다.
    """

    parts = []
    for key in sorted(arguments):
        value = arguments[key]
        text = value if isinstance(value, str) else repr(value)
        if len(text) > 60:
            text = f"{text[:57]}..."
        parts.append(f"{key}={text}")
    summary = " ".join(parts)
    return summary[:INPUT_SUMMARY_MAX]


class RunTrace:
    """agent_run 한 건의 수명. `iterations` 는 Runner 가 돌 때마다 올린다."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.iterations = 0
        self.token_in = 0
        self.token_out = 0

    def count_iteration(self) -> None:
        self.iterations += 1

    def count_tokens(self, *, token_in: int, token_out: int) -> None:
        self.token_in += token_in
        self.token_out += token_out


@contextmanager
def run(*, agent_id: str, session_id: str | None, parent_run_id: str | None) -> Iterator[RunTrace]:
    """RUNNING 으로 열고, 정상 종료면 DONE, 예외면 FAILED 로 닫는다.

    예외는 다시 올린다. 로그를 남기는 것과 실패를 삼키는 것은 다른 일이다.
    """

    run_id = AgentRunRepository.start(
        agent_id=agent_id, session_id=session_id, parent_run_id=parent_run_id
    )
    trace = RunTrace(run_id)
    try:
        yield trace
    except BaseException:
        # GeneratorExit·KeyboardInterrupt 도 잡는다. 소비자가 스트림을 중간에
        # 닫으면(브라우저 이탈) GeneratorExit 이 오는데, Exception 만 잡으면
        # 그 run 이 영원히 RUNNING 으로 남는다.
        AgentRunRepository.finish(
            run_id=run_id,
            status="FAILED",
            iterations=trace.iterations,
            token_in=trace.token_in,
            token_out=trace.token_out,
        )
        raise
    else:
        AgentRunRepository.finish(
            run_id=run_id,
            status="DONE",
            iterations=trace.iterations,
            token_in=trace.token_in,
            token_out=trace.token_out,
        )


@contextmanager
def tool_call(*, run_id: str, tool_ref: str, arguments: dict[str, Any]) -> Iterator[str]:
    """PENDING 으로 먼저 넣고, 끝나면 OK / 실패하면 FAILED 로 갱신한다.

    `error_code` 는 예외 클래스 이름이다. 메시지를 넣지 않는 이유는 그 안에
    문서 내용이나 토큰이 들어올 수 있어서다 — 자세한 내용은 서버 로그로 간다.
    """

    tool_call_id = ToolCallRepository.begin(
        run_id=run_id, tool_ref=tool_ref, input_summary=summarize_input(arguments)
    )
    started = time.monotonic()
    try:
        yield tool_call_id
    except BaseException as exc:
        ToolCallRepository.end(
            tool_call_id=tool_call_id,
            status="FAILED",
            duration_ms=int((time.monotonic() - started) * 1000),
            error_code=exc.__class__.__name__[:50],
        )
        raise
    else:
        ToolCallRepository.end(
            tool_call_id=tool_call_id,
            status="OK",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
