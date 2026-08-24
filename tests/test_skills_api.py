"""「스킬」 REST API(`apps/skills`) — 설정 > 스킬 화면이 부르는 계약.

`DATABASES = {}`라 실제 DB는 안 띄운다. `AccountRepository.get_profile`을
모킹해 팀 스킬의 역할 검사를 확인하고, `get_memory_store()`는
`InMemoryStore`로 바꿔 저장 자체는 실제 `StoreBackend`를 통과시킨다.
"""

from unittest.mock import patch

from django.test import SimpleTestCase
from langgraph.store.memory import InMemoryStore

from apps.accounts.tokens import issue_token

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

    @patch("apps.skills.api_views.AccountRepository.get_profile")
    def test_만들고_목록에서_보인다(self, get_profile):
        get_profile.return_value = _member()
        with _store_patch():
            create = self.client.post(
                "/api/me/skills/",
                {"name": "my-skill", "description": "설명입니다", "body": "본문 절차"},
                content_type="application/json",
                headers=auth_header(),
            )
            self.assertEqual(create.status_code, 201)
            self.assertEqual(create.json()["name"], "my-skill")

            listed = self.client.get("/api/me/skills/", headers=auth_header())
        self.assertEqual(len(listed.json()), 1)
        self.assertNotIn("body", listed.json()[0])

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
    def test_이름이_겹치면_409(self, get_profile):
        get_profile.return_value = _member()
        with _store_patch():
            self.client.post(
                "/api/me/skills/",
                {"name": "dup", "description": "d", "body": "b"},
                content_type="application/json",
                headers=auth_header(),
            )
            response = self.client.post(
                "/api/me/skills/",
                {"name": "dup", "description": "d2", "body": "b2"},
                content_type="application/json",
                headers=auth_header(),
            )
        self.assertEqual(response.status_code, 409)

    @patch("apps.skills.api_views.AccountRepository.get_profile")
    def test_같은_이름의_팀_스킬이_있으면_409(self, get_profile):
        get_profile.return_value = _leader()
        with _store_patch():
            self.client.post(
                "/api/teams/skills/",
                {"name": "shadowed", "description": "팀 것", "body": "b"},
                content_type="application/json",
                headers=auth_header(),
            )
            response = self.client.post(
                "/api/me/skills/",
                {"name": "shadowed", "description": "개인 것", "body": "b"},
                content_type="application/json",
                headers=auth_header(),
            )
        self.assertEqual(response.status_code, 409)

    def test_없는_스킬_조회는_404(self):
        with _store_patch():
            response = self.client.get("/api/me/skills/no-such/", headers=auth_header())
        self.assertEqual(response.status_code, 404)

    @patch("apps.skills.api_views.AccountRepository.get_profile")
    def test_읽고_고치고_지운다(self, get_profile):
        get_profile.return_value = _member()
        with _store_patch():
            self.client.post(
                "/api/me/skills/",
                {"name": "my-skill", "description": "설명", "body": "본문"},
                content_type="application/json",
                headers=auth_header(),
            )

            got = self.client.get("/api/me/skills/my-skill/", headers=auth_header())
            self.assertEqual(got.json()["body"], "본문")

            patched = self.client.patch(
                "/api/me/skills/my-skill/",
                {"description": "새 설명"},
                content_type="application/json",
                headers=auth_header(),
            )
            self.assertEqual(patched.status_code, 200)
            self.assertEqual(patched.json()["description"], "새 설명")

            deleted = self.client.delete("/api/me/skills/my-skill/", headers=auth_header())
            self.assertEqual(deleted.status_code, 204)

            after = self.client.get("/api/me/skills/my-skill/", headers=auth_header())
        self.assertEqual(after.status_code, 404)

    @patch("apps.skills.api_views.AccountRepository.get_profile")
    def test_다른_계정_것은_안_보인다(self, get_profile):
        get_profile.return_value = _member()
        with _store_patch():
            self.client.post(
                "/api/me/skills/",
                {"name": "only-mine", "description": "d", "body": "b"},
                content_type="application/json",
                headers=auth_header("UA001"),
            )
            response = self.client.get("/api/me/skills/", headers=auth_header("UA002"))
        self.assertEqual(response.json(), [])


class TeamSkillsApiTests(SimpleTestCase):
    """팀 스킬 — 조회는 팀원 전체, 쓰기는 leader만."""

    def test_requires_login(self):
        self.assertEqual(self.client.get("/api/teams/skills/").status_code, 401)

    @patch("apps.skills.api_views.AccountRepository.get_profile")
    def test_팀원도_목록은_볼_수_있다(self, get_profile):
        get_profile.return_value = _member()
        with _store_patch():
            response = self.client.get("/api/teams/skills/", headers=auth_header("UA002"))
        self.assertEqual(response.status_code, 200)

    @patch("apps.skills.api_views.AccountRepository.get_profile")
    def test_팀원이_만들면_403(self, get_profile):
        get_profile.return_value = _member()
        with _store_patch():
            response = self.client.post(
                "/api/teams/skills/",
                {"name": "foo", "description": "d", "body": "b"},
                content_type="application/json",
                headers=auth_header("UA002"),
            )
        self.assertEqual(response.status_code, 403)

    @patch("apps.skills.api_views.AccountRepository.get_profile")
    def test_리더가_만들면_201이고_팀원도_목록에서_본다(self, get_profile):
        with _store_patch():
            get_profile.return_value = _leader()
            create = self.client.post(
                "/api/teams/skills/",
                {"name": "team-skill", "description": "d", "body": "b"},
                content_type="application/json",
                headers=auth_header("UA001"),
            )
            self.assertEqual(create.status_code, 201)

            get_profile.return_value = _member()
            listed = self.client.get("/api/teams/skills/", headers=auth_header("UA002"))
        self.assertEqual(len(listed.json()), 1)
        self.assertEqual(listed.json()[0]["name"], "team-skill")

    @patch("apps.skills.api_views.AccountRepository.get_profile")
    def test_팀원이_고치거나_지우면_403(self, get_profile):
        with _store_patch():
            get_profile.return_value = _leader()
            self.client.post(
                "/api/teams/skills/",
                {"name": "team-skill", "description": "d", "body": "b"},
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
        self.assertEqual(patched.status_code, 403)
        self.assertEqual(deleted.status_code, 403)

    @patch("apps.skills.api_views.AccountRepository.get_profile")
    def test_다른_팀_스킬은_안_보인다(self, get_profile):
        with _store_patch():
            get_profile.return_value = _leader(team_id="TM001")
            self.client.post(
                "/api/teams/skills/",
                {"name": "team1-only", "description": "d", "body": "b"},
                content_type="application/json",
                headers=auth_header("UA001"),
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
