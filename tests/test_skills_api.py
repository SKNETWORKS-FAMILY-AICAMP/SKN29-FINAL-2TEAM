"""「스킬」 REST API(`apps/skills`) — 설정 > 스킬 화면이 부르는 계약.

`DATABASES = {}`라 실제 DB는 안 띄운다. `AccountRepository.get_profile`을
모킹해 팀 스킬의 역할 검사를 확인하고, `get_memory_store()`는
`InMemoryStore`로 바꿔 저장 자체는 실제 `StoreBackend`를 통과시킨다.
"""

from unittest.mock import patch
from types import SimpleNamespace

from django.test import SimpleTestCase
from langgraph.store.memory import InMemoryStore

from apps.accounts.tokens import issue_token
from services.agent_runtime.skills.service import create_personal_skill
from services.agent_runtime.skills.versioning import (
    runtime_profile_version, tool_registry_version, validation_hash,
)

from .test_accounts import leader_profile, member_profile


def auth_header(account_id="UA001"):
    return {"authorization": f"Bearer {issue_token(account_id)}"}


def _leader(team_id="TM001"):
    profile = leader_profile()
    profile["team_id"] = team_id
    return profile


def _member(team_id="TM001"):
    profile = member_profile()
    profile["team_id"] = team_id
    return profile


def _store_patch():
    return patch("services.agent_runtime.memory.store.get_memory_store", return_value=InMemoryStore())


def _share_personal_skill(client, *, account_id="UA001", name="team-skill", description="d", body="b"):
    """팀 카탈로그는 개인 스킬 공유로만 채운다."""
    document = {"name": name, "description": description, "body": body}
    create_personal_skill(
        account_id,
        team_id="TM001",
        name=name,
        description=description,
        body=body,
        validation_receipt={
            "validation_state": "VERIFIED",
            "validated_hash": validation_hash(document),
            "source_job_id": "test-job",
            "runtime_profile_version": runtime_profile_version(),
            "tool_registry_version": tool_registry_version(),
        },
    )
    shared = client.post(
        f"/api/me/skills/{name}/share/", headers=auth_header(account_id)
    )
    if shared.status_code != 201:
        raise AssertionError(f"개인 스킬 공유 실패: {shared.status_code} {shared.content!r}")
    return shared


def _job(*, name="my-skill", operation="CREATE"):
    return {
        "job_id": "11111111-1111-1111-1111-111111111111",
        "skill_name": name,
        "operation": operation,
        "status": "QUEUED",
        "stage": "WAITING",
    }


