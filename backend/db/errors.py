"""직접 SQL 접근 계층에서 API로 전달할 도메인 오류."""


class RepositoryError(Exception):
    """Repository 처리 실패의 기본 오류."""


class RecordNotFound(RepositoryError):
    """요청한 레코드가 존재하지 않음."""


class ReferenceNotFound(RepositoryError):
    """FK가 없는 참조 컬럼의 대상 레코드가 존재하지 않음."""


class IdSpaceExhausted(RepositoryError):
    """5자리 코드의 가용 범위를 모두 사용함."""
