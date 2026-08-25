-- =====================================================================
-- 가드레일 정책(sys_setting) + 발동 기록(guardrail_event) 추가 (2026-08-20)
--
-- 정본: docs/설계 및 구현/중간발표 이후/작업기록/2026-08-20_가드레일_조사와_실측.md
--
-- 멘토링 §16(watsonx Orchestrate 벤치마크)이 Guardrail을 Agent Builder·
-- Role & Permission·Analytics와 **같은 층위의 플랫폼 기능**으로 적었고,
-- §17이 "여력이 있다면 **보여줄 것**"으로 분류했다. 즉 코드에 박아 두는
-- 안전장치가 아니라 운영자가 화면에서 정하는 정책이다.
--
-- 새 테이블을 정책용으로 만들지 않는다 — 초대 만료 기간이 이미 같은 길을
-- 갔다(`MemberInviteRepository.INVITE_TTL_DAYS` 하드코딩 → `sys_setting`의
-- `INVITE_EXPIRE_DAYS`). Repository·감사로그·화면 패턴을 그대로 쓴다.
--
-- **키를 항목별로 쪼개지 않고 JSON 한 벌로 둔다.** 항목별로 나누면 변경
-- 이력이 `audit_log`에 흩어져 "그 시점의 정책 한 벌"을 복원할 수 없다.
-- 하나의 행을 FOR UPDATE로 잠그고 한 번에 저장하면 이력도 한 줄로 남는다.
--
-- 기본값의 근거(위 문서 §4-1 실측):
--   pii.enabled=true      — 지금 `mask_sensitive()`가 이미 무조건 도는 것과
--                           동작이 같다. 기본값이 현행 동작을 안 바꾼다.
--   moderation.enabled=false — 아직 배선 전이고, 켜면 외부 호출이 매 턴
--                           늘어난다. 켜는 건 운영자의 판단이어야 한다.
--   thresholds=0.7        — 실측에서 업무 관용표현("팀 전체가 죽는다")이
--                           violence 0.425에 걸렸고 OpenAI 기본 판정은
--                           그걸 차단으로 봤다. 0.7이면 그 오탐은 빠지고
--                           실제 사례(한국어 괴롭힘 0.879·폭력 0.766·
--                           자해 0.987)는 잡힌다.
-- =====================================================================

BEGIN;

INSERT INTO sys_setting (setting_key, setting_value)
VALUES (
    'GUARDRAIL_POLICY',
    '{"pii": {"enabled": true, "strategy": "redact"},
      "moderation": {"enabled": false,
                     "thresholds": {"harassment": 0.7, "hate": 0.7, "sexual": 0.7,
                                    "self_harm": 0.7, "violence": 0.7, "illicit": 0.7}},
      "blocked_words": []}'
)
ON CONFLICT (setting_key) DO NOTHING;

-- 가드레일이 실제로 발동한 기록. `audit_log`를 쓰지 않는다 —
-- `audit_log.actor_account_id`가 NOT NULL인데 가드레일을 발동시키는 것은
-- 사람이 아니라 런타임이다.
--
-- **원문을 저장하지 않는다.** 가려진 값이 로그에 남으면 가드레일을 두는
-- 의미가 없다(`tool_call.input_summary`와 같은 원칙). `detail`에는 건수·
-- 카테고리·점수처럼 튜닝에 필요한 것만 넣는다.
CREATE TABLE IF NOT EXISTS guardrail_event (
    event_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id       UUID,                    -- agent_run.run_id(FK 없음). 입력 검사처럼 run 밖에서 나면 NULL
    session_id   UUID,                    -- chat_session.session_id(FK 없음)
    account_id   VARCHAR(5),              -- user_account.account_id(FK 없음)
    team_id      VARCHAR(5),              -- team.team_id(FK 없음)
    stage        VARCHAR(20)  NOT NULL,   -- INPUT / OUTPUT / TOOL_RESULT
    rule         VARCHAR(30)  NOT NULL,   -- PII / MODERATION / BLOCKED_WORD
    action       VARCHAR(20)  NOT NULL,   -- MASKED / BLOCKED
    detail       JSONB,                   -- 원문 없이 요약만(건수·카테고리·점수)
    occurred_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_guardrail_event_occurred
    ON guardrail_event (occurred_at DESC);

COMMIT;

-- =====================================================================
-- 확인용 — COMMIT 뒤에 따로 실행
-- =====================================================================
-- SELECT setting_value FROM sys_setting WHERE setting_key = 'GUARDRAIL_POLICY';
-- SELECT to_regclass('public.guardrail_event');
