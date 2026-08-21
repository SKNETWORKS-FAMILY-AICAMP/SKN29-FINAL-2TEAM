"""tracing/__init__.py(trace_events) 단위 테스트.

`AgentRunRepository`/`ToolCallRepository`는 mock한다 — DB는 안 띄운다(레거시
`services.harness.trace`를 테스트하는 `tests/test_harness.py`와 같은 방식,
`services.agent_runtime.tracing.AgentRunRepository`처럼 **쓰는 모듈**을 patch
한다).
"""

from types import SimpleNamespace
from unittest.mock import call, patch

from django.test import SimpleTestCase, override_settings

from services.agent_runtime.events import EVENT_AWAITING_CONFIRMATION, EVENT_ERROR, EVENT_RESULT
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


def _awaiting_confirmation(**overrides):
    event = {
        "type": EVENT_AWAITING_CONFIRMATION,
        "run_id": "RUN-ROOT",
        "agent_id": "AG001",
        "agent_version_id": "AV001",
        "interrupt_id": "intr-1",
        "action_requests": [{"name": "task_register", "args": {}}],
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
            resolved_provider=None,
            resolved_endpoint_hash=None,
        )

    def test_resolved_provider_and_endpoint_hash_are_read_from_the_event(self, runs, _calls):
        """2026-08-19, §4순위(Run Snapshot) — `executor.py`가 `EVENT_AGENT_STARTED`에
        실어 보낸 값이 그대로 `start_with_id()`로 전달되는지."""
        list(
            trace_events(
                iter(
                    [
                        _agent_started(
                            resolved_provider="openai_compatible",
                            resolved_endpoint_hash="abc123",
                        )
                    ]
                ),
                context=_context(session_id="S1"),
            )
        )

        self.assertEqual(runs.start_with_id.call_args.kwargs["resolved_provider"], "openai_compatible")
        self.assertEqual(runs.start_with_id.call_args.kwargs["resolved_endpoint_hash"], "abc123")

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
            resolved_provider=None,
            resolved_endpoint_hash=None,
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


@patch(f"{MODULE}.ToolCallRepository")
@patch(f"{MODULE}.AgentRunRepository")
class AwaitingConfirmationSuspendTests(SimpleTestCase):
    """`EVENT_AWAITING_CONFIRMATION` → `AgentRunRepository.suspend()`
    (2026-08-19 추가, §0순위 — HITL resume API). `finish()`가 아니라 `suspend()`를
    불러야 한다 — 끝난 게 아니라 사람의 승인/거부를 기다리는 것뿐이므로."""

    def test_awaiting_confirmation_calls_suspend_not_finish(self, runs, _calls):
        list(trace_events(iter([_agent_started(), _awaiting_confirmation()]), context=_context()))

        runs.suspend.assert_called_once_with(run_id="RUN-ROOT")
        runs.finish.assert_not_called()

    def test_awaiting_confirmation_removes_run_from_open_run_ids(self, runs, _calls):
        """이 스트림 기준으로는 더 이상 '열려' 있지 않다 — 스트림이 여기서
        끝나도(정상 종료) `_close_orphans()`가 이 run을 FAILED로 잘못
        정리하면 안 된다."""
        gen = trace_events(iter([_agent_started(), _awaiting_confirmation()]), context=_context())
        list(gen)  # 정상 소진 — finally의 _close_orphans()까지 실행됨

        runs.suspend.assert_called_once_with(run_id="RUN-ROOT")
        runs.finish.assert_not_called()  # _close_orphans()가 이걸 FAILED로 안 닫는다

    def test_awaiting_confirmation_for_unstarted_run_is_skipped(self, runs, _calls):
        """agent_started 없이(또는 agent_id 없어 기록 안 된 run) 바로
        awaiting_confirmation이 오면 — 그 run_id가 open_run_ids에 없으니
        조용히 건너뛴다."""
        list(trace_events(iter([_awaiting_confirmation(run_id="RUN-NEVER-STARTED")]), context=_context()))

        runs.suspend.assert_not_called()

    def test_event_passes_through_unchanged(self, runs, _calls):
        events = [_agent_started(), _awaiting_confirmation()]

        seen = list(trace_events(iter(events), context=_context()))

        self.assertEqual(seen, events)


