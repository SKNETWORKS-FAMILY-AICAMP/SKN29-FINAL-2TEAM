# 평가 (`tests/eval/`)

기존 단위 테스트(`tests/test_*.py`)와 **다른 것**을 잰다. 단위 테스트는 "코드가
계약대로 도는가"를 묻고 여기는 "검색과 추출이 실제로 맞는 것을 찾는가"를 묻는다.
그래서 `manage.py test` 가 여기를 자동으로 돌리지 않는다 — DB·RunPod·모델이
필요하고 값이 든다.

## 지금 있는 것

`coarse_recall.py` — 문서 단위 Recall 측정. A안(요약 임베딩으로 문서를 먼저
좁히는 coarse 단계)이 정답 문서를 후보에 남기는지를 본다.

**이 숫자가 A vs A′ 판단의 근거다.** coarse 가 요약만으로 부족하다는 결론이
나오면 tsvector 전문 인덱스를 얹는다(A′ — `docs/TO-BE/12_문서처리_방식_비교.md`
§5). `doc_meta.extracted_text` 에 원문을 보관해 둔 이유가 이것이라, 전환은
인덱스 추가만으로 끝난다.

Recall 을 재는 이유는 coarse 가 **거르는 단계**이기 때문이다. 여기서 떨어진
문서는 뒤에서 되살아날 길이 없다 — precision 이 낮으면 fine 단계가 정리하지만
recall 이 낮으면 답이 아예 안 나온다.

## G-QUERY 골든셋 형식

`tests/eval/golden/*.json`. Git 에 올린다 — 팀이 같은 기준으로 재야 한다.

```json
{
  "team_id": "TE001",
  "queries": [
    {
      "id": "GQ001",
      "query": "이 사업의 사업 기간이 어떻게 적혀 있는가",
      "relevant_doc_ids": ["DC001", "DC002"],
      "note": "감리 16개월 / 개발 대상 17개월이 서로 다른 문서에 있다"
    }
  ]
}
```

- `relevant_doc_ids` — **문서 단위**다. 청크가 아니다. coarse 가 문서를 고르는
  단계라 정답도 문서로 적는다.
- 여러 문서에 답이 흩어져 있으면 전부 적는다. 하나만 적으면 나머지를 찾아낸
  것이 오답으로 잡힌다.
- `note` 는 나중에 이 정답이 왜 정답인지 다시 판단할 때 쓴다. 골든셋은 사람이
  만들고, 만든 사람은 잊는다.

## 실행

```bash
DATABASE_URL="postgres://project_copilot:project_copilot@localhost:5432/project_copilot" \
  python tests/eval/coarse_recall.py tests/eval/golden/<파일>.json
```

질의마다 임베딩 1개를 만든다(RunPod). 골든셋이 커지면 그만큼 걸린다.
