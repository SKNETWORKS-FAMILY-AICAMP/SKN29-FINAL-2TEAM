"""2026-08-13_agent_versioning.sql을 실행하는 1회용 스크립트.

`.env`를 셸에서 `source`하면 안 된다 — DEFAULT_FROM_EMAIL 값에 `<`가 들어 있어
bash가 리다이렉트로 오해한다(2026-08-13 확인). 여기서는 `.env`를 셸이 아니라
파이썬으로 직접 읽어서 그 문제를 피한다. `psql` 클라이언트가 없어도 되도록
psycopg(프로젝트 의존성, venv에 이미 있음)로 직접 실행한다.

사용:
    python DB/migrations/_apply_2026-08-13.py

실행 후 지워도 된다 — 마이그레이션 파일 자체(2026-08-13_agent_versioning.sql)가
정본이고 이건 그걸 실행하는 도구일 뿐이다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import psycopg

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env"
MIGRATION_FILE = Path(__file__).with_name("2026-08-13_agent_versioning.sql")


def _read_database_url() -> str:
    with ENV_FILE.open(encoding="utf-8") as f:
        for line in f:
            if line.startswith("DATABASE_URL="):
                return line.strip().split("=", 1)[1].strip("\"'")
    raise SystemExit(f"{ENV_FILE}에 DATABASE_URL이 없습니다.")


def _split_statements(sql: str) -> list[str]:
    # 줄 전체가 주석(--)인 줄만 제거한다. 세미콜론은 이 파일 안에서
    # 문자열 리터럴 안에 나오지 않으므로 단순 split으로 충분하다.
    without_comments = re.sub(r"^--.*$", "", sql, flags=re.MULTILINE)
    statements = [s.strip() for s in without_comments.split(";")]
    # BEGIN/COMMIT은 뺀다 — psycopg 연결은 기본이 autocommit=False라
    # `with conn:` 블록 자체가 이미 트랜잭션이다. 파일 안의 BEGIN/COMMIT까지
    # 그대로 보내면 이중으로 트랜잭션을 여닫으려 해서 불필요하다.
    return [s for s in statements if s and s.upper() not in ("BEGIN", "COMMIT")]


def main() -> None:
    # 인자로 URL을 주면 그걸 쓴다(.env는 안 건드린다 — 그건 팀 공용 RDS를
    # 가리키는 기본값이라, 로컬 docker DB로 잠깐 돌리고 싶을 때 셸에서 임시로
    # 넘기는 용도다). 예:
    #   python DB/migrations/_apply_2026-08-13.py \
    #     "postgres://project_copilot:project_copilot@localhost:5432/project_copilot"
    url = sys.argv[1] if len(sys.argv) > 1 else _read_database_url()
    sql = MIGRATION_FILE.read_text(encoding="utf-8")
    statements = _split_statements(sql)

    print(f"대상 DB: {url.split('@')[-1] if '@' in url else url}")
    print(f"실행할 문장 수: {len(statements)}")

    with psycopg.connect(url) as connection:
        with connection.cursor() as cursor:
            for statement in statements:
                print(f"- {statement.splitlines()[0][:70]}...")
                cursor.execute(statement)
        connection.commit()
    print("마이그레이션 커밋 완료.")

    # 확인 쿼리 (마이그레이션 파일 158줄 이후와 동일)
    with psycopg.connect(url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT table_name FROM information_schema.tables
                 WHERE table_schema = 'public'
                   AND table_name IN ('agents','agent_versions','agent_version_tools',
                                       'agent_version_subagents')
                 ORDER BY table_name
                """
            )
            new_tables = [row[0] for row in cursor.fetchall()]

            cursor.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'chat_session' AND column_name = 'agent_version_id'"
            )
            chat_session_col = cursor.fetchone()

            cursor.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'agent_run' AND column_name = 'agent_version_id'"
            )
            agent_run_col = cursor.fetchone()

            cursor.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'"
            )
            total_tables = cursor.fetchone()[0]

    print()
    print("=== 확인 ===")
    print(f"새 테이블 4개 확인: {new_tables} (4개면 정상)")
    print(f"chat_session.agent_version_id: {'있음' if chat_session_col else '없음 (문제)'}")
    print(f"agent_run.agent_version_id: {'있음' if agent_run_col else '없음 (문제)'}")
    print(f"전체 테이블 수: {total_tables} (53이면 정상, 이미 실행한 적 있으면 그대로일 수 있음)")


if __name__ == "__main__":
    main()
