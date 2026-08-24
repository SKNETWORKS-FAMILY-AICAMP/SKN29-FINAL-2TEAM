from __future__ import annotations

import importlib.util
import io
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
    ) -> None:
        self.correlation_column = correlation_column
        self.correlation_index = correlation_index
        self.correlation_index_unique = correlation_index_unique
        self.result = True

    def execute(self, sql, params=None) -> None:
        normalized = " ".join(str(sql).split())
        if "information_schema.columns" in normalized:
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


if __name__ == "__main__":
    unittest.main()
