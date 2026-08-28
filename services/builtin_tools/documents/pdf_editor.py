"""pypdf 기반의 제한된 PDF 페이지 편집."""

from __future__ import annotations

from io import BytesIO
from typing import Any

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError
from pypdf.generic import RectangleObject

from services.builtin_tools.common.errors import BuiltinToolError
from services.builtin_tools.common.limits import MAX_FILE_BYTES, MAX_OUTPUT_BYTES, MAX_PDF_PAGES

_ROTATIONS = frozenset({90, 180, 270})


def _reader(data: bytes) -> PdfReader:
    if not data:
        raise BuiltinToolError("EMPTY_FILE", "빈 PDF는 편집할 수 없습니다.")
    if len(data) > MAX_FILE_BYTES:
        raise BuiltinToolError("FILE_TOO_LARGE", "PDF는 파일당 20MB 이하여야 합니다.")
    try:
        reader = PdfReader(BytesIO(data))
    except PdfReadError as exc:
        raise BuiltinToolError("INVALID_PDF", "손상되었거나 지원하지 않는 PDF입니다.") from exc
    if reader.is_encrypted:
        raise BuiltinToolError("PASSWORD_REQUIRED", "암호가 설정된 PDF는 편집할 수 없습니다.")
    return reader


def _page_indexes(raw: list[int] | None, count: int) -> list[int]:
    pages = raw or list(range(1, count + 1))
    if not pages or any(not isinstance(page, int) or page < 1 or page > count for page in pages):
        raise BuiltinToolError("INVALID_PAGE_RANGE", "페이지 번호가 PDF 범위를 벗어났습니다.")
    return [page - 1 for page in pages]


def _write(writer: PdfWriter) -> bytes:
    output = BytesIO()
    writer.write(output)
    data = output.getvalue()
    if len(data) > MAX_OUTPUT_BYTES:
        raise BuiltinToolError("OUTPUT_TOO_LARGE", "결과 PDF가 허용 크기를 초과했습니다.")
    return data


def edit_pdf(
    *,
    operation: str,
    files: list[bytes],
    pages: list[int] | None = None,
    rotation: int | None = None,
    crop_box: list[float] | None = None,
    watermark: bytes | None = None,
) -> bytes | list[bytes]:
    """허용된 operation으로 새 PDF를 만든다. 페이지 번호는 1부터 시작한다."""

    if not files:
        raise BuiltinToolError("EMPTY_INPUT", "편집할 PDF를 선택해 주세요.")
    readers = [_reader(data) for data in files]
    total_pages = sum(len(reader.pages) for reader in readers)
    if total_pages > MAX_PDF_PAGES:
        raise BuiltinToolError("PAGE_LIMIT_EXCEEDED", "한 번에 200페이지까지 편집할 수 있습니다.")

    if operation == "merge":
        writer = PdfWriter()
        for reader in readers:
            for page in reader.pages:
                writer.add_page(page)
        return _write(writer)

    if len(readers) != 1:
        raise BuiltinToolError("ONE_FILE_REQUIRED", "이 작업은 PDF 한 개만 선택해야 합니다.")
    reader = readers[0]
    indexes = _page_indexes(pages, len(reader.pages))

    if operation == "split":
        outputs = []
        for index in indexes:
            writer = PdfWriter()
            writer.add_page(reader.pages[index])
            outputs.append(_write(writer))
        return outputs

    if operation in {"extract", "reorder"}:
        writer = PdfWriter()
        for index in indexes:
            writer.add_page(reader.pages[index])
        return _write(writer)

    if operation == "rotate":
        if rotation not in _ROTATIONS:
            raise BuiltinToolError("INVALID_ROTATION", "회전 각도는 90, 180, 270도만 가능합니다.")
        writer = PdfWriter()
        selected = set(indexes)
        for index, page in enumerate(reader.pages):
            if index in selected:
                page.rotate(rotation)
            writer.add_page(page)
        return _write(writer)

    if operation == "crop":
        if not crop_box or len(crop_box) != 4:
            raise BuiltinToolError("INVALID_CROP_BOX", "자르기 영역은 네 좌표로 지정해야 합니다.")
        left, bottom, right, top = crop_box
        if left >= right or bottom >= top:
            raise BuiltinToolError("INVALID_CROP_BOX", "자르기 영역의 좌표 순서가 올바르지 않습니다.")
        writer = PdfWriter()
        selected = set(indexes)
        for index, page in enumerate(reader.pages):
            if index in selected:
                media = page.mediabox
                if left < float(media.left) or bottom < float(media.bottom) or right > float(media.right) or top > float(media.top):
                    raise BuiltinToolError("INVALID_CROP_BOX", "자르기 영역이 페이지 바깥입니다.")
                page.cropbox = RectangleObject((left, bottom, right, top))
            writer.add_page(page)
        return _write(writer)

    if operation == "watermark":
        if watermark is None:
            raise BuiltinToolError("WATERMARK_REQUIRED", "워터마크 PDF를 선택해 주세요.")
        mark_reader = _reader(watermark)
        if len(mark_reader.pages) != 1:
            raise BuiltinToolError("INVALID_WATERMARK", "워터마크 PDF는 한 페이지여야 합니다.")
        writer = PdfWriter()
        selected = set(indexes)
        for index, page in enumerate(reader.pages):
            if index in selected:
                page.merge_page(mark_reader.pages[0])
            writer.add_page(page)
        return _write(writer)

    raise BuiltinToolError("UNSUPPORTED_OPERATION", "지원하지 않는 PDF 편집 작업입니다.")

