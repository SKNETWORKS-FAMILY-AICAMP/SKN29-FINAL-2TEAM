"""신규 파일 감지와 선택 등록.

`DATABASES = {}`라 테스트 DB가 없어 리포지토리는 모킹한다. 여기서 검증하는 것은
**DB에 닿기 전에 결정되는 계약**이다: 이미 아는 파일을 신규로 다시 올리지 않는가,
등록이 기존 문서를 지우지 않는가, 화면이 보낸 이름을 그대로 믿지 않는가,
미지원 형식을 걸러내는가, 무엇을 했는지 기록에 남기는가.
"""

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.accounts.tokens import issue_token
from apps.connectors.oauth import OAuthError


def auth_header():
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_token('UA001')}"}


def folder_source(external="folder-01", role="PLAN", name="01_기획"):
    return {
        "proj_source_id": "PS005",
        "proj_id": "PJ001",
        "conn_id": "CN002",
        "source_type": "DRIVE_FOLDER",
        "external_source_id": external,
        "display_name": name,
        "sync_status": "PENDING",
        "default_doc_role": role,
        "max_depth": 1,
    }


def drive_file(file_id="F-new", name="새 기획서.docx", supported=True, path=""):
    return {
        "file_id": file_id,
        "name": name,
        "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "modified_at": "2026-08-03T01:00:00.000Z",
        "supported": supported,
        "folder_path": path,
    }


def created_doc(doc_id="DC030", name="새 기획서.docx", role="PLAN"):
    return {
        "doc_id": doc_id,
        "proj_id": "PJ001",
        "src_file_id": "F-new",
        "source_type": "DRIVE",
        "file_name": name,
        "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "doc_role": role,
        "src_modified_at": None,
        "storage_key": None,
    }


class NewDocumentScanTests(SimpleTestCase):
    def _patches(self, *, sources, files, known):
        return (
            patch(
                "apps.projects.api_views.ProjectSourceRepository.list_for_project",
                return_value=sources,
            ),
            patch(
                "apps.projects.api_views.DocumentRepository.registered_file_ids",
                return_value=known,
            ),
            patch("apps.projects.api_views.list_drive_files", return_value=files),
        )

    def test_already_registered_files_are_not_new(self):
        sources, known, drive = self._patches(
            sources=[folder_source()],
            files=[drive_file("F-old"), drive_file("F-new")],
            known={"F-old"},
        )
        with sources, known, drive:
            response = self.client.get("/api/projects/PJ001/documents/new/", **auth_header())

        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["file_id"] for row in response.json()], ["F-new"])

    def test_removed_documents_do_not_resurface(self):
        """폴더에서 내린 문서가 스캔할 때마다 신규로 다시 올라오면 안 된다."""

        sources, known, drive = self._patches(
            sources=[folder_source()],
            files=[drive_file("F-dropped")],
            # registered_file_ids 는 deleted 여부를 가리지 않는다.
            known={"F-dropped"},
        )
        with sources, known, drive:
            response = self.client.get("/api/projects/PJ001/documents/new/", **auth_header())

        self.assertEqual(response.json(), [])

    def test_unsupported_files_are_listed_but_flagged(self):
        """목록에서 빼면 "내 파일이 왜 없지"가 된다. 보여주되 표시한다."""

        sources, known, drive = self._patches(
            sources=[folder_source()],
            files=[drive_file("F-png", "도식.png", supported=False)],
            known=set(),
        )
        with sources, known, drive:
            rows = self.client.get("/api/projects/PJ001/documents/new/", **auth_header()).json()

        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["supported"])

    def test_folder_role_is_suggested(self):
        sources, known, drive = self._patches(
            sources=[folder_source(role="MEETING_NOTE", name="02_회의록")],
            files=[drive_file()],
            known=set(),
        )
        with sources, known, drive:
            rows = self.client.get("/api/projects/PJ001/documents/new/", **auth_header()).json()

        self.assertEqual(rows[0]["suggested_role"], "MEETING_NOTE")
        self.assertEqual(rows[0]["folder_name"], "02_회의록")

    def test_subfolder_path_wins_over_folder_name(self):
        sources, known, drive = self._patches(
            sources=[folder_source(name="01_기획")],
            files=[drive_file(path="01_기획/하위")],
            known=set(),
        )
        with sources, known, drive:
            rows = self.client.get("/api/projects/PJ001/documents/new/", **auth_header()).json()

        self.assertEqual(rows[0]["folder_name"], "01_기획/하위")

    def test_drive_failure_is_reported_as_bad_gateway(self):
        sources, known, _ = self._patches(sources=[folder_source()], files=[], known=set())
        with sources, known, patch(
            "apps.projects.api_views.list_drive_files",
            side_effect=OAuthError("Google Drive 파일 목록을 가져오지 못했습니다."),
        ):
            response = self.client.get("/api/projects/PJ001/documents/new/", **auth_header())

        self.assertEqual(response.status_code, 502)


