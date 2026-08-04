"""원문 다운로드 — 문서 저장소와 Drive 다운로드 경로.

`DATABASES = {}`라 테스트 DB가 없어 리포지토리는 모킹한다. 여기서 검증하는 것은
**DB에 닿기 전에 결정되는 계약**이다: 키를 어떻게 만드는가, 저장소 밖을 못 쓰게
막는가, Google 문서를 내보내기로 받는가, 한 건이 실패해도 나머지를 받는가.
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from apps.accounts.tokens import issue_token
from apps.connectors.oauth import OAuthError
from backend.services import storage


class DocumentStorageTests(SimpleTestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        patcher = patch.dict("os.environ", {"DOCUMENT_STORAGE_ROOT": self._directory.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._directory.cleanup)

    def test_key_uses_doc_id_not_file_name(self):
        """파일명은 키에 안 들어간다 — Drive 파일명은 우리가 통제하지 못한다."""

        key = storage.build_key(team_id="TE001", doc_id="DC001", mime_type="application/pdf")
        self.assertEqual(key, "TE001/DC001.pdf")

    def test_unknown_mime_falls_back(self):
        key = storage.build_key(team_id="TE001", doc_id="DC001", mime_type="image/heic")
        self.assertEqual(key, "TE001/DC001.bin")

    def test_save_returns_hash_and_roundtrips(self):
        key = storage.build_key(team_id="TE001", doc_id="DC001", mime_type="text/markdown")
        content_hash = storage.save(key, b"hello")
        self.assertTrue(content_hash.startswith("sha256:"))
        self.assertEqual(storage.load(key), b"hello")
        self.assertTrue(storage.exists(key))

    def test_same_content_same_hash(self):
        """변경 감지가 이 성질에 기댄다 — 안 바뀐 문서는 다시 파싱하지 않는다."""

        first = storage.save("TE001/DC001.md", b"same")
        second = storage.save("TE001/DC002.md", b"same")
        self.assertEqual(first, second)

    def test_overwrite_replaces_content(self):
        storage.save("TE001/DC001.md", b"old")
        storage.save("TE001/DC001.md", b"new")
        self.assertEqual(storage.load("TE001/DC001.md"), b"new")

    def test_no_partial_file_left_behind(self):
        storage.save("TE001/DC001.md", b"done")
        leftovers = list(Path(self._directory.name).rglob("*.part"))
        self.assertEqual(leftovers, [])

    def test_key_escaping_storage_is_rejected(self):
        """키는 우리가 만들지만, 밖을 가리키는 키가 오면 그 자체가 버그다."""

        with self.assertRaises(ValueError):
            storage.save("../escaped.md", b"nope")


class DriveDownloadTests(SimpleTestCase):
    def _credential(self):
        return patch(
            "apps.connectors.clients.credential_for",
            return_value={"access_token": "token"},
        )

    def test_binary_file_uses_alt_media(self):
        from apps.connectors import clients

        meta = Mock(status_code=200)
        meta.json.return_value = {"headRevisionId": "REV1"}
        body = Mock(status_code=200, content=b"%PDF-")

        with self._credential(), patch("apps.connectors.clients.requests.get", side_effect=[meta, body]) as get:
            result = clients.download_drive_file(
                account_id="UA001", file_id="F1", mime_type="application/pdf"
            )

        self.assertEqual(result["content"], b"%PDF-")
        self.assertEqual(result["revision"], "REV1")
        self.assertEqual(get.call_args_list[1].kwargs["params"], {"alt": "media"})

    def test_google_doc_is_exported(self):
        """Google 문서는 실체 파일이 없어 alt=media로 받으면 403이 난다."""

        from apps.connectors import clients

        meta = Mock(status_code=200)
        meta.json.return_value = {"headRevisionId": "REV2"}
        body = Mock(status_code=200, content=b"PK")

        with self._credential(), patch("apps.connectors.clients.requests.get", side_effect=[meta, body]) as get:
            result = clients.download_drive_file(
                account_id="UA001",
                file_id="F2",
                mime_type="application/vnd.google-apps.document",
            )

        self.assertTrue(get.call_args_list[1].args[0].endswith("/export"))
        self.assertEqual(
            result["mime_type"],
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    def test_network_failure_becomes_oauth_error(self):
        from apps.connectors import clients
        import requests

        with self._credential(), patch(
            "apps.connectors.clients.requests.get",
            side_effect=requests.RequestException("boom"),
        ):
            with self.assertRaises(OAuthError):
                clients.download_drive_file(
                    account_id="UA001", file_id="F3", mime_type="application/pdf"
                )


class DownloadEndpointTests(SimpleTestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        patcher = patch.dict("os.environ", {"DOCUMENT_STORAGE_ROOT": self._directory.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._directory.cleanup)
        self.token = issue_token("UA001")

    def _targets(self):
        return [
            {
                "doc_id": "DC001",
                "src_file_id": "F1",
                "file_name": "기획서.docx",
                "mime_type": "application/pdf",
                "storage_key": None,
                "cur_revision": None,
            },
            {
                "doc_id": "DC002",
                "src_file_id": "F2",
                "file_name": "회의록.md",
                "mime_type": "text/markdown",
                "storage_key": None,
                "cur_revision": None,
            },
        ]

    def test_one_failure_does_not_stop_the_rest(self):
        """Drive에서 지워진 문서 하나 때문에 전체가 멈추면 안 된다."""

        def fetch(*, account_id, file_id, mime_type):
            if file_id == "F1":
                raise OAuthError("Google Drive에서 원문을 내려받지 못했습니다.")
            return {"content": b"ok", "mime_type": mime_type, "revision": "REV"}

        with patch(
            "apps.projects.api_views.DocumentRepository.list_pending_download",
            return_value=self._targets(),
        ), patch("apps.projects.api_views.download_drive_file", side_effect=fetch), patch(
            "apps.projects.api_views.DocumentRepository.mark_stored"
        ) as mark:
            response = self.client.post(
                "/api/team/documents/download/",
                HTTP_AUTHORIZATION=f"Bearer {self.token}",
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual([d["file_name"] for d in body["downloaded"]], ["회의록.md"])
        self.assertEqual([f["file_name"] for f in body["failed"]], ["기획서.docx"])
        mark.assert_called_once()

    def test_already_downloaded_is_skipped(self):
        targets = self._targets()
        targets[0]["storage_key"] = "TE001/DC001.pdf"

        with patch(
            "apps.projects.api_views.DocumentRepository.list_pending_download", return_value=targets
        ), patch(
            "apps.projects.api_views.download_drive_file",
            return_value={"content": b"ok", "mime_type": "text/markdown", "revision": None},
        ), patch("apps.projects.api_views.DocumentRepository.mark_stored"):
            response = self.client.post(
                "/api/team/documents/download/",
                HTTP_AUTHORIZATION=f"Bearer {self.token}",
            )

        self.assertEqual(response.json()["skipped"], ["기획서.docx"])

    def test_force_redownloads(self):
        targets = self._targets()
        targets[0]["storage_key"] = "TE001/DC001.pdf"

        with patch(
            "apps.projects.api_views.DocumentRepository.list_pending_download", return_value=targets
        ), patch(
            "apps.projects.api_views.download_drive_file",
            return_value={"content": b"ok", "mime_type": "text/markdown", "revision": None},
        ), patch("apps.projects.api_views.DocumentRepository.mark_stored"):
            response = self.client.post(
                "/api/team/documents/download/",
                {"force": True},
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Bearer {self.token}",
            )

        self.assertEqual(response.json()["skipped"], [])
        self.assertEqual(len(response.json()["downloaded"]), 2)

    def test_requires_authentication(self):
        response = self.client.post("/api/team/documents/download/")
        self.assertEqual(response.status_code, 401)
