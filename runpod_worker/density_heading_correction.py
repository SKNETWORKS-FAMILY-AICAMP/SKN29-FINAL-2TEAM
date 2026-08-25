"""밀도 기반 헤딩 승격(보정) — Docling이 `text`/`list_item`으로 잘못 분류한 실제
헤딩을 되살린다. Docling의 후처리는 레이아웃 모델(Heron)이 이미 헤딩이라고 본 걸
확인·기각만 할 뿐 새 헤딩 후보를 만들지 않으므로, 이 모듈이 직접 후보를 다시 골라
document에 반영한다.

`parser/heading_develop/density_promotion/density_heading_correction.py`(R&D 원본,
`DENSITY_HEADING_CORRECTION_SPEC.md`에 신호별 근거가 정리돼 있다)를 이 프로젝트의
RunPod worker에 맞게 포팅했다. 원본과 다른 점 두 가지:

1. `extract_density_items`의 JSON 저장은 선택(`output_path=None`이면 생략) —
   서버리스 worker는 로컬 디스크에 결과를 남길 이유가 없다.
2. `apply_promotions`가 새로 추가됐다 — 원본은 승격 후보를 계산만 하고(디버그
   이미지로만 시각화) 실제 DoclingDocument에는 반영하지 않았다. 여기서는
   승격된 항목을 `SectionHeaderItem`으로 바꿔치기해서, 이후 청킹이 실제로
   승격된 결과를 보게 한다.

디버그 이미지 생성(`density_heading_debug_image.py`, PyMuPDF 렌더링)은 이식하지
않았다 — worker는 원본 페이지 이미지를 그릴 이유가 없다.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any

# ---------------------------------------------------------------------------
# 컬럼 분할 · 그림 내부 판정
# ---------------------------------------------------------------------------

_DEFAULT_COLUMN_GAP = 100.0  # 같은 컬럼 내 들여쓰기 차와 컬럼 간 차를 가르는 임계값(pt)


def assign_columns(candidates: list[dict], gap_threshold: float = _DEFAULT_COLUMN_GAP) -> list[dict]:
    """페이지별로 l값 갭 클러스터링을 해서 각 후보에 "column" 인덱스를 붙인다(제자리 수정)."""
    by_page: dict[int, list[dict]] = defaultdict(list)
    for c in candidates:
        by_page[c["page_no"]].append(c)

    for group in by_page.values():
        xs = sorted({c["l"] for c in group})
        starts = [xs[0]]
        prev = xs[0]
        for x in xs[1:]:
            if x - prev > gap_threshold:
                starts.append(x)
            prev = x
        for c in group:
            idx = 0
            for i, s in enumerate(starts):
                if c["l"] >= s - 1e-6:
                    idx = i
            c["column"] = idx
    return candidates


def _is_inside_picture(item, document) -> bool:
    """item부터 parent 체인을 타고 올라가며 그림(PictureItem) 아래에 속하는지 확인한다.
    그림 안의 글자는 VLM으로 별도 추출되므로 헤딩 후보에서 완전히 제외한다."""
    seen: set[str] = set()
    current = item
    while True:
        parent_ref = getattr(current, "parent", None)
        if parent_ref is None:
            return False
        cref = getattr(parent_ref, "cref", None) or str(parent_ref)
        if cref == "#/body" or cref in seen:
            return False
        if cref.startswith("#/pictures/"):
            return True
        seen.add(cref)
        try:
            current = parent_ref.resolve(document)
        except Exception:
            return False


# ---------------------------------------------------------------------------
# 추출 — result(라이브 ConversionResult)에서만 가능.
# ---------------------------------------------------------------------------

# 밀도 계산의 "문맥"으로 쓸 라벨. 실제 읽기 흐름에 텍스트로 존재하는 것만 포함한다
# (표/그림 자체는 제외 — 그 안의 캡션은 label="caption"으로 별도로 이미 잡힌다).
_CONTEXT_LABELS = {"text", "list_item", "section_header", "caption", "footnote"}
# 이 중 승격 대상(헤딩 후보)이 될 수 있는 것만 따로 표시한다.
_CANDIDATE_LABELS = {"text", "list_item"}


def _raw_layout_match(hbox, page) -> tuple[str | None, float | None]:
    """item의 top-left bbox와 가장 많이 겹치는 raw layout cluster의 (라벨, confidence)를 찾는다."""
    predictions = getattr(page, "predictions", None)
    layout = getattr(predictions, "layout", None) if predictions is not None else None
    clusters = getattr(layout, "clusters", None) if layout is not None else None
    if not clusters:
        return None, None

    best_overlap = 0.0
    best: tuple[str | None, float | None] = (None, None)
    for cluster in clusters:
        cbox = cluster.bbox.to_top_left_origin(page.size.height)
        if not hbox.overlaps(cbox):
            continue
        inter_l = max(hbox.l, cbox.l)
        inter_t = max(hbox.t, cbox.t)
        inter_r = min(hbox.r, cbox.r)
        inter_b = min(hbox.b, cbox.b)
        inter_area = max(0.0, inter_r - inter_l) * max(0.0, inter_b - inter_t)
        item_area = max(1e-6, (hbox.r - hbox.l) * (hbox.b - hbox.t))
        ratio = inter_area / item_area
        if ratio > best_overlap:
            best_overlap = ratio
            label = cluster.label.value if hasattr(cluster.label, "value") else cluster.label
            best = (label, float(cluster.confidence))
    return best


def extract_density_items(result, output_path: str | Path | None = None) -> list[dict]:
    """`_CONTEXT_LABELS`에 속하는 모든 항목을 뽑아 밀도 계산용 dict 리스트로 만든다.
    `is_candidate`가 True인 것만 승격 대상(text/list_item)이고, 나머지는 밀도 계산의
    문맥으로만 쓰인다. `output_path`를 주면 참고용으로 JSON도 남긴다(worker에서는
    보통 생략한다)."""
    document = result.document
    page_cells = {
        p.page_no: list(p.parsed_page.textline_cells) for p in result.pages if p.parsed_page is not None
    }
    pages_by_no = {p.page_no: p for p in result.pages}
    heights = {no: page.size.height for no, page in document.pages.items()}

    items: list[dict] = []
    for item in document.texts:
        label = item.label.value if hasattr(item.label, "value") else item.label
        if label not in _CONTEXT_LABELS:
            continue
        text = (item.text or "").strip()
        if not text:
            continue
        if _is_inside_picture(item, document):
            continue
        for prov in item.prov:
            page_no = prov.page_no
            ph = heights.get(page_no)
            if ph is None:
                continue
            hbox = prov.bbox.to_top_left_origin(ph)

            overlapping = [
                cell
                for cell in page_cells.get(page_no, [])
                if hbox.overlaps(cell.rect.to_bounding_box().to_top_left_origin(ph))
            ]
            cell_height = median(c.rect.height for c in overlapping) if overlapping else (hbox.b - hbox.t)

            page = pages_by_no.get(page_no)
            raw_label, raw_confidence = _raw_layout_match(hbox, page) if page is not None else (None, None)

            items.append(
                {
                    "self_ref": item.self_ref,
                    "label": label,
                    "is_candidate": label in _CANDIDATE_LABELS,
                    "text": text,
                    "text_length": len(text),
                    "page_no": page_no,
                    "l": hbox.l,
                    "t": hbox.t,
                    "r": hbox.r,
                    "b": hbox.b,
                    "height": cell_height,
                    "raw_layout_label": raw_label,
                    "raw_layout_confidence": raw_confidence,
                }
            )

    if output_path is not None:
        Path(output_path).write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return items


# ---------------------------------------------------------------------------
# 밀도 피처 계산 — result 없이, 저장된 items만으로도 반복 가능한 순수 계산.
# ---------------------------------------------------------------------------

# 아래 상수는 hanwha.pdf 한 건으로 검증한 잠정치다(R&D 원본 SPEC 5·6절 참조).
_DEFAULT_WINDOW_PT = 120.0  # 위/아래 밀도를 잴 창의 수직 범위(pt)
_DEFAULT_SIZE_MARGIN = 1.15  # height가 같은 컬럼 본문(median)의 몇 배 이상이어야 "큰 글씨"인가
_DEFAULT_SHORT_TEXT_MAX_CHARS = 60  # "짧음" 판정 상한(문자 수)
_DEFAULT_MIN_GAP_ABOVE = 4.0  # "위쪽 공백 있음" 최소 pt (0에 가까우면 그냥 바로 위 줄과 이어진 것)
_DEFAULT_MIN_DENSITY_SCORE = 0.0  # heading_density_score(density_below - density_above) 최소값


def compute_density_features(items: list[dict], window_pt: float = _DEFAULT_WINDOW_PT) -> list[dict]:
    """(page, column)별로 읽기 순서(`t` 오름차순)를 세우고, 각 항목에 대해
    `gap_above`(바로 위 항목과의 수직 간격), `density_above`/`density_below`(창 안 텍스트
    밀도, 문자수/pt), `heading_density_score`(density_below - density_above), `body_height`
    (같은 컬럼 `text` 항목들의 median height)를 계산해 원본 dict에 덧붙인다(제자리 수정)."""
    items = assign_columns(items)

    by_group: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for it in items:
        by_group[(it["page_no"], it["column"])].append(it)

    for group in by_group.values():
        group.sort(key=lambda it: it["t"])

        body_heights = [it["height"] for it in group if it["label"] == "text"]
        body_height = median(body_heights) if body_heights else median(it["height"] for it in group)

        n = len(group)
        for i, it in enumerate(group):
            it["body_height"] = body_height

            it["gap_above"] = (it["t"] - group[i - 1]["b"]) if i > 0 else None

            chars_above = 0
            for j in range(i - 1, -1, -1):
                dist = it["t"] - group[j]["b"]
                if dist > window_pt:
                    break
                if dist >= 0:
                    chars_above += group[j]["text_length"]
            it["density_above"] = chars_above / window_pt

            chars_below = 0
            for j in range(i + 1, n):
                dist = group[j]["t"] - it["b"]
                if dist > window_pt:
                    break
                if dist >= 0:
                    chars_below += group[j]["text_length"]
            it["density_below"] = chars_below / window_pt

            it["heading_density_score"] = it["density_below"] - it["density_above"]

    return items


# ---------------------------------------------------------------------------
# 승격 판정 — 네 신호(짧음/큰 글씨/위쪽 공백/density score)를 전부 만족해야 승격.
# ---------------------------------------------------------------------------


def promote_candidates(
    items: list[dict],
    size_margin: float = _DEFAULT_SIZE_MARGIN,
    short_text_max_chars: int = _DEFAULT_SHORT_TEXT_MAX_CHARS,
    min_gap_above: float = _DEFAULT_MIN_GAP_ABOVE,
    min_density_score: float = _DEFAULT_MIN_DENSITY_SCORE,
) -> list[dict]:
    """`is_candidate`인 항목 중 네 조건을 전부 만족하는 것만 `promoted=True`로 표시해 반환한다
    (원본 items는 건드리지 않고, 후보만 골라 새 리스트로 반환)."""
    promoted: list[dict] = []
    for it in items:
        if not it.get("is_candidate"):
            continue
        if it.get("heading_density_score") is None:
            continue  # compute_density_features를 먼저 돌려야 함

        pass_short = it["text_length"] <= short_text_max_chars
        pass_size = it["height"] >= it["body_height"] * size_margin
        pass_gap = it["gap_above"] is None or it["gap_above"] >= min_gap_above
        pass_density = it["heading_density_score"] >= min_density_score

        it["_pass_short"] = pass_short
        it["_pass_size"] = pass_size
        it["_pass_gap"] = pass_gap
        it["_pass_density"] = pass_density
        it["promoted"] = pass_short and pass_size and pass_gap and pass_density

        if it["promoted"]:
            promoted.append(it)

    return promoted


# ---------------------------------------------------------------------------
# 문서 반영 — 승격된 항목을 실제 DoclingDocument에서 SectionHeaderItem으로 바꾼다.
# (R&D 원본에는 없던 단계. 원본은 디버그 이미지로만 승격 결과를 확인했지만, worker는
# 그 결과를 이후 청킹이 실제로 보게 해야 하므로 document 자체를 고친다.)
# ---------------------------------------------------------------------------

#: 승격된 항목에 부여할 헤딩 레벨. 이 모듈은 승격 여부(짧음/큰 글씨/여백/밀도)만
#: 판단하고 계층 깊이는 추론하지 않으므로(R&D 원본 SPEC 5절 한계와 동일), 전부
#: 최상위(level=1)로 취급한다.
_PROMOTED_LEVEL = 1


def apply_promotions(document: Any, promoted_items: list[dict]) -> Any:
    """`promoted_items`(`promote_candidates()`의 반환값)에 해당하는
    `document.texts` 항목을 `SectionHeaderItem`으로 바꿔치기한다(제자리 수정, 같은
    document를 반환). `self_ref`(예: `#/texts/16`)는 그대로 유지하므로 `body`/부모
    `children`의 참조(RefItem)는 인덱스 기반이라 깨지지 않는다."""
    from docling_core.types.doc.document import SectionHeaderItem
    from docling_core.types.doc.labels import DocItemLabel

    by_ref = {item.self_ref: idx for idx, item in enumerate(document.texts)}
    for promoted in promoted_items:
        idx = by_ref.get(promoted["self_ref"])
        if idx is None:
            continue
        original = document.texts[idx]
        if original.label == DocItemLabel.SECTION_HEADER:
            continue
        document.texts[idx] = SectionHeaderItem(
            self_ref=original.self_ref,
            parent=original.parent,
            children=original.children,
            content_layer=original.content_layer,
            meta=original.meta,
            label=DocItemLabel.SECTION_HEADER,
            prov=original.prov,
            source=original.source,
            comments=original.comments,
            orig=original.orig,
            text=original.text,
            formatting=original.formatting,
            hyperlink=original.hyperlink,
            level=_PROMOTED_LEVEL,
        )
    return document


def promote_headings_by_density(
    result,
    *,
    window_pt: float = _DEFAULT_WINDOW_PT,
    size_margin: float = _DEFAULT_SIZE_MARGIN,
    short_text_max_chars: int = _DEFAULT_SHORT_TEXT_MAX_CHARS,
    min_gap_above: float = _DEFAULT_MIN_GAP_ABOVE,
    min_density_score: float = _DEFAULT_MIN_DENSITY_SCORE,
) -> list[dict]:
    """추출 → 피처 계산 → 승격 판정 → document 반영까지 한 번에 실행한다.
    `result.document`를 제자리에서 승격시키고, 승격된 항목 목록을 반환한다."""
    items = extract_density_items(result)
    items = compute_density_features(items, window_pt=window_pt)
    promoted = promote_candidates(
        items,
        size_margin=size_margin,
        short_text_max_chars=short_text_max_chars,
        min_gap_above=min_gap_above,
        min_density_score=min_density_score,
    )
    apply_promotions(result.document, promoted)
    return promoted