@patch(f"{MODULE}.ToolCallRepository")
@patch(f"{MODULE}.AgentRunRepository")
class KnownRunIdsResumeTests(SimpleTestCase):
    """`known_run_ids`(2026-08-19 추가, §0순위) — 재개 스트림은
    `EVENT_AGENT_STARTED`를 다시 안 내므로, 멈췄던 실행의 run_id를 미리
    채워 둬야 `EVENT_RESULT`/`EVENT_ERROR`가 왔을 때 그 run을 닫을 수 있다."""

    def test_without_known_run_ids_a_resumed_result_cannot_close_the_run(self, runs, _calls):
        """대조군: known_run_ids 없이 result만 오면(agent_started 없이) —
        _finish_root_run()이 '내가 시작한 run이 아니다'로 보고 못 닫는다.
        이게 바로 known_run_ids 없이는 §0순위가 동작하지 않는 이유다."""
        list(trace_events(iter([_result()]), context=_context()))

        runs.finish.assert_not_called()

    def test_known_run_ids_lets_a_resumed_result_close_the_run(self, runs, _calls):
        list(
            trace_events(
                iter([_result()]), context=_context(), known_run_ids=("RUN-ROOT",)
            )
        )

        runs.finish.assert_called_once_with(
            run_id="RUN-ROOT", status="DONE", iterations=0, token_in=None, token_out=None
        )

    def test_known_run_ids_lets_a_resumed_error_close_the_run_as_failed(self, runs, _calls):
        list(
            trace_events(
                iter([_error()]), context=_context(), known_run_ids=("RUN-ROOT",)
            )
        )

        runs.finish.assert_called_once_with(
            run_id="RUN-ROOT", status="FAILED", iterations=0, token_in=None, token_out=None
        )

    def test_known_run_ids_default_is_empty(self, runs, _calls):
        """기본값(재개가 아닌 일반 run())은 이전과 동일하게 동작한다 — 이
        파라미터를 추가하기 전 회귀가 없어야 한다."""
        list(trace_events(iter([_agent_started(), _result()]), context=_context()))

        runs.start_with_id.assert_called_once()
        runs.finish.assert_called_once_with(
            run_id="RUN-ROOT", status="DONE", iterations=0, token_in=None, token_out=None
        )


@patch(f"{MODULE}.ToolCallRepository")
@patch(f"{MODULE}.AgentRunRepository")
class RunUsageTests(SimpleTestCase):
    """끝나는 이벤트가 실어 온 회전 수·토큰을 그대로 적는가(2026-08-21).

    누계를 세는 곳은 `events.py`의 `EventMapper`다 — 이 모듈은 변환된
    이벤트만 보므로 원시 `AIMessage`의 `usage_metadata`에 닿지 못한다.
    """

    def test_result_usage_is_written_to_agent_run(self, runs, _calls):
        events = [_agent_started(), _result(iterations=3, token_in=1200, token_out=340)]

        list(trace_events(iter(events), context=_context()))

        runs.finish.assert_called_once_with(
            run_id="RUN-ROOT", status="DONE", iterations=3, token_in=1200, token_out=340
        )

    def test_failed_run_still_records_the_tokens_it_already_spent(self, runs, _calls):
        """실패해도 비용은 이미 나갔다 — 실패만 비면 Usage 합계가 실제보다 작아진다."""
        events = [_agent_started(), _error(iterations=2, token_in=900, token_out=10)]

        list(trace_events(iter(events), context=_context()))

        runs.finish.assert_called_once_with(
            run_id="RUN-ROOT", status="FAILED", iterations=2, token_in=900, token_out=10
        )

    def test_subagent_usage_is_written_to_the_child_run(self, runs, _calls):
        events = [
            _subagent_started(),
            _subagent_completed(status="DONE", iterations=1, token_in=500, token_out=60),
        ]

        list(trace_events(iter(events), context=_context()))

        runs.finish.assert_called_once_with(
            run_id="RUN-CHILD", status="DONE", iterations=1, token_in=500, token_out=60
        )

    def test_tokens_stay_none_when_the_event_does_not_carry_them(self, runs, _calls):
        """usage를 못 받은 실행은 0이 아니라 None이다 — 「안 쟀다」와 「안 썼다」는 다르다."""
        events = [_agent_started(), _result(iterations=4)]

        list(trace_events(iter(events), context=_context()))

        runs.finish.assert_called_once_with(
            run_id="RUN-ROOT", status="DONE", iterations=4, token_in=None, token_out=None
        )

