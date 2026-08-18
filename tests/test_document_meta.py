"""문서 메타 파이프라인(A안) 단위 테스트. DB·RunPod·모델은 mock 한다.

가장 중요하게 보는 것은 **뽑지 못한 것을 뽑은 척하지 않는가**다. 스캔 PDF 가
OK 로 남으면 "내용이 거의 없는 문서"라는 요약이 만들어져 검색을 오염시킨다.
"""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from services.document_meta import extractor, service
from services.harness import registry


def pdf_bytes(text: str) -> bytes:
    """pypdf 로 읽히는 최소 PDF. 텍스트 레이어 유무를 실제로 만들어 확인한다."""

    from io import BytesIO

    from pypdf import PdfWriter

    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    if text:
        # pypdf 5.x 의 텍스트 삽입. 실패하면 테스트가 의미를 잃으므로 감추지 않는다.
        from pypdf.annotations import FreeText

        writer.add_annotation(page_number=0, annotation=FreeText(
            text=text, rect=(10, 10, 190, 190), font_size="8pt"
        ))
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


class ExtractorTests(SimpleTestCase):
    def test_평문은_그대로_뽑는다(self):
        body = ("이 사업은 정보시스템 구축을 목적으로 한다. " * 20).encode("utf-8")

        result = extractor.extract(content=body, mime_type="text/plain", file_name="a.txt")

        self.assertEqual(result.status, extractor.OK)
        self.assertIn("정보시스템", result.text)

    def test_너무_짧으면_실패다(self):
        """요약할 내용이 없는데 요약을 만들면 그 요약이 검색을 오염시킨다."""

        result = extractor.extract(content=b"hi", mime_type="text/plain", file_name="a.txt")

        self.assertEqual(result.status, extractor.FAILED)

    def test_hwp_는_UNSUPPORTED_다(self):
        """FAILED 와 구분한다 — 파서를 붙이면 OK 가 될 수 있는 상태다."""

        result = extractor.extract(content=b"\x00" * 500, mime_type=None, file_name="계획.hwp")

        self.assertEqual(result.status, extractor.UNSUPPORTED)
        self.assertIn("hwp", result.detail)

    def test_docx_는_UNSUPPORTED_다(self):
        result = extractor.extract(
            content=b"PK\x03\x04" + b"\x00" * 500,
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            file_name="a.docx",
        )

        self.assertEqual(result.status, extractor.UNSUPPORTED)

    def test_텍스트_레이어가_없는_PDF_는_실패다(self):
        """스캔본. OCR 을 붙이면 되므로 UNSUPPORTED 가 아니라 FAILED 다."""

        result = extractor.extract(
            content=pdf_bytes(""), mime_type="application/pdf", file_name="scan.pdf"
        )

        self.assertEqual(result.status, extractor.FAILED)
        self.assertIn("텍스트 레이어", result.detail)

    def test_깨진_PDF_는_예외가_아니라_상태다(self):
        """문서 하나가 이상하다고 팀 전체 파이프라인이 멈추면 안 된다."""

        result = extractor.extract(
            content=b"%PDF-1.4 broken", mime_type="application/pdf", file_name="x.pdf"
        )

        self.assertEqual(result.status, extractor.FAILED)

    def test_글자가_깨져_나오면_실패다(self):
        """실측(2026-08-11): 폰트 CMap 이 없는 PDF 가 18,961자를 뱉었는데 전부
        같은 글자였다. 글자 수만 보면 통과하고, 그 요약이 검색을 오염시킨다."""

        garbled = "SK 네네네네 Family AI 네네 " * 200

        self.assertTrue(extractor._is_garbled(garbled))

    def test_정상_한국어는_깨진_것으로_보지_않는다(self):
        normal = (
            "본 사업은 대학 정보시스템을 고도화하여 학생 지원 업무를 자동화하는 것을 "
            "목적으로 한다. 데이터 수집과 정제를 거쳐 예측 모델을 구축하고, 그 결과를 "
            "운영 화면에서 확인할 수 있도록 한다. " * 10
        )

        self.assertFalse(extractor._is_garbled(normal))

    def test_영문_문서는_한글_비율로_판정하지_않는다(self):
        """한글이 거의 없는 문서를 깨졌다고 하면 멀쩡한 문서가 버려진다."""

        self.assertFalse(extractor._is_garbled("This is a normal English document. " * 50))

    def test_요약_입력은_잘라서_넘긴다(self):
        self.assertEqual(
            len(extractor.for_summary("가" * 99999)), extractor.SUMMARY_INPUT_MAX_CHARS
        )


