"""감사 로그 API. 전부 읽기 전용이라 입력값이 없고, 인증 예외는 `AdminView`가
공통으로 처리한다(섹션 1과 동일). 분석·결정 기록 4개 엔드포인트는 추천
파이프라인이 아직 이 저장소에 없어 항상 빈 목록을 반환한다(`OpsAuditRepository`
docstring 참고) — 그 자체는 오류가 아니라 정상 동작이다."""

import psycopg
from rest_framework.response import Response

from backend.api_errors import to_response
from backend.db import OpsAuditRepository

from ..authentication import AdminView


class OperationLogView(AdminView):
    def get(self, request):
        try:
            rows = OpsAuditRepository.list_operations()
        except psycopg.Error as exc:
            return to_response(exc)
        return Response(rows)


class AssignmentRunLogView(AdminView):
    def get(self, request):
        try:
            rows = OpsAuditRepository.list_assignment_runs()
        except psycopg.Error as exc:
            return to_response(exc)
        return Response(rows)


class RecommendationLogView(AdminView):
    def get(self, request):
        try:
            rows = OpsAuditRepository.list_recommendations()
        except psycopg.Error as exc:
            return to_response(exc)
        return Response(rows)


class ValidationLogView(AdminView):
    def get(self, request):
        try:
            rows = OpsAuditRepository.list_validations()
        except psycopg.Error as exc:
            return to_response(exc)
        return Response(rows)


class DecisionLogView(AdminView):
    def get(self, request):
        try:
            rows = OpsAuditRepository.list_decisions()
        except psycopg.Error as exc:
            return to_response(exc)
        return Response(rows)
