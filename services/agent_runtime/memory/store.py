"""장기 메모리를 물리적으로 담는 LangGraph `PostgresStore` — 프로세스 하나에 한 번만 연다.

**이 모듈은 이 패키지(`services.agent_runtime`)의 "호출마다 새로 조립한다"는
원칙(`bootstrap.py` 모듈 docstring)의 유일한 예외다.** `PostgresStore.from_conn_string()`은
컨텍스트 매니저라, 원칙대로 매 호출마다 새로 열고 닫으려면 연결 풀을 실행마다
새로 만들고 버리는 셈이 된다 — 게다가 정석대로 하려면 그 `with` 블록 안에
그래프 실행 전체(스트리밍 제너레이터까지)를 넣어야 하는데, 지금 `executor.py`의
구조를 그렇게까지 바꾸는 건 이번 1차 구현 범위 밖이라고 판단했다. 그래서 대신
프로세스 시작 뒤 첫 호출에서 한 번 열어 계속 재사용한다 — gunicorn 등 prefork
워커 모델과도 맞다(워커마다 자기 연결 풀을 하나씩 갖는 게 정상 동작이다).

멀티 프로세스 배포에서 프로세스 종료 시 이 연결이 깔끔히 안 닫힐 수 있다(atexit
훅 없음) — Postgres 쪽에서 유휴 커넥션은 정리되므로 치명적이진 않지만, 운영
전환 전에 정식으로 점검할 것.

**락으로 감싼 이유 (2026-08-22)** — 설정 > 스킬 화면이 개인/팀 스킬 목록을
`Promise.all`로 **동시에** 두 번 요청한다(`SkillsTab.tsx`의 `load()`). 두
요청이 이 프로세스에서 처음으로 `get_memory_store()`를 부르는 순간이 겹치면,
`if _store is not None` 검사를 둘 다 통과한 뒤 `PostgresStore.from_conn_string()`
과 `.setup()`을 동시에 실행하게 된다 — Postgres 커넥션을 두 번 열고
`.setup()`(멱등이지만 DDL을 두 번 겹쳐 실행)까지 경합하면서 500으로 죽는
사례를 봤다. 잠금을 아주 짧게만 쥔다 — 최초 연결 뒤로는 `_store is not None`
검사에서 즉시 반환되어 락을 아예 안 거친다.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from langgraph.store.postgres import PostgresStore

_store: Any = None
#: `PostgresStore.from_conn_string()`가 돌려주는 컨텍스트 매니저. `__exit__`를
#: 부를 일이 생기면(프로세스 종료 훅 등) 여기서 꺼내 쓴다 — 지금은 아무도
#: 안 부른다(위 docstring의 "치명적이진 않지만" 부분).
_store_cm: Any = None
#: 최초 연결 경합을 막는 락. 연결된 뒤에는 안 거친다(아래 이중 검사).
_store_lock = threading.Lock()


def get_memory_store() -> "PostgresStore":
    """프로세스 전역 `PostgresStore`. 최초 호출에서만 실제로 연결하고 스키마를 만든다."""
    global _store, _store_cm
    if _store is not None:
        return _store

    with _store_lock:
        # 락을 기다리는 동안 다른 스레드가 이미 만들었을 수 있다 — 이중 검사.
        if _store is not None:
            return _store

        # 지연 import — langgraph.store.postgres는 psycopg 커넥션 풀·langgraph
        # 전체를 끌고 들어온다. 이 패키지의 다른 모듈들과 같은 이유로(compat/,
        # tools/loader.py 등) 실제로 메모리를 쓰는 요청이 올 때만 부른다.
        from django.conf import settings
        from langgraph.store.postgres import PostgresStore

        _store_cm = PostgresStore.from_conn_string(settings.RAW_DATABASE_URL)
        _store = _store_cm.__enter__()
        # 멱등 — langgraph가 자기 테이블(store, store_migrations 등)을 만든다.
        # 이미 있으면 아무 것도 안 한다. `DB/schema.sql`이 관리하는 이 저장소의
        # 다른 테이블과 달리, 이 테이블들은 langgraph 라이브러리가 자체 관리한다.
        _store.setup()
        return _store


def get_runtime_store() -> "PostgresStore":
    """Memory와 Skill이 함께 쓰는 PostgreSQL 기반 LangGraph Store.

    기존 함수명은 최초 사용처가 Memory였던 역사 때문에 남아 있다. Skill 코드가
    ``get_memory_store``라는 이름에 의존하면 로컬/메모리 전용 저장소로 오해하기
    쉬우므로, 런타임 공용 저장소라는 이름을 공개한다. 구현은 기존 싱글턴을
    그대로 호출해 연결 풀과 ``store`` 테이블도 하나만 사용한다.
    """

    return get_memory_store()


__all__ = ["get_memory_store", "get_runtime_store"]
