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
from typing import Any, Callable, Iterator

from django.conf import settings

from backend.db.agent_platform import AgentRepository
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
      approved_tool_calls    사용자가 이미 승인한 tool_ref 목록(확인 게이트 재개)

    실패해도 agent_run 은 반드시 닫힌다. 평가가 세는 모수가 그 행이라
    RUNNING 으로 남은 행이 있으면 성공률이 조용히 틀린다.
    """

    context = context or {}
    approved = set(context.get("approved_tool_calls") or [])

    agent = AgentRepository.get(agent_id)
    tools = registry.load_for_agent(agent_id=agent_id, team_id=agent["team_id"])
    system = scaffold.compose(
        instruction=agent["instruction"] or "", max_iterations=agent["max_iterations"]
    )
    call_model = model or _default_model(agent)

    messages: list[dict[str, Any]] = [{"role": "user", "content": user_input}]

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

            decision = call_model(system, messages, list(tools.values()))
            run_trace.count_iteration()
            run_trace.count_tokens(token_in=decision.token_in, token_out=decision.token_out)

            if not decision.tool_calls:
                yield {"type": EVENT_RESULT, "text": decision.text or "", "complete": True}
                return

            messages.append(_assistant_turn(decision))

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
                    }
                    return

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
                        output = tool.handler(**{**arguments, **_injected(tool, agent, context)})
                except Exception as exc:  # noqa: BLE001 - 도구 실패로 run 을 끝내지 않는다
                    logger.exception("도구 실행 실패: %s (run=%s)", tool_ref, run_trace.run_id)
                    error_code = exc.__class__.__name__
                    yield {
                        "type": EVENT_TOOL_CALL_FINISHED,
                        "tool_call_id": tool_call_id,
                        "tool_ref": tool_ref,
                        "status": "FAILED",
                        "error_code": error_code,
                    }
                    # 메시지에는 클래스 이름만 넣는다. 예외 문자열에 문서 원문이나
                    # 토큰이 섞여 들어오면 그대로 모델 컨텍스트에 실린다.
                    messages.append(_tool_turn(call, {"error": f"도구 실행 실패: {error_code}"}))
                else:
                    yield {
                        "type": EVENT_TOOL_CALL_FINISHED,
                        "tool_call_id": tool_call_id,
                        "tool_ref": tool_ref,
                        "status": "OK",
                    }
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


def _injected(tool: Tool, agent: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """모델이 정하면 안 되는 인자.

    `team_id` 를 모델에게 맡기면 프롬프트로 남의 팀 문서를 읽어 낼 수 있다.
    테넌트 경계는 언제나 서버가 정한다.
    """

    if tool.ref == "document_search":
        return {"team_id": agent["team_id"]}
    if tool.ref == "workload_report":
        account_id = context.get("account_id")
        if not account_id:
            # 대화 없이 도는 경로(평가·A2A)에는 요청자가 없다. 조용히 남의 팀
            # 값을 쓰지 않고 이 도구만 실패시킨다.
            raise ValueError("workload_report 는 요청자 계정(account_id)이 필요합니다.")
        return {"account_id": account_id}
    return {}


def _assistant_turn(decision: ModelDecision) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": decision.text or "",
        "tool_calls": decision.tool_calls,
    }


def _tool_turn(call: dict[str, Any], output: Any) -> dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": call.get("id"),
        "tool_ref": call["tool_ref"],
        "content": json.dumps(output, ensure_ascii=False, default=str),
    }


def _default_model(agent: dict[str, Any]) -> ModelClient:
    """실제 모델 호출부.

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
        response = client.chat.completions.create(
            model=model_name,
            reasoning_effort=effort,
            messages=[{"role": "system", "content": system}, *_for_openai(messages)],
            tools=[_tool_spec(tool) for tool in tools] or None,
        )
        choice = response.choices[0].message
        usage = response.usage
        return ModelDecision(
            text=choice.content,
            tool_calls=[
                {
                    "id": item.id,
                    "tool_ref": item.function.name,
                    "arguments": json.loads(item.function.arguments or "{}"),
                }
                for item in (choice.tool_calls or [])
            ],
            token_in=getattr(usage, "prompt_tokens", 0) or 0,
            token_out=getattr(usage, "completion_tokens", 0) or 0,
        )

    return call


def _tool_spec(tool: Tool) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.ref,
            "description": tool.description,
            "parameters": tool.input_schema,
        },
    }


def _for_openai(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """내부 메시지 모양을 OpenAI 형식으로 옮긴다.

    내부에서 `tool_ref` 를 들고 다니는 이유는 우리 로그와 이벤트가 그 이름으로
    말하기 때문이다. OpenAI 쪽에는 그 필드가 없어서 여기서 떨어뜨린다.
    """

    converted: list[dict[str, Any]] = []
    for message in messages:
        if message["role"] == "tool":
            converted.append(
                {
                    "role": "tool",
                    "tool_call_id": message["tool_call_id"],
                    "content": message["content"],
                }
            )
        elif message["role"] == "assistant" and message.get("tool_calls"):
            converted.append(
                {
                    "role": "assistant",
                    "content": message.get("content") or None,
                    "tool_calls": [
                        {
                            "id": call["id"],
                            "type": "function",
                            "function": {
                                "name": call["tool_ref"],
                                "arguments": json.dumps(
                                    call.get("arguments") or {}, ensure_ascii=False
                                ),
                            },
                        }
                        for call in message["tool_calls"]
                    ],
                }
            )
        else:
            converted.append({"role": message["role"], "content": message.get("content") or ""})
    return converted
