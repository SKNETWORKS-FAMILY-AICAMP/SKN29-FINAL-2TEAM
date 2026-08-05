
문서 구조 기반 HierarchicalChunker
+
embedding tokenizer 기반 길이 조정

#### 처리 순서
1. HierarchicalChunker로 문서 구조 기반 청크 생성
2. 여러 DocItem이 길면 DocItem 경계로 분할
3. 하나의 DocItem이 길면 Semchunk로 텍스트 분할
4. merge_peers=True라면 인접 청크 재병합

DoclingDocument
→ HierarchicalChunker가 관련 DocItem을 구조적으로 묶음
→ 토큰 제한을 초과하면 DocItem 경계로 분할
→ DocItem 하나가 여전히 길면 텍스트 내부를 분할
→ 같은 headings를 가진 인접 DocChunk를 다시 병합

### 2. DocItem 경계로 분할
#### 2.1 DocItem : Docling이 문서에서 인식한 개별 구성 요소 하나
```PDF
└─ DoclingDocument
   ├─ 제목 DocItem
   ├─ 본문 DocItem
   ├─ 목록 항목 DocItem
   ├─ 표 DocItem
   ├─ 이미지 DocItem
   └─ 캡션 DocItem
```

#### 2.2 DocChunk : 청킹 단계에서 생성한 결과 단위
기본 HierarchicalChunker 결과에서는 제목이 항상 doc_items에 포함되는 것은 아니다.
대부분 제목은 문맥 메타데이터인 `meta.headings`로 전달되고, 실제 콘텐츠 요소만 `meta.doc_items`에 들어간다.
```
DocChunk
├─ text
├─ meta.headings
│  └─ "Specifications"
└─ meta.doc_items
   ├─ 본문 DocItem
   ├─ 목록 DocItem
   └─ 이미지 DocItem
```
(단, `always_emit_headings=True` 같은 설정이나 본문 없는 빈 섹션의 경우에는 제목 자체가 별도 청크로 출력될 수 있다.)

하나의 청크에는 여러 DocItem이 포함될 수 있다.
반대로 하나의 DocItem이 너무 길면 여러 DocChunk로 나뉠 수 있다.
```
긴 본문 DocItem 하나
├─ DocChunk 1
├─ DocChunk 2
└─ DocChunk 3
```

- **meta.doc_items**
: 해당 청크가 어떤 원본 DocItem에서 만들어졌는지 나타낸다. (HybridChunker 결과 안에 메타데이터 중 하나)
```json
{
  "chunk_id": "stable-chunk-000047",
  "source_refs": [
    "#/pictures/43",
    "#/texts/313",
    "#/texts/314"
  ]
}
```
```
#/pictures/43 → 페이지 5의 이미지
#/texts/313   → 페이지 6의 목록 항목
#/texts/314   → 페이지 6의 목록 항목
```

#### 2.3 DocItem이 가질 수 있는 주요 정보
모든 DocItem이 아래 필드를 전부 갖는 것은 아니다. self_ref / label / prov / parent 정도는 공통이고, text·children·captions·이미지·표 데이터는 서브타입에 따라 달라진다.
- self_ref : 문서 내부 고유 참조 (이 요소를 어떻게 다시 찾을지)
- label : 요소 유형 (제목인지, 본문인지, 표인지)
- prov : 페이지와 좌표 (어느 페이지의 어느 위치인지)
- parent : 상위 그룹 (어떤 목록이나 그룹에 속하는지)

종류별로 실제로 갖는 정보:
```
TextItem    → text, label, prov 등
TableItem   → data.table_cells, captions 등
PictureItem → image, annotations, captions 등
GroupItem   → children
```

#### 2.4 Group 
: 여러 DocItem을 묶는 구조적 컨테이너
```
List Group
├─ list_item DocItem
├─ list_item DocItem
└─ list_item DocItem

body
├─ section_header: 제품 특징
└─ list Group
   ├─ list_item: 높은 효율
   ├─ list_item: 낮은 소음
   └─ list_item: 유지보수 용이
```
Group에는 문장을 복사해 넣는 게 아니라, **참조만 저장**

- Group 안에 Group도 들어갈 수 있다.
- Group과 제목 계층은 다르다
```
Group은 주로:
- 목록
- 중첩 목록
- 폼 영역
- 키-값 영역
- 컨테이너 구조
를 표현

제목 계층은: 문서 섹션의 상하 관계 표현
제품군
└─ 제품
   └─ Specifications
```

