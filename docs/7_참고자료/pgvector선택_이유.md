# pgvector를 선택한 이유 — Vector DB 비교 조사

> 배경: 이 프로젝트는 원래 `chroma_setup.py`(ChromaDB)로 벡터 검색을 구현했다가, `VEC_IDX`를 PostgreSQL `pgvector` 테이블로 옮기는 방향으로 전환했다(`DB/schema.sql`, `backend/services/createDB/vec_idx_setup.py` 참고). 이 문서는 그 전환이 "왜 맞는 선택이었는지"를 다른 Vector DB(ChromaDB, 클라우드형, 하이브리드 특화형)와 비교해서 정리한다.
> 작성일: 2026-07-29

---

## 1. 우리 프로젝트에서 벡터 검색이 필요한 지점

`docs/2_데이터모델/비정형_문서_DB_설계.md`에 정리된 파이프라인 기준으로, 벡터 검색이 붙는 곳은 `CHUNK`(문서를 검색 가능한 크기로 쪼갠 텍스트) 하나뿐이다.

```
DOC → DOC_BLOCK → CHUNK → VEC_IDX(임베딩)
```

`VEC_IDX`는 CHUNK 텍스트를 벡터로 바꿔 저장하는 **보조 인덱스**일 뿐이고, 진짜 데이터(문서·지식·업무·인력)는 전부 같은 PostgreSQL 안의 일반 테이블(`doc`, `know_item`, `task`, `person` 등)에 있다. 즉 이 프로젝트는 "벡터 검색이 주력인 서비스"가 아니라 "관계형 데이터가 중심이고, 그중 텍스트 검색 한 부분만 벡터로 하는" 구조다. 이 전제가 아래 비교의 기준이 된다.

---

## 2. 비교 대상

| 구분 | 대표 제품 | 배포 형태 |
|---|---|---|
| Postgres 확장형 | **pgvector** | 우리가 이미 쓰는 PostgreSQL에 확장(extension)으로 추가 |
| 임베디드/자체 호스팅 Vector DB | **ChromaDB** | 별도 프로세스(우리도 최초엔 Docker 컨테이너로 띄웠었음) |
| 클라우드 매니지드 Vector DB | **Pinecone** 등 | 완전 관리형 SaaS, 인프라 운영 불필요 |
| 하이브리드 특화 Vector DB | **Weaviate, Qdrant** | 벡터 + 키워드(BM25) 검색을 기본 내장 |

---

## 3. 항목별 비교

| 항목 | pgvector | ChromaDB | Pinecone(클라우드형) | Weaviate/Qdrant(하이브리드형) |
|---|---|---|---|---|
| 배포 형태 | 기존 PostgreSQL에 `CREATE EXTENSION`만 추가 | 별도 서버/컨테이너 필요 | 완전 관리형(인프라 없음) | 별도 서버(자체 호스팅 또는 관리형) |
| 관계형 데이터와의 JOIN | 같은 DB라 SQL JOIN·트랜잭션 그대로 가능 | 불가능(별도 스토어, 애플리케이션 레벨에서 다시 조합) | 불가능 | 제한적(자체 스키마 안에서만) |
| 참조 무결성(FK) | 실FK로 강제 가능(`vec_idx.chunk_id → chunk.chunk_id`) | 없음 — 존재하지 않는 chunk_id를 넣어도 안 막힘 | 없음 | 부분 지원 |
| 인프라 구성 요소 | 기존 `db` 서비스 1개 그대로 사용 | Docker 서비스 1개 추가(포트 관리, 볼륨 관리 필요) | 외부 API 키·네트워크 의존 | 별도 서비스 1개 추가 |
| 비용 | 무료(오픈소스, 이미 쓰는 DB에 포함) | 무료(자체 호스팅 인프라 비용만) | 사용량 과금(서버리스 도입 후 완화됐지만 여전히 비용 발생) | 무료(자체 호스팅) 또는 관리형 과금 |
| 대규모 스케일(수천만~수억 벡터) | HNSW 파라미터 튜닝 필요, 대략 수천만 벡터가 실용적 한계로 언급됨 | 대규모·고동시성에서 급격히 성능 저하 | 1억 벡터급에서도 튜닝 없이 recall 유지 | 대규모에 강함(샤딩·분산 설계) |
| 동시 요청 처리 | 개별 쿼리는 상대적으로 느리지만 동시 요청이 많을 때 오히려 안정적(RPS↑, 지연 낮음) | 동시 사용자 늘면 성능 급락 | 매니지드라 스케일 자동 대응 | 설계상 동시성에 강함 |
| 하이브리드(키워드+벡터) 검색 | 기본 제공 안 함 — Postgres 전문검색(`tsvector`)과 직접 결합해야 함 | 별도 결합 필요 | 하이브리드 기능 있으나 조합 방식 제한적 | **BM25 + 벡터 검색을 기본 내장** |
| 운영 부담 | 기존 DB 운영에 흡수됨(백업·모니터링 이미 하던 것 그대로) | 별도 서비스로 백업·헬스체크·버전 관리 추가 | 없음(벤더가 담당) | 별도 서비스 운영 필요 |

