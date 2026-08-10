# 서비스 구조 (IA) — 초안

> 작성 중. 기존 업무 분배 중심 IA를 폐기하고 Agent Platform 관점으로 재설계한다.

## 화면 구성

- **Chat** — 핵심 인터페이스. Agent 선택 → 업무 요청 → Connector 데이터 활용 → Tool 실행 → 결과 확인
- **Agent Builder** — Profile(이름·Description·역할) / Behavior·Instruction / Model 선택 / Tool·MCP 연결. Description은 Agent 호출 판단에 쓰이는 정보
- **Project** — 프로젝트 단위 Context 유지 (Project Operation Copilot 정체성). '업무 분배 시작' 버튼 중심 구조는 제거/축소
- **Settings** — Model / Connector / MCP / Permission
- **Admin** (여력 시) — Model 상태 · Tool · Token 사용량 · Agent 실행 · Analytics · Permission

## 기존 27개 화면 처리

<!-- AS-IS/시스템_전체_설계.md의 화면 목록을 기준으로 유지/축소/제거/재배치 표를 만든다 -->

## 사용자 흐름

<!-- 비개발자 실무자 기준 주요 여정: Agent 생성 → Chat에서 사용 → 결과 확인 -->
