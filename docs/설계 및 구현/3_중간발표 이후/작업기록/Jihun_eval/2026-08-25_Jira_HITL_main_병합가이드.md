# 2026-08-25 Jira HITL main 병합 가이드

## 1. 이 문서의 범위

이 문서는 Jira 생성 승인 카드의 `미리보기 + 안전한 편집 + 별도 최종 승인` 변경을
`main`에 병합하는 담당자와 AI를 위한 실행 순서다.

이번 변경에는 다음이 없다.

- DB 스키마 변경
- DB 마이그레이션
- 새 환경변수
- 새 외부 패키지
- RunPod·파싱·색인 코드 변경

따라서 이 변경만 병합할 때 SQL을 실행하거나 기존 DB 값을 변경하면 안 된다.

작성 시점 로컬 기준은 다음과 같다.

- 현재 브랜치: `jihun`
- 현재 HEAD: `9593b09`
- 로컬 원격 추적 기준 `origin/main...jihun`: main 고유 10개, jihun 고유 2개
- 작업 트리에는 Jira HITL 외의 수정·미추적 파일도 함께 존재함

위 숫자는 작성 시점 스냅샷이다. 실제 병합 직전에는 반드시 `git fetch` 후 다시
확인한다.

## 2. 가장 중요한 병합 원칙

1. `git add .`로 모든 변경을 한 커밋에 넣지 않는다.
2. Jira HITL 제품 코드, 평가 설계, 다른 기능 변경을 목적별 커밋으로 분리한다.
3. 최신 main을 먼저 `jihun`에 병합하고, 충돌을 해결한 상태에서 전체 검증한다.
4. 충돌 파일을 `ours` 또는 `theirs`로 통째로 선택하지 않는다.
5. 편집은 Jira 생성 호출에만 허용하고 기존 승인·거절 흐름을 보존한다.
6. 테스트와 수동 검증이 끝나기 전에 main 병합 완료로 기록하지 않는다.
7. 공유 브랜치에 강제 push하거나 이력을 임의로 다시 쓰지 않는다.

## 3. 커밋 범위 분리

### 3.1 제품 구현 커밋

다음 8개 파일을 하나의 Jira HITL 제품 구현 커밋으로 묶는다.

```text
apps/chat/serializers.py
apps/chat/api_views.py
tests/test_chat.py
frontend/src/api/chat.ts
frontend/src/pages/ChatPage/liveChat.ts
frontend/src/pages/ChatPage/ChatPage.tsx
frontend/src/pages/ChatPage/cards/ChatCards.tsx
frontend/src/pages/ChatPage/cards/cards.module.css
```

권장 커밋 메시지:

```text
Jira 승인 카드에 미리보기와 안전한 편집 추가
```

### 3.2 평가 설계·기록 커밋

Jira workflow와 관련 기록은 제품 구현과 별도 커밋으로 둔다.

```text
docs/설계 및 구현/3_중간발표 이후/설계/eval/agent_workflow_v1.json
docs/설계 및 구현/3_중간발표 이후/설계/eval/workflow_004_jira_hitl_registration.md
docs/설계 및 구현/3_중간발표 이후/설계/eval/README.md
docs/설계 및 구현/3_중간발표 이후/작업기록/Jihun_eval/2026-08-25_Agent평가_연구방식_도입기록.md
docs/설계 및 구현/3_중간발표 이후/작업기록/Jihun_eval/2026-08-25_Jira_HITL_미리보기_편집_구현기록.md
docs/설계 및 구현/3_중간발표 이후/작업기록/Jihun_eval/2026-08-25_Jira_HITL_main_병합가이드.md
```

권장 커밋 메시지:

```text
Jira HITL 평가 결과와 병합 절차 기록
```

다른 평가 기반 파일이 아직 미추적 상태라면 담당자가 그 파일들의 완성도와 의존성을
검토한 뒤 별도 평가 설계 커밋으로 묶는다. 이 가이드의 파일 목록에 없다는 이유로
삭제하지 않는다.

### 3.3 이번 Jira HITL 커밋에 섞지 않을 변경

현재 작업 트리에 있는 다음 범주의 변경은 Jira 미리보기·편집 구현과 별개다.

