"""테넌트(팀) 경계 테스트.

테넌트는 회사가 아니라 **팀**이다. HR에서는 한 회사지만 우리 플랫폼을 쓰는 것은
회사 전체가 아니라 그 안의 그룹이기 때문이다. 그래서 경계는 HR 어댑터가 아니라
플랫폼(`team`/`team_member`)이 갖는다.

이 프로젝트는 `DATABASES = {}`라 Django가 테스트용 DB를 띄우지 않는다. 그래서
"두 팀을 실제로 넣고 교차 조회가 막히는가"는 여기서 재현할 수 없고, DB에 닿기
전에 결정되는 **가드 계약**을 검증한다. 이 가드가 뚫리면 스코프를 안 건 것과
같아지므로, 여기가 깨지면 경계가 무너진 것이다.
"""

from unittest.mock import patch

from django.test import SimpleTestCase

from backend.db.errors import PermissionDenied
from backend.db.repositories import TeamRepository
from backend.services.hr import mock_db


class HrAdapterGuardTests(SimpleTestCase):
    """빈 조건과 조건 없음을 구분해야 한다.

    이걸 구분하지 않으면 "팀원이 아직 없는 팀"이 전 직원을 보게 된다 — 조건이
    빈 리스트일 때 WHERE 절을 통째로 빼버리는 실수가 흔하다.
    """

    def test_empty_person_ids_returns_nothing(self):
        self.assertEqual(mock_db.list_persons(person_ids=[]), [])

    def test_empty_org_ids_returns_nothing(self):
        self.assertEqual(mock_db.list_persons(org_ids=[]), [])
        self.assertEqual(mock_db.list_orgs(org_ids=[]), [])

    def test_no_root_org_returns_no_subtree(self):
        self.assertEqual(mock_db.subtree_org_ids(None), [])

    def test_get_person_without_id_returns_none(self):
        self.assertIsNone(mock_db.get_person(None))

    def test_empty_lookup_does_not_query(self):
        self.assertEqual(mock_db.lookup_persons([]), {})
        self.assertEqual(mock_db.lookup_orgs([]), {})


class TeamScopeTests(SimpleTestCase):
    """팀이 없으면 아무도 보이지 않아야 한다."""

    def test_no_team_means_no_members(self):
        self.assertEqual(TeamRepository.member_person_ids(None), [])

    def test_no_team_means_no_team_record(self):
        self.assertIsNone(TeamRepository.get(None))

    def test_team_member_ids_feed_person_lookup_as_empty(self):
        """팀이 없는 계정은 팀원 0명 → 직원 조회도 0명이어야 한다."""

        self.assertEqual(mock_db.list_persons(person_ids=TeamRepository.member_person_ids(None)), [])


class TeamCreationGuardTests(SimpleTestCase):
    """팀 생성 시점에 지켜야 하는 것."""

    def test_blank_name_is_rejected(self):
        with self.assertRaises(Exception) as ctx:
            TeamRepository.create(owner_account_id="UA001", name="   ", person_ids=[])
        self.assertIn("팀 이름", str(ctx.exception))

    @patch("backend.db.repositories.database_connection")
    @patch("backend.db.repositories.hr.subtree_org_ids", return_value=["A002"])
    @patch("backend.db.repositories.hr.get_person", return_value={"person_id": "PX002", "org_id": "A002"})
    @patch("backend.db.repositories.hr.list_persons")
    @patch("backend.db.repositories._linked_person_id", return_value="PX002")
    def test_member_outside_own_org_subtree_is_rejected(
        self, _linked, list_persons, _get_person, _subtree, connection
    ):
        """초대 범위 밖(다른 부서) 직원을 팀에 담으려 하면 막힌다."""

        cursor = connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = {"team_id": None}
        # A008(마케팅팀)은 팀장 소속 A002의 하위가 아니다.
        list_persons.return_value = [{"person_id": "PM001", "org_id": "A008"}]

        with self.assertRaises(Exception) as ctx:
            TeamRepository.create(owner_account_id="UA001", name="개발팀", person_ids=["PM001"])

        self.assertIn("하위 조직의 직원만", str(ctx.exception))


