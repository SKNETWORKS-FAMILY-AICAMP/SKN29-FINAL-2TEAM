"""§8.10 "격리 실행 하네스" + §8.11 "라우팅 테스트와 행동 테스트 분리".

정본: 03_스킬_검증_등록_설계.md §8.10/§8.11. 실제 개인 Store·외부 시스템을
쓰지 않는 완전히 격리된 미니 에이전트로, 실제 production 시스템 프롬프트·
미들웨어·모델 해석을 재사용해 후보 스킬이 실제 상황에서 골라지는지 잰다.
"""

from __future__ import annotations

import uuid
import queue
import re
import threading
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from .ephemeral_skills import EVAL_CANDIDATE_PATH_PREFIX, EphemeralSkillSnapshot, EvalSkillsProvider
from .stub_tools import EvalToolLoader, ToolCallRecorder
from .types import SkillEvalCase
from .config import EVAL_SINGLE_RUN_TIMEOUT_SECONDS


class EvalCheckpointerProvider:
    """`CheckpointerProvider`(services/agent_runtime/checkpoint/provider.py)와
    같은 얇은 파사드 — 실제 Postgres 대신 실행 하나짜리 인메모리 체크포인터를
    돌려준다. 행동 테스트의 HITL 재생(§8.10)에 필요하다 — `Command(resume=...)`
    는 checkpointer가 있어야만 동작한다(langgraph 자체 제약, `stream_adapter.py`
    가 이미 의존, 정본 §15 20번에서 실측 확인)."""

    def __init__(self) -> None:
        from langgraph.checkpoint.memory import MemorySaver

        self._saver = MemorySaver()

    def get(self):
        return self._saver


def _build_eval_factory(*, tool_loader: EvalToolLoader, skills_provider: EvalSkillsProvider, checkpointer_provider):
    """실제 production 조립(`bootstrap.build_default_executor()`)과 같은 모양으로
    만들되 tool_loader/skills_provider/checkpointer_provider/memory_provider만
    평가용으로 바꾼다.

    `AgentRuntimeFactory.__init__`이 이 넷을 이미 주입 가능한 인자로 받는다는
    걸 실측으로 확인했다(정본 §15 17번) — 새 구조가 필요 없다.
    """

    from services.agent_runtime.factory import AgentRuntimeFactory, DependencyGraphSource
    from services.agent_runtime.middleware.factory import MiddlewareFactory
    from services.agent_runtime.models.factory import ModelConfigResolver, ModelFactory
    from services.agent_runtime.prompts import RuntimePromptAssembler
    from services.agent_runtime.runtime_policy import RuntimeCapabilityPolicy

    policy = RuntimeCapabilityPolicy()
    return AgentRuntimeFactory(
        dependency_graph=DependencyGraphSource(),
        model_config_resolver=ModelConfigResolver(),
        model_factory=ModelFactory(),
        tool_loader=tool_loader,
        middleware_factory=MiddlewareFactory(runtime_policy=policy),
        runtime_policy=policy,
        prompt_assembler=RuntimePromptAssembler(),
        memory_provider=None,
        checkpointer_provider=checkpointer_provider,
        skills_provider=skills_provider,
    )


@dataclass
class CaseRunResult:
    case_id: str
    attempt: int
    activated_candidate: bool | None
    called_tool_refs: list[str]
    interrupted: bool = False
    error: str | None = None


def _run_once(
    *,
    case: SkillEvalCase,
    executor,
    agent_id: str,
    agent_version_id: str,
    account_id: str,
    team_id: str,
    attempt: int,
    recorder: ToolCallRecorder,
) -> CaseRunResult:
    from services.agent_runtime.context import RuntimeContext

    run_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    context = RuntimeContext(
        # 평가 실행은 매번 새 그래프다. 새 UUID를 thread_id로 넘기면
        # stream adapter가 "체크포인터에 과거 턴이 있다"고 간주해 합성
        # conversation_messages를 버린다. 라우팅 평가는 재개가 없으므로
        # thread_id를 주지 않고 명시적인 과거 턴을 그대로 입력한다.
        account_id=account_id, team_id=team_id, role="member", session_id=None, run_id=run_id
    )

    conversation_messages, user_input = _case_input(case)

    activated = False
    interrupted = False
    error: str | None = None
    try:
        for event in executor.run(
            agent_id=agent_id,
            agent_version_id=agent_version_id,
            user_input=user_input,
            context=context,
            conversation_messages=conversation_messages,
        ):
            if event.get("type") == "tool_started" and event.get("tool_ref") == "read_file":
                file_path = str((event.get("arguments") or {}).get("file_path") or "")
                if file_path.startswith(EVAL_CANDIDATE_PATH_PREFIX):
                    activated = True
            if event.get("type") == "awaiting_confirmation":
                interrupted = True
            if event.get("type") == "error":
                error = str(event.get("detail") or event.get("message") or "실행 오류")
    except Exception as exc:  # noqa: BLE001 — 평가 실행 하나의 실패가 전체를 죽이면 안 된다
        error = f"{exc.__class__.__name__}: {exc}"

    return CaseRunResult(
        case_id=case["case_id"],
        attempt=attempt,
        activated_candidate=activated,
        called_tool_refs=recorder.tool_refs(),
        interrupted=interrupted,
        error=error,
    )


