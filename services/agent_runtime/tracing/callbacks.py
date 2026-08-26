"""Langfuse LangChain 콜백 핸들러를 만든다.

2026-08-19 착수(설계 및 구현/3_중간발표 이후/작업기록/LangSmith_LangFuse/2026-08-19_01_작업계획.md) —
이 파일은 원래 의도적으로 비어 있었다(`agent_run`/`tool_call` 적재는
`tracing/__init__.py`의 `trace_events()`가 이벤트 스트림을 감싸는 방식으로
전부 처리하고 있었어서). Langfuse는 이벤트 스트림 밖 정보(모델 원시 호출
페이로드, LangGraph node 단위 span 트리)까지 잡아야 해서 `runtime.stream(...)`
호출부의 LangChain `config["callbacks"]`에 직접 얹는 콜백 기반 연결이 필요해
졌다 — 이 파일이 그 콜백을 만드는 자리다.

**키가 없으면 조용히 꺼진다.** `WEB_SEARCH_API_KEY`와 같은 원칙 — 키가
없다고 에이전트 실행 자체가 막히면 안 된다. `get_langfuse_callback()`이
`None`을 돌려주면 호출 쪽(`executor.py`)이
그냥 콜백 목록에서 뺀다.

**마스킹(2026-08-19, 지훈 리뷰로 추가 — 2026-08-19 API 수정).** 트레이스에는
도구 호출 인자·결과가 통째로 실린다 — `jira_get_issues`/`jira_create_issues`
(services/harness/registry.py, apps/connectors/clients.py의
`_jira_issue_row()`)가 담당자 `assignee_email`을 실제 값 그대로 돌려주는 게
실사용 데이터 기준 유일하게 확인된 이메일 유출 경로다. `_ensure_client_configured()`
가 `Langfuse(...)`에 `mask=_mask_data`를 넘겨서, export 직전에 관측값
(observation의 input/output)에서 민감정보 패턴을 치환한다 — 원본
응답(사용자에게 가는 답, DB `tool_call.input_summary`)은 그대로 두고
**Langfuse로 나가는 사본만** 가린다.

**무엇을 가리는지는 이 파일이 정하지 않는다(2026-08-21).** 패턴은
`services/agent_runtime/sensitive_text.py`의 `mask_for_export()` 한 곳에서
정의한다 — 이메일뿐 아니라 credential(API 키·`password: ...` 꼴)과 주민번호·
카드번호·전화번호까지 포함한다. 처음엔 이 파일이 이메일 정규식 하나만 갖고
있었는데, ① 저장소에 이미 같은 목적의 단일 출처 모듈이 있었고(그 모듈
docstring이 "정의는 여기 하나만 둔다"고 명시), ② RAG 청크·Jira 설명·MCP
도구 결과에 섞인 전화번호나 키 문자열은 그대로 서드파티로 나갔으며,
③ 외부 반출 기준을 "비밀값이나 개인정보 원문 노출"로 잡으면(트레이스는
서드파티 서버로 원문이 나가는 경로다) 이메일만 가리는 구현은 기준에 못 미쳤다.

처음엔 `mask_otel_spans=_mask_otel_spans`(span 속성을 순회하며 패치하는
모양)로 짰는데, 당시 설치된 v3 SDK에는 그런 파라미터가 없었다
— `Langfuse.__init__()`가 그 키워드를 그대로 거부해 `TypeError`를 던진다.
`get_langfuse_callback()`의 넓은 `except Exception`이 이를 삼켜서, 실 키를
넣는 순간(작업계획 §3-5) Langfuse 연동 전체가 **아무 로그도 없이 조용히
안 붙는** 상태가 될 뻔했다. 실제 파라미터 이름은 `mask`이고, 모양도
`langfuse.types.MaskFunction`(`data` 키워드 하나를 받아 마스킹한 값을
돌려주는 함수)로 완전히 다르다 — 아래 `_mask_data()`가 그 모양에 맞춘다.

"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from services.agent_runtime.sensitive_text import mask_for_export

logger = logging.getLogger(__name__)

_configured = False
_client_lock = threading.Lock()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class LangfuseTraceHandle:
    """한 Agent 실행과 HITL 재개가 공유하는 Langfuse 상관관계."""

    callback: Any
    trace_id: str
    root_observation_id: str
    root_observation: Any | None = None

    def finish(self) -> None:
        if self.root_observation is None:
            return
        try:
            self.root_observation.end()
        except Exception:  # noqa: BLE001 - 관측 종료 실패가 Agent 실행을 막으면 안 된다
            logger.exception("Langfuse Agent root observation을 종료하지 못했습니다.")


def _mask_data(*, data: Any, **_kwargs: Any) -> Any:
    """export 직전 관측값 하나에서 민감정보를 지운다.

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

    **가리는 범위(2026-08-21 확대).** 처음엔 이 파일이 자체 이메일 정규식
    하나만 갖고 있었는데, 저장소에는 이미 "무엇이 민감정보인가"를 한 곳에서
    정의하는 `services/agent_runtime/sensitive_text.py`가 있고 그 모듈
    docstring이 "패턴 정의는 여기 하나만 둔다"고 못박아 뒀다 — 정의가 두
    벌이 되면 한쪽만 고쳐진다. 그래서 이 파일의 정규식을 지우고 그 모듈의
    `mask_for_export()`(이메일 + credential + 주민번호·카드·전화 패턴)를
    부른다. 이메일만 가리던 이전 구현은 RAG 청크나 Jira 설명에 섞인 전화번호·
    API 키가 그대로 서드파티로 나갔고, 외부 반출 기준("비밀값이나 개인정보
    원문 노출")보다 좁았다.
    """
    if isinstance(data, str):
        return mask_for_export(data)
    if isinstance(data, dict):
        return {key: _mask_data(data=value) for key, value in data.items()}
    if isinstance(data, (list, tuple)):
        masked = [_mask_data(data=item) for item in data]
        # `type(data)(masked)`가 아니라 `tuple(...)`이다 — namedtuple 생성자는
        # 이터러블 하나가 아니라 필드별 위치 인자를 받아 `TypeError`가 난다.
        # 마스킹 함수가 던지면 Langfuse는 관측치를 통째로
        # `"<fully masked due to failed mask function>"`으로 바꾸므로, 안 던지는
        # 게 우선이라 모양 보존을 포기한다.
        return tuple(masked) if isinstance(data, tuple) else masked
    if not isinstance(data, type):
        model_dump = getattr(data, "model_dump", None)
        if callable(model_dump):
            try:
                return _mask_data(data=model_dump())
            except Exception:  # noqa: BLE001 - 마스킹 함수는 무슨 값이 와도 던지면 안 된다
                # `model_dump`가 미바인드 메서드일 때(도구 스키마의 `args_schema`
                # 처럼 pydantic 모델 "클래스" 자체가 값으로 오는 경우) `self`가
                # 없어 `TypeError`가 난다. 위 `isinstance(data, type)` 체크가 그
                # 흔한 경우는 거르지만, 직렬화 못 하는 필드가 섞인 모델 등 다른
                # 예외도 가능하다. 여기서 던지면 관측치가 통째로 날아가거나
                # 트레이스 전송이 깨지므로, **원본을 그대로 내보내지 않도록**
                # 문자열로 눌러서 다시 마스킹한다.
                try:
                    return mask_for_export(repr(data))
                except Exception:  # noqa: BLE001 - 여기서도 던지면 안 된다
                    return "<unmaskable>"
    return data


def _ensure_client_configured() -> None:
    """프로세스당 한 번만 Langfuse 클라이언트를 구성한다.

    SDK 클라이언트가 싱글턴이라(`get_client()`), `CallbackHandler()`를
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

    # 락으로 감싼다 — 서버는 요청을 스레드로 처리하고, 첫 두 요청이 동시에
    # 들어오면 `Langfuse(...)`(내부에서 OTel provider와 전송 스레드를 세운다)가
    # 두 번 실행될 수 있다.
    with _client_lock:
        if _configured:
            return
        Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_HOST,
            mask=_mask_data,
        )
        _configured = True


