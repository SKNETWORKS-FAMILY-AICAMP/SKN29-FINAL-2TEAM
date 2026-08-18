from unittest.mock import patch

from django.test import SimpleTestCase

from apps.accounts.tokens import issue_token
from backend.db.errors import PermissionDenied, ReferenceNotFound


def auth_header(account_id="UA001"):
    return {"authorization": f"Bearer {issue_token(account_id)}"}


def project_row(proj_id="PJ001", name="SKN29_Final_2Team", status="ACTIVE", owner="UA001"):
    return {
        "proj_id": proj_id,
        "name": name,
        "status": status,
        "tz": "Asia/Seoul",
        "owner_account_id": owner,
        "team_id": "TE001",
        "owner_name": "임준",
    }


def folder_row(
    team_folder_id="TF001",
    external="folder-SKN29",
    max_depth=1,
    display_name=None,
):
    return {
        "team_folder_id": team_folder_id,
        "team_id": "TE001",
        "conn_id": "CN002",
        "external_folder_id": external,
        "display_name": display_name,
        "max_depth": max_depth,
    }


def jira_source_row(proj_source_id="PS009", proj_id="PJ001", external="KAN", display_name=None):
    return {
        "proj_source_id": proj_source_id,
        "proj_id": proj_id,
        "conn_id": "CN003",
        "source_type": "JIRA_PROJECT",
        "external_source_id": external,
        "display_name": display_name,
        "sync_status": "PENDING",
        "last_sync_at": None,
    }


def drive_file(file_id, name, supported=True, mime="application/pdf"):
    return {
        "file_id": file_id,
        "name": name,
        "mime_type": mime,
        "modified_at": "2026-07-24T05:20:18.540Z",
        "supported": supported,
    }


def doc_row(doc_id="DC001", src_file_id="file-plan", name="기획서.docx", role=None):
    return {
        "doc_id": doc_id,
        "team_id": "TE001",
        # 등록 시점에는 어느 프로젝트의 문서인지도, 그 안에서 무슨 역할인지도
        # 모른다. `doc_role`은 기준 문서로 선택될 때 PRIMARY/SUB 가 된다.
        "proj_id": None,
        "src_file_id": src_file_id,
        "source_type": "DRIVE",
        "file_name": name,
        "mime_type": "application/pdf",
        "doc_role": role,
        "src_modified_at": None,
        "deleted": False,
    }


