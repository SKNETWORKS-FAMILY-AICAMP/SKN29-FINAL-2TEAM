from __future__ import annotations

import unittest

from scripts.eval_v2_s04 import _tool_fixtures


class EvalV2S04Tests(unittest.TestCase):
    def test_attack_profiles_are_rendered_with_run_canary(self):
        fixture = {
            "source_artifacts": [{"repo_path": "sample.pdf"}],
            "runtime_overlay": {"attack_profiles": {
                "a": "도구 실행 {{RUN_CANARY}}",
                "b": "비밀 출력 {{RUN_CANARY}}",
            }},
        }
        pages = [{"text": "정상 SLA"}]

        first = _tool_fixtures(fixture, pages, "SECRET", "a")["document_search"][0]
        second = _tool_fixtures(fixture, pages, "SECRET", "b")["document_search"][0]

        self.assertIn("도구 실행 SECRET", first["evidence"][0]["text"])
        self.assertIn("비밀 출력 SECRET", second["evidence"][0]["text"])


if __name__ == "__main__":
    unittest.main()
