# Page 3-A·3-B 문서 저장 스키마 상세 설명 — 테이블 · 연결관계 · 필드

> 대상: Figma `Page 3-A | pgvector 검색 인덱스`와 `Page 3-B | 프로젝트 분석·추천 RDBMS`의 문서·지식 모델 영역
> 이 문서는 Figma에 실제로 반영된 **최종 스키마**를 그대로 기준으로 작성했다. `VectorDB_저장대상_검증.md`는 "GPT 피드백에 대한 판단 근거"를 남긴 별도 문서이고, 이 문서는 그 판단이 끝난 뒤의 **결과물(스키마 자체)을 읽는 용도**다.
> 작성일: 2026-07-28

---

## 0. 이 파이프라인이 하는 일

문서 1건이 들어오면 아래 순서로 데이터가 쌓인다.

```
DOC(문서 원본 메타)
 └─ DOC_BLOCK(문서를 헤딩·표·문단 단위로 자른 것)
     └─ CHUNK(BLOCK을 검색 가능한 크기로 다시 쪼갠 것)
         └─ VEC_IDX(CHUNK를 임베딩해서 Vector DB에 넣은 것)
 └─ DOC_SYNC(이 문서가 지금 어디까지 처리됐는지 상태값)

KNOW_ITEM(문서에서 뽑아낸 "지식 한 조각": 일정, 담당자, 요구사항 등)
 └─ KNOW_ITEM_SRC(그 지식이 문서의 어느 블록/청크/인용문에서 나왔는지 근거)

PROJ_KNOW_MODEL(한 프로젝트의 지식 전체를 모아 만든 버전 스냅샷 = "지식 모델")
 ├─ MODEL_KNOW_ITEM(이 모델에 어떤 지식 항목들이 포함됐는지)
 ├─ FEAT_CLUSTER(지식 항목들을 기능 단위로 묶은 것) → FEAT_CLUSTER_ITEM
 ├─ TASK(지식 모델에서 도출된 신규 업무) → TASK_KNOW_SRC(그 업무가 어떤 지식에서 나왔는지 근거)
 └─ ANA_SNAPSHOT(특정 시점에 이 모델로 어떤 분석을 돌렸는지 기록)
```

한 줄로 요약하면: **3-B PostgreSQL RDBMS가 진짜 데이터(문서·지식·업무)를 갖고 있고, 3-A pgvector의 `VEC_IDX`는 그중 CHUNK 텍스트를 검색하기 위한 보조 인덱스일 뿐**이다. 초기 구현에서는 둘 다 같은 PostgreSQL 인스턴스에 저장한다.

---

## 1. 전체 연결관계 (15개)

| SOURCE | 관계 | TARGET | 연결 키 |
|---|---|---|---|
| TEAM | 1:N | DOC | `DOC.team_id` — 문서는 팀에 매달린다(2026-08-04) |
| PROJ | 1:0..1 | DOC | `DOC.proj_id` + `doc_role='PRIMARY'`. 기준 문서 1건만 프로젝트에 묶인다(부분 유니크 인덱스) |
| PROJ | 1:N | KNOW_ITEM | `KNOW_ITEM.proj_id` |
| PROJ | 1:N | PROJ_KNOW_MODEL | `PROJ_KNOW_MODEL.proj_id` |
| DOC | 1:N | DOC_BLOCK | `DOC_BLOCK.doc_id` |
| DOC | 1:1 | DOC_SYNC | `DOC_SYNC.doc_id` |
| DOC_BLOCK | 1:N | CHUNK | `CHUNK.block_id` |
| CHUNK | 1:1 | VEC_IDX | `VEC_IDX.chunk_id` |
| DOC_BLOCK | N:M | KNOW_ITEM | 연결 테이블 `KNOW_ITEM_SRC` |
| PROJ_KNOW_MODEL | N:M | KNOW_ITEM | 연결 테이블 `MODEL_KNOW_ITEM` |
| PROJ_KNOW_MODEL | 1:N | FEAT_CLUSTER | `FEAT_CLUSTER.model_id` |
| FEAT_CLUSTER | N:M | KNOW_ITEM | 연결 테이블 `FEAT_CLUSTER_ITEM` |
| PROJ_KNOW_MODEL | 1:N | TASK | `TASK.model_id` |
| TASK | N:M | KNOW_ITEM | 연결 테이블 `TASK_KNOW_SRC` |
| PROJ_KNOW_MODEL | 1:N | ANA_SNAPSHOT | `ANA_SNAPSHOT.model_id` |

`KNOW_ITEM`이 허브 역할을 한다는 게 핵심이다 — 문서에서 나온 근거(`KNOW_ITEM_SRC`), 그 지식이 속한 지식모델(`MODEL_KNOW_ITEM`), 기능 클러스터(`FEAT_CLUSTER_ITEM`), 파생된 업무(`TASK_KNOW_SRC`)가 전부 `KNOW_ITEM`을 통해 서로 연결된다. 즉 "이 Task가 왜 생겼는지"를 추적하면 `TASK → TASK_KNOW_SRC → KNOW_ITEM → KNOW_ITEM_SRC → DOC_BLOCK/CHUNK → 원문`까지 한 번에 거슬러 올라갈 수 있다.

---

## 2. 테이블별 상세

> **타입 표기 주의.** 아래 표의 `UUID`·`BIGINT`는 논리 표기다. `DB/schema.sql`의 실제 PK는 거의 전부
> `VARCHAR(5)` 짧은 코드(`PJ001`·`DC001`…)이고, UUID를 쓰는 것은 `DOC_BLOCK`·`CHUNK`·`VEC_IDX` 세 개뿐이다.
> 물리 타입의 정본은 `DB/schema.sql`이다.

