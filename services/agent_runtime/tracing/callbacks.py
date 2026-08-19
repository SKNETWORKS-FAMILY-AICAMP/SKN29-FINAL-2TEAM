"""Langfuse·LangSmith LangChain 콜백 핸들러를 만든다.

2026-08-19 착수(작업기록/LangSmith_LangFuse/2026-08-19_01_작업계획.md) —
이 파일은 원래 의도적으로 비어 있었다(`agent_run`/`tool_call` 적재는
`tracing/__init__.py`의 `trace_events()`가 이벤트 스트림을 감싸는 방식으로
전부 처리하고 있었어서). Langfuse는 이벤트 스트림 밖 정보(모델 원시 호출
페이로드, LangGraph node 단위 span 트리)까지 잡아야 해서 `runtime.stream(...)`
호출부의 LangChain `config["callbacks"]`에 직접 얹는 콜백 기반 연결이 필요해
졌다 — 이 파일이 그 콜백을 만드는 자리다.

**키가 없으면 조용히 꺼진다.** `WEB_SEARCH_API_KEY`와 같은 원칙 — 키가
없다고 에이전트 실행 자체가 막히면 안 된다. `get_langfuse_callback()`/
`get_langsmith_callback()`이 `None`을 돌려주면 호출 쪽(`executor.py`)이
그냥 콜백 목록에서 뺀다.

**마스킹(2026-08-19, 지훈 리뷰로 추가 — 2026-08-19 API 수정).** 트레이스에는
도구 호출 인자·결과가 통째로 실린다 — `jira_get_issues`/`jira_create_issues`
(services/harness/registry.py, apps/connectors/clients.py의
`_jira_issue_row()`)가 담당자 `assignee_email`을 실제 값 그대로 돌려주는 게
실사용 데이터 기준 유일하게 확인된 이메일 유출 경로다. `_ensure_client_configured()`
가 `Langfuse(...)`에 `mask=_mask_data`를 넘겨서, export 직전에 관측값
(observation의 input/output)에서 이메일 패턴을 정규식으로 치환한다 — 원본
응답(사용자에게 가는 답, DB `tool_call.input_summary`)은 그대로 두고
**Langfuse로 나가는 사본만** 가린다.

처음엔 `mask_otel_spans=_mask_otel_spans`(span 속성을 순회하며 패치하는
모양)로 짰는데, **실제 설치된 SDK(`langfuse==3.15.0`, `requirements/base.txt`의
`langfuse>=3.0,<4.0` 범위)를 직접 설치해 확인해 보니 그런 파라미터가 없었다**
— `Langfuse.__init__()`가 그 키워드를 그대로 거부해 `TypeError`를 던진다.
`get_langfuse_callback()`의 넓은 `except Exception`이 이를 삼켜서, 실 키를
넣는 순간(작업계획 §3-5) Langfuse 연동 전체가 **아무 로그도 없이 조용히
안 붙는** 상태가 될 뻔했다. 실제 파라미터 이름은 `mask`이고, 모양도
`langfuse.types.MaskFunction`(`data` 키워드 하나를 받아 마스킹한 값을
돌려주는 함수)로 완전히 다르다 — 아래 `_mask_data()`가 그 모양에 맞춘다.

**LangSmith 마스킹(2026-08-19, 작업계획 §5의 "미해결 항목" 해소).** 원래
계획은 "`LANGCHAIN_TRACING_V2` env var만 켜면 코드 없이 붙는다"였는데,
그 자동 연결 경로는 `langchain-core`가 자기 기본 `Client`(마스킹 없음)로
붙기 때문에 마스킹을 걸 수가 없다 — 그래서 이 자동 경로는 계속 쓰되(끄지
않는다), **우리가 마스킹된 `Client`로 직접 만든 `LangChainTracer`를
`callbacks`에 명시적으로 얹는다.** 실제 설치된 SDK(`langsmith==0.11.0`)로
직접 확인한 근거:

- `langsmith.Client(hide_inputs=..., hide_outputs=...)`— 각각 `Callable[[dict],
  dict]`를 받는다(공식 시그니처, `Client.__init__` docstring 실측). Langfuse의
  `mask`와 같은 모양이라 `_mask_data`를 그대로 재사용한다(아래 `_mask_dict`는
  키워드만 맞춘 얇은 래퍼).
- `langchain_core.tracers.context._get_trace_callbacks()`(실제 설치된
  `langchain-core` 소스 확인) — `callback_manager.handlers`에 **이미
  `LangChainTracer`가 있으면 자기 기본 tracer를 또 안 붙인다**("If it already
  has a LangChainTracer, we don't need to add another one"). 그래서 우리가
  마스킹된 tracer를 명시적으로 넣어 두면, `LANGCHAIN_TRACING_V2=true`가
  켜져 있어도 마스킹 안 된 이중 트레이스가 새로 생기지 않는다 — env var는
  그대로 두고 이 콜백만 추가하면 된다.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_configured = False

_EMAIL_PATTERN = re.compile(r"\b[\w.-]+?@[\w.-]+?\.\w+?\b")


def _mask_data(*, data: Any, **_kwargs: Any) -> Any:
    """export 직전 관측값 하나에서 이메일을 지운다.

    `langfuse.types.MaskFunction`(실제 설치된 SDK로 확인한 진짜 모양)이
    부르는 형태다 — span을 순회하는 게 아니라, Langfuse가 기록하려는 값
    (문자열 하나일 수도, 도구 호출 인자·결과 dict/list 전체일 수도 있다)을
    통째로 `data`로 받아서 같은 모양 그대로 돌려주면 된다. 문자열이 아닌
    구조(dict/list/tuple)는 안까지 재귀적으로 들어가 문자열만 치환한다 —
    `jira_get_issues`의 `assignee_email`처럼 중첩된 dict 안에 있어도 걸러야
    하기 때문이다. 그 밖의 타입(숫자·불리언·None 등)은 그대로 둔다.

    **pydantic 모델(2026-08-19, 실키 검증 중 발견 — 작업계획 §7 재검토).**
    `langfuse.langchain.CallbackHandler`가 LangGraph 노드/미들웨어 경계의
    `on_chain_start`/`on_chain_end`에 넘기는 `inputs`/`outputs`는 LangGraph
    state를 그대로 통과시킨 값이라, `messages` 리스트 안에 아직 dict로
    변환되지 않은 `HumanMessage`/`AIMessage` 같은 langchain-core pydantic
    객체가 그대로 들어 있다(LLM 호출 관측치 자체는 `_convert_message_to_dict`를
    거쳐 이미 dict라 위 분기로 충분했다). 이 객체는 `str`도
    `dict`/`list`/`tuple`도 아니라서 그대로(`return data`) 통과해 마스킹이
    안 걸렸다 — 실키로 Langfuse REST API(`client.observations.get_many`)를
    직접 읽어 9개 관측치 중 7개에서 원본 이메일이 그대로 남는 것을 확인하고
    나서야 드러났다. `model_dump()`(pydantic v2, langchain-core 1.x 전제)로
    한 번 dict화한 뒤 재귀적으로 마스킹한다 — 이 dict는 로그 전송용 사본일
    뿐 실제 그래프 실행에는 다시 안 쓰인다(mask()의 반환값은 Langfuse가
    span attribute를 만드는 데만 쓴다).
    """
    if isinstance(data, str):
        return _EMAIL_PATTERN.sub("[REDACTED_EMAIL]", data)
    if isinstance(data, dict):
        return {key: _mask_data(data=value) for key, value in data.items()}
    if isinstance(data, (list, tuple)):
        masked = [_mask_data(data=item) for item in data]
        return type(data)(masked)
    if not isinstance(data, type):
        model_dump = getattr(data, "model_dump", None)
        if callable(model_dump):
            try:
                return _mask_data(data=model_dump())
            except TypeError:
                # `model_dump`가 인스턴스가 아니라 클래스에 매인 미바인드
                # 메서드일 때(도구 스키마의 `args_schema`처럼 pydantic 모델
                # "클래스" 자체가 값으로 들어오는 경우) `self` 인자가 없어
                # 여기서 걸린다 — 위 `isinstance(data, type)` 체크가 그
                # 흔한 경우를 먼저 걸러내지만, 모든 변형을 다 예상할 수는
                # 없어 방어적으로 한 번 더 잡는다.
                return data
    return data


def _ensure_client_configured() -> None:
    """프로세스당 한 번만 Langfuse 클라이언트를 구성한다.

    v3 SDK는 클라이언트가 싱글턴이라(`get_client()`), `CallbackHandler()`를
    만들기 전에 `Langfuse(...)`를 한 번은 호출해 둬야 한다 — env var
    (`LANGFUSE_HOST` 등 SDK가 기대하는 이름)에 기대지 않고 이 저장소의
    `settings.LANGFUSE_*`를 명시적으로 넘긴다(이 저장소의 "비밀값은 settings를
    거친다" 관례, config/settings/base.py 주석 참고) — SDK가 내부적으로 어떤
    env var 이름을 쓰는지(`LANGFUSE_HOST` vs `LANGFUSE_BASE_URL` 등, 버전마다
    바뀜) 우리가 몰라도 되게.
    """
    global _configured
    if _configured:
        return

    from django.conf import settings
    from langfuse import Langfuse

    Langfuse(
        public_key=settings.LANGFUSE_PUBLIC_KEY,
        secret_key=settings.LANGFUSE_SECRET_KEY,
        host=settings.LANGFUSE_HOST,
        mask=_mask_data,
    )
    _configured = True


def get_langfuse_callback() -> Any | None:
    """키가 있으면 `CallbackHandler` 인스턴스를, 없으면 `None`을 돌려준다.

    호출 하나마다 새로 만든다 — v3 `CallbackHandler`는 생성자 인자를 안 받는
    가벼운 객체라(실제 상태는 싱글턴 클라이언트에 있다), 매번 새로 만들어도
    비용이 없고 여러 요청이 같은 인스턴스를 공유하다 상태가 섞일 걱정도 없다.
    """
    from django.conf import settings

    if not (settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY):
        return None

    try:
        _ensure_client_configured()
        from langfuse.langchain import CallbackHandler

        return CallbackHandler()
    except Exception:  # noqa: BLE001 - 트레이싱 연동 실패가 실제 응답을 막으면 안 된다
        logger.exception("Langfuse 콜백 핸들러를 만들지 못했습니다 — 이번 실행은 Langfuse 없이 진행합니다.")
        return None


def _mask_dict(data: dict) -> dict:
    """`langsmith.Client(hide_inputs=..., hide_outputs=...)`가 부르는 모양
    (`Callable[[dict], dict]`, 위치 인자 하나)에 `_mask_data`를 맞춘 얇은
    래퍼다 — 마스킹 로직 자체(이메일 정규식, 재귀 순회)는 Langfuse와
    똑같으니 새로 안 짠다."""
    return _mask_data(data=data)


def get_langsmith_callback() -> Any | None:
    """키가 있으면 마스킹이 걸린 `LangChainTracer`를, 없으면 `None`을 돌려준다.

    `langsmith.Client`를 직접 만들어 `hide_inputs`/`hide_outputs`로 이메일을
    가리고, 그 클라이언트를 쓰는 `LangChainTracer`를 콜백으로 반환한다 —
    `LANGCHAIN_TRACING_V2` env var의 자동 연결(마스킹 없음)과는 별개
    경로이지만, 이 콜백이 있으면 자동 연결 쪽이 스스로 양보한다(위 모듈
    docstring의 `_get_trace_callbacks()` 근거 참고) — 그래서 env var는 그대로
    둬도 된다.
    """
    from django.conf import settings

    if not settings.LANGCHAIN_API_KEY:
        return None

    try:
        from langchain_core.tracers import LangChainTracer
        from langsmith import Client

        client = Client(
            api_key=settings.LANGCHAIN_API_KEY,
            api_url=settings.LANGCHAIN_ENDPOINT,
            hide_inputs=_mask_dict,
            hide_outputs=_mask_dict,
        )
        return LangChainTracer(client=client, project_name=settings.LANGCHAIN_PROJECT)
    except Exception:  # noqa: BLE001 - 트레이싱 연동 실패가 실제 응답을 막으면 안 된다
        logger.exception("LangSmith 콜백 핸들러를 만들지 못했습니다 — 이번 실행은 LangSmith 없이 진행합니다.")
        return None


__all__ = ["get_langfuse_callback", "get_langsmith_callback"]