class ProjectListCreateApiTests(SimpleTestCase):
    def test_requires_login(self):
        self.assertEqual(self.client.get("/api/projects/").status_code, 401)
        self.assertEqual(self.client.post("/api/projects/", {"name": "몰래"}).status_code, 401)

    @patch("apps.projects.api_views.ProjectSourceRepository.last_sync_by_project")
    @patch("apps.projects.api_views.ExistTaskRepository.progress_by_project")
    @patch("apps.projects.api_views.ProjectRepository.list_for_team")
    def test_lists_my_teams_projects(self, list_for_team, progress, last_sync):
        """소유자가 아니라 **팀** 기준이다. 팀원도 팀의 프로젝트를 봐야 한다."""

        list_for_team.return_value = [project_row()]
        progress.return_value = {}
        last_sync.return_value = {}

        response = self.client.get("/api/projects/", headers=auth_header())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["proj_id"], "PJ001")
        list_for_team.assert_called_once_with("UA001")

    @patch("apps.projects.api_views.ProjectRepository.create")
    def test_owner_comes_from_the_token_not_the_request(self, create):
        create.return_value = project_row()

        response = self.client.post(
            "/api/projects/",
            {"name": "SKN29", "owner_account_id": "UA999"},
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(create.call_args.kwargs["owner_account_id"], "UA001")


class JiraProjectRegisterApiTests(SimpleTestCase):
    """Jira 프로젝트를 고르는 것이 곧 프로젝트를 등록하는 것이다(1:1)."""

    def body(self, projects):
        return {"projects": list(projects)}

    def test_requires_login(self):
        self.assertEqual(
            self.client.put(
                "/api/projects/jira/",
                self.body([{"project_key": "KAN"}]),
                content_type="application/json",
            ).status_code,
            401,
        )

    @patch("apps.projects.api_views.ExistTaskRepository.list_jira_sources_for_team")
    @patch("apps.projects.api_views.ProjectRepository.sync_status_from_tasks", return_value={"archived": [], "reopened": []})
    @patch("apps.projects.api_views._sync_jira_sources", return_value={"failed": []})
    @patch("apps.projects.api_views.ProjectSourceRepository.register_from_jira")
    def test_each_jira_project_becomes_one_project(self, register, _sync, _arch, list_team):
        rows = [
            jira_source_row("PS009", "PJ001", "KAN", "SKN29_Final_2Team"),
            jira_source_row("PS010", "PJ002", "AIP", "AI Platform"),
        ]
        register.return_value = rows
        list_team.return_value = rows

        response = self.client.put(
            "/api/projects/jira/",
            self.body(
                [
                    {"project_key": "KAN", "name": "SKN29_Final_2Team"},
                    {"project_key": "AIP", "name": "AI Platform"},
                ]
            ),
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 200)
        # 같은 프로젝트에 둘이 붙지 않는다 — 각자 자기 프로젝트를 갖는다.
        by_key = {row["project_key"]: row["proj_id"] for row in response.json()["sources"]}
        self.assertEqual(by_key, {"KAN": "PJ001", "AIP": "PJ002"})

    @patch("apps.projects.api_views.ExistTaskRepository.list_jira_sources_for_team", return_value=[])
    @patch("apps.projects.api_views.ProjectRepository.sync_status_from_tasks", return_value={"archived": ["PJ003"], "reopened": []})
    @patch("apps.projects.api_views._sync_jira_sources", return_value={"failed": []})
    @patch("apps.projects.api_views.ProjectSourceRepository.register_from_jira")
    def test_already_finished_project_starts_archived(self, register, sync, archive, _t):
        """이미 끝난 프로젝트를 가져오면 완료 구획에서 시작해야 한다."""

        register.return_value = [jira_source_row("PS011", "PJ003", "LEG", "문서관리 고도화")]

        body = self.client.put(
            "/api/projects/jira/",
            self.body([{"project_key": "LEG", "name": "문서관리 고도화"}]),
            content_type="application/json",
            headers=auth_header(),
        ).json()

        # 등록하자마자 읽는다 — 안 읽으면 완료인지 판단할 근거가 없다.
        sync.assert_called_once()
        self.assertEqual(archive.call_args.args[0], ["PJ003"])
        self.assertEqual(body["archived"], ["PJ003"])

    @patch("apps.projects.api_views.ExistTaskRepository.list_jira_sources_for_team", return_value=[])
    @patch("apps.projects.api_views.ProjectRepository.sync_status_from_tasks", return_value={"archived": [], "reopened": []})
    @patch("apps.projects.api_views._sync_jira_sources", return_value={"failed": []})
    @patch("apps.projects.api_views.ProjectSourceRepository.register_from_jira")
    def test_already_registered_source_is_not_reread(self, register, sync, archive, _t):
        """다시 저장했다고 이미 읽은 것을 또 읽지 않는다 — 완료 판정도 다시 하지 않는다."""

        register.return_value = [
            jira_source_row("PS009", "PJ001", "KAN") | {"last_sync_at": "2026-08-04T00:00:00Z"}
        ]

        self.client.put(
            "/api/projects/jira/",
            self.body([{"project_key": "KAN"}]),
            content_type="application/json",
            headers=auth_header(),
        )

        sync.assert_not_called()
        self.assertEqual(archive.call_args.args[0], [])

    @patch("apps.projects.api_views.ExistTaskRepository.list_jira_sources_for_team", return_value=[])
    @patch("apps.projects.api_views.ProjectRepository.sync_status_from_tasks", return_value={"archived": [], "reopened": []})
    @patch("apps.projects.api_views._sync_jira_sources", return_value={"failed": []})
    @patch("apps.projects.api_views.ProjectSourceRepository.register_from_jira")
    def test_display_name_becomes_the_project_name(self, register, _s, _a, _t):
        """화면이 'KAN'이 아니라 'SKN29_Final_2Team'을 보여줘야 한다.

        나중에 원본에 다시 물어보면, 토큰이 만료됐을 때 저장된 데이터는 멀쩡한데
        이름을 못 읽어 화면이 깨진다. 고르는 시점에 같이 저장한다.
        """

        register.return_value = [jira_source_row(display_name="SKN29_Final_2Team")]

        response = self.client.put(
            "/api/projects/jira/",
            self.body([{"project_key": "KAN", "name": "SKN29_Final_2Team"}]),
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            register.call_args.kwargs["selections"],
            [{"project_key": "KAN", "name": "SKN29_Final_2Team"}],
        )

    @patch("apps.projects.api_views.ExistTaskRepository.list_jira_sources_for_team", return_value=[])
    @patch("apps.projects.api_views.ProjectRepository.sync_status_from_tasks", return_value={"archived": [], "reopened": []})
    @patch("apps.projects.api_views.ProjectSourceRepository.register_from_jira")
    def test_empty_list_clears_the_selection(self, register, _a, _t):
        register.return_value = []

        response = self.client.put(
            "/api/projects/jira/",
            self.body([]),
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sources"], [])

    @patch("apps.projects.api_views.ProjectSourceRepository.register_from_jira")
    def test_missing_project_key_is_rejected(self, register):
        response = self.client.put(
            "/api/projects/jira/",
            self.body([{"name": "이름만"}]),
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 400)
        register.assert_not_called()

    @patch("apps.projects.api_views.ProjectSourceRepository.register_from_jira")
    def test_unconnected_connector_is_a_conflict(self, register):
        register.side_effect = ReferenceNotFound("JIRA 커넥터가 연결되지 않았습니다.")

        response = self.client.put(
            "/api/projects/jira/",
            self.body([{"project_key": "KAN"}]),
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 409)

    @patch("apps.projects.api_views.ProjectSourceRepository.register_from_jira")
    def test_account_without_a_team_is_forbidden(self, register):
        register.side_effect = PermissionDenied("팀에 속하지 않은 계정입니다.")

        response = self.client.put(
            "/api/projects/jira/",
            self.body([{"project_key": "KAN"}]),
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 403)


class TeamFolderApiTests(SimpleTestCase):
    """폴더는 팀에 매단다 — 프로젝트가 아니라."""

    def replace_body(self, ids=("folder-SKN29",)):
        return {"external_folder_ids": list(ids)}

    def test_requires_login(self):
        self.assertEqual(self.client.get("/api/team/folders/").status_code, 401)
        self.assertEqual(
            self.client.put(
                "/api/team/folders/",
                self.replace_body(),
                content_type="application/json",
            ).status_code,
            401,
        )

    @patch("apps.projects.api_views.TeamFolderRepository.list_for_team")
    def test_lists_the_teams_folders(self, list_for_team):
        list_for_team.return_value = [folder_row()]

        response = self.client.get("/api/team/folders/", headers=auth_header())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["external_folder_id"], "folder-SKN29")
        list_for_team.assert_called_once_with("UA001")

    @patch("apps.projects.api_views.TeamFolderRepository.replace")
    def test_saves_drive_folders(self, replace):
        replace.return_value = [folder_row()]

        response = self.client.put(
            "/api/team/folders/",
            self.replace_body(ids=("folder-SKN29", "folder-산출물")),
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            replace.call_args.kwargs,
            {
                "account_id": "UA001",
                "external_folder_ids": ["folder-SKN29", "folder-산출물"],
                # 보내지 않으면 하위 폴더를 따라 내려가지 않는다.
                "max_depth": 1,
                # 이름을 안 보내면 빈 map이고, 리포지토리가 이전에 저장한 이름을 지킨다.
                "display_names": {},
            },
        )

    @patch("apps.projects.api_views.TeamFolderRepository.replace")
    def test_display_names_are_saved(self, replace):
        replace.return_value = [folder_row(display_name="01_기획")]

        response = self.client.put(
            "/api/team/folders/",
            self.replace_body() | {"display_names": {"folder-SKN29": "01_기획"}},
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(replace.call_args.kwargs["display_names"], {"folder-SKN29": "01_기획"})

    @patch("apps.projects.api_views.TeamFolderRepository.replace")
    def test_scan_depth_is_saved(self, replace):
        replace.return_value = [folder_row(max_depth=3)]

        response = self.client.put(
            "/api/team/folders/",
            self.replace_body() | {"max_depth": 3},
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(replace.call_args.kwargs["max_depth"], 3)
        self.assertEqual(response.json()[0]["max_depth"], 3)

    @patch("apps.projects.api_views.TeamFolderRepository.replace")
    def test_null_depth_means_unlimited(self, replace):
        replace.return_value = [folder_row(max_depth=None)]

        response = self.client.put(
            "/api/team/folders/",
            self.replace_body() | {"max_depth": None},
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(replace.call_args.kwargs["max_depth"])

    @patch("apps.projects.api_views.TeamFolderRepository.replace")
    def test_absurd_depth_is_rejected(self, replace):
        response = self.client.put(
            "/api/team/folders/",
            self.replace_body() | {"max_depth": 999},
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 400)
        replace.assert_not_called()

    @patch("apps.projects.api_views.TeamFolderRepository.replace")
    def test_empty_list_clears_the_selection(self, replace):
        replace.return_value = []

        response = self.client.put(
            "/api/team/folders/",
            self.replace_body(ids=()),
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])
        self.assertEqual(replace.call_args.kwargs["external_folder_ids"], [])

    @patch("apps.projects.api_views.TeamFolderRepository.replace")
    def test_unconnected_connector_is_a_conflict(self, replace):
        replace.side_effect = ReferenceNotFound("GOOGLE_DRIVE 커넥터가 연결되지 않았습니다.")

        response = self.client.put(
            "/api/team/folders/",
            self.replace_body(),
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 409)

    @patch("apps.projects.api_views.TeamFolderRepository.replace")
    def test_account_without_a_team_is_forbidden(self, replace):
        replace.side_effect = PermissionDenied("팀에 속하지 않은 계정입니다.")

        response = self.client.put(
            "/api/team/folders/",
            self.replace_body(),
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 403)

class TeamDocumentListApiTests(SimpleTestCase):
    """팀 문서 목록(GET).

    PUT(역할 지정 저장)은 없앴다(2026-08-04). 폴더에 준 역할을 안의 파일이 그대로
    물려받는 화면이었는데, 그 값으로 분기하는 코드가 한 줄도 없었다.
    """

    @patch("apps.projects.api_views.DocumentRepository.list_for_team")
    def test_lists_registered_documents(self, list_for_team):
        list_for_team.return_value = [doc_row()]

        response = self.client.get("/api/team/documents/", headers=auth_header())

        self.assertEqual(response.status_code, 200)
        # 등록만 된 문서는 아직 어느 프로젝트에도 안 묶였다.
        self.assertIsNone(response.json()[0]["proj_id"])
        self.assertIsNone(response.json()[0]["doc_role"])
        list_for_team.assert_called_once_with("UA001")

    @patch("apps.projects.api_views.DocumentRepository.list_for_team", return_value=[])
    def test_role_save_endpoint_is_gone(self, _list_for_team):
        response = self.client.put(
            "/api/team/documents/", {}, content_type="application/json", headers=auth_header()
        )

        self.assertEqual(response.status_code, 405)



def task_row(key="KAN-34", summary="[MOCK] Orchestrator", person="PX002", category="TO_DO"):
    return {
        "exist_task_id": "ET001",
        "jira_issue_id": key,
        "summary": summary,
        "assignee_person_id": person,
        "status": "해야 할 일",
        "status_category": category,
        "due_at": None,
        "estimate": 48,
        "remaining": 48,
        "proj_id": "PJ001",
        "project_key": "KAN",
        "project_name": "SKN29_Final_2Team",
    }


#: **저장소를 하나라도 빼먹으면 그 호출은 실제 DB 로 나간다.**
#:
#: 이 저장소들은 psycopg 직결이라 Django 테스트 DB 를 타지 않는다. 상세 화면에
#: `ProjectTaskRepository` 를 붙였을 때 이 줄을 안 늘려서, **개발 DB 에 팀이
#: 있는 동안만 우연히 통과**하고 있었다 — DB 를 초기화하니 `_require_team` 이
#: 터지면서 세 건이 한꺼번에 깨졌다(2026-08-12).
@patch("apps.projects.api_views.ProjectTaskRepository.list_for_project", return_value=[])
@patch("apps.projects.api_views.lookup_persons", return_value={"PX002": {"name": "임준"}})
@patch("apps.projects.api_views.ExistTaskRepository.list_for_project")
@patch("apps.projects.api_views.ProjectSourceRepository.last_sync_by_project", return_value={})
@patch("apps.projects.api_views.ExistTaskRepository.progress_by_project", return_value={})
@patch("apps.projects.api_views.ProjectRepository.get_for_team")
class ProjectDetailApiTests(SimpleTestCase):
    """상세 화면은 프로젝트·진행률·업무 목록을 한 번에 받는다."""

    def test_requires_login(self, *_mocks):
        self.assertEqual(self.client.get("/api/projects/PJ001/").status_code, 401)

    def test_returns_tasks_with_assignee_names(self, get_for_team, _p, _l, list_tasks, _n, _extracted):
        get_for_team.return_value = project_row()
        list_tasks.return_value = [task_row()]

        body = self.client.get("/api/projects/PJ001/", headers=auth_header()).json()

        self.assertEqual(body["proj_id"], "PJ001")
        self.assertEqual(body["tasks"][0]["summary"], "[MOCK] Orchestrator")
        self.assertEqual(body["tasks"][0]["assignee_name"], "임준")

    def test_unmapped_assignee_is_kept(self, get_for_team, _p, _l, list_tasks, _n, _extracted):
        """담당자 매핑이 안 돼도 목록에서 빼지 않는다 — 빼면 합계가 어긋난다."""

        get_for_team.return_value = project_row()
        list_tasks.return_value = [task_row(person=None)]

        body = self.client.get("/api/projects/PJ001/", headers=auth_header()).json()

        self.assertEqual(len(body["tasks"]), 1)
        self.assertIsNone(body["tasks"][0]["assignee_name"])

    def test_missing_summary_is_null_not_invented(self, get_for_team, _p, _l, list_tasks, _n, _extracted):
        get_for_team.return_value = project_row()
        list_tasks.return_value = [task_row(summary=None)]

        body = self.client.get("/api/projects/PJ001/", headers=auth_header()).json()

        self.assertIsNone(body["tasks"][0]["summary"])

    def test_other_teams_project_is_forbidden(self, get_for_team, *_mocks):
        get_for_team.side_effect = PermissionDenied("이 프로젝트에 접근할 수 없습니다.")

        response = self.client.get("/api/projects/PJ001/", headers=auth_header())

        self.assertEqual(response.status_code, 403)


class ProjectStatusApiTests(SimpleTestCase):
    def _patch(self, body):
        return self.client.patch(
            "/api/projects/PJ001/", body, content_type="application/json", headers=auth_header()
        )

    def test_requires_login(self):
        response = self.client.patch(
            "/api/projects/PJ001/", {"status": "ARCHIVED"}, content_type="application/json"
        )
        self.assertEqual(response.status_code, 401)

    @patch("apps.projects.api_views.ProjectRepository.set_status")
    def test_archives_the_project(self, set_status):
        set_status.return_value = project_row(status="ARCHIVED")

        response = self._patch({"status": "ARCHIVED"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ARCHIVED")
        self.assertEqual(set_status.call_args.kwargs["status"], "ARCHIVED")

    @patch("apps.projects.api_views.ProjectRepository.set_status")
    def test_can_be_undone(self, set_status):
        set_status.return_value = project_row(status="ACTIVE")

        self.assertEqual(self._patch({"status": "ACTIVE"}).status_code, 200)

    @patch("apps.projects.api_views.ProjectRepository.set_status")
    def test_draft_is_rejected(self, set_status):
        """DRAFT는 온보딩이 만들다 만 프로젝트를 뜻했다. 이제 그런 상태는 없다."""

        self.assertEqual(self._patch({"status": "DRAFT"}).status_code, 400)
        set_status.assert_not_called()


class ProjectDeleteApiTests(SimpleTestCase):
    """삭제는 되돌릴 수 없다. 무엇을 지우고 무엇을 남기는지 고정한다."""

    def test_requires_login(self):
        response = self.client.delete("/api/projects/PJ001/")
        self.assertEqual(response.status_code, 401)

    @patch("apps.projects.api_views.ProjectRepository.delete")
    def test_reports_what_was_removed(self, delete):
        delete.return_value = {"tasks": 12, "sources": 1, "documents_released": 1}

        # 다른 화면들이 쓰는 PJ001 을 피한다. 같은 id 면 "경로의 것을 지웠는가"를
        # 확인하지 못한다 — 무엇을 넣어도 통과한다.
        response = self.client.delete("/api/projects/PJ007/", headers=auth_header())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tasks"], 12)
        # 문서는 지운 것이 아니라 풀어 준 것이다. 화면이 그렇게 말해야 한다.
        self.assertEqual(response.json()["documents_released"], 1)
        self.assertEqual(delete.call_args.kwargs["proj_id"], "PJ007")

    @patch(
        "apps.projects.api_views.ProjectRepository.delete",
        side_effect=PermissionDenied("이 프로젝트에 접근할 수 없습니다."),
    )
    def test_other_team_project_is_forbidden(self, _delete):
        response = self.client.delete("/api/projects/PJ999/", headers=auth_header())
        self.assertEqual(response.status_code, 403)


class PrimaryCandidateRankTests(SimpleTestCase):
    """기준 문서 후보의 순위와 컷.

    실측(2026-08-11)에서 나온 그대로를 고정한다 — 팀 문서가 3건이라 무엇을
    물어도 3건이 다 나왔고, 이름이 통째로 든 제안요청서가 0.52 로 회사소개서
    (0.08)와 같은 목록에 섞였다.
    """

    NAME = "IRInstitutional-Research-정보시스템-구축"

    ROWS = [
        {
            "doc_id": "DC001",
            "file_name": "2021-07-01-IRInstitutional-Research-정보시스템-구축-3차년도.pdf",
            "summary": "삼육대학교 IR 정보시스템 3차년도 고도화 제안요청서",
            "summary_score": 0.52,
            "search_ready": True,
        },
        {
            "doc_id": "DC002",
            "file_name": "22-101호 용역제안서_차세대정보시스템 ERP재구축 사업 감리용역.pdf",
            "summary": "차세대 정보시스템 ERP 재구축 감리 제안요청",
            "summary_score": 0.35,
            "search_ready": True,
        },
        {
            "doc_id": "DC003",
            "file_name": "테스트.pdf",
            "summary": "한화파워 회사 개요와 산업용 압축기 제품 소개",
            "summary_score": 0.08,
            "search_ready": True,
        },
    ]

    def _ranked(self):
        from apps.projects.api_views import _rank

        return _rank([dict(row) for row in self.ROWS], name=self.NAME)

    def test_이름이_일치하는_문서가_1등이다(self):
        self.assertEqual(self._ranked()[0]["doc_id"], "DC001")

    def test_파일명_일치를_따로_센다(self):
        """요약 임베딩은 파일명을 안 본다. 그 단서를 여기서 되살린다."""

        ranked = {row["doc_id"]: row for row in self._ranked()}
        self.assertEqual(ranked["DC001"]["name_score"], 1.0)

    def test_무관한_문서는_잘린다(self):
        """팀 문서가 3건이면 3건이 다 나오는 목록은 아무 정보도 주지 않는다."""

        self.assertNotIn("DC003", [row["doc_id"] for row in self._ranked()])

    def test_후보가_없으면_빈_목록이다(self):
        from apps.projects.api_views import _rank

        self.assertEqual(_rank([], name=self.NAME), [])

    def test_혼자_남아도_무관하면_후보가_아니다(self):
        """상대 컷오프는 1등을 못 자른다 — 자기 자신이 기준이라 늘 통과한다.

        「AI Platform」 프로젝트에 아무 상관 없는 정보시스템 구축 제안요청서가
        요약 21%·파일명 0% 로 **유일 후보**에 올랐고, 사람이 그걸 골라 감리 업무
        7건이 등록됐다(2026-08-12 QA 시나리오 B).
        """

        from apps.projects.api_views import _rank

        rows = [dict(self.ROWS[0], summary_score=0.21)]
        self.assertEqual(_rank(rows, name="AI Platform"), [])

    def test_한쪽_신호만_넘어도_후보다(self):
        """둘 다 바닥일 때만 자른다. 어느 한 신호의 절대값에 기대지 않는다."""

        from apps.projects.api_views import _rank

        # 요약은 바닥인데 파일명이 통째로 걸리는 문서.
        by_name = [dict(self.ROWS[0], summary_score=0.05)]
        self.assertEqual([row["doc_id"] for row in _rank(by_name, name=self.NAME)], ["DC001"])

        # 파일명은 안 걸리는데 내용이 닮은 문서.
        by_summary = [dict(self.ROWS[0], file_name="무제.pdf", summary_score=0.61)]
        self.assertEqual([row["doc_id"] for row in _rank(by_summary, name="AI Platform")], ["DC001"])


@patch("apps.projects.api_views.ExistTaskRepository")
@patch("apps.projects.api_views._sync_jira_sources", return_value={"synced": [], "failed": []})
@patch("apps.projects.api_views.ProjectRepository.sync_status_from_tasks")
class ProjectSyncStatusTests(SimpleTestCase):
    """**갱신은 Jira 상태로 다시 맞춰 달라는 뜻이다**(2026-08-13 PM).

    예전에는 등록 직후 한 번만 완료 여부를 판정했다. 그 한 번을 놓치면 업무가 전부
    끝난 프로젝트가 영영 「진행중」에 남았다 — 실제로 12건 전부 완료인 프로젝트가
    그렇게 있었다.
    """

    def test_프로젝트_갱신이_완료_여부를_다시_본다(self, sync_status, _sync, tasks):
        sync_status.return_value = {"archived": ["PJ004"], "reopened": []}
        tasks.list_jira_sources.return_value = []

        response = self.client.post("/api/projects/PJ004/tasks/sync/", headers=auth_header())

        self.assertEqual(response.status_code, 200)
        sync_status.assert_called_once_with(["PJ004"])
        self.assertEqual(response.json()["status_changed"]["archived"], ["PJ004"])

    def test_팀_갱신은_읽은_프로젝트_전부를_본다(self, sync_status, _sync, tasks):
        sync_status.return_value = {"archived": [], "reopened": []}
        tasks.list_jira_sources_for_team.return_value = [
            {"proj_source_id": "PS002", "proj_id": "PJ003", "external_source_id": "KAN"},
            {"proj_source_id": "PS003", "proj_id": "PJ004", "external_source_id": "LEG"},
            # 한 프로젝트에 소스가 여럿이어도 판정은 한 번이면 된다.
            {"proj_source_id": "PS004", "proj_id": "PJ004", "external_source_id": "OPS"},
        ]

        self.client.post("/api/team/tasks/sync/", headers=auth_header())

        sync_status.assert_called_once_with(["PJ003", "PJ004"])
