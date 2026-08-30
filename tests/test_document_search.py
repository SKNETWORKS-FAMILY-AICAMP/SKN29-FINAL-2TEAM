"""`document_search` 도구 단위 테스트. DB·RunPod·모델은 mock 한다.

2026-08-24 에 `services/document_meta`(요약 생성)를 걷어내면서 그 모듈을
대상으로 하던 테스트 셋(추출기·요약 호출·빌드)도 함께 지웠다. 파일 이름도
`test_document_meta.py` 에서 바꿨다 — 남은 것은 검색뿐이다.
"""

import json
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from services.document_intake import IntakeResult
from services.harness import registry


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


def _doc(doc_id, file_name, *, ready=True, index_status=None):
    return {
        "doc_id": doc_id,
        "file_name": file_name,
        "index_status": index_status,
        "search_ready": ready,
    }


@patch("services.harness.registry.embed_queries", return_value=[[0.2] * 768])
@patch("services.harness.registry.VectorSearchRepository.search_hybrid")
@patch("services.harness.registry.PipelineDocumentRepository.searchable_documents")
class DocumentSearchScopeTests(SimpleTestCase):
    """`document_search` 는 **범위를 정하고 청크로 찾는다**(2026-08-24).

    요약으로 문서를 먼저 좁히던 단계(coarse)를 걷어냈다 — 폴더를 저장하면 그
    문서 전부가 본문까지 색인되므로 좁힐 이유가 없다. 순위는 청크 벡터가 매긴다.
    """

    def test_범위_안의_색인된_문서를_전부_훑는다(self, scope, search, _embed):
        scope.return_value = [_doc("DC001", "a.pdf"), _doc("DC002", "b.pdf")]
        search.return_value = []

        _run_document_search(team_id="TE001", query="납기일")

        self.assertEqual(search.call_args.kwargs["document_ids"], ["DC001", "DC002"])
        self.assertEqual(search.call_args.kwargs["query_text"], "납기일")

    def test_검색어_앞뒤_공백은_제거하고_빈_질의는_거부한다(self, scope, search, embed):
        scope.return_value = [_doc("DC001", "a.pdf")]
        search.return_value = []

        _run_document_search(team_id="TE001", query="  납기일  ")

        self.assertEqual(embed.call_args.args[0], ["납기일"])
        self.assertEqual(search.call_args.kwargs["query_text"], "납기일")

        with self.assertRaises(registry.ToolInputError):
            _run_document_search(team_id="TE001", query="   ")

    def test_검색_개수는_모델_입력이_아니라_서버에서_20개로_고정한다(
        self, scope, search, _embed
    ):
        scope.return_value = [_doc("DC001", "a.pdf")]
        search.return_value = []

        _run_document_search(team_id="TE001", query="납기일")

        self.assertNotIn("top_k", search.call_args.kwargs)
        schema = registry.BUILTIN_TOOLS["document_search"].input_schema
        self.assertEqual(set(schema["properties"]), {"query"})

    def test_색인_안_된_문서는_숨기지_않고_알린다(self, scope, search, _embed):
        """조용히 빼면 에이전트가 '관련 문서 없다'고 답하는데 실제로는 색인이
        아직 안 닿았을 뿐이다."""

        scope.return_value = [
            _doc("DC001", "a.pdf"),
            _doc("DC009", "미처리.pdf", ready=False),
        ]
        search.return_value = []

        result = _run_document_search(team_id="TE001", query="납기일")

        self.assertEqual(search.call_args.kwargs["document_ids"], ["DC001"])
        self.assertEqual(result["not_indexed"][0]["doc_id"], "DC009")

    def test_전부_미색인이면_그렇게_말한다(self, scope, search, _embed):
        scope.return_value = [_doc("DC009", "미처리.pdf", ready=False)]

        result = _run_document_search(team_id="TE001", query="납기일")

        search.assert_not_called()
        self.assertEqual(result["evidence"], [])
        self.assertIn("색인", result["note"])
        self.assertEqual(result["not_indexed"][0]["doc_id"], "DC009")

    def test_미색인_문서를_그_자리에서_승격시키지_않는다(self, scope, search, _embed):
        """전에는 요약 유사도 상위 몇 건을 그 자리에서 읽어 올렸다. 좁히는
        단계를 걷어낸 지금은 미색인 문서에 순위가 없어, 앞의 몇 건을 고르는 것이
        `doc_id` 순으로 아무거나 집는 것과 같다 — 관련도 없는 문서 때문에 대화가
        몇 분 멈춘다. 전량 색인이 결국 채우므로 여기서는 알리기만 한다."""

        scope.return_value = [_doc("DC009", "미처리.pdf", ready=False)]

        with patch("services.document_intake.promote_to_searchable") as promote:
            _run_document_search(team_id="TE001", query="납기일", account_id="UA001")

        promote.assert_not_called()

    def test_프로젝트로_좁혀_비면_팀_전체로_넓힌다(self, scope, search, _embed):
        """팀 공용 문서(규정·양식)를 영영 못 보게 하면 「감리 표준양식 보여줘」
        같은 요청이 막힌다(2026-08-19 PM 결정 ⓐ)."""

        scope.side_effect = [[], [_doc("DC001", "규정.pdf")]]
        search.return_value = []

        _run_document_search(team_id="TE001", query="양식", proj_id="PJ001")

        self.assertEqual(scope.call_count, 2)
        self.assertEqual(scope.call_args_list[0].kwargs["proj_id"], "PJ001")
        self.assertNotIn("proj_id", scope.call_args_list[1].kwargs)
        self.assertEqual(search.call_args.kwargs["document_ids"], ["DC001"])

    def test_내_파일을_보려면_요청자_계정이_범위에_넘어가야_한다(self, scope, search, _embed):
        """`account_id` 를 빠뜨리면 오류가 아니라 조용히 팀 문서만 보게 된다(M④)."""

        scope.return_value = [_doc("DC001", "a.pdf")]
        search.return_value = []

        _run_document_search(team_id="TE001", query="납기일", account_id="UA001")

        self.assertEqual(scope.call_args.kwargs["account_id"], "UA001")

    @override_settings(PUBLIC_BACKEND_BASE_URL="https://api.example.com")
    def test_이미지_도구는_picture_청크만_원본_crop과_연결한다(self, scope, search, _embed):
        scope.return_value = [_doc("DC001", "도면.pdf")]
        search.return_value = [
            {
                "chunk_id": "CH001",
                "doc_id": "DC001",
                "file_name": "도면.pdf",
                "mime_type": "application/pdf",
                "block_id": "BL001",
                "block_type": "PICTURE",
                "page": 3,
                "revision": "REV1",
                "heading_path": ["구조도"],
                "text": "배관 연결 구조를 나타낸 도면",
                "retrieval_score": 0.91,
            }
        ]

        result = _run_document_search(
            team_id="TE001", query="배관 구조", include_images=True
        )

        self.assertEqual(result[0]["type"], "text")
        self.assertEqual(result[1]["type"], "image")
        self.assertIn("/api/internal/document-picture-crops/BL001/", result[1]["url"])
        text_payload = json.loads(result[0]["text"])
        self.assertNotIn("text", text_payload["evidence"][0])
        self.assertNotIn("배관 연결 구조를 나타낸 도면", result[0]["text"])

    @override_settings(PUBLIC_BACKEND_BASE_URL="https://api.example.com")
    def test_일반_문서검색은_picture라도_텍스트만_반환한다(self, scope, search, _embed):
        scope.return_value = [_doc("DC001", "도면.pdf")]
        search.return_value = [
            {
                "chunk_id": "CH001", "doc_id": "DC001", "block_type": "PICTURE",
                "heading_path": [], "text": "도면 설명", "retrieval_score": 0.8,
            }
        ]

        result = _run_document_search(team_id="TE001", query="도면")

        self.assertIsInstance(result, dict)
        self.assertEqual(result["evidence"], [])
        self.assertIn("검색 점수", result["picture_note"])

    @override_settings(PUBLIC_BACKEND_BASE_URL="https://api.example.com")
    def test_이미지는_block_id로_중복제거하고_서버에서_다섯개로_제한한다(
        self, scope, search, _embed
    ):
        scope.return_value = [_doc("DC001", "도면.pdf")]
        search.return_value = [
            {
                "chunk_id": f"CH{index:03d}",
                "doc_id": "DC001",
                "file_name": "도면.pdf",
                "mime_type": "application/pdf",
                "block_id": "BL001" if index <= 2 else f"BL{index:03d}",
                "block_type": "PICTURE",
                "page": index,
                "revision": "REV1",
                "heading_path": [],
                "text": f"검색용 description {index}",
                "retrieval_score": 1 - index / 100,
            }
            for index in range(1, 8)
        ]

        result = _run_document_search(
            team_id="TE001", query="도면", include_images=True
        )

        self.assertEqual(len([block for block in result if block["type"] == "image"]), 5)
        payload = json.loads(result[0]["text"])
        self.assertEqual(len(payload["evidence"]), 5)
        self.assertNotIn("검색용 description", result[0]["text"])


