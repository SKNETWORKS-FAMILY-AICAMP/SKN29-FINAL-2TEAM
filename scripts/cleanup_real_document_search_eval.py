"""로컬 실문서 평가용 ``eval_real`` 스키마만 명시적으로 제거한다."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from urllib.parse import urlparse

import psycopg
from psycopg import sql
from psycopg.rows import dict_row


SCHEMA = "eval_real"
CONFIRMATION = "DROP-EVAL-REAL"


def _is_local_database(url: str) -> bool:
    return urlparse(url).hostname in {"db", "localhost", "127.0.0.1"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", required=True)
    parser.add_argument(
        "--reason", required=True, choices=("expired", "evaluation-complete")
    )
    args = parser.parse_args()
    if args.confirm != CONFIRMATION:
        raise RuntimeError(f"확인 문구는 {CONFIRMATION} 이어야 합니다.")

    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url or not _is_local_database(database_url):
        raise RuntimeError("DATABASE_URL은 로컬 Docker DB여야 합니다.")

    with psycopg.connect(database_url, row_factory=dict_row, connect_timeout=8) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regnamespace(%s) AS schema_name", (SCHEMA,))
            if cursor.fetchone()["schema_name"] is None:
                print(f"로컬 {SCHEMA} 스키마가 이미 없습니다.")
                return 0

            cursor.execute(f"SELECT imported_at, expires_at FROM {SCHEMA}.dataset_meta")
            metadata = cursor.fetchone()
            if args.reason == "expired" and metadata["expires_at"] > datetime.now(timezone.utc):
                raise RuntimeError(
                    f"아직 폐기 예정 시각 전입니다: {metadata['expires_at'].isoformat()}"
                )

            cursor.execute(
                f"""
                SELECT (SELECT count(*) FROM {SCHEMA}.document) AS documents,
                       (SELECT count(*) FROM {SCHEMA}.chunk) AS chunks
                """
            )
            counts = cursor.fetchone()
            cursor.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(SCHEMA)))

    print(
        f"로컬 {SCHEMA} 제거 완료: 문서 {counts['documents']} · "
        f"청크 {counts['chunks']} · 사유 {args.reason}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
