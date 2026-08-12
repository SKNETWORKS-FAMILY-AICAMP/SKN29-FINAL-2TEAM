"""대화 제목을 짓는다.

**첫 발화를 그대로 제목으로 쓰면 구별이 안 된다.** 특히 프로젝트 상세의
「업무 뽑기」는 늘 같은 문장(「이 프로젝트의 기준 문서에서 업무를 뽑아줘」)을
보내서, 두 번 누르면 사이드바에 글자까지 똑같은 대화가 둘 생긴다
(2026-08-12 QA 시나리오 B).

첫 답이 끝난 뒤에 짓는다. 질문만 보면 「업무 뽑아줘」밖에 모르지만, 답까지
보면 무엇에 대한 대화였는지가 정해진다 — 「감리 업무 20건 추출」처럼.
"""

from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger(__name__)

#: 사이드바 한 줄에 들어가는 길이. 넘치면 어차피 잘려서 뒤가 안 보인다.
MAX_TITLE = 40

_SYSTEM = (
    "너는 대화 목록에 붙일 짧은 제목을 짓는다. "
    f"한국어 명사구로 {MAX_TITLE}자 이내. 따옴표·마침표·「제목:」 같은 머리말을 붙이지 않는다. "
    "무엇에 대한 대화인지 한눈에 알 수 있게, 구체적인 대상과 행동을 담는다."
)


def suggest_title(*, question: str, answer: str) -> str | None:
    """이 대화의 제목. 지을 수 없으면 `None` — 그때는 부르는 쪽이 원래 제목을 둔다.

    **실패해도 조용히 넘어간다.** 제목은 대화의 부산물이라, 이것 때문에 방금
    끝난 답을 잃거나 오류 카드를 띄우면 손해가 훨씬 크다.
    """

    api_key = str(settings.OPENAI_API_KEY or "").strip()
    if not api_key or not question.strip():
        return None

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, timeout=20, max_retries=0)
        response = client.responses.create(
            model=settings.OPENAI_MODEL,
            service_tier=settings.OPENAI_SERVICE_TIER,
            # 제목 짓기에 추론을 깊게 태울 이유가 없다. 느려지기만 한다.
            # `document_meta` 가 요약에 쓰는 값과 같다(실제로 도는 것을 확인한 값).
            reasoning={"effort": "low"},
            input=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": f"질문: {question}\n\n답: {answer[:1500]}"},
            ],
        )
        title = (response.output_text or "").strip().strip("\"'「」").strip()
    except Exception:  # noqa: BLE001 - 제목 하나 때문에 대화를 잃지 않는다
        logger.exception("대화 제목 생성에 실패했습니다")
        return None

    if not title:
        return None
    return title[:MAX_TITLE]
