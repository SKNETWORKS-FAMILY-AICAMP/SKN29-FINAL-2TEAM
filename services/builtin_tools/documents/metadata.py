"""ExifTool을 사용해 정책 대상 내장 메타데이터가 남았는지 확인한다."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from services.builtin_tools.common.errors import BuiltinToolError
from services.builtin_tools.common.process import run_command
from services.builtin_tools.documents.reader import DOCX_MIME, PDF_MIME, XLSX_MIME

_SUFFIXES = {PDF_MIME: ".pdf", DOCX_MIME: ".docx", XLSX_MIME: ".xlsx"}
_SENSITIVE_NAMES = frozenset(
    {
        "author",
        "category",
        "comments",
        "company",
        "createdate",
        "creator",
        "creatortool",
        "description",
        "keywords",
        "lastmodifiedby",
        "manager",
        "metadatadate",
        "modifydate",
        "producer",
        "subject",
        "title",
    }
)


def sensitive_metadata(*, data: bytes, mime_type: str) -> dict[str, object]:
    """파일 통계가 아닌 작성자·제목·생성 도구 등의 잔여 값만 반환한다."""

    try:
        suffix = _SUFFIXES[mime_type]
    except KeyError as exc:
        raise BuiltinToolError("UNSUPPORTED_FORMAT", "PDF, DOCX, XLSX만 확인할 수 있습니다.") from exc
    with TemporaryDirectory(prefix="builtin-metadata-") as raw_directory:
        directory = Path(raw_directory)
        source = directory / f"source{suffix}"
        source.write_bytes(data)
        stdout, _ = run_command(
            "exiftool",
            ["-j", "-G1", "-a", "-s", str(source)],
            cwd=directory,
            home=directory,
            timeout_seconds=30,
        )
    try:
        payload = json.loads(stdout)
        values = payload[0]
    except (json.JSONDecodeError, IndexError, TypeError) as exc:
        raise BuiltinToolError("METADATA_CHECK_FAILED", "문서 속성 결과를 읽지 못했습니다.") from exc
    remaining = {}
    for key, value in values.items():
        plain_name = key.rsplit(":", 1)[-1].replace("_", "").lower()
        if plain_name in _SENSITIVE_NAMES and value not in (None, ""):
            remaining[key] = value
    return remaining
