"""Chat API — 대화 CRUD 와 Harness 이벤트 중계.

스트림은 NDJSON 이다. 기존 업무 추출(`apps/projects/api_views.py`)과 같은
형식이라 화면이 읽는 방법이 하나다 — 한 줄이 한 사건이다.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
import threading
import uuid
from typing import Any

import psycopg
from django.http import StreamingHttpResponse
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authentication import BearerTokenAuthentication
from apps.accounts.serializers import account_role
from backend.db import AccountRepository
from backend.db.agent_platform import (
    AgentVersionRepository,
    ChatMessageRepository,
    ChatSessionRepository,
    ToolCallRepository,
)
from backend.db.errors import (
    PermissionDenied,
    RecordNotFound,
    ReferenceNotFound,
    RepositoryError,
)
from services.agent_runtime import RuntimeContext
from services.agent_runtime.exceptions import AgentRuntimeError, HTTP_STATUS_BY_EXCEPTION
from services.agent_runtime.sensitive_text import mask_sensitive
from services.agent_runtime.skills.invocation import (
    build_invocation_input,
    parse_invocation,
    resolve_invocable_skill,
)
from services.guardrails import check_user_input, on_check_timeout
from services.harness import EVENT_AWAITING_CONFIRMATION, EVENT_ERROR
from services.harness.naming import suggest_title

from .serializers import (
    ChatConfirmSerializer,
    ChatMessageCreateSerializer,
    ChatSessionCreateSerializer,
    ChatSessionRenameSerializer,
    ChatSessionToolsSerializer,
    message_response,
    session_response,
)

logger = logging.getLogger(__name__)

#: 가드레일 검사를 준비 작업과 겹쳐 돌리는 자리. 외부 호출이라 1~3초가 걸리는데
#: (2026-08-20 실측) 그동안 이력 조회·정의 해석이 놀고 있을 이유가 없다.
#:
#: 작게 잡는다 — 이 풀이 하는 일은 요청당 하나뿐이고, 크게 잡으면 외부 가드레일이
#: 느려질 때 우리 워커보다 많은 연결이 열린다.
_GUARDRAIL_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="guardrail")
#: 검사를 기다리는 **상한**(초). 공급자마다 자기 timeout 이 있지만, 여기서도
#: 한 번 더 끊는다 — 새 공급자를 붙일 때 timeout 을 빠뜨리면 그 팀의 채팅이
#: 통째로 붙들린다. 가드레일이 장애 원인이 되는 것만은 막는다.
#: 공급자 timeout(10초)보다 조금 길게 둬서, 정상적인 지연을 성급히 포기하지 않는다.
GUARDRAIL_WAIT_SECONDS = 12


def _repository_error_response(exc: Exception) -> Response:
    if isinstance(exc, RecordNotFound):
        return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
    if isinstance(exc, PermissionDenied):
        return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
    if isinstance(exc, ReferenceNotFound):
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
    if isinstance(exc, RepositoryError):
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(
        {"detail": "데이터베이스 요청을 처리할 수 없습니다.", "error": exc.__class__.__name__},
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


def _agent_runtime_error_response(exc: AgentRuntimeError) -> Response:
    """`services.agent_runtime.exceptions`를 HTTP 응답으로 바꾼다.

    `apps/agents/api_views.py`의 같은 이름 함수와 동일한 규칙(02 §12) — MRO를
    위에서부터 훑어 가장 구체적인 클래스로 매핑한다. 여기서 쓰는 곳은 실행
    **준비**(런타임 컨텍스트 구성) 단계뿐이다 — 2026-08-14부터 발화가 전부
    새 엔진을 타면서 모든 세션이 이 단계를 거친다. 스트림이 시작된 뒤의 실행 실패는 상태 코드를 더 바꿀 수
    없어서 `_relay()`가 이벤트로 흘려보낸다(아래).
    """

    for cls in type(exc).__mro__:
        if cls in HTTP_STATUS_BY_EXCEPTION:
            return Response({"detail": str(exc)}, status=HTTP_STATUS_BY_EXCEPTION[cls])
    return Response(
        {"detail": "요청을 처리할 수 없습니다.", "error": exc.__class__.__name__},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


class AuthenticatedAPIView(APIView):
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsAuthenticated]


def _start_drive_change_sync(account_id: str) -> None:
    """대화를 시작할 때 Drive 변경분을 따라간다. **응답을 붙잡지 않는다.**

    **여기가 동기화의 시점이다**(2026-08-24). 그전에는 팀장이 「읽을 폴더」를
    저장할 때만 돌아서, 문서를 고쳐도 설정에 다시 들어가지 않으면 반영되지
    않았다. 폴더를 통째로 훑는 방식이라 비싸서 자주 돌릴 수 없었던 것이다.

    Changes API 는 지난 지점 이후의 것만 주고 변화가 없으면 호출 1번이라, 대화를
    열 때마다 물어도 부담이 없다.

    ⚠ **대화 「중간에」 바뀐 것은 다음 대화에서 잡힌다.** 시점을 대화 시작으로
    정한 결과다(PM 결정). 더 촘촘히 하려면 매 발화 앞이나 문서 검색 직전으로
    옮기면 되는데, 그만큼 턴마다 지연이 붙는다.

    실패해도 삼킨다 — 문서 동기화 때문에 대화를 못 열면 안 된다.
    """

    def run() -> None:
        try:
            from services.document_intake import sync_drive_changes

            result = sync_drive_changes(account_id=account_id)
            if result.refreshed or result.removed or result.failed:
                logger.info(
                    "Drive 변경 반영: account=%s 갱신=%d 내림=%d 실패=%d",
                    account_id,
                    len(result.refreshed),
                    len(result.removed),
                    len(result.failed),
                )
        except Exception:  # noqa: BLE001 — 대화 생성은 이미 끝났다.
            logger.exception("Drive 변경 동기화 실패: account=%s", account_id)

    threading.Thread(target=run, daemon=True, name=f"drive-sync-{account_id}").start()


class ChatSessionListCreateAPIView(AuthenticatedAPIView):
    def get(self, request):
        try:
            rows = ChatSessionRepository.list_for_account(request.user.account_id)
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response([session_response(row) for row in rows])

    def post(self, request):
        serializer = ChatSessionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            row = ChatSessionRepository.create(
                account_id=request.user.account_id, **serializer.validated_data
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        _start_drive_change_sync(request.user.account_id)
        return Response(session_response(row), status=status.HTTP_201_CREATED)


class ChatSessionDetailAPIView(AuthenticatedAPIView):
    def get(self, request, session_id):
        try:
            session = ChatSessionRepository.get(
                session_id=session_id, account_id=request.user.account_id
            )
            messages = ChatMessageRepository.list_for_session(
                session_id=session_id, account_id=request.user.account_id
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(
            session_response(session) | {"messages": [message_response(m) for m in messages]}
        )

    def patch(self, request, session_id):
        serializer = ChatSessionRenameSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            row = ChatSessionRepository.rename(
                session_id=session_id,
                account_id=request.user.account_id,
                title=serializer.validated_data["title"],
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(session_response(row))

    def delete(self, request, session_id):
        try:
            ChatSessionRepository.delete(
                session_id=session_id, account_id=request.user.account_id
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ChatSessionToolsAPIView(AuthenticatedAPIView):
    """이 대화 전용 도구·MCP 목록을 켜고 끈다(2026-08-18, Chat "+" 버튼).

    에이전트 원본은 안 건드린다 — 여기서 저장한 값은 다음 메시지부터
    `ChatMessageAPIView`가 `executor.run(tool_refs_override=...)`로 그
    자리에서 정의에 얹는다(§`services/agent_runtime/executor.py`).
    """

    def put(self, request, session_id):
        serializer = ChatSessionToolsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            row = ChatSessionRepository.set_tool_refs_override(
                session_id=session_id,
                account_id=request.user.account_id,
                tool_refs=serializer.validated_data["tool_refs"],
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(session_response(row))


class ChatMessageAPIView(AuthenticatedAPIView):
    """사용자 발화를 받아 에이전트를 돌리고 이벤트를 NDJSON 으로 흘린다."""

    def post(self, request, session_id):
        serializer = ChatMessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        account_id = request.user.account_id
        text = serializer.validated_data["content"]
        applied_skill: dict[str, str] | None = None
        # 2026-08-26 — 마스킹은 `SensitiveInputMaskMiddleware`(그래프 안,
        # `middleware/sensitive_input.py`)가 한다. 예전엔 여기서
        # `mask_sensitive(text)`를 직접 불러 `model_input`을 만들었지만,
        # 이제 `model_input`은 **원문 그대로** 그래프에 넘긴다 — 미들웨어가
        # `before_model`에서 매 모델 호출 직전에 가린다. **저장은 항상
        # 원문 그대로다** — 이건 "모델에게 전달되면 안 된다"는 요구지
        # "사용자 자신도 못 보게 하라"는 요구가 아니다.
        model_input = text

        try:
            session = ChatSessionRepository.get(session_id=session_id, account_id=account_id)
            # 2026-08-22, 명시적 스킬 호출("/스킬이름 ...") — 클로드의 슬래시
            # 커맨드와 같은 방식(사용자 요청). "/"로 시작하는 문장은 이미
            # 어느 스킬을 쓸지 사용자가 확정한 것이라, 모델이 스스로 스킬
            # 설명과 매칭하는 절차(자동 호출, `SkillsMiddleware`)를 기다리지
            # 않고 여기서 직접 본문을 찾아 모델 입력에 박아 넣는다
            # (`services/agent_runtime/skills/invocation.py` 모듈 docstring
            # 참고 — Memory 미들웨어와의 판단 경쟁에 밀려 자동 호출이 안 되는
            # 문제를 실측한 것과 같은 날 나온 요청). 이름이 안 맞으면(스킬이
            # 없거나 "/"로 시작하는 평범한 메모면) 조용히 원래 채팅으로
            # 흘려보낸다 — 오류로 막지 않는다.
            invocation = parse_invocation(text)
            if invocation is not None:
                skill_name, skill_request = invocation
                skill = resolve_invocable_skill(
                    account_id=account_id, team_id=session["team_id"], name=skill_name
                )
                if skill is not None:
                    # `skill_request`도 원문 그대로 — 아래 그래프 진입 전에
                    # `SensitiveInputMaskMiddleware`가 이 문자열이 실린
                    # HumanMessage 전체를 가린다.
                    model_input = build_invocation_input(
                        name=skill_name, body=skill["body"], request=skill_request
                    )
                    applied_skill = {
                        "name": skill_name,
                        "scope": skill.get("scope") or "personal",
                    }
            # 2026-08-20 — 그 팀이 등록한 외부 가드레일이 있으면 거쳐 간다.
            # 없거나 「연결 확인」 전이면 아무 일도 안 한다(`services/guardrails`).
            #
            # **여기서 기다리지 않는다.** 외부 검사는 1~3초가 걸리는데(실측),
            # 그 아래 준비 작업(이력 조회·컨텍스트 구성·에이전트 정의 해석)도
            # DB 를 여러 번 탄다. 순서대로 하면 둘이 더해진다 — 검사를 먼저
            # 띄워 두고 준비가 끝난 자리에서 합류한다.
            guard_check = _GUARDRAIL_POOL.submit(
                check_user_input,
                text,
                team_id=session["team_id"],
                account_id=account_id,
                session_id=str(session_id),
            )
            # **앞선 턴을 읽는다.** 새 발화를 적기 전에 읽어야 방금 것이 안 섞인다.
            # `_history()`는 저장된 원문을 그대로 돌려준다 — 재전송(replay)
            # 경로의 마스킹도 이제 `SensitiveInputMaskMiddleware`가 맡는다
            # (그래프가 `state["messages"]`에 이 값을 얹는 매 순간마다 다시
            # 가리므로, 여기서 한 번만 가리고 넘어가는 것보다 안전하다).
            history = _history(
                ChatMessageRepository.list_for_session(
                    session_id=session_id, account_id=account_id
                )
            )
            # 발화는 전부 새 엔진(services.agent_runtime)을 탄다. 여기서 런타임
            # 컨텍스트를 미리 구성해 두는 이유는 **스트림이 열리기 전에** 실패할
            # 수 있는 부분(계정 프로필 조회)을 먼저 걷어내기 위해서다 — 스트림
            # 안에서 실패하면 상태 코드를 더 바꿀 수 없다.
            #
            # 2026-08-22까지는 여기서 `legacy_bridge`로 draft도 만들었다. 레거시
            # `agent` 스키마를 폐기하면서 모든 세션이 `agent_version_id`를 갖게
            # 돼(`_resolve_session_agent`) 그 갈래가 없어졌다.
            runtime_context = _build_runtime_context(session=session, account_id=account_id)
            if session.get("agent_version_id"):
                # 기본 챗만 예외 — 이미 열린 대화도 "+"로 방금 켠 도구를 바로
                # 쓸 수 있어야 한다(2026-08-18, AgentVersionRepository
                # .resolve_live_version_id 참고). 다른 에이전트는 세션이 만들
                # 때 고정한 버전을 그대로 쓴다(버전 불변성 원칙 유지).
                live_version_id = AgentVersionRepository.resolve_live_version_id(
                    agent_id=session["agent_id"]
                )
                if live_version_id:
                    session = {**session, "agent_version_id": live_version_id}

            # 여기서 검사에 합류한다. 준비가 도는 동안 이미 끝나 있으면 기다림이
            # 없다. **막힌 발화는 저장하지 않는다** — 아래 "질문이 사라진 대화는
            # 복구할 방법이 없다"는 이유는 보낸 발화에 대한 것이고, 여기서는
            # 애초에 보내지지 않았다. 그래서 저장이 이 아래에 있다.
            try:
                guard = guard_check.result(timeout=GUARDRAIL_WAIT_SECONDS)
            except TimeoutError:
                # 못 부른 경우와 **같은 판단**을 한다 — 그 팀이 정한 대로다
                # (`on_check_timeout`). 여기서 통과로 고정하면 「막음」을 켠 팀에
                # 구멍이 생긴다: 가드레일이 죽는 대신 응답을 안 하면 그냥 통과한다.
                logger.warning("가드레일 검사가 %s초 안에 안 끝났습니다", GUARDRAIL_WAIT_SECONDS)
                guard = on_check_timeout(
                    team_id=session["team_id"],
                    account_id=account_id,
                    session_id=str(session_id),
                )
            if guard.blocked:
                return Response({"detail": guard.blocked_reason}, status=status.HTTP_400_BAD_REQUEST)

            # 사용자 발화는 **스트림 전에** 확정한다. 실행이 어떻게 끝나든 사람이
            # 무엇을 물었는지는 남아야 한다 — 답만 없는 대화는 다시 물어보면
            # 되지만, 질문이 사라진 대화는 복구할 방법이 없다. 여기 저장하는
            # `text`는 원문이다 — 화면이 사용자 자신의 발화를 그대로 보여줘야
            # 하고, 마스킹은 모델에게 나가는 값에만 적용한다.
            ChatMessageRepository.append(
                session_id=session_id,
                account_id=account_id,
                role="user",
                content={"type": "text", "text": text},
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        except AgentRuntimeError as exc:
            return _agent_runtime_error_response(exc)

        # 여기서부터 스트림이다. 응답이 시작된 뒤에는 상태 코드를 바꿀 수 없어서
        # 위의 검사를 전부 끝낸 다음에 연다.
        events = _run_deep_agent(
            session=session, context=runtime_context, user_input=model_input, history=history
        )
        if applied_skill is not None:
            events = _with_skill_applied_event(events, skill=applied_skill)

        return StreamingHttpResponse(
            _relay(
                events,
                session_id=session_id,
                account_id=account_id,
                # `suggest_title()`(`services/harness/naming.py`)은 deep agent
                # 그래프를 안 거치고 OpenAI를 직접 부른다 —
                # `SensitiveInputMaskMiddleware`의 보호 범위 밖이라 여기서만
                # 예외적으로 계속 직접 가린다.
                question=mask_sensitive(model_input),
            ),
            content_type="application/x-ndjson",
        )


class SkillFeedbackAPIView(AuthenticatedAPIView):
    """답변 단위 스킬 오사용·미사용 신고. 원문은 회귀 DB에 복사하지 않는다."""

    def post(self, request, message_id):
        from django.conf import settings
        from backend.db.skill_eval import (
            SkillEvalFeedbackNotFound, SkillEvalFeedbackRepository,
        )
        from services.agent_runtime.skills.service import validate_skill_name

        feedback_kind = str(request.data.get("feedback_kind") or "").strip()
        if feedback_kind not in {"WRONG_USAGE", "MISSED_USE"}:
            return Response({"detail": "피드백 종류가 올바르지 않습니다."}, status=400)
        expected_skill = str(request.data.get("expected_skill") or "").strip() or None
        if expected_skill:
            name_error = validate_skill_name(expected_skill, allow_reserved=True)
            if name_error:
                return Response({"detail": name_error}, status=400)
        note = str(request.data.get("note") or "").strip() or None
        if note and len(note) > settings.SKILL_FEEDBACK_NOTE_MAX_LENGTH:
            return Response({"detail": "피드백 설명이 너무 깁니다."}, status=400)
        try:
            row, created = SkillEvalFeedbackRepository.create(
                message_id=message_id, account_id=request.user.account_id,
                feedback_kind=feedback_kind, expected_skill=expected_skill, note=note,
            )
        except SkillEvalFeedbackNotFound as exc:
            return Response({"detail": str(exc)}, status=404)
        return Response(
            {"feedback_id": str(row["feedback_id"]), "review_status": row["review_status"]},
            status=201 if created else 200,
        )


def _with_skill_applied_event(events, *, skill: dict[str, str]):
    """명시 호출로 조회·주입한 스킬을 실제 실행 이벤트 앞에 한 번 알린다.

    명시 호출은 `read_file`을 거치지 않아 기존 도구 타임라인에는 아무 흔적이
    없었다. 이 이벤트도 `_relay()`가 다른 이벤트와 함께 저장하므로 라이브
    스트림뿐 아니라 새로고침으로 복원한 생각 과정에도 그대로 남는다.
    """

    yield {
        "type": "skill_applied",
        "skill_name": skill["name"],
        "scope": skill["scope"],
    }
    yield from events


#: 모델에게 되돌려 줄 앞선 턴의 최대 수(사람 발화 + 답 합계).
#:
#: 전부 보내면 긴 대화에서 토큰이 선형으로 는다. 최근 것만 남기는 이유는 대화가
#: 대개 바로 앞을 가리키기 때문이다("그것 말고", "다시 해줘").
HISTORY_LIMIT = 20


def _history(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """저장된 대화를 **모델이 읽을 수 있는 평범한 메시지**로 바꾼다.

    **도구 호출 원본(reasoning·function_call)은 복원하지 않는다.** 그 아이템들은
    짝이 맞아야 하고(runner.py `_assistant_turn` 주석), 우리가 남긴 것은 재개용
    `resume.messages` 뿐이라 지난 턴 것은 온전하지 않다. 짝이 깨진 채로 보내면
    API 가 400 을 낸다.

    대신 **사람이 본 것과 같은 것**을 준다 — 질문과 답의 텍스트. 그것만으로
    "그것 말고 또 있나?" 가 통한다. 도구 결과를 다시 태우지 않으므로 토큰도 싸다.

    승인 대기로 끝난 턴은 그 사실을 한 줄로 적는다. 비워 두면 모델이 그 턴에
    아무 일도 없었다고 여긴다.

    **여기서 마스킹하지 않는다.** 저장은 원문이고(§2순위 설계 — 화면은
    사용자 자신의 발화를 그대로 보여준다), 이 원문이 그래프에 실릴 때
    가리는 일은 `SensitiveInputMaskMiddleware`(`middleware/sensitive_input.py`)
    가 매 모델 호출 직전에 한다 — 체크포인터가 없어 이 반환값이 매 턴
    통째로 재전송(replay)되는 경우도 그 미들웨어가 매번 다시 보므로 놓치지
    않는다.
    """

    history: list[dict[str, Any]] = []
    for row in rows:
        content = row.get("content") or {}
        if row["role"] == "user":
            text = content.get("text")
            if text:
                history.append({"role": "user", "content": text})
            continue

        if content.get("type") == EVENT_AWAITING_CONFIRMATION:
            history.append(
                {
                    "role": "assistant",
                    "content": f"[{content.get('tool_name') or '작업'} 승인을 요청하고 기다림]",
                }
            )
        elif content.get("text"):
            history.append({"role": "assistant", "content": content["text"]})

    return history[-HISTORY_LIMIT:]


def _build_runtime_context(
    *, session: dict[str, Any], account_id: str, run_id: str | None = None
) -> RuntimeContext:
    """새 엔진(services/agent_runtime)이 요구하는 `RuntimeContext`를 채운다.

    `role`은 가입 경로로 정해진다(`account_role` — apps/accounts/serializers.py,
    apps/connectors/api_views.py가 이미 쓰는 것과 같은 헬퍼). 팀장/팀원에 따른
    도구 사용 가능 여부는 이 값을 `runtime_policy.py`가 읽어서 가른다 — 여기서는
    조회만 한다.

    `run_id`(2026-08-19 추가, §0순위): 기본은 새 발화라 매번 새로 발급
    (`uuid4()`)한다. HITL로 멈춘 실행을 재개할 때만(`_resume_deep_agent()`)
    멈췄던 그 실행의 run_id를 그대로 넘긴다 — 새로 발급하면 그 run_id로
    이미 열어 둔 `agent_run` 행을 못 찾는다(`AgentExecutor.resume()`
    docstring 참고).
    """

    profile = AccountRepository.get_profile(account_id)
    return RuntimeContext(
        account_id=account_id,
        team_id=session["team_id"],
        role=account_role(profile),
        session_id=session["session_id"],
        project_id=session.get("proj_id"),
        run_id=run_id or str(uuid.uuid4()),
    )


def _run_deep_agent(
    *,
    session: dict[str, Any],
    context: RuntimeContext,
    user_input: str,
    history: list[dict[str, Any]],
):
    """대화를 `services.agent_runtime` 엔진으로 돌린다(2026-08-14부터 전부 이 경로).

    이벤트 모양이 레거시와 같아서(`EVENT_RESULT`="result", `EVENT_ERROR`="error")
    아래 `_relay()`/`_persist()`를 그대로 재사용한다 — 차이는 ERROR 이벤트의
    필드 하나뿐이다. 새 엔진은 사람이 읽을 문구를 `message`에 담는데
    (services/agent_runtime/executor.py), `_persist()`는 `text`를 읽으므로
    (레거시 규격) 여기서 하나를 더 채워 맞춘다 — 실행 엔진 쪽 규격을 바꾸지
    않고 이 어댑터 안에서만 흡수한다.

    세션은 언제나 `agent_id`+`agent_version_id` 쌍으로 실행된다 — 2026-08-22에
    레거시 `agent` 스키마를 폐기하면서 draft로 도는 갈래가 없어졌다.

    `build_default_executor`는 **여기서** import한다(모듈 최상단이 아니라).
    이 패키지의 `__init__.py`가 `deepagents` import를 이 이름을 실제로 쓰는
    순간까지 늦추는 이유(PEP 562)가 "Deep Agent를 안 쓰는 요청까지
    `deepagents` 설치 여부에 발목 잡히면 안 된다"였다(2026-08-14 부팅 실패
    사고) — 모듈 최상단에서 이 이름을 import하면 Django가 URL 설정을 읽을 때
    (요청 전, 부팅 시점) 바로 그 사고가 재현된다.
    """

    from services.agent_runtime import build_default_executor
    from services.agent_runtime.tracing import trace_events

    executor = build_default_executor()
    raw_events = executor.run(
        agent_id=session["agent_id"],
        agent_version_id=session["agent_version_id"],
        user_input=user_input,
        context=context,
        conversation_messages=tuple(history),
        # 이 대화가 도구를 커스터마이즈했으면(2026-08-18, Chat "+" 버튼)
        # 에이전트 원본 대신 이 목록으로 돈다 — `None`이면(커스터마이즈 안
        # 함) 로드된 정의를 그대로 쓴다.
        tool_refs_override=session.get("tool_refs_override"),
    )
    # agent_run/tool_call 적재(2026-08-14) — 이벤트는 손대지 않고 그대로
    # 지나간다, 화면에 가는 내용은 감싸기 전과 같다.
    for event in trace_events(raw_events, context=context):
        if event.get("type") == EVENT_ERROR and "text" not in event:
            event = {**event, "text": event.get("message", "")}
        yield event


def _resume_deep_agent(
    *,
    session: dict[str, Any],
    account_id: str,
    content: dict[str, Any],
    decision: str,
    selected: list[int] | None = None,
    per_call_decisions: list[dict[str, Any]] | None = None,
    resolved_decisions: list[dict[str, Any]] | None = None,
):
    """새 엔진에서 HITL interrupt로 멈춘 실행을 재개한다(2026-08-19, §0순위).

    `content`는 `latest_pending_confirmation()`이 돌려준, `_persist()`가
    `EVENT_AWAITING_CONFIRMATION`(새 엔진 모양 — `action_requests` 있음)을
    저장해 둔 그 딕셔너리다. `run_id`는 **멈췄던 그 실행의 run_id**를 그대로
    쓴다 — `_build_runtime_context(run_id=...)`로 넘겨 새로 발급되지 않게
    한다.

    `decision`은 "approve"/"reject" 중 하나이고, 그 턴에 걸린 `action_requests`
    전부에 같은 결정을 적용한다. 다만 승인일 때는 `selected`(카드에서 체크를
    푼 항목)를 `_decisions_for()`가 첫 호출의 인자에 반영한다 — 안 그러면
    화면은 3건을 빼고 승인했는데 10건이 전부 등록된다. 거르는 규칙은 레거시와
    **한 벌만 둔다**(`_apply_selection()`) — 두 벌이 되면 같은 카드가 엔진에
    따라 다른 것을 등록한다.

    `per_call_decisions`(2026-08-21, 병렬실행 Phase 2)가 있으면 **호출 단위의
    부분 승인**을 한다 — 모델이 한 턴에 side_effect 도구를 여러 개 부를 때
    "Jira 3건은 승인하되 이메일 발송만 거절"이 가능해진다. 이 값이 있으면
    `decision`은 무시한다(더 구체적인 쪽이 이긴다, `ChatConfirmSerializer`
    docstring). 배경: `2026-08-21_02_MCP_승인_범위_변경_반영.md` — 팀원도
    쓰기 도구를 자기 승인으로 실행할 수 있게 되면서 "한 번에 몰아 승인"
    위험이 커져 Phase 2로 앞당긴 작업이다.

    `EVENT_AGENT_STARTED`가 없는 스트림이라 `_run_deep_agent()`와 달리
    `trace_events(..., known_run_ids=(run_id,))`로 그 run_id를 미리 열어
    둔 것으로 표시한다(`AgentExecutor.resume()`/`tracing/__init__.py`
    docstring 참고) — 안 하면 재개가 끝나도 그 실행의 `agent_run` 행이
    `PENDING`에서 영원히 안 닫힌다.
    """

    from services.agent_runtime import build_default_executor
    from services.agent_runtime.tracing import trace_events

    run_id = content.get("run_id")
    action_requests = content.get("action_requests") or []
    trace_resume_state = content.get("trace_resume_state") or {}
    context = _build_runtime_context(session=session, account_id=account_id, run_id=run_id)

    if resolved_decisions is None:
        resolved_decisions = (
            _decisions_for(action_requests, selected, per_call=per_call_decisions)
            if per_call_decisions is not None or decision == "approve"
            else [{"type": decision}] * len(action_requests)
        )

    executor = build_default_executor()
    raw_events = executor.resume(
        agent_id=session["agent_id"],
        agent_version_id=session["agent_version_id"],
        context=context,
        decisions=resolved_decisions,
        trace_resume_state=trace_resume_state,
        tool_refs_override=session.get("tool_refs_override"),
    )
    suspended_run_ids = tuple(content.get("suspended_run_ids") or ())
    known_run_ids = suspended_run_ids or ((run_id,) if run_id else ())
    for event in trace_events(raw_events, context=context, known_run_ids=known_run_ids):
        if event.get("type") == EVENT_ERROR and "text" not in event:
            event = {**event, "text": event.get("message", "")}
        yield event


class ChatConfirmAPIView(AuthenticatedAPIView):
    """확인 카드 승인 → 멈춰 있던 실행을 이어서 돌린다.

    승인 대상은 **저장해 둔 그 호출**이다. 모델에게 다시 묻지 않는다 — 다시
    물으면 재실행 때 다른 인자를 고를 수 있고, 그러면 사용자가 승인한 것과
    실제로 실행되는 것이 달라진다(8/11 확정 ③).

    2026-08-19, §0순위 — `pending["content"]["engine"] == "deepagents"`면
    새 엔진 재개 경로(`_resume_deep_agent()`)로 분기한다. 그 앞까지(세션
    조회, pending 조회, 없으면 409)는 두 엔진이 완전히 같다 — "승인 대기
    카드가 있는가"는 엔진과 무관한 질문이라서다.
    """

    def post(self, request, session_id):
        serializer = ChatConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        account_id = request.user.account_id

        try:
            session = ChatSessionRepository.get(session_id=session_id, account_id=account_id)
            pending = ChatMessageRepository.latest_pending_confirmation(
                session_id=session_id, account_id=account_id
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        if pending is None:
            return Response(
                {"detail": "승인을 기다리는 요청이 없습니다."},
                status=status.HTTP_409_CONFLICT,
            )

        content = pending["content"] or {}

        if content.get("engine") == "deepagents":
            per_call_decisions = serializer.validated_data.get("decisions")
            if per_call_decisions is not None:
                # 스트림을 열기 **전에** 검증한다 — 열고 나면 상태 코드를 못
                # 바꿔서, 잘못된 요청도 200 + 스트림 안 에러로만 알릴 수 있다
                # (2026-08-21, 병렬실행 Phase 2).
                try:
                    _per_call_decision_types(
                        content.get("action_requests") or [], per_call_decisions
                    )
                except PerCallDecisionsError as exc:
                    return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

            decision = serializer.validated_data.get("decision") or "approve"
            action_requests = content.get("action_requests") or []
            resolved_decisions = (
                _decisions_for(
                    action_requests,
                    serializer.validated_data.get("selected"),
                    per_call=per_call_decisions,
                )
                if per_call_decisions is not None or decision == "approve"
                else [{"type": decision}] * len(action_requests)
            )
            _close_rejected_tool_calls(
                trace_resume_state=content.get("trace_resume_state") or {},
                resolved_decisions=resolved_decisions,
            )

            return StreamingHttpResponse(
                _relay(
                    _resume_deep_agent(
                        session=session,
                        account_id=account_id,
                        content=content,
                        decision=decision,
                        selected=serializer.validated_data.get("selected"),
                        per_call_decisions=per_call_decisions,
                        resolved_decisions=resolved_decisions,
                    ),
                    session_id=session_id,
                    account_id=account_id,
                    approved_resume=True,
                ),
                content_type="application/x-ndjson",
            )

        # 레거시 harness(`services.harness.run_agent`)로 재개하던 갈래가 여기
        # 있었다. 2026-08-22에 레거시 `agent` 스키마를 폐기하면서 지웠다 —
        # 이제 승인 카드는 전부 `engine="deepagents"`로 저장되므로 위에서
        # 처리되고, 여기 오는 것은 **폐기 전에 저장돼 아직 안 닫힌 카드**뿐이다.
        #
        # 승인한 셈 치고 조용히 넘기지 않는다 — 그 카드가 승인을 기다리던 것은
        # 외부 시스템을 바꾸는 호출이고, 무엇을 승인하는지 다시 보여주지 못하는
        # 채로 실행하는 것이 가장 나쁘다.
        return Response(
            {
                "detail": "이 확인 카드는 더 이상 재개할 수 없습니다. "
                "질문을 다시 보내 주세요."
            },
            status=status.HTTP_409_CONFLICT,
        )


class PerCallDecisionsError(ValueError):
    """호출별 `decisions`가 그 턴의 `action_requests`와 안 맞을 때."""


def _close_rejected_tool_calls(
    *,
    trace_resume_state: dict[str, Any],
    resolved_decisions: list[dict[str, Any]],
) -> None:
    """거절된 호출을 스트림을 열기 전에 REJECTED로 확정한다."""

    rejected_by_run: dict[str, list[str]] = {}
    for pending in trace_resume_state.get("interrupted_tool_calls") or []:
        if not isinstance(pending, dict):
            continue
        action_index = pending.get("action_index")
        if not isinstance(action_index, int) or not 0 <= action_index < len(resolved_decisions):
            continue
        if resolved_decisions[action_index].get("type") != "reject":
            continue
        pending_run_id = pending.get("run_id")
        tool_call_id = pending.get("tool_call_id")
        if pending_run_id and tool_call_id:
            rejected_by_run.setdefault(pending_run_id, []).append(tool_call_id)

    for pending_run_id, tool_call_ids in rejected_by_run.items():
        ToolCallRepository.reject(
            run_id=pending_run_id,
            langchain_tool_call_ids=tool_call_ids,
        )


def _per_call_decision_types(
    action_requests: list[dict[str, Any]], per_call: list[dict[str, Any]]
) -> list[str]:
    """`_per_call_decisions()`의 타입만 뽑은 얇은 래퍼.

    `ChatConfirmAPIView.post()`가 스트림을 열기 전에 형식만 미리 검증할 때
    쓴다(그 자리 주석 참고) — 이 시점엔 `message`까지는 필요 없다.
    """
    return [decision["type"] for decision in _per_call_decisions(action_requests, per_call)]


def _per_call_decisions(
    action_requests: list[dict[str, Any]], per_call: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """호출별 `decisions` 입력을 `action_requests` 순서의 결정 목록으로 편다.

    2026-08-21, 병렬실행 Phase 2. **빠진 항목을 조용히 승인하지 않는다** —
    사용자가 안 본 호출이 실행되면 승인 게이트의 의미가 없어지므로, 모든
    인덱스를 빠짐없이 덮지 않으면 거부한다. 중복 인덱스도 거부한다(같은
    호출에 승인과 거절이 동시에 오면 뭐가 이기는지 애매해진다).

    2026-08-24, skill-creator 되묻기 — `type` 하나만 남기지 않고
    `message`(있으면)도 같이 들고 나온다. `"respond"` 결정은 `message`가
    없으면 `HumanInTheLoopMiddleware`가 그 자리에서 `KeyError`를 내며
    실행 전체를 깨뜨린다(langchain `RespondDecision.message`는 필수 필드) —
    `ChatConfirmSerializer`가 이미 `message` 필수를 검증하지만, 검증을
    통과한 값이 여기서 다시 잘리면 검증이 무의미해진다.

    2026-08-25, Jira 카드 편집 — 화면이 보낸 이슈 전체를 그대로 실행하지
    않는다. 현재 action이 `jira_create_issues`인지와 이슈 개수가 같은지 확인한
    뒤 제목·설명·유형·기한만 원래 호출에 합친다. 프로젝트와 assignee는 원본을
    유지한다.
    """
    by_index: dict[int, dict[str, Any]] = {}
    for item in per_call:
        index = item["action_index"]
        if index >= len(action_requests):
            msg = (
                f"action_index {index}는 이 확인 카드의 범위를 벗어납니다"
                f"(호출 {len(action_requests)}건)."
            )
            raise PerCallDecisionsError(msg)
        if index in by_index:
            msg = f"action_index {index}에 대한 결정이 두 번 왔습니다."
            raise PerCallDecisionsError(msg)
        decision: dict[str, Any] = {"type": item["type"]}
        if item.get("message"):
            decision["message"] = item["message"]
        if item["type"] == "edit":
            request = action_requests[index]
            if request.get("name") != "jira_create_issues":
                raise PerCallDecisionsError("편집은 Jira 이슈 생성 요청에서만 지원합니다.")
            original_args = request.get("args") or {}
            original_issues = original_args.get("issues")
            edited_issues = item.get("edited_issues")
            if not isinstance(original_issues, list) or not isinstance(edited_issues, list):
                raise PerCallDecisionsError("편집할 Jira 이슈 목록을 확인할 수 없습니다.")
            if len(original_issues) != len(edited_issues):
                raise PerCallDecisionsError("편집으로 Jira 이슈의 개수를 바꿀 수 없습니다.")

            merged_issues: list[dict[str, Any]] = []
            for original_issue, edited_issue in zip(original_issues, edited_issues, strict=True):
                if not isinstance(original_issue, dict) or not isinstance(edited_issue, dict):
                    raise PerCallDecisionsError("Jira 이슈 입력 형식이 올바르지 않습니다.")
                merged = dict(original_issue)
                for field in ("title", "description", "issuetype"):
                    merged[field] = edited_issue[field]
                due_date = edited_issue.get("duedate")
                if due_date is None:
                    merged.pop("duedate", None)
                else:
                    merged["duedate"] = due_date.isoformat() if hasattr(due_date, "isoformat") else str(due_date)
                merged_issues.append(merged)

            decision = {
                "type": "edit",
                "edited_action": {
                    "name": request.get("name"),
                    "args": {**original_args, "issues": merged_issues},
                },
            }
        by_index[index] = decision

    missing = [i for i in range(len(action_requests)) if i not in by_index]
    if missing:
        msg = f"결정이 빠진 호출이 있습니다: action_index {missing}. 모든 항목을 보내야 합니다."
        raise PerCallDecisionsError(msg)

    return [by_index[i] for i in range(len(action_requests))]


def _decisions_for(
    action_requests: list[dict[str, Any]],
    selected: list[int] | None,
    per_call: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """승인 카드의 결정 → `HumanInTheLoopMiddleware`가 요구하는 decision 목록.

    **개수가 인터럽트가 요구한 호출 수와 같아야 한다** — 다르면 미들웨어가
    `ValueError`를 던진다(실측: langchain `human_in_the_loop.py`).

    `per_call`(2026-08-21, 병렬실행 Phase 2)이 있으면 호출별로 다른 결정을
    적용한다. 없으면 예전처럼 전부 `approve`로 시작한다.

    체크를 푼 항목이 있으면 첫 호출의 인자를 그만큼 줄여 `edit`로 보낸다.
    줄일 것이 없으면(전체 승인) `approve` 그대로다 — 같은 값을 굳이 `edit`로
    보내면 미들웨어가 인자를 다시 쓰는 경로를 타서, 승인한 것과 실행되는 것이
    같다는 보장이 한 겹 얇아진다. **첫 호출이 거절됐으면 `selected`는 적용하지
    않는다** — 실행 안 될 호출의 인자를 다듬는 건 의미가 없고, `reject`를
    `edit`로 덮어쓰면 거절이 승인으로 뒤집힌다.
    """
    if per_call is not None:
        decisions: list[dict[str, Any]] = _per_call_decisions(action_requests, per_call)
    else:
        decisions = [{"type": "approve"} for _ in action_requests]

    if selected is None or not decisions:
        return decisions
    if decisions[0]["type"] != "approve":
        return decisions

    first = action_requests[0]
    original = first.get("args") or {}
    # 어느 목록을 거를지 정하는 규칙은 레거시와 **하나만 둔다** — 두 벌이 되면
    # 같은 카드가 엔진에 따라 다른 것을 등록한다.
    narrowed = _apply_selection({"arguments": original}, selected).get("arguments") or {}
    if narrowed != original:
        decisions[0] = {
            "type": "edit",
            "edited_action": {"name": first.get("name"), "args": narrowed},
        }
    return decisions


def _apply_selection(tool_call: dict[str, Any], selected: list[int] | None) -> dict[str, Any]:
    """확인 카드에서 체크를 푼 항목을 인자에서 뺀다.

    `selected` 가 없으면 전체 승인이다. 인자에 목록형 값이 하나뿐일 때만 거른다 —
    어느 목록을 거를지 모르는 상태에서 짐작하면, 사용자가 뺀 항목이 그대로
    Jira 에 올라간다.
    """

    if selected is None:
        return tool_call

    arguments = dict(tool_call.get("arguments") or {})
    list_keys = [key for key, value in arguments.items() if isinstance(value, list)]
    if len(list_keys) != 1:
        return tool_call

    key = list_keys[0]
    items = arguments[key]
    arguments[key] = [items[i] for i in selected if 0 <= i < len(items)]
    return {**tool_call, "arguments": arguments}


def _approved_completion_result(
    event: dict[str, Any], *, successful_tool_refs: list[str]
) -> dict[str, Any]:
    """승인 재개 결과를 모델 문장이 아니라 실제 성공한 도구 상태로 확정한다."""

    if event.get("type") != "result" or not successful_tool_refs:
        return event

    unique_refs = list(dict.fromkeys(successful_tool_refs))
    if len(unique_refs) == 1:
        from services.harness.registry import BUILTIN_TOOLS

        tool = BUILTIN_TOOLS.get(unique_refs[0])
        label = getattr(tool, "name", None) or unique_refs[0]
        message = f"{label} 작업을 완료했습니다."
    else:
        message = f"승인한 작업 {len(unique_refs)}건을 완료했습니다."
    return {**event, "text": message}


def _relay(
    events,
    *,
    session_id: str,
    account_id: str,
    question: str = "",
    approved_resume: bool = False,
):
    """이벤트를 NDJSON 한 줄씩 내보내고, 끝나면 결과를 chat_message 로 확정한다.

    적재를 마지막에 하는 이유는 카드 한 벌이 완성돼야 화면이 새로고침 뒤에 같은
    것을 그릴 수 있기 때문이다(8/11 확정 ④). 스트림이 중간에 끊기면 답은 안
    남지만 질문은 이미 남아 있다.

    적재 뒤에 **제목 한 줄을 더 내보낸다**(`session_title`). 첫 답이 나온 뒤라야
    이 대화가 무엇이었는지 정해진다 — 그전에는 「업무 뽑기」로 연 대화가 전부
    같은 이름이었다.
    """

    collected: list[dict[str, Any]] = []
    final: dict[str, Any] | None = None
    successful_tool_refs: list[str] = []
    try:
        for event in events:
            if (
                approved_resume
                and event.get("type") == "tool_completed"
                and event.get("status") == "OK"
                and event.get("tool_ref")
            ):
                successful_tool_refs.append(str(event["tool_ref"]))
            if approved_resume:
                event = _approved_completion_result(
                    event, successful_tool_refs=successful_tool_refs
                )
            collected.append(event)
            # "result"(EVENT_RESULT)뿐 아니라 EVENT_ERROR("error")도 종결로 본다 —
            # 레거시 Harness는 내부적으로 이 이벤트를 만들지 않아 지금까지는
            # 죽은 코드였지만(services/harness/runner.py 확인), 새 엔진
            # (services/agent_runtime/executor.py)은 스트림 중 실패를 예외로
            # 던지지 않고 이 모양으로 끝맺는다 — 안 넣으면 새 엔진의 실패가
            # 대화로 저장되지 않는다.
            if event["type"] in (EVENT_AWAITING_CONFIRMATION, "result", EVENT_ERROR):
                final = event
            yield json.dumps(event, ensure_ascii=False, default=str) + "\n"
    except Exception as exc:  # noqa: BLE001 - 스트림 중에는 500 을 낼 수 없다
        logger.exception("에이전트 실행에 실패했습니다: session=%s", session_id)
        # `AgentRuntimeError`(와 그 하위 클래스 — `ModelUnavailableError`,
        # `InactiveSubagentError` 등)는 우리 코드가 **사람에게 보여줄 문장을
        # 직접 지어 던진 것**이다(2026-08-19 — `ModelUnavailableError`가 여기서
        # 클래스 이름만 뜨고 실제 메시지("이 에이전트에는 아직 모델이 설정되지
        # 않았습니다")는 버려지는 걸 발견하고 고쳤다). `factory.build()`가
        # 스트림 시작 뒤(그래프를 짓는 시점)에 이런 예외를 던지면 여기서 잡히는데,
        # 그 밖의 예외(라이브러리·드라이버)는 여전히 클래스 이름만 남긴다 —
        # 문자열에 쿼리·문서 원문·토큰이 섞여 있을 수 있어서다(같은 판단이
        # `services/agent_runtime/factory.py`의 `_run()`에도 있다).
        detail = (
            str(exc)
            if isinstance(exc, AgentRuntimeError)
            else f"에이전트 실행에 실패했습니다: {exc.__class__.__name__}"
        )
        failure = {
            "type": EVENT_ERROR,
            "detail": detail,
        }
        collected.append(failure)
        final = failure
        yield json.dumps(failure, ensure_ascii=False) + "\n"

    _persist(session_id=session_id, account_id=account_id, events=collected, final=final)

    title = _name_session(
        session_id=session_id, account_id=account_id, question=question, final=final
    )
    if title:
        yield json.dumps({"type": "session_title", "title": title}, ensure_ascii=False) + "\n"


def _name_session(
    *,
    session_id: str,
    account_id: str,
    question: str,
    final: dict[str, Any] | None,
) -> str | None:
    """첫 답 뒤 이 대화의 이름. 실패하면 `None` — 원래 제목이 그대로 남는다."""

    if final is None or final["type"] == EVENT_ERROR:
        return None
    title = suggest_title(question=question, answer=final.get("text") or "")
    if not title:
        return None
    try:
        renamed = ChatSessionRepository.rename_if_first_answer(
            session_id=session_id, account_id=account_id, title=title
        )
    except (RepositoryError, psycopg.Error):
        logger.exception("대화 제목 저장에 실패했습니다: session=%s", session_id)
        return None
    return title if renamed else None


def _persist(
    *,
    session_id: str,
    account_id: str,
    events: list[dict[str, Any]],
    final: dict[str, Any] | None,
) -> None:
    if final is None:
        return

    content: dict[str, Any] = {
        "type": final["type"],
        # 화면은 이 목록으로 카드를 다시 그린다. 요약본만 저장하면 새로고침
        # 뒤에 진행·근거 카드가 사라진다.
        "events": events,
    }
    if final["type"] == EVENT_AWAITING_CONFIRMATION:
        if "action_requests" in final:
            # 새 엔진(HITL interrupt, 2026-08-19 §0순위) — 레거시와 모양이
            # 다르다: 재개 스택(resume/tool_ref/via_agent) 대신 그 턴에
            # interrupt된 action_requests 전부와, 재개에 그대로 써야 하는
            # run_id를 저장한다. `ChatConfirmAPIView`가 `content.get("engine")`
            # 로 이 분기를 골라 `_resume_deep_agent()`로 보낸다.
            content["engine"] = "deepagents"
            content["run_id"] = final.get("run_id")
            content["interrupt_id"] = final.get("interrupt_id")
            content["action_requests"] = final.get("action_requests")
            content["trace_resume_state"] = final.get("trace_resume_state") or {}
            content["suspended_run_ids"] = final.get("suspended_run_ids") or []
            names = [
                a.get("name") for a in (final.get("action_requests") or []) if a.get("name")
            ]
            content["tool_name"] = ", ".join(names) if names else None
        else:
            # 레거시 확인 카드. `message_response` 가 화면으로는 내보내지 않는다.
            content["resume"] = final.get("resume")
            content["tool_ref"] = final.get("tool_ref")
            content["tool_name"] = final.get("tool_name")
            content["arguments"] = final.get("arguments")
            # 위임을 거쳐 올라온 승인이면 누가 요구했는지. 없으면 최상위가
            # 직접 부른 것이다 — 그 차이를 사람이 알아야 무엇을 승인하는지
            # 안다.
            content["via_agent"] = final.get("via_agent")
    else:
        content["text"] = final.get("text", "")
        content["complete"] = final.get("complete", False)
        # 2026-08-19, §12순위(채팅 응답 시간 계측) — `trace_events()`가 실어
        # 보낸 값을 그대로 옮긴다. 재개(resume) 스트림 등 값이 없는 경우도
        # 있어(services/agent_runtime/tracing/__init__.py 참고) 있을 때만
        # 넣는다 — 없는 실행에까지 `0`이나 `None`을 박아 "쟀는데 0초"로
        # 잘못 보이게 하지 않는다.
        if "duration_ms" in final:
            content["duration_ms"] = final["duration_ms"]

    try:
        ChatMessageRepository.append(
            session_id=session_id, account_id=account_id, role="agent", content=content
        )
    except (RepositoryError, psycopg.Error):
        # 스트림은 이미 끝났다. 여기서 터뜨려 봐야 사용자에게 전할 길이 없고,
        # 화면은 방금 받은 이벤트로 이미 그려져 있다. 로그로만 남긴다.
        logger.exception("대화 적재에 실패했습니다: session=%s", session_id)
