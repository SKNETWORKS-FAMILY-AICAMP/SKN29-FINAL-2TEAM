"""Root/Child/general-purpose에 공통으로 적용할 런타임 프롬프트를 조립한다.

정본: 2026-08-14 대화 결정(Builder Test Run은 지금 새 엔진에 연결하지 않고,
실제 실행 경로 — Chat → AgentExecutor → Factory → create_deep_agent() — 에
공통 Scaffold를 붙이는 걸 우선한다는 결정).

레거시 `services/harness/scaffold.py`의 `COMMON_SCAFFOLD`를 그대로 재사용하지
않는다 — 아래 `RUNTIME_SCAFFOLD`는 그 문구를 다시 걸러서 **코드로 강제할 수
없는 것만** 담는다:

- Tool 호출 횟수 상한, 모델 호출 횟수 상한 → `middleware/factory.py`의
  `ModelCallLimitMiddleware`/`ToolCallLimitMiddleware`가 이미 강제한다.
- role별 부수효과 도구 실행 차단 → `factory._to_langchain_tool()`의 `_run()`이
  실행 직전에 `is_tool_allowed_for_role()`로 막는다. **노출은 안 거른다**
  (2026-08-19) — 모델이 도구 존재를 모르면 "그런 기능이 없다"고 답하기 때문이다.
- 위임 깊이 제한(1단계만) → `subagents/validation.py`의 `validate_subagents()`가
  이미 강제한다.

이 세 가지를 프롬프트에 "말로" 다시 적지 않는다 — 코드가 이미 막고 있는 걸
프롬프트에도 적으면, 나중에 코드 쪽 정책이 바뀌었을 때 프롬프트만 옛 규칙을
계속 말하는 두 번째 진실 공급원이 생긴다.

**승인 카드(HITL)는 예외다.** 2026-08-18에 이 엔진에도 붙었다(`factory.py`의
`interrupt_on` → `events.py`의 `awaiting_confirmation` → `api_views.py`의 재개).
게이트가 있다는 **사실**은 모델이 알아야 행동이 달라진다 — 모르면 카드가 이미
묻는 것을 말로 한 번 더 묻고, 승인 전인데 "등록했습니다"라고 말한다. 그래서
아래 `[외부 변경]`은 "코드가 막는 것을 말로 또 적는" 경우가 아니다.

**도구 결과 인젝션 방어는 여기 없다**(2026-08-20 팀 결정). 같은 취지의 문구가
`memory/backend.py`의 `_MEMORY_ROUTING_PROMPT`에는 있어 메모리 채널만 덮인다 —
harness/MCP 도구 결과 쪽은 지금 프롬프트로 막지 않는다는 뜻이다.

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

[객관성]
- 사용자의 주장이나 전제가 사실과 다르면 그대로 동의하지 않고, 확인된 근거에 따라 정정한다.
- 사용자를 만족시키는 것보다 정확성과 객관성을 우선한다.
- 서로 다른 정보가 충돌하면 가능한 경우 추가로 확인하고, 확인할 수 없는 경우 불확실성을 명시한다.

[요청 이해]
- 사용자가 이미 제공한 정보를 다시 묻지 않는다.
- 요청의 목적과 맥락을 파악한 뒤 필요한 작업을 수행한다.
- 충분한 정보가 있으면 불필요한 확인 질문 없이 합리적인 범위에서 진행한다.
- 요청의 해석에 따라 결과가 크게 달라질 수 있거나 필요한 정보가 부족한 경우에만 추가로 질문한다.
- 결과에 실질적인 영향을 주지 않는 세부사항은 합리적인 기본값을 사용한다.

[답변]
- 사용자의 질문에 직접 답한다.
- 불필요한 계획이나 진행 예고를 먼저 나열하지 않는다.
- 필요한 내용만 간결하고 명확하게 전달한다.
- **표·제목·코드블록을 쓰지 않는다.** 화면이 그리는 것은 문단·`- ` 목록·굵게·
  기울임·백틱뿐이라, 표를 쓰면 `| 업무 | 담당 |` 과 `|---|---|` 이 글자 그대로
  보인다. 여러 값을 견주어야 하면 한 줄에 하나씩 적는다.
- **생각 과정도 화면에 그대로 보인다.** 사용자가 한국어로 물으면 생각 과정과
  답변을 모두 한국어로 쓴다.

[할 수 있는 일을 말할 때]
- 파일을 다루는 도구(`ls`·`read_file`·`write_file`·`edit_file`·`glob`·`grep`)는
  **네가 일하는 동안 쓰는 임시 작업 공간**이고, 사용자에게 제공하는 기능이 아니다.
  「무엇을 할 수 있냐」는 물음에 이것들을 능력으로 나열하지 않는다 — 사용자는
  자기 컴퓨터의 파일을 열고 고쳐 준다는 뜻으로 읽는다.
- 할 수 있는 일은 **연결된 업무 도구**(문서 검색·업무·프로젝트·사람·외부 연동
  등)를 기준으로 말한다. 붙어 있는 도구가 없으면 없다고 말한다.

[외부 변경]
- 외부를 바꾸거나 데이터를 남기는 도구(업무 등록·이슈 생성 등)는 사용자 승인
  없이 실행되지 않는다. 그 도구를 부르면 확인 카드가 뜨고 사람이 거기서 정한다 —
  **말로 다시 묻지 말고 도구를 부른다.**
- 승인 전에는 아직 아무것도 등록되지 않았다. 「등록했습니다」처럼 끝난 것처럼
  말하지 않는다.
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