class DocumentSearchCatalogTests(SimpleTestCase):
    def test_도구_목록에_문서_검색이_기본_검색_도구로_노출된다(self):
        from apps.agents.serializers import builtin_tool_response

        tools = {tool["tool_ref"]: tool for tool in builtin_tool_response()}

        self.assertIn("document_search", tools)
        self.assertEqual(tools["document_search"]["category"], "검색")
        self.assertTrue(tools["document_search"]["is_default"])
        self.assertEqual(set(tools["document_search"]["input_schema"]["properties"]), {"query"})
        self.assertEqual(
            set(tools["document_search_with_images"]["input_schema"]["properties"]),
            {"query"},
        )
        self.assertFalse(tools["document_search_with_images"]["is_default"])


def _run_document_sync(**kwargs):
    """`_document_sync` 도 제너레이터다(진행 이벤트). 끝까지 돌려 반환값만 꺼낸다."""
    gen = registry._document_sync(**kwargs)
    try:
        while True:
            next(gen)
    except StopIteration as stop:
        return stop.value


@patch("services.harness.registry.sync_drive_changes")
@patch("services.harness.registry.ConnectorRepository")
class DocumentSyncToolTests(SimpleTestCase):
    """사용자가 「방금 문서 고쳤어」라고 할 때 부르는 도구(2026-08-24).

    대화를 열 때 이미 한 번 확인하지만, 대화 **중간에** 바뀐 것은 그때 못 잡는다.
    버튼을 만드는 대신 도구로 둔 것은 이 제품이 「말하면 불려 나온다」로 동작하기
    때문이다.
    """

    def test_연결이_없으면_변경_없음이라고_하지_않는다(self, connectors, sync):
        """사람에게 「연결이 없다」와 「바뀐 게 없다」는 전혀 다른 말이다.
        `sync_drive_changes` 는 둘을 똑같이 빈 결과로 돌려주므로 여기서 가른다."""

        connectors.drive_sync_target.return_value = None

        result = _run_document_sync(account_id="UA001")

        sync.assert_not_called()
        self.assertFalse(result["checked"])
        self.assertIn("연결", result["note"])

    def test_바뀐_것이_없으면_그렇게_말한다(self, connectors, sync):
        connectors.drive_sync_target.return_value = {"conn_id": "CN001"}
        sync.return_value = IntakeResult()

        result = _run_document_sync(account_id="UA001")

        self.assertTrue(result["checked"])
        self.assertIn("바뀐 문서가 없습니다", result["note"])

    def test_바뀐_것을_갈래별로_돌려준다(self, connectors, sync):
        """다시 받은 것·내려간 것·색인된 것은 사람이 확인할 내용이 각각 다르다."""

        connectors.drive_sync_target.return_value = {"conn_id": "CN001"}
        sync.return_value = IntakeResult(
            refreshed=["기획서.pdf"], removed=["DC009"], indexed=["DC001"]
        )

        result = _run_document_sync(account_id="UA001")

        self.assertTrue(result["checked"])
        self.assertEqual(result["refreshed"], ["기획서.pdf"])
        self.assertEqual(result["removed"], ["DC009"])
        self.assertEqual(result["indexed"], ["DC001"])
        self.assertIn("반영했습니다", result["note"])

    def test_저장소를_못_읽으면_확인_실패로_돌려준다(self, connectors, sync):
        """자격증명이 만료된 경우다. 「바뀐 게 없다」로 답하면 사용자는 최신
        내용으로 답받았다고 믿는다."""

        connectors.drive_sync_target.return_value = {"conn_id": "CN001"}
        sync.return_value = IntakeResult(storage_error="OAuthError")

        result = _run_document_sync(account_id="UA001")

        self.assertFalse(result["checked"])
        self.assertIn("OAuthError", result["note"])
