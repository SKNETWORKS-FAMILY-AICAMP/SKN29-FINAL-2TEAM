# Jira · Google Drive 커넥터 연결 설계

People DB 커넥터([[팀원_초대_계정_매핑_정책]] 참조)는 같은 PostgreSQL 안에 있어 주고받을 자격증명이 없었다. Jira·Drive는 외부 서비스라 인가 흐름과 토큰 보관이 필요하다. 이 문서는 그 두 커넥터를 붙이기 전에 정해야 할 것과 정해진 것을 정리한다.

**현재 상태 (2026-07-30): 구현 완료.** 실계정으로 확인했다. 두 커넥터의 인가 흐름·토큰 갱신·조회가 동작하고, 읽을 폴더·Jira 프로젝트를 골라 `proj_source`에 저장하고 폴더 역할을 파일에 상속시켜 `doc`까지 등록한다. 본문 파싱은 이 문서 범위 밖이며 별도로 진행 중이다(§6).

*작성 시점에는 `connector_conn`에 `PEOPLE_DB`만 있었고 화면의 Jira·Drive 카드는 데모 배지를 달고 목업 흐름(`?mode=demo`)으로 연결돼 있었다. 아래 본문은 그 시점의 계획에 구현 결과를 덧붙여 갱신한 것이다.*

## 1. 공통 구조

두 서비스 모두 표준 인가 코드 흐름을 쓴다. 사용자가 "연결하기"를 누르면 서비스 로그인 화면으로 갔다가 돌아온다.

```
[연결하기]
  → GET  /api/connectors/{type}/authorize/     서버가 인가 URL 생성해 반환
  → (브라우저가 Google/Atlassian 인가 페이지로 이동, 사용자 로그인·승인)
  → GET  /api/connectors/{type}/callback/?code=...&state=...
       code를 access_token + refresh_token으로 교환
       connector_conn upsert (auth_status='CONNECTED')
  → 프론트엔드로 리다이렉트 (FRONTEND_BASE_URL/onboarding/connectors)
```

`People DB` 커넥터와 달리 콜백이 브라우저 리다이렉트로 들어오므로, **콜백은 Bearer 토큰을 받을 수 없다.** 누가 시작한 연결인지 `state`로 전달해야 한다.

### state 설계

서버에 세션 테이블이 없는 구조이므로 `state`도 저장하지 않는다. `apps/accounts/tokens.py`와 같은 방식으로 **서명 토큰**을 쓴다.

```
state = TimestampSigner(salt="halil.connector.state").sign_object({
    "account_id": ...,
    "connector_type": ...,
})
```

- 만료 10분(인가 페이지에 머무는 시간만 커버)
- 콜백에서 서명·만료를 검증하고 `account_id`를 꺼낸다
- 서명이 있으므로 CSRF 방지와 주체 식별을 한 값으로 해결한다

`authorize` 엔드포인트는 콜백과 달리 프론트엔드가 직접 부르므로 **Bearer 인증을 강제한다.** 그리고 경로의 `{type}`을 그대로 `state`나 외부 요청에 싣지 않고 **허용 목록(`GOOGLE_DRIVE` / `JIRA`)으로 검증**한다. 목록에 없으면 404로 끝낸다 — 임의의 `connector_type` 값이 `connector_conn`에 들어가거나, 알 수 없는 provider로 리다이렉트가 만들어지는 것을 막는다.

### 콜백 실패 처리

콜백은 브라우저가 보는 URL이므로 **토큰이나 상세 오류를 쿼리 파라미터에 싣지 않는다.** 사용자가 승인을 거부한 경우(`error=access_denied`), provider가 오류를 준 경우, `state` 검증에 실패한 경우 모두 같은 방식으로 처리한다.

```
성공 → {FRONTEND_BASE_URL}/onboarding/connectors?connector=jira&status=ok
실패 → {FRONTEND_BASE_URL}/onboarding/connectors?connector=jira&status=error
```

