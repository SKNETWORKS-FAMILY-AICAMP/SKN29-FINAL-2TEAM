from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import hashlib
import os
from pathlib import Path
import re
import tempfile
from typing import Any

import requests


CONTROL_PATTERN = re.compile(r"<end_of_(?:utterance|turn|text)?[^>\s]*>?", re.I)
EXPECTED_DIMENSION = 768
SUPPORTED_MIME_TYPES = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}


class PipelineError(Exception):
    pass


class PipelineConfigurationError(PipelineError):
    pass


class InvalidDocumentError(PipelineError):
    pass


class ChunkValidationError(PipelineError):
    pass


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise PipelineConfigurationError(f"필수 환경변수가 없습니다: {name}")
    return value


@lru_cache(maxsize=1)
def embedding_model():
    import torch
    from sentence_transformers import SentenceTransformer

    model_id = _required_env("EMBEDDING_MODEL")
    device = _required_env("EMBEDDING_DEVICE")
    if device != "cuda":
        raise PipelineConfigurationError("RunPod Worker는 cuda 장치만 허용합니다.")
    if not torch.cuda.is_available():
        raise PipelineConfigurationError("CUDA를 사용할 수 없습니다.")
    _required_env("HF_TOKEN")
    return SentenceTransformer(model_id, device=device, token=os.environ["HF_TOKEN"])


@lru_cache(maxsize=1)
def converter():
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.image_classification_engine_options import (
        TransformersImageClassificationEngineOptions,
    )
    from docling.datamodel.pipeline_options import (
        ConvertPipelineOptions,
        DocumentPictureClassifierOptions,
        EasyOcrOptions,
        HeadingHierarchyOptions,
        OcrMode,
        PdfPipelineOptions,
    )
    from docling.document_converter import DocumentConverter, PdfFormatOption, WordFormatOption

    classifier = DocumentPictureClassifierOptions(
        engine_options=TransformersImageClassificationEngineOptions(compile_model=False)
    )
    pdf = PdfPipelineOptions(
        do_picture_classification=True,
        picture_classification_options=classifier,
        do_picture_description=True,
        do_chart_extraction=True,
        force_backend_text=True,
        images_scale=1.0,
        ocr_options=EasyOcrOptions(
            lang=["ko", "en"], mode=OcrMode.LAYOUT_REGIONS, force_full_page_ocr=False
        ),
        heading_hierarchy_options=HeadingHierarchyOptions(enabled=True),
    )
    docx = ConvertPipelineOptions(
        do_picture_classification=True,
        picture_classification_options=classifier,
        do_picture_description=True,
        do_chart_extraction=True,
    )
    return DocumentConverter(
        allowed_formats=[InputFormat.PDF, InputFormat.DOCX],
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pdf),
            InputFormat.DOCX: WordFormatOption(pipeline_options=docx),
        },
    )


def _clean(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _model_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_none=True)
    if hasattr(value, "export_json_dict"):
        return value.export_json_dict()
    if isinstance(value, dict):
        return value
    raise InvalidDocumentError(f"Docling 값을 직렬화할 수 없습니다: {type(value).__name__}")


def _coordinates(cell: dict[str, Any]) -> tuple[int, int, int, int]:
    return (
        int(cell.get("start_row_offset_idx", 0)),
        int(cell.get("end_row_offset_idx", 0)),
        int(cell.get("start_col_offset_idx", 0)),
        int(cell.get("end_col_offset_idx", 0)),
    )


def _area(cell: dict[str, Any]) -> int:
    sr, er, sc, ec = _coordinates(cell)
    return max(1, er - sr) * max(1, ec - sc)


def _covers(cell: dict[str, Any], row: int, col: int) -> bool:
    sr, er, sc, ec = _coordinates(cell)
    return sr <= row < er and sc <= col < ec


def _best_cell(cells: list[dict[str, Any]], row: int, col: int, *, value: bool = False):
    matches = [c for c in cells if _covers(c, row, col)]
    if value:
        matches.sort(
            key=lambda c: (
                bool(c.get("column_header") or c.get("row_header")),
                _area(c),
                _coordinates(c),
            )
        )
    else:
        matches.sort(key=lambda c: (_area(c), _coordinates(c)))
    return matches[0] if matches else None


def _table_pages(table: dict[str, Any]) -> list[int]:
    return sorted(
        {
            int(p["page_no"])
            for p in table.get("prov") or []
            if isinstance(p.get("page_no"), int)
        }
    )


def _table_ref(table: dict[str, Any], index: int) -> str:
    ref = table.get("self_ref")
    if not ref:
        raise InvalidDocumentError(f"tables[{index}]에 self_ref가 없습니다.")
    return str(ref)


def _product_records(table: dict[str, Any], index: int) -> list[dict[str, Any]]:
    data = table.get("data") or {}
    cells = data.get("table_cells") or []
    rows, cols = int(data.get("num_rows") or 0), int(data.get("num_cols") or 0)
    model_columns: list[int] = []
    headers: list[tuple[int, str]] = []
    for col in range(cols):
        cell = _best_cell(cells, 0, col)
        text = _clean(cell.get("text")) if cell else ""
        if cell and cell.get("column_header") and text.casefold() == "model":
            model_columns.append(col)
    if len(model_columns) != 1:
        return []
    model_col = model_columns[0]
    for col in range(model_col + 1, cols):
        cell = _best_cell(cells, 0, col)
        text = _clean(cell.get("text")) if cell else ""
        if cell and cell.get("column_header") and text:
            headers.append((col, text))
    if not headers:
        return []
    first_data_col = model_col + 1
    result = []
    for product_col, product in headers:
        attributes = []
        for row in range(1, rows):
            value_cell = _best_cell(cells, row, product_col, value=True)
            value = _clean(value_cell.get("text")) if value_cell else ""
            descriptors = []
            for col in range(first_data_col):
                cell = _best_cell(cells, row, col)
                text = _clean(cell.get("text")) if cell else ""
                if text and text.casefold() != "model" and text not in descriptors:
                    descriptors.append(text)
            descriptor = " / ".join(descriptors)
            if value:
                attributes.append(
                    {
                        "name": descriptor or f"row_{row}",
                        "value": value,
                        "source_row_index": row,
                        "source_product_col": product_col,
                        "shared_value": _area(value_cell) > 1 if value_cell else False,
                        "cell_ref": _coordinates(value_cell) if value_cell else None,
                    }
                )
        if attributes:
            text = "\n".join(
                [f"제품 모델: {product}"]
                + [f"{a['name']}: {a['value']}" for a in attributes]
            )
            result.append(
                {
                    "text": text,
                    "attributes": attributes,
                    "meta": {
                        "table_index": index,
                        "table_ref": _table_ref(table, index),
                        "orientation": "products_in_columns",
                        "product": product,
                        "source_product_col": product_col,
                    },
                    "pages": _table_pages(table),
                }
            )
    return result


def _generic_row_records(table: dict[str, Any], index: int) -> list[dict[str, Any]]:
    data = table.get("data") or {}
    cells = data.get("table_cells") or []
    rows, cols = int(data.get("num_rows") or 0), int(data.get("num_cols") or 0)
    if rows <= 0 or cols <= 0 or not cells:
        raise InvalidDocumentError(f"표 {_table_ref(table, index)}의 셀 구조가 비어 있습니다.")
    header_values = []
    for col in range(cols):
        cell = _best_cell(cells, 0, col)
        header_values.append(_clean(cell.get("text")) if cell else f"column_{col}")
    result = []
    start_row = 1 if any(header_values) and rows > 1 else 0
    for row in range(start_row, rows):
        values = []
        structured = []
        for col in range(cols):
            cell = _best_cell(cells, row, col, value=True)
            value = _clean(cell.get("text")) if cell else ""
            if value:
                label = header_values[col] or f"column_{col}"
                values.append(f"{label}: {value}")
                structured.append({"header": label, "value": value, "source_col": col})
        if values:
            result.append(
                {
                    "text": "\n".join(values),
                    "attributes": structured,
                    "meta": {
                        "table_index": index,
                        "table_ref": _table_ref(table, index),
                        "orientation": "generic_table_rows",
                        "source_row_index": row,
                        "headers": header_values,
                    },
                    "pages": _table_pages(table),
                }
            )
    if not result:
        raise InvalidDocumentError(f"표 {_table_ref(table, index)}에서 값 행을 만들 수 없습니다.")
    return result


