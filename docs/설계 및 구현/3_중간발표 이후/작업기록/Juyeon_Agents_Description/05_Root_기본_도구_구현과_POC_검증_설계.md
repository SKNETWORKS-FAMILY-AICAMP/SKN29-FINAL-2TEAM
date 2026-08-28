# Root 기본 도구 구현과 POC 검증 설계

- 작성일: 2026-08-27
- 선행 문서: `04_도구_정리와_업무_추출_에이전트_작업계획.md`
- 목적: 최종 카테고리별 Tool의 구현체를 확정하고, 오픈소스를 실제 서비스 코드에 연결하기 전에 실행 가능성과 결과 품질을 POC로 검증한다.

## 0. 핵심 원칙

1. GitHub 설명만 보고 라이브러리를 채택하지 않는다.
2. 후보 라이브러리를 현재 Docker 환경에 설치하고 실제 한국어 파일로 결과를 확인한다.
3. POC를 통과하지 못한 라이브러리는 서비스 코드에 연결하지 않는다.
4. 기존 Tool은 현재 구현을 재사용하고 회귀 테스트만 추가한다.
5. 신규 Tool은 범용 Shell·Python·SQL 실행을 열지 않고 허용된 operation만 제공한다.
6. 파일은 서버 경로가 아니라 `file_id`로 받고, 결과는 기존 파일 저장소와 PostgreSQL 메타데이터에 등록한다.
7. `task_extraction`은 이번 구현에서 현재 Tool로 유지한다.
8. 입력·생성·설명·편집을 포함한 이미지 관련 기능은 설계·POC·구현 대상에서 제외한다.

---

## 1. 현재 실행 환경과 실측 결과

### 1.1 배포 환경

- 백엔드 이미지: `python:3.13-slim`
- Python 실측 버전: `3.13.15`
- 백엔드 의존성: `requirements/base.txt`
- 무거운 문서 파서: 별도 `runpod_worker`에 Docling `2.117.0` 설치
- 파일 저장: 기존 문서 저장소
- 파일 메타데이터: PostgreSQL 문서 Repository

### 1.2 현재 백엔드 컨테이너 가용성

| 패키지·실행 파일 | 현재 상태 | 판단 |
| --- | --- | --- |
| pypdf | 설치됨 | 바로 재사용 가능 |
| python-docx | 설치됨 | 바로 재사용 가능 |
| openpyxl | 설치됨 | 바로 재사용 가능 |
| jsonschema | 설치됨 | 바로 재사용 가능 |
| markdown-it-py | 설치됨 | Markdown→HTML에 바로 재사용 가능 |
| python-dateutil | 설치됨 | 날짜 기간 계산에 바로 재사용 가능 |
| DuckDB | `1.5.5` 설치됨 | POC와 실제 이미지 빌드 통과 |
| Frictionless | `5.19.0` 설치됨 | POC와 실제 이미지 빌드 통과 |
| RapidFuzz | 미설치 | 현재 필수 아님 |
| SymPy | `1.14.0` 설치됨 | 안전한 AST 계산기에 연결 |
| Pint | `0.25.3` 설치됨 | offset 온도 포함 단위 변환 통과 |
| dateparser | `1.4.2` 설치됨 | 한국어 날짜 보정기와 함께 사용 |
| python-holidays | `0.103` 설치됨 | 한국 공휴일·회사 휴일 계산 통과 |
| pdfplumber | `0.11.10` 설치됨 | 실제 한국어 PDF 본문·표 추출 통과 |
| MarkItDown | 채택하지 않음 | 결과는 맞지만 POC 환경이 369MB로 커져 기존 parser 직렬화로 대체 |
| Pandoc | `3.1.11.1` 설치됨 | Markdown을 중간 DOCX로 안전하게 변환 |
| LibreOffice | `25.2.3.2` GUI 없는 구성 설치됨 | DOCX·XLSX·중간 DOCX의 PDF 변환 통과 |
| ExifTool | `13.25` 설치됨 | PDF·DOCX·XLSX 정리 결과의 잔여 속성 검증 |
| libmagic | `5.46`, python-magic `0.4.27` 설치됨 | PDF·DOCX·XLSX 실제 MIME 판별 통과 |

### 1.3 2026-08-27에 실제 실행한 사전 POC

실행 중인 `web` 컨테이너에서 임시 메모리 파일로 확인했다.

| 검증 | 결과 |
| --- | --- |
| 한글 DOCX 생성 후 python-docx로 다시 읽기 | PASS |
| XLSX 생성 후 openpyxl로 시트·셀 다시 읽기 | PASS |
| pypdf로 PDF 페이지 병합 후 페이지 수 확인 | PASS, 2페이지 |
| jsonschema로 숫자 최솟값 위반 탐지 | PASS |
| Python zoneinfo로 Asia/Seoul 시간대 계산 | PASS |
| markdown-it-py로 한국어 Markdown 제목·목록을 HTML로 변환 | PASS |
| python-dateutil로 1월 31일에서 한 달 뒤 월말 계산 | PASS, 2월 28일 |

이 결과는 라이브러리 import만 확인한 것이 아니라 생성 결과를 다시 읽어 값이 보존되는지 확인한 것이다. 다만 실제 업무 파일의 복잡한 서식까지 검증한 것은 아니므로 §11의 정식 POC가 추가로 필요하다.

### 1.4 P1 정식 POC 결과

| 검증 | 결과 |
| --- | --- |
| 고정 버전 7개 설치와 `pip check` | PASS, 충돌 0건 |
| 실제 한국어 6페이지 PDF | PASS, 본문 3,577자·표 9개 추출 |
| CSV·JSON·Parquet 동일 집계 | PASS, 결과 일치 |
| DuckDB 100,000행 집계 | PASS, 0.065초 |
| 같은 100,000행 집계 4개 동시 실행 | PASS, 0.157초·결과 일치 |
| Frictionless·DuckDB 오류 검사 | PASS, 누락·중복·타입·범위 오류 탐지 |
| SymPy 허용 수식과 코드 실행 차단 | PASS |
| Pint 거리·offset 온도 변환 | PASS |
| 한국어 명시 날짜·다음 주 요일·영업일·시간대 | PASS |
| MarkItDown 한국어 DOCX·XLSX 변환 | 출력 PASS, 설치 크기 기준 FAIL로 미채택 |
| 실제 서비스 Docker 이미지 새 빌드 | PASS |

채택 패키지는 외부 네트워크 없이 실행한다. 설치 메타데이터 기준 Frictionless·holidays는 MIT, SymPy·Pint·dateparser는 BSD 계열이며, pdfplumber와 DuckDB는 배포 전 공식 라이선스 파일을 P3에서 다시 확인한다.

### 1.5 P2 정식 POC 결과

