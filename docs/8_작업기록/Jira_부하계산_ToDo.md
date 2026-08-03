# Jira 기존 업무 부하 계산 — To-Do

> 작성 2026-08-03 · 목표 시연 2026-08-06
> 목적: Jira 이슈 → `exist_task` → 부하율 → 화면까지 한 줄기를 세운다
> 근거: `업무량계산_조사_검증.md`(수식 검증), `DB/migrations/2026-08-03_exist_task_source.sql`(스키마)

## 지금 어디까지 됐나

> **2026-08-03 갱신 — 단계 1~3이 구현됐다.** 아래 "여기서 끊김"은 해소됐다.
> 실행 근거와 결정 사항은 [[2026-08-03_부하계산_작업지시서]]에 있다.

```
[완료] Jira OAuth 연결 · 프로젝트 목록 조회
[완료] 프로젝트 선택 → proj_source 저장              ← "설정 완료" 버튼이 하는 일
[완료] Jira 계정 ↔ person_id 매핑 (person_link)
[완료] 목업 이슈 (미완료 35건: KAN 23 + AIP 12)
[완료] exist_task 스키마 보강 (proj_source_id · estimate · status_category · UNIQUE)
[완료] 이슈 수집 코드      POST /api/projects/<id>/tasks/sync/      ← exist_task 35행
[완료] 부하 계산           services/workload/calculator.py
[완료] 화면 노출           /tasks/workload
```

실계정 검증(2026-08-03 ~ 08-31, 근무일 20일, 용량 160h):

| 담당자 | KAN | AIP | KAN만 | 합산 |
|---|---:|---:|---:|---:|
| 임준 | 144h | 52h | **90.0%** | **122.5%** |
| 김지훈 | 114h | 24h | 71.25% | 86.25% |
| 최원빈 | 86h | 16h | 53.75% | 63.75% |
| 성주연 | 50h | 12h | 31.25% | 38.75% |
| 임준억 | 42h | 8h | 26.25% | 31.25% |

미매핑 0 · 공수 미입력 3 · 미일정 Backlog 0h. 과부하는 임준 한 명이라 구분력도 산다.

---

## 단계 0 — 결정 ✅ 완료 (2026-08-03)

검증 결과 수식에 실행 규칙 여섯 개가 비어 있었다. 채우지 않으면 **57명 중 17명이 음수 부하율**을 받는 상태였다. 여섯 개 모두 확정했고 구현·테스트에 반영됐다.

- [x] **D1 기간 창** — `[기준일, 기준일+4주)`. 가용용량 = (주근무시간 ÷ 5) × 창 안의 근무일 수 − *창과 겹치는* 휴가
  - ~~`due_at`이 NULL인 이슈는 창에 포함~~ → **개정됨.** 마감이 없어도 **진행 중이면 포함**, 마감도 없고 시작도 안 했으면 **제외하고 미일정 Backlog로 분리**해 시간·건수를 따로 노출한다. 언젠가 할 일을 이번 4주에 합치면 과부하가 실제보다 커 보인다
  - ~~주근무시간 × 4 × FTE~~ → **FTE를 곱하지 않는다.** `wk_hours`에 이미 반영돼 있다(아래 단계 2-1 참조)
