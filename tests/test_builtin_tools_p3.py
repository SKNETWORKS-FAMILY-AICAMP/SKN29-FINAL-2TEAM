"""P3 Registry·권한·저장소 통합 계약."""

from __future__ import annotations

from contextlib import ExitStack
from io import BytesIO
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from docx import Document
from pypdf import PdfWriter

from backend.db.errors import PermissionDenied
from backend.db.document_pipeline import PipelineDocumentRepository
from services.harness import registry


NEW_TOOL_REFS = {
    "document_read",
    "document_convert",
    "pdf_edit",
    "file_inspect",
    "file_sanitize",
    "archive_manage",
    "table_transform",
    "data_quality_check",
    "file_compare",
    "calculate",
}


def _docx(text: str) -> bytes:
    document = Document()
    document.add_paragraph(text)
    output = BytesIO()
    document.save(output)
    return output.getvalue()


def _pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class RegistryShapeTests(SimpleTestCase):
    FINAL_NAMES = {
        "document_read": "문서 내용 추출",
        "document_convert": "파일 변환",
        "pdf_edit": "PDF 편집",
        "file_inspect": "파일 정보",
        "file_sanitize": "메타데이터 제거",
        "archive_manage": "압축·해제",
        "table_transform": "표 가공·집계",
        "data_quality_check": "데이터 품질 검사",
        "file_compare": "파일 비교",
        "calculate": "수식·날짜 계산",
    }

    def test_registers_all_ten_tools_with_machine_readable_schemas(self):
        self.assertTrue(NEW_TOOL_REFS.issubset(registry.BUILTIN_TOOLS))
        for ref in NEW_TOOL_REFS:
            with self.subTest(ref=ref):
                tool = registry.BUILTIN_TOOLS[ref]
                self.assertEqual(tool.ref, ref)
                self.assertEqual(tool.input_schema["type"], "object")
                self.assertIn("properties", tool.input_schema)
                self.assertGreater(len(tool.description), 20)

    def test_new_tool_display_names_match_the_approved_catalog(self):
        self.assertEqual(
            {ref: registry.BUILTIN_TOOLS[ref].name for ref in NEW_TOOL_REFS},
            self.FINAL_NAMES,
        )

    def test_only_file_creating_tools_require_approval(self):
        writes = {
            "document_convert",
            "pdf_edit",
            "file_sanitize",
            "archive_manage",
            "table_transform",
        }
        self.assertEqual(
            {ref for ref in NEW_TOOL_REFS if registry.BUILTIN_TOOLS[ref].side_effect},
            writes,
        )

    def test_routing_dataset_has_distinct_related_conflict_and_unrelated_cases(self):
        path = Path(__file__).parent / "fixtures/builtin_tools/routing_cases.v1.json"
        cases = json.loads(path.read_text(encoding="utf-8"))["cases"]
        self.assertEqual(len(cases), 30)
        self.assertEqual({case["kind"] for case in cases}, {"related", "conflict", "unrelated"})
        self.assertEqual(len({case["id"] for case in cases}), len(cases))
        self.assertTrue(
            all(case["expected_tool"] is None or case["expected_tool"] in registry.BUILTIN_TOOLS for case in cases)
        )


