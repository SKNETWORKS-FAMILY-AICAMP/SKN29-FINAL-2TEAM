-- =====================================================================
-- 2026-08-18 | 내 파일 공유 (M④ 후속)
--
-- 왜: 「내 파일」과 「공유 받은 파일」을 나눠 보고, 팀원이 공유하면 내 목록에
--     뜨게 한다(8/18 PM). M④ 를 정할 때 「공유는 별개 기능이니 순서를 지킨다」
--     로 뒤로 미뤄 뒀던 것이고, 올리기·파싱·toggle 이 끝나서 이제 온다.
--
-- **`team_id` 를 채우지 않는다.** 그러면 개인 문서가 팀 문서가 되어 소유가
-- 사라지고, `doc_owner_xor_team` 검사에도 걸린다. 공유는 소유를 옮기는 것이
-- 아니라 **보여 주는 것**이라 칸을 따로 둔다.
--
-- 실행 위치: DBeaver 또는 컨테이너에서 직접, 대상 DB 의 public 스키마
-- 전제: 2026-08-18_personal_documents.sql
-- =====================================================================

BEGIN;

-- 공유한 팀. NULL 이면 나만 본다.
--
-- **사람이 아니라 팀에 공유한다.** 8/18 에 「공유는 개인 → 팀으로 올리는
-- 조작」으로 적어 뒀고, 사람 단위로 하면 받는 쪽 표가 하나 더 필요한데 지금
-- 필요한 것은 「팀원이 올린 것을 팀이 본다」까지다.
ALTER TABLE doc
    ADD COLUMN IF NOT EXISTS shared_team_id VARCHAR(5);

COMMENT ON COLUMN doc.shared_team_id IS
    '개인 문서를 공유한 팀(team.team_id, FK 없음). NULL 이면 소유자만 본다. '
    'team_id 와 다르다 — 이 값이 있어도 소유는 여전히 owner_account_id 다.';

-- 공유 받은 목록이 이 칸으로만 걸린다.
CREATE INDEX IF NOT EXISTS ix_doc_shared_team
    ON doc (shared_team_id) WHERE shared_team_id IS NOT NULL;

-- **팀 문서는 공유할 것이 없다.** 이미 팀 것이라 이 칸이 채워지면 두 경로로
-- 같은 문서가 목록에 들어온다(팀 문서 목록 + 공유 받은 목록).
ALTER TABLE doc
    ADD CONSTRAINT doc_share_is_personal_only CHECK (
        shared_team_id IS NULL OR owner_account_id IS NOT NULL
    );

COMMIT;


-- =====================================================================
-- 확인용 — COMMIT 뒤에 따로 실행
-- =====================================================================
-- SELECT column_name FROM information_schema.columns
--  WHERE table_name = 'doc' AND column_name = 'shared_team_id';
--
-- SELECT conname FROM pg_constraint WHERE conname = 'doc_share_is_personal_only';
--
-- SELECT count(*) FILTER (WHERE shared_team_id IS NOT NULL) AS 공유됨 FROM doc;
--   기존 행은 전부 0 이어야 한다 — 공유는 사람이 켜는 것이지 기본값이 아니다.
