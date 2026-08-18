-- =====================================================================
-- 2026-08-18 | 「내 파일」 — 개인 소유 문서 (M④)
--
-- 왜: 사용자가 자기 컴퓨터에서 문서를 올려 파싱·인덱싱하고, 켜 둔 것만
--     검색에 쓰는 기능(8/18 멘토링). 지금 `doc` 은 팀 소유뿐이라 담을 자리가
--     없다.
--
-- **표를 나누지 않는다.** 파싱·임베딩이 `doc` 이 아니라 `doc_id` 에 묶여 있다 —
-- `doc_block`·`chunk`·`vec_idx` 어디에도 팀 칸이 없다. 나누면 그 셋까지
-- 나누거나 `doc_block.doc_id` 를 다형으로 만들어야 하고, 파서·임베딩·검색을
-- 통째로 두 벌 쓰게 된다.
--
-- 실행 위치: DBeaver 또는 _apply 스크립트, 대상 DB 의 public 스키마
-- 전제: 없다. 기존 행은 전부 팀 문서로 남는다(두 칸 다 기본값).
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1. 누구 것인가
--
-- **개인 문서에는 `team_id` 를 넣지 않는다(NULL).** 이것이 이 마이그레이션의
-- 핵심이다. 팀 문서를 읽는 자리가 13 곳인데 전부 `WHERE d.team_id = %s` 로
-- 거는데, NULL 이면 그 13 곳이 **한 줄도 안 바뀐 채** 개인 문서를 걸러낸다
-- (`NULL = 'TE001'` 은 참이 아니다).
--
-- 틀리는 쪽이 안전한 방향이다 — 조건을 빠뜨리면 개인 문서가 팀 검색에 새는
-- 것이 아니라 안 보인다. 새는 것은 사고고 안 보이는 것은 버그다.
-- ---------------------------------------------------------------------
ALTER TABLE doc
    ADD COLUMN IF NOT EXISTS owner_account_id VARCHAR(5);

COMMENT ON COLUMN doc.owner_account_id IS
    '개인 소유 문서를 올린 계정(user_account.account_id, FK 없음). '
    '팀 문서는 NULL. 이 값이 있으면 team_id 는 NULL 이어야 한다.';

-- 팀 것도 아니고 내 것도 아닌 문서, 그리고 둘 다인 문서를 막는다.
-- 둘 다인 행이 생기면 그 순간 팀 검색에 개인 파일이 섞인다.
ALTER TABLE doc
    ADD CONSTRAINT doc_owner_xor_team CHECK (
        (team_id IS NOT NULL AND owner_account_id IS NULL)
     OR (team_id IS NULL AND owner_account_id IS NOT NULL)
    );

CREATE INDEX IF NOT EXISTS ix_doc_owner
    ON doc (owner_account_id) WHERE owner_account_id IS NOT NULL;

-- ---------------------------------------------------------------------
-- 2. 검색 범위에 넣을 것인가
--
-- **`search_ready` 와 다르다.** 그쪽은 칸이 아니라 계산값이다 — 청크가 있는지
-- `EXISTS` 로 본다(`_SEARCH_READY`). 이 칸은 **의도**다: 껐는데 청크는 남아
-- 있는 상태가 정상이다. 둘을 한 값으로 뭉개면 끄는 순간 색인을 지워야 하고,
-- 다시 켤 때 또 파싱한다.
--
-- 팀 문서에는 뜻이 없다 — 커넥터 문서는 시스템이 필요할 때 승격시키지 사람이
-- 켜지 않는다(8/15 결정). 그래서 기본값 true 로 두고 개인 문서에서만 읽는다.
-- ---------------------------------------------------------------------
ALTER TABLE doc
    ADD COLUMN IF NOT EXISTS search_enabled BOOLEAN NOT NULL DEFAULT true;

COMMENT ON COLUMN doc.search_enabled IS
    '내 파일 라이브러리의 toggle. 개인 문서에서만 뜻이 있다 — '
    '팀 문서는 시스템이 필요할 때 승격시키므로 항상 true 다.';

COMMIT;


-- =====================================================================
-- 확인용 — COMMIT 뒤에 따로 실행
-- =====================================================================
-- SELECT column_name, data_type, is_nullable, column_default
--   FROM information_schema.columns
--  WHERE table_name = 'doc' AND column_name IN ('owner_account_id','search_enabled');
--   두 줄이 나오면 정상.
--
-- SELECT conname FROM pg_constraint WHERE conname = 'doc_owner_xor_team';
--   한 줄이 나오면 정상.
--
-- SELECT count(*) FILTER (WHERE team_id IS NOT NULL)  AS 팀문서,
--        count(*) FILTER (WHERE owner_account_id IS NOT NULL) AS 개인문서
--   FROM doc;
--   기존 행은 전부 팀문서로 세어져야 한다. 개인문서가 0 이 아니면 뭔가 잘못됐다.
--
-- `source_type` 은 여기서 안 건드린다. 지금 VARCHAR(20) 자유 문자열이라
-- 'UPLOAD' 를 넣는 데 스키마 변경이 필요 없다 — 값을 쓰는 쪽(업로드 API)에서
-- 넣기 시작하면 된다.
