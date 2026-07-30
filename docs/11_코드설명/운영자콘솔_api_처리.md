# 운영자 콘솔 API 처리 — 섹션 1(관리자 로그인) · 섹션 2(운영 현황)

> 기준일: 2026-07-30
> 범위: `apps/ops` 백엔드가 실제로 구현·검증한 두 섹션의 엔드포인트별 동작을 경로 하나하나 정리한다.
> 나머지 6개 섹션(연결 조직/계정 관리/계정 연결·초대/연결 서비스/감사 로그/전역 정책)은 아직 목업 데이터이며,
> 이 문서에는 포함하지 않는다. 전체 8개 섹션 계획은 프로젝트 채팅 세션의 계획 문서(`fizzy-orbiting-goose.md`)를 참고한다.

---

## 0. 공통 구조

- 앱 위치: `apps/ops/`(Django, ORM 미사용 — `DB/schema.sql` 테이블을 `backend/db/repositories.py`의 Repository가 raw SQL로 직접 조회).
- 라우트 prefix: `config/urls.py`에서 `path("api/ops/", include("apps.ops.api_urls"))`.
- 인증: `Authorization: Bearer <토큰>` 헤더. 토큰은 `apps/ops/tokens.py`가 발급하는 서명 토큰(유효기간 2시간, salt `halil.auth.ops` — 일반 로그인 토큰과 완전히 분리).
- **관리자 인증이 필요한 모든 API**(`AdminView` 상속 — `/auth/me/`, `/auth/logout/`, `/overview/`)는 토큰 서명·만료만 보는 게 아니라, **요청마다 DB를 다시 조회**해서 `user_account.is_admin = true`와 `account_status = 'ACTIVE'`를 재확인한다(`apps/ops/authentication.py`의 `OpsBearerTokenAuthentication`). 로그인 이후에 관리자 권한이 회수되거나 계정이 잠기면, 아직 유효기간이 남은 토큰이라도 **그 즉시** 막힌다.
- 관리자 권한 부여/회수는 API에 없다. `backend/services/createDB/grant_admin.py`를 호스트에서 직접 실행해야만 바뀐다(자기 자신·타인을 API로 승격시키는 경로 자체가 없음).
- DB 오류는 어디서 나든 `{"detail": "데이터베이스 요청을 처리할 수 없습니다."}` + `503`으로 통일해서 응답한다(`backend/api_errors.py`).

---

## 1. 섹션 1 — 관리자 로그인

### 1.1 `POST /api/ops/auth/login/`

요청 바디: `{"email": string, "password": string}`

| # | 입력·상황 | HTTP | 응답 `detail` | 비고 |
|---|---|---|---|---|
| 1 | `email` 필드 누락 | 400 | `{"email": ["이 필드는 필수 항목입니다."]}` | DRF 시리얼라이저 기본 검증(자동 한글화) |
| 2 | `password` 필드 누락 | 400 | `{"password": ["이 필드는 필수 항목입니다."]}` | 〃 |
| 3 | 이메일 형식이 아님(`not-an-email`) | 400 | `{"email": ["유효한 이메일 주소를 입력하세요."]}` | 〃 |
| 4 | 빈 JSON(`{}`) | 400 | 두 필드 오류를 함께 반환 | 〃 |
| 5 | JSON 자체가 깨짐 | 400 | `{"detail": "JSON parse error - ..."}` | DRF `JSONParser`가 만드는 진단 메시지라 영어 그대로임(전 앱 공통 동작, 이 프로젝트만의 문제 아님) |
| 6 | 가입되지 않은 이메일 | 401 | `이메일 또는 비밀번호가 올바르지 않습니다.` | 계정 존재 여부를 노출하지 않으려고 비밀번호 오류와 문구를 통일 |
| 7 | 비밀번호 불일치 | 401 | `이메일 또는 비밀번호가 올바르지 않습니다.` | 〃 |
| 8 | 가입은 됐지만 `is_admin = false` | 403 | `관리자 권한이 없는 계정입니다.` | 비밀번호까지 맞아야 이 문구가 나오므로, 존재하는 다른 이메일의 관리자 여부는 알 수 없음 |
| 9 | 계정 상태 `LOCKED` | 403 | `사용할 수 없는 계정입니다. 관리자에게 문의해 주세요.` | 관리자 여부 확인보다 먼저 체크 |
| 10 | 계정 상태 `WITHDRAWN` | 403 | 〃 | 〃 |
| 11 | 이메일·비밀번호·`is_admin=true`·`ACTIVE` 모두 정상 | 200 | `{"token": "...", "admin": {"account_id","email","display_name"}}` | `user_account.last_login_at` 갱신 + `audit_log`에 `action="OPS_LOGIN"` 기록 |
| 12 | 로그인 처리 도중 DB 연결 불가 | 503 | `데이터베이스 요청을 처리할 수 없습니다.` | db 컨테이너를 내려서 재현·확인함 |