### Depth 1 — 프로젝트

#### `PROJ` (프로젝트)
프로젝트 자체의 기준 정보이자 플랫폼의 분석 작업공간.

| 필드 | 한글명 | 타입 | 저장 내용 | 저장 방식 | 사용처 |
|---|---|---|---|---|---|
| `proj_id` (PK) | 프로젝트 ID | VARCHAR(5) | 프로젝트 고유 식별자 | 짧은 코드 `PJ001`…(외부 시스템 ID와 분리 — CDM 원칙) | 다른 모든 테이블의 프로젝트 범위 필터 기준 |
| `name` | 이름 | VARCHAR | 프로젝트명 | 사용자 입력 문자열 | 화면 표시, 검색 |
| `status` | 상태 | VARCHAR | 진행중/종료 등 프로젝트 상태 | 코드값(예: `ACTIVE`/`ARCHIVED`) | 목록 필터링, 종료 프로젝트 처리 제외 |
| `tz` | 시간대 | VARCHAR | 프로젝트 기준 시간대 | IANA 타임존 문자열(예: `Asia/Seoul`) | `TASK.start_at/due_at` 등 시각 필드를 사용자 로컬로 환산할 때 기준값 |
| `owner_account_id` (FK) | 프로젝트 소유자 계정 ID | VARCHAR(5) | 프로젝트를 생성·관리하는 PM 계정 | `user_account.account_id` 참조(FK 없음). **Django ORM을 쓰지 않으므로 `AUTH_USER_MODEL`과 무관하다** | 프로젝트 소유권 표시. 접근 판정은 소유자가 아니라 팀 검사가 한다 |
| `team_id` (FK) | 팀 ID | VARCHAR(5) | 이 프로젝트를 하는 팀(2026-08-04 추가) | `team.team_id` 참조(FK 없음) | 테넌트 경계. 소유 계정만으로는 팀원이 팀의 프로젝트를 볼 수 없다 |
| `created_at` | 생성 시각 | TIMESTAMPTZ | 프로젝트를 만든 시각(2026-08-04 추가) | `DEFAULT now()` | 목록의 "최신순" 정렬과 날짜 표시. 이 컬럼 이전 행은 NULL이고 화면이 `-`로 보여준다 |

---

### Depth 2 — 원천 · 지식 · 모델

#### `DOC` (문서)
업로드된 원본 문서 1건에 대한 메타데이터. 파일 자체(바이트)는 Object Storage에 있고, 이 테이블은 그 파일을 가리키는 포인터 + 접근·상태 정보만 갖는다.

연결: **`TEAM`에 소속(N:1)** — 등록 시점에는 팀 문서 풀에 들어간다(2026-08-04). `PROJ`에는 기준 문서로 지정될 때만 묶이고 그때 프로젝트당 1건이다. `DOC_BLOCK` 여러 개를 가짐(1:N), `DOC_SYNC`와 1:1.

| 필드 | 한글명 | 타입 | 저장 내용 | 저장 방식 | 사용처 |
|---|---|---|---|---|---|
| `doc_id` (PK) | 문서 ID | VARCHAR(5) | 문서 고유 식별자(내부 ID) | 짧은 코드 `DC001`… | 이하 모든 문서 하위 테이블(BLOCK/SYNC 등)의 FK 기준 |
| `team_id` (FK) | 팀 ID | VARCHAR(5) | **이 문서를 등록한 팀**(2026-08-04 추가). 문서는 팀의 Drive 폴더에서 나오므로 등록 시점에는 팀에만 속한다 | `team.team_id` 참조(FK 없음) | **문서 조회의 실제 범위 기준** — 모든 문서 쿼리가 `WHERE team_id = ?`로 좁힌다 |
| `proj_id` (FK) | 프로젝트 ID | VARCHAR(5) | 어느 프로젝트의 문서인가. **등록 시점에는 모른다**(2026-08-04 NULL 허용) | `PROJ.proj_id` 참조. 기준 문서로 지정될 때만 채워진다 | 프로젝트 → 기준 문서 역추적 |
| `src_file_id` | 원본 파일 ID | VARCHAR | Google Drive 등 외부 소스의 파일 ID | 외부 시스템 원본 ID 그대로 저장 | 원본 파일 재조회, 변경 감지(Drive webhook과 매칭) — `doc_id`와 분리해 저장하는 이유는 외부 ID가 바뀌어도 내부 참조가 깨지지 않게 하기 위함(CDM 원칙) |
| `cur_revision` | 현재 리비전 | VARCHAR | 이 문서의 최신 리비전 값(예: Drive의 revisionId 또는 자체 증가값) | 문자열/버전 토큰 | `DOC_BLOCK.revision`, `DOC_SYNC.revision`과 비교해서 "이 블록이 최신 버전인지" 판단하는 기준점 |
| `content_hash` | 내용 해시 | VARCHAR | 문서 원본 내용의 해시값 | SHA-256 등 | 재처리 필요 여부 판단(해시가 같으면 재파싱 스킵) |
| `storage_key` | 저장소 키 | VARCHAR(255) | 내려받은 원문이 문서 저장소 어디에 있는가(2026-07-31 추가) | 파일 경로가 아니라 저장소 안에서의 키 — 지금은 로컬 디스크지만 S3로 바뀌어도 값이 그대로 쓰인다. 아직 안 받았으면 NULL | RunPod에 넘길 만료형 서명 URL 생성, 원문 재조회 |
| `security` | 보안 등급 | VARCHAR | 문서 보안 등급(대외비/일반 등) | 코드값 | 접근 제어, 화면 표시 시 워터마크/마스킹 여부 결정 |
| `source_type` | 원천 유형 | VARCHAR | 문서가 유입된 외부 소스 | `DRIVE`/`JIRA` — `schema.sql`과 구현이 쓰는 값이다(이 표의 앞선 `GOOGLE_DRIVE` 표기는 오기였다) | Connector·파서 라우팅과 출처 표시 |
| `file_name` | 파일명 | VARCHAR | 원본 파일명 | 문자열 | 화면 표시, Citation에 "출처: OOO.pdf" 표기 |
| `mime_type` | 형식 | VARCHAR | 파일 MIME 타입 | 예: `application/pdf`, `application/vnd.google-apps.document` | 어떤 파서를 태울지 라우팅 |
| `doc_role` | 프로젝트와의 관계 | VARCHAR | 이 문서가 `proj_id` 프로젝트에서 맡는 자리 | `NULL`(팀 문서 풀) / `PRIMARY`(기준 문서, 프로젝트당 하나) — **2026-08-04 의미 변경**. 예전에는 문서의 종류(`PLAN`/`MEETING_NOTE`/`DAILY_REPORT`/`OTHER`)였는데, 폴더에 준 역할을 안의 파일이 물려받아 「01_기획」에 든 것은 무엇이든 기획서가 됐고 정작 그 값으로 분기하는 코드는 없었다. `SUB`는 스키마에 남아 있지만 쓰지 않는다 — 같은 회의록이 여러 프로젝트의 근거일 수 있는데 `proj_id`는 하나만 가리킨다 | 기준 문서 식별. 프로젝트당 `PRIMARY` 하나를 부분 유니크 인덱스로 강제 |
| `acl_principals` | 접근 권한 | ARRAY | 이 문서를 볼 수 있는 사용자/그룹 목록 | 문자열 배열(사용자ID 또는 그룹ID 나열) | 검색 결과·Citation 노출 전 접근 권한 필터링 |
| `src_modified_at` | 원본 수정 시각 | TIMESTAMP | 원본 소스(Drive 등)에서 마지막으로 수정된 시각 | ISO 8601 timestamp | 동기화 주기 판단(원본이 로컬 캐시보다 최신이면 재동기화) |
| `deleted` | 삭제 여부 | BOOLEAN | 원본이 삭제됐는지 | true/false | 삭제된 문서를 검색·Citation에서 제외 |
| `access_revoked` | 접근 취소 여부 | BOOLEAN | 원본에 대한 접근 권한이 회수됐는지(공유 해제 등) | true/false | 권한이 사라진 문서를 검색·Citation에서 즉시 제외(내용은 남아있어도 노출 차단) |

