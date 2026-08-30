# Reading Order Wilson 94 최종 검증 결과

## 결론

Docling 2.119로 사전 동결한 신규 공식 문서 3종 11쪽을 모두 오류 없이 변환했다. 후보 2건은 육안과 JSON 좌표를 함께 확인했을 때 모두 TP였지만, 동결된 자동 적용 조건을 통과한 것은 1건이다.

- 신규 후보 TP: 2 / FP: 0
- 신규 자동 적용: **1 TP / 0 FP**
- 신규 검토 보존: **1 TP / 0 FP**
- 누적 자동 적용: **60 TP / 0 FP**
- 관측 Precision: **100%**
- Wilson 95% 하한: **93.9828%**

소수 첫째 자리로는 94.0%지만, 엄밀한 `> 94%` 기준은 0.0172%p 차이로 통과하지 못했다. 0 FP를 유지한 자동 적용 TP가 1건 더 쌓여 61/61이 되면 하한은 94.0756%다.

## 신규 후보 판정

두 후보 모두 NYSNA 2025 Exhibitor Prospectus 4쪽에서 검출됐다.

1. `*Not eligible for non-members → *After 8/1/2025`
   - 실제 시각 순서: `*After 8/1/2025 → *Not eligible for non-members`
   - 라벨: TP
   - 처리: 두 요소 사이의 시각적 sibling 1개가 검출되어 `REVIEW_REQUIRED`, 원본 보존
2. `badge note → $25 each`
   - 실제 시각 순서: `$25 each → badge note`
   - 라벨: TP
   - 처리: 같은 부모·인접 sibling·중간 요소 없음·복잡 좌표 없음 조건을 통과해 자동 swap

나머지 FOODPOLIS 2쪽, NYSNA 3개 range, SEBC 2개 range에서는 실행 후보가 없었고 원본을 보존했다.

## 마감 판단

94%를 넘기기 위해 `visual_intervening_sibling_count == 0` 조건을 사후 완화하면 이번 결과에 맞춘 threshold 조정이 된다. 기존 fail-closed 정책과 독립 HOLDOUT 원칙을 지키기 위해 규칙은 변경하지 않았다.

따라서 최종 병합 표기는 다음이 정확하다.

> 같은 부모 내 인접 sibling 국소 역전에 대해 60건 연속 오탐 없이 자동 보정했고, 관측 Precision 100%, Wilson 95% 하한 93.98%를 확인했다. 전체 문서 순서 복원이나 Recall 성능을 의미하지 않는다.
