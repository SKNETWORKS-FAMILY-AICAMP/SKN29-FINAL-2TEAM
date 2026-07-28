"""분석 실행의 생성·상태 전이를 담당한다.

문서 파싱, PKM 생성, Snapshot, Readiness 계산은 이후 각 Service가 구현되면
이 Service에서 순서대로 호출한다. View/API View에는 업무 로직을 넣지 않는다.
"""

from django.conf import settings
from django.utils import timezone

from apps.projects.models import AnalysisRun, AnalysisRunStatus, Project


def create_analysis_run(*, project: Project, requested_by) -> AnalysisRun:
    run = AnalysisRun.objects.create(project=project, requested_by=requested_by)

    # 베이스 코드 단계에서는 외부 Connector·파서가 없으므로 실행을 위장하지 않는다.
    # 실제 엔진 구현 시 이 자리를 DB Job 또는 SQS Worker 등록으로 교체한다.
    if settings.ANALYSIS_EXECUTION_MODE == "stub":
        run.snapshot_as_of = timezone.now()
        run.status = AnalysisRunStatus.CREATED
        run.readiness_status = "PENDING"
        run.limitations = ["문서 수집·PKM·Snapshot·추천 엔진은 아직 연결되지 않았습니다."]
        run.save(update_fields=["snapshot_as_of", "status", "readiness_status", "limitations", "updated_at"])

    return run
