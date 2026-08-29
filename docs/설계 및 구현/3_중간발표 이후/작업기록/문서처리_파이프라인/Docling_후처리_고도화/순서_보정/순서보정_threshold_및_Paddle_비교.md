# Reading Order threshold 근거와 PaddleOCR-VL 비교 결과

> 출처 표기: 본문의 `practice/*`, `heading_validation/*`, `autoresearch_lite/*`,
> `handoff/*`는 이 제품 저장소 내부 경로가 아니라 개인 Docling 실험 정본과
> canonical handoff `docling_postprocess_merge_handoff_20260825_v2`에서 검증한
> 원본 상대 경로다. 현재 저장소에는 큐레이션 문서와 대표 이미지만 포함한다.

## 1. threshold를 정하는 원칙

현재 threshold는 문서 결과를 보고 매번 임의로 바꾸는 값이 아니다.

```text
DEV 사례로 초기값 설정
→ 테스트·회귀 확인
→ HOLDOUT 문서와 규칙을 함께 동결
→ HOLDOUT 결과를 보고 threshold를 사후 조정하지 않음
→ 새 DEV 사이클에서만 변경 검토
```

최종 누적 자동 적용 후보는 60건이며 모두 TP, FP는 0건이었다. Wilson 95% 하한은
93.9828%다. 다만 이는 후보 Precision이지 전체 문서 Recall이 아니므로 다음
threshold를 범용 최적값이 아니라 **현재의 보수적 동결값**으로 기록한다.

## 2. 현재 국소 역전 기준

| 지표 | 현재값 | 근거·의도 | 상태 |
|---|---:|---|---|
| 같은 페이지 | 필수 | 페이지 경계를 넘는 순서는 별도 문서 흐름 판단이 필요함 | 구조 필수 |
| 같은 `parent_ref` | 필수 | Docling의 같은 직접 부모 그룹 안에서만 비교 | 구조 필수 |
| JSON상 인접 | 바로 이웃 | 멀리 떨어진 요소의 대규모 재배열을 막음 | 구조 필수 |
| 좌우 정렬 차이 | `≤ 0.035` | 같은 열·같은 세로 흐름으로 볼 수 있는 범위 | 실험값 |
| 세로 차이 | `0.005 ~ 0.08` | 동일 줄의 좌표 잡음은 제외하고, 다른 섹션까지 먼 후보도 제외 | 실험값 |
| 시각적 중간 sibling | `0` | 사이에 다른 요소가 있으면 단순 swap의 안전성이 떨어짐 | 자동 적용 필수 |
| 복합 geometry | 없음 | 다단·표·겹침은 별도 오류군으로 분리 | 자동 적용 필수 |
| operation | `SWAP_ADJACENT` | 최소 변경으로 두 요소만 교환 | 변경 계약 |

현재 `0.035`, `0.005`, `0.08`은 페이지 크기 정규화 좌표 기준이다. 예를 들어 세로 차이 `0.02`는 페이지 높이의 2% 차이다. 이 값들은 일반 문서 전체의 최적값이라고 주장하지 않으며, 새로운 DEV 표본에서 정상 보존률·오탐·미탐을 함께 확인한 뒤에만 변경한다.

## 3. 텍스트 연속성 기준

텍스트 연속성은 자동 보정의 단독 근거가 아니라 보조 신호다.

| 지표 | 현재값 | 의도 | 상태 |
|---|---:|---|---|
| 아래 방향 간격 | `≤ 0.08` | 가까운 다음 문단 후보만 비교 | 실험값 |
| 오른쪽 방향 간격 | `≤ 0.05` | 같은 행의 이어지는 박스 후보만 비교 | 실험값 |
| 아래 요소 가로 겹침 | `≥ 0.5` | 서로 다른 열을 잘못 연결하지 않음 | 실험값 |
| 오른쪽 요소 세로 겹침 | `≥ 0.65` | 같은 행인지 확인 | 실험값 |
| 크기 유사도 | `≥ 0.55` | 전혀 다른 블록을 연결하지 않음 | 실험값 |
| 일반 문단 | 20자 이상·7토큰 이상 | 제목·짧은 라벨을 문단으로 오인하지 않음 | 보수 게이트 |
| 한국어 문단 | 20자 이상·3토큰 이상·12음절 이상 | 한국어 띄어쓰기 토큰 수가 영어보다 작을 수 있음을 반영 | 보수 게이트 |
| 자동 점수 | `≥ 0.82` | 거리·정렬·크기·부모·텍스트 종합 점수 | 실험값 |
| 1·2위 후보 margin | `≥ 0.15` | 비슷한 후보가 여러 개면 자동 보정하지 않음 | 자동 적용 필수 |

