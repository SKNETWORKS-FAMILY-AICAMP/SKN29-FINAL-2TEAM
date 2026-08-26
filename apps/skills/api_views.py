"""「스킬」 REST API — 설정 > 스킬 화면(`SkillsTab.tsx`)이 부르는 계약.

정본: docs/설계 및 구현/3_중간발표 이후/작업기록/Deep_Agents/2026-08-20_16_Skill_Middleware_설계.md.
실제 저장·검증은 `services.agent_runtime.skills.service`가 전담한다(채팅의
`skill_register` 도구와 같은 함수) — 여기는 인증·역할 조회와 HTTP 상태
코드 변환만 한다.

개인 스킬(`/me/skills/`)은 누구나 자기 것만 다루고, 팀 스킬(`/teams/skills/`)은
조회는 팀원 전체가, 생성·수정·삭제는 리더만 할 수 있다(정본 문서 "팀 스킬"
절 — 팀원이 팀 스킬로 등록해 달라고 요청하는 경로 자체가 없다).
"""

import logging

import psycopg
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authentication import BearerTokenAuthentication
from apps.accounts.serializers import account_role
from backend.db.errors import RecordNotFound, RepositoryError
from backend.db.repositories import AccountRepository
from services.agent_runtime.skills.service import (
    SkillError,
    SkillNameConflict,
    SkillNotFound,
    SkillPermissionDenied,
    create_personal_skill,
    create_team_skill,
    delete_personal_skill,
    delete_team_skill,
    get_personal_skill,
    get_team_skill,
    list_personal_skills,
    list_team_skills,
    update_personal_skill,
    update_team_skill,
)

from .serializers import skill_response

logger = logging.getLogger(__name__)


