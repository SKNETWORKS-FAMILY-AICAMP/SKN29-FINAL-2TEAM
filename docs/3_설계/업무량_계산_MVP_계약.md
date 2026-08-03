# 업무량 계산 MVP 계약

> 확정 2026-08-03 · 구현 반영 완료
> 구현: `services/workload/calculator.py` · `GET /api/projects/<id>/workload/` · `/tasks/workload`
> 이력: [[업무량계산_조사]](조사) → [[업무량계산_조사_검증]](검증) → 이 문서(확정)
> 실행 기록: [[2026-08-03_부하계산_작업지시서]] · 단계별 To-Do는 [[Jira_부하계산_ToDo]]

## 1. 무엇을 계산하는가

계산하는 값의 이름은 **실제 업무부하가 아니라 계획 공수 기준 배정률**이다.

```text
부하율(%) = 같은 기간에 수행할 것으로 확인된 Jira 잔여 공수
            ────────────────────────────────────────  × 100
            같은 기간의 개인 유효 근무가능시간
```

이 값이 답하는 질문은 하나다.

> 확인 가능한 Jira 계획과 HR 근무조건을 기준으로, 이 사람이 선택 기간에 쓸 수 있는
> 시간 중 얼마가 이미 배정됐는가?

**답하지 않는 질문:**

- 당사자가 실제로 느끼는 정신적·정서적 부담은 얼마인가
- 같은 8시간 업무 중 어느 것이 더 어렵거나 스트레스가 큰가
- Jira에 없는 지원·회의·돌발업무까지 포함한 실제 노동강도는 얼마인가

NASA-TLX가 주관적 업무부하를 정신적·신체적·시간적 요구, 수행, 노력, 좌절의 여섯
차원으로 재는 데서 보듯, Jira 예상시간만으로 사람의 실제 부하를 측정했다고 말할 근거는
없다. **화면과 발표에서는 그 한계를 함께 표시한다.**

> 코드·DB·API의 이름은 `load_rate`·`부하율`로 유지한다. 기획서 v5를 비롯한 설계 문서
> 6곳과 컬럼명이 그 어휘를 쓰고 있어, 지금 바꾸면 이득보다 정합성 비용이 크다.
> 정직한 명칭은 화면 라벨과 발표 문구에서 쓴다.

## 2. 최종 수식

```text
H = [period_start, period_end)     반열린 구간. 기본 28일, from·to로 변경 가능

① 주 근무시간 = wk_hours
              → 없으면 def_wk_hours × fte
              → 둘 다 없으면 BLOCKED (NO_SCHEDULE)

② 용량 = (주 근무시간 ÷ 5) × H 안의 근무일 수
        − H와 겹치는 APPROVED 부재 (반드시 clip)
        − 확인된 고정일정 (지금은 0)

③ 할당 = Σ remaining
         where status_category != 'DONE'
           and remaining IS NOT NULL
           and (due_at < period_end  OR  status_category = 'IN_PROGRESS')

④ 부하율 = ③ ÷ ② × 100

⑤ ② ≤ 0  →  부하율 NULL + 사유 (ON_LEAVE | NO_SCHEDULE | NO_EFFECTIVE_CAPACITY)
```

**부하율에 섞지 않고 옆에 따로 보여줄 값:**

```text
미일정 Backlog     마감 없고 미시작인 일의 잔여공수·건수
공수 미입력        remaining이 NULL이라 정량 합계에 못 넣은 건수
담당자 미매핑      assignee가 person_link에 없는 건수
```

숨기지 않되, 확인되지 않은 것을 퍼센트 안에 넣지 않는다.

## 3. 조사 문서에서 뒤집힌 결정

| 기존 | 확정 | 이유 |
|---|---|---|
| `× 0.8` 버퍼 | **없음.** 감산항을 0으로 두고 제한사항 노출 | 설계 4개 문서(기획서 v5 포함)가 쓰는 형태는 감산항이다. 버퍼의 근거였던 "두 출처 수렴"은 성립하지 않는다(구간 끝값이 맞닿은 것일 뿐, 두 출처는 기준점이 달라 독립이 아니다) |
| `COALESCE(wk_hours, def, 40) × fte` | `wk_hours` 우선 | `wk_hours`에 이미 FTE가 반영돼 있다. 실측 7명이 `20 / 40 / 0.5`이고 다시 곱하면 10시간이 된다. 개발팀 5명은 전원 `40/40/1.0`이라 **화면에 안 드러나는 조용한 버그**였다 |
| `COALESCE(…, 40)` | 없으면 `NO_SCHEDULE` | 40시간을 가정하면 근무조건을 모르는 사람이 풀타임으로 계산돼 한가해 보인다 |
| 기간 창 없음 | `[기준일, +4주)` | 분모는 주 단위, 분자는 총량이면 전원이 100%를 넘어 지표가 구분력을 잃는다 |
| 부재를 통째로 차감 | H로 **clip** | 육아휴직 214일을 그대로 빼면 −1552시간이 되고, 오름차순 정렬에서 휴직자가 "가장 여유 있는 사람"이 된다 |
| `due_at` NULL을 전부 포함 | 진행 중만 포함, 미시작은 Backlog로 분리 | "이미 하고 있는 일"과 "언젠가 할 일"을 같은 시간축에 합치면 과부하가 부풀려진다. Jira 자신도 기한 없는 일을 `Unscheduled work`로 분리한다 |
| `remaining` NULL을 중앙값으로 대체 | 대체하지 않고 건수 노출 | 없는 값을 지어내면 거짓 정밀도가 된다 |
| 비율(1 초과가 과부하) | **%** | `load_rate` 컬럼과 설계 문서가 %다 |
| 가상 마감일 생성 | 만들지 않음 | 실제 약속과 운영상 검토일은 다른 것이다 |

