from unittest.mock import patch

from django.test import SimpleTestCase

import apps.accounts.tokens as account_tokens
import apps.ops.tokens as ops_tokens
from apps.ops.authentication import REVOKED_DETAIL

OVERVIEW_URL = "/api/ops/overview/"


def admin_account(account_id="UA001", **overrides):
    account = {
        "account_id": account_id,
        "email": "admin@halil.com",
        "display_name": "관리자",
        "password_hash": "unused",
        "account_status": "ACTIVE",
        "is_admin": True,
    }
    account.update(overrides)
    return account


class OpsAuthenticationTests(SimpleTestCase):
    """운영자 콘솔은 고권한 API라, 요청마다 DB를 재확인해서 권한이 꺼지면
    토큰이 아직 유효 기간 안이어도 즉시 막혀야 한다(`apps/ops/authentication.py`)."""

    @patch("apps.ops.authentication.AccountRepository.find_credentials_by_id")
    def test_admin_flag_turned_off_is_rejected(self, find_credentials_by_id):
        find_credentials_by_id.return_value = admin_account(is_admin=False)
        token = ops_tokens.issue_token("UA001")

        response = self.client.get(OVERVIEW_URL, HTTP_AUTHORIZATION=f"Bearer {token}")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], REVOKED_DETAIL)

    @patch("apps.ops.authentication.AccountRepository.find_credentials_by_id")
    def test_locked_admin_account_is_rejected(self, find_credentials_by_id):
        find_credentials_by_id.return_value = admin_account(account_status="LOCKED")
        token = ops_tokens.issue_token("UA001")

        response = self.client.get(OVERVIEW_URL, HTTP_AUTHORIZATION=f"Bearer {token}")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], REVOKED_DETAIL)

    def test_regular_account_token_is_rejected(self):
        """`apps/accounts/tokens.py`는 salt가 달라서, 일반 로그인 토큰으로는
        서명 검증 자체가 실패해 DB까지 가지 않는다."""

        token = account_tokens.issue_token("UA001")

        response = self.client.get(OVERVIEW_URL, HTTP_AUTHORIZATION=f"Bearer {token}")

        self.assertEqual(response.status_code, 401)

    @patch("apps.ops.tokens.TOKEN_MAX_AGE_SECONDS", -1)
    def test_expired_ops_token_is_rejected(self):
        token = ops_tokens.issue_token("UA001")

        response = self.client.get(OVERVIEW_URL, HTTP_AUTHORIZATION=f"Bearer {token}")

        self.assertEqual(response.status_code, 401)

    def test_missing_token_is_rejected(self):
        response = self.client.get(OVERVIEW_URL)

        self.assertEqual(response.status_code, 401)


