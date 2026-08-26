-- =====================================================================
-- 2026-08-25 | Drive 변경 알림 채널(웹훅)
--
-- 왜: 지금 증분 동기화는 **대화를 시작할 때** 돈다(2026-08-24). 그 시점을
--     고른 이유는 폴더 스캔이 비싸서 자주 못 돌렸기 때문이고, Changes API 가
--     붙으면서 「자주 물어도 되는」 상태가 됐기 때문이다.
--
--     그런데 대화를 열 때마다 Drive 를 부르는 것은 **사용자 행동에 얹은 것**
--     이지 문서가 바뀌는 시점과는 무관하다. Google 이 권하는 쪽은 반대다 —
--     `changes.watch` 로 채널을 열어 두면 **바뀔 때 저쪽이 알려 준다**
--     (developers.google.com/workspace/drive/api/guides/push).
--
-- 채널을 기억할 칸이 필요하다. 지금 `connector_conn` 에는 `sync_cursor`(어디까지
-- 봤는가)뿐이고, 「지금 열려 있는 채널이 무엇인가」를 담을 데가 없다.
--
-- **셋을 함께 둔다.**
--   channel_id         우리가 만든 채널의 id. 알림이 오면 이것으로 어느 연결인지 찾는다.
--   channel_resource_id  Google 이 준 값. **채널을 멈추려면 이것이 있어야 한다**
--                        (`channels.stop` 은 id 와 resourceId 를 함께 받는다).
--   channel_expires_at   만료 시각. Drive 의 changes 채널은 **최대 1주**이고
--                        **자동 갱신이 없다** — 만료 전에 새로 열어야 한다.
--                        그 판단을 하려면 시각을 알아야 한다.
--
-- **채널 비밀값은 여기 안 넣는다.** 알림이 진짜 Google 이 보낸 것인지는
-- `X-Goog-Channel-Token` 으로 확인하는데, 그 값은 서버 설정(`.env`)에서 오고
-- 모든 채널이 같은 것을 쓴다 — 팀마다 다를 이유가 없고, DB 에 두면 백업·덤프에
-- 비밀이 섞인다.
--
-- 셋 다 NULL 이 정상이다. **채널이 없는 상태가 고장이 아니다** — 웹훅을 아직
-- 안 연 연결이고, 그때는 예전처럼 대화 시작 시 동기화가 받쳐 준다.
--
-- 실행 위치: DBeaver 또는 컨테이너에서 직접, 대상 DB 의 public 스키마
-- =====================================================================

BEGIN;

ALTER TABLE connector_conn
    ADD COLUMN IF NOT EXISTS channel_id          VARCHAR(64),
    ADD COLUMN IF NOT EXISTS channel_resource_id VARCHAR(255),
    ADD COLUMN IF NOT EXISTS channel_expires_at  TIMESTAMPTZ;

COMMENT ON COLUMN connector_conn.channel_id IS
    'Drive changes.watch 채널 id(우리가 만든 UUID). 알림이 오면 이 값으로 연결을 찾는다. '
    'NULL 이면 아직 채널을 안 열었다는 뜻이고, 그때는 대화 시작 시 동기화가 받친다.';

COMMENT ON COLUMN connector_conn.channel_resource_id IS
    'Google 이 채널을 열어 주며 준 resourceId. channels.stop 에 id 와 함께 필요하다 — '
    '이 값이 없으면 채널을 멈출 수 없어 만료될 때까지 알림이 계속 온다.';

COMMENT ON COLUMN connector_conn.channel_expires_at IS
    '채널 만료 시각. Drive 의 changes 채널은 최대 1주이고 자동 갱신이 없다. '
    '갱신 작업이 이 시각을 보고 만료 전에 새 채널을 연다.';

-- 알림은 채널 id 하나만 들고 온다. 그것으로 연결을 찾는 것이 이 표를 읽는
-- 가장 잦은 경로가 된다.
CREATE UNIQUE INDEX IF NOT EXISTS ux_connector_conn_channel
    ON connector_conn (channel_id) WHERE channel_id IS NOT NULL;

COMMIT;


-- =====================================================================
-- 확인용 — COMMIT 뒤에 따로 실행
-- =====================================================================
-- SELECT column_name, data_type, is_nullable FROM information_schema.columns
--  WHERE table_name = 'connector_conn'
--    AND column_name IN ('channel_id', 'channel_resource_id', 'channel_expires_at');
--
-- 기존 행은 전부 NULL 이어야 한다(= 아직 채널을 안 열었다).
-- SELECT connector_type,
--        count(*) FILTER (WHERE channel_id IS NULL)     AS 채널없음,
--        count(*) FILTER (WHERE channel_id IS NOT NULL) AS 채널있음
--   FROM connector_conn GROUP BY connector_type;
