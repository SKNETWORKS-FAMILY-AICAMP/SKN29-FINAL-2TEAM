from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.accounts.tokens import issue_token
from runpod_worker.pipeline import _generic_row_records, _product_records
from services.document_pipeline.errors import PipelineConfigurationError
from services.document_pipeline.signing import read_download_token, signed_download_url


def auth_header(account_id="UA001"):
    return {"authorization": f"Bearer {issue_token(account_id)}"}


def table(cells, rows=2, cols=3):
    return {
        "self_ref": "#/tables/0",
        "data": {"num_rows": rows, "num_cols": cols, "table_cells": cells},
        "prov": [{"page_no": 2}],
    }


def cell(text, sr, er, sc, ec, **flags):
    return {
        "text": text,
        "start_row_offset_idx": sr,
        "end_row_offset_idx": er,
        "start_col_offset_idx": sc,
        "end_col_offset_idx": ec,
        **flags,
    }


class TableChunkingTests(SimpleTestCase):
    def test_product_columns_preserve_source_order_and_values(self):
        source = table(
            [
                cell("Model", 0, 1, 0, 1, column_header=True),
                cell("B", 0, 1, 1, 2, column_header=True),
                cell("A", 0, 1, 2, 3, column_header=True),
                cell("압력", 1, 2, 0, 1, row_header=True),
                cell("10 bar", 1, 2, 1, 2),
                cell("20 bar", 1, 2, 2, 3),
            ]
        )
        records = _product_records(source, 0)
        self.assertEqual([r["meta"]["product"] for r in records], ["B", "A"])
        self.assertIn("압력: 10 bar", records[0]["text"])

    def test_non_product_table_uses_generic_rows(self):
        source = table(
            [
                cell("요구사항", 0, 1, 0, 1, column_header=True),
                cell("담당", 0, 1, 1, 2, column_header=True),
                cell("상태", 0, 1, 2, 3, column_header=True),
                cell("로그인", 1, 2, 0, 1),
                cell("백엔드", 1, 2, 1, 2),
                cell("진행", 1, 2, 2, 3),
            ]
        )
        self.assertEqual(_product_records(source, 0), [])
        rows = _generic_row_records(source, 0)
        self.assertEqual(len(rows), 1)
        self.assertIn("요구사항: 로그인", rows[0]["text"])


class SigningTests(SimpleTestCase):
    """서명은 `doc_id`+`revision`만 묶는다(2026-08-04).

    `project_id`를 함께 서명하던 시절이 있었는데, 문서 처리는 팀 단위라 이 시점에
    문서가 어느 프로젝트에 속할지 아직 정해지지 않았다(`doc.proj_id`가 NULL).
    """

    @override_settings(PUBLIC_BACKEND_BASE_URL="https://demo.example.com")
    def test_signed_url_round_trip(self):
        url = signed_download_url(doc_id="DC001", revision="rev-1")
        token = url.split("token=", 1)[1]
        self.assertEqual(
            read_download_token(token),
            {"doc_id": "DC001", "revision": "rev-1"},
        )

    @override_settings(PUBLIC_BACKEND_BASE_URL="https://demo.example.com")
    def test_url_carries_no_storage_path(self):
        """원문이 로컬 어디에 있는지는 RunPod에 알려 줄 이유가 없다."""

        url = signed_download_url(doc_id="DC001", revision="rev-1")

        self.assertNotIn("storage", url)
        self.assertTrue(url.startswith("https://demo.example.com/"))

    @override_settings(PUBLIC_BACKEND_BASE_URL="http://127.0.0.1:8000")
    def test_public_base_url_must_be_https(self):
        with self.assertRaises(PipelineConfigurationError):
            signed_download_url(doc_id="DC001", revision="rev-1")


