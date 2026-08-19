"""memory/write_lock.py(MemoryWriteLockMiddleware) 단위 테스트.

`ToolCallRequest`는 실제 langchain 클래스를 그대로 쓴다(`test_memory_write_guard.py`
와 같은 관례) — DB 연결(`backend.db.connection.database_connection`)만 patch해서
"어떤 SQL을, 어떤 락 키로, handler 호출 전에 실행하는가"를 확인한다. 실제
Postgres는 여기서 안 쓴다(실제 Postgres 검증은 완료 보고서에서 별도로 한다,
`2026-08-19_09_Run_Snapshot...` 등 이전 항목들과 같은 패턴).
"""

from unittest.mock import MagicMock, Mock, patch

from django.test import SimpleTestCase
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolMessage

from services.agent_runtime.memory.write_lock import (
    MemoryWriteLockMiddleware,
    build_memory_write_lock,
)

_CONNECTION_TARGET = "backend.db.connection.database_connection"
_NAMESPACE = ("TM001", "AG001", "AC001")


def _request(*, name: str, args: dict, tool_call_id: str = "call-1") -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": name, "args": args, "id": tool_call_id}, tool=None, state={}, runtime=None
    )


def _mock_database_connection():
    """`with database_connection() as connection, connection.cursor() as cursor:`가
    그대로 동작하는 MagicMock 체인을 만든다."""
    cursor = MagicMock()
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    connection.cursor.return_value.__exit__.return_value = False
    ctx = MagicMock()
    ctx.__enter__.return_value = connection
    ctx.__exit__.return_value = False
    factory = Mock(return_value=ctx)
    return factory, connection, cursor


class BuildMemoryWriteLockTests(SimpleTestCase):
    def test_returns_a_configured_middleware(self):
        lock = build_memory_write_lock(namespace=_NAMESPACE)

        self.assertIsInstance(lock, MemoryWriteLockMiddleware)
        self.assertEqual(lock._namespace, _NAMESPACE)


class UnguardedToolPassthroughTests(SimpleTestCase):
    """대상 도구(write_file/edit_file/delete)가 아니면 DB에 손대지 않고 그대로 통과한다."""

    def test_read_file_is_not_locked(self):
        lock = MemoryWriteLockMiddleware(namespace=_NAMESPACE)
        handler = Mock(return_value="handled")
        request = _request(name="read_file", args={"file_path": "/memories/users/preferences.md"})

        with patch(_CONNECTION_TARGET) as mock_conn:
            result = lock.wrap_tool_call(request, handler)

        handler.assert_called_once_with(request)
        self.assertEqual(result, "handled")
        mock_conn.assert_not_called()

    def test_ls_is_not_locked(self):
        lock = MemoryWriteLockMiddleware(namespace=_NAMESPACE)
        handler = Mock(return_value="handled")
        request = _request(name="ls", args={})

        with patch(_CONNECTION_TARGET) as mock_conn:
            result = lock.wrap_tool_call(request, handler)

        handler.assert_called_once_with(request)
        mock_conn.assert_not_called()


class OutsideGuardedPrefixTests(SimpleTestCase):
    def test_write_file_outside_prefix_passes_without_locking(self):
        lock = MemoryWriteLockMiddleware(namespace=_NAMESPACE)
        handler = Mock(return_value="handled")
        request = _request(name="write_file", args={"file_path": "/memories/projects/PJ001.md", "content": "x"})

        with patch(_CONNECTION_TARGET) as mock_conn:
            result = lock.wrap_tool_call(request, handler)

        handler.assert_called_once_with(request)
        self.assertEqual(result, "handled")
        mock_conn.assert_not_called()


class InvalidPathPassthroughTests(SimpleTestCase):
    def test_path_traversal_is_not_write_locks_concern(self):
        lock = MemoryWriteLockMiddleware(namespace=_NAMESPACE)
        handler = Mock(return_value="handled")
        request = _request(name="write_file", args={"file_path": "../etc/passwd", "content": "x"})

        with patch(_CONNECTION_TARGET) as mock_conn:
            result = lock.wrap_tool_call(request, handler)

        handler.assert_called_once_with(request)
        mock_conn.assert_not_called()


