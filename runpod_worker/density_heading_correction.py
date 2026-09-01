"""밀도 기반 헤딩 승격(보정) 로직 — `heading_develop/dbscan_heading_comparison.py`
([크기, 들여쓰기] DBSCAN)와는 독립된 별도 신호 경로다. 서로 교차검증하는 용도로 설계했고,
아직 두 결과를 합치는 로직은 없다.

디버그 이미지 생성은 이 파일이 아니라 같은 폴더의 `density_heading_debug_image.py`에 있다
— 이 파일은 추출·계산·승격 판정("보정")까지만 담당한다.

## 설계 근거 (사용자 제시, 2026-08-13)

"Cluster A" 패턴 — 짧음 + 큰 글씨 + 위쪽 공백 큼 + 아래 밀도 높음 → Heading.

    heading_density_score = density_below - density_above

네 신호를 이렇게 대응시켰다:
- 짧음        → `text_length`(문자 수)
- 큰 글씨      → `height`(셀 높이) vs 같은 컬럼의 본문 median
- 위쪽 공백 큼  → `gap_above`(바로 위 항목과의 수직 간격) — 여전히 좌표(pt) 기반. 공백은
  본질적으로 시각적 간격이라 좌표를 벗어날 이유가 없다.
- 아래 밀도 높음 → `heading_density_score`(읽기순서 기준 아래쪽 인접 항목들의 평균 텍스트
  길이 − 위쪽 인접 항목들의 평균 텍스트 길이)

## 설계 개정 — density_above/below를 좌표창에서 읽기순서 인접으로 변경 (2026-08-25)

처음 버전은 density_above/below를 "위/아래로 고정 pt 범위(window_pt) 안의 텍스트량"으로
쟀다. 이건 애초에 읽기 순서가 정확히 보존된다고 신뢰할 수 없었을 때(38번 항목 — 컬럼이
잘못 병합되는 문제) 좌표에 기대 만든 임시 기준이었다. 이제 읽기 순서가 잘 복원된다는
전제 위에서는, 좌표창 대신 **`document.iterate_items()`가 주는 실제 body 읽기순서상
인접 항목**을 직접 비교할 수 있다 — 컬럼 판정(`assign_columns`)에 기대지 않고 문서가
이미 알고 있는 순서를 그대로 신뢰하는 것이다.

다만 이 가정 자체는 이 모듈이 보장하는 게 아니다 — Docling 기본 `ReadingOrderPredictor`는
좌→우(컬럼) 인접 판단 로직이 사실상 비활성 상태라는 게 이미 확인돼 있다
(`reading_order/DOCLING_READING_ORDER_MECHANISM_SPEC.md` 4.2절). 즉 "읽기 순서가 잘
복원됐다"는 전제는 **이 파이프라인 앞단에 별도의 읽기순서 보정이 적용돼 있을 때만
유효**하다. 지금 `extract_density_items()`는 `result.document`를 가공 없이 그대로
읽으므로, 그런 보정이 실제로 적용된 문서를 입력으로 줄 때만 이 가정이 성립한다.

`gap_above`("위쪽 공백 큼")는 이 개정과 무관하게 그대로 좌표(pt) 기반이다 — 공백은
"인접 항목이 무엇인가"가 아니라 "그 항목과 얼마나 떨어져 있는가"를 재는 값이라 좌표가
맞는 신호다. `body_height`(같은 컬럼 본문 median)도 컬럼 기반 그대로 둔다.

## 입력 3종 (`extract_density_items`가 받는 것)

1. `result` — `converter.convert(...)`가 반환한 ConversionResult. `result.pages[].parsed_page`
   에서 backend/OCR cell(줄 단위 bbox·문자열)을 얻어 셀 높이를 계산한다
   (`dbscan_heading_comparison.export_candidate_features`와 동일한 겹침 기반 join 방식).
2. `result.document` — 최종 DoclingDocument. 승격 후보(`text`/`list_item`)뿐 아니라 밀도 계산의
   문맥으로 쓸 텍스트 보유 항목(`section_header`/`caption`/`footnote` 등) 전부를 여기서 얻는다.
3. `result.pages[].predictions.layout.clusters` — 레이아웃 모델 원시 cluster(라벨+confidence).
   지금 점수 공식에는 안 쓰지만, 각 후보의 원본 raw label·confidence를 같이 기록해둬서 나중에
   DBSCAN 쪽 결과나 34번 항목(레이아웃 confidence 신호)과 교차 대조할 때 바로 쓸 수 있게 한다.

## 알려진 제약

컬럼 분할(`assign_columns`)은 인접 간격만 보고 체이닝하는 방식이라, 폭넓게 퍼진 영역을
하나의 컬럼으로 잘못 묶을 수 있다는 한계(HEADING_LEVEL_작업_명세.md 38번 항목)가 있다.
이번 작업 범위가 아니라서 고치지 않고 그대로 둔다.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any

# ---------------------------------------------------------------------------
# 컬럼 분할 · 그림 내부 판정 (heading_develop/dbscan_heading_comparison.py에서 복사)
# ---------------------------------------------------------------------------

_DEFAULT_COLUMN_GAP = 100.0  # hanwha.pdf 실측: 같은 컬럼 내 들여쓰기 차 ~9pt, 컬럼 간 차 ~540pt


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
    """item부터 parent 체인을 타고 올라가며 그림(PictureItem) 아래에 속하는지 확인한다
    (라이브 DoclingDocument 객체 버전). 그림 안의 글자는 어차피 VLM으로 별도 추출되므로
    헤딩 후보에서 완전히 제외한다."""
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
# 추출 — result(라이브 ConversionResult)에서만 가능. 세션 밖에서는 load_density_items로 재사용.
# ---------------------------------------------------------------------------

# 밀도 계산의 "문맥"으로 쓸 라벨. 실제 읽기 흐름에 텍스트로 존재하는 것만 포함한다
# (표/그림 자체는 제외 — 그 안의 캡션은 label="caption"으로 별도로 이미 잡힌다).
_CONTEXT_LABELS = {"text", "list_item", "section_header", "caption", "footnote"}
# 실제 연구 범위에 맞춰 잘못 분류된 whole-element list item만 헤딩
# 후보로 삼는다. 일반 text는 밀도 문맥에는 참여하지만 승격 대상이 아니다.
_CANDIDATE_LABELS = {"list_item"}


def _raw_layout_match(hbox, page) -> tuple[str | None, float | None]:
    """item의 top-left bbox와 가장 많이 겹치는 raw layout cluster의 (라벨, confidence)를 찾는다.
    `page.predictions.layout.clusters`가 없거나 겹치는 게 없으면 (None, None)."""
    predictions = getattr(page, "predictions", None)
    layout = getattr(predictions, "layout", None) if predictions is not None else None
    clusters = getattr(layout, "clusters", None) if layout is not None else None
    if not clusters:
        return None, None

    best_overlap = 0.0
    best = (None, None)
    for cluster in clusters:
        cbox = cluster.bbox.to_top_left_origin(page.size.height)
        if not hbox.overlaps(cbox):
            continue
        # 겹침 정도는 item bbox 면적 대비로 잰다(overlap_ratio와 같은 방향).
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


def extract_density_items(
    result, output_path: str | Path | None = None
) -> list[dict]:
    """`_CONTEXT_LABELS`에 속하는 모든 항목을 뽑아 밀도 계산용 JSON으로 저장한다.
    `is_candidate`가 True인 것만 승격 대상(text/list_item)이고, 나머지는 밀도 계산의
    문맥으로만 쓰인다.

    `document.texts`(단순 배열, 읽기 순서 보장 없음) 대신 `document.iterate_items()`로
    body 트리를 실제 읽기순서대로 순회한다 — density_above/below가 이 순서에 의존하기
    때문이다(2026-08-25 개정, 위 모듈 docstring 참조). 순회에서 만나는 순서대로
    `reading_order_index`를 매겨서, `compute_density_features`가 좌표 재계산 없이
    바로 인접 항목을 찾을 수 있게 한다.
    """
    document = result.document
    page_cells = {
        p.page_no: list(p.parsed_page.textline_cells) for p in result.pages if p.parsed_page is not None
    }
    pages_by_no = {p.page_no: p for p in result.pages}
    heights = {no: page.size.height for no, page in document.pages.items()}

    items: list[dict] = []
    reading_order_index = 0
    for item, _level in document.iterate_items():
        raw_label = getattr(item, "label", None)
        label = raw_label.value if hasattr(raw_label, "value") else raw_label
        if label not in _CONTEXT_LABELS:
            continue
        text = (getattr(item, "text", "") or "").strip()
        if not text:
            continue
        if _is_inside_picture(item, document):
            continue

        matched_any_page = False
        for prov in getattr(item, "prov", []) or []:
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
            matched_layout_label, matched_layout_confidence = (
                _raw_layout_match(hbox, page) if page is not None else (None, None)
            )

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
                    "raw_layout_label": matched_layout_label,
                    "raw_layout_confidence": matched_layout_confidence,
                    "reading_order_index": reading_order_index,
                }
            )
            matched_any_page = True

        if matched_any_page:
            reading_order_index += 1  # 항목 하나당 한 번만 증가(prov가 여럿이어도 같은 순서)

    if output_path is not None:
        Path(output_path).write_text(
            json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return items


def load_density_items(path: str | Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def backfill_reading_order_index(document_json_path: str | Path, density_items_path: str | Path) -> list[dict]:
    """2026-08-25 스키마 변경(`reading_order_index` 필드 추가) 이전에 저장된
    `density_items.json`을 문서를 다시 변환하지 않고 보정한다.

    `document.json`만으로(`result` 없이) `document.iterate_items()`를 다시 돌려
    self_ref -> 읽기순서 인덱스를 만들고, 기존 density_items에 병합해 덮어쓴다. 이미
    `reading_order_index`가 있으면 아무것도 안 하고 그대로 반환한다(멱등 — 재개 로직에서
    문서마다 매번 호출해도 안전).
    """
    from docling_core.types.doc.document import DoclingDocument

    items = load_density_items(density_items_path)
    if items and "reading_order_index" in items[0]:
        return items

    with open(document_json_path, encoding="utf-8") as f:
        document = DoclingDocument.model_validate(json.load(f))

    index_by_ref: dict[str, int] = {}
    reading_order_index = 0
    for item, _level in document.iterate_items():
        raw_label = getattr(item, "label", None)
        label = raw_label.value if hasattr(raw_label, "value") else raw_label
        if label not in _CONTEXT_LABELS:
            continue
        text = (getattr(item, "text", "") or "").strip()
        if not text:
            continue
        if _is_inside_picture(item, document):
            continue
        index_by_ref[item.self_ref] = reading_order_index
        reading_order_index += 1

    for it in items:
        # self_ref로 못 찾으면(추출 로직이 그새 더 바뀐 경우 등) 맨 끝 취급 — 조용히
        # 죽는 것보다야 낫지만, 이 분기를 타면 필터링 로직이 갈라졌다는 신호이므로
        # 확인이 필요하다.
        it["reading_order_index"] = index_by_ref.get(it["self_ref"], reading_order_index)

    Path(density_items_path).write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return items


# ---------------------------------------------------------------------------
# 밀도 피처 계산 — result 없이, 저장된 JSON만으로도 반복 가능한 순수 계산.
# ---------------------------------------------------------------------------

# 아래 세 상수는 전부 초기값이다 — hanwha.pdf 한 건으로도 아직 튜닝 전이라 확정값이 아니다
# (33~35번 항목에서 굵기 문턱값을 문서 1건으로만 튜닝했다가 문제됐던 함정을 반복하지 않도록,
# 여러 문서로 확대 검증하기 전까지는 잠정치로 취급한다).
_DEFAULT_DENSITY_WINDOW_ITEMS = 3  # density_above/below를 잴 때 볼 읽기순서 인접 항목 개수
_DEFAULT_SIZE_MARGIN = 1.15  # height가 같은 컬럼 본문(median)의 몇 배 이상이어야 "큰 글씨"인가
_DEFAULT_SHORT_TEXT_MAX_CHARS = 60  # "짧음" 판정 상한(문자 수)
_DEFAULT_MIN_GAP_ABOVE = 4.0  # "위쪽 공백 있음" 최소 pt (0에 가까우면 그냥 바로 위 줄과 이어진 것)


def compute_density_features(
    items: list[dict], density_window_items: int = _DEFAULT_DENSITY_WINDOW_ITEMS
) -> list[dict]:
    """`gap_above`(바로 위 항목과의 수직 간격)·`body_height`(같은 컬럼 `text` 항목들의
    median height)는 기존대로 (page, column) 좌표 그룹 안에서 계산한다.

    `density_above`/`density_below`/`heading_density_score`는 좌표가 아니라
    **읽기순서(`reading_order_index`) 인접 항목**으로 계산한다(2026-08-25 개정, 모듈
    docstring 참조) — 문서 전체를 읽기순서로 한 줄 세운 뒤, 각 항목 앞뒤로
    `density_window_items`개씩 이웃의 평균 문자 수를 비교한다. 컬럼 판정과 무관하게
    문서가 이미 아는 순서를 그대로 쓰므로, 이 계산에는 `assign_columns`가 관여하지 않는다.

    문맥 항목(`is_candidate=False`)에도 전부 계산하지만, 승격 판단에는 후보만 쓴다.
    """
    items = assign_columns(items)

    by_group: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for it in items:
        by_group[(it["page_no"], it["column"])].append(it)

    for group in by_group.values():
        group.sort(key=lambda it: it["t"])

        body_heights = [it["height"] for it in group if it["label"] == "text"]
        body_height = median(body_heights) if body_heights else median(it["height"] for it in group)

        for i, it in enumerate(group):
            it["body_height"] = body_height
            # gap_above: 바로 위 항목(같은 컬럼, 좌표상 직전)과의 수직 간격.
            it["gap_above"] = (it["t"] - group[i - 1]["b"]) if i > 0 else None

    # density_above/below: 문서 전체를 읽기순서 하나로 정렬해서 계산한다(컬럼 무관).
    reading_order_seq = sorted(items, key=lambda it: it["reading_order_index"])
    for i, it in enumerate(reading_order_seq):
        above = reading_order_seq[max(0, i - density_window_items) : i]
        below = reading_order_seq[i + 1 : i + 1 + density_window_items]
        it["density_above"] = (sum(a["text_length"] for a in above) / len(above)) if above else 0.0
        it["density_below"] = (sum(b["text_length"] for b in below) / len(below)) if below else 0.0
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
    min_density_score: float = 0.0,
) -> list[dict]:
    """`is_candidate`인 항목 중 네 조건을 전부 만족하는 것만 `promoted=True`로 표시해 반환한다
    (원본 items는 건드리지 않고, 후보만 골라 새 리스트로 반환). 각 항목에 조건별 통과 여부를
    `_pass_short`/`_pass_size`/`_pass_gap`/`_pass_density`로 같이 남겨서, 어느 조건 때문에
    떨어졌는지 바로 확인할 수 있게 한다.
    """
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


_PROMOTED_LEVEL = 1
_STRUCTURAL_RAW_LABELS = {"key_value_region", "key_value_area"}


def apply_promotions(
    document: Any, promoted_items: list[dict]
) -> tuple[list[dict], list[dict]]:
    """Apply only schema-safe, validated whole-list-item promotions.

    A promoted ``list_item`` is replaced with ``SectionHeaderItem`` while
    retaining its ref, parent, children, provenance, text, formatting,
    comments, and metadata.  Ordinary ``text`` items are not candidates.
    """
    from docling_core.types.doc.document import DoclingDocument, SectionHeaderItem
    from docling_core.types.doc.labels import DocItemLabel

    by_ref = {str(item.self_ref): idx for idx, item in enumerate(document.texts)}
    applied: list[dict] = []
    skipped: list[dict] = []
    for promoted in promoted_items:
        ref = str(promoted.get("self_ref") or "")
        raw_label = str(promoted.get("raw_layout_label") or "").lower()
        if promoted.get("label") != "list_item":
            skipped.append({"self_ref": ref, "reason": "NOT_LIST_ITEM_CANDIDATE"})
            continue
        if raw_label in _STRUCTURAL_RAW_LABELS:
            skipped.append({"self_ref": ref, "reason": "KEY_VALUE_STRUCTURE_GUARD"})
            continue
        idx = by_ref.get(ref)
        if idx is None:
            skipped.append({"self_ref": ref, "reason": "REF_NOT_FOUND"})
            continue
        original = document.texts[idx]
        if original.label == DocItemLabel.SECTION_HEADER:
            skipped.append({"self_ref": ref, "reason": "ALREADY_SECTION_HEADER"})
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
        applied.append(
            {"self_ref": ref, "before": str(original.label), "after": "section_header"}
        )

    # Validate the full tree after replacing discriminated item models.
    DoclingDocument.model_validate(
        document.model_dump(mode="json", exclude_none=True)
    )
    return applied, skipped


def promote_headings_by_density(
    result,
    *,
    density_window_items: int = _DEFAULT_DENSITY_WINDOW_ITEMS,
    size_margin: float = _DEFAULT_SIZE_MARGIN,
    short_text_max_chars: int = _DEFAULT_SHORT_TEXT_MAX_CHARS,
    min_gap_above: float = _DEFAULT_MIN_GAP_ABOVE,
    min_density_score: float = 0.0,
) -> dict[str, Any]:
    """Extract, score, guard, apply, and audit density heading candidates."""
    items = extract_density_items(result)
    items = compute_density_features(items, density_window_items=density_window_items)
    candidates = promote_candidates(
        items,
        size_margin=size_margin,
        short_text_max_chars=short_text_max_chars,
        min_gap_above=min_gap_above,
        min_density_score=min_density_score,
    )
    applied, skipped = apply_promotions(result.document, candidates)
    return {
        "schema": "final-parse-heading-audit/1.0",
        "density_window_items": density_window_items,
        "candidate_count": len(candidates),
        "applied_count": len(applied),
        "skipped_count": len(skipped),
        "heading_candidate_policy": "list_item_only",
        "list_item_density_only_policy": "apply",
        "applied": applied,
        "skipped": skipped,
    }
