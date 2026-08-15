from __future__ import annotations

from functools import lru_cache
import hashlib
import os
from pathlib import Path
import re
import tempfile
import zlib
from typing import Any

import requests

from density_heading_correction import promote_headings_by_density


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


#: 텍스트 레이어가 있다고 볼 최소 텍스트 연산자 수.
#:
#: PDF 안의 압축 스트림에서 Tj/TJ(문자 그리기) 연산자를 센다. 스캔본은 페이지가
#: 통째로 이미지라 이 값이 0에 가깝고, 프로그램으로 만든 문서는 수천이 나온다.
#: 실측: 제안요청서 5,012 · 용역제안서 35,141 · 발표자료 1,009 · 스캔본 0.
TEXT_OPERATOR_THRESHOLD = 200

#: PDF 안의 압축 스트림 한 덩어리.
STREAM_PATTERN = re.compile(rb"stream[\r\n]+(.*?)endstream", re.S)


def _has_text_layer(path: Path) -> bool:
    """PDF 가 자기 텍스트를 들고 있는가.

    들고 있으면 OCR 을 끈다. **OCR 이 멀쩡한 텍스트를 덮어써서 망가뜨렸다**
    (2026-08-05). 제안요청서 본문이 「중도탈락을」→「중도달락올」,
    「프로젝트」→「프로적트」, 「솔루션」→「슬루선」처럼 자모 단위로 치환돼
    적재됐고, 그 글을 업무 추출 에이전트가 읽었다. 같은 PDF 를 pypdf 로 읽으면
    원문이 깨끗하게 나온다.

    스캔본은 반대로 OCR 없이는 아무것도 못 읽으므로 문서마다 갈라야 한다.
    외부 의존성 없이 표준 라이브러리만으로 판정한다.
    """

    try:
        raw = path.read_bytes()
    except OSError:
        return False
    operators = 0
    for match in STREAM_PATTERN.finditer(raw):
        try:
            operators += len(re.findall(rb"(?:Tj|TJ)", zlib.decompress(match.group(1))))
        except zlib.error:
            continue
        if operators >= TEXT_OPERATOR_THRESHOLD:
            return True
    return operators >= TEXT_OPERATOR_THRESHOLD


