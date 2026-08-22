"""Chat API 단위 테스트. DB 는 띄우지 않고 Repository 를 mock 한다.

가장 중요하게 보는 것은 **확인 게이트**다. 승인 전에 아무것도 실행되지 않고,
승인 뒤에는 사용자가 승인한 바로 그 호출이 실행되는가.
"""

import json
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.accounts.tokens import issue_token
from apps.chat.api_views import PerCallDecisionsError, _apply_selection, _decisions_for
from apps.chat.serializers import message_response
from backend.db.errors import PermissionDenied

SESSION = {
    "session_id": "11111111-1111-1111-1111-111111111111",
    "team_id": "TM001",
    "account_id": "UA001",
    "agent_id": "AG001",
    # 2026-08-22: 레거시 `agent` 스키마를 폐기하면서 모든 대화가 버전을 갖는다
    # (`_resolve_session_agent`가 신규 `agents`만 본다).
    "agent_version_id": "AV001",
    "proj_id": None,
    "title": "8/11 업무 정리",
    "created_at": "2026-08-11T09:00:00Z",
    "updated_at": "2026-08-11T09:00:00Z",
}

#: 예전에 「신규 스키마 대화」를 따로 가리키던 이름. 지금은 모든 대화가 그렇다 —
#: 읽는 쪽 문맥을 살리려고 별칭만 남긴다.
DEEP_SESSION = SESSION

#: `AccountRepository.get_profile()`이 돌려주는 모양 중 `account_role()`이 보는
#: 부분만 — 초대로 들어오지 않았으므로 팀장.
LEADER_PROFILE = {"account_id": "UA001", "invited": False}


def auth_header(account_id="UA001"):
    return {"authorization": f"Bearer {issue_token(account_id)}"}


def ndjson(response) -> list[dict]:
    body = b"".join(response.streaming_content).decode("utf-8")
    return [json.loads(line) for line in body.splitlines() if line]


class SelectionTests(SimpleTestCase):
    """확인 카드에서 체크를 푼 항목이 실제로 빠지는가."""

    def test_고른_항목만_남긴다(self):
        call = {"tool_ref": "mcp:MT001", "arguments": {"issues": ["A", "B", "C"]}}

        result = _apply_selection(call, [0, 2])

        self.assertEqual(result["arguments"]["issues"], ["A", "C"])

    def test_선택을_안_보내면_전체_승인이다(self):
        call = {"tool_ref": "mcp:MT001", "arguments": {"issues": ["A", "B"]}}

        self.assertEqual(_apply_selection(call, None)["arguments"]["issues"], ["A", "B"])

    def test_목록이_둘이면_짐작하지_않는다(self):
        """어느 쪽을 거를지 모르는데 찍으면, 사용자가 뺀 항목이 그대로 올라간다."""

        call = {"tool_ref": "mcp:MT001", "arguments": {"issues": ["A", "B"], "labels": ["x"]}}

        self.assertEqual(_apply_selection(call, [0]), call)


class MessageResponseTests(SimpleTestCase):
    def test_재개_정보는_화면으로_나가지_않는다(self):
        row = {
            "message_id": "M1",
            "role": "agent",
            "content": {"type": "awaiting_confirmation", "resume": {"messages": ["비밀"]}},
            "created_at": None,
        }

        self.assertNotIn("resume", message_response(row)["content"])


@patch("apps.chat.api_views.ChatMessageRepository")
@patch("apps.chat.api_views.ChatSessionRepository")
class ChatSessionApiTests(SimpleTestCase):
    def test_대화를_연다(self, sessions, _messages):
        sessions.create.return_value = SESSION

        response = self.client.post(
            "/api/chat/sessions/",
            {"agent_id": "AG001", "title": "8/11 업무 정리"},
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["agent_id"], "AG001")
        self.assertEqual(sessions.create.call_args.kwargs["account_id"], "UA001")

    def test_에이전트를_안_고르면_거절한다(self, _sessions, _messages):
        """서버가 알아서 고르지 않는다(확정 ① — 수동 선택기)."""

        response = self.client.post(
            "/api/chat/sessions/", {}, content_type="application/json", headers=auth_header()
        )

        self.assertEqual(response.status_code, 400)

    def test_남의_팀_대화는_403(self, sessions, _messages):
        sessions.get.side_effect = PermissionDenied("이 대화에 접근할 수 없습니다.")

        response = self.client.get(
            f"/api/chat/sessions/{SESSION['session_id']}/", headers=auth_header()
        )

        self.assertEqual(response.status_code, 403)

    def test_로그인_없이는_401(self, _sessions, _messages):
        self.assertEqual(self.client.get("/api/chat/sessions/").status_code, 401)


def _mock_new_engine(build_executor, events):
    mock_executor = MagicMock()
    mock_executor.run.return_value = iter(events)
    build_executor.return_value = mock_executor
    return mock_executor


