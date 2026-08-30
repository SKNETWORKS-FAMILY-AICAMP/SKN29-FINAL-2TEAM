"""문서 처리 실패를 API·UI에 안전하게 노출하는 규칙."""

from __future__ import annotations


def safe_document_failure_detail(
    detail: object,
    *,
    state: str = "FAILED",
    error_type: str = "",
) -> str:
    """내부 주소·서명값·예외 구현을 제거하고 사용자가 할 행동만 남긴다."""

    def fallback() -> str:
        if state == "TIMED_OUT":
            return "문서를 읽는 시간이 초과되었습니다. 잠시 후 다시 읽어 주세요."
        if state == "CANCELLED":
            return "문서 읽기가 취소되었습니다. 다시 읽어 주세요."
        return "문서를 읽지 못했습니다. 잠시 후 다시 읽어 주세요."

    if not isinstance(detail, str) or not detail.strip():
        return fallback()

    message = detail.strip()
    technical = f"{error_type} {message}".lower()
    if any(
        marker in technical
        for marker in (
            "connectionpool",
            "connectionerror",
            "nameresolutionerror",
            "failed to resolve",
            "max retries exceeded",
            "connection refused",
            "temporary failure in name resolution",
        )
    ):
        return "문서 처리 서버에 연결하지 못했습니다. 잠시 후 다시 읽어 주세요."
    if any(marker in technical for marker in ("timeout", "timed out", "readtimeout")):
        return "문서를 읽는 시간이 초과되었습니다. 잠시 후 다시 읽어 주세요."
    if any(
        marker in technical
        for marker in (
            "http://",
            "https://",
            "?token=",
            "&token=",
            "access_token=",
            "api_key=",
            "apikey=",
            "signature=",
            "x-amz-credential",
            "x-amz-signature",
            "bearer ",
            "traceback",
            "secret",
            "authorization",
            "worker exited",
        )
    ):
        return fallback()
    return message[:500]


__all__ = ["safe_document_failure_detail"]
