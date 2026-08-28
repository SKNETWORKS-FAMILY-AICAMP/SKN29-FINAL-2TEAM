# 실문서 기반 문서 검색 평가 가이드

## 목적과 경계

합성 평가에서 고른 현재 검색 방식(vector 0.5 + lexical 0.5)이 실제 프로젝트
문서에서도 벡터 단독보다 나쁘지 않은지 확인한다. 이 세트는 새 가중치 선택이나
검색 규칙 튜닝에 사용하지 않는다. 결과가 좋지 않으면 실패 유형을 기록하고,
별도의 다음 개발 세트를 만든 뒤에만 알고리즘 변경을 검토한다.

실문서 원문, 개인정보, 고객명, 비밀정보는 Git에 넣지 않는다. 이 디렉터리에는
비식별 ID와 사람이 확정한 근거 위치만 커밋한다.

## 현재 로컬 준비 상태

2026-08-28 기준 로컬 DB에는 사용 가능한 개인 문서 47개(Word 27, Excel 20)가
있지만 활성 청크와 벡터 색인은 0개다. 평가 전 문서 소유자와 사용 범위를 확인하고
선정 문서만 제품 문서 처리 파이프라인으로 색인해야 한다.

현재 프로젝트 `.env`의 `DATABASE_URL`은 공용 RDS가 아니라 Docker 로컬 DB
`db:5432/project_copilot`을 가리킨다. AWS Compose도 별도 공용 DB 변수를 갖지
않고 같은 `.env`를 읽으므로, 이 PC의 현재 환경변수만으로 공용 DB에 접속할 수 없다.

## 공용 DB 자료를 사용할 때의 안전한 방식

웹·워커의 `DATABASE_URL`을 공용 RDS로 바꿔 평가하지 않는다. 애플리케이션 기동,
백그라운드 작업, 실수한 관리 명령이 공용 DB에 쓰기를 만들 수 있다.

공용 DB를 쓰려면 다음 조건을 모두 지킨다.

1. 운영 설정과 분리된 `EVAL_SOURCE_DATABASE_URL` 같은 일회성 평가 전용 변수만 쓴다.
2. 가능하면 SELECT만 허용된 전용 DB role을 발급받는다. 마스터 계정은 쓰지 않는다.
3. 연결 직후 read-only transaction, 짧은 statement timeout을 강제한다.
4. 사용자에게 승인받은 team/account/doc ID allowlist 밖의 행은 읽지 않는다.
5. `doc`의 승인 메타데이터, 현재 revision의 `doc_block`, 활성 `chunk`, 해당
   `vec_idx`만 로컬 격리 DB로 복사한다. 계정·대화·업무 등 다른 표는 가져오지 않는다.
6. 원문이 필요하지 않고 공용 DB에 청크·embedding이 있으면 S3 원문은 내려받지 않는다.
7. 복사본에서 개인정보·고객명을 비식별화할 수 있는지 확인하고 보관·폐기 시점을 정한다.
8. 실제 벡터/하이브리드 평가는 공용 DB가 아니라 로컬 복사본에서 실행한다.

승인 범위는 `tests/eval/real/approved_documents.json`의 정확한
`doc_id + revision + content_hash` 8개로 동결한다. 실행 시점에 조건에 맞는 문서
8개를 다시 고르는 방식은 사용하지 않는다.

공용 DB에 청크나 embedding이 없다면 RDS만으로는 평가할 수 없다. 이 경우 승인된
S3 원문 또는 비식별 복사본을 로컬 파이프라인으로 색인해야 한다.

## 권장 최소 구성

- 실제 문서 10~20개
- 사람이 작성하고 검수한 질문 15~20개
- 자연어 표현 변형 4개 이상
- 유사 문서·개정본 혼동 4개 이상
- 날짜·금액·수치 2개 이상
- 사람·역할·프로젝트명 2개 이상
- 표 안의 값 2개 이상

