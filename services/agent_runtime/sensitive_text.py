"""코드로 형태 판단이 가능한 민감정보 패턴 — credential/개인정보/권한·보안 서술.

네 곳이 **같은 패턴을 공유**한다 — 정의가 갈리면 한쪽만 고쳐질 위험이 있어
패턴은 여기 하나만 둔다:

- `memory/write_guard.py` — 개인 장기 메모리 저장 차단
- `middleware/sensitive_input.py` — 채팅 입력을 모델에게 보내기 전 마스킹
  (2026-08-26 이전엔 `apps/chat/api_views.py`가 직접 불렀다. `suggest_title()`용
  질문 문구만 예외로 지금도 `api_views.py`가 직접 부른다 — 그 호출은 그래프를
  안 거쳐 미들웨어 보호 밖이라서다, 모듈 docstring 참고)
- `apps/chat/api_views.py` — 사용자 발화를 `ChatMessageRepository`에 쓰기
  **직전** 마스킹(2026-08-27 추가, 아래 `mask_for_storage()` docstring 참고)
- `tracing/callbacks.py` — Langfuse로 나가는 trace 사본 마스킹

**어디까지 가릴지는 사용처마다 다르다.** 같은 패턴 목록을 쓰되 조합만 달리한다:
모델에게 보내는 값과 장기 메모리는 `mask_sensitive()`(credential+PII+권한
서술), DB 저장은 `mask_for_storage()`(credential+PII, 권한 서술 제외), 외부
반출 trace는 `mask_for_export()`(credential+PII+**이메일**, 권한 서술 제외).
이유는 각 함수 docstring에 있다.

판단 범위는 **값의 "형태"만으로 가릴 수 있는 세 카테고리뿐이다** — 맥락 판단은
각 사용처의 몫이다. 한계는 `memory/write_guard.py`와 같다: 여러 조각으로 쪼개면
못 잡고, 전화번호 패턴은 오탐이 있으며, 권한/보안 키워드는 문맥 없이 문자열
포함 여부만 본다.
"""

from __future__ import annotations

import re

#: 검사에 걸리는 값을 대신하는 자리표시자. 매칭된 원문은 어디에도 남기지
#: 않는다 — 로그·오류 메시지·모델 입력 어디로도 원문이 새어나가면 이 모듈을
#: 쓰는 의미가 없다.
MASK_PLACEHOLDER = "[가려짐]"

# credential / secret — 값의 "형태"만으로 판단, 진위 판단 불필요.
CREDENTIAL_PATTERNS = [
    # OpenAI/Anthropic류 API 키. **하이픈을 허용해야 한다** — `sk-` 뒤에 영숫자만
    # 연속으로 요구하면 접두사가 붙은 현행 형식(`sk-proj-`·`sk-svcacct-`·
    # `sk-ant-api03-`)을 4자 만에 놓친다.
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key 형식
    re.compile(r"AIza[0-9A-Za-z_-]{35}"),  # Google API 키 형식
    re.compile(r"(?i)(api[_-]?key|secret|token|password|passwd|pwd)\s*[:=]\s*\S+"),
    re.compile(r"(?i)(aws_secret|db_password|secret_key|private_key)\s*[:=]"),
]

# 개인정보 — 자릿수·형식이 고정된 패턴.
PII_PATTERNS = [
    re.compile(r"\d{6}[-\s]?[1-4]\d{6}"),  # 주민등록번호
    re.compile(r"\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}"),  # 카드번호
    re.compile(r"01[016789][-\s]?\d{3,4}[-\s]?\d{4}"),  # 휴대전화번호(모듈 docstring 한계 참고)
]

#: 이메일 — **외부 관측 백엔드로 나가는 사본에만 쓴다**(`mask_for_export()`).
#:
#: `PII_PATTERNS`에 넣지 않는 건 의도적이다. 채팅 입력 마스킹과 메모리 write
#: guard가 그 목록을 공유하는데, 거기서 이메일을 가리면 "박서준한테 메일로
#: 공유해줘" 같은 정상 업무 요청이 망가진다. 반대로 Langfuse는
#: **서드파티 서버로 원문이 나가는** 경로라 이메일까지 가려야 한다
#: (`2026-08-19_01_작업계획.md` §4 — `jira_get_issues`의 `assignee_email`).
EMAIL_PATTERN = re.compile(r"\b[\w.-]+?@[\w.-]+?\.\w+?\b")

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
#: 대소문자 무시 + **긴 키워드부터** 매칭한다 — 짧은 키워드가 긴 키워드의 일부를
#: 먼저 잘라먹지 않게 한다. 지금 목록에는 겹치는 쌍이 없지만 새 키워드가 추가될
#: 때를 대비한 원칙이다.
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