- [x] **D2 휴가 환산** — `absence` 구간을 창으로 clip → 근무일 수 × (주근무시간 ÷ 5). 하루 연차는 `start_at = end_at`이라 **날짜 단위로 읽어** 그날 전체를 차감한다
- [x] **D3 진행중 정의** — Jira `statusCategory.key`를 `TO_DO`/`IN_PROGRESS`/`DONE`으로 변환해 `exist_task.status_category`에 저장하고 **로직은 이 값만 본다.** 한글 표시 문자열을 조건에 쓰면 안 되는 이유가 실데이터로 확인됐다 — 같은 카테고리인데 KAN은 `'해야 할 일'`, AIP는 `'할 일'`로 온다
- [x] **D4 대상자** — `person.emp_status = 'ACTIVE'`만. 범위는 요청자의 팀(`team_member`)이다
- [x] **D5 휴가 필터** — `absence.status = 'APPROVED'` 화이트리스트 (블랙리스트면 반려·취소분이 차감된다)
- [x] **D6 가드·단위** — 가용용량 ≤ 0이면 부하율을 계산하지 않고 `NULL` + 사유(`ON_LEAVE`/`NO_SCHEDULE`/`NO_EFFECTIVE_CAPACITY`). 단위는 %, 999.99에서 clamp
  - **버퍼 `× 0.8`은 쓰지 않는다**(개정안). 설계 문서가 쓰는 형태는 감산항이고, 그 원천인 `cal_event`는 채우는 경로가 없어 0으로 두고 제한사항에 노출한다
  - 근무조건이 아예 없으면 40시간을 가정하지 않고 `NO_SCHEDULE`로 막는다

---

## 단계 1 — Jira 이슈 수집 (P0, 반나절)

**단계 0과 무관하게 지금 시작 가능.**

### 1-1. Jira 검색 클라이언트

- [ ] `apps/connectors/clients.py`에 `search_jira_issues(*, account_id, project_key)` 추가
  - `list_jira_projects()` 바로 아래, 같은 `credential_for` → `cloud_id` 패턴

**⚠️ 엔드포인트 주의 — 옛날 것은 이미 제거됐다.**

```
❌ GET  /rest/api/3/search            ← Jira Cloud에서 완전히 제거됨
✅ POST /rest/api/3/search/jql
```

페이지네이션도 `startAt` → **`nextPageToken`**으로 바뀌었다. `startAt`으로 짜면 조용히 첫 페이지만 돌아온다.

```python
POST https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3/search/jql
{
  "jql": f'project = "{project_key}" AND statusCategory != Done ORDER BY key',
  "fields": ["assignee", "status", "priority", "duedate", "timetracking", "created"],
  "maxResults": 100,
  "nextPageToken": <이전 응답의 값, 첫 호출은 생략>
}
```

- [ ] `nextPageToken`이 없을 때까지 반복. 37건이면 한 페이지지만 코드는 돌게
- [ ] 시간 필드는 **초 단위**로 온다 → `/3600` 해서 `NUMERIC(6,2)`
  - `timetracking.remainingEstimateSeconds` → `remaining`
  - `timetracking.originalEstimateSeconds` → `estimate`
  - `timetracking.timeSpentSeconds` → `spent`
- [ ] `start_at` — Jira 표준 이슈에 시작일 필드가 없다. `fields.created`로 대체하거나 NULL로 두고, 어느 쪽인지 주석에 남긴다
- [ ] 스코프는 `read:jira-work`로 충분. Board·Sprint API(`read:board-scope:jira-software`)는 필요 없다

### 1-2. 이메일 → person_id 매핑

- [ ] `assignee.emailAddress` → `mock_hr.person_link WHERE sys_type='JIRA' AND ext_email = ?`
- [ ] **매핑 실패해도 행을 버리지 않는다.** `assignee_person_id`를 NULL로 넣고 건수를 센다
  - 버리면 부하 총량이 조용히 줄어든다 — 틀린 숫자가 맞는 숫자처럼 보이는 최악의 형태
- [ ] `emailAddress` 자체가 응답에 없는 경우(프로필 비공개)도 같은 처리. 5명은 공개 설정을 켰지만 **되돌리면 조용히 깨진다**

### 1-3. Repository

- [ ] `backend/db/repositories.py`에 `ExistTaskRepository.replace_for_source(proj_source_id, rows)`
  - `ProjectSourceRepository.replace()`와 같은 **delete-then-insert**
  - `DELETE FROM exist_task WHERE proj_source_id = %s` → 08-03 ALTER 덕에 이제 범위가 특정된다
  - `exist_task_id`는 `next_short_code(table='exist_task', column='exist_task_id')`
  - Done으로 넘어간 이슈는 JQL에서 안 잡히므로 delete 단계에서 자연히 사라진다

