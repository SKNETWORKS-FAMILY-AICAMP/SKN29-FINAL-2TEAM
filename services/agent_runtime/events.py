"""Deep Agents 내부 이벤트를 애플리케이션 공통 이벤트로 변환한다.

정본: docs/작업기록/Deep_Agents/2026-08-13_02_Deep-Agent_런타임_공통_계약_v1.md §14

⚠ 스파이크 결론(2026-08-13, §15 실행 완료): fallback 불필요. `stream_mode="updates"`
하나만으로 부모/자식/도구 실행을 실시간·정확하게 구분할 수 있다. 관찰한 신호:

- 네임스페이스 튜플이 부모/자식을 가른다 — 부모는 `()`, 자식은
  `('tools:<run-uuid>', ...)`로 시작한다.
- 부모가 서브 에이전트를 부르는 순간은 `{'model': {'messages': [AIMessage(
  tool_calls=[{'name': 'task', 'args': {'subagent_type': <alias>,
  'description': <task_summary>}}])]}}`로 나온다 — `subagent_type`이 alias,
  `description`이 task_summary와 정확히 대응한다(deepagents 내장 `task` 도구
  계약).
- 자식 네임스페이스 안에서 도구 호출은 `{'model': {'messages': [AIMessage(
  tool_calls=[{'name': <tool_ref>, ...}])]}}` → `{'tools': {'messages':
  [ToolMessage(name=<tool_ref>, ...)]}}` 순서로 온다.
- 자식이 끝나면 **부모 네임스페이스**로 돌아와 `{'tools': {'messages':
  [ToolMessage(name='task', content=<자식의 최종 답변>)]}}`이 온다.
- 부모의 최종 응답은 부모 네임스페이스의 `{'model': {'messages': [AIMessage(
  content=<텍스트>, tool_calls=[])]}}`(tool_calls가 비어 있음)다.
- 부모가 서브 에이전트 위임 없이 **자기 도구를 직접** 호출하는 경우도 자식
  네임스페이스와 동일한 model→tools 순서로 온다. langgraph의 `ToolNode`는
  루트 그래프냐 서브그래프냐를 구분하지 않는다 — 네임스페이스 튜플은 "어느
  그래프가 이 업데이트를 냈는지"를 나타내는 스트리밍 귀속 태그일 뿐, 도구
  실행 자체의 의미를 바꾸지 않는다(langgraph.prebuilt.tool_node.ToolNode
  소스 확인 — namespace 개념 자체가 없음). 그래서 tool_started/
  tool_completed는 부모/자식에 상관없이 동일하게 낸다. 부모 자신의 직접
  호출은 `subagent_alias=None`으로 구분한다.

`"messages"`(토큰 단위 델타) 모드는 이 6단계 분류에는 안 쓴다 — tool_started 등
6단계 분류는 여전히 다 끝난 `AIMessage`가 있어야 정확하다(예: `tool_calls`는
스트리밍 중간엔 아직 다 안 채워져 있을 수 있다). 대신 reasoning 실시간
스트리밍에만 쓴다(2026-08-18, `_classify_reasoning_delta` 참고) — "updates"는
모델 노드 하나가 통째로 끝나야 나오는 완성된 텍스트라, reasoning도 다 끝난
뒤에야 한 덩어리로 보여줬었다. `"messages"`는 OpenAI가 실제로 보내는 조각
단위(`response.reasoning_summary_text.delta`)를 그 자리에서 받을 수 있어
"다 끝난 뒤 한 번에"가 아니라 "쓰는 대로" 보여줄 수 있다.

`"custom"` 모드는 쓴다 — `task_extraction`/`jira_get_issues`처럼 제너레이터로
진행 이벤트를 내는 내장 도구(tools/adapters.py)가 `langgraph.config
.get_stream_writer()`로 직접 흘려보내는 값이 여기로 들어온다(2026-08-13 실제
`stream_mode=["updates", "custom"]`로 실행해 확인 — payload가 어댑터가 채운
그대로 나온다). 내용은 도구마다 달라서 여기서 재해석하지 않고 `EVENT_TOOL_PROGRESS`
로 감싸 `detail`에 그대로 담아 보낸다.

## 병렬 위임/도구 호출 (2026-08-14 재설계)

이전 버전은 "부모가 한 번에 하나의 서브 에이전트만 부르고 그것이 끝나야 다음으로
넘어간다"는 전제로 `tool_calls[0]`만 보고, 위임 추적을 FIFO(`list.pop(0)`)로
했다. 그런데 실제로 설치된 langgraph(`langgraph/prebuilt/tool_node.py`
`ToolNode._func`)를 직접 읽어보면 여러 `tool_calls`는
`executor.map(self._run_one, tool_calls, ...)`로 **스레드풀에서 동시에** 실행된다
— 즉 모델이 한 AIMessage에 `task` 위임을 2개 이상 담아 내면 그 완료 순서는
시작 순서와 다를 수 있다. FIFO로 매칭하면 나중에 시작한 위임의 완료를 먼저 시작한
위임의 것으로 잘못 붙일 수 있었다(모듈 docstring이 스스로 인정했던 TODO).

이제는:
- `AIMessage.tool_calls`를 전부 순회한다(더 이상 `[0]`만 안 봄) — 위임 여러 개,
  또는 위임+직접 호출이 섞여도 전부 이벤트로 낸다.
- 위임(`task`) 완료 매칭은 FIFO가 아니라 **`ToolMessage.tool_call_id`**로 한다.
  `task()`/`atask()`가 `Command(update={"messages": [ToolMessage(content,
  tool_call_id=runtime.tool_call_id)]})`로 항상 원래 호출의 `tool_call_id`를
  그대로 돌려준다는 걸 deepagents 소스로 확인했다(`_return_command_with_
  state_update`) — 이건 실행 순서와 무관하게 항상 정확하다.
- 위임을 시작할 때 이 EventMapper가 직접 자식 `run_id`(uuid4)를 하나 만들어
  `subagent_started`/`subagent_completed`와 그 자식 네임스페이스에서 나오는
  `tool_started`/`tool_completed`/`tool_progress`에 일관되게 붙인다.
  `parent_run_id`는 그 실행의 `context.run_id`다(§14.2~14.4).
- 다만 **자식 네임스페이스 접두사(`'tools:<uuid>'`)를 "어느 위임에 속하는가"로
  묶는 것은 여전히 근사치다** — 자식 내부에서 도는 model/tools 이벤트에는 부모의
  `tool_call_id`가 실려 오지 않는다(오직 위임이 끝나고 부모로 복귀하는
  `ToolMessage`만 tool_call_id를 갖는다). 그래서 "이 네임스페이스를 처음 보면
  아직 네임스페이스에 안 묶인 것 중 가장 먼저 시작된 위임에 붙인다"는 순서
  휴리스틱을 그대로 쓴다 — 위임이 진짜 동시에(스레드에서) 실행되면 이 귀속이
  틀릴 수 있다는 한계가 남는다. `subagent_started`/`subagent_completed`(부모
  네임스페이스, tool_call_id로 정확히 매칭됨)는 이 한계의 영향을 받지 않는다.

## `subagent_started`/`subagent_completed`의 agent_id/agent_version_id/subagent_name
(2026-08-14 추가)

§14.2/§14.3 예시(`AG011`/`AV023`/"Jira 등록 에이전트")는 **Child 자신의** 값이지 루트의
값이 아니다. `EventMapper.convert()`가 이미 받는 `definition`(루트 `AgentDefinition`)에
`definition.subagents: tuple[SubagentDefinition, ...]`가 있고, 그 각 항목은 이미
DB에서 조회한 Child 자신의 `agent_id`/`agent_version_id`/`name`을 담고 있다
(`loader.py`의 `_subagent_definition_from_row`/`_placeholder_subagent_definition`).
`alias`로 이 tuple을 찾으면 된다 — `build_subagent()`가 `CompiledSubAgent(
name=definition.alias, ...)`로 등록한 이름이 정확히 이 `alias`이고, deepagents의
`task()` 도구가 받는 `subagent_type`이 바로 이 이름이므로, `subagent_type`(=alias)로
`definition.subagents`를 찾으면 항상 맞는 Child를 가리킨다. **MVP가 위임 1단계로
제한돼 있어서**(`validate_subagents()`의 무조건 `has_subagents` 검사, `loader.py`의
`_reject_if_has_subagents()`, `build_subagent()`의 `definition_has_subagents()` —
3중으로 강제) 이 조회에 재귀가 필요 없다: Child는 항상 leaf이고 `definition.subagents`
평탄한 한 단계 매핑이면 충분하다.

## tool_started/tool_completed의 tool_call_id·arguments·status(2026-08-14 추가)

`agent_run`/`tool_call` 로깅(`tracing/__init__.py`)이 이 이벤트들을 그대로
읽어서 DB에 적재한다 — 위임(`subagent_started`/`subagent_completed`)과 같은
방식으로 `tool_call_id`가 시작-종료를 정확히 묶어야 한다(같은 도구를 병렬로
호출해도 어긋나지 않게). `arguments`는 `tool_call.input_summary`를 채우는
원본이고(`services.harness.trace.summarize_input()`이 요약한다 — 자격증명이
로그에 그대로 안 남는다), `status`는 LangChain `ToolMessage.status`
("success"/"error", langgraph `ToolNode`가 도구 예외를 잡으면 "error"로
채우는 필드)를 그대로 옮긴 것이다("OK"/"FAILED"). 이 셋은 §14 계약이 정한
목록엔 없다 — 이벤트 타입 자체는 그대로 두고 기존 이벤트에 필드만 얹었다
(`_11_` 문서와 같은 판단).

`tool_completed`의 `output`(2026-08-18 추가)은 도구가 실제로 돌려준 값이다
— "타임라인에 도구 호출은 보이는데 뭘 반환했는지는 왜 안 보이냐"는 요청으로
붙였다. `ToolMessage.text`를 `_summarize_tool_output()`으로 길이만 잘라
담는다(`arguments`처럼 사전이 아니라 이미 문자열이라 키=값 요약은 필요 없다).
DB에는 안 쌓는다 — `_end_tool_call()`(tracing/__init__.py)은 여전히 `status`만
읽고, 이 필드는 스트림을 타고 화면까지만 간다.

## reasoning 실시간 스트리밍(2026-08-18 추가)

`stream_mode="messages"`로 받는 `AIMessageChunk.content`는 OpenAI Responses
API의 SSE 이벤트 하나하나를 그대로 옮긴 블록 리스트다(`langchain_openai`
`_convert_responses_chunk_to_generation_chunk` 소스로 확인). reasoning 블록은
실측으로 이런 순서로 온다(디버그 스크립트로 직접 확인, 2026-08-18):

```
{'id': 'rs_...', 'summary': [], 'type': 'reasoning', 'content': [], 'index': 0}
{'summary': [{'index': 0, 'type': 'summary_text', 'text': ''}], 'index': 0, ...}
{'summary': [{'index': 0, 'type': 'summary_text', 'text': '**Clarifying...'}], 'index': 0, ...}
{'summary': [{'index': 0, 'type': 'summary_text', 'text': ' primes'}], 'index': 0, ...}
...
```

`block['index']`(위 예시의 바깥 `index`)는 이 reasoning 항목 전체를 가리키는
langchain-core의 청크 병합 키다(`+`로 청크를 더할 때 같은 `index`끼리
이어붙인다는 게 `langchain_openai` 주석에 그대로 적혀 있다) — 모델 호출
하나 안에서 새 reasoning 항목마다 증가하고, **다음 모델 호출에서는 다시
0부터 시작한다.** `block['summary'][i]['index']`(summary_index)는 그 항목
**안의** 문단 하나를 가리킨다 — OpenAI가 reasoning을 여러 문단으로 나눠
낼 때 문단마다 다른 summary_index를 쓴다.

그래서 "지금 받은 조각이 방금 그 문단의 이어지는 델타인가, 새 문단인가"는
`(block['index'], summary_index)` 쌍으로 판단한다(`_classify_reasoning_delta`).
같은 쌍이면 direct으로 이어붙이고(`"append": true`), 다르면 새 단계로
띄운다(`"append": false`) — 화면(`liveChat.ts`)은 이 플래그만 보고 마지막
`reasoningSteps` 항목에 이어붙일지 새 항목을 만들지 정한다.

**모델 호출 사이의 경계도 명시적으로 지운다.** `block['index']`가 모델
호출마다 다시 0부터 시작하므로, 이전 호출의 마지막 `(index, summary_index)`가
다음 호출의 첫 조각과 우연히 같은 값일 수 있다 — `_classify()`의 "model"
노드(`"updates"` 모드, 그 호출이 완전히 끝났을 때만 옴) 분기에서 그 네임스페이스의
커서를 지워서, 다음 호출의 첫 reasoning 조각은 항상 새 단계로 뜨게 한다.

**"updates" 모드는 더 이상 reasoning을 내지 않는다.** 예전엔 다 끝난
`AIMessage.content`에서 완성된 텍스트를 한 번에 뽑아 냈지만(구
`_extract_reasoning()`), 이제 "messages" 모드가 실시간으로 이미 다 보여줬으므로
그대로 두면 같은 내용이 끝에 한 번 더(완성본으로) 중복된다.

## MCP 도구 이름 치환(2026-08-14 추가)

모델에게 나가는 함수 이름은 `factory.py`의 `model_safe_tool_name()`이
`mcp:<id>`의 콜론을 `__`로 바꿔 보낸다(OpenAI 함수 이름 제약 —
`tools/loader.py` 모듈 docstring 참고). 그래서 여기서 읽는
`AIMessage.tool_calls[i]['name']`/`ToolMessage.name`은 원래 tool_ref와 다를
수 있다 — `tool_ref_from_model_name()`으로 되돌린 값만 `"tool_ref"`로
내보낸다. 위 예시의 `<tool_ref>`는 이 되돌림 이후의 값 기준이다.
"""

