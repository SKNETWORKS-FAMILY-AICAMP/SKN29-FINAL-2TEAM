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
            # **앞선 턴을 읽는다.** 새 발화를 적기 전에 읽어야 방금 것이 안 섞인다.
            history = _history(
                ChatMessageRepository.list_for_session(
                    session_id=session_id, account_id=account_id
                )
            )
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
                        # 때 고른 값이고, 없으면 그 도구가 거절한다.
                        "proj_id": session.get("proj_id"),
                        # 앞선 턴 + 이번 발화. 이걸 안 주면 **매 턴이 콜드
                        # 스타트**라 "그것 말고 또 있나?" 같은 말이 통하지 않는다.
                        "messages": [*history, {"role": "user", "content": text}],
                    },
                ),
                session_id=session_id,
                account_id=account_id,
            ),
            content_type="application/x-ndjson",
        )


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
        # 재개 정보는 **스택**이다. 위임(agent:)이 끼어 있으면 바깥 호출은
        # "그 에이전트를 다시 부른다"이고, 사람이 승인한 실제 호출은 맨 안쪽에
        # 있다 — 선택 적용도 승인도 거기서 해야 한다.
        plan, approved_ref = _apply_to_innermost(resume, selected)

        return StreamingHttpResponse(
            _relay(
                run_agent(
                    session["agent_id"],
                    "",
                    {
                        "session_id": session_id,
                        "account_id": account_id,
                        "proj_id": session.get("proj_id"),
                        "messages": plan.get("messages") or [],
                        "resume_tool_call": plan.get("tool_call"),
                        "resume_inner": plan.get("inner"),
                        "approved_tool_calls": [approved_ref],
                    },
                ),
                session_id=session_id,
                account_id=account_id,
            ),
            content_type="application/x-ndjson",
        )


def _apply_to_innermost(
    node: dict[str, Any], selected: list[int] | None
) -> tuple[dict[str, Any], str]:
    """재개 스택의 가장 안쪽 호출에 선택을 적용하고, 승인할 `tool_ref` 를 돌려준다.

    바깥 층의 호출은 손대지 않는다 — 그것은 「이 에이전트를 다시 부른다」이고,
    사용자가 확인 카드에서 체크를 푼 것은 맨 안쪽의 인자다. 바깥에 적용하면
    위임 자체가 잘려 나간다.

    승인도 안쪽 `tool_ref` 하나만 준다. 바깥까지 승인하면 「위임은 늘 승인된
    것」이 되어 게이트가 한 층 헐거워진다.
    """

    inner = node.get("inner")
    if inner:
        applied, approved_ref = _apply_to_innermost(inner, selected)
        return {**node, "inner": applied}, approved_ref

    tool_call = _apply_selection(node["tool_call"], selected)
    return {**node, "tool_call": tool_call}, tool_call["tool_ref"]


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
        # 위임을 거쳐 올라온 승인이면 누가 요구했는지. 없으면 최상위가 직접
        # 부른 것이다 — 그 차이를 사람이 알아야 무엇을 승인하는지 안다.
        content["via_agent"] = final.get("via_agent")
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
