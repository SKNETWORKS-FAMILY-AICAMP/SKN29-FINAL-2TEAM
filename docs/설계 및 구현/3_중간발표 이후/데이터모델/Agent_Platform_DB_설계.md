# Agent Platform DB 설계 — 에이전트 · 대화 · 실행 · 도구 · 가드레일

> **2026-08-25 작성.** 이 폴더의 다른 문서와 `../../2_중간발표 이전/데이터모델/` 은
> **피벗 이전 스키마(문서·업무·팀·HR)만** 다룬다. 8/08 이후 늘어난 **Agent Platform
> 15개 테이블은 어느 데이터모델 문서에도 없었다.** 그 구멍을 메운다.
>
> **정본은 `DB/schema.sql` 이다** — 컬럼 주석이 「왜 이 모양인가」를 담고 있으므로
> 여기 옮겨 적지 않는다. 이 문서는 **무엇이 있고 어떻게 이어지는지**의 지도다.

## 이 저장소 스키마의 공통 규칙

- **외래키 제약이 하나도 없다**(실측 0개). 참조는 주석으로만 표시하고, 대상이
  사라진 링크를 화면이 죽지 않고 표시하도록 모든 조회가 처리한다.
- PK 가 두 종류다. **사람이 만드는 설정**은 `VARCHAR(5)`(접두사 2자 + 숫자 3자,
  `backend/db/codes.py`)라 **테이블당 999행이 상한**이다. 대화 한 번에 수십 줄씩
  쌓이는 **로그성 테이블은 UUID** 를 쓴다.
- 마이그레이션 도구를 쓰지 않는다. 스키마를 바꾸면 `DB/migrations/` 에 파일을 더하고
  `개발환경/DB_시작_가이드.md` §4.3 의 ALTER 블록에 한 줄 추가한다.
  ⚠ **`main` push = 즉시 배포인데 배포는 마이그레이션을 돌리지 않는다. RDS 먼저.**

## 1. 에이전트 정의 — 4테이블

레거시 `agent`·`agent_tool` 은 **2026-08-22 에 폐기했다**
(`DB/migrations/2026-08-22_drop_legacy_agent.sql`). 정의는 전부 아래에 있다.

| 테이블 | 칼럼 | 무엇 |
|---|---|---|
| `agents` | 12 | 에이전트의 **정체성**. 팀 소속(`team_id`), 소유자, `visibility`(v1 은 항상 `TEAM`), `status`(DRAFT/ACTIVE/DISABLED/ARCHIVED), `current_version_id` |
| `agent_versions` | 9 | **발행된 판.** `system_prompt` · `model` · `reasoning_effort` · `max_iterations`. 에이전트를 고치면 새 행이 생긴다 |
| `agent_version_tools` | 3 | 그 판이 쓸 수 있는 도구(`tool_ref`) 목록 |
| `agent_version_subagents` | 6 | **위임 관계.** `parent_version_id` → `child_agent_id` + `child_version_id`(발행 시점 고정) + `alias` + `delegation_description` |
| `agent_favorites` | 3 | 계정별 즐겨찾기 (`/agents/versions/favorites`) |

**두 플래그를 헷갈리지 말 것** —

| 플래그 | 뜻 |
|---|---|
| `is_prebuilt` | 우리가 심어 둔 예시 에이전트인가 |
| `is_default_chat` | **이 팀의 Chat 기본값인가.** 팀당 최대 1개(부분 유니크 인덱스). 삭제·비활성화는 Repository 가 막는다 |

`is_prebuilt` 로는 기본값을 못 가른다 — 예시 에이전트도 같은 플래그를 쓴다.

### 위임은 1단계다

`child_agent_id` 가 이미 서브에이전트를 갖고 있으면 `DelegationDepthError` 다
(`services/agent_runtime/subagents/validation.py`). 자기 참조 · alias 중복 ·
비활성 · 권한 없음 · 순환도 같은 곳에서 막는다.

> ⚠ **옛 `agent:*` 도구 방식이 아니다.** 그 메커니즘은 2026-08-22 에 없어졌다
> (`services/harness/registry.py` 의 「레거시 A2A 섹션」 주석). 설계 문서 여러 곳에
> 아직 `agent:*` · `MAX_AGENT_DEPTH = 2` 로 적혀 있으면 그건 옛 서술이다.

## 2. 대화와 실행 — 4테이블

```
chat_session ──< chat_message
      │
      └──< agent_run ──< tool_call
                 │
                 └── parent_run_id (에이전트가 에이전트를 부른 경우 자기 참조)
```

