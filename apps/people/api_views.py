from rest_framework import permissions
from rest_framework.generics import ListAPIView

from .models import Organization, Person
from .serializers import OrganizationSerializer, PersonSerializer


class OrganizationListAPIView(ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OrganizationSerializer
    queryset = Organization.objects.select_related("parent").filter(is_active=True)


class PersonListAPIView(ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PersonSerializer
    queryset = Person.objects.select_related("organization").filter(is_active=True)
