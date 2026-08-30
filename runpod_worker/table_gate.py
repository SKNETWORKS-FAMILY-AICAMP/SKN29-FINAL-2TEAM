"""Docling TableFormer parsing plus the validated conservative TableItem gate.

This production pipeline intentionally contains only two stages:

1. Docling PDF parsing with TableFormer ACCURATE and cell matching enabled.
2. The fixed TableItem-only non-table gate validated on 28,885 table crops.

No VLM, LLM, image classifier, TF taxonomy, structural-error repair, missing
slot insertion, span mutation, or alternate TableFormer retry is performed.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from importlib.metadata import version
from pathlib import Path
from typing import Any


DOCLING_VERSION = "2.119.0"
PAGE_RE = re.compile(r"^\s*\d{1,3}\s*$")
DOT_LEADER_RE = re.compile(r"(?:\.{5,}|…{2,})")
TITLE_WORD_RE = re.compile(
    r"(?:message|overview|appendix|introduction|보고서|회사\s*소개|사업\s*소개)",
    re.IGNORECASE,
)
BULLET_RE = re.compile(r"(^|\s)[·•▪■▶►◆◇○●✓✔-](\s|$)")
SENTENCE_RE = re.compile(r"[.!?。]|(?:입니다|한다|됩니다|있습니다|합니다)(?:\s|$)")


def _safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def gate_features(table: dict[str, Any]) -> dict[str, float]:
    """Calculate the exact features used by the frozen gate."""
    data = table.get("data") or {}
    cells = data.get("table_cells") or []
    num_cols = int(data.get("num_cols") or 0)
    num_rows = int(data.get("num_rows") or 0)
    nonempty: list[str] = []
    last_col: list[str] = []
    max_text_len = 0
    largest_span_area = 0

    for cell in cells:
        text = (cell.get("text") or "").strip()
        if not text:
            continue
        nonempty.append(text)
        max_text_len = max(max_text_len, len(text))
        if cell.get("end_col_offset_idx") == num_cols:
            last_col.append(text)

        sr = cell.get("start_row_offset_idx")
        er = cell.get("end_row_offset_idx")
        sc = cell.get("start_col_offset_idx")
        ec = cell.get("end_col_offset_idx")
        if None not in (sr, er, sc, ec):
            span_area = max(int(er) - int(sr), 0) * max(int(ec) - int(sc), 0)
            largest_span_area = max(largest_span_area, span_area)

    provenance = table.get("prov") or []
    bbox = (provenance[0].get("bbox") or {}) if provenance else {}
    bbox_width = abs(float(bbox.get("r", 0)) - float(bbox.get("l", 0)))
    bbox_height = abs(float(bbox.get("t", 0)) - float(bbox.get("b", 0)))

    return {
        "long_cell_ratio": _safe_div(
            sum(len(text) >= 30 for text in nonempty), len(nonempty)
        ),
        "sentence_cell_ratio": _safe_div(
            sum(bool(SENTENCE_RE.search(text)) for text in nonempty), len(nonempty)
        ),
        "bullet_cell_ratio": _safe_div(
            sum(bool(BULLET_RE.search(text)) for text in nonempty), len(nonempty)
        ),
        "last_col_page_number_ratio": _safe_div(
            sum(bool(PAGE_RE.match(text)) for text in last_col), len(last_col)
        ),
        "max_text_len": float(max_text_len),
        "bbox_width": bbox_width,
        "bbox_height": bbox_height,
        "dot_leader_cells": float(
            sum(bool(DOT_LEADER_RE.search(text)) for text in nonempty)
        ),
        "page_only_ratio": _safe_div(
            sum(bool(PAGE_RE.fullmatch(text)) for text in nonempty), len(nonempty)
        ),
        "title_word_cells": float(
            sum(bool(TITLE_WORD_RE.search(text)) for text in nonempty)
        ),
        "largest_cell_grid_ratio": _safe_div(
            largest_span_area, num_rows * num_cols
        ),
    }


def gate_tableitem(table: dict[str, Any]) -> dict[str, Any]:
    """Return the frozen fail-open decision and its complete evidence."""
    features = gate_features(table)
    if features["dot_leader_cells"] >= 1:
        decision, reason = "REJECT", "DOT_LEADER_TOC"
    elif features["page_only_ratio"] >= 0.30 and features["title_word_cells"] >= 2:
        decision, reason = "REJECT", "TITLE_PAGE_LIST"
    elif (
        features["largest_cell_grid_ratio"] >= 1.0
        and features["bbox_height"] <= 33.781
    ):
        decision, reason = "REJECT", "SHORT_SINGLE_CELL_FRAGMENT"
    elif (
        features["bullet_cell_ratio"] >= 1.0
        and features["long_cell_ratio"] >= 0.75
    ):
        decision, reason = "REJECT", "ALL_BULLETED_LONG_TEXT"
    elif (
        features["sentence_cell_ratio"] >= 1.0
        and features["max_text_len"] >= 407
    ):
        decision, reason = "REJECT", "ALL_SENTENCE_EXTREME_TEXT"
    elif (
        features["last_col_page_number_ratio"] >= 1.0
        and features["bbox_width"] >= 542.878
    ):
        decision, reason = "REJECT", "FULL_WIDTH_PAGE_NUMBER_LIST"
    else:
        decision, reason = "PASS", "NO_HIGH_PRECISION_REJECT_PATTERN"
    return {"decision": decision, "reason": reason, "features": features}


def _table_json(table: Any) -> dict[str, Any]:
    """Serialize one Docling TableItem for the JSON-only gate."""
    return table.model_dump(mode="json", by_alias=True, exclude_none=False)


def _bbox_json(table_json: dict[str, Any]) -> dict[str, Any] | None:
    provenance = table_json.get("prov") or []
    return provenance[0].get("bbox") if provenance else None


def apply_table_gate(document: Any) -> dict[str, Any]:
    """Delete rejected TableItems through DoclingDocument's reference-safe API."""
    original_tables = list(document.tables)
    rejected_items = []
    decisions: list[dict[str, Any]] = []
    final_index = 0

    for original_index, table in enumerate(original_tables):
        table_json = _table_json(table)
        result = gate_tableitem(table_json)
        provenance = table_json.get("prov") or []
        page_no = provenance[0].get("page_no") if provenance else None
        accepted_index = final_index if result["decision"] == "PASS" else None
        if accepted_index is not None:
            final_index += 1
        else:
            rejected_items.append(table)
        decisions.append(
            {
                "original_table_index": original_index,
                "original_self_ref": str(table.self_ref),
                "final_table_index": accepted_index,
                "page_no": page_no,
                "bbox": _bbox_json(table_json),
                **result,
            }
        )

    if rejected_items:
        document.delete_items(node_items=rejected_items)

    post_gate_failures = []
    for index, table in enumerate(document.tables):
        check = gate_tableitem(_table_json(table))
        if check["decision"] != "PASS":
            post_gate_failures.append(
                {"table_index": index, "self_ref": str(table.self_ref), **check}
            )
    if post_gate_failures:
        raise RuntimeError(
            "Gate postcondition failed: "
            + json.dumps(post_gate_failures, ensure_ascii=False)
        )

    reason_counts = Counter(
        item["reason"] for item in decisions if item["decision"] == "REJECT"
    )
    return {
        "schema": "final-table-gate-audit/1.0",
        "gate_name": "TABLEITEM_HIGH_PRECISION_FAIL_OPEN_V1",
        "gate_input": "Docling TableItem JSON only",
        "gate_validation": {
            "visually_reviewed_tableitems": 28885,
            "visual_pass_tables": 27647,
            "visual_reject_non_tables": 1238,
            "runtime_rejected_non_tables": 134,
            "runtime_wrongly_rejected_tables": 0,
            "known_visual_non_tables_left_as_pass": 1104,
        },
        "table_count_before": len(original_tables),
        "table_count_after": len(document.tables),
        "pass_count": sum(item["decision"] == "PASS" for item in decisions),
        "reject_count": sum(item["decision"] == "REJECT" for item in decisions),
        "reject_reason_counts": dict(reason_counts),
        "decisions": decisions,
    }