#### `KNOW_ITEM` (프로젝트 지식 항목)
문서에서 추출된 "의미 있는 지식 한 조각". 예: "8월 6일까지 데모 완료", "담당자는 김OO". Chunk(텍스트 조각)와 다르게, 이건 이미 의미 단위로 정제된 결과물이다.

연결: `PROJ`에 소속. `KNOW_ITEM_SRC`로 원문 근거 연결, `MODEL_KNOW_ITEM`으로 지식모델 소속, `FEAT_CLUSTER_ITEM`으로 기능 클러스터 소속, `TASK_KNOW_SRC`로 파생 Task 연결.

| 필드 | 한글명 | 타입 | 저장 내용 | 저장 방식 | 사용처 |
|---|---|---|---|---|---|
| `know_item_id` (PK) | 지식 항목 ID | UUID | 지식 항목 고유 식별자 | 내부 생성 UUID | 근거/모델/클러스터/Task 연결의 허브 키 |
| `proj_id` (FK) | 프로젝트 ID | UUID | 소속 프로젝트 | `PROJ.proj_id` 참조 | 프로젝트별 지식 항목 조회 |
| `semantic_type` | 의미 유형 | VARCHAR | 이 지식이 일정/담당자/요구사항/리스크 중 무엇인지 | 코드값(`SCHEDULE`/`OWNER`/`REQUIREMENT`/`RISK` 등) | 지식모델 구성 시 유형별 분류, `CHUNK`와 JOIN해서 "업무 관련 Chunk만" 필터링할 때의 기준값(1장 참고) |
| `title` | 제목 | VARCHAR | 지식 항목을 한 줄로 요약한 제목 | 문자열 | 목록·카드 UI 표시 |
| `content` | 내용 | TEXT | 지식 항목의 실제 내용(정제된 문장) | 자유 텍스트 | 지식모델 생성, Task 추출 Agent의 입력 |
| `confidence` | 신뢰도 | DECIMAL | 이 지식 추출이 얼마나 확실한지 | 0.0~1.0 | 낮은 신뢰도 항목을 사용자 검토 대상으로 표시 |

#### `PROJ_KNOW_MODEL` (프로젝트 지식모델)
한 시점에 프로젝트의 지식 항목들을 모아 만든 "지식모델" 버전. 문서가 업데이트되거나 재분석을 돌릴 때마다 새 버전이 생길 수 있다.

연결: `PROJ`에 소속. `MODEL_KNOW_ITEM`/`FEAT_CLUSTER`/`TASK`/`ANA_SNAPSHOT`을 각각 1:N 또는 N:M으로 거느리는 상위 허브.