### 3. semchunk로 텍스트 분할
#### 3.1 semchunk
: 긴 텍스트를 **토큰 제한 안에서 자연스러운 경계로 나누는 텍스트 분할 라이브러리**
- Docling의 HybridChunker가 문서 구조만으로 해결할 수 없는 긴 텍스트를 만났을 때 내부적으로 사용
- semchunk는 모든 문서를 처음부터 청킹하는 주체가 아니라 구조적 분할을 수행한 후에도 **하나의 텍스트가 토큰 제한을 넘을 때 사용하는 보조 분할기**이다.

#### 3.2 무엇을 기준으로 나누는가?
: semchunk는 지정된 토크나이저로 토큰 수를 계산하면서 가능한 자연스러운 텍스트 경계를 선택한다.
- 선호하는 경계
```
긴 텍스트
→ 문단 경계
→ 줄바꿈
→ 문장 경계
→ 구·절 경계
→ 단어 경계
→ 그래도 너무 길면 더 작은 단위
```
단순히 max_tokens에 딱 맞춰 자르는 방식이 아니다.

(※ 위 순서는 이해를 돕기 위한 개념적 설명이며, semchunk 버전과 내부 splitter 구현에 따라 세부 우선순위는 달라질 수 있다. 안전하게 표현하면: semchunk는 토크나이저 기준 제한을 지키면서 공백, 문장부호, 줄바꿈 등 가능한 자연스러운 텍스트 경계를 우선 활용한다.)

#### 3.3 semchunk의 한계
semchunk는 텍스트 경계를 자연스럽게 선택하지만 다음은 알지 못한다.
- 이 문장이 어느 제품 설명인지
- 페이지가 바뀌었는지
- 이미지와 설명이 정확히 연결되는지
- 표의 행, 열 관계
- 제목 계층이 잘못 파싱됐는지
- 두 문단의 실제 주제가 같은지


### 4. HybridChunker의 표 처리
#### 4.1 기본 표 처리 흐름
```
TableItem
   ↓
TripletTableSerializer
표를 하나의 긴 텍스트로 변환
   ↓
토큰 수 검사
   ├─ 512 이하 → 그대로 하나의 청크
   └─ 512 초과 → 표 전용 LineBasedTokenChunker
                    ↓
                 토큰 제한에 맞게 분할
   ↓
merge_peers
```

(※ 여기서 512는 HybridChunker의 고정 기본값이 아니라 우리 실험 설정값이다. HybridChunker는 전달된 tokenizer 기준으로 `max_tokens = tokenizer.get_max_tokens()`처럼 max_tokens를 결정한다. 사용 모델(EmbeddingGemma)의 최대 입력은 2,048토큰이지만, 우리는 청크 제한을 512토큰으로 설정해 실험했다.)

#### 4.2 표를 Triplet 문자열로 변환

- **HybridChunker의 ChunkingDocSerializer**
```
table_serializer = TripletTableSerializer()
```
=> 표의 행과 열을 삼중항 문장으로 바꾼다.
```
행 제목, 열 제목 = 값
```
```
|Model   |SM3100 Pro |SM4100 Pro|
|Capacity|3,300~5,690|4,340~9,030|
|Pressure|3.0~13     |3.0~13|

Capacity, SM3100 Pro = 3,300~5,690.
Capacity, SM4100 Pro = 4,340~9,030.
Pressure, SM3100 Pro = 3.0~13.
Pressure, SM4100 Pro = 3.0~13.
```
개념적으로는 행,열,값의 관계를 텍스트에 포함하는 방식

- **맥스 토큰 이하면 그대로 출력**
제목과 캡션까지 포함한 표의 직렬화 결과가 512토큰 이하면 별도로 나누지 않는다.
```
Triplet 표 텍스트 ≤ 512
→ 하나의 TableItem 기반 DocChunk
```
이경우 semchunk, LineBasedTokenChunker도 실행되지 않는다.

- **표가 맥스 토큰을 넘으면**
HybridChunker는 먼저 해당 청크가 다음 조건인지 확인한다.
```
repeat_table_header is True
청크의 DocItem이 정확히 1개
그 DocItem이 TableItem
기본 ChunkingDocSerializer 사용
```
=> LineBasedTokenChunker 실행

