# HITL Migration Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `DB/migrations/_apply.py --check` fail unless the HITL correlation column and its required UNIQUE index both exist.

**Architecture:** Keep the existing table/column expectations unchanged in shape and add a separate index expectation list. Extend `check()` with one PostgreSQL catalog query that verifies the index name, owning table, schema, and `indisunique`; use a small fake psycopg connection in a focused unit test so no real DB is required.

**Tech Stack:** Python 3.13, `unittest`, `unittest.mock`, psycopg, PostgreSQL system catalogs

---

### Task 1: Add failing migration-check regression tests

**Files:**
- Create: `tests/test_migration_apply.py`
- Test: `tests/test_migration_apply.py`

- [ ] **Step 1: Create a focused fake DB and four behavioral tests**

Create `tests/test_migration_apply.py` with the following content:

```python
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
```

- [ ] **Step 2: Run the new tests and verify the regression is exposed**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_migration_apply -v
```

Expected: three tests fail because `_apply.py` does not yet inspect the new column or index; `test_complete_correlation_schema_passes` passes.

- [ ] **Step 3: Commit the failing regression tests**

```powershell
git add tests/test_migration_apply.py
git commit -m "HITL 마이그레이션 검사 회귀 테스트를 추가한다"
```

### Task 2: Implement column and UNIQUE-index checks

**Files:**
- Modify: `DB/migrations/_apply.py:51-90`
- Modify: `DB/migrations/_apply.py:133-162`
- Test: `tests/test_migration_apply.py`

- [ ] **Step 1: Add the correlation column expectation**

Append this tuple to `EXPECTED` after the existing `tool_call.retrieved_doc_ids` entry:

```python
    (
        "tool_call",
        "langchain_tool_call_id",
        "2026-08-24 HITL 도구 호출 상관관계",
    ),
```

- [ ] **Step 2: Add a separate index expectation list**

Immediately after `EXPECTED`, add:

```python
EXPECTED_INDEXES: list[tuple[str, str, str]] = [
    (
        "tool_call",
        "ux_tool_call_run_langchain_id",
        "2026-08-24 HITL 도구 호출 중복 방지",
    ),
]
```

- [ ] **Step 3: Query PostgreSQL catalogs for the expected UNIQUE index**

In `check()`, after the existing `for table, column, why in EXPECTED` loop and before `name_of`, add:

```python
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
```

Keep the existing `missing` tuple shape and `name_of()` formatting. This makes the new missing item print as `tool_call.ux_tool_call_run_langchain_id` without introducing another result type or formatter.

- [ ] **Step 4: Include index expectations in the reported check count**

Replace the existing count print in `check()` with:

```python
    checked = len(EXPECTED) + len(EXPECTED_INDEXES)
    print(f"확인 항목 {checked}개 · 빠진 것 {len(missing)}개")
```

This keeps the existing output format while preventing the displayed total from excluding the new index check.

- [ ] **Step 5: Run the focused tests and verify they pass**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_migration_apply -v
```

Expected: `Ran 4 tests` and `OK`.

- [ ] **Step 6: Run a syntax check**

Run:

```powershell
.\.venv\Scripts\python.exe -m py_compile DB\migrations\_apply.py tests\test_migration_apply.py
```

Expected: exit code `0` with no output.

- [ ] **Step 7: Commit the minimal implementation**

```powershell
git add DB/migrations/_apply.py
git commit -m "HITL 마이그레이션 인덱스를 배포 전에 검사한다"
```

### Task 3: Verify the completed checker change

**Files:**
- Verify: `DB/migrations/_apply.py`
- Verify: `tests/test_migration_apply.py`

- [ ] **Step 1: Run the focused test again from a clean process**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_migration_apply -v
```

Expected: `Ran 4 tests` and `OK`.

- [ ] **Step 2: Run repository diff validation**

```powershell
git diff --check HEAD~2..HEAD
```

Expected: exit code `0` with no output.

- [ ] **Step 3: Confirm only planned files were committed**

```powershell
git diff --name-only HEAD~2..HEAD
```

Expected output:

```text
DB/migrations/_apply.py
tests/test_migration_apply.py
```

- [ ] **Step 4: Record the external DB follow-up without running it locally**

Do not claim the migration is applied. Report these remaining commands for a DB-accessible container or deployment host:

```powershell
.\.venv\Scripts\python.exe DB\migrations\_apply.py --check
.\.venv\Scripts\python.exe DB\migrations\_apply.py DB\migrations\2026-08-24_tool_call_hitl_lifecycle.sql
.\.venv\Scripts\python.exe DB\migrations\_apply.py --check
```

Expected after the final command: missing count `0`. The manual approve, reject, and subagent HITL scenarios remain separate QA work after the DB migration.
