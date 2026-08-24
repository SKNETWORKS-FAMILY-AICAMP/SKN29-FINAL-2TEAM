"""외부 관측 백엔드 콜백 구성 계약을 검증한다."""

from importlib.metadata import version
from unittest.mock import patch

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
