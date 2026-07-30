"""직접 SQL 접근 계층에서 API로 전달할 도메인 오류."""


class RepositoryError(Exception):
    """Repository 처리 실패의 기본 오류."""


class RecordNotFound(RepositoryError):
    """요청한 레코드가 존재하지 않음."""


class ReferenceNotFound(RepositoryError):
    """FK가 없는 참조 컬럼의 대상 레코드가 존재하지 않음."""


class IdSpaceExhausted(RepositoryError):
    """5자리 코드의 가용 범위를 모두 사용함."""


class DuplicateRecord(RepositoryError):
    """유니크 제약과 충돌하는 레코드를 만들려고 함."""


class PermissionDenied(RepositoryError):
    """요청자가 대상 레코드를 다룰 권한이 없음."""
