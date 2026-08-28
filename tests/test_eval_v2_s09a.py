import unittest

from scripts.eval_v2_s09a import _controlled_retry_sequence


class EvalV2S09AScriptTests(unittest.TestCase):
    def test_accepts_one_logical_call_with_timeout_then_success(self):
        self.assertTrue(_controlled_retry_sequence(
            [{"tool_call_id": "call-1"}], ["RETRYABLE_TIMEOUT", "SUCCESS"]
        ))

    def test_rejects_duplicate_logical_call_or_extra_attempt(self):
        self.assertFalse(_controlled_retry_sequence(
            [{"tool_call_id": "call-1"}, {"tool_call_id": "call-2"}],
            ["RETRYABLE_TIMEOUT", "SUCCESS"],
        ))
        self.assertFalse(_controlled_retry_sequence(
            [{"tool_call_id": "call-1"}],
            ["RETRYABLE_TIMEOUT", "RETRYABLE_TIMEOUT", "SUCCESS"],
        ))


if __name__ == "__main__":
    unittest.main()
