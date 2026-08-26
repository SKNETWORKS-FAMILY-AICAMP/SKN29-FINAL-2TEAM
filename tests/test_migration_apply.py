from __future__ import annotations

import importlib.util
import io
import os
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "DB" / "migrations" / "_apply.py"
SPEC = importlib.util.spec_from_file_location("migration_apply", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
migration_apply = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(migration_apply)


class FakeCursor:
    def __init__(
        self,
        *,
        correlation_column: bool = True,
        correlation_index: bool = True,
        correlation_index_unique: bool = True,
        max_iterations_default: str = "10",
    ) -> None:
        self.correlation_column = correlation_column
        self.correlation_index = correlation_index
        self.correlation_index_unique = correlation_index_unique
        self.max_iterations_default = max_iterations_default
        self.result = True

    def execute(self, sql, params=None) -> None:
        normalized = " ".join(str(sql).split())
        # `column_default` 조회도 `information_schema.columns`를 쓰므로 이 분기를
        # 먼저 본다 — 안 그러면 아래 EXISTS 분기로 잘못 잡혀 bool을 돌려준다.
        if "column_default" in normalized:
            self.result = self.max_iterations_default
        elif "information_schema.columns" in normalized:
            self.result = not (
                params == ("tool_call", "langchain_tool_call_id")
                and not self.correlation_column
            )
        elif "pg_index" in normalized:
            checks_unique = "indisunique" in normalized
            self.result = self.correlation_index and (
                self.correlation_index_unique or not checks_unique
            )
        else:
            self.result = True

    def fetchone(self):
        return (self.result,)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class MigrationCheckTests(unittest.TestCase):
    def run_check(self, **cursor_options):
        connection = FakeConnection(FakeCursor(**cursor_options))
        output = io.StringIO()
        with (
            patch.object(migration_apply.psycopg, "connect", return_value=connection),
            redirect_stdout(output),
        ):
            result = migration_apply.check("postgresql://user:secret@db:5432/project")
        return result, output.getvalue()

    def test_missing_correlation_column_fails(self):
        result, output = self.run_check(correlation_column=False)

        self.assertEqual(result, 1)
        self.assertIn("tool_call.langchain_tool_call_id", output)

    def test_missing_correlation_index_fails(self):
        result, output = self.run_check(correlation_index=False)

        self.assertEqual(result, 1)
        self.assertIn("tool_call.ux_tool_call_run_langchain_id", output)

    def test_non_unique_correlation_index_fails(self):
        result, output = self.run_check(correlation_index_unique=False)

        self.assertEqual(result, 1)
        self.assertIn("tool_call.ux_tool_call_run_langchain_id", output)

    def test_complete_correlation_schema_passes(self):
        result, output = self.run_check()

        self.assertEqual(result, 0)
        self.assertIn("[OK]", output)

    def test_stale_default_fails(self):
        """컬럼은 있지만 기본값이 옛 마이그레이션 전 값(6)에 멈춰 있으면 잡는다 —
        존재 여부만 보는 EXPECTED로는 이 마이그레이션 누락이 안 드러난다."""
        result, output = self.run_check(max_iterations_default="6")

        self.assertEqual(result, 1)
        self.assertIn("[값다름]", output)
        self.assertIn("agent_versions.max_iterations", output)


class SplitStatementsTests(unittest.TestCase):
    def test_semicolon_inside_string_literal_does_not_split_statement(self):
        sql = "COMMENT ON COLUMN tool_call.status IS 'before; after';"

        self.assertEqual(migration_apply._split_statements(sql), [sql.rstrip(";")])


class GuardrailOnFailureMigrationTests(unittest.TestCase):
    def test_migration_succeeds_when_legacy_provider_column_is_absent(self):
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            self.skipTest("DATABASE_URL이 설정되지 않았습니다.")

        migration = (
            SCRIPT.parent / "2026-08-24_guardrail_on_failure_to_team.sql"
        ).read_text(encoding="utf-8")

        with migration_apply.psycopg.connect(database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("CREATE TEMP TABLE team (team_id VARCHAR(5) PRIMARY KEY)")
                cursor.execute(
                    "CREATE TEMP TABLE guardrail_provider (team_id VARCHAR(5) NOT NULL)"
                )
                cursor.execute("INSERT INTO team (team_id) VALUES ('TE001')")

                statements = migration_apply._split_statements(migration)
                for _ in range(2):
                    for statement in statements:
                        cursor.execute(statement)

                cursor.execute(
                    "SELECT guardrail_on_failure FROM team WHERE team_id = 'TE001'"
                )
                self.assertEqual(cursor.fetchone(), ("OPEN",))


if __name__ == "__main__":
    unittest.main()