| 검증 | 결과 |
| --- | --- |
| libmagic PDF·DOCX·XLSX signature 판별 | PASS, 선언 MIME 위장도 실제 형식으로 구분 |
| 한국어 DOCX → PDF | PASS, 제목·본문·표와 페이지 재검증 |
| 한국어 XLSX → PDF | PASS, 셀 값과 페이지 재검증 |
| 한국어 Markdown → DOCX → PDF | PASS, 제목·목록·표 보존 |
| ExifTool PDF·DOCX·XLSX 속성 검사 | PASS, 원본 속성 발견·정리본 잔여 0건 |
| LibreOffice 4개 동시 변환 | PASS, 충돌 없이 결과 일치 |
| 외부 이미지·OOXML 외부 리소스·패키지 밖 경로 | PASS, 실행 전에 거절 |
| OOXML 파일 수·압축 해제 크기·압축률 제한 | PASS |
| 실행 파일 누락·비정상 종료·60초 timeout | 안정적인 오류 코드로 처리 |
| 실제 서비스 Docker 이미지 새 빌드·의존성 검사 | PASS |

Pandoc의 `--sandbox`는 Debian 패키지의 DOCX template도 읽지 못하게 해 사용할 수 없었다. 대신 Markdown은 stdin으로만 전달하고 이미지와 raw HTML을 실행 전에 제외하며, Shell 없이 고정 인자만 호출한다. LibreOffice는 요청별 임시 HOME·profile·출력 경로를 분리한다.

---

## 2. 구현 구조

### 2.1 신규 코드 위치

```text
services/
└─ builtin_tools/
   ├─ common/
   │  ├─ files.py          file_id 권한 확인·임시 파일·결과 저장
   │  ├─ limits.py         크기·페이지·행·시간 제한
   │  └─ errors.py         사용자에게 보여줄 오류 코드
   ├─ documents/
   │  ├─ reader.py
   │  ├─ converter.py
   │  ├─ pdf_editor.py
   │  ├─ inspector.py
   │  ├─ sanitizer.py
   │  └─ archive.py
   ├─ data/
   │  ├─ transformer.py
   │  ├─ quality.py
   │  └─ comparer.py
   └─ calculation/
      └─ calculator.py
```

`services/harness/registry.py`에는 JSON Schema와 얇은 handler만 둔다. 실제 파일 처리와 검증 규칙은 위 서비스 모듈에 둬 API·테스트에서도 같은 코드를 사용한다.

### 2.2 공통 실행 흐름

```text
Root Tool 호출
  → 입력 JSON Schema 검증
  → account/team/file_id 권한 확인
  → 격리 임시 디렉터리에 입력 복사
  → 파일 실제 형식·크기 확인
  → 선택된 구현체 실행
  → 결과 구조·파일 재검증
  → 파일 저장소 저장
  → PostgreSQL 메타데이터 등록
  → 임시 디렉터리 삭제
  → 요약과 output_file_id 반환
```

---

## 3. 검색 카테고리

검색 Tool은 모두 현재 구현을 재사용한다. 새 오픈소스를 추가하지 않는다.

| Tool | 구현 | 추가할 테스트 |
| --- | --- | --- |
| `document_search` | `VectorSearchRepository`, RunPod query embedding | 팀·개인·프로젝트 범위, 미색인 문서, top_k, 출처 |
| `document_list` | 문서 Repository, `TeamFolderRepository`, Drive client | 수집·미수집·빈 저장소·연결 오류 구분 |
| `document_sync` | `sync_drive_changes()` | 변경 없음·추가·수정·삭제·연결 만료·부분 실패 |
| `web_search` | 기존 Tavily REST client | 키 없음·401·429·timeout·URL 포함·최대 5건 |

`document_sync`와 `web_search`는 현재 구현된 연결 기능이므로 유지하지만, 신규 로컬 오픈소스 도입 대상은 아니다.

---

## 4. 문서 카테고리

### 4.1 `document_read` — 문서 내용 추출

#### 구현 선택

| 형식 | 1차 구현 | 보조 구현 | 이유 |
| --- | --- | --- | --- |
| PDF | pdfplumber | 현재 설치된 pypdf | 페이지별 본문·표·좌표 추출은 pdfplumber, 단순 본문 fallback은 pypdf |
| DOCX | python-docx | 없음 | 이미 설치되어 있고 문단·표를 직접 순회 가능 |
| XLSX | openpyxl `read_only=True`, `data_only=False` | 없음 | 시트·셀 값·수식·병합 셀을 구조적으로 읽을 수 있음 |

Docling은 현재 RunPod 문서 수집 파이프라인에 유지한다. Root의 단일 파일 읽기를 위해 백엔드에 Docling과 Torch 전체를 중복 설치하지 않는다. POC에서 pdfplumber의 PDF 표 품질이 기준을 충족하지 못할 때만 기존 RunPod `process_document` 결과 재사용을 검토한다.

#### 반환 구조

```json
{
  "file_id": "file_123",
  "format": "pdf",
  "sections": [],
  "tables": [],
  "warnings": [],
  "truncated": false
}
```

#### POC 통과 기준

- 한국어 PDF·DOCX 본문 필수 문장 재현율 98% 이상
- DOCX 표와 XLSX 셀 값은 gold fixture 기준 100% 일치
- PDF 표는 셀 재현율 95% 이상 또는 `table_unreliable` 경고 반환
- 페이지·문단·시트·셀 위치가 결과에 포함됨
- 글자 레이어가 없는 PDF는 내용을 만들어내지 않고 `TEXT_NOT_EXTRACTABLE` 반환
- 20MB 또는 200페이지 제한에서 30초 이내 종료

### 4.2 `document_convert` — 파일 변환

#### 변환 경로

| 입력 | 출력 | 구현 후보 | 실행 위치 |
| --- | --- | --- | --- |
| Markdown | DOCX | Pandoc에 stdin으로 입력 | 백엔드 컨테이너 |
| Markdown | HTML | 현재 설치된 markdown-it-py | 백엔드 |
| Markdown | PDF | Pandoc DOCX 생성 후 LibreOffice 변환 | 백엔드 컨테이너 |
| DOCX | PDF | LibreOffice headless | 백엔드 컨테이너 |
| XLSX | PDF | LibreOffice headless | 백엔드 컨테이너 |
| PDF·DOCX·XLSX | Markdown | pdfplumber·python-docx·openpyxl 결과의 결정적 직렬화 | 백엔드 |

지원 조합은 코드 상수로 관리하고 임의 `from`, `to`, CLI 옵션을 허용하지 않는다. POC를 통과한 Pandoc과 LibreOffice는 Docker 이미지에 고정 버전으로 설치했고, Shell 없이 허용된 인자만 전달한다.

#### POC 통과 기준

