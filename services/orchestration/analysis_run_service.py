"""배정 실행 생성은 `backend.db.AnalysisRunRepository`가 담당한다.

과거 Django ORM `AnalysisRun` 모델을 사용하던 Service는 제거했다. 문서 파싱,
PKM, Snapshot, Readiness 실행 순서는 각 기능이 구현될 때 이 모듈에서
Repository 호출을 조합한다.
"""

from backend.db import AnalysisRunRepository


def create_assignment_run(**kwargs):
    return AnalysisRunRepository.create(**kwargs)
