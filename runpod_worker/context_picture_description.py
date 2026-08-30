"""Retrieval-oriented, context-aware Docling picture description stage."""

from __future__ import annotations

import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image
from pydantic import BaseModel, ConfigDict
from docling_core.types.doc import (
    DescriptionMetaField,
    ImageRefMode,
    PictureClassificationLabel,
    PictureItem,
)
from docling_core.types.doc.document import ContentLayer
from docling.backend.json.docling_json_backend import DoclingJSONBackend
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    ConvertPipelineOptions,
    PictureDescriptionVlmEngineOptions,
)
from docling.document_converter import DocumentConverter, FormatOption
from docling.models.base_model import BaseModelWithOptions, GenericEnrichmentModel
from docling.models.stages.picture_description.picture_description_vlm_engine_model import (
    PictureDescriptionVlmEngineModel,
)
from docling.pipeline.simple_pipeline import SimplePipeline
from docling.utils.profiling import ProfilingScope, TimeRecorder
from docling.utils.utils import chunkify


TECHNICAL_PICTURE_PROMPT = """
이미지에 보이는 대상, 글자, 숫자, 단위, 기호와 위치·연결·방향을 설명하라.
완결된 한국어 문장 1~3개로 작성하고 제품명·모델명·기호는 보이는 표기를 유지하라.
설명 본문만 출력하고 제목, 머리말, 목록, JSON은 출력하지 마라.
보이지 않는 내용은 쓰지 말고 같은 내용을 반복하지 마라.
""".strip()

CHART_LABELS = {
    "bar_chart", "box_plot", "line_chart", "pie_chart",
    "scatter_plot", "other_chart",
}
FLOW_LABELS = {"flow_chart"}
DRAWING_LABELS = {"engineering_drawing"}
SCREENSHOT_LABELS = {"screenshot_from_computer", "screenshot_from_manual"}
MAP_LABELS = {"geographical_map", "topographical_map"}
PHOTO_LABELS = {"photograph"}
CHEMISTRY_LABELS = {"chemistry_structure"}
TABLE_LABELS = {"table"}
ROUTING_PROMPTS = {
    "chart": "읽히는 제목, 축, 단위, 범례, 계열, 주요 값과 증가·감소를 설명하라.",
    "flow": "노드 글자, 화살표 방향, 분기·병합과 진행 순서를 설명하라.",
    "drawing": "장치·부품명, 기호, 치수, 단위, callout, 연결과 방향을 설명하라.",
    "screenshot": "화면 제목, 메뉴, 버튼, 입력값, 상태와 선택 영역을 설명하라.",
    "map": "지도 제목, 지명, 범례, 축척, 방향, 경계, 경로와 표시 지점을 설명하라.",
    "photo": "주요 피사체, 행동, 배경과 보이는 표지·라벨을 설명하라.",
    "chemistry": "보이는 원자, 결합, 작용기, 입체·반응 표시와 구조명을 설명하라.",
    "table": "표의 제목, 행·열 머리글, 단위, 항목 관계와 주요 값을 설명하라.",
    "generic": "주요 대상, 보이는 글자와 대상 사이의 위치·연결 관계를 설명하라.",
}


def select_routing_prompt(class_name: str) -> tuple[str, str]:
    if class_name in CHART_LABELS:
        route = "chart"
    elif class_name in FLOW_LABELS:
        route = "flow"
    elif class_name in DRAWING_LABELS:
        route = "drawing"
    elif class_name in SCREENSHOT_LABELS:
        route = "screenshot"
    elif class_name in MAP_LABELS:
        route = "map"
    elif class_name in PHOTO_LABELS:
        route = "photo"
    elif class_name in CHEMISTRY_LABELS:
        route = "chemistry"
    elif class_name in TABLE_LABELS:
        route = "table"
    else:
        route = "generic"
    return route, ROUTING_PROMPTS[route]


ALLOW_LABELS = {
    "bar_chart", "box_plot", "flow_chart", "line_chart", "pie_chart",
    "scatter_plot", "other_chart", "photograph", "chemistry_structure",
    "engineering_drawing", "screenshot_from_computer", "screenshot_from_manual",
    "geographical_map", "topographical_map", "calendar", "table", "other",
}
DENY_LABELS = {
    "full_page_image", "page_thumbnail", "bar_code", "icon", "logo",
    "qr_code", "signature", "stamp", "crossword_puzzle", "music",
}


