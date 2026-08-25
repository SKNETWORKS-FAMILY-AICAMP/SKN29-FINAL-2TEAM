from django.urls import path

from .api_views import (
    HealthAPIView,
    ProjectDetailAPIView,
    ProjectJiraRegisterAPIView,
    ProjectPrimaryCandidateAPIView,
    ProjectListCreateAPIView,
    ProjectSourceDocumentAPIView,
    ProjectTaskSyncAPIView,
    RunPodDocumentDownloadAPIView,
    TaskExtractionRunAPIView,
    TeamDocumentAPIView,
    TeamDocumentIndexingAPIView,
    TeamDocumentLibraryAPIView,
    TeamDocumentReindexAPIView,
    TeamNewDocumentAPIView,
    TeamDocumentHistoryAPIView,
    TeamDocumentRemoveAPIView,
    TeamFolderAPIView,
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
    # 「문서」 화면이 쓰는 한 방 — 폴더 트리와 그 안의 파일 상태를 함께 준다.
    # 위 `documents/` 와 나눈 이유는 저쪽이 **문서의 신원**만 주기 때문이다.
    path(
        "team/documents/library/",
        TeamDocumentLibraryAPIView.as_view(),
        name="api_team_document_library",
    ),
    # 전역 진행 표시가 폴링하는 자리. 집계 넷만 준다.
    path(
        "team/documents/indexing/",
        TeamDocumentIndexingAPIView.as_view(),
        name="api_team_document_indexing",
    ),
    # 색인 재시도. **고정 경로들보다 아래에 두면 안 된다** — `<str:doc_id>` 가
    # 'library'·'indexing' 도 문서 id 로 받아 먹는다.
    path(
        "team/documents/<str:doc_id>/reindex/",
        TeamDocumentReindexAPIView.as_view(),
        name="api_team_document_reindex",
    ),
    # Drive 와 우리 DB 를 맞대 본다 — 새로 생긴 파일과 **사라진 파일**을 함께 준다.
    # 수집 자체는 자동이라(2026-08-15) 새 파일 쪽은 이제 쓰이지 않지만, 아래
    # `remove/` 가 내릴 대상을 찾아 주는 곳이 여기뿐이라 남긴다.
    path("team/documents/new/", TeamNewDocumentAPIView.as_view(), name="api_team_documents_new"),
    # Drive 에서 사라진 문서를 내린다. 대상은 위 `new/` 가 찾아 준다(쓰기를 갈라 뒀다).
    path(
        "team/documents/remove/",
        TeamDocumentRemoveAPIView.as_view(),
        name="api_team_document_remove",
    ),
    path(
        "team/documents/history/",
        TeamDocumentHistoryAPIView.as_view(),
        name="api_team_document_history",
    ),
    path("team/tasks/sync/", TeamTaskSyncAPIView.as_view(), name="api_team_task_sync"),
    path("team/workload/", TeamWorkloadAPIView.as_view(), name="api_team_workload"),
    # RunPod Worker 가 원문을 받아 가는 경로. 로그인 세션 대신 만료형 서명을 쓴다.
    path(
        "internal/runpod/documents/<str:doc_id>/",
        RunPodDocumentDownloadAPIView.as_view(),
        name="api_runpod_document_download",
    ),
    path("projects/", ProjectListCreateAPIView.as_view(), name="api_project_list_create"),
    # 프로젝트를 **만드는** 요청이라 프로젝트 하위가 아니다.
    path("projects/jira/", ProjectJiraRegisterAPIView.as_view(), name="api_project_jira_register"),
    # 아직 프로젝트가 없을 때도 부른다 — `<str:project_id>` 보다 **앞**에 둘 것.
    path(
        "projects/primary-candidates/",
        ProjectPrimaryCandidateAPIView.as_view(),
        name="api_project_primary_candidates",
    ),
    path("projects/<str:project_id>/", ProjectDetailAPIView.as_view(), name="api_project_detail"),
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
]
