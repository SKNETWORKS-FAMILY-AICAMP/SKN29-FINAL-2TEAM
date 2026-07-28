from django.urls import path

from .api_views import AnalysisRunDetailAPIView, HealthAPIView, ProjectAnalysisRunAPIView, ProjectDetailAPIView, ProjectListCreateAPIView

urlpatterns = [
    path("health/", HealthAPIView.as_view(), name="api_health"),
    path("projects/", ProjectListCreateAPIView.as_view(), name="api_project_list_create"),
    path("projects/<uuid:project_id>/", ProjectDetailAPIView.as_view(), name="api_project_detail"),
    path("projects/<uuid:project_id>/analysis-runs/", ProjectAnalysisRunAPIView.as_view(), name="api_project_analysis_runs"),
    path("analysis-runs/<uuid:run_id>/", AnalysisRunDetailAPIView.as_view(), name="api_analysis_run_detail"),
]
