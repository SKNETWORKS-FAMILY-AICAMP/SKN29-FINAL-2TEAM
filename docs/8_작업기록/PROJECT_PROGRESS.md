# Docling 기반 문서 청킹 프로젝트 진행 기록

> 이 문서는 프로젝트의 **살아 있는 작업 일지**다. 파싱 설정, 정규화 규칙, 청킹 규칙, 평가 결과가 바뀔 때마다 아래의 `변경 이력`과 해당 상세 섹션을 함께 갱신한다.
>
> 마지막 갱신: 2026-07-31
> 현재 단계: **정규화 전략 수립 및 1차 구현·실행 완료 / 청킹 전략 설계 시작 전**

## 1. 프로젝트 목표

Google Drive 커넥터에서 팀 문서(PDF, 기획서, 회의록, 보고서 등)를 가져와 다음 파이프라인으로 검색·RAG에 사용할 수 있는 데이터로 만든다.

```text
Google Drive 원본 문서
  → Docling + EasyOCR 파싱
  → Docling JSON
  → 정규화(Normalization)
  → 청킹(Chunking)
  → 임베딩·인덱싱
  → 검색/RAG 및 평가
```

핵심 원칙은 파싱 결과의 페이지 순서, 제목·목록·표·그림 같은 구조, 원문 위치를 최대한 보존한 뒤 청킹하는 것이다. 단순히 모든 텍스트를 일정 글자 수로 자르는 방식은 사용하지 않는다.

## 2. 현재 대상과 전제

| 항목 | 현재 내용 |
| --- | --- |
| 문서 출처 | 향후 Google Drive 커넥터 |
| 현재 검증 문서 | `Documents/hanwha.pdf` |
| 파서 | Docling |
| OCR | EasyOCR (`ko`, `en`) |
| 주 대상 문서 | 기획서, 회의록, 보고서 등 팀 프로젝트 문서 |
| 정규화 입력 | DoclingDocument JSON |
| 정규화 출력 | 검색/청킹 친화적인 `NormalizedElement[]` JSON |

현재 구현은 로컬 파일을 대상으로 검증한다. Google Drive에서 가져온 뒤에는 `drive_file_id`, Drive revision, 수정 시각처럼 **원본 파일을 다시 찾고 갱신을 감지할 수 있는 메타데이터**를 실제 값으로 채워야 한다.

## 3. 현재 폴더와 산출물

```text
chunking_practice/
├─ Documents/
│  └─ hanwha.pdf                         # 정규화 검증에 사용한 원본 PDF
├─ 추출 JSON/
│  ├─ hanwha (1).json                    # 팀 설정 기반 Docling 출력 예시
│  └─ json_계층                          # Docling 객체/참조 구조 설명
├─ normalizer/
│  ├─ normalization_strategy.md          # 정규화 전략 문서
│  ├─ pipeline.py                         # 정규화 전체 흐름
│  ├─ walker.py                           # body 순회·furniture 제거
│  ├─ heading.py                          # 제목 신뢰도·경로 처리
│  ├─ builders.py                         # 표/목록/그림/차트 등의 변환
│  ├─ quality.py                          # 품질 플래그·중복 후보 탐지
│  ├─ ref_utils.py                        # Docling $ref 해석
│  ├─ text_utils.py                       # 최소 텍스트 정리
│  └─ types.py                            # 정규화 출력 타입과 ID 규칙
├─ run_normalize.py                       # 현재 입력 JSON을 정규화하는 실행 진입점
├─ output/
│  ├─ hanwha (1).normalized.json          # 1차 정규화 결과
│  └─ docling_study/                      # Docling PDF 구조 탐색 산출물
├─ inspect_docling_pdf.py                 # Docling 결과를 탐색하기 위한 보조 스크립트
└─ PROJECT_PROGRESS.md                    # 현재 문서
```

`.venv/`, `__pycache__/`는 실행 환경/캐시이므로 작업 산출물로 관리하지 않는다.

