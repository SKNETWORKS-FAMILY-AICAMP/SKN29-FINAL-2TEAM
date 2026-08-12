"""Chat API 단위 테스트. DB 는 띄우지 않고 Repository 를 mock 한다.

가장 중요하게 보는 것은 **확인 게이트**다. 승인 전에 아무것도 실행되지 않고,
승인 뒤에는 사용자가 승인한 바로 그 호출이 실행되는가.
"""

import json
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.accounts.tokens import issue_token
from apps.chat.api_views import _apply_selection
from apps.chat.serializers import message_response
from backend.db.errors import PermissionDenied

SESSION = {
    "session_id": "11111111-1111-1111-1111-111111111111",
    "team_id": "TM001",
    "account_id": "UA001",
    "agent_id": "AG001",
    "proj_id": None,
    "title": "8/11 업무 정리",
    "created_at": "2026-08-11T09:00:00Z",
    "updated_at": "2026-08-11T09:00:00Z",
}


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


@patch("apps.chat.api_views.run_agent")
@patch("apps.chat.api_views.ChatMessageRepository")
@patch("apps.chat.api_views.ChatSessionRepository")
class ChatStreamTests(SimpleTestCase):
    def test_이벤트를_NDJSON_으로_중계한다(self, sessions, messages, run):
        sessions.get.return_value = SESSION
        run.return_value = iter(
            [
                {"type": "stage", "step": 1, "total": 10, "label": "생각하는 중"},
                {"type": "result", "text": "8월 20일입니다.", "complete": True},
            ]
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

    def test_사용자_발화는_스트림_전에_확정한다(self, sessions, messages, run):
        """답이 없는 대화는 다시 물으면 되지만, 질문이 사라지면 복구할 수 없다."""

        sessions.get.return_value = SESSION
        run.return_value = iter([])

        self.client.post(
            f"/api/chat/sessions/{SESSION['session_id']}/messages/",
            {"content": "일정 알려줘"},
            content_type="application/json",
            headers=auth_header(),
        )

        first = messages.append.call_args_list[0].kwargs
        self.assertEqual(first["role"], "user")
        self.assertEqual(first["content"], {"type": "text", "text": "일정 알려줘"})

    def test_승인_대기가_남아_있어도_새_발화를_받는다(self, sessions, messages, run):
        """승인 대기 중에도 말할 수 있다(6차 단계 1-5 · 확정 ③).

        화면이 승인 대기 중 입력창을 여는 근거다. 발화 경로는 pending 을 아예
        보지 않고 새 실행을 시작한다 — 승인을 강요하지 않고, 대신 지나간 확인
        카드가 「승인하지 않고 넘어감」으로 남는다.
        """

        sessions.get.return_value = SESSION
        run.return_value = iter([{"type": "result", "text": "다시 뽑았습니다.", "complete": True}])

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
        # 재개가 아니라 **새 실행**이다 — 앞선 대화 상태를 물려받지 않는다.
        self.assertNotIn("resume_tool_call", run.call_args.args[2])

    def test_스트림이_끝나면_카드를_통째로_적재한다(self, sessions, messages, run):
        sessions.get.return_value = SESSION
        run.return_value = iter(
            [
                {"type": "stage", "step": 1, "total": 10, "label": "생각하는 중"},
                {"type": "result", "text": "끝", "complete": True},
            ]
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

    def test_실행이_터지면_마지막_줄로_알린다(self, sessions, messages, run):
        sessions.get.return_value = SESSION

        def boom():
            yield {"type": "stage", "step": 1, "total": 10, "label": "생각하는 중"}
            raise TimeoutError("느립니다")

        run.return_value = boom()

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


@patch("apps.chat.api_views.run_agent")
@patch("apps.chat.api_views.ChatMessageRepository")
@patch("apps.chat.api_views.ChatSessionRepository")
class ConfirmGateTests(SimpleTestCase):
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

    def test_승인_대기가_없으면_409(self, sessions, messages, _run):
        sessions.get.return_value = SESSION
        messages.latest_pending_confirmation.return_value = None

        response = self.client.post(
            f"/api/chat/sessions/{SESSION['session_id']}/confirm/",
            {},
            content_type="application/json",
            headers=auth_header(),
        )

        self.assertEqual(response.status_code, 409)

    def test_승인하면_저장해_둔_그_호출을_실행한다(self, sessions, messages, run):
        """모델에게 다시 묻지 않는다 — 물으면 승인한 것과 다른 게 실행될 수 있다."""

        sessions.get.return_value = SESSION
        messages.latest_pending_confirmation.return_value = self.PENDING
        run.return_value = iter([{"type": "result", "text": "3건 등록", "complete": True}])

        response = self.client.post(
            f"/api/chat/sessions/{SESSION['session_id']}/confirm/",
            {},
            content_type="application/json",
            headers=auth_header(),
        )
        ndjson(response)

        context = run.call_args.args[2]
        self.assertEqual(
            context["resume_tool_call"]["arguments"]["issues"], ["A", "B", "C"]
        )
        self.assertEqual(context["approved_tool_calls"], ["mcp:MT001"])
        self.assertEqual(context["messages"], self.PENDING["content"]["resume"]["messages"])

    def test_체크를_푼_항목은_실행에서_빠진다(self, sessions, messages, run):
        sessions.get.return_value = SESSION
        messages.latest_pending_confirmation.return_value = self.PENDING
        run.return_value = iter([{"type": "result", "text": "2건 등록", "complete": True}])

        response = self.client.post(
            f"/api/chat/sessions/{SESSION['session_id']}/confirm/",
            {"selected": [0, 2]},
            content_type="application/json",
            headers=auth_header(),
        )
        ndjson(response)

        context = run.call_args.args[2]
        self.assertEqual(context["resume_tool_call"]["arguments"]["issues"], ["A", "C"])

    def test_재개_정보가_없는_카드는_거절한다(self, sessions, messages, _run):
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

    def test_확인_대기는_재개_정보와_함께_적재된다(self, sessions, messages, run):
        sessions.get.return_value = SESSION
        resume = {"messages": [{"role": "user", "content": "올려줘"}], "tool_call": {"id": "c1"}}
        run.return_value = iter(
            [
                {
                    "type": "awaiting_confirmation",
                    "run_id": "RUN-1",
                    "tool_ref": "mcp:MT001",
                    "tool_name": "Jira 이슈 생성",
                    "arguments": {"issues": ["A"]},
                    "resume": resume,
                }
            ]
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


@patch("apps.chat.api_views.run_agent")
@patch("apps.chat.api_views.ChatMessageRepository")
@patch("apps.chat.api_views.ChatSessionRepository")
class ChatHistoryTests(SimpleTestCase):
    """앞선 턴이 모델에게 간다.

    이게 없으면 **매 턴이 콜드 스타트**다 — 「그것 말고 또 있나?」에 대해
    "무엇을 가리키는지 확인하지 못했습니다"라고 답한다(2026-08-11 실측).
    """

    def _post(self, run, messages, rows):
        messages.list_for_session.return_value = rows
        run.return_value = iter([])
        self.client.post(
            f"/api/chat/sessions/{SESSION['session_id']}/messages/",
            {"content": "그것 말고 또 있나?"},
            content_type="application/json",
            headers=auth_header(),
        )
        return run.call_args.args[2]["messages"]

    def test_앞선_질문과_답이_함께_간다(self, sessions, messages, run):
        sessions.get.return_value = SESSION
        sent = self._post(
            run,
            messages,
            [
                {"role": "user", "content": {"type": "text", "text": "뭘 할 수 있지?"}},
                {"role": "agent", "content": {"type": "result", "text": "문서를 찾고 업무를 뽑습니다."}},
            ],
        )

        self.assertEqual(
            sent,
            [
                {"role": "user", "content": "뭘 할 수 있지?"},
                {"role": "assistant", "content": "문서를 찾고 업무를 뽑습니다."},
                {"role": "user", "content": "그것 말고 또 있나?"},
            ],
        )

    def test_도구_호출_원본은_복원하지_않는다(self, sessions, messages, run):
        """reasoning·function_call 은 짝이 맞아야 해서 지난 턴 것은 온전하지 않다."""

        sessions.get.return_value = SESSION
        sent = self._post(
            run,
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
        )

        self.assertNotIn("function_call", str(sent))
        self.assertEqual(sent[1], {"role": "assistant", "content": "3건 뽑았습니다."})

    def test_승인_대기로_끝난_턴도_한_줄로_남는다(self, sessions, messages, run):
        """비워 두면 모델이 그 턴에 아무 일도 없었다고 여긴다."""

        sessions.get.return_value = SESSION
        sent = self._post(
            run,
            messages,
            [
                {"role": "user", "content": {"type": "text", "text": "등록해줘"}},
                {
                    "role": "agent",
                    "content": {"type": "awaiting_confirmation", "tool_name": "업무 등록"},
                },
            ],
        )

        self.assertIn("업무 등록", sent[1]["content"])

    def test_긴_대화는_최근_것만_보낸다(self, sessions, messages, run):
        sessions.get.return_value = SESSION
        rows = [
            {"role": "user", "content": {"type": "text", "text": f"질문{i}"}} for i in range(40)
        ]
        sent = self._post(run, messages, rows)

        # 앞선 이력 20건 + 이번 발화 1건.
        self.assertEqual(len(sent), 21)
        self.assertEqual(sent[0]["content"], "질문20")