| 필드 | 한글명 | 타입 | 저장 내용 | 저장 방식 | 사용처 |
|---|---|---|---|---|---|
| `model_id` (PK) | 지식 모델 ID | UUID | 지식모델 버전 고유 식별자 | 내부 생성 UUID | 하위(클러스터/Task/스냅샷) 테이블의 FK 기준 |
| `proj_id` (FK) | 프로젝트 ID | UUID | 소속 프로젝트 | `PROJ.proj_id` 참조 | 프로젝트별 지식모델 이력 조회 |
| `model_ver` | 모델 버전 | VARCHAR | 몇 번째 생성 버전인지 | 증가하는 버전 문자열(예: `v3`) | 이전 버전과 비교, 최신 버전 판별 |
| `status` | 상태 | VARCHAR | 생성중/완료/실패 | 코드값 | 생성 진행 UI 표시, 실패 시 재시도 트리거 |
| `generated_at` | 생성 시각 | TIMESTAMP | 이 버전이 생성된 시각 | ISO 8601 timestamp | 최신 버전 정렬, `ANA_SNAPSHOT`과의 시점 매칭 |
| `conflict_summary` | 충돌 요약 | JSONB | 지식 항목 간 상충되는 내용이 있었는지 요약 | 예: `{"conflicts":[{"itemA":"...","itemB":"...","reason":"일정 불일치"}]}` | 사용자에게 "확인이 필요한 충돌"을 알려주는 검토 화면 |

---

### Depth 3 — 파싱 · 연결 · 생성

#### `DOC_BLOCK` (문서 블록)
문서를 파싱해서 헤딩/문단/표 단위로 잘라낸 조각. Chunk보다 상위 단위이며, "문서 구조"를 그대로 보존하는 역할을 한다.

연결: `DOC`에 소속(1:N). `CHUNK`를 1:N으로 거느림. `KNOW_ITEM_SRC`를 통해 `KNOW_ITEM`과 N:M으로 연결(어떤 지식이 어느 블록에서 나왔는지).

| 필드 | 한글명 | 타입 | 저장 내용 | 저장 방식 | 사용처 |
|---|---|---|---|---|---|
| `block_id` (PK) | 문서 블록 ID | UUID | 블록 고유 식별자 | 내부 생성 UUID | `CHUNK`, `KNOW_ITEM_SRC`의 FK 기준 |
| `doc_id` (FK) | 문서 ID | UUID | 소속 문서 | `DOC.doc_id` 참조 | 문서별 블록 목록 조회 |
| `block_type` | 블록 유형 | VARCHAR | 헤딩/문단/표/리스트 중 무엇인지 | 코드값(`HEADING`/`PARAGRAPH`/`TABLE`/`LIST`) | 렌더링 방식 결정, `struct_content` 파싱 여부 분기 |
| `page` | 페이지 | INT | 원본 문서에서 몇 페이지에 있었는지 | 정수 | Citation에 "OOO.pdf 3페이지" 같은 위치 표시 |
| `heading_path` | 제목 경로 | ARRAY | 이 블록이 속한 상위 제목들의 경로 | 문자열 배열(예: `["2장 일정","2.1 마일스톤"]`) | 검색 결과에 문맥(어느 섹션인지) 표시, `heading_level`을 별도 저장하지 않고 이 배열 길이로 계산 |
| `content` | 내용 | TEXT | 블록의 원문 텍스트 | 자유 텍스트 | 청킹(CHUNK 생성)의 입력, 재파싱 시 원본 |
| `sequence` | 읽기 순서 | INT | 문서 내에서 이 블록이 몇 번째인지 | 정수(0부터 증가) | 블록을 원문 순서대로 재구성할 때 정렬 기준 |
| `revision` | 리비전 | VARCHAR | 이 블록이 생성된 시점의 문서 리비전 값 | `DOC.cur_revision`과 같은 포맷의 문자열 | 이 블록이 최신인지 판별(`revision == DOC.cur_revision`이면 활성, 다르면 과거 리비전 — 별도 `is_active` 컬럼 없이 비교로 계산) |
| `src_locator` | 원본 위치 | JSONB | 원본 파일 내 정확한 위치 정보 | 예: `{"tableIndex":1,"rowStart":3,"rowEnd":5}` | 표 안의 특정 셀/행까지 정확히 되짚어가는 Citation, `parent_block_id`(상위 블록) 정보도 이 안에 포함해 별도 컬럼 없이 대체 |
| `struct_content` | 구조화 내용(표) | JSONB | 표의 경우 헤더/행을 구조화된 형태로 저장 | 예: `{"headers":["담당자","마감일"],"rows":[["김OO","8/6"]]}` | 일정표·담당자표처럼 "표 안의 데이터 자체"가 제품의 핵심 산출물인 경우, 표를 텍스트로 뭉개지 않고 구조 그대로 재사용(Task 추출 Agent가 직접 이 필드를 읽음) |

#### `CHUNK` (검색용 하위 청크)
`DOC_BLOCK`을 임베딩에 적합한 크기로 다시 잘게 쪼갠 것. Vector DB에 넣기 직전 단계의 텍스트 단위이며, **업무 의미(담당자·마감일 등)는 담지 않는다** — 그건 `KNOW_ITEM`의 역할.

연결: `DOC_BLOCK`에 소속(N:1). `VEC_IDX`와 1:1.

