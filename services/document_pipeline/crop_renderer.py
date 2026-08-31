"""원본 PDF와 Docling provenance bbox로 응답용 PNG crop을 만든다."""

from __future__ import annotations

from typing import Any


class PictureCropError(ValueError):
    pass


def _first_bbox(src_locator: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    for provenance in src_locator.get("prov") or []:
        bbox = provenance.get("bbox") if isinstance(provenance, dict) else None
        page_no = provenance.get("page_no") if isinstance(provenance, dict) else None
        if isinstance(bbox, dict) and isinstance(page_no, int) and page_no >= 1:
            return page_no, bbox
    raise PictureCropError("Picture block에 유효한 page/bbox provenance가 없습니다.")


def render_picture_crop(pdf_bytes: bytes, src_locator: dict[str, Any]) -> bytes:
    """Docling point 좌표를 PyMuPDF 좌표로 변환해 2배율 PNG를 반환한다."""

    import pymupdf as fitz

    page_no, bbox = _first_bbox(src_locator)
    try:
        left = float(bbox["l"])
        right = float(bbox["r"])
        top = float(bbox["t"])
        bottom = float(bbox["b"])
    except (KeyError, TypeError, ValueError) as exc:
        raise PictureCropError("Picture bbox 좌표가 올바르지 않습니다.") from exc

    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        if page_no > document.page_count:
            raise PictureCropError("Picture page가 원본 PDF 범위를 벗어났습니다.")
        page = document.load_page(page_no - 1)
        if bbox.get("coord_origin") == "BOTTOMLEFT":
            y0, y1 = page.rect.height - top, page.rect.height - bottom
        elif bbox.get("coord_origin") == "TOPLEFT":
            y0, y1 = top, bottom
        else:
            raise PictureCropError("지원하지 않는 Picture bbox 좌표 원점입니다.")

        padding = 4.0
        crop = fitz.Rect(
            max(page.rect.x0, left - padding),
            max(page.rect.y0, y0 - padding),
            min(page.rect.x1, right + padding),
            min(page.rect.y1, y1 + padding),
        )
        if crop.is_empty or crop.is_infinite or crop.width <= 1 or crop.height <= 1:
            raise PictureCropError("Picture crop 영역이 비어 있습니다.")
        return page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=crop, alpha=False).tobytes("png")


__all__ = ["PictureCropError", "render_picture_crop"]