- 동일 Dockerfile을 세 번 새로 빌드해 설치 성공
- 한글 제목·본문·표의 필수 값 100% 보존
- 생성 파일을 pypdf, python-docx, openpyxl로 다시 열 수 있음
- 원본 파일은 변경되지 않음
- 지원하지 않는 조합은 `UNSUPPORTED_CONVERSION` 반환
- 외부 URL이 포함된 입력도 네트워크를 호출하지 않음
- 20MB 파일 기준 60초 timeout 안에 종료

### 4.3 `document_create` — Word 만들기

- **구현:** 기존 python-docx와 `services/document_export/docx.py`
- **변경:** 구현 교체 없음. 최종 표시 이름과 category/provider/capability만 변경
- **회귀 테스트:** 한글 제목, 제목 단계, 글머리표, 번호 목록, 굵게, 제어문자, 빈 본문, 긴 본문, 파일 저장 실패

### 4.4 `table_export` — Excel 만들기

- **구현:** 기존 openpyxl과 `services/document_export/xlsx.py`
- **변경:** 구현 교체 없음. 최종 표시 이름과 분류만 변경
- **회귀 테스트:** 한글 시트명, 5,000행 제한, 열 수 불일치, 수식 주입 방지, 숫자·문자 타입, 긴 열 너비

### 4.5 `pdf_edit` — PDF 편집

- **구현:** 현재 설치된 pypdf
- **operation:** `merge`, `split`, `extract`, `reorder`, `rotate`, `crop`, `watermark`
- **원칙:** 원본을 수정하지 않고 새 PDF 생성

#### POC 통과 기준

- 병합 후 입력 순서와 총 페이지 수 100% 일치
- split·extract·reorder 결과의 페이지 내용 hash가 기대 순서와 일치
- 90·180·270도 회전 결과의 rotation 값 확인
- 잘못된 페이지 범위는 실행 전 거절
- 암호 PDF는 비밀번호 우회 없이 `PASSWORD_REQUIRED` 반환
- 손상 PDF는 원본을 바꾸지 않고 `INVALID_PDF` 반환

### 4.6 `file_inspect` — 파일 정보

#### 구현 선택

- MIME 확인: `python-magic` + 시스템 `libmagic`
- SHA-256: Python `hashlib`
- PDF: pypdf의 페이지 수와 metadata
- DOCX: python-docx의 `core_properties`, 문단·표 수
- XLSX: openpyxl의 workbook properties, 시트·사용 영역

확장자만 보는 Python `mimetypes`는 실제 파일 형식을 검증하지 못하므로 단독으로 사용하지 않는다.

#### POC 통과 기준

- 확장자와 실제 MIME이 다른 fixture를 탐지
- SHA-256이 같은 파일에는 항상 같은 값 반환
- PDF 페이지 수, DOCX 문단·표 수, XLSX 시트 수가 gold와 일치
- 다른 팀의 file_id는 파일을 열기 전에 거절

### 4.7 `file_sanitize` — 메타데이터 제거

#### 구현 선택

- PDF: pypdf로 새 문서를 다시 쓰고 document information 제거
- DOCX: python-docx core properties를 비우고 새 파일 저장
- XLSX: openpyxl workbook properties를 비우고 새 파일 저장
- 검증기: ExifTool로 정리 전후 metadata 차이를 검사

Python 구현이 속성을 제거하고 ExifTool이 정책 대상 속성의 잔존 여부를 다시 확인한다. 속성이 남으면 정리된 파일을 성공 결과로 반환하지 않는다.

#### POC 통과 기준

- author, creator, last_modified_by, title, subject, keywords 등 정책 대상 필드가 결과에서 없음
- 본문·표·수식·페이지 수는 원본과 일치
- 원본 hash는 변하지 않음
- 새 파일 hash는 원본과 다름
- 제거되지 않은 필드는 `remaining_metadata`로 반환

### 4.8 `archive_manage` — 압축·해제

- **1차 구현:** Python 표준 라이브러리 `zipfile`
- **지원 형식:** ZIP만 지원. 다른 압축 형식은 초기 범위에서 제외
- **추가 라이브러리:** 초기 구현에는 libarchive를 넣지 않음

#### 필수 방어와 POC

- `../`, 절대 경로, Windows drive path가 있는 entry 거절
- symlink entry 거절
- 압축 파일 수, 개별 크기, 총 해제 크기 제한
- 압축률 상한으로 압축 폭탄 거절
- 중복 파일명 충돌 정책 검증
- 한글 파일명 round-trip 검증
- 일부 손상 ZIP에서 생성된 파일을 저장하지 않음

---

## 5. 업무 카테고리

업무 Tool은 전부 현재 구현을 유지한다.

| Tool | 구현 | 필수 회귀 테스트 |
| --- | --- | --- |
| `project_list` | Project·ExistTask Repository | 프로젝트 없음, progress null·0·100 구분 |
| `task_list` | ProjectTask Repository | 프로젝트 미선택, 빈 목록, 상태·날짜·공수 null |
| `task_register` | ProjectTask Repository | 승인, 중복 제목, 누락 값 drop, 부분 성공 |
| `task_update` | ProjectTask Repository | 승인, 잘못된 task_id, 상태 enum, 마감 수정 |
| `task_extraction` | 기존 `extract_tasks_stream()` | 기준 문서 없음, 미색인 승격, 진행 이벤트, 근거, 0건, 모델 fallback |
| `jira_get_issues` | 기존 Jira REST client | 연결 없음·만료, 프로젝트 key, 빈 목록, 상태 집계 |
| `jira_create_issues` | 기존 Jira REST client | 승인, 전체 성공·부분 성공·전체 실패, 미배정, 요청자 배정 |

### 업무 추출 처리

이번 작업에서는 `task_extraction`의 handler, tool_ref, 실행 흐름을 바꾸지 않는다. 표시 이름과 카테고리 메타데이터만 정리한다. 전용 에이전트 전환은 별도 작업으로 진행한다.

---

## 6. 팀 카테고리

| Tool | 구현 | 필수 회귀 테스트 |
| --- | --- | --- |
| `people_list` | Team Repository, HR skills service | 계정 없는 팀원, 기술 없음, 권한 경계 |
| `workload_report` | HR·Task Repository, workload calculator | 기간 1·12주, 부재 반영, null 공수, 완료 업무 제외 |
| `absence_list` | HR absence service | 승인 상태만 포함, 경계 날짜, 부재 없음 |

팀원 추천·가용성 브리핑·업무 매칭은 위 Tool을 조합하는 에이전트 역할이므로 신규 Tool로 만들지 않는다.

---

## 7. 데이터 카테고리

### 7.1 `table_transform` — 표 가공·집계

#### 구현 선택