#: 제목 짓기는 **모델을 부른다.** 막지 않으면 스트림을 타는 테스트마다 실제
#: OpenAI 호출이 나가서 느려지고 네트워크에 흔들린다(2026-08-12 실측: 3.4초 →
#: 12초). 제목이 붙는지는 `ChatSessionTitleTests` 에서 따로 본다.
@patch("services.agent_runtime.build_default_executor")
@patch("apps.chat.api_views.AgentVersionRepository.resolve_live_version_id", new=lambda **_: None)
@patch("apps.chat.api_views.suggest_title", return_value=None)
@patch("apps.chat.api_views.AccountRepository")
@patch("apps.chat.api_views.ChatMessageRepository")
@patch("apps.chat.api_views.ChatSessionRepository")
class ChatStreamTests(SimpleTestCase):
    """SESSION은 레거시 `agent` 스키마다(agent_version_id 없음) — 2026-08-14
    전환으로 이 경로도 새 엔진(services.agent_runtime)을 탄다.
    """

    def test_이벤트를_NDJSON_으로_중계한다(self, sessions, messages, accounts, _title, build_executor):
        sessions.get.return_value = SESSION
        accounts.get_profile.return_value = LEADER_PROFILE
        _mock_new_engine(
            build_executor,
            [
                {"type": "stage", "step": 1, "total": 10, "label": "생각하는 중"},
                {"type": "result", "text": "8월 20일입니다.", "complete": True},
            ],
        )

        response = self.client.post(
            f"/api/chat/sessions/{SESSION['session_id']}/messages/",
            {"content": "일정 알려줘"},
            content_type="application/json",
            headers=auth_header(),
        )
        events = ndjson(response)

        self.assertEqual(response["Content-Type"], "application/x-ndjson")
        self.assertEqual([e["type"] for e in events], ["stage", "result"])

    def test_사용자_발화는_스트림_전에_확정한다(self, sessions, messages, accounts, _title, build_executor):
        """답이 없는 대화는 다시 물으면 되지만, 질문이 사라지면 복구할 수 없다."""

        sessions.get.return_value = SESSION
        accounts.get_profile.return_value = LEADER_PROFILE
        _mock_new_engine(build_executor, [])

        self.client.post(
            f"/api/chat/sessions/{SESSION['session_id']}/messages/",
            {"content": "일정 알려줘"},
            content_type="application/json",
            headers=auth_header(),
        )

        first = messages.append.call_args_list[0].kwargs
        self.assertEqual(first["role"], "user")
        self.assertEqual(first["content"], {"type": "text", "text": "일정 알려줘"})

    def test_승인_대기가_남아_있어도_새_발화를_받는다(self, sessions, messages, accounts, _title, build_executor):
        """승인 대기 중에도 말할 수 있다(6차 단계 1-5 · 확정 ③).

        화면이 승인 대기 중 입력창을 여는 근거다. 발화 경로는 pending 을 아예
        보지 않고 새 실행을 시작한다 — 승인을 강요하지 않고, 대신 지나간 확인
        카드가 「승인하지 않고 넘어감」으로 남는다.
        """

        sessions.get.return_value = SESSION
        accounts.get_profile.return_value = LEADER_PROFILE
        mock_executor = _mock_new_engine(
            build_executor, [{"type": "result", "text": "다시 뽑았습니다.", "complete": True}]
        )

        response = self.client.post(
            f"/api/chat/sessions/{SESSION['session_id']}/messages/",
            {"content": "3번은 빼고 다시 뽑아줘"},
            content_type="application/json",
            headers=auth_header(),
        )
        events = ndjson(response)

        self.assertEqual(response.status_code, 200)
        self.assertEqual([e["type"] for e in events], ["result"])
        # 승인 경로가 아니므로 저장된 확인 카드를 들춰 보지 않는다.
        messages.latest_pending_confirmation.assert_not_called()
        # 재개가 아니라 **새 실행**이다 — 새 엔진 executor.run()에는 애초에
        # resume 개념 자체가 없다(HITL 미착수, 2026-08-14).
        self.assertNotIn("resume_tool_call", mock_executor.run.call_args.kwargs)

    def test_스트림이_끝나면_카드를_통째로_적재한다(self, sessions, messages, accounts, _title, build_executor):
        sessions.get.return_value = SESSION
        accounts.get_profile.return_value = LEADER_PROFILE
        _mock_new_engine(
            build_executor,
            [
                {"type": "stage", "step": 1, "total": 10, "label": "생각하는 중"},
                {"type": "result", "text": "끝", "complete": True},
            ],
        )

        response = self.client.post(
            f"/api/chat/sessions/{SESSION['session_id']}/messages/",
            {"content": "질문"},
            content_type="application/json",
            headers=auth_header(),
        )
        ndjson(response)

        agent_write = messages.append.call_args_list[-1].kwargs
        self.assertEqual(agent_write["role"], "agent")
        self.assertEqual(agent_write["content"]["text"], "끝")
        # 새로고침 뒤에 같은 카드를 그리려면 이벤트가 통째로 남아야 한다.
        self.assertEqual(len(agent_write["content"]["events"]), 2)

    def test_실행이_터지면_마지막_줄로_알린다(self, sessions, messages, accounts, _title, build_executor):
        sessions.get.return_value = SESSION
        accounts.get_profile.return_value = LEADER_PROFILE

        def boom():
            yield {"type": "stage", "step": 1, "total": 10, "label": "생각하는 중"}
            raise TimeoutError("느립니다")

        mock_executor = MagicMock()
        mock_executor.run.return_value = boom()
        build_executor.return_value = mock_executor

        response = self.client.post(
            f"/api/chat/sessions/{SESSION['session_id']}/messages/",
            {"content": "질문"},
            content_type="application/json",
            headers=auth_header(),
        )
        events = ndjson(response)

        # 응답이 이미 시작됐으므로 500 을 낼 수 없다.
        self.assertEqual(response.status_code, 200)
        self.assertEqual(events[-1]["type"], "error")
        self.assertIn("TimeoutError", events[-1]["detail"])

    def test_승인_대기_이벤트가_오면_재개_정보와_함께_적재된다(self, sessions, messages, accounts, _title, build_executor):
        """새 엔진은 아직 이 이벤트를 만들지 않는다(HITL 미착수, 설계 계획
        4번) — 하지만 `_relay()`/`_persist()`의 적재 규칙 자체는 이벤트
        출처(레거시 run_agent든 새 엔진이든)를 가리지 않는다. 나중에 새
        엔진이 이 이벤트를 내기 시작해도 적재가 깨지지 않는지 여기서 미리
        고정해 둔다. (원래 ConfirmGateTests에 run_agent mock으로 있었으나
        2026-08-14 전환으로 /messages/ 가 run_agent를 더 이상 안 불러서
        이쪽으로 옮김.)
        """

        sessions.get.return_value = SESSION
        accounts.get_profile.return_value = LEADER_PROFILE
        resume = {"messages": [{"role": "user", "content": "올려줘"}], "tool_call": {"id": "c1"}}
        _mock_new_engine(
            build_executor,
            [
                {
                    "type": "awaiting_confirmation",
                    "run_id": "RUN-1",
                    "tool_ref": "mcp:MT001",
                    "tool_name": "Jira 이슈 생성",
                    "arguments": {"issues": ["A"]},
                    "resume": resume,
                }
            ],
        )

        response = self.client.post(
            f"/api/chat/sessions/{SESSION['session_id']}/messages/",
            {"content": "Jira에 올려줘"},
            content_type="application/json",
            headers=auth_header(),
        )
        ndjson(response)

        stored = messages.append.call_args_list[-1].kwargs["content"]
        self.assertEqual(stored["type"], "awaiting_confirmation")
        self.assertEqual(stored["resume"], resume)

