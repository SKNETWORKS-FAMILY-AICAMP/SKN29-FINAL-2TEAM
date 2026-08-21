"""skills/backend.py 단위 테스트 — memory/backend.py의 격리 검증과 같은 방식.

정본: docs/작업기록/Deep_Agents/2026-08-20_16_Skill_Middleware_설계.md

실제 `StoreBackend`/`CompositeBackend` 객체로 확인한다(deepagents를 mock하지
않음) — namespace 튜플이 실제로 갈리는지가 핵심이라 Fake로는 이 회귀를 못
잡는다(`test_memory_backend.py`와 같은 이유).
"""

from django.test import SimpleTestCase

from services.agent_runtime.skills.backend import (
    SKILLS_PERSONAL_PATH_PREFIX,
    SKILLS_TEAM_PATH_PREFIX,
    personal_namespace,
    skill_md_path,
    skill_routes,
    skill_sources,
)


class SkillSourcesTests(SimpleTestCase):
    def test_personal_before_team(self):
        """`SkillsMiddleware`는 나중 소스가 같은 이름의 스킬을 덮어쓴다 — 팀 스킬이
        더 넓은 합의를 거쳤으므로 이겨야 해서 팀을 뒤에 둔다(설계 문서 참고)."""
        self.assertEqual(
            skill_sources(), [SKILLS_PERSONAL_PATH_PREFIX, SKILLS_TEAM_PATH_PREFIX]
        )


class SkillMdPathTests(SimpleTestCase):
    def test_builds_skill_md_under_name_directory(self):
        self.assertEqual(
            skill_md_path(SKILLS_PERSONAL_PATH_PREFIX, "jira-issue-registration"),
            "/skills/personal/jira-issue-registration/SKILL.md",
        )


class SkillRoutesTests(SimpleTestCase):
    def test_routes_cover_both_prefixes(self):
        routes = skill_routes(account_id="AC001", team_id="TM001")

        self.assertEqual(set(routes.keys()), {SKILLS_PERSONAL_PATH_PREFIX, SKILLS_TEAM_PATH_PREFIX})

    def test_different_accounts_get_isolated_personal_namespaces(self):
        """계정 A/B가 서로 다른 namespace를 받아야 서로의 개인 스킬을 못 본다."""
        routes_a = skill_routes(account_id="AC001", team_id="TM001")
        routes_b = skill_routes(account_id="AC002", team_id="TM001")

        namespace_a = routes_a[SKILLS_PERSONAL_PATH_PREFIX]._namespace(None)
        namespace_b = routes_b[SKILLS_PERSONAL_PATH_PREFIX]._namespace(None)
        self.assertNotEqual(namespace_a, namespace_b)

    def test_different_teams_get_isolated_team_namespaces(self):
        routes_a = skill_routes(account_id="AC001", team_id="TM001")
        routes_b = skill_routes(account_id="AC001", team_id="TM002")

        namespace_a = routes_a[SKILLS_TEAM_PATH_PREFIX]._namespace(None)
        namespace_b = routes_b[SKILLS_TEAM_PATH_PREFIX]._namespace(None)
        self.assertNotEqual(namespace_a, namespace_b)

    def test_personal_namespace_matches_standalone_helper(self):
        """`skill_register`(services/harness/registry.py)가 쓰는 `personal_namespace()`와
        `SkillsMiddleware`가 읽을 때 쓰는 라우트의 namespace가 같아야 서로 같은
        저장 공간을 가리킨다 — 단일 진실 공급원 확인."""
        routes = skill_routes(account_id="AC001", team_id="TM001")

        self.assertEqual(routes[SKILLS_PERSONAL_PATH_PREFIX]._namespace(None), personal_namespace("AC001"))
