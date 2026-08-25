"""middleware/builtin_write_lock.py — 내장 쓰기 도구의 같은 프로젝트 직렬화.

정본: `docs/설계 및 구현/3_중간발표 이후/작업기록/Deep_Agents/2026-08-20_02_에이전트_병렬실행_설계.md` §5.2.

`test_memory_write_guard.py`/`test_memory_write_lock.py`와 같은 관례로, 실제
`ToolCallRequest`를 쓰고 DB 연결만 가짜로 바꾼다 — 여기서 지키려는 건 "어떤
호출에 어떤 키로 락을 잡는가"이지 Postgres 동작이 아니다.
"""

from contextlib import contextmanager
from unittest.mock import patch

from django.test import SimpleTestCase
from langchain.agents.middleware.types import ToolCallRequest

from services.agent_runtime.context import RuntimeContext
from services.agent_runtime.middleware.builtin_write_lock import (
    BuiltinWriteLockMiddleware,
    build_builtin_write_lock,
)

CONNECTION = "backend.db.connection.database_connection"


class _Cursor:
    def __init__(self, sink):
        self.sink = sink

    def execute(self, sql, params=None):
        self.sink.append((sql, params))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Connection:
    def __init__(self, sink):
        self.sink = sink

    def cursor(self):
        return _Cursor(self.sink)


@contextmanager
def _fake_connection(sink):
    yield _Connection(sink)


def _request(name: str) -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": name, "args": {}, "id": "call-1"}, tool=None, state={}, runtime=None
    )


def _context(project_id: str | None = "PJ001") -> RuntimeContext:
    return RuntimeContext(
        account_id="AC001", team_id="TM001", role="leader", project_id=project_id
    )


class LockedToolsTests(SimpleTestCase):
    def test_task_register_takes_an_advisory_lock(self):
        sink: list = []
        middleware = BuiltinWriteLockMiddleware(context=_context())

        with patch(CONNECTION, lambda: _fake_connection(sink)):
            result = middleware.wrap_tool_call(_request("task_register"), lambda r: "done")

        self.assertEqual(result, "done")
        self.assertEqual(len(sink), 1)
        self.assertIn("pg_advisory_xact_lock", sink[0][0])

    def test_lock_key_is_scoped_to_team_and_project(self):
        """프로젝트가 다르면 서로 아무것도 공유하지 않으므로 병렬로 둔다 —
        키가 프로젝트를 포함해야 그렇게 된다. 팀도 함께 건다(다른 팀의 같은
        이름 프로젝트와 섞이지 않게)."""
        sink: list = []
        middleware = BuiltinWriteLockMiddleware(context=_context(project_id="PJ042"))

        with patch(CONNECTION, lambda: _fake_connection(sink)):
            middleware.wrap_tool_call(_request("task_register"), lambda r: "done")

        self.assertEqual(sink[0][1], ("builtin-write:TM001:PJ042",))

    def test_different_projects_get_different_keys(self):
        first: list = []
        second: list = []

        with patch(CONNECTION, lambda: _fake_connection(first)):
            BuiltinWriteLockMiddleware(context=_context("PJ001")).wrap_tool_call(
                _request("task_register"), lambda r: "done"
            )
        with patch(CONNECTION, lambda: _fake_connection(second)):
            BuiltinWriteLockMiddleware(context=_context("PJ002")).wrap_tool_call(
                _request("task_register"), lambda r: "done"
            )

        self.assertNotEqual(first[0][1], second[0][1])

    def test_all_three_side_effect_builtins_are_guarded(self):
        for name in ("task_register", "task_update", "jira_create_issues"):
            with self.subTest(tool=name):
                sink: list = []
                middleware = BuiltinWriteLockMiddleware(context=_context())

                with patch(CONNECTION, lambda: _fake_connection(sink)):
                    middleware.wrap_tool_call(_request(name), lambda r: "done")

                self.assertEqual(len(sink), 1)

    def test_handler_runs_inside_the_lock(self):
        """handler를 락 전용 connection의 `with` 블록 **안에서** 불러야 락을
        쥔 채로 쓰기가 끝난다 — 밖에서 부르면 두 번째 호출이 안 기다린다
        (`memory/write_lock.py`와 같은 이유)."""
        order: list = []
        sink: list = []

        @contextmanager
        def _tracking():
            order.append("lock-open")
            yield _Connection(sink)
            order.append("lock-close")

        middleware = BuiltinWriteLockMiddleware(context=_context())

        with patch(CONNECTION, _tracking):
            middleware.wrap_tool_call(
                _request("task_register"), lambda r: order.append("handler") or "done"
            )

        self.assertEqual(order, ["lock-open", "handler", "lock-close"])


class NotLockedTests(SimpleTestCase):
    def test_read_tool_is_not_locked(self):
        sink: list = []
        middleware = BuiltinWriteLockMiddleware(context=_context())

        with patch(CONNECTION, lambda: _fake_connection(sink)):
            result = middleware.wrap_tool_call(_request("document_search"), lambda r: "read")

        self.assertEqual(result, "read")
        self.assertEqual(sink, [])

    def test_mcp_tool_is_not_locked(self):
        """MCP는 직렬화하지 않고 승인 카드 경고로 다룬다(`2026-08-21_04`) —
        최대 480초짜리 호출을 락을 쥔 채 기다리면 대기하는 호출마다 DB
        커넥션을 그만큼 붙잡는다."""
        sink: list = []
        middleware = BuiltinWriteLockMiddleware(context=_context())

        with patch(CONNECTION, lambda: _fake_connection(sink)):
            result = middleware.wrap_tool_call(_request("mcp__MT001"), lambda r: "mcp")

        self.assertEqual(result, "mcp")
        self.assertEqual(sink, [])

    def test_missing_project_id_passes_through(self):
        """잠글 대상이 없다. 도구 자신이 "프로젝트를 먼저 고르세요"로 되돌릴
        것이므로 여기서 가로채지 않는다 — 막으면 그 사유가 사라진다."""
        sink: list = []
        middleware = BuiltinWriteLockMiddleware(context=_context(project_id=None))

        with patch(CONNECTION, lambda: _fake_connection(sink)):
            result = middleware.wrap_tool_call(_request("task_register"), lambda r: "done")

        self.assertEqual(result, "done")
        self.assertEqual(sink, [])


class BuilderTests(SimpleTestCase):
    def test_builder_returns_configured_middleware(self):
        context = _context()

        middleware = build_builtin_write_lock(context=context)

        self.assertIsInstance(middleware, BuiltinWriteLockMiddleware)
        self.assertIs(middleware._context, context)
