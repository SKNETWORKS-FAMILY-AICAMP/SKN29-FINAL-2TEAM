from unittest.mock import patch

from django.test import SimpleTestCase

from apps.accounts.tokens import issue_token
from backend.db.errors import PermissionDenied, RecordNotFound, ReferenceNotFound


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
    @patch("apps.projects.api_views.ProjectRepository.archive_if_all_done", return_value=[])
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
    @patch("apps.projects.api_views.ProjectRepository.archive_if_all_done", return_value=["PJ003"])
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
    @patch("apps.projects.api_views.ProjectRepository.archive_if_all_done", return_value=[])
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
    @patch("apps.projects.api_views.ProjectRepository.archive_if_all_done", return_value=[])
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
    @patch("apps.projects.api_views.ProjectRepository.archive_if_all_done", return_value=[])
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


class ProjectSourceApiTests(SimpleTestCase):
    def test_requires_login(self):
        self.assertEqual(self.client.get("/api/projects/PJ001/sources/").status_code, 401)

    @patch("apps.projects.api_views.ProjectSourceRepository.get_for_project")
    def test_returns_at_most_one_jira_source(self, get_for_project):
        get_for_project.return_value = jira_source_row()

        response = self.client.get("/api/projects/PJ001/sources/", headers=auth_header())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]["external_source_id"], "KAN")

    @patch("apps.projects.api_views.ProjectSourceRepository.get_for_project")
    def test_unconnected_project_returns_empty(self, get_for_project):
        get_for_project.return_value = None

        response = self.client.get("/api/projects/PJ001/sources/", headers=auth_header())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    @patch("apps.projects.api_views.ProjectSourceRepository.get_for_project")
    def test_other_teams_project_is_forbidden(self, get_for_project):
        get_for_project.side_effect = PermissionDenied("이 프로젝트에 접근할 수 없습니다.")

        response = self.client.get("/api/projects/PJ001/sources/", headers=auth_header())

        self.assertEqual(response.status_code, 403)

    @patch("apps.projects.api_views.ProjectSourceRepository.get_for_project")
    def test_missing_project_is_404(self, get_for_project):
        get_for_project.side_effect = RecordNotFound("존재하지 않는 프로젝트입니다: PJ999")

        response = self.client.get("/api/projects/PJ999/sources/", headers=auth_header())

        self.assertEqual(response.status_code, 404)


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


@patch("apps.projects.api_views.lookup_persons", return_value={"PX002": {"name": "임준"}})
@patch("apps.projects.api_views.ExistTaskRepository.list_for_project")
@patch("apps.projects.api_views.ProjectSourceRepository.last_sync_by_project", return_value={})
@patch("apps.projects.api_views.ExistTaskRepository.progress_by_project", return_value={})
@patch("apps.projects.api_views.ProjectRepository.get_for_team")
class ProjectDetailApiTests(SimpleTestCase):
    """상세 화면은 프로젝트·진행률·업무 목록을 한 번에 받는다."""

    def test_requires_login(self, *_mocks):
        self.assertEqual(self.client.get("/api/projects/PJ001/").status_code, 401)

    def test_returns_tasks_with_assignee_names(self, get_for_team, _p, _l, list_tasks, _n):
        get_for_team.return_value = project_row()
        list_tasks.return_value = [task_row()]

        body = self.client.get("/api/projects/PJ001/", headers=auth_header()).json()

        self.assertEqual(body["proj_id"], "PJ001")
        self.assertEqual(body["tasks"][0]["summary"], "[MOCK] Orchestrator")
        self.assertEqual(body["tasks"][0]["assignee_name"], "임준")

    def test_unmapped_assignee_is_kept(self, get_for_team, _p, _l, list_tasks, _n):
        """담당자 매핑이 안 돼도 목록에서 빼지 않는다 — 빼면 합계가 어긋난다."""

        get_for_team.return_value = project_row()
        list_tasks.return_value = [task_row(person=None)]

        body = self.client.get("/api/projects/PJ001/", headers=auth_header()).json()

        self.assertEqual(len(body["tasks"]), 1)
        self.assertIsNone(body["tasks"][0]["assignee_name"])

    def test_missing_summary_is_null_not_invented(self, get_for_team, _p, _l, list_tasks, _n):
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