### 1-4. 엔드포인트

- [ ] `POST /api/projects/<project_id>/tasks/sync/` — `ProjectTaskSyncAPIView`
  - 원문 다운로드(`ProjectDocumentDownloadAPIView`)와 같은 구조를 따른다
  - 그 프로젝트의 `proj_source WHERE source_type='JIRA_PROJECT'` 전부 순회
  - **부분 실패 허용** — 소스 하나가 실패해도 나머지는 반영
  - 응답에 진단값을 담는다:

    ```json
    {"sources": [{"proj_source_id": "S001", "project_key": "KAN", "fetched": 23}],
     "unmapped_assignees": 0, "missing_estimate": 3, "synced_at": "..."}
    ```

  - `unmapped_assignees`·`missing_estimate`가 Readiness의 PARTIAL_RESULT 입력이 된다

### 1-5. 호출 지점

- [ ] 온보딩 `설정 완료` 직후 프론트에서 1회 호출 (`JiraProjectSelectPage.tsx:114-122`)
- [ ] 추천 요청 경로에서도 같은 함수 호출 — 스냅샷을 얼리기 직전
  - 스냅샷 불변성은 "요청 시점 입력을 얼린다"는 뜻이라, 3일 전 값을 얼리면 요청 시점 상태가 아니다
  - 마지막 동기화가 N분 이내면 건너뛰기
  - Jira 장애 시엔 **BLOCKED가 아니라 PARTIAL_RESULT** — 마지막 동기화 시각을 근거에 박고 진행 여부는 PM이 판단

### 1-6. 테스트

- [ ] `tests/test_task_sync.py` — `test_document_download.py`(16개) 형식
  - `nextPageToken` 2페이지 이상
  - `emailAddress` 없는 담당자 → NULL + 카운트
  - `timetracking` 없는 이슈 → `remaining` NULL + 카운트
  - 재동기화 2회 → 건수가 안 늘어난다 (중복 방지 확인)
  - 소스 하나 실패해도 나머지 반영

---

## 단계 2 — 부하 계산 (P0, 반나절 · 단계 0 필요)

수식 자체는 `업무량계산_조사.md` Q4-2에 있다. **설계가 아니라 옮기는 작업이다.**

### 2-1. 가용용량

- [x] D1·D2·D4·D5를 반영 — `backend/services/hr/mock_db.py`의 `list_capacity_profiles()`·`list_absences()`가 조회하고, 환산은 `calculator.py`가 한다

> **⚠ 아래 SQL의 `* COALESCE(s.fte, 1)`은 틀렸다 (2026-08-03 정정).** `wk_hours`에는
> **이미 FTE가 반영돼 있다** — 시드 실측에서 `wk_hours 20 / def_wk_hours 40 / fte 0.5`인
> 직원이 7명이다. 다시 곱하면 20시간이 10시간으로 반토막 난다. 개발팀 5명은 전원
> `40/40/1.00`이라 **화면에는 안 드러나는 조용한 버그**였다.
>
> ```
> 올바른 순서:  wk_hours  →  없으면 def_wk_hours × fte  →  둘 다 없으면 BLOCKED
> ```

```sql
-- 기간: [:from, :to)
WITH target AS (
  SELECT p.person_id,
         COALESCE(s.wk_hours, s.def_wk_hours, 40) * COALESCE(s.fte, 1) AS wk   -- ← 틀림. 위 주의 참조
  FROM mock_hr.person p
  JOIN mock_hr.sched s ON s.person_id = p.person_id
   AND s.eff_from <= :to AND (s.eff_to IS NULL OR s.eff_to >= :from)   -- 행 1건 선택
  WHERE p.emp_status = 'ACTIVE'                                        -- D4
)
-- 휴가는 창으로 clip 후 근무일 환산 (D2)
-- absence.status = 'APPROVED' 만 (D5)
```