@patch("apps.ops.authentication.AccountRepository.find_credentials_by_id", return_value=admin_account())
@patch("apps.ops.views.models.log_audit")
@patch("apps.ops.views.models.CustomModelRepository")
class OpsModelRegisterTests(SimpleTestCase):
    """팀별 모델 등록 — **팀이 스스로 등록하지 않는다**(2026-08-13 멘토링).

    권한 범위는 여전히 팀이다. 등록하는 사람만 운영자로 바뀐다.
    """

    URL = "/api/ops/models/"
    BODY = {
        "team_id": "TE001",
        "label": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key": "AIza-x",
        "model": "models/gemini-3.6-flash",
    }

    def _headers(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {ops_tokens.issue_token('UA001')}"}

    @patch("apps.ops.views.models._verify", return_value=None)
    def test_그_팀에_등록한다(self, _verify, repo, _audit, _admin):
        repo.models_for_team.return_value = set()

        response = self.client.post(
            self.URL, self.BODY, content_type="application/json", **self._headers()
        )

        self.assertEqual(response.status_code, 201)
        kwargs = repo.add_for_team.call_args.kwargs
        self.assertEqual(kwargs["team_id"], "TE001")
        # 등록한 사람이 남아야 소유 계정만 보고 팀장이 등록한 것으로 오해하지 않는다.
        self.assertEqual(kwargs["registered_by"], "UA001")

    @patch("apps.ops.views.models._verify", return_value=None)
    def test_같은_팀에_같은_모델을_두_번_등록하지_않는다(self, _verify, repo, _audit, _admin):
        repo.models_for_team.return_value = {"models/gemini-3.6-flash"}

        response = self.client.post(
            self.URL, self.BODY, content_type="application/json", **self._headers()
        )

        self.assertEqual(response.status_code, 400)
        repo.add_for_team.assert_not_called()

    @patch("apps.ops.views.models._verify", return_value="이 주소와 모델로 답을 받지 못했습니다.")
    def test_안_도는_주소는_등록하지_않는다(self, _verify, repo, _audit, _admin):
        """등록해 두면 그 팀의 대화가 조용히 실패하고, 팀은 운영자가 등록했으니 되는 줄 안다."""

        repo.models_for_team.return_value = set()

        response = self.client.post(
            self.URL, self.BODY, content_type="application/json", **self._headers()
        )

        self.assertEqual(response.status_code, 400)
        repo.add_for_team.assert_not_called()

    def test_기본_제공_이름은_거절한다(self, repo, _audit, _admin):
        response = self.client.post(
            self.URL,
            {**self.BODY, "model": "gpt-5.6-luna"},
            content_type="application/json",
            **self._headers(),
        )

        self.assertEqual(response.status_code, 400)
        repo.add_for_team.assert_not_called()

    def test_키는_목록에_안_나온다(self, repo, _audit, _admin):
        repo.list_all.return_value = [
            {
                "conn_id": "CN002", "team_id": "TE001", "team_name": "개발팀",
                "label": "Google Gemini", "base_url": "https://x/v1",
                "model": "models/gemini-3.6-flash", "connected_at": None,
            }
        ]

        body = self.client.get(self.URL, **self._headers()).json()

        self.assertNotIn("api_key", body[0])
        self.assertEqual(body[0]["team_name"], "개발팀")

    def test_운영자가_아니면_못_본다(self, repo, _audit, _admin):
        token = account_tokens.issue_token("UA001")

        response = self.client.get(self.URL, HTTP_AUTHORIZATION=f"Bearer {token}")

        self.assertEqual(response.status_code, 401)
        repo.list_all.assert_not_called()

    @patch("apps.ops.views.models._verify", return_value=None)
    def test_등록_응답은_목록을_다시_만들지_않는다(self, _verify, repo, _audit, _admin):
        """목록을 만들다 실패하면 **이미 끝난 등록이 실패로 보고된다.**

        운영자는 안 됐다고 믿고 다시 누르고, 그때는 중복이라 거절당한다 — 무슨
        일이 벌어진 건지 아무도 모른다(2026-08-13 검토).
        """

        repo.models_for_team.return_value = set()

        self.client.post(self.URL, self.BODY, content_type="application/json", **self._headers())

        repo.list_all.assert_not_called()

    def test_지울_때_무엇을_지웠는지_남긴다(self, repo, audit, _admin):
        """행을 지우고 나면 conn_id 는 아무것도 안 가리킨다. 그 값만 남기면
        나중에 「어느 팀의 무슨 모델이 없어졌나」를 복원할 수 없다."""

        repo.remove_by_conn_id.return_value = {
            "team_id": "TE001", "model": "models/gemini-3.6-flash",
            "label": "Google Gemini", "base_url": "https://x/v1",
        }

        response = self.client.delete(f"{self.URL}CN002/", **self._headers())

        self.assertEqual(response.status_code, 204)
        kwargs = audit.call_args.kwargs
        self.assertEqual(kwargs["target_type"], "TEAM")
        self.assertEqual(kwargs["target_id"], "TE001")
        self.assertEqual(kwargs["payload"]["model"], "models/gemini-3.6-flash")

    def test_쓰는_에이전트가_있으면_못_지운다(self, repo, _audit, _admin):
        """지우면 그 에이전트는 실행 시점에 없는 모델을 부르다 죽는다."""

        from backend.db.errors import ReferenceNotFound

        repo.remove_by_conn_id.side_effect = ReferenceNotFound(
            "이 모델을 쓰는 에이전트가 있습니다: 회의록 정리."
        )

        response = self.client.delete(f"{self.URL}CN002/", **self._headers())

        self.assertEqual(response.status_code, 409)

    def test_모델_목록을_받아_온다(self, repo, _audit, _admin):
        """**이름을 외워 적게 하지 않는다** — 오타 하나가 실행 시점 404 가 된다."""

        with patch("openai.OpenAI") as client:
            client.return_value.models.list.return_value.data = [
                type("M", (), {"id": "models/gemini-3.6-flash"}),
                type("M", (), {"id": "models/gemini-3.6-pro"}),
            ]
            response = self.client.post(
                f"{self.URL}probe/",
                {"base_url": "https://x/v1", "api_key": "k"},
                content_type="application/json",
                **self._headers(),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["models"], ["models/gemini-3.6-flash", "models/gemini-3.6-pro"])

    def test_목록을_못_주면_이유를_준다(self, repo, _audit, _admin):
        """Anthropic 호환 경로는 401 이다. 그때는 화면이 직접 입력으로 넘어간다."""

        with patch("openai.OpenAI", side_effect=RuntimeError("401")):
            response = self.client.post(
                f"{self.URL}probe/",
                {"base_url": "https://x/v1", "api_key": "k"},
                content_type="application/json",
                **self._headers(),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["models"], [])
        self.assertTrue(response.json()["detail"])

    def test_probe_가_conn_id_에_먹히지_않는다(self, repo, _audit, _admin):
        """`models/probe/` 가 `models/<conn_id>/` 뒤에 있으면 삭제로 잡힌다."""

        from django.urls import resolve

        self.assertEqual(resolve("/api/ops/models/probe/").url_name, "api_ops_model_probe")


@patch("apps.ops.authentication.AccountRepository.find_credentials_by_id", return_value=admin_account())
@patch("apps.ops.views.accounts.OpsAccountRepository")
class OpsAdminGrantApiTests(SimpleTestCase):
    """운영자 권한 부여·회수.

    원래 이 경로는 API 에 없었다(`grant_admin.py` 로만 켰다). 콘솔이 자기 자신을
    관리하지 못하는 문제라 열되, 취지를 지키는 안전장치를 함께 둔다.
    """

    URL = "/api/ops/accounts/UA002/admin/"

    def _headers(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {ops_tokens.issue_token('UA001')}"}

    def test_권한을_준다(self, repo, _admin):
        repo.set_admin.return_value = {"account_id": "UA002", "is_admin": True}

        response = self.client.post(
            self.URL,
            {"is_admin": True, "reason": "운영 인수인계"},
            content_type="application/json",
            **self._headers(),
        )

        self.assertEqual(response.status_code, 200)
        kwargs = repo.set_admin.call_args.kwargs
        self.assertTrue(kwargs["is_admin"])
        self.assertEqual(kwargs["reason"], "운영 인수인계")
        # 누가 줬는지가 감사 기록의 핵심이다.
        self.assertEqual(kwargs["actor_account_id"], "UA001")

    def test_사유는_없어도_된다(self, repo, _admin):
        repo.set_admin.return_value = {"account_id": "UA002", "is_admin": False}

        response = self.client.post(
            self.URL, {"is_admin": False}, content_type="application/json", **self._headers()
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(repo.set_admin.call_args.kwargs["reason"], "")

    def test_is_admin_은_필수다(self, repo, _admin):
        """켜는지 끄는지를 안 주면 무엇을 하려는지 알 수 없다."""

        response = self.client.post(
            self.URL, {"reason": "x"}, content_type="application/json", **self._headers()
        )

        self.assertEqual(response.status_code, 400)
        repo.set_admin.assert_not_called()

    def test_운영자가_아니면_못_부른다(self, repo, _admin):
        token = account_tokens.issue_token("UA001")

        response = self.client.post(
            self.URL,
            {"is_admin": True},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(response.status_code, 401)
        repo.set_admin.assert_not_called()

    def test_본인_권한_회수는_403(self, repo, _admin):
        """실수로 스스로를 잠그면 되돌릴 방법이 없다."""

        from backend.db.errors import PermissionDenied

        repo.set_admin.side_effect = PermissionDenied("본인의 운영자 권한은 내릴 수 없습니다.")

        response = self.client.post(
            self.URL, {"is_admin": False}, content_type="application/json", **self._headers()
        )

        self.assertEqual(response.status_code, 403)

    def test_마지막_운영자_회수는_400(self, repo, _admin):
        """콘솔에 아무도 못 들어가는 상태를 화면에서 만들 수 있으면 안 된다."""

        from backend.db.errors import RepositoryError as RepoError

        repo.set_admin.side_effect = RepoError("마지막 운영자입니다.")

        response = self.client.post(
            self.URL, {"is_admin": False}, content_type="application/json", **self._headers()
        )

        self.assertEqual(response.status_code, 400)


@patch("apps.ops.authentication.AccountRepository.find_credentials_by_id", return_value=admin_account())
@patch("apps.ops.views.teams.OpsTeamRepository")
class OpsTeamOwnerTransferTests(SimpleTestCase):
    """팀 소유자 이전.

    **팀장이 나가면 그 팀을 아무도 손댈 수 없었다** — `owner_account_id` 를 바꾸는
    경로가 어디에도 없었다(2026-08-13 PM 지적).
    """

    URL = "/api/ops/teams/TE001/owner/"

    def _headers(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {ops_tokens.issue_token('UA001')}"}

    def test_후보는_그_팀_계정만_준다(self, repo, _admin):
        """계정 전체에서 고르게 하면 남의 팀 사람을 고를 수 있다."""

        repo.candidates.return_value = [
            {"account_id": "UA002", "email": "a@b.c", "display_name": "홍길동"}
        ]

        response = self.client.get(self.URL, **self._headers())

        self.assertEqual(response.status_code, 200)
        repo.candidates.assert_called_once_with("TE001")

    def test_넘긴다(self, repo, _admin):
        repo.transfer_owner.return_value = {
            "team_id": "TE001", "owner_account_id": "UA002", "moved_models": 1,
        }

        response = self.client.post(
            self.URL,
            {"account_id": "UA002", "reason": "팀장 퇴사"},
            content_type="application/json",
            **self._headers(),
        )

        self.assertEqual(response.status_code, 200)
        kwargs = repo.transfer_owner.call_args.kwargs
        self.assertEqual(kwargs["new_owner_account_id"], "UA002")
        self.assertEqual(kwargs["actor_account_id"], "UA001")
        self.assertEqual(kwargs["reason"], "팀장 퇴사")
        # 모델이 따라간 사실을 화면이 말할 수 있어야 한다.
        self.assertEqual(response.json()["moved_models"], 1)

    def test_남의_팀_계정에는_못_넘긴다(self, repo, _admin):
        """테넌트 경계가 그 자리에서 무너진다."""

        from backend.db.errors import PermissionDenied

        repo.transfer_owner.side_effect = PermissionDenied("이 팀에 속한 계정에게만 넘길 수 있습니다.")

        response = self.client.post(
            self.URL, {"account_id": "UA999"}, content_type="application/json", **self._headers()
        )

        self.assertEqual(response.status_code, 403)

    def test_정지된_계정에는_못_넘긴다(self, repo, _admin):
        from backend.db.errors import RepositoryError as RepoError

        repo.transfer_owner.side_effect = RepoError("정지된 계정에는 넘길 수 없습니다.")

        response = self.client.post(
            self.URL, {"account_id": "UA002"}, content_type="application/json", **self._headers()
        )

        self.assertEqual(response.status_code, 400)

    def test_account_id_는_필수다(self, repo, _admin):
        response = self.client.post(
            self.URL, {"reason": "x"}, content_type="application/json", **self._headers()
        )

        self.assertEqual(response.status_code, 400)
        repo.transfer_owner.assert_not_called()

    def test_운영자가_아니면_못_부른다(self, repo, _admin):
        token = account_tokens.issue_token("UA001")

        response = self.client.get(self.URL, HTTP_AUTHORIZATION=f"Bearer {token}")

        self.assertEqual(response.status_code, 401)
        repo.candidates.assert_not_called()


@patch("apps.ops.authentication.AccountRepository.find_credentials_by_id", return_value=admin_account())
@patch("apps.ops.views.accounts.OpsAccountRepository")
class OpsAccountDetailTests(SimpleTestCase):
    """계정 상세가 별도 페이지가 되면서 생긴 경로.

    목록 아래 섹션일 때는 목록이 이미 들고 있는 값을 썼다. 페이지가 갈리면
    **주소로 바로 들어올 수 있어야** 하므로 한 건을 줄 자리가 필요하다.
    """

    def _headers(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {ops_tokens.issue_token('UA001')}"}

    def test_한_건을_준다(self, repo, _admin):
        repo.get.return_value = {
            "account_id": "UA002", "email": "a@b.c", "display_name": "홍길동",
            "account_status": "ACTIVE", "is_admin": False, "team_id": "TE001",
            "team_name": "개발팀", "link_count": 1, "person_id": None,
            "person_name": None, "org_id": None, "org_name": None, "services": ["JIRA"],
        }

        response = self.client.get("/api/ops/accounts/UA002/", **self._headers())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["email"], "a@b.c")
        repo.get.assert_called_once_with("UA002")

    def test_없는_계정은_404(self, repo, _admin):
        from backend.db.errors import RecordNotFound

        repo.get.side_effect = RecordNotFound("존재하지 않는 계정입니다: UA999")

        response = self.client.get("/api/ops/accounts/UA999/", **self._headers())

        self.assertEqual(response.status_code, 404)

    def test_상세_경로가_조치_경로를_먹지_않는다(self, repo, _admin):
        """`accounts/<id>/` 를 `accounts/<id>/lock/` 보다 앞에 두면 잠금이 상세로 잡힌다."""

        from django.urls import resolve

        self.assertEqual(resolve("/api/ops/accounts/UA001/").url_name, "api_ops_account_detail")
        self.assertEqual(resolve("/api/ops/accounts/UA001/lock/").url_name, "api_ops_account_lock")
        self.assertEqual(resolve("/api/ops/accounts/UA001/admin/").url_name, "api_ops_account_admin")


@patch("apps.ops.authentication.AccountRepository.find_credentials_by_id", return_value=admin_account())
@patch("apps.ops.views.invites.OpsInviteRepository")
class OpsInviteDetailTests(SimpleTestCase):
    """초대 상세도 별도 페이지가 되면서 한 건을 줄 자리가 필요해졌다."""

    def _headers(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {ops_tokens.issue_token('UA001')}"}

    def test_한_건을_준다(self, repo, _admin):
        repo.get.return_value = {
            "invite_id": "IV001", "person_id": "PE001", "person_name": "홍길동",
            "person_email": "a@b.c", "org_id": "A001", "org_name": "개발본부",
            "invited_by": "UA001", "inviter_email": "x@y.z", "status": "PENDING",
            "expires_at": None, "accepted_at": None, "created_at": None,
            "linked_account_id": None, "linked_account_email": None,
            "linked_account_duplicate": False,
        }

        response = self.client.get("/api/ops/invites/IV001/", **self._headers())

        self.assertEqual(response.status_code, 200)
        repo.get.assert_called_once_with("IV001")

    def test_없는_초대는_404(self, repo, _admin):
        from backend.db.errors import RecordNotFound

        repo.get.side_effect = RecordNotFound("존재하지 않는 초대입니다: IV999")

        response = self.client.get("/api/ops/invites/IV999/", **self._headers())

        self.assertEqual(response.status_code, 404)

    def test_상세_경로가_조치_경로를_먹지_않는다(self, repo, _admin):
        from django.urls import resolve

        self.assertEqual(resolve("/api/ops/invites/IV001/").url_name, "api_ops_invite_detail")
        self.assertEqual(resolve("/api/ops/invites/IV001/discard/").url_name, "api_ops_invite_discard")
        self.assertEqual(resolve("/api/ops/invites/IV001/unlink/").url_name, "api_ops_invite_unlink")


@patch("apps.ops.authentication.AccountRepository.find_credentials_by_id", return_value=admin_account())
@patch("apps.ops.views.teams.OpsTeamRepository")
class OpsTeamContentTests(SimpleTestCase):
    """고객이 「에이전트가 이상해요」라고 할 때 운영자가 볼 것이 아무것도 없었다.

    **경계는 유지한다** — 무엇을 들고 있고 무슨 일이 있었는지는 보되, 대화 내용과
    문서 원문은 주지 않는다.
    """

    URL = "/api/ops/teams/TE001/content/"

    def _headers(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {ops_tokens.issue_token('UA001')}"}

    def test_에이전트와_실행을_준다(self, repo, _admin):
        repo.agents.return_value = [
            {"agent_id": "AG001", "name": "코파일럿", "model": "gpt-5.6-luna", "tool_refs": ["agent:*"]}
        ]
        repo.runs.return_value = [
            {"run_id": "r1", "agent_name": "코파일럿", "status": "FAILED", "failed_tools": ["jira_get_issues (401)"]}
        ]

        body = self.client.get(self.URL, **self._headers()).json()

        self.assertEqual(body["agents"][0]["name"], "코파일럿")
        # 왜 실패했는지가 그 줄에 있어야 운영자가 답할 수 있다.
        self.assertEqual(body["runs"][0]["failed_tools"], ["jira_get_issues (401)"])
        repo.agents.assert_called_once_with("TE001")
        repo.runs.assert_called_once_with("TE001")

    def test_대화나_문서는_주지_않는다(self, repo, _admin):
        """열람 통제 장치가 없는 상태에서 고객의 업무 내용까지 열지 않는다."""

        repo.agents.return_value = []
        repo.runs.return_value = []

        body = self.client.get(self.URL, **self._headers()).json()

        self.assertEqual(set(body), {"agents", "runs"})

    def test_운영자가_아니면_못_본다(self, repo, _admin):
        token = account_tokens.issue_token("UA001")

        response = self.client.get(self.URL, HTTP_AUTHORIZATION=f"Bearer {token}")

        self.assertEqual(response.status_code, 401)
        repo.agents.assert_not_called()
