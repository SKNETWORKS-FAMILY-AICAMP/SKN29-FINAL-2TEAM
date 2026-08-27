"""Deep Agents 내부 이벤트를 애플리케이션 공통 이벤트로 변환한다.

정본: docs/설계 및 구현/3_중간발표 이후/작업기록/Deep_Agents/2026-08-13_02_Deep-Agent_런타임_공통_계약_v1.md §14

## 스트림 모드

- `"updates"` — 6단계 분류(위임·도구 시작/종료)의 유일한 근거. 모델 노드가
  통째로 끝난 뒤 오는 완성된 `AIMessage`라 `tool_calls`가 다 채워져 있다.
- `"messages"` — reasoning 델타 전용(`_classify_reasoning_delta`). 토큰 단위라
  6단계 분류에는 못 쓴다.
- `"custom"` — `task_extraction`/`jira_get_issues`처럼 제너레이터로 진행 상황을
  내는 도구(`tools/adapters.py`)가 `get_stream_writer()`로 흘려보내는 값.
  내용이 도구마다 달라 재해석하지 않고 `EVENT_TOOL_PROGRESS`의 `detail`에
  그대로 담는다.

## `"updates"`에서 관찰되는 신호

- 네임스페이스 튜플이 부모/자식을 가른다 — 부모는 `()`, 자식은
  `('tools:<run-uuid>', ...)`로 시작한다.
- 위임 시작: `{'model': {'messages': [AIMessage(tool_calls=[{'name': 'task',
  'args': {'subagent_type': <alias>, 'description': <task_summary>}}])]}}`
  (deepagents 내장 `task` 도구 계약).
- 도구 호출: `{'model': ...AIMessage(tool_calls=[...])}` →
  `{'tools': ...ToolMessage(name=<tool_ref>, ...)}` 순서.
- 위임 종료: **부모 네임스페이스**로 돌아와
  `{'tools': ...ToolMessage(name='task', content=<자식의 최종 답변>)}`.
- 부모의 최종 응답: 부모 네임스페이스의 `AIMessage(content=..., tool_calls=[])`.

부모가 자기 도구를 직접 부르는 경우도 자식과 같은 model→tools 순서로 온다 —
`ToolNode`에는 namespace 개념 자체가 없고, 네임스페이스 튜플은 "어느 그래프가
이 업데이트를 냈는지"를 나타내는 귀속 태그일 뿐이다. 그래서 tool_started/
tool_completed는 부모/자식 구분 없이 동일하게 내고, 부모의 직접 호출만
`subagent_alias=None`으로 구분한다.

## 병렬 위임/도구 호출

`ToolNode._func`가 여러 `tool_calls`를 `executor.map(...)`으로 스레드풀에서
동시에 실행하므로 완료 순서가 시작 순서와 다를 수 있다. 따라서:

- `AIMessage.tool_calls`를 전부 순회한다. 위임 여러 개, 위임+직접 호출이
  섞여도 전부 이벤트로 낸다.
- 위임 완료 매칭은 FIFO가 아니라 **`ToolMessage.tool_call_id`**로 한다.
  `task()`/`atask()`가 원래 호출의 `tool_call_id`를 그대로 돌려주므로
  (`_return_command_with_state_update`) 실행 순서와 무관하게 정확하다.
- 위임 시작 시 EventMapper가 자식 `run_id`(uuid4)를 만들어
  `subagent_started`/`subagent_completed`와 그 자식 네임스페이스의
  `tool_started`/`tool_completed`/`tool_progress`에 일관되게 붙인다.
  `parent_run_id`는 그 실행의 `context.run_id`다(§14.2~14.4).

**알려진 한계**: 자식 네임스페이스 접두사(`'tools:<uuid>'`)를 어느 위임에
묶을지는 근사치다. 자식 내부 이벤트에는 부모의 `tool_call_id`가 실려 오지
않아(복귀하는 `ToolMessage`만 갖는다) "처음 보는 네임스페이스는 아직 안 묶인
것 중 가장 먼저 시작된 위임에 붙인다"는 순서 휴리스틱을 쓴다 — 위임이 진짜
동시에 돌면 틀릴 수 있다. `subagent_started`/`subagent_completed`는 부모
네임스페이스에서 tool_call_id로 정확히 매칭되므로 영향을 받지 않는다.

## Child의 agent_id/agent_version_id/subagent_name

§14.2/§14.3의 값은 루트가 아니라 **Child 자신의** 것이다. `convert()`가 받는
`definition.subagents`의 각 항목이 DB에서 조회한 Child의
`agent_id`/`agent_version_id`/`name`을 담고 있으므로(`loader.py`), `subagent_type`
(=alias)으로 찾으면 된다 — `build_subagent()`가 등록한 `CompiledSubAgent.name`과
`task()`가 받는 `subagent_type`이 같은 alias다.

위임이 1단계로 제한돼 있어(`validate_subagents()` / `loader.py`의
`_reject_if_has_subagents()` / `build_subagent()`의 `definition_has_subagents()`가
3중 강제) Child는 항상 leaf고, 평탄한 한 단계 매핑이면 충분하다.

## tool_started/tool_completed의 부가 필드

`tracing/__init__.py`가 이 이벤트를 그대로 읽어 DB에 적재하므로, `tool_call_id`가
시작-종료를 정확히 묶어야 한다(같은 도구를 병렬 호출해도 어긋나지 않게).

- `arguments` — `tool_call.input_summary`의 원본. `summarize_input()`이 요약해
  자격증명이 로그에 남지 않게 한다.
- `status` — LangChain `ToolMessage.status`("success"/"error")를 "OK"/"FAILED"로
  옮긴 값.
- `output` — 도구가 돌려준 값. `ToolMessage.text`를 `_summarize_tool_output()`으로
  길이만 잘라 담는다. **DB에는 안 쌓는다** — `_end_tool_call()`은 `status`만 읽고,
  이 필드는 스트림을 타고 화면까지만 간다.

이 필드들은 §14 계약 목록에 없다 — 이벤트 타입은 그대로 두고 필드만 얹었다.

## reasoning 실시간 스트리밍

`stream_mode="messages"`의 `AIMessageChunk.content`는 OpenAI Responses API SSE를
그대로 옮긴 블록 리스트다. reasoning 블록은 이 순서로 온다:

```
{'id': 'rs_...', 'summary': [], 'type': 'reasoning', 'content': [], 'index': 0}
{'summary': [{'index': 0, 'type': 'summary_text', 'text': ''}], 'index': 0, ...}
{'summary': [{'index': 0, 'type': 'summary_text', 'text': '**Clarifying...'}], 'index': 0, ...}
{'summary': [{'index': 0, 'type': 'summary_text', 'text': ' primes'}], 'index': 0, ...}
```

- `block['index']` — reasoning 항목 전체를 가리키는 langchain-core의 청크 병합
  키. 모델 호출 하나 안에서 항목마다 증가하고, **다음 호출에서 0부터 다시
  시작한다.**
- `block['summary'][i]['index']`(summary_index) — 그 항목 **안의** 문단 하나.

"이어지는 델타인가 새 문단인가"는 `(index, summary_index)` 쌍으로 판단한다
(`_classify_reasoning_delta`). 같으면 `"append": true`, 다르면 `false` — 화면
(`liveChat.ts`)은 이 플래그만 보고 마지막 `reasoningSteps`에 이어붙일지
새 항목을 만들지 정한다.

**모델 호출 경계에서 커서를 지운다.** `block['index']`가 호출마다 0으로
돌아가므로 이전 호출의 마지막 쌍과 다음 호출의 첫 쌍이 우연히 같을 수 있다.
`_classify()`의 "model" 노드 분기에서 그 네임스페이스 커서를 지워, 다음 호출의
첫 조각은 항상 새 단계로 뜬다.

**`"updates"` 모드는 reasoning을 내지 않는다** — "messages"가 실시간으로 이미
다 보여줬으므로 완성본을 한 번 더 내면 중복된다.

## MCP 도구 이름 치환

모델에게 나가는 함수 이름은 `model_safe_tool_name()`이 `mcp:<id>`의 콜론을
`__`로 바꾼 값이다(OpenAI 함수 이름 제약). 그래서 여기서 읽는
`AIMessage.tool_calls[i]['name']`/`ToolMessage.name`은 원래 tool_ref와 다를 수
있다 — `tool_ref_from_model_name()`으로 되돌린 값만 `"tool_ref"`로 내보낸다.
위 예시의 `<tool_ref>`도 되돌림 이후 기준이다.
"""

