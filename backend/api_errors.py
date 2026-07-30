"""Repository 예외 → DRF 응답 변환.

`backend/db/errors.py`는 DB 접근 계층 예외만 정의하고 HTTP를 모른다. 이 모듈이
그 예외를 실제 API 응답으로 바꾸는 유일한 자리다 — 앱마다 같은 변환 함수를
새로 베껴 쓰지 않기 위함.
"""

from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response

from .db.errors import DuplicateRecord, PermissionDenied, RecordNotFound, ReferenceNotFound, RepositoryError


class ServiceUnavailable(APIException):
    """DB 예외를 뷰 밖(예: 인증 클래스의 `authenticate()`)에서 알릴 때 쓴다.

    `authenticate()`는 `Response`를 반환할 수 없고 예외만 raise할 수 있어서
    `to_response()`를 쓸 수 없다 — DRF 예외 처리 파이프라인이 대신 503으로
    렌더링하도록 이 예외를 raise한다.
    """

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "데이터베이스 요청을 처리할 수 없습니다."
    default_code = "service_unavailable"


def to_response(exc: Exception) -> Response:
    if isinstance(exc, RecordNotFound):
        return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
    if isinstance(exc, PermissionDenied):
        return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
    if isinstance(exc, (DuplicateRecord, ReferenceNotFound)):
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
    if isinstance(exc, RepositoryError):
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(
        {"detail": "데이터베이스 요청을 처리할 수 없습니다.", "error": exc.__class__.__name__},
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )
