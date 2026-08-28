"""현재 의존성만 사용하는 문서 변환 경로."""

from __future__ import annotations

from io import BytesIO
import posixpath
from pathlib import Path
from pathlib import PurePosixPath
from tempfile import TemporaryDirectory
from urllib.parse import unquote, urlsplit
from zipfile import BadZipFile, ZipFile
from xml.etree import ElementTree

from markdown_it import MarkdownIt
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from services.builtin_tools.common.errors import BuiltinToolError
from services.builtin_tools.common.limits import (
    MAX_ARCHIVE_FILES,
    MAX_ARCHIVE_RATIO,
    MAX_ARCHIVE_UNCOMPRESSED_BYTES,
    MAX_FILE_BYTES,
    MAX_OUTPUT_BYTES,
    MAX_PDF_PAGES,
)
from services.builtin_tools.common.process import run_command
from services.builtin_tools.documents.inspector import detect_mime_type
from services.builtin_tools.documents.reader import DOCX_MIME, PDF_MIME, XLSX_MIME, read_document

_OFFICE_SUFFIXES = {DOCX_MIME: ".docx", XLSX_MIME: ".xlsx"}
_OFFICE_PDF_FILTERS = {DOCX_MIME: "pdf:writer_pdf_Export", XLSX_MIME: "pdf:calc_pdf_Export"}


def markdown_to_html(markdown: str) -> bytes:
    """Markdown을 외부 네트워크와 raw HTML 없이 UTF-8 HTML로 변환한다."""

    if not (markdown or "").strip():
        raise BuiltinToolError("EMPTY_CONTENT", "변환할 Markdown 내용이 비어 있습니다.")
    if len(markdown.encode("utf-8")) > MAX_FILE_BYTES:
        raise BuiltinToolError("FILE_TOO_LARGE", "Markdown은 20MB 이하여야 합니다.")
    parser = MarkdownIt("commonmark", {"html": False, "linkify": False})
    fragment = parser.render(markdown)
    return (
        '<!doctype html><html lang="ko"><head><meta charset="utf-8">'
        f"</head><body>{fragment}</body></html>"
    ).encode("utf-8")


def _markdown_table(rows: list[list[object]]) -> list[str]:
    if not rows:
        return []
    width = max(len(row) for row in rows)
    normalized = [list(row) + [None] * (width - len(row)) for row in rows]

    def cell(value: object) -> str:
        return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")

    header = [cell(value) for value in normalized[0]]
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * width) + " |"]
    lines.extend("| " + " | ".join(cell(value) for value in row) + " |" for row in normalized[1:])
    return lines


def document_to_markdown(*, data: bytes, mime_type: str) -> str:
    """기존 parser 결과를 결정적으로 Markdown으로 직렬화한다."""

    document = read_document(data=data, mime_type=mime_type)
    lines: list[str] = []
    for section in document["sections"]:
        location = section["location"]
        if "page" in location:
            lines.append(f"## {location['page']}페이지")
        text = section["text"].strip()
        if text:
            lines.append(text)
    for table in document["tables"]:
        location = table["location"]
        if "sheet" in location:
            lines.append(f"## {location['sheet']}")
        elif "page" in location:
            lines.append(f"### {location['page']}페이지 표 {location['table']}")
        elif "table" in location:
            lines.append(f"## 표 {location['table']}")
        lines.extend(_markdown_table(table["rows"]))
    return "\n\n".join(line for line in lines if line).strip()


def _reject_markdown_images(markdown: str) -> None:
    parser = MarkdownIt("commonmark", {"html": False, "linkify": False})
    for token in parser.parse(markdown):
        for child in token.children or []:
            if child.type == "image":
                raise BuiltinToolError(
                    "IMAGE_NOT_SUPPORTED", "이미지가 포함된 Markdown은 변환할 수 없습니다."
                )


