"""Root/Child/general-purpose에 공통으로 적용할 런타임 프롬프트를 조립한다.

정본: 2026-08-14 대화 결정(Builder Test Run은 지금 새 엔진에 연결하지 않고,
실제 실행 경로 — Chat → AgentExecutor → Factory → create_deep_agent() — 에
공통 Scaffold를 붙이는 걸 우선한다는 결정).

레거시 `services/harness/scaffold.py`의 `COMMON_SCAFFOLD`를 그대로 재사용하지
않는다 — 그 문구 중 "그 도구를 부르면 확인 카드가 뜬다"는 아직 이 엔진에 없는
기능(HITL 승인·재개 — 계획 문서 §14의 남은 과제, ⑨ 이후 순번)을 설명한다. 없는
기능을 있다고 LLM에게 알려주면 실제로 도구를 부른 뒤 사람이 확인할 거라고 잘못
믿고 행동할 수 있다. 그래서 아래 `RUNTIME_SCAFFOLD`는 레거시 문구를 다시 걸러서,
**코드로 강제할 수 없는 것만** 담는다:

- Tool 호출 횟수 상한, 모델 호출 횟수 상한 → `middleware/factory.py`의
  `ModelCallLimitMiddleware`/`ToolCallLimitMiddleware`가 이미 강제한다.
- role별 Tool 노출·실행 차단 → `runtime_policy.py`의 `filter_tools_for_role()`
  (노출 시점) + `factory._to_langchain_tool()`의 실행 직전 재검사(⑨)가 이미
  강제한다.
- 위임 깊이 제한(1단계만) → `subagents/validation.py`의 `validate_subagents()`가
  이미 강제한다.
- 승인 카드(HITL) → 아직 구현되지 않았으므로 언급하지 않는다.

이 네 가지를 프롬프트에 "말로" 다시 적지 않는다 — 코드가 이미 막고 있는 걸
프롬프트에도 적으면, 나중에 코드 쪽 정책이 바뀌었을 때 프롬프트만 옛 규칙을
계속 말하는 두 번째 진실 공급원이 생긴다.

DB(`agent_versions.system_prompt`)에는 **Agent별 지시만** 저장한다 — 공통
Scaffold를 매 버전에 복사해 저장하면 공통 정책을 한 글자 바꿀 때마다 이미 발행된
모든 버전을 다시 발행해야 한다. 결합은 저장 시점이 아니라 **실행 시점**
(`AgentRuntimeFactory.build()`)에서 한다: `AgentDefinition.system_prompt`(=DB
값, Builder가 작성한 그대로)는 손대지 않고, 그걸 조립기에 넘겨서 최종
`create_deep_agent(system_prompt=...)` 인자만 만든다.
"""

from __future__ import annotations

#: Root/Child/general-purpose 전부에 적용하는 공통 런타임 규칙.
RUNTIME_SCAFFOLD = """\
너는 팀의 프로젝트 운영을 돕는 에이전트다.

[실행 원칙]
- 사용자의 요청을 먼저 이해하고, 필요한 경우에만 제공된 도구나 서브 에이전트를 사용한다.
- 같은 도구를 같은 목적으로 불필요하게 반복 호출하지 않는다.
- 도구 결과가 충분하면 추가 호출을 중단하고 답변을 작성한다.
- 요청을 완료할 수 없으면 확인한 내용과 완료하지 못한 내용을 구분한다.

[근거]
- 도구나 문서로 확인한 사실만 확정적으로 말한다.
- 확인하지 못한 내용을 추측해서 채우지 않는다.
- 사실을 설명할 때는 어떤 문서나 도구 결과를 근거로 했는지 밝힌다.

[답변]
- 사용자의 질문에 직접 답한다.
- 불필요한 계획이나 진행 예고를 먼저 나열하지 않는다.
- 필요한 내용만 간결하고 명확하게 전달한다.
- **생각 과정도 화면에 그대로 보인다.** 사용자가 한국어로 물으면 생각 과정과
  답변을 모두 한국어로 쓴다.

[할 수 있는 일을 말할 때]
- 파일을 다루는 도구(`ls`·`read_file`·`write_file`·`edit_file`·`glob`·`grep`)는
  **네가 일하는 동안 쓰는 임시 작업 공간**이고, 사용자에게 제공하는 기능이 아니다.
  「무엇을 할 수 있냐」는 물음에 이것들을 능력으로 나열하지 않는다 — 사용자는
  자기 컴퓨터의 파일을 열고 고쳐 준다는 뜻으로 읽는다.
- 할 수 있는 일은 **연결된 업무 도구**(문서 검색·업무·프로젝트·사람·외부 연동
  등)를 기준으로 말한다. 붙어 있는 도구가 없으면 없다고 말한다.
"""

#: Child(위임받은 서브 에이전트)에만 더 붙는 지침 — 위임 범위를 벗어나지 않게 한다.
_CHILD_SCOPE_ADDENDUM = """
[위임 범위]
- 호출한 Root가 요청한 범위 안에서만 작업한다.
- 위임받지 않은 외부 변경을 추가로 수행하지 않는다.
- 최종 결과에 확인한 내용과 사용한 근거를 포함해 Root에게 돌려준다.
"""


class RuntimePromptAssembler:
    """공통 Runtime Scaffold와 Agent별 system_prompt를 결합해 최종 system_prompt를 만든다.

    무상태다 — 매번 새로 만들 필요 없이 하나를 계속 재사용해도 된다(참고:
    `AgentRuntimeFactory`는 그래도 다른 의존성처럼 생성자에서 주입받는다 — 테스트가
    가짜 Scaffold로 교체할 수 있게, 그리고 이 클래스의 조립 규칙 자체가 나중에
    설정 가능해질 여지를 남기기 위해서다).
    """

    def assemble_root(self, *, agent_prompt: str) -> str:
        """Root의 최종 system_prompt.

        `agent_prompt`는 Builder가 작성해 DB에 저장한 값 그대로다
        (`AgentDefinition.system_prompt` = `agent_versions.system_prompt`).
        """
        return self._combine(RUNTIME_SCAFFOLD, agent_prompt)

    def assemble_child(self, *, agent_prompt: str) -> str:
        """Child(서브 에이전트)의 최종 system_prompt.

        공통 Scaffold + 위임 범위 지침 + Child 자신의 system_prompt 순서로 붙인다.
        """
        return self._combine(RUNTIME_SCAFFOLD + _CHILD_SCOPE_ADDENDUM, agent_prompt)

    def assemble_general_purpose(self, *, gp_prompt: str) -> str:
        """general-purpose 서브 에이전트의 최종 system_prompt.

        `gp_prompt`는 deepagents가 내장한 기본값이다
        (`compat.default_general_purpose_prompt()`로 얻는다) — GP도 위임받은
        Child처럼 이 팀 전용 정책(근거 표시, 추측 금지, 간결한 답변 등)을 같이
        따라야 하므로 공통 Scaffold를 그대로 앞에 붙인다.
        """
        return self._combine(RUNTIME_SCAFFOLD, gp_prompt)

    @staticmethod
    def _combine(scaffold: str, agent_prompt: str) -> str:
        agent_prompt = (agent_prompt or "").strip()
        if not agent_prompt:
            return scaffold
        return f"{scaffold}\n[이 에이전트의 지시]\n{agent_prompt}\n"


__all__ = ["RuntimePromptAssembler", "RUNTIME_SCAFFOLD"]
