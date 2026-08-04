"""신규 파일 감지와 선택 등록.

`DATABASES = {}`라 테스트 DB가 없어 리포지토리는 모킹한다. 여기서 검증하는 것은
**DB에 닿기 전에 결정되는 계약**이다: 이미 아는 파일을 신규로 다시 올리지 않는가,
등록이 기존 문서를 지우지 않는가, 화면이 보낸 이름을 그대로 믿지 않는가,
미지원 형식을 걸러내는가, 무엇을 했는지 기록에 남기는가.
"""

import pathlib
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.accounts.tokens import issue_token
from apps.connectors.oauth import OAuthError


def auth_header():
    return {"HTTP_AUTHORIZATION": f"Bearer {issue_token('UA001')}"}


def folder_source(external="folder-01", name="01_기획"):
    return {
        "team_folder_id": "TF001",
        "team_id": "TE001",
        "conn_id": "CN002",
        "external_folder_id": external,
        "display_name": name,
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
                "apps.projects.api_views.TeamFolderRepository.list_for_team",
                return_value=sources,
            ),
            patch(
                "apps.projects.api_views.DocumentRepository.registered_file_ids",
                return_value=known,
            ),
            patch("apps.projects.api_views.list_drive_files", return_value=files),
            # 스캔은 조회만 한다. 되살리기·누락 조회는 별도로 확인한다.
            patch(
                "apps.projects.api_views.DocumentRepository.restore_reappeared",
                return_value=[],
            ),
            patch(
                "apps.projects.api_views.DocumentRepository.list_missing_from_drive",
                return_value=[],
            ),
        )

    def test_already_registered_files_are_not_new(self):
        sources, known, drive, restore, missing = self._patches(
            sources=[folder_source()],
            files=[drive_file("F-old"), drive_file("F-new")],
            known={"F-old"},
        )
        with sources, known, drive, restore, missing:
            response = self.client.get("/api/team/documents/new/", **auth_header())

        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["file_id"] for row in response.json()["candidates"]], ["F-new"])

    def test_removed_documents_do_not_resurface(self):
        """폴더에서 내린 문서가 스캔할 때마다 신규로 다시 올라오면 안 된다."""

        sources, known, drive, restore, missing = self._patches(
            sources=[folder_source()],
            files=[drive_file("F-dropped")],
            # registered_file_ids 는 deleted 여부를 가리지 않는다.
            known={"F-dropped"},
        )
        with sources, known, drive, restore, missing:
            response = self.client.get("/api/team/documents/new/", **auth_header())

        self.assertEqual(response.json()["candidates"], [])

    def test_unsupported_files_are_listed_but_flagged(self):
        """목록에서 빼면 "내 파일이 왜 없지"가 된다. 보여주되 표시한다."""

        sources, known, drive, restore, missing = self._patches(
            sources=[folder_source()],
            files=[drive_file("F-png", "도식.png", supported=False)],
            known=set(),
        )
        with sources, known, drive, restore, missing:
            rows = self.client.get("/api/team/documents/new/", **auth_header()).json()["candidates"]

        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["supported"])

    def test_saved_scan_depth_is_used_for_the_file_scan(self):
        """탐색 깊이는 폴더를 저장할 때 정한다. 화면이 다시 보내지 않는다.

        역할 지정 화면이 사라지면서 이 검증이 그 화면 테스트와 함께 없어질
        뻔했다(2026-08-04). 깊이는 여전히 살아 있는 설정이라 여기로 옮겼다.
        """

        sources, known, drive, restore, missing = self._patches(
            sources=[folder_source() | {"max_depth": None}],
            files=[drive_file()],
            known=set(),
        )
        with sources, known, drive as list_files, restore, missing:
            self.client.get("/api/team/documents/new/", **auth_header())

        self.assertIsNone(list_files.call_args.kwargs["max_depth"])

    def test_subfolder_path_wins_over_folder_name(self):
        sources, known, drive, restore, missing = self._patches(
            sources=[folder_source(name="01_기획")],
            files=[drive_file(path="01_기획/하위")],
            known=set(),
        )
        with sources, known, drive, restore, missing:
            rows = self.client.get("/api/team/documents/new/", **auth_header()).json()["candidates"]

        self.assertEqual(rows[0]["folder_name"], "01_기획/하위")

    def test_drive_failure_is_reported_as_bad_gateway(self):
        sources, known, _drive, restore, missing = self._patches(sources=[folder_source()], files=[], known=set())
        with sources, known, restore, missing, patch(
            "apps.projects.api_views.list_drive_files",
            side_effect=OAuthError("Google Drive 파일 목록을 가져오지 못했습니다."),
        ):
            response = self.client.get("/api/team/documents/new/", **auth_header())

        self.assertEqual(response.status_code, 502)


