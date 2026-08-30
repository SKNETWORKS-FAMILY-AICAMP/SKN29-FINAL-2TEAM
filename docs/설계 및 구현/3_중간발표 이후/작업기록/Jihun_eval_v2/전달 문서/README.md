# Agent Eval V2 HOLDOUT 전달 자료

이 폴더는 HOLDOUT 담당 팀원에게 전달하는 **공개 가능한 빈 양식과 참고 자료**다. 실제
질문, 정답, 문서명, 날짜, required fact, forbidden claim, canary를 이 Git 폴더에
작성하지 않는다.

## 읽는 순서

1. [`01_HOLDOUT_비공개_문제_제작_가이드.md`](01_HOLDOUT_비공개_문제_제작_가이드.md) — 문제 하나를 만드는 전체 절차
2. [`06_설계_참고/`](06_설계_참고/) — 시나리오가 정확히 뭘 검사하는지, gold를 어떤 채점 기준에 묶는지 (03_scenario_contract, 04_fixture_and_gold_policy, 05_scoring_contract, 02_risk_scenario_matrix)
3. [`07_DEV_비교용_fixture/`](07_DEV_비교용_fixture/) — "DEV 독립성" 검증용 기존 DEV fixture 10개 (S01~S07, S09A/B. S08은 Jira 변경 미승인이라 제외, S10·S11은 별도 Expansion HOLDOUT 라운드에서 다룬다)
4. [`08_비공개_저장소_및_커밋먼트_설정_가이드.md`](08_비공개_저장소_및_커밋먼트_설정_가이드.md) — 실행 전에 먼저 준비해야 하는 인프라(접근 제한 저장소, HMAC 커밋먼트 도구)
5. [`05_HOLDOUT_검수_체크리스트.md`](05_HOLDOUT_검수_체크리스트.md) — Reviewer가 승인 전 확인하는 최종 체크리스트

비공개 저장소를 만든 뒤, 아래 템플릿을 그 저장소로 복사해 문제별 package를 만든다.

- [`02_fixture.template.yaml`](02_fixture.template.yaml)
- [`03_gold.template.yaml`](03_gold.template.yaml)
- [`04_public_manifest.template.yaml`](04_public_manifest.template.yaml)
- [`tools/make_commitment.py`](tools/make_commitment.py) — fixture/gold/package의 HMAC commitment를 계산하는 스크립트 (반드시 비공개 저장소 안에서만 실행)

```text
공개 Git                         접근 제한 비공개 저장소
가이드·빈 템플릿·설계 참고        실제 HOLDOUT package
·DEV 비교용 fixture             ├─ secrets/hmac_secret.key
                                ├─ fixture.yaml
                                ├─ gold.yaml
                                ├─ source 파일 또는 snapshot
                                └─ private package manifest
```

Jihun은 S01~S11 DEV 설계·Candidate 개선을 담당한다. HOLDOUT 담당자는 Phase 9 freeze
승인 전에는 실제 batch를 실행하지 않으며, round 종료 전까지 Jihun에게 원문·gold·개별
trace를 공개하지 않는다. 공식 점수는 사람 입력이 아니라 deterministic checker와
`gpt-5.6-sol` Judge가 생성한다.
