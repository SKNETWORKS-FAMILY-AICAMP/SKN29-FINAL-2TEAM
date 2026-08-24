"""마이그레이션을 **확인**하고 **적용**한다.

이 저장소는 마이그레이션 도구를 쓰지 않는다(`DATABASES = {}`). 그래서 「코드는
새 스키마 전제, DB 는 옛 스키마」가 조용히 만들어지고, 실제로 2026-08-18 오전에
그 상태로 배포돼 채팅이 통째로 막혔다. **테스트 700건이 전부 통과해도 못 잡는다**
— 테스트가 실제 RDS 를 쓰지 않기 때문이다.

그래서 배포 전에 한 줄로 물어볼 수 있게 해 둔다.

    python DB/migrations/_apply.py --check            # 무엇이 빠졌나 (읽기만)
    python DB/migrations/_apply.py <파일.sql> ...      # 적용

대상은 **`--url` → 환경변수 `DATABASE_URL` → `.env`** 순으로 정하고, **어디서
읽었는지를 함께 찍는다.** 컨테이너 안에는 `.env` 파일이 없고 compose 가 값을
환경변수로 넣어 주므로, 공유 RDS 에 적용하는 자리에서는 환경변수 갈래가 쓰인다.

**`.env` 를 셸에서 `source` 하지 않는다.** `DEFAULT_FROM_EMAIL` 값에 `<` 가 들어
있어 bash 가 리다이렉트로 오해한다(2026-08-13 확인). 여기서는 파이썬이 직접 읽어
그 문제를 피하고, `psql` 클라이언트가 없어도 되도록 psycopg 로 실행한다.

    # 서버(EC2)에서 공유 RDS 에 적용
    cd ~/SKN29-Final-2Team
    docker compose -f infra/docker/docker-compose.aws.yml exec -T web \
      python DB/migrations/_apply.py --check

**적용은 멱등이다** — 마이그레이션 파일들이 `IF NOT EXISTS` 로 쓰여 있다. 예외는
`doc` 의 CHECK 둘로, `DROP ... IF EXISTS` 뒤에 다시 걸므로 여러 번 돌려도 되지만
**데이터가 조건을 어기면 거기서 실패한다**(`DB_시작_가이드.md` §4.3 참고).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import psycopg

# Windows 콘솔은 기본이 cp949 라 한글이 깨져 나간다. 출력은 항상 UTF-8 로 낸다.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env"

#: 배포가 전제하는 스키마. **새 마이그레이션을 더하면 여기에 한 줄 추가한다** —
#: 안 그러면 `--check` 가 「다 있다」고 거짓말을 한다.
#: (테이블, 컬럼) 에서 컬럼이 None 이면 테이블 자체의 존재만 본다.
EXPECTED: list[tuple[str, str | None, str]] = [
    ("agents", None, "2026-08-13 에이전트 버전 스키마"),
    ("agent_versions", None, "2026-08-13"),
    ("agent_version_tools", None, "2026-08-13"),
    ("agent_version_subagents", None, "2026-08-13"),
    ("agent_run", "runtime_profile_version", "2026-08-14 실행 로그에 코드 버전"),
    ("agents", "is_default_chat", "2026-08-15 기본 챗 에이전트"),
    ("doc", "owner_account_id", "2026-08-18 내 파일(M④)"),
    ("doc", "search_enabled", "2026-08-18 내 파일 toggle"),
    ("doc", "shared_team_id", "2026-08-18 개인 문서 팀 공유"),
    ("doc", "index_status", "2026-08-18 색인 상태"),
    ("doc", "index_detail", "2026-08-24 색인 실패 사유"),
    ("connector_conn", "sync_cursor", "2026-08-24 증분 동기화 커서"),
    ("agent_favorites", None, "2026-08-18 즐겨찾기"),
    ("chat_session", "tool_refs_override", "2026-08-18 대화별 도구 교체"),
    # `doc_meta` 는 2026-08-24 에 폐기했다(`2026-08-24_drop_doc_meta.sql`).
    # 있으면 있는 대로 두고 없으면 없는 대로 맞는 상태라 여기서 묻지 않는다 —
    # 물으면 이미 지운 DB 가 「빠졌다」로 보고된다.
    ("agent_run", "resolved_provider", "2026-08-19 실행 스냅샷 — 어느 provider 로 돌았나"),
    ("agent_run", "resolved_endpoint_hash", "2026-08-19 실행 스냅샷 — 엔드포인트 해시"),
    # 2026-08-20 정정 — 이 세 줄은 「기존 tool_call 표에 컬럼 3개를 더한다」는
    # 초기 설계를 그대로 옮긴 것이었는데, 실제로 나간 마이그레이션
    # (2026-08-19_tool_call_idempotency.sql)은 그 설계를 버리고 **전용 표
    # tool_call_idempotency**를 새로 만드는 쪽으로 바뀌었다(그 파일 자체의
    # 주석: "기존 tool_call 테이블을 그대로 확장하지 않는다" — 쓰는 시점이
    # tool_call의 관측용 생명주기와 달라서다). `DB/schema.sql`의 `tool_call`
    # 정의(실측)엔 애초에 `session_id`/`langchain_tool_call_id`/`result_text`
    # 컬럼이 없다 — 이 체크는 실제로 배포된 스키마가 아니라 버려진 초기 설계를
    # 보고 있었다. 실사용 중 `tool_call_idempotency`가 실제로는 없는 DB에서도
    # `--check`가 "전부 있다"고 답한 사례로 발견됐다(`UndefinedTable`로
    # 실행이 깨진 뒤에야 드러남) — 코드가 실제로 쓰는 표 이름으로 바꾼다.
    ("tool_call_idempotency", None, "2026-08-19 외부 쓰기 도구 재실행 방지 — 전용 표"),
    ("guardrail_event", None, "2026-08-20 가드레일 발동 기록"),
    ("guardrail_provider", None, "2026-08-20 외부 가드레일 공급자 등록"),
    ("guardrail_provider", "is_active", "2026-08-20 여러 개 중 하나만 사용"),
    ("team", "guardrail_on_failure", "2026-08-24 가드레일 연결 실패 시 동작(팀 속성)"),
    ("mcp_call_note", None, "2026-08-21 MCP 동시 실행·timeout 경고 재료"),
    ("tool_call", "retrieved_doc_ids", "2026-08-21 도구가 조회한 문서 식별자"),
]


def _read_database_url() -> tuple[str, str]:
    """URL 과 **그것을 어디서 읽었는지**를 함께 준다.

    출처를 함께 찍는 이유 — 호스트에서 테스트를 돌릴 때 `DATABASE_URL` 을
    `localhost` 로 덮어쓰는 습관이 있어서(`.env` 값이 컨테이너 이름 `db` 다),
    어느 쪽이 이겼는지 안 보이면 **엉뚱한 DB 에 적용하고도 성공으로 읽는다.**
    """
    # 컨테이너 안에는 `.env` 파일이 없다 — compose 가 값을 환경변수로 넣어 준다.
    # 공유 RDS 에 적용하는 자리가 바로 거기라 이 갈래가 먼저다.
    from_env = os.environ.get("DATABASE_URL", "").strip()
    if from_env:
        return from_env, "환경변수 DATABASE_URL"

    if ENV_FILE.exists():
        with ENV_FILE.open(encoding="utf-8") as f:
            for line in f:
                if line.startswith("DATABASE_URL="):
                    return line.strip().split("=", 1)[1].strip("\"'"), str(ENV_FILE)

    raise SystemExit(
        "DATABASE_URL 을 찾지 못했습니다 — 환경변수에도 없고 "
        f"{ENV_FILE} 도 없습니다. `--url` 로 직접 주세요."
    )


def _target(url: str) -> str:
    """**자격증명은 찍지 않는다.** 어디에 붙었는지만 보여 준다."""
    return url.split("@")[-1] if "@" in url else url


def _split_statements(sql: str) -> list[str]:
    # 줄 전체가 주석(--)인 줄만 지운다. 세미콜론은 마이그레이션 파일 안에서
    # 문자열 리터럴로 나오지 않으므로 단순 split 으로 충분하다.
    without_comments = re.sub(r"^--.*$", "", sql, flags=re.MULTILINE)
    statements = [s.strip() for s in without_comments.split(";")]
    # BEGIN/COMMIT 은 뺀다 — psycopg 연결은 기본이 autocommit=False 라
    # `with conn:` 블록 자체가 이미 트랜잭션이다.
    return [s for s in statements if s and s.upper() not in ("BEGIN", "COMMIT")]


def check(url: str) -> int:
    missing: list[tuple[str, str | None, str]] = []
    with psycopg.connect(url) as connection, connection.cursor() as cursor:
        for table, column, why in EXPECTED:
            if column is None:
                cursor.execute("SELECT to_regclass(%s) IS NOT NULL", (f"public.{table}",))
            else:
                cursor.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns
                         WHERE table_schema = 'public'
                           AND table_name = %s AND column_name = %s
                    )
                    """,
                    (table, column),
                )
            if not cursor.fetchone()[0]:
                missing.append((table, column, why))

    name_of = lambda t, c: t if c is None else f"{t}.{c}"  # noqa: E731
    print(f"대상 DB: {_target(url)}")
    print(f"확인 항목 {len(EXPECTED)}개 · 빠진 것 {len(missing)}개")
    for table, column, why in missing:
        print(f"  [없음] {name_of(table, column):<38} {why}")
    if not missing:
        print("  [OK] 배포가 전제하는 스키마가 전부 있습니다.")
        return 0
    print("\n적용하려면 `DB_시작_가이드.md` §4.3 블록을 돌리거나, 해당 .sql 을 인자로 주세요.")
    return 1