class DocumentRegisterTests(SimpleTestCase):
    def _post(self, body, *, files, known=frozenset(), sources=None):
        with patch(
            "apps.projects.api_views.TeamFolderRepository.list_for_team",
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
                "/api/team/documents/register/",
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

    def test_registered_document_belongs_to_no_project_yet(self):
        """등록 시점에는 이 문서가 어느 프로젝트의 무엇인지 모른다.

        `doc_role`은 기준 문서 선택 화면에서 PRIMARY/SUB 로 채워진다. 예전에는
        폴더에 준 종류를 여기서 물려받았는데, 「01_기획」에 든 것은 무엇이든
        기획서가 되어 3건 중 2건이 틀렸다.
        """

        response, add, _ = self._post(
            {"files": [{"file_id": "F-new"}]},
            files=[drive_file("F-new")],
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(add.call_args.kwargs["documents"][0]["doc_role"])

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

    def test_registering_adds_only_the_chosen_files(self):
        """고른 것만 더한다. 폴더 전체를 훑어 기존 문서를 지우지 않는다.

        전체 동기화 경로(`save_drive_documents`)는 역할 지정 화면과 함께
        없어졌다(2026-08-04). 남은 것은 이 「더하기」 하나뿐이다.
        """

        _response, add, _download = self._post(
            {"files": [{"file_id": "F-new"}]},
            files=[drive_file("F-new"), drive_file("F-other", "다른파일.docx")],
        )

        added = [doc["src_file_id"] for doc in add.call_args.kwargs["documents"]]
        self.assertEqual(added, ["F-new"])

    def test_registration_is_recorded_in_the_audit_log(self):
        """무엇이 언제 들어왔는지 남지 않아 예전에 doc 건수 변화를 추적하지 못했다."""

        _, _, audit = self._post({"files": [{"file_id": "F-new"}]}, files=[drive_file("F-new")])

        audit.assert_called_once()
        self.assertEqual(audit.call_args.kwargs["action"], "DOCUMENT_REGISTER")
        self.assertEqual(audit.call_args.kwargs["target_type"], "DOCUMENT")
        # 문서 등록은 프로젝트와 무관해졌다. 이력은 행위자의 팀으로 찾는다.
        self.assertNotIn("proj_id", audit.call_args.kwargs)
        self.assertEqual(audit.call_args.kwargs["payload"]["registered"], 1)

    def test_nothing_registered_leaves_no_history(self):
        """"파일 등록 0건"은 이력이 아니다 — 바뀐 게 없다."""

        with patch(
            "apps.projects.api_views.TeamFolderRepository.list_for_team",
            return_value=[folder_source()],
        ), patch(
            "apps.projects.api_views.DocumentRepository.registered_file_ids", return_value=set()
        ), patch(
            "apps.projects.api_views.list_drive_files",
            return_value=[drive_file("F-png", "도식.png", supported=False)],
        ), patch(
            "apps.projects.api_views.DocumentRepository.add_drive_documents", return_value=[]
        ), patch(
            "apps.projects.api_views.log_audit"
        ) as audit:
            response = self.client.post(
                "/api/team/documents/register/",
                {"files": [{"file_id": "F-png"}]},
                content_type="application/json",
                **auth_header(),
            )

        self.assertEqual(response.status_code, 200)
        audit.assert_not_called()

    def test_empty_request_is_rejected(self):
        response = self.client.post(
            "/api/team/documents/register/",
            {"files": []},
            content_type="application/json",
            **auth_header(),
        )
        self.assertEqual(response.status_code, 400)


class DocumentHistoryTests(SimpleTestCase):
    def _history(self, rows, has_more=False, query=""):
        with patch(
            "apps.projects.api_views.DocumentRepository.list_history",
            return_value=(rows, has_more),
        ) as list_history:
            response = self.client.get(
                f"/api/team/documents/history/{query}", **auth_header()
            )
        self.call = list_history.call_args
        return response

    def _row(self, action="DOCUMENT_REGISTER", payload=None):
        from datetime import UTC, datetime

        return {
            "audit_id": "AL020",
            "action": action,
            "payload": payload if payload is not None else {"registered": 3, "skipped": 0},
            "occurred_at": datetime(2026, 8, 3, 5, 0, tzinfo=UTC),
            "actor_display_name": "임준",
        }

    def test_clean_run_is_ok(self):
        body = self._history([self._row()]).json()
        self.assertEqual(body["entries"][0]["status"], "OK")
        self.assertEqual(body["entries"][0]["actor_display_name"], "임준")

    def test_real_failure_is_flagged(self):
        """실패가 섞였는데 '완료'로만 보이면 몇 건이 빠졌는지 알 수 없다."""

        body = self._history(
            [self._row(action="DOCUMENT_DOWNLOAD", payload={"downloaded": 7, "failed": 2})]
        ).json()
        self.assertEqual(body["entries"][0]["status"], "PARTIAL")

    def test_skipped_is_not_a_failure(self):
        """미지원이라 걸러진 것은 하려다 안 된 것이 아니다. 건수는 payload에 남는다."""

        body = self._history([self._row(payload={"registered": 3, "skipped": 2})]).json()
        self.assertEqual(body["entries"][0]["status"], "OK")
        self.assertEqual(body["entries"][0]["payload"]["skipped"], 2)

    def test_more_pages_are_announced(self):
        """「더 보기」를 보일지는 화면이 정하지만, 남았다는 사실은 서버가 안다."""

        self.assertTrue(self._history([self._row()], has_more=True).json()["has_more"])
        self.assertFalse(self._history([self._row()]).json()["has_more"])

    def test_offset_is_passed_through(self):
        self._history([], query="?offset=20")
        self.assertEqual(self.call.kwargs["offset"], 20)
        self.assertEqual(self.call.kwargs["limit"], 20)

    def test_broken_offset_falls_back_to_the_first_page(self):
        """주소창을 손댄 값 때문에 이력이 통째로 안 보이면 안 된다."""

        self._history([], query="?offset=abc")
        self.assertEqual(self.call.kwargs["offset"], 0)

        self._history([], query="?offset=-5")
        self.assertEqual(self.call.kwargs["offset"], 0)


class MissingFromDriveTests(SimpleTestCase):
    """Drive 에서 사라진 문서.

    2026-08-04 이전에는 이 경로가 아예 없었다. `deleted = true` 로 내리는 코드는
    역할 지정 저장 화면에만 있었고, 그 화면이 사라지면서 함께 없어졌다.
    """

    def _get(self, *, files, missing):
        with patch(
            "apps.projects.api_views.TeamFolderRepository.list_for_team",
            return_value=[folder_source()],
        ), patch(
            "apps.projects.api_views.DocumentRepository.registered_file_ids",
            return_value=set(),
        ), patch(
            "apps.projects.api_views.list_drive_files", return_value=files
        ), patch(
            "apps.projects.api_views.DocumentRepository.restore_reappeared", return_value=[]
        ) as restore, patch(
            "apps.projects.api_views.DocumentRepository.list_missing_from_drive",
            return_value=missing,
        ) as lookup:
            response = self.client.get("/api/team/documents/new/", **auth_header())
        return response, restore, lookup

    def test_scan_reports_documents_no_longer_in_drive(self):
        response, _restore, lookup = self._get(
            files=[drive_file("F-live")],
            missing=[
                {
                    "doc_id": "DC019",
                    "file_name": "기획서.docx",
                    "mime_type": "application/pdf",
                    "proj_id": "PJ001",
                    "project_name": "SKN29",
                    "doc_role": "PRIMARY",
                }
            ],
        )

        self.assertEqual(response.status_code, 200)
        missing = response.json()["missing"]
        self.assertEqual(missing[0]["doc_id"], "DC019")
        # 어느 프로젝트의 기준 문서였는지 알려야 한다. 그게 사라졌다는 것은 그
        # 프로젝트의 업무 추출 근거가 없어졌다는 뜻이다.
        self.assertEqual(missing[0]["doc_role"], "PRIMARY")
        self.assertEqual(missing[0]["project_name"], "SKN29")

    def test_scan_passes_every_scanned_file_id(self):
        """이미 등록된 파일도 「살아 있는 id」에 들어가야 한다.

        신규 후보만 넘기면 등록된 문서가 전부 사라진 것으로 잡힌다.
        """

        _response, _restore, lookup = self._get(
            files=[drive_file("F-live"), drive_file("F-known")], missing=[]
        )

        self.assertEqual(lookup.call_args.kwargs["live_file_ids"], {"F-live", "F-known"})

    def test_scan_does_not_delete_anything(self):
        """조회가 데이터를 바꾸면 안 된다.

        휴지통·완전삭제·폴더 밖 이동이 전부 똑같이 「안 잡힘」으로 보여서, 자동으로
        내리면 잠깐 옮겨 둔 문서가 조용히 사라진다.
        """

        with patch(
            "apps.projects.api_views.DocumentRepository.mark_removed_from_drive"
        ) as remove:
            self._get(files=[], missing=[])

        remove.assert_not_called()

    def test_removal_is_explicit_and_audited(self):
        with patch(
            "apps.projects.api_views.DocumentRepository.mark_removed_from_drive",
            return_value={"removed": 2, "blocks": 30, "chunks": 12, "vectors": 12},
        ) as remove, patch("apps.projects.api_views.log_audit") as audit:
            response = self.client.post(
                "/api/team/documents/remove/",
                {"doc_ids": ["DC019", "DC020"]},
                content_type="application/json",
                **auth_header(),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["removed"], 2)
        # 무엇을 얼마나 지웠는지 화면과 감사 로그 양쪽에 남는다.
        self.assertEqual(response.json()["chunks"], 12)
        self.assertEqual(remove.call_args.kwargs["doc_ids"], ["DC019", "DC020"])
        self.assertEqual(audit.call_args.kwargs["action"], "DOCUMENT_REMOVE")
        self.assertEqual(audit.call_args.kwargs["payload"]["vectors"], 12)
        # 인자명을 틀리면 TypeError 가 나는데, 삭제는 이미 커밋된 뒤라 화면에는
        # 「실패」가 뜨고 데이터는 지워진 채로 남는다(2026-08-04 실측).
        self.assertEqual(audit.call_args.kwargs["actor_account_id"], "UA001")

    def test_removal_requires_login(self):
        response = self.client.post(
            "/api/team/documents/remove/",
            {"doc_ids": ["DC019"]},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)


class AuditSignatureTests(SimpleTestCase):
    """감사 로그 호출이 실제 시그니처와 맞는가.

    `log_audit`을 모킹하면 인자명이 틀려도 통과한다. 실제로 2026-08-04에
    `account_id=`로 넘겨 `TypeError`가 났는데, 그때는 이미 삭제가 커밋된 뒤라
    화면에는 실패가 뜨고 데이터는 지워진 상태로 남았다.
    """

    def test_every_call_site_matches_log_audit(self):
        import inspect

        from backend.db.audit import log_with

        allowed = set(inspect.signature(log_with).parameters) - {"cursor"}

        import re

        source = pathlib.Path("apps/projects/api_views.py").read_text(encoding="utf-8")
        used: set[str] = set()
        for block in re.findall(r"log_audit\(\s*(.*?)\n\s*\)", source, re.S):
            used |= set(re.findall(r"^\s*(\w+)=", block, re.M))

        self.assertTrue(used, "log_audit 호출을 찾지 못했다")
        self.assertEqual(used - allowed, set(), f"log_audit 이 받지 않는 인자: {used - allowed}")
