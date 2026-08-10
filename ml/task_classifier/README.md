# 과업 서술 분류기 (task_classifier_v1)

문서 청크가 「실행 과업 서술」인지 「사업관리 보일러플레이트」인지 판정한다.
벡터 검색이 뽑은 근거 후보를 업무 추출 에이전트에 넘기기 전에 거르는 자리에 놓인다.

## 파일

| 파일 | 설명 |
|---|---|
| `task_classifier_v1.pkl` | 학습된 모델 (joblib, 766 KB) |
| `taskclf.py` | 파이프라인 구성 모듈. **로딩 시 import 가능해야 한다** |
| `chunks_labeled.csv` | 학습 데이터 456건 (label: 1=과업, 0=비과업) |
| `train.py` | 후보 모델 6종 + 누수 검증 2종 비교 실험 |
| `tune.py` | Grid Search · 학습곡선 · Leave-One-Document-Out |
| `exp_results.csv` · `final_metrics.json` | 실험 결과 원본 |
| `learning_curve.png` | 학습곡선 |

## 로딩과 추론

```python
import joblib, pandas as pd
from taskclf import select_text      # 반드시 먼저 import (pickle 복원에 필요)

model = joblib.load('task_classifier_v1.pkl')

df = pd.DataFrame({'search_text': ['3) 시스템 시험 및 운영방안 - 테스트 단계별로 수행방법, 절차를 기술한다',
                                   'Ⅰ. 사업 개요 · · · · · · · · · · · · · 4']})
print(model.predict(df))              # [1 0]
print(model.predict_proba(df)[:, 1])  # 과업일 확률
```

## 성능 (홀드아웃 114건)

Accuracy 0.930 · F1(macro) 0.891 · Recall(과업) 0.905 · ROC-AUC 0.987
5-fold CV F1(macro) 0.910 ± 0.020 · 추론 1.44 ms/건 (CPU)

## 한계

- **문서 간 일반화가 약하다.** Leave-One-Document-Out F1(macro) 0.585~0.762.
  무작위 분할의 0.910 은 같은 문서 안의 어휘 공유 때문에 낙관적이다.
- 학습 표본 456건(양성 85건), 원천 문서 3건. 학습곡선이 아직 수렴하지 않았다.
- 라벨은 1인 판정. 표본 교차 검수 미실시.
- `scikit-learn 1.8.0` 에서 저장. 버전이 다르면 경고가 난다.

## 재현

```bash
pip install scikit-learn==1.8.0 xgboost pandas joblib matplotlib
python train.py     # 후보 비교
python tune.py      # 튜닝·진단·모델 저장
```
