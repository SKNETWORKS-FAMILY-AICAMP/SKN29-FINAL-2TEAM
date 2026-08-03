"""부하 계산 — 회귀 테스트.

계산기가 순수 함수라 DB 없이 그대로 돌린다. 여기 있는 기대값은 2026-08-03에
실계정 Jira와 People DB 시드에서 실측한 값이다(작업지시서 A-2·A-3·0-5).

이 테스트가 막는 것은 검증 문서가 실데이터로 재현했던 네 가지 오작동이다.
- 육아휴직자가 음수 부하율을 받아 "가장 여유 있는 사람"으로 추천 1순위에 오름
- 하루 연차가 0시간으로 차감돼 연차를 안 쓴 것이 됨
- `wk_hours`에 FTE를 다시 곱해 반차 근무자의 용량이 반토막 남
- 기간 창이 없어 전원이 100%를 넘어 구분력을 잃음
"""

from datetime import date

from django.test import SimpleTestCase

from services.workload import calculator

# 2026-08-03(월) ~ 08-31(월) 전. 평일 20일이고 광복절(8/15)이 토요일이라
# 공휴일 보정 없이도 실제 근무일과 일치한다.
PERIOD_START = date(2026, 8, 3)
PERIOD_END = date(2026, 8, 31)

# 실계정 Jira 실측(작업지시서 0-5)
MOCK_HOURS = {
    "PX002": {"name": "임준", "KAN": 144.0, "AIP": 52.0},
    "PB001": {"name": "김지훈", "KAN": 114.0, "AIP": 24.0},
    "PF002": {"name": "최원빈", "KAN": 86.0, "AIP": 16.0},
    "PB002": {"name": "성주연", "KAN": 50.0, "AIP": 12.0},
    "PF001": {"name": "임준억", "KAN": 42.0, "AIP": 8.0},
}


def _fulltime(person_id, name="아무개"):
    return {
        "person_id": person_id,
        "name": name,
        "job_role": "개발",
        "wk_hours": 40.0,
        "def_wk_hours": 40.0,
        "fte": 1.0,
    }


def _task(issue, person_id, hours, *, project="KAN", due="2026-08-14", category="TO_DO"):
    return {
        "jira_issue_id": issue,
        "assignee_person_id": person_id,
        "remaining": hours,
        "due_at": due,
        "status_category": category,
        "project_key": project,
    }


def _run(profiles, tasks, absences=()):
    return calculator.calculate(
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        profiles=profiles,
        absences=list(absences),
        tasks=tasks,
    )


def _person(result, person_id):
    return next(row for row in result["people"] if row["person_id"] == person_id)


