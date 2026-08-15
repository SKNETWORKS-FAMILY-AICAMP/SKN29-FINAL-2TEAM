"""tracing/__init__.py(trace_events) 단위 테스트.

`AgentRunRepository`/`ToolCallRepository`는 mock한다 — DB는 안 띄운다(레거시
`services.harness.trace`를 테스트하는 `tests/test_harness.py`와 같은 방식,
`services.agent_runtime.tracing.AgentRunRepository`처럼 **쓰는 모듈**을 patch
한다).
"""

from types import SimpleNamespace
from unittest.mock import call, patch

from django.test import SimpleTestCase, override_settings

from services.agent_runtime.events import EVENT_ERROR, EVENT_RESULT
from services.agent_runtime.tracing import trace_events

MODULE = "services.agent_runtime.tracing"


def _context(*, session_id="SESSION-1", parent_run_id=None):
    return SimpleNamespace(session_id=session_id, parent_run_id=parent_run_id)


def _agent_started(**overrides):
    event = {
        "type": "agent_started",
        "run_id": "RUN-ROOT",
        "agent_id": "AG001",
        "agent_version_id": "AV001",
        "complete": False,
    }
    event.update(overrides)
    return event


def _result(**overrides):
    event = {"type": EVENT_RESULT, "text": "답", "run_id": "RUN-ROOT", "complete": True}
    event.update(overrides)
    return event


def _error(**overrides):
    event = {
        "type": EVENT_ERROR,
        "error_code": "AGENT_EXECUTION_FAILED",
        "message": "실패",
        "run_id": "RUN-ROOT",
        "complete": True,
    }
    event.update(overrides)
    return event


def _subagent_started(**overrides):
    event = {
        "type": "subagent_started",
        "run_id": "RUN-CHILD",
        "parent_run_id": "RUN-ROOT",
        "agent_id": "AG011",
        "agent_version_id": "AV023",
        "subagent_alias": "jira_writer",
        "subagent_name": "Jira 등록 에이전트",
        "task_summary": "...",
        "complete": False,
    }
    event.update(overrides)
    return event


def _subagent_completed(**overrides):
    event = {
        "type": "subagent_completed",
        "run_id": "RUN-CHILD",
        "parent_run_id": "RUN-ROOT",
        "agent_id": "AG011",
        "agent_version_id": "AV023",
        "subagent_alias": "jira_writer",
        "subagent_name": "Jira 등록 에이전트",
        "status": "DONE",
        "complete": False,
    }
    event.update(overrides)
    return event


def _tool_started(**overrides):
    event = {
        "type": "tool_started",
        "run_id": "RUN-ROOT",
        "subagent_alias": None,
        "tool_ref": "document_search",
        "tool_call_id": "call-1",
        "arguments": {"query": "일정"},
        "complete": False,
    }
    event.update(overrides)
    return event


def _tool_completed(**overrides):
    event = {
        "type": "tool_completed",
        "run_id": "RUN-ROOT",
        "subagent_alias": None,
        "tool_ref": "document_search",
        "tool_call_id": "call-1",
        "status": "OK",
        "complete": False,
    }
    event.update(overrides)
    return event


@patch(f"{MODULE}.ToolCallRepository")
@patch(f"{MODULE}.AgentRunRepository")
class RootRunLifecycleTests(SimpleTestCase):
    def test_agent_started_opens_run_with_start_with_id(self, runs, _calls):
        list(trace_events(iter([_agent_started()]), context=_context(session_id="S1")))

        runs.start_with_id.assert_called_once_with(
            run_id="RUN-ROOT",
            agent_id="AG001",
            session_id="S1",
            parent_run_id=None,
            agent_version_id="AV001",
            runtime_profile_version=None,
        )

    def test_result_closes_run_as_done(self, runs, _calls):
        list(trace_events(iter([_agent_started(), _result()]), context=_context()))

        runs.finish.assert_called_once_with(
            run_id="RUN-ROOT", status="DONE", iterations=0, token_in=None, token_out=None
        )

    def test_error_closes_run_as_failed(self, runs, _calls):
        list(trace_events(iter([_agent_started(), _error()]), context=_context()))

        runs.finish.assert_called_once_with(
            run_id="RUN-ROOT", status="FAILED", iterations=0, token_in=None, token_out=None
        )

    def test_events_pass_through_unchanged(self, runs, calls):
        runs.start_with_id.return_value = "RUN-ROOT"
        events = [_agent_started(), _result()]

        seen = list(trace_events(iter(events), context=_context()))

        self.assertEqual(seen, events)

    def test_agent_started_without_agent_id_is_not_logged(self, runs, calls):
        """agent_id 없는 draft 시험 실행 — agent_run.agent_id는 NOT NULL이라
        기록하지 않는다(harness run_ephemeral()과 같은 이유)."""
        events = [_agent_started(agent_id=None), _result()]

        list(trace_events(iter(events), context=_context()))

        runs.start_with_id.assert_not_called()
        runs.finish.assert_not_called()

    @override_settings(RUNTIME_PROFILE_VERSION="abc1234")
    def test_runtime_profile_version_is_read_from_settings(self, runs, _calls):
        list(trace_events(iter([_agent_started()]), context=_context()))

        self.assertEqual(runs.start_with_id.call_args.kwargs["runtime_profile_version"], "abc1234")


