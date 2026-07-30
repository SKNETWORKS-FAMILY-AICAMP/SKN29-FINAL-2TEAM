"""`audit_log` 기록 공용 헬퍼.

운영자 콘솔의 모든 조치(로그인, 계정 잠금, 연결 해제, 정책 변경 등)는 이 모듈을
통해서만 `audit_log`에 쓴다 — 조치 종류마다 INSERT문을 새로 만들지 않기 위함.
"""

from typing import Any

from psycopg.types.json import Jsonb

from .codes import next_short_code
from .connection import database_connection


def log_with(
    cursor,
    *,
    actor_account_id: str,
    action: str,
    proj_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    """다른 트랜잭션에 이어 붙일 때 쓴다(예: 계정 잠금 처리와 같은 커밋 단위)."""

    audit_id = next_short_code(cursor, table="audit_log", column="audit_id", prefix="AL")
    cursor.execute(
        """
        INSERT INTO audit_log
            (audit_id, proj_id, actor_account_id, action, target_type, target_id, payload)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (audit_id, proj_id, actor_account_id, action, target_type, target_id, Jsonb(payload or {})),
    )


def log(**kwargs: Any) -> None:
    """단독 호출용. 자체 커넥션을 열고 바로 commit한다."""

    with database_connection() as connection:
        with connection.cursor() as cursor:
            log_with(cursor, **kwargs)
