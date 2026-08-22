"""hitl_warnings.py — 승인 카드에 붙는 동시 실행·재시도 경고.

정본: `docs/작업기록/Deep_Agents/2026-08-21_04_MCP_동시_쓰기_경고_설계.md`,
`..._03_외부_Write_Tool_재시도_안전성.md` §4.2.

DB는 `McpCallNoteRepository`를 통째로 patch해서 대신한다 — 여기서 지키려는
것은 "어떤 사실이 있을 때 어떤 경고가 붙는가"이지 SQL이 아니다.
"""

from unittest.mock import patch

from django.test import SimpleTestCase
from langchain_core.messages import AIMessage, HumanMessage

from services.agent_runtime.context import RuntimeContext
from services.agent_runtime.hitl_warnings import build_confirmation_description

REPO = "backend.db.agent_platform.McpCallNoteRepository"


def _context(run_id="11111111-1111-1111-1111-111111111111"):
    return RuntimeContext(account_id="AC001", team_id="TM001", role="leader", run_id=run_id)


def _call(name, call_id):
    return {"name": name, "args": {"q": call_id}, "id": call_id}


def _state(*tool_calls):
    return {
        "messages": [
            HumanMessage(content="해줘"),
            AIMessage(content="", tool_calls=list(tool_calls)),
        ]
    }


class _Repo:
    """기본은 "아무 경고도 없음". 테스트가 필요한 것만 켠다."""

    def __init__(self, *, server_ids=None, active=False, timed_out=False):
        self.server_ids = server_ids or {}
        self.active = active
        self.timed_out = timed_out
        self.active_calls = []

    def server_ids_for_tool_refs(self, tool_refs):
        return {ref: self.server_ids[ref] for ref in tool_refs if ref in self.server_ids}

    def has_other_active_on_same_server(self, **kwargs):
        self.active_calls.append(kwargs)
        return self.active

    def has_timeout_in_run(self, **kwargs):
        return self.timed_out


class NonMcpToolsGetNoWarningTests(SimpleTestCase):
    """내장 도구는 이 경고의 대상이 아니다 — 그쪽은 lock으로 직렬화한다."""

    def test_builtin_tool_description_has_no_warning(self):
        describe = build_confirmation_description(context=_context(), stale_after_seconds=600)

        text = describe(_call("task_register", "c1"), _state(), None)

        self.assertNotIn("⚠", text)
        self.assertIn("task_register", text)


class SameBatchWarningTests(SimpleTestCase):
    """§3.2 — DB의 "실행 중" 표시만으로는 못 잡는 사각지대.

    같은 AIMessage에 걸린 호출들은 승인 대기 시점에 **어느 것도 아직 실행을
    시작하지 않았다**. 그래서 state를 직접 봐야 한다.
    """

    def test_two_calls_to_the_same_server_warn_each_other(self):
        repo = _Repo(server_ids={"mcp:MT001": "MS001", "mcp:MT002": "MS001"})
        state = _state(_call("mcp__MT001", "c1"), _call("mcp__MT002", "c2"))
        describe = build_confirmation_description(context=_context(), stale_after_seconds=600)

        with patch(REPO, repo):
            text = describe(_call("mcp__MT001", "c1"), state, None)

        self.assertIn("같은 MCP 서버를 쓰는 다른 작업도 함께", text)

    def test_calls_to_different_servers_do_not_warn(self):
        repo = _Repo(server_ids={"mcp:MT001": "MS001", "mcp:MT002": "MS002"})
        state = _state(_call("mcp__MT001", "c1"), _call("mcp__MT002", "c2"))
        describe = build_confirmation_description(context=_context(), stale_after_seconds=600)

        with patch(REPO, repo):
            text = describe(_call("mcp__MT001", "c1"), state, None)

        self.assertNotIn("함께 걸려 있습니다", text)

    def test_a_lone_mcp_call_does_not_warn_about_itself(self):
        repo = _Repo(server_ids={"mcp:MT001": "MS001"})
        state = _state(_call("mcp__MT001", "c1"))
        describe = build_confirmation_description(context=_context(), stale_after_seconds=600)

        with patch(REPO, repo):
            text = describe(_call("mcp__MT001", "c1"), state, None)

        self.assertNotIn("⚠", text)