@patch("services.agent_runtime.build_default_executor")
@patch("apps.chat.api_views.AgentVersionRepository.resolve_live_version_id", new=lambda **_: None)
@patch("apps.chat.api_views.suggest_title", return_value=None)
@patch("apps.chat.api_views.AccountRepository")
@patch("apps.chat.api_views.ChatMessageRepository")
@patch("apps.chat.api_views.ChatSessionRepository")
class DeepAgentSessionStreamTests(SimpleTestCase):
    """`agent_version_id`가 있는 세션(새-스키마 에이전트로 연 대화)은 레거시
    `run_agent()` 대신 `services.agent_runtime` 엔진을 돈다.

    `build_default_executor`는 여기서 patch한다 — `apps/chat/api_views.py`가
    이 이름을 함수 안에서 지연 import하기 때문에(2026-08-14 부팅 실패 사고를
    피하려는 패턴, `_run_deep_agent` docstring 참고)
    `apps.chat.api_views.build_default_executor`라는 모듈 속성이 없다.
    """

    def test_new_engine_events_relay_through_ndjson(
        self, sessions, messages, accounts, _title, build_executor
    ):
        sessions.get.return_value = DEEP_SESSION
        messages.list_for_session.return_value = []
        accounts.get_profile.return_value = LEADER_PROFILE
        mock_executor = MagicMock()
        mock_executor.run.return_value = iter(
            [
                {"type": "agent_started", "run_id": "R1", "complete": False},
                {"type": "result", "text": "새 엔진 답", "complete": True},
            ]
        )
        build_executor.return_value = mock_executor

        response = self.client.post(
            f"/api/chat/sessions/{DEEP_SESSION['session_id']}/messages/",
            {"content": "질문"},
            content_type="application/json",
            headers=auth_header(),
        )
        events = ndjson(response)

        self.assertEqual(response["Content-Type"], "application/x-ndjson")
        self.assertEqual([e["type"] for e in events], ["agent_started", "result"])

    def test_레거시_harness_는_더_이상_import_되지_않는다(
        self, sessions, messages, accounts, _title, build_executor
    ):
        """예전에는 `apps.chat.api_views.run_agent`를 patch해서 "안 불린다"를
        봤다. 2026-08-22에 레거시 `agent` 스키마를 폐기하면서 그 이름 자체가
        모듈에서 사라졌으므로, 이제는 **없다는 것**을 직접 본다 — 있으면
        patch가 성공하고 그건 레거시 경로가 되살아났다는 뜻이다."""

        import apps.chat.api_views as chat_views

        self.assertFalse(hasattr(chat_views, "run_agent"))

        sessions.get.return_value = DEEP_SESSION
        messages.list_for_session.return_value = []
        accounts.get_profile.return_value = LEADER_PROFILE
        mock_executor = MagicMock()
        mock_executor.run.return_value = iter([{"type": "result", "text": "ok", "complete": True}])
        build_executor.return_value = mock_executor

        response = self.client.post(
            f"/api/chat/sessions/{DEEP_SESSION['session_id']}/messages/",
            {"content": "질문"},
            content_type="application/json",
            headers=auth_header(),
        )
        # StreamingHttpResponse는 지연 스트림이라 실제로 읽어야 돈다.
        ndjson(response)

        mock_executor.run.assert_called_once()

    def test_agent_id_version_id_and_role_reach_the_executor(
        self, sessions, messages, accounts, _title, build_executor
    ):
        sessions.get.return_value = DEEP_SESSION
        messages.list_for_session.return_value = []
        # 초대로 들어온 계정 — 팀원.
        accounts.get_profile.return_value = {"account_id": "UA001", "invited": True}
        mock_executor = MagicMock()
        mock_executor.run.return_value = iter([{"type": "result", "text": "ok", "complete": True}])
        build_executor.return_value = mock_executor

        response = self.client.post(
            f"/api/chat/sessions/{DEEP_SESSION['session_id']}/messages/",
            {"content": "질문"},
            content_type="application/json",
            headers=auth_header(),
        )
        # StreamingHttpResponse는 지연 스트림이다 — 실제로 읽어야
        # `_run_deep_agent`(제너레이터)가 돌기 시작하고 executor.run()이 불린다.
        ndjson(response)

        call_kwargs = mock_executor.run.call_args.kwargs
        self.assertEqual(call_kwargs["agent_id"], "AG001")
        self.assertEqual(call_kwargs["agent_version_id"], "AV001")
        self.assertEqual(call_kwargs["context"].role, "member")
        self.assertEqual(call_kwargs["context"].team_id, "TM001")
        # 세션은 언제나 agent_id/agent_version_id 쌍으로 실행된다 — 2026-08-22에
        # 레거시 `agent` 스키마를 폐기하면서 draft 갈래 자체가 없어졌다.
        self.assertNotIn("draft", call_kwargs)

    def test_conversation_history_is_threaded_through(
        self, sessions, messages, accounts, _title, build_executor
    ):
        sessions.get.return_value = DEEP_SESSION
        messages.list_for_session.return_value = [
            {"role": "user", "content": {"text": "이전 질문"}},
            {"role": "agent", "content": {"text": "이전 답"}},
        ]
        accounts.get_profile.return_value = LEADER_PROFILE
        mock_executor = MagicMock()
        mock_executor.run.return_value = iter([{"type": "result", "text": "ok", "complete": True}])
        build_executor.return_value = mock_executor

        response = self.client.post(
            f"/api/chat/sessions/{DEEP_SESSION['session_id']}/messages/",
            {"content": "새 질문"},
            content_type="application/json",
            headers=auth_header(),
        )
        ndjson(response)

        call_kwargs = mock_executor.run.call_args.kwargs
        self.assertEqual(
            call_kwargs["conversation_messages"],
            ({"role": "user", "content": "이전 질문"}, {"role": "assistant", "content": "이전 답"}),
        )

    def test_error_event_gets_a_text_field_copied_from_message(
        self, sessions, messages, accounts, _title, build_executor
    ):
        """새 엔진의 ERROR 이벤트는 `message`를 쓰는데 `_persist()`는 `text`를
        읽는다(레거시 규격) — `_run_deep_agent`가 맞춰 주지 않으면 저장된
        카드에 빈 텍스트만 남는다."""

        sessions.get.return_value = DEEP_SESSION
        messages.list_for_session.return_value = []
        accounts.get_profile.return_value = LEADER_PROFILE
        mock_executor = MagicMock()
        mock_executor.run.return_value = iter(
            [
                {
                    "type": "error",
                    "error_code": "AGENT_EXECUTION_FAILED",
                    "message": "에이전트 실행 중 오류가 발생했습니다.",
                    "complete": True,
                }
            ]
        )
        build_executor.return_value = mock_executor

        response = self.client.post(
            f"/api/chat/sessions/{DEEP_SESSION['session_id']}/messages/",
            {"content": "질문"},
            content_type="application/json",
            headers=auth_header(),
        )
        events = ndjson(response)

        # 에러도 마지막 줄로 온다 — _relay()의 종결 판정에 EVENT_ERROR가
        # 포함됐다는 뜻(안 들어 있으면 final이 None으로 남아 아래 적재 자체가
        # 안 된다).
        self.assertEqual(events[-1]["type"], "error")
        agent_write = messages.append.call_args_list[-1].kwargs
        self.assertEqual(agent_write["role"], "agent")
        self.assertEqual(agent_write["content"]["text"], "에이전트 실행 중 오류가 발생했습니다.")
        self.assertEqual(agent_write["content"]["complete"], True)


