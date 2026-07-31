# DoclingDocument 정규화 전략

## 목적과 범위

이 문서는 Google Drive에서 수집한 문서를 Docling + EasyOCR로 파싱한 뒤,
`DoclingDocument` JSON을 청킹 가능한 공통 요소 목록(`NormalizedElement[]`)으로
변환하는 규칙을 정의한다.

정규화는 OCR 오타를 임의로 교정하거나 문서를 요약하는 과정이 아니다. 파싱 결과의
읽기 순서, 유형, 참조 관계, 원본 위치를 보존하면서 파싱기별 표현 차이를 일관되게
정리하는 과정이다.

```text
원본 문서
→ Docling + EasyOCR 파싱
→ DoclingDocument JSON 원본 보존
→ 정규화
→ NormalizedElement[]
→ 청킹
→ 임베딩 및 검색 인덱스
```

## 입력과 출력

### 입력

- `DoclingDocument` JSON
- 파싱 실행 메타데이터
  - Docling 및 문서 스키마 버전
  - OCR 엔진, 언어, mode, threshold
  - 표·그림·차트 보강 옵션
  - 원본 Google Drive 파일 ID, revision 또는 modified time

### 출력

```json
{
  "element_id": "drive_file_id:source_hash:parser_run_id:sequence",
  "sequence": 42,
  "type": "heading | paragraph | list | key_value | table | chart_table | picture | picture_ocr | picture_description | caption | footnote",
  "text": "검색 및 표시용 정제 텍스트",
  "heading_path": ["상위 제목", "현재 제목"],
  "heading_confidence": "high | low | none",
  "page_numbers": [1],
  "source_refs": ["#/texts/91"],
  "bboxes": [],
  "relations": {
    "parent_id": null,
    "prev_id": null,
    "next_id": null
  },
  "metadata": {},
  "quality_flags": []
}
```

`#/texts/91` 같은 `source_ref`는 특정 파싱 실행 안에서만 유효한 내부 주소다.
OCR 엔진·옵션·Docling 버전이 바뀌면 같은 원문도 배열 위치가 달라질 수 있으므로,
정규화 결과의 안정 ID로 사용하지 않는다.

## 공통 처리 순서

1. 원본 JSON과 파싱 실행 메타데이터를 보존한다.
2. `self_ref`를 키로 하는 참조 맵을 만든다.
3. `body.children`을 순회해 문서 읽기 순서 기반의 요소 스트림을 만든다.
4. 머리글·바닥글·주변 요소를 제외한다.
5. 텍스트를 최소한으로 정리한다.
6. 제목, 목록, 키-값, 표, 차트, 그림을 유형별 Element로 변환한다.
7. 제목 계층 품질에 따라 두 가지 분기 중 하나로 `heading_path`를 생성한다.
8. 모든 Element에 페이지, 좌표, 원본 참조, 관계와 품질 플래그를 연결한다.

## 1. 참조 해석과 읽기 순서

### 규칙

`texts`, `tables`, `pictures`, `groups` 배열은 유형별 객체 저장소로 사용한다.
실제 읽기 순서는 `body.children`의 `$ref` 순서를 기준으로 복원한다.

```text
body.children
├─ #/texts/0
├─ #/groups/0
├─ #/pictures/0
└─ #/tables/0
```

### 근거

배열 인덱스는 OCR 결과가 달라지면 바뀌며, 목록·그림 OCR 텍스트는 각각 `group`,
`picture`의 자식으로 읽어야 한다. 따라서 `texts` 배열만 순회하면 문서 순서와
명시적 관계를 잃을 수 있다.

## 2. 머리글·바닥글·주변 요소 제외

### 규칙

다음 조건의 요소는 기본 청킹 대상에서 제외한다.

```text
content_layer == "furniture"
label == "page_header"
label == "page_footer"
```

### 근거