- 리다이렉트 대상은 **`FRONTEND_BASE_URL` + 고정 경로 허용 목록**으로만 만든다. `state`나 쿼리에서 받은 값으로 경로를 조립하지 않는다(open redirect 방지)
- 실패 사유는 서버 로그에만 남긴다. 화면에는 "연결하지 못했습니다. 다시 시도해 주세요." 수준으로 표시하고, 상세는 노출하지 않는다
- 토큰·`code`·`state` 값은 어떤 경우에도 리다이렉트 URL에 포함하지 않는다

### 토큰 보관

`connector_conn.encrypted_credential_ref`에 **Fernet 암호문**을 넣는다.

> `encrypted_credential_ref` — 외부 자격증명의 DB 저장용 암호문(기존 ref 명칭 유지). People DB는 자격증명이 없어 NULL

- 키는 `SECRET_KEY` 파생(HKDF 또는 `base64(sha256(SECRET_KEY))`)으로 만든다. **`SECRET_KEY`가 바뀌면 기존 연결이 전부 복호화 불가**가 되므로, 그때는 재연결을 유도해야 한다(`auth_status='ERROR'`)
- 암호문 payload는 JSON으로 묶어 한 컬럼에 넣는다 — `refresh_token`, `access_token`, `expires_at`, 그리고 Jira는 `cloud_id`까지
- `granted_scopes`(JSONB)에는 범위 문자열만 둔다. 자격증명이나 식별자를 섞지 않는다

Secret Manager를 쓰지 않는 이유는 부트캠프 범위에서 과하기 때문이다. 컬럼명이 `ref`인데 실제로는 암호문이 들어가는 불일치는 감수하고 주석으로 남겼다.

#### 컬럼 타입은 TEXT여야 한다 (선행 조건)

`encrypted_credential_ref`는 원래 `VARCHAR(255)`였다. Secret Manager 참조 키를 담는다는 전제였기 때문인데, 암호문을 넣기로 바꾼 지금은 **길이가 전혀 맞지 않는다.** 실측값이다.

| 케이스 | 평문 | Fernet 암호문 |
|---|---|---|
| Jira (JWT access_token 830 + refresh 250 + cloud_id) | 1209 | **1700** |
| Google Drive (access 230 + refresh 103) | 412 | **632** |
| 최소 가정 (access 120 + refresh 60) | 259 | **440** |

Fernet 오버헤드(버전·타임스탬프·IV·HMAC 57바이트) + AES 패딩 + Base64 4/3 확장 때문에, `VARCHAR(255)`에 담을 수 있는 **평문은 최대 127바이트**다. 토큰 하나도 들어가지 않는다.

PostgreSQL은 초과 시 **절단하지 않고 에러(SQLSTATE 22001)를 던진다** — 조용한 손상이 아니라 연결 시도가 즉시 실패하는 형태로 드러난다. 그래도 작업 1번을 시작하기 전에 반드시 고쳐야 한다.

`DB/schema.sql`은 `TEXT`로 갱신했다. **이미 DB를 만들어 둔 사람은 다음을 실행해야 한다.**

```sql
ALTER TABLE connector_conn
    ALTER COLUMN encrypted_credential_ref TYPE TEXT;
```

기존 값은 NULL(People DB만 연결된 상태)이므로 변환 손실이 없다. 이 프로젝트는 마이그레이션 도구를 쓰지 않으므로(`DATABASES = {}`) 스키마 변경은 이렇게 수동 `ALTER`로 공유한다.

#### `proj_source`에 컬럼 두 개 추가 (선행 조건, 2026-07-30)

```sql
ALTER TABLE proj_source ADD COLUMN IF NOT EXISTS default_doc_role VARCHAR(30);
ALTER TABLE proj_source ADD COLUMN IF NOT EXISTS max_depth INT;
```

`DB/schema.sql`은 갱신했다. 이미 DB가 있으면 위를 실행해야 한다([[DB_시작_가이드]] §4.3에 모아 뒀다). 둘 다 `JIRA_PROJECT` 소스에서는 NULL이다.

**`default_doc_role`** — 폴더에 역할을 주고 안의 파일이 물려받는 화면(`/onboarding/folder-roles`)을 저장하려면 폴더 단위 역할을 담을 곳이 필요하다. `doc.doc_role`은 문서 단위라서, 상속을 풀어 각 문서에 써넣으면 **나중에 그 폴더에 파일이 추가될 때 무엇을 상속할지 알 수 없다.** 값은 `doc.doc_role`과 같은 코드다(`PLAN`/`MEETING_NOTE`/`DAILY_REPORT`/`OTHER`).

**`max_depth`** — 폴더 탐색 깊이. 선택한 폴더를 1단계로 센다.

```
1      선택한 폴더의 직속 파일만
2      한 단계 더 (하위 폴더까지)
NULL   제한 없음
```

화면에는 "하위 폴더 포함" 토글과 "탐색 깊이" 선택이 따로 있지만 **DB는 컬럼 하나로 받는다.** 토글을 끄는 것이 곧 `max_depth = 1`이다. 불리언을 따로 두면 "off인데 깊이가 3이면 어느 쪽이 이기나"를 아무도 강제하지 않는 규칙으로 남는다.

깊이 설정은 이번에 저장하는 모든 폴더에 같은 값으로 들어간다. 화면의 컨트롤이 폴더별이 아니라 하나이기 때문이다. 폴더별로 다르게 두는 것은 컬럼이 이미 폴더 단위라 나중에 화면만 바꾸면 된다.

### 토큰 갱신

만료된 access_token은 refresh_token으로 갱신한다.

- 갱신 성공 → 암호문 갱신, `connected_at` 유지
- 갱신 실패(만료·철회) → `auth_status='EXPIRED'`로 전이. 화면은 "재연결" 버튼을 보여준다
- 갱신은 API 호출 직전에 lazy로 한다. 배치 스케줄러는 만들지 않는다(초대 만료를 lazy 체크하는 것과 같은 방침)

## 2. Google Drive

### 콘솔 준비 (June 님)

1. Google Cloud 프로젝트 생성
2. OAuth 동의 화면 구성 — **게시 상태는 "테스트"**로 두고 팀원 5명을 테스트 사용자로 등록
3. 사용자 인증 정보 → OAuth 클라이언트 ID → **웹 애플리케이션**
4. 승인된 리디렉션 URI 등록: `http://localhost:8000/api/connectors/google-drive/callback/`
5. `client_id` / `client_secret`을 `.env`에 (Gmail 앱 비밀번호와 같은 방식)

### 범위

문서를 읽어 업무를 추출하는 것이 목적이므로 읽기 전용으로 충분하다.

```
https://www.googleapis.com/auth/drive.metadata.readonly   폴더·파일 목록
https://www.googleapis.com/auth/drive.readonly            본문 읽기
```

`drive.readonly`는 Google의 **제한된 범위**에 해당한다. 테스트 모드에서는 심사가 필요 없지만, 프로덕션 게시로 바꾸면 보안 평가를 받아야 한다. MVP 범위에서는 테스트 모드를 유지한다.

### 주의할 것

- **테스트 모드의 refresh_token은 7일 후 만료된다.** 연결해두고 일주일 뒤 시연하면 끊겨 있다. 시연 직전에 재연결하면 되지만 모르면 당황한다
- refresh_token을 받으려면 `access_type=offline`이 필요하고, 두 번째 연결부터는 `prompt=consent`가 없으면 refresh_token이 오지 않는다

## 3. Jira (Atlassian)

두 갈래가 있고, 시연에서 보여줄 것이 다르다.

| | API 토큰 | 인가 흐름(3LO) |
|---|---|---|
| 사용자 경험 | 사이트 URL·이메일·토큰을 폼에 입력 | "연결하기" → Atlassian 로그인 → 승인 |
| 콘솔 준비 | 불필요 | Developer Console에 앱 등록 |
| 구현량 | 적음 | Drive와 동일 |
| 시연 인상 | 약함 | 실제 연동처럼 보임 |