@patch("services.agent_runtime.build_default_executor")
@patch("apps.chat.api_views.AgentVersionRepository.resolve_live_version_id", new=lambda **_: None)
@patch("apps.chat.api_views.suggest_title")
@patch("apps.chat.api_views.AccountRepository")
@patch("apps.chat.api_views.ChatMessageRepository")
@patch("apps.chat.api_views.ChatSessionRepository")
class ChatSessionTitleTests(SimpleTestCase):
    """첫 답이 끝나면 이 대화의 이름을 짓는다.

    첫 발화를 그대로 제목으로 쓰면, 프로젝트 상세의 「업무 뽑기」가 늘 같은
    문장을 보내서 대화 둘이 글자까지 똑같아진다(2026-08-12 QA 시나리오 B).
    """

    def _post(self, accounts, content="이 프로젝트의 기준 문서에서 업무를 뽑아줘"):
        accounts.get_profile.return_value = LEADER_PROFILE
        return self.client.post(
            f"/api/chat/sessions/{SESSION['session_id']}/messages/",
            {"content": content},
            content_type="application/json",
            headers=auth_header(),
        )

    def test_첫_답_뒤에_제목이_한_줄로_온다(self, sessions, _messages, accounts, title, build_executor):
        sessions.get.return_value = SESSION
        sessions.rename_if_first_answer.return_value = True
        title.return_value = "감리 업무 20건 추출"
        _mock_new_engine(build_executor, [{"type": "result", "text": "20건 뽑았습니다.", "complete": True}])

        events = ndjson(self._post(accounts))

        self.assertEqual(events[-1], {"type": "session_title", "title": "감리 업무 20건 추출"})
        # 질문만으로는 「업무 뽑아줘」밖에 모른다. 답까지 넘겨야 이름이 정해진다.
        self.assertEqual(title.call_args.kwargs["answer"], "20건 뽑았습니다.")

    def test_두_번째_답부터는_안_바꾼다(self, sessions, _messages, accounts, title, build_executor):
        """대화가 길어질 때마다 제목이 바뀌면 사이드바에서 찾던 것이 사라진다."""

        sessions.get.return_value = SESSION
        sessions.rename_if_first_answer.return_value = False
        title.return_value = "다른 이름"
        _mock_new_engine(build_executor, [{"type": "result", "text": "네.", "complete": True}])

        self.assertEqual([e["type"] for e in ndjson(self._post(accounts))], ["result"])

    def test_실패한_실행에는_이름을_안_짓는다(self, sessions, _messages, accounts, title, build_executor):
        """오류로 끝난 대화를 그럴듯한 이름으로 덮으면 무엇이 실패했는지 가려진다."""

        sessions.get.return_value = SESSION

        def boom():
            raise TimeoutError("느립니다")
            yield  # pragma: no cover - 제너레이터로 만들기 위한 줄

        mock_executor = MagicMock()
        mock_executor.run.return_value = boom()
        build_executor.return_value = mock_executor

        self.assertEqual([e["type"] for e in ndjson(self._post(accounts))], ["error"])
        title.assert_not_called()

    def test_제목을_못_지으면_조용히_넘어간다(self, sessions, _messages, accounts, title, build_executor):
        sessions.get.return_value = SESSION
        title.return_value = None
        _mock_new_engine(build_executor, [{"type": "result", "text": "네.", "complete": True}])

        self.assertEqual([e["type"] for e in ndjson(self._post(accounts))], ["result"])
        sessions.rename_if_first_answer.assert_not_called()

@patch("apps.chat.api_views.ChatMessageRepository")
@patch("apps.chat.api_views.ChatSessionRepository")
class ConfirmGateTests(SimpleTestCase):
    """`engine` 필드가 없는 **레거시 확인 카드**를 본다.

    2026-08-22에 레거시 harness 재개 경로(`run_agent`)를 지우면서, 이런 카드는
    실행되지 않고 409로 거절된다. 승인한 셈 치고 조용히 넘기지 않는 것이
    요점이다 — 그 카드가 기다리던 것은 외부 시스템을 바꾸는 호출이다.
    """

    PENDING = {
        "message_id": "M1",
        "content": {
            "type": "awaiting_confirmation",
            "tool_ref": "mcp:MT001",
            "arguments": {"issues": ["A", "B", "C"]},
            "resume": {
                "messages": [{"role": "user", "content": "Jira에 올려줘"}],
                "tool_call": {
                    "id": "c1",
                    "tool_ref": "mcp:MT001",
                    "arguments": {"issues": ["A", "B", "C"]},
                },
            },
        },
    }

    def test_승인_대기가_없으면_409(self, sessions, messages):
        sessions.get.return_value = SESSION
        messages.latest_pending_confirmation.return_value = None

        response = self.client.post(
            f"/api/chat/sessions/{SESSION['session_id']}/confirm/",
            {},
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 409)

    def test_레거시_카드는_실행하지_않고_409로_거절한다(self, sessions, messages):
        """**승인한 셈 치고 넘기지 않는다.** 재개 경로가 없어진 지금 이 카드를
        조용히 통과시키면, 사람이 무엇을 승인하는지 다시 보여주지도 못한 채
        외부 시스템을 바꾸는 호출이 나갈 수 있다."""

        sessions.get.return_value = SESSION
        messages.latest_pending_confirmation.return_value = self.PENDING

        response = self.client.post(
            f"/api/chat/sessions/{SESSION['session_id']}/confirm/",
            {},
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 409)

    def test_재개_정보가_없는_카드는_거절한다(self, sessions, messages):
        """승인한 셈 치고 아무것도 안 하는 것보다 못 한다고 말하는 편이 낫다."""

        sessions.get.return_value = SESSION
        messages.latest_pending_confirmation.return_value = {
            "message_id": "M1",
            "content": {"type": "awaiting_confirmation"},
        }

        response = self.client.post(
            f"/api/chat/sessions/{SESSION['session_id']}/confirm/",
            {},
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 409)


