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
from backend.db.agent_platform import AgentRepository
from backend.db.errors import RepositoryError
from services.harness import registry, scaffold, trace
from services.harness.registry import Tool, ToolNotAllowed

logger = logging.getLogger(__name__)

#: 이벤트 타입. 단계 3(Chat API)과 화면이 같은 문자열을 봐야 해서 상수로 둔다.
EVENT_STAGE = "stage"
EVENT_TOOL_CALL_STARTED = "tool_call_started"
EVENT_TOOL_CALL_FINISHED = "tool_call_finished"
EVENT_AWAITING_CONFIRMATION = "awaiting_confirmation"
EVENT_RESULT = "result"
EVENT_ERROR = "error"


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


#: 모델 호출부. 테스트가 mock 모델을 꽂을 수 있게 함수로 받는다 —
#: (system, messages, tools) -> ModelDecision
ModelClient = Callable[[str, list[dict[str, Any]], list[Tool]], ModelDecision]


def run_agent(
    agent_id: str,
    user_input: str,
    context: dict[str, Any] | None = None,
    *,
    model: ModelClient | None = None,
) -> Iterator[dict[str, Any]]:
    """에이전트를 한 번 돌리고 이벤트를 순서대로 내보낸다.

    `context` 로 받는 것:
      session_id             대화에 속한 실행이면 그 id. 없으면 None
      parent_run_id          에이전트가 에이전트를 부른 경우의 상위 run
      account_id             요청자. workload_report 처럼 사람이 기준인 도구가 쓴다
      approved_tool_calls    사용자가 승인한 tool_ref 목록(확인 게이트 재개)
      messages               재개할 때 이어 붙일 이전 대화 상태
      resume_tool_call       승인받은 그 호출. 모델을 다시 묻지 않고 이것부터 실행한다

    실패해도 agent_run 은 반드시 닫힌다. 평가가 세는 모수가 그 행이라
    RUNNING 으로 남은 행이 있으면 성공률이 조용히 틀린다.
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

    agent = AgentRepository.get(agent_id)
    tools = registry.load_for_agent(agent_id=agent_id, team_id=agent["team_id"], depth=depth)
    system = scaffold.compose(
        instruction=agent["instruction"] or "", max_iterations=agent["max_iterations"]
    )
    call_model = model or _default_model(agent)

    messages: list[dict[str, Any]] = list(context.get("messages") or []) or [
        {"role": "user", "content": user_input}
    ]

    with trace.run(
        agent_id=agent_id,
        session_id=context.get("session_id"),
        parent_run_id=context.get("parent_run_id"),
    ) as run_trace:
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
                    yield {"type": EVENT_RESULT, "text": decision.text or "", "complete": True}
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
                    messages.append(_tool_turn(call, {"error": str(exc)}))
                    continue

                # 승인 게이트 — 외부를 바꾸는 도구는 승인 전에 실행하지 않는다
                # (8/11 확정 ③). 여기서 멈추고, 재개는 단계 3의 confirm API 가
                # `approved_tool_calls` 를 채워 다시 부르는 방식이다.
                if tool.side_effect and tool_ref not in approved:
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
                try:
                    with trace.tool_call(
                        run_id=run_trace.run_id, tool_ref=tool_ref, arguments=arguments
                    ) as tool_call_id:
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
                    error_code = exc.__class__.__name__
                    # **사람이 고칠 수 있는 사유만 그대로 내보낸다.** 그 밖의
                    # 예외는 문자열에 문서 원문이나 토큰이 섞여 있을 수 있어
                    # 클래스 이름만 남긴다.
                    detail = str(exc) if isinstance(exc, _SPEAKABLE_ERRORS) else None
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
                        _tool_turn(call, {"error": detail or f"도구 실행 실패: {error_code}"})
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

                    messages.append(_tool_turn(call, output))

        # 상한에 걸려 나온 길. `error` 가 아니라 `result` 인 이유는 여기까지 한
        # 일이 버려지지 않기 때문이다 — 대신 끝내지 못했다고 분명히 적는다.
        yield {
            "type": EVENT_RESULT,
            "text": "",
            "complete": False,
            "stopped_reason": "max_iterations",
            "iterations": limit,
        }


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
_SPEAKABLE_ERRORS = (registry.ToolInputError, RepositoryError, OAuthError)


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

    if tool.ref == "document_search" or tool.ref.startswith("mcp:"):
        # MCP 도구도 팀이 필요하다 — 실행 직전에 그 팀의 서버·토큰을 찾는다.
        # 모델이 team_id 를 보내면 남의 팀 MCP 서버를 부를 수 있다.
        return {"team_id": agent["team_id"]}
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
    {"task_extraction", "task_register", "jira_create_issues", "jira_get_issues"}
)

#: 요청자 계정만 서버가 넣어 주는 도구. 모델이 정하면 남의 팀 명부·남의 부하를
#: 읽는다. Connector 자격증명이 계정별인 것도 같은 이유다.
_ACCOUNT_SCOPED_TOOLS = frozenset({"people_list", "workload_report"})


def _assistant_turn(decision: ModelDecision) -> list[dict[str, Any]]:
    """모델 턴을 다음 입력에 이어 붙일 아이템들.

    받은 원본을 그대로 쓴다 — reasoning 과 function_call 은 짝이라 우리가 다시
    조립하면 API 가 거절한다. mock 모델(테스트)은 원본이 없으므로 평범한
    assistant 메시지로 떨어진다.
    """

    if decision.raw_items:
        return list(decision.raw_items)
    return [{"role": "assistant", "content": decision.text or ""}]


def _tool_turn(call: dict[str, Any], output: Any) -> dict[str, Any]:
    """도구 결과. Responses API 의 function_call_output 형식 그대로다."""

    return {
        "type": "function_call_output",
        "call_id": call.get("id"),
        "output": json.dumps(output, ensure_ascii=False, default=str),
    }


def _default_model(agent: dict[str, Any]) -> ModelClient:
    """실제 모델 호출부.

    **Responses API 를 쓴다.** `services/task_extraction` 이 이미 쓰고 있는
    경로이고(`client.responses.parse`), 이 계정·모델에서 도구 호출이 실제로
    도는 것을 확인한 형태다(2026-08-11 실측). `chat.completions` 가 아니다.

    에이전트 레코드의 `model`·`reasoning_effort` 를 쓰고, 비어 있으면 설정의
    기본값으로 떨어진다 — 에이전트마다 모델을 고르게 해 놓고 코드가 하나로
    덮어쓰면 Builder 의 모델 선택이 거짓말이 된다.
    """

    from openai import OpenAI

    api_key = settings.OPENAI_API_KEY
    if not str(api_key).strip():
        raise RuntimeError("OPENAI_API_KEY 가 없습니다.")

    client = OpenAI(api_key=api_key, timeout=300, max_retries=1)
    model_name = agent.get("model") or settings.OPENAI_MODEL
    effort = agent.get("reasoning_effort") or settings.OPENAI_REASONING_EFFORT

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
                    "tool_ref": item.name,
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


def _echoable(item: Any) -> dict[str, Any]:
    """응답 아이템을 다음 요청의 입력으로 되돌려 보낼 수 있는 모양으로.

    `status` 는 응답 전용이라 그대로 보내면 400 `unknown_parameter` 다
    (2026-08-11 실측). 나머지는 손대지 않는다 — reasoning 아이템의 내용물을
    우리가 해석하거나 줄이면 짝이 깨진다.
    """

    return item.model_dump(exclude={"status"}, exclude_none=True)


def _tool_spec(tool: Tool) -> dict[str, Any]:
    """Responses API 의 function tool 은 평평하다 — `function` 안에 넣지 않는다."""

    return {
        "type": "function",
        "name": tool.ref,
        "description": tool.description,
        "parameters": tool.input_schema,
    }