def _without_tables(raw: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(raw)
    refs = {str(t["self_ref"]) for t in result.get("tables") or [] if t.get("self_ref")}
    body = result.get("body") or {}
    body["children"] = [c for c in body.get("children") or [] if c.get("$ref") not in refs]
    for group in result.get("groups") or []:
        group["children"] = [c for c in group.get("children") or [] if c.get("$ref") not in refs]
    result["tables"] = []
    return result


def _document_order(raw: dict[str, Any]) -> dict[str, int]:
    groups = {str(g.get("self_ref")): g for g in raw.get("groups") or [] if g.get("self_ref")}
    order: dict[str, int] = {}
    visiting: set[str] = set()

    def visit(ref: str):
        if ref in order:
            return
        order[ref] = len(order)
        group = groups.get(ref)
        if not group or ref in visiting:
            return
        visiting.add(ref)
        for child in group.get("children") or []:
            if child.get("$ref"):
                visit(str(child["$ref"]))
        visiting.remove(ref)

    for child in (raw.get("body") or {}).get("children") or []:
        if child.get("$ref"):
            visit(str(child["$ref"]))
    return order


def _chunk_document(document: Any, max_tokens: int, merge_peers: bool) -> tuple[list[dict], list[dict]]:
    from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
    from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
    from docling_core.types.doc import DoclingDocument

    model = embedding_model()
    raw = _model_dict(document)
    order = _document_order(raw)
    token_counter = HuggingFaceTokenizer(tokenizer=model.tokenizer, max_tokens=max_tokens)
    hybrid = HybridChunker(
        tokenizer=token_counter, max_tokens=max_tokens, merge_peers=merge_peers
    )
    text_document = DoclingDocument.model_validate(_without_tables(raw))
    chunks: list[dict] = []
    for item in hybrid.chunk(dl_doc=text_document):
        meta = _model_dict(getattr(item, "meta", None))
        refs = [str(x["self_ref"]) for x in meta.get("doc_items") or [] if x.get("self_ref")]
        text = CONTROL_PATTERN.sub("", hybrid.contextualize(chunk=item)).strip()
        if not refs:
            raise ChunkValidationError("Hybrid Chunk에 source reference가 없습니다.")
        chunks.append(
            {
                "chunk_type": "text",
                "text": text,
                "raw_text": str(getattr(item, "text", "")),
                "source_refs": refs,
                "pages": sorted(
                    {
                        int(p["page_no"])
                        for d in meta.get("doc_items") or []
                        for p in d.get("prov") or []
                        if isinstance(p.get("page_no"), int)
                    }
                ),
                "primary_order": min(order.get(r, 10**9) for r in refs),
                "meta": meta,
            }
        )
    diagnostics = []
    for index, table in enumerate(raw.get("tables") or []):
        records = _product_records(table, index)
        strategy = "structured_product_columns"
        if not records:
            records = _generic_row_records(table, index)
            strategy = "generic_table_rows"
        diagnostics.append(
            {"table_ref": _table_ref(table, index), "strategy": strategy, "records": len(records)}
        )
        for record in records:
            ref = record["meta"]["table_ref"]
            chunks.append(
                {
                    "chunk_type": "table",
                    "text": record["text"],
                    "raw_text": None,
                    "source_refs": [ref],
                    "pages": record["pages"],
                    "primary_order": order.get(ref, 10**9),
                    "meta": record["meta"] | {"attributes": record["attributes"]},
                }
            )
    # A cell/row is atomic. Oversized records fail rather than being truncated.
    for chunk in chunks:
        chunk["text"] = CONTROL_PATTERN.sub("", chunk["text"]).strip()
        chunk["token_count"] = token_counter.count_tokens(chunk["text"])
        if not chunk["text"]:
            raise ChunkValidationError("빈 embedding_text가 생성되었습니다.")
        if chunk["token_count"] > max_tokens:
            raise ChunkValidationError(
                f"원자 Chunk가 token 상한을 초과했습니다: {chunk['token_count']} > {max_tokens}"
            )
    chunks.sort(
        key=lambda c: (
            c["primary_order"],
            0 if c["chunk_type"] == "text" else 1,
            c["meta"].get("table_index", -1),
            c["meta"].get("source_row_index", -1),
            c["meta"].get("source_product_col", -1),
        )
    )
    for sequence, chunk in enumerate(chunks):
        chunk["sequence"] = sequence
        chunk["local_chunk_key"] = f"stable-chunk-{sequence:06d}"
    return chunks, diagnostics


def _blocks_for_chunks(document: Any, chunks: list[dict]) -> list[dict]:
    raw = _model_dict(document)
    items: dict[str, dict] = {}
    for collection in ("texts", "tables", "pictures", "key_value_items"):
        for item in raw.get(collection) or []:
            ref = item.get("self_ref")
            if ref:
                items[str(ref)] = item
    refs = []
    for chunk in chunks:
        for ref in chunk["source_refs"]:
            if ref not in refs:
                refs.append(ref)
    blocks = []
    for sequence, ref in enumerate(refs):
        item = items.get(ref)
        if item is None:
            raise ChunkValidationError(f"source reference를 Docling 원문에서 찾지 못했습니다: {ref}")
        content = _clean(item.get("text") or item.get("orig"))
        if not content and ref.startswith("#/tables/"):
            content = "표 구조 데이터"
        blocks.append(
            {
                "local_block_key": f"block-{sequence:06d}",
                "source_ref": ref,
                "block_type": "TABLE" if ref.startswith("#/tables/") else str(item.get("label", "PARAGRAPH")).upper(),
                "page": next(
                    (p.get("page_no") for p in item.get("prov") or [] if p.get("page_no") is not None),
                    None,
                ),
                "heading_path": [],
                "content": content or next(c["text"] for c in chunks if ref in c["source_refs"]),
                "sequence": sequence,
                "src_locator": {"source_ref": ref, "prov": item.get("prov") or []},
                "struct_content": item if ref.startswith("#/tables/") else None,
            }
        )
    return blocks


def _download(input_data: dict[str, Any]) -> tuple[Path, str]:
    source_url = str(input_data.get("source_url") or "").strip()
    mime_type = str(input_data.get("mime_type") or "").strip()
    if not source_url.startswith("https://"):
        raise InvalidDocumentError("source_url은 외부 접근 가능한 HTTPS URL이어야 합니다.")
    suffix = SUPPORTED_MIME_TYPES.get(mime_type)
    if suffix is None:
        raise InvalidDocumentError(f"지원하지 않는 MIME type입니다: {mime_type}")
    response = requests.get(source_url, timeout=(10, 180), allow_redirects=False)
    response.raise_for_status()
    data = response.content
    if not data:
        raise InvalidDocumentError("다운로드한 문서가 비어 있습니다.")
    path = Path(tempfile.mkstemp(suffix=suffix)[1])
    path.write_bytes(data)
    return path, f"sha256:{hashlib.sha256(data).hexdigest()}"


def process_document(input_data: dict[str, Any]) -> dict[str, Any]:
    doc_id = str(input_data.get("doc_id") or "").strip()
    revision = str(input_data.get("revision") or "").strip()
    if not doc_id or not revision:
        raise InvalidDocumentError("doc_id와 revision이 필요합니다.")
    max_tokens = int(input_data.get("max_tokens") or 0)
    if not 1 <= max_tokens <= 2048:
        raise InvalidDocumentError("max_tokens는 1~2048 범위여야 합니다.")
    merge_peers = input_data.get("merge_peers")
    if not isinstance(merge_peers, bool):
        raise InvalidDocumentError("merge_peers는 boolean이어야 합니다.")

    path, content_hash = _download(input_data)
    try:
        result = converter().convert(path)
        document = result.document
        chunks, diagnostics = _chunk_document(document, max_tokens, merge_peers)
        blocks = _blocks_for_chunks(document, chunks)
        block_by_ref = {b["source_ref"]: b["local_block_key"] for b in blocks}
        texts = [c["text"] for c in chunks]
        vectors = embedding_model().encode_document(
            texts, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False
        )
        if vectors.shape != (len(chunks), EXPECTED_DIMENSION):
            raise ChunkValidationError(
                f"임베딩 차원이 올바르지 않습니다: {vectors.shape}; expected (*, 768)"
            )
        for chunk, vector in zip(chunks, vectors, strict=True):
            chunk["local_block_key"] = block_by_ref[chunk["source_refs"][0]]
            chunk["embedding"] = vector.astype(float).tolist()
        return {
            "schema_version": "runpod-document-result-1.0",
            "doc_id": doc_id,
            "revision": revision,
            "content_hash": content_hash,
            "parser_status": str(result.status),
            "embedding_model": _required_env("EMBEDDING_MODEL"),
            "embedding_dimension": EXPECTED_DIMENSION,
            "chunker_version": "stable-structured-1.0",
            "blocks": blocks,
            "chunks": chunks,
            "validation": {"passed": True, "table_diagnostics": diagnostics},
        }
    finally:
        path.unlink(missing_ok=True)


def embed_queries(input_data: dict[str, Any]) -> dict[str, Any]:
    texts = input_data.get("texts")
    if not isinstance(texts, list) or not texts or not all(isinstance(x, str) and x.strip() for x in texts):
        raise InvalidDocumentError("비어 있지 않은 texts 문자열 배열이 필요합니다.")
    if len(texts) > 20:
        raise InvalidDocumentError("한 요청에서 검색 질의는 최대 20개입니다.")
    vectors = embedding_model().encode_query(
        texts, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False
    )
    if vectors.shape != (len(texts), EXPECTED_DIMENSION):
        raise ChunkValidationError(
            f"검색 임베딩 차원이 올바르지 않습니다: {vectors.shape}; expected (*, 768)"
        )
    return {
        "embedding_model": _required_env("EMBEDDING_MODEL"),
        "embedding_dimension": EXPECTED_DIMENSION,
        "embeddings": [v.astype(float).tolist() for v in vectors],
    }
