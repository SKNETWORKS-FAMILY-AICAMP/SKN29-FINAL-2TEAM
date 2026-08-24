"""`services/document_intake/service.py`의 배치 실패 처리 단위 테스트.

전체 파이프라인(등록·다운로드·요약·색인)을 다 재현하지 않는다. 여기서 보는
것은 **"어떤 실패가 배치를 멈추고 어떤 실패가 그 한 건으로 끝나는가"** 하나다
(2026-08-20 자격증명, 2026-08-24 전량 색인).
"""

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.connectors.oauth import OAuthError
from backend.services.storage import content_hash
from services.document_intake.service import (
    IntakeResult,
    _fetch_originals,
    _index_all,
    _refetch_changed,
)
from services.document_pipeline.errors import PipelineConfigurationError, RunPodRequestError


def _pending(doc_id, file_name):
    return {
        "doc_id": doc_id,
        "file_name": file_name,
        "storage_key": None,
        "src_file_id": f"SRC-{doc_id}",
        "mime_type": "application/pdf",
    }


@patch("services.document_intake.service.DocumentRepository")
@patch("services.document_intake.service.download_drive_file")
class FetchAndSummarizeCredentialShortCircuitTests(SimpleTestCase):
    """자격증명 문제(`OAuthError`)는 같은 계정·같은 커넥터로 도는 남은 모든
    대기 문서에 반드시 똑같이 재현된다 — 첫 건에서 막히면 나머지는 더
    시도하지 않는다. 파일 하나만의 문제(`OSError` 등)는 그 한 건으로 끝나야
    하는 기존 규칙(모듈 docstring) 그대로 유지되는지도 같이 본다.
    """

    def test_자격증명_오류면_남은_문서를_더_받으려_하지_않는다(self, download, documents):
        documents.list_pending_download.return_value = [
            _pending("D1", "a.pdf"),
            _pending("D2", "b.pdf"),
            _pending("D3", "c.pdf"),
        ]
        download.side_effect = OAuthError("Google Drive 인증이 만료되었습니다.")

        result = IntakeResult()
        _fetch_originals(account_id="UA001", team_id="TM001", result=result)

        self.assertEqual(download.call_count, 1, "첫 건에서 막히면 나머지는 더 시도하면 안 된다")
        self.assertEqual(len(result.failed), 3, "대기 중이던 3건 전부에 실패 사유가 남아야 한다")
        self.assertTrue(all(row["detail"] == "OAuthError" for row in result.failed))

    def test_파일_하나만의_문제면_나머지는_계속_시도한다(self, download, documents):
        documents.list_pending_download.return_value = [
            _pending("D1", "a.pdf"),
            _pending("D2", "b.pdf"),
        ]
        download.side_effect = OSError("disk full")

        result = IntakeResult()
        _fetch_originals(account_id="UA001", team_id="TM001", result=result)

        self.assertEqual(download.call_count, 2, "파일 개별 문제는 그 한 건의 실패로 끝나야 한다")
        self.assertEqual(len(result.failed), 2)


@patch("services.document_intake.service.promote_to_searchable")
@patch("services.document_intake.service.PipelineDocumentRepository")
class IndexAllTests(SimpleTestCase):
    """폴더를 저장하면 **그 폴더 문서 전부**가 본문 색인까지 가야 한다(2026-08-24).

    전에는 요약에서 끊고 대화 중 좁혀진 문서만 승격시켰다. 그러면 폴더에 있는데도
    문장 근거를 못 내는 문서가 계속 남는다.
    """

    def test_대기_문서를_전부_색인한다(self, repository, promote):
        repository.list_pending_index.return_value = ["DC001", "DC002", "DC003"]
        promote.side_effect = lambda **kw: {"doc_id": kw["doc_id"], "ok": True}

        result = IntakeResult()
        _index_all(account_id="UA001", team_id="TM001", result=result)

        self.assertEqual(promote.call_count, 3, "대기 중인 문서는 하나도 빠지면 안 된다")
        self.assertEqual(result.indexed, ["DC001", "DC002", "DC003"])
        self.assertEqual(result.failed, [])

    def test_한_건이_실패해도_나머지는_계속한다(self, repository, promote):
        repository.list_pending_index.return_value = ["DC001", "DC002", "DC003"]

        def _promote(*, account_id, doc_id):
            if doc_id == "DC002":
                raise RunPodRequestError("워커가 응답하지 않습니다.")
            return {"doc_id": doc_id, "ok": True}

        promote.side_effect = _promote

        result = IntakeResult()
        _index_all(account_id="UA001", team_id="TM001", result=result)

        self.assertEqual(promote.call_count, 3, "한 건의 문제로 배치가 멈추면 안 된다")
        self.assertEqual(result.indexed, ["DC001", "DC003"])
        self.assertEqual(len(result.failed), 1)
        self.assertEqual(result.failed[0]["detail"], "RunPodRequestError")

    def test_설정이_없으면_남은_문서를_더_시도하지_않는다(self, repository, promote):
        """`PipelineConfigurationError` 는 RunPod 설정 자체가 없다는 뜻이라 남은
        문서도 전부 같은 이유로 실패한다 — 자격증명 실패와 같은 규칙이다."""

        repository.list_pending_index.return_value = ["DC001", "DC002", "DC003"]
        promote.side_effect = PipelineConfigurationError("필수 RunPod 설정이 없습니다")

        result = IntakeResult()
        _index_all(account_id="UA001", team_id="TM001", result=result)

        self.assertEqual(promote.call_count, 1, "첫 건에서 막히면 나머지는 더 시도하면 안 된다")
        self.assertEqual(len(result.failed), 3, "대기 중이던 3건 전부에 사유가 남아야 한다")
        self.assertTrue(all(row["detail"] == "PipelineConfigurationError" for row in result.failed))

    def test_시간_안에_못_끝낸_문서는_실패로_남아_다음_회차가_집는다(self, repository, promote):
        """승격은 240초에서 기다리기를 포기하고 `ok=False` 로 돌아온다. 색인된
        것으로 세면 안 된다 — 다음 호출이 다시 집어야 한다."""

        repository.list_pending_index.return_value = ["DC001"]
        promote.return_value = {"doc_id": "DC001", "ok": False, "detail": "아직 준비 중입니다"}

        result = IntakeResult()
        _index_all(account_id="UA001", team_id="TM001", result=result)

        self.assertEqual(result.indexed, [])
        self.assertEqual(result.failed[0]["detail"], "아직 준비 중입니다")