class CapacityTests(SimpleTestCase):
    def test_fulltime_four_weeks_is_160_hours(self):
        """버퍼를 곱하지 않는다. ×0.8을 넣으면 128시간이 되고 시연 숫자가 어긋난다."""

        result = _run([_fulltime("PX002")], [])
        self.assertEqual(result["workdays"], 20)
        self.assertEqual(_person(result, "PX002")["effective_capacity"], 160.0)

    def test_half_time_is_80_hours_not_40(self):
        """`wk_hours`에 이미 FTE가 반영돼 있다. 또 곱하면 반토막 난다."""

        profile = {
            "person_id": "PB003",
            "name": "윤수빈",
            "wk_hours": 20.0,
            "def_wk_hours": 40.0,
            "fte": 0.5,
        }
        self.assertEqual(_person(_run([profile], []), "PB003")["effective_capacity"], 80.0)

    def test_falls_back_to_contract_hours_times_fte(self):
        profile = {
            "person_id": "PB003",
            "name": "윤수빈",
            "wk_hours": None,
            "def_wk_hours": 40.0,
            "fte": 0.5,
        }
        self.assertEqual(_person(_run([profile], []), "PB003")["effective_capacity"], 80.0)

    def test_no_schedule_is_blocked_not_assumed_fulltime(self):
        """40시간을 가정하면 근무조건을 모르는 사람이 한가해 보인다."""

        profile = {"person_id": "PZ999", "name": "미상", "wk_hours": None, "def_wk_hours": None, "fte": None}
        row = _person(_run([profile], []), "PZ999")

        self.assertIsNone(row["load_rate"])
        self.assertEqual(row["blocked_reason"], calculator.BLOCKED_NO_SCHEDULE)

    def test_single_day_leave_deducts_a_full_day(self):
        """시드의 하루 연차는 `start_at = end_at`이다. 시각 차로 계산하면 0시간이다."""

        absence = {
            "person_id": "PX002",
            "start_at": "2026-08-04T00:00:00+00:00",
            "end_at": "2026-08-04T00:00:00+00:00",
        }
        row = _person(_run([_fulltime("PX002")], [], [absence]), "PX002")

        self.assertEqual(row["absent_days"], 1)
        self.assertEqual(row["absence_hours"], 8.0)
        self.assertEqual(row["effective_capacity"], 152.0)

    def test_long_leave_is_clipped_to_the_window(self):
        """육아휴직 214일을 통째로 빼면 −1552시간이 된다."""

        absence = {
            "person_id": "PB005",
            "start_at": "2026-06-01T00:00:00+00:00",
            "end_at": "2026-12-31T00:00:00+00:00",
        }
        row = _person(_run([_fulltime("PB005", "서지호")], [], [absence]), "PB005")

        self.assertEqual(row["effective_capacity"], 0.0)
        self.assertGreaterEqual(row["effective_capacity"], 0)

    def test_person_on_leave_is_blocked_not_the_most_available(self):
        """음수 용량이면 부하율 오름차순에서 휴직자가 1순위로 올라온다."""

        absence = {
            "person_id": "PB005",
            "start_at": "2026-06-01T00:00:00+00:00",
            "end_at": "2026-12-31T00:00:00+00:00",
        }
        result = _run(
            [_fulltime("PB005", "서지호"), _fulltime("PX002", "임준")],
            [_task("KAN-1", "PX002", 80.0)],
            [absence],
        )
        on_leave = _person(result, "PB005")

        self.assertIsNone(on_leave["load_rate"])
        self.assertIsNone(on_leave["remaining_capacity"])
        self.assertEqual(on_leave["blocked_reason"], calculator.BLOCKED_ON_LEAVE)

    def test_zero_capacity_does_not_divide_by_zero(self):
        absence = {
            "person_id": "PB005",
            "start_at": "2026-06-01T00:00:00+00:00",
            "end_at": "2026-12-31T00:00:00+00:00",
        }
        result = _run([_fulltime("PB005")], [_task("KAN-1", "PB005", 40.0)], [absence])
        self.assertIsNone(_person(result, "PB005")["load_rate"])

    def test_overlapping_absences_deduct_a_day_once(self):
        absences = [
            {"person_id": "PX002", "start_at": "2026-08-04", "end_at": "2026-08-06"},
            {"person_id": "PX002", "start_at": "2026-08-05", "end_at": "2026-08-07"},
        ]
        row = _person(_run([_fulltime("PX002")], [], absences), "PX002")
        self.assertEqual(row["absent_days"], 4)


