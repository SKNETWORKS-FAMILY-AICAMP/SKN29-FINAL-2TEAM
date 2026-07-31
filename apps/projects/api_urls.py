from django.urls import path

from .api_views import (
    AnalysisRunDetailAPIView,
    HealthAPIView,
    ProjectAnalysisRunAPIView,
    ProjectDetailAPIView,
    ProjectDocumentAPIView,
    ProjectDocumentDownloadAPIView,
    ProjectListCreateAPIView,
    ProjectSourceAPIView,
)

urlpatterns = [
    path("health/", HealthAPIView.as_view(), name="api_health"),
    path("projects/", ProjectListCreateAPIView.as_view(), name="api_project_list_create"),
    path("projects/<str:project_id>/", ProjectDetailAPIView.as_view(), name="api_project_detail"),
    path(
        "projects/<str:project_id>/sources/",
        ProjectSourceAPIView.as_view(),
        name="api_project_sources",
    ),
    path(
        "projects/<str:project_id>/documents/",
        ProjectDocumentAPIView.as_view(),
        name="api_project_documents",
    ),
    path(
        "projects/<str:project_id>/documents/download/",
        ProjectDocumentDownloadAPIView.as_view(),
        name="api_project_document_download",
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
