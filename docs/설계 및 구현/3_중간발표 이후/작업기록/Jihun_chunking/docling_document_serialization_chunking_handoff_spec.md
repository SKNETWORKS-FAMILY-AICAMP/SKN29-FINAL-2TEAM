# 최종 DoclingDocument 직렬화·청킹 전략 인계 명세서

> 기준 입력: 중간 파싱 결과나 실행 파라미터가 아니라 `final.docling.json`을 복원한 최종 `DoclingDocument`

## 1. 목적

이 문서는 파싱 담당자가 직렬화·청킹 담당자에게 전달하는 최종 데이터 계약이다.

파싱 과정, OCR 설정, 모델 실행 과정, 중간 JSON은 다루지 않는다. 최종 `DoclingDocument`에 어떤 구조와 정보가 있으며, 팀원이 어떤 serializer와 chunker 선택지를 판단해야 하는지만 정의한다.

### 책임 경계

- 파싱 담당
  - 유효한 `final.docling.json` 생성
  - `DoclingDocument` 복원 가능성 보장
  - 표 구조, 그림 분류·설명, 문서 계층, provenance 제공
- 직렬화·청킹 담당
  - component serializer 구성
  - chunk 경계와 token 예산 결정
  - 표·그림 직렬화 방식 비교
  - 검색용 문자열과 chunk metadata 계약 구현
- 공동
  - 대표 문서 세트 선정
  - 누락, 중복, 과대 chunk, 표·그림 검색성 평가

## 2. 입력 원칙

1. 입력 JSON은 `DoclingDocument.load_from_json()` 또는 동등한 방식으로 복원한다.
2. JSON 문자열 자체를 generic text splitter로 직접 분할하지 않는다.
3. `body`, `groups`, `parent`, `children`의 참조 구조를 유지한다.
4. embedded 이미지의 Base64/data URI를 텍스트 임베딩 입력으로 취급하지 않는다.
5. 필드가 스키마에 존재하는 것과 특정 문서에서 값이 채워진 것은 구분한다.

## 3. 최종 DoclingDocument 구조

```text
DoclingDocument
├─ schema_name
├─ version
├─ name
├─ origin
├─ body
├─ furniture
├─ groups[]
├─ texts[]
├─ tables[]
├─ pictures[]
├─ key_value_items[]
├─ form_items[]
├─ field_regions[]
├─ field_items[]
└─ pages
```

| 최상위 필드 | 형태 | 직렬화·청킹 관점 |
|---|---|---|
| `schema_name`, `version`, `name` | 스칼라 | 스키마 호환성과 문서 식별 |
| `origin` | 객체 또는 `null` | 원본 출처와 문서 식별 metadata |
| `body` | `GroupItem` | 본문 루트와 읽기 순서 |
| `furniture` | `GroupItem` | 페이지 header/footer 등 비본문 구조 |
| `groups[]` | GroupItem 계열 | 목록, 인라인, 기타 구조 컨테이너 |
| `texts[]` | TextItem 계열 | 제목, 절 제목, 본문, 목록, 코드, 수식 등 |
| `tables[]` | `TableItem` | 행·열·셀 구조를 가진 표 |
| `pictures[]` | `PictureItem` | 그림, 내부 텍스트, 분류, 설명, 이미지 |
| `key_value_items[]` | `KeyValueItem` | 키-값 구조가 존재할 경우 사용 |
| `form_items[]` | `FormItem` | 폼 구조가 존재할 경우 사용 |
| `pages` | 페이지 번호 → `PageItem` | 페이지 크기와 embedded 페이지 이미지 |

배열의 물리적 순서만으로 문서 읽기 순서를 단정하지 않는다. `body.children`과 `groups[].children`의 JSON pointer를 따라 구조를 복원해야 한다.

## 4. 공통 item 필드

| 필드 | 의미 | 활용 |
|---|---|---|
| `self_ref` | `#/texts/0`과 같은 JSON pointer | chunk에서 원본 item을 역추적하는 키 |
| `parent` | 부모 item 참조 | 계층 복원 |
| `children[]` | 자식 item 참조 | 읽기 순서, 목록, 중첩 구조 복원 |
| `label` | `text`, `section_header`, `table`, `picture` 등 | serializer route 및 chunk label |
| `content_layer` | `BODY`, `FURNITURE` 등 | 본문과 비본문의 포함 정책 결정 |
| `prov[]` | `page_no`, `bbox`, `charspan` 등 | 페이지 인용, 좌표, 원문 추적 |

