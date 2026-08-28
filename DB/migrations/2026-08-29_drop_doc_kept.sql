-- `doc.kept` 되돌리기(2026-08-29). 도구가 만든 파일은 다시 자동으로 「내 파일」에
-- 저장한다 — 채팅 카드에는 「다운로드」만 두고, 「내 파일에 저장」 버튼과 명시적
-- 저장 흐름을 없앤다. `2026-08-28_doc_kept.sql` 의 반대다.

ALTER TABLE doc DROP COLUMN IF EXISTS kept;