def _reject_external_office_resources(data: bytes) -> None:
    """LibreOffice가 변환 중 외부 파일이나 URL을 가져오지 못하게 한다."""

    try:
        with ZipFile(BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ARCHIVE_FILES:
                raise BuiltinToolError("TOO_MANY_ARCHIVE_FILES", "Office 문서 내부 파일이 너무 많습니다.")
            uncompressed_size = sum(info.file_size for info in entries)
            compressed_size = max(sum(info.compress_size for info in entries), 1)
            if (
                uncompressed_size > MAX_ARCHIVE_UNCOMPRESSED_BYTES
                or uncompressed_size / compressed_size > MAX_ARCHIVE_RATIO
            ):
                raise BuiltinToolError("ARCHIVE_LIMIT_EXCEEDED", "Office 문서의 압축 크기가 안전 기준을 넘었습니다.")
            for name in archive.namelist():
                if not name.endswith(".rels"):
                    continue
                try:
                    relationships = ElementTree.fromstring(archive.read(name))
                except ElementTree.ParseError as exc:
                    raise BuiltinToolError(
                        "INVALID_OFFICE_FILE", "Office 문서의 연결 정보를 읽지 못했습니다."
                    ) from exc
                for relationship in relationships:
                    external = relationship.attrib.get("TargetMode", "").lower() == "external"
                    relation_type = relationship.attrib.get("Type", "").lower()
                    raw_target = relationship.attrib.get("Target", "").replace("\\", "/")
                    parsed_target = urlsplit(raw_target)
                    target = unquote(parsed_target.path)
                    if external and not relation_type.endswith("/hyperlink"):
                        raise BuiltinToolError(
                            "EXTERNAL_RESOURCE_NOT_ALLOWED",
                            "외부 파일을 참조하는 문서는 PDF로 변환할 수 없습니다.",
                        )
                    relation_path = PurePosixPath(name)
                    base = "" if name == "_rels/.rels" else str(relation_path.parent.parent)
                    resolved_target = posixpath.normpath(
                        target.lstrip("/") if target.startswith("/") else posixpath.join(base, target)
                    )
                    if not external and (
                        bool(parsed_target.scheme)
                        or bool(parsed_target.netloc)
                        or target.startswith("//")
                        or resolved_target == ".."
                        or resolved_target.startswith("../")
                    ):
                        raise BuiltinToolError(
                            "UNSAFE_OFFICE_RELATIONSHIP",
                            "문서 밖의 파일을 참조하는 Office 문서는 변환할 수 없습니다.",
                        )
    except BadZipFile as exc:
        raise BuiltinToolError("INVALID_OFFICE_FILE", "손상된 Office 문서입니다.") from exc


def _validate_pdf(data: bytes) -> None:
    if not data or len(data) > MAX_OUTPUT_BYTES:
        raise BuiltinToolError("INVALID_PDF_OUTPUT", "PDF 변환 결과가 올바르지 않습니다.")
    try:
        reader = PdfReader(BytesIO(data))
    except PdfReadError as exc:
        raise BuiltinToolError("INVALID_PDF_OUTPUT", "PDF 변환 결과를 열지 못했습니다.") from exc
    if not 1 <= len(reader.pages) <= MAX_PDF_PAGES:
        raise BuiltinToolError("INVALID_PDF_OUTPUT", "PDF 변환 결과의 페이지 수가 올바르지 않습니다.")


def markdown_to_docx(markdown: str) -> bytes:
    """외부 리소스 없이 Markdown을 DOCX로 변환한다."""

    if not (markdown or "").strip():
        raise BuiltinToolError("EMPTY_CONTENT", "변환할 Markdown 내용이 비어 있습니다.")
    encoded = markdown.encode("utf-8")
    if len(encoded) > MAX_FILE_BYTES:
        raise BuiltinToolError("FILE_TOO_LARGE", "Markdown은 20MB 이하여야 합니다.")
    _reject_markdown_images(markdown)
    with TemporaryDirectory(prefix="builtin-pandoc-") as raw_directory:
        directory = Path(raw_directory)
        output, _ = run_command(
            "pandoc",
            ["--from=gfm-raw_html", "--to=docx", "--standalone"],
            cwd=directory,
            home=directory,
            timeout_seconds=60,
            input_data=encoded,
        )
    if not output or len(output) > MAX_OUTPUT_BYTES:
        raise BuiltinToolError("INVALID_DOCX_OUTPUT", "DOCX 변환 결과가 올바르지 않습니다.")
    if detect_mime_type(output) != DOCX_MIME:
        raise BuiltinToolError("INVALID_DOCX_OUTPUT", "DOCX 변환 결과의 형식이 올바르지 않습니다.")
    return output


def office_to_pdf(*, data: bytes, mime_type: str) -> bytes:
    """DOCX 또는 XLSX를 별도의 새 PDF로 변환한다."""

    if not data:
        raise BuiltinToolError("EMPTY_FILE", "빈 문서는 변환할 수 없습니다.")
    if len(data) > MAX_FILE_BYTES:
        raise BuiltinToolError("FILE_TOO_LARGE", "문서는 20MB 이하여야 합니다.")
    try:
        suffix = _OFFICE_SUFFIXES[mime_type]
        conversion_filter = _OFFICE_PDF_FILTERS[mime_type]
    except KeyError as exc:
        raise BuiltinToolError("UNSUPPORTED_CONVERSION", "DOCX와 XLSX만 PDF로 변환할 수 있습니다.") from exc
    if detect_mime_type(data) != mime_type:
        raise BuiltinToolError("MIME_MISMATCH", "선택한 형식과 실제 파일 형식이 다릅니다.")
    _reject_external_office_resources(data)
    with TemporaryDirectory(prefix="builtin-office-") as raw_directory:
        directory = Path(raw_directory)
        source = directory / f"source{suffix}"
        output_directory = directory / "output"
        profile = directory / "profile"
        source.write_bytes(data)
        output_directory.mkdir()
        profile.mkdir()
        run_command(
            "soffice",
            [
                "--headless",
                "--nologo",
                "--nodefault",
                "--nofirststartwizard",
                f"-env:UserInstallation={profile.as_uri()}",
                "--convert-to",
                conversion_filter,
                "--outdir",
                str(output_directory),
                str(source),
            ],
            cwd=directory,
            home=directory,
            timeout_seconds=60,
        )
        target = output_directory / "source.pdf"
        if not target.is_file():
            raise BuiltinToolError("CONVERSION_OUTPUT_MISSING", "PDF 변환 결과가 생성되지 않았습니다.")
        output = target.read_bytes()
    _validate_pdf(output)
    return output


def markdown_to_pdf(markdown: str) -> bytes:
    """Markdown을 중간 DOCX로 만든 뒤 한글 글꼴이 적용되는 PDF로 변환한다."""

    return office_to_pdf(data=markdown_to_docx(markdown), mime_type=DOCX_MIME)