| 테이블 | PK | 무엇 |
|---|---|---|
| `chat_session` | UUID | 대화. `team_id` · `account_id` · `agent_id`/`agent_version_id` · **`proj_id`**(프로젝트 컨텍스트) · `title` · `tool_refs_override` |
| `chat_message` | UUID | 발화. `role` 은 `user` / `agent` / `system` |
| `agent_run` | UUID | 한 번의 실행. `status` · `iterations` · `token_in`/`token_out` · `resolved_provider` |
| `tool_call` | UUID | 도구 호출 한 건. `tool_ref` · **`input_summary`**(원문이 아니라 요약) · `status` · `error_code` · `duration_ms` · `retrieved_doc_ids` |

**`agent_run.session_id` 는 NULL 을 허용한다** — 평가 스크립트나 에이전트 간 호출에는
대화가 아예 없다.

**실행 기록에는 내용이 아니라 요약만 남는다.** 무엇을 언제 돌렸고 어떤 도구가
실패했는지는 남고, 대화와 문서 원문은 남지 않는다.

## 3. 커스텀 도구(MCP) — 2테이블 + 안전장치 2

| 테이블 | 무엇 |
|---|---|
| `mcp_server` | 팀이 요청하고 **운영자가 등록한** 서버. `endpoint_url` · `auth_token_enc`(암호화) · `status` |
| `mcp_tool` | 그 서버에서 발견한 도구. `input_schema` · `enabled` |
| `tool_call_idempotency` | `(run_id, langchain_tool_call_id)` 로 **같은 호출의 재시도가 두 번 실행되지 않게** 결과를 붙든다 |
| `mcp_call_note` | 같은 대상에 **동시 쓰기**가 일어나는지 보고 경고한다 |

⚠ **화면에 보이는 이름은 「커스텀 도구」다**(2026-08-18). 등록·수정·연결 확인·삭제는
운영자 콘솔 `/ops/mcp` 에 있고, 팀 쪽 쓰기 API 는 걷어냈다(`apps/mcp/api_urls.py` 에
GET 하나만 남는다). 커스텀 도구는 우리가 내용을 모르므로 **전부 승인 게이트**를 탄다.

## 4. 가드레일 — 2테이블

| 테이블 | 무엇 |
|---|---|
| `guardrail_provider` | 팀별 외부 공급자 등록. `kind` · `config` · `credential_enc` · `is_active` |
| `guardrail_event` | 걸린 사건. `stage` · `rule` · `action` · `detail` |

내장 정책으로 만들었다가 걷어낸 경위는
`../작업기록/2026-08-20_가드레일_조사와_실측.md` §8.

## 5. 내장 도구는 DB 에 없다

**내장 도구 ~~16종~~ ~~17종~~ 19종(2026-08-27 재측정)은 테이블이 아니라 코드다** — `services/harness/registry.py` 의
`BUILTIN_TOOLS` 가 정본이고, `agent_version_tools.tool_ref` 가 그 이름을 가리킨다.

그중 **`task_update` · `task_register` · `jira_create_issues` · `skill_register` ·
`table_export` · `document_create`** 여섯이 `side_effect=True` 라 승인 게이트를 탄다
(뒤의 둘은 2026-08-26 추가 — 결과 파일을 「내 파일」에 저장한다).

**`skill_creator_ask_followup` 도 `side_effect=True` 다**(2026-08-26 추가 확인). 다만
화면이 승인/거절 버튼 대신 **질문+입력창 카드**를 그리고 답을 `respond` 로 돌려보내므로,
세는 방식은 ~~「승인 게이트 4종 + 질문 카드 1종」~~ **「승인 게이트 6종 + 질문 카드 1종」**
(2026-08-27 재측정 · `side_effect=True` 는 모두 7개)이다.

## 6. 지울 때 손으로 다 적어야 한다

**외래키가 없어서 CASCADE 가 없다.** 팀·계정 완전 삭제는 지울 것을 표로 손수 적어
둔 것이 전부다 — 팀 ~~39단계~~ **42단계**(2026-08-25 에 셋을 채웠다) · 계정 **15단계**
(`backend/db/repositories.py` 의 `_TEAM_PURGE_STEPS` · `_ACCOUNT_PURGE_STEPS`).

⚠ **새 테이블이 `team_id`/`account_id` 를 갖게 되면 그 표에 줄을 더해야 한다.**
안 더하면 지운 팀의 행이 조용히 남는다.

🔴 **그리고 또 재발했다 (2026-08-27 · 아직 안 고쳤다).** 8/26~8/27 스킬
마이그레이션이 만든 넷이 두 표 어디에도 없다 — `skill_registration_job`
(`team_id`·`account_id`) · `skill_catalog_revision`(`account_id`) ·
`skill_eval_regression_case`(`team_id`) · `skill_eval_feedback`
(`team_id`·`account_id`). 다섯 번째 `skill_worker_heartbeat` 는 워커 기록이라
대상이 아니다. **`DB/schema.sql` 과 `DB/reset_demo.sql` 에도 다섯 전부 빠져
있다** — 상세는 `../설계/작업목록.md` 의 「스킬 테이블 다섯이 세 곳에서
빠져 있다」.
