"""웹 검색 — 팀 문서 밖의 근거.

**우리 문서와 다른 종류의 근거다.** 팀 문서는 사람이 올려 둔 것이고 파싱·색인을
거쳤지만, 웹은 아무도 검증하지 않았다. 그 차이가 답에서 지워지면 사용자는
「우리 기획서에 그렇게 적혀 있다」와 「인터넷에 그런 글이 있다」를 구별하지
못한다 — 이 제품이 지키는 정직 표기의 핵심이 거기다.

그래서 결과에 **출처 URL 을 반드시 붙이고**, 도구 설명이 모델에게 「문서에 있는
것은 document_search 로 답하라」고 못 박는다.
"""

from .client import WebSearchUnavailable
from .client import search as search_web

__all__ = ["WebSearchUnavailable", "search_web"]