### 1.2 `GET /api/ops/auth/me/`

| # | 입력·상황 | HTTP | 응답 `detail` | 비고 |
|---|---|---|---|---|
| 1 | `Authorization` 헤더 없음 | 401 | `자격 인증 데이터가 제공되지 않았습니다.` | DRF `IsAuthenticated`의 기본 메시지 — `LANGUAGE_CODE=ko-kr` 덕분에 자동으로 한글 렌더링됨(추가 코드 불필요) |
| 2 | `Authorization: Basic ...`(다른 스킴) | 401 | 〃 | 우리 인증 클래스가 `Bearer`가 아니면 그냥 넘어가고, 결국 미인증 처리 |
| 3 | `Authorization: Bearer`(토큰 파트 없음) | 401 | `인증 헤더 형식이 올바르지 않습니다.` | 공백으로 split했을 때 파트가 2개가 아님 |
| 4 | `Authorization: Bearer a b`(파트 3개) | 401 | 〃 | 〃 |
| 5 | 서명이 위조/손상된 토큰 | 401 | `유효하지 않은 인증 정보입니다.` | `django.core.signing.BadSignature` |
| 6 | 유효기간이 지난 토큰 | 401 | `로그인이 만료됐습니다. 다시 로그인해 주세요.` | `TOKEN_MAX_AGE_SECONDS`를 1초로 낮춰 실제 만료를 재현해 단위 테스트로 확인(2시간을 실시간으로 기다릴 수 없어 `apps.ops.tokens`를 직접 호출) |
| 7 | 서명은 정상인데 로그인 이후 계정이 `LOCKED`로 바뀜 | 401 | `관리자 권한이 해제됐거나 계정을 사용할 수 없습니다. 다시 로그인해 주세요.` | 매 요청 DB 재조회가 실제로 동작함을 확인(같은 토큰으로 상태 변경 전후 비교) |
| 8 | 서명은 정상인데 로그인 이후 `is_admin`이 회수됨 | 401 | 〃 | 〃 |
| 9 | 정상 토큰 | 200 | `{"account_id","email","display_name"}` | |
| 10 | 인증 재조회 도중 DB 연결 불가 | 503 | `데이터베이스 요청을 처리할 수 없습니다.` | ⚠️ 처음 구현 시 이 경로가 500(진단 traceback)으로 새는 버그가 있었음 — 2장 참고 |

### 1.3 `POST /api/ops/auth/logout/`

| # | 입력·상황 | HTTP | 비고 |
|---|---|---|---|
| 1 | 인증 실패(헤더 없음/형식 오류/위조/만료/권한없음) | 401 | 1.2절과 동일한 인증 매트릭스를 그대로 공유(`AdminView` 상속) |
| 2 | 정상 토큰 | 204 | `audit_log`에 `action="OPS_LOGOUT"` 기록 |
| 3 | 로그아웃 후 같은 토큰으로 다시 API 호출 | 200(그대로 통과) | **알려진 설계상 한계**: 서버에 세션을 두지 않는 구조(`apps/accounts/tokens.py`와 동일 설계)라 토큰 자체를 무효화할 수는 없다. 로그아웃은 "감사 로그에 기록을 남기는 것"과 "클라이언트가 들고 있는 토큰을 스스로 지우는 것"까지가 전부이고, 실제 접근 차단은 토큰 만료(2시간) 또는 관리자 권한 회수로만 가능하다. |

---

## 2. 섹션 2 — 운영 현황

### 2.1 `GET /api/ops/overview/`

읽기 전용, 입력값 없음. 인증 매트릭스는 1.2절과 완전히 동일(같은 `AdminView`/`OpsBearerTokenAuthentication` 사용).

