# Agent Platform DB 설계 — 에이전트 · 대화 · 실행 · 도구 · 가드레일

> **2026-08-25 작성.** 이 폴더의 다른 문서와 `../../2_중간발표 이전/데이터모델/` 은
> **피벗 이전 스키마(문서·업무·팀·HR)만** 다룬다. 8/08 이후 늘어난 **Agent Platform
> 테이블(~~15개~~ 20개)은 어느 데이터모델 문서에도 없었다.** 그 구멍을 메운다
> (스킬 5테이블은 8/26~8/27 에 들어와 **2026-08-29 에 §5 로 채웠다**).
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

## 5. 스킬 — 5테이블 (2026-08-29 추가)

**이 문서를 쓴 8/25 에는 없던 표다.** 8/26~8/27 마이그레이션으로 들어왔고, 이 문서가
메우겠다던 바로 그 구멍이 같은 자리에 다시 뚫려 있었다 — §7 의 삭제 절에만 이름이
나오고 정작 「무엇이 있는가」는 어디에도 없었다.

| 테이블 | PK | 무엇 |
|---|---|---|
| `skill_registration_job` | UUID | 등록 요청 한 건. `candidate_document`(JSONB) · `candidate_hash` · `operation`(CREATE/UPDATE/RETRY) · `status`(QUEUED→RUNNING→SUCCEEDED/FAILED) · `stage` · `attempt` · `retry_of_job_id`(자기 참조) |
| `skill_catalog_revision` | `account_id` | 그 계정의 스킬 목록이 몇 번 바뀌었나. 런타임이 카탈로그를 다시 읽을지 판단하는 값 |
| `skill_worker_heartbeat` | `worker_id` | 검증 워커의 생존 신호. **테넌트 데이터가 아니라** 프로세스 기록이다 |
| `skill_eval_regression_case` | `case_id` | 운영자가 손으로 넣는 회귀 데이터셋. `scope`(GLOBAL/TEAM/SKILL) · `polarity` · `case_document` |
| `skill_eval_feedback` | UUID | 사용자가 남긴 「이 스킬이 맞았나」. `observed_skills` · `expected_skill` · `review_status` |

⚠ **`target_scope` 가 `CHECK (target_scope = 'PERSONAL')` 로 고정돼 있다.** 만들 수
있는 것은 개인 스킬뿐이고, 팀 스킬은 공유를 거친다. 팀 등록 경로를 「숨긴」 것이
아니라 **DB 가 거절**한다.

⚠ **원문을 안 남긴다.** `skill_eval_regression_case.source_trace_hash` ·
`skill_eval_feedback.source_trace_hash` 는 추적용 해시다 — `tool_call.input_summary`
가 요약만 남기는 것과 같은 판단이다.

🔴 **등록된 스킬 자체는 이 표에 없다.** 여기 있는 것은 **등록 절차**이고, 스킬 본문과
장기메모리는 LangGraph 의 `store` 에 있다(§7 마지막 절).

## 6. 내장 도구는 DB 에 없다

**내장 도구 ~~16종~~ ~~17종~~ ~~19종~~ 32종(2026-08-29 재측정)은 테이블이 아니라 코드다** — `services/harness/registry.py` 의
`BUILTIN_TOOLS` 가 정본이고, `agent_version_tools.tool_ref` 가 그 이름을 가리킨다.

**8/27 이후 열셋이 더 붙었다** — 파일·데이터·시각화 계열이다(`document_read` ·
`document_convert` · `pdf_edit` · `file_inspect` · `file_sanitize` · `archive_manage` ·
`table_transform` · `data_quality_check` · `file_compare` · `calculate` ·
`diagram_create` · `chart_create` · `graph_create`). 갈래도 `_CATALOG_METADATA` 가
덮어써서 여덟이다 — 검색 4 · 문서 8 · 팀 3 · 업무 7 · 데이터 3 · 시각화 3 · 계산 2 ·
시스템 2.

