from unittest.mock import patch

from django.test import SimpleTestCase

from apps.accounts.tokens import issue_token
from backend.db.errors import PermissionDenied, RecordNotFound, ReferenceNotFound


def auth_header(account_id="UA001"):
    return {"authorization": f"Bearer {issue_token(account_id)}"}


def project_row(proj_id="PJ001", name="SKN29", status="DRAFT", owner="UA001"):
    return {
        "proj_id": proj_id,
        "name": name,
        "status": status,
        "tz": "Asia/Seoul",
        "owner_account_id": owner,
        "owner_name": "임준",
    }


def source_row(
    proj_source_id="PS001",
    source_type="DRIVE_FOLDER",
    external="folder-SKN29",
    role=None,
    max_depth=1,
):
    return {
        "proj_source_id": proj_source_id,
        "proj_id": "PJ001",
        "conn_id": "CN002",
        "source_type": source_type,
        "external_source_id": external,
        "sync_status": "PENDING",
        "default_doc_role": role,
        "max_depth": max_depth,
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
        "proj_id": "PJ001",
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

    @patch("apps.projects.api_views.ProjectRepository.list_for_owner")
    def test_lists_only_my_projects(self, list_for_owner):
        list_for_owner.return_value = [project_row()]

        response = self.client.get("/api/projects/", headers=auth_header())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["proj_id"], "PJ001")
        list_for_owner.assert_called_once_with("UA001")

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

    @patch("apps.projects.api_views.ProjectRepository.create")
    def test_onboarding_project_starts_as_draft(self, create):
        create.return_value = project_row()

        self.client.post(
            "/api/projects/",
            {"name": "SKN29"},
            content_type="application/json",
            headers=auth_header(),
        )

        # 기획서를 읽기 전에는 이름조차 임시다. ACTIVE로 만들면 안 된다.
        self.assertEqual(create.call_args.kwargs["status"], "DRAFT")


