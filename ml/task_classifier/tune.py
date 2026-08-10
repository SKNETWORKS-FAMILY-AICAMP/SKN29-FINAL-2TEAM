# -*- coding: utf-8 -*-
import warnings, numpy as np, pandas as pd, json, joblib
from taskclf import build_pipeline, select_text
warnings.filterwarnings('ignore')
from sklearn.model_selection import StratifiedKFold, train_test_split, GridSearchCV, learning_curve
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline, FeatureUnion
from sklearn.preprocessing import FunctionTransformer
from sklearn.metrics import (f1_score, accuracy_score, precision_score, recall_score,
                             roc_auc_score, classification_report, confusion_matrix)
SEED=42
df=pd.read_csv('chunks_labeled.csv'); df['heading']=df.heading.fillna('')
Xtr,Xte,ytr,yte=train_test_split(df,df.label.values,test_size=0.25,stratify=df.label.values,random_state=SEED)
cv=StratifiedKFold(5,shuffle=True,random_state=SEED)

def build(C=10.0, wng=(1,2), cng=(2,4), mindf=2):
    return build_pipeline(C=C, word_ngram=wng, char_ngram=cng, min_df=mindf)

grid={'clf__C':[0.3,1.0,3.0,10.0],
      'vec__w__ngram_range':[(1,1),(1,2)],
      'vec__c__ngram_range':[(2,4),(2,5)],
      'vec__w__min_df':[1,2]}
gs=GridSearchCV(build(),grid,cv=cv,scoring='f1_macro',n_jobs=-1,return_train_score=True)
gs.fit(Xtr,ytr)
print("최적 조합:",json.dumps({k:str(v) for k,v in gs.best_params_.items()},ensure_ascii=False))
print(f"CV F1(macro) {gs.best_score_:.4f}  (탐색 {len(gs.cv_results_['params'])}조합)\n")

best=gs.best_estimator_
pred=best.predict(Xte); prob=best.predict_proba(Xte)[:,1]
print("=== 홀드아웃 테스트 (114건) ===")
print(classification_report(yte,pred,target_names=['보일러플레이트(0)','실행 과업(1)'],digits=3))
cm=confusion_matrix(yte,pred); print("혼동행렬 [[TN FP],[FN TP]]:\n",cm)
final=dict(acc=accuracy_score(yte,pred),f1m=f1_score(yte,pred,average='macro'),
           prec=precision_score(yte,pred),rec=recall_score(yte,pred),auc=roc_auc_score(yte,prob),
           cv_f1m=gs.best_score_, params={k:str(v) for k,v in gs.best_params_.items()},
           cm=cm.tolist())

# ── 과적합 진단: learning curve ──
sizes,tr,va=learning_curve(build(**{'C':gs.best_params_['clf__C']}),Xtr,ytr,cv=cv,scoring='f1_macro',
                           train_sizes=np.linspace(0.2,1.0,6),n_jobs=-1,random_state=SEED)
print("\n=== Learning Curve (F1 macro) ===")
print(f"{'학습건수':>8} {'train':>8} {'val':>8} {'격차':>8}")
lc=[]
for n,a,b in zip(sizes,tr.mean(1),va.mean(1)):
    print(f"{int(n):>8} {a:>8.3f} {b:>8.3f} {a-b:>8.3f}"); lc.append([int(n),round(a,4),round(b,4)])
final['learning_curve']=lc

# ── 일반화 진단: 문서 단위 leave-one-out ──
# 문서 구분: 한화 카탈로그 / 감리 제안서 / 정보시스템 RFP 를 어휘로 나눈다
import re
def docgroup(t):
    t=str(t)
    if re.search(r'한화|압축기|Compressor|SM\d|SA\d|Hanwha|Impeller|Turbo|CFM|bar A',t): return 'catalog'
    if re.search(r'감리|감리원|수석감리|시정조치',t): return 'audit'
    return 'rfp'
df['doc']=df.search_text.map(docgroup)
print("\n=== 문서군별 분포 ===")
print(pd.crosstab(df.doc,df.label,margins=True))
print("\n=== Leave-One-Document-Out (새 문서 일반화) ===")
lodo=[]
for g in df.doc.unique():
    tr_i=df.doc!=g; te_i=df.doc==g
    if df[te_i].label.nunique()<2: 
        print(f"  {g:8s} 양성 0건 → F1 산출 불가, 오탐률만: ", end="")
        m=build(C=gs.best_params_['clf__C']).fit(df[tr_i],df[tr_i].label)
        p=m.predict(df[te_i]); print(f"{p.mean():.3f} ({p.sum()}/{len(p)}건 오탐)")
        lodo.append([g,len(df[te_i]),int(df[te_i].label.sum()),None,float(p.mean())]); continue
    m=build(C=gs.best_params_['clf__C']).fit(df[tr_i],df[tr_i].label)
    p=m.predict(df[te_i]); f=f1_score(df[te_i].label,p,average='macro')
    print(f"  {g:8s} n={len(df[te_i]):3d} 양성={df[te_i].label.sum():3d}  F1(macro)={f:.3f}")
    lodo.append([g,len(df[te_i]),int(df[te_i].label.sum()),round(f,4),None])
final['lodo']=lodo

best.fit(df,df.label.values)          # 전체로 재학습해 저장
joblib.dump(best,'task_classifier_v1.pkl')
import os; final['model_size_kb']=round(os.path.getsize('task_classifier_v1.pkl')/1024,1)
import time
t0=time.perf_counter()
for _ in range(100): best.predict(df.iloc[[0]])
final['infer_ms']=round((time.perf_counter()-t0)/100*1000,2)
n_feat=best.named_steps['vec'].transform(df.iloc[:1]).shape[1]
final['n_features']=int(n_feat)
json.dump(final,open('final_metrics.json','w'),ensure_ascii=False,indent=2)
print(f"\n모델 저장 task_classifier_v1.pkl  {final['model_size_kb']} KB | 피처 {n_feat:,}차원 | 추론 {final['infer_ms']} ms/건")
