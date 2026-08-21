# Child(서브 에이전트) 실행의 Run Snapshot — 구현 완료 (2026-08-19)

## 배경

`2026-08-19_09_Run_Snapshot_모델엔드포인트_구현완료.md`(§4순위)에서 Root
실행의 `resolved_provider`/`resolved_endpoint_hash`(팀 커스텀 엔드포인트가
바뀌어도 "그때 실제로 어느 서버로 요청이 나갔는지" 재구성할 수 있게 하는 값)를
`agent_run`에 남기도록 고쳤지만, 그 문서 "한계" 절에 정직하게 남겨 둔 대로
Child(서브 에이전트) 실행은 범위 밖이었다 — `EVENT_SUBAGENT_STARTED`에 이 두
필드가 없어 Child의 `agent_run` 행은 항상 `NULL`이었다.

Child는 Root와 다른 model을 가질 수 있다(`SubagentDefinition.model`) — 예를
들어 Root는 기본 Anthropic 모델을 쓰고 Child(Jira 작성 담당)는 팀이 등록한
사내 vLLM 엔드포인트를 쓰는 구성이 가능하다. 이 경우 Child 쪽 엔드포인트가
바뀌어도 지금까지는 실행 로그로 알 방법이 없었다.

## 왜 Root와 같은 방식을 그대로 못 쓰는가

Root는 `executor.py`의 `run()`이 `factory.build()`를 부른 **직후**
`EVENT_AGENT_STARTED`를 직접 만들어 낸다 — `resolved_model`을 그 자리에서
바로 실어 보내면 된다. 하지만 Child 그래프는 런타임의 `subagent_started`
이벤트 시점(모델이 실제로 위임을 결정한 순간)이 아니라 **Root `build()` 호출
시점에 모든 Child가 한 번에 정적으로 컴파일된다** — `factory.py`의
`compiled_children` 리스트 컴프리헨션이 `definition.subagents`를 순회하며
`build_subagent()`를 전부 미리 불러 둔다. 그래서 이벤트가 나올 때는 이미
늦다 — Child의 `resolved_model`을 캐치하려면 Root `build()` 호출 시점에
미리 만들어 알아 둔 값을 나중에 "이 위임이 어느 Child였는지"로 찾아 쓰는
lookup 구조가 필요하다.