**권장: 인가 흐름.** Drive와 구조가 같아 코드를 대부분 공유할 수 있고, 화면도 이미 "연결하기" 버튼으로 그려져 있다. API 토큰 방식은 콘솔 등록이 막힐 때의 대비책으로 남긴다.

### 콘솔 준비 (June 님)

1. Atlassian Developer Console에서 OAuth 2.0 (3LO) 앱 생성
2. 권한(Permissions)에 Jira API 추가
3. 콜백 URL: `http://localhost:8000/api/connectors/jira/callback/`
4. `client_id` / `client_secret`을 `.env`에

### 범위

```
read:jira-work    프로젝트·이슈 조회
read:jira-user    담당자 정보
offline_access    refresh_token 발급
```

### cloudId가 추가로 필요하다

Atlassian은 토큰만으로 API를 부를 수 없다. 사이트를 식별하는 `cloudId`를 먼저 조회해야 한다.

```
GET https://api.atlassian.com/oauth/token/accessible-resources
  → [{ id: "<cloudId>", name, url, scopes }]

이후 호출: https://api.atlassian.com/ex/jira/<cloudId>/rest/api/3/project
```

`cloudId`를 담을 컬럼이 `connector_conn`에 없다. **암호문 payload에 함께 넣는다** — 새 컬럼을 추가하지 않는다. 사이트가 여러 개면 첫 연결 시 선택 단계가 필요하지만, 팀 사이트는 하나이므로 MVP에서는 첫 항목을 쓰고 여러 개일 때만 선택을 노출한다.

## 4. 데이터 소스 연결(`proj_source`) — 폴더를 고르는 것이 프로젝트를 만드는 것이다

커넥터 연결(`connector_conn`)은 **계정 단위**지만, 어느 폴더·어느 Jira 프로젝트를 읽을지(`proj_source`)는 **프로젝트 단위**다.

```
connector_conn   account_id  + connector_type            계정이 서비스에 연결됨
proj_source      proj_id + conn_id + external_source_id  이 프로젝트가 저 소스를 읽음
```

### 이 절의 앞선 서술은 틀렸다 (2026-07-30 수정)

원래 이 절은 "`proj_source.proj_id`가 NOT NULL이므로 **프로젝트 생성 흐름이 선행되어야 한다**"고 적었다. 테이블 의존 순서로는 맞지만, 그것을 **화면 순서**로 옮기면 제품 목적과 거꾸로 간다. 이 서비스는 Drive의 기획서를 읽어 프로젝트를 만들고 업무를 추출하는 것이 목적이다. 사람이 프로젝트를 먼저 정의해야 한다면 자동화할 것이 없다.

**해결: 폴더를 고르는 행위가 프로젝트를 만드는 행위다.** 별도 프로젝트 생성 화면을 두지 않는다.

`proj.status`에 이미 `DRAFT`가 있다(`ProjectCreateSerializer`의 기본값이기도 하다). 원래 설계도 "내용이 채워지기 전의 프로젝트"를 상정하고 있었다.

```
1. 커넥터 연결            connector_conn                    계정 단위
2. 폴더·프로젝트 선택      proj(DRAFT) + proj_source          ← 여기서 프로젝트가 생긴다
                          이름은 임시로 최상위 폴더명
3. 파일 스캔·역할 지정     doc / doc_role
4. 기획서 파싱             proj.name 갱신, DRAFT → ACTIVE
                          know_item
5. 업무 추출               task
6. 배정                    assign_run
```

Drive 폴더와 Jira 프로젝트는 **같은 `proj`에 붙는다** — Drive는 기획서, Jira는 진행 상황인 한 프로젝트의 두 소스다. 어느 화면을 먼저 끝내도 진행 중인 `DRAFT`를 찾아 공유하고, 없을 때만 만든다(`ensureOnboardingProject`).

### 조회는 프로젝트 없이도 된다 (구현됨)

