"""Jira 이슈 수집 — 검색 클라이언트·교체 저장·동기화 엔드포인트.

`DATABASES = {}`라 테스트 DB가 없어 리포지토리와 커서는 모킹한다. 여기서 검증하는
것은 **DB에 닿기 전에 결정되는 계약**이다: 상태 표시 문자열이 아니라 표준 카테고리를
쓰는가, 초를 시간으로 바꾸는가, 매핑에 실패한 행을 버리지 않는가, 소스 하나가
실패해도 나머지를 반영하는가, 재동기화가 행을 늘리지 않는가.
"""

from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase

from apps.accounts.tokens import issue_token
from apps.connectors.oauth import OAuthError


def _issue(key, *, category="indeterminate", status_name="진행 중", email="a@b.com", tracking=None):
    fields = {
        "status": {"name": status_name, "statusCategory": {"key": category, "name": status_name}},
        "priority": {"name": "Medium"},
        "duedate": "2026-08-07",
    }
    if email is not None:
        fields["assignee"] = {"emailAddress": email}
    if tracking is not None:
        fields["timetracking"] = tracking
    return {"key": key, "fields": fields}


class JiraIssueSearchTests(SimpleTestCase):
    def _credential(self):
        return patch(
            "apps.connectors.clients.credential_for",
            return_value={"access_token": "token", "cloud_id": "CLOUD"},
        )

    def _response(self, payload):
        response = Mock(status_code=200)
        response.json.return_value = payload
        return response

    def test_uses_post_jql_endpoint_not_removed_get_search(self):
        """구 `GET /rest/api/3/search`는 Jira Cloud에서 제거됐다."""

        from apps.connectors import clients

        with self._credential(), patch(
            "apps.connectors.clients.requests.post",
            return_value=self._response({"issues": []}),
        ) as post:
            clients.search_jira_issues(account_id="UA001", project_key="KAN")

        url = post.call_args.args[0]
        self.assertTrue(url.endswith("/rest/api/3/search/jql"))
        self.assertIn("statusCategory != Done", post.call_args.kwargs["json"]["jql"])

    def test_display_name_differs_by_project_but_category_is_the_same(self):
        """실측 케이스 — KAN은 '해야 할 일', AIP는 '할 일'로 오지만 둘 다 TO_DO다."""

        from apps.connectors import clients

        payload = {
            "issues": [
                _issue("KAN-1", category="new", status_name="해야 할 일"),
                _issue("AIP-1", category="new", status_name="할 일"),
            ]
        }
        with self._credential(), patch(
            "apps.connectors.clients.requests.post", return_value=self._response(payload)
        ):
            rows = clients.search_jira_issues(account_id="UA001", project_key="KAN")

        self.assertEqual([row["status_category"] for row in rows], ["TO_DO", "TO_DO"])
        # 표시 문자열은 그대로 남긴다 — 사람이 보는 값이라 지우지 않는다.
        self.assertEqual([row["status"] for row in rows], ["해야 할 일", "할 일"])

    def test_unknown_category_key_becomes_none(self):
        """모르는 key를 TO_DO로 밀어넣으면 부하가 조용히 늘어난다."""

        from apps.connectors import clients

        payload = {"issues": [_issue("KAN-2", category="something-new")]}
        with self._credential(), patch(
            "apps.connectors.clients.requests.post", return_value=self._response(payload)
        ):
            rows = clients.search_jira_issues(account_id="UA001", project_key="KAN")

        self.assertIsNone(rows[0]["status_category"])

    def test_seconds_become_hours(self):
        from apps.connectors import clients

        payload = {
            "issues": [
                _issue(
                    "KAN-3",
                    tracking={
                        "originalEstimateSeconds": 28800,
                        "remainingEstimateSeconds": 14400,
                        "timeSpentSeconds": 5400,
                    },
                )
            ]
        }
        with self._credential(), patch(
            "apps.connectors.clients.requests.post", return_value=self._response(payload)
        ):
            rows = clients.search_jira_issues(account_id="UA001", project_key="KAN")

        self.assertEqual(rows[0]["estimate"], 8.0)
        self.assertEqual(rows[0]["remaining"], 4.0)
        self.assertEqual(rows[0]["spent"], 1.5)

    def test_missing_timetracking_leaves_remaining_null(self):
        """0시간으로 간주하면 공수 미입력이 "일이 없는 사람"으로 보인다."""

        from apps.connectors import clients

        payload = {"issues": [_issue("KAN-4", tracking=None)]}
        with self._credential(), patch(
            "apps.connectors.clients.requests.post", return_value=self._response(payload)
        ):
            rows = clients.search_jira_issues(account_id="UA001", project_key="KAN")

        self.assertIsNone(rows[0]["remaining"])

    def test_private_profile_leaves_email_null(self):
        from apps.connectors import clients

        payload = {"issues": [_issue("KAN-5", email=None)]}
        with self._credential(), patch(
            "apps.connectors.clients.requests.post", return_value=self._response(payload)
        ):
            rows = clients.search_jira_issues(account_id="UA001", project_key="KAN")

        self.assertIsNone(rows[0]["assignee_email"])

    def test_start_at_is_not_invented_from_created(self):
        """Jira에 시작일 필드가 없다. created를 넣으면 없는 정보를 만드는 것이다."""

        from apps.connectors import clients

        payload = {"issues": [_issue("KAN-6")]}
        with self._credential(), patch(
            "apps.connectors.clients.requests.post", return_value=self._response(payload)
        ):
            rows = clients.search_jira_issues(account_id="UA001", project_key="KAN")

        self.assertIsNone(rows[0]["start_at"])

    def test_follows_next_page_token(self):
        """`startAt`으로 짜면 오류 없이 첫 페이지만 돌아온다."""

        from apps.connectors import clients

        first = self._response({"issues": [_issue("KAN-7")], "nextPageToken": "TOKEN2"})
        second = self._response({"issues": [_issue("KAN-8")]})

        with self._credential(), patch(
            "apps.connectors.clients.requests.post", side_effect=[first, second]
        ) as post:
            rows = clients.search_jira_issues(account_id="UA001", project_key="KAN")

        self.assertEqual([row["jira_issue_id"] for row in rows], ["KAN-7", "KAN-8"])
        self.assertNotIn("nextPageToken", post.call_args_list[0].kwargs["json"])
        self.assertEqual(post.call_args_list[1].kwargs["json"]["nextPageToken"], "TOKEN2")

    def test_network_failure_becomes_oauth_error(self):
        from apps.connectors import clients

        with self._credential(), patch(
            "apps.connectors.clients.requests.post",
            side_effect=requests.RequestException("boom"),
        ):
            with self.assertRaises(OAuthError):
                clients.search_jira_issues(account_id="UA001", project_key="KAN")