그중 ~~여섯~~ **열다섯**이 `side_effect=True` 라 승인 게이트를 탄다 —
`task_update` · `task_register` · `jira_create_issues` · `skill_register` ·
`table_export` · `document_create` 에 **`document_convert` · `pdf_edit` ·
`file_sanitize` · `archive_manage` · `table_transform` · `diagram_create` ·
`chart_create` · `graph_create` · `skill_creator_ask_followup`** 이 더해졌다.

**`skill_creator_ask_followup` 도 `side_effect=True` 다**(2026-08-26 추가 확인). 다만
화면이 승인/거절 버튼 대신 **질문+입력창 카드**를 그리고 답을 `respond` 로 돌려보내므로,
세는 방식은 ~~「승인 게이트 4종 + 질문 카드 1종」~~ ~~「승인 게이트 6종 + 질문 카드 1종」~~
**「승인 게이트 14종 + 질문 카드 1종」**(2026-08-29 재측정 · `side_effect=True` 는 모두 15개)이다.

⚠ **`table_transform` 은 조건부다**(2026-08-29). `approval_when` 이 붙어 있어
**결과를 파일로 만들 때만**(`output_format` 지정) 멈춘다 — 값을 보기만 하는 호출은
승인 없이 지나간다. `BUILTIN_TOOLS` 에서 `approval_when` 이 있는 도구는 이것뿐이다.

⚠ **`interrupt_on` 은 이 15개로 끝이 아니다**(`services/agent_runtime/factory.py`).
매 요청 시점의 실제 도구 목록을 훑으므로 팀마다 다른 **MCP 커스텀 도구가 전부**
들어오고, deepagents 기본 파일시스템의 `delete` 도 같은 자리에서 따로 붙는다.

## 7. 지울 때 손으로 다 적어야 한다

**외래키가 없어서 CASCADE 가 없다.** 팀·계정 완전 삭제는 지울 것을 표로 손수 적어
둔 것이 전부다 — 팀 ~~39단계~~ ~~42단계~~ ~~45단계~~ **46단계** · 계정 ~~15단계~~ **18단계**
(2026-08-27 에 스킬 넷을 채웠고, 팀 쪽은 그 뒤 한 단계가 더 늘었다 —
2026-08-29 재측정 · `backend/db/repositories.py` 의
`_TEAM_PURGE_STEPS` · `_ACCOUNT_PURGE_STEPS`).

⚠ **새 테이블이 `team_id`/`account_id` 를 갖게 되면 그 표에 줄을 더해야 한다.**
안 더하면 지운 팀의 행이 조용히 남는다.

✅ **2026-08-27 에 또 재발했고 같은 날 고쳤다.** 8/26~8/27 스킬 마이그레이션이
만든 넷이 두 표 어디에도 없어 **팀·계정을 완전 삭제해도 남았다**(실제 DB 드릴로
확인). `skill_registration_job`(`team_id`·`account_id`) ·
`skill_catalog_revision`(`account_id`) · `skill_eval_regression_case`(`team_id`) ·
`skill_eval_feedback`(`team_id`·`account_id`) 넷을 채웠다. 다섯 번째
`skill_worker_heartbeat` 는 워커 기록이라 대상이 아니다.

⚠ **손댈 곳이 셋이 아니라 다섯이다.** 위 두 표와 `DB/reset_demo.sql` 에 더해
`DB/reset_eval.sql` 과 `tests/test_ops_purge.py` 의 `RESET_KEEP`·`EVAL_KEEP` 이
있다. 그 테스트가 다섯을 서로 대조하므로 **표를 더하면 먼저 깨진다** — 삭제
표를 손대면 `python manage.py test tests.test_ops_purge` 부터 돌린다.

🔴 **아직 안 지워지는 것이 하나 남았다 — `store`.** 등록된 스킬과 장기메모리는
`skill_*` 표가 아니라 LangGraph 의 `store` 에 있는데(`skill.personal.<account_id>`
같은 `prefix`) 삭제 표 어디에도 없다. `schema.sql` 이 아니라 런타임이 만드는
표라 스키마 대조에도 안 걸린다. 상세와 판단은 `../설계/작업목록.md` 의 「개인
스킬과 장기메모리는 아직 안 지워진다」.
