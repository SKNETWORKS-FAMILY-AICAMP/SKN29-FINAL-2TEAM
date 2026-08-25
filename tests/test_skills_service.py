"""`services.agent_runtime.skills.service` 단위 테스트.

정본: docs/설계 및 구현/3_중간발표 이후/작업기록/Deep_Agents/2026-08-20_16_Skill_Middleware_설계.md.
`get_memory_store()`만 실제 `PostgresStore` 대신 langgraph의 `InMemoryStore`로
바꾼다 — 그 외에는 `StoreBackend`를 실제로 통과시킨다(namespace 격리 같은
회귀는 진짜 protocol을 태워야 잡힌다, `tests/test_memory_backend.py`와 같은
이유).
"""

from unittest.mock import patch

from django.test import SimpleTestCase
from langgraph.store.memory import InMemoryStore

from services.agent_runtime.skills import service


def _patched_store():
    return patch("services.agent_runtime.memory.store.get_memory_store", return_value=InMemoryStore())


class ValidateSkillNameTests(SimpleTestCase):
    def test_정상_이름은_통과한다(self):
        for name in ("foo", "foo-bar", "a1-b2-c3", "a" * 64):
            with self.subTest(name=name):
                self.assertIsNone(service.validate_skill_name(name))

    def test_잘못된_이름은_사유를_돌려준다(self):
        for name in ("", "Foo", "-foo", "foo-", "foo--bar", "a" * 65, "foo_bar", "foo bar"):
            with self.subTest(name=name):
                self.assertIsNotNone(service.validate_skill_name(name))


class ParseSkillMdTests(SimpleTestCase):
    def test_정상_형식을_나눈다(self):
        content = "---\nname: my-skill\ndescription: 설명입니다\n---\n\n본문 첫 줄\n본문 둘째 줄\n"
        name, description, body, enabled = service.parse_skill_md(content)
        self.assertEqual(name, "my-skill")
        self.assertEqual(description, "설명입니다")
        self.assertEqual(body, "본문 첫 줄\n본문 둘째 줄")
        self.assertTrue(enabled)

    def test_metadata_enabled가_false면_비활성으로_읽는다(self):
        content = (
            "---\nname: my-skill\ndescription: 설명입니다\n"
            "metadata:\n  enabled: 'false'\n---\n\n본문\n"
        )
        _name, _description, _body, enabled = service.parse_skill_md(content)
        self.assertFalse(enabled)

    def test_frontmatter_없으면_거부한다(self):
        with self.assertRaises(service.SkillError):
            service.parse_skill_md("그냥 마크다운입니다.")

    def test_frontmatter가_안_닫히면_거부한다(self):
        with self.assertRaises(service.SkillError):
            service.parse_skill_md("---\nname: foo\n\n본문")

    def test_name이_없으면_거부한다(self):
        with self.assertRaises(service.SkillError):
            service.parse_skill_md("---\ndescription: d\n---\n\nbody")

    def test_description이_없으면_거부한다(self):
        with self.assertRaises(service.SkillError):
            service.parse_skill_md("---\nname: foo\n---\n\nbody")


class PersonalSkillCrudTests(SimpleTestCase):
    def test_목록은_처음엔_비어있다(self):
        with _patched_store():
            self.assertEqual(service.list_personal_skills("AC001"), [])

    def test_만들고_읽고_고치고_지운다(self):
        with _patched_store():
            created = service.create_personal_skill(
                "AC001", team_id="TM001", name="my-skill", description="설명", body="본문"
            )
            self.assertEqual(created["name"], "my-skill")
            self.assertEqual(created["skill_id"], "my-skill")

            listed = service.list_personal_skills("AC001")
            self.assertEqual(len(listed), 1)
            self.assertNotIn("body", listed[0])  # 목록에는 본문을 안 싣는다.

            fetched = service.get_personal_skill("AC001", "my-skill")
            self.assertEqual(fetched["body"], "본문")

            updated = service.update_personal_skill("AC001", "my-skill", description="새 설명")
            self.assertEqual(updated["description"], "새 설명")
            self.assertEqual(updated["body"], "본문")  # body를 안 넘기면 그대로.

            service.delete_personal_skill("AC001", "my-skill")
            with self.assertRaises(service.SkillNotFound):
                service.get_personal_skill("AC001", "my-skill")

    def test_없는_스킬을_읽거나_고치거나_지우면_SkillNotFound(self):
        with _patched_store():
            with self.assertRaises(service.SkillNotFound):
                service.get_personal_skill("AC001", "no-such-skill")
            with self.assertRaises(service.SkillNotFound):
                service.update_personal_skill("AC001", "no-such-skill", description="d")
            with self.assertRaises(service.SkillNotFound):
                service.delete_personal_skill("AC001", "no-such-skill")


