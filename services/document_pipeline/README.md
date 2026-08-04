# 문서 파이프라인 모듈

현재 구현 경계는 다음과 같다.

1. Django가 Drive 원문을 로컬 문서 저장소에 저장한다.
2. Django가 Cloudflare Tunnel 기반의 만료형 서명 URL을 만든다.
3. RunPod Serverless CUDA Worker가 PDF/DOCX를 Docling으로 파싱한다.
4. Worker가 본문과 표를 구조 보존 청킹하고
   `google/embeddinggemma-300m`으로 768차원 임베딩을 만든다.
5. Django가 Block, Chunk, Vector를 하나의 PostgreSQL 트랜잭션으로 적재한다.
6. 업무 추출 Query Agent가 같은 모델로 검색 질의를 임베딩하고 pgvector에서
   근거 Chunk를 검색한다.
7. Extraction Agent는 검색된 Chunk에 직접 근거가 있는 업무만 구조화해 반환한다.

구성 누락, 원문 불일치, 768차원 불일치, 준비되지 않은 문서에는 대체값을
사용하지 않고 명시적으로 오류를 반환한다. 전체 변경 명세는
`docs/11_코드설명/RunPod_구조보존청킹_멀티에이전트_병합_구현명세.md`를 참고한다.