@patch(f"{MODULE}.ToolCallRepository")
@patch(f"{MODULE}.AgentRunRepository")
class SubagentRunLifecycleTests(SimpleTestCase):
    def test_subagent_started_opens_run_with_parent_run_id_from_event(self, runs, _calls):
        list(trace_events(iter([_subagent_started()]), context=_context()))

        runs.start_with_id.assert_called_once_with(
            run_id="RUN-CHILD",
            agent_id="AG011",
            session_id="SESSION-1",
            parent_run_id="RUN-ROOT",
            agent_version_id="AV023",
            runtime_profile_version=None,
        )

    def test_subagent_completed_done_closes_run_as_done(self, runs, _calls):
        list(trace_events(iter([_subagent_started(), _subagent_completed(status="DONE")]), context=_context()))

        runs.finish.assert_called_once_with(
            run_id="RUN-CHILD", status="DONE", iterations=0, token_in=None, token_out=None
        )

    def test_subagent_completed_failed_closes_run_as_failed(self, runs, _calls):
        list(trace_events(iter([_subagent_started(), _subagent_completed(status="FAILED")]), context=_context()))

        runs.finish.assert_called_once_with(
            run_id="RUN-CHILD", status="FAILED", iterations=0, token_in=None, token_out=None
        )


@patch(f"{MODULE}.ToolCallRepository")
@patch(f"{MODULE}.AgentRunRepository")
class ToolCallLifecycleTests(SimpleTestCase):
    def test_tool_started_begins_tool_call_with_summarized_arguments(self, runs, calls):
        calls.begin.return_value = "TC-1"

        list(trace_events(iter([_agent_started(), _tool_started()]), context=_context()))

        calls.begin.assert_called_once_with(
            run_id="RUN-ROOT", tool_ref="document_search", input_summary="query=일정"
        )

    def test_tool_completed_ends_tool_call_ok(self, runs, calls):
        calls.begin.return_value = "TC-1"

        list(
            trace_events(
                iter([_agent_started(), _tool_started(), _tool_completed(status="OK")]),
                context=_context(),
            )
        )

        calls.end.assert_called_once()
        kwargs = calls.end.call_args.kwargs
        self.assertEqual(kwargs["tool_call_id"], "TC-1")
        self.assertEqual(kwargs["status"], "OK")
        self.assertIsNone(kwargs["error_code"])

    def test_tool_completed_ends_tool_call_failed_with_error_code(self, runs, calls):
        calls.begin.return_value = "TC-1"

        list(
            trace_events(
                iter([_agent_started(), _tool_started(), _tool_completed(status="FAILED")]),
                context=_context(),
            )
        )

        kwargs = calls.end.call_args.kwargs
        self.assertEqual(kwargs["status"], "FAILED")
        self.assertEqual(kwargs["error_code"], "TOOL_EXECUTION_FAILED")

    def test_tool_started_without_tool_call_id_is_skipped(self, runs, calls):
        list(
            trace_events(
                iter([_agent_started(), _tool_started(tool_call_id=None)]),
                context=_context(),
            )
        )

        calls.begin.assert_not_called()

    def test_tool_started_for_unlogged_run_is_skipped(self, runs, calls):
        """agent_started가 agent_id 없어서 기록 안 된 run — 그 run의 tool_started도
        자동으로 같이 건너뛴다."""
        list(
            trace_events(
                iter([_agent_started(agent_id=None), _tool_started()]),
                context=_context(),
            )
        )

        calls.begin.assert_not_called()


@patch(f"{MODULE}.ToolCallRepository")
@patch(f"{MODULE}.AgentRunRepository")
class StreamCloseCleanupTests(SimpleTestCase):
    """스트림이 result/error 없이 중간에 닫히면(GeneratorExit) 열린 행을 정리한다."""

    def test_early_close_marks_open_run_failed(self, runs, _calls):
        gen = trace_events(iter([_agent_started()]), context=_context())
        next(gen)  # agent_started만 소비 — 아직 result/error 안 옴
        gen.close()

        runs.finish.assert_called_once_with(
            run_id="RUN-ROOT", status="FAILED", iterations=0, token_in=None, token_out=None
        )

    def test_early_close_marks_open_tool_call_failed(self, runs, calls):
        calls.begin.return_value = "TC-1"

        gen = trace_events(iter([_agent_started(), _tool_started()]), context=_context())
        next(gen)
        next(gen)
        gen.close()

        calls.end.assert_called_once()
        kwargs = calls.end.call_args.kwargs
        self.assertEqual(kwargs["tool_call_id"], "TC-1")
        self.assertEqual(kwargs["status"], "FAILED")
        self.assertEqual(kwargs["error_code"], "STREAM_CLOSED")


@patch(f"{MODULE}.ToolCallRepository")
@patch(f"{MODULE}.AgentRunRepository")
class TracingFailureIsolationTests(SimpleTestCase):
    """적재 실패가 사용자에게 가는 실제 이벤트 전달을 끊으면 안 된다."""

    def test_db_failure_during_record_does_not_break_event_passthrough(self, runs, _calls):
        runs.start_with_id.side_effect = RuntimeError("DB 연결 실패")
        events = [_agent_started(), _result()]

        seen = list(trace_events(iter(events), context=_context()))

        self.assertEqual(seen, events)