class TeamMemberApiTests(SimpleTestCase):
    """팀 명부. 초대 현황과 다르다 — 명부는 업무 배정 대상이다."""

    def _headers(self):
        from apps.accounts.tokens import issue_token

        return {"authorization": f"Bearer {issue_token('UA001')}"}

    def _row(self, person_id="PB002", name="성주연", account=None, invite="PENDING", owner=False):
        return {
            "team_member_id": "TM003",
            "person_id": person_id,
            "name": name,
            "org_name": "개발팀",
            "job_role": "사원",
            "added_at": None,
            "account_id": account,
            "account_email": f"{account}@halil.com" if account else None,
            "account_status": "ACTIVE" if account else None,
            "is_owner": owner,
            "invite_id": "MI002" if invite else None,
            "invite_status": invite,
            "invited_at": None,
        }

    def test_requires_login(self):
        self.assertEqual(self.client.get("/api/teams/members/").status_code, 401)

    @patch("apps.people.api_views.TeamRepository.list_members")
    def test_lists_members_with_account_and_invite(self, list_members):
        """계정이 없어도 팀원이다 — team_member 는 사람 단위다."""

        list_members.return_value = [
            self._row(person_id="PX002", name="임준", account="UA001", invite=None, owner=True),
            self._row(),
        ]

        body = self.client.get("/api/teams/members/", headers=self._headers()).json()

        self.assertEqual(len(body), 2)
        # 직접 가입한 팀장은 초대 기록이 없다. 초대 목록만 보면 아예 빠진다.
        self.assertIsNone(body[0]["invite_status"])
        self.assertTrue(body[0]["is_owner"])
        self.assertIsNone(body[1]["account_id"])
        self.assertEqual(body[1]["invite_status"], "PENDING")

    def test_owner_comes_first_then_higher_grade(self):
        """명부에 들어온 순서로 두면 나중에 추가한 팀장이 맨 아래에 붙는다."""

        rows = [
            {"name": "성주연", "level_rank": 1, "is_owner": False},
            {"name": "임준", "level_rank": 6, "is_owner": True},
            {"name": "김지훈", "level_rank": 4, "is_owner": False},
            # 직급을 모르는 사람은 맨 뒤다. 0으로 치면 사원보다 위로 올라간다.
            {"name": "미상", "level_rank": None, "is_owner": False},
        ]
        rows.sort(
            key=lambda row: (
                0 if row["is_owner"] else 1,
                -(row["level_rank"] or 0),
                row["name"] or "",
            )
        )

        self.assertEqual([row["name"] for row in rows], ["임준", "김지훈", "성주연", "미상"])

    @patch("apps.people.api_views.TeamRepository.list_members", return_value=[])
    @patch("apps.people.api_views.TeamRepository.add_member_for")
    def test_add_requires_person_id(self, add_member, _list):
        response = self.client.post(
            "/api/teams/members/", {}, content_type="application/json", headers=self._headers()
        )

        self.assertEqual(response.status_code, 400)
        add_member.assert_not_called()

    @patch("apps.people.api_views.TeamRepository.list_members", return_value=[])
    @patch("apps.people.api_views.TeamRepository.add_member_for")
    def test_add_passes_person_id(self, add_member, _list):
        response = self.client.post(
            "/api/teams/members/",
            {"person_id": "PB003"},
            content_type="application/json",
            headers=self._headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(add_member.call_args.kwargs["person_id"], "PB003")

    @patch("apps.people.api_views.TeamRepository.add_member_for")
    def test_add_outside_org_subtree_is_forbidden(self, add_member):
        add_member.side_effect = PermissionDenied(
            "본인이 속한 조직과 그 하위 조직의 직원만 팀에 담을 수 있습니다."
        )

        response = self.client.post(
            "/api/teams/members/",
            {"person_id": "PZ001"},
            content_type="application/json",
            headers=self._headers(),
        )

        self.assertEqual(response.status_code, 403)

    @patch("apps.people.api_views.TeamRepository.list_members", return_value=[])
    @patch("apps.people.api_views.TeamRepository.remove_member")
    def test_remove_passes_person_id(self, remove_member, _list):
        response = self.client.delete("/api/teams/members/PB003/", headers=self._headers())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(remove_member.call_args.kwargs["person_id"], "PB003")

    @patch("apps.people.api_views.TeamRepository.remove_member")
    def test_removing_someone_with_a_team_account_is_forbidden(self, remove_member):
        """명부에서만 지우면 그 사람의 계정은 여전히 팀 데이터를 본다."""

        remove_member.side_effect = PermissionDenied(
            "이 직원은 팀 계정을 쓰고 있어 명부에서 뺄 수 없습니다."
        )

        response = self.client.delete("/api/teams/members/PB001/", headers=self._headers())

        self.assertEqual(response.status_code, 403)

    @patch("apps.people.api_views.TeamRepository.remove_member")
    def test_removing_the_owner_is_forbidden(self, remove_member):
        remove_member.side_effect = PermissionDenied("팀을 만든 사람은 명부에서 뺄 수 없습니다.")

        response = self.client.delete("/api/teams/members/PX002/", headers=self._headers())

        self.assertEqual(response.status_code, 403)
