# Jira · Google Drive 커넥터 연결 설계

People DB 커넥터([[팀원_초대_계정_매핑_정책]] 참조)는 같은 PostgreSQL 안에 있어 주고받을 자격증명이 없었다. Jira·Drive는 외부 서비스라 인가 흐름과 토큰 보관이 필요하다. 이 문서는 그 두 커넥터를 붙이기 전에 정해야 할 것과 정해진 것을 정리한다.

작성 시점 구현 상태: `connector_conn`에 `PEOPLE_DB`만 기록되고, 화면의 Jira·Drive 카드는 **데모 배지**를 달고 목업 흐름(`?mode=demo`)으로 연결된다.

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

### 토큰 보관

`connector_conn.encrypted_credential_ref`에 **Fernet 암호문**을 넣는다. 스키마 주석이 이미 그렇게 갱신돼 있다.

> `encrypted_credential_ref` — 외부 자격증명의 DB 저장용 암호문(기존 ref 명칭 유지). People DB는 자격증명이 없어 NULL

- 키는 `SECRET_KEY` 파생(HKDF 또는 `base64(sha256(SECRET_KEY))`)으로 만든다. **`SECRET_KEY`가 바뀌면 기존 연결이 전부 복호화 불가**가 되므로, 그때는 재연결을 유도해야 한다(`auth_status='ERROR'`)
- 암호문 payload는 JSON으로 묶어 한 컬럼에 넣는다 — `refresh_token`, `access_token`, `expires_at`, 그리고 Jira는 `cloud_id`까지
- `granted_scopes`(JSONB)에는 범위 문자열만 둔다. 자격증명이나 식별자를 섞지 않는다

Secret Manager를 쓰지 않는 이유는 부트캠프 범위에서 과하기 때문이다. 컬럼명이 `ref`인데 실제로는 암호문이 들어가는 불일치는 감수하고 주석으로 남겼다.

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

## 4. 데이터 소스 연결(`proj_source`)은 프로젝트가 먼저다

커넥터 연결(`connector_conn`)은 **계정 단위**지만, 어느 폴더·어느 Jira 프로젝트를 읽을지(`proj_source`)는 **프로젝트 단위**다.

```
connector_conn   account_id  + connector_type            계정이 서비스에 연결됨
proj_source      proj_id + conn_id + external_source_id  이 프로젝트가 저 소스를 읽음
```

`proj` 테이블이 아직 0행이므로 **프로젝트 생성 흐름이 선행되어야 한다.** 기존 화면 `/onboarding/folders`(Drive 폴더 선택)와 `/onboarding/jira-project`(Jira 프로젝트 선택)가 실연결되는 시점은 프로젝트 생성 이후다.

즉 커넥터 인증을 붙이는 것과, 그 커넥터로 소스를 고르는 것은 별개 작업이다.

## 5. 작업 순서 제안

```
1. 공통 기반
   backend/connectors/oauth.py   state 서명, 토큰 교환·갱신, Fernet 암·복호화
   ConnectorRepository           upsert 시 암호문 저장, EXPIRED 전이
   → 검증: 암호문 왕복, 만료된 state 거부, 잘못된 서명 거부

2. Jira 인가 흐름 (Drive보다 제약이 적어 먼저)
   authorize / callback + cloudId 조회
   → 검증: 실제 Atlassian 계정으로 연결 후 프로젝트 목록 조회 성공

3. Google Drive 인가 흐름
   → 검증: 실제 Google 계정으로 연결 후 폴더 목록 조회 성공

4. 화면
   데모 배지 제거, 실제 연결 상태·재연결 버튼
   → 검증: 새로고침해도 연결 유지, EXPIRED면 재연결 유도

5. (별건) 프로젝트 생성 → proj_source 연결
```

## 6. 정해야 할 것

- **HTTP 클라이언트** — 현재 `requirements/base.txt`에 `requests`가 없다. 표준 `urllib`로도 되지만 토큰 교환·갱신 코드가 지저분해진다. `requests` 추가 여부
- **암호화 라이브러리** — Fernet을 쓰려면 `cryptography`를 명시적으로 추가해야 한다(`psycopg[binary]`가 간접 의존하지만 직접 import는 명시가 맞다)
- **AWS 이전 시 콜백 URI** — 도메인이 정해지면 두 콘솔에 URI를 다시 등록해야 한다. `wonbin` 브랜치의 AWS 이전 작업과 함께 처리
- **팀원의 Jira 셀프 연동** — [[팀원_초대_계정_매핑_정책]]이 "의도적으로 다루지 않은 것"으로 미뤄둔 항목. 팀원 Jira 이메일이 HR 이메일과 다를 수 있는 문제는 여전히 미해결. 잠정적으로 `person_link`(이메일 기반)를 쓴다

## 7. 의도적으로 다루지 않는 것

- **쓰기 권한** — 읽기 전용 범위만 쓴다. Jira에 이슈를 만들거나 Drive에 파일을 쓰는 기능은 범위 밖
- **토큰 갱신 배치** — lazy 갱신으로 충분하다고 본다
- **다중 사이트·다중 계정** — 한 계정이 같은 서비스에 두 번 연결하는 경우는 막지 않지만(스키마에 유니크 제약 없음) 화면에서는 하나로 다룬다
- **프로덕션 게시** — Google 보안 평가, Atlassian 마켓플레이스 등록은 MVP 범위 밖
