import dataclasses
import json
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

import django

django.setup()

from langgraph.types import Command

from services.agent_runtime.checkpoint.provider import CheckpointerProvider
from services.agent_runtime.context import RuntimeContext
from services.agent_runtime.definitions import AgentDefinition
from services.agent_runtime.factory import AgentRuntimeFactory, DependencyGraphSource
from services.agent_runtime.memory.provider import MemoryProvider
from services.agent_runtime.middleware.factory import MiddlewareFactory
from services.agent_runtime.models.factory import ModelConfigResolver, ModelFactory
from services.agent_runtime.prompts import RuntimePromptAssembler
from services.agent_runtime.runtime_policy import RuntimeCapabilityPolicy
from services.agent_runtime.tools.loader import ToolLoader
from services.harness import registry as harness_registry

MODEL_ID = os.environ.get("AGENT_LIVE_CHECK_MODEL", "gpt-5.6-luna")
REASONING_EFFORT = os.environ.get("AGENT_LIVE_CHECK_REASONING_EFFORT", "low")
TEAM_ID = os.environ.get("AGENT_LIVE_CHECK_TEAM_ID", "TEAM-QUERY-CHECK")
ACCOUNT_ID = os.environ.get("AGENT_LIVE_CHECK_ACCOUNT_ID", "ACCOUNT-QUERY-CHECK")
PROJECT_ID = os.environ.get("AGENT_LIVE_CHECK_PROJECT_ID") or None
AGENT_ID = "AGENT-QUERY-CHECK"

_side_effect_call_log = []


def _stub_side_effect_handler(ref):
    def _handler(**kwargs):
        _side_effect_call_log.append({"ref": ref, "args": kwargs})
        return f"[스텁] {ref} 호출됨: {kwargs}"

    return _handler


def _stub_side_effect_handlers_in_registry():
    for ref, tool in list(harness_registry.BUILTIN_TOOLS.items()):
        if tool.side_effect:
            harness_registry.BUILTIN_TOOLS[ref] = dataclasses.replace(
                tool, handler=_stub_side_effect_handler(ref)
            )


_stub_side_effect_handlers_in_registry()

ALL_TOOL_REFS = tuple(harness_registry.BUILTIN_TOOLS.keys())


def _build_factory():
    policy = RuntimeCapabilityPolicy(enable_todo=True)
    return AgentRuntimeFactory(
        dependency_graph=DependencyGraphSource(),
        model_config_resolver=ModelConfigResolver(),
        model_factory=ModelFactory(),
        tool_loader=ToolLoader(),
        middleware_factory=MiddlewareFactory(runtime_policy=policy),
        runtime_policy=policy,
        prompt_assembler=RuntimePromptAssembler(),
        memory_provider=MemoryProvider(),
        checkpointer_provider=CheckpointerProvider(),
    )


def _definition():
    return AgentDefinition(
        agent_id=AGENT_ID,
        agent_version_id="AV-QUERY-CHECK",
        name="사용자 질의 tool-선택 점검용 에이전트",
        description="",
        system_prompt="",
        model=MODEL_ID,
        reasoning_effort=REASONING_EFFORT,
        max_iterations=12,
        tool_refs=ALL_TOOL_REFS,
    )


def _build_graph():
    factory = _build_factory()
    context = RuntimeContext(
        account_id=ACCOUNT_ID, team_id=TEAM_ID, role="leader", project_id=PROJECT_ID
    )
    return factory.build(definition=_definition(), context=context)


def _extract_tool_calls(messages):
    calls = []
    for msg in messages:
        for c in getattr(msg, "tool_calls", None) or []:
            calls.append(c.get("name"))
    return calls


def _final_ai_text(messages):
    for m in reversed(messages):
        if getattr(m, "type", None) != "ai":
            continue
        text = getattr(m, "text", None)
        if text and str(text).strip():
            return str(text)
    return ""


