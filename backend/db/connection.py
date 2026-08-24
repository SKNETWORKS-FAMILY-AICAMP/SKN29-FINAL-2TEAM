"""psycopg 기반 PostgreSQL 연결 관리.

테이블 생성과 변경은 `DB/schema.sql`이 담당한다. 이 모듈은 Django ORM이나
Migration을 사용하지 않고 이미 존재하는 테이블에 직접 SQL을 실행한다.

**연결을 매번 새로 열지 않는다**(2026-08-24). 전에는 `database_connection()`이
호출될 때마다 `psycopg.connect()`를 했다. 저장소에 그 자리가 209곳이고 메서드
하나가 한 번씩 쓰므로 **메서드 호출 = 새 연결**이었다. 실측(로컬 컨테이너):

    연결만 열고 닫기      24.5 ms
    열린 연결에서 질의 1회  0.5 ms

즉 **일하는 시간의 8할이 핸드셰이크**였다(화면 하나 그리는 저장소 4번 호출:
81ms 중 67ms). AWS RDS 는 네트워크 + TLS 라 더 크다.

연결 하나는 Postgres 프로세스 하나이기도 해서, 사용자가 몰리면 `max_connections`
에 부딪힌다 — 백그라운드 스레드(문서 수집·증분 동기화)도 각자 열고 있었다.
"""

import atexit
from contextlib import contextmanager
import threading
from typing import Iterator

from django.conf import settings
import psycopg
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

#: 프로세스가 유지하는 연결 수.
#:
#: **워커 프로세스마다 이만큼 잡는다.** gunicorn 워커가 4개면 최대 32개이므로,
#: RDS 인스턴스의 `max_connections` 를 넘지 않는지 확인하고 늘려야 한다.
#: 질의 하나가 1ms 아래라 8개면 사실상 대기가 생기지 않는다.
_POOL_MIN_SIZE = 1
_POOL_MAX_SIZE = 8

#: 빈 연결을 기다리는 상한(초).
#:
#: 짧게 잡는 것이 맞다. 질의가 빨라서 정상 상황에서는 대기가 없고, **오래
#: 기다리는 경우는 사실상 DB 가 안 붙는 것**이다 — 그때는 30초(기본값) 붙들고
#: 있다가 실패하는 것보다 빨리 실패하는 쪽이 낫다(헬스체크가 그 자리다).
_POOL_TIMEOUT_SECONDS = 10

_pool: ConnectionPool | None = None
_pool_lock = threading.Lock()


def _get_pool() -> ConnectionPool:
    """프로세스 전역 풀. **첫 호출에서만** 만든다.

    import 시점에 만들지 않는 이유가 둘이다.

    1. 이 모듈은 Django 밖(스크립트·마이그레이션 확인)에서도 import 된다.
       import 만으로 DB 를 요구하면 그쪽이 못 쓴다.
    2. gunicorn 이 `preload_app` 으로 뜨면 **fork 전에 만든 연결이 자식에서
       깨진다.** 첫 질의 때 만들면 이미 fork 된 뒤라 그 문제가 없다.

    `services/agent_runtime/memory/store.py` 의 `get_memory_store()` 와 같은
    모양이다 — 프로세스 전역 · 지연 생성.
    """

    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        # 잠금을 기다리는 동안 다른 스레드가 이미 만들었을 수 있다.
        if _pool is None:
            _pool = ConnectionPool(
                settings.RAW_DATABASE_URL,
                min_size=_POOL_MIN_SIZE,
                max_size=_POOL_MAX_SIZE,
                # 호출부는 전부 `row["컬럼"]` 으로 읽는다. 풀이 만드는 연결에도
                # 그대로 걸어야 한다 — 빠뜨리면 209곳이 튜플을 받는다.
                kwargs={
                    "row_factory": dict_row,
                    # `pg_stat_activity` 에서 우리 연결을 알아보게 한다. 연결이
                    # 몇 개나 열려 있는지 물어볼 일이 생기는데(풀 크기 조정,
                    # `max_connections` 점검), 이름이 없으면 세는 방법이 없다.
                    "application_name": "halil",
                },
                timeout=_POOL_TIMEOUT_SECONDS,
                # **빌려주기 전에 살아 있는지 본다.** 유휴 연결은 RDS·NAT·방화벽이
                # 조용히 끊는다. 확인 없이 내주면 그 사실이 엉뚱한 질의에서
                # 처음 드러난다.
                check=ConnectionPool.check_connection,
                # 연결이 영원히 살지 않게 한다(기본값 그대로 명시).
                max_lifetime=3600.0,
                max_idle=600.0,
                # 배경 스레드로 연결한다 — 생성자가 DB 를 기다리지 않으므로
                # DB 가 죽어 있어도 프로세스는 뜬다.
                open=True,
                name="halil",
            )
            # 풀은 배경 스레드(연결 워커·스케줄러)를 띄운다. 안 닫으면 프로세스가
            # 끝날 때 「couldn't stop thread ... within 5.0 seconds」가 줄줄이
            # 찍힌다 — 서버는 오래 살아 티가 안 나지만 관리 명령·스크립트에서는
            # 매번 보인다.
            atexit.register(_pool.close)
    return _pool


@contextmanager
def database_connection() -> Iterator[Connection]:
    """풀에서 연결을 빌리고, 성공 시 commit·예외 시 rollback 한 뒤 **반납**한다.

    호출부는 한 줄도 바뀌지 않는다. `pool.connection()` 이 `psycopg.connect()` 의
    컨텍스트 매니저와 같은 트랜잭션 규칙을 쓰고, 다른 점은 블록을 나갈 때 연결을
    **닫는 대신 돌려놓는다**는 것뿐이다.

    예외 형도 그대로다 — 풀이 던지는 `PoolTimeout`·`TooManyRequests` 는 둘 다
    `psycopg.OperationalError` 하위라, 기존 `except psycopg.Error` 가 그대로
    받는다.
    """

    with _get_pool().connection() as connection:
        yield connection


def database_status() -> dict[str, str]:
    """DB 연결과 현재 물리 스키마 존재 여부를 확인한다."""

    try:
        with database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        to_regclass('public.proj') IS NOT NULL AS schema_ready,
                        -- HR 8개 테이블은 2026-07-31에 mock_hr 스키마로 옮겼다.
                        -- 여기가 public을 계속 보고 있어서, 사람이 57명 들어 있어도
                        -- 항상 missing으로 보고했다(2026-08-03 수정).
                        to_regclass('mock_hr.person') IS NOT NULL AS people_ready,
                        to_regclass('public.vec_idx') IS NOT NULL AS vector_ready
                    """
                )
                row = cursor.fetchone()
    except psycopg.Error as exc:
        return {"status": "unavailable", "detail": exc.__class__.__name__}

    if not row["schema_ready"]:
        return {"status": "not_initialized"}

    return {
        "status": "ok",
        "people": "ready" if row["people_ready"] else "missing",
        "vector": "ready" if row["vector_ready"] else "missing",
    }