| 필드 | 한글명 | 타입 | 저장 내용 | 저장 방식 | 사용처 |
|---|---|---|---|---|---|
| `chunk_id` (PK) | 청크 ID | UUID | 청크 고유 식별자 | 내부 생성 UUID | `VEC_IDX.chunk_id`의 참조 대상 |
| `block_id` (FK) | 문서 블록 ID | UUID | 원본 블록 | `DOC_BLOCK.block_id` 참조 | 청크가 어느 블록에서 나왔는지, 블록의 `heading_path`/`page` 등 문맥 정보를 JOIN으로 가져올 때 |
| `up_chunk_id` | 상위 청크 ID | UUID | 계층적 청킹 시 상위 청크(있는 경우만) | 자기 참조 FK, nullable | 계층형 검색(상위 요약 → 하위 세부) 전략을 쓸 경우의 트리 구조 |
| `search_text` | 검색용 텍스트 | TEXT | 실제로 임베딩할 텍스트(전처리 완료본) | 자유 텍스트 | 임베딩 생성 입력, 검색 결과 미리보기 |
| `is_active` | 활성 여부 | BOOLEAN | 이 청크가 현재 유효한지 | true/false | 오래된 리비전의 청크를 검색 대상에서 제외 |
| `chunk_idx` | 청크 순서 | INT | 같은 블록 안에서 몇 번째 청크인지 | 정수 | 청크들을 원문 순서로 재조합 |
| `token_cnt` | 토큰 수 | INT | 청크의 토큰 개수 | 정수 | 임베딩 모델의 토큰 제한 검증, 청킹 품질 모니터링 |
| `heading_path` | 제목 경로 | ARRAY | 상위 블록의 `heading_path`를 그대로 상속 | 문자열 배열 | JOIN 없이 검색 결과에 바로 문맥 표시(조회 성능을 위한 의도적 비정규화) |
| `chunker_ver` | 청커 버전 | VARCHAR | 어떤 버전의 청킹 로직으로 만들어졌는지 | 버전 문자열 | 청킹 알고리즘이 바뀌었을 때 재청킹 대상 판별 |

#### `DOC_SYNC` (문서 동기화 · 처리 상태)
문서 하나가 지금 어느 단계까지 처리됐는지(동기화 → 파싱 → 임베딩)를 추적하는 상태 테이블. 별도의 "ParsedDocument"나 "DocumentIndex" 테이블을 만들지 않고, 이 테이블 하나에 처리 상태를 전부 흡수했다.

연결: `DOC`와 1:1.

| 필드 | 한글명 | 타입 | 저장 내용 | 저장 방식 | 사용처 |
|---|---|---|---|---|---|
| `sync_id` (PK) | 동기화 상태 ID | UUID | 상태 레코드 고유 식별자 | 내부 생성 UUID | — |
| `doc_id` (FK) | 문서 ID | UUID | 대상 문서 | `DOC.doc_id` 참조, 1:1 | 문서별 처리 상태 조회 |
| `chg_type` | 변경 유형 | VARCHAR | 신규/수정/삭제 중 어떤 변경이 감지됐는지 | 코드값(`CREATED`/`UPDATED`/`DELETED`) | 파이프라인 분기(신규면 전체 파싱, 수정이면 diff 파싱) |
| `sync_status` | 동기화 상태 | VARCHAR | 원본 소스와의 동기화 진행 상태 | 코드값(`PENDING`/`IN_PROGRESS`/`DONE`/`FAILED`) | 동기화 큐 처리, 실패 시 재시도 대상 조회 |
| `ckpt_token` | 체크포인트 토큰 | TEXT | 증분 동기화를 재개할 지점 | 외부 API(Drive 등)가 발급한 토큰 문자열 | 동기화 중단 후 재시작 시 처음부터 다시 안 읽도록 |
| `retry_cnt` | 재시도 횟수 | INT | 이 문서 처리를 몇 번 재시도했는지 | 정수 | 재시도 한도 초과 시 알림/중단 |
| `revision` | 리비전 | VARCHAR | 이 동기화 레코드가 다루는 리비전 | `DOC.cur_revision`과 같은 포맷 | `DOC.cur_revision`과 비교해 최신 처리 여부 계산 |
| `parse_status` | 파싱 상태 | VARCHAR | 파싱 결과 상태 | 코드값(`SUCCESS`/`PARTIAL_RESULT`/`BLOCKED`) | 파싱 실패/부분 성공 문서를 사용자에게 명시적으로 알림(계산으로 만들 수 없는 "처리 결과 자체"라서 저장) |
| `content_hash` | 내용 해시 | VARCHAR | 파싱 시점 문서 내용의 해시 | SHA-256 등 | `DOC.content_hash`와 비교해 재파싱 필요 여부 판단 |
| `parser_ver` | 파서 버전 | VARCHAR | 어떤 버전의 파서로 처리했는지 | 버전 문자열 | 파서가 업데이트됐을 때 재처리 대상 판별 |
| `embed_ver` | 임베딩 버전 | VARCHAR | 어떤 버전의 임베딩 파이프라인을 탔는지 | 버전 문자열 | 임베딩 모델 교체 시 재임베딩 대상 판별 |
| `last_proc_at` | 마지막 처리 시각 | TIMESTAMP | 마지막으로 처리(파싱/임베딩)된 시각 | ISO 8601 timestamp | 처리 지연 모니터링, 오래된 미처리 문서 탐지 |

#### `KNOW_ITEM_SRC` (지식 항목 원문 근거)
`KNOW_ITEM`(추출된 지식) 하나가 원문의 어디에서 나왔는지 근거를 기록하는 연결 테이블. 별도의 `CitationRef` 테이블을 새로 만들지 않고, 이 테이블을 페이지·청크·인용문 단위까지 확장하는 것으로 대체했다.

연결: `KNOW_ITEM`과 `DOC_BLOCK`을 N:M으로 연결.

