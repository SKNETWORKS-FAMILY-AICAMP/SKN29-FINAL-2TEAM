"""Root·GP·Child 조립과 Tool 노출을 확인하는 수동 검증 스크립트.

실제 API 대신 미리 정한 응답을 내는 가짜 모델을 사용한다.
실행: `python services/agent_runtime/_spike/runtime_skeleton.py`
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

if sys.version_info < (3, 11):
    print(
        f"이 스크립트는 Python >= 3.11이 필요하다 (현재 {sys.version}). "
        "deepagents requires-python이 >=3.11이다.",
        file=sys.stderr,
    )
    raise SystemExit(1)

try:
    from pydantic import Field
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, ChatResult
    from langchain_core.tools import BaseTool
except ImportError as exc:
    print("langchain-core가 없다. `pip install langchain`", file=sys.stderr)
    raise SystemExit(1) from exc

try:
    from deepagents import CompiledSubAgent
except ImportError as exc:
    print("deepagents가 없다. `pip install deepagents==0.7.5`", file=sys.stderr)
    raise SystemExit(1) from exc

# `services.agent_runtime` 절대 import를 위해 저장소 루트를 추가한다.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

try:
    from services.agent_runtime.compat import (
        assert_supported_version,
        build_general_purpose_spec,
        create_child_graph,
        create_root_graph,
        register_default_harness_profile,
    )
except ImportError as exc:
    print(
        "services.agent_runtime.compat을 import할 수 없다 — 저장소 루트에서 실행 중인지, "
        "compat/deepagents_v075.py가 존재하는지 확인할 것.",
        file=sys.stderr,
    )
    raise SystemExit(1) from exc


class ScriptedToolCallingModel(BaseChatModel):
    """준비된 응답을 반환하고 모델에 노출된 Tool 이름을 기록한다."""

    responses: list[AIMessage] = Field(default_factory=list)
    call_count: int = 0
    bind_calls_log: list[list[str]] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}

    def bind_tools(self, tools: Any, *, tool_choice: str | None = None, **kwargs: Any) -> "ScriptedToolCallingModel":
        names: list[str] = []
        for t in tools:
            if isinstance(t, BaseTool):
                names.append(t.name)
            elif isinstance(t, dict):
                names.append(t.get("name") or (t.get("function") or {}).get("name"))
            else:
                names.append(getattr(t, "name", None) or getattr(t, "__name__", str(t)))
        self.bind_calls_log.append(names)
        return self

    def _generate(self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any) -> ChatResult:
        idx = min(self.call_count, len(self.responses) - 1)
        response = self.responses[idx]
        self.call_count += 1
        return ChatResult(generations=[ChatGeneration(message=response)])

    @property
    def _llm_type(self) -> str:
        return "scripted-fake"

    @property
    def ever_bound_tool_names(self) -> set[str]:
        names: set[str] = set()
        for call in self.bind_calls_log:
            names.update(n for n in call if n)
        return names


def _assert(condition: bool, label: str) -> None:
    print(f"[{'PASS' if condition else 'FAIL'}] {label}")
    if not condition:
        raise SystemExit(f"검증 실패: {label}")


def get_server_time() -> str:
    """현재 서버 시각을 ISO 8601 문자열로 반환한다."""
    from datetime import datetime

    return datetime.now().isoformat()


def main() -> None:
    # 지원 버전 확인
    assert_supported_version()
    print(f"=== deepagents 버전 확인 통과 (=={__import__('deepagents').__version__}) ===\n")

    # 가짜 모델에 자동 general-purpose 비활성화 프로필 적용
    register_default_harness_profile(model_key="scriptedtoolcallingmodel")
    print("=== 전역 harness profile 등록: 자동 general-purpose 비활성화 (compat.register_default_harness_profile) ===\n")

    # A. 단순 응답
    print("=== A. 단순 응답 ===")
    model_a = ScriptedToolCallingModel(responses=[AIMessage(content="안녕하세요")])
    agent_a = create_root_graph(model=model_a, system_prompt="너는 테스트용 에이전트다.", tools=[], subagents=[])
    result_a = agent_a.invoke({"messages": [{"role": "user", "content": "안녕"}]})
    _assert(bool(result_a["messages"][-1].content), "단순 응답이 비어있지 않다")

    # B. Root Tool 호출
    print("\n=== B. Root Tool 호출 ===")
    model_b = ScriptedToolCallingModel(
        responses=[
            AIMessage(content="", tool_calls=[{"name": "get_server_time", "args": {}, "id": "b1"}]),
            AIMessage(content="지금은 자정입니다."),
        ]
    )
    agent_b = create_root_graph(
        model=model_b,
        system_prompt="사용자가 시간을 물으면 반드시 get_server_time 도구를 호출해서 답하라.",
        tools=[get_server_time],
        subagents=[],
    )
    result_b = agent_b.invoke({"messages": [{"role": "user", "content": "지금 몇 시야?"}]})
    tool_msgs_b = [m for m in result_b["messages"] if getattr(m, "name", None) == "get_server_time"]
    _assert(len(tool_msgs_b) >= 1, "get_server_time 도구가 실제로 호출됐다")

    # D/E/F. Child Tool 호출과 task 미노출 확인
    print("\n=== D/E/F. Child 독립 컴파일 — task 미노출 + 내부 도구 호출 확인 ===")
    child_model = ScriptedToolCallingModel(
        responses=[
            AIMessage(content="", tool_calls=[{"name": "get_server_time", "args": {}, "id": "c1"}]),
            AIMessage(content="자정입니다."),
        ]
    )
    child_graph = create_child_graph(
        model=child_model,
        system_prompt="사용자가 시간을 물으면 get_server_time 도구로 답하라.",
        tools=[get_server_time],
    )
    child_result = child_graph.invoke({"messages": [{"role": "user", "content": "지금 몇 시야?"}]})
    child_tool_msgs = [m for m in child_result["messages"] if getattr(m, "name", None) == "get_server_time"]
    _assert(len(child_tool_msgs) >= 1, "E. Child가 자신의 도구를 호출했다")
    _assert(
        "task" not in child_model.ever_bound_tool_names,
        f"F. Child에게 task 툴이 노출된 적이 없다 (실제 bind 이력: {child_model.bind_calls_log})",
    )

    child = CompiledSubAgent(name="time_teller", description="현재 서버 시각을 물어볼 때 사용한다.", runnable=child_graph)

    # D. Root가 저장된 Child에게 위임
    print("\n=== D. Root -> 저장된 Child 위임 ===")
    root_model_d = ScriptedToolCallingModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "task", "args": {"subagent_type": "time_teller", "description": "지금 몇 시인지 확인"}, "id": "d1"}],
            ),
            AIMessage(content="지금은 자정입니다 (Child 위임 결과)."),
        ]
    )
    root_gp_spec = build_general_purpose_spec()
    root_d = create_root_graph(
        model=root_model_d,
        system_prompt="사용자가 시간을 물으면 반드시 time_teller 서브 에이전트에게 위임하라.",
        tools=[],
        subagents=[root_gp_spec, child],
    )
    result_d = root_d.invoke({"messages": [{"role": "user", "content": "지금 몇 시야?"}]})
    # Tool 바인딩은 실행 시점에 일어나므로 invoke() 뒤에 검사한다.
    _assert("task" in root_model_d.ever_bound_tool_names, "Root에게 task 툴이 노출된다")
    delegation_msgs_d = [m for m in result_d["messages"] if getattr(m, "name", None) == "task"]
    _assert(len(delegation_msgs_d) >= 1, "Root가 저장된 Child(time_teller)에게 실제로 위임했다")

    # C. Root가 명시적 general-purpose에게 위임
    print("\n=== C. Root -> 명시적 general-purpose 위임 ===")
    root_model_c = ScriptedToolCallingModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "task", "args": {"subagent_type": "general-purpose", "description": "아무 파일이나 찾아봐"}, "id": "c1"}],
            ),
            AIMessage(content="GP가 찾아본 결과입니다."),
        ]
    )
    root_c = create_root_graph(
        model=root_model_c,
        system_prompt="파일 조사가 필요하면 general-purpose에게 위임하라.",
        tools=[],
        subagents=[build_general_purpose_spec()],
    )
    result_c = root_c.invoke({"messages": [{"role": "user", "content": "아무 파일이나 찾아줘"}]})
    delegation_msgs_c = [m for m in result_c["messages"] if getattr(m, "name", None) == "task"]
    _assert(len(delegation_msgs_c) >= 1, "Root가 명시적 general-purpose에게 위임했다(자동 GP가 아니라 우리가 넣은 spec)")

    # G. 스트림에서 Root와 Child 네임스페이스 구분
    print("\n=== G. updates 스트림 네임스페이스 구분 ===")
    root_model_g = ScriptedToolCallingModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "task", "args": {"subagent_type": "time_teller", "description": "몇 시인지"}, "id": "g1"}],
            ),
            AIMessage(content="최종 답변."),
        ]
    )
    root_g = create_root_graph(
        model=root_model_g,
        system_prompt="위임하라.",
        tools=[],
        subagents=[build_general_purpose_spec(), child],
    )
    namespaces: set[str] = set()
    for namespace, _mode, _payload in root_g.stream(
        {"messages": [{"role": "user", "content": "몇 시야?"}]},
        stream_mode=["updates"],
        subgraphs=True,
    ):
        namespaces.add(namespace[0] if namespace else "(root)")
    _assert(len(namespaces) >= 2, f"부모/자식 네임스페이스가 스트림에서 구분됨 (관측: {namespaces})")

    print("\n=== 전체 통과 — 6개 검증 항목 확인됨 ===")
    print(
        "1. Root의 tool 목록에 task가 있다: PASS\n"
        "2. Child의 tool 목록에 task가 없다: PASS\n"
        "3. Root가 GP를 호출한다: PASS\n"
        "4. Root가 저장된 Child를 호출한다: PASS\n"
        "5. Child가 자신의 Tool을 호출한다: PASS\n"
        "6. Child는 다시 위임을 시도할 수 없다(task 자체가 없음): PASS"
    )


if __name__ == "__main__":
    main()
