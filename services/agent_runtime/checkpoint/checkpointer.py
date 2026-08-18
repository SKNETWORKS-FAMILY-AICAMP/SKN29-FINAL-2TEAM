"""LangGraph Checkpointer를 물리적으로 담는 `PostgresSaver` — 프로세스 하나에 한 번만 연다.

`services/agent_runtime/memory/store.py`(장기 메모리 `PostgresStore`)와 이유가 완전히 같아서
같은 패턴을 그대로 따른다. 이 모듈도 이 패키지의 "호출마다 새로 조립한다"는 원칙
(`bootstrap.py` 모듈 docstring)의 예외다 — `PostgresSaver.from_conn_string()`도
컨텍스트 매니저라, 원칙대로 매 호출마다 새로 열고 닫으면 연결 풀을 매번 새로 만들고
버리는 셈이 된다. 그래서 `memory/store.py`와 똑같이 프로세스 시작 뒤 첫 호출에서 한 번
열어 계속 재사용한다(gunicorn 등 prefork 워커 모델과도 맞다).

`langgraph-checkpoint-postgres`는 이미 `requirements/base.txt`에 있다(2026-08-15, 장기
메모리 착수와 함께 추가 — `PostgresStore`와 `PostgresSaver`가 같은 패키지에 들어 있어서
새 의존성 추가 없이 그대로 재사용한다, 실측: `requirements/base.txt` 42번째 줄 근처
주석 참고). 커넥션 문자열도 `memory/store.py`와 동일하게 `settings.RAW_DATABASE_URL`을
그대로 쓴다 — 이미 떠 있는 Postgres를 새 용도(체크포인트 저장)로 한 번 더 여는 것뿐,
새 인프라가 아니다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from langgraph.checkpoint.postgres import PostgresSaver

_checkpointer: Any = None
#: `PostgresSaver.from_conn_string()`가 돌려주는 컨텍스트 매니저 자체.
#: `memory/store.py`의 `_store_cm`과 같은 이유로 보관한다(`__exit__`를 나중에
#: 부를 일이 생기면 여기서 꺼내 쓴다 — 지금은 아무도 안 부른다).
_checkpointer_cm: Any = None


def get_checkpointer() -> "PostgresSaver":
    """프로세스 전역 `PostgresSaver`. 최초 호출에서만 실제로 연결하고 스키마를 만든다."""
    global _checkpointer, _checkpointer_cm
    if _checkpointer is not None:
        return _checkpointer

    # 지연 import — langgraph.checkpoint.postgres는 psycopg 커넥션 풀·langgraph
    # 전체를 끌고 들어온다. memory/store.py와 같은 이유로 실제로 체크포인트를
    # 쓰는 요청이 올 때만 부른다.
    from django.conf import settings
    from langgraph.checkpoint.postgres import PostgresSaver

    _checkpointer_cm = PostgresSaver.from_conn_string(settings.RAW_DATABASE_URL)
    _checkpointer = _checkpointer_cm.__enter__()
    # 멱등 — langgraph가 자기 테이블(checkpoints, checkpoint_blobs,
    # checkpoint_writes 등)을 만든다. 이미 있으면 아무 것도 안 한다.
    # `DB/schema.sql`이 관리하는 이 저장소의 다른 테이블과 달리, 이 테이블들은
    # langgraph 라이브러리가 자체 관리한다(memory/store.py의 store 테이블과 동일).
    _checkpointer.setup()
    return _checkpointer


__all__ = ["get_checkpointer"]