- `DB/migrations/2026-08-24_guardrail_on_failure_to_team.sql`
- `services/agent_runtime/factory.py`
- `services/agent_runtime/prompts.py`
- `tests/test_factory.py`
- `tests/test_prompts.py`
- `services/evaluation/`, `scripts/eval_record.py`, `tests/test_eval_recorder.py`
- `Jihun_Deep_Agents` 아래의 다른 작업 문서

이 파일들은 원래 작업 목적에 맞는 별도 커밋 또는 별도 PR로 처리한다. 임의로
되돌리거나 삭제해서도 안 된다.

stage 후에는 다음을 확인한다.

```powershell
git diff --cached --name-status
git diff --cached --check
```

## 4. 최신 main 통합 순서

작업 트리 변경을 목적별로 안전하게 커밋한 뒤 다음 순서로 진행한다.

```powershell
git switch jihun
git fetch origin main
git rev-list --left-right --count origin/main...jihun
git merge origin/main
```

`git fetch`와 `git merge`는 원격 상태를 읽거나 현재 브랜치 이력을 변경하므로 실제
실행 전 팀의 일반 Git 절차와 권한을 따른다. 병합 전에 작업 트리가 깨끗하지 않다면
진행하지 않는다. 사용자 변경을 임의 stash, reset, checkout으로 치우지 않는다.

충돌이 없더라도 검증을 다시 수행한다. 충돌이 있다면 다음 의미를 보존한다.

### 백엔드 충돌 해결 기준

- 기존 승인·거절 결정 처리 보존
- 일부 도구 호출만 승인·거절하는 기존 동작 보존
- skill의 기존 `respond`·`reexplain` 처리 보존
- Jira `edit`만 새로 허용
- 수정 후에도 원래 도구 이름, 프로젝트 키, assignee 보존
- 이슈 개수가 바뀌면 거부
- 서버에 저장된 `action_requests`를 기준으로 재개

### 프런트엔드 충돌 해결 기준

- 기존 승인·거절 버튼과 처리 상태 보존
- 대기 이벤트에서 Jira 이슈 정보를 읽어 카드에 표시
- `편집 → 수정 적용 → 최종 승인`을 서로 다른 동작으로 유지
- `수정 적용`만으로 confirm API를 호출하지 않음
- 프로젝트와 assignee 편집 UI를 추가하지 않음
- 모바일·기존 카드 레이아웃을 깨뜨리지 않음

특히 `ChatPage.tsx`, `liveChat.ts`, `ChatCards.tsx`, `api_views.py`는 main에서도
변경될 가능성이 높은 파일이다. 충돌을 한쪽 파일 전체로 덮지 말고 함수 단위로
양쪽 의도를 합친다.

## 5. 자동 검증 순서

최신 main 통합과 충돌 해결이 끝난 뒤 다음 순서로 검증한다. 프로젝트에서 사용하는
로컬 또는 Docker 실행 방식 중 팀 표준 방식을 사용한다.

### 5.1 백엔드

최소 필수 범위:

```powershell
python manage.py test tests.test_chat
```

main에 다른 채팅·이벤트 변경이 함께 들어왔다면 다음 관련 회귀 테스트도 실행한다.

```powershell
python manage.py test tests.test_chat tests.test_events tests.test_tracing
```

최종 PR 전에는 가능하면 백엔드 전체 테스트를 실행한다.

```powershell
python manage.py test tests
```

### 5.2 프런트엔드

```powershell
cd frontend
npm run build
cd ..
```

### 5.3 변경 품질과 범위

```powershell
git diff --check
git status --short
git diff --name-status origin/main...jihun
```

완료 조건은 테스트 실패 0건, 프런트 빌드 성공, whitespace 오류 0건, 의도하지 않은
파일과 비밀값 포함 0건이다. 테스트 개수는 main 변경에 따라 달라질 수 있으므로
고정 숫자보다 실패가 없는지를 판정한다.

## 6. DB와 배포 처리

이 Jira HITL 변경 자체에는 DB 마이그레이션이 없다.

- 새 SQL을 실행하지 않는다.
- 기존 데이터를 수정하지 않는다.
- `.env` 값을 추가하거나 바꾸지 않는다.
- RunPod 설정을 바꾸지 않는다.

단, 같은 PR에 다른 기능의 DB 마이그레이션을 의도적으로 포함한다면 해당 기능의
별도 인수인계 문서를 따라야 한다. Jira HITL 변경을 이유로 다른 SQL을 함께
실행해서는 안 된다.