def mask_for_storage(text: str) -> str:
    """`ChatMessageRepository`에 **쓰기 직전** 적용한다 — 화면·DB에 영구히
    남기 전에 credential·PII를 가린다.

    2026-08-27 결정 — 그 전까지는 사용자 발화를 저장할 때 항상 원문
    그대로였다("화면이 사용자 자신의 발화를 그대로 보여줘야 한다"는 원칙,
    `apps/chat/api_views.py`의 옛 주석). 채팅에 실제로 살아있는 API
    키·비밀번호를 붙여넣으면 그 값이 DB에 평문으로 영구히 남는다는 뜻이었다
    — LLM에게 안 보내는 것과는 다른 문제다: DB 백업·로그 적재·DB 접근
    권한이 있는 운영자는 여전히 그 값을 그대로 볼 수 있고, 키가 아직
    유효하면 레코드 하나가 곧 작동하는 크리덴셜이다.

    `mask_sensitive()`와 두 가지가 다르다.

    1. **`AUTHORITY_KEYWORDS`는 제외한다** — "관리자 비밀번호 알려줘" 같은
       *서술*은 실제 유출 가능한 값이 아니라 사용자가 무엇을 물었는지 보여주는
       기록이라, `mask_for_export()`와 같은 이유로 대화 이력에는 남긴다.
    2. **`PII_PATTERNS`는 포함한다** — `mask_sensitive()`가 채팅 입력·메모리에
       쓸 때 이 셋을 다 가리는 것과 같은 이유(모듈 상단 "왜 이메일은
       PII_PATTERNS에 없는가" 참고)로 주민등록번호·카드번호·전화번호 형태도
       저장 시점부터 가린다. 이 부분은 "사용자 자신의 발화를 그대로 보여준다"는
       기존 원칙과 정면으로 충돌하는 선택이다 — 그 원칙보다 저장 자체를 막는
       쪽을 우선한 것이다(2026-08-27, 사용자 결정).
    """

    masked = text
    for pattern in [*CREDENTIAL_PATTERNS, *PII_PATTERNS]:
        masked = pattern.sub(MASK_PLACEHOLDER, masked)
    return masked


#: `mask_for_export()`가 쓰는 자리표시자. `MASK_PLACEHOLDER`와 달리 카테고리를
#: 구분해 적는다 — trace는 사람이 디버깅하려고 보는 화면이라 "뭐가 지워졌는지"는
#: 남는 편이 낫고, 평가 채점기가 "trace에 원문이 없다"를 판정할 때 이 문자열을
#: 찾는다.
EXPORT_PLACEHOLDERS = {
    "email": "[REDACTED_EMAIL]",
    "credential": "[REDACTED_SECRET]",
    "pii": "[REDACTED_PII]",
}


def mask_for_export(text: str) -> str:
    """외부 관측 백엔드(Langfuse)로 **나가는 사본**에서 이메일·
    credential·개인정보 패턴을 가린다.

    `mask_sensitive()`와 두 가지가 다르다.

    1. **이메일을 포함한다** — 서드파티 서버로 원문이 나가는 경로라서다
       (`EMAIL_PATTERN` 주석 참고).
    2. **`AUTHORITY_KEYWORDS`는 제외한다** — 저건 "관리자 권한" 같은 *서술*을
       장기메모리에 못 쓰게 막는 규칙이지 유출될 값이 아니고, trace에서까지
       지우면 에이전트가 왜 그렇게 판단했는지를 디버깅할 수 없게 된다.

    사용처는 `services/agent_runtime/tracing/callbacks.py` 하나뿐이지만 패턴
    정의는 이 모듈에 둔다 — 모듈 docstring의 "무엇을 민감정보로 보는가는 여기
    한 곳에서 정한다" 원칙.
    """
    masked = EMAIL_PATTERN.sub(EXPORT_PLACEHOLDERS["email"], text)
    for pattern in CREDENTIAL_PATTERNS:
        masked = pattern.sub(EXPORT_PLACEHOLDERS["credential"], masked)
    for pattern in PII_PATTERNS:
        masked = pattern.sub(EXPORT_PLACEHOLDERS["pii"], masked)
    return masked


__all__ = [
    "AUTHORITY_KEYWORDS",
    "CATEGORY_LABELS",
    "CREDENTIAL_PATTERNS",
    "EMAIL_PATTERN",
    "EXPORT_PLACEHOLDERS",
    "MASK_PLACEHOLDER",
    "PII_PATTERNS",
    "mask_for_export",
    "mask_for_storage",
    "mask_sensitive",
    "match_category",
]