무엇을 고를지 **보여주는 것**은 `connector_conn`의 토큰만 있으면 되고, 고른 결과를 **저장하는 것**만 `proj_id`를 요구한다.

```
GET /api/connectors/google-drive/folders/?parent=<folder_id>
    → [{ folder_id, name, modified_at }]
GET /api/connectors/google-drive/folders/?ids=<id>,<id>
    → 같은 형태. 저장된 선택의 이름을 되짚는 용도
GET /api/connectors/google-drive/files/?parent=<folder_id>&depth=<n|unlimited>
    → [{ file_id, name, mime_type, modified_at, supported, folder_path }]
GET /api/connectors/jira/projects/
    → [{ project_key, project_id, name, description, project_type, lead_name, avatar_url }]
```

모두 `apps/connectors/clients.py`에 있다. 호출 직전에 만료를 확인해 갱신·저장까지 하고(§토큰 갱신), 갱신이 실패하면 `EXPIRED`로 전이시킨 뒤 502를 돌려준다. 화면은 404(미연결)와 502(재연결 필요)를 같은 안내로 묶어 커넥터 화면으로 되돌린다.

**Drive는 한 단계씩 내려가며 조회한다.** 폴더 전체를 한 번에 받는 방식으로 먼저 만들었더니 실제 계정에서 473개가 나와 `pageSize` 상한 200개에서 잘렸고, 무관한 템플릿 폴더에 작업 폴더가 묻혔다. `parent`의 직속 자식만 받으면 최상위가 3개다. `parent`를 생략하면 내 드라이브 최상단(`'root'`)이다.

`parent`는 Drive 검색식(`'<parent>' in parents`)에 그대로 들어가므로 따옴표·백슬래시가 섞인 값은 400으로 막는다.

Jira의 `description`·`lead`는 기본 응답에 없어 `expand=description,lead`가 필요하다.

`ids`를 주면 그 폴더들만 돌려준다(`?ids=a,b,c`). `proj_source`에는 폴더 id만 남아서 저장된 선택을 화면에 되살릴 때 이름을 되짚어야 한다. Drive 검색식은 id 비교를 지원하지 않아 개별 조회를 쓰고, 지워졌거나 권한이 사라진 폴더는 목록에서 조용히 빠진다. Jira는 프로젝트 키가 목록과 바로 맞춰지므로 이런 조회가 필요 없다.

파일 조회는 `depth`만큼 하위 폴더를 따라 내려간다(BFS). `depth`를 생략하면 1이라 직속 파일만 본다. `folder_path`는 선택한 폴더 기준 상대 경로로, 직속 파일은 빈 문자열이다 — 재귀로 모으면 평면 목록만 봐서는 어디서 온 파일인지 알 수 없다.

`supported`는 본문에서 업무를 뽑아낼 수 있는 형식인지다(Google Docs 계열·PDF·Office·txt/md/csv). 미지원 파일도 목록에는 넣는다 — 조용히 빼면 "내 파일이 왜 없지"를 묻게 된다.

"제한 없음"은 폴더 200개(`_DRIVE_MAX_FOLDERS`)에서 멈춘다. 폴더마다 파일 조회 1회 + 하위 폴더 조회 1회라 상한이 없으면 호출이 무한정 늘어난다. 실측으로 `SKN29`는 깊이 1에서 16개, 깊이 2에서 21개다.

### 저장 (구현됨)

```
GET  /api/projects/                       내가 소유한 프로젝트
POST /api/projects/                       DRAFT 생성. 소유자는 토큰에서 정한다
GET  /api/projects/<proj_id>/sources/     저장된 소스
PUT  /api/projects/<proj_id>/sources/     { source_type, external_source_ids, max_depth }
GET  /api/projects/<proj_id>/documents/   등록된 문서
PUT  /api/projects/<proj_id>/documents/   { folder_roles, file_roles }
```