#### 4.3 LineBasedTokenChunker
: Docling이 제공하는 "**줄 단위 보존형 토큰 청커**"
=> 토큰 제한은 지키되, 가능하면 한 줄을 중간에서 자르지 않고 청크에 넣는 청커

- 입력
```
제품 모델: SM3100 Pro
Capacity: 3,300 ~ 5,690
Pressure: 3.0 ~ 13
Dimension: 5,250 x 2,250 x 2,500
```
max_tokens 안에 모두 들어가면 하나의 청크로 만든다.
```
[청크 1]
제품 모델: SM3100 Pro
Capacity: 3,300 ~ 5,690
Pressure: 3.0 ~ 13
Dimension: 5,250 x 2,250 x 2,500
```
전체가 제한을 넘으면 줄 사이에서 나눈다.
```
[청크 1]
제품 모델: SM3100 Pro
Capacity: 3,300 ~ 5,690
Pressure: 3.0 ~ 13

[청크 2]
제품 모델: SM3100 Pro
Dimension: 5,250 x 2,250 x 2,500
```
단, 한 줄 자체가 토큰 제한보다 길면 그 줄은 어쩔 수 없이 내부에서 분할한다.

- 주요 특징
**줄 경계를 우선 보존**
: 일반 토큰 청커가 토큰 수만 보고 자르는 것과 달리 줄바꿈을 의미 있는 경계로 본다.
Markdown 표, 코드, 로그, 목록, 속성명: 값 구조, CSV와 유사한 행 데이터에 유리하다

**prefix 반복 가능**
각 청크 앞에 공통 문맥을 반복할 수 있다.
예를 들어 표 헤더를 prefix로 줄 수 있다.
```
Model | Capacity | Pressure | Dimension

[청크 1]
Model | Capacity | Pressure | Dimension
SM3100 | 3,300~5,690 | 3.0~13 | ...

[청크 2]
Model | Capacity | Pressure | Dimension
SM4100 | 4,340~9,030 | 3.0~13 | ...
```

**omit_prefix_on_overflow (LineBasedTokenChunker) / omit_header_on_overflow (HybridChunker)**
어떤 행은 단독으로는 토큰 제한 안에 들어가지만 prefix까지 붙이면 초과할 수 있다.
=> 값이 True이면 해당 행에 대해서만 헤더를 생략해서 행 전체를 보존한다.
반대로 기본값인 `False`라면 헤더 문맥을 유지하기 위해 내용을 추가 분할할 수 있다.

주의: 이 설정의 실제 이름은 클래스마다 다르다.
- `LineBasedTokenChunker` 자체의 파라미터명 : `omit_prefix_on_overflow`
- `HybridChunker`가 외부로 노출하는 파라미터명 : `omit_header_on_overflow`
- 매핑 관계 : `HybridChunker.omit_header_on_overflow` → 내부적으로 `LineBasedTokenChunker.omit_prefix_on_overflow`로 전달
(※ 정확한 파라미터명은 사용 중인 docling-core 버전 소스로 재확인 권장)

#### 4.4 그렇다면 왜 셀 값이 잘리는가?

- `TripletTableSerializer`의 특징
현재 버전은 모든 삼중항을 `.`로 이어 붙여 사실상 **하나의 긴 줄**로 만든다.
```
Capacity, SM3100 = 3,300~5,690. Capacity, SM4100 = ...
```
- `TripletTableSerializer`는 별도의 헤더 추출 방법을 구현하지 않는다.
```
header_lines = []
body_lines = [표 전체의 긴 한 줄]
```

따라서 LineBasedTokenChunker가 받는 입력은 실제 표의 행들이 아니다.
```
기대한 입력
├─ 헤더 줄
├─ Capacity 줄
├─ Power 줄
└─ Pressure 줄

실제 입력
└─ 표 전체가 이어진 하나의 긴 줄
```
LineBasedTokenChunker는 원래 줄 경계를 보존하려고 하지만, **그 한 줄 자체가 맥스 토큰보다 크면 결국 그 줄 내부를 토큰 제한에 맞춰 잘라야 한다.**
즉, 이름은 표 전용 줄 기반 분할이지만, 기본 Triplet 결과에 실제 줄 구분과 헤더 정보가 없어서 셀의 원자성까지 보장하지 못한다.