class FinalPictureElement(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    item: PictureItem
    image: Image.Image
    context_payload: dict
    class_name: str
    confidence: float


class ContextPicturePipelineOptions(ConvertPipelineOptions):
    picture_description_options: PictureDescriptionVlmEngineOptions
    context_max_chars: int = 1200
    surrounding_context_max_chars: int = 500
    vlm_max_image_side: int = 1280
    vlm_batch_size: int = 4
    allow_labels: set[str]
    deny_labels: set[str]
    min_confidence: float = 0.5


class FinalPictureDescriptionModel(
    GenericEnrichmentModel[FinalPictureElement], BaseModelWithOptions
):
    elements_batch_size = 4
    EXCLUDED_CONTEXT_LABELS = {"page_header", "page_footer", "page_number"}
    CHART_LABELS = {
        "bar_chart", "box_plot", "line_chart", "pie_chart",
        "scatter_plot", "other_chart",
    }
    PROMPT_LEAK_TERMS = (
        "Docling 문서 읽기 순서", "클래스별 설명 지침", "컨텍스트 선택 기준",
        "보이는 텍스트, 수치, 단위", "이미지 분류 시각 요소로서",
        "이미지 유형:", "관찰 항목:", "direct_context", "structural_context",
        "surrounding_context", "JSON 내부 문장", "제공된 보조 문맥",
        "프롬프트", "지시사항",
    )
    INVALID_RESPONSE_TERMS = (
        "이미지 분류", "설명할 수 없습니다", "이미지가 보이지 않습니다",
        "I can't provide", "not visible",
    )
    PHOTO_HALLUCINATION_TERMS = (
        "태어났", "사망했", "살고 있", "국적", "정치인",
        "30대", "40대", "50대",
    )

    def __init__(self, *, options):
        self.options = options
        self.elements_batch_size = max(1, int(options.vlm_batch_size))
        self.picture_description_model = PictureDescriptionVlmEngineModel(
            enabled=True,
            enable_remote_services=False,
            artifacts_path=None,
            options=options.picture_description_options,
            accelerator_options=options.accelerator_options,
        )

    @classmethod
    def get_options_type(cls):
        return ContextPicturePipelineOptions

    def is_processable(self, doc, element):
        return isinstance(element, PictureItem)

    @staticmethod
    def _text(item):
        value = getattr(item, "text", None)
        if not isinstance(value, str) or not value.strip():
            return ""
        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def _resolve(ref, doc):
        try:
            return ref.resolve(doc=doc)
        except Exception:
            return None

    @staticmethod
    def _ref_value(ref):
        """Normalize Docling RefItem/string values for sibling comparison."""
        return str(getattr(ref, "cref", None) or ref)

    @staticmethod
    def _classification(item):
        raw = item.model_dump(mode="json")
        predictions = (
            ((raw.get("meta") or {}).get("classification") or {}).get(
                "predictions"
            )
            or []
        )
        if not predictions:
            return None, 0.0
        top = predictions[0]
        return str(top.get("class_name", "")), float(top.get("confidence", 0.0))

    def _collect_related_text(self, refs, doc, max_chars):
        values, seen, queue = [], set(), list(refs or [])
        while queue and sum(len(value) for value in values) < max_chars:
            item = self._resolve(queue.pop(0), doc)
            item_ref = str(getattr(item, "self_ref", "")) if item else ""
            if item is None or item_ref in seen:
                continue
            seen.add(item_ref)
            text = self._text(item)
            if text and text not in values:
                values.append(text)
            queue.extend(getattr(item, "children", []) or [])
        return values

    def _direct_context(self, item, doc):
        return {
            "captions": self._collect_related_text(
                getattr(item, "captions", []), doc, 400
            ),
            "footnotes": self._collect_related_text(
                getattr(item, "footnotes", []), doc, 250
            ),
            "references": self._collect_related_text(
                getattr(item, "references", []), doc, 250
            ),
        }

    @staticmethod
    def _page_no(item):
        prov = getattr(item, "prov", []) or []
        return getattr(prov[0], "page_no", None) if prov else None

    def _is_text_context(self, item, target_page):
        if item is None:
            return False
        if isinstance(item, PictureItem) or item.__class__.__name__ == "TableItem":
            return False
        label = str(getattr(item, "label", "")).lower()
        if any(value in label for value in self.EXCLUDED_CONTEXT_LABELS):
            return False
        page = self._page_no(item)
        if target_page is not None and page is not None and page != target_page:
            return False
        return len(self._text(item)) >= 3

    def _neighbor_text(self, doc, siblings, position, direction, target_page, budget):
        values, used, seen = [], 0, set()
        index = position + direction
        while 0 <= index < len(siblings) and used < budget:
            candidate = self._resolve(siblings[index], doc)
            if self._is_text_context(candidate, target_page):
                text = re.sub(r"\s+", " ", self._text(candidate)).strip()
                key = text.lower()
                if key not in seen:
                    remaining = budget - used
                    text = text[:remaining].strip()
                    if text:
                        values.append(text)
                        used += len(text)
                        seen.add(key)
            index += direction
        return " | ".join(values)

    def _filtered_sibling_context(self, doc, element):
        parent_ref = getattr(element, "parent", None)
        parent = self._resolve(parent_ref, doc) if parent_ref is not None else doc.body
        if parent is None:
            parent = doc.body
        siblings = getattr(parent, "children", []) or []
        position = next(
            (
                index
                for index, ref in enumerate(siblings)
                if self._ref_value(ref) == str(element.self_ref)
            ),
            None,
        )
        if position is None:
            return None, None
        target_page = self._page_no(element)

        total_budget = max(0, int(self.options.surrounding_context_max_chars))
        before_budget = total_budget // 2
        after_budget = total_budget - before_budget
        before = self._neighbor_text(
            doc, siblings, position, -1, target_page, before_budget
        )
        after = self._neighbor_text(
            doc, siblings, position, 1, target_page, after_budget
        )
        return before, after

    def _section_path(self, doc, element):
        headers = []
        for item, _ in doc.iterate_items(
            traverse_pictures=True,
            included_content_layers={ContentLayer.BODY},
        ):
            if str(getattr(item, "self_ref", "")) == str(element.self_ref):
                break
            label = str(getattr(item, "label", "")).lower()
            text = self._text(item)
            if "section_header" in label and text:
                headers.append(text)
        return headers[-1:]

    def _context_payload(self, doc, element, label, confidence):
        before, after = self._filtered_sibling_context(doc, element)
        payload = {
            "picture": {
                "self_ref": str(element.self_ref),
                "class_name": label,
                "confidence": round(confidence, 3),
            },
            "direct_context": self._direct_context(element, doc),
            "structural_context": {
                "section_path": self._section_path(doc, element),
            },
            "surrounding_context": {"before": before, "after": after},
        }
        encoded = json.dumps(
            payload, ensure_ascii=False, separators=(",", ":")
        )
        if len(encoded) > self.options.context_max_chars:
            payload["surrounding_context"] = {"before": None, "after": None}
            encoded = json.dumps(
                payload, ensure_ascii=False, separators=(",", ":")
            )
        return payload

    @staticmethod
    def _picture_area_ratio(doc, item):
        """Return picture bbox area divided by its page area."""
        prov = getattr(item, "prov", []) or []
        if not prov:
            return None
        page_no = getattr(prov[0], "page_no", None)
        bbox = getattr(prov[0], "bbox", None)
        pages = getattr(doc, "pages", {}) or {}
        page = pages.get(page_no) if hasattr(pages, "get") else None
        size = getattr(page, "size", None) if page is not None else None
        if bbox is None or size is None:
            return None
        width = abs(float(getattr(bbox, "r")) - float(getattr(bbox, "l")))
        height = abs(float(getattr(bbox, "t")) - float(getattr(bbox, "b")))
        page_area = float(getattr(size, "width")) * float(getattr(size, "height"))
        return (width * height / page_area) if page_area > 0 else None

    def prepare_element(self, conv_res, element):
        if not isinstance(element, PictureItem):
            return None
        label, confidence = self._classification(element)
        label = label or "other"
        confidence = float(confidence or 0.0)
        area_ratio = self._picture_area_ratio(conv_res.document, element)
        if (
            area_ratio is not None
            and area_ratio < self.picture_description_model.options.picture_area_threshold
        ):
            return None
        high_confidence = confidence >= self.options.min_confidence
        # 분류 신뢰도가 낮다는 이유만으로 검색 후보 이미지를 버리지 않는다.
        # 저신뢰도 이미지는 generic route로 설명하고, table/deny 판정은
        # 분류가 임계값 이상일 때만 적용한다.
        if high_confidence and (
            label in self.options.deny_labels or label not in self.options.allow_labels
        ):
            return None
        image = element.get_image(conv_res.document)
        if image is None:
            return None
        return FinalPictureElement(
            item=element,
            image=image.convert("RGB"),
            context_payload=self._context_payload(
                conv_res.document, element, label, confidence
            ),
            class_name=label,
            confidence=confidence,
        )

    def _quality_failures(self, text, route, captions):
        normalized = re.sub(r"\s+", " ", text or "").strip()
        failures = []
        if len(normalized) < 25:
            failures.append("too_short")
        if len(normalized) > 900:
            failures.append("too_long")
        if len(re.findall(r"[가-힣]", normalized)) < 5:
            failures.append("not_korean")
        if normalized.startswith(("{", "[")) or '"direct_context"' in normalized:
            failures.append("structured_input_echo")
        if any(
            term.lower() in normalized.lower() for term in self.PROMPT_LEAK_TERMS
        ):
            failures.append("prompt_leak")
        if any(
            term.lower() in normalized.lower() for term in self.INVALID_RESPONSE_TERMS
        ):
            failures.append("invalid_response")
        sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?。])\s+|\n+", normalized)
            if len(sentence.strip()) >= 8
        ]
        sentence_keys = [
            "".join(re.findall(r"[가-힣A-Za-z0-9]+", sentence.lower()))
            for sentence in sentences
        ]
        if sentence_keys and len(sentence_keys) != len(set(sentence_keys)):
            failures.append("sentence_repetition")
        return sorted(set(failures))

    def _prepare_vlm_image(self, image):
        vlm_image = image.copy()
        max_side = max(1, int(self.options.vlm_max_image_side))
        if max(vlm_image.size) > max_side:
            vlm_image.thumbnail(
                (max_side, max_side), Image.Resampling.LANCZOS
            )
        return vlm_image

    def _generate_batch(self, images, prompts):
        """Run one Docling VLM-engine call for aligned image/prompt pairs."""
        stage = self.picture_description_model
        if stage.engine is None:
            raise RuntimeError("Picture Description VLM engine is not initialized")
        vlm_images = [self._prepare_vlm_image(image) for image in images]
        engine_inputs = stage._build_engine_inputs(vlm_images)
        if len(engine_inputs) != len(prompts):
            raise RuntimeError("VLM batch input alignment failed")
        for engine_input, prompt in zip(engine_inputs, prompts):
            engine_input.prompt = prompt
        outputs = stage.engine.predict_batch(engine_inputs)
        if len(outputs) != len(images):
            raise RuntimeError(
                f"VLM batch output mismatch: {len(outputs)} != {len(images)}"
            )
        return [self._normalize_vlm_output(output.text) for output in outputs]

    @staticmethod
    def _normalize_vlm_output(text):
        """Remove model control tokens before quality checks and storage."""
        normalized = str(text or "")
        markers = ("<|im_", "<|end", "<|eot_", "</s>", "<s>")
        positions = [normalized.find(marker) for marker in markers]
        positions = [position for position in positions if position >= 0]
        if positions:
            normalized = normalized[:min(positions)]
        return re.sub(r"\s+", " ", normalized).strip()

    @staticmethod
    def _join_context(values, limit):
        text = " | ".join(str(value).strip() for value in values if value)
        return text[:limit] if text else "(없음)"

    def _context_text(self, payload):
        direct = payload["direct_context"]
        structural = payload["structural_context"]
        surrounding = payload["surrounding_context"]

        def compact_neighbor(value):
            if not value:
                return "(없음)"
            if isinstance(value, str):
                return re.sub(r"\s+", " ", value).strip()[:180]
            if isinstance(value, dict):
                label = value.get("label") or value.get("type") or "object"
                text = value.get("text") or value.get("summary") or ""
                return re.sub(r"\s+", " ", f"{label}: {text}").strip()[:180]
            return re.sub(r"\s+", " ", str(value)).strip()[:180]

        rows = []
        if direct["captions"]:
            rows.append("캡션: " + self._join_context(direct["captions"], 220))
        related = direct["footnotes"] + direct["references"]
        if related:
            rows.append("각주·참조: " + self._join_context(related, 140))
        if structural["section_path"]:
            rows.append(
                "소속 절: " + self._join_context(structural["section_path"], 180)
            )
        if surrounding["before"]:
            rows.append("직전 객체: " + compact_neighbor(surrounding["before"]))
        if surrounding["after"]:
            rows.append("직후 객체: " + compact_neighbor(surrounding["after"]))
        return "\n".join(rows) if rows else "(보조 문맥 없음)"

    def __call__(self, doc, element_batch):
        elements = list(element_batch)
        prepared = []
        for element in elements:
            ref = str(element.item.self_ref)
            route_class = (
                element.class_name
                if element.confidence >= self.options.min_confidence
                else "other"
            )
            route, route_prompt = select_routing_prompt(route_class)
            direct = element.context_payload["direct_context"]
            captions = direct["captions"]
            context_text = self._context_text(element.context_payload)
            prompt = (
                f"{TECHNICAL_PICTURE_PROMPT}\n"
                f"{route_prompt}\n"
                f"문맥:\n{context_text}\n"
                "문맥의 명칭이 이미지에도 보일 때만 그 명칭을 써라."
            )
            prepared.append((element, ref, route, captions, prompt))

        candidates = self._generate_batch(
            [value[0].image for value in prepared],
            [value[4] for value in prepared],
        )

        for (element, ref, route, captions, _), candidate in zip(
            prepared, candidates
        ):
            failures = self._quality_failures(candidate, route, captions)
            accepted = candidate if not failures else ""
            if accepted:
                element.item.meta.description = DescriptionMetaField(
                    text=accepted,
                    created_by="context-aware-qwen2.5-vl-final",
                )
            yield element.item