---

## 4. 왜 우리 프로젝트엔 pgvector가 맞았는가

### 4.1 검색 후 반드시 관계형 JOIN이 필요한 구조다
벡터 검색 결과만으로는 "이 청크가 어느 팀의 어떤 문서에서 왔는지"를 알 수 없어서 관계형 JOIN이 반드시 따라온다. ChromaDB나 Pinecone처럼 별도 스토어를 쓰면 이 JOIN을 애플리케이션 코드에서 두 번(벡터 검색 → ID 목록 획득 → RDBMS 재질의)에 걸쳐 해야 한다. pgvector는 이걸 SQL 하나로 끝낸다 — 실제 검색이 `vec_idx JOIN chunk JOIN doc_block JOIN doc`을 한 번에 처리한다(`backend/db/document_pipeline.py:340-353`).

> ⚠ **2026-08-05 정정 2건.** ① `CHUNK → KNOW_ITEM_SRC → KNOW_ITEM.semantic_type` JOIN은
> 존재하지 않는다 — `know_item`은 0행이고 `KNOW_ITEM_SRC`로 거르는 코드가 없다. 실제
> 필터는 `d.team_id`이고 경계는 프로젝트가 아니라 **팀**이다. ② 예시로 든
> `backend/services/createDB/vec_idx_setup.py`는 **1536차원 데모 스크립트라 지금 돌리면
> 실패한다**(`vec_idx.embedding`은 `VECTOR(768)`). 현행 검색 경로로 예시를 바꿨다.

### 4.2 참조 무결성이 실제로 문제가 됐었다
ChromaDB로 처음 구현했을 때는 `chunk_id`가 실제로 존재하는지 DB가 검증해주지 않았다(설계 문서에도 "Chroma는 참조 무결성 검사를 하지 않는다"고 명시돼 있었음). pgvector로 옮기면서 **같은 트랜잭션 안에서** 청크와 벡터를 함께 정리할 수 있게 됐다 — 별도 스토어를 쓰면 한쪽만 지워지는 상태가 구조적으로 가능하다.