| # | 입력·상황 | HTTP | 비고 |
|---|---|---|---|
| 1~8 | 인증 실패 케이스 전부 | 401 | 1.2절 표와 동일 |
| 9 | 정상 토큰 | 200 | 아래 2.2절 응답 구조 |
| 10 | 조회 도중 DB 연결 불가 | 503 | db 컨테이너를 내려서 재현·확인함 |

### 2.2 응답 구조와 실제 DB 매핑

```json
{
  "org_count": 9,
  "accounts": { "total": 2, "locked": 0, "duplicate_mapping": 0, "needs_review": 0 },
  "connectors": { "total": 0, "connected": 0, "expired": 0, "error": 0 },
  "invites": { "pending": 0, "expiring_today": 0 },
  "recent_activity": [
    { "audit_id": "AL012", "action": "OPS_LOGIN", "target_type": null, "target_id": null,
      "occurred_at": "2026-07-30T06:13:13.577244Z", "actor_display_name": "관리자", "actor_email": "rhksflwk@halil.com" }
  ]
}
```

값이 어디서 나오는지(하드코딩 없이 전부 실시간 SQL 집계 — `backend/db/repositories.py`의 `OpsOverviewRepository.summary()`):

| 필드 | 산출 방식 |
|---|---|
| `org_count` | `SELECT count(*) FROM org WHERE status='ACTIVE'` |
| `accounts.total` | `SELECT count(*) FROM user_account` |
| `accounts.locked` | 위 중 `account_status='LOCKED'` |
| `accounts.duplicate_mapping` | `user_person_link`에서 `mapping_status='VERIFIED'`인 링크가 계정 1개당 2개 이상인 계정 수(스키마상 한 계정이 여러 PERSON에 연결되는 걸 막지 않음 — `repositories.py`의 `_linked_person()` 주석 참고) |
| `accounts.needs_review` | `locked`이거나 `duplicate_mapping`인 계정의 합집합(중복 집계 없이) |
| `connectors.*` | `connector_conn`을 `auth_status`(`CONNECTED`/`EXPIRED`/`ERROR`)로 집계 |
| `invites.pending` | `member_invite`에서 `status='PENDING' AND expires_at > now()` |
| `invites.expiring_today` | 위 조건에 `expires_at::date = CURRENT_DATE` 추가 |
| `recent_activity` | `audit_log` 최신 5건 + `user_account.display_name`/`email` LEFT JOIN |

프론트엔드(`OpsOverviewPage.tsx`)는 이 숫자만 받아서 화면을 그린다 — "오늘 확인할 일" 카드도 `accounts.needs_review`/`connectors.expired+error`/`invites.expiring_today`가 0보다 클 때만 동적으로 만들어지고, 하나도 없으면 "확인이 필요한 항목이 없습니다."를 보여준다. 예전 목업처럼 "제품전략팀", "직원 18" 같은 특정 이름이 박힌 카드는 없다(그 정보는 아직 없는 연결 조직/계정 관리 섹션의 상세 데이터라 지금은 만들 수 없음).

계정·연결서비스 총합이 0일 때 막대그래프 퍼센트가 `NaN%`이 되지 않도록 `pct(part, total)`가 `total === 0`이면 `0`을 반환하도록 처리했고, `accounts.total === 0`/`connectors.total === 0`일 때는 막대 대신 "등록된 계정이 없습니다."/"연결된 서비스가 없습니다." 문구로 대체한다.

---

## 3. 테스트 중 발견하고 수정한 버그

**증상**: `db` 컨테이너가 완전히 죽어서 접속 자체가 안 되는 상황(단순 쿼리 실패가 아니라 `psycopg.OperationalError: failed to resolve host`)에서, `/auth/me/`·`/auth/logout/`·`/overview/`처럼 `AdminView`를 쓰는 모든 엔드포인트가 503이 아니라 **500(Django 진단 traceback)**을 반환했다.

**원인**: `OpsBearerTokenAuthentication.authenticate()`가 매 요청마다 관리자 권한을 재확인하려고 `AccountRepository.find_credentials_by_id()`를 호출하는데(1.2절 인증 매트릭스의 핵심 기능), 이 호출에 `try/except`가 없었다. DRF는 인증 단계에서 발생한 `AuthenticationFailed` 계열 예외만 정해진 상태코드로 변환하고, `psycopg.OperationalError` 같은 임의의 예외는 그대로 흘려보내 Django 기본 에러 처리(500)로 떨어진다. `LoginView`(`POST /auth/login/`)는 인증이 필요 없는 뷰라 이 코드 경로를 타지 않아서 처음부터 503이 정상 동작했었다 — 그래서 로그인은 되는데 로그인 이후 화면들만 500이 나는 형태로 드러났다.