배포 순서는 기존 애플리케이션 배포 절차를 따른다. 백엔드와 프런트가 API 계약을
함께 바꾸므로 둘 중 하나만 장기간 따로 배포하지 않는다. 불가피하게 순차 배포할
경우 기존 `approve`·`reject` 요청이 계속 동작하는지 먼저 확인한다.

## 7. 병합·배포 후 수동 검증

### 7.1 기존 HITL 회귀 확인

- 일반 승인 카드에서 승인 가능
- 일반 승인 카드에서 거절 가능
- 거절 뒤 외부 side effect 없음
- 완료 메시지는 실제 `tool_completed(status=OK)` 이후에만 표시

### 7.2 Jira 미리보기·편집 확인

1. 테스트 Jira 프로젝트의 초기 이슈 수를 기록한다.
2. `WF-JIRA-HITL-004B`를 새 채팅에서 실행한다.
3. 카드에 프로젝트·제목·유형·기한·설명이 표시되는지 확인한다.
4. 편집 화면에서 제목 또는 설명을 바꾼다.
5. `수정 적용` 후 수정된 미리보기가 표시되는지 확인한다.
6. 아직 Jira 이슈가 생성되지 않았는지 확인한다.
7. 최종 승인한다.
8. `tool_completed(status=OK)`를 확인한다.
9. Jira 실제 저장값이 최종 미리보기와 같은지 확인한다.
10. 생성 issue key를 기록한다.
11. Jira UI에서 그 이슈만 삭제한다.
12. Jira가 초기 상태로 돌아왔는지 확인한다.

수동 검증용 입력과 정확한 기대값은
`설계/eval/workflow_004_jira_hitl_registration.md`를 기준으로 한다.

## 8. 중단 기준

다음 중 하나라도 발생하면 main 병합 또는 배포를 완료로 처리하지 않는다.

- 승인 카드에 실제 Jira 입력값이 보이지 않음
- `수정 적용`만 했는데 Jira 이슈가 생성됨
- 클라이언트 편집으로 프로젝트 또는 assignee가 바뀜
- 수정 전 이슈 수와 수정 후 이슈 수가 달라짐
- Jira 외 도구가 `edit` 결정으로 실행됨
- 거절했는데 Jira 이슈가 생성됨
- 승인 카드와 실제 Jira 저장값이 다름
- 도구 실패·거절인데 완료 메시지가 표시됨
- 테스트 또는 프런트 빌드 실패
- 의도하지 않은 DB·RunPod·파싱 코드가 포함됨
- 테스트 Jira 이슈를 정리할 권한이나 방법이 없음

## 9. 되돌리기와 cleanup

### 코드

공유 main을 `reset --hard`하거나 강제 push하지 않는다. 문제가 확인되면 팀과
협의해 Jira HITL 구현 커밋을 되돌리는 새 revert 커밋을 만든다. DB 변경이 없으므로
이 기능만 되돌릴 때 DB 롤백은 필요하지 않다.

### 외부 Jira 데이터

- 승인 전 또는 거절 경로: 생성된 이슈가 없어야 한다.
- 승인 후: 기록한 issue key와 일치하는 테스트 이슈 한 건만 Jira UI에서 삭제한다.
- 삭제 뒤 조회해 초기 이슈 수로 돌아왔는지 확인한다.
- issue key가 불명확하면 추측해서 삭제하지 말고 cleanup을 중단한다.

## 10. 최종 완료 체크리스트

- [ ] Jira HITL 제품 구현과 다른 변경이 별도 커밋으로 분리됨
- [ ] 최신 `origin/main`을 `jihun`에 통합함
- [ ] 충돌 해결 시 기존 승인·거절 동작을 보존함
- [ ] 백엔드 관련 테스트와 가능하면 전체 테스트 통과
- [ ] 프런트 production build 통과
- [ ] `git diff --check` 통과
- [ ] DB 마이그레이션이 없음을 재확인함
- [ ] 승인 카드의 미리보기·편집·별도 승인 수동 검증 통과
- [ ] 거절 무부작용 확인
- [ ] 승인 후 실제 Jira 저장값 확인
- [ ] 테스트 이슈 cleanup 완료
- [ ] 미해결 근거 명칭·상태 문구·assignee 문제를 후속 이슈로 유지