페이지 번호, 반복 로고, 반복 회사명은 문서 전반에서 중복된다. 이를 임베딩하면
유사한 불필요 벡터가 다수 생성되어 검색 결과를 오염시킨다. 필요하다면 삭제 대신
문서 수준 메타데이터로만 보관한다.

## 3. 최소 텍스트 정리

### 규칙

- 앞뒤 공백, 연속 공백, 불필요한 개행을 정리한다.
- `<end_of_utterance>` 계열처럼 그림 설명 모델이 남긴 제어 토큰을 제거한다.
- 빈 문자열은 제외한다.
- `orig`가 있으면 원문 문자열로 보존한다.

### 근거

정규화의 목표는 포맷 오류 제거이지 의미 수정이 아니다. OCR 오타 자동 교정,
문장 재작성, 요약은 원본 근거를 약화시킬 수 있으므로 별도 품질 향상 단계로 둔다.

## 4. 제목 계층 처리

제목 계층은 파싱 품질에 따라 다음 두 경우로 처리한다.

### A. 제목 계층이 신뢰 가능한 경우

#### 판정 조건

다음 조건을 다수 만족하는 경우다.

- `section_header.level`이 두 단계 이상으로 자연스럽게 분포한다.
- 상위 → 하위 → 동급 전환이 읽기 순서상 일관된다.
- 제목 번호 체계와 level이 크게 충돌하지 않는다.
- 각 제목 뒤에 실제 본문·표·목록이 이어진다.

#### 규칙

`level` 기반 heading stack을 유지한다. 현재 제목보다 같거나 낮은 level이 나오면
stack에서 해당 깊이와 하위 항목을 제거하고 새 제목을 넣는다. 이후 요소에는 현재
stack을 `heading_path`로 복사한다.

```text
I. 개요                  level 1
  1. 배경                level 2
    1.1 시장 현황         level 3
  2. 목적                level 2
```

```json
{
  "type": "paragraph",
  "heading_path": ["I. 개요", "1. 배경", "1.1 시장 현황"],
  "heading_confidence": "high"
}
```

### B. 제목 계층이 불완전하거나 신뢰하기 어려운 경우

#### 판정 조건

- 모든 제목이 같은 level로 나오는 경우
- level이 누락된 경우
- 번호·제목이 별도 요소로 분리된 경우
- 제목과 표·도표 레이블을 구분하기 어려운 경우

#### 규칙

계층을 임의로 만들지 않는다. 가장 가까운 신뢰 가능한 제목만 `heading_path`에
넣고, 깊이가 확정되지 않으면 `heading_confidence`를 `low` 또는 `none`으로 둔다.

```json
{
  "type": "heading",
  "text": "Oil & Gas",
  "heading_path": ["Oil & Gas"],
  "heading_confidence": "low"
}
```

#### 분리 제목 결합

다음 조건을 모두 만족할 때만 인접 제목을 하나로 결합한다.

- 두 요소가 모두 `section_header`
- `body.children`에서 인접
- 같은 페이지
- 첫 요소가 `1.`, `I.`, `가.`처럼 번호만 포함
- 두 번째 요소가 짧은 제목 텍스트
- 좌표가 같은 행이거나 가까운 세로 위치

```text
"1." + "배경" → "1. 배경"
```

결합한 Element는 양쪽 `source_ref`를 모두 보존하고
`merged_layout_fragments` 플래그를 남긴다.

## 5. 목록 처리

### 규칙

`groups[label="list"]`와 그 자식 `list_item`을 하나의 `list` Element로 만든다.

```json
{
  "type": "list",
  "items": ["항목 1", "항목 2"],
  "source_refs": ["#/groups/0", "#/texts/92", "#/texts/93"]
}
```

### 근거

목록 항목은 단독으로 짧고, 동일한 기준 아래 나열된다는 관계가 핵심이다. 항목을
일반 문단으로 독립 저장하면 상위 기준과 항목 간 관계가 사라진다.

## 6. 키-값 영역 처리

### 규칙