def _state_snapshot(*, graph, config, resume_turns, still_interrupted):
    state = graph.get_state(config)
    messages = state.values.get("messages", [])
    return {
        "tool_calls": _extract_tool_calls(messages),
        "resume_turns": resume_turns,
        "still_interrupted": still_interrupted,
        "final_ai_text": _final_ai_text(messages),
        "todos_state": state.values.get("todos", []),
    }


def _run_scenario(*, graph, thread_id, user_query, max_resume_turns=6):
    config = {"configurable": {"thread_id": thread_id}, "max_concurrency": 32}
    try:
        result = graph.invoke({"messages": [{"role": "user", "content": user_query}]}, config=config)

        resume_turns = 0
        while "__interrupt__" in result and resume_turns < max_resume_turns:
            request = result["__interrupt__"][0].value
            decisions = [{"type": "approve"} for _ in request["action_requests"]]
            result = graph.invoke(Command(resume={"decisions": decisions}), config=config)
            resume_turns += 1
    except Exception as exc:  # noqa: BLE001 - 예외가 나도 그 시점까지의 실제 tool 호출 흔적을 남긴다
        snapshot = _state_snapshot(
            graph=graph, config=config, resume_turns=0, still_interrupted=False
        )
        snapshot["error"] = repr(exc)
        return snapshot

    return _state_snapshot(
        graph=graph, config=config, resume_turns=resume_turns, still_interrupted="__interrupt__" in result
    )


SCENARIOS = [
    {
        "id": 1,
        "label": "가장 진행률 낮은 프로젝트의 미등록 업무 정리",
        "query": (
            "현재 진행 중인 프로젝트 중 가장 진행률이 낮은 프로젝트를 찾아서, 그 프로젝트의 "
            "기준 문서에서 해야 할 업무를 확인하고, 이미 우리 플랫폼에 등록된 업무와 비교해서 "
            "아직 등록되지 않은 업무가 무엇인지 정리해줘."
        ),
        "expected_tools": ["project_list", "task_extraction", "task_list"],
        "checks": ["프로젝트 선택", "기준 문서에서 업무 추출", "기존 등록 업무 조회", "두 결과 비교"],
    },
    {
        "id": 2,
        "label": "API 개발 관련 문서 확인 및 미색인 문서 안내",
        "query": (
            "우리 팀에 현재 어떤 문서가 있는지 먼저 확인하고, 그중 API 개발과 관련된 문서를 "
            "찾아서 인증 방식과 API 변경사항에 대한 내용을 정리해줘. 아직 색인되지 않은 관련 "
            "문서가 있다면 그것도 알려줘."
        ),
        "expected_tools": ["document_list", "document_search"],
        "checks": ["document_list와 document_search를 구분하는지", "not_indexed를 문서가 없는 것으로 오해하지 않는지"],
    },
    {
        "id": 3,
        "label": "신규 개발 업무 담당자 추천",
        "query": (
            "다음 달에 새로운 개발 업무를 하나 맡긴다면 누구에게 맡기는 게 가장 적절한지 "
            "추천해줘. 팀원의 스킬, 현재 업무량, 앞으로의 휴가 일정을 모두 고려하고, 추천 "
            "이유를 구체적으로 설명해줘."
        ),
        "expected_tools": ["people_list", "workload_report", "absence_list"],
        "checks": ["스킬만 보고 추천하지 않는지", "workload와 absence를 함께 고려하는지"],
    },
    {
        "id": 4,
        "label": "등록된 업무 검토(미확정/마감임박/담당자 필요)",
        "query": (
            "현재 프로젝트에 등록된 업무를 확인해서 아직 확정되지 않은 업무가 무엇인지 "
            "정리해줘. 그중 마감일이 가까운 업무가 있다면 어떤 것인지 알려주고, 담당자 배정이 "
            "필요해 보이는 업무도 찾아줘."
        ),
        "expected_tools": ["task_list", "people_list"],
        "checks": ["task_list의 PROPOSED/CONFIRMED/REJECTED를 이해하는지", "등록된 업무와 Jira 업무를 혼동하지 않는지"],
    },
    {
        "id": 5,
        "label": "기준 문서 기반 업무 추출 + 우선순위 판단",
        "query": (
            "프로젝트 기준 문서에서 앞으로 해야 할 업무를 추출해서 정리해줘. 이미 등록된 "
            "업무와 비교해서 빠진 업무가 있는지 확인하고, 새로 해야 할 업무 중 현재 팀 상황을 "
            "고려했을 때 우선적으로 처리해야 할 업무가 무엇인지 알려줘."
        ),
        "expected_tools": ["task_extraction", "task_list", "workload_report", "absence_list", "people_list"],
        "checks": ["문서 → 업무 추출 → 기존 업무 비교 → 팀 상황 분석 → 우선순위 판단"],
    },
]


