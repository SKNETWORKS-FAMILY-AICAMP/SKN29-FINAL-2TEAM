"""skills/backend.py 단위 테스트 — memory/backend.py의 격리 검증과 같은 방식.

정본: docs/설계 및 구현/3_중간발표 이후/작업기록/Deep_Agents/2026-08-20_16_Skill_Middleware_설계.md

실제 `StoreBackend`/`CompositeBackend` 객체로 확인한다(deepagents를 mock하지
않음) — namespace 튜플이 실제로 갈리는지가 핵심이라 Fake로는 이 회귀를 못
잡는다(`test_memory_backend.py`와 같은 이유).
"""

from django.test import SimpleTestCase

from services.agent_runtime.skills.backend import (
    SKILLS_BUILTIN_PATH_PREFIX,
    SKILLS_PERSONAL_PATH_PREFIX,
    SKILLS_TEAM_PATH_PREFIX,
    personal_namespace,
    skill_md_path,
    skill_routes,
    skill_sources,
    skills_system_prompt,
)


class SkillSourcesTests(SimpleTestCase):
    def test_team_catalog_is_not_an_agent_skill_source(self):
        """팀 카탈로그는 직접 적용하지 않고 개인 사본으로 가져와 사용한다."""
        self.assertEqual(
            skill_sources(),
            [SKILLS_BUILTIN_PATH_PREFIX, SKILLS_PERSONAL_PATH_PREFIX],
        )


class SkillMdPathTests(SimpleTestCase):
    def test_builds_skill_md_under_name_directory(self):
        self.assertEqual(
            skill_md_path(SKILLS_PERSONAL_PATH_PREFIX, "jira-issue-registration"),
            "/skills/personal/jira-issue-registration/SKILL.md",
        )


class SkillRoutesTests(SimpleTestCase):
    def test_routes_cover_every_prefix(self):
        routes = skill_routes(account_id="AC001", team_id="TM001")

        self.assertEqual(
            set(routes.keys()),
            {SKILLS_BUILTIN_PATH_PREFIX, SKILLS_PERSONAL_PATH_PREFIX, SKILLS_TEAM_PATH_PREFIX},
        )

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


class SkillsSystemPromptTests(SimpleTestCase):
    """2026-08-22 추가 — Skill 사용 우선순위 규칙 배선. `memory_system_prompt()`
    (`memory/backend.py`)와 같은 패턴 — deepagents 기본 프롬프트에 텍스트를
    이어붙인다."""

    def test_starts_with_the_real_deepagents_default_prompt(self):
        """deepagents가 실제로 쓰는 기본값 위에 이어붙이는지 확인한다 — 새
        프롬프트를 통째로 만드는 게 아니라, 이미 검증된 progressive
        disclosure 안내(이름·설명 목록, `read_file` 안내 등)를 그대로 살린다."""
        from deepagents.middleware.skills import SKILLS_SYSTEM_PROMPT

        self.assertTrue(skills_system_prompt().startswith(SKILLS_SYSTEM_PROMPT))

    def test_appended_text_keeps_required_format_slots_intact(self):
        """`SkillsMiddleware.__init__`이 요구하는 세 포맷 슬롯이 그대로 남아
        있어야 한다 — 안 그러면 `ValueError`로 Root 조립 자체가 실패한다
        (`deepagents/middleware/skills.py` 실측)."""
        prompt = skills_system_prompt()

        for slot in ("{skills_locations}", "{skills_load_warnings}", "{skills_list}"):
            self.assertIn(slot, prompt)

    def test_can_actually_construct_skillsmiddleware_with_it(self):
        """가장 확실한 검증 — 실제 `SkillsMiddleware(system_prompt=...)`
        생성자에 그대로 넘겨서 예외 없이 만들어지는지 본다."""
        from unittest.mock import Mock

        from deepagents.middleware.skills import SkillsMiddleware

        SkillsMiddleware(
            backend=Mock(name="backend"), sources=["/skills/personal/"], system_prompt=skills_system_prompt()
        )

    def test_mentions_memory_vs_skill_priority(self):
        """사용자가 요청한 네 규칙의 핵심 취지 — "지금 답변에 대한 스타일
        피드백은 스킬을 먼저 확인" — 이 실제로 문구에 들어 있는지 확인한다.
        문구를 통째로 비교하지 않는다 — 다듬을 때마다 이 테스트가 깨지면
        본말이 전도된다. 핵심 신호어만 담겼는지만 본다."""
        prompt = skills_system_prompt()

        self.assertIn("Skill usage rules", prompt)
        self.assertIn("memory", prompt.lower())