from __future__ import annotations

import uuid
from typing import Any

from services.agent_runtime.tools.loader import tool_ref_from_model_name

# --- 이벤트 타입(§14.1) -----------------------------------------------------
EVENT_AGENT_STARTED = "agent_started"
EVENT_SUBAGENT_STARTED = "subagent_started"
EVENT_SUBAGENT_COMPLETED = "subagent_completed"
EVENT_TOOL_STARTED = "tool_started"
EVENT_TOOL_COMPLETED = "tool_completed"
EVENT_TOOL_PROGRESS = "tool_progress"
EVENT_MESSAGE_DELTA = "message_delta"
EVENT_RESULT = "result"
EVENT_ERROR = "error"
# 2026-08-18 추가 — 승인 게이트(`interrupt_on`)가 실행을 멈춘 자리.
# 레거시 Harness의 같은 이름 이벤트와 **모양을 맞춘다**(`tool_ref`/`tool_name`/
# `arguments`/`resume`) — 화면(`liveChat.ts`의 `awaiting_confirmation` 분기)과
# 저장(`apps/chat/api_views.py`의 `_persist`)이 이미 그 모양을 읽고 있어서,
# 맞춰 두면 양쪽 다 안 고쳐도 된다. 다른 점은 `resume`의 내용물뿐이다 —
# 레거시는 대화 전체를 담아 되돌려 받아야 재개하지만, 이 엔진은 상태가
# Checkpointer(RDS)에 있어서 "무엇을 승인하는가"만 있으면 된다.
# 2026-08-18 추가. §14 계약엔 없던 타입이라(그 문서 갱신 전까지) 여기 새로 둔다
# — `_11_`류 판례처럼 계약 목록에 없는 필드를 기존 이벤트에 얹는 것과 달리
# 이건 아예 새 타입이 필요해서(추론 텍스트는 tool_started/result 어디에도
# 자연스럽게 안 얹힌다). `tracing/__init__.py`의 `_record()`는 모르는
# 타입을 조용히 지나치므로 DB 적재는 없다 — 지금은 화면에 실시간으로
# 보여주는 것만이 목적이라 저장할 이유가 없다.
EVENT_REASONING = "reasoning"

