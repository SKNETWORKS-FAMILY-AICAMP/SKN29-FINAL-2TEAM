-- 도구가 만든 파일(`source_type='GENERATED'`)을 「내 파일」에 자동으로 남기지 않고,
-- 사용자가 채팅에서 「내 파일에 저장」을 눌러야 남게 한다(2026-08-28).
--
-- `kept=false` 인 생성물은 채팅 카드로는 내려받을 수 있지만 라이브러리 목록·문서
-- 검색 목록에는 안 뜬다. 저장을 누르면 true 가 된다. 올린 파일·팀 문서는 기본값
-- true 라 영향이 없다.
BEGIN;

ALTER TABLE doc ADD COLUMN IF NOT EXISTS kept BOOLEAN NOT NULL DEFAULT true;

-- 이 마이그레이션 전에 만들어져 이미 목록에 노출된 생성물은 그대로 둔다(회수하면
-- 사용자가 저장해 둔 것처럼 쓰던 파일이 갑자기 사라진다). 앞으로 만들어지는
-- 생성물만 `create_generated()` 가 false 로 넣는다.
UPDATE doc SET kept = true WHERE source_type = 'GENERATED' AND kept = false;

COMMIT;
