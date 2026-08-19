"""Agent Loop.

`run_agent` 는 **chat_session 에 종속되지 않는 순수 실행기**다(A2A 대비 —
공통구조_비교_회의자료 §3-⑨). 대화가 있으면 `context["session_id"]` 로 받아
로그에만 적고, 없으면 없는 대로 돈다. 평가 스크립트와 에이전트 간 호출이
그 경로다.

이벤트는 NDJSON 으로 그대로 흘려보낼 수 있는 dict 다. 기존 업무 추출 스트림
(`services/task_extraction/service.py`)이 쓰던 `stage`·`result`·`error` 를
그대로 쓰고, Loop 에만 필요한 세 가지를 더한다.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from types import GeneratorType
from typing import Any, Callable, Iterator

from django.conf import settings

from apps.connectors.oauth import OAuthError
from backend.db.agent_platform import AgentRepository, CustomModelRepository
from backend.db.errors import RepositoryError
from services.harness import registry, scaffold, trace
from services.harness.trace import error_code_of
from services.harness.registry import Tool, ToolNotAllowed

logger = logging.getLogger(__name__)

#: 이벤트 타입. 단계 3(Chat API)과 화면이 같은 문자열을 봐야 해서 상수로 둔다.
EVENT_STAGE = "stage"
EVENT_TOOL_CALL_STARTED = "tool_call_started"
EVENT_TOOL_CALL_FINISHED = "tool_call_finished"
EVENT_AWAITING_CONFIRMATION = "awaiting_confirmation"
EVENT_RESULT = "result"
EVENT_ERROR = "error"

#: Anthropic 의 OpenAI 호환 경로. 우리가 제공하는 Claude 가 여기로 간다 —
#: 별도 SDK 없이 같은 어댑터로 받는다(2026-08-12 실측: 도구 호출까지 정상,
#: `max_tokens` 도 필수가 아니다).
ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1/"

#: 에이전트에 값이 없을 때의 기본. **`.env` 가 아니라 코드에 둔다** — 환경마다
#: 다른 모델로 도는 것을 막고, 화면이 고른 값이 언제나 이긴다(2026-08-12).
DEFAULT_MODEL = "gpt-5.6-luna"
DEFAULT_EFFORT = "low"


@dataclass
class ModelDecision:
    """모델이 한 번 답한 결과.

    `tool_calls` 가 비면 그것으로 끝이고, 있으면 실행하고 한 번 더 돈다.
    """

    text: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    token_in: int = 0
    token_out: int = 0
    #: 이 턴을 다음 호출의 입력으로 되돌려 보낼 때 쓸 **원본 아이템 그대로**.
    #:
    #: 추론 모델은 function_call 을 되돌려 줄 때 짝이 되는 reasoning 아이템을
    #: 함께 요구한다. 실측(2026-08-11, gpt-5.6-luna):
    #:   function_call 만 보냄 → 400 "was provided without its required
    #:   'reasoning' item". 그래서 우리가 모양을 다시 만들지 않고 받은 것을
    #:   그대로 들고 다닌다.
    raw_items: list[dict[str, Any]] = field(default_factory=list)
    #: 이 답을 만든 API 가 도구 결과를 어떤 모양으로 받는가.
    #:
    #: `responses` 는 OpenAI Responses API(`function_call_output`), `chat` 은
    #: OpenAI 호환 엔드포인트가 쓰는 `/chat/completions`(`role: tool`)다. 두
    #: 형식을 섞으면 그 다음 호출이 400 으로 죽는다 — 그래서 **답을 만든 쪽이
    #: 자기 형식을 들고 다닌다**(2026-08-12).
    tool_style: str = "responses"


#: 모델 호출부. 테스트가 mock 모델을 꽂을 수 있게 함수로 받는다 —
#: (system, messages, tools) -> ModelDecision
ModelClient = Callable[[str, list[dict[str, Any]], list[Tool]], ModelDecision]


def run_agent(
    agent_id: str | None,
    user_input: str,
    context: dict[str, Any] | None = None,
    *,
    model: ModelClient | None = None,
    draft: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> Iterator[dict[str, Any]]:
    """에이전트를 한 번 돌리고 이벤트를 순서대로 내보낸다.

    `context` 로 받는 것:
      session_id             대화에 속한 실행이면 그 id. 없으면 None
      parent_run_id          에이전트가 에이전트를 부른 경우의 상위 run
      account_id             요청자. workload_report 처럼 사람이 기준인 도구가 쓴다
      approved_tool_calls    사용자가 승인한 tool_ref 목록(확인 게이트 재개)
      messages               재개할 때 이어 붙일 이전 대화 상태
      resume_tool_call       승인받은 그 호출. 모델을 다시 묻지 않고 이것부터 실행한다

    `draft` 가 있으면 `agent_id` 로 DB 를 읽지 않고 이 값으로 에이전트·도구를
    조립한다 — **아직 저장되지 않은 빌더 초안을 시험 실행**할 때 쓴다. 이때는
    `agent_id` 가 None 이어도 된다(Agent Builder 가 쓰는 유일한 경로).

    `dry_run=True` 면 승인이 필요한(`side_effect`) 도구를 실제로 부르지 않고
    "이런 인자로 부르려 했다"만 이벤트로 남긴다 — 사람이 승인할 자리가 없는
    시험 실행에서 그대로 실행하면 남의 Jira 를 건드릴 수 있다.

    실패해도 agent_run 은 반드시 닫힌다(단, `draft` 시험 실행은 애초에
    기록하지 않는다 — 아래 `trace.run_ephemeral` 참고). 평가가 세는 모수가
    그 행이라 RUNNING 으로 남은 행이 있으면 성공률이 조용히 틀린다.
    """

    context = context or {}
    approved = set(context.get("approved_tool_calls") or [])
    # **승인한 호출을 그대로 실행한다.** 원래 입력으로 모델을 다시 물으면 재실행
    # 때 다른 인자를 고를 수 있고, 그러면 사용자가 승인한 것과 실제로 실행되는
    # 것이 달라진다 — 외부를 바꾸는 게이트에서 그건 승인이 아니다.
    pending = context.get("resume_tool_call")
    # 그 호출이 **위임**이면, 하위 에이전트도 자기 지점부터 이어 돌아야 한다.
    # 재개 정보가 한 겹이 아니라 스택인 이유다.
    resume_inner = context.get("resume_inner")
    depth = int(context.get("depth") or 1)

    if draft is not None:
        agent: dict[str, Any] = {
            "team_id": draft.get("team_id"),
            "instruction": draft.get("instruction") or "",
            "model": draft.get("model"),
            "reasoning_effort": draft.get("reasoning_effort"),
            "max_iterations": draft.get("max_iterations") or 6,
        }
        tools: dict[str, Tool] = registry.load_for_refs(
            tool_refs=draft.get("tool_refs") or [], team_id=agent["team_id"]
        )
    else:
        agent = AgentRepository.get(agent_id)
        tools = registry.load_for_agent(agent_id=agent_id, team_id=agent["team_id"], depth=depth)

    system = scaffold.compose(
        instruction=agent["instruction"] or "", max_iterations=agent["max_iterations"]
    )
    call_model = model or _default_model(agent)

    messages: list[dict[str, Any]] = list(context.get("messages") or []) or [
        {"role": "user", "content": user_input}
    ]

    made_tool_call = False

    def _grounded() -> bool:
        # 계획 도구가 없으므로 "쓸 수 있는 도구가 있었는데 하나도 안 불렀는가"만 본다.
        return made_tool_call or not tools

    # 초안 시험 실행은 DB 에 기록하지 않는다 — `agent_run.agent_id` 는 NOT NULL 인데
    # 저장 전 초안엔 넣을 id 가 없고, 시험 실행을 평가 로그에 실제 실행처럼 남기면
    # 안 된다.
    run_cm = (
        trace.run_ephemeral()
        if draft is not None
        else trace.run(
            agent_id=agent_id,
            session_id=context.get("session_id"),
            parent_run_id=context.get("parent_run_id"),
        )
    )

    with run_cm as run_trace:
        # **하드 상한은 코드가 건다.** 스캐폴드로 권고도 하지만, 권고를 안 지키는
        # 모델이 있으면 비용과 시간이 무한이 된다.
        limit = agent["max_iterations"]
        for step in range(1, limit + 1):
            yield {"type": EVENT_STAGE, "step": step, "total": limit, "label": "생각하는 중"}

            if pending is not None:
                # 재개 턴. 모델을 부르지 않았으므로 assistant 턴도 다시 넣지 않는다 —
                # `messages` 에 이미 그 턴이 들어 있다(멈출 때 같이 저장했다).
                decision = ModelDecision(tool_calls=[pending])
                pending = None
            else:
                decision = call_model(system, messages, list(tools.values()))
                run_trace.count_iteration()
                run_trace.count_tokens(token_in=decision.token_in, token_out=decision.token_out)

                if not decision.tool_calls:
                    yield {
                        "type": EVENT_RESULT,
                        "text": decision.text or "",
                        "complete": True,
                        "grounded": _grounded(),
                    }
                    return

                messages.extend(_assistant_turn(decision))

            for call in decision.tool_calls:
                tool_ref = call["tool_ref"]
                # 모델이 정한 인자. 서버가 정하는 인자(team_id 등)는 실행 직전에
                # **덮어쓴다** — 합치는 순서가 뒤바뀌면 모델이 보낸 team_id 가
                # 이기고, 같은 키를 두 번 넘기면 TypeError 로 죽는다.
                arguments = call.get("arguments") or {}

                try:
                    tool = registry.resolve(tools, tool_ref)
                except ToolNotAllowed as exc:
                    # 모델에게 돌려주고 계속 돈다. 허용되지 않은 도구를 부른 것은
                    # 실행 실패가 아니라 모델의 잘못된 선택이고, 다음 턴에 고칠 수
                    # 있다. 상한이 있어 무한히 시도하지는 못한다.
                    messages.append(_tool_turn(call, {"error": str(exc)}, decision.tool_style))
                    continue

                made_tool_call = True

                # 승인 게이트 — 외부를 바꾸는 도구는 승인 전에 실행하지 않는다
                # (8/11 확정 ③). 여기서 멈추고, 재개는 단계 3의 confirm API 가
                # `approved_tool_calls` 를 채워 다시 부르는 방식이다.
                if tool.side_effect and tool_ref not in approved:
                    if dry_run:
                        # 시험 실행엔 승인할 사람이 없다. 실제로 부르지 않고
                        # "이런 인자로 부르려 했다"만 남기고 다음 도구로 넘어간다.
                        yield {
                            "type": EVENT_TOOL_CALL_STARTED,
                            "tool_call_id": None,
                            "tool_ref": tool_ref,
                            "tool_name": tool.name,
                        }
                        yield {
                            "type": EVENT_TOOL_CALL_FINISHED,
                            "tool_call_id": None,
                            "tool_ref": tool_ref,
                            "status": "SIMULATED",
                            "arguments": arguments,
                        }
                        messages.append(
                            _tool_turn(
                                call,
                                {
                                    "simulated": True,
                                    "note": "테스트 실행이라 실제로 호출하지 않았습니다.",
                                },
                            )
                        )
                        continue
                    yield {
                        "type": EVENT_AWAITING_CONFIRMATION,
                        "run_id": run_trace.run_id,
                        "tool_ref": tool_ref,
                        "tool_name": tool.name,
                        "arguments": arguments,
                        # 재개에 필요한 전부. 호출자가 이대로 저장했다가 승인 뒤
                        # 그대로 돌려주면 같은 호출이 실행된다. `inner` 가 없는
                        # 것은 "이 층에서 멈췄다"는 뜻이다.
                        "resume": {"messages": messages, "tool_call": call, "inner": None},
                    }
                    return

                delegating = tool_ref.startswith(registry.AGENT_TOOL_PREFIX)
                # 재개 스택은 **한 번만 쓴다.** 안 비우면 같은 재개 정보로 다음
                # 위임까지 이어 돌려 버린다. 실행이 성공하든 실패하든 소비된다.
                inner_resume, resume_inner = (resume_inner, None) if delegating else (None, resume_inner)

                tool_call_id = None
                tool_call_cm = (
                    trace.tool_call_ephemeral()
                    if draft is not None
                    else trace.tool_call(run_id=run_trace.run_id, tool_ref=tool_ref, arguments=arguments)
                )
                try:
                    with tool_call_cm as tool_call_id:
                        yield {
                            "type": EVENT_TOOL_CALL_STARTED,
                            "tool_call_id": tool_call_id,
                            "tool_ref": tool_ref,
                            "tool_name": tool.name,
                        }
                        # 주입은 `with` 안에서 한다. 밖에서 하다 실패하면 tool_call
                        # 행 없이 run 이 끝나 로그에 흔적이 남지 않는다.
                        injected = (
                            {
                                "delegation": _delegation(
                                    context=context,
                                    parent_run_id=run_trace.run_id,
                                    depth=depth,
                                    approved=approved,
                                    inner=inner_resume,
                                )
                            }
                            if delegating
                            else _injected(tool, agent, context)
                        )
                        raw = tool.handler(**{**arguments, **injected})
                        if isinstance(raw, GeneratorType):
                            # 오래 걸리는 도구는 진행을 흘린다. 모델에게 줄 값은
                            # `return` 으로 받는다.
                            output = yield from _forward(raw, tool_ref, tool_call_id)
                        else:
                            output = raw
                except Exception as exc:  # noqa: BLE001 - 도구 실패로 run 을 끝내지 않는다
                    logger.exception("도구 실행 실패: %s (run=%s)", tool_ref, run_trace.run_id)
                    # MCP 실패는 **왜 실패했는지가 코드에 담겨 있다**(timeout ·
                    # unreachable · 401 · 429). 클래스 이름만 남기면 전부
                    # 「McpError」 하나로 뭉개져, 기록만 보고는 서버가 죽은 것과
                    # 토큰이 만료된 것을 못 가른다 — 운영자 콘솔의 「실패한 도구」
                    # 열도 그 코드를 그대로 보여준다(2026-08-13에 실제 서버로
                    # 돌려 보다 드러났다).
                    error_code = error_code_of(exc)
                    # **사람이 고칠 수 있는 사유만 그대로 내보낸다.** 그 밖의
                    # 예외는 문자열에 문서 원문이나 토큰이 섞여 있을 수 있어
                    # 클래스 이름만 남긴다.
                    detail = str(exc) if isinstance(exc, SPEAKABLE_ERRORS) else None
                    yield {
                        "type": EVENT_TOOL_CALL_FINISHED,
                        "tool_call_id": tool_call_id,
                        "tool_ref": tool_ref,
                        "status": "FAILED",
                        "error_code": error_code,
                        "detail": detail,
                    }
                    # 모델에게도 같은 기준으로 준다 — 고칠 수 있는 사유는 알려
                    # 줘야 다음 턴에 사람에게 제대로 되물을 수 있다.
                    messages.append(
                        _tool_turn(call, {"error": detail or f"도구 실행 실패: {error_code}"}, decision.tool_style)
                    )
                else:
                    yield {
                        "type": EVENT_TOOL_CALL_FINISHED,
                        "tool_call_id": tool_call_id,
                        "tool_ref": tool_ref,
                        "status": "OK",
                    }

                    # 하위 에이전트가 승인 게이트에서 멈췄다. 이 층도 함께 멈추고
                    # **두 층의 재개 정보를 한 장에 담아** 올린다 — 승인은 사람이
                    # 한 번 하고, 재개는 위에서 아래로 같은 순서로 되짚는다.
                    #
                    # 결과를 `messages` 에 넣지 않는다. 재개할 때 이 호출을 그대로
                    # 다시 실행하므로, 넣으면 같은 위임이 두 번 들어간다.
                    inner = _suspended(output)
                    if inner is not None:
                        yield {
                            "type": EVENT_AWAITING_CONFIRMATION,
                            "run_id": run_trace.run_id,
                            "tool_ref": inner["tool_ref"],
                            "tool_name": inner["tool_name"],
                            "arguments": inner["arguments"],
                            # 어느 에이전트가 이 승인을 요구했는지. 화면이
                            # "「부하 리포트」가 Jira 등록을 요청합니다"로 쓴다.
                            "via_agent": output.get("name"),
                            "resume": {
                                "messages": messages,
                                "tool_call": call,
                                "inner": inner["resume"],
                            },
                        }
                        return

                    messages.append(_tool_turn(call, output, decision.tool_style))

        # 상한에 걸려 나온 길. `error` 가 아니라 `result` 인 이유는 여기까지 한
        # 일이 버려지지 않기 때문이다 — 대신 끝내지 못했다고 분명히 적는다.
        yield {
            "type": EVENT_RESULT,
            "text": "",
            "complete": False,
            "stopped_reason": "max_iterations",
            "iterations": limit,
            "grounded": _grounded(),
        }


#: `check_tools` 가 건너뛰는 도구. 업무 추출은 몇 분 걸리는 파이프라인이라
#: 여기서 확인하지 않는다 — 프로젝트의 업무 추출 화면을 쓰면 된다.
_CHECK_EXCLUDED_TOOLS = frozenset({"task_extraction"})


def check_tools(
    *,
    team_id: str | None,
    account_id: str,
    tool_refs: list[str],
    arguments_by_ref: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """선택한 도구 전부를 모델 판단 없이 순서대로 하나씩 직접 불러 본다.

    실사용 중 "필요할 때만 부른다"는 모델 판단에 맡기면, 데이터가 없거나
    모델이 안 부른 도구는 영영 확인이 안 된다 — 저장 전에 도구 하나하나가
    실제로 도는지 사람이 직접 볼 수 있게 하는 경로다.

    `side_effect` 도구는 실시간으로 승인할 사람이 없으므로 항상 시뮬레이션한다.
    도구 하나가 실패해도 나머지는 계속 확인한다. 저장 전 시험이라 DB 에 기록을
    남기지 않는다(`agent_run.agent_id` 가 NOT NULL 이라 초안엔 붙일 데가 없다).
    """

    arguments_by_ref = arguments_by_ref or {}
    agent: dict[str, Any] = {"team_id": team_id}
    tools = registry.load_for_refs(tool_refs=tool_refs, team_id=team_id)
    context = {"account_id": account_id}

    results: list[dict[str, Any]] = []
    for tool_ref in tool_refs:
        if tool_ref in _CHECK_EXCLUDED_TOOLS:
            results.append(
                {
                    "tool_ref": tool_ref,
                    "tool_name": tool_ref,
                    "status": "SKIPPED",
                    "detail": "여기서는 확인하지 않습니다 — 프로젝트의 업무 추출 화면을 쓰세요.",
                }
            )
            continue
        try:
            tool = registry.resolve(tools, tool_ref)
        except ToolNotAllowed as exc:
            results.append(
                {
                    "tool_ref": tool_ref,
                    "tool_name": tool_ref,
                    "status": "FAILED",
                    "error_code": "ToolNotAllowed",
                    "detail": str(exc),
                }
            )
            continue

        arguments = arguments_by_ref.get(tool_ref) or {}
        if tool.side_effect:
            results.append(
                {"tool_ref": tool_ref, "tool_name": tool.name, "status": "SIMULATED", "arguments": arguments}
            )
            continue

        try:
            with trace.tool_call_ephemeral():
                raw = tool.handler(**{**arguments, **_injected(tool, agent, context)})
                output = _drain(raw) if isinstance(raw, GeneratorType) else raw
        except Exception as exc:  # noqa: BLE001 - 하나 실패해도 나머지는 계속 확인한다
            results.append(
                {
                    "tool_ref": tool_ref,
                    "tool_name": tool.name,
                    "status": "FAILED",
                    "error_code": error_code_of(exc),
                    "detail": str(exc) if isinstance(exc, SPEAKABLE_ERRORS) else None,
                }
            )
        else:
            results.append({"tool_ref": tool_ref, "tool_name": tool.name, "status": "OK", "output": output})

    return results


def _drain(events: Iterator[dict[str, Any]]) -> Any:
    """제너레이터 도구의 진행 이벤트는 버리고 `return` 값만 취한다.

    `check_tools` 는 스트리밍 채널이 없는 동기 응답이라 진행을 보여줄 데가 없다.
    """

    try:
        while True:
            next(events)
    except StopIteration as stop:
        return stop.value


def _forward(events: Iterator[dict[str, Any]], tool_ref: str, tool_call_id: str | None):
    """도구가 흘리는 진행 이벤트에 출처를 붙여 중계한다.

    붙이지 않으면 두 층의 `stage` 가 구별되지 않는다. Loop 의 `stage` 는
    `1/4`(회전 수)이고 업무 추출의 `stage` 는 `1/5`(파이프라인 단계)인데,
    화면에서는 같은 타입으로 도착해 진행 카드가 1/4 → 1/5 → 2/5 → 2/4 로
    튄다(2026-08-11 실호출에서 확인). 서로 다른 축이라 카드도 달라야 한다.

    타입 이름을 바꾸지 않는 이유는 기존 업무 추출 화면이 이미 이 어휘
    (`stage`·`queries`·`stage_done`)를 읽고 있어서다 — 필드만 더한다.
    화면 규칙: `tool_ref` 가 있으면 그 도구의 진행, 없으면 Loop 의 회전.
    """

    while True:
        try:
            event = next(events)
        except StopIteration as stop:
            # 도구가 `return` 으로 준 값. 제너레이터 표현식에 `yield from` 을
            # 걸면 이 값이 사라져 모델이 None 을 받는다.
            return stop.value
        yield {**event, "tool_ref": tool_ref, "tool_call_id": tool_call_id}


#: 메시지를 **사람에게 그대로 보여도 되는** 예외.
#:
#: 셋 다 이 저장소가 사용자용 한국어 문장으로 쓰고 있는 것들이다 — 실제로
#: `apps/*/api_views.py` 의 `_repository_error_response` 가 `RepositoryError` 의
#: 문자열을 그대로 응답에 싣는다. 화면에만 감출 이유가 없다.
#:
#: 여기 없는 예외(라이브러리·드라이버)는 클래스 이름만 나간다. 그 문자열에는
#: 쿼리·문서 원문·토큰이 섞여 있을 수 있다.
#:
#: **공개 이름이다** — 새 런타임(`services/agent_runtime/factory.py`)이 같은
#: 기준을 써야 해서 밑줄을 뗐다. 두 엔진이 서로 다른 목록을 들면, 같은 실패가
#: 한쪽에서는 사유와 함께 보이고 다른 쪽에서는 「요청을 끝내지 못했습니다」로만
#: 보인다(2026-08-18 QA 에서 실제로 그랬다).
SPEAKABLE_ERRORS = (registry.ToolInputError, RepositoryError, OAuthError)


def _suspended(output: Any) -> dict[str, Any] | None:
    """위임 결과가 「하위가 승인 대기로 멈췄다」인가.

    표식을 값으로 받는 이유는 `registry.SUSPENDED_KEY` 주석에 있다 — 예외로
    올리면 안쪽 run 이 GeneratorExit 로 FAILED 가 된다.
    """

    if isinstance(output, dict):
        return output.get(registry.SUSPENDED_KEY)
    return None


def _delegation(
    *,
    context: dict[str, Any],
    parent_run_id: str,
    depth: int,
    approved: set[str],
    inner: dict[str, Any] | None,
) -> dict[str, Any]:
    """하위 에이전트에게 넘길 실행 문맥.

    **테넌트·요청자는 그대로 물려준다.** 위임이 권한을 넓히는 통로가 되면 안
    된다 — 하위 에이전트도 같은 사람의 자격으로 같은 팀 것만 본다
    (`_injected` 가 그 값으로 다시 경계를 긋는다).

    `approved` 도 내려보낸다. 승인 재개는 **가장 안쪽 호출**을 실행하러 가는
    길이라, 그 층에서 게이트가 다시 뜨면 사람이 두 번 승인하게 된다.

    `inner` 는 하위의 재개 지점이다. 없으면 하위는 처음부터 돈다.
    """

    child: dict[str, Any] = {
        "session_id": context.get("session_id"),
        "account_id": context.get("account_id"),
        "proj_id": context.get("proj_id"),
        # 이 값으로 agent_run 이 이어진다. 어느 실행이 어느 실행을 불렀는지가
        # 스키마에 남는다(schema.sql:857).
        "parent_run_id": parent_run_id,
        "depth": depth + 1,
        "approved_tool_calls": sorted(approved),
    }
    if inner:
        child["messages"] = inner.get("messages") or []
        child["resume_tool_call"] = inner.get("tool_call")
        child["resume_inner"] = inner.get("inner")
    return child


def _injected(tool: Tool, agent: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """모델이 정하면 안 되는 인자.

    `team_id` 를 모델에게 맡기면 프롬프트로 남의 팀 문서를 읽어 낼 수 있다.
    테넌트 경계는 언제나 서버가 정한다.
    """

    if tool.ref == "document_search":
        # **`account_id` 를 빠뜨리면 조용히 반쪽이 된다**(2026-08-18 QA 에서 잡았다).
        # 없으면 `coarse_search` 가 팀 문서만 보고 **내가 켠 내 파일이 안 잡히며**
        # (M④), 온디맨드 승격도 통째로 꺼진다 — `registry.py` 의
        # `not_indexed[:PROMOTE_TOP_N] if account_id else []`. 그런데 오류가 아니라
        # 「문서가 없습니다」로 끝나서 **기능이 없는 것처럼 보인다.**
        # 승격은 2026-08-15 에 이 값이 온다는 전제로 만들어졌는데 이 자리가 그때
        # 같이 안 고쳐졌다.
        #
        # `proj_id` 는 2026-08-19 에 더했다(PM 결정 ⓐ) — 프로젝트 대화면 그
        # 프로젝트 문서를 먼저 본다. 없으면 `_document_search` 가 팀 전체로
        # 넓힌다. 프로젝트 없는 대화(「팀 전체 문서」)는 None 이라 예전과 같다.
        return {
            "team_id": agent["team_id"],
            "account_id": context.get("account_id"),
            "proj_id": context.get("proj_id"),
        }
    if tool.ref.startswith("mcp:"):
        # MCP 도구도 팀이 필요하다 — 실행 직전에 그 팀의 서버·토큰을 찾는다.
        # 모델이 team_id 를 보내면 남의 팀 MCP 서버를 부를 수 있다.
        # **account_id 는 넘기지 않는다** — MCP 핸들러가 받지 않는 인자다.
        return {"team_id": agent["team_id"]}
    if tool.ref == "task_extraction":
        # **부른 에이전트의 모델로 돈다.** 도구 안에 `.env` 모델이 박혀 있으면,
        # 에이전트에서 모델을 골라 놓고 정작 제일 무거운 호출은 다른 모델로 도는
        # 어긋남이 생긴다. 팀이 자기 키를 넣은 경우(BYOK)도 마찬가지로, 추출만
        # 우리 키로 나가면 그 팀이 키를 넣은 이유를 배신한다(2026-08-12).
        return {
            "proj_id": context.get("proj_id"),
            "account_id": context.get("account_id"),
            "team_id": agent["team_id"],
            "model": agent.get("model"),
        }
    if tool.ref in _PROJECT_SCOPED_TOOLS:
        # 어느 프로젝트의 일인지는 대화의 문맥이지 모델의 선택이 아니다.
        # 모델이 proj_id 를 정하면 남의 프로젝트에 업무를 등록할 수 있다.
        #
        # Jira 도구도 여기 있다. 프로젝트 하나에 Jira 프로젝트 하나라
        # (`proj_source`) 이 값이면 키가 나온다 — **모델에게 키를 묻지 않는다.**
        # 물어보게 두면 「확인할 Jira 프로젝트 키를 알려주세요」로 대화가 끊긴다.
        return {"proj_id": context.get("proj_id"), "account_id": context.get("account_id")}
    if tool.ref in _ACCOUNT_SCOPED_TOOLS:
        account_id = context.get("account_id")
        if not account_id:
            # 대화 없이 도는 경로(평가·A2A)에는 요청자가 없다. 조용히 남의 자격으로
            # 외부를 부르지 않고 이 도구만 실패시킨다.
            raise ValueError(f"{tool.ref} 는 요청자 계정(account_id)이 필요합니다.")
        return {"account_id": account_id}
    return {}


#: 대화의 프로젝트를 서버가 넣어 주는 도구. 요청자 계정도 함께 간다.
#:
#: Jira 도구가 여기 있는 이유는 `proj_source` 가 프로젝트 ↔ Jira 프로젝트를
#: 1:1 로 들고 있어서다 — 대화가 어느 프로젝트인지 알면 키는 서버가 찾는다.
_PROJECT_SCOPED_TOOLS = frozenset(
    {
        "task_extraction",
        "task_register",
        "task_list",
        "task_update",
        "jira_create_issues",
        "jira_get_issues",
    }
)

#: 요청자 계정만 서버가 넣어 주는 도구. 모델이 정하면 남의 팀 명부·남의 부하를
#: 읽는다. Connector 자격증명이 계정별인 것도 같은 이유다.
_ACCOUNT_SCOPED_TOOLS = frozenset(
    {
        "people_list",
        "workload_report",
        "project_list",
        "document_list",
        "absence_list",
    }
)


def _assistant_turn(decision: ModelDecision) -> list[dict[str, Any]]:
    """모델 턴을 다음 입력에 이어 붙일 아이템들.

    받은 원본을 그대로 쓴다 — reasoning 과 function_call 은 짝이라 우리가 다시
    조립하면 API 가 거절한다. mock 모델(테스트)은 원본이 없으므로 평범한
    assistant 메시지로 떨어진다.
    """

    if decision.raw_items:
        return list(decision.raw_items)
    return [{"role": "assistant", "content": decision.text or ""}]


def _tool_turn(call: dict[str, Any], output: Any, style: str = "responses") -> dict[str, Any]:
    """도구 결과. **답을 만든 API 의 형식으로 되돌린다.**"""

    text = json.dumps(output, ensure_ascii=False, default=str)
    if style == "chat":
        return {"role": "tool", "tool_call_id": call.get("id"), "content": text}
    return {"type": "function_call_output", "call_id": call.get("id"), "output": text}


def _default_model(agent: dict[str, Any]) -> ModelClient:
    """실제 모델 호출부.

    에이전트 레코드의 `model`·`reasoning_effort` 를 쓰고, 비어 있을 때만 이
    모듈의 `DEFAULT_MODEL`·`DEFAULT_EFFORT` 로 떨어진다 — 에이전트마다 모델을
    고르게 해 놓고 코드가 하나로 덮어쓰면 Builder 의 모델 선택이 거짓말이 된다.

    그 이름으로 **어느 경로로 부를지까지 정해진다**: 우리가 제공하는 OpenAI 는
    Responses API(`client.responses.create` — 도구 호출이 실제로 도는 것을 확인한
    형태다, 2026-08-11 실측), Claude 와 팀이 등록한 커스텀 주소는 OpenAI 호환
    `/chat/completions` 다. 아래 두 갈래를 보라.
    """

    from openai import OpenAI

    # **팀이 넣어 둔 것이 있으면 그것으로 돈다.** 없으면 우리 키다 — 기본은
    # 우리가 제공하는 것이고(타깃이 비개발자라 키를 요구할 수 없다), 자기 계약을
    # 써야 하는 팀만 덮어쓴다(2026-08-12 PM 결정).
    model_name = agent.get("model") or DEFAULT_MODEL
    endpoint = _team_endpoint(agent.get("team_id"), model_name) or {}
    api_key = endpoint.get("api_key") or settings.OPENAI_API_KEY
    base_url = endpoint.get("base_url") or None
    if not str(api_key).strip():
        raise RuntimeError("OPENAI_API_KEY 가 없습니다.")

    effort = agent.get("reasoning_effort") or DEFAULT_EFFORT

    # **우리가 제공하는 Claude 는 Anthropic 키로 부른다.** 팀이 자기 주소를 넣은
    # 경우가 아니면, 모델 이름이 어느 제공자 것인지로 갈린다.
    if not base_url and model_name.startswith("claude-"):
        api_key = settings.ANTHROPIC_API_KEY
        base_url = ANTHROPIC_BASE_URL
        if not str(api_key).strip():
            raise RuntimeError("ANTHROPIC_API_KEY 가 없습니다.")

    client = OpenAI(api_key=api_key, base_url=base_url or None, timeout=300, max_retries=1)

    # **Responses API 는 사실상 OpenAI 전용이다.** 호환 엔드포인트(Anthropic·
    # OpenRouter·Groq·vLLM…)에 그대로 보내면 404 라, 주소가 있으면 무조건
    # `/chat/completions` 로 간다. 형식이 다른 만큼 도구 결과를 되돌리는 모양도
    # 달라진다(`ModelDecision.tool_style`).
    if base_url:
        return _chat_completions_model(client, model_name)

    def call(system: str, messages: list[dict[str, Any]], tools: list[Tool]) -> ModelDecision:
        response = client.responses.create(
            model=model_name,
            service_tier=settings.OPENAI_SERVICE_TIER,
            reasoning={"effort": effort},
            tools=[_tool_spec(tool) for tool in tools] or None,
            input=[{"role": "system", "content": system}, *messages],
        )
        usage = response.usage
        return ModelDecision(
            text=response.output_text or None,
            tool_calls=[
                {
                    "id": item.call_id,
                    # 모델은 `agent__AG005` 로 부른다. 저장소 규칙인
                    # `agent:AG005` 로 되돌린다(`model_name_for` 주석).
                    "tool_ref": tool_ref_for(item.name),
                    "arguments": json.loads(item.arguments or "{}"),
                }
                for item in response.output
                if item.type == "function_call"
            ],
            token_in=getattr(usage, "input_tokens", 0) or 0,
            token_out=getattr(usage, "output_tokens", 0) or 0,
            raw_items=[_echoable(item) for item in response.output],
        )

    return call


def _team_endpoint(team_id: str | None, model: str | None) -> dict[str, Any] | None:
    """이 모델 이름을 감당하는 커스텀 엔드포인트. 없으면 `None` — 우리 것으로 돈다.

    **모델 이름 하나로 경로가 정해진다.** 팀이 등록한 API 중 그 모델을 선언한
    것이 있으면 거기로 가고, 없으면 우리가 제공하는 경로다.

    **여기서 터뜨리지 않는다.** 못 읽었다고 대화 전체를 실패시키면, 등록해 둔
    값이 깨졌을 때 아무것도 못 하게 된다.
    """

    if not team_id or not model:
        return None
    try:
        return CustomModelRepository.for_model(team_id, model)
    except Exception:  # noqa: BLE001 - 조회 실패로 실행을 막지 않는다
        logger.exception("커스텀 모델 API 를 읽지 못했습니다: team=%s", team_id)
        return None


def _chat_tool_spec(tool: Tool) -> dict[str, Any]:
    """`/chat/completions` 의 function tool 은 `function` 안에 한 겹 들어간다."""

    return {
        "type": "function",
        "function": {
            "name": model_name_for(tool.ref),
            "description": tool.description,
            "parameters": tool.input_schema,
        },
    }


def _chat_completions_model(client: Any, model_name: str) -> ModelClient:
    """OpenAI 호환 엔드포인트(`/chat/completions`)용 호출부.

    OpenRouter·Groq·Together·Azure·사내 vLLM, 그리고 **Anthropic 의 OpenAI 호환
    경로**가 전부 이 모양이다. Responses API 와 다른 점은 셋이다 —
    도구 스펙이 한 겹 더 싸여 있고, 답이 `choices[0].message` 이며, 도구 결과를
    `role: tool` 로 되돌린다.

    `reasoning` 은 보내지 않는다. 호환 구현마다 받는 곳도 있고 400 을 내는 곳도
    있어서, 공통분모만 쓴다.
    """

    def call(system: str, messages: list[dict[str, Any]], tools: list[Tool]) -> ModelDecision:
        response = client.chat.completions.create(
            model=model_name,
            tools=[_chat_tool_spec(tool) for tool in tools] or None,
            messages=[{"role": "system", "content": system}, *messages],
        )
        message = response.choices[0].message
        raw_calls = list(message.tool_calls or [])
        usage = response.usage
        return ModelDecision(
            text=message.content or None,
            tool_calls=[
                {
                    "id": item.id,
                    "tool_ref": tool_ref_for(item.function.name),
                    "arguments": json.loads(item.function.arguments or "{}"),
                }
                for item in raw_calls
            ],
            token_in=getattr(usage, "prompt_tokens", 0) or 0,
            token_out=getattr(usage, "completion_tokens", 0) or 0,
            # 다음 호출에 그대로 이어 붙일 assistant 턴. Responses 와 달리 우리가
            # 조립해도 되지만, 도구 호출은 **id 까지 그대로** 돌려줘야 짝이 맞는다.
            #
            # ⚠ **제공자가 얹어 보낸 필드를 같이 돌려준다**(`model_extra`).
            # Gemini 3.x 는 함수 호출에 `extra_content.google.thought_signature`
            # 를 달아 주고, 다음 요청에 그것이 없으면 **400 으로 거절한다**:
            #   "Function call is missing a thought_signature in functionCall
            #    parts. This is required for tools to work correctly."
            # 우리가 아는 칸만 골라 다시 조립하면 그 서명이 조용히 사라진다.
            # 첫 호출은 멀쩡하고 **도구 결과를 되돌리는 두 번째 호출에서만**
            # 깨지므로, 화면에는 도구 카드가 뜬 뒤 실패로 보인다(2026-08-14 실측).
            # Responses API 쪽 `_echoable` 이 「우리가 해석하거나 줄이면 짝이
            # 깨진다」고 적어 둔 것과 같은 이야기다.
            raw_items=[
                {
                    "role": "assistant",
                    "content": message.content or "",
                    **(
                        {
                            "tool_calls": [
                                {
                                    "id": item.id,
                                    "type": "function",
                                    "function": {
                                        "name": item.function.name,
                                        "arguments": item.function.arguments or "{}",
                                    },
                                    **(item.model_extra or {}),
                                }
                                for item in raw_calls
                            ]
                        }
                        if raw_calls
                        else {}
                    ),
                }
            ],
            tool_style="chat",
        )

    return call


def _echoable(item: Any) -> dict[str, Any]:
    """응답 아이템을 다음 요청의 입력으로 되돌려 보낼 수 있는 모양으로.

    `status` 는 응답 전용이라 그대로 보내면 400 `unknown_parameter` 다
    (2026-08-11 실측). 나머지는 손대지 않는다 — reasoning 아이템의 내용물을
    우리가 해석하거나 줄이면 짝이 깨진다.
    """

    return item.model_dump(exclude={"status"}, exclude_none=True)


def model_name_for(tool_ref: str) -> str:
    """모델에게 보낼 함수 이름.

    **`tool_ref` 를 그대로 못 쓴다.** OpenAI 함수 이름은 `^[a-zA-Z0-9_-]+$` 라
    콜론이 들어가면 400 이다(2026-08-12 실측:
    `Invalid 'tools[7].name': string does not match pattern`).

    우리 `tool_ref` 는 `agent:AG005`·`mcp:MT001` 처럼 접두사에 콜론을 쓴다 —
    그건 **저장소(`agent_tool.tool_ref`) 규칙**이라 바꾸지 않는다. 모델에게
    보낼 때만 `__` 로 바꾸고, 응답이 오면 되돌린다.

    ⚠ MCP 도구도 같은 문제였다. 지금까지 아무도 MCP 서버를 안 붙여서 안
    드러났을 뿐이고, 붙였으면 똑같이 죽었을 자리다.
    """

    return tool_ref.replace(":", "__")


def tool_ref_for(model_name: str) -> str:
    """모델이 부른 이름을 우리 `tool_ref` 로 되돌린다."""

    return model_name.replace("__", ":")


def _tool_spec(tool: Tool) -> dict[str, Any]:
    """Responses API 의 function tool 은 평평하다 — `function` 안에 넣지 않는다."""

    return {
        "type": "function",
        "name": model_name_for(tool.ref),
        "description": tool.description,
        "parameters": tool.input_schema,
    }