class GuardedWriteAcquiresLockTests(SimpleTestCase):
    def test_write_file_under_prefix_acquires_advisory_lock_before_calling_handler(self):
        lock = MemoryWriteLockMiddleware(namespace=_NAMESPACE)
        call_order = []
        handler = Mock(side_effect=lambda req: call_order.append("handler") or "handled")
        request = _request(
            name="write_file", args={"file_path": "/memories/users/preferences.md", "content": "x"}
        )

        factory, connection, cursor = _mock_database_connection()
        cursor.execute.side_effect = lambda *a, **k: call_order.append("execute")

        with patch(_CONNECTION_TARGET, factory):
            result = lock.wrap_tool_call(request, handler)

        self.assertEqual(result, "handled")
        self.assertEqual(call_order, ["execute", "handler"])
        cursor.execute.assert_called_once()
        sql, params = cursor.execute.call_args[0]
        self.assertIn("pg_advisory_xact_lock", sql)
        self.assertIn("hashtext", sql)
        (lock_key,) = params
        self.assertEqual(lock_key, "memory-write:TM001:AG001:AC001:/memories/users/preferences.md")

    def test_edit_file_under_prefix_is_locked(self):
        lock = MemoryWriteLockMiddleware(namespace=_NAMESPACE)
        handler = Mock(return_value="handled")
        request = _request(
            name="edit_file",
            args={"file_path": "/memories/users/preferences.md", "old_string": "a", "new_string": "b"},
        )

        factory, connection, cursor = _mock_database_connection()

        with patch(_CONNECTION_TARGET, factory):
            result = lock.wrap_tool_call(request, handler)

        self.assertEqual(result, "handled")
        cursor.execute.assert_called_once()

    def test_delete_under_prefix_is_locked(self):
        """delete는 지금 정책상 노출되지 않지만(runtime_policy 기본값), 나중에
        정책이 바뀌어도 안전하도록 대상에 포함한다(모듈 docstring)."""
        lock = MemoryWriteLockMiddleware(namespace=_NAMESPACE)
        handler = Mock(return_value="handled")
        request = _request(name="delete", args={"file_path": "/memories/users/preferences.md"})

        factory, connection, cursor = _mock_database_connection()

        with patch(_CONNECTION_TARGET, factory):
            result = lock.wrap_tool_call(request, handler)

        self.assertEqual(result, "handled")
        cursor.execute.assert_called_once()

    def test_path_normalization_missing_leading_slash_is_still_locked(self):
        lock = MemoryWriteLockMiddleware(namespace=_NAMESPACE)
        handler = Mock(return_value="handled")
        request = _request(
            name="write_file", args={"file_path": "memories/users/preferences.md", "content": "x"}
        )

        factory, connection, cursor = _mock_database_connection()

        with patch(_CONNECTION_TARGET, factory):
            result = lock.wrap_tool_call(request, handler)

        self.assertEqual(result, "handled")
        cursor.execute.assert_called_once()
        (lock_key,) = cursor.execute.call_args[0][1]
        self.assertEqual(lock_key, "memory-write:TM001:AG001:AC001:/memories/users/preferences.md")


class LockReleasedViaConnectionExitTests(SimpleTestCase):
    """락 해제는 별도 SQL이 아니라 connection의 with 블록을 벗어나는 것 자체
    (commit/rollback)로 이뤄진다 — handler가 그 블록 안에서 불렸는지, 예외가
    나도 블록을 정상적으로 벗어나는지(=rollback되며 락도 풀리는지) 확인한다."""

    def test_handler_is_called_while_connection_context_is_still_open(self):
        lock = MemoryWriteLockMiddleware(namespace=_NAMESPACE)
        factory, connection, cursor = _mock_database_connection()
        ctx = factory.return_value

        def _handler(_req):
            # handler가 불릴 때 connection __exit__(commit)이 아직 안 불렸어야
            # 한다 — 그래야 락을 쥔 채로 실제 쓰기가 끝난다.
            ctx.__exit__.assert_not_called()
            return "handled"

        request = _request(
            name="write_file", args={"file_path": "/memories/users/preferences.md", "content": "x"}
        )

        with patch(_CONNECTION_TARGET, factory):
            result = lock.wrap_tool_call(request, _handler)

        self.assertEqual(result, "handled")
        ctx.__exit__.assert_called_once()

    def test_handler_exception_propagates_and_connection_still_exits(self):
        lock = MemoryWriteLockMiddleware(namespace=_NAMESPACE)
        factory, connection, cursor = _mock_database_connection()
        ctx = factory.return_value

        def _handler(_req):
            raise ValueError("handler가 터졌다")

        request = _request(
            name="write_file", args={"file_path": "/memories/users/preferences.md", "content": "x"}
        )

        with patch(_CONNECTION_TARGET, factory):
            with self.assertRaises(ValueError):
                lock.wrap_tool_call(request, _handler)

        # 예외가 나도 `with` 블록은 __exit__을 거쳐 빠져나간다(psycopg가
        # 예외 시 rollback 처리 — 여기선 __exit__ 호출 여부만 확인한다).
        ctx.__exit__.assert_called_once()


class GuardedPrefixOverrideTests(SimpleTestCase):
    def test_custom_prefix_is_respected(self):
        lock = MemoryWriteLockMiddleware(namespace=_NAMESPACE, guarded_prefix="/memories/scratch/")
        handler = Mock(return_value="handled")
        request = _request(name="write_file", args={"file_path": "/memories/scratch/notes.md", "content": "x"})

        factory, connection, cursor = _mock_database_connection()

        with patch(_CONNECTION_TARGET, factory):
            result = lock.wrap_tool_call(request, handler)

        self.assertEqual(result, "handled")
        cursor.execute.assert_called_once()

    def test_default_prefix_users_path_is_unaffected_by_custom_prefix(self):
        lock = MemoryWriteLockMiddleware(namespace=_NAMESPACE, guarded_prefix="/memories/scratch/")
        handler = Mock(return_value="handled")
        request = _request(
            name="write_file", args={"file_path": "/memories/users/preferences.md", "content": "x"}
        )

        with patch(_CONNECTION_TARGET) as mock_conn:
            result = lock.wrap_tool_call(request, handler)

        handler.assert_called_once_with(request)
        mock_conn.assert_not_called()


class NamespaceIsolationTests(SimpleTestCase):
    """다른 namespace(계정/팀/에이전트)로 만든 인스턴스는 다른 락 키를 쓴다 —
    락 키에 namespace가 섞여 들어가는지 확인한다."""

    def test_different_namespace_produces_different_lock_key(self):
        handler = Mock(return_value="handled")
        request = _request(
            name="write_file", args={"file_path": "/memories/users/preferences.md", "content": "x"}
        )

        keys = []
        for namespace in [("TM001", "AG001", "AC001"), ("TM001", "AG001", "AC002")]:
            lock = MemoryWriteLockMiddleware(namespace=namespace)
            factory, connection, cursor = _mock_database_connection()
            with patch(_CONNECTION_TARGET, factory):
                lock.wrap_tool_call(request, handler)
            keys.append(cursor.execute.call_args[0][1][0])

        self.assertNotEqual(keys[0], keys[1])