## 4. 지금까지 파악한 Docling JSON의 핵심

### 4.1 저장 위치와 읽는 순서는 다르다

Docling JSON의 `texts`, `tables`, `pictures`, `groups`는 요소를 보관하는 목록이다. 실제 문서의 읽기 순서는 `body.children` 안의 `$ref`가 결정한다. 따라서 정규화와 청킹은 목록의 인덱스 순서가 아니라 **`body.children`을 따라가며 `$ref`를 해석**해야 한다.

### 4.2 `$ref`와 `self_ref`의 의미

- `#/texts/62` 같은 `$ref`는 **해당 파싱 실행 결과 내부에서만** 요소를 가리키는 주소다.
- 동일 PDF를 다른 OCR 엔진이나 다른 설정으로 다시 파싱하면 인덱스와 내용이 달라질 수 있다.
- 따라서 `$ref` 자체를 DB의 영구 ID로 쓰지 않는다.
- 영구 식별자는 `drive_file_id + source_hash + parser_run_id + sequence` 조합으로 만든다.

### 4.3 구조 요소별 처리 방향

| Docling 요소 | 정규화 처리 |
| --- | --- |
| `section_header` | 제목 요소 생성, 제목 경로 후보로 사용 |
| `text` | 문단으로 정리. 제목으로 오인된 경우 별도 규칙 검토 |
| `list`, `list_item` | 목록 경계를 보존하고 목록 단위로 직렬화 |
| `key_value_area` | key-value 구조를 보존 |
| `table` | 표를 문장으로 평탄화하지 않고 셀/헤더 구조를 보존 |
| `picture` | 분류·설명·OCR 자식·차트 표를 분리하여 기록 |
| `page_header`, `page_footer`, furniture | 검색 본문에서 제외 |
| `caption`, `footnote` | 출처를 유지한 보조 요소로 저장 |

### 4.4 제목 계층은 항상 신뢰할 수 없다

현재 한화 예시에서는 `section_header` 57개가 모두 `level=1`로 나왔다. 즉, 제목이 있다고 해서 제목 깊이까지 정확하다고 볼 수 없다. 이에 따라 정규화기는 다음 두 분기를 둔다.

1. **계층 신뢰 가능**: 여러 제목 깊이가 일관되게 존재하면 Docling의 level을 제목 경로에 활용한다.
2. **계층 신뢰 불가**: 전부 같은 level이거나 누락·역전이 많으면 순서와 페이지를 보존하되 `heading_confidence=low`로 표시한다. 이 경우 제목 경로를 사실처럼 만들어 내지 않는다.

향후 번호 체계, 글꼴 정보, 북마크, 텍스트 패턴을 이용한 계층 복원은 별도 평가를 거쳐 추가한다.

## 5. 파싱 설정에서 합의한 방향

팀에서 공유한 현재 EasyOCR 방향은 다음과 같다.

- 언어: 한국어·영어 (`ko`, `en`)
- OCR 범위: `layout_regions` 우선. 구버전 Docling에서는 `bitmap_area_threshold=0.05` 대체
- 전체 페이지 OCR 강제: 하지 않음 (`force_full_page_ocr=False`)
- 그림 분류·설명, 차트 추출: 사용
- 제목 계층 추론: 사용
- 이미지 배율: 현재 `images_scale=1.0`

이 설정은 출발점이다. 실제 문서군에서 OCR 누락, 표/차트 인식, 비용·처리시간을 측정한 뒤 변경될 수 있다. 설정을 바꾸면 같은 문서라도 JSON의 참조와 요소 수가 달라질 수 있으므로, 이후에는 반드시 파싱 실행 메타데이터와 설정 버전을 함께 기록한다.

## 6. 정규화 전략 v1

상세 전략은 [normalization_strategy.md](normalization_strategy.md)에 기록되어 있다. 현재 구현한 핵심 결정은 다음과 같다.

