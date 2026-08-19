"""코드로 형태 판단이 가능한 민감정보 패턴 — credential/개인정보/권한·보안 서술.

`memory/write_guard.py`(개인 장기 메모리에 저장하지 못하게 막음)와
`apps/chat/api_views.py`(사용자가 채팅에 직접 입력한 내용 중 이 패턴에 걸리는
값을 모델에게 보내기 전에 가림, 2026-08-19 §2순위)가 **같은 패턴을 공유**한다
— 두 기능이 "무엇을 민감정보로 보는가"에 대해 서로 다른 정의를 갖게 되면
한쪽만 고쳐질 위험이 있어서, 패턴 정의는 여기 하나만 둔다.

이 모듈이 판단할 수 있는 범위는 **값의 "형태"만으로 판단 가능한 세 카테고리
뿐이다** — "모델이 추론한 사실인가", "이 프로젝트에만 해당하는 얘기인가" 같은
맥락 판단은 여기서 하지 않는다(그건 각 사용처의 몫이다). 한계는
`memory/write_guard.py` 모듈 docstring과 동일하게 적용된다: 여러 조각으로
쪼개면 개별 조각은 못 잡는다, 전화번호 패턴은 오탐 가능성이 있다, 권한/보안
키워드는 문맥 없이 문자열 포함 여부만 본다.
"""

from __future__ import annotations

import re

#: 검사에 걸리는 값을 대신하는 자리표시자. 매칭된 원문은 어디에도 남기지
#: 않는다 — 로그·오류 메시지·모델 입력 어디로도 원문이 새어나가면 이 모듈을
#: 쓰는 의미가 없다.
MASK_PLACEHOLDER = "[가려짐]"

# credential / secret — 값의 "형태"만으로 판단, 진위 판단 불필요.
CREDENTIAL_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),  # OpenAI/Anthropic류 API 키 형식
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key 형식
    re.compile(r"(?i)(api[_-]?key|secret|token|password|passwd|pwd)\s*[:=]\s*\S+"),
    re.compile(r"(?i)(aws_secret|db_password|secret_key|private_key)\s*[:=]"),
]

# 개인정보 — 자릿수·형식이 고정된 패턴.
PII_PATTERNS = [
    re.compile(r"\d{6}[-\s]?[1-4]\d{6}"),  # 주민등록번호
    re.compile(r"\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}"),  # 카드번호
    re.compile(r"01[016789][-\s]?\d{3,4}[-\s]?\d{4}"),  # 휴대전화번호(모듈 docstring 한계 참고)
]

# 권한/보안 관련 사실 — 진위와 무관하게 카테고리째 차단.
AUTHORITY_KEYWORDS = [
    "관리자 권한",
    "관리자 계정",
    "관리자 비밀번호",
    "루트 계정",
    "root 계정",
    "내부 접속 정보",
    "administrator privilege",
    "admin password",
    "root access",
    "superuser",
]

CATEGORY_LABELS = {
    "credential": "credential/secret로 보이는 값",
    "pii": "개인정보로 보이는 값(주민등록번호·카드번호·전화번호 패턴)",
    "authority": "권한/보안 관련 서술",
}

#: `AUTHORITY_KEYWORDS`를 `re.sub`으로 한 번에 치환하기 위한 컴파일된 패턴.
#: 대소문자 무시 + 길이가 긴 키워드부터 매칭해야 짧은 키워드가 긴 키워드의
#: 일부를 먼저 잘라먹는 걸 막는다(예: "관리자 계정"이 "관리자 권한"보다 먼저
#: 매칭돼도 겹치지 않으므로 지금 목록엔 실질적 위험은 없지만, 새 키워드가
#: 추가될 때를 대비해 원칙을 지켜 둔다).
_AUTHORITY_PATTERN = re.compile(
    "|".join(re.escape(keyword) for keyword in sorted(AUTHORITY_KEYWORDS, key=len, reverse=True)),
    re.IGNORECASE,
)


def match_category(text: str) -> str | None:
    """`text`에서 세 카테고리 중 하나라도 걸리면 그 이름을, 없으면 `None`을
    반환한다. 하나만 알면 되는 판단(예: 저장을 막을지 말지)에 쓴다 — 여러
    개가 섞여 있어도 첫 번째로 찾은 카테고리만 돌려준다."""
    for pattern in CREDENTIAL_PATTERNS:
        if pattern.search(text):
            return "credential"
    for pattern in PII_PATTERNS:
        if pattern.search(text):
            return "pii"
    if _AUTHORITY_PATTERN.search(text):
        return "authority"
    return None


def mask_sensitive(text: str) -> str:
    """`text` 안에서 세 카테고리에 걸리는 부분만 `MASK_PLACEHOLDER`로 가리고
    나머지는 그대로 돌려준다.

    `match_category()`와 다르게 **첫 매치에서 멈추지 않는다** — 한 문장에
    여러 값이 섞여 있으면(예: API 키와 전화번호가 같이 있는 문장) 전부
    가린다. 매칭된 원문은 반환값 어디에도 남지 않는다.
    """
    masked = text
    for pattern in [*CREDENTIAL_PATTERNS, *PII_PATTERNS]:
        masked = pattern.sub(MASK_PLACEHOLDER, masked)
    masked = _AUTHORITY_PATTERN.sub(MASK_PLACEHOLDER, masked)
    return masked


__all__ = [
    "AUTHORITY_KEYWORDS",
    "CATEGORY_LABELS",
    "CREDENTIAL_PATTERNS",
    "MASK_PLACEHOLDER",
    "PII_PATTERNS",
    "mask_sensitive",
    "match_category",
]