`prov`는 검색 본문에 직접 합치는 정보가 아니라 chunk metadata로 보존하는 것이 일반적이다. 최종 선택은 청킹 담당자가 결정한다.

## 5. `texts[]`

`texts[]`에는 단순 본문뿐 아니라 다음 계열이 함께 들어갈 수 있다.

- `TitleItem`
- `SectionHeaderItem`
- `ListItem`
- `CodeItem`
- `FormulaItem`
- 일반 `TextItem`

| 필드 | 의미 | 판단 지점 |
|---|---|---|
| `text` | 정규화된 텍스트 | 기본 직렬화 대상 |
| `orig` | 원문 표현 | 검색 본문 또는 감사·비교용 보존 여부 |
| `label` | item의 의미 유형 | 형식 처리 및 chunk metadata |
| `level` | section header의 제목 깊이 | heading path 구성 |
| `marker` | 목록 기호 | 목록 표현 보존 여부 |
| `enumerated` | 순서 목록 여부 | 순서 의미 보존 |
| `parent`, `children` | 계층 참조 | 구조 기반 chunking |
| `prov[]` | 페이지와 bbox | 원문 역추적 |

현재 최종 문서는 section header level을 최대 6단계까지 표현할 수 있다. 이 값은 `HierarchicalChunker`와 `HybridChunker`가 heading context를 구성할 때 활용할 수 있다.

## 6. `tables[]`

표는 Markdown 문자열이 아니라 구조화된 `TableItem`으로 존재한다.

```text
tables[]
├─ self_ref
├─ parent
├─ children[]
├─ label
├─ prov[]
├─ captions[]
├─ footnotes[]
└─ data
   ├─ num_rows
   ├─ num_cols
   └─ table_cells[]
```

주요 table cell 필드:

```text
text
row_span
col_span
start_row_offset_idx
end_row_offset_idx
start_col_offset_idx
end_col_offset_idx
column_header
row_header
row_section
bbox
```

모든 필드가 모든 표와 셀에서 항상 유효한 값을 갖는다고 가정해서는 안 된다.

### 표 직렬화 선택지

| 방식 | 장점 | 주의점 | 평가 기준 |
|---|---|---|---|
| Triplet | 행과 열의 관계가 문장형으로 반복되어 embedding에 유리할 수 있음 | 텍스트가 길어지고 사람이 읽기 어려울 수 있음 | 셀·행 단위 retrieval recall |
| Markdown | 사람과 생성 모델이 표 구조를 읽기 쉬움 | 넓은 표는 token 비용이 큼 | 답변 정확도와 헤더 보존 |
| Custom | 도메인별 핵심 열, 단위, 헤더를 최적화 가능 | 별도 구현과 회귀 테스트 필요 | 도메인 대표 표의 검색·생성 성능 |

원본 `tables[].data`는 폐기하지 않는다. 직렬화 결과는 원본에서 생성한 파생 데이터로 취급하고 serializer profile과 함께 버전 관리한다.

## 7. `pictures[]`

```text
pictures[]
├─ self_ref
├─ parent
├─ children[]
├─ label
├─ prov[]
├─ captions[]
├─ footnotes[]
├─ references[]
├─ image
└─ meta
   ├─ classification
   │  └─ predictions[]
   │     ├─ class_name
   │     └─ confidence
   └─ description
      ├─ text
      └─ created_by
```

`meta.description`이 모든 그림에 존재한다고 가정하지 않는다. description이 없어도 picture, 내부 텍스트, caption, classification, image, provenance는 존재할 수 있다.

### 그림 직렬화 선택 축

그림 직렬화는 description을 기본값으로 정하지 않는다. 다음 후보를 서로 독립적인 축으로 평가한다.

| 후보 | DoclingDocument 출처 | 가능한 역할 | 팀원이 결정할 항목 |
|---|---|---|---|
| 그림 내부 텍스트 | PictureItem 아래 중첩 OCR/text item | 그림 안의 문자·수치 직접 검색 | `traverse_pictures`, 정제 방식, 노이즈 허용 수준 |
| Caption | `pictures[].captions[]` 참조 | 문서 저자가 부여한 그림 문맥 | 단독 사용, 다른 후보와 결합, 중복 제거 |
| Description | `pictures[].meta.description.text` | 그림에 대한 생성형 자연어 설명 | 포함 여부, 별도 필드 여부, 품질 기준 |
| Classification | `meta.classification.predictions[]` | 그림 유형 필터와 serializer routing | 본문 포함 또는 metadata-only |
| Placeholder/reference | picture serializer와 image reference | 그림 존재 표시와 원본 연결 | placeholder, URI, 멀티모달 후처리 |