@patch("services.agent_runtime.build_default_executor")
@patch("apps.chat.api_views.suggest_title", return_value=None)
@patch("apps.chat.api_views.AccountRepository")
@patch("apps.chat.api_views.ChatMessageRepository")
@patch("apps.chat.api_views.ChatSessionRepository")
class HITLResumeConfirmTests(SimpleTestCase):
    """`ChatConfirmAPIView` → `_resume_deep_agent()`(2026-08-19, §0순위 — 새 엔진
    HITL resume API). `content.get("engine") == "deepagents"`인 확인 카드는
    여기로 온다(`ConfirmGateTests`는 그 반대 — `engine` 필드가 없는 레거시
    카드가 409로 거절되는 것을 본다).
    """

    #: `run_id`는 `agent_run.run_id`(UUID 컬럼)에 그대로 들어가므로 실제
    #: 운영 코드가 늘 그러듯(`uuid.uuid4()`) 유효한 UUID 문자열로 둔다 —
    #: 임의 문자열이면 `_close_orphans()`의 정리 쿼리가 DB 타입 오류로
    #: 실패한다(적재 실패는 삼켜지지만 로그가 지저분해지고, "정말 닫혔는가"를
    #: 확인하는 테스트를 못 쓰게 된다).
    PENDING_RUN_ID = "22222222-2222-2222-2222-222222222222"

    PENDING = {
        "message_id": "M1",
        "content": {
            "type": "awaiting_confirmation",
            "engine": "deepagents",
            "run_id": PENDING_RUN_ID,
            "interrupt_id": "intr-1",
            "action_requests": [
                {
                    "name": "task_register",
                    "args": {"tasks": [{"title": "더미"}]},
                    "description": "업무 등록",
                }
            ],
            "tool_name": "task_register",
        },
    }

    def test_engine_deepagents_routes_to_resume_not_run(
        self, sessions, messages, accounts, _title, build_executor
    ):
        sessions.get.return_value = DEEP_SESSION
        accounts.get_profile.return_value = LEADER_PROFILE
        messages.latest_pending_confirmation.return_value = self.PENDING
        mock_executor = MagicMock()
        mock_executor.resume.return_value = iter(
            [{"type": "result", "text": "등록했습니다", "run_id": self.PENDING_RUN_ID, "complete": True}]
        )
        build_executor.return_value = mock_executor

        response = self.client.post(
            f"/api/chat/sessions/{DEEP_SESSION['session_id']}/confirm/",
            {},
            content_type="application/json",
            headers=auth_header(),
        )
        events = ndjson(response)

        mock_executor.resume.assert_called_once()
        mock_executor.run.assert_not_called()
        self.assertEqual([e["type"] for e in events], ["result"])

    def test_pending_run_id_reaches_context_run_id(
        self, sessions, messages, accounts, _title, build_executor
    ):
        """새로 발급하지 않는다 — 멈췄던 그 실행의 run_id를 그대로 써야
        `AgentRunRepository`가 그 행을 찾아 닫을 수 있다."""
        sessions.get.return_value = DEEP_SESSION
        accounts.get_profile.return_value = LEADER_PROFILE
        messages.latest_pending_confirmation.return_value = self.PENDING
        mock_executor = MagicMock()
        mock_executor.resume.return_value = iter(
            [{"type": "result", "text": "ok", "run_id": self.PENDING_RUN_ID, "complete": True}]
        )
        build_executor.return_value = mock_executor

        response = self.client.post(
            f"/api/chat/sessions/{DEEP_SESSION['session_id']}/confirm/",
            {},
            content_type="application/json",
            headers=auth_header(),
        )
        ndjson(response)

        call_kwargs = mock_executor.resume.call_args.kwargs
        self.assertEqual(call_kwargs["context"].run_id, self.PENDING_RUN_ID)

    def test_decision_defaults_to_approve(
        self, sessions, messages, accounts, _title, build_executor
    ):
        sessions.get.return_value = DEEP_SESSION
        accounts.get_profile.return_value = LEADER_PROFILE
        messages.latest_pending_confirmation.return_value = self.PENDING
        mock_executor = MagicMock()
        mock_executor.resume.return_value = iter(
            [{"type": "result", "text": "ok", "run_id": self.PENDING_RUN_ID, "complete": True}]
        )
        build_executor.return_value = mock_executor

        response = self.client.post(
            f"/api/chat/sessions/{DEEP_SESSION['session_id']}/confirm/",
            {},
            content_type="application/json",
            headers=auth_header(),
        )
        ndjson(response)

        call_kwargs = mock_executor.resume.call_args.kwargs
        self.assertEqual(call_kwargs["decisions"], [{"type": "approve"}])

    def test_체크를_푼_항목은_재개에도_반영된다(
        self, sessions, messages, accounts, _title, build_executor
    ):
        """화면에서 3건 중 2건만 승인하면 **2건만** 실행돼야 한다.

        2026-08-19 병합에서 이 연결이 한 번 끊겼다 — `_decisions_for()`는
        멀쩡한데 재개 경로가 그걸 안 부르고 전부 승인으로 보냈다. 함수만 덮는
        테스트로는 못 잡아서, 여기서 **executor 에 실제로 뭐가 넘어가는지**를
        본다.
        """

        pending = {
            "message_id": "M1",
            "content": {
                **self.PENDING["content"],
                "action_requests": [
                    {
                        "name": "task_register",
                        "args": {"tasks": [{"title": "가"}, {"title": "나"}, {"title": "다"}]},
                        "description": "업무 등록",
                    }
                ],
            },
        }
        sessions.get.return_value = DEEP_SESSION
        accounts.get_profile.return_value = LEADER_PROFILE
        messages.latest_pending_confirmation.return_value = pending
        mock_executor = MagicMock()
        mock_executor.resume.return_value = iter(
            [{"type": "result", "text": "ok", "run_id": self.PENDING_RUN_ID, "complete": True}]
        )
        build_executor.return_value = mock_executor

        response = self.client.post(
            f"/api/chat/sessions/{DEEP_SESSION['session_id']}/confirm/",
            {"selected": [0, 2]},
            content_type="application/json",
            headers=auth_header(),
        )
        ndjson(response)

        decisions = mock_executor.resume.call_args.kwargs["decisions"]
        self.assertEqual(decisions[0]["type"], "edit")
        self.assertEqual(
            [t["title"] for t in decisions[0]["edited_action"]["args"]["tasks"]],
            ["가", "다"],
        )

    def test_decision_reject_is_forwarded(
        self, sessions, messages, accounts, _title, build_executor
    ):
        sessions.get.return_value = DEEP_SESSION
        accounts.get_profile.return_value = LEADER_PROFILE
        messages.latest_pending_confirmation.return_value = self.PENDING
        mock_executor = MagicMock()
        mock_executor.resume.return_value = iter(
            [{"type": "result", "text": "취소했습니다", "run_id": self.PENDING_RUN_ID, "complete": True}]
        )
        build_executor.return_value = mock_executor

        response = self.client.post(
            f"/api/chat/sessions/{DEEP_SESSION['session_id']}/confirm/",
            {"decision": "reject"},
            content_type="application/json",
            headers=auth_header(),
        )
        ndjson(response)

        call_kwargs = mock_executor.resume.call_args.kwargs
        self.assertEqual(call_kwargs["decisions"], [{"type": "reject"}])

    def test_decisions_length_matches_action_requests_count(
        self, sessions, messages, accounts, _title, build_executor
    ):
        """`HumanInTheLoopMiddleware`는 `decisions`의 길이가 그 턴에 걸린
        `action_requests` 개수와 정확히 같아야 한다 — 다르면 ValueError."""
        pending = {
            "message_id": "M1",
            "content": {
                **self.PENDING["content"],
                "action_requests": [
                    {"name": "task_register", "args": {}},
                    {"name": "task_register", "args": {}},
                ],
            },
        }
        sessions.get.return_value = DEEP_SESSION
        accounts.get_profile.return_value = LEADER_PROFILE
        messages.latest_pending_confirmation.return_value = pending
        mock_executor = MagicMock()
        mock_executor.resume.return_value = iter(
            [{"type": "result", "text": "ok", "run_id": self.PENDING_RUN_ID, "complete": True}]
        )
        build_executor.return_value = mock_executor

        response = self.client.post(
            f"/api/chat/sessions/{DEEP_SESSION['session_id']}/confirm/",
            {},
            content_type="application/json",
            headers=auth_header(),
        )
        ndjson(response)

        call_kwargs = mock_executor.resume.call_args.kwargs
        self.assertEqual(call_kwargs["decisions"], [{"type": "approve"}, {"type": "approve"}])

    def test_agent_id_and_version_id_match_session(
        self, sessions, messages, accounts, _title, build_executor
    ):
        sessions.get.return_value = DEEP_SESSION
        accounts.get_profile.return_value = LEADER_PROFILE
        messages.latest_pending_confirmation.return_value = self.PENDING
        mock_executor = MagicMock()
        mock_executor.resume.return_value = iter(
            [{"type": "result", "text": "ok", "run_id": self.PENDING_RUN_ID, "complete": True}]
        )
        build_executor.return_value = mock_executor

        response = self.client.post(
            f"/api/chat/sessions/{DEEP_SESSION['session_id']}/confirm/",
            {},
            content_type="application/json",
            headers=auth_header(),
        )
        ndjson(response)

        call_kwargs = mock_executor.resume.call_args.kwargs
        self.assertEqual(call_kwargs["agent_id"], "AG001")
        self.assertEqual(call_kwargs["agent_version_id"], "AV001")
        self.assertNotIn("draft", call_kwargs)

    def test_result_from_resume_is_persisted_and_clears_pending_shape(
        self, sessions, messages, accounts, _title, build_executor
    ):
        """재개가 끝까지 성공하면(EVENT_RESULT) 저장되는 내용은 새로운 확인
        대기 카드가 아니라 보통의 답변이다 — `_persist()`의 `else` 분기."""
        sessions.get.return_value = DEEP_SESSION
        accounts.get_profile.return_value = LEADER_PROFILE
        messages.latest_pending_confirmation.return_value = self.PENDING
        mock_executor = MagicMock()
        mock_executor.resume.return_value = iter(
            [{"type": "result", "text": "등록했습니다", "run_id": self.PENDING_RUN_ID, "complete": True}]
        )
        build_executor.return_value = mock_executor

        response = self.client.post(
            f"/api/chat/sessions/{DEEP_SESSION['session_id']}/confirm/",
            {},
            content_type="application/json",
            headers=auth_header(),
        )
        ndjson(response)

        stored = messages.append.call_args.kwargs["content"]
        self.assertEqual(stored["type"], "result")
        self.assertEqual(stored["text"], "등록했습니다")

    def test_resumed_result_closes_the_agent_run_via_known_run_ids(
        self, sessions, messages, accounts, _title, build_executor
    ):
        """`trace_events(..., known_run_ids=(run_id,))` 없이는 이 run의
        `agent_run` 행이 `PENDING`에서 영원히 못 닫힌다(이 세션의 §0순위
        핵심 버그) — HTTP 계층까지 통째로 거쳐 실제로 닫히는지 확인한다."""
        sessions.get.return_value = DEEP_SESSION
        accounts.get_profile.return_value = LEADER_PROFILE
        messages.latest_pending_confirmation.return_value = self.PENDING
        mock_executor = MagicMock()
        mock_executor.resume.return_value = iter(
            [{"type": "result", "text": "등록했습니다", "run_id": self.PENDING_RUN_ID, "complete": True}]
        )
        build_executor.return_value = mock_executor

        with patch("services.agent_runtime.tracing.AgentRunRepository") as runs:
            response = self.client.post(
                f"/api/chat/sessions/{DEEP_SESSION['session_id']}/confirm/",
                {},
                content_type="application/json",
                headers=auth_header(),
            )
            ndjson(response)

        runs.finish.assert_called_once_with(
            run_id=self.PENDING_RUN_ID, status="DONE", iterations=0, token_in=None, token_out=None
        )
        # known_run_ids로 미리 채워 둔 덕에 닫혔다 — start_with_id는 이
        # 스트림에서 한 번도 안 불린다(EVENT_AGENT_STARTED가 없는 재개
        # 스트림이므로).
        runs.start_with_id.assert_not_called()

    def test_rejected_run_still_persists_as_result(
        self, sessions, messages, accounts, _title, build_executor
    ):
        """거절도 승인과 마찬가지로 실행이 끝까지 간다(그저 handler가 아예
        안 불린 채로) — HumanInTheLoopMiddleware가 거절 사유를 ToolMessage로
        모델에 되돌려주고 모델이 다음 말을 잇는다, 별도의 '거절됨' 이벤트
        타입이 있는 게 아니다."""
        sessions.get.return_value = DEEP_SESSION
        accounts.get_profile.return_value = LEADER_PROFILE
        messages.latest_pending_confirmation.return_value = self.PENDING
        mock_executor = MagicMock()
        mock_executor.resume.return_value = iter(
            [
                {
                    "type": "result",
                    "text": "요청하신 대로 취소했습니다.",
                    "run_id": self.PENDING_RUN_ID,
                    "complete": True,
                }
            ]
        )
        build_executor.return_value = mock_executor

        response = self.client.post(
            f"/api/chat/sessions/{DEEP_SESSION['session_id']}/confirm/",
            {"decision": "reject"},
            content_type="application/json",
            headers=auth_header(),
        )
        events = ndjson(response)

        self.assertEqual(events[-1]["type"], "result")


