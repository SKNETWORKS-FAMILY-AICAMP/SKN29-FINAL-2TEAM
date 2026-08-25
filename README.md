# halil · 프로젝트 운영 Agent Platform

> 팀에 필요한 AI 에이전트를 **코딩 없이** 만들어 쓰는 플랫폼.
> 무슨 일을 하는지, 무엇을 참고할지, 어떤 도구를 쓸지 적으면 팀 전체가 쓰는 에이전트가 됩니다.

팀이 이미 쓰는 도구(Google Drive · Jira · 인사 시스템)를 연결해 두면, 대화로 물어보고
승인 한 번으로 실제 반영까지 갑니다. 두 가지를 끝까지 지킵니다 —
**모든 답에는 원문 근거가 붙고, 실제로 무언가를 바꾸는 일은 사람의 승인을 거칩니다.**

---

## 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [서비스 흐름](#2-서비스-흐름)
3. [팀 소개](#3-팀-소개)
4. [주요 기능](#4-주요-기능)
5. [기술 스택](#5-기술-스택)
6. [시스템 아키텍처](#6-시스템-아키텍처)
7. [에이전트 실행 흐름](#7-에이전트-실행-흐름)
8. [데이터 구조](#8-데이터-구조)
9. [실행 방법](#9-실행-방법)
10. [한계와 개선 방향](#10-한계와-개선-방향)
11. [팀원 회고](#11-팀원-회고)

---

## 1. 프로젝트 개요

| | |
|---|---|
| **프로젝트명** | halil · 프로젝트 운영 Agent Platform |
| **개발 기간** | 2026.07.20 ~ 2026.08.13 (4주) |
| **팀** | SKN29기 Final 2팀 (5인) |
| **대상** | 문서와 이슈 트래커를 쓰지만, 그것을 이어 붙일 도구는 없는 실무 팀 |

### 무엇이 문제였나

팀의 정보는 이미 흩어진 채로 다 있습니다. 기획서는 Drive에, 업무는 Jira에, 누가 무엇을
할 줄 아는지는 인사 시스템에 있습니다. 그런데 **「이 기획서로 할 일을 뽑아서, 여유 있는
사람에게, Jira에 올려 줘」** 한 문장을 처리하려면 사람이 세 시스템을 오가며 옮겨 적어야
합니다.

일반 AI 챗봇은 이 일을 못 합니다. 우리 문서를 모르고, 우리 팀을 모르고, Jira에 쓰지도
못하기 때문입니다.

### 어떻게 풀었나

- **연결한다** — Drive·Jira·인사 시스템을 팀 계정으로 연결하면 그때부터 근거가 됩니다.
- **좁힌다** — 「회의록 정리」는 문서만 봅니다. 에이전트의 본질은 할 수 있는 일을 좁히는
  것이고, 그 좁힘을 코딩 없이 세 칸(설명·지시문·도구)으로 정합니다.
- **보여준다** — 답에는 그 문장이 나온 원문 문단이 붙습니다.
- **멈춘다** — Jira 등록처럼 바깥을 바꾸는 도구는 확인 카드를 띄우고 승인 전까지 실행하지
  않습니다.

> 「AI가 알아서 배정해 준다」가 아니라 **사람이 결정하고, 그 결정의 근거가 남는다**는
> 쪽에 섰습니다.

---

## 2. 서비스 흐름

```mermaid
flowchart LR
    A["① 도구 연결<br/>Drive · Jira · 인사"] --> B["② 문서 등록<br/>파싱 · 청킹 · 임베딩"]
    B --> C["③ 에이전트 준비<br/>기본 제공 또는 직접 제작"]
    C --> D["④ 대화로 요청"]
    D --> E["⑤ 에이전트가 도구 호출<br/>문서 검색 · 팀원 조회 · 부하 계산"]
    E --> F["⑥ 근거와 함께 답변"]
    F --> G{"⑦ 바깥을 바꾸는 일인가"}
    G -- 아니오 --> H["끝"]
    G -- 예 --> I["⑧ 확인 카드 → 사람이 승인"]
    I --> J["⑨ Jira 등록 등 실제 반영"]
```

---

## 3. 팀 소개

| 이름 | GitHub | 주로 맡은 곳 |
|---|---|---|
| *(이름)* | [@Somber-7](https://github.com/Somber-7) | PM · 화면 전반 · 에이전트 하네스 · 운영자 콘솔 |
| *(이름)* | [@SoungJuyeon](https://github.com/SoungJuyeon) | 운영자 콘솔(`apps/ops`) · 설계 문서 |
| *(이름)* | [@Jihun](https://github.com/Jihun105) | 화면 구현 · 에이전트 빌더 |
| *(이름)* | [@Juneok](https://github.com/Juneok) | 화면 구현 |
| *(이름)* | *(계정)* | 문서 파이프라인 · 업무 추출 |

> 담당 열은 **커밋 이력에서 뽑은 초안**입니다(`git log --author`). 이름·계정·역할 표기는
> 각자 확인해서 채워 주세요.

---

## 4. 주요 기능

### 4.1 대화 (`/chat`)

무엇이든 말하면 됩니다. 플랫폼의 정문 역할을 하는 에이전트가 받아, 그 일에 더 맞는 팀
에이전트가 있으면 넘깁니다. 답변에는 근거 문단이 카드로 붙습니다.

### 4.2 에이전트 만들기 (`/agents`)

코딩 없이 **세 가지**만 정합니다 — 무슨 일을 하는지(설명), 어떻게 답하는지(지시문),
무엇을 쓸 수 있는지(도구). 저장 전에 두 단계를 거칩니다.

- **검증** — 지시문이 도구와 어긋나지 않는지, 설명이 실제 하는 일과 맞는지 확인하고 고쳐 씁니다.
- **시험 실행** — 실제로 한 번 돌려 봅니다. 바깥을 바꾸는 도구는 부르지 않고 **시뮬레이션**으로 표시합니다.

### 4.3 커넥터 (`/settings/connectors`)

세 자리를 채웁니다 — 인사 시스템 · 문서 저장소 · 업무 기록소. Drive와 Jira는 OAuth로
연결하고, 연결 후 읽을 폴더를 고릅니다. Jira 프로젝트는 연결 즉시 전부 자동 등록됩니다.

### 4.4 문서 파이프라인

Drive 원문을 가져와 파싱 → 청킹 → 임베딩까지 처리하고 pgvector에 넣습니다. 임베딩은
GPU가 필요해 **RunPod 워커**가 별도로 돌고, 진행 상황은 화면이 단계별로 보여줍니다.

### 4.5 업무 추출과 등록

기준 문서에서 할 일을 뽑아 제목·역할·공수·마감일로 정리합니다. **근거가 확인되지 않은
업무는 빼고, 뺐다는 사실을 말합니다.** 등록은 확인 카드 승인 후 우리 DB에 먼저 남고,
Jira 등록은 그다음입니다.

### 4.6 에이전트가 쓰는 도구 16종

| 갈래 | 도구 |
|---|---|
| 문서 | `document_search` · `document_list` · `document_sync` |
| 사람 | `people_list` · `absence_list` · `workload_report` |
| 업무 | `task_extraction` · `task_list` · `task_update` · `task_register` |
| 프로젝트 | `project_list` |
| 외부 | `jira_get_issues` · `jira_create_issues` · `web_search` |
| 일반 | `get_current_datetime` — 상대적 날짜(「이번 주 금요일」 등)를 등록 도구에 넘기기 전 오늘 날짜를 확인한다 |
| 스킬 | `skill_register` — 반복하는 일을 스킬로 저장한다 |

이 중 **`task_update` · `task_register` · `jira_create_issues` · `skill_register`
넷이 승인 게이트**를 탑니다. 여기에 팀이 요청해 운영자가 등록한 **커스텀 도구**가
더해지고, 그쪽은 우리가 내용을 모르므로 **전부** 승인 게이트를 탑니다.

### 4.7 운영자 콘솔 (`/ops`)

일반 로그인과 **완전히 분리된 별도 로그인**입니다. 토큰 서명 salt가 다르고, 매 요청마다
DB에서 `is_admin`과 계정 상태를 다시 확인합니다.

| 화면 | 하는 일 |
|---|---|
| 운영 현황 | 오늘 확인할 숫자 |
| 팀 현황 | 팀별 상태, 팀이 만든 에이전트·실행 기록, 소유자 이전 |
| 계정 관리 | 정지·재활성·직원 연결 해제·운영자 권한 부여 |
| 계정 연결·초대 | 모든 팀의 초대 조회와 정리 |
| 연결 서비스 | Drive·Jira 연결 상태와 **강제 해제** |
| 모델 등록 | 팀이 요청한 커스텀 모델을 우리가 등록. 팀별 기본 채팅 모델도 여기서 |
| 커스텀 도구 | 팀이 요청한 MCP·FastAPI 도구를 우리가 등록·연결 확인 |
| 가드레일 | 입력 검사 정책 |
| 사용량 | 팀별 실행·토큰 사용량 |
| 감사 로그 | 누가 무엇을 왜 했는가 |
| 전역 정책 | 초대 만료 기간, 시스템 공지 |

**고객의 대화 내용과 문서 원문은 운영자도 보지 않습니다.** 파괴적 조치 아홉 개는 사유를
함께 기록합니다.

---

## 5. 기술 스택

| 영역 | 기술 |
|---|---|
| **Frontend** | React 19 · TypeScript · Vite · CSS Modules · React Router |
| **Backend** | Python 3.13 · Django 5 · Django REST Framework |
| **Database** | PostgreSQL 17 · pgvector |
| **DB 접근** | psycopg 3 직접 SQL (ORM 미사용) |
| **LLM** | OpenAI · Anthropic · Google Gemini (팀별 커스텀 모델 등록 가능) |
| **임베딩** | RunPod GPU 워커 |
| **외부 연동** | Google Drive API · Jira REST API (OAuth 2.0) · MCP |
| **인프라** | Docker Compose · AWS (RDS · EC2) |

**Django ORM·Migration·Admin·기본 Auth 테이블을 쓰지 않습니다.** 스키마는
`DB/schema.sql` 한 곳에서 관리하고, 데이터 접근은 `backend/db/`의 psycopg Repository가
전담합니다. 인증도 `user_account` 기준으로 직접 구현했습니다.

---

## 6. 시스템 아키텍처

```mermaid
flowchart TB
    subgraph FE["Frontend · React + Vite"]
        F1["대화"] --- F2["에이전트 빌더"] --- F3["설정 · 커넥터"] --- F4["운영자 콘솔"]
    end

    subgraph BE["Backend · Django + DRF"]
        A1["apps/chat"]
        A2["apps/agents"]
        A3["apps/connectors"]
        A4["apps/projects"]
        A5["apps/ops"]
    end

    subgraph SV["services · 도메인 로직"]
        S1["agent_runtime<br/>실행 루프 · 미들웨어 · 메모리 · 위임"]
        S6["harness<br/>도구 레지스트리 16종"]
        S2["agent_builder<br/>검증 · 시험 실행"]
        S3["document_pipeline"]
        S4["task_extraction"]
        S5["workload"]
    end

    subgraph DB["PostgreSQL 17 + pgvector"]
        D1["public<br/>계정 · 팀 · 프로젝트 · 문서 · 에이전트"]
        D2["mock_hr<br/>조직 · 직원 (읽기 전용)"]
    end

    EXT["Google Drive · Jira · MCP 서버"]
    GPU["RunPod GPU 워커<br/>파싱 · 청킹 · 임베딩"]

    FE --> BE --> SV
    SV --> D1
    SV -. 어댑터로만 읽는다 .-> D2
    A3 <--> EXT
    S3 --> GPU --> D1
```

`mock_hr`는 **고객사 HR 시스템 자리**입니다. 우리가 쓰지 않고 읽기만 하며, 애플리케이션
코드에 쓰기 경로가 아예 없습니다.

---

## 7. 에이전트 실행 흐름

```mermaid
sequenceDiagram
    participant U as 사용자
    participant C as Chat
    participant H as agent_runtime
    participant M as LLM
    participant T as 도구

    U->>C: "이번 주 마감인 업무 알려줘"
    C->>H: 실행 시작 (에이전트 · 도구 목록)
    loop 반복 상한까지
        H->>M: 대화 + 쓸 수 있는 도구
        M-->>H: 도구 호출 요청
        alt 승인이 필요한 도구
            H-->>U: 확인 카드
            U-->>H: 승인
        end
        H->>T: 실행
        T-->>H: 결과 (원본이 아니라 요약)
        H->>M: 결과 전달
    end
    M-->>C: 최종 답변
    C-->>U: 답변 + 근거 문단
```

실행 기록(`agent_run` · `tool_call`)에는 **내용이 아니라 요약만** 남습니다. 무엇을 언제
돌렸고 어떤 도구가 실패했는지는 남고, 대화와 문서 원문은 남지 않습니다.

---

## 8. 데이터 구조

전체 63개 테이블입니다. 핵심만 추리면:

```mermaid
erDiagram
    team ||--o{ user_account : "소속"
    team ||--o{ team_member : "명부"
    team ||--o{ agent : "만든 에이전트"
    team ||--o{ team_folder : "읽을 Drive 폴더"
    user_account ||--o{ connector_conn : "연결한 도구"
    proj ||--o{ proj_source : "대응 Jira 프로젝트"
    proj ||--o{ task : "업무"
    doc ||--o{ doc_block : "블록"
    doc_block ||--o{ chunk : "청크"
    chunk ||--o{ vec_idx : "임베딩"
    agent ||--o{ agent_tool : "쓸 수 있는 도구"
    agent ||--o{ agent_run : "실행"
    agent_run ||--o{ tool_call : "도구 호출"
```

| 경계 | 어떻게 |
|---|---|
| **테넌트** | `team`. 계정·프로젝트·문서·에이전트가 전부 팀에 매달립니다 |
| **HR 데이터** | `mock_hr` 스키마로 분리. `backend/services/hr/` 어댑터만 읽습니다 |
| **참조 무결성** | FK를 걸지 않고 `VARCHAR(5)` 코드로 관리합니다. 대상이 사라진 링크를 화면이 죽지 않고 표시하도록 모든 조회가 처리합니다 |

---

## 9. 실행 방법

### 1) 환경 파일

```powershell
Copy-Item .env.example .env
```

`DATABASE_URL`과 커넥터 자격증명을 채웁니다. 로컬 컨테이너를 쓸 때 DB 호스트는
`127.0.0.1`이 아니라 **`db`** 입니다.

### 2) 컨테이너 기동

```powershell
docker compose -f infra/docker/docker-compose.yml up --build
```

### 3) People 목업 데이터 적재 (최초 1회)

```powershell
Get-Content -Raw DB/peopleDB/peopledb_mock.sql | docker compose -f infra/docker/docker-compose.yml exec -T db psql -U project_copilot -d project_copilot
```

### 4) 확인

- API 상태 — `http://127.0.0.1:8000/api/health/`
- 화면 — `http://127.0.0.1:5173/`

### 테스트

호스트에서 돌립니다. `.env`의 `DATABASE_URL`은 컨테이너 안 이름이라 그대로 쓰면 DB에
닿는 테스트가 깨집니다.

```powershell
$env:DATABASE_URL="postgresql://project_copilot:project_copilot@localhost:5432/project_copilot"; python manage.py test tests
```

```powershell
cd frontend; npm run build
```

자세한 설치 절차는 `docs/설계 및 구현/중간발표 이후/개발환경/로컬_Docker_개발환경_설치_매뉴얼.md`에 있습니다.

---

## 10. 한계와 개선 방향

### 지금의 한계

| 한계 | 내용 |
|---|---|
| **인사 시스템은 목업이다** | Workday API는 결제한 기업 고객만 쓸 수 있어 같은 모양의 DB(`mock_hr`)로 대신합니다. 경계를 코드와 스키마로 분리해 두어 실제 HR로 바꿔도 어댑터만 갈면 됩니다 |
| **업무 배정 추천은 하지 않는다** | 초기 기획이었지만 **근거 없이 사람을 고르는 기능**이 되기 쉬워 접었습니다. 부하 계산까지만 하고 판단은 사람이 합니다 |
| **문서 형식 제한** | 파싱이 지원하는 형식만 등록됩니다. 미지원 파일은 성공으로 위장하지 않고 그대로 표시합니다 |
| **임베딩이 외부 GPU에 의존** | RunPod 워커가 죽으면 문서 등록이 멈춥니다. 대기열 상태를 화면이 보여주지만 자동 복구는 없습니다 |
| **커넥터가 계정 단위** | 연결한 사람이 팀을 떠나면 그 연결도 끊깁니다. 운영자가 강제 해제는 할 수 있지만 이전은 못 합니다 |

### 개선 방향

1. 실제 HR 커넥터(Workday·사내 시스템) 어댑터 추가
2. 커넥터를 계정이 아니라 팀 소유로 옮겨 담당자 변경에 견디게 하기
3. 문서 갱신 감지 — 지금은 등록 시점의 스냅샷이라 원문이 바뀌어도 모릅니다
4. 에이전트 실행 비용·지연 시간 표시(토큰은 이미 기록 중)
5. 스키마에 남은 미사용 테이블 15개 정리 — 폐기된 추천 파이프라인의 자리입니다
6. 운영자 콘솔의 조치에 되돌리기(undo) 추가

---

## 11. 팀원 회고

| 이름 | 회고 |
|---|---|
| *(이름)* | *(작성 예정)* |

---

## 문서

- 화면·API가 실제로 어떻게 동작하는가 — `docs/설계 및 구현/중간발표 이전/코드설명/`
- 왜 그렇게 만들었는가 — `docs/설계 및 구현/중간발표 이전/설계/`, `docs/참고자료/`
- 무엇을 만들기로 했는가 — `docs/설계 및 구현/중간발표 이후/설계/`
- 작업 기록 — `docs/작업기록/`
