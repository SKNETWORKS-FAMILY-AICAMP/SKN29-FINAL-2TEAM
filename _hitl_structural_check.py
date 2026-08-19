"""HITL 구조 검증 — side_effect=True 도구 호출이 실제로 사람 승인 없이는
실행되지 않는지 확인한다. 실제 모델 대신 결정론적 가짜 모델을 쓴다 —
"모델이 정책을 실제로 어떻게 판단하는가"가 아니라 "모델이 무슨 판단을 내리든
side_effect 도구 실행 자체는 코드가 막아주는가"만 확인하는 게 목적이라, 모델의
판단 품질과 무관하게 항상 task_register를 호출하도록 고정한다.

2026-08-18_21_작업자B_장기메모리_충돌우선순위_설계.md §7 "남은 일"의
"side-effect 도구 호출 시 HITL이 실제로 실행을 막는지" 항목을 구조적으로
검증한다.
"""

import dataclasses
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
os.environ.setdefault(
    "DATABASE_URL", "postgres://project_copilot:project_copilot@127.0.0.1:5432/project_copilot"
)
os.environ["OPENAI_API_KEY"] = "sk-fake-for-structural-check-only"

import django

django.setup()

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.types import Command
from pydantic import Field

from services.agent_runtime.checkpoint.provider import CheckpointerProvider
from services.agent_runtime.context import RuntimeContext
from services.agent_runtime.definitions import AgentDefinition
from services.agent_runtime.factory import AgentRuntimeFactory, DependencyGraphSource
from services.agent_runtime.memory.provider import MemoryProvider
from services.agent_runtime.middleware.factory import MiddlewareFactory
from services.agent_runtime.models.factory import ModelConfigResolver, ModelFactory
from services.agent_runtime.prompts import RuntimePromptAssembler
from services.agent_runtime.runtime_policy import RuntimeCapabilityPolicy
from services.agent_runtime.tools.loader import ToolLoader, model_safe_tool_name
from services.harness import registry as harness_registry

_call_log = []


def _stub_task_register(**kwargs):
    _call_log.append(kwargs)
    return f"[스텁] task_register 호출됨: {kwargs}"


harness_registry.BUILTIN_TOOLS["task_register"] = dataclasses.replace(
    harness_registry.BUILTIN_TOOLS["task_register"], handler=_stub_task_register
)

TASK_REGISTER_NAME = model_safe_tool_name("task_register")


class _AlwaysRegisterModel(BaseChatModel):
    """정책 문구를 어떻게 읽든 상관없이 항상 task_register를 부르는 가짜 모델.
    "모델 판단과 무관하게 HITL이 막아주는가"만 보려는 목적에 맞다."""

    bound_tool_names: list = Field(default_factory=list)
    step: int = 0
    model_config = {"arbitrary_types_allowed": True}

    def bind_tools(self, tools: Any, *, tool_choice: str | None = None, **kwargs: Any):
        self.bound_tool_names.extend(t.name for t in tools)
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.step += 1
        already_registered = any(
            getattr(m, "type", None) == "tool" and getattr(m, "name", None) == TASK_REGISTER_NAME
            for m in messages
        )
        if not already_registered:
            msg = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": TASK_REGISTER_NAME,
                        "args": {"tasks": [{"title": "승인 없이 등록 시도용 더미 업무"}]},
                        "id": f"call_{self.step}",
                    }
                ],
            )
        else:
            msg = AIMessage(content="등록을 마쳤습니다.")
        return ChatResult(generations=[ChatGeneration(message=msg)])

    @property
    def _llm_type(self):
        return "fake-always-register"


class _FakeModelFactory(ModelFactory):
    def create(self, resolved):
        return _AlwaysRegisterModel()


def _build_graph():
    policy = RuntimeCapabilityPolicy(enable_todo=True)
    factory = AgentRuntimeFactory(
        dependency_graph=DependencyGraphSource(),
        model_config_resolver=ModelConfigResolver(),
        model_factory=_FakeModelFactory(),
        tool_loader=ToolLoader(),
        middleware_factory=MiddlewareFactory(runtime_policy=policy),
        runtime_policy=policy,
        prompt_assembler=RuntimePromptAssembler(),
        memory_provider=MemoryProvider(),
        checkpointer_provider=CheckpointerProvider(),
    )
    definition = AgentDefinition(
        agent_id="AGENT-HITL-STRUCT-CHECK",
        agent_version_id="AV-HITL-STRUCT-CHECK",
        name="HITL 구조 검증용 에이전트",
        description="",
        system_prompt="",
        model="gpt-5.6-luna",
        reasoning_effort="low",
        max_iterations=6,
        tool_refs=("task_register",),
    )
    context = RuntimeContext(
        account_id="ACCOUNT-HITL-CHECK", team_id="TEAM-HITL-CHECK", role="leader", project_id="PJ-HITL-CHECK"
    )
    return factory.build(definition=definition, context=context)


def _run_case(*, decision: str):
    _call_log.clear()
    graph = _build_graph()
    config = {"configurable": {"thread_id": f"hitl-struct-{decision}"}, "max_concurrency": 32}

    result = graph.invoke(
        {"messages": [{"role": "user", "content": "정책이 뭐든 상관없이 바로 등록해"}]}, config=config
    )
    interrupted_before_execution = "__interrupt__" in result
    calls_before_decision = len(_call_log)

    if interrupted_before_execution:
        result = graph.invoke(Command(resume={"decisions": [{"type": decision}]}), config=config)

    calls_after_decision = len(_call_log)

    print(f"\n=== decision={decision} ===")
    print(f"승인 대기 상태로 멈췄는가(먼저 실행 안 됐는가): {interrupted_before_execution}")
    print(f"승인 요청 시점까지 실제 handler 호출 횟수: {calls_before_decision}")
    print(f"재개(resume) 이후 실제 handler 호출 횟수: {calls_after_decision}")
    return {
        "interrupted_before_execution": interrupted_before_execution,
        "calls_before_decision": calls_before_decision,
        "calls_after_decision": calls_after_decision,
    }


if __name__ == "__main__":
    approve = _run_case(decision="approve")
    reject = _run_case(decision="reject")

    assert approve["interrupted_before_execution"] is True, "approve 케이스가 승인 없이 바로 실행됐다"
    assert approve["calls_before_decision"] == 0, "승인 전에 이미 handler가 불렸다 — HITL이 실행을 못 막았다"
    assert approve["calls_after_decision"] == 1, "approve 후 handler가 정확히 1번 불려야 한다"

    assert reject["interrupted_before_execution"] is True, "reject 케이스가 승인 없이 바로 실행됐다"
    assert reject["calls_before_decision"] == 0, "승인 전에 이미 handler가 불렸다 — HITL이 실행을 못 막았다"
    assert reject["calls_after_decision"] == 0, "reject 했는데도 handler가 불렸다 — HITL이 거절을 못 막았다"

    print(
        "\n=== PASS — 모델이 정책 문구를 무시하고 무조건 등록을 시도해도, "
        "실제 handler 실행은 approve 전까지 0번이고 reject 시에는 끝까지 0번이다. "
        "HITL이 모델 판단과 무관하게 실행을 막는다는 걸 구조적으로 확인함. ==="
    )