class ResumeDecisionTests(SimpleTestCase):
    """새 엔진 재개에서 **체크를 푼 항목이 실행되지 않는지** 지킨다.

    2026-08-19 병합에서 이 경로가 조용히 사라진 적이 있다 — 결정 목록을
    `[{"type": "approve"}] * n` 으로만 만들면, 화면에서 3건을 빼고 승인해도
    10건이 전부 등록된다. 실패가 아니라 **틀린 데이터**로 끝나서 누가 볼
    때까지 안 드러난다. 그때 이 함수를 덮는 테스트가 하나도 없어서 아무
    테스트도 안 깨졌다.
    """

    def _requests(self, count=3):
        return [{"name": "task_register", "args": {"tasks": [{"title": f"업무{i}"} for i in range(count)]}}]

    def test_전체_승인은_그대로_승인이다(self):
        """줄일 것이 없으면 `edit` 로 안 바꾼다 — 승인한 것과 실행되는 것이
        같다는 보장이 인자를 다시 쓰는 경로를 안 타야 한 겹 더 두껍다."""

        self.assertEqual(_decisions_for(self._requests(), None), [{"type": "approve"}])

    def test_체크를_푼_항목은_빠진다(self):
        decisions = _decisions_for(self._requests(3), [0, 2])

        self.assertEqual(decisions[0]["type"], "edit")
        self.assertEqual(
            [t["title"] for t in decisions[0]["edited_action"]["args"]["tasks"]],
            ["업무0", "업무2"],
        )

    def test_결정_개수는_요청_개수와_같다(self):
        """다르면 `HumanInTheLoopMiddleware` 가 `ValueError` 를 던진다(실측)."""

        requests = self._requests() * 2

        self.assertEqual(len(_decisions_for(requests, [0])), len(requests))

    def test_전부_그대로_고르면_승인으로_둔다(self):
        self.assertEqual(_decisions_for(self._requests(3), [0, 1, 2]), [{"type": "approve"}])