평가할 조합 예시:

```text
A. 내부 텍스트만
B. caption만
C. description만
D. 내부 텍스트 + caption
E. 내부 텍스트 + description
F. caption + description
G. 내부 텍스트 + caption + description
H. 각 후보는 별도 index field로 저장
```

판단 항목:

- retrieval recall과 precision
- OCR 노이즈 유입량
- description hallucination 또는 과도한 일반화
- caption과 description의 중복
- token 사용량
- 그림 종류별 성능 차이
- 최종 검색 결과에서 원 `PictureItem.self_ref`로 역추적 가능한지

`traverse_pictures=True`는 그림 아래 중첩 텍스트를 포함하는 방식이다. 이를 켠 결과와 description 기반 결과는 별도 실험군으로 비교해야 한다.

### 이미지 payload 처리

최종 JSON은 `ImageRefMode.EMBEDDED`로 저장되므로 다음 이미지가 Base64/data URI 형태일 수 있다.

```text
pages[page_no].image
pictures[].image
```

이 payload는 다음과 같이 처리한다.

- `chunk.text`에서 제외
- `contextualized_text`에서 제외
- tokenizer 입력에서 제외
- 필요한 경우 원본 이미지 저장소 또는 멀티모달 검색 경로에 별도 전달

## 8. `key_value_items[]`와 `form_items[]`

최종 문서에 값이 있다면 text/table로 임의 평탄화하지 않고 전용 serializer 경로를 검토한다.

- `KeyValueItem` → `key_value_serializer`
- `FormItem` → `form_serializer`

현재 문서 집합에서 빈 배열이더라도 향후 다른 입력 문서에서 출현할 수 있으므로 fallback 정책을 마련한다.

## 9. Docling serializer 구조

Docling serializer는 text/table/picture 세 종류만으로 구성되지 않는다. component serializer의 구성 슬롯은 다음 10개다.

| serializer 슬롯 | 대상 | 역할 |
|---|---|---|
| `text_serializer` | `TextItem` 계열 | 제목, 본문, 목록 item, 코드, 수식 표현 |
| `table_serializer` | `TableItem` | Triplet, Markdown 또는 custom 표 표현 |
| `picture_serializer` | `PictureItem` | caption, meta, placeholder, image reference 처리 |
| `key_value_serializer` | `KeyValueItem` | 키-값 구조 표현 |
| `form_serializer` | `FormItem` | 폼 구조 표현 |
| `list_serializer` | `ListGroup` | 목록 컨테이너와 자식 조합 |
| `inline_serializer` | `InlineGroup` | 인라인 자식과 서식 조합 |
| `meta_serializer` | `item.meta` | description, classification 등 metadata 표현 |
| `annotation_serializer` | legacy annotation | 호환 경로. 신규 설계는 meta 중심 검토 |
| `fallback_serializer` | 기타 `NodeItem` | 미지원 또는 신규 item의 유실 방지 |

이 serializer들을 전체 문서 단위로 조율하는 것이 document serializer이며, document와 serializer 구성을 분리하는 wrapper가 serializer provider다.

### 대표 청킹용 serializer 구성

`ChunkingDocSerializer`는 Markdown 계열 serializer를 기반으로 한다.

```text
ChunkingDocSerializer
├─ text       → MarkdownTextSerializer
├─ table      → TripletTableSerializer
├─ picture    → MarkdownPictureSerializer
├─ key_value  → MarkdownKeyValueSerializer
├─ form       → MarkdownFormSerializer
├─ list       → MarkdownListSerializer
├─ inline     → MarkdownInlineSerializer
├─ meta       → MarkdownMetaSerializer
├─ annotation → MarkdownAnnotationSerializer
└─ fallback   → MarkdownFallbackSerializer
```

표 serializer와 picture/meta 관련 parameter는 팀원이 목적에 맞게 변경할 수 있다.

## 10. Native chunking 선택지

### `HierarchicalChunker`

- `DoclingDocument` 구조를 직접 사용한다.
- 기본적으로 detected document element 단위로 chunk를 만든다.
- list item은 기본 설정에서 병합될 수 있다.
- headings와 captions 등 관련 metadata를 chunk에 연결한다.

