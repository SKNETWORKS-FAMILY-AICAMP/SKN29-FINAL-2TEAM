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
from services.agent_runtime.skills.document import SkillDocument


def _patched_store():
    return patch("services.agent_runtime.memory.store.get_memory_store", return_value=InMemoryStore())


def _create_verified_personal(
    account_id="AC001", *, name="my-skill", description="설명", body="본문"
):
    from services.agent_runtime.skills.versioning import (
        runtime_profile_version, tool_registry_version, validation_hash,
    )

    document = {"name": name, "description": description, "body": body}
    return service.create_personal_skill(
        account_id, team_id="TM001", name=name, description=description, body=body,
        validation_receipt={
            "validation_state": "VERIFIED",
            "validated_hash": validation_hash(document),
            "source_job_id": "test-job",
            "runtime_profile_version": runtime_profile_version(),
            "tool_registry_version": tool_registry_version(),
        },
    )


def _create_legacy_team_skill(
    *, team_id="TM001", name="legacy-skill", description="설명", body="본문"
):
    """직접 팀 등록 기능이 사라지기 전에 저장된 데이터를 테스트에만 만든다."""

    return service.create_skill(
        service._team_scope(team_id),
        name=name,
        description=description,
        body=body,
        validation_receipt={"validation_state": "LEGACY_UNVERIFIED"},
    )


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

    def test_표준과_추가_frontmatter를_손실_없이_왕복한다(self):
        content = (
            "---\nname: my-skill\ndescription: 설명\nlicense: Apache-2.0\n"
            "compatibility: Python 3.13\nallowed-tools:\n  - document_search\n"
            "metadata:\n  owner: platform\ncustom-field:\n  nested: value\n---\n\n본문\n"
        )
        first = SkillDocument.parse(content)
        second = SkillDocument.parse(first.updated(description="새 설명", enabled=False).render())
        self.assertEqual(second.frontmatter["license"], "Apache-2.0")
        self.assertEqual(second.frontmatter["allowed-tools"], ["document_search"])
        self.assertEqual(second.frontmatter["custom-field"], {"nested": "value"})
        self.assertEqual(second.metadata["owner"], "platform")
        self.assertFalse(second.enabled)


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
        store = InMemoryStore()
        with patch("services.agent_runtime.memory.store.get_memory_store", return_value=store):
            service.create_personal_skill(
                "AC001", team_id="TM001", name="my-skill", description="설명", body="본문"
            )
            updated = service.update_personal_skill("AC001", "my-skill", enabled=False)
            self.assertFalse(updated["enabled"])

            fetched = service.get_personal_skill("AC001", "my-skill")
            self.assertFalse(fetched["enabled"])
            self.assertIsNone(store.get(("skill", "personal", "AC001"), "/my-skill/SKILL.md"))
            self.assertIsNotNone(
                store.get(("skill", "inactive-personal", "AC001"), "/my-skill/SKILL.md")
            )

    def test_다시_활성화하면_돌아온다(self):
        with _patched_store():
            service.create_personal_skill(
                "AC001", team_id="TM001", name="my-skill", description="설명", body="본문"
            )
            service.update_personal_skill("AC001", "my-skill", enabled=False)
            reenabled = service.update_personal_skill("AC001", "my-skill", enabled=True)
            self.assertTrue(reenabled["enabled"])

    def test_구버전_false파일은_조회전에_비활성_namespace로_이관한다(self):
        from deepagents.backends import StoreBackend

        store = InMemoryStore()
        StoreBackend(namespace=lambda _rt: ("skill", "personal", "AC001"), store=store).write(
            "/legacy/SKILL.md",
            service._render_skill_md(name="legacy", description="설명", body="본문", enabled=False),
        )
        with patch("services.agent_runtime.memory.store.get_memory_store", return_value=store):
            rows = service.list_personal_skills("AC001")
        self.assertEqual([row["name"] for row in rows], ["legacy"])
        self.assertIsNone(store.get(("skill", "personal", "AC001"), "/legacy/SKILL.md"))
        self.assertIsNotNone(
            store.get(("skill", "inactive-personal", "AC001"), "/legacy/SKILL.md")
        )

    def test_수정해도_추가_frontmatter가_보존된다(self):
        with _patched_store():
            service.create_personal_skill(
                "AC001", team_id="TM001", name="my-skill", description="설명", body="본문",
                frontmatter={
                    "name": "my-skill", "description": "설명", "license": "MIT",
                    "allowed-tools": ["document_search"], "metadata": {"owner": "platform"},
                },
            )
            updated = service.update_personal_skill("AC001", "my-skill", description="새 설명")
        self.assertEqual(updated["frontmatter"]["license"], "MIT")
        self.assertEqual(updated["frontmatter"]["allowed-tools"], ["document_search"])
        self.assertEqual(updated["frontmatter"]["metadata"]["owner"], "platform")

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

    def test_같은_이름의_팀_카탈로그가_있어도_개인_스킬을_만들_수_있다(self):
        """팀 카탈로그는 SkillsMiddleware 소스가 아니므로 개인 스킬을 가리지 않는다."""
        with _patched_store():
            _create_legacy_team_skill(name="shadowed", description="팀 것", body="팀 본문")
            created = service.create_personal_skill(
                "AC001", team_id="TM001", name="shadowed", description="개인 것", body="개인 본문"
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
    def test_팀_직접_생성_수정_경로는_노출하지_않는다(self):
        self.assertFalse(hasattr(service, "create_team_skill"))
        self.assertFalse(hasattr(service, "update_team_skill"))

    def test_리더만_팀_카탈로그에서_지울_수_있다(self):
        with _patched_store():
            _create_legacy_team_skill(name="foo", description="d", body="b")
            with self.assertRaises(service.SkillPermissionDenied):
                service.delete_team_skill("TM001", "foo", actor_role="member")
            service.delete_team_skill("TM001", "foo", actor_role="leader")

    def test_팀원도_조회는_할_수_있다(self):
        with _patched_store():
            _create_legacy_team_skill(name="foo", description="d", body="b")
            # list_team_skills/get_team_skill 자체는 role을 안 받는다 — 호출부
            # (REST 뷰)가 "조회는 팀원 전체"를 그냥 통과시키면 된다는 뜻이다.
            self.assertEqual(len(service.list_team_skills("TM001")), 1)
            self.assertEqual(service.get_team_skill("TM001", "foo")["name"], "foo")

    def test_다른_팀은_서로_안_보인다(self):
        with _patched_store():
            _create_legacy_team_skill(name="only-team1", description="d", body="b")
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


class SkillSharingTests(SimpleTestCase):
    def test_검증하지_않은_개인_스킬은_공유하지_못한다(self):
        with _patched_store():
            service.create_personal_skill(
                "AC001", team_id="TM001", name="draft-skill", description="설명", body="본문"
            )
            with self.assertRaises(service.SkillError):
                service.share_personal_skill("AC001", team_id="TM001", name="draft-skill")

    def test_가져올_때_재검증하지_않고_바로_개인_사본을_만든다(self):
        """팀 카탈로그에는 검증된 스킬만 올라오므로 가져오기는 복사일 뿐이다.
        미검증으로 표시된 기존(legacy) 항목도 검증 job 없이 바로 가져온다."""

        with _patched_store(), patch(
            "services.agent_runtime.skills.registration.SkillRegistrationService.enqueue"
        ) as enqueue:
            created = _create_legacy_team_skill()
            self.assertEqual(created["validation_state"], "LEGACY_UNVERIFIED")
            result = service.import_team_skill("AC002", team_id="TM001", name="legacy-skill")

        self.assertFalse(result["requires_validation"])
        self.assertEqual(result["skill"]["name"], "legacy-skill")
        self.assertEqual(result["skill"]["imported_from_team_id"], "TM001")
        enqueue.assert_not_called()

    def test_개인_스킬을_팀에_공유하고_중지한다(self):
        with _patched_store():
            _create_verified_personal()

            shared = service.share_personal_skill("AC001", team_id="TM001", name="my-skill")
            self.assertEqual(shared["shared_by_account_id"], "AC001")
            self.assertEqual(service.get_team_skill("TM001", "my-skill")["body"], "본문")

            service.stop_sharing_personal_skill("AC001", team_id="TM001", name="my-skill")
            with self.assertRaises(service.SkillNotFound):
                service.get_team_skill("TM001", "my-skill")
            self.assertEqual(service.get_personal_skill("AC001", "my-skill")["body"], "본문")

    def test_다른_사용자는_공유를_중지할_수_없다(self):
        with _patched_store():
            _create_verified_personal()
            service.share_personal_skill("AC001", team_id="TM001", name="my-skill")
            with self.assertRaises(service.SkillPermissionDenied):
                service.stop_sharing_personal_skill("AC002", team_id="TM001", name="my-skill")

    def test_개인_스킬_내용은_공유본에_반영되지만_활성상태는_영향을_주지_않는다(self):
        with _patched_store():
            _create_verified_personal()
            service.share_personal_skill("AC001", team_id="TM001", name="my-skill")

            service.update_personal_skill_and_shared_copy(
                "AC001",
                team_id="TM001",
                name="my-skill",
                description="새 설명",
                enabled=False,
            )
            team = service.get_team_skill("TM001", "my-skill")
            self.assertEqual(team["description"], "새 설명")
            self.assertTrue(team["enabled"])
            self.assertEqual(team["shared_by_account_id"], "AC001")

    def test_팀_스킬을_가져오면_독립_개인_사본이_된다(self):
        with _patched_store():
            _create_verified_personal(description="원본", body="원본 본문")
            service.share_personal_skill("AC001", team_id="TM001", name="my-skill")

            imported = service.import_team_skill("AC002", team_id="TM001", name="my-skill")["skill"]
            self.assertTrue(imported["enabled"])
            self.assertEqual(imported["imported_from_team_id"], "TM001")

            service.update_personal_skill("AC001", "my-skill", enabled=False)
            service.stop_sharing_personal_skill("AC001", team_id="TM001", name="my-skill")

            kept = service.get_personal_skill("AC002", "my-skill")
            self.assertTrue(kept["enabled"])
            self.assertEqual(kept["body"], "원본 본문")

    def test_가져온_스킬은_가져온_사람이_비활성화하고_삭제할_수_있다(self):
        with _patched_store():
            _create_verified_personal(name="team-skill", description="d", body="b")
            service.share_personal_skill("AC001", team_id="TM001", name="team-skill")
            service.import_team_skill("AC002", team_id="TM001", name="team-skill")
            disabled = service.update_personal_skill("AC002", "team-skill", enabled=False)
            self.assertFalse(disabled["enabled"])
            service.delete_personal_skill("AC002", "team-skill")
            with self.assertRaises(service.SkillNotFound):
                service.get_personal_skill("AC002", "team-skill")

    def test_팀에서_가져온_개인_스킬은_다시_팀에_공유할_수_없다(self):
        with _patched_store():
            _create_verified_personal(name="team-skill", description="d", body="b")
            service.share_personal_skill("AC001", team_id="TM001", name="team-skill")
            service.import_team_skill("AC002", team_id="TM001", name="team-skill")

            with self.assertRaises(service.SkillPermissionDenied):
                service.share_personal_skill("AC002", team_id="TM001", name="team-skill")

    def test_개인_원본을_삭제하면_팀_공유본도_정리한다(self):
        with _patched_store():
            _create_verified_personal()
            service.share_personal_skill("AC001", team_id="TM001", name="my-skill")
            service.delete_personal_skill_and_shared_copy(
                "AC001", team_id="TM001", name="my-skill"
            )
            with self.assertRaises(service.SkillNotFound):
                service.get_personal_skill("AC001", "my-skill")
            with self.assertRaises(service.SkillNotFound):
                service.get_team_skill("TM001", "my-skill")