이 lookup 패턴 자체는 새로 발명한 게 아니다 — `events.py`가 이미
`subagent_started`의 `agent_id`/`agent_version_id`/`subagent_name`을
정확히 이 방식으로 채우고 있었다(2026-08-14 추가, 모듈 docstring
"`subagent_started`/`subagent_completed`의 agent_id/agent_version_id/
subagent_name" 절): Root `AgentDefinition.subagents`에 이미 Child 자신의
DB 조회 결과가 들어 있고, `task` 도구가 넘기는 `subagent_type`(=alias)으로
그 목록을 찾으면 된다. MVP가 위임 1단계로 제한돼 있어서(`subagents/
validation.py`/`loader.py`/`subagents/builder.py`가 3중으로 강제) 이 조회에
재귀가 필요 없다는 전제도 그대로 재사용했다.

## 구현

### 값이 만들어지는 곳 → 이벤트에 실리는 곳까지

1. **`services/agent_runtime/factory.py`** — `AgentRuntimeFactory.build()`의
   반환값을 `(graph, resolved_model)` 2-tuple에서 `(graph, resolved_model,
   child_resolved_models)` 3-tuple로 바꿨다. `child_resolved_models`는
   `{alias: ResolvedModelConfig}` 딕셔너리다.
   - `compiled_children`을 만드는 리스트 컴프리헨션 안에서, Child를 짓는
     재귀 호출(`self.build(..., allow_subagents=False)`)의 결과 중 이전에는
     `[0]`으로 버리던 `resolved_model`을 이제 `sub_def.alias`를 key로 삼아
     모아 둔다. alias는 람다 기본 인자로 미리 묶었다(`lambda d, c,
     _alias=sub_def.alias: ...`) — 그냥 클로저로 반복문 변수를 참조하면
     파이썬의 흔한 지연 바인딩 버그(모든 람다가 마지막 `sub_def`를 보게 됨)에
     걸린다.
   - Child 자신을 짓는 재귀 호출(`allow_subagents=False` 분기)은 leaf라(1단계
     위임 제한 — Child는 자기 Child를 못 가진다) 세 번째 반환값을 항상 빈
     딕셔너리로 돌려준다.
2. **`services/agent_runtime/executor.py`** — `run()`/`resume()` 둘 다
   `factory.build()`의 3-tuple을 그대로 받아 `event_mapper.convert()`에
   `root_resolved_model=`/`child_resolved_models=` 키워드 인자로 넘긴다.
   `resume()`은 `EVENT_AGENT_STARTED`를 새로 안 내므로(재개는 "새로 시작"이
   아니라 "이어서 진행") Root 자신의 `resolved_model`을 다시 기록할 자리는
   없지만, 재개된 뒤에도 이 실행이 새 위임(`subagent_started`)을 낼 수
   있으므로 그 이벤트를 위해 두 값 다 계속 갖고 있는다(§4순위 당시엔
   `[0]`으로 버렸던 부분을 이번에 고쳤다).
3. **`services/agent_runtime/events.py`** — `EventMapper.convert()`에
   `root_resolved_model`/`child_resolved_models` 파라미터를 추가하고(둘 다
   기본값 `None` — 안 넘기는 기존 호출자를 안 깬다), `_classify()` →
   `_classify_parent_tool_calls()`까지 그대로 threading했다.
   `_classify_parent_tool_calls()`가 `subagent_started` 이벤트를 만들 때
   (기존 `agent_id`/`agent_version_id`/`subagent_name`을 alias로 찾던 바로
   그 자리) `child_resolved_models`에서 같은 alias로 `resolved_model`을
   찾고, `resolved_provider`/`resolved_endpoint_hash` 두 필드를 이벤트에
   추가로 싣는다. `resolved_endpoint_hash()`(models/factory.py, §4순위가
   이미 만든 함수)를 그대로 재사용한다 — 새로 판단하지 않았다.
   - **못 찾으면(예: general-purpose) Root 자신의 값으로 폴백한다.** GP는
     `definition.subagents`에 없는 alias라 기존에도 `agent_id`/
     `agent_version_id`가 Root 값으로 폴백하고 있었는데(2026-08-14 결정,
     기존 코드), 이 폴백이 실제로 정확하다 — GP는 `factory.py`가 전용
     모델을 따로 resolve하지 않고 Root와 같은 `model` 객체로 돈다
     (`build_general_purpose_spec()`은 모델 인자를 아예 안 받는다,
     `compat/deepagents_v075.py` 확인). 그래서 이 폴백은 "값이 없을 때의
     임시방편"이 아니라 "GP는 실제로 Root와 같은 엔드포인트를 쓴다"는
     사실을 정확히 반영한다.
4. **`services/agent_runtime/tracing/__init__.py`/`backend/db/
   agent_platform.py`** — **고칠 필요가 없었다.** `_start_run()`은
   `EVENT_AGENT_STARTED`와 `EVENT_SUBAGENT_STARTED` 둘 다 같은 함수로
   처리하면서 이미 `event.get("resolved_provider")`/
   `event.get("resolved_endpoint_hash")`로 제네릭하게 읽고 있었다(§4순위
   구현 당시부터 그랬다 — Child 이벤트에 이 필드가 없어서 지금까지는
   `.get()`이 자연히 `None`으로 떨어졌을 뿐이다). `AgentRunRepository.
   start_with_id()`도 이미 두 파라미터를 받는다. 이게 이번 작업 범위가
   "이미 상당 부분 되어 있고 남은 건 한 칸"이라던 §4순위 문서의 평가가
   실제로 맞았다는 뜻이다.

### 왜 `AgentDefinition`/`SubagentDefinition`에 필드를 추가하지 않았는가

`resolved_model`은 **실행 시점에 계산되는 런타임 값**이다(팀 커스텀
엔드포인트가 언제든 바뀔 수 있다는 게 애초에 이 기능의 존재 이유) —
`AgentDefinition`/`SubagentDefinition`은 DB에서 그대로 읽어 온 불변 정의
객체라 여기 실행 시점 값을 얹으면 "정의"와 "이번 실행에서 실제로 벌어진 일"의
경계가 흐려진다. 대신 `factory.build()`의 반환값(호출마다 새로 계산)으로
흘려보내는 지금 구조가 Root의 `resolved_model` 반환과 정확히 같은 층위를
유지한다.

## 테스트

- `tests/test_factory.py` — `BuildReturnsResolvedModelTests`를 3-tuple
  반환에 맞게 갱신, `test_child_build_returns_empty_child_resolved_models`
  신규 추가. `BuildChildResolvedModelsTests`(신규 3개) — 단일 Child가
  alias로 정확히 찾아지는지, 여러 Child가 서로 안 섞이는지, subagents가
  없으면 빈 딕셔너리인지.
- `tests/test_events.py` — `SubagentResolvedModelTests`(신규 4개) — alias로
  찾은 Child 자신의 resolved_model을 쓰는지, `child_resolved_models`에
  없는 alias(GP 등)는 Root 값으로 폴백하는지, 두 인자를 아예 안 넘기면
  `None`/`None`으로 자연히 떨어지는지(기존 호출자 호환), 여러 Child가 서로
  안 섞이는지.
- `tests/test_executor.py` — `_FakeFactory.build()`가 3-tuple을 반환하도록
  갱신(기존 ~20여 개 호출부는 기본값이 있어 수정 없이 통과). 실제
  `EventMapper`로 변환하는 `SubagentStartedResolvedModelTests`(신규 2개) —
  `executor.run()`을 끝까지 돌려 `subagent_started` 이벤트가 Child 고유의
  resolved_provider/hash를 담는지, 매핑에 없는 alias는 Root 값으로
  폴백하는지.
- `tests/test_tracing.py` — `test_subagent_started_resolved_provider_and_
  endpoint_hash_are_read_from_the_event`(신규 1개) — `_start_run()`이 고친
  게 없다는 주장의 회귀 테스트.

## 회귀 확인

- 영향받는 모듈: `test_factory` `test_events` `test_executor` `test_tracing`
  `test_subagents_builder` `test_model_factory` — 184개 전체 통과(신규
  10개 포함).
- `manage.py check` — 이상 없음.

## 실제 Postgres 종단 검증

단위 테스트는 전부 mock/fake 기반이라, "Child의 `agent_run` 행에 실제로 그
값이 들어가는가"까지는 별도로 실제 로컬 Postgres(project_copilot DB)에
대고 직접 확인했다 — `AgentRuntimeFactory`/`AgentExecutor`/`trace_events()`를
전부 실물로 조립하고(§4순위 검증과 같은 방식), 모델만 미리 정해 둔 응답을
순서대로 내는 가짜(`FakeMessagesListChatModel` 기반)로 바꿔치기해 네트워크
호출 없이 실제 deepagents/langgraph 그래프 전체를 태웠다.

시나리오: Root(`claude-root-model`, 팀 커스텀 엔드포인트 없음) → 실제
DB에 저장된 Child(`gpt-child-model`, `jira_writer` alias, 팀 커스텀
엔드포인트 있음)로 위임하는 실행 하나.

```
=== agent_run rows ===
{'agent_id': 'AGZ01', 'parent_run_id': None,
 'resolved_provider': 'anthropic', 'resolved_endpoint_hash': None}
{'agent_id': 'AGZ02', 'parent_run_id': UUID('...'),
 'resolved_provider': 'openai_compatible',
 'resolved_endpoint_hash': '69f19a1978bb9509c613ec8bc3deef05a522edd3b692ff5f1a1b9edfc0d7cc3d'}
```

Root 행은 예상대로 `('anthropic', None)`(커스텀 엔드포인트 없음). Child
행은 `('openai_compatible', '<sha256 해시>')`로, 지금까지 항상 `NULL`이던
값이 처음으로 채워졌다 — 해시값은 파이썬 `hashlib.sha256(base_url)
.hexdigest()`로 미리 계산해 둔 기대값과 정확히 일치했고, `parent_run_id`가
Root의 `run_id`를 정확히 가리켰으며, `base_url` 원문
(`team-custom-child.example.com`)은 어디에도 나타나지 않았다(§4순위와
같은 사내망 주소 비노출 확인). 검증 뒤 만든 행은 직접 `DELETE`로 정리했고,
검증용 스크립트도 레포에 남기지 않고 지웠다.

이 로컬 Postgres에 §4순위의 `resolved_provider`/`resolved_endpoint_hash`
컬럼이 이번 세션 시작 시점엔 없어서(컨테이너가 새로 뜨며 로컬 DB가
schema.sql 기준의 이전 상태로 남아 있었다) 검증 전에 먼저
`ALTER TABLE agent_run ADD COLUMN IF NOT EXISTS ...`로 두 컬럼을 추가했다
— `DB/schema.sql`은 이미 §4순위 때 이 두 컬럼을 포함하도록 갱신돼 있으므로
(정본 파일은 안 건드렸다), 이번 작업으로 스키마가 새로 바뀐 건 없다. RDS
등 실제 배포 환경에는 이 컬럼이 §4순위 배포 시점에 이미 반영됐어야 하고,
이번 §10순위는 그 컬럼에 Child도 값을 채워 넣게 된 것뿐이다.

## 한계 — 정직하게 기록

- **GP(general-purpose)의 `resolved_provider`/`resolved_endpoint_hash`는
  "Root와 같은 값"으로 나온다.** 이건 버그가 아니라 정확한 반영이다 — GP는
  실제로 Root와 같은 model 객체로 돈다(위 "왜 Root 값으로 폴백하는가" 참고).
  다만 "GP도 서브 에이전트니까 자기만의 독립된 스냅샷이 있어야 하지 않냐"는
  관점에서 보면 Root 행과 GP 행의 `resolved_provider`가 같은 값으로 중복
  기록되는 셈이다 — 지금은 사실을 그대로 반영한 것으로 판단했지만, 나중에
  GP도 전용 모델을 가질 수 있게 구조가 바뀌면 이 폴백은 다시 봐야 한다.
- **위임이 2단계 이상으로 확장되면 이 lookup은 재검토가 필요하다.** 지금은
  `definition.subagents`가 평탄한 1단계 목록이라 alias 하나로 바로
  찾아지지만(3중으로 강제되는 전제), 그 제한이 풀리면 Child의 Child를
  찾는 재귀 lookup으로 다시 설계해야 한다 — 이 문서와 §4순위 문서가 이미
  같은 한계를 각자 적어 뒀다.