class SummarizeCallTests(SimpleTestCase):
    """`_summarize` 를 mock 하지 않고 **호출부 자체**를 한 번 태운다.

    나머지 테스트가 전부 `_summarize` 를 통째로 mock 하는 바람에, 이 함수가
    참조하는 `SUMMARY_MODEL` 이 정의되지 않아 실제 호출이 NameError 로 죽는
    상태가 테스트를 그대로 통과했다(2026-08-14). mock 은 OpenAI 클라이언트에만
    건다 — 우리 코드가 어떤 인자로 부르는지가 검사 대상이다.
    """

    @patch("services.document_meta.service.OpenAI")
    def test_설정된_모델로_구조화_출력을_요청한다(self, openai_cls):
        parsed = service.DocumentSummary(summary="요약", doc_type="보고서", keywords=["a"])
        openai_cls.return_value.responses.parse.return_value = SimpleNamespace(
            output_parsed=parsed
        )

        with self.settings(OPENAI_API_KEY="sk-test", OPENAI_SERVICE_TIER="auto"):
            result = service._summarize(text="본문", file_name="a.pdf")

        self.assertEqual(result.doc_type, "보고서")
        kwargs = openai_cls.return_value.responses.parse.call_args.kwargs
        self.assertEqual(kwargs["model"], service.SUMMARY_MODEL)
        # 요약은 팀 문서 전부에 도는 일이라 단가가 그대로 총액이 된다.
        self.assertEqual(kwargs["reasoning"], {"effort": "low"})
        self.assertIs(kwargs["text_format"], service.DocumentSummary)


class BuildTests(SimpleTestCase):
    @patch("services.document_meta.service.embed_queries")
    @patch("services.document_meta.service._summarize")
    def test_추출부터_임베딩까지_한_벌(self, summarize, embed):
        summarize.return_value = service.DocumentSummary(
            summary="정보시스템 구축 사업 제안요청서다.", doc_type="제안요청서", keywords=["구축"]
        )
        embed.return_value = [[0.1] * 768]

        meta = service.build(
            doc_id="DC001",
            content=("본 사업은 " * 100).encode("utf-8"),
            mime_type="text/plain",
            file_name="rfp.txt",
        )

        self.assertEqual(meta.extract_status, "OK")
        self.assertEqual(len(meta.summary_vec), 768)
        # A′ 전환 대비 — 원문을 버리지 않는다(12_문서처리_방식_비교 §5).
        self.assertIn("본 사업은", meta.extracted_text)
        # 임베딩은 요약 하나뿐이다. 원문을 통째로 넣으면 청크 경로와 같아진다.
        embed.assert_called_once_with(["정보시스템 구축 사업 제안요청서다."])

    @patch("services.document_meta.service.embed_queries")
    @patch("services.document_meta.service._summarize")
    def test_추출에_실패하면_모델도_임베딩도_안_부른다(self, summarize, embed):
        meta = service.build(
            doc_id="DC002", content=b"\x00" * 10, mime_type=None, file_name="a.hwp"
        )

        self.assertEqual(meta.extract_status, "UNSUPPORTED")
        summarize.assert_not_called()
        embed.assert_not_called()
        # 행은 남는다 — 안 남기면 왜 검색에 안 걸리는지 화면이 말할 수 없다.
        self.assertEqual(service.as_row(meta)["doc_id"], "DC002")

    @patch("services.document_meta.service.embed_queries", return_value=[[0.0] * 768])
    @patch("services.document_meta.service._summarize")
    def test_목록_밖_문서유형은_기타로_떨어진다(self, summarize, _embed):
        """화면 필터가 모르는 값이 들어오면 그 문서가 조용히 안 잡힌다."""

        summarize.return_value = service.DocumentSummary(
            summary="요약", doc_type="아무거나", keywords=[]
        )
        # `_summarize` 자체를 mock 했으므로 정규화는 그 안에서 일어난다 —
        # 여기서는 서비스가 목록을 한 곳에만 두고 있는지만 확인한다.
        self.assertIn("기타", service.DOC_TYPES)