- CSV·JSON·Parquet 엔진: DuckDB Python package
- XLSX 읽기: openpyxl `read_only=True`로 임시 CSV 또는 Arrow 형태로 변환한 뒤 DuckDB에 등록
- 출력: JSON preview 또는 새 CSV·JSON·XLSX·Parquet 파일
- 쿼리: 모델이 SQL을 보내지 않고 서버 Query DSL을 받음

```json
{
  "operation": "aggregate",
  "group_by": ["department"],
  "metrics": [{"column": "hours", "function": "avg", "as": "average_hours"}],
  "limit": 100
}
```

#### POC 통과 기준

- CSV·JSON·Parquet 동일 데이터의 집계 결과가 동일
- XLSX를 거친 결과도 숫자·날짜·빈 값이 gold와 일치
- filter, sort, aggregate, join, statistics, convert 각 operation 정답 일치
- SQL·경로·함수 문자열을 입력해도 Query DSL 검증에서 거절
- 반환 행 제한과 전체 스캔 크기 제한 동작
- 100,000행 fixture의 기본 집계가 10초 이내

### 7.2 `data_quality_check` — 데이터 품질 검사

#### 구현 선택

- 테이블 스키마·형식 검사: Frictionless
- JSON Schema: 현재 설치된 jsonschema
- 빈 값·정확한 중복·범위 검사: DuckDB
- XLSX 읽기: openpyxl
- Great Expectations: 초기 구현에서 제외. 현재 기능에 비해 의존성과 설정 구조가 큼
- RapidFuzz: 유사 중복은 사용자가 임계값을 이해하기 어려우므로 초기 구현에서 제외

#### POC 통과 기준

- 의도적으로 넣은 빈 값·중복·타입·범위·스키마 오류를 100% 탐지
- 정상 fixture에 false positive 0건
- 오류마다 파일명, 시트, 행, 열, 오류 이유, 실제 값 포함
- 스키마가 없으면 자동 수정하지 않고 추론 결과만 반환
- 검사 도중 원본 데이터를 변경하지 않음

### 7.3 `file_compare` — 파일 비교

#### 구현 선택

| 형식 | parser | 비교 엔진 |
| --- | --- | --- |
| DOCX | python-docx | Python `difflib.SequenceMatcher` |
| PDF | pdfplumber, pypdf fallback | 페이지별 `difflib.SequenceMatcher` |
| XLSX | openpyxl `data_only=False` | 시트·셀 key 비교 |

Google diff-match-patch는 저장소가 보관 상태이고 현재 요구에는 Python 표준 `difflib`로 충분하므로 초기 의존성에 넣지 않는다.

#### POC 통과 기준

- DOCX 문단·표 셀의 추가·삭제·수정을 모두 탐지
- PDF 본문 차이를 페이지 번호와 함께 탐지
- XLSX 시트·셀 값·수식의 추가·삭제·수정을 셀 주소와 함께 탐지
- 동일한 파일은 변경 0건
- PDF 서식·DOCX 글꼴처럼 지원하지 않는 비교 범위를 결과에 명시
- 추출 가능한 글자가 없는 PDF는 `TEXT_NOT_EXTRACTABLE` 반환

---

## 8. 계산 카테고리

### 8.1 `get_current_datetime` — 날짜·시간 확인

- **구현:** 기존 Python `datetime`, `zoneinfo`
- **변경:** 구현 변경 없이 표시 이름과 category만 변경
- **회귀 테스트:** Asia/Seoul, 자정·월말·연말, 요일, timezone 포함

### 8.2 `calculate` — 수식·날짜 계산

#### 구현 선택

| operation | 구현 |
| --- | --- |
| `math` | SymPy parser + 허용 함수 whitelist |
| `unit` | Pint |
| `date` | dateparser + 명시적 `RELATIVE_BASE` |
| `duration` | Python datetime/dateutil |
| `business_days` | python-holidays + 회사 휴일 입력 |
| `timezone` | Python zoneinfo |

환율은 실시간 외부 데이터가 필요하므로 단위 변환에서 제외한다.

#### POC 통과 기준

- 사칙연산·괄호·백분율·허용 함수 정답 일치
- Python 코드, attribute 접근, import, 무한 계산식을 거절
- 온도처럼 offset이 있는 단위 변환 정답 일치
- `다음 주 금요일` 계산에 account timezone과 기준 시각 사용
- 월말·윤년·DST 시간대 경계 테스트 통과
- 한국 공휴일과 별도 회사 휴일을 영업일 계산에 반영

---

## 9. Tool 설명과 메타데이터

### 9.1 설명 작성 원칙

Tool의 `description`은 사용자에게 보여주는 소개문이 아니라 모델이 호출 대상을 고르는 라우팅 규칙이다. 다음 원칙을 모든 Tool에 적용한다.

1. 첫 문장에 이 Tool을 써야 하는 사용자 목적을 적는다.
2. 두 번째 문장에 입력 대상과 반환 결과를 적는다.
3. 혼동하기 쉬운 Tool이 있으면 “이 경우에는 다른 Tool을 사용한다”는 경계를 적는다.
4. 실제 구현이 지원하지 않는 형식이나 행동은 설명에 넣지 않는다.
5. 입력 필드의 형식·enum·최솟값 같은 규칙은 `input_schema`에 두고 description을 길게 만들지 않는다.
6. 승인, 원본 보존, 연결 필요처럼 호출 판단에 영향을 주는 제약만 description에 남긴다.
7. “필요할 때 사용한다”, “도움을 준다”처럼 모든 Tool에 적용될 수 있는 모호한 표현은 쓰지 않는다.

### 9.2 최종 Tool description

아래 문구를 Registry의 `Tool.description` 초안으로 사용한다. 각 설명은 단독으로 읽어도 호출 범위와 제외 범위를 알 수 있게 작성한다.

#### 검색

| tool_ref | description |
| --- | --- |
| `document_search` | 팀에 등록되어 색인된 문서에서 질문과 관련된 내용과 원문 근거를 찾을 때 사용한다. 관련 문장과 출처 문서를 반환한다. 문서 이름이나 보유 목록만 필요하면 `document_list`, 사용자가 지정한 파일 전체를 읽어야 하면 `document_read`, 외부 최신 정보가 필요하면 `web_search`를 사용한다. |
| `document_list` | 팀에 어떤 문서가 있는지 파일 이름과 수집·색인 상태를 확인할 때 사용한다. 읽은 문서뿐 아니라 연결된 저장소에 있지만 아직 수집하지 않은 문서도 구분해 반환한다. 문서 안의 특정 내용을 찾는 요청에는 `document_search`를 사용한다. |
| `document_sync` | 사용자가 연결 저장소의 문서를 새로 올렸거나 수정했으며 최신 변경을 지금 반영해 달라고 할 때 사용한다. 변경된 문서를 확인해 수집·색인 작업을 시작하고 처리 상태를 반환한다. 일반적인 문서 조회나 검색에는 사용하지 않는다. |
| `web_search` | 인터넷의 최신 정보, 외부 자료 또는 팀 문서에 없는 사실을 출처와 함께 찾을 때 사용한다. 검색 결과의 제목·요약·URL을 반환한다. 사내 문서에 있을 내용은 `document_search`를 우선 사용하고, 이 Tool의 결과로 답할 때는 출처 URL을 함께 제시한다. |

