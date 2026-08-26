"""사용자가 채팅에 직접 입력한 credential·개인정보·권한/보안 서술을 모델에게 보내기 전에 가린다.

정본: `sensitive_text.py` 모듈 docstring, `docs/설계 및 구현/3_중간발표 이후/작업기록/
Juyeon_Agents_Description/00_내부_흐름_분석.md` §2-①.

2026-08-26 이전에는 `apps/chat/api_views.py`가 `mask_sensitive()`를 직접 불러
그래프에 넘길 문자열(`model_input`)과 과거 대화 재전송(`_history()`)을 각각
가렸다. 이 미들웨어가 그 두 호출을 대체한다 — `before_model`은 매 모델 호출
직전에 그 시점의 `state["messages"]` 전체를 보므로, 이번 턴에 새로 들어온
입력이든(§2-①의 "채팅 입력") 체크포인터가 없어 매 턴 통째로 다시 실리는
과거 대화든(§2-①의 재전송 경로, `stream_adapter.py`의 `thread_id` 없는 분기)
같은 자리에서 한 번에 처리된다 — 호출 지점을 둘로 나눌 필요가 없어졌다.

**모든 `HumanMessage`를 본다** — langchain 표준 `PIIMiddleware`는 가장 최근
사용자 메시지 하나만 본다(그 미들웨어가 지키는 카테고리는 매 턴 새로 도착하는
값이라 그걸로 충분하다). 이 미들웨어는 그렇게 하면 안 된다 — 체크포인터가
없어 과거 발화가 이번 호출에 한꺼번에 실리는 경우, 가장 최근 것만 가리면
`_history()`가 하던 재전송 마스킹이 빠진다. `mask_sensitive()`는 이미
가려진 텍스트(`MASK_PLACEHOLDER`)를 다시 넣어도 그대로 돌려주므로(멱등),
매번 전체를 다시 훑어도 안전하다.

`suggest_title()`(`services/harness/naming.py`)에 넘기는 질문 문구는 예외다
— 그 호출은 deep agent 그래프를 거치지 않고 OpenAI를 직접 부르므로 이
미들웨어의 보호 범위 밖이고, `api_views.py`가 그 자리에서만 `mask_sensitive()`를
계속 직접 부른다.

**메모리 write guard(`memory/write_guard.py`)와는 다른 문제다.** 그쪽은
저장을 거부하는 차단이고, 이건 값을 가리고 통과시키는 마스킹이다 — 코드도
따로, 시점도 따로다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import HumanMessage

from services.agent_runtime.sensitive_text import mask_sensitive

if TYPE_CHECKING:
    from langchain.agents.middleware.types import AgentState
    from langgraph.runtime import Runtime


class SensitiveInputMaskMiddleware(AgentMiddleware):
    """`state["messages"]`의 모든 `HumanMessage`에서 credential·개인정보·
    권한/보안 서술을 가린다. Root/Child 둘 다에 붙인다(`middleware/factory.py`)
    — GP는 사용자 원문을 직접 보는 경로가 아직 없어서 대상이 아니다.
    """

    def before_model(self, state: "AgentState", runtime: "Runtime[Any]") -> dict[str, Any] | None:  # noqa: ARG002
        messages = state["messages"]
        if not messages:
            return None

        new_messages = list(messages)
        any_modified = False
        for i, message in enumerate(messages):
            if not isinstance(message, HumanMessage) or not message.content:
                continue
            content = str(message.content)
            masked = mask_sensitive(content)
            if masked == content:
                continue
            # 같은 `id`를 유지해야 `add_messages` reducer가 새 메시지를
            # 덧붙이는 대신 이 자리를 그대로 교체한다(langchain `PIIMiddleware`와
            # 같은 패턴).
            new_messages[i] = HumanMessage(content=masked, id=message.id, name=message.name)
            any_modified = True

        if not any_modified:
            return None
        return {"messages": new_messages}


def build_sensitive_input_mask() -> SensitiveInputMaskMiddleware:
    return SensitiveInputMaskMiddleware()


__all__ = ["SensitiveInputMaskMiddleware", "build_sensitive_input_mask"]