`PUT /sources/`는 **그 종류의 소스를 통째로 교체한다.** 선택 화면은 항상 전체 선택 상태를 보내므로, 덧붙이면 화면에서 해제한 폴더가 남는다. 빈 목록은 전부 해제한다는 뜻이다. 계속 선택된 폴더의 `default_doc_role`은 지키고 넘어간다 — 폴더를 다시 저장했다고 역할 지정을 날릴 이유가 없다(탐색 깊이만 바꿔도 마찬가지다).

`max_depth`를 생략하면 1이다. 하위 폴더를 따라 내려가는 것은 명시적으로 요청해야 한다.

`conn_id`는 요청에서 받지 않고 소유자의 `CONNECTED` 연결에서 찾는다 — 남의 연결에 소스를 매달 수 없어야 한다. 해당 커넥터가 연결돼 있지 않으면 409다.

### 역할 지정 → `doc` 등록

`PUT /documents/`는 **파일 목록과 이름을 받지 않는다.** 저장된 `proj_source`의 폴더를 서버가 Drive에서 다시 읽는다. 클라이언트가 보낸 메타데이터를 그대로 `doc`에 넣으면 실재하지 않는 문서가 생길 수 있다. 탐색 깊이도 요청에서 받지 않고 `proj_source.max_depth`를 쓴다 — 화면이 보여준 것과 저장되는 것이 어긋나면 안 된다.

```
folder_roles  { <folder_id>: "PLAN" }         → proj_source.default_doc_role
file_roles    { <file_id>: "MEETING_NOTE" }   → 폴더 역할을 덮어쓸 파일만
```

역할이 지정되지 않은 폴더의 파일과 `supported = false` 파일은 등록하지 않는다. 파싱할 수 없는 문서를 `doc`에 넣으면 이후 파이프라인이 헛돈다.

**`doc` 행은 지우고 다시 만들지 않는다.** `src_file_id`로 찾아 갱신하고, 목록에서 빠진 문서는 `deleted = true`로 표시한다(스키마가 이를 위해 둔 컬럼이다). 역할만 바꿨다고 파싱이 채워 둘 `content_hash`·`cur_revision`을 날릴 수 없다.

`cur_revision`·`content_hash`·`acl_principals`는 이 단계에서 채우지 않는다. 본문을 읽어야 알 수 있어 파싱 단계의 일이다.

## 5. 작업 순서 제안

```
0. 선행 조건 — encrypted_credential_ref를 TEXT로 변경
   ALTER TABLE connector_conn ALTER COLUMN encrypted_credential_ref TYPE TEXT;
   → 검증: 1700자 문자열 저장·조회 성공

1. 공통 기반
   backend/connectors/oauth.py   state 서명, 토큰 교환·갱신, Fernet 암·복호화
   ConnectorRepository           upsert 시 암호문 저장, EXPIRED 전이
   → 검증: 암호문 왕복, 만료된 state 거부, 잘못된 서명 거부,
           실제 토큰 길이(Jira JWT 기준)로 저장 성공

2. Jira 인가 흐름 (Drive보다 제약이 적어 먼저)
   authorize / callback + cloudId 조회
   → 검증: 실제 Atlassian 계정으로 연결 후 프로젝트 목록 조회 성공

3. Google Drive 인가 흐름
   → 검증: 실제 Google 계정으로 연결 후 폴더 목록 조회 성공

4. 화면
   데모 배지 제거, 실제 연결 상태·재연결 버튼
   → 검증: 새로고침해도 연결 유지, EXPIRED면 재연결 유도

5. 폴더·프로젝트 선택 저장 → proj(DRAFT) + proj_source
   → 검증: 저장 후 새로고침해도 선택이 남아 있음

6. 선행 조건 — proj_source에 컬럼 두 개 추가
   ALTER TABLE proj_source ADD COLUMN IF NOT EXISTS default_doc_role VARCHAR(30);
   ALTER TABLE proj_source ADD COLUMN IF NOT EXISTS max_depth INT;

7. 역할 지정 → doc 등록
   → 검증: 폴더 역할이 파일에 상속되고, 파일별 덮어쓰기가 이김
           폴더를 다시 저장해도 역할이 남고, doc_id가 유지됨
           선택이 해제된 폴더의 문서만 deleted = true

8. 하위 폴더 탐색
   → 검증: 깊이를 바꾸면 미리보기 파일 수가 달라짐
           저장된 깊이가 doc 등록에 그대로 쓰임
           깊이만 바꿔 다시 저장해도 폴더 역할이 남음
```

