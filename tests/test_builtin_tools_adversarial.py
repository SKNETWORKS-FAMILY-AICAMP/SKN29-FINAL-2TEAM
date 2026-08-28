"""기능별 happy path와 다른 경계에서 신규 기본 Tool을 역검증한다."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
import json
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

from django.test import SimpleTestCase
from botocore.exceptions import ClientError
from openpyxl import Workbook

from services.agent_runtime.context import RuntimeContext
from services.agent_runtime.factory import _to_langchain_tool
from services.agent_runtime.runtime_policy import RuntimeCapabilityPolicy
from services.agent_runtime.tools.loader import Tool
from services.builtin_tools.common.errors import BuiltinToolError
from services.builtin_tools.documents.package_safety import validate_ooxml_package
from services.builtin_tools.documents.reader import XLSX_MIME, read_document
from services.builtin_tools.data.comparer import compare_files
from services.harness import registry


def _xlsx(value) -> bytes:
    workbook = Workbook()
    workbook.active["A1"] = value
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


class CompressedOfficeAttackTests(SimpleTestCase):
    def test_small_zip_with_extreme_expansion_is_rejected_before_office_parser(self):
        output = BytesIO()
        with ZipFile(output, "w", ZIP_DEFLATED) as archive:
            archive.writestr("word/document.xml", b"0" * (1024 * 1024))

        with self.assertRaisesRegex(BuiltinToolError, "압축률"):
            validate_ooxml_package(output.getvalue())

    def test_document_reader_uses_the_same_package_guard(self):
        output = BytesIO()
        with ZipFile(output, "w", ZIP_DEFLATED) as archive:
            archive.writestr("xl/worksheets/sheet1.xml", b"0" * (1024 * 1024))

        with self.assertRaisesRegex(BuiltinToolError, "압축률"):
            read_document(data=output.getvalue(), mime_type=XLSX_MIME)


class JsonBoundaryTests(SimpleTestCase):
    def test_xlsx_dates_from_read_and_compare_are_json_serializable(self):
        before = _xlsx(datetime(2026, 8, 27, 9, 30))
        after = _xlsx(datetime(2026, 8, 28, 9, 30))

        read_result = read_document(data=before, mime_type=XLSX_MIME)
        compare_result = compare_files(before=before, after=after, mime_type=XLSX_MIME)

        json.dumps(read_result, ensure_ascii=False)
        json.dumps(compare_result, ensure_ascii=False)
        self.assertEqual(read_result["tables"][0]["rows"][0][0], "2026-08-27T09:30:00")


class GeneratedNameBoundaryTests(SimpleTestCase):
    def test_model_generated_long_title_cannot_overflow_database_file_name(self):
        with patch.object(
            registry.PersonalDocumentRepository, "create_generated", return_value="DC900"
        ) as create, patch.object(
            registry.storage, "save", return_value="sha256:" + "a" * 64
        ), patch.object(registry.DocumentRepository, "mark_stored"):
            _doc_id, file_name = registry._store_generated(
                account_id="UA001",
                title="가" * 1000,
                suffix=".docx",
                mime_type=registry._DOCX_MIME,
                data=b"x",
            )

        self.assertLessEqual(len(file_name), 255)
        self.assertEqual(create.call_args.kwargs["file_name"], file_name)


class ObjectStorageParityTests(SimpleTestCase):
    def test_s3_read_failure_is_a_speakable_file_error_like_local_storage_failure(self):
        row = {
            "doc_id": "DC001",
            "file_name": "보고서.pdf",
            "mime_type": registry._PDF_MIME,
            "storage_key": "user/UA001/DC001.pdf",
            "src_file_id": None,
        }
        failure = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "denied"}}, "GetObject"
        )
        with patch.object(
            registry.PipelineDocumentRepository, "get_for_processing", return_value=row
        ), patch.object(registry.storage, "load", side_effect=failure):
            with self.assertRaisesRegex(registry.ToolInputError, "원문을 읽지 못"):
                registry._tool_input_file(account_id="UA001", doc_id="DC001")

    def test_failed_compensation_is_enqueued_for_worker_retry(self):
        failure = ClientError(
            {"Error": {"Code": "ServiceUnavailable", "Message": "retry"}},
            "DeleteObject",
        )
        with patch.object(
            registry.PersonalDocumentRepository, "create_generated", return_value="DC901"
        ), patch.object(
            registry.storage, "save", return_value="sha256:" + "b" * 64
        ), patch.object(
            registry.DocumentRepository, "mark_stored", side_effect=RuntimeError("db")
        ), patch.object(
            registry.PersonalDocumentRepository, "delete"
        ), patch.object(
            registry.storage, "remove", side_effect=failure
        ), patch.object(
            registry.StorageCleanupOutboxRepository, "enqueue"
        ) as enqueue:
            with self.assertRaises(RuntimeError):
                registry._store_generated(
                    account_id="UA001",
                    title="실패",
                    suffix=".pdf",
                    mime_type=registry._PDF_MIME,
                    data=b"pdf",
                )

        enqueue.assert_called_once_with(
            storage_key="user/UA001/DC901.pdf", error_code="ClientError"
        )


class ArchiveContentConfusionTests(SimpleTestCase):
    def test_executable_disguised_as_pdf_is_rejected_before_persistence(self):
        archive = registry.create_zip([("invoice.pdf", b"MZ\x90\x00not-a-pdf")])
        row = {
            "doc_id": "ZIP01",
            "file_name": "upload.zip",
            "mime_type": registry._ZIP_MIME,
            "storage_key": "zip",
            "src_file_id": None,
        }
        with patch.object(
            registry.PipelineDocumentRepository, "get_for_processing", return_value=row
        ), patch.object(registry.storage, "load", return_value=archive), patch.object(
            registry, "_store_generated"
        ) as store:
            with self.assertRaisesRegex(registry.ToolInputError, "실제 형식"):
                registry.BUILTIN_TOOLS["archive_manage"].handler(
                    account_id="UA001", operation="extract", archive_file_id="ZIP01"
                )
        store.assert_not_called()


class IdempotencyReplayShapeTests(SimpleTestCase):
    def test_cached_file_result_is_restored_as_a_dict_not_python_repr_text(self):
        handler_calls = []
        tool = Tool(
            ref="document_create",
            name="Word 만들기",
            description="파일을 만든다.",
            input_schema={"type": "object", "properties": {}},
            handler=lambda: handler_calls.append(True),
            side_effect=True,
        )
        context = RuntimeContext(
            account_id="UA001", team_id="TE001", role="leader", run_id="run-1"
        )
        langchain_tool = _to_langchain_tool(
            tool, context=context, runtime_policy=RuntimeCapabilityPolicy()
        )
        cached = json.dumps(
            {"file": {"doc_id": "DC001", "file_name": "결과.docx", "mime_type": "x/y"}},
            ensure_ascii=False,
        )

        with patch(
            "backend.db.agent_platform.ToolCallIdempotencyRepository.claim_or_get",
            return_value=("SUCCEEDED", cached),
        ):
            result = langchain_tool.run({}, tool_call_id="call-1")

        self.assertEqual(json.loads(result.content)["file"]["doc_id"], "DC001")
        self.assertEqual(handler_calls, [])

    def test_new_idempotency_record_uses_json_instead_of_python_repr(self):
        value = {"file": {"doc_id": "DC002", "file_name": "결과.docx", "mime_type": "x/y"}}
        tool = Tool(
            ref="document_create",
            name="Word 만들기",
            description="파일을 만든다.",
            input_schema={"type": "object", "properties": {}},
            handler=lambda: value,
            side_effect=True,
        )
        context = RuntimeContext(
            account_id="UA001", team_id="TE001", role="leader", run_id="run-1"
        )
        langchain_tool = _to_langchain_tool(
            tool, context=context, runtime_policy=RuntimeCapabilityPolicy()
        )

        with patch(
            "backend.db.agent_platform.ToolCallIdempotencyRepository.claim_or_get",
            return_value=("CLAIMED", None),
        ), patch(
            "backend.db.agent_platform.ToolCallIdempotencyRepository.record_result"
        ) as record:
            langchain_tool.run({}, tool_call_id="call-2")

        stored = record.call_args.kwargs["result"]
        self.assertEqual(json.loads(stored), value)
        self.assertIn('"file"', stored)

    def test_failed_claim_is_released_so_a_retry_can_execute(self):
        tool = Tool(
            ref="document_create",
            name="Word 만들기",
            description="파일을 만든다.",
            input_schema={"type": "object", "properties": {}},
            handler=lambda: (_ for _ in ()).throw(ValueError("boom")),
            side_effect=True,
        )
        context = RuntimeContext(
            account_id="UA001", team_id="TE001", role="leader", run_id="run-1"
        )
        langchain_tool = _to_langchain_tool(
            tool, context=context, runtime_policy=RuntimeCapabilityPolicy()
        )

        with patch(
            "backend.db.agent_platform.ToolCallIdempotencyRepository.claim_or_get",
            return_value=("CLAIMED", None),
        ), patch(
            "backend.db.agent_platform.ToolCallIdempotencyRepository.abandon_claim"
        ) as abandon:
            result = langchain_tool.run({}, tool_call_id="call-failed")

        self.assertEqual(result.status, "error")
        abandon.assert_called_once_with(
            run_id="run-1", langchain_tool_call_id="call-failed"
        )
