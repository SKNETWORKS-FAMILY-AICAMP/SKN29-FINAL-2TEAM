"""레거시 Agent Loop이 남긴 **공유 상수**.

2026-08-22까지 이 파일에는 `run_agent()`(레거시 실행기)와 그 조립부가 있었다.
챗 발화는 2026-08-14에 전부 새 엔진(`services/agent_runtime/`)으로 옮겨 갔고,
마지막 호출자였던 레거시 챗 재개 경로와 빌더 테스트 실행을 2026-08-22에
지우면서 그 엔진은 아무도 부르지 않는 코드가 됐다 — 레거시 `agent`/`agent_tool`
스키마 폐기와 함께 걷어냈다.

**그런데 이 모듈이 정한 몇 가지는 새 엔진이 그대로 쓴다.** 옮기지 않고 여기
둔 이유는 이 이름들이 이미 여러 곳에서 import되고 있고, 값이 어디서 왔는지
(두 엔진이 같은 기준을 봐야 한다는 근거) 이 파일에 적혀 있기 때문이다.
"""

from __future__ import annotations

from apps.connectors.oauth import OAuthError
from backend.db.errors import RepositoryError
from services.harness import registry

#: 이벤트 타입. Chat API와 화면이 같은 문자열을 봐야 해서 상수로 둔다.
#: 새 엔진(`services/agent_runtime/events.py`)이 같은 값을 내보내므로
#: `apps/chat/api_views.py`의 중계·적재가 두 엔진을 구분하지 않아도 된다.
EVENT_STAGE = "stage"
EVENT_TOOL_CALL_STARTED = "tool_call_started"
EVENT_TOOL_CALL_FINISHED = "tool_call_finished"
EVENT_AWAITING_CONFIRMATION = "awaiting_confirmation"
EVENT_RESULT = "result"
EVENT_ERROR = "error"

#: Anthropic 의 OpenAI 호환 경로. 우리가 제공하는 Claude 가 여기로 간다 —
#: 별도 SDK 없이 같은 어댑터로 받는다(2026-08-12 실측: 도구 호출까지 정상,
#: `max_tokens` 도 필수가 아니다).
ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1/"

#: 에이전트에 값이 없을 때의 기본. **`.env` 가 아니라 코드에 둔다** — 환경마다
#: 다른 모델로 도는 것을 막고, 화면이 고른 값이 언제나 이긴다(2026-08-12).
DEFAULT_MODEL = "gpt-5.6-luna"
DEFAULT_EFFORT = "low"

#: 사용자에게 사유를 그대로 보여도 되는 실패들. 나머지는 뭉뚱그려 말한다 —
#: 내부 사정을 그대로 흘리지 않기 위해서다.
#:
#: **공개 이름이다** — 새 런타임(`services/agent_runtime/factory.py`)이 같은
#: 기준을 써야 해서 밑줄을 뗐다. 두 엔진이 서로 다른 목록을 들면, 같은 실패가
#: 한쪽에서는 사유와 함께 보이고 다른 쪽에서는 「요청을 끝내지 못했습니다」로만
#: 보인다(2026-08-18 QA 에서 실제로 그랬다).
SPEAKABLE_ERRORS = (registry.ToolInputError, RepositoryError, OAuthError)

__all__ = [
    "ANTHROPIC_BASE_URL",
    "DEFAULT_EFFORT",
    "DEFAULT_MODEL",
    "EVENT_AWAITING_CONFIRMATION",
    "EVENT_ERROR",
    "EVENT_RESULT",
    "EVENT_STAGE",
    "EVENT_TOOL_CALL_FINISHED",
    "EVENT_TOOL_CALL_STARTED",
    "SPEAKABLE_ERRORS",
]
