"""skills/visibility.py(SkillVisibilityMiddleware) 단위 테스트.

2026-08-26, §7 — deepagents가 세션 시작 시 스킬 전체를 `skills_metadata`에
채운 뒤, 이 미들웨어가 `metadata.enabled == "false"`인 항목만 걸러낸다.
"""

from django.test import SimpleTestCase

from services.agent_runtime.skills.visibility import SkillVisibilityMiddleware, build_skill_visibility_filter


def _skill(name: str, *, enabled: bool | None = True) -> dict:
    metadata = {} if enabled is None else {"enabled": "true" if enabled else "false"}
    return {"name": name, "path": f"/skills/personal/{name}/SKILL.md", "description": "d", "metadata": metadata}


class BuildSkillVisibilityFilterTests(SimpleTestCase):
    def test_returns_a_configured_middleware(self):
        self.assertIsInstance(build_skill_visibility_filter(), SkillVisibilityMiddleware)


class BeforeAgentTests(SimpleTestCase):
    def test_no_skills_metadata_yet_is_a_noop(self):
        mw = SkillVisibilityMiddleware()

        result = mw.before_agent({}, runtime=None)

        self.assertIsNone(result)

    def test_empty_skills_metadata_is_a_noop(self):
        mw = SkillVisibilityMiddleware()

        result = mw.before_agent({"skills_metadata": []}, runtime=None)

        self.assertIsNone(result)

    def test_all_enabled_is_a_noop(self):
        """아무것도 걸러낼 게 없으면 state를 안 건드린다(불필요한 갱신 방지)."""
        mw = SkillVisibilityMiddleware()
        skills = [_skill("a"), _skill("b", enabled=None)]  # metadata 없는 옛 스킬도 활성 취급

        result = mw.before_agent({"skills_metadata": skills}, runtime=None)

        self.assertIsNone(result)

    def test_disabled_skill_is_removed(self):
        mw = SkillVisibilityMiddleware()
        skills = [_skill("a", enabled=True), _skill("b", enabled=False)]

        result = mw.before_agent({"skills_metadata": skills}, runtime=None)

        self.assertIsNotNone(result)
        names = {s["name"] for s in result["skills_metadata"]}
        self.assertEqual(names, {"a"})

    def test_skill_without_metadata_field_is_treated_as_enabled(self):
        """metadata 필드 자체가 없는(옛날 스킬) 항목도 걸러지면 안 된다 — 하위 호환."""
        mw = SkillVisibilityMiddleware()
        legacy_skill = {"name": "legacy", "path": "/skills/personal/legacy/SKILL.md", "description": "d"}
        skills = [legacy_skill, _skill("b", enabled=False)]

        result = mw.before_agent({"skills_metadata": skills}, runtime=None)

        names = {s["name"] for s in result["skills_metadata"]}
        self.assertEqual(names, {"legacy"})