@lru_cache(maxsize=2)
def converter(use_ocr: bool = True):
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

    # ⚠ 아래 이미지 계열 셋은 **워커 디스크를 많이 쓴다.** Docling 이 Granite Vision
    # 차트 모델과 이미지 설명 VLM 을 런타임에 HuggingFace 에서 내려받는데, 수 GB다.
    # 2026-08-04 기본 디스크로 DOCX 한 건을 돌렸다가 파싱 전에 죽었다:
    #
    #   OSError: I/O error: No space left on device (os error 28)
    #     └ docling/models/stages/chart_extraction/granite_vision.py
    #
    # Endpoint 의 Container Disk 를 키워서 해결했다. 워커를 새로 만들 때 이 값을
    # 줄이면 같은 곳에서 다시 죽는다.
    #
    # Dockerfile 이 모델을 굽지 않고 Cached model 에도 없어서, **최소 Worker 0 이면
    # 워커가 새로 뜰 때마다 다시 받는다**(Idle timeout 300초). 콜드 스타트를 줄이려면
    # Network Volume 에 HF 캐시를 두거나 이미지에 구워야 한다.
    classifier = DocumentPictureClassifierOptions(
        engine_options=TransformersImageClassificationEngineOptions(compile_model=False)
    )
    # `force_backend_text=True` 로도 OCR 결과가 본문을 덮었다. 그래서 텍스트
    # 레이어가 있는 PDF 는 아예 OCR 을 끈다 — 판정은 `_has_text_layer` 가 한다.
    pdf = PdfPipelineOptions(
        do_picture_classification=True,
        picture_classification_options=classifier,
        do_picture_description=True,
        do_chart_extraction=True,
        force_backend_text=True,
        images_scale=1.0,
        do_ocr=use_ocr,
        ocr_options=EasyOcrOptions(
            lang=["ko", "en"], mode=OcrMode.LAYOUT_REGIONS, force_full_page_ocr=False
        ),
        heading_hierarchy_options=HeadingHierarchyOptions(enabled=True),
        # density_heading_correction이 backend/OCR cell(parsed_page.textline_cells)로
        # 실측 글자 높이를 재려면 필수 — 없으면 item bbox 전체 높이로 대체돼 여러 줄
        # 문단에서 부풀려진다. heading_hierarchy_options.use_style(글꼴 기반 제목 깊이
        # 추론)도 이 옵션 없이는 조용히 생략된다.
        generate_parsed_pages=True,
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


def _table_refs(raw: dict[str, Any]) -> set[str]:
    """이 문서의 표 self_ref 모음. 본문 청크에서 표를 걸러낼 때 쓴다."""

    return {str(t["self_ref"]) for t in raw.get("tables") or [] if t.get("self_ref")}


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

    model = embedding_model()
    raw = _model_dict(document)
    order = _document_order(raw)
    table_refs = _table_refs(raw)
    token_counter = HuggingFaceTokenizer(tokenizer=model.tokenizer, max_tokens=max_tokens)
    hybrid = HybridChunker(
        tokenizer=token_counter, max_tokens=max_tokens, merge_peers=merge_peers
    )

    # 원본 문서를 그대로 청킹하고 표에서 나온 청크만 뒤에서 걸러낸다(2026-08-04).
    #
    # 예전에는 표를 지운 사본을 만들어 넘겼는데, `tables` 를 비워도 트리 어딘가에
    # `#/tables/N` 참조가 남아 docling 이 그것을 인덱스로 풀다 죽었다:
    #
    #   IndexError: list index out of range
    #     └ docling_core/types/doc/document.py  validate_tree(self.body)
    #
    # body 와 groups 의 children 만 청소했는데 texts·pictures 의 children 에도
    # 표가 달릴 수 있었다. 트리를 수술해서 전부 맞추는 것보다, 손대지 않고 결과를
    # 거르는 쪽이 깨질 구석이 없다.
    chunks: list[dict] = []
    for item in hybrid.chunk(dl_doc=document):
        meta = _model_dict(getattr(item, "meta", None))
        refs = [str(x["self_ref"]) for x in meta.get("doc_items") or [] if x.get("self_ref")]
        text = CONTROL_PATTERN.sub("", hybrid.contextualize(chunk=item)).strip()
        if not refs:
            raise ChunkValidationError("Hybrid Chunk에 source reference가 없습니다.")
        # 표만으로 이뤄진 청크는 버린다 — 아래 구조 보존 청킹이 같은 표를 행/제품
        # 단위로 다시 만든다. 표와 본문이 한 청크에 섞인 경우는 남긴다. 버리면
        # 본문까지 사라지고, 그쪽 손실이 표가 한 번 더 들어가는 것보다 크다.
        if all(ref in table_refs for ref in refs):
            continue
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
    chunks, dropped = _screen_oversized(
        chunks, table_refs, max_tokens, token_counter.count_tokens
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
    return chunks, diagnostics, dropped


def _screen_oversized(
    chunks: list[dict],
    table_refs: set[str],
    max_tokens: int,
    count_tokens: Any,
) -> tuple[list[dict], list[dict]]:
    """한도를 넘는 청크를 걸러낸다. 표가 걸렸는지에 따라 처리가 갈린다.

    표는 더 쪼갤 수 없다. 행 하나를 반으로 자르면 열과 값이 어긋나 검색에 잡혀도
    읽을 수 없는 조각이 되고, 뒤를 잘라 버리면 뒷열이 조용히 사라진다. 그렇다고
    문서 전체를 실패시키면 넘친 표 한 줄 때문에 본문 수백 블록을 함께 잃는다 —
    실제로 제안요청서 한 건이 749 토큰짜리 청크 하나 때문에 통째로 버려졌다
    (2026-08-04). 그래서 그 청크만 빼고 무엇을 뺐는지 남긴다.

    표가 안 걸렸는데 넘쳤다면 그대로 실패시킨다. HybridChunker 는 본문을 한도
    안에서 쪼개도록 되어 있고, 그게 안 지켜지는 것은 조용히 버릴 일이 아니라
    고칠 일이다.
    """

    kept: list[dict] = []
    dropped: list[dict] = []
    for chunk in chunks:
        chunk["text"] = CONTROL_PATTERN.sub("", chunk["text"]).strip()
        chunk["token_count"] = count_tokens(chunk["text"])
        if not chunk["text"]:
            raise ChunkValidationError("빈 embedding_text가 생성되었습니다.")
        if chunk["token_count"] <= max_tokens:
            kept.append(chunk)
            continue

        touches_table = chunk["chunk_type"] == "table" or any(
            ref in table_refs for ref in chunk["source_refs"]
        )
        if not touches_table:
            raise ChunkValidationError(
                f"원자 Chunk가 token 상한을 초과했습니다: {chunk['token_count']} > {max_tokens}"
            )
        dropped.append(
            {
                "chunk_type": chunk["chunk_type"],
                "token_count": chunk["token_count"],
                "limit": max_tokens,
                "source_refs": chunk["source_refs"],
                "preview": chunk["text"][:160],
            }
        )

    if not kept:
        raise ChunkValidationError("한도를 넘지 않는 Chunk가 하나도 없습니다.")
    return kept, dropped


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
        # 스캔본만 OCR 한다. 텍스트가 있는 문서에 OCR 을 걸면 멀쩡한 본문이 깨진다.
        use_ocr = not _has_text_layer(path)
        result = converter(use_ocr).convert(path)
        document = result.document
        # 밀도 기반 헤딩 승격(제자리 수정): 레이아웃 모델이 text/list_item으로 잘못
        # 분류한 실제 헤딩을 section_header로 바꿔치기한다. 청킹은 이 승격이 반영된
        # document를 그대로 넘겨받으므로, HybridChunker가 만드는 chunk.meta.headings도
        # 승격 결과를 따라간다.
        promoted_headings = promote_headings_by_density(result)
        chunks, diagnostics, dropped = _chunk_document(document, max_tokens, merge_peers)
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
            "validation": {
                "passed": True,
                "table_diagnostics": diagnostics,
                # 한도를 넘어 버려진 청크. 비어 있지 않으면 그 문서의 일부가
                # 검색에 안 잡힌다는 뜻이라 결과에 실어 보낸다.
                "dropped_chunks": dropped,
                # 밀도 기반으로 section_header로 승격된 항목 수. 0이어도 정상(해당
                # 패턴의 오분류 헤딩이 없었다는 뜻)이라 오류로 취급하지 않는다.
                "promoted_heading_count": len(promoted_headings),
            },
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
