# TO-BE — Agent Platform 설계 작업 공간

8/8 멘토링에서 확정된 방향(업무 분배 서비스 → 비개발자용 Agent Platform 확장)의
설계 문서가 여기에 쌓인다. 근거는 `../회의록/2026-08-08_오프라인_멘토링.md`.

구 방향(중간발표 시점) 문서는 `../AS-IS/`에 있다. AS-IS 문서는 현재 코드의
기록으로는 유효하지만 TO-BE 설계의 근거로 쓰지 않는다.

## 한 줄 정의

기업의 데이터와 업무 도구를 연결하고, 비개발자가 프로젝트 운영에 필요한
AI Agent를 직접 만들고 활용할 수 있도록 하는 Agent 기반 Project Operation Copilot.

- Platform = 우리가 만드는 제품 (Builder + Harness + Connector/MCP)
- 업무 추출·분배 = Platform 위의 Pre-built Agent / 대표 데모

## 문서

| 문서 | 내용 | 마감 |
|---|---|---|
| `1_서비스구조_IA.md` | Chat·Builder·Project·Settings·Admin 화면과 사용자 흐름 | 08/11 초안 |
| `2_아키텍처_초안.md` | 전체 구조 — Harness·Connector·MCP·기존 파이프라인 재배치 | 08/12 멘토링 리뷰 |
| `3_Harness_조사/` | 참고 repo 분석 (팀원별 1개) → 우리 설계 적용안 | 08/11 |
| `4_평가_설계.md` | Document/Retrieval/Extraction/Tool/E2E 지표 — 개발 전에 정의 | 08/12 |
| `5_E2E_시나리오.md` | 대표 시나리오 (문서 → Task 추출 → 확인 → Jira 생성) | 08/12 |

## 일정

- 08/09~10 조사·설계 → 08/11~12 Architecture 초안 확정 → **08/12 온라인 멘토링 리뷰** → 즉시 개발
