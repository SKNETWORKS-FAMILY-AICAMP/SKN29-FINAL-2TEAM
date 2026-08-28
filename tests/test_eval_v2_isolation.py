"""S10/S11 평가 provider가 운영 저장소 없이 scope를 분리하는지 검증한다."""

from django.test import SimpleTestCase

from services.evaluation.v2_isolation import EvalCheckpointProvider, EvalMemoryProvider


class EvalMemoryProviderTests(SimpleTestCase):
    def setUp(self):
        self.provider = EvalMemoryProvider()

    def test_same_namespace_reads_seeded_preferences(self):
        self.provider.seed_preferences(
            team_id="TM001", agent_id="AG004", account_id="UA001", content="문장 형식 선호"
        )

        content = self.provider.preference_content(
            team_id="TM001", agent_id="AG004", account_id="UA001"
        )

        self.assertEqual(content, "문장 형식 선호")

    def test_different_account_cannot_read_seeded_preferences(self):
        self.provider.seed_preferences(
            team_id="TM001", agent_id="AG004", account_id="UA001", content="금지 canary"
        )

        content = self.provider.preference_content(
            team_id="TM001", agent_id="AG004", account_id="UA002"
        )

        self.assertIsNone(content)

    def test_different_team_or_agent_cannot_read_seeded_preferences(self):
        self.provider.seed_preferences(
            team_id="TM001", agent_id="AG004", account_id="UA001", content="금지 canary"
        )

        self.assertIsNone(
            self.provider.preference_content(
                team_id="TM002", agent_id="AG004", account_id="UA001"
            )
        )
        self.assertIsNone(
            self.provider.preference_content(
                team_id="TM001", agent_id="AG999", account_id="UA001"
            )
        )

    def test_cleanup_deletes_only_the_requested_namespace(self):
        for account_id in ("UA001", "UA002"):
            self.provider.seed_preferences(
                team_id="TM001", agent_id="AG004", account_id=account_id, content=account_id
            )

        self.provider.delete_preferences(
            team_id="TM001", agent_id="AG004", account_id="UA001"
        )

        self.assertIsNone(
            self.provider.preference_content(
                team_id="TM001", agent_id="AG004", account_id="UA001"
            )
        )
        self.assertEqual(
            self.provider.preference_content(
                team_id="TM001", agent_id="AG004", account_id="UA002"
            ),
            "UA002",
        )

    def test_backend_route_uses_the_same_in_memory_store(self):
        backend = self.provider.backend(
            team_id="TM001", agent_id="AG004", account_id="UA001"
        )

        route = backend.routes["/memories/users/"]

        self.assertIs(route.store, self.provider.store())
        self.assertEqual(route._namespace(None), ("TM001", "AG004", "UA001"))


class EvalCheckpointProviderTests(SimpleTestCase):
    def test_returns_one_saver_and_exact_thread_cleanup_is_safe(self):
        provider = EvalCheckpointProvider()

        self.assertIs(provider.get(), provider.get())
        provider.delete_thread("S10-NOT-YET-CREATED")

    def test_seeded_message_is_visible_only_in_its_thread(self):
        from langgraph.graph import START, MessagesState, StateGraph

        provider = EvalCheckpointProvider()
        builder = StateGraph(MessagesState)
        builder.add_node("noop", lambda state: {})
        builder.add_edge(START, "noop")
        runtime = builder.compile(checkpointer=provider.get())

        provider.seed_messages(
            runtime, thread_id="S10-SOURCE", messages=["임시 코드명 CHECKPOINT_CANARY"]
        )

        self.assertTrue(
            provider.contains_text(thread_id="S10-SOURCE", text="CHECKPOINT_CANARY")
        )
        self.assertFalse(
            provider.contains_text(thread_id="S10-TARGET", text="CHECKPOINT_CANARY")
        )

        provider.delete_thread("S10-SOURCE")
        self.assertFalse(
            provider.contains_text(thread_id="S10-SOURCE", text="CHECKPOINT_CANARY")
        )
