"""지연·임박 업무 집계 — `GET /api/team/deadlines/`.

`DATABASES = {}`라 리포지토리는 모킹한다. 여기서 지키는 계약은 **무엇을 세고
무엇을 빼는가**다: 끝난 일은 마감이 지났어도 지연이 아니고, 마감이 없는 일은 어느
쪽도 아니며, 며칠 남았는지는 서버가 정한다.

날짜 경계가 이 화면의 전부라 `due_at`을 UTC 자정이 아닌 시각으로 둔다 — 시간대
때문에 하루가 밀리는 실수를 테스트가 잡아야 한다.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.accounts.tokens import issue_token

TODAY = datetime.now(UTC).date()


def _task(key, *, days=None, category="IN_PROGRESS", person="PX002"):
    """마감이 오늘로부터 `days` 뒤인 업무. `days=None`이면 마감이 없다."""

    due = None
    if days is not None:
        # 자정이 아니라 오후로 둔다. 시간대 보정을 빠뜨리면 여기서 하루가 밀린다.
        due = datetime.combine(TODAY + timedelta(days=days), datetime.min.time(), UTC)
        due = due.replace(hour=15)

    return {
        "exist_task_id": f"ET{key[-3:]}",
        "jira_issue_id": key,
        "summary": f"{key} 작업",
        "assignee_person_id": person,
        "status_category": category,
        "due_at": due,
        "proj_id": "PJ001",
        "project_key": "KAN",
        "project_name": "KAN 프로젝트",
    }


class DeadlineEndpointTests(SimpleTestCase):
    def setUp(self):
        self.token = issue_token("UA001")

    def _get(self, tasks):
        with patch(
            "apps.projects.api_views.ExistTaskRepository.list_for_team",
            return_value=tasks,
        ), patch(
            "apps.projects.api_views.lookup_persons",
            return_value={"PX002": {"name": "임준"}},
        ):
            response = self.client.get(
                "/api/team/deadlines/",
                HTTP_AUTHORIZATION=f"Bearer {self.token}",
            )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_overdue_and_soon_are_split_at_today(self):
        body = self._get([_task("KAN-1", days=-1), _task("KAN-2", days=0), _task("KAN-3", days=3)])

        self.assertEqual([t["jira_issue_id"] for t in body["overdue"]], ["KAN-1"])
        self.assertEqual([t["jira_issue_id"] for t in body["soon"]], ["KAN-2", "KAN-3"])

    def test_done_is_never_overdue(self):
        """이미 끝난 일은 마감이 지났어도 팀장이 할 일이 없다."""

        body = self._get([_task("KAN-1", days=-5, category="DONE")])

        self.assertEqual(body["overdue"], [])
        self.assertEqual(body["soon"], [])

    def test_task_without_a_deadline_is_in_neither(self):
        """마감을 모르는 것을 지연으로 세면 없는 문제를 만든다."""

        body = self._get([_task("KAN-1", days=None)])

        self.assertEqual(body["overdue"], [])
        self.assertEqual(body["soon"], [])

    def test_beyond_the_week_is_in_neither(self):
        body = self._get([_task("KAN-1", days=7), _task("KAN-2", days=6)])

        self.assertEqual(body["overdue"], [])
        self.assertEqual([t["jira_issue_id"] for t in body["soon"]], ["KAN-2"])

    def test_server_computes_the_day_count(self):
        """브라우저가 TIMESTAMPTZ 를 빼면 시간대에 따라 하루가 밀린다."""

        body = self._get([_task("KAN-1", days=-4), _task("KAN-2", days=2)])

        self.assertEqual(body["overdue"][0]["days"], -4)
        self.assertEqual(body["soon"][0]["days"], 2)

    def test_most_urgent_first(self):
        body = self._get([_task("KAN-1", days=-1), _task("KAN-2", days=-9)])

        self.assertEqual([t["jira_issue_id"] for t in body["overdue"]], ["KAN-2", "KAN-1"])

    def test_row_carries_what_the_screen_needs_to_act(self):
        """이슈 키만으로는 어느 쪽을 밀지 판단할 수 없다."""

        row = self._get([_task("KAN-1", days=-2)])["overdue"][0]

        self.assertEqual(row["summary"], "KAN-1 작업")
        self.assertEqual(row["assignee_name"], "임준")
        self.assertEqual(row["project_name"], "KAN 프로젝트")
        self.assertEqual(row["proj_id"], "PJ001")

    def test_unmapped_assignee_is_kept(self):
        """담당자를 모른다고 빼면 지연 건수가 조용히 줄어든다."""

        body = self._get([_task("KAN-1", days=-2, person=None)])

        self.assertEqual(len(body["overdue"]), 1)
        self.assertIsNone(body["overdue"][0]["assignee_name"])