@override_settings(
    PUBLIC_BACKEND_BASE_URL="https://demo.example.com",
    CHUNKING_MAX_TOKENS=512,
    CHUNKING_MERGE_PEERS=True,
)
class ProcessingApiTests(SimpleTestCase):
    @patch("apps.projects.api_views.submit_document_job")
    @patch("apps.projects.api_views.document_exists", return_value=True)
    @patch("apps.projects.api_views.PipelineDocumentRepository.get_for_processing")
    def test_submit_uses_signed_url_not_local_path(self, get_document, _exists, submit):
        """RunPod에 로컬 경로를 보내면 남의 인프라에서 열 수 없을 뿐 아니라,
        우리 저장소 구조를 바깥에 알려 주게 된다."""

        get_document.return_value = {
            "doc_id": "DC001", "team_id": "TM001", "proj_id": None, "file_name": "plan.pdf",
            "mime_type": "application/pdf", "cur_revision": "rev-1",
            "storage_key": "TM001/DC001.pdf",
        }
        submit.return_value = {"id": "job-1", "status": "IN_QUEUE"}
        response = self.client.post(
            "/api/team/documents/DC001/processing-runs/",
            headers=auth_header(),
        )
        self.assertEqual(response.status_code, 202)
        payload = submit.call_args.args[0]
        self.assertTrue(payload["source_url"].startswith("https://demo.example.com/"))
        self.assertNotIn("storage_key", payload)

    @patch("apps.projects.api_views.submit_document_job")
    @patch("apps.projects.api_views.document_exists", return_value=True)
    @patch("apps.projects.api_views.PipelineDocumentRepository.get_for_processing")
    def test_document_not_yet_in_a_project_can_be_processed(self, get_document, _exists, submit):
        """`proj_id`가 NULL이어도 처리된다 — 파싱이 기준 문서 선택보다 먼저다.

        프로젝트로 걸렀다면 처리 가능한 문서가 언제나 0건이었다.
        """

        get_document.return_value = {
            "doc_id": "DC002", "team_id": "TM001", "proj_id": None, "file_name": "rfp.docx",
            "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "cur_revision": "rev-9", "storage_key": "TM001/DC002.docx",
        }
        submit.return_value = {"id": "job-2", "status": "IN_QUEUE"}

        response = self.client.post(
            "/api/team/documents/DC002/processing-runs/", headers=auth_header()
        )

        self.assertEqual(response.status_code, 202)

    @patch("apps.projects.api_views.PipelineDocumentRepository.list_ready_for_analysis")
    def test_unprocessed_primary_document_is_conflict(self, list_documents):
        list_documents.return_value = [
            {"doc_id": "DC001", "file_name": "plan.pdf", "search_ready": False}
        ]
        response = self.client.post(
            "/api/projects/PJ001/task-extraction-runs/",
            {"primary_document_id": "DC001"},
            content_type="application/json",
            headers=auth_header(),
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("파싱", response.json()["detail"])


class SourceDocumentSelectionTests(SimpleTestCase):
    """기준 문서 선택이 프로젝트에 문서를 묶는다.

    **이 저장이 신규 프로젝트를 정의하는 행위다.** 기존 프로젝트에 문서를 붙이는
    것이 아니라, 기획서를 고르는 것이 곧 프로젝트를 만드는 것이라는 전제를 지킨다.
    """

    def _put(self, body):
        return self.client.put(
            "/api/projects/PJ001/source-documents/",
            body,
            content_type="application/json",
            headers=auth_header(),
        )

    @patch("apps.projects.api_views.PipelineDocumentRepository.list_ready_for_analysis")
    @patch("apps.projects.api_views.PipelineDocumentRepository.set_project_documents")
    def test_primary_and_subs_are_saved_together(self, save, list_ready):
        list_ready.return_value = []

        response = self._put(
            {"primary_document_id": "DC001", "sub_document_ids": ["DC002", "DC003"]}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(save.call_args.kwargs["primary_doc_id"], "DC001")
        self.assertEqual(save.call_args.kwargs["sub_doc_ids"], ["DC002", "DC003"])

    @patch("apps.projects.api_views.PipelineDocumentRepository.list_ready_for_analysis")
    @patch("apps.projects.api_views.PipelineDocumentRepository.set_project_documents")
    def test_subs_may_be_omitted(self, save, list_ready):
        """근거 문서 없이 기준 문서만으로도 시작할 수 있어야 한다."""

        list_ready.return_value = []

        response = self._put({"primary_document_id": "DC001"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(save.call_args.kwargs["sub_doc_ids"], [])

    @patch(
        "apps.projects.api_views.PipelineDocumentRepository.set_project_documents",
        side_effect=ValueError("기준 문서를 서브 문서로 함께 지정할 수 없습니다."),
    )
    def test_primary_cannot_also_be_a_sub(self, _save):
        """같은 문서가 기준이자 근거이면 1단계와 2~4단계 범위가 같아진다."""

        response = self._put(
            {"primary_document_id": "DC001", "sub_document_ids": ["DC001"]}
        )

        self.assertEqual(response.status_code, 400)

    def test_requires_login(self):
        response = self.client.put(
            "/api/projects/PJ001/source-documents/",
            {"primary_document_id": "DC001"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)