class FileBoundaryTests(SimpleTestCase):
    def test_reads_only_after_repository_permission_check(self):
        row = {
            "doc_id": "DC001",
            "file_name": "보고서.docx",
            "mime_type": registry._DOCX_MIME,
            "storage_key": "user/UA001/DC001.docx",
            "src_file_id": None,
        }
        with patch.object(
            registry.PipelineDocumentRepository, "get_for_processing", return_value=row
        ) as allowed, patch.object(registry.storage, "load", return_value=_docx("확인할 본문")):
            result = registry.BUILTIN_TOOLS["document_read"].handler(
                account_id="UA001", file_id="DC001"
            )

        allowed.assert_called_once_with(doc_id="DC001", account_id="UA001")
        self.assertEqual(result["sections"][0]["text"], "확인할 본문")

    def test_rejects_cross_tenant_file_before_storage_load(self):
        with patch.object(
            registry.PipelineDocumentRepository,
            "get_for_processing",
            side_effect=PermissionDenied("이 문서에 접근할 수 없습니다."),
        ), patch.object(registry.storage, "load") as load:
            with self.assertRaisesRegex(registry.ToolInputError, "접근할 수 없"):
                registry.BUILTIN_TOOLS["file_inspect"].handler(
                    account_id="UA001", file_id="OTHER"
                )
        load.assert_not_called()

    def test_connector_file_is_fetched_ephemerally_when_local_copy_was_discarded(self):
        row = {
            "doc_id": "DC001",
            "team_id": "TM001",
            "file_name": "연결문서.docx",
            "mime_type": registry._DOCX_MIME,
            "storage_key": None,
            "src_file_id": "drive-1",
        }
        with patch.object(
            registry.PipelineDocumentRepository, "get_for_processing", return_value=row
        ), patch.object(
            registry,
            "download_drive_file",
            return_value={"content": _docx("연결 본문"), "mime_type": registry._DOCX_MIME},
        ) as download, patch.object(registry.storage, "save") as save:
            result = registry.BUILTIN_TOOLS["document_read"].handler(
                account_id="UA001", file_id="DC001"
            )

        self.assertEqual(result["sections"][0]["text"], "연결 본문")
        download.assert_called_once_with(
            account_id="UA001", file_id="drive-1", mime_type=registry._DOCX_MIME
        )
        save.assert_not_called()

    def test_shared_personal_file_is_available_only_to_the_shared_team(self):
        row = {
            "doc_id": "DC001",
            "team_id": None,
            "owner_account_id": "UA002",
            "shared_team_id": "TE001",
            "proj_id": None,
            "file_name": "공유자료.pdf",
            "mime_type": registry._PDF_MIME,
            "doc_role": None,
            "cur_revision": "rev-1",
            "content_hash": "sha256:x",
            "storage_key": "user/UA002/DC001.pdf",
            "deleted": False,
            "access_revoked": False,
            "src_file_id": None,
        }
        cursor = MagicMock()
        cursor.fetchone.return_value = row
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor

        with patch("backend.db.document_pipeline.database_connection") as db, patch(
            "backend.db.document_pipeline._require_team", return_value="TE001"
        ):
            db.return_value.__enter__.return_value = connection
            result = PipelineDocumentRepository.get_for_processing(
                doc_id="DC001", account_id="UA001"
            )

        self.assertEqual(result["doc_id"], "DC001")

        with patch("backend.db.document_pipeline.database_connection") as db, patch(
            "backend.db.document_pipeline._require_team", return_value="TE999"
        ):
            db.return_value.__enter__.return_value = connection
            with self.assertRaises(PermissionDenied):
                PipelineDocumentRepository.get_for_processing(
                    doc_id="DC001", account_id="UA999"
                )


class GeneratedFilePersistenceTests(SimpleTestCase):
    def _stored(self):
        stack = ExitStack()
        create = stack.enter_context(
            patch.object(registry.PersonalDocumentRepository, "create_generated", return_value="DC900")
        )
        save = stack.enter_context(
            patch.object(registry.storage, "save", return_value="sha256:" + "a" * 64)
        )
        mark = stack.enter_context(patch.object(registry.DocumentRepository, "mark_stored"))
        delete = stack.enter_context(patch.object(registry.PersonalDocumentRepository, "delete"))
        return stack, create, save, mark, delete

    def test_conversion_creates_db_row_and_storage_object_without_mutating_source(self):
        source = _docx("원본")
        original = bytes(source)
        row = {
            "doc_id": "DC001",
            "file_name": "원본.docx",
            "mime_type": registry._DOCX_MIME,
            "storage_key": "source",
            "src_file_id": None,
        }
        stack, create, save, mark, _delete = self._stored()
        with stack, patch.object(
            registry.PipelineDocumentRepository, "get_for_processing", return_value=row
        ), patch.object(registry.storage, "load", return_value=source):
            result = registry.BUILTIN_TOOLS["document_convert"].handler(
                account_id="UA001", file_id="DC001", target_format="md"
            )

        self.assertEqual(result["file"]["doc_id"], "DC900")
        create.assert_called_once()
        save.assert_called_once()
        mark.assert_called_once()
        self.assertEqual(source, original)

    def test_storage_failure_removes_pending_database_row(self):
        with patch.object(
            registry.PersonalDocumentRepository, "create_generated", return_value="DC900"
        ), patch.object(registry.storage, "save", side_effect=OSError("disk full")), patch.object(
            registry.PersonalDocumentRepository, "delete", return_value=None
        ) as delete:
            with self.assertRaises(OSError):
                registry._store_generated(
                    account_id="UA001",
                    title="결과",
                    suffix=".pdf",
                    mime_type=registry._PDF_MIME,
                    data=b"result",
                )
        delete.assert_called_once_with(doc_id="DC900", account_id="UA001")

    def test_database_finalize_failure_removes_row_and_storage_object(self):
        with patch.object(
            registry.PersonalDocumentRepository, "create_generated", return_value="DC900"
        ), patch.object(
            registry.storage, "save", return_value="sha256:" + "c" * 64
        ), patch.object(
            registry.DocumentRepository, "mark_stored", side_effect=RuntimeError("db down")
        ), patch.object(
            registry.PersonalDocumentRepository, "delete", return_value=None
        ) as delete, patch.object(registry.storage, "remove") as remove:
            with self.assertRaises(RuntimeError):
                registry._store_generated(
                    account_id="UA001",
                    title="결과",
                    suffix=".pdf",
                    mime_type=registry._PDF_MIME,
                    data=b"result",
                )

        delete.assert_called_once_with(doc_id="DC900", account_id="UA001")
        remove.assert_called_once_with("user/UA001/DC900.pdf")

    def test_batch_output_failure_removes_already_persisted_results(self):
        archive = registry.create_zip([("one.txt", b"1"), ("two.txt", b"2")])
        row = {
            "doc_id": "ZIP01",
            "file_name": "files.zip",
            "mime_type": registry._ZIP_MIME,
            "storage_key": "zip-key",
            "src_file_id": None,
        }
        with patch.object(
            registry.PipelineDocumentRepository, "get_for_processing", return_value=row
        ), patch.object(registry.storage, "load", return_value=archive), patch.object(
            registry,
            "_store_generated",
            side_effect=[("DC901", "one.txt"), OSError("disk full")],
        ), patch.object(
            registry.PersonalDocumentRepository, "delete", return_value="user/UA001/DC901.txt"
        ) as delete, patch.object(registry.storage, "remove") as remove:
            with self.assertRaises(OSError):
                registry.BUILTIN_TOOLS["archive_manage"].handler(
                    account_id="UA001", operation="extract", archive_file_id="ZIP01"
                )

        delete.assert_called_once_with(doc_id="DC901", account_id="UA001")
        remove.assert_called_once_with("user/UA001/DC901.txt")


