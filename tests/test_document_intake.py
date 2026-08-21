"""`services/document_intake/service.py`의 자격증명 실패 처리 단위 테스트.

전체 파이프라인(등록·다운로드·요약)을 다 재현하지 않는다. 여기서 보는 것은
"자격증명 문제가 나면 배치가 그 자리에서 멈추는가" 하나뿐이다(2026-08-20).
"""

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.connectors.oauth import OAuthError
from services.document_intake.service import IntakeResult, _fetch_and_summarize


def _pending(doc_id, file_name):
    return {
        "doc_id": doc_id,
        "file_name": file_name,
        "storage_key": None,
        "src_file_id": f"SRC-{doc_id}",
        "mime_type": "application/pdf",
    }


@patch("services.document_intake.service.DocMetaRepository")
@patch("services.document_intake.service.DocumentRepository")
@patch("services.document_intake.service.download_drive_file")
class FetchAndSummarizeCredentialShortCircuitTests(SimpleTestCase):
    """자격증명 문제(`OAuthError`)는 같은 계정·같은 커넥터로 도는 남은 모든
    대기 문서에 반드시 똑같이 재현된다 — 첫 건에서 막히면 나머지는 더
    시도하지 않는다. 파일 하나만의 문제(`OSError` 등)는 그 한 건으로 끝나야
    하는 기존 규칙(모듈 docstring) 그대로 유지되는지도 같이 본다.
    """

    def test_자격증명_오류면_남은_문서를_더_받으려_하지_않는다(self, download, documents, doc_meta):
        documents.list_pending_download.return_value = [
            _pending("D1", "a.pdf"),
            _pending("D2", "b.pdf"),
            _pending("D3", "c.pdf"),
        ]
        doc_meta.pending_doc_ids.return_value = []
        download.side_effect = OAuthError("Google Drive 인증이 만료되었습니다.")

        result = IntakeResult()
        _fetch_and_summarize(account_id="UA001", team_id="TM001", result=result)

        self.assertEqual(download.call_count, 1, "첫 건에서 막히면 나머지는 더 시도하면 안 된다")
        self.assertEqual(len(result.failed), 3, "대기 중이던 3건 전부에 실패 사유가 남아야 한다")
        self.assertTrue(all(row["detail"] == "OAuthError" for row in result.failed))

    def test_파일_하나만의_문제면_나머지는_계속_시도한다(self, download, documents, doc_meta):
        documents.list_pending_download.return_value = [
            _pending("D1", "a.pdf"),
            _pending("D2", "b.pdf"),
        ]
        doc_meta.pending_doc_ids.return_value = []
        download.side_effect = OSError("disk full")

        result = IntakeResult()
        _fetch_and_summarize(account_id="UA001", team_id="TM001", result=result)

        self.assertEqual(download.call_count, 2, "파일 개별 문제는 그 한 건의 실패로 끝나야 한다")
        self.assertEqual(len(result.failed), 2)