# 2026-08-19 추가(§0순위 — 새 엔진 HITL resume API). 값은 레거시
# `services/harness/runner.py`의 동명 상수와 의도적으로 같은 문자열이다 —
# `backend/db/agent_platform.py`의 `ChatMessageRepository.latest_pending_confirmation()`
# 이 SQL에서 `content->>'type' = 'awaiting_confirmation'`을 그대로 리터럴로
# 검사하고, `apps/chat/api_views.py`의 `_history()`/`_relay()`도 이 문자열
# 기준으로 두 엔진을 가리지 않고 같은 분기를 탄다 — 값이 갈리면 그 공용
# 코드가 새 엔진의 확인 대기를 못 알아본다. import로 묶지 않고 값만
# 맞추는 이유는 `EVENT_ERROR`/`EVENT_RESULT`가 이미 이 파일에서 같은
# 방식으로 하고 있는 것과 같다 — 레거시(`services.harness`)와 새 엔진
# (`services.agent_runtime`)은 서로의 내부 구현을 몰라도 되게 분리하되,
# 화면·DB로 나가는 이벤트 "타입 문자열"만 계약처럼 맞춘다.
EVENT_AWAITING_CONFIRMATION = "awaiting_confirmation"

# deepagents가 서브 에이전트 위임에 쓰는 내장 도구 이름. 이 이름의 tool_call은
# "실제 도구 호출"이 아니라 "위임"으로 분류한다.
DELEGATION_TOOL_NAME = "task"

# deepagents 0.7.5의 `task` 도구가 존재하지 않는 subagent_type을 받았을 때
# 예외 대신 돌려주는 문자열의 접두어 그대로다(설치된 패키지
# `deepagents/middleware/subagents.py`의 `task()`/`atask()`:
# `f"We cannot invoke subagent {subagent_type} because it does not exist,
# the only allowed types are {allowed_types}"`). langchain의 ToolMessage는
# 이 경우도 `status="success"`인 평범한 성공 메시지로 감싸므로(직접 확인함),
# status 필드로는 이 실패를 구분할 수 없다 — 이 문자열 접두어 매칭이 현재
# 유일하게 근거 있는 탐지 방법이다. 버전이 고정(requirements/base.txt
# `deepagents==0.7.5`)이라 이 문구도 고정이다 — 업그레이드 시 이 상수도
# 같이 확인해야 한다.
_SUBAGENT_NOT_FOUND_PREFIX = "We cannot invoke subagent "


