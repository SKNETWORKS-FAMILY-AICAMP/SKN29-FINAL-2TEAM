# Heading AutoResearch-lite 적용 과정

작성일: 2026-08-25

## 1. AutoResearch를 사용한 이유

이 프로젝트의 AutoResearch-lite는 모델 재학습이나 LLM 자율 연구가 아니다. Docling 2.119가 한 번 추출한 고정 JSON과 사람이 확정한 라벨을 대상으로, 제한된 threshold 조합을 로컬 CPU에서 반복 평가하는 결정론적 실험기다.

목적은 다음 두 가지였다.

1. 사람이 임의로 threshold를 바꿔 좋은 사례만 고르는 일을 막는다.
2. 오탐을 만들지 않으면서 더 많은 실제 누락 헤딩을 회수하는 단순 정책을 찾는다.

```text
RunPod: PDF를 Docling 2.119 JSON으로 한 번 추출
    ↓
사람: 원본/overlay를 보고 TP·FP 라벨 확정
    ↓
로컬 CPU: 고정 라벨에서 threshold 조합 전수 평가
    ↓
정책·코드·입력 hash 동결
    ↓
RunPod: 처음 보는 HOLDOUT만 다시 추출
```

## 2. 과적합 방지 계약

- 탐색 입력은 `role=DEV`만 허용한다.
- gold label, 평가기, HOLDOUT은 탐색기가 수정하지 못한다.
- 입력 CSV·JSON·정책 코드의 SHA-256을 manifest에 남긴다.
- 중대 구조 FP가 생긴 설정은 버린다.
- 같은 성능이면 기존 기준선에 가까운 단순 설정을 우선한다.
- HOLDOUT 결과를 보고 threshold를 바꾸면 그 세트는 회귀 DEV로 이동한다.

근거:

- `autoresearch_lite/program.md`
- `autoresearch_lite/dataset_manifest.json:role,immutable_files,immutable_trees`
- `autoresearch_lite/run_heading_experiments.py:21-22,39-44,66-78,93-102`

## 3. 실제 개선 흐름

### 단계 0 — 인계 상태

한화 1문서에서 만든 density 4신호의 기본값은 `120pt / 1.15배 / 60자 / 4pt / density 0`이었다. 후보 생성은 가능했지만 평가 데이터와 지표가 없었다.

변화: 코드를 “작동하는 휴리스틱”에서 “검증해야 할 가설”로 재정의했다.

### 단계 1 — Docling 2.119 교차문서 기준선

15개 sample에서 22개 평가 행(TP 8/FP 14)을 확정했다. 기존 네 숫자 조건의 조정만으로는 최고 F1 설정도 FP 10건이었고, FP 0을 요구하면 Recall이 25%로 떨어졌다.

변화: 숫자 threshold 미세 조정만으로는 해결할 수 없다는 근거를 얻었다.

### 단계 2 — 구조 guard와 관계 분기

목차/index, 반복 카드, key-value, 기존 헤딩 중복을 차단하고, 후보 뒤 본문/목록 관계를 보는 분기를 시험했다. 같은 DEV에서 8 TP/0 FP가 됐다.

주의: 같은 DEV를 보고 만든 가설이므로 이 100%는 성능 주장이 아니라 다음 HOLDOUT에 가져갈 후보였다.

### 단계 3 — AutoResearch-lite 23,328 설정

10개 수치 threshold의 카테시안 곱 23,328개를 전수 실행했다. v2 기준선은 8 TP/0 FP였고 동일 결과를 만든 설정이 10,368개였다.

변화: AutoResearch가 새 threshold를 발견한 것이 아니라, 현재 DEV가 threshold를 식별하기에 너무 작고 쉬움을 수치로 증명했다. 따라서 임의 변경 대신 기준선을 유지했다.

### 단계 4 — 첫 HOLDOUT 실패와 범위 축소