class MySkillsApiTests(SimpleTestCase):
    """개인 스킬 — 조회·수정·삭제는 `AccountRepository`를 안 거친다
    (`request.user.account_id`뿐). **생성만 예외다** — 같은 이름의 팀 스킬이
    있으면 만들어도 에이전트에게 안 보이므로(`create_personal_skill` 참고)
    `team_id`가 필요해 프로필을 한 번 조회한다."""

    def test_requires_login(self):
        self.assertEqual(self.client.get("/api/me/skills/").status_code, 401)

    def test_처음엔_빈_목록이다(self):
        with _store_patch():
            response = self.client.get("/api/me/skills/", headers=auth_header())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    @patch("apps.skills.api_views.SkillRegistrationService.enqueue")
    @patch("apps.skills.api_views.AccountRepository.get_profile")
    def test_생성은_즉시_게시하지_않고_검증_job을_만든다(self, get_profile, enqueue):
        get_profile.return_value = _member()
        enqueue.return_value = SimpleNamespace(job=_job(), created=True)
        with _store_patch():
            create = self.client.post(
                "/api/me/skills/",
                {"name": "my-skill", "description": "설명입니다", "body": "본문 절차"},
                content_type="application/json",
                headers=auth_header(),
            )
            self.assertEqual(create.status_code, 202)
            self.assertEqual(create.json()["skill_name"], "my-skill")
            listed = self.client.get("/api/me/skills/", headers=auth_header())
        self.assertEqual(listed.json(), [])

    @patch("apps.skills.api_views.SkillRegistrationService.enqueue")
    @patch("apps.skills.api_views.AccountRepository.get_profile")
    def test_업로드는_추가_frontmatter까지_job에_전달한다(self, get_profile, enqueue):
        get_profile.return_value = _member()
        enqueue.return_value = SimpleNamespace(job=_job(name="uploaded"), created=True)
        source = (
            "---\nname: uploaded\ndescription: 업로드 설명\nlicense: MIT\n"
            "allowed-tools:\n  - document_search\nmetadata:\n  owner: platform\n---\n\n본문\n"
        )
        response = self.client.post(
            "/api/me/skills/",
            {"source_content": source},
            content_type="application/json",
            headers=auth_header(),
        )
        self.assertEqual(response.status_code, 202)
        frontmatter = enqueue.call_args.kwargs["frontmatter"]
        self.assertEqual(frontmatter["license"], "MIT")
        self.assertEqual(frontmatter["allowed-tools"], ["document_search"])
        self.assertEqual(frontmatter["metadata"]["owner"], "platform")

    @patch("apps.skills.api_views.AccountRepository.get_profile")
    def test_이름이_없으면_400(self, get_profile):
        get_profile.return_value = _member()
        with _store_patch():
            response = self.client.post(
                "/api/me/skills/",
                {"name": "", "description": "d", "body": "b"},
                content_type="application/json",
                headers=auth_header(),
            )
        self.assertEqual(response.status_code, 400)

    @patch("apps.skills.api_views.AccountRepository.get_profile")
    @patch("apps.skills.api_views.SkillRegistrationService.enqueue")
    def test_같은_열린_job이면_기존_job을_반환한다(self, enqueue, get_profile):
        get_profile.return_value = _member()
        enqueue.return_value = SimpleNamespace(job=_job(name="dup"), created=False)
        with _store_patch():
            response = self.client.post(
                "/api/me/skills/",
                {"name": "dup", "description": "d2", "body": "b2"},
                content_type="application/json",
                headers=auth_header(),
            )
        self.assertEqual(response.status_code, 200)

    @patch("apps.skills.api_views.AccountRepository.get_profile")
    def test_같은_이름의_팀_카탈로그가_있어도_개인_스킬을_만들_수_있다(self, get_profile):
        get_profile.return_value = _leader()
        with _store_patch():
            _share_personal_skill(
                self.client,
                account_id="UA002",
                name="shadowed",
                description="팀 것",
            )
            response = create_personal_skill(
                "UA001", team_id="TM001", name="shadowed", description="개인 것", body="b"
            )
        self.assertEqual(response["name"], "shadowed")

    def test_없는_스킬_조회는_404(self):
        with _store_patch():
            response = self.client.get("/api/me/skills/no-such/", headers=auth_header())
        self.assertEqual(response.status_code, 404)

    @patch("apps.skills.api_views.AccountRepository.get_profile")
    @patch("apps.skills.api_views.SkillRegistrationService.enqueue")
    def test_읽고_내용_수정은_검증_job을_만들고_지운다(self, enqueue, get_profile):
        get_profile.return_value = _member()
        enqueue.return_value = SimpleNamespace(job=_job(operation="UPDATE"), created=True)
        with _store_patch():
            create_personal_skill(
                "UA001", team_id="TM001", name="my-skill", description="설명", body="본문"
            )

            got = self.client.get("/api/me/skills/my-skill/", headers=auth_header())
            self.assertEqual(got.json()["body"], "본문")

            patched = self.client.patch(
                "/api/me/skills/my-skill/",
                {"description": "새 설명"},
                content_type="application/json",
                headers=auth_header(),
            )
            self.assertEqual(patched.status_code, 202)
            self.assertEqual(patched.json()["operation"], "UPDATE")
            enqueue.assert_called_once_with(
                account_id="UA001",
                team_id="TM001",
                name="my-skill",
                description="새 설명",
                body="본문",
                frontmatter={
                    "name": "my-skill",
                    "description": "설명",
                    "metadata": {"enabled": "true"},
                },
            )
            unchanged = self.client.get("/api/me/skills/my-skill/", headers=auth_header())
            self.assertEqual(unchanged.json()["description"], "설명")

            deleted = self.client.delete("/api/me/skills/my-skill/", headers=auth_header())
            self.assertEqual(deleted.status_code, 204)

            after = self.client.get("/api/me/skills/my-skill/", headers=auth_header())
        self.assertEqual(after.status_code, 404)

    @patch("apps.skills.api_views.AccountRepository.get_profile")
    def test_활성_상태만_즉시_변경하고_내용과_섞으면_거부한다(self, get_profile):
        get_profile.return_value = _member()
        with _store_patch():
            create_personal_skill(
                "UA001", team_id="TM001", name="my-skill", description="설명", body="본문"
            )
            toggled = self.client.patch(
                "/api/me/skills/my-skill/",
                {"enabled": False},
                content_type="application/json",
                headers=auth_header(),
            )
            mixed = self.client.patch(
                "/api/me/skills/my-skill/",
                {"description": "새 설명", "enabled": True},
                content_type="application/json",
                headers=auth_header(),
            )
        self.assertEqual(toggled.status_code, 200)
        self.assertFalse(toggled.json()["enabled"])
        self.assertEqual(mixed.status_code, 400)

    @patch("apps.skills.api_views.AccountRepository.get_profile")
    def test_다른_계정_것은_안_보인다(self, get_profile):
        get_profile.return_value = _member()
        with _store_patch():
            create_personal_skill(
                "UA001", team_id="TM001", name="only-mine", description="d", body="b"
            )
            response = self.client.get("/api/me/skills/", headers=auth_header("UA002"))
        self.assertEqual(response.json(), [])

    @patch("apps.skills.api_views.AccountRepository.get_profile")
    def test_개인_스킬을_팀에_공유하고_중지한다(self, get_profile):
        get_profile.return_value = _member()
        with _store_patch():
            shared = _share_personal_skill(self.client, name="shared-skill")
            self.assertEqual(shared.status_code, 201)
            self.assertTrue(shared.json()["shared_by_me"])

            team_list = self.client.get("/api/teams/skills/", headers=auth_header("UA001"))
            self.assertTrue(team_list.json()[0]["shared_by_me"])
            self.assertFalse(team_list.json()[0]["can_delete"])

            stopped = self.client.delete(
                "/api/me/skills/shared-skill/share/", headers=auth_header("UA001")
            )
            self.assertEqual(stopped.status_code, 204)
            personal = self.client.get(
                "/api/me/skills/shared-skill/", headers=auth_header("UA001")
            )
            self.assertEqual(personal.status_code, 200)

    @patch("apps.skills.api_views.AccountRepository.get_profile")
    def test_다른_사람이_공유한_스킬은_공유중지할_수_없다(self, get_profile):
        with _store_patch():
            get_profile.return_value = _member()
            _share_personal_skill(self.client, name="shared-skill")

            response = self.client.delete(
                "/api/me/skills/shared-skill/share/", headers=auth_header("UA002")
            )
            self.assertEqual(response.status_code, 403)


