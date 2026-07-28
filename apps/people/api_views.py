import psycopg
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.db import OrganizationRepository, PersonRepository

from .serializers import organization_response, person_response


class OrganizationListAPIView(APIView):
    def get(self, request):
        try:
            rows = OrganizationRepository.list_active()
        except psycopg.Error as exc:
            return Response(
                {"detail": "조직 데이터를 조회할 수 없습니다.", "error": exc.__class__.__name__},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response([organization_response(row) for row in rows])


class PersonListAPIView(APIView):
    def get(self, request):
        try:
            rows = PersonRepository.list_active()
        except psycopg.Error as exc:
            return Response(
                {"detail": "직원 데이터를 조회할 수 없습니다.", "error": exc.__class__.__name__},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response([person_response(row) for row in rows])
