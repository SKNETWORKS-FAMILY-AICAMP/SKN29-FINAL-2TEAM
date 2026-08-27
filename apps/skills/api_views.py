"""「스킬」 REST API — 설정 > 스킬 화면(`SkillsTab.tsx`)이 부르는 계약.

정본: docs/설계 및 구현/3_중간발표 이후/작업기록/Deep_Agents/2026-08-20_16_Skill_Middleware_설계.md.
실제 저장·검증은 `services.agent_runtime.skills.service`가 전담한다(채팅의
`skill_register` 도구와 같은 함수) — 여기는 인증·역할 조회와 HTTP 상태
코드 변환만 한다.

개인 스킬(`/me/skills/`)은 누구나 자기 것만 다룬다. 팀 스킬
(`/teams/skills/`)은 검증된 개인 스킬을 공유해서만 생기는 카탈로그다.
팀원은 조회·가져오기, 공유자는 공유 중지, 리더는 카탈로그 삭제만 할 수 있다.
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
from backend.db.skill_jobs import SkillRegistrationJobRepository
from services.agent_runtime.skills.registration import SkillRegistrationService
from services.agent_runtime.skills.document import SkillDocument
from services.agent_runtime.skills.service import (
    SkillError,
    SkillNameConflict,
    SkillNotFound,
    SkillPermissionDenied,
    MAX_SKILL_BODY_BYTES,
    delete_personal_skill_and_shared_copy,
    delete_team_skill,
    get_personal_skill,
    get_team_skill,
    import_team_skill,
    list_personal_skills,
    list_team_skills,
    share_personal_skill,
    stop_sharing_personal_skill,
    update_personal_skill_and_shared_copy,
)

from .serializers import job_response, skill_response

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
        return Response([skill_response(row, account_id=request.user.account_id) for row in skills])

    def post(self, request):
        context = _team_context(request)
        if isinstance(context, Response):
            return context
        team_id, _role = context
        data = request.data
        try:
            frontmatter = None
            if data.get("source_content"):
                source_content = str(data["source_content"])
                if len(source_content.encode("utf-8")) > MAX_SKILL_BODY_BYTES:
                    raise SkillError(
                        f"스킬 파일은 {MAX_SKILL_BODY_BYTES // 1024}KB를 넘을 수 없습니다."
                    )
                try:
                    uploaded = SkillDocument.parse(source_content)
                except ValueError as exc:
                    # YAML 파서의 행·열/토큰 오류는 사용자가 고칠 방향을 알려 주지
                    # 못하고 내부 구현만 노출한다. 업로드 화면에서는 필요한 구조를
                    # 안내하고 원인은 서버 로그에만 남긴다.
                    logger.info("스킬 파일 frontmatter 파싱 실패", exc_info=exc)
                    raise SkillError(
                        "스킬 파일의 기본 정보 형식을 확인해 주세요. "
                        "파일 맨 위에 name과 description을 올바른 YAML 형식으로 적어야 합니다."
                    ) from exc
                name = uploaded.name
                description = uploaded.description
                body = uploaded.body
                frontmatter = uploaded.frontmatter
            else:
                name = str(data.get("name", "")).strip()
                description = str(data.get("description", "")).strip()
                body = data.get("body", "")
            result = SkillRegistrationService.enqueue(
                account_id=request.user.account_id,
                team_id=team_id,
                name=name,
                description=description,
                body=body,
                frontmatter=frontmatter,
            )
        except SkillError as exc:
            return _skill_error_response(exc)
        return Response(
            job_response(result.job),
            status=status.HTTP_202_ACCEPTED if result.created else status.HTTP_200_OK,
        )


class MySkillDetailAPIView(AuthenticatedAPIView):
    def get(self, request, name):
        try:
            row = get_personal_skill(request.user.account_id, name)
        except SkillError as exc:
            return _skill_error_response(exc)
        return Response(skill_response(row, account_id=request.user.account_id))

    def patch(self, request, name):
        context = _team_context(request)
        if isinstance(context, Response):
            return context
        team_id, _role = context
        data = request.data
        content_keys = {"description", "body"}.intersection(data)
        if content_keys and "enabled" in data:
            return Response(
                {"detail": "내용 수정과 활성 상태 변경은 따로 요청해 주세요."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            if content_keys:
                current = get_personal_skill(request.user.account_id, name)
                result = SkillRegistrationService.enqueue(
                    account_id=request.user.account_id,
                    team_id=team_id,
                    name=name,
                    description=(
                        str(data["description"]).strip()
                        if "description" in data
                        else current["description"]
                    ),
                    body=data["body"] if "body" in data else current["body"],
                    frontmatter=current.get("frontmatter"),
                )
                return Response(
                    job_response(result.job),
                    status=status.HTTP_202_ACCEPTED if result.created else status.HTTP_200_OK,
                )
            if set(data) != {"enabled"}:
                return Response(
                    {"detail": "수정할 설명, 내용 또는 활성 상태를 보내 주세요."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            row = update_personal_skill_and_shared_copy(
                request.user.account_id,
                team_id=team_id,
                name=name,
                enabled=bool(data["enabled"]),
            )
        except SkillError as exc:
            return _skill_error_response(exc)
        return Response(skill_response(row, account_id=request.user.account_id))

    def delete(self, request, name):
        context = _team_context(request)
        if isinstance(context, Response):
            return context
        team_id, _role = context
        try:
            delete_personal_skill_and_shared_copy(
                request.user.account_id, team_id=team_id, name=name
            )
        except SkillError as exc:
            return _skill_error_response(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MySkillShareAPIView(AuthenticatedAPIView):
    """개인 스킬 한 건을 현재 팀에 공유하거나 공유를 중지한다."""

    def post(self, request, name):
        context = _team_context(request)
        if isinstance(context, Response):
            return context
        team_id, role = context
        try:
            row = share_personal_skill(
                request.user.account_id, team_id=team_id, name=name
            )
        except SkillError as exc:
            return _skill_error_response(exc)
        row["can_delete"] = role == "leader"
        return Response(
            skill_response(row, account_id=request.user.account_id),
            status=status.HTTP_201_CREATED,
        )

    def delete(self, request, name):
        context = _team_context(request)
        if isinstance(context, Response):
            return context
        team_id, _role = context
        try:
            stop_sharing_personal_skill(
                request.user.account_id, team_id=team_id, name=name
            )
        except SkillError as exc:
            return _skill_error_response(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TeamSkillListCreateAPIView(AuthenticatedAPIView):
    def get(self, request):
        context = _team_context(request)
        if isinstance(context, Response):
            return context
        team_id, role = context
        skills = list_team_skills(team_id)
        imported_names = {
            row.get("imported_from_skill_name")
            for row in list_personal_skills(request.user.account_id)
            if row.get("imported_from_team_id") == team_id
        }
        for row in skills:
            row["imported_by_me"] = row["name"] in imported_names
            row["can_delete"] = role == "leader"
        return Response(
            [skill_response(row, account_id=request.user.account_id) for row in skills]
        )

class TeamSkillImportAPIView(AuthenticatedAPIView):
    """팀 공유 카탈로그의 스킬을 현재 사용자의 독립 개인 사본으로 가져온다."""

    def post(self, request, name):
        context = _team_context(request)
        if isinstance(context, Response):
            return context
        team_id, _role = context
        try:
            result = import_team_skill(
                request.user.account_id,
                team_id=team_id,
                name=name,
            )
        except SkillError as exc:
            return _skill_error_response(exc)
        if result["requires_validation"]:
            return Response(
                job_response(result["job"]),
                status=status.HTTP_202_ACCEPTED if result.get("created") else status.HTTP_200_OK,
            )
        return Response(
            skill_response(result["skill"], account_id=request.user.account_id),
            status=status.HTTP_201_CREATED,
        )


class TeamSkillDetailAPIView(AuthenticatedAPIView):
    def get(self, request, name):
        context = _team_context(request)
        if isinstance(context, Response):
            return context
        team_id, role = context
        try:
            row = get_team_skill(team_id, name)
        except SkillError as exc:
            return _skill_error_response(exc)
        row["can_delete"] = role == "leader"
        return Response(skill_response(row, account_id=request.user.account_id))

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


class SkillRegistrationJobListCreateAPIView(AuthenticatedAPIView):
    """`skill_registration_job` 목록·생성 — 정본 §14.

    설정의 직접 작성·업로드와 채팅 `skill_register` 모두 최종적으로
    `SkillRegistrationService.enqueue()`를 사용한다. 이 엔드포인트는 job을
    직접 생성하거나 `SkillJobCenter`가 목록을 복원할 때 사용한다.
    """

    def get(self, request):
        from django.conf import settings
        from backend.db.skill_operations import SkillWorkerHeartbeatRepository

        open_only = request.query_params.get("open") == "true"
        jobs = SkillRegistrationJobRepository.list_for_account(
            request.user.account_id, open_only=open_only
        )
        worker_available = SkillWorkerHeartbeatRepository.active_count(
            ttl_seconds=settings.SKILL_VALIDATION_WORKER_HEARTBEAT_TTL_SECONDS
        ) > 0
        return Response([job_response(job, worker_available=worker_available) for job in jobs])

    def post(self, request):
        context = _team_context(request)
        if isinstance(context, Response):
            return context
        team_id, _role = context
        data = request.data
        try:
            result = SkillRegistrationService.enqueue(
                account_id=request.user.account_id,
                team_id=team_id,
                name=str(data.get("name", "")).strip(),
                description=str(data.get("description", "")).strip(),
                body=data.get("body", ""),
            )
        except SkillError as exc:
            return _skill_error_response(exc)
        return Response(
            job_response(result.job),
            status=status.HTTP_201_CREATED if result.created else status.HTTP_200_OK,
        )


class SkillRegistrationJobDetailAPIView(AuthenticatedAPIView):
    def get(self, request, job_id):
        from django.conf import settings
        from backend.db.skill_operations import SkillWorkerHeartbeatRepository

        job = SkillRegistrationJobRepository.get(job_id, account_id=request.user.account_id)
        available = SkillWorkerHeartbeatRepository.active_count(
            ttl_seconds=settings.SKILL_VALIDATION_WORKER_HEARTBEAT_TTL_SECONDS
        ) > 0
        return Response(job_response(job, include_candidate=True, worker_available=available))

    def delete(self, request, job_id):
        SkillRegistrationJobRepository.delete_terminal(job_id, account_id=request.user.account_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SkillRegistrationJobCancelAPIView(AuthenticatedAPIView):
    def post(self, request, job_id):
        job = SkillRegistrationJobRepository.request_cancel(job_id, account_id=request.user.account_id)
        return Response(job_response(job))


class SkillRegistrationJobRetryAPIView(AuthenticatedAPIView):
    def post(self, request, job_id):
        context = _team_context(request)
        if isinstance(context, Response):
            return context
        team_id, _role = context
        try:
            result = SkillRegistrationService.retry(
                job_id=job_id, account_id=request.user.account_id, team_id=team_id,
                candidate_document=request.data.get("candidate_document"),
            )
        except SkillError as exc:
            return _skill_error_response(exc)
        return Response(job_response(result.job), status=status.HTTP_202_ACCEPTED if result.created else status.HTTP_200_OK)