class TeamSkillsApiTests(SimpleTestCase):
    """팀 스킬 — 개인 스킬 공유로만 만들고, 조회는 팀원 전체가 한다."""

    def test_requires_login(self):
        self.assertEqual(self.client.get("/api/teams/skills/").status_code, 401)

    @patch("apps.skills.api_views.AccountRepository.get_profile")
    def test_팀원도_목록은_볼_수_있다(self, get_profile):
        get_profile.return_value = _member()
        with _store_patch():
            response = self.client.get("/api/teams/skills/", headers=auth_header("UA002"))
        self.assertEqual(response.status_code, 200)

    @patch("apps.skills.api_views.AccountRepository.get_profile")
    def test_팀원은_팀_카탈로그에_직접_만들_수_없다(self, get_profile):
        get_profile.return_value = _member()
        with _store_patch():
            response = self.client.post(
                "/api/teams/skills/",
                {"name": "foo", "description": "d", "body": "b"},
                content_type="application/json",
                headers=auth_header("UA002"),
            )
        self.assertEqual(response.status_code, 405)

    @patch("apps.skills.api_views.AccountRepository.get_profile")
    def test_리더도_팀_카탈로그에_직접_만들_수_없다(self, get_profile):
        get_profile.return_value = _leader()
        with _store_patch():
            response = self.client.post(
                "/api/teams/skills/",
                {"name": "team-skill", "description": "d", "body": "b"},
                content_type="application/json",
                headers=auth_header("UA001"),
            )
        self.assertEqual(response.status_code, 405)

    @patch("apps.skills.api_views.AccountRepository.get_profile")
    def test_공유하면_팀원도_목록에서_본다(self, get_profile):
        with _store_patch():
            get_profile.return_value = _leader()
            _share_personal_skill(self.client)

            get_profile.return_value = _member()
            listed = self.client.get("/api/teams/skills/", headers=auth_header("UA002"))
        self.assertEqual(len(listed.json()), 1)
        self.assertEqual(listed.json()[0]["name"], "team-skill")
        self.assertFalse(listed.json()[0]["can_delete"])

    @patch("apps.skills.api_views.AccountRepository.get_profile")
    def test_팀장만_팀_목록에서_삭제_권한을_받는다(self, get_profile):
        with _store_patch():
            get_profile.return_value = _leader()
            _share_personal_skill(self.client)
            leader_list = self.client.get(
                "/api/teams/skills/", headers=auth_header("UA001")
            )
            self.assertTrue(leader_list.json()[0]["can_delete"])

            get_profile.return_value = _member()
            member_list = self.client.get(
                "/api/teams/skills/", headers=auth_header("UA002")
            )
            self.assertFalse(member_list.json()[0]["can_delete"])

    @patch("apps.skills.api_views.AccountRepository.get_profile")
    def test_가져온_개인_스킬을_삭제하면_팀_목록에서_다시_등록할_수_있다(self, get_profile):
        with _store_patch():
            get_profile.return_value = _leader()
            _share_personal_skill(self.client)

            get_profile.return_value = _member()
            self.client.post(
                "/api/teams/skills/team-skill/import/", headers=auth_header("UA002")
            )
            registered = self.client.get(
                "/api/teams/skills/", headers=auth_header("UA002")
            )
            self.assertTrue(registered.json()[0]["imported_by_me"])

            self.client.delete(
                "/api/me/skills/team-skill/", headers=auth_header("UA002")
            )
            available_again = self.client.get(
                "/api/teams/skills/", headers=auth_header("UA002")
            )
            self.assertFalse(available_again.json()[0]["imported_by_me"])

    @patch("apps.skills.api_views.AccountRepository.get_profile")
    def test_팀원이_내_스킬로_가져오면_독립_사본이_된다(self, get_profile):
        with _store_patch():
            get_profile.return_value = _leader()
            _share_personal_skill(self.client)

            get_profile.return_value = _member()
            imported = self.client.post(
                "/api/teams/skills/team-skill/import/",
                headers=auth_header("UA002"),
            )
            self.assertEqual(imported.status_code, 201)
            self.assertTrue(imported.json()["imported_from_team"])

            reshared = self.client.post(
                "/api/me/skills/team-skill/share/", headers=auth_header("UA002")
            )
            self.assertEqual(reshared.status_code, 403)

            listed = self.client.get("/api/teams/skills/", headers=auth_header("UA002"))
            self.assertTrue(listed.json()[0]["imported_by_me"])

            get_profile.return_value = _leader()
            self.client.delete(
                "/api/teams/skills/team-skill/", headers=auth_header("UA001")
            )

            personal = self.client.get(
                "/api/me/skills/team-skill/", headers=auth_header("UA002")
            )
            self.assertEqual(personal.status_code, 200)
            self.assertEqual(personal.json()["body"], "b")

    @patch("apps.skills.api_views.AccountRepository.get_profile")
    def test_팀_카탈로그는_누구도_직접_수정할_수_없고_팀원은_삭제할_수_없다(self, get_profile):
        with _store_patch():
            get_profile.return_value = _leader()
            _share_personal_skill(self.client)

            leader_patched = self.client.patch(
                "/api/teams/skills/team-skill/",
                {"description": "새 설명"},
                content_type="application/json",
                headers=auth_header("UA001"),
            )

            get_profile.return_value = _member()
            patched = self.client.patch(
                "/api/teams/skills/team-skill/",
                {"description": "새 설명"},
                content_type="application/json",
                headers=auth_header("UA002"),
            )
            deleted = self.client.delete(
                "/api/teams/skills/team-skill/", headers=auth_header("UA002")
            )
        self.assertEqual(leader_patched.status_code, 405)
        self.assertEqual(patched.status_code, 405)
        self.assertEqual(deleted.status_code, 403)

    @patch("apps.skills.api_views.AccountRepository.get_profile")
    def test_다른_팀_스킬은_안_보인다(self, get_profile):
        with _store_patch():
            get_profile.return_value = _leader(team_id="TM001")
            _share_personal_skill(
                self.client, name="team1-only", account_id="UA001"
            )

            get_profile.return_value = _leader(team_id="TM002")
            response = self.client.get("/api/teams/skills/", headers=auth_header("UA003"))
        self.assertEqual(response.json(), [])


