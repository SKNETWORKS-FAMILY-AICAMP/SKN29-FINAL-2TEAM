# halil React 프론트엔드

이 폴더는 Figma HTML 목업 14개를 React + Vite + TypeScript 화면으로 옮긴 실제 프론트엔드 코드다.

- `figma-export`는 디자인 비교용 원본이며, 서비스 화면 수정은 이 폴더에서 한다.
- 프로젝트·People 화면의 기본 모드는 기존 백엔드 API를 호출한다.
- API 계약이 없는 기능은 성공으로 위장하지 않고 `DEMO`, `PARTIAL`, `BLOCKED`로 구분한다.
- 최신 화면별 상태와 외부 의존사항은 루트의 `프론트엔드_MVP_진행기록.md`를 따른다.

## 실행 방법

```powershell
docker compose -f infra/docker/docker-compose.yml up -d
```

`http://localhost:5173/screens`에 개발용 화면 목록이 있다(`/`는 랜딩이다).

- 홈(로그인 후 랜딩): `/chat`
- 연결·설정: `/settings/connectors`
- 실제 API 상태 확인: `/projects`

의존성을 다시 설치해야 할 때는 프론트 컨테이너 안에서 실행한다.

```powershell
docker compose -f infra/docker/docker-compose.yml exec frontend npm ci
```

## 구조

```
src/
  api/           — 백엔드 API 클라이언트 (http.ts, types.ts)
  styles/
    tokens.css   — 색상/라운드/그림자/spacing 등 디자인 토큰 (CSS 변수)
    global.css   — 리셋 스타일
  components/    — 공통 컴포넌트 (Button, Badge, Input, Select, Checkbox,
                   ToggleSwitch, Card, Modal, AppShell, StepIndicator, Toast, Icon)
                   ※ `TopNav`는 사용처가 0이다 — `SettingsLayout`의 죽은
                     비-embedded 분기에만 남아 있다(4차 단계 2 기록)
  pages/         — 화면별 페이지 컴포넌트 (25개 디렉터리)
  routes.ts      — 전체 라우트 목록 + 메인 앱 상단 탭 정의
  App.tsx        — react-router 라우팅 + 화면 목록 홈
```

## 화면 목록 (라우트)

> 2026-08-11 갱신. **정본은 `src/routes.ts`의 `PATHS`다** — 이 표는 읽기용
> 사본이라 어긋나면 `routes.ts`가 맞다.

| 그룹 | 라우트 | 비고 |
|---|---|---|
| 마케팅 | `/` | 랜딩 (4차 단계 1에서 전면 재작성) |
| 인증 | `/login` `/signup` `/invite-code` `/find-password` `/reset-password` | 로그인·가입 뒤는 전부 `/chat` |
| Agent Platform | `/chat` | **홈** |
| Agent Platform | `/agents` `/agents/new/edit` `/agents/:agentId/edit` | Builder |
| Agent Platform | `/documents` | 팀 문서 상태 |
| 설정 | `/settings/team` `/settings/connectors` `/settings/mcp` `/settings/model` `/settings/permissions` | 탭 컨테이너 하나(`SettingsPage`) |
| 메인 (구) | `/files/new` `/projects` `/projects/:projectId` | 5차 단계 3에서 AppShell로 이식 |
| 운영자 콘솔 | `/ops/login` `/ops` 외 6종 | 별도 로그인 |
| 개발용 | `/screens` `/dev/screens` | 화면 목록 |

**없어진 라우트** (직접 열면 `path="*"`에 걸려 랜딩으로 간다):
`/dashboard`(4차 단계 2 · Q13) · `/onboarding/connectors` `/onboarding/folders`
`/onboarding/jira-project`(5차 단계 4) · `/tasks/extraction`
`/tasks/distribution/documents`(4차 단계 3) · `/workspace` `/tasks/distribution`
`/tasks/recommendation` `/tasks/result`(8/10, 정적 4종).

프로젝트와 People 화면은 기본 경로에서 `src/api`의 클라이언트를 사용한다. 현재 보호 API에는 React 인증 계약이 없어 인증 실패가 발생할 수 있으며, 이 경우 화면은 차단 사유와 명시적인 데모 진입 경로를 표시한다. 나머지 파일·분석·추천·승인 기능은 담당 API가 준비될 때까지 데모 또는 차단 상태다.

People DB에는 근무일정·휴가·스킬·외부 계정 구조가 정의되어 있지만 현재 `/api/people/` 응답에는 가용시간·휴가·현재 Jira 업무량이 포함되지 않는다. 프론트에서 이를 추측하지 말고 해당 계약이 제공될 때까지 실제 업무 분배를 차단한다.

## 스타일링

Tailwind 없이 CSS Modules + CSS 변수(`tokens.css`)만 사용한다. 새 컴포넌트를 만들 때는 `tokens.css`에 이미 있는 변수를 재사용하고, 없는 값이 필요하면 토큰을 먼저 추가한 뒤 사용한다.
