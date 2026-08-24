-- =====================================================================
-- 2026-08-24 | 커넥터 증분 동기화 커서
--
-- 왜: 지금 변경 감지는 **연결된 폴더를 통째로 훑어** 수정 시각을 비교한다.
--     폴더마다 API 를 2번 부르므로(파일 목록 + 하위 폴더 목록, 상한 200폴더)
--     한 번이 비싸고, 그래서 「폴더 설정을 저장할 때」만 돌고 있었다.
--
--     Google Drive 의 Changes API 는 **지난 지점 이후의 변경만** 돌려준다.
--     변화가 없으면 호출 1번이라 자주 물어도 부담이 없다. 그 「지난 지점」을
--     가리키는 것이 이 칸이다.
--
-- 이름을 `drive_page_token` 이 아니라 `sync_cursor` 로 둔다. 계획된 저장소
-- 넷 중 델타 API 가 있는 것은 Drive 와 SharePoint 뿐이고(Notion·Confluence 는
-- 수정 시각 폴링밖에 없다), 저장소마다 그 값의 이름과 모양이 다르다 —
-- Drive 전용 낱말을 스키마에 새기면 두 번째 커넥터에서 바꿔야 한다.
--
-- **NULL 은 「아직 기준점을 안 잡았다」**는 뜻이다. 그때는 변경을 처리하지 않고
-- 현재 시점 토큰만 받아 저장한다 — 연결 이전의 변경까지 거슬러 올라갈 이유가
-- 없고, 처음 등록은 폴더 스캔이 이미 한다.
--
-- 실행 위치: DBeaver 또는 컨테이너에서 직접, 대상 DB 의 public 스키마
-- =====================================================================

BEGIN;

ALTER TABLE connector_conn
    ADD COLUMN IF NOT EXISTS sync_cursor TEXT;

COMMENT ON COLUMN connector_conn.sync_cursor IS
    '증분 동기화의 재개 지점. Google Drive 는 changes API 의 pageToken 이 들어간다. '
    'NULL 이면 아직 기준점을 안 잡은 상태이고, 그때는 현재 시점 토큰만 받아 저장한다.';

COMMIT;


-- =====================================================================
-- 확인용 — COMMIT 뒤에 따로 실행
-- =====================================================================
-- SELECT column_name FROM information_schema.columns
--  WHERE table_name = 'connector_conn' AND column_name = 'sync_cursor';
--
-- SELECT connector_type, count(*) FILTER (WHERE sync_cursor IS NOT NULL) AS 커서있음
--   FROM connector_conn GROUP BY connector_type;
--   기존 행은 전부 NULL 이어야 한다.
