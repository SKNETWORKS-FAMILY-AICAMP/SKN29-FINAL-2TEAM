# MCP 실행 구조 설계 v1

> **⚠ 8/11 구현 결과로 §1·§5가 C안으로 대체됨** (구현: `c02d940`·`cac1c6c`).
> 발견 2건: ①B안(자체 서버를 같은 호스트 별도 프로세스로)은 §4-1 SSRF 차단과
> 자기모순 — 등록 플로우가 localhost·사설 대역을 막는다 ②공식 Atlassian MCP는
> OAuth 액세스 토큰 요구(실측 401) — 정적 토큰 모델로는 만료 후 끊김.
> **C안 확정**: Jira 등록·조회는 내장 tool(`jira_create_issues` 부분 실패 반환·
> 사전 검증·순번 복원, `side_effect=true` 승인 게이트), MCP는 사용자 확장
> 경로로 유지(§2~§4·§6·§7은 그대로 유효하며 구현 완료). 남은 미결 = MCP용
> OAuth 지원 여부(질문지 Q16).

> 2026-08-11 작성. Priority 4(멘토링 §10~11)의 구현 전 설계. 근거:
> 아키텍처 §4, opencode_분석 §8(MCP = 외부 Tool 공급 경로, Client/Adapter),
> Deep-Agent_활용_설계_정리 §4(보안 경계 미해결 제기), E2E STEP 7~8.

## 0. 이 설계가 증명해야 하는 것 (8/11 PM 프레임 확정)

> **핵심은 "어느 Jira MCP를 쓰느냐"가 아니라 "처음 보는 커스텀 MCP 서버를
> 붙일 수 있느냐"다.** 멘토링 §9: 기업이 이미 운영하는 MCP Server를 연결해
Agent가 쓰게 해주는 것이 플랫폼의 역할이다.

그래서 수용 기준이 이렇게 된다:

1. **특권 경로 금지** — 우리가 만드는 자체 Jira MCP도 코드 내부 하드코딩이
   아니라 **외부 서버와 똑같은 등록 폼(URL+토큰)으로만** 접속한다. 이게
   깨지면 "통합"이지 "플랫폼"이 아니다.
2. **일반 경로 증명** — 등록 → tool 목록 자동 발견 → Builder 체크 → Chat에서
   실행. 이 4단계가 서버 종류와 무관하게 동작하는 것이 데모의 증명 포인트.
3. **(여력) 라이브 등록 시연** — 발표 자리에서 미리 안 보여준 두 번째 MCP
   서버(또는 공개 서버 하나)를 그 자리에서 등록해 tool이 잡히는 것까지
   보여주면 플랫폼 주장이 완성된다.

자체 Jira MCP(§5)는 이 관점에서 "우리가 만든 도구"가 아니라 **"고객사가
자기 API를 감싼 커스텀 MCP"의 대역**으로 시연하는 것이다.

## 0-1. 원칙

1. MCP는 Harness의 일부가 아니라 **외부 Tool 공급 경로**다(준억 분석 §8).
   Harness 쪽 접점은 Tool Registry 하나 — MCP Tool도 내장 Tool과 같은
   인터페이스로 등록된다.
2. 우리는 MCP 제품을 만드는 게 아니다. 필요한 것은 **등록 → tool 목록 조회 →
   호출 → 로그** 4가지뿐(멘토링 §10의 최소 범위).
3. 행동(side effect)은 반드시 승인 게이트 뒤에서만 — 확인 카드 승인 전 MCP
   호출 없음(E2E STEP 6→7 순서 고정).

## 1. 핵심 결정 — 데모 대표 서버: 자체 Jira MCP 래핑 (제안)