1. `body.children`을 문서의 기준 읽기 순서로 사용한다.
2. 헤더·푸터·furniture는 검색 대상 본문에서 제외한다.
3. 공백/줄바꿈/제어 토큰만 최소한 정리하고, OCR 오탈어를 정답처럼 자동 수정하지 않는다.
4. 표, 차트 표, 목록, key-value, 그림 OCR, 그림 설명을 서로 다른 타입으로 보존한다.
5. 각 요소에 원문 페이지·bbox·원본 참조를 넣어 검색 결과에서 원문 근거를 추적할 수 있게 한다.
6. OCR 유래, 그림 유래, 표 유래, 중복 가능성, 짧은 텍스트 등의 품질 신호를 `quality_flags`에 기록한다.
7. 제목 계층이 불확실하면 낮은 신뢰도로 명시하고, 허위 계층을 만들지 않는다.

## 7. 정규화 구현 현황

### 7.1 구현된 처리 흐름

`run_normalize.py`가 `추출 JSON/hanwha (1).json`을 읽고 `normalizer.pipeline.normalize_document()`를 호출해 `output/hanwha (1).normalized.json`을 생성한다.

```text
원본 Docling JSON
  → ref map 생성
  → body 순회 및 furniture 필터
  → 제목 신뢰도 판단·heading path 부여
  → 요소 타입별 builder 변환
  → 페이지/bbox/ref/관계 메타데이터 부여
  → 품질 플래그·중복 후보 표시
  → NormalizedElement 배열 출력
```

### 7.2 모듈별 책임

| 모듈 | 현재 책임 |
| --- | --- |
| `pipeline.py` | 전체 순서 조립, heading 상태 관리, 최종 요소 생성 |
| `walker.py` | `body`를 순회하고 header/footer/furniture 필터링 |
| `heading.py` | 제목 level 신뢰도 판단, 제목 번호 조각 결합 보조 |
| `builders.py` | 목록·표·차트·그림·OCR·설명 직렬화 |
| `ref_utils.py` | `$ref`를 현재 JSON의 실제 객체로 연결 |
| `text_utils.py` | 안전한 최소 텍스트 정리 |
| `quality.py` | OCR/표/그림 플래그, 중복 가능성 표시 |
| `types.py` | 출력 구조 및 안정 ID 생성 규칙 |

### 7.3 현재 출력 구조의 핵심 필드

각 `NormalizedElement`는 최소한 다음 정보를 가진다.

```json
{
  "element_id": "drive_file_id:source_hash:parser_run_id:sequence",
  "sequence": 0,
  "type": "paragraph | heading | list | table | picture | ...",
  "text": "검색과 청킹에 사용할 정리된 표현",
  "heading_path": ["상위 제목", "현재 제목"],
  "heading_confidence": "high | low",
  "page_numbers": [2],
  "source_refs": ["#/texts/133"],
  "bboxes": [],
  "relations": {},
  "metadata": {},
  "quality_flags": []
}
```

## 8. 한화 샘플 실행 결과

입력 `추출 JSON/hanwha (1).json`은 6페이지이며, 원본 Docling JSON에는 text 371개, table 5개, picture 54개, group 28개가 있다.

1차 정규화 결과 `output/hanwha (1).normalized.json`에는 총 **232개 요소**가 생성되었다.

| 타입 | 개수 |
| --- | ---: |
| heading | 57 |
| paragraph | 39 |
| list | 25 |
| key_value | 3 |
| table | 5 |
| chart_table | 2 |
| picture | 54 |
| picture_ocr | 28 |
| picture_description | 7 |
| caption | 7 |
| footnote | 5 |

품질 플래그 중 `ocr_derived`와 `picture_content`는 각 28개, `table_text`는 7개, `possible_duplicate`는 8개가 표시되었다. 현재 모든 제목은 원본 level이 전부 1인 문제 때문에 `heading_confidence=low` 상태다.

