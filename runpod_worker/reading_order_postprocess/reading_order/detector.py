"""Conservative, non-mutating reading-order candidate detection."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import re
from typing import Any

from .features import add_spatial_features
from .semantic_scope import filter_ordering_records


LOCAL_FLOW_LABELS = frozenset({"text", "paragraph", "list_item", "caption"})
_ENUMERATED_MARKERS = (
    ("bracket", re.compile(r"^\[(\d{1,4})\]$")),
    ("parenthesized", re.compile(r"^\((\d{1,4})\)$")),
    ("decimal", re.compile(r"^(\d{1,4})[.)]$")),
)
_STANDALONE_LIST_MARKERS = frozenset({
    "-", "–", "—", "*", "·", "•", "◦", "▪", "■", "●", "○", "‣", "⁃", "∙",
    "¦", "Ÿ",  # common OCR-rendered bullet/marker artifacts
})


def _text_quality_flags(record: dict[str, Any]) -> list[str]:
    """Return cheap extraction-risk flags without trying to repair text."""

    text = record.get("text")
    if not isinstance(text, str) or not text.strip():
        return ["empty_text"]
    flags: list[str] = []
    if "�" in text:
        flags.append("replacement_character")
    if text.strip() in _STANDALONE_LIST_MARKERS:
        flags.append("standalone_list_marker")
    width = record.get("width_norm")
    height = record.get("height_norm")
    if (
        isinstance(width, (int, float))
        and isinstance(height, (int, float))
        and 0 < width <= 0.03
        and height >= 0.05
        and height / width >= 2.0
    ):
        # A very narrow, tall text box is commonly text rotated by 90°.
        # The local vertical-inversion rule assumes horizontal text, so its
        # top/bottom comparison is not executable evidence in this geometry.
        flags.append("suspected_rotated_text")
    if any(
        (ord(char) < 32 and char not in "\t\n\r")
        or 0x7F <= ord(char) <= 0x9F
        for char in text
    ):
        flags.append("control_character")
    return flags


@dataclass(frozen=True)
class DetectorConfig:
    """Explicit experimental thresholds for candidate detection."""

    min_vertical_gap: float = 0.005
    max_vertical_gap: float = 0.08
    review_max_vertical_gap: float = 0.18
    left_alignment_tolerance: float = 0.035
    heading_table_min_gap: float = -0.015
    heading_table_max_gap: float = 0.09
    heading_table_max_horizontal_gap: float = 0.04
    premature_vertical_margin: float = 0.025
    continuation_max_horizontal_gap: float = 0.03
    continuation_min_vertical_overlap: float = 0.8
    continuation_min_size_similarity: float = 0.75
    continuation_min_order_separation: int = 10
    split_group_vertical_tolerance: float = 0.005
    split_group_max_horizontal_gap: float = 0.05
    section_block_max_horizontal_gap: float = 0.08
    section_block_min_vertical_overlap: float = 0.5
    section_block_max_member_count: int = 8
    key_value_row_tolerance: float = 0.005
    list_column_left_tolerance: float = 0.05


def _proposal(*records: dict[str, Any]) -> list[str]:
    return [record["self_ref"] for record in records]


def _bbox_intersects_vertical_corridor(
    sibling: dict[str, Any],
    first: dict[str, Any],
    second: dict[str, Any],
) -> bool:
    """Detect a large sibling crossing the candidate pair's bbox corridor."""

    first_center = (first["top_norm"] + first["bottom_norm"]) / 2
    second_center = (second["top_norm"] + second["bottom_norm"]) / 2
    lower, upper = (
        (first, second) if first_center <= second_center else (second, first)
    )
    # If the candidate boxes overlap vertically, there is no open corridor.
    # The existing top-coordinate inversion signal can still be valid, but a
    # broad neighboring bbox should not be treated as an intervening object.
    if lower["top_norm"] >= upper["bottom_norm"]:
        return False
    corridor_bottom = lower["top_norm"]
    corridor_top = upper["bottom_norm"]
    corridor_left = min(first["left_norm"], second["left_norm"])
    corridor_right = max(first["right_norm"], second["right_norm"])
    y_overlap = max(
        0.0,
        min(sibling["top_norm"], corridor_top)
        - max(sibling["bottom_norm"], corridor_bottom),
    )
    x_overlap = max(
        0.0,
        min(sibling["right_norm"], corridor_right)
        - max(sibling["left_norm"], corridor_left),
    )
    return y_overlap > 1e-6 and x_overlap > 1e-6