class ContextPictureDescriptionPipeline(SimplePipeline):
    def __init__(self, pipeline_options):
        super().__init__(pipeline_options)
        self.pipeline_options = pipeline_options
        self.enrichment_pipe = [
            FinalPictureDescriptionModel(options=pipeline_options)
        ]

    @classmethod
    def get_default_options(cls):
        raise RuntimeError("ContextPicturePipelineOptions를 명시하세요.")

    def _enrich_document(self, conv_res):
        def prepared_elements(model):
            for item, _ in conv_res.document.iterate_items(
                traverse_pictures=True,
                included_content_layers={ContentLayer.BODY, ContentLayer.FURNITURE},
            ):
                prepared = model.prepare_element(
                    conv_res=conv_res, element=item
                )
                if prepared is not None:
                    yield prepared

        with TimeRecorder(
            conv_res, "doc_enrich_v3", scope=ProfilingScope.DOCUMENT
        ):
            for model in self.enrichment_pipe:
                for batch in chunkify(
                    prepared_elements(model), model.elements_batch_size
                ):
                    for _ in model(
                        doc=conv_res.document, element_batch=batch
                    ):
                        pass
        return conv_res


def describe_document_with_context(
    document,
    *,
    accelerator_options,
    context_max_chars: int = 1200,
    surrounding_context_max_chars: int = 500,
    vlm_max_image_side: int = 1280,
    vlm_batch_size: int = 4,
    min_confidence: float = 0.5,
) -> tuple[object, dict]:
    """Run the context-aware JSON enrichment stage on an in-memory document."""
    if not getattr(document, "pictures", None):
        return document, {
            "schema": "final-parse-picture-audit/1.0",
            "outcome": "PRESERVED",
            "picture_count": 0,
            "described_count": 0,
            "failure_reason": None,
        }

    description_options = PictureDescriptionVlmEngineOptions.from_preset(
        "qwen",
        prompt=TECHNICAL_PICTURE_PROMPT,
        generation_config={
            "max_new_tokens": 224,
            "do_sample": False,
            "repetition_penalty": 1.25,
            "no_repeat_ngram_size": 3,
        },
        classification_allow=[
            PictureClassificationLabel(value) for value in sorted(ALLOW_LABELS)
        ],
        classification_deny=[
            PictureClassificationLabel(value) for value in sorted(DENY_LABELS)
        ],
        classification_min_confidence=min_confidence,
        picture_area_threshold=0.02,
    )
    options = ContextPicturePipelineOptions(
        accelerator_options=accelerator_options,
        picture_description_options=description_options,
        context_max_chars=context_max_chars,
        surrounding_context_max_chars=surrounding_context_max_chars,
        vlm_max_image_side=vlm_max_image_side,
        vlm_batch_size=vlm_batch_size,
        allow_labels=ALLOW_LABELS,
        deny_labels=DENY_LABELS,
        min_confidence=min_confidence,
    )
    with TemporaryDirectory(prefix="final_parse_picture_") as directory:
        source = Path(directory) / "structured.docling.json"
        document.save_as_json(source, image_mode=ImageRefMode.EMBEDDED)
        converter = DocumentConverter(
            allowed_formats=[InputFormat.JSON_DOCLING],
            format_options={
                InputFormat.JSON_DOCLING: FormatOption(
                    pipeline_cls=ContextPictureDescriptionPipeline,
                    pipeline_options=options,
                    backend=DoclingJSONBackend,
                )
            },
        )
        enriched = converter.convert(source).document

    described = sum(
        bool(getattr(getattr(item, "meta", None), "description", None))
        for item in enriched.pictures
    )
    return enriched, {
        "schema": "final-parse-picture-audit/1.0",
        "outcome": "DESCRIBED" if described else "PRESERVED",
        "picture_count": len(enriched.pictures),
        "described_count": described,
        "failure_reason": None,
    }
