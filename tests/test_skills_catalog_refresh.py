"""revision이 바뀐 턴에만 스킬 Store를 다시 읽는다."""

from unittest.mock import patch

from django.test import SimpleTestCase
from langgraph.store.memory import InMemoryStore

from services.agent_runtime.skills.catalog_refresh import SkillCatalogRefreshMiddleware


class CatalogRefreshTests(SimpleTestCase):
    def _middleware(self):
        from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
        from services.agent_runtime.skills.service import _render_skill_md

        store = InMemoryStore()
        inner = StoreBackend(namespace=lambda _rt: ("skill", "personal", "AC001"), store=store)
        inner.write(
            "/new-skill/SKILL.md",
            _render_skill_md(name="new-skill", description="새 작업에 사용", body="절차"),
        )
        backend = CompositeBackend(default=StateBackend(), routes={"/skills/personal/": inner})
        return SkillCatalogRefreshMiddleware(
            backend=backend, sources=["/skills/personal/"], account_id="AC001"
        )

    @patch("services.agent_runtime.skills.versioning.catalog_revision", return_value=3)
    def test_첫_턴은_revision만_심고_중복_scan하지_않는다(self, _revision):
        update = self._middleware().before_agent({"skills_metadata": [{"name": "new-skill"}]}, None)
        self.assertEqual(update, {"skill_catalog_revision": 3})

    @patch("services.agent_runtime.skills.versioning.catalog_revision", return_value=3)
    def test_revision이_같으면_io가_없다(self, _revision):
        update = self._middleware().before_agent(
            {"skills_metadata": [{"name": "old-skill"}], "skill_catalog_revision": 3}, None
        )
        self.assertIsNone(update)

    @patch("services.agent_runtime.skills.versioning.catalog_revision", return_value=4)
    def test_revision이_바뀌면_최신_목록으로_교체한다(self, _revision):
        update = self._middleware().before_agent(
            {"skills_metadata": [{"name": "old-skill"}], "skill_catalog_revision": 3}, None
        )
        self.assertEqual([skill["name"] for skill in update["skills_metadata"]], ["new-skill"])
        self.assertEqual(update["skill_catalog_revision"], 4)

    @patch("services.agent_runtime.skills.versioning.catalog_revision", return_value=5)
    def test_100개가_넘는_catalog도_누락없이_교체한다(self, _revision):
        from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
        from services.agent_runtime.skills.service import _render_skill_md

        store = InMemoryStore()
        inner = StoreBackend(namespace=lambda _rt: ("skill", "personal", "AC001"), store=store)
        expected = []
        for index in range(105):
            name = f"catalog-skill-{index}"
            expected.append(name)
            inner.write(
                f"/{name}/SKILL.md",
                _render_skill_md(name=name, description=f"기능 {index}", body="절차"),
            )
        backend = CompositeBackend(default=StateBackend(), routes={"/skills/personal/": inner})
        middleware = SkillCatalogRefreshMiddleware(
            backend=backend, sources=["/skills/personal/"], account_id="AC001"
        )
        update = middleware.before_agent({"skills_metadata": [], "skill_catalog_revision": 4}, None)
        self.assertEqual(sorted(item["name"] for item in update["skills_metadata"]), sorted(expected))
