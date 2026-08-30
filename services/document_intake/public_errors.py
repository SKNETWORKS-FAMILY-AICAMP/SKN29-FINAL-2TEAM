"""문서 처리 실패를 API·UI에 안전하게 노출하는 규칙.

**허용 목록이지 차단 목록이 아니다.** 처음에는 「위험해 보이는 표지가 있으면
막고 나머지는 원문 그대로」였는데, 그 방식은 표지를 하나 빠뜨릴 때마다 샌다 —
실제로 내부 경로(`/srv/app/media/...`), 내부 주소(`10.0.3.14:8000`), JWT,
`HF_TOKEN=...` 이 그대로 통과했다. 표지 목록을 늘려도 다음에 무엇이 올지는 모른다.

그래서 **바깥에서 온 문자열은 화면에 절대 싣지 않는다.** 그것으로 하는 일은
아래 `_CATALOGUE` 중 하나를 고르는 것뿐이고, 화면에 나가는 문장은 전부 우리가
여기 적어 둔 것이다. 원문은 사라지지 않는다 — 부르는 쪽이 로그에 남긴다
(`services/document_intake/service.py`).

**구체성은 분류로 지킨다.** 이 칸을 만든 이유가 「칸만 있고 말은 없는 상태」를
없애는 것이었으므로(2026-08-24), 하나로 뭉뚱그리지 않고 사람이 할 행동이 갈리는
만큼 나눈다 — 파일을 고쳐 다시 올릴 일, 잠시 뒤 다시 읽을 일, 기다릴 일.
워커가 준 표 번호·청크 참조 같은 내부 식별자는 사용자가 할 수 있는 일을 바꾸지
않으므로 로그에만 둔다.
"""

from __future__ import annotations

_GENERIC = "문서를 읽지 못했습니다. 잠시 후 다시 읽어 주세요."
_TIMEOUT = "문서를 읽는 시간이 초과되었습니다. 잠시 후 다시 읽어 주세요."
_CANCELLED = "문서 읽기가 취소되었습니다. 다시 읽어 주세요."
_UNREACHABLE = "문서 처리 서버에 연결하지 못했습니다. 잠시 후 다시 읽어 주세요."
_UNREADABLE = "문서에서 읽을 내용을 찾지 못했습니다. 파일을 확인해 다시 올려 주세요."
_INCOMPLETE = "문서 내용을 정리하지 못했습니다. 잠시 후 다시 읽어 주세요."

#: 이 함수가 낼 수 있는 문장 전부. 저장된 값이 이 중 하나면 그대로 돌려준다 —
#: 쓸 때 한 번(`service.py`) 읽을 때 한 번(`serializers.py`) 두 번 거치므로
#: **두 번 넣어도 같은 값이 나와야 한다.**
_CATALOGUE = frozenset(
    {_GENERIC, _TIMEOUT, _CANCELLED, _UNREACHABLE, _UNREADABLE, _INCOMPLETE}
)

#: 저장 계층이 직접 쓰는 문구. 바깥에서 온 것이 아니라 우리가 적은 문장이라
#: 그대로 내보낸다(`apps/personal_files/api_views.py`, `service.py`).
_AUTHORED = frozenset(
    {
        "문서를 읽지 못했습니다. 다시 올려 주세요.",
        "처리 결과가 비어 있습니다.",
        "원문을 아직 받지 않았습니다.",
    }
)

_STATE_MESSAGES = {"TIMED_OUT": _TIMEOUT, "CANCELLED": _CANCELLED}

#: 원인을 나누는 표지. **고르는 데만 쓰고 원문을 내보내지는 않는다.**
_CLASSIFIERS = (
    (
        (
            "connectionpool",
            "connectionerror",
            "nameresolutionerror",
            "failed to resolve",
            "max retries exceeded",
            "connection refused",
            "temporary failure in name resolution",
        ),
        _UNREACHABLE,
    ),
    (("timeout", "timed out"), _TIMEOUT),
    (("invaliddocumenterror", "unsupportedmedia"), _UNREADABLE),
    (("chunkvalidationerror",), _INCOMPLETE),
)


def safe_document_failure_detail(
    detail: object,
    *,
    state: str = "FAILED",
    error_type: str = "",
) -> str:
    """화면에 실을 실패 사유. 반환값은 항상 이 모듈이 적어 둔 문장이다."""

    message = detail.strip() if isinstance(detail, str) else ""
    if message in _CATALOGUE or message in _AUTHORED:
        return message

    evidence = f"{error_type} {message}".lower()
    for markers, chosen in _CLASSIFIERS:
        if any(marker in evidence for marker in markers):
            return chosen
    return _STATE_MESSAGES.get(state, _GENERIC)


__all__ = ["safe_document_failure_detail"]