class _FakeCursor:
    def __init__(self):
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def execute(self, sql, params=None):
        self.statements.append((" ".join(str(sql).split()), params))


class _FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def cursor(self):
        return self._cursor


class ExistTaskReplaceTests(SimpleTestCase):
    def _run(self, rows):
        from backend.db import repositories

        cursor = _FakeCursor()
        codes = iter(f"ET{n:03d}" for n in range(1, 99))
        with patch.object(
            repositories, "database_connection", return_value=_FakeConnection(cursor)
        ), patch.object(repositories, "next_short_code", side_effect=lambda *a, **k: next(codes)):
            inserted = repositories.ExistTaskRepository.replace_for_source(
                proj_source_id="PS009", rows=rows
            )
        return inserted, cursor

    def test_deletes_only_its_own_source_first(self):
        """`proj_id`로 지우면 같은 프로젝트의 다른 Jira 소스까지 날아간다."""

        _, cursor = self._run([{"jira_issue_id": "KAN-1"}])

        first_sql, first_params = cursor.statements[0]
        self.assertEqual(first_sql, "DELETE FROM exist_task WHERE proj_source_id = %s")
        self.assertEqual(first_params, ("PS009",))

    def test_resync_does_not_grow_row_count(self):
        rows = [{"jira_issue_id": "KAN-1"}, {"jira_issue_id": "KAN-2"}]
        first, _ = self._run(rows)
        second, cursor = self._run(rows)

        self.assertEqual(first, 2)
        self.assertEqual(second, 2)
        self.assertEqual(sum(1 for sql, _ in cursor.statements if sql.startswith("INSERT")), 2)

    def test_duplicate_issue_in_one_response_is_inserted_once(self):
        """같은 이슈가 두 줄이 되면 그 사람 부하가 2배로 잡힌다."""

        inserted, _ = self._run(
            [{"jira_issue_id": "KAN-1"}, {"jira_issue_id": "KAN-1"}]
        )
        self.assertEqual(inserted, 1)

    def test_unmapped_assignee_row_is_still_inserted(self):
        """버리면 부하 총량이 조용히 줄어든다 — 틀린 숫자가 맞아 보이는 최악의 형태."""

        inserted, cursor = self._run(
            [{"jira_issue_id": "KAN-1", "assignee_person_id": None, "remaining": 8}]
        )
        insert_params = [params for sql, params in cursor.statements if sql.startswith("INSERT")]

        self.assertEqual(inserted, 1)
        self.assertIn(None, insert_params[0])


