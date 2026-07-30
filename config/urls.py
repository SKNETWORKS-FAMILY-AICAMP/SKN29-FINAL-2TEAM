from django.urls import include, path

urlpatterns = [
    path("api/", include("apps.accounts.api_urls")),
    path("api/", include("apps.projects.api_urls")),
    path("api/", include("apps.people.api_urls")),
]
