# 문서 파이프라인 모듈

구현 순서:

1. Drive/로컬 파일 원천 등록
2. 파일 시그니처·MIME 검증
3. PDF/DOCX Parser
4. DocumentBlock 정규화
5. KnowledgeItem 추출
6. ProjectKnowledgeModel 통합

Embedding·Vector 검색은 전체 Task 추출의 주 입력이 아니라 보조 검색으로 연결한다.