#### 문서

| tool_ref | description |
| --- | --- |
| `document_read` | 사용자가 지정한 PDF·DOCX·XLSX 파일의 실제 내용과 구조를 읽을 때 사용한다. `file_id`의 본문·표와 페이지·문단·시트 위치를 반환한다. 여러 문서에서 관련 내용을 찾는 요청은 `document_search`, 파일 이름 목록만 필요한 요청은 `document_list`를 사용한다. |
| `document_convert` | 기존 파일의 내용을 바꾸지 않고 지원되는 다른 파일 형식으로 변환해 새 파일을 만들 때 사용한다. 입력 `file_id`와 변환 형식을 받아 결과 파일을 반환한다. 내용을 새로 작성하는 요청은 `document_create` 또는 `table_export`, PDF 페이지를 재구성하는 요청은 `pdf_edit`를 사용한다. |
| `document_create` | 완성된 글을 새 Word 문서로 만들어 달라는 요청에 사용한다. 제목과 본문을 DOCX로 저장해 결과 파일을 반환한다. 표 데이터가 주된 결과면 `table_export`를 사용하고, 기존 파일의 형식만 바꾸는 요청에는 `document_convert`를 사용한다. |
| `table_export` | 확정된 열과 행 데이터를 새 Excel 파일로 만들어 달라는 요청에 사용한다. 전달받은 표를 XLSX로 저장해 결과 파일을 반환하며 데이터를 검색하거나 분석하지 않는다. 필터·집계·정렬이 먼저 필요하면 `table_transform`을 실행한 뒤 사용한다. |
| `pdf_edit` | 기존 PDF의 병합·분할·페이지 추출·순서 변경·회전·자르기·워터마크 작업을 요청할 때 사용한다. 원본을 덮어쓰지 않고 편집된 새 PDF를 반환한다. PDF의 내용을 다른 형식으로 바꾸려면 `document_convert`, 본문을 읽으려면 `document_read`를 사용한다. |
| `file_inspect` | 파일의 실제 형식, 크기, 해시, 페이지·시트 수와 작성 정보 같은 속성을 확인할 때 사용한다. 파일 내용 요약이 아니라 구조와 메타데이터를 반환한다. 본문을 읽는 요청에는 `document_read`, 메타데이터를 제거하는 요청에는 `file_sanitize`를 사용한다. |
| `file_sanitize` | PDF·DOCX·XLSX에서 작성자와 생성 도구 등 정책 대상 메타데이터를 제거한 사본을 만들 때 사용한다. 제거 결과와 남은 메타데이터 경고를 반환하며 원본과 본문은 변경하지 않는다. 속성을 확인만 하는 요청에는 `file_inspect`를 사용한다. |
| `archive_manage` | 여러 플랫폼 파일을 하나의 ZIP으로 묶거나 ZIP 파일을 안전하게 풀어 달라는 요청에 사용한다. 생성하거나 해제한 파일 목록을 반환한다. 문서 형식 변환이나 개별 문서 내용 변경에는 사용하지 않는다. |

#### 업무

| tool_ref | description |
| --- | --- |
| `project_list` | 팀의 프로젝트 목록과 각 프로젝트의 상태·진행률을 확인할 때 사용한다. 프로젝트 단위의 요약을 반환한다. 특정 프로젝트의 개별 업무가 필요하면 `task_list`, Jira 이슈가 필요하면 `jira_get_issues`를 사용한다. |
| `task_list` | 현재 프로젝트에 우리 플랫폼으로 등록된 업무와 상태·마감 정보를 조회할 때 사용한다. 플랫폼 업무 목록을 반환하며 Jira 이슈는 포함하지 않는다. Jira 업무는 `jira_get_issues`, 문서에서 아직 등록되지 않은 업무 후보를 찾는 요청은 `task_extraction`을 사용한다. |
| `task_register` | 사용자가 확인한 업무를 현재 프로젝트의 플랫폼 업무로 등록할 때 사용한다. 등록·중복·누락 결과를 건별로 반환하며 실행 전 사용자 승인이 필요하다. 문서에서 후보를 찾는 작업은 `task_extraction`, Jira 등록은 `jira_create_issues`를 사용한다. |
| `task_update` | `task_list`로 확인한 기존 플랫폼 업무의 상태나 마감일을 변경할 때 사용한다. 실제 `task_id`가 있는 업무만 수정하며 실행 전 사용자 승인이 필요하다. 새 업무 생성에는 `task_register`, Jira 이슈 변경에는 사용하지 않는다. |
| `task_extraction` | 현재 프로젝트에서 사람이 미리 선택한 기준 문서와 관련 문서를 바탕으로 업무 후보와 원문 근거를 추출해 달라는 요청에 사용한다. 후보와 근거만 반환하고 자동 등록하지 않으며 몇 분 걸릴 수 있다. 단순 문서 요약이나 이미 확인된 업무의 등록에는 사용하지 않는다. |
| `jira_get_issues` | 현재 프로젝트에 연결된 Jira의 기존 이슈와 진행 상태를 조회할 때 사용한다. Jira 이슈 목록을 반환하며 플랫폼 업무는 포함하지 않는다. 플랫폼 업무는 `task_list`를 사용하고, 프로젝트 키는 사용자가 다른 Jira 프로젝트를 명시한 경우에만 지정한다. |
| `jira_create_issues` | 사용자가 확인한 업무를 연결된 Jira에 새 이슈로 등록할 때 사용한다. 건별 성공·실패 결과를 반환하며 실행 전 사용자 승인이 필요하다. 플랫폼 업무 등록은 `task_register`를 사용하고, 담당자 정보가 확인되지 않으면 임의로 배정하지 않는다. |

#### 팀

| tool_ref | description |
| --- | --- |
| `people_list` | 현재 팀에 누가 있는지와 각 팀원의 직책·기술을 확인할 때 사용한다. 팀원 명부와 역할 정보를 반환한다. 업무량은 `workload_report`, 휴가·교육 일정은 `absence_list`를 사용하며 사람을 자동 배정하지 않는다. |
| `workload_report` | 지정한 기간의 팀원별 예정 업무 시간과 남은 여유를 비교할 때 사용한다. 팀원별 업무량 요약을 반환한다. 직책·기술만 필요하면 `people_list`, 부재 일정 자체를 확인하려면 `absence_list`를 사용한다. |
| `absence_list` | 지정한 기간에 승인된 팀원의 휴가·교육 등 부재 일정을 확인할 때 사용한다. 부재자와 기간을 반환한다. 전체 업무량이나 남은 여유를 비교하는 요청에는 `workload_report`를 사용한다. |

