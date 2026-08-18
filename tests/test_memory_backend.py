"""memory/backend.py 단위 테스트.

정본: docs/작업기록/Deep_Agents/2026-08-13_04_작업자B_실행코어_세부계획.md §4-8, §5 Phase 3

2026-08-18, Phase 3 이전에는 이 파일이 없었다 — `build_memory_backend()`가
`account_id`를 받지 않고 팀·에이전트 단위 공유 namespace 하나만 만들었기 때문에
검증할 "격리"가 없었다. Phase 3에서 계정 전용 namespace(`/memories/users/`)가
추가되면서, §5 Phase 3의 검증 기준("사용자 A/B가 서로 다른 내용을 쓰고, 서로
상대방 것을 못 읽는지")을 실제 `CompositeBackend`/`StoreBackend` 객체로 확인한다
(deepagents를 mock하지 않음 — namespace 튜플이 실제로 갈리는지가 핵심이라
Fake로는 이 회귀를 못 잡는다).
"""

from django.test import SimpleTestCase

from services.agent_runtime.memory.backend import (
    MEMORY_FILE,
    MEMORY_PATH_PREFIX,
    MEMORY_USERS_PATH_PREFIX,
    build_memory_backend,
    memory_paths,
    memory_system_prompt,
)


class ConstantsTests(SimpleTestCase):
    def test_users_prefix_is_nested_under_shared_prefix(self):
        self.assertTrue(MEMORY_USERS_PATH_PREFIX.startswith(MEMORY_PATH_PREFIX))

    def test_memory_file_lives_under_shared_prefix_not_users_prefix(self):
        """AGENTS.md는 여전히 공유 route(§4-8 "4. memory_paths()는 변경 없음")다."""
        self.assertTrue(MEMORY_FILE.startswith(MEMORY_PATH_PREFIX))
        self.assertFalse(MEMORY_FILE.startswith(MEMORY_USERS_PATH_PREFIX))


class MemoryPathsTests(SimpleTestCase):
    def test_returns_agents_md_only(self):
        self.assertEqual(memory_paths(), [MEMORY_FILE])


class BuildMemoryBackendTests(SimpleTestCase):
    def test_routes_cover_shared_and_personal_prefixes(self):
        backend = build_memory_backend(team_id="TM001", agent_id="AG001", account_id="AC001")

        self.assertEqual(set(backend.routes.keys()), {MEMORY_PATH_PREFIX, MEMORY_USERS_PATH_PREFIX})

    def test_personal_route_is_matched_before_shared_route(self):
        """CompositeBackend는 route를 prefix 길이 기준 내림차순으로 매칭한다
        (deepagents/backends/composite.py의 `sorted_routes` 실제 소스로 확인) —
        `/memories/users/...`가 `/memories/...`보다 먼저 매칭돼야 한다."""

        backend = build_memory_backend(team_id="TM001", agent_id="AG001", account_id="AC001")

        self.assertEqual(backend.sorted_routes[0][0], MEMORY_USERS_PATH_PREFIX)

    def test_shared_namespace_excludes_account_id(self):
        """팀·에이전트 공유 메모리는 계정과 무관하게 같은 namespace를 써야 한다."""

        backend = build_memory_backend(team_id="TM001", agent_id="AG001", account_id="AC001")

        shared = backend.routes[MEMORY_PATH_PREFIX]
        self.assertEqual(shared._namespace(None), ("TM001", "AG001"))

    def test_personal_namespace_includes_account_id(self):
        backend = build_memory_backend(team_id="TM001", agent_id="AG001", account_id="AC001")

        personal = backend.routes[MEMORY_USERS_PATH_PREFIX]
        self.assertEqual(personal._namespace(None), ("TM001", "AG001", "AC001"))

    def test_different_accounts_get_isolated_personal_namespaces(self):
        """§5 Phase 3 검증 기준 그대로 — 사용자 A/B가 서로 다른 namespace를 받아야
        서로의 개인 메모리를 못 읽는다(namespace가 다르면 StoreBackend는 아예
        다른 저장 공간을 본다)."""

        backend_a = build_memory_backend(team_id="TM001", agent_id="AG001", account_id="AC001")
        backend_b = build_memory_backend(team_id="TM001", agent_id="AG001", account_id="AC002")

        namespace_a = backend_a.routes[MEMORY_USERS_PATH_PREFIX]._namespace(None)
        namespace_b = backend_b.routes[MEMORY_USERS_PATH_PREFIX]._namespace(None)
        self.assertNotEqual(namespace_a, namespace_b)

    def test_default_backend_is_state_backend(self):
        """`/memories/`, `/memories/users/` 외 경로는 여전히 휘발성 StateBackend."""
        from deepagents.backends import StateBackend

        backend = build_memory_backend(team_id="TM001", agent_id="AG001", account_id="AC001")

        self.assertIsInstance(backend.default, StateBackend)


class MemorySystemPromptTests(SimpleTestCase):
    def test_includes_deepagents_default_template(self):
        from deepagents.middleware.memory import MEMORY_SYSTEM_PROMPT

        self.assertIn(MEMORY_SYSTEM_PROMPT, memory_system_prompt())

    def test_appends_routing_guidance(self):
        self.assertIn("Memory routing", memory_system_prompt())
        self.assertIn("/memories/users/", memory_system_prompt())

    def test_still_contains_agent_memory_slot(self):
        """`MemoryMiddleware.__init__`이 요구하는 `{agent_memory}` 슬롯이 라우팅
        안내를 덧붙인 뒤에도 남아있어야 한다 — 없으면 ValueError."""

        self.assertIn("{agent_memory}", memory_system_prompt())

    def test_is_a_valid_memory_middleware_system_prompt(self):
        """실제 `MemoryMiddleware` 생성자에 그대로 넘겨도 예외 없이 만들어지는지."""
        from unittest.mock import Mock

        from deepagents import MemoryMiddleware

        MemoryMiddleware(backend=Mock(), sources=[MEMORY_FILE], system_prompt=memory_system_prompt())

    def test_survives_actual_format_agent_memory_call(self):
        """2026-08-18 회귀 테스트 — `MemoryMiddleware.__init__`이 요구하는
        `{agent_memory}` 슬롯 존재 여부만으로는 부족하다. `_format_agent_memory()`는
        전체 문자열을 실제 `str.format(agent_memory=...)`로 처리하므로, 라우팅
        안내문 안에 이스케이프 안 된 `{project_id}` 같은 다른 중괄호가 섞여
        있으면 `KeyError`로 죽는다 — 생성자 검사는 이걸 못 잡는다.
        `agent_tool_selection_live_check.py`로 실제 `AgentRuntimeFactory.build()`
        파이프라인을 끝까지 돌려 보다가 이 실패를 재현했다."""
        from unittest.mock import Mock

        from deepagents import MemoryMiddleware

        middleware = MemoryMiddleware(
            backend=Mock(), sources=[MEMORY_FILE], system_prompt=memory_system_prompt()
        )

        formatted = middleware._format_agent_memory({}, template=middleware.system_prompt)

        self.assertIn("(No memory loaded)", formatted)
