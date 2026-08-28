"""P3 결과 파일의 PostgreSQL·object storage 연결을 만들고 즉시 회수해 확인한다."""

from __future__ import annotations

from io import BytesIO
import json
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from pypdf import PdfWriter  # noqa: E402

from backend.db.connection import database_connection  # noqa: E402
from backend.db.document_pipeline import PersonalDocumentRepository  # noqa: E402
from backend.services import storage  # noqa: E402
from services.harness.registry import _PDF_MIME, _store_generated  # noqa: E402


def _sample_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def main() -> int:
    with database_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT account_id FROM user_account WHERE account_status = 'ACTIVE' ORDER BY account_id LIMIT 1"
        )
        row = cursor.fetchone()
    if row is None:
        print(json.dumps({"ok": False, "reason": "NO_ACCOUNT"}))
        return 2

    account_id = row["account_id"]
    doc_id = None
    key = None
    try:
        doc_id, _file_name = _store_generated(
            account_id=account_id,
            title="P3 저장 연결 확인",
            suffix=".pdf",
            mime_type=_PDF_MIME,
            data=_sample_pdf(),
        )
        stored = PersonalDocumentRepository.get_for_download(
            doc_id=doc_id, account_id=account_id
        )
        key = stored["storage_key"]
        payload = storage.load(key)
        ok = bool(payload.startswith(b"%PDF-") and stored["mime_type"] == _PDF_MIME)
        print(
            json.dumps(
                {
                    "ok": ok,
                    "postgres_row": bool(stored),
                    "storage_object": bool(payload),
                    "cleaned": True,
                },
                ensure_ascii=False,
            )
        )
        return 0 if ok else 1
    finally:
        if doc_id:
            try:
                removed_key = PersonalDocumentRepository.delete(
                    doc_id=doc_id, account_id=account_id
                )
                key = removed_key or key
            finally:
                if key:
                    storage.remove(key)


if __name__ == "__main__":
    raise SystemExit(main())
