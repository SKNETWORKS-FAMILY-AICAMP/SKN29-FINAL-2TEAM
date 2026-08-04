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
    @override_settings(PUBLIC_BACKEND_BASE_URL="https://demo.example.com")
    def test_signed_url_round_trip(self):
        url = signed_download_url(project_id="PJ001", doc_id="DC001", revision="rev-1")
        token = url.split("token=", 1)[1]
        self.assertEqual(
            read_download_token(token),
            {"project_id": "PJ001", "doc_id": "DC001", "revision": "rev-1"},
        )

    @override_settings(PUBLIC_BACKEND_BASE_URL="http://127.0.0.1:8000")
    def test_public_base_url_must_be_https(self):
        with self.assertRaises(PipelineConfigurationError):
            signed_download_url(project_id="PJ001", doc_id="DC001", revision="rev-1")


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
        get_document.return_value = {
            "doc_id": "DC001", "proj_id": "PJ001", "file_name": "plan.pdf",
            "mime_type": "application/pdf", "cur_revision": "rev-1",
            "storage_key": "PJ001/DC001.pdf",
        }
        submit.return_value = {"id": "job-1", "status": "IN_QUEUE"}
        response = self.client.post(
            "/api/projects/PJ001/documents/DC001/processing-runs/",
            headers=auth_header(),
        )
        self.assertEqual(response.status_code, 202)
        payload = submit.call_args.args[0]
        self.assertTrue(payload["source_url"].startswith("https://demo.example.com/"))
        self.assertNotIn("storage_key", payload)

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