class IntegratedHandlersTests(SimpleTestCase):
    def _sources(self, rows: dict[str, tuple[str, bytes]]):
        def get(*, doc_id, account_id):
            mime, _data = rows[doc_id]
            return {
                "doc_id": doc_id,
                "file_name": f"{doc_id}.bin",
                "mime_type": mime,
                "storage_key": doc_id,
                "src_file_id": None,
            }

        def load(key):
            return rows[key][1]

        return patch.object(
            registry.PipelineDocumentRepository, "get_for_processing", side_effect=get
        ), patch.object(registry.storage, "load", side_effect=load)

    def test_read_inspect_quality_compare_and_calculate_paths(self):
        rows = {
            "CSV": (registry._CSV_MIME, b"name,hours\nkim,8\nkim,8\nlee,\n"),
            "OLD": (registry._DOCX_MIME, _docx("이전")),
            "NEW": (registry._DOCX_MIME, _docx("이후")),
        }
        source, load = self._sources(rows)
        with source, load:
            quality = registry.BUILTIN_TOOLS["data_quality_check"].handler(
                account_id="UA001", file_id="CSV"
            )
            compared = registry.BUILTIN_TOOLS["file_compare"].handler(
                account_id="UA001", before_file_id="OLD", after_file_id="NEW"
            )
            inspected = registry.BUILTIN_TOOLS["file_inspect"].handler(
                account_id="UA001", file_id="OLD"
            )
        calculated = registry.BUILTIN_TOOLS["calculate"].handler(
            operation="math", expression="(12 + 8) * 0.5"
        )

        self.assertFalse(quality["valid"])
        self.assertGreater(compared["change_count"], 0)
        self.assertEqual(inspected["paragraph_count"], 1)
        self.assertEqual(calculated["decimal"], 10.0)

    def test_pdf_edit_archive_and_table_export_paths_persist_results(self):
        rows = {
            "PDF": (registry._PDF_MIME, _pdf()),
            "CSV": (registry._CSV_MIME, b"team,hours\na,2\nb,1\n"),
            "TXT": ("text/plain", b"hello"),
        }
        source, load = self._sources(rows)
        counter = iter(["DC901", "DC902", "DC903"])
        with source, load, patch.object(
            registry.PersonalDocumentRepository,
            "create_generated",
            side_effect=lambda **_kwargs: next(counter),
        ), patch.object(
            registry.storage, "save", return_value="sha256:" + "b" * 64
        ), patch.object(registry.DocumentRepository, "mark_stored"):
            edited = registry.BUILTIN_TOOLS["pdf_edit"].handler(
                account_id="UA001", operation="rotate", file_ids=["PDF"], rotation=90
            )
            archived = registry.BUILTIN_TOOLS["archive_manage"].handler(
                account_id="UA001", operation="create", file_ids=["TXT"]
            )
            transformed = registry.BUILTIN_TOOLS["table_transform"].handler(
                account_id="UA001",
                file_id="CSV",
                operation="sort",
                sort=[{"column": "hours", "direction": "desc"}],
                output_format="csv",
            )

        self.assertEqual(edited["files"][0]["doc_id"], "DC901")
        self.assertEqual(archived["files"][0]["doc_id"], "DC902")
        self.assertEqual(transformed["file"]["doc_id"], "DC903")
