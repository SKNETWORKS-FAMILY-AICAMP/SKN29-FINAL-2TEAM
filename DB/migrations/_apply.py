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
    # **이 둘은 빠지면 수집이 통째로 멈춘다.** 「문서」 화면이 읽기만 하는 것이
    # 아니라 `add_drive_documents` 의 INSERT 가 두 칸을 함께 넣는다 — 컬럼이
    # 없으면 새 문서 등록이 전부 실패한다.
    ("doc", "team_folder_id", "2026-08-25 문서의 출처 폴더(「문서」 화면 트리)"),
    ("doc", "src_folder_path", "2026-08-25 뿌리 폴더 안에서의 상대 경로"),
    ("connector_conn", "sync_cursor", "2026-08-24 증분 동기화 커서"),
    # 웹훅 채널. 없으면 `changes.watch` 를 열어도 기억할 데가 없다.
    ("connector_conn", "channel_id", "2026-08-25 Drive 변경 알림 채널"),
    ("connector_conn", "channel_resource_id", "2026-08-25 채널 중지에 필요한 값"),
    ("connector_conn", "channel_expires_at", "2026-08-25 채널 만료 시각(갱신 판단)"),
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
    ("eval_run", None, "2026-08-26 Agent 평가 실행 결과"),
    ("eval_case_result", None, "2026-08-26 Agent 평가 사례 결과"),
    ("eval_judge_result", None, "2026-08-26 Agent 평가 LLM Judge 판정"),
    ("eval_v2_run", None, "2026-08-27 Agent 평가 V2 실행 결과"),
    ("eval_v2_scenario_result", None, "2026-08-27 Agent 평가 V2 사례 결과"),
    ("guardrail_event", None, "2026-08-20 가드레일 발동 기록"),
    ("guardrail_provider", None, "2026-08-20 외부 가드레일 공급자 등록"),
    ("guardrail_provider", "is_active", "2026-08-20 여러 개 중 하나만 사용"),
    ("team", "guardrail_on_failure", "2026-08-24 가드레일 연결 실패 시 동작(팀 속성)"),
    ("mcp_call_note", None, "2026-08-21 MCP 동시 실행·timeout 경고 재료"),
    ("tool_call", "retrieved_doc_ids", "2026-08-21 도구가 조회한 문서 식별자"),
    (
        "tool_call",
        "langchain_tool_call_id",
        "2026-08-24 HITL 도구 호출 상관관계",
    ),
    ("team", "default_model", "2026-08-22 팀 기본 채팅 모델 — 레거시 정문 에이전트에서 옮김"),
    ("skill_registration_job", None, "2026-08-26 스킬 등록 검증 job 큐"),
    ("skill_registration_job", "metrics", "2026-08-26 §8 평가 지표·재현성 컬럼"),
    ("skill_registration_job", "progress_message", "2026-08-27 스킬 검증 세부 진행 문구"),
    ("skill_registration_job", "progress_events", "2026-08-27 스킬 검증 진행 이력"),
    ("skill_registration_job", "runtime_profile_version", "2026-08-27 스킬 검증 런타임 스냅샷"),
    ("skill_registration_job", "tool_registry_version", "2026-08-27 스킬 검증 도구 스냅샷"),
    ("skill_registration_job", "model_call_count", "2026-08-27 스킬 검증 호출 예산"),
    ("skill_catalog_revision", None, "2026-08-27 개인 스킬 카탈로그 revision"),
    ("skill_worker_heartbeat", None, "2026-08-27 스킬 검증 워커 상태"),
    ("skill_eval_regression_case", None, "2026-08-26 실제 오발동 회귀 케이스"),
    ("skill_eval_feedback", None, "2026-08-27 스킬 사용 피드백"),
    ("skill_eval_regression_case", "source_feedback_id", "2026-08-27 회귀 사례 신고 연결"),
    # 2026-08-22_drop_legacy_agent.sql 은 여기 못 적는다 — 이 표는 "있어야 할
    # 것이 있는가"만 보는데, 그 마이그레이션이 하는 일은 `agent`/`agent_tool`을
    # **없애는** 것이다. 적용 여부는 아래 쿼리로 직접 확인한다(0이어야 한다):
    #   SELECT count(*) FROM information_schema.tables
    #    WHERE table_schema='public' AND table_name IN ('agent','agent_tool');
]

EXPECTED_INDEXES: list[tuple[str, str, str]] = [
    (
        "tool_call",
        "ux_tool_call_run_langchain_id",
        "2026-08-24 HITL 도구 호출 중복 방지",
    ),
]

EXPECTED_CONSTRAINTS: list[tuple[str, str, str]] = [
    (
        "skill_eval_regression_case",
        "ck_skill_eval_regression_scope_fields",
        "2026-08-27 회귀 사례 범위별 team/skill 필드 정합성",
    ),
]

EXPECTED_COLUMN_TYPES: list[tuple[str, str, str, int | None, str]] = [
    (
        "skill_registration_job",
        "operation",
        "character varying",
        10,
        "2026-08-27 스킬 재검증 RETRY 저장 길이",
    ),
    (
        "skill_eval_regression_case",
        "dataset_version",
        "character varying",
        64,
        "2026-08-27 회귀 평가 데이터 버전 길이",
    ),
]

