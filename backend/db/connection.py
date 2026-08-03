"""psycopg 기반 PostgreSQL 연결 관리.

테이블 생성과 변경은 `DB/schema.sql`이 담당한다. 이 모듈은 Django ORM이나
Migration을 사용하지 않고 이미 존재하는 테이블에 직접 SQL을 실행한다.
"""

from contextlib import contextmanager
from typing import Iterator

import psycopg
from django.conf import settings
from psycopg import Connection
from psycopg.rows import dict_row


@contextmanager
def database_connection() -> Iterator[Connection]:
    """요청 단위 연결을 열고 성공 시 commit, 예외 시 rollback한다."""

    with psycopg.connect(settings.RAW_DATABASE_URL, row_factory=dict_row) as connection:
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
