"""skills/provider.py(SkillsProvider) 단위 테스트 — `test_memory_provider.py`와 같은 패턴.

"SkillsProvider가 skills/backend.py의 실제 함수를 그대로 호출·전달하는가"만
검증한다 — 각 함수 자체의 행동은 test_skills_backend.py의 몫이다.
"""

from django.test import SimpleTestCase

from services.agent_runtime.skills.provider import SkillsProvider


class SourcesTests(SimpleTestCase):
    def test_delegates_to_skill_sources(self):
        from services.agent_runtime.skills.backend import skill_sources

        self.assertEqual(SkillsProvider().sources(), skill_sources())


class RoutesTests(SimpleTestCase):
    def test_passes_account_and_team_id_through(self):
        from services.agent_runtime.skills.backend import SKILLS_PERSONAL_PATH_PREFIX, personal_namespace

        routes = SkillsProvider().routes(account_id="AC001", team_id="TM001")

        self.assertEqual(
            routes[SKILLS_PERSONAL_PATH_PREFIX]._namespace(None), personal_namespace("AC001")
        )


class SystemPromptTests(SimpleTestCase):
    def test_delegates_to_skills_system_prompt(self):
        from services.agent_runtime.skills.backend import skills_system_prompt

        self.assertEqual(SkillsProvider().system_prompt(), skills_system_prompt())
