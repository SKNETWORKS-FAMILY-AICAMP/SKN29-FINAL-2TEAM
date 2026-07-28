# React 프론트엔드 베이스

이 폴더는 React + Vite + TypeScript 실행 환경과 백엔드 API 클라이언트를 제공한다.

- 화면 컴포넌트, HTML, CSS는 Figma 담당 팀원이 구현한다.
- API 주소는 `VITE_API_BASE_URL`로 관리한다.
- 백엔드 계약은 `docs/0_개발환경/로컬_Docker_개발환경_설치_매뉴얼.md`를 따른다.

## 실행 방법

```bash
npm install
npm run dev
```

`npm run dev` 실행 후 `/` 로 접속하면 변환된 14개 화면 전체 목록(그룹별)이 나온다. 각 화면을 클릭해서 확인한다.

## 구조

```
src/
  api/           — 백엔드 API 클라이언트 (http.ts, types.ts)
  styles/
    tokens.css   — 색상/라운드/그림자/spacing 등 디자인 토큰 (CSS 변수)
    global.css   — 리셋 스타일
  components/    — 공통 컴포넌트 (Button, Badge, Input, Select, Checkbox,
                   ToggleSwitch, Card, Modal, TopNav, StepIndicator, Toast, Icon)
  pages/         — 화면별 페이지 컴포넌트 (14개, 폴더당 1개씩)
  routes.ts      — 전체 라우트 목록 + 메인 앱 상단 탭 정의
  App.tsx        — react-router 라우팅 + 화면 목록 홈
```

## 화면 목록 (라우트)

| 그룹 | 라우트 | 원본 HTML |
|---|---|---|
| 인증 | `/login` | login.html |
| 인증 | `/signup` | signup.html |
| 인증 | `/find-password` | find-password.html |
| 온보딩 | `/onboarding/connectors` | connector-onboarding.html |
| 온보딩 | `/onboarding/folders` | folder-select.html |
| 온보딩 | `/onboarding/folder-roles` | folder-role-assignment.html |
| 온보딩 | `/onboarding/jira-project` | jira-project-select.html |
| 메인 | `/dashboard` | main-dashboard.html |
| 메인 | `/files/new` | new-files.html |
| 메인 | `/projects` | project-list.html |
| 메인 | `/workspace` | workspace.html |
| 업무 분배 | `/tasks/distribution` | task-distribution.html |
| 업무 분배 | `/tasks/recommendation` | task-recommendation.html |
| 업무 분배 | `/tasks/result` | assignment-result.html |

화면들은 아직 `src/api`의 백엔드 클라이언트를 호출하지 않고 목업 데이터로 동작한다. React용 로그인/인증 방식이 정해지면 순차적으로 실 API 연동으로 교체한다.

## 스타일링

Tailwind 없이 CSS Modules + CSS 변수(`tokens.css`)만 사용한다. 새 컴포넌트를 만들 때는 `tokens.css`에 이미 있는 변수를 재사용하고, 없는 값이 필요하면 토큰을 먼저 추가한 뒤 사용한다.
