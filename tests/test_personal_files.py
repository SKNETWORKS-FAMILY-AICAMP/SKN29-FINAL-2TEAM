"""「내 파일」 — 개인 소유 문서 (M④).

`DATABASES = {}` 라 테스트 DB 가 없어 리포지토리는 모킹한다. 여기서 재는 것은
**DB 에 닿기 전에 결정되는 계약**이다: 무엇을 받고 무엇을 거절하는가, 형식을
누가 판정하는가, 순서가 맞는가, 그리고 **내 것이 아닌 것에 손대지 못하는가.**
"""

from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from apps.accounts.tokens import issue_token
from backend.services import storage


def auth_header(account_id="UA001"):
    return {"authorization": f"Bearer {issue_token(account_id)}"}


class UploadTypeTests(SimpleTestCase):
    """**아바타만큼 강하지 않다는 것을 고정한다.** 문서는 바이트만으로 형식이
    안 갈린다 — 그 한계를 테스트가 알고 있어야 다음 사람이 더 믿지 않는다."""

    def test_pdf_is_checked_by_signature(self):
        self.assertEqual(storage.upload_mime_type("a.pdf", b"%PDF-1.4 ..."), "application/pdf")

    def test_pdf_extension_with_wrong_bytes_is_rejected(self):
        """확장자만 바꿔 올리는 것을 시그니처가 잡는다."""

        self.assertIsNone(storage.upload_mime_type("a.pdf", b"MZ\x90\x00 exe"))

    def test_office_formats_only_get_a_zip_check(self):
        """docx·pptx·xlsx 는 셋 다 zip 이라 **서로 구분되지 않는다.**
        여기서 재는 것은 「zip 인가」까지다."""

        docx = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        self.assertEqual(storage.upload_mime_type("a.docx", b"PK\x03\x04rest"), docx)
        self.assertIsNone(storage.upload_mime_type("a.docx", b"not a zip"))

    def test_text_has_no_signature_to_check(self):
        self.assertEqual(storage.upload_mime_type("a.md", "# 아무 내용".encode("utf-8")), "text/markdown")

    def test_unknown_extension_is_rejected(self):
        for name in ("a.hwp", "a.exe", "a.zip", "noextension"):
            with self.subTest(name=name):
                self.assertIsNone(storage.upload_mime_type(name, b"%PDF-"))

    def test_extension_case_does_not_matter(self):
        self.assertEqual(storage.upload_mime_type("A.PDF", b"%PDF-"), "application/pdf")


class PersonalKeyTests(SimpleTestCase):
    def test_key_is_under_its_own_prefix(self):
        """팀 아래에 두면 팀을 지울 때 내 파일이 함께 지워진다."""

        key = storage.build_personal_key(
            account_id="UA001", doc_id="DC009", mime_type="application/pdf"
        )
        self.assertEqual(key, "user/UA001/DC009.pdf")

    def test_file_name_is_not_in_the_key(self):
        """올린 파일명에 `/` 나 `..` 이 들어 있어도 키는 우리가 만든 값뿐이다."""

        key = storage.build_personal_key(
            account_id="UA001", doc_id="DC009", mime_type="text/markdown"
        )
        self.assertNotIn("..", key)
        self.assertTrue(key.startswith("user/UA001/"))