from __future__ import annotations

import json

import uuid
from typing import Any

from services.agent_runtime.tools.loader import tool_ref_from_model_name
from services.agent_runtime.user_results import build_user_result

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
# 도구 호출 전에 사용자에게 보여줄 짧은 실행 안내. Reasoning 원문과 분리한다.
# §14 계약에 없는 타입이다. 추론 텍스트는 tool_started/result 어디에도 자연스럽게
# 안 얹혀서 새 타입이 필요했다. `tracing/__init__.py`의 `_record()`는 모르는 타입을
# 조용히 지나치므로 DB 적재는 없다 — 화면에 실시간으로 보여주는 것이 목적이다.
EVENT_REASONING = "reasoning"

# 승인 게이트(`interrupt_on`)가 실행을 멈춘 자리. 값은 레거시
# `services/harness/runner.py`의 동명 상수와 **같은 문자열이어야 한다** —
# `ChatMessageRepository.latest_pending_confirmation()`이 SQL에서
# `content->>'type' = 'awaiting_confirmation'`을 리터럴로 검사하고,
# `apps/chat/api_views.py`의 `_history()`/`_relay()`도 이 문자열로 두 엔진을
# 가리지 않고 같은 분기를 탄다. 값이 갈리면 그 공용 코드가 새 엔진의 확인
# 대기를 못 알아본다.
#
# import로 묶지 않고 값만 맞추는 건 `EVENT_ERROR`/`EVENT_RESULT`와 같은 방식이다
# — 두 엔진은 서로의 내부를 몰라도 되게 분리하되, 화면·DB로 나가는 타입 문자열만
# 계약처럼 맞춘다.
#
# 이벤트 모양(`tool_ref`/`tool_name`/`arguments`/`resume`)도 레거시와 맞춰
# 화면·저장 코드를 그대로 재사용한다. `resume`의 내용물만 다르다 — 이 엔진은
# 상태가 Checkpointer(RDS)에 있어 "무엇을 승인하는가"만 있으면 된다.
EVENT_AWAITING_CONFIRMATION = "awaiting_confirmation"