class AllocationTests(SimpleTestCase):
    def test_in_progress_without_due_date_counts(self):
        result = _run(
            [_fulltime("PX002")],
            [_task("KAN-1", "PX002", 20.0, due=None, category="IN_PROGRESS")],
        )
        self.assertEqual(_person(result, "PX002")["current_allocation"], 20.0)

    def test_unstarted_without_due_date_goes_to_backlog(self):
        """언젠가 할 일을 이번 창에 합치면 과부하가 실제보다 커 보인다."""

        row = _person(
            _run([_fulltime("PX002")], [_task("KAN-1", "PX002", 40.0, due=None, category="TO_DO")]),
            "PX002",
        )
        self.assertEqual(row["current_allocation"], 0.0)
        self.assertEqual(row["unscheduled_backlog_hours"], 40.0)
        self.assertEqual(row["unscheduled_backlog_count"], 1)

    def test_overdue_task_still_counts(self):
        """밀린 일은 지금 해야 한다."""

        result = _run([_fulltime("PX002")], [_task("KAN-1", "PX002", 10.0, due="2026-07-01")])
        self.assertEqual(_person(result, "PX002")["current_allocation"], 10.0)

    def test_missing_remaining_is_counted_not_zeroed(self):
        """0으로 간주하면 공수를 안 적은 사람이 한가해 보인다."""

        row = _person(
            _run([_fulltime("PX002")], [_task("KAN-49", "PX002", None)]),
            "PX002",
        )
        self.assertEqual(row["current_allocation"], 0.0)
        self.assertEqual(row["missing_estimate_count"], 1)

    def test_done_tasks_are_ignored(self):
        result = _run(
            [_fulltime("PX002")],
            [_task("KAN-1", "PX002", 40.0, category="DONE")],
        )
        self.assertEqual(_person(result, "PX002")["current_allocation"], 0.0)

    def test_duplicate_issue_counts_once(self):
        result = _run(
            [_fulltime("PX002")],
            [_task("KAN-1", "PX002", 40.0), _task("KAN-1", "PX002", 40.0, project="AIP")],
        )
        self.assertEqual(_person(result, "PX002")["current_allocation"], 40.0)

    def test_unmapped_assignee_is_reported_not_silently_dropped(self):
        result = _run([_fulltime("PX002")], [_task("KAN-9", None, 30.0)])
        self.assertEqual(result["unmapped_assignee_count"], 1)
        self.assertEqual(_person(result, "PX002")["current_allocation"], 0.0)

    def test_identity_capacity_minus_allocation(self):
        result = _run([_fulltime("PX002")], [_task("KAN-1", "PX002", 60.0)])
        row = _person(result, "PX002")
        self.assertEqual(
            row["effective_capacity"] - row["current_allocation"], row["remaining_capacity"]
        )

    def test_load_rate_is_clamped_to_column_range(self):
        """`load_rate NUMERIC(5,2)`가 999.99까지다. 분자·분모는 그대로 남는다."""

        result = _run([_fulltime("PX002")], [_task("KAN-1", "PX002", 9999.0)])
        row = _person(result, "PX002")

        self.assertEqual(row["load_rate"], 999.99)
        self.assertEqual(row["current_allocation"], 9999.0)


class DemoScenarioTests(SimpleTestCase):
    """시연 장면 — "한 프로젝트만 보면 90%, 합치면 122%"."""

    def _profiles(self):
        return [_fulltime(pid, data["name"]) for pid, data in MOCK_HOURS.items()]

    def _tasks(self):
        tasks = []
        for person_id, data in MOCK_HOURS.items():
            for project in ("KAN", "AIP"):
                tasks.append(
                    _task(f"{project}-{person_id}", person_id, data[project], project=project)
                )
        return tasks

    def test_combined_load_matches_measured_values(self):
        result = _run(self._profiles(), self._tasks())
        actual = {row["person_id"]: row["load_rate"] for row in result["people"]}

        self.assertEqual(actual["PX002"], 122.5)
        self.assertEqual(actual["PB001"], 86.25)
        self.assertEqual(actual["PF002"], 63.75)
        self.assertEqual(actual["PB002"], 38.75)
        self.assertEqual(actual["PF001"], 31.25)

    def test_single_project_view_is_ninety_percent(self):
        """08-03 ALTER의 `proj_source_id`가 이 분해를 가능하게 했다."""

        result = _run(self._profiles(), self._tasks())
        breakdown = {row["project_key"]: row for row in _person(result, "PX002")["by_project"]}

        self.assertEqual(breakdown["KAN"]["hours"], 144.0)
        self.assertEqual(breakdown["KAN"]["load_rate"], 90.0)
        self.assertEqual(breakdown["AIP"]["hours"], 52.0)

    def test_only_the_top_person_is_overloaded(self):
        """전원이 100%를 넘으면 누가 과부하인지 구분이 안 된다."""

        result = _run(self._profiles(), self._tasks())
        overloaded = [row["person_id"] for row in result["people"] if (row["load_rate"] or 0) > 100]

        self.assertEqual(overloaded, ["PX002"])
