from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.projects.api_urls")),
    path("api/", include("apps.people.api_urls")),
]