# deepagents가 서브 에이전트 위임에 쓰는 내장 도구 이름. 이 이름의 tool_call은
# "실제 도구 호출"이 아니라 "위임"으로 분류한다.
DELEGATION_TOOL_NAME = "task"

# deepagents 0.7.5의 `task`가 존재하지 않는 subagent_type을 받으면 예외 대신
# 돌려주는 문자열의 접두어다(`deepagents/middleware/subagents.py`).
#
# ToolMessage가 이 경우도 `status="success"`로 감싸기 때문에 status로는 구분할 수
# 없어, 문자열 접두어 매칭이 유일하게 근거 있는 탐지 방법이다. 버전이 고정
# (`deepagents==0.7.5`)이라 문구도 고정 — **업그레이드 시 이 상수를 같이 확인할 것.**
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
    """도구가 실제로 돌려준 내용을 화면(작업 과정 타임라인)에 보일 만큼만 남긴다.

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


#: 한 호출이 남길 문서 식별자의 상한. `document_search` 는 coarse 후보 + 근거를
#: 합쳐도 수십 건이지만, 도구가 비정상적으로 큰 결과를 낼 가능성까지 열어 두지
#: 않는다(`tool_call_idempotency.result_text` 의 상한과 같은 이유).
RETRIEVED_DOC_IDS_MAX = 50


def _retrieved_doc_ids(content: Any) -> list[str]:
    """도구 결과에서 **문서 식별자만** 골라낸다(2026-08-21).

    멘토링 전달 "Tool 호출 결과 어떤 문서/데이터가 조회되었는지" 를 받는
    자리다. `document_search` 가 무엇을 골랐는지는 지금까지 `sources` 진행
    이벤트로 화면에 한 번 흐르고 사라졌다 — `tool_call` 에는 질의문
    (`input_summary`)만 남아서, 나중에 "그때 무슨 문서를 봤나"를 물을 수 없었다.

    **도구별로 분기하지 않는다.** 결과 JSON 안에 있는 `doc_id` 키를 재귀로
    전부 모은다 — `document_search` 는 `evidence` 와 `not_indexed` 두 곳에 나눠
    담고, 다른 도구가 나중에 같은 키를 쓰면 자동으로 함께 잡힌다. 어느 목록에
    있었는지는 구분하지 않는다: 접근 감사가 묻는 것은 "어느 문서를 봤나"이지
    "그중 무엇을 인용했나"가 아니다.

    `content` 는 `ToolMessage.text`(문자열)다. 핸들러가 dict 를 돌려주면
    langchain-core 의 `_stringify()` 가 `json.dumps(..., ensure_ascii=False)`
    로 만든 값이라(설치된 소스 확인) 되읽을 수 있다. 평문을 돌려주는 도구는
    파싱이 실패하고 빈 목록이 된다 — 그게 정상이다.
    """
    if not isinstance(content, str) or "doc_id" not in content:
        # 흔한 경우(문서와 무관한 도구)를 JSON 파싱 없이 먼저 걸러낸다.
        return []
    try:
        parsed = json.loads(content)
    except (ValueError, TypeError):
        return []

    found: list[str] = []
    seen: set[str] = set()

    def walk(node: Any) -> None:
        if len(found) >= RETRIEVED_DOC_IDS_MAX:
            return
        if isinstance(node, dict):
            doc_id = node.get("doc_id")
            if isinstance(doc_id, str) and doc_id and doc_id not in seen:
                seen.add(doc_id)
                found.append(doc_id)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(parsed)
    return found


def _produced_file(content: Any) -> dict[str, str] | None:
    """도구가 **만들어 낸 파일**. 없으면 `None`(대부분의 도구가 그렇다).

    `_retrieved_doc_ids` 와 달리 `doc_id` 를 찾아 헤매지 않는다 — 최상위 `file`
    키 하나만 본다. 읽기 도구의 결과에는 `doc_id` 가 잔뜩 들어 있어서(검색 근거·
    문서 목록) 그 방식으로는 「본 문서」와 「만든 파일」을 구별할 수 없다.
    **도구가 명시적으로 `file` 로 담을 때만** 화면에 받기 단추가 생긴다
    (`registry.py` 의 `_file_ref()` 가 그 모양을 만든다).

    도구별로 분기하지 않는다 — 같은 계약을 지키는 도구가 늘어도 화면은 안 고친다.
    """

    if not isinstance(content, str) or '"file"' not in content:
        # 흔한 경우를 JSON 파싱 없이 먼저 걸러낸다(`_retrieved_doc_ids` 와 같은 이유).
        return None
    try:
        parsed = json.loads(content)
    except (ValueError, TypeError):
        return None
    if not isinstance(parsed, dict):
        return None
    node = parsed.get("file")
    if not isinstance(node, dict):
        return None
    doc_id, file_name = node.get("doc_id"), node.get("file_name")
    if not isinstance(doc_id, str) or not isinstance(file_name, str):
        return None
    return {
        "doc_id": doc_id,
        "file_name": file_name,
        "mime_type": node.get("mime_type") if isinstance(node.get("mime_type"), str) else None,
    }


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
        # 아직 ToolMessage 완료를 못 본 직접 도구 호출. HITL interrupt payload의
        # action_requests에는 LangChain tool_call_id가 빠져 있으므로, 직전에 본
        # AIMessage 호출과 이름·인자로 대응시켜 승인 카드의 trace_resume_state에
        # 영속화한다. middleware에 되돌려줄 action_requests 자체에는 내부 필드를
        # 섞지 않는다.
        self._pending_direct_tool_calls: list[dict[str, Any]] = []
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
        # run_id -> {"iterations", "token_in", "token_out"}. 아래
        # `_count_model_call()`이 채우고 끝나는 이벤트가 실어 나른다.
        self._usage: dict[str, dict[str, int | None]] = {}
        # 같은 interrupt가 서브그래프와 루트 namespace에서 반복 전달될 수
        # 있다. 승인 카드와 재개 상태는 interrupt ID당 한 번만 낸다.
        self._seen_interrupt_ids: set[str] = set()

    def restore_hitl_state(self, state: dict[str, Any] | None) -> None:
        """승인 대기 전에 저장한 EventMapper의 최소 상관관계 상태를 복원한다."""
        if not isinstance(state, dict):
            return
        pending_subagents = state.get("pending_subagents")
        if isinstance(pending_subagents, dict):
            self._pending = {
                str(call_id): dict(info)
                for call_id, info in pending_subagents.items()
                if call_id and isinstance(info, dict)
            }
        pending_tools = state.get("pending_tool_calls")
        if isinstance(pending_tools, list):
            self._pending_direct_tool_calls = [
                dict(item) for item in pending_tools if isinstance(item, dict)
            ]
        namespace_subagents = state.get("namespace_subagents")
        if isinstance(namespace_subagents, dict):
            self._namespace_subagent = {
                str(namespace): dict(info)
                for namespace, info in namespace_subagents.items()
                if namespace and isinstance(info, dict)
            }

    def _remember_direct_tool_call(
        self, *, run_id: str | None, call: dict[str, Any]
    ) -> None:
        call_id = call.get("id")
        name = call.get("name")
        if not run_id or not call_id or not name:
            return
        self._pending_direct_tool_calls.append(
            {
                "run_id": run_id,
                "tool_call_id": call_id,
                "name": name,
                "args": call.get("args") or {},
            }
        )

    def _forget_direct_tool_call(self, tool_call_id: str | None) -> None:
        if not tool_call_id:
            return
        self._pending_direct_tool_calls = [
            item
            for item in self._pending_direct_tool_calls
            if item.get("tool_call_id") != tool_call_id
        ]

    def _interrupted_tool_calls(
        self, action_requests: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """HITL action 순서에 맞는 영속 `(run_id, tool_call_id)` 목록을 만든다."""
        available = list(self._pending_direct_tool_calls)
        matched: list[dict[str, Any]] = []
        for action_index, request in enumerate(action_requests):
            if not isinstance(request, dict):
                continue
            name = request.get("name")
            args = request.get("args") or {}
            index = next(
                (
                    i
                    for i, item in enumerate(available)
                    if item.get("name") == name and item.get("args") == args
                ),
                None,
            )
            if index is None:
                # 일부 middleware 버전은 description/정규화 과정에서 args 모양을
                # 바꿀 수 있다. 같은 이름 중 먼저 시작된 호출로 제한해 매칭하고,
                # 이름조차 없으면 잘못된 행을 고르지 않고 누락시킨다.
                index = next(
                    (i for i, item in enumerate(available) if item.get("name") == name),
                    None,
                )
            if index is not None:
                item = available.pop(index)
                matched.append(
                    {
                        "action_index": action_index,
                        "run_id": item["run_id"],
                        "tool_call_id": item["tool_call_id"],
                    }
                )
        return matched

    def _count_model_call(self, run_id: str | None, message: Any) -> None:
        """모델 호출 하나를 이 run 의 누계에 더한다(2026-08-21).

        `agent_run.iterations`/`token_in`/`token_out` 을 채우려고 둔다. 이 값을
        볼 수 있는 자리가 여기뿐이다 — 변환된 이벤트만 보는 `tracing/` 은 원시
        `AIMessage` 에 닿지 못하고, 전용 이벤트를 새로 내면 `apps/chat` 의
        `_relay()` 가 그대로 브라우저까지 흘려보낸다(그쪽은 종류를 안 가리고
        전부 내보낸다).

        **`usage_metadata` 가 없으면 토큰은 계속 `None` 이다 — 0 이 아니다.**
        모르는 값을 0 으로 적으면 「토큰을 안 쓴 실행」과 구분이 사라진다
        (`registry.py` 의 `_positive_or_none` 이 공수 0 을 비우는 것과 같은
        판단이다). 실제로 안 오는 경로가 있다: `openai_compatible`(팀 커스텀
        엔드포인트)은 `base_url` 을 넘기는 순간 `langchain_openai` 의
        `stream_usage` 자동 활성화 조건에서 빠진다(설치된 1.3.0 소스 확인) —
        스트리밍 응답에 usage 가 안 실린다. `iterations` 는 usage 와 무관하게
        항상 센다.
        """
        if not run_id:
            return
        totals = self._usage.setdefault(
            run_id, {"iterations": 0, "token_in": None, "token_out": None}
        )
        totals["iterations"] = (totals["iterations"] or 0) + 1
        usage = getattr(message, "usage_metadata", None)
        if not isinstance(usage, dict):
            return
        token_in = usage.get("input_tokens")
        token_out = usage.get("output_tokens")
        total = usage.get("total_tokens")
        # **설명되지 않는 나머지는 출력으로 센다.** Gemini의 OpenAI 호환 주소는
        # thinking 토큰을 `total_tokens`에만 넣고 `completion_tokens_details`를
        # `null`로 준다(실측: `prompt 6 · completion 1 · total 149`). 그대로 적으면
        # 합계가 149 대신 7이 된다. 별도 칸을 두려면 스키마 컬럼 추가 = 팀원 전원
        # ALTER라, 모델이 만든 토큰이니 출력 쪽에 얹는다. 총합이 맞는 제공자는
        # 나머지가 0이라 영향이 없다.
        if isinstance(total, int) and isinstance(token_in, int) and isinstance(token_out, int):
            token_out = max(token_out, total - token_in)
        for key, value in (("token_in", token_in), ("token_out", token_out)):
            if isinstance(value, int):
                totals[key] = (totals[key] or 0) + value

    def usage_for(self, run_id: str | None, *, close: bool = False) -> dict[str, Any]:
        """이 run 의 누계. 끝나는 이벤트에 실으면 `tracing/` 이 그대로 적재한다.

        `close=True` 면 누계를 버린다 — 끝난 실행을 다시 볼 일이 없다. 모델을
        한 번도 못 부르고 끝난 실행(시작하자마자 실패)은 `iterations=0` 이다.
        """
        empty: dict[str, Any] = {"iterations": 0, "token_in": None, "token_out": None}
        if not run_id:
            return empty
        totals = self._usage.pop(run_id, None) if close else self._usage.get(run_id)
        return dict(totals) if totals is not None else empty

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
            # Reasoning summary는 관측·저장 호환성을 위해 이벤트 계약에 남긴다.
            # 채팅 UI는 이를 표시하지 않고, 사용자용 안내는 아래 updates/model
            # 분기의 일반 text 블록에서 만든 사용자용 작업 안내만 소비한다.
            return self._classify_reasoning_delta(ns_prefix=ns_prefix, chunk=chunk, run_id=run_id)

        if not isinstance(payload, dict):
            return []

        if mode == "custom":
            event = self._classify_progress(ns_prefix=ns_prefix, payload=payload, run_id=run_id)
            return [event] if event is not None else []

        if mode != "updates":
            return []

        # `HumanInTheLoopMiddleware.after_model`이 `interrupt()`를 부르면 LangGraph는
        # 다른 노드 출력과 **완전히 분리된** 자기만의 "updates" 청크로
        # `{"__interrupt__": (Interrupt(...),)}`를 낸다(`pregel/_loop.py`의
        # `output_writes()`: `map_output_updates()`가 `INTERRUPT` 채널 write를 걸러낸
        # 뒤 `_emit("updates", ...)`으로 따로 낸다). 이 키가 있으면 다른 node_name과
        # 섞일 수 없으므로 바로 처리하고 반환한다.
        #
        # **여기서 안 잡으면 조용히 사라진다.** 아래 일반 루프는 `node_output`이
        # dict가 아니면 건너뛰는데 `__interrupt__`의 값은 `tuple[Interrupt, ...]`다.
        # 그러면 `convert()`가 빈 리스트를 돌려주고 스트림이 그대로 끝나서, 화면에는
        # 확인 카드도 오류도 없이 아무 일 없었던 것처럼 보이지만 실제로는 그래프가
        # 도구 실행 직전에 멈춰 있게 된다.
        # 정본: `2026-08-19_05_HITL_resume_구현설계.md` §1
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
        interrupt_id = getattr(first, "id", None)
        if interrupt_id and interrupt_id in self._seen_interrupt_ids:
            return []
        if interrupt_id:
            self._seen_interrupt_ids.add(interrupt_id)
        hitl_request = first.value if isinstance(first.value, dict) else {}
        action_requests = hitl_request.get("action_requests") or []
        interrupted_tool_calls = self._interrupted_tool_calls(action_requests)
        return [
            {
                "type": EVENT_AWAITING_CONFIRMATION,
                "run_id": run_id,
                "agent_id": getattr(definition, "agent_id", None),
                "agent_version_id": getattr(definition, "agent_version_id", None),
                # 재개 키. 한 턴에 interrupt가 하나뿐이라 지금은 없어도 재개되지만,
                # 병렬 interrupt를 지원하게 되면 이 값으로 특정 interrupt를 고른다.
                "interrupt_id": interrupt_id,
                # 화면이 확인 카드를 그리는 데 필요한 전부(도구 이름·인자·설명).
                # 재개 시 이 목록 길이만큼 `decisions`를 만들어야 하므로
                # (순서·개수가 어긋나면 `HumanInTheLoopMiddleware`가 ValueError)
                # 그대로 저장해 둔다.
                "action_requests": action_requests,
                # 화면/미들웨어 입력과 분리된 내부 추적 상태. 채팅 메시지에 이
                # 이벤트가 저장됐다가 resume 때 EventMapper와 DB 상관관계를
                # 복원한다. 원문 Tool 결과나 credential은 포함하지 않는다.
                "trace_resume_state": {
                    "pending_subagents": dict(self._pending),
                    # 병렬 Child가 둘 이상이면 새 mapper가 도착 순서만 보고 다시
                    # 붙일 경우 run_id가 서로 바뀔 수 있다. interrupt 전 이미
                    # 확정한 namespace → Child 대응도 함께 보존한다.
                    "namespace_subagents": dict(self._namespace_subagent),
                    "pending_tool_calls": list(self._pending_direct_tool_calls),
                    "interrupted_tool_calls": interrupted_tool_calls,
                },
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
        # `.content`를 직접 쓰면 블록 리스트가 원시 그대로 `result` 이벤트의 `text`로
        # 샌다. `BaseMessage.text`는 문자열/블록 리스트 둘 다 받아 `type: "text"`
        # 블록만 이어붙인 평문을 돌려주고(`str` 서브클래스라 JSON 직렬화도 안전),
        # 콘텐츠가 이미 문자열인 일반 모델에도 동일하게 안전하다.
        content = message.text

        agent_id = getattr(definition, "agent_id", None)
        agent_version_id = getattr(definition, "agent_version_id", None)

        if ns_prefix is None:
            # --- 부모 네임스페이스 -------------------------------------------
            if node_name == "model":
                # reasoning은 "messages" 모드가 이미 실시간으로 다 냈다. 여기서
                # 완성본을 또 내면 중복되므로, 커서만 지워 다음 호출의 첫 조각이
                # 이 호출 끝에 잘못 이어붙지 않게 한다(모듈 docstring 참고).
                self._reasoning_cursor[ns_prefix] = None
                # 도구를 부르든 최종 답이든 모델 호출은 모델 호출이라 분기 앞에서
                # 한 번만 센다.
                self._count_model_call(run_id, message)
                events: list[dict[str, Any]] = []
                if tool_calls:
                    # 프롬프트가 요청한 Preamble은 tool_calls와 같은 AIMessage의
                    # 일반 text 블록으로 온다. 모델이 생략해도 UI가 영어
                    # Reasoning에 의존하지 않도록 결정론적 한국어 안내를 보낸다.
                    korean_content = content if any("가" <= char <= "힣" for char in content) else ""
                    tool_events = self._classify_parent_tool_calls(
                            tool_calls=tool_calls,
                            run_id=run_id,
                            agent_id=agent_id,
                            agent_version_id=agent_version_id,
                            definition=definition,
                            root_resolved_model=root_resolved_model,
                            child_resolved_models=child_resolved_models,
                        )
                    if tool_events:
                        tool_events[0]["user_update"] = korean_content or "요청을 처리하기 위해 필요한 도구를 확인하고 있습니다."
                        tool_events[0]["user_update_source"] = "model" if korean_content else "application_fallback"
                    events.extend(tool_events)
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
                            # 이 실행이 쓴 회전 수·토큰. `tracing/` 의
                            # `_finish_root_run()` 이 그대로 `agent_run` 에 적는다.
                            **self.usage_for(run_id, close=True),
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
                # 자식이 쓴 몫은 자식 run 에 적는다 — 자식의 모델 호출은 이미
                # 자식 네임스페이스에서 다 지나갔으므로 여기서는 누계가 완성돼 있다.
                base.update(self.usage_for(info.get("run_id"), close=True))
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
                self._forget_direct_tool_call(msg_tool_call_id)
                completed_tool_ref = tool_ref_from_model_name(msg_name)
                return [
                    {
                        "type": EVENT_TOOL_COMPLETED,
                        "run_id": run_id,
                        "subagent_alias": None,
                        "tool_ref": completed_tool_ref,
                        "tool_call_id": msg_tool_call_id,
                        "status": _tool_status(msg_status),
                        "output": _summarize_tool_output(content),
                        # 화면용 허용 필드. 원본 모델 입력과 500자 output 계약은
                        # 그대로 두고, 큰 구조화 결과도 UI가 안전하게 읽게 한다.
                        "user_result": build_user_result(
                            tool_ref=completed_tool_ref, content=content
                        ),
                        # 이 호출이 건드린 문서. `tracing/` 이 `tool_call`에 적는다.
                        "retrieved_doc_ids": _retrieved_doc_ids(content),
                        # 이 호출이 만들어 낸 파일. 화면이 받기 단추를 그린다.
                        "produced_file": _produced_file(content),
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
            self._count_model_call(child_run_id, message)
            events: list[dict[str, Any]] = []
            for call in tool_calls:
                tool_ref = call.get("name")
                if tool_ref and tool_ref != DELEGATION_TOOL_NAME:
                    self._remember_direct_tool_call(run_id=child_run_id, call=call)
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
            self._forget_direct_tool_call(msg_tool_call_id)
            completed_tool_ref = tool_ref_from_model_name(msg_name)
            return [
                {
                    "type": EVENT_TOOL_COMPLETED,
                    "run_id": child_run_id,
                    "parent_run_id": run_id,
                    "subagent_alias": alias,
                    "tool_ref": completed_tool_ref,
                    "tool_call_id": msg_tool_call_id,
                    "status": _tool_status(msg_status),
                    "output": _summarize_tool_output(content),
                    "user_result": build_user_result(
                        tool_ref=completed_tool_ref, content=content
                    ),
                    "retrieved_doc_ids": _retrieved_doc_ids(content),
                    # **서브 에이전트가 만든 것도 낸다.** 여기 있는 다른 값들과
                    # 달리 파일은 내부 진행이 아니라 **결과물**이라, 누가 만들었든
                    # 사람은 받아야 한다(화면이 subagent_alias 로 거르는 규칙의
                    # 의도적 예외 — `liveChat.ts` 의 같은 자리 주석 참고).
                    "produced_file": _produced_file(content),
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

                # 여기 값들은 루트가 아니라 Child 자신의 것이다 — 자세한 근거는
                # 모듈 docstring "Child의 agent_id/..." 절.
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
                # Child의 resolved_model을 alias로 찾는다(위와 같은 조회 패턴).
                # 못 찾으면 Root 값으로 폴백한다 — GP가 그 경우다. `factory.py`가
                # GP 전용 모델을 따로 resolve하지 않아 Root와 같은 model로 돈다.
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
                        # `tracing/__init__.py`의 `_start_run()`이 이벤트 타입을
                        # 가리지 않고 `.get()`으로 읽어 적재한다.
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
                self._remember_direct_tool_call(run_id=run_id, call=call)
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