> ⚠ **2026-08-05 정정 — 실FK를 걸지 않았다.** 이 절은
> `vec_idx.chunk_id UNIQUE REFERENCES chunk(chunk_id) ON DELETE CASCADE`로 FK를 걸었다고
> 적고 있었으나, `DB/schema.sql`에 `REFERENCES`·`FOREIGN KEY`가 **0건**이다. `vec_idx`
> 테이블 주석도 "FK 제약은 사용하지 않으며 chunk_id 존재 여부는 적재 코드에서 검증한다"고
> 적는다. 삭제 정리는 CASCADE가 아니라 **애플리케이션의 명시적 DELETE 3개**가 한다 —
> `vec_idx` → `chunk` → `doc_block` 순으로 지운다(`backend/db/repositories.py:912-930`).
> 참조하는 쪽부터 지워야 중간에 실패해도 고아가 남지 않는다.
>
> pgvector를 고른 이유 자체는 유효하다(같은 트랜잭션·단일 인프라·JOIN). 다만 **"DB가
> 대신 정리해 준다"고 믿으면 안 된다** — 새 삭제 경로를 만들 때 위 세 DELETE를 직접
> 넣어야 한다.

### 4.3 인프라를 하나로 유지할 수 있다
학기 프로젝트 규모의 소규모 팀에서 Docker Compose 서비스를 하나 줄이는 건 실질적인 이득이다. ChromaDB를 쓰던 시절엔 `chroma` 서비스·전용 포트(8001)·전용 볼륨(`chroma_data`)을 팀원 전원이 추가로 관리해야 했다(`docs/0_개발환경/DB_시작_가이드.md` 초기 버전 참고). pgvector는 이미 떠 있는 `db` 컨테이너에 `CREATE EXTENSION IF NOT EXISTS vector;` 한 줄만 추가하면 끝나서, 팀원이 새로 익혀야 할 운영 지식이 늘지 않는다.

### 4.4 우리 데이터 규모는 pgvector의 실용 범위 안에 있다
조사 결과 pgvector가 튜닝 없이 무난하게 버티는 규모는 수천만 벡터 수준으로 언급된다. 이 프로젝트가 다룰 문서·청크 수(프로젝트별 기획서·회의록 문서 묶음)는 이 범위에 크게 못 미친다. 대규모 벡터 검색 전용 엔진(Pinecone 등)이 강점을 갖는 "1억 벡터급, 튜닝 없는 자동 스케일"은 지금 이 프로젝트에는 해당하지 않는 요구사항이다.

### 4.5 비용·트랜잭션 일관성
Pinecone류 클라우드 매니지드는 무료 등급이 제한적이고 스토리지·쿼리 사용량에 따라 과금된다 — 학기 프로젝트 예산으로는 부담이다. 또한 pgvector는 같은 트랜잭션 안에서 문서 삭제(`doc.deleted`/`access_revoked`)와 관련 벡터 삭제(`ON DELETE CASCADE`)를 함께 처리할 수 있어서, "문서는 지웠는데 벡터는 검색에 계속 잡히는" 류의 정합성 문제가 구조적으로 생기지 않는다. 별도 스토어를 쓰면 이 정합성을 애플리케이션이 직접 챙겨야 한다(듀얼 라이트 문제).

---

## 5. 우리가 감수하는 트레이드오프

- **하이브리드 검색이 기본 제공되지 않는다.** Weaviate/Qdrant는 BM25(키워드)+벡터 검색을 내장 기능으로 제공하지만, pgvector는 Postgres의 전문검색(`tsvector`)과 직접 조합해야 한다. 지금 설계(`VEC_IDX`는 순수 임베딩 검색, 업무 의미 필터링은 JOIN)에서는 당장 필요하지 않지만, 키워드 검색을 강화하려면 추가 설계가 필요하다.
- **초대규모 스케일에서는 전용 벡터 DB에 밀린다.** HNSW 인덱스는 메모리 사용량이 크고, 데이터가 계속 늘면 파라미터(`m`, `ef_construction`) 튜닝 부담이 커진다. 클라우드 매니지드는 이런 튜닝 없이도 스케일이 되지만, 그만큼 비용과 벤더 종속이 따른다.
- **동시성 이점은 있지만 개별 쿼리 지연은 더 클 수 있다.** 조사 결과 pgvector는 동시 요청이 많을 때 오히려 안정적이라는 결과가 있지만, 단건 쿼리 latency 자체는 전용 엔진보다 느릴 수 있다.