class ActiveElsewhereWarningTests(SimpleTestCase):
    def test_another_running_call_on_the_same_server_warns(self):
        repo = _Repo(server_ids={"mcp:MT001": "MS001"}, active=True)
        state = _state(_call("mcp__MT001", "c1"))
        describe = build_confirmation_description(context=_context(), stale_after_seconds=600)

        with patch(REPO, repo):
            text = describe(_call("mcp__MT001", "c1"), state, None)

        self.assertIn("다른 실행이 지금 같은 MCP 서버에", text)

    def test_calls_in_this_batch_are_excluded_from_the_active_lookup(self):
        """같은 배치의 형제는 §3.2가 이미 알렸으므로 여기서 또 세지 않는다 —
        안 빼면 같은 사실로 경고가 두 번 붙는다."""
        repo = _Repo(server_ids={"mcp:MT001": "MS001", "mcp:MT002": "MS001"})
        state = _state(_call("mcp__MT001", "c1"), _call("mcp__MT002", "c2"))
        describe = build_confirmation_description(context=_context(), stale_after_seconds=600)

        with patch(REPO, repo):
            describe(_call("mcp__MT001", "c1"), state, None)

        excluded = repo.active_calls[0]["exclude_tool_call_ids"]
        self.assertIn("c1", excluded)
        self.assertIn("c2", excluded)

    def test_stale_threshold_is_passed_through(self):
        """오래된 "실행 중" 표시를 거르는 기준(gunicorn worker timeout)이 실제로
        조회까지 전달돼야 한다 — 안 그러면 죽은 실행이 남긴 찌꺼기가 영원히
        경고를 띄운다."""
        repo = _Repo(server_ids={"mcp:MT001": "MS001"})
        describe = build_confirmation_description(context=_context(), stale_after_seconds=600)

        with patch(REPO, repo):
            describe(_call("mcp__MT001", "c1"), _state(_call("mcp__MT001", "c1")), None)

        self.assertEqual(repo.active_calls[0]["stale_after_seconds"], 600)


class TimeoutRetryWarningTests(SimpleTestCase):
    """§4.2 — timeout은 "실패"가 아니라 "결과를 모름"이다."""

    def test_a_previous_timeout_on_the_same_tool_warns(self):
        repo = _Repo(server_ids={"mcp:MT001": "MS001"}, timed_out=True)
        describe = build_confirmation_description(context=_context(), stale_after_seconds=600)

        with patch(REPO, repo):
            text = describe(_call("mcp__MT001", "c9"), _state(_call("mcp__MT001", "c9")), None)

        self.assertIn("결과를 확인하지 못한 적이", text)

    def test_no_run_id_skips_the_timeout_lookup(self):
        """run_id 없이 도구를 직접 부르는 호출자(테스트 등)를 안 깨뜨린다."""
        repo = _Repo(server_ids={"mcp:MT001": "MS001"}, timed_out=True)
        describe = build_confirmation_description(
            context=RuntimeContext(account_id="AC001", team_id="TM001", role="leader"),
            stale_after_seconds=600,
        )

        with patch(REPO, repo):
            text = describe(_call("mcp__MT001", "c9"), _state(_call("mcp__MT001", "c9")), None)

        self.assertNotIn("결과를 확인하지 못한 적이", text)


class WarningsNeverBlockApprovalTests(SimpleTestCase):
    """경고는 **판단을 돕는 부가 정보**지 승인 게이트가 아니다."""

    def test_repository_failure_still_produces_a_usable_card(self):
        class _Broken:
            def server_ids_for_tool_refs(self, tool_refs):
                raise RuntimeError("DB 안 됨")

            def has_other_active_on_same_server(self, **kwargs):
                raise RuntimeError("DB 안 됨")

            def has_timeout_in_run(self, **kwargs):
                raise RuntimeError("DB 안 됨")

        describe = build_confirmation_description(context=_context(), stale_after_seconds=600)

        with patch(REPO, _Broken()):
            text = describe(_call("mcp__MT001", "c1"), _state(_call("mcp__MT001", "c1")), None)

        # 카드 자체는 그대로 뜬다 — 도구와 인자가 여전히 보인다.
        self.assertIn("mcp__MT001", text)
        self.assertNotIn("⚠", text)

    def test_all_three_warnings_can_stack(self):
        repo = _Repo(
            server_ids={"mcp:MT001": "MS001", "mcp:MT002": "MS001"}, active=True, timed_out=True
        )
        state = _state(_call("mcp__MT001", "c1"), _call("mcp__MT002", "c2"))
        describe = build_confirmation_description(context=_context(), stale_after_seconds=600)

        with patch(REPO, repo):
            text = describe(_call("mcp__MT001", "c1"), state, None)

        self.assertEqual(text.count("⚠"), 3)