- [x] `sched`는 이력 테이블이라 기준일에 유효한 행 **1건**만 골라야 한다. 안 그러면 과거 근무조건이 섞인다 (`LATERAL … ORDER BY eff_from DESC LIMIT 1`)
- [x] `absence` 구간이 창을 넘어가는 경우 clip 필수 — **이게 음수의 원인이다.** 육아휴직은 `2026-06-01 ~ 12-31`(214일) **12명**이고, 4주 창을 통째로 덮어 용량 0 → `ON_LEAVE`가 된다
  > **2026-08-03 정정 — "17명"이 아니라 12명이다.** 17은 30일을 넘는 장기 부재 전체(육아휴직 12 + 안식월 5)이고, 그중 4주 창을 통째로 덮는 것은 육아휴직 12명이다.

### 2-2. 업무량

- [x] D1·D3 반영 — ~~창 안에 `due_at`이 있거나 `due_at`이 NULL인 `remaining` 합~~ → **개정됨:**

  ```
  포함 = due_at < 창끝  OR  status_category = 'IN_PROGRESS'
  제외 = 마감 없고 미시작  →  미일정 Backlog로 분리해 시간·건수 노출
  ```

  지난 마감도 포함한다(밀린 일은 지금 해야 한다). 마감 없는 일을 전부 넣던 원안은
  "이미 하고 있는 일"과 "언젠가 할 일"을 같은 시간축에 합쳐 과부하를 부풀렸다.
- [x] `assignee_person_id IS NULL`인 행은 개인 합계에서 빼되 **건수는 남겨 노출**
- [x] 같은 이슈가 두 `proj_source`로 들어온 경우 `jira_issue_id` 기준 중복 제거

### 2-3. calculator.py

- [ ] `services/workload/calculator.py` — 지금 docstring만 있는 스텁
  - 순수 함수로: 입력(기간, 대상자 목록) → 출력(person별 capacity/allocation/load_rate)
  - LLM 호출 없음. 결정론적 코드
- [ ] D6 가드: 가용용량 ≤ 0 → `load_rate = NULL` + 사유(`ON_LEAVE` / `NO_SCHEDULE`)
- [ ] 999.99 clamp

### 2-4. 저장

- [ ] `workload_result` (`run_id`, `person_id`, `effective_capacity`, `current_allocation`, `remaining_capacity`, `load_rate`)
- [ ] `ana_snapshot.snap_as_of`에 동기화 시각을 남겨 "언제 기준 숫자인지"를 근거로 보여줄 수 있게

### 2-5. 테스트

- [ ] **회귀 테스트 필수**: 육아휴직자(`PB005` 등 17명)가 음수·최상위 추천으로 안 나오는지
- [ ] 하루 연차(`start_at = end_at`)가 0시간이 아니라 8시간 차감되는지 (D2 확인)
- [ ] 가용용량 0일 때 ZeroDivision 안 나는지
- [ ] `load_rate` 1000% 이상에서 INSERT 실패 안 하는지

---

## 단계 3 — 노출 (P1, 2시간)

- [ ] `GET /api/projects/<id>/workload/?from=&to=` — 사람별 부하율 + 진단값
- [ ] 화면: 부하율 막대 + **프로젝트별 분해**(KAN 144h / AIP 52h)
  - 08-03 ALTER의 `proj_source_id`가 이 분해를 가능하게 한다
  - **"한 프로젝트만 보면 90%, 합치면 123%"가 시연의 핵심 장면**
- [ ] 미매핑 담당자·추정치 없는 건수를 화면에 노출 (숨기면 신뢰를 잃는다)

---

## 단계 4 — 목업 데이터 재조정 ❌ 폐기 (2026-08-03)

**이 작업은 하지 않는다.** 전제였던 `× 0.8` 버퍼가 개정안에서 빠지면서 4주 가용용량이
`128h`가 아니라 **`160h`**가 됐고, 그러면 **목업 원본이 그대로 목표 숫자를 낸다.**

```
버퍼 있음(128h):  임준 196h → 153%          ← 대비가 안 살아서 20% 하향이 필요했다
버퍼 없음(160h):  임준 144h/160 =  90.0%    ← KAN만
                       196h/160 = 122.5%    ← 합산.  바로 이 숫자다
```

