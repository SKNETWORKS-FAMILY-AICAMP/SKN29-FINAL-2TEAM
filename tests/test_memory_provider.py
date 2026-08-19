"""memory/provider.py(MemoryProvider) 단위 테스트.

"MemoryProvider가 memory/backend.py의 실제 함수를 그대로 호출·전달하는가"만
검증한다 — 각 함수 자체의 행동은 test_memory_backend.py의 몫이다(파일 docstring
관례는 test_deepagents_compat.py 등과 동일).
"""

from django.test import SimpleTestCase

from services.agent_runtime.memory.provider import MemoryProvider


class PathsTests(SimpleTestCase):
    def test_delegates_to_memory_paths(self):
        from services.agent_runtime.memory.backend import memory_paths

        self.assertEqual(MemoryProvider().paths(), memory_paths())


class BackendTests(SimpleTestCase):
    def test_passes_team_agent_account_id_through(self):
        backend = MemoryProvider().backend(team_id="TM001", agent_id="AG001", account_id="AC001")

        from services.agent_runtime.memory.backend import MEMORY_USERS_PATH_PREFIX

        self.assertEqual(
            backend.routes[MEMORY_USERS_PATH_PREFIX]._namespace(None), ("TM001", "AG001", "AC001")
        )


class SystemPromptTests(SimpleTestCase):
    def test_delegates_to_memory_system_prompt(self):
        from services.agent_runtime.memory.backend import memory_system_prompt

        self.assertEqual(MemoryProvider().system_prompt(), memory_system_prompt())