def run():
    import uuid

    graph = _build_graph()
    results = []
    run_id = uuid.uuid4().hex[:8]

    for scenario in SCENARIOS:
        print(f"\n{'=' * 70}")
        print(f"시나리오 {scenario['id']} — {scenario['label']}")
        print(f"질의: {scenario['query']}")
        print(f"예상 tool: {scenario['expected_tools']}")
        print("=" * 70)

        _side_effect_call_log.clear()
        thread_id = f"query-check-{run_id}-{scenario['id']}"
        result = _run_scenario(graph=graph, thread_id=thread_id, user_query=scenario["query"])

        tool_calls = result["tool_calls"]
        expected = scenario["expected_tools"]
        missing = [t for t in expected if t not in tool_calls]
        extra = [t for t in tool_calls if t not in expected and t != "write_todos"]
        matched = not missing and "error" not in result

        wrote_todos = "write_todos" in tool_calls
        todos_final_state = result["todos_state"]

        if result.get("error"):
            print(f"실행 중 오류(스크립트가 잡음, 그 시점까지의 흔적은 아래): {result['error']}")
        print(f"실제 호출된 tool 순서(전체, 오류 시점까지): {tool_calls}")
        print(f"기대 tool 중 누락: {missing if missing else '없음'}")
        print(f"기대에 없던 추가 tool: {extra if extra else '없음'}")
        print(f"tool 정답 여부(기대 tool 전부 호출됐는지, 오류 없이): {'OK' if matched else 'FAIL'}")
        print(f"write_todos 호출 여부: {'예' if wrote_todos else '아니오'}")
        print(f"승인 재개 턴 수: {result['resume_turns']}, 아직 승인 대기 중: {result['still_interrupted']}")
        if _side_effect_call_log:
            print(f"부수효과 tool 실제 호출 상세(스텁): {_side_effect_call_log}")
        print(f"최종 todos 상태: {todos_final_state}")
        if result["final_ai_text"]:
            print(f"최종 응답: {result['final_ai_text']}")

        results.append(
            {
                **scenario,
                "tool_calls": tool_calls,
                "missing": missing,
                "extra": extra,
                "matched": matched,
                "wrote_todos": wrote_todos,
                "todos_final_state": todos_final_state,
                "final_ai_text": result["final_ai_text"],
                "error": result.get("error"),
            }
        )

    print(f"\n{'=' * 70}")
    print("=== 요약 ===")
    print("=" * 70)
    for r in results:
        if r.get("error"):
            print(
                f"시나리오 {r['id']}({r['label']}): ERROR — {r['error']} "
                f"(오류 시점까지 호출된 tool: {r['tool_calls']})"
            )
            continue
        print(
            f"시나리오 {r['id']}({r['label']}): {'OK' if r['matched'] else 'FAIL'} — "
            f"실제={r['tool_calls']} / write_todos={'Y' if r['wrote_todos'] else 'N'}"
        )

    print("\n=== JSON (파싱용) ===")
    print(json.dumps(results, ensure_ascii=False))

    return results


if __name__ == "__main__":
    run()
