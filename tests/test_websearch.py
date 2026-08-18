"""웹 검색 도구.

**지키는 것은 「못 찾았다」와 「찾아보지 않았다」의 구별이다.** 키가 없거나
한도를 넘겼을 때 빈 결과를 주면 에이전트가 "웹에서 못 찾았습니다"라고 답하는데,
그때 사람이 할 행동은 다시 물어보기가 아니라 키를 넣는 것이다.
"""

from unittest.mock import patch

import requests
from django.test import SimpleTestCase, override_settings

from services.harness import registry
from services.websearch import WebSearchUnavailable, search_web


@override_settings(WEB_SEARCH_API_KEY="", WEB_SEARCH_TIMEOUT_SECONDS=5)
class MissingKeyTests(SimpleTestCase):
    def test_키가_없으면_빈_결과가_아니라_사유를_올린다(self):
        with self.assertRaises(WebSearchUnavailable) as caught:
            search_web("장고 최신 버전")

        self.assertIn("WEB_SEARCH_API_KEY", str(caught.exception))

    def test_도구는_그_사유를_사람에게_보여준다(self):
        """`ToolInputError` 라야 화면에 문장이 뜬다(그 밖의 예외는 클래스명만).

        핸들러가 제너레이터라(2026-08-18, 진행 이벤트 스트리밍) 호출 자체는
        예외를 안 던진다 — 끝까지 돌려야(`list()`) 안에서 난 예외가 밖으로
        전파된다."""

        with self.assertRaises(registry.ToolInputError):
            list(registry.BUILTIN_TOOLS["web_search"].handler(query="장고 최신 버전"))


@override_settings(WEB_SEARCH_API_KEY="test-key", WEB_SEARCH_TIMEOUT_SECONDS=5)
@patch("services.websearch.client.requests.post")
class SearchTests(SimpleTestCase):
    @staticmethod
    def _response(status=200, payload=None):
        response = requests.Response()
        response.status_code = status
        response._content = __import__("json").dumps(payload or {}).encode()
        return response

    def test_출처_URL_을_반드시_함께_준다(self, post):
        """웹 근거와 문서 근거를 가르는 표시다. 빠지면 구별할 수 없다."""

        post.return_value = self._response(
            payload={
                "results": [
                    {"title": "Django 5.2", "url": "https://example.com/a", "content": "본문"},
                ]
            }
        )

        results = search_web("장고 최신 버전")

        self.assertEqual(results[0]["url"], "https://example.com/a")
        self.assertEqual(results[0]["title"], "Django 5.2")

    def test_URL_없는_결과는_버린다(self, post):
        post.return_value = self._response(payload={"results": [{"title": "출처 없음"}]})

        self.assertEqual(search_web("질의"), [])

    def test_본문은_잘라서_넘긴다(self, post):
        """다섯 건이 수천 자면 프롬프트의 대부분이 이것이 된다."""

        post.return_value = self._response(
            payload={"results": [{"url": "https://example.com", "content": "가" * 5000}]}
        )

        from services.websearch.client import SNIPPET_CHARS

        self.assertEqual(len(search_web("질의")[0]["snippet"]), SNIPPET_CHARS)

    def test_한도_초과는_사유로_올린다(self, post):
        post.return_value = self._response(status=429)

        with self.assertRaises(WebSearchUnavailable) as caught:
            search_web("질의")
        self.assertIn("한도", str(caught.exception))

    def test_연결_실패도_사유로_올린다(self, post):
        post.side_effect = requests.ConnectionError("boom")

        with self.assertRaises(WebSearchUnavailable):
            search_web("질의")

    def test_남이_만든_요약은_받지_않는다(self, post):
        """Tavily 의 `answer` 를 우리 모델이 또 요약하면 근거가 두 겹 멀어진다."""

        post.return_value = self._response(payload={"results": []})
        search_web("질의")

        self.assertFalse(post.call_args.kwargs["json"]["include_answer"])