class SkillEnabledTests(SimpleTestCase):
    """2026-08-26, §7 — 활성화/비활성화 토글."""

    def test_새로_만든_스킬은_기본_활성이다(self):
        with _patched_store():
            created = service.create_personal_skill(
                "AC001", team_id="TM001", name="my-skill", description="설명", body="본문"
            )
            self.assertTrue(created["enabled"])

    def test_비활성화하면_enabled가_false로_읽힌다(self):
        with _patched_store():
            service.create_personal_skill(
                "AC001", team_id="TM001", name="my-skill", description="설명", body="본문"
            )
            updated = service.update_personal_skill("AC001", "my-skill", enabled=False)
            self.assertFalse(updated["enabled"])

            fetched = service.get_personal_skill("AC001", "my-skill")
            self.assertFalse(fetched["enabled"])

    def test_다시_활성화하면_돌아온다(self):
        with _patched_store():
            service.create_personal_skill(
                "AC001", team_id="TM001", name="my-skill", description="설명", body="본문"
            )
            service.update_personal_skill("AC001", "my-skill", enabled=False)
            reenabled = service.update_personal_skill("AC001", "my-skill", enabled=True)
            self.assertTrue(reenabled["enabled"])

    def test_enabled를_안_넘기면_기존_값을_유지한다(self):
        with _patched_store():
            service.create_personal_skill(
                "AC001", team_id="TM001", name="my-skill", description="설명", body="본문"
            )
            service.update_personal_skill("AC001", "my-skill", enabled=False)
            # description만 바꾸고 enabled는 안 건드림 — 여전히 비활성이어야 한다.
            updated = service.update_personal_skill("AC001", "my-skill", description="새 설명")
            self.assertFalse(updated["enabled"])

    def test_비활성화해도_삭제되지_않는다(self):
        with _patched_store():
            service.create_personal_skill(
                "AC001", team_id="TM001", name="my-skill", description="설명", body="본문"
            )
            service.update_personal_skill("AC001", "my-skill", enabled=False)

            listed = service.list_personal_skills("AC001")
            self.assertEqual(len(listed), 1)
            self.assertFalse(listed[0]["enabled"])

    def test_이름이_겹치면_거부하고_원본을_보존한다(self):
        with _patched_store():
            service.create_personal_skill("AC001", team_id="TM001", name="dup", description="원본", body="원본 본문")
            with self.assertRaises(service.SkillNameConflict):
                service.create_personal_skill(
                    "AC001", team_id="TM001", name="dup", description="새 것", body="새 본문"
                )

            # 거부됐으니 원본이 그대로 남아 있어야 한다 — 조용히 덮어쓰지 않는다.
            self.assertEqual(service.get_personal_skill("AC001", "dup")["description"], "원본")

    def test_같은_이름의_팀_스킬이_있으면_개인_스킬을_못_만든다(self):
        """`SkillsMiddleware`가 이름이 같으면 팀 스킬로 완전히 덮어쓴다
        (`create_skill` docstring 근거) — 만들어도 안 보이는 스킬이 생기는
        걸 여기서 막는다."""
        with _patched_store():
            service.create_team_skill(
                "TM001", actor_role="leader", name="shadowed", description="팀 것", body="팀 본문"
            )
            with self.assertRaises(service.SkillNameConflict):
                service.create_personal_skill(
                    "AC001", team_id="TM001", name="shadowed", description="개인 것", body="개인 본문"
                )
            # 다른 팀 소속이면 안 겹친다 — team_id로 정확히 그 팀만 본다.
            created = service.create_personal_skill(
                "AC001", team_id="TM002", name="shadowed", description="개인 것", body="개인 본문"
            )
            self.assertEqual(created["name"], "shadowed")

    def test_본문이_너무_크면_거부한다(self):
        with _patched_store():
            too_big = "a" * (service.MAX_SKILL_BODY_BYTES + 1)
            with self.assertRaises(service.SkillError):
                service.create_personal_skill(
                    "AC001", team_id="TM001", name="too-big", description="d", body=too_big
                )

    def test_다른_계정은_서로_안_보인다(self):
        with _patched_store():
            service.create_personal_skill("AC001", team_id="TM001", name="only-mine", description="d", body="b")
            self.assertEqual(service.list_personal_skills("AC002"), [])
            with self.assertRaises(service.SkillNotFound):
                service.get_personal_skill("AC002", "only-mine")


class TeamSkillCrudTests(SimpleTestCase):
    def test_리더만_만들고_고치고_지울_수_있다(self):
        with _patched_store():
            with self.assertRaises(service.SkillPermissionDenied):
                service.create_team_skill(
                    "TM001", actor_role="member", name="foo", description="d", body="b"
                )

            created = service.create_team_skill(
                "TM001", actor_role="leader", name="foo", description="d", body="b"
            )
            self.assertEqual(created["name"], "foo")

            with self.assertRaises(service.SkillPermissionDenied):
                service.update_team_skill("TM001", "foo", actor_role="member", description="d2")
            with self.assertRaises(service.SkillPermissionDenied):
                service.delete_team_skill("TM001", "foo", actor_role="member")

    def test_팀원도_조회는_할_수_있다(self):
        with _patched_store():
            service.create_team_skill(
                "TM001", actor_role="leader", name="foo", description="d", body="b"
            )
            # list_team_skills/get_team_skill 자체는 role을 안 받는다 — 호출부
            # (REST 뷰)가 "조회는 팀원 전체"를 그냥 통과시키면 된다는 뜻이다.
            self.assertEqual(len(service.list_team_skills("TM001")), 1)
            self.assertEqual(service.get_team_skill("TM001", "foo")["name"], "foo")

    def test_다른_팀은_서로_안_보인다(self):
        with _patched_store():
            service.create_team_skill(
                "TM001", actor_role="leader", name="only-team1", description="d", body="b"
            )
            self.assertEqual(service.list_team_skills("TM002"), [])

    def test_업로드로_받은_frontmatter_이름_설명이_그대로_저장된다(self):
        """업로드 탭이 하는 일과 같은 순서 — `parse_skill_md`로 이름·설명을
        꺼낸 뒤 `create_personal_skill`에 그대로 넘긴다."""
        with _patched_store():
            content = "---\nname: uploaded-skill\ndescription: 업로드로 만든 설명\n---\n\n업로드 본문\n"
            name, description, body, _enabled = service.parse_skill_md(content)
            created = service.create_personal_skill(
                "AC001", team_id="TM001", name=name, description=description, body=body
            )
            self.assertEqual(created["name"], "uploaded-skill")
            self.assertEqual(created["description"], "업로드로 만든 설명")
            self.assertEqual(created["body"], "업로드 본문")