적합성 판단:

- 구조 보존이 최우선인가?
- 각 item이 embedding token 한도 안에 대부분 들어오는가?
- token 기반 재분할이나 작은 peer 병합이 필요 없는가?

### `HybridChunker`

`HierarchicalChunker`의 결과 위에 tokenizer 기반 처리를 추가한다.

1. token 한도를 넘는 oversized chunk를 분할한다.
2. headings와 captions가 같은 작은 인접 chunk를 조건에 따라 병합한다.

주요 결정 항목:

- embedding 모델과 동일한 tokenizer
- `max_tokens`
- `merge_peers`
- `merge_list_items`
- `repeat_table_header`
- `omit_header_on_overflow`
- custom `serializer_provider`

일반적인 RAG baseline 후보로 사용할 수 있지만, 최종 채택은 대표 문서 평가 후 결정한다.

### `LineBasedTokenChunker`

- line boundary를 우선 보존한다.
- 한 줄이 한도를 넘지 않는 한 줄 내부 분할을 피한다.
- 표, 코드, 로그, 목록처럼 줄 단위 의미가 강한 콘텐츠에 검토할 수 있다.

## 11. `chunk.text`와 `contextualize()`

```python
chunk.text
chunker.contextualize(chunk)
```

- `chunk.text`: serializer가 만든 원 item/chunk 문자열
- `contextualize(chunk)`: heading, caption 등 metadata context를 결합한 문자열

두 값을 하나로 덮어쓰지 않는다. 검색 실험과 재현을 위해 별도 필드로 저장하는 것이 좋다.

임베딩에 어느 값을 사용할지는 팀원이 다음 실험으로 결정한다.

- `chunk.text`만 사용
- contextualized text만 사용
- 두 필드를 별도 embedding
- item 종류에 따라 선택

## 12. 권장 파생 chunk 계약

다음은 Docling 원본 스키마가 아니라 청킹 시스템이 생성할 수 있는 프로젝트 파생 레코드다.

| 필드 | 형태 | 내용 |
|---|---|---|
| `chunk_id` | string | 문서 ID, profile 버전, 순번 또는 안정적 hash |
| `text` | string | serializer가 만든 원 chunk 문자열 |
| `contextualized_text` | string | context가 보강된 문자열 |
| `doc_item_refs` | string[] | 원본 `self_ref` 목록 |
| `labels` | string[] | 원본 item label 목록 |
| `headings` | string[] | 상위 heading 경로 |
| `captions` | string[] | 연결 caption |
| `page_nos` | int[] | `prov`에서 집계한 페이지 번호 |
| `bboxes` | object[] | 필요한 경우 page number와 함께 보존 |
| `has_table` | boolean | 표 포함 여부 |
| `has_picture` | boolean | 그림 포함 여부 |
| `picture_classes` | object[] | class name과 confidence, 존재할 경우 |
| `serializer_profile` | string | table/picture/meta 직렬화 정책 버전 |
| `chunker_profile` | string | chunker, tokenizer, token 및 merge 정책 버전 |

이 계약의 필수 여부와 실제 필드명은 팀원이 확정한다.

## 13. 팀 의사결정 목록

| ID | 결정 항목 | 결정할 내용 |
|---|---|---|
| D-01 | 주 chunker | Hierarchical, Hybrid, LineBased 중 baseline과 예외 경로 |
| D-02 | tokenizer | 실제 embedding 모델 tokenizer와 token 한도 |
| D-03 | 표 표현 | Triplet, Markdown, custom 및 표 유형별 예외 |
| D-04 | 표 분할 | header 반복과 overflow 처리 |
| D-05 | 그림 내부 텍스트 | `traverse_pictures` 적용 및 OCR noise 정제 |
| D-06 | 그림 description | 포함 여부, 별도 field 여부, 품질 기준 |
| D-07 | 그림 조합 | 내부 text, caption, description의 단독·조합·중복 제거 |
| D-08 | classification | 본문 포함 또는 metadata-only |
| D-09 | meta 허용 목록 | embedding에 포함할 metadata 종류 |
| D-10 | 비본문 | furniture와 page header/footer의 제외 또는 별도 index |
| D-11 | merge 정책 | peer 및 list item 병합 조건 |
| D-12 | 파생 chunk 계약 | 필수 metadata와 profile 버전 관리 |

## 14. 검증 시나리오

