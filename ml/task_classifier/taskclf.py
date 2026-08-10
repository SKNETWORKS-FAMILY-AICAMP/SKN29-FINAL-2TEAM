# -*- coding: utf-8 -*-
"""과업 서술 분류기 — 파이프라인 구성 요소. 모델 로딩 시 import 가능해야 한다."""
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline, FeatureUnion
from sklearn.preprocessing import FunctionTransformer

TEXT_COLUMN = 'search_text'

def select_text(X):
    """DataFrame에서 본문 열만 뽑는다. lambda 대신 이름 있는 함수여야 pickle 된다."""
    return X[TEXT_COLUMN]

def build_pipeline(C=10.0, word_ngram=(1,2), char_ngram=(2,4), min_df=2, seed=42):
    return Pipeline([
        ('pick', FunctionTransformer(select_text, validate=False)),
        ('vec', FeatureUnion([
            ('w', TfidfVectorizer(analyzer='word', ngram_range=word_ngram, min_df=min_df,
                                  sublinear_tf=True, max_features=20000)),
            ('c', TfidfVectorizer(analyzer='char_wb', ngram_range=char_ngram, min_df=min_df,
                                  sublinear_tf=True, max_features=30000))])),
        ('clf', LogisticRegression(max_iter=3000, class_weight='balanced', C=C, random_state=seed)),
    ])
