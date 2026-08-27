import unittest

import requests

from services.agent_runtime.skills.evaluation.stub_tools import (
    EVAL_FAULT_KEY,
    ToolCallRecorder,
    _make_stub_handler,
)
from services.agent_runtime.tools.loader import Tool


class EvaluationStubToolTests(unittest.TestCase):
    def test_retryable_timeout_is_raised_and_recorded_before_success(self):
        recorder = ToolCallRecorder()
        tool = Tool(
            ref="document_search", name="document_search", description="search",
            input_schema={"type": "object"}, handler=lambda **_kwargs: None,
            side_effect=False,
        )
        handler = _make_stub_handler(
            tool,
            fixtures=[{EVAL_FAULT_KEY: "RETRYABLE_TIMEOUT"}, {"evidence": []}],
            recorder=recorder,
        )

        with self.assertRaises(requests.exceptions.Timeout):
            handler(query="q")
        self.assertEqual(handler(query="q"), {"evidence": []})
        self.assertEqual(
            [call.outcome for call in recorder.calls], ["RETRYABLE_TIMEOUT", "SUCCESS"]
        )


if __name__ == "__main__":
    unittest.main()