이 결과는 “최종 검색 품질이 검증됐다”는 뜻이 아니라, **청킹 전에 구조·근거·품질 신호를 잃지 않는 정규화 파이프라인의 첫 실행이 가능해졌다**는 뜻이다.

## 9. 지금까지 확인한 중요한 사례

- 2페이지의 `Introduction to Hanuha Pouer`, `History`, `Total Solution` 등은 문서의 body 순서를 통해 이어진다.
- `#/pictures/5`, `#/pictures/20`은 차트 분류·설명·차트 표를 함께 가지므로, 그림 하나를 일반 문단으로만 저장하면 수치 검색 근거가 사라진다.
- `#/pictures/11`, `#/pictures/12`처럼 프로세스/흐름도 OCR 텍스트가 있는 그림도 있다. 다만 그림 분류 신뢰도가 낮거나 설명과 맞지 않는 사례가 있어, VLM 분류·설명은 보조 정보로 취급한다.
- `Hanuha Pouer` 같은 header/footer 성 텍스트가 furniture에도 존재한다. 단순 텍스트 중복 제거가 아니라 `label`과 `content_layer`를 함께 봐야 한다.

## 10. 아직 해결하지 않은 과제와 주의점

| 구분 | 현재 한계 |
| --- | --- |
| 제목 계층 | 샘플의 모든 heading level이 1 |
| 파싱 메타데이터 | 출력에 OCR mode/threshold, 이미지 설정, 설정 버전이 비어 있음 |
| OCR 품질 | 오탈어·누락·레이아웃 분할 오류 가능 |
| 그림 설명 | 그림 분류/설명은 오분류 가능 |
| 중복 탐지 | 현재 유사도 비교가 문서가 커질수록 비용 증가 가능 |
| 테스트 | 고정 JSON fixture와 자동 회귀 테스트가 아직 없음 |
| Drive 연동 | 현재 로컬 실행만 검증 |

## 11. 변경 이력

| 날짜 | 상태 | 변경/확인 내용 | 영향 |
| --- | --- | --- | --- |
| 2026-07-31 | 완료 | Docling JSON의 `body.children`/`$ref`/`self_ref` 구조와 참조 범위를 분석 | 정규화 기준 읽기 순서와 ID 정책 확정 |
| 2026-07-31 | 완료 | RapidOCR 결과와 EasyOCR 결과의 차이, 동일 ref의 비영속성 확인 | ref를 영구 ID로 사용하지 않기로 결정 |
| 2026-07-31 | 완료 | 팀 EasyOCR 설정과 그림·차트·제목 계층 옵션 검토 | 파싱 메타데이터 보존 필요성 확인 |
| 2026-07-31 | 완료 | 정규화 전략 v1 문서화 | 구조 보존, furniture 제거, 품질 플래그 원칙 수립 |
| 2026-07-31 | 완료 | `normalizer` 구현과 한화 JSON 1차 실행 | 232개 정규화 요소 생성, 제목 계층 low 상태 확인 |

## 12. 앞으로 이 문서를 갱신하는 규칙

아래 변화가 생기면 같은 작업에서 이 문서도 함께 업데이트한다.

| 변화 | 기록할 내용 |
| --- | --- |
| 파싱 옵션 변경 | 변경 이유, 이전/이후 옵션, 영향 문서, 재파싱 필요 여부 |
| JSON 스키마 변화 | 추가/삭제/변경 필드와 normalizer 대응 |
| 정규화 규칙 변경 | 대상 타입, 전후 예시, 품질·검색 영향 |
| 청킹 규칙 추가 | 경계 규칙, 병합/분할 기준, 토큰 목표, 예외 처리 |
| 임베딩/인덱스 변경 | 모델, 차원, 메타데이터, 재색인 범위 |
| 평가 실행 | 문서 수, 질의 수, 주요 실패 사례, 다음 개선 항목 |

작업이 실제로 완료되거나 설정·설계가 변경되면 `현재 단계`와 `변경 이력`, 관련 상세 섹션을 함께 갱신한다.
