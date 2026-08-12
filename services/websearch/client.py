"""Tavily 검색 호출.

`requests` 를 직접 쓴다 — 이 저장소가 Jira·Drive·RunPod 를 부르는 방식과 같다.
SDK 를 하나 더 넣으면 배포 이미지만 커지고, 우리가 쓰는 것은 엔드포인트 하나다.
"""

from __future__ import annotations

import logging
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

_ENDPOINT = "https://api.tavily.com/search"

#: 한 번에 받을 결과 수. 많이 받아도 모델이 앞쪽 몇 개만 쓰고 토큰만 는다.
MAX_RESULTS = 5

#: 결과 하나에서 모델에게 넘길 본문 길이. Tavily 가 주는 `content` 는 길면
#: 수천 자라, 다섯 건이면 프롬프트의 대부분이 이것이 된다.
SNIPPET_CHARS = 700


class WebSearchUnavailable(Exception):
    """검색을 할 수 없는 상태. **키 없음도 여기에 포함된다.**

    키가 없는 것은 버그가 아니라 설정이다. 그때 예외를 삼키고 빈 결과를 주면
    에이전트가 "웹에서 못 찾았습니다"라고 답하는데, 실제로는 **찾아보지도
    않은** 것이다 — 그 둘은 사용자가 할 행동이 다르다(다시 물어보기 vs 키 넣기).
    """


def search(query: str, *, max_results: int = MAX_RESULTS) -> list[dict[str, Any]]:
    """웹에서 찾고 **출처와 함께** 돌려준다.

    `answer` 필드(Tavily 가 만들어 주는 요약)는 받지 않는다. 남이 요약한 문장을
    우리 에이전트가 다시 요약하면 근거가 두 겹 멀어지고, 그 문장이 어느 페이지에서
    왔는지도 흐려진다 — 우리는 원문 조각과 URL 만 받아 모델이 직접 읽게 한다.
    """

    api_key = str(settings.WEB_SEARCH_API_KEY or "").strip()
    if not api_key:
        raise WebSearchUnavailable(
            "웹 검색이 설정되지 않았습니다. 관리자가 WEB_SEARCH_API_KEY 를 넣어야 합니다."
        )

    try:
        response = requests.post(
            _ENDPOINT,
            json={
                "api_key": api_key,
                "query": query,
                "max_results": max_results,
                "search_depth": "basic",
                # 우리가 쓰지 않는 것은 받지 않는다 — 응답이 작을수록 빠르다.
                "include_answer": False,
                "include_raw_content": False,
                "include_images": False,
            },
            timeout=settings.WEB_SEARCH_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        logger.warning("웹 검색 호출 실패: %s", exc.__class__.__name__)
        raise WebSearchUnavailable("웹 검색 서버에 연결하지 못했습니다.") from exc

    if response.status_code == 401:
        raise WebSearchUnavailable("웹 검색 인증이 거부됐습니다. 키를 확인해 주세요.")
    if response.status_code == 429:
        raise WebSearchUnavailable("웹 검색 한도를 초과했습니다. 잠시 후 다시 시도해 주세요.")
    if not response.ok:
        logger.warning("웹 검색 응답 오류: %s", response.status_code)
        raise WebSearchUnavailable(f"웹 검색이 실패했습니다 (HTTP {response.status_code}).")

    try:
        payload = response.json()
    except ValueError as exc:
        raise WebSearchUnavailable("웹 검색이 예상한 형식으로 응답하지 않았습니다.") from exc

    results = payload.get("results")
    if not isinstance(results, list):
        return []

    return [
        {
            "title": item.get("title"),
            # **URL 을 빼지 않는다.** 이것이 웹 근거와 문서 근거를 가르는 표시다.
            "url": item.get("url"),
            "snippet": (item.get("content") or "")[:SNIPPET_CHARS],
        }
        for item in results
        if isinstance(item, dict) and item.get("url")
    ]
