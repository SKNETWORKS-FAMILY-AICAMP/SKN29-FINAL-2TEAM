# Jira 기존 업무 부하 계산 — To-Do

> 작성 2026-08-03 · 목표 시연 2026-08-06
> 목적: Jira 이슈 → `exist_task` → 부하율 → 화면까지 한 줄기를 세운다
> 근거: `업무량계산_조사_검증.md`(수식 검증), `DB/migrations/2026-08-03_exist_task_source.sql`(스키마)

## 지금 어디까지 됐나

```
[완료] Jira OAuth 연결 · 프로젝트 목록 조회
[완료] 프로젝트 선택 → proj_source 저장              ← "설정 완료" 버튼이 하는 일
[완료] Jira 계정 ↔ person_id 매핑 (person_link, 5명)
[완료] 목업 이슈 37건 (KAN 25 + AIP 12, 라벨 mock-workload)
[완료] exist_task 스키마 보강 (proj_source_id · estimate · UNIQUE)
──────────────────────── 여기서 끊김 ────────────────────────
[없음] 이슈 수집 코드                                 ← exist_task 0행
[없음] 부하 계산                                      ← calculator.py 스텁
[없음] 화면 노출
```

`exist_task`가 0인 건 데이터가 안 들어온 게 아니라 **넣는 코드가 없어서**다.

---

## 단계 0 — 결정 (사람, 30분)

**단계 2를 막는다. 단계 1은 이거 없이도 시작할 수 있다.**

검증 결과 수식에 실행 규칙 여섯 개가 비어 있다. 채우지 않으면 57명 중 17명이 음수 부하율을 받는다.

- [ ] **D1 기간 창** — `[기준일, 기준일+4주)`. 가용용량 = 주근무시간 × 4 × FTE − *창과 겹치는* 휴가. 업무량 = 창 안에 `due_at`이 있는 `remaining` 합
  - `due_at`이 NULL인 이슈는 **창에 포함**(제외하면 부하 총량이 조용히 줄어든다). 건수는 따로 세서 노출
- [ ] **D2 휴가 환산** — `absence` 구간을 창으로 clip → 근무일 수 × (주근무시간 ÷ 5). `sched.tz` 기준
- [ ] **D3 진행중 정의** — `'진행 중'`·`'검토 중'` 둘 다 포함. **상태 한글 문자열을 코드에 박지 말고** Jira `statusCategory != Done` 기준으로 수집 단계에서 거른다
- [ ] **D4 대상자** — `person.emp_status = 'ACTIVE'`만. `backend/services/hr/mock_db.py`가 이미 쓰는 기준
- [ ] **D5 휴가 필터** — `absence.status = 'APPROVED'` 화이트리스트 (블랙리스트면 반려·취소분이 차감된다)
- [ ] **D6 가드·단위** — 가용용량 ≤ 0이면 부하율을 계산하지 않고 `NULL` + 사유 코드. 단위는 %, `load_rate NUMERIC(5,2)` 상한 999.99에서 clamp

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

- [ ] D1·D2·D4·D5를 반영한 SQL

```sql
-- 기간: [:from, :to)
WITH target AS (
  SELECT p.person_id,
         COALESCE(s.wk_hours, s.def_wk_hours, 40) * COALESCE(s.fte, 1) AS wk
  FROM mock_hr.person p
  JOIN mock_hr.sched s ON s.person_id = p.person_id
   AND s.eff_from <= :to AND (s.eff_to IS NULL OR s.eff_to >= :from)   -- 행 1건 선택
  WHERE p.emp_status = 'ACTIVE'                                        -- D4
)
-- 휴가는 창으로 clip 후 근무일 환산 (D2)
-- absence.status = 'APPROVED' 만 (D5)
```

- [ ] `sched`는 이력 테이블이라 기준일에 유효한 행 **1건**만 골라야 한다. 안 그러면 과거 근무조건이 섞인다
- [ ] `absence` 구간이 창을 넘어가는 경우(육아휴직 213일) clip 필수 — **이게 음수 17명의 원인**

### 2-2. 업무량

- [ ] D1·D3 반영: 창 안에 `due_at`이 있거나 `due_at`이 NULL인 `remaining` 합
- [ ] `assignee_person_id IS NULL`인 행은 개인 합계에서 빼되 **건수는 남겨 노출**
- [ ] 같은 이슈가 두 `proj_source`로 들어온 경우 `jira_issue_id` 기준 중복 제거

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

## 단계 4 — 목업 데이터 재조정 (P1, 30분)

D1을 4주로 잡으면 가용용량 = `40 × 4 × 0.8 = 128h`. 지금 추정치로는 임준 196h → 153%라 대비가 안 산다.

- [ ] Jira 37건 추정치를 **20% 하향**

| 담당자 | 현재 KAN/AIP | 조정 후 | 4주 128h 기준 |
|---|---|---|---|
| 임준 | 144 / 52 | 115 / 41 | KAN만 **90%** → 합산 **122%** |
| 김지훈 | 114 / 24 | 91 / 19 | 71% → 86% |
| 최원빈 | 86 / 16 | 69 / 13 | 54% → 64% |
| 성주연 | 50 / 12 | 40 / 10 | 31% → 39% |
| 임준억 | 42 / 8 | 34 / 6 | 27% → 31% |

- [ ] 재조정 후 `POST .../tasks/sync/` 다시 돌려 DB 반영

---

## 단계 5 — 문서 정정 (P2)

- [ ] `업무량계산_조사.md`에 D1~D6을 반영. 특히:
  - `cal_event`는 **있다**(07-31 추가). "테이블이 없다" → "채우는 경로가 없다"로 정정
  - Weinberg 확장형 `×(1+L)` → `÷(1−L)`
  - Gloria Mark 23분 등급을 [실측/공식] → [미검증]
  - Tempo Capacity에서 Planned Time 감산 제거 (`출처.md`가 맞다)
  - `× 0.8` 근거를 "두 출처 수렴" → "Actonic 15~20%의 보수적 끝값, [정책값]"
- [ ] `중간발표_개요.md` 9장 — 파싱까지 붙은 뒤 한 번에

---

## 순서와 병렬

```
지금 ─┬─ 단계 1 (수집)  ────────────┐
      └─ 단계 0 (결정, 30분) ─→ 단계 2 (계산) ─┴─→ 단계 3 (화면) → 단계 4 (재조정)
```

- 단계 1은 결정을 안 기다린다. 수집은 D1~D6과 무관
- 단계 2는 단계 0·1이 둘 다 끝나야 시작
- **단계 4는 단계 2가 돌아간 뒤에** — 숫자를 보고 맞춰야 하므로

## 8/6 최소선

이 셋만 되면 파싱이 늦어져도 보여줄 게 있다.

1. `POST /tasks/sync/`로 37건이 `exist_task`에 들어온다
2. 부하율이 계산되고 육아휴직자가 음수로 안 나온다
3. 화면에 "KAN만 90% → 합산 122%"가 보인다

문서 파싱과 **완전히 독립**이라 최원빈 일정에 안 물린다.