`groups[label="key_value_area"]`는 `key_value` Element로 변환한다. 가능하면
레이블과 값의 쌍을 보존하고, 불가능하면 원문 순서를 유지한 구조화 텍스트를 만든다.

### 근거

회사 주소, 연락처, 담당자, 제품 사양 등은 키와 값의 관계가 핵심이다. 이를 일반
문단으로 합치면 "무엇의 전화번호인가"와 같은 질문에 취약해진다.

## 7. 표 처리

### 규칙

`tables[].data.table_cells`를 사용해 `table` Element를 만든다. 행·열 위치,
병합 셀(`row_span`, `col_span`), 헤더 여부, 표 캡션·각주·출처를 보존한다.

### 근거

표는 문자열 집합이 아니라 행·열 관계 데이터다. 일반 문단처럼 이어 붙이면 특정
행의 제품명과 수치, 일정과 담당자 같은 관계를 잃는다.

## 8. 차트 처리

### 규칙

`pictures[].meta.tabular_chart.chart_data.table_cells`가 존재하면 일반 그림과
별도로 `chart_table` Element를 만든다.

### 근거

차트에서 추출한 값은 구조적으로 표와 유사하지만, 원본은 이미지다. 일반 표와
구분하면 이후 출처 표시와 품질 검증을 더 정확히 할 수 있다.

## 9. 그림, 그림 OCR, 그림 보강 정보 처리

### 규칙

그림은 하나의 `picture` Element로 보존하고, 관련 정보를 분리한다.

```text
picture
├─ picture_ocr: picture.children의 OCR 텍스트
├─ picture_description: meta.description.text
├─ picture_type: meta.classification.predictions
└─ chart_table: meta.tabular_chart가 있을 때
```

- `picture_ocr`는 일반 본문과 분리하고 `ocr_derived`, `picture_content` 플래그를 남긴다.
- `picture_description`은 제어 토큰 제거 후 보조 문맥으로 사용한다.
- `classification`은 검색 본문보다 메타데이터·필터·라우팅 용도로 사용한다.
- `meta`를 우선 사용하고, 없을 때만 `annotations`를 호환성 fallback으로 사용한다.

### 근거

그림 내부 OCR은 일반 PDF 텍스트보다 오인식 가능성이 높고, 축·범례·레이블처럼
문단과 다른 성격의 텍스트일 수 있다. 반면 다이어그램·제품 사양·차트는 핵심 정보를
그림 안에만 포함할 수 있으므로 버리지 않는다.

## 10. 원본 근거와 관계 보존

### 규칙

모든 Element에 다음을 보존한다.

- `source_refs`
- `page_numbers`
- `prov.bbox` 기반 좌표
- `parent_id`, `prev_id`, `next_id`
- 원본 Drive 파일 ID, binary hash, parser run metadata

### 근거

이 정보가 있어야 검색 결과의 원본 페이지 연결, OCR 오류 검토, 청크 오류 분석,
문서 수정 후 증분 재처리가 가능하다.

## 11. 품질 플래그

자동 삭제보다 플래그를 우선한다.

```text
ocr_derived
picture_content
merged_layout_fragments
possible_duplicate
low_text_density
table_text
```

`possible_duplicate`는 같은 페이지, 많이 겹치는 bbox, 동일하거나 거의 동일한
정규화 텍스트가 함께 나타날 때 부여한다. 표·캡션·본문의 의도적 반복도 가능하므로
이 단계에서 자동 삭제하지 않는다.

## 구현 전제

- `do_ocr=True`, `do_table_structure=True`는 파싱 설정에 명시한다.
- 그림 분류·설명·차트 정보는 선택적 필드로 처리한다.
- OCR confidence가 JSON에 없으면 confidence 기반 필터를 적용하지 않는다.
- 실제 JSON이 팀 문서의 필드 설명과 다를 수 있으므로, 구현은 항상 실제 JSON을
  기준으로 하고 필요한 경우 fallback을 둔다.
