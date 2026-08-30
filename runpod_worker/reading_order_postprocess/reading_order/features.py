"""Geometry features shared by conservative reading-order detectors."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any


_SUPPORTED_ORIGINS = frozenset({"BOTTOMLEFT", "TOPLEFT"})
# PDF renderer output can drift very slightly outside its declared page box.
# Accept at most 0.5 page units (about 0.18 mm at 72 dpi) or 0.01% of a page.
_RELATIVE_RANGE_TOLERANCE = 1e-4
_ABSOLUTE_RANGE_TOLERANCE = 0.5
_RELATIVE_ORDER_TOLERANCE = 1e-9


class GeometryContractError(ValueError):
    """An input record cannot be compared safely using page geometry."""

    def __init__(self, message: str, *, code: str, record_ref: str) -> None:
        super().__init__(message)
        self.code = code
        self.record_ref = record_ref


def _record_name(record: Mapping[str, Any]) -> str:
    return str(record.get("self_ref", "<unknown record>"))


def _finite_float(value: Any, *, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a finite number, got {value!r}")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a finite number, got {value!r}") from exc
    if not math.isfinite(result):
        raise ValueError(f"{field} must be a finite number, got {value!r}")
    return result


def _page_number(value: Any, *, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a positive integer, got {value!r}")
    if isinstance(value, int):
        result = value
    elif isinstance(value, str) and value.strip().isdigit():
        result = int(value.strip())
    else:
        raise ValueError(f"{field} must be a positive integer, got {value!r}")
    if result < 1:
        raise ValueError(f"{field} must be a positive integer, got {value!r}")
    return result


def _page_size(document: Mapping[str, Any], page_no: int) -> tuple[float, float]:
    pages = document.get("pages")
    if not isinstance(pages, Mapping):
        raise ValueError("document.pages must be an object")
    page = pages.get(str(page_no), pages.get(page_no))
    if not isinstance(page, Mapping):
        raise ValueError(f"Missing page metadata for page {page_no}")
    size = page.get("size")
    if not isinstance(size, Mapping):
        raise ValueError(f"Missing page size for page {page_no}")
    width = _finite_float(size.get("width"), field=f"page {page_no} width")
    height = _finite_float(size.get("height"), field=f"page {page_no} height")
    if width <= 0 or height <= 0:
        raise ValueError(
            f"Page {page_no} size must be positive, got width={width}, height={height}"
        )
    return width, height


def _clamp_to_page(value: float, *, limit: float) -> float:
    return min(max(value, 0.0), limit)


def _normalized_bbox(
    bbox: Mapping[str, Any],
    *,
    page_no: int,
    width: float,
    height: float,
    field: str,
) -> tuple[float, float, float, float, str, tuple[str, ...]]:
    origin = bbox.get("coord_origin")
    if origin is None:
        raise ValueError(
            f"{field}.coord_origin is required; refusing to assume BOTTOMLEFT"
        )
    if origin not in _SUPPORTED_ORIGINS:
        raise ValueError(f"Unsupported {field}.coord_origin: {origin!r}")

    left_raw = _finite_float(bbox.get("l"), field=f"{field}.l")
    right_raw = _finite_float(bbox.get("r"), field=f"{field}.r")
    top_raw = _finite_float(bbox.get("t"), field=f"{field}.t")
    bottom_raw = _finite_float(bbox.get("b"), field=f"{field}.b")
    x_range_tolerance = max(
        width * _RELATIVE_RANGE_TOLERANCE, _ABSOLUTE_RANGE_TOLERANCE
    )
    y_range_tolerance = max(
        height * _RELATIVE_RANGE_TOLERANCE, _ABSOLUTE_RANGE_TOLERANCE
    )
    x_order_tolerance = max(width * _RELATIVE_ORDER_TOLERANCE, 1e-9)
    y_order_tolerance = max(height * _RELATIVE_ORDER_TOLERANCE, 1e-9)

    if left_raw < -x_range_tolerance or right_raw > width + x_range_tolerance:
        raise ValueError(
            f"{field} horizontal coordinates are outside page {page_no}: "
            f"l={left_raw}, r={right_raw}, width={width}"
        )
    if top_raw < -y_range_tolerance or top_raw > height + y_range_tolerance:
        raise ValueError(
            f"{field}.t is outside page {page_no}: t={top_raw}, height={height}"
        )
    if bottom_raw < -y_range_tolerance or bottom_raw > height + y_range_tolerance:
        raise ValueError(
            f"{field}.b is outside page {page_no}: b={bottom_raw}, height={height}"
        )
    if left_raw > right_raw + x_order_tolerance:
        raise ValueError(f"{field} has l > r: l={left_raw}, r={right_raw}")

    was_clamped = not (
        0 <= left_raw <= width
        and 0 <= right_raw <= width
        and 0 <= top_raw <= height
        and 0 <= bottom_raw <= height
    )
    left_raw = _clamp_to_page(left_raw, limit=width)
    right_raw = _clamp_to_page(right_raw, limit=width)
    top_raw = _clamp_to_page(top_raw, limit=height)
    bottom_raw = _clamp_to_page(bottom_raw, limit=height)
    if left_raw > right_raw:
        midpoint = (left_raw + right_raw) / 2
        left_raw = right_raw = midpoint

    if origin == "BOTTOMLEFT":
        if bottom_raw > top_raw + y_order_tolerance:
            raise ValueError(
                f"{field} BOTTOMLEFT coordinates require b <= t: "
                f"b={bottom_raw}, t={top_raw}"
            )
        if bottom_raw > top_raw:
            midpoint = (bottom_raw + top_raw) / 2
            bottom_raw = top_raw = midpoint
        top_norm = top_raw / height
        bottom_norm = bottom_raw / height
    else:
        if top_raw > bottom_raw + y_order_tolerance:
            raise ValueError(
                f"{field} TOPLEFT coordinates require t <= b: "
                f"t={top_raw}, b={bottom_raw}"
            )
        if top_raw > bottom_raw:
            midpoint = (top_raw + bottom_raw) / 2
            top_raw = bottom_raw = midpoint
        top_norm = (height - top_raw) / height
        bottom_norm = (height - bottom_raw) / height

    flags = ("bbox_clamped_to_page",) if was_clamped else ()
    return left_raw / width, right_raw / width, top_norm, bottom_norm, origin, flags


def _record_geometry(
    document: Mapping[str, Any], record: Mapping[str, Any]
) -> tuple[
    int,
    dict[str, Any],
    str,
    int,
    float,
    float,
    float,
    float,
    tuple[str, ...],
]:
    name = _record_name(record)
    page_numbers = record.get("page_numbers")
    if not isinstance(page_numbers, Sequence) or isinstance(
        page_numbers, (str, bytes)
    ):
        raise ValueError(f"{name}: page_numbers must be a non-empty array")
    if not page_numbers:
        raise ValueError(f"{name}: page_numbers must not be empty")
    declared_pages = {
        _page_number(value, field=f"{name}.page_numbers") for value in page_numbers
    }
    if len(declared_pages) != 1:
        raise GeometryContractError(
            f"{name}: cross-page records are not safe for page-local ordering: "
            f"{sorted(declared_pages)}",
            code="cross_page_record",
            record_ref=name,
        )
    page_no = next(iter(declared_pages))
    width, height = _page_size(document, page_no)

    provenances = record.get("provenances")
    if not isinstance(provenances, Sequence) or isinstance(
        provenances, (str, bytes)
    ):
        raise ValueError(f"{name}: provenances must be a non-empty array")
    if not provenances:
        raise ValueError(f"{name}: provenances must not be empty")

    normalized: list[
        tuple[float, float, float, float, str, tuple[str, ...]]
    ] = []
    for index, provenance in enumerate(provenances):
        field = f"{name}.provenances[{index}]"
        if not isinstance(provenance, Mapping):
            raise ValueError(f"{field} must be an object")
        provenance_page = _page_number(
            provenance.get("page_no"), field=f"{field}.page_no"
        )
        if provenance_page != page_no:
            raise ValueError(
                f"{name}: provenance page {provenance_page} does not match "
                f"declared page {page_no}"
            )
        bbox = provenance.get("bbox")
        if not isinstance(bbox, Mapping):
            raise ValueError(f"{field}.bbox must be an object")
        normalized.append(
            _normalized_bbox(
                bbox,
                page_no=page_no,
                width=width,
                height=height,
                field=f"{field}.bbox",
            )
        )

    left = min(value[0] for value in normalized)
    right = max(value[1] for value in normalized)
    top = max(value[2] for value in normalized)
    bottom = min(value[3] for value in normalized)

    if len(provenances) == 1:
        output_bbox = dict(provenances[0]["bbox"])
        output_origin = normalized[0][4]
    else:
        output_bbox = {
            "l": left * width,
            "r": right * width,
            "t": top * height,
            "b": bottom * height,
            "coord_origin": "BOTTOMLEFT",
        }
        output_origin = "BOTTOMLEFT"

    flags = {flag for value in normalized for flag in value[5]}
    if len(provenances) > 1:
        flags.add("same_page_provenances_aggregated")
    return (
        page_no,
        output_bbox,
        output_origin,
        len(provenances),
        left,
        right,
        top,
        bottom,
        tuple(sorted(flags)),
    )


def add_spatial_features(
    document: dict[str, Any],
    records: list[dict[str, Any]],
    *,
    geometry_issues: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return record copies with validated, page-normalized geometry.

    Output coordinates use a bottom-left-like convention where larger
    ``top_norm``/``bottom_norm`` values are visually higher. Every provenance
    must explicitly declare ``BOTTOMLEFT`` or ``TOPLEFT``; missing origins are
    rejected instead of being silently interpreted. Same-page provenance
    fragments are aggregated. Cross-page records are excluded from page-local
    ordering rather than aborting the entire document; callers can supply
    ``geometry_issues`` when they need an audit trail.
    """

    enriched: list[dict[str, Any]] = []
    for record in records:
        try:
            (
                page_no,
                bbox,
                coord_origin,
                provenance_count,
                left,
                right,
                top,
                bottom,
                geometry_flags,
            ) = _record_geometry(document, record)
        except GeometryContractError as exc:
            if geometry_issues is not None:
                geometry_issues.append(
                    {
                        "self_ref": exc.record_ref,
                        "code": exc.code,
                        "message": str(exc),
                        "auto_reorder_eligible": False,
                    }
                )
            continue

        item = dict(record)
        item.update(
            {
                "page_no": page_no,
                "order_index": int(record["visual_order"]),
                "bbox": bbox,
                "coord_origin": coord_origin,
                "provenance_count": provenance_count,
                "geometry_flags": list(geometry_flags),
                "left_norm": left,
                "right_norm": right,
                "top_norm": top,
                "bottom_norm": bottom,
                "center_x_norm": (left + right) / 2,
                "width_norm": right - left,
                "height_norm": top - bottom,
                "column_half": "left" if (left + right) / 2 < 0.5 else "right",
            }
        )
        enriched.append(item)
    return enriched