def _run_document_search(**kwargs):
    """`_document_search`는 제너레이터다(2026-08-18, 진행 이벤트 스트리밍 —
    `adapters.py`의 `_drain_with_progress`와 같은 방식). 끝까지 돌려서
    `return`(도구의 실제 결과)만 꺼낸다 — 중간 진행 이벤트는 이 테스트의
    관심사가 아니다."""
    gen = registry._document_search(**kwargs)
    try:
        while True:
            next(gen)
    except StopIteration as stop:
        return stop.value


@patch("services.harness.registry.embed_queries", return_value=[[0.2] * 768])
@patch("services.harness.registry.VectorSearchRepository.search")
@patch("services.harness.registry.DocMetaRepository.coarse_search")
class CoarseSearchTests(SimpleTestCase):
    """document_search 의 2단계 검색(A안 — 8/11 확정 ⑥)."""

    def test_coarse_가_고른_문서_안에서만_청크를_찾는다(self, coarse, search, _embed):
        coarse.return_value = [
            {"doc_id": "DC001", "file_name": "a.pdf", "summary": "s", "doc_type": "제안요청서",
             "keywords": [], "summary_score": 0.8, "search_ready": True, "index_status": None},
            {"doc_id": "DC002", "file_name": "b.pdf", "summary": "s", "doc_type": "회의록",
             "keywords": [], "summary_score": 0.7, "search_ready": True},
        ]
        search.return_value = []

        _run_document_search(team_id="TE001", query="납기일")

        self.assertEqual(search.call_args.kwargs["document_ids"], ["DC001", "DC002"])

    def test_색인_안_된_후보는_숨기지_않고_알린다(self, coarse, search, _embed):
        """조용히 빼면 에이전트가 '관련 문서 없다'고 답하는데 실제로는 있다."""

        coarse.return_value = [
            {"doc_id": "DC001", "file_name": "a.pdf", "summary": "s", "doc_type": "제안요청서",
             "keywords": [], "summary_score": 0.8, "search_ready": True, "index_status": None},
            {"doc_id": "DC009", "file_name": "미처리.pdf", "summary": "관련 요약", "doc_type": "회의록",
             "keywords": [], "summary_score": 0.7, "search_ready": False, "index_status": None},
        ]
        search.return_value = []

        result = _run_document_search(team_id="TE001", query="납기일")

        self.assertEqual(search.call_args.kwargs["document_ids"], ["DC001"])
        self.assertEqual(result["not_indexed"][0]["doc_id"], "DC009")

    def test_후보가_전부_미색인이면_그렇게_말한다(self, coarse, search, _embed):
        coarse.return_value = [
            {"doc_id": "DC009", "file_name": "미처리.pdf", "summary": "관련 요약", "doc_type": "회의록",
             "keywords": [], "summary_score": 0.7, "search_ready": False, "index_status": None},
        ]

        result = _run_document_search(team_id="TE001", query="납기일")

        search.assert_not_called()
        self.assertEqual(result["evidence"], [])
        self.assertIn("색인", result["note"])
        self.assertEqual(result["not_indexed"][0]["doc_id"], "DC009")

    @patch("services.harness.registry.PipelineDocumentRepository.searchable_doc_ids")
    def test_메타가_없으면_예전처럼_팀_문서_전체를_훑는다(self, all_ids, coarse, search, _embed):
        """coarse 를 켰다고 파이프라인 안 돌린 팀의 검색이 죽으면 안 된다."""

        coarse.return_value = []
        all_ids.return_value = ["DC001", "DC002", "DC003"]
        search.return_value = []

        _run_document_search(team_id="TE001", query="납기일")

        self.assertEqual(search.call_args.kwargs["document_ids"], ["DC001", "DC002", "DC003"])