- HOLDOUT v1: 8문서 24페이지에서 카드 제목 1건 FP
- HOLDOUT v2: 10문서 69페이지에서 6건 승격 전부 FP

변화: broad `text/list_item` heading promotion은 운영 후보에서 탈락했다. 팀원 지침과 실패 유형을 반영해 `list_item` whole element만 대상으로 별도 문제를 만들었다.

### 단계 5 — list-item DEV v1

회귀 DEV 4문서·8페이지의 raw list-item 122건을 전수 라벨링했는데 모두 FP였다. 기존 seed 6건을 합치면 TP 3/FP 125였고, TP 3건이 모두 한화 한 페이지라 AutoResearch를 바로 확정하지 않았다.

변화: hard negative는 충분해졌지만, 양성 문서 다양성이 부족하다는 문제를 명시적으로 차단했다.

### 단계 6 — NOAA 양성 보강과 DEV v2

Docling issue #2246의 NOAA PDF를 2.119에서 재현해 TP 15/FP 1을 추가했다. 부산·건설 지침도 추출했지만 목표 소제목이 이미 `section_header`라 list-item 라벨 행은 추가되지 않았다.

최종 탐색 데이터:

- 고유 문서 ID 9개
- 144행
- TP 18 / FP 126
- 실제 양성 문서 2종: 한화, NOAA

변화: 적어도 두 문서에서 양성을 갖춘 list-item 전용 DEV가 만들어졌다.

### 단계 7 — list-item 96설정 탐색

`indent_min × indent_max × vertical_max = 4 × 4 × 6 = 96`개 조합을 평가했다. 최종 기록값 `0~25pt / vertical≤35pt`에서 12 TP/0 FP, Recall 66.7%, F1 0.80이었다.

변화: 18개 양성 중 구조 근거가 강한 12개만 자동 후보로 만들고 6개는 원본 유지하는 보수 정책이 생겼다.

감사상 제한: 96개 모두 FP 0, 최상 성능 동률 36개였다. 선택된 숫자는 유일한 최적값이 아니라 동률 재현값이다.

### 단계 8 — 동결 HOLDOUT

- list-item HOLDOUT v1: 3문서·13페이지·67 음성, 0 FP
- 신규 표적 3문서·7페이지·36 list-item, 자동 후보 0
- 공동 신규 5문서·9페이지·97 list-item, 자동 후보 0

변화: 일반 불렛·목차·카드를 보존하는 안전성은 강화됐지만, 독립 신규 문서 효용은 재현되지 않았다.

### 단계 9 — 실제 JSON 변경 경로

한화 Global Network의 `Asia-Pacific`, `Americas`, `Europe` 3건을 RunPod Docling 2.119에서 `section_header`로 변경했고 schema·ref·parent·중복 검증을 통과했다.

하지만 생성 level이 3/6/5로 달라 후보 판단과 level 결정을 분리했다. level은 기존 담당자의 heading level 보정 단계가 맡는다.

## 4. 단계별 숫자

| 단계 | 데이터 | 탐색/정책 | TP | FP | FN | 핵심 변화 |
|---|---|---|---:|---:|---:|---|
| 최초 density | 한화 1문서 | 4신호 잠정값 | 성능 분모 없음 | 성능 분모 없음 | - | 후보 생성기 |
| 숫자 threshold 진단 | 15 sample, DEV 22행 | 1,120 조합 | 최고 F1 8 | 10 | 0 | 숫자만으로 불충분 |
| 구조 가설 | 같은 DEV 22행 | guard+관계 분기 | 8 | 0 | 0 | HOLDOUT 후보 생성 |
| broad AutoResearch | 같은 DEV 22행 | 23,328 조합 | 8 | 0 | 0 | 10,368 동률, 기준 유지 |
| broad HOLDOUT v1 | 8문서·24p | 동결 broad | 0 | 1 | 0 | 실패, 회귀 DEV 전환 |
| broad HOLDOUT v2 | 10문서·69p | 동결 broad | 0 | 6 | 미완료 | broad 정책 거부 |
| list-item DEV v1 | 8문서 ID, 128행 | 탐색 보류 | 3 | 125 gold negatives | - | 한화 양성 편중 발견 |
| list-item DEV v2 | 9문서 ID, 144행 | 96 조합 | 12 | 0 | 6 | 보수적 정책 동결 |
| list-item HOLDOUT v1 | 3문서·13p | 동결 | 0 | 0 | 0 | 67/67 정상 보존 |
| 신규 HOLDOUT 2회 | 8문서·16p | 동결 | 자동 후보 0 | 0 | 미산출 | 효용 재현 실패 |
| 적용 데모 | 한화 1문서 | max 3 | 3 적용 | - | - | schema 경로 검증 |