def _enumerated_marker(marker: Any) -> tuple[str, int] | None:
    """Parse only explicit list markers, never years or bare body numbers."""

    if not isinstance(marker, str):
        return None
    value = marker.strip()
    for style, pattern in _ENUMERATED_MARKERS:
        match = pattern.fullmatch(value)
        if match:
            return style, int(match.group(1))
    return None


def _enumerated_sequence_inversions(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Find complete consecutive numeric runs stored out of marker order.

    Docling already exposes ``list_item``, ``enumerated`` and ``marker`` for
    many lists, but the body order can still disagree with markers.  Marker
    order is review-only corroboration: bullets have no intrinsic ordinal and
    years, addresses and arbitrary numbers are intentionally excluded.
    """

    grouped: dict[tuple[int, str, str], list[tuple[dict[str, Any], int]]] = (
        defaultdict(list)
    )
    for record in records:
        parent_ref = record.get("parent_ref")
        parsed = _enumerated_marker(record.get("marker"))
        if (
            record.get("label") != "list_item"
            or record.get("enumerated") is not True
            or not isinstance(parent_ref, str)
            or parsed is None
        ):
            continue
        style, number = parsed
        grouped[(record["page_no"], parent_ref, style)].append((record, number))

    candidates: list[dict[str, Any]] = []
    for (page_no, parent_ref, style), members in grouped.items():
        members.sort(key=lambda pair: pair[0]["order_index"])
        numbers = [number for _, number in members]
        if len(numbers) < 2 or len(set(numbers)) != len(numbers):
            continue
        expected = list(range(min(numbers), max(numbers) + 1))
        if len(expected) != len(numbers) or numbers == expected:
            continue
        proposed = sorted(members, key=lambda pair: pair[1])
        candidates.append(
            {
                "page_no": page_no,
                "type": "ENUMERATED_SEQUENCE_INVERSION",
                "confidence": "MEDIUM",
                "decision": "REVIEW_REQUIRED",
                "operation": "REORDER_SUBSET",
                "reason": (
                    "The same list parent contains a complete consecutive "
                    "numeric marker run, but body order is not ascending."
                ),
                "parent_ref": parent_ref,
                "observed_order": [record["self_ref"] for record, _ in members],
                "proposed_order": [record["self_ref"] for record, _ in proposed],
                "metrics": {
                    "marker_style": style,
                    "observed_numbers": numbers,
                    "proposed_numbers": expected,
                    "member_count": len(members),
                    "auto_reorder_eligible": False,
                },
            }
        )
    return candidates


def _vertical_group_inversions(
    records: list[dict[str, Any]], config: DetectorConfig
) -> list[dict[str, Any]]:
    """Find adjacent siblings whose order contradicts a small vertical offset."""

    candidates: list[dict[str, Any]] = []
    groups: dict[tuple[int, str | None], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[(record["page_no"], record.get("parent_ref"))].append(record)

    for (page_no, parent_ref), siblings in groups.items():
        # A missing parent is not evidence of a shared structural container.
        # Keep body/unknown elements out of the local-sibling auto candidate
        # path; a later explicit review can still handle them.
        if not isinstance(parent_ref, str):
            continue
        siblings.sort(key=lambda item: item["order_index"])
        for current, following in zip(siblings, siblings[1:]):
            if (
                current["label"] not in LOCAL_FLOW_LABELS
                or following["label"] not in LOCAL_FLOW_LABELS
            ):
                continue
            upward_gap = following["top_norm"] - current["top_norm"]
            if (
                abs(following["left_norm"] - current["left_norm"])
                <= config.left_alignment_tolerance
                and config.min_vertical_gap
                <= upward_gap
                <= max(config.max_vertical_gap, config.review_max_vertical_gap)
            ):
                lower = min(current["top_norm"], following["top_norm"])
                upper = max(current["top_norm"], following["top_norm"])
                visual_intervening = sum(
                    1
                    for sibling in siblings
                    if sibling["self_ref"] not in {
                        current["self_ref"],
                        following["self_ref"],
                    }
                    and (
                        lower
                        < (sibling["top_norm"] + sibling["bottom_norm"]) / 2
                        < upper
                        or _bbox_intersects_vertical_corridor(
                            sibling, current, following
                        )
                    )
                )
                complex_geometry = (
                    current.get("provenance_count", 1) > 1
                    or following.get("provenance_count", 1) > 1
                    or bool(current.get("geometry_flags"))
                    or bool(following.get("geometry_flags"))
                )
                text_quality_flags = sorted(
                    set(_text_quality_flags(current) + _text_quality_flags(following))
                )
                long_gap_relation = upward_gap > config.max_vertical_gap
                # A wider gap can expose missed paragraph relations, but it is
                # not sufficient evidence for an executable swap.  Limit this
                # recall-only band to simple body paragraphs and fail closed
                # when geometry or an intervening sibling is ambiguous.
                if long_gap_relation and (
                    current["label"] not in {"text", "paragraph"}
                    or following["label"] not in {"text", "paragraph"}
                    or visual_intervening > 0
                    or complex_geometry
                    or text_quality_flags
                ):
                    continue
                candidates.append(
                    {
                        "page_no": page_no,
                        "type": (
                            "LONG_GAP_LOCAL_VERTICAL_RELATION"
                            if long_gap_relation
                            else "LOCAL_VERTICAL_INVERSION"
                        ),
                        "confidence": "MEDIUM" if long_gap_relation else "HIGH",
                        "decision": (
                            "AUTO_REORDER_ELIGIBLE"
                            if (
                                not long_gap_relation
                                and
                                visual_intervening == 0
                                and not complex_geometry
                                and not text_quality_flags
                            )
                            else "REVIEW_REQUIRED"
                        ),
                        "operation": "RELATION_ONLY" if long_gap_relation else "SWAP_ADJACENT",
                        "relation": "BEFORE" if long_gap_relation else None,
                        "reason": (
                            "같은 부모·좌측 정렬의 인접 본문이 자동 기준보다 넓은 간격에서 역전되어 검토 관계로 기록함"
                            if long_gap_relation
                            else "같은 부모·유사한 좌측 정렬의 인접 요소가 아래 요소부터 기록됨"
                        ),
                        "parent_ref": parent_ref,
                        "observed_order": _proposal(current, following),
                        "proposed_order": _proposal(following, current),
                        "metrics": {
                            "left_delta_norm": round(
                                abs(following["left_norm"] - current["left_norm"]), 6
                            ),
                            "upward_gap_norm": round(upward_gap, 6),
                            "visual_intervening_sibling_count": visual_intervening,
                            "complex_geometry": complex_geometry,
                            "text_quality_flags": text_quality_flags,
                            "auto_gap_threshold_exceeded": long_gap_relation,
                            "auto_reorder_eligible": not long_gap_relation,
                        },
                    }
                )
    return candidates


def _section_table_candidates(
    records: list[dict[str, Any]], config: DetectorConfig
) -> list[dict[str, Any]]:
    """Find headings crossing their visually adjacent table/list boundary."""

    candidates: list[dict[str, Any]] = []
    by_page: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_page[record["page_no"]].append(record)

    for page_no, page_records in by_page.items():
        tables = [item for item in page_records if item["label"] == "table"]
        headings = [
            item
            for item in page_records
            if item["label"] in {"section_header", "title"}
        ]
        for table in tables:
            nearby = []
            for heading in headings:
                if heading["column_half"] != table["column_half"]:
                    continue
                horizontal_gap = max(
                    heading["left_norm"] - table["right_norm"],
                    table["left_norm"] - heading["right_norm"],
                    0.0,
                )
                if horizontal_gap > config.heading_table_max_horizontal_gap:
                    continue
                gap = heading["top_norm"] - table["top_norm"]
                if config.heading_table_min_gap <= gap <= config.heading_table_max_gap:
                    nearby.append((abs(gap), horizontal_gap, heading))
            if not nearby:
                continue
            _, horizontal_gap, heading = min(
                nearby, key=lambda pair: (pair[0], pair[1])
            )

            if heading["order_index"] > table["order_index"]:
                candidates.append(
                    {
                        "page_no": page_no,
                        "type": "TABLE_HEADING_AFTER_TABLE",
                        "confidence": "HIGH",
                        "decision": "REVIEW_REQUIRED",
                        "operation": "REORDER_SUBSET",
                        "reason": "표 바로 위 제목이 body 순서에서는 표 뒤에 위치함",
                        "observed_order": _proposal(table, heading),
                        "proposed_order": _proposal(heading, table),
                        "metrics": {
                            "heading_table_gap_norm": round(
                                heading["top_norm"] - table["top_norm"], 6
                            ),
                            "heading_table_horizontal_gap_norm": round(
                                horizontal_gap, 6
                            ),
                        },
                    }
                )
                continue

            intervening = [
                item
                for item in page_records
                if heading["order_index"] < item["order_index"] < table["order_index"]
                and item["column_half"] == heading["column_half"]
                and item["bottom_norm"]
                > heading["top_norm"] + config.premature_vertical_margin
                and item["label"] not in {"section_header", "title", "table"}
            ]
            if intervening:
                intervening.sort(key=lambda item: (-item["top_norm"], item["left_norm"]))
                candidates.append(
                    {
                        "page_no": page_no,
                        "type": "PREMATURE_TABLE_HEADING",
                        "confidence": "MEDIUM",
                        "decision": "REVIEW_REQUIRED",
                        "operation": "REORDER_SUBSET",
                        "reason": "표 제목이 같은 열의 시각적으로 더 위인 본문보다 먼저 기록됨",
                        "observed_order": _proposal(heading, *intervening, table),
                        "proposed_order": _proposal(*intervening, heading, table),
                        "metrics": {"intervening_count": len(intervening)},
                    }
                )
    return candidates


def _vertical_overlap_ratio(first: dict[str, Any], second: dict[str, Any]) -> float:
    overlap = max(
        0.0,
        min(first["top_norm"], second["top_norm"])
        - max(first["bottom_norm"], second["bottom_norm"]),
    )
    return overlap / max(min(first["height_norm"], second["height_norm"]), 1e-9)


def _size_similarity(first: dict[str, Any], second: dict[str, Any]) -> float:
    width_similarity = min(first["width_norm"], second["width_norm"]) / max(
        first["width_norm"], second["width_norm"], 1e-9
    )
    height_similarity = min(first["height_norm"], second["height_norm"]) / max(
        first["height_norm"], second["height_norm"], 1e-9
    )
    return min(width_similarity, height_similarity)


def _horizontal_overlap_ratio(first: dict[str, Any], second: dict[str, Any]) -> float:
    overlap = max(
        0.0,
        min(first["right_norm"], second["right_norm"])
        - max(first["left_norm"], second["left_norm"]),
    )
    return overlap / max(min(first["width_norm"], second["width_norm"]), 1e-9)


def _downward_continuation_alternative(
    first: dict[str, Any], records: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Return a plausible next block below ``first`` in the same text column."""

    alternatives = []
    for item in records:
        if (
            item["self_ref"] == first["self_ref"]
            or item["page_no"] != first["page_no"]
            or item.get("parent_ref") != first.get("parent_ref")
            or item["label"] not in {"text", "paragraph"}
            or item["order_index"] <= first["order_index"]
        ):
            continue
        vertical_gap = first["bottom_norm"] - item["top_norm"]
        overlap_ratio = _horizontal_overlap_ratio(first, item)
        if (
            0 <= vertical_gap <= first["height_norm"] * 1.5
            and overlap_ratio >= 0.5
        ):
            alternatives.append((vertical_gap, -overlap_ratio, item))
    return min(alternatives, key=lambda value: (value[0], value[1]))[2] if alternatives else None


def _interrupted_column_continuations(
    records: list[dict[str, Any]], config: DetectorConfig
) -> list[dict[str, Any]]:
    """Find aligned peer text blocks separated by a column-major body traversal."""

    terminal_marks = (".", "!", "?", "。", "！", "？")
    candidates: list[dict[str, Any]] = []
    text_records = [
        item for item in records if item["label"] in {"text", "paragraph"}
    ]
    for first in text_records:
        text = (first.get("text") or "").rstrip()
        if not text or text.endswith(terminal_marks):
            continue
        if _downward_continuation_alternative(first, text_records) is not None:
            continue
        matches = []
        for second in text_records:
            if (
                second["page_no"] != first["page_no"]
                or second.get("parent_ref") != first.get("parent_ref")
                or second["order_index"] - first["order_index"]
                < config.continuation_min_order_separation
            ):
                continue
            horizontal_gap = second["left_norm"] - first["right_norm"]
            overlap_ratio = _vertical_overlap_ratio(first, second)
            size_similarity = _size_similarity(first, second)
            if (
                0 <= horizontal_gap <= config.continuation_max_horizontal_gap
                and overlap_ratio >= config.continuation_min_vertical_overlap
                and size_similarity >= config.continuation_min_size_similarity
            ):
                matches.append(
                    (horizontal_gap, -overlap_ratio, -size_similarity, second)
                )
        if not matches:
            continue
        horizontal_gap, neg_overlap, neg_similarity, second = min(matches)
        candidates.append(
            {
                "page_no": first["page_no"],
                "type": "INTERRUPTED_COLUMN_CONTINUATION",
                "confidence": "HIGH",
                "reason": "같은 행의 유사한 본문 블록이 짧은 가로 간격으로 이어지지만 body 순회가 다른 영역으로 이탈함",
                # Cross-column adjacency can move many intervening body items.
                # Keep this detector review-only; the stricter continuation
                # analyzer remains the place where any future promotion is
                # evaluated.
                "decision": "REVIEW_REQUIRED",
                "operation": "MOVE_AFTER",
                "parent_ref": first.get("parent_ref"),
                "observed_order": _proposal(first, second),
                "proposed_order": _proposal(first, second),
                "metrics": {
                    "horizontal_gap_norm": round(horizontal_gap, 6),
                    "vertical_overlap_ratio": round(-neg_overlap, 6),
                    "size_similarity": round(-neg_similarity, 6),
                    "order_separation": second["order_index"] - first["order_index"],
                    "downward_alternative_found": False,
                },
            }
        )
    return candidates


def _axis_gap(
    first_start: float, first_end: float, second_start: float, second_end: float
) -> float:
    return max(0.0, max(first_start, second_start) - min(first_end, second_end))


def _heading_led_blocks(
    records: list[dict[str, Any]], config: DetectorConfig
) -> list[dict[str, Any]]:
    """Build small top-level heading/body blocks without using document text."""

    blocks: list[dict[str, Any]] = []
    by_page: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_page[record["page_no"]].append(record)

    body_labels = {"text", "paragraph", "list_item", "caption"}
    for page_no, page_records in by_page.items():
        page_records.sort(key=lambda item: item["order_index"])
        for index, heading in enumerate(page_records):
            if (
                heading["label"] not in {"section_header", "title"}
                or heading.get("parent_ref") != "#/body"
            ):
                continue
            members = [heading]
            for following in page_records[index + 1 :]:
                if following["label"] in {"section_header", "title"}:
                    break
                if (
                    following.get("parent_ref") != heading.get("parent_ref")
                    or following["label"] not in body_labels
                ):
                    break
                members.append(following)
                if len(members) >= config.section_block_max_member_count:
                    break
            if len(members) < 2:
                continue
            blocks.append(
                {
                    "page_no": page_no,
                    "parent_ref": heading.get("parent_ref"),
                    "heading_ref": heading["self_ref"],
                    "members": members,
                    "first_order": members[0]["order_index"],
                    "last_order": members[-1]["order_index"],
                    "left_norm": min(item["left_norm"] for item in members),
                    "right_norm": max(item["right_norm"] for item in members),
                    "top_norm": max(item["top_norm"] for item in members),
                    "bottom_norm": min(item["bottom_norm"] for item in members),
                }
            )
    return blocks


def _horizontal_section_block_inversions(
    records: list[dict[str, Any]], config: DetectorConfig
) -> list[dict[str, Any]]:
    """Find adjacent independent sections traversed right-to-left in one row.

    This is deliberately review-only.  Vertical overlap distinguishes a true
    same-row inversion from the normal transition from a right column to the
    next row on the left.
    """

    candidates: list[dict[str, Any]] = []
    blocks = _heading_led_blocks(records, config)
    groups: dict[tuple[int, str | None], list[dict[str, Any]]] = defaultdict(list)
    for block in blocks:
        groups[(block["page_no"], block["parent_ref"])].append(block)

    for (page_no, parent_ref), page_blocks in groups.items():
        page_blocks.sort(key=lambda item: item["first_order"])
        for current, following in zip(page_blocks, page_blocks[1:]):
            if following["first_order"] != current["last_order"] + 1:
                continue
            horizontal_gap = current["left_norm"] - following["right_norm"]
            if not 0 <= horizontal_gap <= config.section_block_max_horizontal_gap:
                continue
            overlap = max(
                0.0,
                min(current["top_norm"], following["top_norm"])
                - max(current["bottom_norm"], following["bottom_norm"]),
            )
            current_height = current["top_norm"] - current["bottom_norm"]
            following_height = following["top_norm"] - following["bottom_norm"]
            overlap_ratio = overlap / max(min(current_height, following_height), 1e-9)
            if overlap_ratio < config.section_block_min_vertical_overlap:
                continue
            candidates.append(
                {
                    "page_no": page_no,
                    "type": "HORIZONTAL_SECTION_BLOCK_INVERSION",
                    "confidence": "MEDIUM",
                    "decision": "REVIEW_REQUIRED",
                    "operation": "SWAP_BLOCKS",
                    "reason": (
                        "Adjacent heading-led blocks occupy the same visual row, "
                        "but body order traverses the right block before the left block."
                    ),
                    "parent_ref": parent_ref,
                    "source_heading_ref": current["heading_ref"],
                    "target_heading_ref": following["heading_ref"],
                    "observed_order": [
                        item["self_ref"]
                        for block in (current, following)
                        for item in block["members"]
                    ],
                    "proposed_order": [
                        item["self_ref"]
                        for block in (following, current)
                        for item in block["members"]
                    ],
                    "metrics": {
                        "horizontal_gap_norm": round(horizontal_gap, 6),
                        "vertical_overlap_ratio": round(overlap_ratio, 6),
                        "source_member_count": len(current["members"]),
                        "target_member_count": len(following["members"]),
                    },
                }
            )
    return candidates


def _row_major_order(
    members: list[dict[str, Any]], tolerance: float
) -> list[dict[str, Any]]:
    rows: list[list[dict[str, Any]]] = []
    for member in sorted(members, key=lambda item: -item["top_norm"]):
        if rows and abs(rows[-1][0]["top_norm"] - member["top_norm"]) <= tolerance:
            rows[-1].append(member)
        else:
            rows.append([member])
    return [
        member
        for row in rows
        for member in sorted(row, key=lambda item: item["left_norm"])
    ]


def _column_major_order(
    members: list[dict[str, Any]], tolerance: float
) -> tuple[list[dict[str, Any]], int]:
    columns: list[list[dict[str, Any]]] = []
    for member in sorted(members, key=lambda item: item["left_norm"]):
        if columns:
            mean_left = sum(item["left_norm"] for item in columns[-1]) / len(columns[-1])
        else:
            mean_left = 0.0
        if columns and abs(mean_left - member["left_norm"]) <= tolerance:
            columns[-1].append(member)
        else:
            columns.append([member])
    ordered = [
        member
        for column in columns
        for member in sorted(column, key=lambda item: -item["top_norm"])
    ]
    return ordered, len(columns)


def _semantic_group_reorders(
    document: dict[str, Any],
    records: list[dict[str, Any]],
    local_candidates: list[dict[str, Any]],
    config: DetectorConfig,
) -> tuple[list[dict[str, Any]], set[str]]:
    """Replace unsafe pair swaps with one review-only semantic group proposal."""

    triggered_parents = {
        item.get("parent_ref")
        for item in local_candidates
        if item.get("metrics", {}).get("visual_intervening_sibling_count", 0) > 0
        and isinstance(item.get("parent_ref"), str)
    }
    groups = {
        f"#/groups/{index}": group
        for index, group in enumerate(document.get("groups", []))
    }
    candidates: list[dict[str, Any]] = []
    replaced_parents: set[str] = set()
    for parent_ref in sorted(triggered_parents):
        group = groups.get(parent_ref)
        if not group or group.get("label") not in {"key_value_area", "list"}:
            continue
        members = sorted(
            [item for item in records if item.get("parent_ref") == parent_ref],
            key=lambda item: item["order_index"],
        )
        if len(members) < 3 or len({item["page_no"] for item in members}) != 1:
            continue
        if group.get("label") == "key_value_area":
            if any(item["label"] not in {"text", "paragraph"} for item in members):
                continue
            proposed = _row_major_order(members, config.key_value_row_tolerance)
            column_count = None
            candidate_type = "KEY_VALUE_GROUP_REORDER"
        else:
            if any(item["label"] != "list_item" for item in members):
                continue
            proposed, column_count = _column_major_order(
                members, config.list_column_left_tolerance
            )
            candidate_type = "LIST_GROUP_REORDER"
        observed_refs = _proposal(*members)
        proposed_refs = _proposal(*proposed)
        if observed_refs == proposed_refs:
            continue
        candidates.append(
            {
                "page_no": members[0]["page_no"],
                "type": candidate_type,
                "confidence": "MEDIUM",
                "decision": "REVIEW_REQUIRED",
                "operation": "REORDER_SUBSET",
                "reason": (
                    "A semantic group contains a non-local visual inversion; "
                    "one full-group geometric order is safer than a partial pair swap."
                ),
                "parent_ref": parent_ref,
                "observed_order": observed_refs,
                "proposed_order": proposed_refs,
                "metrics": {
                    "member_count": len(members),
                    "column_count": column_count,
                    "nonlocal_trigger_count": sum(
                        item.get("parent_ref") == parent_ref
                        and item.get("metrics", {}).get(
                            "visual_intervening_sibling_count", 0
                        )
                        > 0
                        for item in local_candidates
                    ),
                },
            }
        )
        replaced_parents.add(parent_ref)
    return candidates, replaced_parents


def _split_group_section_candidates(
    document: dict[str, Any],
    records: list[dict[str, Any]],
    config: DetectorConfig,
) -> list[dict[str, Any]]:
    """Find a spatially split group whose upper tail belongs to a nearby section."""

    by_ref = {item["self_ref"]: item for item in records}
    body = document.get("body")
    if not isinstance(body, dict):
        return []
    groups = {
        f"#/groups/{index}": group
        for index, group in enumerate(document.get("groups", []))
    }
    last_heading_by_page: dict[int, dict[str, Any]] = {}
    associations = []
    for child in body.get("children", []):
        ref = child.get("$ref")
        record = by_ref.get(ref)
        if record and record["label"] in {"section_header", "title"}:
            last_heading_by_page[record["page_no"]] = record
            continue
        if ref not in groups:
            continue
        children = [item for item in records if item.get("parent_ref") == ref]
        if not children:
            continue
        pages = {item["page_no"] for item in children}
        if len(pages) != 1:
            continue
        page_no = next(iter(pages))
        heading = last_heading_by_page.get(page_no)
        if heading:
            associations.append(
                {"group_ref": ref, "heading": heading, "children": children}
            )

    candidates = []
    for association in associations:
        heading = association["heading"]
        children = association["children"]
        upper = [
            item
            for item in children
            if item["top_norm"]
            > heading["top_norm"] + config.split_group_vertical_tolerance
        ]
        lower_or_aligned = [item for item in children if item not in upper]
        if not upper or not lower_or_aligned:
            continue

        upper.sort(key=lambda item: (-item["top_norm"], item["left_norm"]))
        upper_left = min(item["left_norm"] for item in upper)
        upper_right = max(item["right_norm"] for item in upper)
        upper_top = max(item["top_norm"] for item in upper)
        alternatives = []
        for other in associations:
            if (
                other["group_ref"] == association["group_ref"]
                or other["heading"]["page_no"] != heading["page_no"]
            ):
                continue
            other_children = other["children"]
            other_left = min(item["left_norm"] for item in other_children)
            other_right = max(item["right_norm"] for item in other_children)
            horizontal_gap = _axis_gap(
                upper_left, upper_right, other_left, other_right
            )
            vertical_gap = other["heading"]["bottom_norm"] - upper_top
            if (
                horizontal_gap <= config.split_group_max_horizontal_gap
                and vertical_gap >= -config.split_group_vertical_tolerance
            ):
                alternatives.append((vertical_gap, horizontal_gap, other))
        if not alternatives:
            continue
        vertical_gap, horizontal_gap, target = min(
            alternatives, key=lambda value: (value[0], value[1])
        )
        source_children = sorted(
            children, key=lambda item: item["order_index"]
        )
        target_children = sorted(
            target["children"], key=lambda item: item["order_index"]
        )
        # The source group can be spatially split across two section cards.
        # Keep both halves in the proposal: the upper tail belongs with the
        # nearby target heading, while the lower/aligned tail remains with the
        # source heading.  The previous proposal omitted the source heading
        # and lower tail, making it impossible to apply or audit safely.
        proposed_source_order = [
            *upper,
            heading,
            *lower_or_aligned,
        ]
        candidates.append(
            {
                "page_no": heading["page_no"],
                "type": "SPLIT_GROUP_SECTION_ASSOCIATION",
                "confidence": "MEDIUM",
                "decision": "REVIEW_REQUIRED",
                "reason": "그룹 일부가 자기 제목보다 위에 있고 인접한 다른 섹션 흐름에 가까움",
                "source_group_ref": association["group_ref"],
                "source_heading_ref": heading["self_ref"],
                "target_group_ref": target["group_ref"],
                "target_heading_ref": target["heading"]["self_ref"],
                "operation": "MOVE_CHILDREN",
                "source_parent_ref": association["group_ref"],
                "target_parent_ref": target["group_ref"],
                "moved_refs": _proposal(*upper),
                "observed_order": _proposal(
                    target["heading"], *target_children, heading, *source_children
                ),
                "proposed_order": _proposal(
                    target["heading"], *target_children, *proposed_source_order
                ),
                "metrics": {
                    "detached_item_count": len(upper),
                    "horizontal_gap_norm": round(horizontal_gap, 6),
                    "heading_to_tail_gap_norm": round(vertical_gap, 6),
                },
            }
        )
    return candidates


def _late_section_heading_relations(
    records: list[dict[str, Any]], config: DetectorConfig
) -> list[dict[str, Any]]:
    """Find an adjacent section heading stored after a lower body block.

    This is relation-only evidence.  A two-item swap is usually insufficient
    because the heading can own several following blocks, so no executable
    correction is proposed here.
    """

    grouped: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        parent_ref = record.get("parent_ref")
        if isinstance(parent_ref, str):
            grouped[(record["page_no"], parent_ref)].append(record)

    candidates: list[dict[str, Any]] = []
    for (page_no, parent_ref), siblings in grouped.items():
        siblings.sort(key=lambda item: item["order_index"])
        for current, following in zip(siblings, siblings[1:]):
            upward_offset = following["top_norm"] - current["top_norm"]
            if (
                current.get("label") not in LOCAL_FLOW_LABELS
                or following.get("label") != "section_header"
                or upward_offset < config.premature_vertical_margin
                or current["left_norm"] - following["left_norm"]
                < config.left_alignment_tolerance
            ):
                continue
            candidates.append(
                {
                    "page_no": page_no,
                    "type": "LATE_SECTION_HEADING_RELATION",
                    "confidence": "MEDIUM",
                    "decision": "REVIEW_REQUIRED",
                    "operation": "RELATION_ONLY",
                    "relation": "BEFORE",
                    "reason": (
                        "같은 parent의 section heading이 시각적으로 더 아래인 "
                        "본문 요소 뒤에 저장되어 heading 선행 관계 검토가 필요함"
                    ),
                    "parent_ref": parent_ref,
                    "from_ref": following["self_ref"],
                    "to_ref": current["self_ref"],
                    "observed_order": _proposal(current, following),
                    "proposed_order": _proposal(following, current),
                    "metrics": {
                        "upward_offset_norm": round(upward_offset, 6),
                        "left_delta_norm": round(
                            abs(following["left_norm"] - current["left_norm"]), 6
                        ),
                        "exact_correction_available": False,
                        "auto_reorder_eligible": False,
                    },
                }
            )
    return candidates


def detect_reading_order_candidates(
    document: dict[str, Any],
    records: list[dict[str, Any]],
    config: DetectorConfig | None = None,
) -> list[dict[str, Any]]:
    """Detect review candidates without modifying the Docling document."""

    active_config = config or DetectorConfig()
    required = filter_ordering_records(records)
    enriched = add_spatial_features(document, required)
    local_candidates = _vertical_group_inversions(enriched, active_config)
    group_candidates, replaced_parents = _semantic_group_reorders(
        document, enriched, local_candidates, active_config
    )
    sequence_candidates = _enumerated_sequence_inversions(enriched)
    sequence_parents = {item["parent_ref"] for item in sequence_candidates}
    sequence_covered_refs: dict[str, set[str]] = defaultdict(set)
    for item in sequence_candidates:
        sequence_covered_refs[item["parent_ref"]].update(item["observed_order"])
    candidates = []
    for item in local_candidates:
        parent_ref = item.get("parent_ref")
        if parent_ref in replaced_parents:
            continue
        if parent_ref in sequence_parents:
            if set(item.get("observed_order", [])) <= sequence_covered_refs[parent_ref]:
                continue
            # A partially parsed numeric list is structurally ambiguous. Keep
            # the uncovered relation visible, but do not let it bypass the
            # sequence detector and become a new automatic swap.
            item = {
                **item,
                "type": "SEQUENCE_PARENT_LOCAL_RELATION",
                "decision": "REVIEW_REQUIRED",
                "operation": "RELATION_ONLY",
                "relation": "BEFORE",
                "metrics": {
                    **item.get("metrics", {}),
                    "sequence_parent_partial_coverage": True,
                    "auto_reorder_eligible": False,
                },
            }
        candidates.append(item)
    candidates.extend(
        item for item in group_candidates
        if item.get("parent_ref") not in sequence_parents
    )
    candidates.extend(sequence_candidates)
    candidates.extend(_section_table_candidates(enriched, active_config))
    candidates.extend(_late_section_heading_relations(enriched, active_config))
    candidates.extend(_interrupted_column_continuations(enriched, active_config))
    candidates.extend(
        _horizontal_section_block_inversions(enriched, active_config)
    )
    candidates.extend(
        _split_group_section_candidates(document, enriched, active_config)
    )
    candidates.sort(key=lambda item: (item["page_no"], item["type"], item["observed_order"]))
    for index, candidate in enumerate(candidates, start=1):
        candidate["candidate_id"] = f"ROC-{index:04d}"
    return candidates