점수 가중치는 거리 35%, 정렬 30%, 크기 20%, 같은 부모 10%, 텍스트 5%다. 한국어 조사 하나만으로는 자동 게이트를 통과하지 못한다.

## 4. PaddleOCR-VL/PP-Layout과의 관계

공식 PaddleOCR 문서에 따르면 PaddleOCR-VL의 첫 단계인 layout analysis는 레이아웃 요소를 검출·배치하고 읽기 순서를 결정한 뒤, 그 순서대로 요소 이미지를 VLM에 전달한다. 결과의 `parsing_res_list`도 읽기 순서로 정렬되며 `block_order`를 제공한다. [PaddleOCR-VL 공식 문서](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/pipeline_usage/PaddleOCR-VL.en.md)

따라서 두 방식은 적용 위치가 다르다.

```text
PP-Layout:
페이지 이미지 → 레이아웃 검출 + 읽기 순서 생성 → VLM 인식

우리 룰:
Docling 최종 JSON → 구조·좌표 기반 국소 순서 검증/보정 → Chunk
```

PP-Layout이 더 넓은 다단·표·이미지 구조를 처리할 가능성은 있지만, 공식 이슈에도 PaddleOCR-VL에서 읽기 순서가 잘못 나온 사례가 보고되어 있다. [PaddleOCR-VL 순서 오류 이슈](https://github.com/PaddlePaddle/PaddleOCR/issues/16766)

## 5. Paddle 동일 페이지 shadow 비교 결과

한화, LS일렉트릭, 한화솔루션, 삼성전기 등 5개 문서·9페이지에서 Docling과
PaddleOCR-VL full-page `block_order`를 같은 페이지 기준으로 대조했다.

- 한화 p2 소개문은 양쪽 결과가 같은 좌→우 흐름을 지지했다.
- LS일렉트릭 p2의 두 국소 역전은 우리 최소 swap이 시각 순서와 일치했다.
- 표·도면·카드가 섞인 페이지에서는 Paddle의 element 병합과 ordered coverage가
  달라 직접적인 정답 또는 자동 대체로 사용할 수 없었다.
- Paddle full-page 실측은 평균 약 11.3초/쪽, 우리 로컬 후처리는 약 18ms 수준이라
  전 페이지 운영 편입보다 고난도·불일치 페이지 shadow 진단이 효율적이었다.

따라서 Paddle 결과를 Docling JSON에 복사하거나 threshold 조정 근거로 사용하지
않았다. 최종 역할은 독립적인 전역 순서 관측값과 disagreement sampling 보조다.

```text
Docling 완성 JSON → 저비용 국소 보정 → Chunk
          ↘ Paddle block_order는 선별 페이지 shadow 진단만 수행
```

## 6. 2026-08-19 실행 자료와 범위 고정

팀원이 공유한 `docling_tableformer_paddleocr_vl16_shadow_runpod.ipynb`는 Docling TableFormer가 만든 **표 crop**만 PaddleOCR-VL에 전달하는 구조다. `use_layout_detection=False`이므로 전체 페이지 `block_order` 비교 자료로 해석하지 않는다. 표 구조 승자도 사람 라벨 전에는 자동 선택하지 않는다.

전체 페이지 비교는 별도 `practice/runpod_paddle_full_page_shadow.py`로 수행한다. 이 runner는 페이지 이미지를 입력으로 PaddleOCR-VL-1.6의 `use_layout_detection=True`를 켜고 `block_order`를 저장하지만, Docling JSON·order map은 수정하지 않는다. 공식 API도 `predict()` 결과에서 `block_bbox`, `block_label`, `block_content`, `block_id`, `block_order`를 제공하도록 정의한다. [PaddleOCR-VL Python API](https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/PaddleOCR-VL.html)

첫 sample은 결과 확인 전에 한화 2쪽과 새 한국 기업 문서 4종의 9쪽으로 고정했다.
비교 완료 후에도 threshold를 사후 조정하지 않았으며 Paddle은 진단용 shadow로
유지했다.
