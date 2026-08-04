from django.urls import path

from .api_views import (
    AnalysisRunDetailAPIView,
    HealthAPIView,
    ProjectAnalysisRunAPIView,
    ProjectDetailAPIView,
    ProjectJiraRegisterAPIView,
    ProjectListCreateAPIView,
    ProjectSourceAPIView,
    ProjectTaskSyncAPIView,
    TeamDocumentAPIView,
    TeamDocumentDownloadAPIView,
    TeamDocumentHistoryAPIView,
    TeamDocumentRegisterAPIView,
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