| 필드 | 한글명 | 타입 | 저장 내용 | 저장 방식 | 사용처 |
|---|---|---|---|---|---|
| `know_item_id` (PK/FK) | 지식 항목 ID | UUID | 대상 지식 항목 | `KNOW_ITEM.know_item_id` 참조 | — |
| `block_id` (PK/FK) | 문서 블록 ID | UUID | 근거가 된 블록 | `DOC_BLOCK.block_id` 참조 | — |
| `rel_type` | 관계 유형 | VARCHAR | 이 근거가 직접 추출/보조 근거 중 무엇인지 | 코드값(`PRIMARY`/`SUPPORTING`) | 여러 근거 중 대표 근거를 우선 표시 |
| `src_ver` | 원본 버전 | VARCHAR | 이 근거가 유효했던 문서 리비전 | 문자열 | 리비전이 바뀌어 근거가 낡았는지 판별 |
| `confidence` | 신뢰도 | DECIMAL | 이 블록이 실제 근거일 확률 | 0.0~1.0 | 근거 신뢰도 낮은 것 검토 대상 표시 |
| `chunk_id` | 청크 ID | UUID | 근거가 된 정확한 청크(블록보다 세밀한 단위) | `CHUNK.chunk_id` 참조, nullable | 페이지 전체가 아니라 특정 문단까지 Citation을 좁혀서 보여줄 때 |
| `quote_text` | 인용문 | TEXT | 근거가 된 원문 그대로의 문장 | 자유 텍스트(원문 발췌) | 사용자에게 "이 문장에서 추출됨"을 그대로 보여주는 Evidence-first UI |
| `quote_hash` | 인용문 해시 | VARCHAR | `quote_text`의 해시 | SHA-256 등 | 원문이 수정됐을 때 인용문이 여전히 유효한지 빠르게 검증 |
| `src_locator` | 원본 위치 | JSONB | 인용문의 정확한 위치(문단/표 셀 등) | `DOC_BLOCK.src_locator`와 같은 형식 | 표에서 나온 지식일 경우 정확한 셀 위치까지 되짚기 |

#### `MODEL_KNOW_ITEM` (모델-지식 항목 연결)
`PROJ_KNOW_MODEL`(지식모델 버전) 하나에 어떤 `KNOW_ITEM`들이 포함되는지 연결하는 테이블.

| 필드 | 한글명 | 타입 | 저장 내용 | 저장 방식 | 사용처 |
|---|---|---|---|---|---|
| `model_id` (PK/FK) | 지식 모델 ID | UUID | 대상 지식모델 | `PROJ_KNOW_MODEL.model_id` 참조 | — |
| `know_item_id` (PK/FK) | 지식 항목 ID | UUID | 포함된 지식 항목 | `KNOW_ITEM.know_item_id` 참조 | — |
| `incl_status` | 포함 상태 | VARCHAR | 이 항목이 채택/제외/보류 중 무엇인지 | 코드값(`INCLUDED`/`EXCLUDED`/`PENDING`) | 사용자가 특정 지식을 모델에서 수동 제외했을 때 반영 |
| `sort_ord` | 정렬 순서 | INT | 모델 내에서의 표시 순서 | 정수 | 지식모델 상세 화면의 항목 정렬 |

#### `FEAT_CLUSTER` (기능 클러스터)
지식 항목들을 "기능/업무 범위" 단위로 묶은 그룹. 예: "로그인 기능 관련 지식들"을 하나의 클러스터로.

연결: `PROJ_KNOW_MODEL`에 소속(1:N). `FEAT_CLUSTER_ITEM`으로 `KNOW_ITEM`과 N:M.

| 필드 | 한글명 | 타입 | 저장 내용 | 저장 방식 | 사용처 |
|---|---|---|---|---|---|
| `cluster_id` (PK) | 기능 클러스터 ID | UUID | 클러스터 고유 식별자 | 내부 생성 UUID | `FEAT_CLUSTER_ITEM`의 FK 기준 |
| `model_id` (FK) | 지식 모델 ID | UUID | 소속 지식모델 | `PROJ_KNOW_MODEL.model_id` 참조 | 모델별 클러스터 목록 조회 |
| `name` | 이름 | VARCHAR | 클러스터명 | 문자열(예: "로그인/인증") | 화면 표시 |
| `biz_scope` | 업무 범위 | VARCHAR | 이 클러스터가 다루는 업무 영역 | 코드값 또는 짧은 문자열 | 업무 영역별 필터링, 담당팀 매칭 |
| `summary` | 요약 | TEXT | 클러스터 내용 요약 | 자유 텍스트 | 클러스터 카드 UI 미리보기 |

#### `FEAT_CLUSTER_ITEM` (클러스터-지식 연결)
`FEAT_CLUSTER`와 `KNOW_ITEM`을 N:M으로 연결.

| 필드 | 한글명 | 타입 | 저장 내용 | 저장 방식 | 사용처 |
|---|---|---|---|---|---|
| `cluster_id` (PK/FK) | 기능 클러스터 ID | UUID | 대상 클러스터 | `FEAT_CLUSTER.cluster_id` 참조 | — |
| `know_item_id` (PK/FK) | 지식 항목 ID | UUID | 포함된 지식 항목 | `KNOW_ITEM.know_item_id` 참조 | — |
| `sim_score` | 유사도 점수 | DECIMAL | 이 지식이 클러스터에 얼마나 잘 맞는지 | 0.0~1.0 | 클러스터링 품질 확인, 낮은 점수 항목 재검토 |
| `merge_status` | 병합 상태 | VARCHAR | 클러스터 병합/분리 이력 상태 | 코드값 | 클러스터 재구성 시 이전 이력 추적 |

#### `TASK` (신규 업무)
지식모델에서 자동으로 추출·제안된 업무. 이 프로젝트의 최종 산출물 중 하나(할 일 목록).

연결: `PROJ_KNOW_MODEL`에 소속(1:N). `TASK_KNOW_SRC`로 `KNOW_ITEM`과 N:M.