class TaskSyncEndpointTests(SimpleTestCase):
    def setUp(self):
        self.token = issue_token("UA001")

    def _sources(self):
        return [
            {"proj_source_id": "PS009", "external_source_id": "AIP"},
            {"proj_source_id": "PS010", "external_source_id": "KAN"},
        ]

    def _post(self, **patches):
        with patch(
            "apps.projects.api_views.ExistTaskRepository.list_jira_sources",
            return_value=self._sources(),
        ), patch(
            "apps.projects.api_views.ExistTaskRepository.replace_for_source",
            side_effect=lambda *, proj_source_id, rows: len(rows),
        ) as replace, patch(
            "apps.projects.api_views.search_jira_issues", **patches
        ), patch(
            "apps.projects.api_views.lookup_person_ids_by_external_email",
            return_value={"a@b.com": "PX002"},
        ):
            response = self.client.post(
                "/api/projects/PJ001/tasks/sync/",
                HTTP_AUTHORIZATION=f"Bearer {self.token}",
            )
        return response, replace

    def test_one_source_failure_does_not_stop_the_rest(self):
        def search(*, account_id, project_key):
            if project_key == "AIP":
                raise OAuthError("Jira 이슈를 가져오지 못했습니다(AIP).")
            return [
                {
                    "jira_issue_id": "KAN-1",
                    "assignee_email": "a@b.com",
                    "remaining": 8.0,
                    "status_category": "IN_PROGRESS",
                }
            ]

        response, _ = self._post(side_effect=search)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual([s["project_key"] for s in body["sources"]], ["KAN"])
        self.assertEqual([f["project_key"] for f in body["failed"]], ["AIP"])

    def test_counts_unmapped_and_missing_estimate(self):
        issues = [
            {
                "jira_issue_id": "KAN-1",
                "assignee_email": "a@b.com",
                "remaining": 8.0,
                "status_category": "IN_PROGRESS",
            },
            # 담당자가 person_link에 없다
            {
                "jira_issue_id": "KAN-2",
                "assignee_email": "ghost@b.com",
                "remaining": 4.0,
                "status_category": "TO_DO",
            },
            # 공수 미입력 (`no-estimate` 라벨 케이스)
            {
                "jira_issue_id": "KAN-3",
                "assignee_email": "a@b.com",
                "remaining": None,
                "status_category": "TO_DO",
            },
        ]
        response, replace = self._post(return_value=issues)
        body = response.json()

        # 소스 두 개에 같은 목록을 물렸으므로 각각 1건씩, 합해서 2건이 잡힌다.
        self.assertEqual(body["unmapped_assignees"], 2)
        self.assertEqual(body["missing_estimate"], 2)
        # 진단에 잡혔다고 행을 버리지는 않는다.
        self.assertEqual([s["fetched"] for s in body["sources"]], [3, 3])
        self.assertEqual(len(replace.call_args.kwargs["rows"]), 3)

    def test_email_matching_ignores_case(self):
        issues = [
            {
                "jira_issue_id": "KAN-1",
                "assignee_email": "A@B.com",
                "remaining": 8.0,
                "status_category": "IN_PROGRESS",
            }
        ]
        response, replace = self._post(return_value=issues)

        self.assertEqual(response.json()["unmapped_assignees"], 0)
        self.assertEqual(replace.call_args.kwargs["rows"][0]["assignee_person_id"], "PX002")