class UnexpectedErrorHandlingTests(SimpleTestCase):
    """`AuthenticatedAPIView.handle_exception` — `SkillError`도 아니고
    `RepositoryError`/`psycopg.Error`도 아닌, 진짜 예상 못 한 예외가 났을 때.

    2026-08-22 실제로 겪은 사례(`get_memory_store()`의 최초 연결 경합 — 그
    자체는 `tests.test_memory_store`가 따로 검증한다)를 재현하지는 않는다.
    여기서 확인하는 것은 **그런 예외가 어떤 이유로든 나면 Django 기본 500
    HTML 페이지가 아니라 항상 JSON으로 응답이 온다는 것**이다 — 그래야
    `apiRequest()`(`frontend/src/api/client.ts`)가 상태 코드와 문구를 화면에
    보여줄 수 있다. 목록 조회(GET) 두 개는 원래 `try/except`가 아예 없었다.
    """

    @patch("apps.skills.api_views.list_personal_skills")
    def test_개인_스킬_목록_조회_중_예상_못_한_예외는_503_JSON이다(self, list_personal_skills):
        list_personal_skills.side_effect = RuntimeError("연결 경합 같은 임의의 예외")
        response = self.client.get("/api/me/skills/", headers=auth_header())
        self.assertEqual(response.status_code, 503)
        self.assertIn("detail", response.json())

    @patch("apps.skills.api_views.AccountRepository.get_profile")
    @patch("apps.skills.api_views.list_team_skills")
    def test_팀_스킬_목록_조회_중_예상_못_한_예외는_503_JSON이다(self, list_team_skills, get_profile):
        get_profile.return_value = _member()
        list_team_skills.side_effect = RuntimeError("연결 경합 같은 임의의 예외")
        response = self.client.get("/api/teams/skills/", headers=auth_header())
        self.assertEqual(response.status_code, 503)
        self.assertIn("detail", response.json())