거꾸로 **버퍼도 빼고 20% 하향도 하면** `156h/160 = 97.5%`로 100%를 못 넘어 시연의
핵심 장면이 죽는다. 둘 중 하나만 해야 하고, 개정안을 채택했으므로 하향은 안 한다.

<details>
<summary>폐기된 원안 (참고용)</summary>

D1을 4주로 잡으면 가용용량 = `40 × 4 × 0.8 = 128h`. 지금 추정치로는 임준 196h → 153%라 대비가 안 산다.

- Jira 37건 추정치를 **20% 하향**

| 담당자 | 현재 KAN/AIP | 조정 후 | 4주 128h 기준 |
|---|---|---|---|
| 임준 | 144 / 52 | 115 / 41 | KAN만 **90%** → 합산 **122%** |
| 김지훈 | 114 / 24 | 91 / 19 | 71% → 86% |
| 최원빈 | 86 / 16 | 69 / 13 | 54% → 64% |
| 성주연 | 50 / 12 | 40 / 10 | 31% → 39% |
| 임준억 | 42 / 8 | 34 / 6 | 27% → 31% |

</details>

---

## 단계 5 — 문서 정정 (P2)

- [x] `업무량계산_조사.md`에 D1~D6을 반영:
  - `cal_event`는 **있다**(07-31 추가). "테이블이 없다" → "채우는 경로가 없다"로 정정
  - Weinberg 확장형 `×(1+L)` → `÷(1−L)`
  - Gloria Mark 23분 등급을 [실측/공식] → [미검증]
  - `× 0.8` 근거를 "두 출처 수렴" → **철회**(기본식에서 제거). 조직이 원하면 버전된 정책값으로
  - Q4-2에 "구현은 이 수식이 아니다" 대조표 추가 — `× fte` 이중 적용·단위·기간 창 포함
- [ ] `중간발표_개요.md` 9장 — 파싱까지 붙은 뒤 한 번에

---

## 순서와 병렬

```
✅ 단계 0 (결정) ─→ ✅ 단계 1 (수집) ─→ ✅ 단계 2 (계산) ─→ ✅ 단계 3 (화면)
                                                            ❌ 단계 4 (폐기)
```

원래는 단계 1을 결정과 병렬로 돌릴 계획이었고 실제로 그렇게 했다. 단계 4는 `× 0.8`이
빠지면서 필요가 없어졌다.

## 8/6 최소선 ✅ 달성 (2026-08-03)

이 셋만 되면 파싱이 늦어져도 보여줄 게 있다.

1. [x] `POST /tasks/sync/`로 미완료 **35건**이 `exist_task`에 들어온다 (재동기화해도 안 늘어남)
2. [x] 부하율이 계산되고 육아휴직자가 음수로 안 나온다 (용량 0 → `ON_LEAVE`, 부하율 `NULL`)
3. [x] 화면에 "KAN만 90.0% → 합산 122.5%"가 보인다 (`/tasks/workload`)

문서 파싱과 **완전히 독립**이라 최원빈 일정에 안 물린다.

## 남은 것

- **결과 저장** — `workload_result`에 넣으려면 `run_id` → `assign_run` → `ana_snapshot`
  체인이 필요한데 전부 0행이다(P6 Snapshot 미착수). 지금은 계산 결과를 API 응답으로만
  낸다
- **`due_at < 창끝`의 하한** — 한참 지난 연체 이슈를 분자에 통째로 넣을지. 목업 마감이
  `2026-08-07~08-28`이라 8/6에는 연체가 0건이라 걸리지 않는다
- **개정안 §9·§10** — 마감 위험 신호(`SlackHours`·`RequiredPace`)와 재검토 주기
  (`review_by`). 중간발표 이후
- **`proj_source.sync_status`** — 동기화 후에도 `PENDING`인 채다. 읽는 곳이 없어 두었다
