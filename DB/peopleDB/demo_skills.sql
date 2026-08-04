-- ============================================================
-- 팀장 자리(PX002)의 보유 스킬
--
-- 왜 필요한가:
--   peopledb_mock.sql은 55명에게 스킬을 넣었는데 PX002만 빠졌다. 그 자리가
--   team_overrides.sql에서 실제 팀장으로 바뀌므로, 로그인해서 「내 프로필 →
--   보유 스킬」을 열면 본인만 비어 보인다. 목업 데이터의 결손이지 의도가 아니다.
--
--   이 파일에는 실명·실이메일이 없어 커밋한다(team_overrides.sql과 다르다).
--   자리(person_id)에 스킬을 매다는 것이라 누가 그 자리에 앉든 그대로 쓰인다.
--
-- 실행 순서: schema.sql → peopledb_mock.sql → team_overrides.sql → 이 파일
-- 여러 번 실행해도 안전하다.
--
-- 출처(source)를 네 가지로 섞은 것은 의도적이다. 인사가 등록한 것과 AI가
-- 추정한 것은 신뢰도가 달라서 화면이 다른 배지로 보여주는데, 한 종류만 있으면
-- 그 구분이 시연되지 않는다. confidence는 AI 추정에만 값이 있다 —
-- 확인된 스킬을 1.0으로 채우면 추정한 것과 같아 보인다.
-- ============================================================

INSERT INTO mock_hr.person_skill (person_id, skill_id, proficiency, source, confidence) VALUES
    ('PX002', 'S010', 5, 'HR',          NULL),   -- Project Management
    ('PX002', 'S011', 5, 'HR',          NULL),   -- Agile
    ('PX002', 'S001', 3, 'RESUME',      NULL),   -- Python
    ('PX002', 'S005', 3, 'HR',          NULL),   -- SQL
    ('PX002', 'S003', 3, 'USER_ADDED',  NULL),   -- React
    ('PX002', 'S006', 1, 'AI_INFERRED', 0.620)   -- AWS
ON CONFLICT (person_id, skill_id) DO NOTHING;


-- ============================================================
-- 확인용
-- ============================================================
-- SELECT s.name, ps.proficiency, ps.source, ps.confidence
--   FROM mock_hr.person_skill ps
--   JOIN mock_hr.skill s ON s.skill_id = ps.skill_id
--  WHERE ps.person_id = 'PX002'
--  ORDER BY ps.proficiency DESC, s.name;
