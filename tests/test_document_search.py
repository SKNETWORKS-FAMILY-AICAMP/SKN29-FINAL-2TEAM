"""`document_search` 도구 단위 테스트. DB·RunPod·모델은 mock 한다.

2026-08-24 에 `services/document_meta`(요약 생성)를 걷어내면서 그 모듈을
대상으로 하던 테스트 셋(추출기·요약 호출·빌드)도 함께 지웠다. 파일 이름도
`test_document_meta.py` 에서 바꿨다 — 남은 것은 검색뿐이다.
"""

from unittest.mock import patch

from django.test import SimpleTestCase

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
@patch("services.harness.registry.VectorSearchRepository.search")
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