class PerCallDecisionTests(SimpleTestCase):
    """호출별 승인·거절(2026-08-21, 병렬실행 Phase 2).

    모델이 한 턴에 side_effect 도구를 여러 개 부르면 확인 카드에 여러 항목이
    한꺼번에 뜨는데, 지금까지는 전부에 같은 결정만 적용할 수 있었다. 배경은
    `docs/작업기록/Deep_Agents/2026-08-21_02_MCP_승인_범위_변경_반영.md`.
    """

    def _requests(self, count=3):
        return [
            {"name": f"tool_{i}", "args": {"n": i}} for i in range(count)
        ]

    def test_호출마다_다른_결정을_적용한다(self):
        decisions = _decisions_for(
            self._requests(3),
            None,
            per_call=[
                {"action_index": 0, "type": "approve"},
                {"action_index": 1, "type": "reject"},
                {"action_index": 2, "type": "approve"},
            ],
        )

        self.assertEqual(
            decisions, [{"type": "approve"}, {"type": "reject"}, {"type": "approve"}]
        )

    def test_입력_순서가_섞여_있어도_action_index_순서로_편다(self):
        """`HumanInTheLoopMiddleware`는 `action_requests`와 **같은 순서**의
        목록을 요구한다(실측) — 화면이 어떤 순서로 보내든 인덱스 기준으로
        정렬해야 결정이 엉뚱한 호출에 붙지 않는다."""
        decisions = _decisions_for(
            self._requests(3),
            None,
            per_call=[
                {"action_index": 2, "type": "reject"},
                {"action_index": 0, "type": "approve"},
                {"action_index": 1, "type": "approve"},
            ],
        )

        self.assertEqual(
            decisions, [{"type": "approve"}, {"type": "approve"}, {"type": "reject"}]
        )

    def test_빠진_항목이_있으면_거부한다(self):
        """빠진 걸 조용히 승인하면 사용자가 안 본 호출이 실행된다."""
        with self.assertRaises(PerCallDecisionsError):
            _decisions_for(
                self._requests(3), None, per_call=[{"action_index": 0, "type": "approve"}]
            )

    def test_같은_인덱스가_두_번_오면_거부한다(self):
        """같은 호출에 승인과 거절이 동시에 오면 뭐가 이기는지 애매해진다."""
        with self.assertRaises(PerCallDecisionsError):
            _decisions_for(
                self._requests(2),
                None,
                per_call=[
                    {"action_index": 0, "type": "approve"},
                    {"action_index": 0, "type": "reject"},
                    {"action_index": 1, "type": "approve"},
                ],
            )

    def test_범위를_벗어난_인덱스는_거부한다(self):
        with self.assertRaises(PerCallDecisionsError):
            _decisions_for(
                self._requests(1),
                None,
                per_call=[
                    {"action_index": 0, "type": "approve"},
                    {"action_index": 5, "type": "approve"},
                ],
            )

    def test_거절된_첫_호출에는_selected를_적용하지_않는다(self):
        """`reject`를 `edit`로 덮어쓰면 거절이 승인으로 뒤집힌다 — 실행 안 될
        호출의 인자를 다듬는 건 의미도 없다."""
        requests = [{"name": "task_register", "args": {"tasks": [{"title": "A"}, {"title": "B"}]}}]

        decisions = _decisions_for(
            requests, [0], per_call=[{"action_index": 0, "type": "reject"}]
        )

        self.assertEqual(decisions, [{"type": "reject"}])

    def test_승인된_첫_호출에는_selected가_그대로_적용된다(self):
        """호출별 결정을 써도 기존 항목 단위 선택(체크 해제)은 그대로 살아
        있어야 한다 — 두 기능은 다른 층위다."""
        requests = [{"name": "task_register", "args": {"tasks": [{"title": "A"}, {"title": "B"}]}}]

        decisions = _decisions_for(
            requests, [0], per_call=[{"action_index": 0, "type": "approve"}]
        )

        self.assertEqual(decisions[0]["type"], "edit")
        self.assertEqual(
            [t["title"] for t in decisions[0]["edited_action"]["args"]["tasks"]], ["A"]
        )

    def test_per_call이_없으면_예전_동작_그대로다(self):
        self.assertEqual(_decisions_for(self._requests(2), None), [{"type": "approve"}] * 2)


@patch("services.agent_runtime.build_default_executor")
@patch("apps.chat.api_views.AgentVersionRepository.resolve_live_version_id", new=lambda **_: None)
@patch("apps.chat.api_views.suggest_title", return_value=None)
@patch("apps.chat.api_views.AccountRepository")
@patch("apps.chat.api_views.ChatMessageRepository")
@patch("apps.chat.api_views.ChatSessionRepository")
class ChatHistoryTests(SimpleTestCase):
    """앞선 턴이 모델에게 간다.

    이게 없으면 **매 턴이 콜드 스타트**다 — 「그것 말고 또 있나?」에 대해
    "무엇을 가리키는지 확인하지 못했습니다"라고 답한다(2026-08-11 실측).

    새 엔진은 이력(`conversation_messages`)과 이번 발화(`user_input`)를 따로
    받는다 — 레거시처럼 한 리스트로 합쳐 보내지 않는다. 그래서
    `conversation_messages`에는 **이번 발화가 안 들어 있다**(레거시 시절
    `_post()`가 돌려주던 것과 다름, 2026-08-14 전환).
    """

    def _post(self, build_executor, accounts, messages, rows):
        messages.list_for_session.return_value = rows
        accounts.get_profile.return_value = LEADER_PROFILE
        mock_executor = _mock_new_engine(build_executor, [])
        response = self.client.post(
            f"/api/chat/sessions/{SESSION['session_id']}/messages/",
            {"content": "그것 말고 또 있나?"},
            content_type="application/json",
            headers=auth_header(),
        )
        # StreamingHttpResponse는 지연 스트림이다 — 실제로 읽어야
        # executor.run()이 불린다(DeepAgentSessionStreamTests와 같은 이유,
        # 2026-08-15 로컬 실행에서 실측: 안 읽으면 call_args가 None으로
        # 남는다).
        ndjson(response)
        return mock_executor.run.call_args.kwargs

    def test_앞선_질문과_답이_함께_간다(self, sessions, messages, accounts, _title, build_executor):
        sessions.get.return_value = SESSION
        call_kwargs = self._post(
            build_executor,
            accounts,
            messages,
            [
                {"role": "user", "content": {"type": "text", "text": "뭘 할 수 있지?"}},
                {"role": "agent", "content": {"type": "result", "text": "문서를 찾고 업무를 뽑습니다."}},
            ],
        )

        self.assertEqual(
            call_kwargs["conversation_messages"],
            (
                {"role": "user", "content": "뭘 할 수 있지?"},
                {"role": "assistant", "content": "문서를 찾고 업무를 뽑습니다."},
            ),
        )
        # 이번 발화는 이력이 아니라 user_input으로 따로 간다.
        self.assertEqual(call_kwargs["user_input"], "그것 말고 또 있나?")

    def test_도구_호출_원본은_복원하지_않는다(self, sessions, messages, accounts, _title, build_executor):
        """reasoning·function_call 은 짝이 맞아야 해서 지난 턴 것은 온전하지 않다."""

        sessions.get.return_value = SESSION
        sent = self._post(
            build_executor,
            accounts,
            messages,
            [
                {"role": "user", "content": {"type": "text", "text": "업무 뽑아줘"}},
                {
                    "role": "agent",
                    "content": {
                        "type": "result",
                        "text": "3건 뽑았습니다.",
                        "events": [{"type": "tool_call_started", "tool_ref": "task_extraction"}],
                    },
                },
            ],
        )["conversation_messages"]

        self.assertNotIn("function_call", str(sent))
        self.assertEqual(sent[1], {"role": "assistant", "content": "3건 뽑았습니다."})

    def test_승인_대기로_끝난_턴도_한_줄로_남는다(self, sessions, messages, accounts, _title, build_executor):
        """비워 두면 모델이 그 턴에 아무 일도 없었다고 여긴다."""

        sessions.get.return_value = SESSION
        sent = self._post(
            build_executor,
            accounts,
            messages,
            [
                {"role": "user", "content": {"type": "text", "text": "등록해줘"}},
                {
                    "role": "agent",
                    "content": {"type": "awaiting_confirmation", "tool_name": "업무 등록"},
                },
            ],
        )["conversation_messages"]

        self.assertIn("업무 등록", sent[1]["content"])

    def test_긴_대화는_최근_것만_보낸다(self, sessions, messages, accounts, _title, build_executor):
        sessions.get.return_value = SESSION
        rows = [
            {"role": "user", "content": {"type": "text", "text": f"질문{i}"}} for i in range(40)
        ]
        sent = self._post(build_executor, accounts, messages, rows)["conversation_messages"]

        # 이력 최근 20건 — 이번 발화는 user_input으로 따로 가므로 여기 안 섞인다.
        self.assertEqual(len(sent), 20)
        self.assertEqual(sent[0]["content"], "질문20")