#### 데이터

| tool_ref | description |
| --- | --- |
| `table_transform` | CSV·JSON·XLSX·Parquet 표를 필터·정렬·결합·집계하거나 기본 통계를 계산하고 다른 표 형식으로 저장할 때 사용한다. 요청한 가공 결과와 미리보기 또는 결과 파일을 반환한다. 빈 값·중복·타입 오류를 찾는 요청에는 `data_quality_check`를 사용한다. |
| `data_quality_check` | 표나 JSON의 빈 값·중복·타입·범위·열 구성·스키마 오류를 검사할 때 사용한다. 오류 위치와 이유를 반환하며 원본 데이터를 수정하지 않는다. 값을 집계·정렬·결합하는 요청에는 `table_transform`, 두 파일의 변경점 확인에는 `file_compare`를 사용한다. |
| `file_compare` | 두 PDF·DOCX·XLSX 파일 사이의 본문·표·셀 값과 수식 변경점을 확인할 때 사용한다. 형식별 위치와 함께 추가·삭제·수정 내역을 반환한다. 한 파일의 품질 검사에는 `data_quality_check`, 파일 형식 변환에는 `document_convert`를 사용한다. |

#### 계산

| tool_ref | description |
| --- | --- |
| `get_current_datetime` | 현재 날짜·시간·요일 또는 상대 날짜 계산의 기준 시각이 필요할 때 사용한다. 계정 시간대의 현재 시각을 반환한다. 수식·단위·기간·영업일처럼 실제 계산이 필요한 요청에는 `calculate`를 사용한다. |
| `calculate` | 사칙연산·백분율·허용 수식, 단위 변환, 날짜 차이, 영업일과 시간대 변환을 정확히 계산할 때 사용한다. 계산 결과와 적용한 기준을 반환한다. 현재 시각만 묻는 요청에는 `get_current_datetime`을 사용하며 환율처럼 실시간 외부 값이 필요한 계산은 지원하지 않는다. |

### 9.3 메타데이터 구현

현재 `Tool` dataclass에 화면 분류용 필드를 추가한다.

```python
@dataclass(frozen=True)
class Tool:
    ref: str
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., Any]
    side_effect: bool = False
    category: str = "기타"
    provider: str = "플랫폼"
    capability: str = "조회"
    requires_connection: bool = False
```

- `provider`: 플랫폼, 내 파일, 연결 문서, 웹, Jira
- `capability`: 검색, 목록, 조회, 추출, 만들기, 수정, 등록, 동기화, 가공, 검사, 비교, 계산
- `requires_connection`: 연결되지 않았을 때 Builder에서 안내에 사용
- 실행 권한과 side effect 판단은 기존 로직을 유지한다.

---

## 10. POC 전용 테스트 자료

서비스 fixture와 섞지 않고 다음 경로에 둔다.

```text
tests/fixtures/builtin_tools/
├─ documents/
│  ├─ korean_simple.pdf
│  ├─ korean_table.pdf
│  ├─ korean_document.docx
│  ├─ korean_workbook.xlsx
│  ├─ malformed.pdf
│  └─ password_required.pdf
├─ data/
│  ├─ valid.csv
│  ├─ invalid_missing_duplicate.csv
│  ├─ valid.json
│  ├─ invalid_schema.json
│  └─ sample.parquet
├─ compare/
│  ├─ before.docx
│  ├─ after.docx
│  ├─ before.pdf
│  ├─ after.pdf
│  ├─ before.xlsx
│  └─ after.xlsx
├─ archive/
│  ├─ normal.zip
│  ├─ traversal.zip
│  ├─ symlink.zip
│  └─ bomb.zip
└─ expected/
   ├─ extraction.json
   ├─ validation.json
   ├─ comparison.json
   └─ calculations.json
```

fixture는 실제 고객 문서를 쓰지 않고 테스트용 문장을 직접 만들어 저장한다. 예상 결과는 라이브러리 출력에서 자동 생성하지 않고 사람이 먼저 작성한다. 그래야 잘못된 라이브러리 출력을 정답으로 복사하는 일을 막을 수 있다.

---

## 11. 오픈소스 채택 전 POC 절차

### 11.1 1단계 — 설치 검증

1. 후보 버전을 명시적으로 고정한다.
2. POC 전용 Dockerfile에서 깨끗한 이미지를 세 번 빌드한다.
3. Python 3.13 import와 CLI `--version`을 확인한다.
4. 설치 이미지 증가량과 전이 의존성을 기록한다.
5. 라이선스와 최근 보안 이슈를 확인한다.

### 11.2 2단계 — 기능 검증

1. §10 fixture를 각 후보에 실행한다.
2. 실제 출력과 사람이 작성한 expected JSON을 비교한다.
3. 한글, 표, 수식, 날짜, 빈 값의 보존 여부를 확인한다.
4. 정상·경계·손상 파일을 모두 실행한다.
5. 같은 입력을 세 번 실행해 결과 안정성을 확인한다.

### 11.3 3단계 — 운영 검증

1. timeout과 메모리 상한 안에서 종료하는지 측정한다.
2. 동시에 2·4개 요청을 실행해 프로세스 충돌을 확인한다.
3. 외부 네트워크를 끈 상태에서도 로컬 Tool이 동작하는지 확인한다.
4. 프로세스가 실패해도 임시 파일과 child process가 남지 않는지 확인한다.
5. 악성 파일로 다른 경로·팀 파일을 읽을 수 없는지 확인한다.

### 11.4 판정

| 상태 | 의미 | 다음 행동 |
| --- | --- | --- |
| `CANDIDATE` | 조사만 완료 | POC 실행 |
| `POC_FAILED` | 설치·정확도·보안 기준 미달 | 서비스 코드에 넣지 않고 대안 조사 |
| `POC_PASSED` | 단독 기능 기준 통과 | adapter 구현 가능 |
| `INTEGRATED` | file_id·저장소·Registry 연결 완료 | 통합 테스트 실행 |
| `RELEASE_READY` | 회귀·보안·성능 테스트 통과 | 기본 Tool로 노출 |

`POC_PASSED` 이전에는 `requirements/base.txt`, Dockerfile, Registry에 해당 후보를 넣지 않는다.

---

## 12. 통합 테스트

### 12.1 모든 신규 Tool 공통 경로

