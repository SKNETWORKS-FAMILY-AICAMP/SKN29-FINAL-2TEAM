"""Chat API — 대화 CRUD 와 Harness 이벤트 중계.

스트림은 NDJSON 이다. 기존 업무 추출(`apps/projects/api_views.py`)과 같은
형식이라 화면이 읽는 방법이 하나다 — 한 줄이 한 사건이다.
"""

import json
import logging
from typing import Any

import psycopg
from django.http import StreamingHttpResponse
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authentication import BearerTokenAuthentication
from backend.db.agent_platform import ChatMessageRepository, ChatSessionRepository
from backend.db.errors import (
    PermissionDenied,
    RecordNotFound,
    ReferenceNotFound,
    RepositoryError,
)
from services.harness import EVENT_AWAITING_CONFIRMATION, EVENT_ERROR, run_agent

from .serializers import (
    ChatConfirmSerializer,
    ChatMessageCreateSerializer,
    ChatSessionCreateSerializer,
    message_response,
    session_response,
)

logger = logging.getLogger(__name__)


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


class AuthenticatedAPIView(APIView):
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsAuthenticated]


class ChatSessionListCreateAPIView(AuthenticatedAPIView):
    def get(self, request):
        try:
            rows = ChatSessionRepository.list_for_team(request.user.account_id)
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

    def delete(self, request, session_id):
        try:
            ChatSessionRepository.delete(
                session_id=session_id, account_id=request.user.account_id
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ChatMessageAPIView(AuthenticatedAPIView):
    """사용자 발화를 받아 에이전트를 돌리고 이벤트를 NDJSON 으로 흘린다."""

    def post(self, request, session_id):
        serializer = ChatMessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        account_id = request.user.account_id
        text = serializer.validated_data["content"]

        try:
            session = ChatSessionRepository.get(session_id=session_id, account_id=account_id)
            # 사용자 발화는 **스트림 전에** 확정한다. 실행이 어떻게 끝나든 사람이
            # 무엇을 물었는지는 남아야 한다 — 답만 없는 대화는 다시 물어보면
            # 되지만, 질문이 사라진 대화는 복구할 방법이 없다.
            ChatMessageRepository.append(
                session_id=session_id,
                account_id=account_id,
                role="user",
                content={"type": "text", "text": text},
            )
        except (RepositoryError, psycopg.Error) as exc:
            return _repository_error_response(exc)

        # 여기서부터 스트림이다. 응답이 시작된 뒤에는 상태 코드를 바꿀 수 없어서
        # 위의 검사를 전부 끝낸 다음에 연다.
        return StreamingHttpResponse(
            _relay(
                run_agent(
                    session["agent_id"],
                    text,
                    {
                        "session_id": session_id,
                        "account_id": account_id,
                        # 업무 추출처럼 프로젝트가 전제인 도구가 쓴다. 대화를 열
                        # 때 고른 값이고, 없으면(전체(팀) 문맥) 그 도구가 거절한다.
                        "proj_id": session.get("proj_id"),
                    },
                ),
                session_id=session_id,
                account_id=account_id,
            ),
            content_type="application/x-ndjson",
        )


class ChatConfirmAPIView(AuthenticatedAPIView):
    """확인 카드 승인 → 멈춰 있던 실행을 이어서 돌린다.

    승인 대상은 **저장해 둔 그 호출**이다. 모델에게 다시 묻지 않는다 — 다시
    물으면 재실행 때 다른 인자를 고를 수 있고, 그러면 사용자가 승인한 것과
    실제로 실행되는 것이 달라진다(8/11 확정 ③).
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
        resume = content.get("resume") or {}
        tool_call = resume.get("tool_call")
        if tool_call is None:
            # 이 카드로는 재개할 수 없다. 승인한 셈 치고 아무것도 안 하는 것보다
            # 못 한다고 말하는 편이 낫다.
            return Response(
                {"detail": "이 확인 카드는 재개 정보를 갖고 있지 않습니다. 다시 요청해 주세요."},
                status=status.HTTP_409_CONFLICT,
            )

        selected = serializer.validated_data.get("selected")
        tool_call = _apply_selection(tool_call, selected)

        return StreamingHttpResponse(
            _relay(
                run_agent(
                    session["agent_id"],
                    "",
                    {
                        "session_id": session_id,
                        "account_id": account_id,
                        "proj_id": session.get("proj_id"),
                        "messages": resume.get("messages") or [],
                        "resume_tool_call": tool_call,
                        "approved_tool_calls": [tool_call["tool_ref"]],
                    },
                ),
                session_id=session_id,
                account_id=account_id,
            ),
            content_type="application/x-ndjson",
        )


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


def _relay(events, *, session_id: str, account_id: str):
    """이벤트를 NDJSON 한 줄씩 내보내고, 끝나면 결과를 chat_message 로 확정한다.

    적재를 마지막에 하는 이유는 카드 한 벌이 완성돼야 화면이 새로고침 뒤에 같은
    것을 그릴 수 있기 때문이다(8/11 확정 ④). 스트림이 중간에 끊기면 답은 안
    남지만 질문은 이미 남아 있다.
    """

    collected: list[dict[str, Any]] = []
    final: dict[str, Any] | None = None
    try:
        for event in events:
            collected.append(event)
            if event["type"] in (EVENT_AWAITING_CONFIRMATION, "result"):
                final = event
            yield json.dumps(event, ensure_ascii=False, default=str) + "\n"
    except Exception as exc:  # noqa: BLE001 - 스트림 중에는 500 을 낼 수 없다
        logger.exception("에이전트 실행에 실패했습니다: session=%s", session_id)
        failure = {
            "type": EVENT_ERROR,
            "detail": f"에이전트 실행에 실패했습니다: {exc.__class__.__name__}",
        }
        collected.append(failure)
        final = failure
        yield json.dumps(failure, ensure_ascii=False) + "\n"

    _persist(session_id=session_id, account_id=account_id, events=collected, final=final)


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
        # 재개 정보. `message_response` 가 화면으로는 내보내지 않는다.
        content["resume"] = final.get("resume")
        content["tool_ref"] = final.get("tool_ref")
        content["tool_name"] = final.get("tool_name")
        content["arguments"] = final.get("arguments")
    else:
        content["text"] = final.get("text", "")
        content["complete"] = final.get("complete", False)

    try:
        ChatMessageRepository.append(
            session_id=session_id, account_id=account_id, role="agent", content=content
        )
    except (RepositoryError, psycopg.Error):
        # 스트림은 이미 끝났다. 여기서 터뜨려 봐야 사용자에게 전할 길이 없고,
        # 화면은 방금 받은 이벤트로 이미 그려져 있다. 로그로만 남긴다.
        logger.exception("대화 적재에 실패했습니다: session=%s", session_id)