@patch("services.agent_runtime.build_default_executor")
@patch("apps.chat.api_views.AgentVersionRepository.resolve_live_version_id", new=lambda **_: None)
@patch("apps.chat.api_views.suggest_title", return_value=None)
@patch("apps.chat.api_views.AccountRepository")
@patch("apps.chat.api_views.ChatMessageRepository")
@patch("apps.chat.api_views.ChatSessionRepository")
class PiiMaskingTests(SimpleTestCase):
    """사용자가 채팅에 직접 입력한 credential·개인정보·권한/보안 서술은
    모델에게 보내기 전에 가린다(2026-08-19, §2순위, 사용자 확정 범위).

    **저장은 원문 그대로** 다 — 화면은 사용자 자신이 뭘 썼는지 그대로 봐야
    한다. 마스킹은 모델로 가는 값에만 적용한다: 이번 턴 `user_input`,
    이력 재전송(`conversation_messages`), 제목 생성용 `question`.
    """

    SENSITIVE = "제 전화번호는 010-1234-5678이에요"

    def test_이번_턴_발화는_모델에게_가려서_간다(
        self, sessions, messages, accounts, _title, build_executor
    ):
        sessions.get.return_value = SESSION
        messages.list_for_session.return_value = []
        accounts.get_profile.return_value = LEADER_PROFILE
        mock_executor = _mock_new_engine(build_executor, [{"type": "result", "text": "ok", "complete": True}])

        response = self.client.post(
            f"/api/chat/sessions/{SESSION['session_id']}/messages/",
            {"content": self.SENSITIVE},
            content_type="application/json",
            headers=auth_header(),
        )
        ndjson(response)

        user_input = mock_executor.run.call_args.kwargs["user_input"]
        self.assertNotIn("010-1234-5678", user_input)
        self.assertIn("제 전화번호는", user_input)

    def test_저장은_원문_그대로_한다(
        self, sessions, messages, accounts, _title, build_executor
    ):
        """화면은 사용자 자신의 발화를 그대로 봐야 한다 — 마스킹은 모델
        입력에만 적용하고 저장에는 적용하지 않는다."""

        sessions.get.return_value = SESSION
        messages.list_for_session.return_value = []
        accounts.get_profile.return_value = LEADER_PROFILE
        _mock_new_engine(build_executor, [{"type": "result", "text": "ok", "complete": True}])

        response = self.client.post(
            f"/api/chat/sessions/{SESSION['session_id']}/messages/",
            {"content": self.SENSITIVE},
            content_type="application/json",
            headers=auth_header(),
        )
        ndjson(response)

        user_write = next(
            call.kwargs for call in messages.append.call_args_list if call.kwargs["role"] == "user"
        )
        self.assertEqual(user_write["content"]["text"], self.SENSITIVE)

    def test_이력_재전송도_가려서_간다(
        self, sessions, messages, accounts, _title, build_executor
    ):
        """`_history()`가 저장된(원문) 과거 발화를 모델에게 다시 태울 때도
        가린다 — 이번 요청만 막고 다음 턴 재전송에서 새면 의미가 없다."""

        sessions.get.return_value = SESSION
        messages.list_for_session.return_value = [
            {"role": "user", "content": {"type": "text", "text": self.SENSITIVE}},
            {"role": "agent", "content": {"type": "result", "text": "알겠습니다."}},
        ]
        accounts.get_profile.return_value = LEADER_PROFILE
        mock_executor = _mock_new_engine(build_executor, [{"type": "result", "text": "ok", "complete": True}])

        response = self.client.post(
            f"/api/chat/sessions/{SESSION['session_id']}/messages/",
            {"content": "다음 질문"},
            content_type="application/json",
            headers=auth_header(),
        )
        ndjson(response)

        conversation_messages = mock_executor.run.call_args.kwargs["conversation_messages"]
        self.assertNotIn("010-1234-5678", str(conversation_messages))
        self.assertIn("제 전화번호는", conversation_messages[0]["content"])

    def test_제목_생성도_가려진_값을_받는다(
        self, sessions, messages, accounts, title, build_executor
    ):
        sessions.get.return_value = SESSION
        messages.list_for_session.return_value = []
        sessions.rename_if_first_answer.return_value = True
        accounts.get_profile.return_value = LEADER_PROFILE
        title.return_value = "전화번호 문의"
        _mock_new_engine(build_executor, [{"type": "result", "text": "확인했습니다.", "complete": True}])

        response = self.client.post(
            f"/api/chat/sessions/{SESSION['session_id']}/messages/",
            {"content": self.SENSITIVE},
            content_type="application/json",
            headers=auth_header(),
        )
        ndjson(response)

        question = title.call_args.kwargs["question"]
        self.assertNotIn("010-1234-5678", question)

    def test_민감정보가_없으면_그대로_간다(
        self, sessions, messages, accounts, _title, build_executor
    ):
        """오탐 걱정 — 평범한 문장까지 바뀌면 안 된다."""

        sessions.get.return_value = SESSION
        messages.list_for_session.return_value = []
        accounts.get_profile.return_value = LEADER_PROFILE
        mock_executor = _mock_new_engine(build_executor, [{"type": "result", "text": "ok", "complete": True}])

        response = self.client.post(
            f"/api/chat/sessions/{SESSION['session_id']}/messages/",
            {"content": "이 프로젝트 문서에서 업무를 뽑아줘"},
            content_type="application/json",
            headers=auth_header(),
        )
        ndjson(response)

        self.assertEqual(
            mock_executor.run.call_args.kwargs["user_input"], "이 프로젝트 문서에서 업무를 뽑아줘"
        )


@patch("apps.chat.api_views.ChatSessionRepository")
class ChatListScopeTests(SimpleTestCase):
    """대화 목록은 **내 것만**이다 — 계층 `팀 > 프로젝트 > 채팅(개인)`.

    8/12 까지 `WHERE s.team_id` 라 팀원 전체가 서로의 대화를 보고 있었다.
    사이드바를 「프로젝트 > 대화」로 바꾸면서 화면만 고치고 쿼리를 안 고쳤다 —
    조용히 되돌아갈 수 있는 종류라 여기서 못 박는다.
    """

    def test_팀이_아니라_계정으로_고른다(self, sessions):
        sessions.list_for_account.return_value = []

        self.client.get("/api/chat/sessions/", headers=auth_header())

        sessions.list_for_account.assert_called_once_with("UA001")
        self.assertFalse(
            hasattr(sessions.list_for_team, "assert_not_called")
            and sessions.list_for_team.called,
            "팀 전체 목록을 부르면 안 된다",
        )