한 질문에 여러 유형 태그를 붙일 수 있다. 개수를 채우기 위해 무의미한 질문을
만들지 않는다.

## 고정 순서

1. 평가에 사용할 비민감 문서와 소유 계정·팀 범위를 사람이 승인한다.
2. 선정 문서만 제품 파이프라인으로 파싱·청킹·임베딩한다.
3. 검색 결과를 보기 전에 사람이 자연스러운 질문을 작성한다.
4. 사람이 원문에서 정답 revision과 근거 chunk/block을 지정한다.
5. 다른 사람이 가능한 범위에서 질문·근거를 교차 검수한다.
6. `golden.template.json`을 복사해 정답지를 만들고 `FROZEN`으로 바꾼다.
7. 정답지 동결 뒤 벡터 단독과 현재 하이브리드 0.5/0.5를 한 번 비교한다.
8. Recall@20, Precision@5/8/20, MRR, 금지 근거 Top-3 잠식을 기록한다.

검색 결과를 본 뒤 누락 정답을 발견하면 원문을 사람이 검수하고 `label_corrections`
감사 이력을 남긴다. 그 보정으로 알고리즘을 다시 선택하지 않고 전체 결과만 다시
계산한다.

질문 문구는 Codex가 검색 결과나 청크를 보고 대신 생성하지 않는다. 사람이 검색을
실행하기 전에 실제 업무에서 물을 법한 질문을 먼저 작성하고 작성 시각과 작성자를
남긴다. Codex는 형식 검증, 중복 검사, 지표 계산만 보조한다.

동결할 때 문서는 `doc_id + revision + content_hash`, 검색기는 vector/lexical 및
내부 가중치, Top-K, embedding model, 실행 commit SHA까지 함께 기록한다. 같은
정답지를 다시 실행했을 때 데이터 변화와 코드 변화를 구분하기 위한 기준이다.

## 합격과 중단 기준

- Evidence Recall@20이 벡터 단독 이상
- MRR과 Precision@5의 벡터 대비 하락폭이 각각 0.05 이내
- 권한 밖·삭제·이전 revision 근거 Top-3 잠식 0
- 심각한 오답이 반복되지 않음

15~20개는 강한 일반화 증명이 아니라 실제 데이터에서의 최소 독립 확인이다.
한두 질의의 변화보다 반복되는 실패 유형과 사용자 체감 상위 순위를 함께 본다.

## 2026-08-28 공용 DB 읽기 전용 조사 결과

- 평가 전용 URL은 서울 RDS를 가리키고 SSL을 요구한다.
- 연결 계정은 SELECT 전용이 아니며 DB CREATE와 `doc` INSERT/UPDATE/DELETE가
  가능한 고권한 계정이다. 웹·워커와 일반 관리 명령에는 절대 사용하지 않는다.
- 조사 세션은 `default_transaction_read_only=on`, statement timeout 5초,
  lock timeout 1초를 강제했고 SELECT 집계 후 rollback했다.
- 사용 가능한 문서 13개, 활성 청크 301개, 벡터 301개가 있다.
- 현재 revision까지 완전 색인된 문서는 10개다. 개인 Markdown 2개는 평가 범위에서
  제외하고 팀 공유 PDF 8개만 복사 후보로 둔다.
- 팀 PDF의 본문·청크·embedding을 로컬로 복사하는 것은 별도 사용자 확인 후 진행한다.

## 2026-08-28 승인 데이터 복사 결과

- 사용자가 팀 공유 PDF 8개의 실문서 평가용 로컬 복사를 승인했다.
- `scripts/import_real_document_search_eval.py`가 공용 RDS를 read-only로 열고,
  개인 문서를 제외한 팀 PDF 8개의 current revision만 로컬 `eval_real` 스키마에
  복사했다.
- 복사 결과: 문서 8, 블록 238, 청크 294, 벡터 294. content hash와 벡터 누락은
  0개이며 원본 PDF 파일은 복사하지 않았다. 로컬 저장 크기는 약 2.1MB다.