def run_routing_case(
    *,
    case: SkillEvalCase,
    snapshot: EphemeralSkillSnapshot,
    agent_id: str,
    agent_version_id: str,
    account_id: str,
    team_id: str,
    attempts: int = 3,
    attempt_offset: int = 0,
) -> list[CaseRunResult]:
    """라우팅 테스트 — 케이스 하나를 `attempts`회 반복 실행한다(§8.11, 기본 3회).

    실행마다 완전히 새 `EvalToolLoader`(빈 recorder)와 새 `AgentExecutor`를
    만든다 — 반복 사이에 상태가 새지 않게 하기 위해서다(checkpointer도 없어
    실행마다 완전히 새 대화로 시작한다).
    """

    from services.agent_runtime.executor import AgentExecutor
    from services.agent_runtime.loader import AgentDefinitionLoader

    results = []
    for attempt in range(1, attempts + 1):
        recorder = ToolCallRecorder()
        tool_loader = EvalToolLoader(tool_fixtures=_tool_fixtures(case), recorder=recorder)
        skills_provider = EvalSkillsProvider(snapshot)
        factory = _build_eval_factory(
            tool_loader=tool_loader, skills_provider=skills_provider, checkpointer_provider=None
        )
        executor = AgentExecutor(loader=AgentDefinitionLoader(), factory=factory)
        result = _bounded_call(
            lambda: _run_once(
                case=case,
                executor=executor,
                agent_id=agent_id,
                agent_version_id=agent_version_id,
                account_id=account_id,
                team_id=team_id,
                attempt=attempt_offset + attempt,
                recorder=recorder,
            ),
            EVAL_SINGLE_RUN_TIMEOUT_SECONDS,
        )
        results.append(result if result is not None else CaseRunResult(
            case_id=case["case_id"], attempt=attempt_offset + attempt,
            activated_candidate=None, called_tool_refs=[], error="EVAL_RUN_TIMEOUT",
        ))
    return results


@dataclass
class BehaviorRunResult:
    case_id: str
    activated_candidate: bool | None
    called_tool_refs: list[str]
    deterministic_tool_failures: list[str] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    final_response: str = ""
    error: str | None = None


def _bounded_call(fn, timeout_seconds: float):
    """호출 하나가 멈춰도 워커 전체를 붙잡지 않는 30초 경계."""
    output: queue.Queue = queue.Queue(maxsize=1)

    def invoke() -> None:
        try:
            output.put((True, fn()))
        except BaseException as exc:  # noqa: BLE001
            output.put((False, exc))

    threading.Thread(target=invoke, daemon=True, name="skill-eval-bounded-call").start()
    try:
        ok, value = output.get(timeout=timeout_seconds)
    except queue.Empty:
        return None
    if not ok:
        raise value
    return value


def _tool_fixtures(case: SkillEvalCase) -> dict[str, list[dict[str, Any]]]:
    fixtures = {key: list(value) for key, value in (case.get("tool_fixtures") or {}).items()}
    documents = case.get("document_fixtures") or []
    if documents:
        listed = [{"document_id": d["document_id"], "title": d["title"]} for d in documents]
        fixtures.setdefault("document_list", []).append({"documents": listed})
        fixtures.setdefault("document_search", []).append({"results": documents})
    return fixtures