def _looks_like_subagent_not_found(content: str) -> bool:
    """`task` 완료 메시지가 '존재하지 않는 subagent_type' 실패인지 판별한다."""
    return isinstance(content, str) and content.startswith(_SUBAGENT_NOT_FOUND_PREFIX)


def _resolved_endpoint_hash(resolved: Any) -> str | None:
    """`resolved`(`ResolvedModelConfig | None`)의 endpoint 해시.

    2026-08-19, §10순위(Child Run Snapshot) — `models/factory.py`의
    `resolved_endpoint_hash()`를 그대로 재사용한다(§4순위가 Root용으로
    이미 만들어 둔 값, 새로 판단하지 않는다). **함수 안에서 import한다** —
    `executor.py`가 같은 이유로 `services.agent_runtime.models.factory`를
    함수 본문에서 늦게 import하는 것과 동일하다(모듈 최상단에서 부르면
    `models.factory` → `backend.db.agent_platform` → (이 패키지 진입 시점에
    이미 그 모듈을 부른 호출자가 있어) 순환 import가 생긴다, `executor.py`
    주석 참고). `resolved`가 `None`이면(Child/Root 어느 쪽도 못 찾은 경우 —
    이론상 `root_resolved_model`도 안 넘긴 옛 호출자만 해당) 비교할 대상
    자체가 없으므로 `None`을 그대로 돌려준다.
    """
    if resolved is None:
        return None
    from services.agent_runtime.models.factory import resolved_endpoint_hash

    return resolved_endpoint_hash(resolved)


def _tool_status(msg_status: str | None) -> str:
    """LangChain `ToolMessage.status`("success"/"error"/None) → DB 상태값.

    langgraph `ToolNode`가 도구 핸들러 예외를 잡으면 "error"로 채운다 —
    그 값만 FAILED고, 나머지는(보통 "success", 드물게 필드 자체가 없는 경우도
    안전하게) OK로 본다.
    """
    return "FAILED" if msg_status == "error" else "OK"


TOOL_OUTPUT_SUMMARY_MAX = 500


def _summarize_tool_output(content: Any) -> str:
    """도구가 실제로 돌려준 내용을 화면(생각 과정 타임라인)에 보일 만큼만 남긴다.

    `summarize_input()`(services/harness/trace.py)과 같은 동기다 — 다만 입력은
    키=값 쌍이라 사전을 받지만, 도구 출력은 이미 `ToolMessage.text`가 만들어 둔
    평문 문자열이라 길이만 자르면 된다. 자격증명·토큰류를 도구가 반환값에
    직접 담는 경우는 없다고 가정한다(그런 값을 담는 도구가 있다면 그건 이
    자르기가 아니라 그 도구 자체를 고쳐야 할 문제다).
    """
    text = content if isinstance(content, str) else str(content)
    if len(text) > TOOL_OUTPUT_SUMMARY_MAX:
        return f"{text[:TOOL_OUTPUT_SUMMARY_MAX]}..."
    return text


def _tool_label(tool_ref: str) -> str:
    """승인 카드·대화 기록에 쓸 사람이 읽는 도구 이름. 못 찾으면 ref 그대로.

    레지스트리를 **함수 안에서** 부른다 — `services.harness.registry`는 저장소
    접근까지 끌고 들어와서, 이 모듈을 읽는 것만으로 그걸 세우게 하지 않는다
    (`factory.py`가 `SPEAKABLE_ERRORS`를 가져오는 방식과 같은 이유).
    MCP 도구는 여기 없어서 ref가 그대로 나온다 — 지금 이 값이 보이는 곳은
    대화 기록 한 줄뿐이라(`_history`) 그 편이 틀린 이름보다 낫다.
    """
    from services.harness.registry import BUILTIN_TOOLS

    tool = BUILTIN_TOOLS.get(tool_ref)
    return getattr(tool, "name", None) or tool_ref