def get_langfuse_callback(*, trace_context: dict[str, str] | None = None) -> Any | None:
    """키가 있으면 `CallbackHandler` 인스턴스를, 없으면 `None`을 돌려준다.

    호출 하나마다 새로 만든다. v4 `CallbackHandler`는 `trace_context`를 받아
    기존 trace/root 아래에 연결할 수 있다. handler 인스턴스 자체는 재사용하지
    않아 동시 요청 상태가 섞이지 않게 한다.
    """
    from django.conf import settings

    if not (settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY):
        return None

    try:
        _ensure_client_configured()
        from langfuse.langchain import CallbackHandler

        return (
            CallbackHandler(trace_context=trace_context)
            if trace_context is not None
            else CallbackHandler()
        )
    except Exception:  # noqa: BLE001 - 트레이싱 연동 실패가 실제 응답을 막으면 안 된다
        logger.exception("Langfuse 콜백 핸들러를 만들지 못했습니다 — 이번 실행은 Langfuse 없이 진행합니다.")
        return None


def get_langfuse_trace(
    *,
    run_id: str,
    metadata: dict[str, Any],
    resume_state: dict[str, Any] | None = None,
) -> LangfuseTraceHandle | None:
    """Agent root를 만들거나 HITL 카드에 저장된 trace/root를 재사용한다.

    `CallbackHandler` 인스턴스 캐시는 쓰지 않는다. Langfuse v4의 내장 resume
    저장소가 handler 인스턴스 소유라 웹 요청을 건너 보존되지 않기 때문이다.
    최초 실행에서 Langfuse가 실제 root observation과 trace ID를 발급하고,
    resume에서는 그 두 ID를 명시적으로 전달해 같은 tree 아래에 붙인다.
    """

    from django.conf import settings

    if not (settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY):
        return None

    root = None
    try:
        _ensure_client_configured()
        from langfuse import get_client

        stored_trace_id = str((resume_state or {}).get("langfuse_trace_id") or "")
        stored_root_id = str(
            (resume_state or {}).get("langfuse_root_observation_id") or ""
        )
        if stored_trace_id and stored_root_id:
            trace_id = stored_trace_id
            root_id = stored_root_id
            interrupted_at = str(
                (resume_state or {}).get("langfuse_interrupted_at") or ""
            )
            if interrupted_at:
                try:
                    started = datetime.fromisoformat(
                        interrupted_at.replace("Z", "+00:00")
                    )
                    resumed = _utc_now()
                    wait_ms = max(0, round((resumed - started).total_seconds() * 1000))
                    wait = get_client().start_observation(
                        name="hitl-wait",
                        as_type="span",
                        trace_context={"trace_id": trace_id, "parent_span_id": root_id},
                        metadata={
                            "kind": "human_approval_wait",
                            "wait_started_at": interrupted_at,
                            "wait_resumed_at": resumed.isoformat().replace("+00:00", "Z"),
                            "wait_duration_ms": wait_ms,
                        },
                    )
                    wait.end()
                except Exception:  # noqa: BLE001 - 대기 계측 실패가 resume을 막으면 안 된다
                    logger.exception("Langfuse HITL 대기 observation을 기록하지 못했습니다.")
        else:
            root = get_client().start_observation(
                name="agent-run",
                as_type="agent",
                metadata={"run_id": run_id, **metadata},
            )
            trace_id = str(root.trace_id)
            root_id = str(root.id)

        callback = get_langfuse_callback(
            trace_context={"trace_id": trace_id, "parent_span_id": root_id}
        )
        if callback is None:
            if root is not None:
                root.end()
            return None
        return LangfuseTraceHandle(
            callback=callback,
            trace_id=trace_id,
            root_observation_id=root_id,
            root_observation=root,
        )
    except Exception:  # noqa: BLE001 - 관측 연동 실패가 실제 실행을 막으면 안 된다
        if root is not None:
            try:
                root.end()
            except Exception:  # noqa: BLE001
                pass
        logger.exception("Langfuse Agent trace를 만들지 못했습니다 — 이번 실행은 Langfuse 없이 진행합니다.")
        return None


