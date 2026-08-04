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
    role=None,
    max_depth=1,
    display_name=None,
):
    return {
        "team_folder_id": team_folder_id,
        "team_id": "TE001",
        "conn_id": "CN002",
        "external_folder_id": external,
        "display_name": display_name,
        "default_doc_role": role,
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


def doc_row(doc_id="DC001", src_file_id="file-plan", name="기획서.docx", role="PLAN"):
    return {
        "doc_id": doc_id,
        "team_id": "TE001",
        # 등록 시점에는 어느 프로젝트의 문서인지 모른다.
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

    @patch("apps.projects.api_views.ProjectSourceRepository.register_from_jira")
    def test_each_jira_project_becomes_one_project(self, register):
        register.return_value = [
            jira_source_row("PS009", "PJ001", "KAN", "SKN29_Final_2Team"),
            jira_source_row("PS010", "PJ002", "AIP", "AI Platform"),
        ]

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
        by_key = {row["external_source_id"]: row["proj_id"] for row in response.json()}
        self.assertEqual(by_key, {"KAN": "PJ001", "AIP": "PJ002"})

    @patch("apps.projects.api_views.ProjectSourceRepository.register_from_jira")
    def test_display_name_becomes_the_project_name(self, register):
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

    @patch("apps.projects.api_views.ProjectSourceRepository.register_from_jira")
    def test_empty_list_clears_the_selection(self, register):
        register.return_value = []

        response = self.client.put(
            "/api/projects/jira/",
            self.body([]),
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

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


@patch("apps.projects.api_views.DocumentRepository.save_drive_documents")
@patch("apps.projects.api_views.list_drive_files")
@patch("apps.projects.api_views.TeamFolderRepository.list_for_team")
class DocumentRoleSaveApiTests(SimpleTestCase):
    """역할 지정 저장. 파일 목록은 서버가 Drive에서 다시 읽는다."""

    PLAN_FILE = "file-plan"
    WBS_FILE = "file-wbs"
    ZIP_FILE = "file-zip"

    def save(self, body):
        return self.client.put(
            "/api/team/documents/",
            body,
            content_type="application/json",
            headers=auth_header(),
        )

    def test_requires_login(self, *_mocks):
        self.assertEqual(self.client.get("/api/team/documents/").status_code, 401)
        self.assertEqual(
            self.client.put(
                "/api/team/documents/",
                {"folder_roles": {}},
                content_type="application/json",
            ).status_code,
            401,
        )

    def test_folder_role_is_inherited_by_its_files(self, list_folders, list_files, save):
        list_folders.return_value = [folder_row(external="folder-산출물")]
        list_files.return_value = [
            drive_file(self.PLAN_FILE, "기획서.docx"),
            drive_file(self.WBS_FILE, "WBS.xlsx"),
        ]
        save.return_value = [doc_row()]

        response = self.save({"folder_roles": {"folder-산출물": "PLAN"}})

        self.assertEqual(response.status_code, 200)
        saved = {doc["src_file_id"]: doc["doc_role"] for doc in save.call_args.kwargs["documents"]}
        self.assertEqual(saved, {self.PLAN_FILE: "PLAN", self.WBS_FILE: "PLAN"})

    def test_file_role_overrides_the_folder_role(self, list_folders, list_files, save):
        list_folders.return_value = [folder_row(external="folder-산출물")]
        list_files.return_value = [
            drive_file(self.PLAN_FILE, "기획서.docx"),
            drive_file(self.WBS_FILE, "WBS.xlsx"),
        ]
        save.return_value = [doc_row()]

        self.save(
            {
                "folder_roles": {"folder-산출물": "PLAN"},
                "file_roles": {self.WBS_FILE: "DAILY_REPORT"},
            }
        )

        saved = {doc["src_file_id"]: doc["doc_role"] for doc in save.call_args.kwargs["documents"]}
        self.assertEqual(saved, {self.PLAN_FILE: "PLAN", self.WBS_FILE: "DAILY_REPORT"})

    def test_unsupported_files_are_not_registered(self, list_folders, list_files, save):
        list_folders.return_value = [folder_row(external="folder-SKN29")]
        list_files.return_value = [
            drive_file(self.PLAN_FILE, "기획서.docx"),
            drive_file(self.ZIP_FILE, "Apart Deal.zip", supported=False, mime="application/x-zip-compressed"),
        ]
        save.return_value = []

        self.save({"folder_roles": {"folder-SKN29": "OTHER"}})

        # 파싱할 수 없는 형식을 doc에 넣으면 이후 파이프라인이 헛돈다.
        self.assertEqual(
            [doc["src_file_id"] for doc in save.call_args.kwargs["documents"]],
            [self.PLAN_FILE],
        )

    def test_folder_without_a_role_registers_nothing(self, list_folders, list_files, save):
        list_folders.return_value = [folder_row(external="folder-SKN29")]
        list_files.return_value = [drive_file(self.PLAN_FILE, "기획서.docx")]
        save.return_value = []

        self.save({"folder_roles": {}})

        self.assertEqual(save.call_args.kwargs["documents"], [])

    def test_saved_scan_depth_is_used_for_the_file_scan(self, list_folders, list_files, save):
        list_folders.return_value = [folder_row(external="folder-산출물", max_depth=None)]
        list_files.return_value = [drive_file(self.PLAN_FILE, "기획서.docx")]
        save.return_value = []

        self.save({"folder_roles": {"folder-산출물": "PLAN"}})

        # 화면이 다시 보내지 않는다 — 폴더를 저장할 때 정한 값을 쓴다.
        self.assertIsNone(list_files.call_args.kwargs["max_depth"])

    def test_unknown_role_code_is_rejected(self, list_folders, _list_files, save):
        response = self.save({"folder_roles": {"folder-산출물": "기획서"}})

        self.assertEqual(response.status_code, 400)
        list_folders.assert_not_called()
        save.assert_not_called()

    def test_drive_failure_reports_bad_gateway(self, list_folders, list_files, save):
        from apps.connectors.oauth import OAuthError

        list_folders.return_value = [folder_row(external="folder-산출물")]
        list_files.side_effect = OAuthError("Google Drive 연결이 만료됐습니다. 다시 연결해 주세요.")

        response = self.save({"folder_roles": {"folder-산출물": "PLAN"}})

        self.assertEqual(response.status_code, 502)
        save.assert_not_called()

    @patch("apps.projects.api_views.DocumentRepository.list_for_team")
    def test_lists_registered_documents(self, list_for_team, *_mocks):
        list_for_team.return_value = [doc_row()]

        response = self.client.get("/api/team/documents/", headers=auth_header())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["doc_role"], "PLAN")
        # 등록만 된 문서는 아직 프로젝트가 없다.
        self.assertIsNone(response.json()[0]["proj_id"])
        list_for_team.assert_called_once_with("UA001")