| | A. 공식 Atlassian Remote MCP | B. 자체 Custom MCP (기존 Jira REST 래핑) |
|---|---|---|
| 구현 비용 | 없음 | 작음 — tool 3개 (FastMCP류로 1~2일) |
| 인증 | OAuth 2.1 브라우저 흐름 신규 — 데모 리스크 추가 | **기존 Connector의 Jira 인증 재사용** |
| Tool 적합성 | 목록이 우리 요구와 다를 수 있음 (벌크 생성·사전 검증) | E2E에 딱 맞게 설계 가능 — 실패 사유(필수 필드 누락)를 우리가 만들어 반환 |
| 통제력 | rate limit·스키마 변경 통제 불가 | 데모 통제 가능 |
| 발표 스토리 | "표준 생태계 연결" | **"기업 API를 MCP로 감싸 Agent가 행동한다" = 멘토링 §11이 명시한 경로** |

**제안: B를 기본, A는 여력 시 검증용.** 단 플랫폼 구조는 특정 서버에 묶지
않는다 — 설정 화면의 "임의 MCP Server 등록"(Figma MCP 탭에 이미 반영)은 A·B
어느 쪽이든 같은 폼으로 등록된다. 즉 **구조는 범용, 데모 서버는 자체 제작**.
→ 멘토링에서 확인 (Q16으로 등재).

## 2. 데이터 모델 (스키마 초안 구체화)

```
mcp_server   id · team_id · name · endpoint_url · auth_token(암호화) ·
             status(CONNECTED/ERROR/UNCHECKED) · last_checked_at · created_by
mcp_tool     id · server_id · name · description · input_schema(JSON) ·
             enabled · discovered_at        ← 연결 테스트 시 list_tools로 채움
agent_tool   (기존 초안) tool_ref = 내장 tool 식별자 or mcp_tool.id
tool_call    (기존 초안) + error_code 열 — 실패 사유 집계용 (429·401·validation)
```

## 3. 흐름

**등록 (Settings > MCP)**: URL·토큰 입력 → 연결 테스트(initialize+list_tools)
→ tool 목록 저장·표시 → status 갱신. 실패 시 저장은 하되 ERROR 표시(Figma의
"연결 상태가 나쁘면 편집 화면에서 선택 불가"와 일치).

**연결 (Builder)**: agent_tool에 mcp_tool 체크. Tool Description은
mcp_tool.description 그대로 노출 — 모델의 Tool 선택 품질이 여기 걸림.

**실행 (Runtime)**: Loop가 tool_call 결정 → Registry가 내장/MCP 판별 →
MCP Client가 호출 → 결과/오류를 Loop에 반환 → tool_call 적재(선기록:
"하려 한다" 기록 → 호출 → 결과 갱신, 준억 분석 §4.2 패턴).

## 4. 보안 경계 (지훈 제기 — 이번 설계로 1차 답)

사용자가 임의 URL을 등록하는 구조의 최소 방어선:

1. **SSRF 차단**: endpoint는 https만, 사설 IP 대역(10./172.16~31./192.168./
   127./169.254.)·내부 호스트명 거부. 등록 시·호출 시 모두 검사(DNS 리바인딩
   대비 호출 시 재검사).
2. **토큰 보호**: auth_token은 암호화 저장, 화면에는 마스킹(Figma 반영됨),
   로그·tool_call에 절대 기록 안 함.
3. **호출 격리**: MCP 호출에 타임아웃(기본 30s)·응답 크기 상한. 실패는
   Loop에 오류로 반환하고 Harness는 계속 산다.
4. **권한**: MCP 서버 등록은 팀장 권한(권한 탭 골격에 이미 있음). Tool 실행은
   Agent별 허용 목록 + side effect는 승인 게이트.
5. v1 제외(Future Work): 서버별 도메인 allowlist 관리 UI, tool 사용량 쿼터.

## 5. 자체 Jira MCP — Tool 3종 스펙 (B안 채택 시)

| Tool | 입력 | 출력 | 비고 |
|---|---|---|---|
| `jira_create_issues` | project_key, issues[] (title·description·assignee?·issuetype·estimate?) | 건별 성공/실패 목록 (key 또는 error_code) | **부분 실패를 그대로 반환** — PARTIAL_RESULT의 데이터 원천. 필수 필드는 호출 전 검증해 사유 생성(Figma 실패 사유와 일치: issuetype·assignee 누락) |
| `jira_create_project` | name, key, lead? | project_key | Q6(생성 단위) 결정에 따라 데모 포함 여부 |
| `jira_get_issues` | project_key, jql? | 이슈 목록 | 등록 후 확인·기존 이슈 조회용 (Figma 에이전트 편집의 "Jira 이슈 조회") |