우선순위·난이도·업무유형 배수와 Weinberg 동시진행 손실률도 기본식에 넣지 않는다.
조직 실측이 쌓이면 버전된 정책으로 실험할 수 있지만, 지금은 정확한 퍼센트처럼
표시하지 않는다.

## 4. 데이터 계약

| 값 | 원천 | 비고 |
|---|---|---|
| `remaining` | Jira `timetracking.remainingEstimateSeconds ÷ 3600` | `Original Estimate × (1−진행률)`로 재구성하지 않는다. Jira는 작업 중 remaining을 독립적으로 조정한다 |
| `status_category` | Jira `statusCategory.key` → `TO_DO`/`IN_PROGRESS`/`DONE` | **`status.name`은 로직에 쓰지 않는다.** 실측에서 같은 카테고리가 KAN은 `'해야 할 일'`, AIP는 `'할 일'`로 왔고 `statusCategory.name`마저 지역화된다 |
| `due_at` | Jira `duedate` | 없으면 만들지 않는다 |
| 담당자 | `assignee.emailAddress` → `mock_hr.person_link` | 매핑 실패해도 행을 버리지 않고 건수를 센다 |
| 주 근무시간 | `mock_hr.sched` | 이력 테이블이라 기간에 유효한 행 1건만 고른다 |
| 부재 | `mock_hr.absence`, `status = 'APPROVED'` | 화이트리스트. 하루 연차는 `start_at = end_at`이라 날짜 단위로 읽는다 |
| 고정일정 | `cal_event` | 테이블은 있으나 채우는 경로와 `availability_impact` 단위 계약이 없다 → **0** |

## 5. 제한사항 (결과에 항상 함께 낸다)

- 공휴일 캘린더가 없어 **월~금**을 근무일로 본다
- 회의·돌발업무는 반영하지 않는다
- 기간별 공수 배분이 아니라 **보수적 근사**다 — 창에 걸리는 일의 `remaining` 전부가
  그 창에서 소비된다고 본다. Sprint·시작일·일별 배정이 생기면 겹침에 따라 나눠야 한다

## 6. 중간발표 이후로 미룬 것

- **결과 저장** — `workload_result.run_id`가 `assign_run` → `ana_snapshot` 체인을
  요구하는데 P6가 미착수다. 지금은 API 응답으로만 낸다
- **마감 위험 신호** — `SlackHours`, `RequiredPace`, `DeadlineDemandRate`. 부하율과
  분리된 보조 신호이고 저장할 컬럼도 없다
- **`review_by`** — 기한 없는 업무의 재검토 주기. 가상 마감일과 달리 "사람이 다시
  확인할 날짜"이고 부하율 계산에는 쓰지 않는다
- **`planning_end_at`** — Sprint·마일스톤 같은 합의된 계획 경계. 수집되면 `due_at`을
  덮어쓰지 않고 별도로 쓴다
- **`load_rate` 정밀도 확대** — 현재 최대가 122.5%라 999.99에 안 걸린다. 넘으면
  clamp하되 분자·분모가 같이 남아 원값을 복원할 수 있다
- **`due_at < 창끝`의 하한** — 한참 지난 연체를 통째로 넣을지. 목업 마감이
  `2026-08-07~08-28`이라 지금은 연체가 0건이다

## 7. 출처

확인일 2026-08-03. 전체 목록은 [[업무량계산_출처]]에 있고, 이 계약의 골격에 직접
쓰인 것만 옮긴다.

- Atlassian, *Jira Cloud REST API — Issue search* — `timetracking.*` 응답과 JQL 계약
  https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-search/
- Atlassian, *Schedule work in your calendar* — 기한 없는 업무를 `Unscheduled work`로
  분리하는 공식 동작
  https://support.atlassian.com/jira-software-cloud/docs/schedule-work-in-your-calendar/
- Microsoft, *View resource workloads and availability in Project desktop* —
  `Resource Availability = Resource Capacity − (Summary Resource Assignment + Calendar Exceptions)`
  https://support.microsoft.com/en-us/project/view-resource-workloads-and-availability-in-project-desktop
- NASA, *NASA Task Load Index (TLX)* — 주관적 workload가 다차원 평가 대상임
  https://www.nasa.gov/human-systems-integration-division/nasa-task-load-index-tlx/
- Hart, S. G. & Staveland, L. E. (1988), *Development of NASA-TLX*,
  Advances in Psychology 52, 139–183 — https://doi.org/10.1016/S0166-4115(08)62386-9