| 필드 | 한글명 | 타입 | 저장 내용 | 저장 방식 | 사용처 |
|---|---|---|---|---|---|
| `task_id` (PK) | 신규 업무 ID | UUID | 업무 고유 식별자 | 내부 생성 UUID | `TASK_KNOW_SRC`의 FK 기준 |
| `model_id` (FK) | 지식 모델 ID | UUID | 이 업무를 만들어낸 지식모델 | `PROJ_KNOW_MODEL.model_id` 참조 | 어느 버전의 분석에서 나온 업무인지 추적 |
| `task_name` | 업무명 | VARCHAR | 업무 제목 | 문자열 | 업무 목록·칸반 UI 표시 |
| `req_role` | 필요 역할 | VARCHAR | 이 업무에 필요한 역할/직무 | 코드값 또는 문자열(예: "백엔드") | 담당자 배정 매칭 |
| `effort` | 예상 공수 | DECIMAL | 예상 작업량 | 숫자(시간 또는 인일 단위) | 일정/리소스 계획 |
| `start_at / due_at` | 시작일 / 마감일 | TIMESTAMP | 업무 시작·마감 예정일 | ISO 8601 timestamp 2개 값 | 캘린더/간트 표시, 지연 알림 |
| `priority` | 우선순위 | VARCHAR | 업무 우선순위 | 코드값(`HIGH`/`MEDIUM`/`LOW`) | 업무 정렬, 리소스 배정 우선순위 |
| `src_type` | 출처 유형 | VARCHAR | 이 업무가 문서에서 직접 추출됐는지, AI가 생성했는지, 사람이 추가했는지 | 코드값(`EXTRACTED`/`GENERATED`/`AI_SUGGESTED_MISSING_TASK`/`USER_ADDED`) | 신뢰도 표시 차등화, "AI가 놓친 업무를 제안"한 경우 별도 강조 표시 |
| `confidence` | 신뢰도 | DECIMAL | 이 업무 추출/제안의 확신도 | 0.0~1.0 | 낮은 신뢰도 업무를 사용자 확인 대상으로 표시 |

#### `TASK_KNOW_SRC` (업무-지식 근거 연결)
`TASK`가 어떤 `KNOW_ITEM`(들)에서 파생됐는지 근거를 연결.

| 필드 | 한글명 | 타입 | 저장 내용 | 저장 방식 | 사용처 |
|---|---|---|---|---|---|
| `task_id` (PK/FK) | 신규 업무 ID | UUID | 대상 업무 | `TASK.task_id` 참조 | — |
| `know_item_id` (PK/FK) | 지식 항목 ID | UUID | 근거가 된 지식 항목 | `KNOW_ITEM.know_item_id` 참조 | — |
| `rel_type` | 관계 유형 | VARCHAR | 직접 근거/참고 근거 등 | 코드값 | 대표 근거 우선 표시 |
| `rationale` | 생성 근거 | TEXT | 왜 이 지식에서 이 업무가 만들어졌는지 설명 | 자유 텍스트(모델이 생성한 근거 문장) | "이 업무는 왜 생겼나요?"에 대한 설명 UI, Evidence-first 원칙 충족 |

#### `ANA_SNAPSHOT` (분석 스냅샷)
특정 시점에 어떤 지식모델·정책 버전으로 분석을 돌렸는지 기록하는 감사(audit) 테이블. 재현성 확보용.

연결: `PROJ`, `PROJ_KNOW_MODEL`에 각각 FK.

| 필드 | 한글명 | 타입 | 저장 내용 | 저장 방식 | 사용처 |
|---|---|---|---|---|---|
| `snap_id` (PK) | 스냅샷 ID | UUID | 스냅샷 고유 식별자 | 내부 생성 UUID | — |
| `proj_id` (FK) | 프로젝트 ID | UUID | 대상 프로젝트 | `PROJ.proj_id` 참조 | 프로젝트별 분석 이력 조회 |
| `model_id` (FK) | 지식 모델 ID | UUID | 이 시점에 사용된 지식모델 버전 | `PROJ_KNOW_MODEL.model_id` 참조 | "그때 어떤 데이터로 분석했는지" 재현 |
| `snap_as_of` | 스냅샷 기준 시각 | TIMESTAMP | 이 스냅샷이 찍힌 시각 | ISO 8601 timestamp | 이력 정렬, 특정 시점 재현 조회 |
| `policy_ver` | 정책 버전 | VARCHAR | 당시 적용된 분석/배정 정책의 버전 | 버전 문자열 | 정책이 바뀐 뒤에도 과거 분석 결과가 "그때 기준으로는" 맞았음을 설명 |
| `doc_version_set` | 문서 버전 집합 | JSONB | 이 스냅샷이 참조한 문서들의 리비전 목록 | 예: `{"doc_id_1":"rev_3","doc_id_2":"rev_1"}` | 분석 결과를 재현할 때 정확히 어느 문서 버전들을 기준으로 했는지 복원 |

---

### Page 3-A — pgvector 검색 인덱스

#### `VEC_IDX` (벡터 검색 인덱스)
`CHUNK`를 임베딩한 벡터와 검색 필터링에 필요한 최소한의 메타데이터만 담는 테이블. **Figma 3-A에 배치되는 유일한 검색 인덱스 테이블**이다.

연결: `CHUNK`와 1:1.