여기까지가 **탐색해서 고른 폴더·파일을 저장하는 범위**다. 본문 파싱은 별도로 진행 중이다.

5번은 원래 "(별건) 프로젝트 생성 → proj_source 연결"이었다. 별건이 아니었다 — §4의 수정 참고.

## 6. 파싱 작업과의 경계

문서 파싱은 **별도로 진행 중이다.** 이 문서의 범위는 어떤 문서를 읽을지 고르고 저장하는 것까지다. 넘겨주는 것과 넘겨받지 않는 것을 분명히 해 둔다.

파싱 쪽이 넘겨받는 것:

```
doc.src_file_id      Drive 파일 id (파일을 내려받을 키)
doc.mime_type        어떤 파서를 태울지
doc.doc_role         파싱 규칙 분기·Vector 검색 필터
doc.file_name        Citation 표기
doc.deleted = false  아직 읽어야 하는 문서
```

파싱 쪽이 채울 것 — 여기서는 건드리지 않는다:

- `doc.cur_revision`·`content_hash`·`acl_principals` — 본문과 권한을 읽어야 안다
- `doc_sync` — 변경 감지·재시도·파서 버전(`chg_type`, `parse_status`, `parser_ver`, `embed_ver`)
- `doc_block` → `chunk` → `know_item` → `task`

`doc` 행은 지우지 않고 `deleted`로 표시하므로, 파싱이 채워 둔 값은 폴더·역할을 다시 저장해도 남는다.

## 7. 정해야 할 것

- **HTTP 클라이언트** — 현재 `requirements/base.txt`에 `requests`가 없다. 표준 `urllib`로도 되지만 토큰 교환·갱신 코드가 지저분해진다. `requests` 추가 여부
- **암호화 라이브러리** — Fernet을 쓰려면 `cryptography`를 명시적으로 추가해야 한다(`psycopg[binary]`가 간접 의존하지만 직접 import는 명시가 맞다)
- **AWS 이전 시 콜백 URI** — 도메인이 정해지면 두 콘솔에 URI를 다시 등록해야 한다. `wonbin` 브랜치의 AWS 이전 작업과 함께 처리
- **팀원의 Jira 셀프 연동** — [[팀원_초대_계정_매핑_정책]]이 "의도적으로 다루지 않은 것"으로 미뤄둔 항목. 팀원 Jira 이메일이 HR 이메일과 다를 수 있는 문제는 여전히 미해결. 잠정적으로 `person_link`(이메일 기반)를 쓴다
- **폴더별 탐색 깊이** — `max_depth`는 폴더 단위 컬럼인데 화면 컨트롤은 하나라서 모든 폴더에 같은 값이 들어간다. 폴더마다 다르게 하려면 화면만 바꾸면 된다. 필요한지 여부는 미결
- **`proj.name` 자동 갱신** — 지금은 최상위 선택 폴더명이다. 기획서를 파싱한 뒤 제안·갱신하는 시점을 정해야 한다. `DRAFT → ACTIVE` 전이도 같은 자리다

## 8. 의도적으로 다루지 않는 것

- **쓰기 권한** — 읽기 전용 범위만 쓴다. Jira에 이슈를 만들거나 Drive에 파일을 쓰는 기능은 범위 밖
- **토큰 갱신 배치** — lazy 갱신으로 충분하다고 본다
- **다중 사이트·다중 계정** — 한 계정이 같은 서비스에 두 번 연결하는 경우는 막지 않지만(스키마에 유니크 제약 없음) 화면에서는 하나로 다룬다
- **프로덕션 게시** — Google 보안 평가, Atlassian 마켓플레이스 등록은 MVP 범위 밖
