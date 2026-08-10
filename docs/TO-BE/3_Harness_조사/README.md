# Agent Harness 참고 Repo 분석

목적: repo 공부가 아니라 **우리 Harness Architecture의 설계 근거** 만들기.
"잘 만들어진 Agent Product는 어떻게 Context를 유지하고, Tool을 호출하고,
Agent를 실행하는가"를 확인해 설계 시간을 줄인다. 세 프로젝트를 전부 구현하는
것이 아니라 **공통 구조를 찾아 필요한 부분만 추출**한다.

공통 관찰 항목: 전체 Architecture / Agent 실행 흐름(Loop) / Context 유지 방식 /
Memory 구조 / Tool 호출 구조 / MCP 연결 / LLM·Model 연결 구조 / 여러 Agent·Tool
연결 방식. 코드만이 아니라 Mermaid·Architecture 문서·실행 흐름까지 본다.

## 분담 (2026-08-10 확정)

| Repo | 담당 | 마감 | 상태 | 정리 문서 |
|---|---|---|---|---|
| [Deep Agents From Scratch](https://github.com/langchain-ai/deep-agents-from-scratch) — Planning·Context Offloading·Sub-Agent 위임의 '왜' | **지훈** | 월(8/10) 분석 → 화 공유 | 완료 | `deep-agents_분석.md` |
| [OpenCode](https://github.com/anomalyco/opencode) — 실제 제품의 Loop·Model 연결·Session·MCP | **준억** | 월(8/10) 분석 → 화 공유 | **✅ 완료** (8/10 밤, juneok 브랜치 `e070860` — main 병합 대기) | `opencode_분석.md` (2,082줄) |
| [Claw Code](https://github.com/ultraworkers/claw-code) — 실행 흐름·Context·Tool·Agent Architecture | **주연** | 월(8/10) 분석 → 화 공유 | **✅ 완료** (8/11, juyeon 브랜치 `a8a611a` — main 병합 대기) | `claw-code_분석.md` (1,025줄) |

각자 맡은 프로젝트를 **팀원에게 설명할 수 있을 정도**까지 파악한다:
전체 Architecture, Agent 실행 흐름, Context/Memory, Tool Calling, MCP, Model
연결, 그리고 "우리 프로젝트에 가져올 수 있는 구조".

## 산출 규칙

각 분석은 이 폴더에 위 표의 파일명으로 남기고, 마지막 절은 반드시
**"우리 Harness에 적용할 것 / 적용하지 않을 것과 이유"**로 끝낸다.

세 분석이 모이면(화) 공통점 비교 → 실제로 우리 서비스에 쓸 구조만 선정 →
`../2_아키텍처_초안.md` §3(Harness 설계 골자)와 §6(직접 구현 vs 프레임워크)에
반영한다. 반영 담당: 준(PM).

**8/11 수합 완료** — 3/3 도착, 결론 수렴(직접 구현+구조 차용). 비교표와 회의
결정 안건 5건은 [`공통구조_비교_회의자료.md`](./공통구조_비교_회의자료.md) —
이 문서로 회의 후 아키텍처 v2 확정.
