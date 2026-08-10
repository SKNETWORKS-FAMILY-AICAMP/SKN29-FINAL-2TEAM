# -*- coding: utf-8 -*-
"""과업 서술 vs 보일러플레이트 이진 분류 — 모델 비교 실험"""
import json, warnings, numpy as np, pandas as pd
warnings.filterwarnings('ignore')
from sklearn.model_selection import StratifiedKFold, train_test_split, cross_validate, learning_curve, GridSearchCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.svm import LinearSVC
from sklearn.calibration import CalibratedClassifierCV
from sklearn.pipeline import Pipeline, FeatureUnion
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.compose import ColumnTransformer
from sklearn.metrics import (accuracy_score, f1_score, precision_score, recall_score,
                             roc_auc_score, classification_report, confusion_matrix)
from xgboost import XGBClassifier
import joblib

SEED = 42
df = pd.read_csv('chunks_labeled.csv'); df['heading'] = df.heading.fillna('')
X, y = df, df.label.values

Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25, stratify=y, random_state=SEED)
print(f"train {len(Xtr)} (양성 {ytr.sum()}) / test {len(Xte)} (양성 {yte.sum()})\n")

cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
SCORING = {'acc':'accuracy','f1m':'f1_macro','prec':'precision','rec':'recall','auc':'roc_auc'}

def word_tfidf(**kw):
    d = dict(analyzer='word', ngram_range=(1,2), min_df=2, sublinear_tf=True, max_features=20000)
    d.update(kw); return TfidfVectorizer(**d)
def char_tfidf(**kw):
    d = dict(analyzer='char_wb', ngram_range=(2,5), min_df=2, sublinear_tf=True, max_features=30000)
    d.update(kw); return TfidfVectorizer(**d)

TEXT = 'search_text'
def txt(X): return X[TEXT]

from sklearn.preprocessing import FunctionTransformer
pick_text = FunctionTransformer(txt, validate=False)

def make(vec, clf):
    return Pipeline([('pick', pick_text), ('vec', vec), ('clf', clf)])

EXPS = []
EXPS.append(('EXP-01','Baseline','TF-IDF(word 1-2gram) + LogisticRegression',
             make(word_tfidf(), LogisticRegression(max_iter=2000, random_state=SEED))))
EXPS.append(('EXP-02','ML','TF-IDF(char_wb 2-5gram) + LogisticRegression',
             make(char_tfidf(), LogisticRegression(max_iter=2000, random_state=SEED))))
EXPS.append(('EXP-03','ML','TF-IDF(word+char union) + LogisticRegression',
             make(FeatureUnion([('w',word_tfidf()),('c',char_tfidf())]),
                  LogisticRegression(max_iter=2000, random_state=SEED))))
EXPS.append(('EXP-04','ML','TF-IDF(word) + LinearSVC',
             make(word_tfidf(), CalibratedClassifierCV(LinearSVC(random_state=SEED), cv=3))))
EXPS.append(('EXP-05','ML','TF-IDF(word) + XGBoost',
             make(word_tfidf(), XGBClassifier(n_estimators=300, max_depth=6, learning_rate=0.1,
                  subsample=0.8, colsample_bytree=0.8, eval_metric='logloss', random_state=SEED))))
EXPS.append(('EXP-06','ML','TF-IDF(word+char) + LogReg, class_weight=balanced',
             make(FeatureUnion([('w',word_tfidf()),('c',char_tfidf())]),
                  LogisticRegression(max_iter=2000, class_weight='balanced', random_state=SEED))))

# ── 누수 검증용 ──
meta_ct = ColumnTransformer([('bt', OneHotEncoder(handle_unknown='ignore'), ['block_type']),
                             ('tc', StandardScaler(), ['token_cnt'])])
EXPS.append(('EXP-09','누수 상한','block_type + token_cnt 만 (본문 미사용)',
             Pipeline([('ct', meta_ct), ('clf', LogisticRegression(max_iter=2000,
                        class_weight='balanced', random_state=SEED))])))

class TextPlusMeta(Pipeline): pass
text_union = ColumnTransformer([
    ('w', word_tfidf(), TEXT), ('c', char_tfidf(), TEXT),
    ('bt', OneHotEncoder(handle_unknown='ignore'), ['block_type']),
    ('tc', StandardScaler(), ['token_cnt'])])
EXPS.append(('EXP-07','Ablation','본문 + block_type + token_cnt (누수 피처 투입)',
             Pipeline([('ct', text_union), ('clf', LogisticRegression(max_iter=2000,
                        class_weight='balanced', random_state=SEED))])))

rows = []
for eid, kind, desc, pipe in EXPS:
    r = cross_validate(pipe, Xtr, ytr, cv=cv, scoring=SCORING, n_jobs=1, return_train_score=True)
    pipe.fit(Xtr, ytr)
    pred = pipe.predict(Xte)
    prob = pipe.predict_proba(Xte)[:,1] if hasattr(pipe,'predict_proba') else pred
    rows.append(dict(exp=eid, kind=kind, desc=desc,
        cv_acc=r['test_acc'].mean(), cv_f1m=r['test_f1m'].mean(), cv_f1m_std=r['test_f1m'].std(),
        cv_prec=r['test_prec'].mean(), cv_rec=r['test_rec'].mean(), cv_auc=r['test_auc'].mean(),
        train_f1m=r['train_f1m'].mean(),
        te_acc=accuracy_score(yte,pred), te_f1m=f1_score(yte,pred,average='macro'),
        te_prec=precision_score(yte,pred,zero_division=0), te_rec=recall_score(yte,pred),
        te_auc=roc_auc_score(yte,prob)))
    print(f"{eid} {desc[:52]:52s} CV_F1m {r['test_f1m'].mean():.3f}±{r['test_f1m'].std():.3f} "
          f"| train_F1m {r['train_f1m'].mean():.3f} | test_F1m {f1_score(yte,pred,average='macro'):.3f}")

res = pd.DataFrame(rows)
res.to_csv('exp_results.csv', index=False)
print("\n" + "="*100)
print(res[['exp','cv_acc','cv_f1m','cv_prec','cv_rec','cv_auc','train_f1m','te_f1m']].round(3).to_string(index=False))
