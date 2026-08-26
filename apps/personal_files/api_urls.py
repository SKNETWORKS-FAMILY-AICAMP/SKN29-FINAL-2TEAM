from django.urls import path

from .api_views import (
    PersonalFileDetailAPIView,
    PersonalFileDownloadAPIView,
    PersonalFileListAPIView,
    PersonalFileReindexAPIView,
    SharedFileListAPIView,
)

# 「내 파일」은 **계정** 소유다. 팀도 프로젝트도 아래에 두지 않는다 —
# 그 둘에 걸면 팀을 옮기거나 프로젝트가 지워질 때 내 파일이 딸려 간다.
urlpatterns = [
    path("me/files/", PersonalFileListAPIView.as_view(), name="api_personal_files"),
    # `<doc_id>` 앞에 둔다 — 뒤에 있으면 `shared` 가 doc_id 로 잡힌다.
    path("me/files/shared/", SharedFileListAPIView.as_view(), name="api_shared_files"),
    path(
        "me/files/<str:doc_id>/download/",
        PersonalFileDownloadAPIView.as_view(),
        name="api_personal_file_download",
    ),
    path(
        "me/files/<str:doc_id>/reindex/",
        PersonalFileReindexAPIView.as_view(),
        name="api_personal_file_reindex",
    ),
    path("me/files/<str:doc_id>/", PersonalFileDetailAPIView.as_view(), name="api_personal_file_detail"),
]
