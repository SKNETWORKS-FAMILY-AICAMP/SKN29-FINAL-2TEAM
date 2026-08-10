from django.urls import path

from .api_views import (
    ChatConfirmAPIView,
    ChatMessageAPIView,
    ChatSessionDetailAPIView,
    ChatSessionListCreateAPIView,
)

# 대화는 프로젝트가 아니라 팀에 속한다. `proj_id` 는 문맥일 뿐이고 없을 수도
# 있어서, 경로를 `projects/<id>/` 아래로 넣지 않는다.
urlpatterns = [
    path("sessions/", ChatSessionListCreateAPIView.as_view(), name="api_chat_sessions"),
    path(
        "sessions/<str:session_id>/",
        ChatSessionDetailAPIView.as_view(),
        name="api_chat_session_detail",
    ),
    path(
        "sessions/<str:session_id>/messages/",
        ChatMessageAPIView.as_view(),
        name="api_chat_messages",
    ),
    path(
        "sessions/<str:session_id>/confirm/",
        ChatConfirmAPIView.as_view(),
        name="api_chat_confirm",
    ),
]