class EventMapper:
    """raw deepagents 'updates' 이벤트 스트림 → 위 EVENT_* 딕셔너리 리스트로 변환.

    무상태로 쓸 수 없다 — 부모의 위임 결정(subagent_started)과 자식 네임스페이스를
    대응시키려면 "아직 안 끝난 위임"을 기억해야 한다. 실행(run) 하나당
    인스턴스 하나를 새로 만들 것 — executor.py가 run_agent() 호출마다 새
    EventMapper()를 생성해야 한다(재사용하면 이전 실행의 상태가 남는다).

    `convert()`는 항상 리스트를 반환한다(비어 있을 수 있음) — 모델이 한
    AIMessage에 여러 `tool_calls`를 담아 내면(병렬 위임/도구 호출) 그 전부가
    각자의 이벤트가 되어야 하므로, 원시 이벤트 1개가 공통 이벤트 0~N개로
    펼쳐질 수 있다.
    """

    def __init__(self) -> None:
        # 아직 subagent_completed로 안 닫힌 위임들. `tool_call_id` -> 위임 정보.
        # dict 삽입 순서 = 시작 순서이므로, 네임스페이스 귀속 휴리스틱(아직 어느
        # 네임스페이스에도 안 묶인 것 중 가장 먼저 시작된 것)에도 이 순서를 쓴다.
        self._pending: dict[str, dict[str, str]] = {}
        # 네임스페이스 접두사(예: 'tools:94cc782c-...') -> 그 안에서 도는 서브
        # 에이전트 정보(위 _pending의 값과 같은 dict). 같은 네임스페이스에서
        # 여러 이벤트가 나오므로 캐시한다.
        self._namespace_subagent: dict[str, dict[str, str]] = {}
        # reasoning 델타 스트리밍용(2026-08-18). ns_prefix -> 그 네임스페이스에서
        # 마지막으로 본 (block_index, summary_index). 다음 조각이 같은 값이면
        # "이어지는 문단"(append), 다르면 "새 문단"이다. "updates" 모드의 model
        # 노드 완료(그 호출이 끝났다는 뜻)에서 None으로 지운다 — 안 지우면 다음
        # 호출의 첫 조각이 우연히 같은 (0, 0)을 받아 이전 호출 끝에 잘못 이어붙는다.
        self._reasoning_cursor: dict[str | None, tuple[int | None, int | None] | None] = {}

    def convert(
        self,
        raw_event: Any,
        *,
        definition: Any,
        context: Any,
        root_resolved_model: Any = None,
        child_resolved_models: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """raw_event는 `(namespace_tuple, mode, payload)` 형태를 기대한다.

        `mode`가 `"updates"`/`"custom"`/`"messages"` 셋 다 아닌 이벤트는 빈
        리스트를 반환한다 — 6단계 분류엔 `"messages"`를 안 쓴다는 뜻이지,
        버린다는 뜻이 아니다(위 "reasoning 실시간 스트리밍" 절 참고).

        `root_resolved_model`/`child_resolved_models`(2026-08-19, §10순위 —
        Child Run Snapshot): `executor.py`가 `factory.build()`에서 받은 값을
        그대로 넘긴다. `subagent_started` 이벤트를 만들 때만 쓴다(아래
        `_classify_parent_tool_calls()`) — Child 자신의 resolved_model을
        `child_resolved_models`에서 alias로 찾고, 못 찾으면(예: alias가
        `definition.subagents`에 없는 general-purpose — GP는 Root와 같은
        `model`로 돈다, `factory.py`가 GP 전용 모델을 따로 resolve하지
        않는다) Root 자신의 값(`root_resolved_model`)으로 폴백한다. 기본값을
        `None`으로 둔 이유는 이 값 없이도 기존 호출자(테스트 등)가 그대로
        동작해야 해서다 — 그러면 `resolved_provider`/`resolved_endpoint_hash`가
        둘 다 `None`으로 채워진다(`_start_run()`의 `.get()` 처리와 같은
        "값이 없으면 자연히 None" 원칙).
        """
        if not isinstance(raw_event, tuple) or len(raw_event) != 3:
            return []

        namespace, mode, payload = raw_event
        ns_prefix = namespace[0] if namespace else None
        run_id = getattr(context, "run_id", None)

        if mode == "messages":
            # "messages"는 dict가 아니라 (AIMessageChunk, metadata) 2-tuple로
            # 온다(langgraph 1.2.11) — 아래 dict 검사와 별도로 먼저 갈라낸다.
            if not isinstance(payload, tuple) or len(payload) != 2:
                return []
            chunk, metadata = payload
            node_name = metadata.get("langgraph_node") if isinstance(metadata, dict) else None
            if node_name != "model":
                return []
            return self._classify_reasoning_delta(ns_prefix=ns_prefix, chunk=chunk, run_id=run_id)

        if not isinstance(payload, dict):
            return []

        if mode == "custom":
            event = self._classify_progress(ns_prefix=ns_prefix, payload=payload, run_id=run_id)
            return [event] if event is not None else []

        if mode != "updates":
            return []

        # 2026-08-19 추가(§0순위) — `HumanInTheLoopMiddleware.after_model`이
        # `interrupt()`를 부르면 LangGraph는 이 턴의 다른 노드 출력과 **완전히
        # 분리된** 자기만의 "updates" 청크로 `{"__interrupt__": (Interrupt(...),)}`
        # 를 낸다(설치된 `langgraph==...`의 `pregel/_loop.py`
        # `output_writes()` 실제 소스로 확인 — `map_output_updates()`가
        # `INTERRUPT` 채널의 write는 애초에 걸러내고, 대신
        # `self._emit("updates", lambda: iter([{INTERRUPT: interrupts}]))`로
        # 따로 낸다). 그래서 이 키가 있으면 그 청크는 다른 node_name과
        # 섞일 수 없다 — 바로 처리하고 반환한다.
        #
        # **이걸 처리 안 하면 무슨 일이 있었는지(2026-08-19 이전)**: 아래
        # 일반 루프는 `node_output`이 dict가 아니면(`__interrupt__`의 값은
        # `tuple[Interrupt, ...]`) 그냥 건너뛰므로, interrupt가 나면 이
        # `convert()`는 빈 리스트만 돌려주고 스트림은 그대로 끝났다 —
        # side_effect 도구를 부르면 화면에는 아무 일도 없었던 것처럼 보이고
        # (확인 카드도, 오류도 없이 스트림만 조용히 종료), 실제로는
        # `HumanInTheLoopMiddleware`가 도구 실행을 막아 둔 채 그래프가
        # 멈춰 있었다 — 재개할 API 자체도 없었으니 그 실행은 영원히 그
        # 상태였다. `2026-08-19_05_HITL_resume_구현설계.md` §1 참고.
        if "__interrupt__" in payload:
            return self._handle_interrupt(
                payload["__interrupt__"], run_id=run_id, definition=definition
            )

        events: list[dict[str, Any]] = []
        for node_name, node_output in payload.items():
            if not isinstance(node_output, dict):
                continue
            messages = node_output.get("messages")
            if not messages:
                continue

            for message in messages:
                events.extend(
                    self._classify(
                        node_name=node_name,
                        ns_prefix=ns_prefix,
                        message=message,
                        definition=definition,
                        run_id=run_id,
                        root_resolved_model=root_resolved_model,
                        child_resolved_models=child_resolved_models,
                    )
                )

        return events

    def _handle_interrupt(
        self,
        interrupts: tuple[Any, ...],
        *,
        run_id: str | None,
        definition: Any,
    ) -> list[dict[str, Any]]:
        """`HumanInTheLoopMiddleware`의 interrupt를 `EVENT_AWAITING_CONFIRMATION`
        으로 바꾼다.

        `interrupts`는 `langgraph.types.Interrupt` 인스턴스들이다. 원소가
        보통 하나뿐인 이유: `HumanInTheLoopMiddleware.after_model`(설치된
        `langchain` 실제 소스)이 그 턴의 `AIMessage`에 실린 side_effect
        tool_call **전부**를 한 번에 모아 `interrupt(hitl_request)`를 딱
        한 번만 부른다 — tool_call마다 따로 interrupt하지 않는다. 그래서
        이 턴에 한해 최대 하나의 `Interrupt`만 온다고 보고, 첫 번째만
        쓴다. `Interrupt.value`는 `interrupt()`에 넘긴 그 값
        (`HITLRequest` — `{"action_requests": [...], "review_configs":
        [...]}`) 그대로다.
        """
        if not interrupts:
            return []
        first = interrupts[0]
        hitl_request = first.value if isinstance(first.value, dict) else {}
        action_requests = hitl_request.get("action_requests") or []
        return [
            {
                "type": EVENT_AWAITING_CONFIRMATION,
                "run_id": run_id,
                "agent_id": getattr(definition, "agent_id", None),
                "agent_version_id": getattr(definition, "agent_version_id", None),
                # 승인/거부를 그대로 이어붙일 수 있는 재개 키. 지금 구조에서는
                # 한 턴에 interrupt가 하나뿐이라(위 docstring) 재개할 때
                # `Command(resume={"decisions": [...]})`를 이 id 없이
                # 그대로 보내도 되지만, 나중에 병렬 interrupt를 지원하게
                # 되면 이 값으로 특정 interrupt를 골라야 하므로 지금부터
                # 실어 둔다.
                "interrupt_id": first.id,
                # 화면이 확인 카드를 그리는 데 필요한 전부 — 도구 이름·인자·
                # 설명. 승인 재개 시에도 이 목록의 길이만큼
                # `decisions`를 만들어야 하므로(순서·개수가 안 맞으면
                # `HumanInTheLoopMiddleware`가 ValueError) 그대로 저장해 둔다.
                "action_requests": action_requests,
                "complete": False,
            }
        ]

    def _classify(
        self,
        *,
        node_name: str,
        ns_prefix: str | None,
        message: Any,
        definition: Any,
        run_id: str | None,
        root_resolved_model: Any = None,
        child_resolved_models: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        tool_calls = list(getattr(message, "tool_calls", None) or [])
        msg_name = getattr(message, "name", None)
        msg_tool_call_id = getattr(message, "tool_call_id", None)
        # LangChain ToolMessage.status — "success"/"error". langgraph의
        # ToolNode가 도구 핸들러 예외를 잡아 ToolMessage로 감쌀 때 "error"로
        # 채운다(직접 실행해 확인함, tracing/__init__.py가 OK/FAILED로 옮긴다).
        msg_status = getattr(message, "status", None)
        # `.content`가 아니라 `.text`다(2026-08-14 실측 발견): OpenAI Responses API
        # 경로(`models/factory.py`의 `ChatOpenAI(..., use_responses_api=True)`,
        # gpt-5.6-luna 같은 추론 모델)는 `AIMessage.content`를 평문 문자열이 아니라
        # `[{'type': 'reasoning', 'id': 'rs_...', ...}, {'type': 'text', 'text':
        # '...'}]` 같은 콘텐츠 블록 리스트로 채운다 — `scripts/team_status_agent.py`로
        # 라이브 실행해서 `result` 이벤트의 `text`가 그 원시 리스트 그대로 새는 걸
        # 재현했다. `BaseMessage.text`(langchain-core, 설치된 버전에서 직접 확인)는
        # 문자열/블록 리스트 둘 다 받아 `type: "text"` 블록만 이어붙인 평문 문자열을
        # 돌려준다(`str` 서브클래스라 `.startswith()`/JSON 직렬화 그대로 안전) —
        # 일반 모델(콘텐츠가 이미 문자열)에도 동일하게 안전하다.
        content = message.text

        agent_id = getattr(definition, "agent_id", None)
        agent_version_id = getattr(definition, "agent_version_id", None)

        if ns_prefix is None:
            # --- 부모 네임스페이스 -------------------------------------------
            if node_name == "model":
                # 이 호출의 reasoning은 이미 "messages" 모드로 실시간으로 다
                # 내보냈다(_classify_reasoning_delta) — 여기서 완성본을 또
                # 내면 끝에 중복된다. 커서만 지워서 다음 호출의 첫 조각이
                # 이 호출 끝에 잘못 이어붙지 않게 한다(위 모듈 docstring
                # "reasoning 실시간 스트리밍" 절).
                self._reasoning_cursor[ns_prefix] = None
                events: list[dict[str, Any]] = []
                if tool_calls:
                    events.extend(
                        self._classify_parent_tool_calls(
                            tool_calls=tool_calls,
                            run_id=run_id,
                            agent_id=agent_id,
                            agent_version_id=agent_version_id,
                            definition=definition,
                            root_resolved_model=root_resolved_model,
                            child_resolved_models=child_resolved_models,
                        )
                    )
                    return events
                if content:
                    # 도구 호출 없이 텍스트만 낸 최종 응답.
                    events.append(
                        {
                            "type": EVENT_RESULT,
                            "text": content,
                            "run_id": run_id,
                            "agent_id": agent_id,
                            "agent_version_id": agent_version_id,
                            "complete": True,
                        }
                    )
                return events

            if node_name == "tools" and msg_name == DELEGATION_TOOL_NAME:
                # tool_call_id로 정확히 매칭한다(FIFO 아님) — 병렬 위임이면
                # 완료 순서가 시작 순서와 다를 수 있어서다(위 모듈 docstring).
                info = self._pending.pop(msg_tool_call_id, None) if msg_tool_call_id else None
                if info is None:
                    info = {}
                base = {
                    "type": EVENT_SUBAGENT_COMPLETED,
                    "run_id": info.get("run_id"),
                    "parent_run_id": run_id,
                    # Child 자신의 agent_id/agent_version_id다(§14.3/§14.4) — 아래
                    # info.get(...)이 없으면(정상 경로에선 안 생김) 루트 값으로
                    # 폴백한다.
                    "agent_id": info.get("agent_id", agent_id),
                    "agent_version_id": info.get("agent_version_id", agent_version_id),
                    "subagent_alias": info.get("alias"),
                    "subagent_name": info.get("subagent_name"),
                    "complete": False,
                }
                if _looks_like_subagent_not_found(content):
                    # deepagents가 예외 대신 평범한 성공 ToolMessage로 감싸
                    # 돌려주는 "존재하지 않는 subagent_type" 실패 — 계약
                    # §14.4대로 FAILED로 표시한다. 이걸 걸러내지 않으면
                    # 위임이 실패했는데도 DONE으로 표시된다(2026-08-14 발견·수정).
                    base["status"] = "FAILED"
                    base["error_code"] = "SUBAGENT_EXECUTION_FAILED"
                else:
                    base["status"] = "DONE"
                return [base]

            if node_name == "tools" and msg_name and msg_name != DELEGATION_TOOL_NAME:
                # 부모가 직접 호출한 도구의 완료 — 자식 네임스페이스의
                # tool_completed와 동일한 모양, subagent_alias만 None.
                return [
                    {
                        "type": EVENT_TOOL_COMPLETED,
                        "run_id": run_id,
                        "subagent_alias": None,
                        "tool_ref": tool_ref_from_model_name(msg_name),
                        "tool_call_id": msg_tool_call_id,
                        "status": _tool_status(msg_status),
                        "output": _summarize_tool_output(content),
                        "complete": False,
                    }
                ]
            return []

        # --- 자식(서브 에이전트) 네임스페이스 -----------------------------------
        info = self._resolve_subagent_info(ns_prefix)
        alias = info.get("alias") if info else None
        child_run_id = info.get("run_id") if info else None

        if node_name == "model":
            # 부모 분기와 같은 이유로 커서만 지운다(위 "reasoning 실시간
            # 스트리밍" 절) — 이 자식 네임스페이스의 reasoning도 "messages"
            # 모드로 이미 실시간으로 다 나갔다.
            self._reasoning_cursor[ns_prefix] = None
            events: list[dict[str, Any]] = []
            for call in tool_calls:
                tool_ref = call.get("name")
                if tool_ref and tool_ref != DELEGATION_TOOL_NAME:
                    events.append(
                        {
                            "type": EVENT_TOOL_STARTED,
                            "run_id": child_run_id,
                            "parent_run_id": run_id,
                            "subagent_alias": alias,
                            "tool_ref": tool_ref_from_model_name(tool_ref),
                            # 화면 상태줄이 그대로 읽는다(2026-08-18) — ref 를 쓰면
                            # 「task_register 실행 중」처럼 내부 이름이 그대로 보인다(§0 원칙 2).
                            "tool_name": _tool_label(tool_ref_from_model_name(tool_ref)),
                            "tool_call_id": call.get("id"),
                            "arguments": call.get("args") or {},
                            "complete": False,
                        }
                    )
            return events

        if node_name == "tools" and msg_name and msg_name != DELEGATION_TOOL_NAME:
            return [
                {
                    "type": EVENT_TOOL_COMPLETED,
                    "run_id": child_run_id,
                    "parent_run_id": run_id,
                    "subagent_alias": alias,
                    "tool_ref": tool_ref_from_model_name(msg_name),
                    "tool_call_id": msg_tool_call_id,
                    "status": _tool_status(msg_status),
                    "output": _summarize_tool_output(content),
                    "complete": False,
                }
            ]

        return []

    def _classify_parent_tool_calls(
        self,
        *,
        tool_calls: list[dict[str, Any]],
        run_id: str | None,
        agent_id: str | None,
        agent_version_id: str | None,
        definition: Any,
        root_resolved_model: Any = None,
        child_resolved_models: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """부모 AIMessage의 `tool_calls`를 전부 순회해 이벤트로 펼친다.

        위임(`task`)과 직접 도구 호출이 한 AIMessage에 같이 실려 올 수도 있다는
        전제로, 종류를 가리지 않고 전부 처리한다(예전에는 `tool_calls[0]`만
        보고 나머지는 조용히 버렸다).
        """
        subagent_defs_by_alias = {
            sub_def.alias: sub_def for sub_def in getattr(definition, "subagents", ()) or ()
        }

        events: list[dict[str, Any]] = []
        for call in tool_calls:
            tool_ref = call.get("name")
            if not tool_ref:
                continue

            if tool_ref == DELEGATION_TOOL_NAME:
                args = call.get("args") or {}
                alias = args.get("subagent_type")
                task_summary = args.get("description", "")
                call_id = call.get("id")
                child_run_id = str(uuid.uuid4())

                # §14.2/§14.3의 agent_id/agent_version_id/subagent_name은 Child
                # 자신의 값이다(루트 값이 아님) — `definition.subagents`에 이미
                # DB에서 조회한 Child 자신의 정의가 들어 있다(loader.py). MVP는
                # 위임 1단계뿐이라 이 조회에 재귀가 필요 없다: `alias`는
                # `build_subagent()`가 `CompiledSubAgent(name=definition.alias,
                # ...)`로 등록한 값과 정확히 같은 값이라(같은 SubagentDefinition.
                # alias), deepagents의 `subagent_type`과 1:1로 대응한다.
                sub_def = subagent_defs_by_alias.get(alias)
                child_agent_id = sub_def.agent_id if sub_def is not None else agent_id
                child_agent_version_id = sub_def.agent_version_id if sub_def is not None else agent_version_id
                subagent_name = sub_def.name if sub_def is not None else None

                info = {
                    "alias": alias,
                    "task_summary": task_summary,
                    "run_id": child_run_id,
                    "agent_id": child_agent_id,
                    "agent_version_id": child_agent_version_id,
                    "subagent_name": subagent_name,
                }
                if call_id:
                    # call_id가 없으면(비정상 입력) 나중에 tool_call_id로 못
                    # 찾는다 — 그래도 subagent_started 자체는 그대로 낸다.
                    self._pending[call_id] = info
                # 2026-08-19, §10순위(Child Run Snapshot) — Child 자신의
                # resolved_model을 `child_resolved_models`에서 alias로
                # 찾는다(위 agent_id/agent_version_id/subagent_name과 정확히
                # 같은 조회 패턴). 못 찾으면(예: general-purpose — GP는 Root와
                # 같은 model로 돈다, `factory.py`가 GP 전용 모델을 따로
                # resolve하지 않는다) Root 자신의 값으로 폴백한다.
                resolved = (child_resolved_models or {}).get(alias)
                if resolved is None:
                    resolved = root_resolved_model
                events.append(
                    {
                        "type": EVENT_SUBAGENT_STARTED,
                        "run_id": child_run_id,
                        "parent_run_id": run_id,
                        "agent_id": child_agent_id,
                        "agent_version_id": child_agent_version_id,
                        "subagent_alias": alias,
                        "subagent_name": subagent_name,
                        "task_summary": task_summary,
                        # `tracing/__init__.py`의 `_start_run()`이 `EVENT_AGENT_STARTED`와
                        # 동일하게 `.get()`으로 읽어 `agent_run.resolved_provider`/
                        # `resolved_endpoint_hash`에 적재한다 — 그 함수 자체는
                        # 안 고쳤다(이미 이벤트 타입을 안 가리고 제네릭하게
                        # 읽는다).
                        "resolved_provider": getattr(resolved, "provider", None),
                        "resolved_endpoint_hash": _resolved_endpoint_hash(resolved),
                        "complete": False,
                    }
                )
            else:
                # 위임이 아닌, 부모가 자기 도구를 직접 호출하는 경우
                # (langgraph ToolNode는 루트/서브그래프를 구분하지 않는다 —
                # 위 모듈 docstring 참고). subagent_alias=None으로 "부모
                # 자신의 호출"임을 구분한다.
                events.append(
                    {
                        "type": EVENT_TOOL_STARTED,
                        "run_id": run_id,
                        "subagent_alias": None,
                        "tool_ref": tool_ref_from_model_name(tool_ref),
                        "tool_name": _tool_label(tool_ref_from_model_name(tool_ref)),
                        "tool_call_id": call.get("id"),
                        "arguments": call.get("args") or {},
                        "complete": False,
                    }
                )
        return events

    def _resolve_subagent_info(self, ns_prefix: str | None) -> dict[str, str] | None:
        """네임스페이스 접두사를 그 안에서 도는 서브 에이전트 정보(alias/run_id)로 바꾼다.

        `_classify`의 자식 네임스페이스 분기와 `_classify_progress`(도구 진행
        이벤트)가 똑같이 쓴다 — "이 네임스페이스가 어느 위임에 속하는가"는 한
        곳에서만 판단해야 두 분기가 다른 답을 내는 일이 없다.

        **한계(2026-08-14 재설계 후에도 남음)**: 자식 내부 이벤트에는 부모의
        `tool_call_id`가 실려 오지 않으므로, 여러 위임이 동시에 도는 동안
        "이 네임스페이스를 처음 보면 아직 안 묶인 것 중 가장 먼저 시작된
        위임에 붙인다"는 순서 휴리스틱을 쓴다. 위 모듈 docstring 참고.
        """
        if ns_prefix is None:
            return None

        info = self._namespace_subagent.get(ns_prefix)
        if info is None:
            for candidate in self._pending.values():
                if candidate not in self._namespace_subagent.values():
                    info = candidate
                    self._namespace_subagent[ns_prefix] = info
                    break

        return info

    def _classify_progress(
        self, *, ns_prefix: str | None, payload: dict[str, Any], run_id: str | None
    ) -> dict[str, Any] | None:
        """`mode="custom"` 이벤트 — 도구 핸들러가 `get_stream_writer()`로 직접
        흘려보낸 진행 이벤트(tools/adapters.py `_drain_with_progress`).

        어댑터가 항상 `tool_ref`를 채워 보낸다 — 없으면 이 런타임이 낸 게
        아니라고 보고 무시한다(다른 목적의 custom 이벤트가 섞여 들어올 가능성에
        대비).
        """
        tool_ref = payload.get("tool_ref")
        if not tool_ref:
            return None

        info = self._resolve_subagent_info(ns_prefix)
        event: dict[str, Any] = {
            "type": EVENT_TOOL_PROGRESS,
            "run_id": info.get("run_id") if info else run_id,
            "subagent_alias": info.get("alias") if info else None,
            "tool_ref": tool_ref,
            "detail": {key: value for key, value in payload.items() if key != "tool_ref"},
            "complete": False,
        }
        if info is not None:
            event["parent_run_id"] = run_id
        return event

    def _classify_reasoning_delta(
        self, *, ns_prefix: str | None, chunk: Any, run_id: str | None
    ) -> list[dict[str, Any]]:
        """`mode="messages"`의 `AIMessageChunk` 하나에서 reasoning 텍스트 조각을
        뽑는다. 위 "reasoning 실시간 스트리밍" 절의 `(block_index, summary_index)`
        커서 판정이 여기 있다 — 실측(2026-08-18)으로는 청크 하나에 reasoning
        블록이 최대 하나, 그 안 `summary`도 항목 하나뿐이지만, 방어적으로
        전부 순회한다.
        """
        content = getattr(chunk, "content", None)
        if not isinstance(content, list):
            return []

        info = self._resolve_subagent_info(ns_prefix)
        events: list[dict[str, Any]] = []
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "reasoning":
                continue
            block_index = block.get("index")
            for summary_item in block.get("summary") or []:
                if not isinstance(summary_item, dict):
                    continue
                text = summary_item.get("text")
                if not text:
                    # 문단이 막 시작될 때(`response.reasoning_summary_part.added`)
                    # 빈 문자열 placeholder로 온다 — 보여줄 게 없다.
                    continue

                key = (block_index, summary_item.get("index"))
                append = self._reasoning_cursor.get(ns_prefix) == key
                self._reasoning_cursor[ns_prefix] = key

                event: dict[str, Any] = {
                    "type": EVENT_REASONING,
                    "text": text,
                    # 이 문단의 이어지는 델타인가(true) 새 문단인가(false) —
                    # 화면(liveChat.ts)이 이 값만 보고 마지막 reasoningSteps
                    # 항목에 이어붙일지 새로 만들지 정한다.
                    "append": append,
                    "run_id": info.get("run_id") if info else run_id,
                    "subagent_alias": info.get("alias") if info else None,
                    "complete": False,
                }
                if info is not None:
                    event["parent_run_id"] = run_id
                events.append(event)
        return events


__all__ = [
    "EVENT_AGENT_STARTED",
    "EVENT_AWAITING_CONFIRMATION",
    "EVENT_ERROR",
    "EVENT_MESSAGE_DELTA",
    "EVENT_REASONING",
    "EVENT_RESULT",
    "EVENT_SUBAGENT_COMPLETED",
    "EVENT_SUBAGENT_STARTED",
    "EVENT_TOOL_COMPLETED",
    "EVENT_TOOL_PROGRESS",
    "EVENT_TOOL_STARTED",
    "EventMapper",
]
