-- 2026-08-21 — 도구 호출이 어떤 문서를 건드렸는지 남긴다.
--
-- 멘토링 전달: "Tool 호출 결과 어떤 문서/데이터가 조회되었는지". 지금까지
-- `tool_call` 은 `input_summary`(질의문)만 남겨서, 검색이 무엇을 골랐는지는
-- SSE 로 화면에 한 번 흐르고 사라졌다.
--
-- **본문이 아니라 식별자만 담는다.** 원문을 남기면 감사 로그가 문서 사본이
-- 된다(`input_summary` 가 자격증명을 안 남기는 것과 같은 원칙). 접근 감사에
-- 필요한 것은 "어느 문서를 봤나"이지 "무엇이라고 쓰여 있었나"가 아니다.
--
-- `TEXT[]` 인 이유: `doc_meta.keywords` 가 이미 같은 모양이고, 배열이면
-- `WHERE 'DC001' = ANY(retrieved_doc_ids)` 로 "이 문서가 언제 누구에게
-- 조회됐나"를 바로 물을 수 있다. JSON 으로 담으면 그 질문마다 파싱해야 한다.
ALTER TABLE tool_call ADD COLUMN IF NOT EXISTS retrieved_doc_ids TEXT[];

-- 위 질문(문서 하나로 역추적)이 이 컬럼의 주된 사용처라 GIN 을 건다.
CREATE INDEX IF NOT EXISTS ix_tool_call_retrieved_docs
    ON tool_call USING GIN (retrieved_doc_ids);