- 정상 요청 성공
- 필수 인자 누락
- 알 수 없는 operation
- 지원하지 않는 형식
- 존재하지 않는 file_id
- 다른 팀의 file_id
- 빈 파일
- 제한 초과 파일
- 손상 파일
- timeout
- 라이브러리 예외의 내부 경로·원문 비노출
- 결과 저장 성공 후 PostgreSQL row 확인
- 저장 실패 시 부분 결과 정리
- 원본 hash 불변
- 같은 요청 중복 실행

### 12.2 Root 라우팅

Tool마다 다음 질문 세트를 별도로 만든다.

- 해당 Tool을 사용해야 하는 실제 사용자 질문 20개
- 비슷하지만 사용하면 안 되는 질문 20개
- 다른 Tool을 써야 하는 충돌 질문 10개

예를 들면 `table_transform`은 “부서별 평균 계산”에는 선택되어야 하지만 “빈 값이 있는지 검사”에는 선택되면 안 된다. 후자는 `data_quality_check`가 선택되어야 한다.

### 12.3 부작용과 승인

- 조회·검사·비교·계산: 승인 없음
- 새 파일 생성: 사용자가 결과 파일 생성을 명시한 요청의 승인 정책을 일관되게 적용
- 플랫폼 업무 등록·수정, Jira 등록: 기존 HITL 유지
- 원본 덮어쓰기·삭제: 지원하지 않음

---

## 13. 구현 순서

P0·P1·P2는 검증만 하는 단계가 아니다. 각 항목은 **POC 또는 기존 의존성 확인 → Tool adapter 구현 → 단위·회귀 테스트**까지 완료하는 작업 묶음이다. 후보가 POC에 실패하면 해당 Tool을 구현 완료로 표시하지 않고 대체 구현체를 다시 검증한다.

### P0 — 현재 의존성으로 먼저 구현·회귀 검증 — 완료

현재 의존성만 사용하는 처리 모듈과 자동 테스트가 구현되었다. 신규 Tool은 P3 전까지 Registry와 Builder에 노출하지 않는다.

1. 기존 Tool 이름·카테고리·provider 메타데이터 변경
2. `pdf_edit`
3. `document_read`의 DOCX·XLSX와 pypdf PDF fallback 경로
4. `file_compare`의 DOCX·XLSX 경로
5. `file_inspect`의 hash·DOCX·XLSX·PDF 기본 정보
6. pypdf·python-docx·openpyxl 기반 `file_sanitize`
7. `archive_manage`
8. `document_convert`의 Markdown→HTML 경로
9. 현재 `document_create`, `table_export`, `get_current_datetime` 회귀 테스트

### P1 — Python 패키지 POC 후 구현 — 완료

Python 3.13 실제 서비스 이미지에 버전을 고정하고 처리 모듈과 자동 테스트를 구현했다. P0와 마찬가지로 Registry·파일 저장소 연결은 P3에서 수행한다.

1. pdfplumber → `document_read`, PDF 비교
2. DuckDB → `table_transform`
3. Frictionless → `data_quality_check`
4. SymPy·Pint·dateparser·holidays → `calculate`
5. MarkItDown은 설치 크기 기준으로 제외하고 기존 형식별 parser → Markdown 직렬화로 대체

구현 결과:

- `document_read`와 `file_compare`의 PDF 경로에 pdfplumber를 연결했다.
- `document_convert`에 PDF·DOCX·XLSX → Markdown 경로를 추가했다.
- `table_transform`은 임의 SQL 대신 열 검증·값 parameter binding이 적용된 Query DSL만 받는다.
- `data_quality_check`는 오류 위치를 반환하고 원본을 수정하지 않는다.
- `calculate`는 임의 Python 실행 없이 허용 AST·단위·날짜·영업일·시간대 operation만 실행한다.
- P0·P1 자동 테스트 40개와 의존성 무결성 검사를 실제 서비스 이미지에서 통과했다.
- 이 단계에서 발견한 `reset_demo.sql`의 `eval_judge_result` 누락은 P3 최종 점검에서 수정했다.
- 프런트엔드 TypeScript 검사와 프로덕션 빌드도 통과했다.

### P2 — 시스템 패키지 POC 후 구현 — 완료

1. libmagic → 실제 MIME 판별
2. LibreOffice → DOCX·XLSX의 PDF 변환
3. Pandoc → Markdown PDF 변환
4. ExifTool → P0에서 구현한 `file_sanitize` 결과 검증 및 필요 시 구현 보완

구현 결과:

- `file_inspect`가 libmagic으로 실제 MIME을 판별하고 선언값과의 일치 여부를 반환한다.
- `document_convert`에 Markdown→DOCX·PDF와 DOCX·XLSX→PDF 경로를 추가했다.
- LibreOffice·Pandoc·ExifTool은 Shell 없이 고정된 명령만 실행하며 요청별 임시 디렉터리와 60초 제한을 사용한다.
- Markdown 이미지는 지원 범위 밖으로 거절하고, Office 외부 리소스·패키지 밖 관계·압축 폭탄은 LibreOffice 실행 전에 차단한다.
- `file_sanitize`는 ExifTool로 정책 대상 속성이 실제로 0건인지 재검증한다.
- P0~P2 자동 테스트 49개와 `pip check`를 새 서비스 이미지에서 통과했다.
- 이 단계에서 계속 재현된 `eval_judge_result` 초기화 누락은 P3 최종 점검에서 수정했다.
- 프런트엔드 TypeScript 검사와 프로덕션 빌드가 통과했다.
- 시스템 패키지를 추가했지만 Docker `COPY --chown`으로 중복 소유권 계층을 없애 이미지 크기는 약 1.67GB에서 1.27GB로 줄었다.

P2까지 통과하면 신규 Tool 10개의 기능 구현은 모두 끝난다. 다만 아직 Root 기본 Tool로 배포가 끝난 것은 아니며, 다음 통합 단계를 통과해야 한다.

### P3 — 통합·라우팅·배포 검증 — 통합 완료, localhost 화면 실측 진행

1. 신규 Tool 10개를 Registry에 등록하고 `file_id` 권한 확인·파일 저장소·PostgreSQL 메타데이터 흐름을 연결한다.
2. §9의 최종 description과 input schema를 적용한다.
3. 정상·실패·권한·손상·제한·timeout 통합 테스트를 실행한다.
4. 관련 질문·비관련 질문·충돌 질문으로 Root Tool 선택 평가를 실행한다.
5. side effect와 HITL 정책, 결과 파일 저장, 원본 불변을 확인한다.
6. 전체 회귀 테스트를 통과한 뒤 Builder와 Root에 노출한다.

#### P3 구현 결과