@patch("apps.personal_files.api_views._start_processing")
@patch("apps.personal_files.api_views.storage")
@patch("apps.personal_files.api_views.DocumentRepository")
@patch("apps.personal_files.api_views.PersonalDocumentRepository")
class UploadApiTests(SimpleTestCase):
    URL = "/api/me/files/"

    def _upload(self, name="계약서.pdf", content=b"%PDF-1.4 body"):
        return self.client.post(
            self.URL,
            {"file": SimpleUploadedFile(name, content)},
            headers=auth_header(),
        )

    def test_saves_the_file_before_recording_it(self, repo, doc_repo, store, _process):
        """반대 순서면 「DB 에는 있는데 파일이 없는」 상태가 생기고 파싱이 죽는다."""

        repo.create.return_value = "DC009"
        store.upload_mime_type.return_value = "application/pdf"
        store.build_personal_key.return_value = "user/UA001/DC009.pdf"
        store.save.return_value = "sha256:" + "a" * 64

        response = self._upload()

        self.assertEqual(response.status_code, 201)
        store.save.assert_called_once()
        self.assertEqual(doc_repo.mark_stored.call_args.kwargs["storage_key"], "user/UA001/DC009.pdf")
        # 올린 파일에는 원천 리비전이 없다 — 내용 해시가 그 자리를 대신한다.
        self.assertEqual(doc_repo.mark_stored.call_args.kwargs["revision"], "a" * 16)

    def test_owner_is_the_logged_in_account(self, repo, _doc_repo, store, _process):
        repo.create.return_value = "DC009"
        store.upload_mime_type.return_value = "application/pdf"
        store.save.return_value = "sha256:" + "a" * 64

        self._upload()

        self.assertEqual(repo.create.call_args.kwargs["account_id"], "UA001")

    def test_rejects_a_format_we_cannot_read(self, repo, _doc_repo, store, _process):
        """올린 뒤에 「못 읽습니다」로 끝나면 사람은 기다린 만큼 손해다."""

        store.upload_mime_type.return_value = None

        response = self._upload(name="문서.hwp", content=b"anything")

        self.assertEqual(response.status_code, 400)
        repo.create.assert_not_called()
        store.save.assert_not_called()

    def test_rejects_a_file_that_is_too_large(self, repo, _doc_repo, store, _process):
        from apps.personal_files.api_views import MAX_UPLOAD_BYTES

        big = SimpleUploadedFile("큰.pdf", b"x" * (MAX_UPLOAD_BYTES + 1))
        response = self.client.post(self.URL, {"file": big}, headers=auth_header())

        self.assertEqual(response.status_code, 400)
        repo.create.assert_not_called()
        # 크기를 형식보다 먼저 본다 — 큰 파일을 다 읽고 나서 거절할 이유가 없다.
        store.upload_mime_type.assert_not_called()

    def test_missing_file_is_a_clear_message(self, _repo, _doc_repo, _store, _process):
        response = self.client.post(self.URL, {}, headers=auth_header())
        self.assertEqual(response.status_code, 400)

    def test_login_is_required(self, repo, _doc_repo, _store, _process):
        response = self.client.post(self.URL, {"file": SimpleUploadedFile("a.pdf", b"%PDF-")})
        self.assertEqual(response.status_code, 401)
        repo.create.assert_not_called()


@patch("apps.personal_files.api_views.storage")
@patch("apps.personal_files.api_views.PersonalDocumentRepository")
class ToggleAndDeleteTests(SimpleTestCase):
    URL = "/api/me/files/DC009/"

    def test_toggle_passes_the_owner(self, repo, _store):
        """`doc_id` 만으로 켜고 끄면 남의 파일도 켜진다."""

        response = self.client.patch(
            self.URL, {"search_enabled": False}, content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 200)
        kwargs = repo.set_search_enabled.call_args.kwargs
        self.assertEqual(kwargs["account_id"], "UA001")
        self.assertIs(kwargs["enabled"], False)

    def test_toggle_rejects_a_non_boolean(self, repo, _store):
        response = self.client.patch(
            self.URL, {"search_enabled": "true"}, content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 400)
        repo.set_search_enabled.assert_not_called()

    def test_delete_removes_the_original_too(self, repo, store):
        """원본이 우리뿐이라 남겨 둘 이유가 없다 — 커넥터 문서와 다른 점이다."""

        repo.delete.return_value = "user/UA001/DC009.pdf"

        response = self.client.delete(self.URL, headers=auth_header())

        self.assertEqual(response.status_code, 204)
        self.assertEqual(repo.delete.call_args.kwargs["account_id"], "UA001")
        store.remove.assert_called_once_with("user/UA001/DC009.pdf")

    def test_delete_survives_a_missing_original(self, repo, store):
        """행은 이미 지웠다. 여기서 실패로 돌려주면 화면은 안 지워졌다고 말한다."""

        repo.delete.return_value = "user/UA001/DC009.pdf"
        store.remove.side_effect = OSError("gone")

        self.assertEqual(self.client.delete(self.URL, headers=auth_header()).status_code, 204)

    def test_login_is_required(self, repo, _store):
        self.assertEqual(self.client.delete(self.URL).status_code, 401)
        repo.delete.assert_not_called()


@patch("apps.personal_files.api_views.PersonalDocumentRepository")
class ListTests(SimpleTestCase):
    def test_list_is_scoped_to_me(self, repo):
        repo.list_for_account.return_value = []

        response = self.client.get("/api/me/files/", headers=auth_header())

        self.assertEqual(response.status_code, 200)
        repo.list_for_account.assert_called_once_with("UA001")

    def test_states_are_not_collapsed(self, repo):
        """「요약 없음」·「추출 실패」·「색인됨」은 사람이 할 행동이 각각 다르다."""

        repo.list_for_account.return_value = [
            {
                "doc_id": "DC009", "file_name": "계약서.pdf", "mime_type": "application/pdf",
                "search_enabled": True, "search_ready": False, "summary": None,
                "doc_type": None, "keywords": None, "extract_status": "FAILED",
                "src_modified_at": None,
            }
        ]

        body = self.client.get("/api/me/files/", headers=auth_header()).json()[0]

        self.assertFalse(body["search_ready"])
        self.assertEqual(body["extract_status"], "FAILED")
        self.assertTrue(body["search_enabled"])