#### 4.5 semchunk는 언제 표에 적용되는가?
일반적인 기본 설정의 단일 TableItem에는 적용되지 않는다.

HybridChunker는 semchunk를 적용하기 전에 `_split_by_doc_items()`로 먼저 DocItem 경계 분할을 수행한다.
여러 DocItem으로 구성된 청크가 토큰 제한을 넘으면 이 단계에서 DocItem별로 먼저 쪼개지기 때문에, 긴 TableItem은 기본 실행에서 대부분 이미 단독 청크로 분리된 채로 표 처리 경로(LineBasedTokenChunker)에 진입한다.
즉 "청크 안에 TableItem 외 DocItem이 존재"한 상태로 semchunk까지 도달하는 경우는 기본 실행 흐름에서는 발생하기 어렵다.

기본 실행에서 긴 표의 일반적인 경로:
```
여러 DocItem 청크
→ DocItem 경계 분할 (_split_by_doc_items)
→ TableItem 단독 청크
→ LineBasedTokenChunker
```

##### 표 직렬화 문자열이 semchunk 경로로 가는 대표적인 경우
- `repeat_table_header = False`
- 다른 serializer/provider를 사용해 `ChunkingDocSerializer` 조건을 만족하지 못함
- 표가 이미 TableItem이 아닌 일반 텍스트로 입력됨
- 커스텀 처리로 "단일 TableItem" 조건을 만족하지 못함

##### Markdown serializer를 사용했을 때
Markdown serializer는 보통 실제 줄 단위 구조를 만든다.
```
| Model | SM3100 | SM4100 |
|---|---|---|
| Capacity | 3,300 | 4,340 |
| Pressure | 3.0~13 | 3.0~13 |
```
이 경우 `get_header_and_body_lines()`가 
```
header_lines
├─ | Model ... |
└─ |---...|

body_lines
├─ | Capacity ... |
└─ | Pressure ... |
```
로 구분할 수 있다.

그래서 LineBasedTokenChunker가 행 단위로 나누고 각 조각에 헤더를 반복 할 수 있다. 
기본 Triplet 방식보다 안정적이지만, 한 행이 너무 길면 그 행 내부는 여전히 분할될 수 있다.

### 5. 인접 DocChunk 병합
#### 5.1 merge_peers = True
: 같은 peer인 청크를 병합

- 같은 peer의 실제 기준
```
headings == current_headings
combined_token_count <= max_tokens
```
1. 서로 인접해 있어야 한다.
2. meta.headings가 완전히 같아야 한다.
3. 합친 최종 텍스트가 맥스토큰 이하여야 한다.
##### 확인하지 않는것
- 임베딩 의미 유사도
- 문장 간 의미적 연결성
- 같은 페이지인지
- 같은 label 인지
- 같은 이미지, 표, 본문 유형인지
- 좌표상 가까운지
- 제품명이 같은지

=> 인접하면서 동일한 제목 메타데이터를 가진 청크들을 토큰 제한까지 병합한다.

#### 5.2 페이지 청크가 합쳐진 이유

합쳐진 청크에는 
```
페이지 5 : Engineering drawing
페이지 6 : SA Series 기능 목록과 제품 이미지
```
가 함께 들어있다.

두 조각의 메타데이터가 모두 
`headings = ["specifications"]`로 인식 + 합쳐졌을 때 512토큰이 넘지 않음
HybridChunker는 페이지가 다름을 검사하지 않기 때문에 합쳐짐

#### 5.3 merge_peers=False 실험
(※ 아래 수치는 순수 HybridChunker 단독 결과가 아니라, 표를 별도 TableChunker로 고정 처리하는 통합 파이프라인에서 HybridChunker의 merge_peers 옵션만 바꾼 비교 결과다. 표를 별도 TableChunker로 고정한 통합 파이프라인이라서 표 청크 수(13개)가 양쪽 모두 동일하게 유지된다.)
```
항목	   merge_peers=True	    merge_peers=False
전체 청크	    52	                  153
일반 청크	    39	                  140
표 청크	        13	                  13
평균 토큰	  126.77	             46.51
20토큰 미만    	7	                  83
다중 페이지	    1	                  0
```
병합을 끄면 다중 페이지 문제는 없어지지만 청크가 지나치게 조각난다.