class AuthenticatedAPIView(APIView):
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def handle_exception(self, exc):
        """DRF가 처리 못 하는 예외를 여기서 마지막으로 잡는다.

        원래 목록 조회(GET) 두 개(`MySkillListCreateAPIView`/`TeamSkillListCreateAPIView`)는
        `try/except`가 아예 없었다 — `SkillError`가 아닌 예외(예: 저장소 첫
        연결 경합, `services/agent_runtime/memory/store.py` 2026-08-22 수정
        참고)가 나면 DRF 기본 `handle_exception`이 못 알아보는 예외는 다시
        던지고, Django가 그걸 HTML 500 페이지로 바꾼다. `apiRequest()`
        (`frontend/src/api/client.ts`)는 그 HTML을 JSON으로 못 읽어
        "요청을 처리하지 못했습니다. (상태 코드 500)"만 보여준다 — 진짜 원인이
        화면 어디에도 안 남는다. 여기서 잡아 항상 JSON으로 돌려준다.
        """
        if isinstance(exc, SkillError):
            return _skill_error_response(exc)
        if isinstance(exc, (RepositoryError, psycopg.Error)):
            return _profile_error_response(exc)
        try:
            return super().handle_exception(exc)
        except Exception:  # noqa: BLE001 — 마지막 안전망, 무엇이 올지 미리 모른다.
            logger.exception("스킬 API에서 예상하지 못한 오류")
            return Response(
                {"detail": "스킬 정보를 처리하지 못했습니다. 잠시 후 다시 시도해 주세요."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


def _profile_error_response(exc: Exception) -> Response:
    if isinstance(exc, RecordNotFound):
        return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
    if isinstance(exc, RepositoryError):
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(
        {"detail": "데이터베이스 요청을 처리할 수 없습니다.", "error": exc.__class__.__name__},
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


def _skill_error_response(exc: SkillError) -> Response:
    if isinstance(exc, SkillNotFound):
        return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
    if isinstance(exc, SkillNameConflict):
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
    if isinstance(exc, SkillPermissionDenied):
        return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
    return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


def _team_context(request) -> tuple[str, str] | Response:
    """이 계정의 `(team_id, role)`. 프로필을 못 찾으면 그 자리에서 Response를 돌려준다
    — 호출부가 `isinstance(result, Response)`로 갈라 쓴다."""

    try:
        profile = AccountRepository.get_profile(request.user.account_id)
    except (RepositoryError, psycopg.Error) as exc:
        return _profile_error_response(exc)
    return profile["team_id"], account_role(profile)


class MySkillListCreateAPIView(AuthenticatedAPIView):
    def get(self, request):
        skills = list_personal_skills(request.user.account_id)
        return Response([skill_response(row) for row in skills])

    def post(self, request):
        # 만들 때만 team_id가 필요하다 — 같은 이름의 팀 스킬이 있으면 만들어도
        # 에이전트에게 안 보이는 상태가 되므로(`create_personal_skill` 참고)
        # 여기서 막는다. 조회·수정·삭제는 이름이 안 바뀌니 필요 없다.
        context = _team_context(request)
        if isinstance(context, Response):
            return context
        team_id, _role = context

        data = request.data
        try:
            row = create_personal_skill(
                request.user.account_id,
                team_id=team_id,
                name=str(data.get("name", "")).strip(),
                description=str(data.get("description", "")).strip(),
                body=data.get("body", ""),
            )
        except SkillError as exc:
            return _skill_error_response(exc)
        return Response(skill_response(row), status=status.HTTP_201_CREATED)


class MySkillDetailAPIView(AuthenticatedAPIView):
    def get(self, request, name):
        try:
            row = get_personal_skill(request.user.account_id, name)
        except SkillError as exc:
            return _skill_error_response(exc)
        return Response(skill_response(row))

    def patch(self, request, name):
        data = request.data
        try:
            row = update_personal_skill(
                request.user.account_id,
                name,
                description=(str(data["description"]).strip() if "description" in data else None),
                body=(data["body"] if "body" in data else None),
                enabled=(bool(data["enabled"]) if "enabled" in data else None),
            )
        except SkillError as exc:
            return _skill_error_response(exc)
        return Response(skill_response(row))

    def delete(self, request, name):
        try:
            delete_personal_skill(request.user.account_id, name)
        except SkillError as exc:
            return _skill_error_response(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TeamSkillListCreateAPIView(AuthenticatedAPIView):
    def get(self, request):
        context = _team_context(request)
        if isinstance(context, Response):
            return context
        team_id, _role = context
        skills = list_team_skills(team_id)
        return Response([skill_response(row) for row in skills])

    def post(self, request):
        context = _team_context(request)
        if isinstance(context, Response):
            return context
        team_id, role = context
        data = request.data
        try:
            row = create_team_skill(
                team_id,
                actor_role=role,
                name=str(data.get("name", "")).strip(),
                description=str(data.get("description", "")).strip(),
                body=data.get("body", ""),
            )
        except SkillError as exc:
            return _skill_error_response(exc)
        return Response(skill_response(row), status=status.HTTP_201_CREATED)


class TeamSkillDetailAPIView(AuthenticatedAPIView):
    def get(self, request, name):
        context = _team_context(request)
        if isinstance(context, Response):
            return context
        team_id, _role = context
        try:
            row = get_team_skill(team_id, name)
        except SkillError as exc:
            return _skill_error_response(exc)
        return Response(skill_response(row))

    def patch(self, request, name):
        context = _team_context(request)
        if isinstance(context, Response):
            return context
        team_id, role = context
        data = request.data
        try:
            row = update_team_skill(
                team_id,
                name,
                actor_role=role,
                description=(str(data["description"]).strip() if "description" in data else None),
                body=(data["body"] if "body" in data else None),
                enabled=(bool(data["enabled"]) if "enabled" in data else None),
            )
        except SkillError as exc:
            return _skill_error_response(exc)
        return Response(skill_response(row))

    def delete(self, request, name):
        context = _team_context(request)
        if isinstance(context, Response):
            return context
        team_id, role = context
        try:
            delete_team_skill(team_id, name, actor_role=role)
        except SkillError as exc:
            return _skill_error_response(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)