## 5. AutoResearch 사용 효과

### 실제로 좋아진 점

- 수동 threshold 조정이 아니라 모든 후보 설정과 결과를 JSON/TSV로 남겼다.
- 숫자만 조정하는 접근이 실패한다는 것을 1,120조합으로 확인했다.
- 구조 guard를 고정하고 수치만 제한적으로 탐색했다.
- 양성이 한 문서에만 있을 때 정책 확정을 중단했다.
- NOAA를 추가해 양성 문서를 2종으로 늘렸다.
- DEV와 HOLDOUT을 분리하고, 실패한 HOLDOUT을 성능으로 재사용하지 않았다.
- 안전한 자동 후보와 보수적 원본 유지를 구분했다.

### 좋아졌다고 말하면 안 되는 점

- broad DEV의 100%를 범용 성능으로 말하면 안 된다.
- `0~25/35`가 유일한 최적 threshold라고 말하면 안 된다.
- 9문서 DEV를 신규 HOLDOUT 성능으로 말하면 안 된다.
- 한화 3건 적용을 독립 문서 범용 효용으로 말하면 안 된다.
- 신규 HOLDOUT에서 후보가 0이므로 heading 자동승격 Precision을 새로 계산할 수 없다.

## 6. 왜 매회 개선 그래프가 없는가

실제 실행기는 “한 번 바꾸고 결과를 보고 다음 값을 제안하는” 순차 최적화기가 아니라 정해진 검색 공간을 한 번에 전수 평가하는 grid search다. 따라서 존재하지 않는 회차별 개선 곡선을 만들면 안 된다.

발표에서는 다음 네 checkpoint만 실제 개선 과정으로 보여주는 것이 정확하다.

```text
한화 1문서 잠정 휴리스틱
  → 15 sample에서 숫자 threshold 실패 확인
  → 구조 guard 도입 후 broad HOLDOUT 실패
  → list_item 전용으로 축소 + NOAA 보강 + 144행/96조합
  → 12 TP/0 FP DEV 정책, 신규 HOLDOUT no-hit로 default-off 동결
```

## 7. 핵심 증거 파일

- 최초 로직: `heading_validation/density_promotion/DENSITY_HEADING_CORRECTION_SPEC.md`
- 1,120조합: `heading_validation/evaluation/crossdoc_119_v2_threshold_search.json`
- 구조 가설: `heading_validation/evaluation/crossdoc_119_v2_structure_hypothesis.json`
- 23,328조합: `autoresearch_lite/results/heading_v2/summary.json`, `results.tsv`
- list-item 라벨: `heading_validation/list_item_autoresearch_dev_v2/artifacts/list_item_dev_v2.csv`
- 96조합: `heading_validation/list_item_autoresearch_dev_v2/artifacts/all_results.json`
- 최종 DEV 정책: `heading_validation/list_item_autoresearch_dev_v2/artifacts/best_policy.json`
- 독립 정상 보존: `heading_validation/list_item_heading_holdout_v1/holdout_metrics.json`
- 실제 적용: `handoff/docling_postprocess_merge_handoff_20260825/heading_evidence/promotion_audit_max3_docling119.json`