def apply(url: str, paths: list[Path]) -> int:
    print(f"대상 DB: {_target(url)}")
    for path in paths:
        if not path.exists():
            raise SystemExit(f"없는 파일: {path}")
        statements = _split_statements(path.read_text(encoding="utf-8"))
        print(f"\n== {path.name} — 문장 {len(statements)}개")
        with psycopg.connect(url) as connection:
            with connection.cursor() as cursor:
                for statement in statements:
                    print(f"   - {statement.splitlines()[0][:72]}")
                    cursor.execute(statement)
            connection.commit()
        print("   커밋 완료")
    print()
    return check(url)


def main() -> None:
    parser = argparse.ArgumentParser(description="마이그레이션 확인·적용")
    parser.add_argument("files", nargs="*", type=Path, help="적용할 .sql (없으면 확인만)")
    parser.add_argument("--check", action="store_true", help="읽기만 한다")
    parser.add_argument("--url", help="대상 DB. 안 주면 환경변수 → .env 순으로 읽는다")
    args = parser.parse_args()

    if args.url:
        url, source = args.url, "--url"
    else:
        url, source = _read_database_url()
    print(f"URL 출처: {source}")

    if args.check or not args.files:
        sys.exit(check(url))
    sys.exit(apply(url, args.files))


if __name__ == "__main__":
    main()
