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
        # provider 를 함께 고정한다. 이 값이 s3 인 환경에서 돌면 로컬 백엔드가
        # 아니라 S3 를 재게 된다(2026-08-18 에 이 값이 처음 의미를 갖게 됐다).
        patcher = patch.dict(
            "os.environ",
            {"DOCUMENT_STORAGE_ROOT": self._directory.name, "OBJECT_STORAGE_PROVIDER": "local"},
        )
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


class S3StorageTests(SimpleTestCase):
    """S3 백엔드 — **네트워크에 안 나간다.** boto3 클라이언트를 목으로 막는다.

    여기서 재는 것은 **두 백엔드가 같은 계약을 지키는가**다. 키 모양·해시·
    없는 것과 못 읽는 것의 구분이 갈리면, 갈아타는 날 조용히 다르게 돈다.
    """

    def setUp(self):
        patcher = patch.dict(
            "os.environ",
            {
                "OBJECT_STORAGE_PROVIDER": "s3",
                "AWS_STORAGE_BUCKET_NAME": "bucket-x",
                "AWS_S3_REGION_NAME": "ap-northeast-2",
            },
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _client(self):
        client = Mock()
        return patch("backend.services.storage._client", return_value=client), client

    def test_save_puts_the_object_and_returns_same_hash_as_local(self):
        """해시가 백엔드마다 다르면 변경 감지가 갈아타는 순간 전부 「바뀜」이 된다."""

        patcher, client = self._client()
        with patcher:
            digest = storage.save("TE001/DC001.md", b"hello")

        client.put_object.assert_called_once_with(
            Bucket="bucket-x", Key="TE001/DC001.md", Body=b"hello"
        )
        self.assertEqual(
            digest, "sha256:2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
        )

    def test_load_reads_the_body(self):
        patcher, client = self._client()
        client.get_object.return_value = {"Body": Mock(read=Mock(return_value=b"data"))}
        with patcher:
            self.assertEqual(storage.load("TE001/DC001.md"), b"data")

    def test_missing_object_is_false(self):
        from botocore.exceptions import ClientError

        patcher, client = self._client()
        client.head_object.side_effect = ClientError({"Error": {"Code": "404"}}, "HeadObject")
        with patcher:
            self.assertFalse(storage.exists("TE001/DC001.md"))

    def test_permission_error_is_not_reported_as_missing(self):
        """`False` 로 뭉개면 화면이 「원문 파일이 없습니다」라고 말하고,
        설정이 틀렸다는 사실을 아무도 못 본다."""

        from botocore.exceptions import ClientError

        patcher, client = self._client()
        client.head_object.side_effect = ClientError({"Error": {"Code": "403"}}, "HeadObject")
        with patcher, self.assertRaises(ClientError):
            storage.exists("TE001/DC001.md")

    def test_key_escaping_storage_is_rejected(self):
        """경로 해석이 없다고 검사를 건너뛰면 `a/../b` 가 그대로 객체 이름이 되어
        로컬에서는 하나였던 파일이 두 이름으로 생긴다."""

        patcher, client = self._client()
        with patcher:
            for key in ("../escaped.md", "/absolute.md", "TE001/../../out.md"):
                with self.subTest(key=key):
                    with self.assertRaises(ValueError):
                        storage.save(key, b"nope")
        client.put_object.assert_not_called()

    def test_missing_bucket_name_is_loud(self):
        """조용히 로컬로 떨어지면 저장은 됐는데 아무도 못 찾는 상태가 된다."""

        with patch.dict("os.environ", {"AWS_STORAGE_BUCKET_NAME": ""}):
            with self.assertRaises(RuntimeError):
                storage.save("TE001/DC001.md", b"x")


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

        # DB에 닿는 경로를 전부 막는다. `DATABASES = {}`라 Django가 테스트 DB를
        # 만들어 주지 않으므로, 안 막으면 **개발 DB에 그대로 쓴다** — 실제로
        # 실행할 때마다 audit_log 에 3행씩 쌓여 문서 등록 화면의 처리 이력이
        # 테스트 찌꺼기로 뒤덮였다(51행).
        self.audit = self._patch("apps.projects.api_views.log_audit")
        self._patch("apps.projects.api_views.AccountRepository.team_id", return_value="TE001")

        self.token = issue_token("UA001")

    def _patch(self, target, **kwargs):
        patcher = patch(target, **kwargs)
        mock = patcher.start()
        self.addCleanup(patcher.stop)
        return mock

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
        # 받은 것과 실패한 것이 있으면 이력을 남긴다.
        self.assertEqual(self.audit.call_args.kwargs["payload"]["downloaded"], 1)
        self.assertEqual(self.audit.call_args.kwargs["payload"]["failed"], 1)

    def test_nothing_downloaded_leaves_no_history(self):
        """건드린 것이 없으면 이력이 아니다 — "0건 다운로드"를 남기지 않는다."""

        with patch(
            "apps.projects.api_views.DocumentRepository.list_pending_download", return_value=[]
        ):
            response = self.client.post(
                "/api/team/documents/download/",
                HTTP_AUTHORIZATION=f"Bearer {self.token}",
            )

        self.assertEqual(response.status_code, 200)
        self.audit.assert_not_called()

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

    def test_doc_ids_limits_what_is_fetched(self):
        """고른 문서만 Drive를 때린다. 폴더 전체를 받아 오면 안 된다."""

        with patch(
            "apps.projects.api_views.DocumentRepository.list_pending_download",
            return_value=self._targets(),
        ), patch(
            "apps.projects.api_views.download_drive_file",
            return_value={"content": b"ok", "mime_type": "text/markdown", "revision": "REV"},
        ) as fetch, patch("apps.projects.api_views.DocumentRepository.mark_stored"):
            response = self.client.post(
                "/api/team/documents/download/",
                {"doc_ids": ["DC002"]},
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Bearer {self.token}",
            )

        self.assertEqual([d["file_name"] for d in response.json()["downloaded"]], ["회의록.md"])
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(fetch.call_args.kwargs["file_id"], "F2")

    def test_requires_authentication(self):
        response = self.client.post("/api/team/documents/download/")
        self.assertEqual(response.status_code, 401)