- 승인자·승인 문구·가져온 시각·폐기 예정일(2026-09-04)과 source/runtime DB
  환경을 `eval_real.dataset_meta`에 기록했다.
- 데이터 출처 RDS는 PostgreSQL 18.3이며 pg_trgm이 없다. 평가는 PostgreSQL
  17.10, pg_trgm 1.6, vector 0.8.5, FTS simple인 로컬 DB에서 수행한다.
- 이번 실문서 평가는 current revision 검색 품질만 다룬다. 이전 revision 누수는
  기존 합성·회귀 테스트가 담당한다.
- 복사된 294개 embedding은 모두 768차원이지만 `vec_idx.metadata`에 모델 식별자가
  없다. 복사 후 공용 DB에서 해당 문서 이력도 정리되어, 현재 단계에서는
  `google/embeddinggemma-300m`과 동일하다고 입증할 수 없다. 차원 일치는 충분한
  증거가 아니므로 provenance 상태를 `UNVERIFIED`로 두고 벡터 비교 실행을 보류한다.
- 실문서 평가는 문서 8개·청크 294개의 current revision에 한정된 최소 확인이며,
  전체 문서 유형이나 향후 revision에 대한 일반화 증명이 아니다.
- Golden JSON 자체에는 본문이 없지만 로컬 `eval_real`에는 실제
  `doc_block.content`와 `chunk.search_text`가 있다. 두 범위를 하나의
  `contains_raw_content`로 표현하지 않고 각각 별도 필드로 기록한다.
- 평가 종료 또는 폐기 예정일 도달 시 로컬 DB에서 `eval_real` 스키마만 제거한다.
  제거 전 정답지와 결과에 본문이 포함되지 않았는지 다시 확인한다.

## 로컬 평가 데이터 폐기

`expires_at`은 기록일 뿐 자동 삭제 기능이 아니다. 평가 완료 직후에는 다음처럼
명시적 확인 문구와 사유를 주어 로컬 `eval_real` 스키마만 제거한다.

```powershell
docker compose -f infra/docker/docker-compose.yml exec -T web python scripts/cleanup_real_document_search_eval.py --confirm DROP-EVAL-REAL --reason evaluation-complete
```

기한 만료 사유로 제거할 때는 `--reason expired`를 쓴다. 이 방식은 기록된 만료
시각 전에는 실패한다. 명령은 대상 DB 호스트가 `db`, `localhost`, `127.0.0.1` 중
하나가 아니면 중단하며 공용 DB에는 사용할 수 없다.

## 평가 실행 전 남은 차단 조건

1. 문서 embedding과 질의 embedding의 모델·전처리 동일성을 증명한다.
2. 증명 자료가 없으면 승인받은 로컬 복사본의 `chunk.search_text` 294개를 현재
   평가 모델로 다시 임베딩하고, 모델 ID·revision·전처리·생성 시각을 기록한다.
3. 사람이 검색 전에 질문과 근거를 작성·교차 검수하고 Golden Set을 동결한다.
4. 실제 실행 commit SHA와 모든 가중치·Top-K·모델 정보를 고정한다.

현재 통합 중인 정식 Docling·청킹·임베딩 파이프라인이 반영될 때까지 별도 평가용
재임베딩 경로를 만들지 않는다. 통합 후 승인 문서를 같은 제품 파이프라인으로 다시
색인하고, 새 chunk/block ID를 기준으로 Golden Set 근거와 검색 평가를 확정한다.

## 필요한 사용자 결정

- 평가에 사용해도 되는 로컬 계정 또는 문서 묶음
- 문서 원문을 사람이 검수할 담당자
- 개인 파일을 그대로 쓸지, 비식별 평가용 복사본을 만들지
- 실제 문서·정답지의 Git 포함 가능 범위
- 공용 DB 읽기 전용 계정 또는 안전한 접속 경로 제공 가능 여부
- 공용 DB에서 로컬로 복사해도 되는 team/account/doc ID 범위