| 대상 | 검증 질문 | 합격 기준 예시 |
|---|---|---|
| 계층 | heading level과 heading path가 유지되는가? | chunk heading이 원 문서 구조와 일치 |
| 본문 | 긴 문단이 token limit을 넘지 않는가? | 모든 embedding 입력이 모델 한도 이내 |
| 목록 | 목록이 누락, 중복, 오병합되지 않는가? | 순서와 marker 의미 보존 |
| 표 | 분할 후에도 header와 cell 의미를 이해할 수 있는가? | 각 표 chunk에서 열 의미 확인 가능 |
| 그림 내부 text | OCR 기반 검색이 유효한가? | 검색 이득이 노이즈 증가보다 큼 |
| 그림 description | 설명 기반 검색이 유효한가? | 대표 그림 질의에서 원 picture ref 반환 |
| 그림 조합 | caption/description/OCR 결합이 중복을 만드는가? | token 대비 retrieval 지표 개선 |
| 이미지 payload | Base64가 token 계산에 유입되는가? | chunk 문자열에 Base64 URI가 없음 |
| provenance | 원 페이지와 좌표로 역추적 가능한가? | `self_ref`, page, bbox 복원 가능 |
| 비본문 | header/footer가 검색 노이즈가 되는가? | 정책에 따라 제외 또는 명시적 분리 |
| 안정성 | 같은 입력과 profile에서 결과가 재현되는가? | chunk 수, ID, text가 결정적 |

## 15. 구현 권장 순서

1. `final.docling.json`을 `DoclingDocument`로 복원하고 참조 유효성을 검사한다.
2. 기본 serializer와 native chunker로 baseline을 만든다.
3. 동일 tokenizer와 token 한도에서 table serializer만 변경해 비교한다.
4. 그림 내부 text, caption, description, classification을 각각 단독 실험한다.
5. 유효한 그림 후보 조합과 중복 제거 방식을 비교한다.
6. furniture 제외, peer merge, list merge, table header 반복을 한 축씩 실험한다.
7. 확정한 설정을 `serializer_profile`과 `chunker_profile`로 버전 관리한다.
8. 대표 문서 세트를 고정하고 회귀 테스트를 자동화한다.

## 16. 금지 사항

- 최종 JSON 문자열 자체를 generic text splitter로 직접 분할하지 않는다.
- `pages[].image` 또는 `pictures[].image`의 Base64를 embedding 문자열에 포함하지 않는다.
- 모든 picture에 description이 있다고 가정하지 않는다.
- description을 picture 직렬화의 기본 정답으로 미리 확정하지 않는다.
- classification label만으로 그림의 실제 내용을 대체하지 않는다.
- 배열의 물리적 순서만으로 읽기 순서를 단정하지 않는다.
- 표를 평문으로 손실 변환한 뒤 원본 `tables[].data`를 폐기하지 않는다.
- 서로 다른 tokenizer 조건에서 chunk 크기 실험 결과를 직접 비교하지 않는다.

## 17. 인계 체크리스트

- [ ] `final.docling.json` 샘플과 DoclingDocument schema version을 공유했다.
- [ ] text, table, picture, list, heading 사례가 포함된 대표 문서를 선정했다.
- [ ] description이 있는 그림과 없는 그림을 모두 테스트한다.
- [ ] 그림 내부 텍스트가 있는 경우와 없는 경우를 모두 테스트한다.
- [ ] 큰 표와 multi-row header 표를 테스트한다.
- [ ] Base64가 chunk text에서 제외됨을 자동 검사한다.
- [ ] chunk에서 원 `self_ref`, page number, bbox로 역추적할 수 있다.
- [ ] serializer와 chunker profile을 기록한다.
- [ ] 평가 결과와 최종 결정 사항을 이 문서의 의사결정 표에 반영한다.

## 18. 공식 참고 자료

- [DoclingDocument API](https://docling-project.github.io/docling/reference/docling_document/)
- [Docling Serialization](https://docling-project.github.io/docling/concepts/serialization/)
- [Docling Chunking](https://docling-project.github.io/docling/concepts/chunking/)
- [Hybrid chunking example](https://docling-project.github.io/docling/_generated/examples/hybrid_chunking/)
- [Advanced chunking and serialization](https://docling-project.github.io/docling/_generated/examples/advanced_chunking_and_serialization/)
- [docling-core Markdown serializers](https://github.com/docling-project/docling-core/blob/main/docling_core/transforms/serializer/markdown.py)