def _changed(doc_id, file_name, *, content_hash, drive_modified="2026-08-24T09:00:00Z"):
    return {
        "doc_id": doc_id,
        "src_file_id": f"SRC-{doc_id}",
        "file_name": file_name,
        "mime_type": "application/pdf",
        "src_modified_at": None,
        "content_hash": content_hash,
        "drive_modified_at": drive_modified,
    }


@patch("services.document_intake.service.save_document")
@patch("services.document_intake.service.download_drive_file")
@patch("services.document_intake.service.DocumentRepository")
class RefetchChangedTests(SimpleTestCase):
    """Drive 에서 고쳐진 문서를 다시 받는다(2026-08-24).

    없으면 기획서를 개정해도 우리는 영원히 등록 시점의 판으로 답한다.

    **`modifiedTime` 만으로 판단하지 않는다.** 이름 변경·공유 설정 변경·이동에도
    그 값은 오른다 — 그대로 믿고 재파싱하면 내용이 그대로인 문서로 GPU 를 태운다.
    """

    def test_내용이_바뀌었으면_다시_받아_저장한다(self, documents, download, save):
        documents.list_changed_on_drive.return_value = [
            _changed("DC001", "기획서.pdf", content_hash="sha256:old")
        ]
        download.return_value = {"content": b"new bytes", "mime_type": "application/pdf",
                                 "revision": "REV-2"}

        result = IntakeResult()
        _refetch_changed(
            account_id="UA001", team_id="TM001",
            live_modified={"SRC-DC001": "2026-08-24T09:00:00Z"}, result=result,
        )

        save.assert_called_once()
        self.assertEqual(result.refreshed, ["기획서.pdf"])
        stored = documents.mark_stored.call_args.kwargs
        self.assertEqual(stored["revision"], "REV-2", "새 revision 이 들어가야 옛 청크가 빠진다")
        self.assertEqual(stored["src_modified_at"], "2026-08-24T09:00:00Z")

    def test_내용이_같으면_저장도_재색인도_안_한다(self, documents, download, save):
        """`modifiedTime` 만 오른 경우다. 시각만 맞춰 두지 않으면 다음 스캔이
        같은 문서를 또 내려받는다."""

        same = content_hash(b"same bytes")
        documents.list_changed_on_drive.return_value = [
            _changed("DC001", "기획서.pdf", content_hash=same)
        ]
        download.return_value = {"content": b"same bytes", "mime_type": "application/pdf",
                                 "revision": "REV-1"}

        result = IntakeResult()
        _refetch_changed(
            account_id="UA001", team_id="TM001",
            live_modified={"SRC-DC001": "2026-08-24T09:00:00Z"}, result=result,
        )

        save.assert_not_called()
        documents.mark_stored.assert_not_called()
        documents.mark_unchanged.assert_called_once()
        self.assertEqual(result.refreshed, [], "내용이 그대로면 갱신으로 세지 않는다")

    def test_자격증명_오류면_남은_문서를_더_받으려_하지_않는다(self, documents, download, save):
        documents.list_changed_on_drive.return_value = [
            _changed("DC001", "a.pdf", content_hash="sha256:old"),
            _changed("DC002", "b.pdf", content_hash="sha256:old"),
        ]
        download.side_effect = OAuthError("Google Drive 인증이 만료되었습니다.")

        result = IntakeResult()
        _refetch_changed(
            account_id="UA001", team_id="TM001",
            live_modified={"SRC-DC001": "x", "SRC-DC002": "x"}, result=result,
        )

        self.assertEqual(download.call_count, 1)
        self.assertEqual(len(result.failed), 2)

    def test_바뀐_문서가_없으면_아무것도_안_받는다(self, documents, download, save):
        documents.list_changed_on_drive.return_value = []

        result = IntakeResult()
        _refetch_changed(
            account_id="UA001", team_id="TM001", live_modified={"SRC-DC001": "x"}, result=result,
        )

        download.assert_not_called()
        self.assertEqual(result.refreshed, [])