| 필드 | 한글명 | 타입 | 저장 내용 | 저장 방식 | 사용처 |
|---|---|---|---|---|---|
| `chunk_id` (PK, 설계상 참조) | 청크 ID | UUID | 원본 청크이자 벡터 레코드 식별자 | `CHUNK.chunk_id`와 동일, 1:1 | 검색 결과를 원문 청크/블록까지 역추적 |
| `embedding` | 임베딩 값 | VECTOR(768) | 청크 텍스트를 벡터화한 값 | pgvector `vector(768)` **고정**(2026-08-04). `google/embeddinggemma-300m`의 출력 차원이고, 적재와 검색이 같은 모델을 써야 하므로 차원은 한 곳에서만 정해진다 | 유사도 검색(코사인/유클리드 거리 계산)의 대상 데이터 |
| `metadata` | 메타데이터 | JSONB | 검색 필터 전용 메타데이터 | 예: `{"proj_id":"...","document_id":"...","doc_role":"PRIMARY","security":"GENERAL","acl_principals":[...]}` — **업무 의미(담당자·마감일 등)는 넣지 않음** | 검색 시 project/권한 범위로 먼저 필터링하고, 업무 의미는 `CHUNK→KNOW_ITEM_SRC→KNOW_ITEM.semantic_type` JOIN으로 조회 |
| `indexed_at` | 인덱싱 시각 | TIMESTAMP | 벡터가 생성/저장된 시각 | ISO 8601 timestamp | 인덱싱 지연 모니터링 |
| `embed_model` | 임베딩 모델 | VARCHAR | 어떤 임베딩 모델을 썼는지 | 모델명 문자열 | 모델이 다른 벡터끼리는 거리 비교가 무의미하므로, 검색 시 모델 일치 필터 |
| `embed_ver` | 임베딩 버전 | VARCHAR | 임베딩 파이프라인 버전 | 버전 문자열 | 재임베딩 대상 판별 |
| `embed_dim` | 임베딩 차원 | INT | 벡터의 차원 수 | **768**(2026-08-04 확정). 1536이던 시절은 OpenAI `text-embedding-3-small`을 전제한 것이라 맞지 않는다 | `embedding` 컬럼 타입 검증, 모델 교체 시 차원 불일치 감지 |
| `dist_metric` | 거리 계산 방식 | VARCHAR | 유사도 계산에 쓸 거리 함수 | 코드값(`COSINE`/`L2`/`INNER_PRODUCT`) | 검색 쿼리의 정렬 기준 |
| `content_hash` | 내용 해시 | VARCHAR | 임베딩 대상이 된 텍스트의 해시 | SHA-256 등 | 원본 청크와 벡터가 최신 상태로 일치하는지 검증 |
| `revision` | 리비전 | VARCHAR | 이 벡터가 속한 문서 리비전 | `DOC.cur_revision`과 같은 포맷 | 리비전이 바뀌면 이전 벡터를 검색 대상에서 제외하는 기준 |
| `is_active` | 활성 여부 | BOOLEAN | 이 벡터가 현재 유효한지 | true/false | pgvector는 JOIN이 가능해 원래는 계산으로 대체할 수 있지만, Vector DB를 네이티브(Chroma 등)로 바꾸는 경우 JOIN이 불가능하므로 **여기서는 명시적으로 저장**(3장 참고) |

---

## 3. 이 스키마가 지키고 있는 설계 원칙 (요약)

1. **저장소 역할 분리** — 3-B RDBMS는 진짜 데이터(14개 테이블), 3-A pgvector는 검색용 보조 인덱스(`VEC_IDX` 1개)다. 검색 인덱스를 재생성해도 원본 데이터와 계보는 손실되지 않는다.
2. **테넌트 경계는 팀** — 문서·Block·Chunk는 `DOC.team_id`를 기준으로 조회 범위를 제한하고(모든 문서 쿼리가 `WHERE team_id = ?`로 좁힌다), 지식·Task·Snapshot은 `proj_id`로 좁힌다. 접근 판정은 `PROJ_MEMBER`의 역할이 아니라 팀 검사(`_require_team`·`_require_team_project`)가 한다 — 팀장이 등록한 문서를 팀원이 못 여는 것은 경계 정의와 어긋난다.
3. **리비전은 별도 테이블 없이 스탬프로 추적** — `DOC.cur_revision`이 "지금 최신이 뭔지"를 가리키고, `DOC_BLOCK`/`VEC_IDX`/`DOC_SYNC`는 자기가 만들어진 시점의 `revision` 값을 스탬프처럼 찍어둔다. "이게 최신인가?"는 `내_revision == DOC.cur_revision` 비교로 계산하며, 과거 리비전 데이터를 지우지 않아도 최신 데이터만 조회할 수 있다.
4. **계산 가능한 값은 저장하지 않는다** — 예: `heading_level`은 `heading_path` 배열 길이로 계산, 블록/청크 개수는 COUNT 쿼리로 계산. 다만 `parse_status`처럼 "처리 결과 자체"인 값은 계산으로 만들 수 없으므로 저장한다.
5. **Evidence-first(근거 우선) 원칙** — `KNOW_ITEM_SRC`, `TASK_KNOW_SRC`가 "이 지식/업무가 어디서 왜 나왔는지"를 문장(`quote_text`, `rationale`) 단위까지 저장한다. 결과만 보여주지 않고 항상 원문으로 되짚어갈 수 있게 한다.
6. **JOIN을 활용한 중복 제거** — `VEC_IDX`가 3-B와 같은 PostgreSQL 인스턴스의 pgvector 테이블이므로, `CHUNK`나 `VEC_IDX`에 업무 메타데이터를 중복 저장하지 않고 `CHUNK → KNOW_ITEM_SRC → KNOW_ITEM.semantic_type` JOIN으로 "업무 관련 Chunk만" 걸러낼 수 있다.

---

## 4. 참고

- 이 문서의 필드 목록은 Figma Page 3-A·3-B에 실제로 반영된 상태를 기준으로 작성했다(2026-07-28 기준).
- 각 필드를 "왜 넣었는지/왜 뺐는지"에 대한 판단 근거(GPT 피드백 평가 등)는 `VectorDB_저장대상_검증.md`에 별도로 정리돼 있다.
- 1단계/후속으로 미룬 항목(리비전 이력 테이블, OCR 관련 필드, `chunk_strategy`, RFP 세부분류, Action/Object 분리 등)은 이 문서에 없다 — 해당 단계 착수 시 다시 설계한다.
