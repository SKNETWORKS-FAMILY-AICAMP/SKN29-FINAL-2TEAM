"""`VARCHAR(5)` PK를 안전하게 발급하는 코드 생성기."""

from psycopg import sql

from .errors import IdSpaceExhausted


def next_short_code(cursor, *, table: str, column: str, prefix: str) -> str:
    """두 글자 접두사와 세 자리 번호로 다음 ID를 생성한다.

    FK를 DB에서 강제하지 않는 현재 설계에서는 애플리케이션이 ID 충돌도
    방지해야 한다. PostgreSQL advisory transaction lock으로 같은 테이블의
    동시 발급을 직렬화한다.
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
    next_number = cursor.fetchone()["coalesce"] + 1
    if next_number > 999:
        raise IdSpaceExhausted(f"{table}.{column}의 {prefix} 코드 공간이 소진됐습니다.")

    return f"{prefix}{next_number:03d}"