class DocumentRegisterTests(SimpleTestCase):
    def _post(self, body, *, files, known=frozenset(), sources=None):
        with patch(
            "apps.projects.api_views.ProjectSourceRepository.list_for_project",
            return_value=sources if sources is not None else [folder_source()],
        ), patch(
            "apps.projects.api_views.DocumentRepository.registered_file_ids",
            return_value=set(known),
        ), patch(
            "apps.projects.api_views.list_drive_files", return_value=files
        ), patch(
            "apps.projects.api_views.DocumentRepository.add_drive_documents",
            return_value=[created_doc()],
        ) as add, patch(
            "apps.projects.api_views.log_audit"
        ) as audit:
            response = self.client.post(
                "/api/projects/PJ001/documents/register/",
                body,
                content_type="application/json",
                **auth_header(),
            )
        return response, add, audit

    def test_registers_only_requested_files(self):
        response, add, _ = self._post(
            {"files": [{"file_id": "F-new"}]},
            files=[drive_file("F-new"), drive_file("F-other", "다른 문서.docx")],
        )

        self.assertEqual(response.status_code, 200)
        sent = add.call_args.kwargs["documents"]
        self.assertEqual([row["src_file_id"] for row in sent], ["F-new"])

    def test_file_name_comes_from_drive_not_the_client(self):
        """화면이 보낸 이름을 믿으면 사용자가 무엇이든 등록시킬 수 있다."""

        response, add, _ = self._post(
            {"files": [{"file_id": "F-new", "file_name": "위조.docx"}]},
            files=[drive_file("F-new", "진짜 기획서.docx")],
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(add.call_args.kwargs["documents"][0]["file_name"], "진짜 기획서.docx")

    def test_role_defaults_to_folder_role(self):
        response, add, _ = self._post(
            {"files": [{"file_id": "F-new"}]},
            files=[drive_file("F-new")],
            sources=[folder_source(role="DAILY_REPORT")],
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(add.call_args.kwargs["documents"][0]["doc_role"], "DAILY_REPORT")

    def test_row_role_overrides_folder_role(self):
        response, add, _ = self._post(
            {"files": [{"file_id": "F-new", "doc_role": "OTHER"}]},
            files=[drive_file("F-new")],
            sources=[folder_source(role="PLAN")],
        )

        self.assertEqual(add.call_args.kwargs["documents"][0]["doc_role"], "OTHER")

    def test_unsupported_file_is_skipped_not_registered(self):
        response, add, _ = self._post(
            {"files": [{"file_id": "F-png"}]},
            files=[drive_file("F-png", "도식.png", supported=False)],
        )

        self.assertEqual(response.json()["skipped"], [{"file_id": "F-png", "reason": "UNSUPPORTED"}])
        self.assertEqual(add.call_args.kwargs["documents"], [])

    def test_file_registered_since_the_scan_is_skipped(self):
        response, add, _ = self._post(
            {"files": [{"file_id": "F-gone"}]},
            files=[drive_file("F-new")],
        )

        self.assertEqual(response.json()["skipped"], [{"file_id": "F-gone", "reason": "NOT_FOUND"}])

    def test_registering_leaves_existing_documents_alone(self):
        """`PUT /documents/`와 달리 아무것도 지우지 않는다 — 그게 이 경로가 따로 있는 이유다."""

        with patch(
            "apps.projects.api_views.DocumentRepository.save_drive_documents"
        ) as full_sync:
            self._post({"files": [{"file_id": "F-new"}]}, files=[drive_file("F-new")])

        full_sync.assert_not_called()

    def test_registration_is_recorded_in_the_audit_log(self):
        """무엇이 언제 들어왔는지 남지 않아 예전에 doc 건수 변화를 추적하지 못했다."""

        _, _, audit = self._post({"files": [{"file_id": "F-new"}]}, files=[drive_file("F-new")])

        audit.assert_called_once()
        self.assertEqual(audit.call_args.kwargs["action"], "DOCUMENT_REGISTER")
        self.assertEqual(audit.call_args.kwargs["proj_id"], "PJ001")
        self.assertEqual(audit.call_args.kwargs["payload"]["registered"], 1)

    def test_empty_request_is_rejected(self):
        response = self.client.post(
            "/api/projects/PJ001/documents/register/",
            {"files": []},
            content_type="application/json",
            **auth_header(),
        )
        self.assertEqual(response.status_code, 400)


class DocumentHistoryTests(SimpleTestCase):
    def _history(self, rows):
        with patch(
            "apps.projects.api_views.DocumentRepository.list_history", return_value=rows
        ):
            return self.client.get("/api/projects/PJ001/documents/history/", **auth_header())

    def _row(self, action="DOCUMENT_REGISTER", payload=None):
        from datetime import UTC, datetime

        return {
            "audit_id": "AL020",
            "action": action,
            "payload": payload if payload is not None else {"registered": 3, "skipped": 0},
            "occurred_at": datetime(2026, 8, 3, 5, 0, tzinfo=UTC),
            "actor_display_name": "임준",
        }

    def test_clean_run_is_complete(self):
        body = self._history([self._row()]).json()
        self.assertEqual(body[0]["status"], "완료")
        self.assertEqual(body[0]["actor_display_name"], "임준")

    def test_partial_failure_is_flagged(self):
        """실패가 섞였는데 '완료'로만 보이면 몇 건이 빠졌는지 알 수 없다."""

        body = self._history(
            [self._row(action="DOCUMENT_DOWNLOAD", payload={"downloaded": 7, "failed": 2})]
        ).json()
        self.assertEqual(body[0]["status"], "PARTIAL_RESULT")
