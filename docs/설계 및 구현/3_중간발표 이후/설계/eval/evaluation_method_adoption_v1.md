# Agent 평가 연구 반영 결정 v1

## 목적

공개 Agent 벤치마크를 그대로 설치하는 대신 우리 제품의 실제 업무, 도구, 권한,
승인, DB 상태에 맞는 평가 원칙만 선별해 적용한다. 외부 벤치마크 점수와 우리 제품
점수를 같은 값처럼 비교하지 않는다.

## 도입 결정

| 연구 | 가져오는 개념 | 현재 반영 | 남은 일 |
|---|---|---|---|
| [AgentBench](https://openreview.net/pdf?id=zAdUB0aCTQ) | 다양한 상호작용 업무, 반복 실행, 실패 유형 분석 | 복합 workflow, 도구·상태 assertion, 3회 반복 | workflow를 5개 이상으로 확대하고 실패 유형 집계 |
| [AgentBoard](https://proceedings.neurips.cc/paper_files/paper/2024/hash/877b40688e330a0e2a3fc24084208dfa-Abstract-Datasets_and_Benchmarks_Track.html) | 최종 성공 외 중간 진행률 분석 | `progress_milestones`와 결과 기록기 진행률 집계 도입 | 기존·신규 workflow 실행 결과에 마일스톤 판정 추가 |
| [AgentRewardBench](https://arxiv.org/abs/2504.08942) | 자동 평가기를 사람 판정과 비교하는 메타평가 | Judge 교차검증 계약 설계 | runner와 Judge 구현 후 calibration 실행 |
| [AgentDojo](https://arxiv.org/abs/2406.13352) | 신뢰할 수 없는 도구·문서 데이터의 prompt injection 평가 | 격리 문서로 로컬 3회 실행, 3/3 성공·side effect 0건 | 자동 runner에서 도구 구성을 고정하고 배포 환경 재검증 |
| [WebArena](https://arxiv.org/abs/2307.13854) | 재현 가능한 환경 초기 상태와 실행 후 상태 판정 | sandbox·postcondition·cleanup 원칙에 반영 | 배포 환경 Jira 사례에 동일 원칙 적용 |
| [OSWorld](https://arxiv.org/abs/2404.07972) | 실제 GUI·OS 조작의 실행 기반 평가 | 미도입 | GUI 조작 Agent가 생길 때만 재검토 |

## 적용 원칙

1. 외부 벤치마크 전체를 제품 의존성으로 추가하지 않는다.
2. 정답 문장이나 단일 trajectory를 고정하지 않는다.
3. 권한, 승인, 중복 쓰기, tenant 격리와 최종 상태는 코드 assertion으로 판정한다.
4. 의미 품질은 rubric과 사람 판정을 우선하고, LLM Judge는 검증 전까지 보조 수단이다.
5. 단계별 진행률은 최종 성공률을 대체하지 않는다. 실패 위치를 설명하는 분석값이다.
6. prompt injection fixture는 평가 전용 팀·문서에만 두고 실제 팀 문서와 섞지 않는다.
7. 브라우저·OS 조작 기능이 없는 현재 제품에 WebArena·OSWorld 실행 환경을 억지로 붙이지 않는다.

## 이번 버전에서 실제 반영한 것

- 결과 계약에 선택 필드 `progress.milestones` 추가
- 기록기에서 사례별 완료율, 평균 완료율, 실패 마일스톤 집계
- 기존 workflow 2개에 각각 5개의 중간 마일스톤 정의
- prompt injection 전용 workflow 설계와 로컬 3회 기준선 확보
- 자동 Judge와 사람 판정을 비교하는 calibration 계약 설계

## 아직 구현하지 않은 것

- 평가 runner 자동 실행
- LLM Judge 호출과 점수 저장
- Judge-사람 일치율 계산 자동화
- prompt injection 자동 반복과 배포 환경 재검증
- 평가 대시보드
- OpenTelemetry 연결

이 항목들을 완료한 것처럼 표현하지 않는다.
