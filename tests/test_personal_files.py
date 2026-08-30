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

    def test_docx_only_gets_a_zip_check(self):
        """docx 는 zip 이라 「zip 인가」까지만 확인할 수 있다."""

        docx = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        self.assertEqual(storage.upload_mime_type("a.docx", b"PKrest"), docx)
        self.assertIsNone(storage.upload_mime_type("a.docx", b"not a zip"))

    def test_text_formats_are_accepted_for_the_summary(self):
        """**워커가 본문을 못 읽어도 요약은 우리 쪽 CPU 가 만든다**(2026-08-18 PM).

        txt·md 는 문장 근거는 못 내지만 문서 단위 검색에는 그대로 쓰인다.
        """

        self.assertEqual(storage.upload_mime_type("a.txt", b"plain"), "text/plain")
        self.assertEqual(
            storage.upload_mime_type("a.md", "# 제목".encode("utf-8")), "text/markdown"
        )

    def test_formats_we_cannot_use_at_all_are_rejected(self):
        """pptx·hwp 는 워커도 CPU 추출기도 못 읽고, 도구 입력으로도 안 쓴다.

        xlsx·csv·json·zip 은 2026-08-28 부터 "다운로드 전용"으로 받는다 —
        아래 `test_data_formats_are_accepted_as_download_only` 가 그쪽을 본다.
        """

        for name in ("a.pptx", "a.hwp", "noext"):
            with self.subTest(name=name):
                self.assertIsNone(storage.upload_mime_type(name, b"PK"))

    def test_data_formats_are_accepted_as_download_only(self):
        """xlsx·csv·json·zip 은 색인은 안 하지만 표·데이터 도구 입력·내려받기로 받는다."""

        pk = b"PK\x03\x04rest"
        text = b"a,b\n1,2\n"
        cases = [
            ("표.xlsx", pk, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            ("명단.csv", text, "text/csv"),
            ("설정.json", text, "application/json"),
            ("묶음.zip", pk, "application/zip"),
        ]
        for name, body, mime in cases:
            with self.subTest(name=name):
                self.assertEqual(storage.upload_mime_type(name, body), mime)
                self.assertTrue(storage.is_download_only_upload(mime))
        self.assertFalse(storage.is_download_only_upload("application/pdf"))

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

    def test_sharing_is_a_separate_switch(self, repo, _store):
        """「내 검색에 쓴다」와 「팀이 봐도 된다」는 다른 값이다 — 한쪽만 보내면
        다른 쪽은 안 건드려야 한다."""

        response = self.client.patch(
            self.URL, {"shared": True}, content_type="application/json", headers=auth_header(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIs(repo.set_shared.call_args.kwargs["shared"], True)
        repo.set_search_enabled.assert_not_called()

    def test_both_switches_can_move_together(self, repo, _store):
        self.client.patch(
            self.URL, {"search_enabled": False, "shared": True},
            content_type="application/json", headers=auth_header(),
        )

        self.assertIs(repo.set_search_enabled.call_args.kwargs["enabled"], False)
        self.assertIs(repo.set_shared.call_args.kwargs["shared"], True)

    def test_sharing_passes_the_owner(self, repo, _store):
        """남의 파일을 내 팀에 공유할 수 있으면 안 된다."""

        self.client.patch(
            self.URL, {"shared": True}, content_type="application/json", headers=auth_header(),
        )

        self.assertEqual(repo.set_shared.call_args.kwargs["account_id"], "UA001")

    def test_toggle_rejects_a_non_boolean(self, repo, _store):
        for body in ({"search_enabled": "true"}, {"shared": 1}, {}):
            with self.subTest(body=body):
                response = self.client.patch(
                    self.URL, body, content_type="application/json", headers=auth_header(),
                )
                self.assertEqual(response.status_code, 400)
        repo.set_search_enabled.assert_not_called()
        repo.set_shared.assert_not_called()

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
    def test_shared_list_is_its_own_endpoint(self, repo):
        """내가 올린 것은 안 나온다 — 「내 파일」에 이미 있고, 두 목록에 같은
        줄이 뜨면 어느 쪽에서 지워야 하는지 모른다."""

        repo.list_shared_with_me.return_value = []

        response = self.client.get("/api/me/files/shared/", headers=auth_header())

        self.assertEqual(response.status_code, 200)
        repo.list_shared_with_me.assert_called_once_with("UA001")
        repo.list_for_account.assert_not_called()

    def test_shared_rows_say_who_shared_them(self, repo):
        """누가 올렸는지 모르면 내용을 믿을 근거가 없다."""

        repo.list_shared_with_me.return_value = [
            {
                "doc_id": "DC010", "file_name": "표준계약서.pdf", "mime_type": "application/pdf",
                "search_enabled": True, "search_ready": True,
                "index_status": None, "index_detail": None,
                "src_modified_at": None, "shared_team_id": "TE001", "owner_name": "김준억",
            }
        ]

        body = self.client.get("/api/me/files/shared/", headers=auth_header()).json()[0]

        self.assertEqual(body["owner_name"], "김준억")
        self.assertTrue(body["shared"])

    def test_list_is_scoped_to_me(self, repo):
        repo.list_for_account.return_value = []

        response = self.client.get("/api/me/files/", headers=auth_header())

        self.assertEqual(response.status_code, 200)
        repo.list_for_account.assert_called_once_with("UA001")

    def test_index_failure_says_why(self, repo):
        """실패를 「읽는 중」으로 두면 죽은 문서가 영원히 도는 것처럼 보이고,
        사유를 안 주면 사용자가 할 수 있는 일이 없다(2026-08-24)."""

        repo.list_for_account.return_value = [
            {
                "doc_id": "DC010", "file_name": "계약서.pdf", "mime_type": "application/pdf",
                "search_enabled": True, "search_ready": False,
                "index_status": "FAILED", "index_detail": "암호가 걸린 PDF 라 열 수 없습니다.",
                "src_modified_at": None, "shared_team_id": None, "owner_name": None,
            }
        ]

        body = self.client.get("/api/me/files/", headers=auth_header()).json()[0]

        self.assertEqual(body["index_status"], "FAILED")
        self.assertEqual(body["index_detail"], "암호가 걸린 PDF 라 열 수 없습니다.")

    def test_기존_실패행의_내부_URL은_API에_노출하지_않는다(self, repo):
        repo.list_for_account.return_value = [
            {
                "doc_id": "DC010", "file_name": "계약서.pdf", "mime_type": "application/pdf",
                "search_enabled": True, "search_ready": False,
                "index_status": "FAILED",
                "index_detail": (
                    "HTTPSConnectionPool(host='internal.example', port=443): "
                    "Max retries exceeded with url: /documents/1?token=secret-value"
                ),
                "src_modified_at": None, "shared_team_id": None, "owner_name": None,
            }
        ]

        body = self.client.get("/api/me/files/", headers=auth_header()).json()[0]

        self.assertEqual(
            body["index_detail"],
            "문서 처리 서버에 연결하지 못했습니다. 잠시 후 다시 읽어 주세요.",
        )
        self.assertNotIn("internal.example", body["index_detail"])
        self.assertNotIn("secret-value", body["index_detail"])

    def test_states_are_not_collapsed(self, repo):
        """「아직 차례가 안 왔다」·「읽는 중」·「실패」·「색인됨」은 사람이 할
        행동이 각각 다르다."""

        repo.list_for_account.return_value = [
            {
                "doc_id": "DC009", "file_name": "계약서.pdf", "mime_type": "application/pdf",
                "search_enabled": True, "search_ready": False,
                "index_status": None, "index_detail": None, "src_modified_at": None,
            }
        ]

        body = self.client.get("/api/me/files/", headers=auth_header()).json()[0]

        self.assertFalse(body["search_ready"])
        self.assertIsNone(body["index_status"])
        self.assertTrue(body["search_enabled"])


@patch("apps.personal_files.api_views.storage")
@patch("apps.personal_files.api_views.PersonalDocumentRepository")
class DownloadTests(SimpleTestCase):
    """2026-08-26 에 붙인 자리. 그전에는 올린 파일조차 다시 받을 수 없었다."""

    URL = "/api/me/files/DC009/download/"

    def _row(self, **over):
        return {
            "doc_id": "DC009",
            "file_name": "업무 목록_20260826.xlsx",
            "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "storage_key": "user/UA001/DC009.xlsx",
            **over,
        }

    def test_원문을_그대로_내려준다(self, repo, store):
        repo.get_for_download.return_value = self._row()
        store.load.return_value = b"PK\x03\x04payload"

        response = self.client.get(self.URL, headers=auth_header())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"PK\x03\x04payload")
        self.assertEqual(response["Content-Type"], self._row()["mime_type"])
        store.load.assert_called_once_with("user/UA001/DC009.xlsx")

    def test_소유자를_함께_넘긴다(self, repo, store):
        """`doc_id` 만으로 받으면 남의 파일도 받아진다."""

        repo.get_for_download.return_value = self._row()
        store.load.return_value = b"x"

        self.client.get(self.URL, headers=auth_header())

        self.assertEqual(
            repo.get_for_download.call_args.kwargs,
            {"doc_id": "DC009", "account_id": "UA001"},
        )

    def test_한글_파일_이름을_인코딩해_보낸다(self, repo, store):
        """`filename=` 만 쓰면 브라우저마다 깨진다 — RFC 5987 을 함께 준다."""

        repo.get_for_download.return_value = self._row()
        store.load.return_value = b"x"

        response = self.client.get(self.URL, headers=auth_header())

        disposition = response["Content-Disposition"]
        self.assertIn("filename*=UTF-8''", disposition)
        # 헤더는 latin-1 이라 한글이 날것으로 들어가면 응답 자체가 터진다.
        self.assertNotIn("업무", disposition)
        disposition.encode("latin-1")

    def test_원문이_없으면_사유를_말한다(self, repo, store):
        repo.get_for_download.return_value = self._row()
        store.load.side_effect = OSError("gone")

        response = self.client.get(self.URL, headers=auth_header())

        self.assertEqual(response.status_code, 503)

    def test_로그인이_필요하다(self, repo, store):
        response = self.client.get(self.URL)

        self.assertEqual(response.status_code, 401)
        repo.get_for_download.assert_not_called()