- 신규 Tool 10개를 Registry에 등록하고 전체 내장 Tool을 29개로 맞춰다. 내부 시스템 Tool 2개를 뺀 Builder에는 기본 Tool 27개가 보인다.
- 모든 file_id 입력은 `PipelineDocumentRepository.get_for_processing()`으로 본인 소유·같은 팀 문서·같은 팀에 공유된 개인 파일인지 먼저 확인한 뒤 저장소를 읽는다. 다른 팀, 삭제, 접근 철회 파일은 거절한다. 로컬 사본이 없는 연결 문서는 권한을 확인한 요청자의 연결로 해당 실행에서만 다시 받는다.
- 결과 파일은 `PersonalDocumentRepository.create_generated()` → object storage 저장 → `DocumentRepository.mark_stored()` 순으로 연결한다. 중간에 실패하면 이미 만든 DB 행과 저장 객체를 회수한다.
- 원본을 바꾸는 경로는 없다. 파일을 생성하는 `document_convert`, `pdf_edit`, `file_sanitize`, `archive_manage`, `table_transform`은 기존 HITL 승인 경계를 탄다.
- 신규 읽기 전용 Tool 5개는 앞으로 만들어지는 기본 Root에 자동으로 붙는다. `2026-08-27_builtin_tools_p3.sql`은 이미 있는 기본 Root에도 동일한 5개를 멱등으로 추가한다. 사용자가 만든 에이전트 버전은 변경하지 않는다.
- 개발 DB 스모크 테스트에서 임시 PDF의 PostgreSQL 행·저장소 객체·다운로드를 확인한 뒤 모두 정리했다.
- P0~P3 관련·역검증 테스트, `pip check`, 프런트 빌드를 통과했다. `reset_demo.sql`의 `eval_judge_result` 누락을 수정하고 개발 DB 마이그레이션까지 적용했다.
- 라우팅 데이터셋은 관련 10건·충돌 10건·비관련 10건으로 고정했다. localhost Chrome의 실제 기본 어시스턴트에 대표 질문을 전송하고 `chat_session → agent_run → tool_call` 기록으로 선택 도구를 대조했다. 일반 설명은 무도구, 문서 목록은 `document_list`, 파일 속성은 `file_inspect`, 계산은 `web_search → calculate`로 동작했다.
- 특정 file_id의 본문 읽기·비교 요청에서 모델이 전용 도구 대신 `document_list`를 선행 호출하는 오류를 실측으로 발견했다. 파일 처리 도구가 존재·권한을 직접 검사한다는 공통 라우팅 규칙과 `document_list`/`document_read` 설명을 보완했고, 같은 읽기 질문이 `document_read` 1회로 성공하는 것을 Chrome에서 재검증했다.
- 현재 backend 전체 테스트 1,673개와 프런트 프로덕션 빌드가 통과한다.

#### 기존 기능 테스트와 다른 경계의 역검증 결과

- UI 다운로드와 Tool 실행 권한을 교차해, 같은 팀에 공유된 개인 파일도 Tool에서 읽되 다른 팀은 계속 차단하도록 맞췄다.
- DOCX·XLSX는 압축 파일 크기뿐 아니라 내부 파일 수·압축 해제 크기·압축률·심볼릭 링크를 parser 실행 전에 검사한다.
- Excel의 날짜·시간 같은 비기본 값은 Tool 결과와 실행 로그에 저장할 수 있는 JSON 값으로 정규화한다.
- 모델이 지나치게 긴 제목을 만들더라도 PostgreSQL `doc.file_name VARCHAR(255)`를 넘지 않게 자른다.
- ZIP 안에서 확장자만 PDF·DOCX·XLSX로 위장한 파일은 저장 전에 실제 형식과 대조하며, 지원하지 않는 파일은 실행 가능한 형식으로 신뢰하지 않고 `.bin`으로 저장한다.
- PDF 분할과 ZIP 해제처럼 한 호출이 여러 파일을 만들면 `produced_files`로 전부 채팅 다운로드 목록에 전달한다.
- idempotency 결과는 Python repr이 아니라 JSON으로 저장해 재개 뒤에도 생성 파일 구조를 잃지 않는다.
- 같은 run·tool_call_id가 동시에 재개돼도 DB의 RUNNING claim을 한 요청만 얻는다. 실패 시 claim을 해제하고 프로세스 종료 시 lease 만료 뒤 회수한다. 실제 PostgreSQL 동시 호출에서 `CLAIMED` 1건·`RUNNING` 1건을 확인했다.
- `table_transform`은 미리보기에는 승인하지 않고 `output_format`으로 결과 파일을 만들 때만 승인한다.
- PDF 본문·표 parser와 PDF 비교는 45초 timeout, Linux CPU 30초, 메모리 768MB 제한이 있는 별도 프로세스에서 실행한다.
- 저장 객체 삭제 실패는 `storage_cleanup_outbox`에 남기고, 별도 worker를 늘리지 않은 채 기존 `skill-validation-worker` 한 프로세스가 지수 백오프로 재시도한다.
- 로컬 `OSError`만 처리하던 파일 경계를 S3 `ClientError`·`BotoCoreError`까지 같은 사용자 오류로 처리한다.

#### 별도 환경 확인이 남은 경계

- 30개 고정 데이터셋을 직접 실행하는 스크립트는 localhost 경로가 아니라 질문과 전체 Tool 스키마를 외부 모델 API로 전송하므로 별도 egress 승인 없이는 실행하지 않는다. 대신 실제 localhost 화면 질의와 실행 로그 대조를 수행했다.
- 복수 결과 파일의 백엔드 이벤트·TypeScript 빌드는 검증했지만 Chrome 확장 연결이 중간에 제어권을 넘기지 않아, 한 답변에 표시된 여러 파일을 각각 누르는 브라우저 다운로드 E2E만 수동 확인이 남았다.

---

## 14. 완료 조건

다음이 모두 충족되어야 Root 기본 Tool 구현이 완료된 것으로 본다.

1. 04 문서의 기본 Tool 27개와 코드 Registry가 일치한다.
2. 기존 Tool 17개 회귀 테스트가 모두 통과한다.
3. 신규 Tool 10개의 선택 구현체가 `POC_PASSED`이고 adapter 구현이 끝났다.
4. 신규 Tool 10개가 Registry와 파일 저장소·PostgreSQL 메타데이터 흐름에 연결된다.
5. 지원 형식별 gold fixture와 expected 결과가 존재한다.
6. 정상·실패·권한·손상·제한·timeout 경로가 자동 테스트된다.
7. Root Tool 선택 평가에서 관련 질문과 충돌 질문 기준을 통과한다.
8. 결과 파일이 저장소와 PostgreSQL에 등록되고 원본은 바뀌지 않는다.
9. 새 의존성·CLI의 버전, 라이선스, 이미지 증가량, timeout이 문서화된다.
10. `task_extraction`은 기존 Tool로 정상 동작한다.
