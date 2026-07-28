from django.urls import path

from .api_views import OrganizationListAPIView, PersonListAPIView

urlpatterns = [
    path("organizations/", OrganizationListAPIView.as_view(), name="api_organization_list"),
    path("people/", PersonListAPIView.as_view(), name="api_person_list"),
]
