from django.urls import path

from .api_views import (
    AnalysisRunDetailAPIView,
    DocumentProcessingRunAPIView,
    HealthAPIView,
    ProjectAnalysisRunAPIView,
    ProjectDetailAPIView,
    ProjectJiraRegisterAPIView,
    ProjectListCreateAPIView,
    ProjectSourceAPIView,
    ProjectSourceDocumentAPIView,
    ProjectTaskSyncAPIView,
    RunPodDocumentDownloadAPIView,
    TaskExtractionRunAPIView,
    TeamDeadlineAPIView,
    TeamDocumentAPIView,
    TeamPipelineDocumentAPIView,
    TeamDocumentDownloadAPIView,
    TeamDocumentHistoryAPIView,
    TeamDocumentMetaAPIView,
    TeamDocumentRegisterAPIView,
    TeamDocumentRemoveAPIView,
    TeamFolderAPIView,
    TeamNewDocumentAPIView,
    TeamTaskSyncAPIView,
    TeamWorkloadAPIView,
)

# 폴더·문서·부하는 `team/` 아래다(2026-08-04). 프로젝트에 속하지 않기 때문이다 —
# 폴더는 파일이 있는 경로일 뿐이고, 문서는 어느 프로젝트 것인지 열어 봐야 알며,
# 사람의 부하는 그가 맡은 모든 프로젝트의 합이다.
urlpatterns = [
    path("health/", HealthAPIView.as_view(), name="api_health"),
    path("team/folders/", TeamFolderAPIView.as_view(), name="api_team_folders"),
    path("team/documents/", TeamDocumentAPIView.as_view(), name="api_team_documents"),
    path("team/documents/new/", TeamNewDocumentAPIView.as_view(), name="api_team_documents_new"),
    # 요약·유형·키워드·요약 임베딩. 다운로드 다음 단계다(A안 — 8/11 확정 ⑥).
    path("team/documents/meta/", TeamDocumentMetaAPIView.as_view(), name="api_team_documents_meta"),
    # Drive 에서 사라진 문서를 내린다. 스캔(GET)이 조회만 하도록 쓰기를 갈라 뒀다.
    path(
        "team/documents/remove/",
        TeamDocumentRemoveAPIView.as_view(),
        name="api_team_document_remove",
    ),
    path(
        "team/documents/register/",
        TeamDocumentRegisterAPIView.as_view(),
        name="api_team_document_register",
    ),
    path(
        "team/documents/history/",
        TeamDocumentHistoryAPIView.as_view(),
        name="api_team_document_history",
    ),
    path(
        "team/documents/download/",
        TeamDocumentDownloadAPIView.as_view(),
        name="api_team_document_download",
    ),
    path("team/tasks/sync/", TeamTaskSyncAPIView.as_view(), name="api_team_task_sync"),
    path("team/workload/", TeamWorkloadAPIView.as_view(), name="api_team_workload"),
    path("team/deadlines/", TeamDeadlineAPIView.as_view(), name="api_team_deadlines"),
    # 문서 처리(파싱·청킹·임베딩)는 **팀** 단위다. 프로젝트에 묶이는 것은 기준
    # 문서로 선택될 때이고, 그 선택 화면은 이미 처리된 문서를 골라야 한다.
    path(
        "team/pipeline-documents/",
        TeamPipelineDocumentAPIView.as_view(),
        name="api_team_pipeline_documents",
    ),
    path(
        "team/documents/<str:doc_id>/processing-runs/",
        DocumentProcessingRunAPIView.as_view(),
        name="api_document_processing_run",
    ),
    path(
        "team/documents/<str:doc_id>/processing-runs/<str:job_id>/",
        DocumentProcessingRunAPIView.as_view(),
        name="api_document_processing_run_detail",
    ),
    # RunPod Worker 가 원문을 받아 가는 경로. 로그인 세션 대신 만료형 서명을 쓴다.
    path(
        "internal/runpod/documents/<str:doc_id>/",
        RunPodDocumentDownloadAPIView.as_view(),
        name="api_runpod_document_download",
    ),
    path("projects/", ProjectListCreateAPIView.as_view(), name="api_project_list_create"),
    # 프로젝트를 **만드는** 요청이라 프로젝트 하위가 아니다.
    path("projects/jira/", ProjectJiraRegisterAPIView.as_view(), name="api_project_jira_register"),
    path("projects/<str:project_id>/", ProjectDetailAPIView.as_view(), name="api_project_detail"),
    path(
        "projects/<str:project_id>/sources/",
        ProjectSourceAPIView.as_view(),
        name="api_project_sources",
    ),
    path(
        "projects/<str:project_id>/tasks/sync/",
        ProjectTaskSyncAPIView.as_view(),
        name="api_project_task_sync",
    ),
    # 이 프로젝트의 기준 문서·서브 문서. PUT 이 프로젝트에 문서를 묶는 행위다.
    path(
        "projects/<str:project_id>/source-documents/",
        ProjectSourceDocumentAPIView.as_view(),
        name="api_project_source_documents",
    ),
    path(
        "projects/<str:project_id>/task-extraction-runs/",
        TaskExtractionRunAPIView.as_view(),
        name="api_task_extraction_run",
    ),
    path(
        "projects/<str:project_id>/assignment-runs/",
        ProjectAnalysisRunAPIView.as_view(),
        name="api_project_assignment_runs",
    ),
    path(
        "projects/<str:project_id>/analysis-runs/",
        ProjectAnalysisRunAPIView.as_view(),
        name="api_project_analysis_runs_compat",
    ),
    path("assignment-runs/<str:run_id>/", AnalysisRunDetailAPIView.as_view(), name="api_assignment_run_detail"),
    path("analysis-runs/<str:run_id>/", AnalysisRunDetailAPIView.as_view(), name="api_analysis_run_detail_compat"),
]
