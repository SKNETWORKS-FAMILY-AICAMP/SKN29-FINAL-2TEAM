"""전역 정책 API.

초대 만료 기간(`invite-ttl/`)은 조회 시 검증할 입력이 없고, 저장 시에는
`InviteTtlSerializer`가 `days`의 타입만 확인하고 나머지(1~90 범위, 변경 여부)는
`OpsPolicyRepository`가 판단한다. 시스템 공지(`notices/`)는 `NoticeSerializer`가
타입만 확인하고, 제목·내용 공백/일정 누락 검증은 Repository가 한글 문구로
직접 던진다 — 두 계층에서 서로 다른 문구가 나오는 것을 피하기 위함.
"""

from datetime import datetime
from typing import Any

import psycopg
from django.utils import timezone
from rest_framework.response import Response

from backend.api_errors import to_response
from backend.db import GuardrailEventRepository, OpsPolicyRepository
from backend.db.errors import RepositoryError

from ..authentication import AdminView
from ..serializers import (
    GuardrailPolicySerializer,
    guardrail_event_row_response,
    InviteTtlSerializer,
    NoticeDeleteSerializer,
    NoticeSerializer,
    notice_row_response,
    policy_change_row_response,
)


def _combine_schedule(data: dict[str, Any]):
    """날짜·시간이 둘 다 있을 때만 하나의 타임존 인지 datetime으로 합친다.

    둘 중 하나라도 없으면 None을 돌려주고, "날짜와 시간을 선택해 주세요"라는
    구체적인 한글 메시지는 Repository가 낸다(여기서 즉시 400을 내지 않음).
    """

    schedule_date = data.get("schedule_date")
    schedule_time = data.get("schedule_time")
    if schedule_date is None or schedule_time is None:
        return None
    return timezone.make_aware(datetime.combine(schedule_date, schedule_time))


class InviteTtlView(AdminView):
    def get(self, request):
        try:
            days = OpsPolicyRepository.get_invite_ttl_days()
        except psycopg.Error as exc:
            return to_response(exc)
        return Response({"days": days})

    def put(self, request):
        serializer = InviteTtlSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            result = OpsPolicyRepository.set_invite_ttl_days(
                days=serializer.validated_data["days"],
                actor_account_id=request.user.account_id,
                reason=serializer.validated_data["reason"],
            )
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)
        return Response(result)


class GuardrailPolicyView(AdminView):
    """가드레일 정책 조회·저장.

    응답은 정책 한 벌 그대로다 — Repository가 빠진 항목을 기본값으로 채워
    **항상 같은 모양**을 주므로, 화면이 `?.` 체인이나 자체 기본값을 들 필요가 없다.
    """

    def get(self, request):
        try:
            policy = OpsPolicyRepository.get_guardrail_policy()
        except psycopg.Error as exc:
            return to_response(exc)
        return Response(policy)

    def put(self, request):
        serializer = GuardrailPolicySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            saved = OpsPolicyRepository.set_guardrail_policy(
                policy=serializer.validated_data["policy"],
                actor_account_id=request.user.account_id,
                reason=serializer.validated_data["reason"],
            )
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)
        return Response(saved)


class NoticeListCreateView(AdminView):
    def get(self, request):
        try:
            rows = OpsPolicyRepository.list_notices()
        except psycopg.Error as exc:
            return to_response(exc)
        return Response([notice_row_response(row) for row in rows])

    def post(self, request):
        serializer = NoticeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            notice = OpsPolicyRepository.create_notice(
                title=data["title"],
                content=data["content"],
                status=data["status"],
                schedule_at=_combine_schedule(data),
                schedule_mode=data["schedule_mode"],
                actor_account_id=request.user.account_id,
                reason=data["reason"],
            )
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)
        return Response(notice_row_response(notice))


class NoticeDetailView(AdminView):
    def put(self, request, notice_id):
        serializer = NoticeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            notice = OpsPolicyRepository.update_notice(
                notice_id=notice_id,
                title=data["title"],
                content=data["content"],
                status=data["status"],
                schedule_at=_combine_schedule(data),
                schedule_mode=data["schedule_mode"],
                actor_account_id=request.user.account_id,
                reason=data["reason"],
            )
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)
        return Response(notice_row_response(notice))

    def delete(self, request, notice_id):
        serializer = NoticeDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            OpsPolicyRepository.delete_notice(
                notice_id=notice_id,
                actor_account_id=request.user.account_id,
                reason=serializer.validated_data["reason"],
            )
        except (RepositoryError, psycopg.Error) as exc:
            return to_response(exc)
        return Response(status=204)


class PolicyChangeListView(AdminView):
    def get(self, request):
        try:
            rows = OpsPolicyRepository.list_policy_changes()
        except psycopg.Error as exc:
            return to_response(exc)
        return Response([policy_change_row_response(row) for row in rows])


class GuardrailEventListView(AdminView):
    """가드레일이 실제로 발동한 기록.

    「정책 변경 이력」(사람이 정책을 바꾼 것)과 나란히 둔다 — 정한 것과 걸린 것을
    한 화면에서 봐야 기준값을 어디로 옮길지 판단할 수 있다.
    """

    #: 화면이 한 번에 받는 최대 건수. 「정책 변경 이력」과 달리 발동은 사용자
    #: 발화마다 날 수 있어 상한을 둔다.
    LIMIT = 100

    def get(self, request):
        try:
            rows = GuardrailEventRepository.list_recent(limit=GuardrailEventListView.LIMIT)
        except psycopg.Error as exc:
            return to_response(exc)
        return Response([guardrail_event_row_response(row) for row in rows])