## 6. 재검토 조건

아래 상황이 오면 pgvector를 유지할지 다시 판단해야 한다.

- 문서·청크 수가 수천만 건 이상으로 늘어나 HNSW 인덱스 튜닝/메모리로 감당이 안 될 때 → `pgvectorscale`(Timescale의 pgvector 확장, 대규모 확장을 목표로 함) 또는 전용 Vector DB로 이관 검토
- 키워드+벡터 하이브리드 검색이 핵심 요구사항이 될 때 → Postgres `tsvector` 결합을 직접 구현하거나 Weaviate/Qdrant급 전환 검토
- 멀티테넌시·대규모 동시 사용자 트래픽이 실제로 발생할 때 → 클라우드 매니지드로 전환해 운영 부담을 벤더에 이전하는 것을 고려

---

## 7. 결론

이 프로젝트는 관계형 데이터(문서·지식·업무·인력)가 중심이고 벡터 검색은 그 위에 얹히는 보조 기능이며, 팀 규모와 데이터 규모가 작고, 인프라 운영 부담을 최소화해야 하는 학기 프로젝트다. 이 세 가지 조건 모두 "이미 쓰는 PostgreSQL에 확장만 추가하면 되고, JOIN·FK·트랜잭션을 그대로 쓸 수 있는" pgvector 쪽으로 answer가 기운다. ChromaDB·Pinecone·Weaviate 같은 대안들이 나쁜 선택은 아니지만, 각각 "별도 인프라 운영", "비용", "하이브리드 검색이 핵심일 때"처럼 우리 프로젝트에는 해당하지 않는 상황에서 강점을 갖는 도구들이다.

> 관계형 데이터(PostgreSQL)가 중심인 시스템이기 때문에, 문서·업무·인력 데이터와 벡터 데이터를 하나의 DB에서 SQL JOIN과 트랜잭션으로 함께 처리할 수 있는 pgvector를 선택했습니다. 또한 별도의 Vector DB를 운영할 필요가 없어 인프라를 단순하게 유지하면서도 프로젝트 규모에 충분한 성능을 제공합니다.

---

Sources:
- [Pinecone vs pgvector vs Chroma vs Weaviate (2026): Best Vector DB by Use Case](https://www.groovyweb.co/blog/vector-database-comparison-2026)
- [Top 5 Vector Databases 2026: Pinecone vs Weaviate vs Qdrant vs Chroma vs pgvector](https://guptadeepak.com/tools/top-5-vector-databases-2026/)
- [Pinecone vs ChromaDB vs pgvector: Cost & Speed (2026)](https://topictrick.com/blog/pinecone-vs-chromadb-vs-pgvector)
- [The Good and Bad of ChromaDB for RAG](https://www.altexsoft.com/blog/chroma-pros-and-cons/)
- [pgvector performance: Benchmark results and 5 ways to boost performance](https://www.instaclustr.com/education/vector-database/pgvector-performance-benchmark-results-and-5-ways-to-boost-performance/)
- [PGVector: HNSW vs IVFFlat — A Comprehensive Study](https://medium.com/@bavalpreetsinghh/pgvector-hnsw-vs-ivfflat-a-comprehensive-study-21ce0aaab931)
- [pgvector vs Dedicated Vector Databases: When PostgreSQL Is Enough](https://zenvanriel.com/ai-engineer-blog/pgvector-vs-dedicated-vector-db/)
- [Postgres Vector Search Compared 2026: pgvector vs pgvectorscale vs ParadeDB vs Lantern](https://www.web3aiblog.com/blog/postgres-vector-search-compared-pgvector-pgvectorscale-paradedb-lantern-2026)
- [pgvector Hybrid Search: Benefits, Use Cases, and Quick Tutorial](https://www.instaclustr.com/education/vector-database/pgvector-hybrid-search-benefits-use-cases-and-quick-tutorial/)