class ProjectSourceApiTests(SimpleTestCase):
    def replace_body(self, source_type="DRIVE_FOLDER", ids=("folder-SKN29",)):
        return {"source_type": source_type, "external_source_ids": list(ids)}

    def test_requires_login(self):
        self.assertEqual(self.client.get("/api/projects/PJ001/sources/").status_code, 401)
        self.assertEqual(
            self.client.put(
                "/api/projects/PJ001/sources/",
                self.replace_body(),
                content_type="application/json",
            ).status_code,
            401,
        )

    @patch("apps.projects.api_views.ProjectSourceRepository.list_for_project")
    def test_lists_the_projects_sources(self, list_for_project):
        list_for_project.return_value = [source_row()]

        response = self.client.get("/api/projects/PJ001/sources/", headers=auth_header())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["external_source_id"], "folder-SKN29")
        list_for_project.assert_called_once_with(proj_id="PJ001", account_id="UA001")

    @patch("apps.projects.api_views.ProjectSourceRepository.replace")
    def test_saves_drive_folders(self, replace):
        replace.return_value = [source_row()]

        response = self.client.put(
            "/api/projects/PJ001/sources/",
            self.replace_body(ids=("folder-SKN29", "folder-산출물")),
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            replace.call_args.kwargs,
            {
                "proj_id": "PJ001",
                "account_id": "UA001",
                "source_type": "DRIVE_FOLDER",
                "external_source_ids": ["folder-SKN29", "folder-산출물"],
                # 보내지 않으면 하위 폴더를 따라 내려가지 않는다.
                "max_depth": 1,
            },
        )

    @patch("apps.projects.api_views.ProjectSourceRepository.replace")
    def test_scan_depth_is_saved(self, replace):
        replace.return_value = [source_row(max_depth=3)]

        response = self.client.put(
            "/api/projects/PJ001/sources/",
            self.replace_body() | {"max_depth": 3},
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(replace.call_args.kwargs["max_depth"], 3)
        self.assertEqual(response.json()[0]["max_depth"], 3)

    @patch("apps.projects.api_views.ProjectSourceRepository.replace")
    def test_null_depth_means_unlimited(self, replace):
        replace.return_value = [source_row(max_depth=None)]

        response = self.client.put(
            "/api/projects/PJ001/sources/",
            self.replace_body() | {"max_depth": None},
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(replace.call_args.kwargs["max_depth"])

    @patch("apps.projects.api_views.ProjectSourceRepository.replace")
    def test_absurd_depth_is_rejected(self, replace):
        response = self.client.put(
            "/api/projects/PJ001/sources/",
            self.replace_body() | {"max_depth": 999},
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 400)
        replace.assert_not_called()

    @patch("apps.projects.api_views.ProjectSourceRepository.replace")
    def test_saves_jira_projects(self, replace):
        replace.return_value = [source_row(source_type="JIRA_PROJECT", external="KAN")]

        response = self.client.put(
            "/api/projects/PJ001/sources/",
            self.replace_body(source_type="JIRA_PROJECT", ids=("KAN",)),
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["source_type"], "JIRA_PROJECT")

    @patch("apps.projects.api_views.ProjectSourceRepository.replace")
    def test_empty_list_clears_the_selection(self, replace):
        replace.return_value = []

        response = self.client.put(
            "/api/projects/PJ001/sources/",
            self.replace_body(ids=()),
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])
        self.assertEqual(replace.call_args.kwargs["external_source_ids"], [])

    @patch("apps.projects.api_views.ProjectSourceRepository.replace")
    def test_unknown_source_type_is_rejected(self, replace):
        response = self.client.put(
            "/api/projects/PJ001/sources/",
            self.replace_body(source_type="SLACK"),
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 400)
        replace.assert_not_called()

    @patch("apps.projects.api_views.ProjectSourceRepository.replace")
    def test_other_peoples_project_is_forbidden(self, replace):
        replace.side_effect = PermissionDenied("본인이 소유한 프로젝트만 수정할 수 있습니다.")

        response = self.client.put(
            "/api/projects/PJ001/sources/",
            self.replace_body(),
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 403)

    @patch("apps.projects.api_views.ProjectSourceRepository.replace")
    def test_missing_project_is_404(self, replace):
        replace.side_effect = RecordNotFound("존재하지 않는 프로젝트입니다: PJ999")

        response = self.client.put(
            "/api/projects/PJ999/sources/",
            self.replace_body(),
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 404)

    @patch("apps.projects.api_views.ProjectSourceRepository.replace")
    def test_unconnected_connector_is_a_conflict(self, replace):
        replace.side_effect = ReferenceNotFound("GOOGLE_DRIVE 커넥터가 연결되지 않았습니다.")

        response = self.client.put(
            "/api/projects/PJ001/sources/",
            self.replace_body(),
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 409)


@patch("apps.projects.api_views.DocumentRepository.save_drive_documents")
@patch("apps.projects.api_views.list_drive_files")
@patch("apps.projects.api_views.ProjectSourceRepository.list_for_project")
class DocumentRoleSaveApiTests(SimpleTestCase):
    """역할 지정 저장. 파일 목록은 서버가 Drive에서 다시 읽는다."""

    PLAN_FILE = "file-plan"
    WBS_FILE = "file-wbs"
    ZIP_FILE = "file-zip"

    def save(self, body):
        return self.client.put(
            "/api/projects/PJ001/documents/",
            body,
            content_type="application/json",
            headers=auth_header(),
        )

    def test_requires_login(self, *_mocks):
        self.assertEqual(self.client.get("/api/projects/PJ001/documents/").status_code, 401)
        self.assertEqual(
            self.client.put(
                "/api/projects/PJ001/documents/",
                {"folder_roles": {}},
                content_type="application/json",
            ).status_code,
            401,
        )

    def test_folder_role_is_inherited_by_its_files(self, list_sources, list_files, save):
        list_sources.return_value = [source_row(external="folder-산출물")]
        list_files.return_value = [
            drive_file(self.PLAN_FILE, "기획서.docx"),
            drive_file(self.WBS_FILE, "WBS.xlsx"),
        ]
        save.return_value = [doc_row()]

        response = self.save({"folder_roles": {"folder-산출물": "PLAN"}})

        self.assertEqual(response.status_code, 200)
        saved = {doc["src_file_id"]: doc["doc_role"] for doc in save.call_args.kwargs["documents"]}
        self.assertEqual(saved, {self.PLAN_FILE: "PLAN", self.WBS_FILE: "PLAN"})

    def test_file_role_overrides_the_folder_role(self, list_sources, list_files, save):
        list_sources.return_value = [source_row(external="folder-산출물")]
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

    def test_unsupported_files_are_not_registered(self, list_sources, list_files, save):
        list_sources.return_value = [source_row(external="folder-SKN29")]
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

    def test_folder_without_a_role_registers_nothing(self, list_sources, list_files, save):
        list_sources.return_value = [source_row(external="folder-SKN29")]
        list_files.return_value = [drive_file(self.PLAN_FILE, "기획서.docx")]
        save.return_value = []

        self.save({"folder_roles": {}})

        self.assertEqual(save.call_args.kwargs["documents"], [])

    def test_jira_sources_are_skipped(self, list_sources, list_files, save):
        list_sources.return_value = [source_row(source_type="JIRA_PROJECT", external="KAN")]
        save.return_value = []

        self.save({"folder_roles": {"KAN": "PLAN"}})

        list_files.assert_not_called()

    def test_saved_scan_depth_is_used_for_the_file_scan(self, list_sources, list_files, save):
        list_sources.return_value = [source_row(external="folder-산출물", max_depth=None)]
        list_files.return_value = [drive_file(self.PLAN_FILE, "기획서.docx")]
        save.return_value = []

        self.save({"folder_roles": {"folder-산출물": "PLAN"}})

        # 화면이 다시 보내지 않는다 — 폴더를 저장할 때 정한 값을 쓴다.
        self.assertIsNone(list_files.call_args.kwargs["max_depth"])

    def test_unknown_role_code_is_rejected(self, list_sources, _list_files, save):
        response = self.save({"folder_roles": {"folder-산출물": "기획서"}})

        self.assertEqual(response.status_code, 400)
        list_sources.assert_not_called()
        save.assert_not_called()

    def test_drive_failure_reports_bad_gateway(self, list_sources, list_files, save):
        from apps.connectors.oauth import OAuthError

        list_sources.return_value = [source_row(external="folder-산출물")]
        list_files.side_effect = OAuthError("Google Drive 연결이 만료됐습니다. 다시 연결해 주세요.")

        response = self.save({"folder_roles": {"folder-산출물": "PLAN"}})

        self.assertEqual(response.status_code, 502)
        save.assert_not_called()

    @patch("apps.projects.api_views.DocumentRepository.list_for_project")
    def test_lists_registered_documents(self, list_for_project, *_mocks):
        list_for_project.return_value = [doc_row()]

        response = self.client.get("/api/projects/PJ001/documents/", headers=auth_header())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["doc_role"], "PLAN")
        list_for_project.assert_called_once_with(proj_id="PJ001", account_id="UA001")