def _save_pass_table_images(document: Any, directory: Path, stem: str) -> int:
    directory.mkdir(parents=True, exist_ok=True)
    count = 0
    for table_number, table in enumerate(document.tables, start=1):
        provenance = table.prov or []
        page_no = provenance[0].page_no if provenance else 0
        image = table.get_image(document)
        if image is None:
            continue
        filename = f"{stem}__p{int(page_no or 0):04d}__t{table_number:03d}.png"
        image.save(directory / filename, format="PNG")
        count += 1
    return count


def parse_and_gate_pdf(
    source_path: Path,
    output_dir: Path,
    *,
    page_range: tuple[int, int] | None = None,
    image_scale: float = 1.5,
    layout_batch_size: int = 16,
    table_batch_size: int = 16,
    queue_max_size: int = 64,
    save_pass_table_images: bool = True,
) -> dict[str, Any]:
    """Parse one PDF, apply the fixed gate, and save production artifacts."""
    import torch
    from docling_core.types.doc import ImageRefMode
    from docling.datamodel.accelerator_options import (
        AcceleratorDevice,
        AcceleratorOptions,
    )
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
    from docling.document_converter import DocumentConverter, PdfFormatOption

    source_path = source_path.resolve()
    if not source_path.is_file() or source_path.suffix.lower() != ".pdf":
        raise FileNotFoundError(source_path)
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU가 필요합니다.")
    if version("docling") != DOCLING_VERSION:
        raise RuntimeError(f"docling=={DOCLING_VERSION}이 필요합니다.")

    output_dir.mkdir(parents=True, exist_ok=True)
    raw_json = output_dir / f"{source_path.stem}.raw.docling.json"
    final_json = output_dir / f"{source_path.stem}.final.docling.json"
    final_markdown = output_dir / f"{source_path.stem}.final.md"
    gate_audit_path = output_dir / f"{source_path.stem}.table_gate.json"
    table_image_dir = output_dir / "table_images"

    options = PdfPipelineOptions()
    options.do_table_structure = True
    options.table_structure_options.mode = TableFormerMode.ACCURATE
    options.table_structure_options.do_cell_matching = True
    options.do_ocr = False
    options.do_picture_classification = False
    options.do_picture_description = False
    options.do_chart_extraction = False
    options.do_code_enrichment = False
    options.do_formula_enrichment = False
    options.generate_page_images = True
    options.generate_table_images = False
    options.generate_picture_images = False
    options.images_scale = image_scale
    options.layout_batch_size = layout_batch_size
    options.table_batch_size = table_batch_size
    options.ocr_batch_size = 1
    options.queue_max_size = queue_max_size
    options.accelerator_options = AcceleratorOptions(device=AcceleratorDevice.CUDA)

    converter = DocumentConverter(
        allowed_formats=[InputFormat.PDF],
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=options)
        },
    )
    convert_kwargs: dict[str, Any] = {}
    if page_range is not None:
        convert_kwargs["page_range"] = page_range
    result = converter.convert(source_path, **convert_kwargs)
    document = result.document
    document.save_as_json(raw_json, image_mode=ImageRefMode.EMBEDDED)

    gate_audit = apply_table_gate(document)
    image_count = 0
    if save_pass_table_images:
        image_count = _save_pass_table_images(
            document, table_image_dir, source_path.stem
        )
    document.save_as_json(final_json, image_mode=ImageRefMode.EMBEDDED)
    final_markdown.write_text(document.export_to_markdown(), encoding="utf-8")

    gate_audit["runtime"] = {
        "docling_version": version("docling"),
        "torch_version": torch.__version__,
        "tableformer_mode": "ACCURATE",
        "do_cell_matching": True,
        "do_ocr": False,
        "image_scale": image_scale,
        "layout_batch_size": layout_batch_size,
        "table_batch_size": table_batch_size,
        "queue_max_size": queue_max_size,
        "same_configuration_retry": False,
    }
    gate_audit["source_pdf"] = str(source_path)
    gate_audit["outputs"] = {
        "raw_docling_json": str(raw_json),
        "final_docling_json": str(final_json),
        "final_markdown": str(final_markdown),
        "pass_table_image_dir": str(table_image_dir) if save_pass_table_images else None,
        "pass_table_image_count": image_count,
    }
    gate_audit_path.write_text(
        json.dumps(gate_audit, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return gate_audit


def run(
    source: Path,
    output_root: Path,
    *,
    page_range: tuple[int, int] | None = None,
    image_scale: float = 1.5,
    layout_batch_size: int = 16,
    table_batch_size: int = 16,
    queue_max_size: int = 64,
    save_pass_table_images: bool = True,
) -> list[dict[str, Any]]:
    """Process one PDF or every PDF recursively below a source directory."""
    source = source.resolve()
    if source.is_file():
        pdf_paths = [source]
    elif source.is_dir():
        pdf_paths = sorted(
            {path.resolve() for path in source.rglob("*.pdf") if path.is_file()}
        )
    else:
        raise FileNotFoundError(source)
    if not pdf_paths:
        raise RuntimeError(f"PDF 파일이 없습니다: {source}")

    results = []
    for pdf_path in pdf_paths:
        document_output = output_root / f"final_table_parsing_{pdf_path.stem}"
        results.append(
            parse_and_gate_pdf(
                pdf_path,
                document_output,
                page_range=page_range,
                image_scale=image_scale,
                layout_batch_size=layout_batch_size,
                table_batch_size=table_batch_size,
                queue_max_size=queue_max_size,
                save_pass_table_images=save_pass_table_images,
            )
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="PDF 파일 또는 PDF 디렉터리")
    parser.add_argument("output_root", type=Path)
    parser.add_argument("--page-start", type=int)
    parser.add_argument("--page-end", type=int)
    parser.add_argument("--image-scale", type=float, default=1.5)
    parser.add_argument("--layout-batch-size", type=int, default=16)
    parser.add_argument("--table-batch-size", type=int, default=16)
    parser.add_argument("--queue-max-size", type=int, default=64)
    parser.add_argument("--no-table-images", action="store_true")
    args = parser.parse_args()
    if (args.page_start is None) != (args.page_end is None):
        parser.error("--page-start와 --page-end는 함께 지정해야 합니다.")
    page_range = (
        (args.page_start, args.page_end)
        if args.page_start is not None
        else None
    )
    results = run(
        args.source,
        args.output_root,
        page_range=page_range,
        image_scale=args.image_scale,
        layout_batch_size=args.layout_batch_size,
        table_batch_size=args.table_batch_size,
        queue_max_size=args.queue_max_size,
        save_pass_table_images=not args.no_table_images,
    )
    print(
        json.dumps(
            [
                {
                    "source_pdf": result["source_pdf"],
                    "table_count_before": result["table_count_before"],
                    "table_count_after": result["table_count_after"],
                    "reject_count": result["reject_count"],
                }
                for result in results
            ],
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