**수정**: `backend/api_errors.py`에 `ServiceUnavailable`(DRF `APIException`, `status_code=503`, 기본 메시지 `데이터베이스 요청을 처리할 수 없습니다.`)를 추가하고, `apps/ops/authentication.py`의 그 DB 조회를 `try/except psycopg.Error: raise ServiceUnavailable()`로 감쌌다. `Response`를 직접 만들 수 없는 인증 클래스 안에서도 DRF 예외 처리 파이프라인을 통해 깔끔한 503 JSON으로 렌더링된다.

**재검증**: db 컨테이너를 내렸다 올리면서 `/auth/login/`, `/auth/me/`, `/overview/` 세 엔드포인트 모두 503 + 동일한 한글 메시지로 응답하는 것을 확인했고, db 복구 후 정상 200 응답도 다시 확인했다.

---

## 4. 실행해 본 검증 절차 요약

1. `docker compose -f infra/docker/docker-compose.yml up -d`로 db/web/frontend 기동.
2. `POST /api/auth/signup/`으로 테스트 계정 생성 → `grant_admin.py`로 관리자 지정 → `POST /api/ops/auth/login/` 성공 확인.
3. 위 1·2장의 표에 있는 모든 케이스를 `curl`로 하나씩 재현(비밀번호 오류, 미가입 이메일, 잠금/탈퇴 계정, 비관리자 계정, 헤더 누락/형식 오류/위조 토큰, 로그인 중 권한·상태 변경 후 같은 토큰 재사용 등).
4. 토큰 만료는 실시간 2시간을 기다릴 수 없어 `apps.ops.tokens.TOKEN_MAX_AGE_SECONDS`를 1초로 낮춘 별도 스크립트로 단위 검증.
5. `db` 컨테이너를 직접 멈춰서 503 경로를 재현 → 3장의 버그 발견·수정 → 재현 케이스 재실행으로 수정 확인.
6. 프론트엔드 소스(`OpsOverviewPage.tsx`, `OpsLoginPage.tsx`, `api/ops.ts`, `api/opsOverview.ts`)에 예전 목업 숫자(89, 86, 96.6% 등)나 `opsMockData` 참조가 남아있지 않은지 grep으로 확인.
7. `tsc --noEmit`(프론트) / `manage.py check`(백엔드) 통과 확인.
8. 테스트로 만든 임시 계정·데이터는 정리하고, 실제 관리자 계정(`rhksflwk@halil.com`)과 실제 감사 로그 기록은 남겨둠.

---

## 5. 관련 파일

| 구분 | 경로 |
|---|---|
| 인증/토큰 | `apps/ops/authentication.py`, `apps/ops/tokens.py` |
| 뷰 | `apps/ops/views/login.py`, `apps/ops/views/overview.py` |
| URL | `apps/ops/api_urls.py`, `config/urls.py` |
| Repository | `backend/db/repositories.py`(`OpsOverviewRepository`), `backend/db/audit.py`, `backend/db/__init__.py` |
| 공용 에러 처리 | `backend/api_errors.py`(`to_response`, `ServiceUnavailable`) |
| 관리자 부여 스크립트 | `backend/services/createDB/grant_admin.py` |
| 스키마 | `DB/schema.sql`(`user_account.is_admin`) |
| 프론트 API | `frontend/src/api/ops.ts`, `frontend/src/api/opsClient.ts`, `frontend/src/api/opsOverview.ts` |
| 프론트 화면 | `frontend/src/pages/OpsLoginPage/OpsLoginPage.tsx`, `frontend/src/pages/OpsOverviewPage/OpsOverviewPage.tsx`, `frontend/src/components/OpsLayout/OpsLayout.tsx` |
| 프론트 세션 | `frontend/src/utils/opsSession.ts` |
| 공용 유틸 | `frontend/src/utils/relativeTime.ts`(`timeAgo` — 감사 로그 섹션에서도 재사용 예정) |
