-- =====================================================================
-- 2026-08-04 | 팀과 프로젝트의 경계를 바로잡는다
--
-- 무엇이 틀렸나:
--   폴더를 고르는 행위가 프로젝트를 만드는 행위로 구현돼 있었다. 폴더는 파일이
--   어디 있는지 알려주는 경로일 뿐이고, 그 안의 파일이 어느 프로젝트 것인지는
--   열어 봐야 안다. 그래서 폴더 선택만으로 프로젝트가 생기면 안 된다.
--
--   Jira 프로젝트는 반대다. Jira 프로젝트 하나에는 프로젝트 하나의 업무가 들어
--   있으므로, 그것을 고르는 것이 곧 "이 프로젝트를 우리 쪽에 등록"하는 행위다.
--   여러 개를 한 프로젝트에 매달면 서로 다른 프로젝트의 업무가 한 진행률로
--   뭉개진다.
--
-- 바뀌는 것:
--   Drive 폴더  proj_source → team_folder   (팀에 매단다)
--   문서(doc)   프로젝트 필수 → 팀 필수      (프로젝트는 지정될 때 채운다)
--   Jira        프로젝트당 여러 개 → 1:1
--
-- 실행 위치: DBeaver, 대상 DB의 public 스키마
-- 전제: team 테이블이 있어야 한다(2026-07-31 추가분).
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1. 프로젝트가 팀에 속한다
-- ---------------------------------------------------------------------
ALTER TABLE proj ADD COLUMN team_id VARCHAR(5);

-- 지금 있는 프로젝트는 소유자의 팀 것이다.
UPDATE proj
   SET team_id = (SELECT ua.team_id FROM user_account ua WHERE ua.account_id = proj.owner_account_id)
 WHERE team_id IS NULL;


-- ---------------------------------------------------------------------
-- 2. Drive 폴더를 팀으로 옮긴다
-- ---------------------------------------------------------------------
CREATE TABLE team_folder (
    team_folder_id      VARCHAR(5) PRIMARY KEY,
    team_id             VARCHAR(5)  NOT NULL,
    conn_id             VARCHAR(5)  NOT NULL,
    external_folder_id  VARCHAR(255) NOT NULL,
    display_name        VARCHAR(255),
    default_doc_role    VARCHAR(30),
    max_depth           INT,
    UNIQUE (team_id, external_folder_id)
);

-- 기존 DRIVE_FOLDER 행을 그대로 옮긴다. ID는 TF 접두어로 새로 매긴다
-- (proj_source_id를 재사용하면 PS/TF가 섞여 어느 테이블 것인지 알 수 없다).
INSERT INTO team_folder
    (team_folder_id, team_id, conn_id, external_folder_id, display_name, default_doc_role, max_depth)
SELECT 'TF' || lpad((row_number() OVER (ORDER BY ps.proj_source_id))::text, 3, '0'),
       p.team_id, ps.conn_id, ps.external_source_id,
       ps.display_name, ps.default_doc_role, ps.max_depth
  FROM proj_source ps
  JOIN proj p ON p.proj_id = ps.proj_id
 WHERE ps.source_type = 'DRIVE_FOLDER'
   AND p.team_id IS NOT NULL;

DELETE FROM proj_source WHERE source_type = 'DRIVE_FOLDER';


-- ---------------------------------------------------------------------
-- 3. 문서는 팀 것이다. 프로젝트는 지정될 때 채운다
-- ---------------------------------------------------------------------
ALTER TABLE doc ADD COLUMN team_id VARCHAR(5);

UPDATE doc
   SET team_id = (SELECT p.team_id FROM proj p WHERE p.proj_id = doc.proj_id)
 WHERE team_id IS NULL;

-- 등록 시점에는 어느 프로젝트 문서인지 모른다. 지금 들어 있는 proj_id는
-- "폴더를 고른 그 프로젝트"라는 뜻이었을 뿐이라 근거가 없다 — 비운다.
ALTER TABLE doc ALTER COLUMN proj_id DROP NOT NULL;
UPDATE doc SET proj_id = NULL;


-- ---------------------------------------------------------------------
-- 4. Jira 프로젝트는 프로젝트당 하나
-- ---------------------------------------------------------------------
-- proj_source에서 Drive 전용 컬럼을 뺀다. team_folder로 옮겨 갔다.
ALTER TABLE proj_source DROP COLUMN default_doc_role;
ALTER TABLE proj_source DROP COLUMN max_depth;

-- 한 프로젝트에 Jira가 여럿 붙어 있으면 프로젝트를 나눈다. Jira 프로젝트 하나가
-- 프로젝트 하나이므로, 붙어 있던 나머지는 원래 별개의 프로젝트였다.
-- 남기는 하나는 먼저 등록된 것이고, 나머지는 새 proj로 옮긴다.
DO $$
DECLARE
    r RECORD;
    new_proj_id VARCHAR(5);
BEGIN
    FOR r IN
        SELECT ps.proj_source_id, ps.display_name, ps.external_source_id,
               p.team_id, p.owner_account_id, p.tz
          FROM (
              SELECT proj_source_id, proj_id, display_name, external_source_id,
                     row_number() OVER (PARTITION BY proj_id ORDER BY proj_source_id) AS rn
                FROM proj_source
          ) ps
          JOIN proj p ON p.proj_id = ps.proj_id
         WHERE ps.rn > 1
    LOOP
        SELECT 'PJ' || lpad((COALESCE(max(substring(proj_id FROM 3)::int), 0) + 1)::text, 3, '0')
          INTO new_proj_id
          FROM proj;

        INSERT INTO proj (proj_id, name, status, tz, owner_account_id, team_id)
        VALUES (new_proj_id,
                COALESCE(NULLIF(r.display_name, ''), r.external_source_id),
                'ACTIVE', r.tz, r.owner_account_id, r.team_id);

        UPDATE proj_source SET proj_id = new_proj_id WHERE proj_source_id = r.proj_source_id;
    END LOOP;
END $$;

-- 프로젝트 이름을 Jira 프로젝트 이름으로 맞춘다. 지금 이름은 폴더를 고를 때
-- 최상위 폴더명에서 따온 임시값이라 프로젝트를 가리키지 않는다.
UPDATE proj p
   SET name = ps.display_name
  FROM proj_source ps
 WHERE ps.proj_id = p.proj_id
   AND NULLIF(ps.display_name, '') IS NOT NULL;

-- Jira에서 가져온 프로젝트는 이미 진행 중이다. DRAFT는 "온보딩이 만들다 만 것"을
-- 뜻했는데, 이제 온보딩은 프로젝트를 만들지 않는다.
UPDATE proj SET status = 'ACTIVE'
 WHERE status = 'DRAFT' AND proj_id IN (SELECT proj_id FROM proj_source);

ALTER TABLE proj_source ADD CONSTRAINT ux_proj_source_proj UNIQUE (proj_id);

COMMIT;


-- =====================================================================
-- 확인용 — COMMIT 뒤에 따로 실행
-- =====================================================================
-- SELECT proj_id, name, team_id FROM proj ORDER BY proj_id;
-- SELECT * FROM team_folder ORDER BY team_folder_id;          -- 폴더 4개가 팀에
-- SELECT count(*) FILTER (WHERE team_id IS NULL) FROM doc;    -- 0이어야 한다
-- SELECT proj_id, count(*) FROM proj_source GROUP BY 1;       -- 전부 1이어야 한다