구현: 기존 `apps/connectors`의 Jira REST 클라이언트 재사용, FastMCP류로 노출.
배포는 Django와 같은 호스트의 별도 프로세스(초기) — 외부 MCP와 동일한 등록
플로우로 접속해 "임의 서버 등록" 구조를 그대로 검증한다.

## 6. 오류 매핑 (화면·평가와의 계약)

| 오류 | tool_call.error_code | 화면 |
|---|---|---|
| 인증 만료 | `401` | 오류 카드 "설정 > MCP에서 연결 확인" (Figma 41:336 그대로) |
| rate limit | `429` | 부분 실패 사유 "잠시 후 재시도 가능" |
| 필수 필드 누락 | `validation` | 부분 실패 사유 "담당자 미지정" 등 |
| 타임아웃·연결 실패 | `timeout`/`unreachable` | 재시도 버튼, 업무 목록 보존 |

이 코드들이 평가 §4(Tool 실행 성공률)와 §5(실패 단계 분포)의 집계 키가 된다.

## 7. 개발 순서 (목요일~)

1. `mcp_server`·`mcp_tool` 마이그레이션 + 등록·연결 테스트 API
2. MCP Client(호출·타임아웃·오류 매핑) + Registry 통합
3. 자체 Jira MCP tool 3종 (기존 REST 재사용)
4. Settings > MCP 화면 연결 (Figma 확정안)
5. (여력) 공식 Atlassian MCP 등록 검증

## 8. 확정 (2026-08-11 · 팀 결정 — 멘토링에 올리지 않는다)

**Connector 와 MCP 를 인증 주체로 가른다.** 이 구분이 곧 발표의 설계 근거다.

| | 무엇 | 인증 주체 | 상태 |
|---|---|---|---|
| **Connector** | 우리가 검증해 미리 붙인 통로 (Jira·Drive) | **우리(운영자)가 OAuth 앱 사전 등록**, 사용자는 「연결」만 | 구현 완료 |
| **MCP** | 사용자가 **직접 만들거나 운영하는** 서버 | 사용자가 주소 + 정적 토큰 | 구현 완료 |

- **MCP OAuth 는 Future Work — 추가 구현 없음.** 남는 갭은 "남이 호스팅하는
  제3자 MCP 를 사용자가 붙이는 경우"(예: 공식 Atlassian MCP)뿐인데, Jira 는 이미
  Connector 로 붙였으니 **중복 경로**고, 자기 서버라면 자기가 토큰을 발급하면 된다.
- **대신 화면 문구를 바꾼다.** 지금 McpTab 안내문("읽기는 Connector, 쓰기는 MCP")은
  **대표 시나리오 Jira 가 반례**라 어차피 틀린 문장이다 — Jira 는 수집도 하고
  등록도 한다. **"직접 만들거나 운영하는 MCP 서버를 붙입니다"** 로 재정의하면
  정적 토큰만 받는 것이 *한계*가 아니라 *범위 정의*가 된다.
  → `작업목록.md` 작업 9 에서 처리.
- Q6(Jira 생성 단위) → **항상 Project 신규 생성**으로 확정(`5_E2E_시나리오.md` §4-2).

### 참고 — MCP 인증 규격의 등록 우선순위

규격은 등록 방식을 **① 사전 등록된 클라이언트 정보 → ② Client ID Metadata
Documents → ③ Dynamic Client Registration → ④ 사용자 직접 입력** 순으로 못박는다.
**사전 등록이 1순위**다. CIMD·DCR 은 사전 관계가 *없을 때*의 대비책이지 대체재가
아니다 — 우리처럼 붙일 서비스를 아는 경우는 사전 등록이 규격상으로도 정석이다.
(DCR 은 현행 규격에서 하위 호환용 fallback 으로 내려갔다.)
출처: https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization
