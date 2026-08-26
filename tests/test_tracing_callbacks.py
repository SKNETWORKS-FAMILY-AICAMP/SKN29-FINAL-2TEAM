"""외부 관측 백엔드 콜백 구성 계약을 검증한다."""

from datetime import datetime, timezone
from importlib.metadata import version
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from django.test import SimpleTestCase, override_settings
from packaging.version import Version

from services.agent_runtime.tracing import callbacks


class LangfuseCallbackTests(SimpleTestCase):
    def setUp(self):
        callbacks._configured = False

    def tearDown(self):
        callbacks._configured = False

    def test_supported_sdk_major_is_installed(self):
        installed = Version(version("langfuse"))

        self.assertGreaterEqual(installed, Version("4.7"))
        self.assertLess(installed, Version("5"))

    @override_settings(
        LANGFUSE_PUBLIC_KEY="pk-lf-test",
        LANGFUSE_SECRET_KEY="sk-lf-test",
        LANGFUSE_HOST="https://jp.cloud.langfuse.com",
    )
    @patch("langfuse.Langfuse")
    def test_client_receives_explicit_settings_and_export_mask(self, langfuse_client):
        callbacks._ensure_client_configured()

        langfuse_client.assert_called_once_with(
            public_key="pk-lf-test",
            secret_key="sk-lf-test",
            host="https://jp.cloud.langfuse.com",
            mask=callbacks._mask_data,
        )

    @override_settings(LANGFUSE_PUBLIC_KEY="", LANGFUSE_SECRET_KEY="")
    def test_missing_keys_disable_callback(self):
        self.assertIsNone(callbacks.get_langfuse_callback())

    @override_settings(
        LANGFUSE_PUBLIC_KEY="pk-lf-test",
        LANGFUSE_SECRET_KEY="sk-lf-test",
    )
    @patch(
        "services.agent_runtime.tracing.callbacks._ensure_client_configured",
        side_effect=RuntimeError("Langfuse unavailable"),
    )
    def test_trace_initialization_failure_is_non_blocking(self, _configured):
        self.assertIsNone(
            callbacks.get_langfuse_trace(run_id="RUN001", metadata={"case_id": "CASE001"})
        )

    @override_settings(
        LANGFUSE_PUBLIC_KEY="pk-lf-test",
        LANGFUSE_SECRET_KEY="sk-lf-test",
    )
    @patch("langfuse.langchain.CallbackHandler")
    @patch("langfuse.get_client")
    def test_new_trace_creates_one_explicit_root(self, get_client, callback_handler):
        callbacks._configured = True
        root = SimpleNamespace(trace_id="TRACE001", id="ROOT001", end=MagicMock())
        get_client.return_value.start_observation.return_value = root
        callback = object()
        callback_handler.return_value = callback

        handle = callbacks.get_langfuse_trace(
            run_id="RUN001",
            metadata={"eval_run_id": "EVAL001", "case_id": "CASE001"},
        )

        self.assertEqual(handle.trace_id, "TRACE001")
        self.assertEqual(handle.root_observation_id, "ROOT001")
        self.assertIs(handle.callback, callback)
        get_client.return_value.start_observation.assert_called_once_with(
            name="agent-run",
            as_type="agent",
            metadata={"run_id": "RUN001", "eval_run_id": "EVAL001", "case_id": "CASE001"},
        )
        callback_handler.assert_called_once_with(
            trace_context={"trace_id": "TRACE001", "parent_span_id": "ROOT001"}
        )
        handle.finish()
        root.end.assert_called_once_with()

    @override_settings(
        LANGFUSE_PUBLIC_KEY="pk-lf-test",
        LANGFUSE_SECRET_KEY="sk-lf-test",
    )
    @patch("langfuse.langchain.CallbackHandler")
    @patch("langfuse.get_client")
    def test_resume_reuses_stored_trace_without_creating_root(
        self, get_client, callback_handler
    ):
        callbacks._configured = True

        handle = callbacks.get_langfuse_trace(
            run_id="RUN001",
            metadata={},
            resume_state={
                "langfuse_trace_id": "TRACE001",
                "langfuse_root_observation_id": "ROOT001",
            },
        )

        get_client.return_value.start_observation.assert_not_called()
        callback_handler.assert_called_once_with(
            trace_context={"trace_id": "TRACE001", "parent_span_id": "ROOT001"}
        )
        self.assertEqual(handle.trace_id, "TRACE001")
        handle.finish()

    @override_settings(
        LANGFUSE_PUBLIC_KEY="pk-lf-test",
        LANGFUSE_SECRET_KEY="sk-lf-test",
    )
    @patch(
        "services.agent_runtime.tracing.callbacks._utc_now",
        return_value=datetime(2026, 8, 26, 0, 0, 5, tzinfo=timezone.utc),
    )
    @patch("langfuse.langchain.CallbackHandler")
    @patch("langfuse.get_client")
    def test_resume_records_hitl_wait_metric(
        self, get_client, _callback_handler, _now
    ):
        callbacks._configured = True
        wait = MagicMock()
        get_client.return_value.start_observation.return_value = wait

        callbacks.get_langfuse_trace(
            run_id="RUN001",
            metadata={},
            resume_state={
                "langfuse_trace_id": "TRACE001",
                "langfuse_root_observation_id": "ROOT001",
                "langfuse_interrupted_at": "2026-08-26T00:00:00Z",
            },
        )

        get_client.return_value.start_observation.assert_called_once_with(
            name="hitl-wait",
            as_type="span",
            trace_context={"trace_id": "TRACE001", "parent_span_id": "ROOT001"},
            metadata={
                "kind": "human_approval_wait",
                "wait_started_at": "2026-08-26T00:00:00Z",
                "wait_resumed_at": "2026-08-26T00:00:05Z",
                "wait_duration_ms": 5000,
            },
        )
        wait.end.assert_called_once_with()

    @override_settings(
        LANGFUSE_PUBLIC_KEY="pk-lf-test",
        LANGFUSE_SECRET_KEY="sk-lf-test",
    )
    @patch("langfuse.get_client")
    def test_evaluation_result_is_attached_as_trace_score(self, get_client):
        callbacks._configured = True

        recorded = callbacks.record_langfuse_evaluation_result(
            trace_id="TRACE001",
            case_id="CASE001",
            status="FAILED",
            failed_assertions=["tool_call_limit"],
            environment="local-docker",
        )

        self.assertTrue(recorded)
        self.assertEqual(get_client.return_value.create_score.call_count, 2)
        get_client.return_value.create_score.assert_has_calls(
            [
                call(
                    trace_id="TRACE001",
                    name="deterministic-evaluation-status",
                    value="FAILED",
                    data_type="CATEGORICAL",
                    comment="tool_call_limit",
                    metadata={
                        "case_id": "CASE001",
                        "evaluator": "deterministic_code_assertions",
                    },
                    environment="local-docker",
                ),
                call(
                    trace_id="TRACE001",
                    name="deterministic-evaluation-failure",
                    value="tool_call_limit",
                    data_type="TEXT",
                    environment="local-docker",
                ),
            ]
        )

    @override_settings(
        LANGFUSE_PUBLIC_KEY="pk-lf-test",
        LANGFUSE_SECRET_KEY="sk-lf-test",
    )
    @patch("langfuse.get_client")
    def test_evaluation_score_failure_is_non_blocking(self, get_client):
        callbacks._configured = True
        get_client.return_value.create_score.side_effect = ConnectionError("unavailable")

        recorded = callbacks.record_langfuse_evaluation_result(
            trace_id="TRACE001",
            case_id="CASE001",
            status="FAILED",
            failed_assertions=["tool_call_limit"],
            environment="local-docker",
        )

        self.assertFalse(recorded)