#: 컬럼이 **있기는 한데 기본값이 옛날 값에 멈춰 있는** 경우를 잡는다. 위
#: `EXPECTED`는 존재 여부만 보므로, `ALTER COLUMN ... SET DEFAULT`만 하는
#: 마이그레이션(컬럼 추가가 아니라 기본값만 바꾸는 것)은 안 돌려도 `--check`가
#: "전부 있다"고 거짓으로 답한다 — 2026-08-25에 실제로 이 틈을 만났다
#: (`agent_versions.max_iterations` 기본값 6→10 마이그레이션).
#: `information_schema.columns.column_default`는 문자열로 온다(정수 컬럼은
#: `"10"`처럼 캐스트 없이 그대로).
EXPECTED_DEFAULTS: list[tuple[str, str, str, str]] = [
    (
        "agent_versions",
        "max_iterations",
        "10",
        "2026-08-25 새 에이전트 기본 호출 상한 6→10",
    ),
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
    # 문자열 리터럴에도 나올 수 있으므로 따옴표 밖의 것만 문장 끝으로 본다.
    without_comments = re.sub(r"^--.*$", "", sql, flags=re.MULTILINE)
    statements: list[str] = []
    current: list[str] = []
    in_string = False
    index = 0
    while index < len(without_comments):
        char = without_comments[index]
        if char == "'":
            current.append(char)
            if in_string and index + 1 < len(without_comments) and without_comments[index + 1] == "'":
                current.append("'")
                index += 2
                continue
            in_string = not in_string
        elif char == ";" and not in_string:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
        else:
            current.append(char)
        index += 1

    final_statement = "".join(current).strip()
    if final_statement:
        statements.append(final_statement)
    # BEGIN/COMMIT 은 뺀다 — psycopg 연결은 기본이 autocommit=False 라
    # `with conn:` 블록 자체가 이미 트랜잭션이다.
    return [s for s in statements if s and s.upper() not in ("BEGIN", "COMMIT")]


def check(url: str) -> int:
    missing: list[tuple[str, str | None, str]] = []
    mismatched_defaults: list[tuple[str, str, str, str, str]] = []
    mismatched_types: list[tuple[str, str, str, str, str]] = []
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

        for table, index, why in EXPECTED_INDEXES:
            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                      FROM pg_index AS index_meta
                      JOIN pg_class AS index_class
                        ON index_class.oid = index_meta.indexrelid
                      JOIN pg_class AS table_class
                        ON table_class.oid = index_meta.indrelid
                      JOIN pg_namespace AS namespace
                        ON namespace.oid = table_class.relnamespace
                     WHERE namespace.nspname = 'public'
                       AND table_class.relname = %s
                       AND index_class.relname = %s
                       AND index_meta.indisunique
                )
                """,
                (table, index),
            )
            if not cursor.fetchone()[0]:
                missing.append((table, index, why))

        for table, constraint, why in EXPECTED_CONSTRAINTS:
            cursor.execute(
                """SELECT EXISTS (
                       SELECT 1 FROM information_schema.table_constraints
                        WHERE table_schema = 'public' AND table_name = %s
                          AND constraint_name = %s
                   )""",
                (table, constraint),
            )
            if not cursor.fetchone()[0]:
                missing.append((table, constraint, why))

        for table, column, expected_type, expected_length, why in EXPECTED_COLUMN_TYPES:
            cursor.execute(
                """SELECT data_type, character_maximum_length
                     FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = %s AND column_name = %s""",
                (table, column),
            )
            row = cursor.fetchone()
            actual = None if row is None else (row[0], row[1])
            if actual != (expected_type, expected_length):
                mismatched_types.append((
                    table, column, f"{expected_type}({expected_length})",
                    "없음" if actual is None else f"{actual[0]}({actual[1]})", why,
                ))

        for table, column, expected_default, why in EXPECTED_DEFAULTS:
            cursor.execute(
                """
                SELECT column_default FROM information_schema.columns
                 WHERE table_schema = 'public' AND table_name = %s AND column_name = %s
                """,
                (table, column),
            )
            row = cursor.fetchone()
            actual_default = row[0] if row else None
            if actual_default != expected_default:
                mismatched_defaults.append((table, column, expected_default, actual_default, why))

    name_of = lambda t, c: t if c is None else f"{t}.{c}"  # noqa: E731
    print(f"대상 DB: {_target(url)}")
    checked = (
        len(EXPECTED) + len(EXPECTED_INDEXES) + len(EXPECTED_CONSTRAINTS)
        + len(EXPECTED_COLUMN_TYPES) + len(EXPECTED_DEFAULTS)
    )
    print(
        f"확인 항목 {checked}개 · 빠진 것 {len(missing)}개 · "
        f"기본값 불일치 {len(mismatched_defaults)}개 · 타입 불일치 {len(mismatched_types)}개"
    )
    for table, column, why in missing:
        print(f"  [없음] {name_of(table, column):<38} {why}")
    for table, column, expected_default, actual_default, why in mismatched_defaults:
        print(
            f"  [값다름] {name_of(table, column):<38} "
            f"기대 {expected_default!r} · 실제 {actual_default!r}  {why}"
        )
    for table, column, expected, actual, why in mismatched_types:
        print(f"  [타입다름] {name_of(table, column):<38} 기대 {expected} · 실제 {actual}  {why}")
    if not missing and not mismatched_defaults and not mismatched_types:
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
