# Agent Eval V2 HOLDOUT 전달 자료

이 폴더는 HOLDOUT 담당 팀원에게 전달하는 **공개 가능한 빈 양식**이다. 실제 질문,
정답, 문서명, 날짜, required fact, forbidden claim, canary를 이 Git 폴더에 작성하지 않는다.

처음에는 다음 문서만 읽는다.

1. [`01_HOLDOUT_비공개_문제_제작_가이드.md`](01_HOLDOUT_비공개_문제_제작_가이드.md)
2. [`05_HOLDOUT_검수_체크리스트.md`](05_HOLDOUT_검수_체크리스트.md)

비공개 저장소에서 아래 파일을 복사해 문제별 package를 만든다.

- [`02_fixture.template.yaml`](02_fixture.template.yaml)
- [`03_gold.template.yaml`](03_gold.template.yaml)
- [`04_public_manifest.template.yaml`](04_public_manifest.template.yaml)

```text
공개 Git                         접근 제한 비공개 저장소
가이드·빈 템플릿               실제 HOLDOUT package
                               ├─ fixture.yaml
                               ├─ gold.yaml
                               ├─ source 파일 또는 snapshot
                               └─ private package manifest
```

Jihun은 S01~S11 DEV 설계·Candidate 개선을 담당한다. HOLDOUT 담당자는 Phase 9 freeze
승인 전에는 실제 batch를 실행하지 않으며, round 종료 전까지 Jihun에게 원문·gold·개별
trace를 공개하지 않는다. 공식 점수는 사람 입력이 아니라 deterministic checker와
`gpt-5.6-sol` Judge가 생성한다.