def record_langfuse_evaluation_result(
    *,
    trace_id: str | None,
    case_id: str,
    status: str,
    failed_assertions: list[str],
    environment: str | None,
) -> bool:
    """결정론적 평가 결과를 해당 trace의 score로 연결한다."""

    from django.conf import settings

    if not trace_id or not (
        settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY
    ):
        return False
    try:
        _ensure_client_configured()
        from langfuse import get_client

        get_client().create_score(
            trace_id=trace_id,
            name="deterministic-evaluation-status",
            value=status,
            data_type="CATEGORICAL",
            comment=", ".join(failed_assertions) if failed_assertions else None,
            metadata={
                "case_id": case_id,
                "evaluator": "deterministic_code_assertions",
            },
            environment=environment,
        )
        if failed_assertions:
            get_client().create_score(
                trace_id=trace_id,
                name="deterministic-evaluation-failure",
                value=", ".join(failed_assertions),
                data_type="TEXT",
                environment=environment,
            )
        return True
    except Exception:  # noqa: BLE001 - 평가 score 실패가 로컬·DB 저장을 막으면 안 된다
        logger.exception("Langfuse 평가 score를 기록하지 못했습니다.")
        return False


__all__ = [
    "LangfuseTraceHandle",
    "get_langfuse_callback",
    "get_langfuse_trace",
    "record_langfuse_evaluation_result",
]
