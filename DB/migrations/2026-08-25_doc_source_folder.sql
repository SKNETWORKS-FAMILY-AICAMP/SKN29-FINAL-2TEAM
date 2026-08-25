-- =====================================================================
-- 2026-08-25 | 문서가 어느 폴더에서 왔는지
--
-- 왜: 「문서」 화면이 좌측에 폴더 트리를, 우측에 그 폴더의 파일과 색인 상태를
--     보여준다. 그런데 `doc` 은 **어느 폴더에서 온 파일인지 기억하지 않는다** —
--     `src_file_id` 로 Drive 파일 하나를 가리킬 뿐이라, 폴더로 묶을 방법이 없다.
--
--     정작 그 정보는 이미 만들어지고 있었다. `clients.list_drive_files` 가
--     항목마다 `folder_path` 를 붙여 주는데(하위 폴더까지 따라 내려가므로
--     평면 목록만 봐서는 알 수 없어서 붙인 값이다), 수집이 등록할 때 그것을
--     쓰지 않고 버렸다. 여기서는 **버리던 값을 받을 칸**을 만든다.
--
-- 폴더 테이블을 따로 만들지 않는다. 트리는 이 두 칸에서 유도한다 —
-- `team_folder` 가 뿌리(사람이 고른 폴더)를 주고, 그 아래 가지는 문서들이
-- 들고 있는 `src_folder_path` 의 서로 다른 값이다. 하위 폴더 구조를 따로
-- 저장하면 Drive 에서 폴더가 바뀔 때마다 두 곳을 맞춰야 하는데, 문서에 붙여
-- 두면 다음 수집이 자연히 갱신한다.
--
-- **Drive 에 다시 물어보는 방식을 택하지 않는 이유**는 `TeamFolderRepository`
-- `replace` 가 폴더 이름을 굳이 저장해 두는 이유와 같다 — 화면이 커넥터 생존에
-- 묶이면 연결이 만료된 순간 문서 화면이 통째로 안 열린다.
--
-- 기존 행은 둘 다 NULL 이다. **「모른다」이지 「최상위」가 아니다** — 다음
-- 수집이 채운다. 화면은 그동안 「미분류」로 묶어 보여준다. 빈 문자열('')이
-- 「고른 폴더 바로 아래」라서, 그 둘을 NULL 로 뭉치면 구분이 사라진다.
--
-- 실행 위치: DBeaver 또는 컨테이너에서 직접, 대상 DB 의 public 스키마
-- =====================================================================

BEGIN;

ALTER TABLE doc
    ADD COLUMN IF NOT EXISTS team_folder_id  VARCHAR(5),
    ADD COLUMN IF NOT EXISTS src_folder_path TEXT;

COMMENT ON COLUMN doc.team_folder_id IS
    '이 문서를 데려온 team_folder.team_folder_id(FK 없음) — 사람이 고른 뿌리 폴더. '
    '어느 저장소 연결에서 왔는지는 team_folder.conn_id 를 따라가면 나온다. '
    'NULL 은 아직 모르는 것이고(이 칸이 생기기 전에 등록된 문서), 다음 수집이 채운다.';

COMMENT ON COLUMN doc.src_folder_path IS
    '뿌리 폴더 안에서의 상대 경로. 빈 문자열이면 뿌리 바로 아래이고, '
    '''기획/요구사항'' 처럼 슬래시로 이어진다(clients.list_drive_files 의 folder_path 그대로). '
    'NULL 은 모르는 것이라 빈 문자열과 뜻이 다르다.';

-- 폴더로 묶어 보는 것이 이 화면의 기본 동작이다.
CREATE INDEX IF NOT EXISTS idx_doc_team_folder
    ON doc (team_id, team_folder_id);

COMMIT;


-- =====================================================================
-- 확인용 — COMMIT 뒤에 따로 실행
-- =====================================================================
-- SELECT column_name, data_type, is_nullable FROM information_schema.columns
--  WHERE table_name = 'doc' AND column_name IN ('team_folder_id', 'src_folder_path');
--
-- 기존 행은 전부 NULL 이어야 한다(= 아직 모른다).
-- SELECT count(*) FILTER (WHERE team_folder_id IS NULL) AS 모름,
--        count(*) FILTER (WHERE team_folder_id IS NOT NULL) AS 채워짐
--   FROM doc WHERE team_id IS NOT NULL;
--
-- 수집을 한 번 돌린 뒤에는 팀 문서가 폴더별로 묶여야 한다.
-- SELECT team_folder_id, coalesce(src_folder_path, '(모름)') AS 경로, count(*)
--   FROM doc WHERE team_id IS NOT NULL GROUP BY 1, 2 ORDER BY 1, 2;
