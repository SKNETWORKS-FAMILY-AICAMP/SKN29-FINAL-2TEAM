"""`VARCHAR(5)` PK를 안전하게 발급하는 코드 생성기."""

from psycopg import sql

from .errors import IdSpaceExhausted


def next_short_code(cursor, *, table: str, column: str, prefix: str) -> str:
    """두 글자 접두사와 세 자리 번호로 다음 ID를 생성한다.

    FK를 DB에서 강제하지 않는 현재 설계에서는 애플리케이션이 ID 충돌도
    방지해야 한다. PostgreSQL advisory transaction lock으로 같은 테이블의
    동시 발급을 직렬화한다.

    **지워진 번호는 다시 주지 않는다**(2026-08-19). 살아 있는 행의 최대값만
    보면 삭제가 구멍을 내고, 다음 가입자가 그 자리를 그대로 물려받는다 —
    실제로 `UA005` 를 지운 뒤 재가입자가 같은 `UA005` 를 받았다. 그러면 감사
    기록의 「UA005 를 삭제했다」와 지금 살아 있는 `UA005` 가 **다른 사람**인데
    id 로는 구별되지 않아, 나중에 무슨 일이 있었는지 재구성할 수 없다.

    그래서 `audit_log` 의 삭제 기록까지 함께 본다. 감사 기록은 대상이
    사라져도 지우지 않기로 했으므로(`repositories.py` 의 완전 삭제 표),
    「한때 존재했다가 지워진 번호」의 정본이 된다 — 이 목적으로 표를 새로
    만들면 팀원이 각자 ALTER 를 돌려야 하는데, 이미 있는 기록으로 되는 일이다.
    """

    if len(prefix) != 2 or not prefix.isascii() or not prefix.isalpha():
        raise ValueError("prefix는 영문 두 글자여야 합니다.")

    lock_name = f"id-sequence:{table}:{column}:{prefix}"
    cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (lock_name,))

    pattern = f"^{prefix}[0-9]{{3}}$"
    query = sql.SQL(
        """
        SELECT COALESCE(MAX(CAST(SUBSTRING({column} FROM 3) AS INTEGER)), 0)
        FROM {table}
        WHERE {column} ~ %s
        """
    ).format(
        table=sql.Identifier(table),
        column=sql.Identifier(column),
    )
    cursor.execute(query, (pattern,))
    live_max = cursor.fetchone()["coalesce"]

    # 지워진 번호(위 docstring). 접두사 패턴이 이미 종류를 가르므로
    # (`UA###` 는 계정 삭제, `TE###` 는 팀 삭제) 표를 따로 지정하지 않는다.
    cursor.execute(
        """
        SELECT COALESCE(MAX(CAST(SUBSTRING(target_id FROM 3) AS INTEGER)), 0)
        FROM audit_log
        WHERE action IN ('ACCOUNT_PURGE', 'TEAM_PURGE') AND target_id ~ %s
        """,
        (pattern,),
    )
    purged_max = cursor.fetchone()["coalesce"]

    next_number = max(live_max, purged_max) + 1
    if next_number > 999:
        raise IdSpaceExhausted(f"{table}.{column}의 {prefix} 코드 공간이 소진됐습니다.")

    return f"{prefix}{next_number:03d}"