def _case_input(
    case: SkillEvalCase, *, flatten_history: bool = False
) -> tuple[list[dict[str, str]], str]:
    """이전 대화와 현재 입력을 실제 실행 가능한 형태로 만든다.

    ``document_fixtures``는 stub 검색 도구의 응답일 뿐 아니라 테스트 요청에
    첨부된 합성 문서다. 내용이 현재 입력에 전달되지 않으면 도구를 쓰지 않는
    요약·번역 스킬은 존재하지 않는 첨부를 보게 된다. 실제 파일을 읽지 않고
    합성 내용만 명시적인 첨부 블록으로 현재 요청에 제공한다.
    """

    conversation = [{"role": m["role"], "content": m["content"]} for m in case["messages"][:-1]]
    user_input = case["messages"][-1]["content"]
    documents = case.get("document_fixtures") or []
    if documents:
        attachment_blocks = [
            f"[첨부 문서: {document['title']}]\n{document['content']}" for document in documents
        ]
        attachment_text = "\n\n".join(attachment_blocks)
        user_input = f"{attachment_text}\n\n[사용자 요청]\n{user_input}"
    if flatten_history and conversation:
        labels = {"user": "사용자", "assistant": "도우미"}
        transcript = "\n".join(
            f"{labels.get(message['role'], message['role'])}: {message['content']}"
            for message in conversation
        )
        user_input = f"[이전 대화]\n{transcript}\n\n[현재 요청]\n{user_input}"
        conversation = []
    return conversation, user_input


def _event_text(event: dict[str, Any]) -> str:
    """Root의 최종 답변만 반환한다.

    도구 완료 이벤트의 ``output``까지 최종 응답으로 취급하면, 마지막 도구가
    ``read_file``인 스킬 실행에서 SKILL.md 원문을 행동 reviewer에게 보내게
    된다. 운영 EventMapper의 최종 답변 계약은 ``type=result, text=...``다.
    """

    if event.get("type") != "result":
        return ""
    value = event.get("text")
    return value if isinstance(value, str) else ""


def _value_at_path(value: Any, path: str) -> tuple[bool, Any]:
    current = value
    normalized = path.removeprefix("$").lstrip(".")
    for key, index in re.findall(r"([^.\[\]]+)|\[(\d+)\]", normalized):
        if key:
            if not isinstance(current, dict) or key not in current:
                return False, None
            current = current[key]
        else:
            position = int(index)
            if not isinstance(current, (list, tuple)) or position >= len(current):
                return False, None
            current = current[position]
    return True, current


def _check_argument_rule(args: dict[str, Any], rule: dict[str, Any]) -> bool:
    exists, actual = _value_at_path(args, str(rule.get("path") or rule.get("json_path") or ""))
    operator = rule.get("operator") or rule.get("op") or "equals"
    expected = rule.get("value")
    if operator == "exists":
        return exists is bool(expected if expected is not None else True)
    if not exists:
        return False
    if operator == "equals":
        return actual == expected
    if operator == "not_equals":
        return actual != expected
    if operator == "contains":
        if isinstance(actual, str):
            return str(expected) in actual
        return expected in actual if isinstance(actual, (list, tuple, set)) else False
    if operator in {"regex", "matches"}:
        return re.search(str(rule.get("pattern") or expected or ""), str(actual)) is not None
    return False


def _run_behavior_case(
    *,
    case: SkillEvalCase,
    snapshot: EphemeralSkillSnapshot,
    agent_id: str,
    agent_version_id: str,
    account_id: str,
    team_id: str,
) -> BehaviorRunResult:
    """행동 테스트 대표 케이스 하나 — §8.10 "HITL 재생"까지 포함한 전체 실행 1회.

    side-effect 도구 호출이 interrupt를 만들면 `approval_fixtures`의 결정으로
    자동 resume한다. fixture에 없는 결정이 필요하면 그 자리에서
    `UNEXPECTED_APPROVAL_REQUEST`로 기록하고 멈춘다(§8.10 마지막 문단).
    """

    from services.agent_runtime.context import RuntimeContext
    from services.agent_runtime.executor import AgentExecutor
    from services.agent_runtime.loader import AgentDefinitionLoader

    recorder = ToolCallRecorder()
    tool_loader = EvalToolLoader(tool_fixtures=_tool_fixtures(case), recorder=recorder)
    skills_provider = EvalSkillsProvider(snapshot)
    checkpointer_provider = EvalCheckpointerProvider()
    factory = _build_eval_factory(
        tool_loader=tool_loader, skills_provider=skills_provider, checkpointer_provider=checkpointer_provider
    )
    executor = AgentExecutor(loader=AgentDefinitionLoader(), factory=factory)

    run_id = str(uuid.uuid4())
    needs_checkpoint = bool(case.get("approval_fixtures"))
    session_id = str(uuid.uuid4()) if needs_checkpoint else None
    context = RuntimeContext(
        account_id=account_id, team_id=team_id, role="member", session_id=session_id, run_id=run_id
    )
    conversation_messages, user_input = _case_input(case, flatten_history=needs_checkpoint)

    approval_by_tool: dict[str, deque[str]] = defaultdict(deque)
    for fixture in case.get("approval_fixtures", []):
        approval_by_tool[fixture["tool_ref"]].append(fixture["decision"])
    activated = False
    deterministic_failures: list[str] = []
    error: str | None = None
    final_response = ""

    try:
        events = executor.run(
            agent_id=agent_id,
            agent_version_id=agent_version_id,
            user_input=user_input,
            context=context,
            conversation_messages=conversation_messages,
        )
        interrupt_count = 0
        while True:
            pending_actions: list[dict[str, Any]] | None = None
            for event in events:
                text = _event_text(event)
                if text:
                    final_response = text
                if event.get("type") == "tool_started" and event.get("tool_ref") == "read_file":
                    file_path = str((event.get("arguments") or {}).get("file_path") or "")
                    if file_path.startswith(EVAL_CANDIDATE_PATH_PREFIX):
                        activated = True
                if event.get("type") == "awaiting_confirmation":
                    pending_actions = (
                        [{"name": r["name"]} for r in event["action_requests"]]
                        if "action_requests" in event
                        else [{"name": event.get("tool_name")}]
                    )
                    break
                if event.get("type") == "error":
                    error = str(event.get("detail") or event.get("message") or "실행 오류")
            if pending_actions is None:
                break
            interrupt_count += 1
            if interrupt_count > 20:
                deterministic_failures.append("TOO_MANY_APPROVAL_REQUESTS")
                break
            decisions = []
            for index, action in enumerate(pending_actions):
                tool_name = action.get("name")
                queue_for_tool = approval_by_tool.get(tool_name or "")
                if not queue_for_tool:
                    deterministic_failures.append("UNEXPECTED_APPROVAL_REQUEST")
                    decision = "reject"
                else:
                    decision = queue_for_tool.popleft()
                decisions.append({"action_index": index, "type": decision})
            events = executor.resume(
                agent_id=agent_id, agent_version_id=agent_version_id, context=context, decisions=decisions
            )
    except Exception as exc:  # noqa: BLE001
        error = f"{exc.__class__.__name__}: {exc}"

    called = recorder.tool_refs()
    first_positions: list[int] = []
    for expectation in case.get("required_tools", []):
        tool_ref = expectation["tool_ref"]
        count = called.count(tool_ref)
        if count < expectation.get("min_calls", 1):
            deterministic_failures.append(f"MISSING_REQUIRED_TOOL:{tool_ref}")
        max_calls = expectation.get("max_calls")
        if max_calls is not None and count > max_calls:
            deterministic_failures.append(f"TOO_MANY_CALLS:{tool_ref}")
        positions = [index for index, call in enumerate(recorder.calls) if call.tool_ref == tool_ref]
        if positions:
            first_positions.append(positions[0])
        for rule in expectation.get("argument_rules") or []:
            if not any(_check_argument_rule(call.args, rule) for call in recorder.calls if call.tool_ref == tool_ref):
                deterministic_failures.append(f"ARGUMENT_RULE_FAILED:{tool_ref}")
    if first_positions != sorted(first_positions):
        deterministic_failures.append("TOOL_ORDER_MISMATCH")
    for tool_ref in case.get("forbidden_tools", []):
        if tool_ref in called:
            deterministic_failures.append(f"FORBIDDEN_TOOL_CALLED:{tool_ref}")

    return BehaviorRunResult(
        case_id=case["case_id"],
        activated_candidate=activated,
        called_tool_refs=called,
        deterministic_tool_failures=deterministic_failures,
        tool_calls=[{"tool_ref": call.tool_ref, "args": call.args} for call in recorder.calls],
        final_response=final_response,
        error=error,
    )


def run_behavior_case(**kwargs: Any) -> BehaviorRunResult:
    case = kwargs["case"]
    try:
        result = _bounded_call(lambda: _run_behavior_case(**kwargs), EVAL_SINGLE_RUN_TIMEOUT_SECONDS)
    except Exception as exc:  # noqa: BLE001
        return BehaviorRunResult(case_id=case["case_id"], activated_candidate=None, called_tool_refs=[], error=f"{exc.__class__.__name__}: {exc}")
    return result if result is not None else BehaviorRunResult(
        case_id=case["case_id"], activated_candidate=None, called_tool_refs=[], error="EVAL_RUN_TIMEOUT"
    )


__all__ = [
    "EvalCheckpointerProvider",
    "CaseRunResult",
    "BehaviorRunResult",
    "run_routing_case",
    "run_behavior_case",
]
