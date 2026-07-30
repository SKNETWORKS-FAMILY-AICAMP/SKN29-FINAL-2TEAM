-- ============================================================
-- 팀 계정 오버라이드 (템플릿)
--
-- peopledb_mock.sql의 목업 인물 중 몇 자리를 실제 팀원으로 바꾼다.
-- 비밀번호 재설정 메일이 실제로 도착하려면 person.email이 살아 있는
-- 주소여야 하는데, 목업은 전부 존재하지 않는 @halil.com이라서 필요하다.
--
-- 실제 이름·이메일이 담긴 team_overrides.sql은 .gitignore 대상이다.
-- .env와 같은 방식으로 팀 내부에서만 공유할 것.
--
-- 실행 순서: schema.sql → peopledb_mock.sql → team_overrides.sql
--
-- 주의: 직접 가입한 팀장의 HR 본인 매핑은 People DB 커넥터 연결 시
-- 단순 문자열 비교(lower)로 수행한다. 여기 적은 주소와 가입 화면에
-- 입력한 주소가 정확히 같아야 SELF_EMAIL 매핑을 만들 수 있다.
-- Gmail은 점을 무시하지만 이 비교는 무시하지 않는다
-- (foo.bar@gmail.com ≠ foobar@gmail.com).
-- 역할은 이메일이나 org.mgr_id가 아니라 가입 경로로 판정한다.
-- 초대 코드 가입(TEAM_INVITATION)만 팀원이고 직접 가입은 팀장이다.
--
-- 업무 분배는 같은 팀 안에서 이뤄지므로 실제 팀원은 한 조직에 모아 둔다.
--
-- 자리를 고를 때 참고할 조직 구조(peopledb_mock.sql 기준):
--   A001 HALIL테크 (mgr_id 없음)
--     A002 개발팀        mgr_id=PX002  ← 하위에 A003·A004가 있어 초대 범위 시연에 적합
--       A003 백엔드파트   mgr_id=PB001
--       A004 프론트엔드파트 mgr_id=PF001
--     A005 기획팀 / A006 디자인팀 / A007 QA팀 / A008 마케팅팀
--
-- 목업 인물을 다른 조직으로 옮겼다면, 그 사람이 원래 조직의 mgr_id였는지
-- 확인하고 남은 인원에게 넘겨야 한다(조직 밖을 가리키는 mgr_id 방지).
-- ============================================================

-- 팀장(초대를 발급하는 쪽) — 초대 코드 없이 직접 가입한 뒤 People DB에서
-- 이 이메일로 본인 확인(SELF_EMAIL)을 완료해야 초대 범위가 열린다.
UPDATE person SET name = '팀장이름', email = 'leader@example.com',
                  org_id = 'A002', job_role = '팀장', level_id = 'L6'
WHERE person_id = 'PX002';

-- 팀원(초대를 받는 쪽) — 같은 조직으로 옮긴다.
UPDATE person SET name = '팀원이름', email = 'member@example.com',
                  org_id = 'A002', job_role = '사원', level_id = 'L1'
WHERE person_id = 'PB002';

-- 팀원이 원래 조직의 조직장이었다면 남은 인원에게 넘긴다.
-- UPDATE org SET mgr_id = 'PB003' WHERE org_id = 'A003';

-- 적용 결과 확인
SELECT p.person_id, p.name, p.email, o.name AS org_name, p.job_role,
       (o2.org_id IS NOT NULL) AS is_manager
FROM person AS p
LEFT JOIN org AS o ON o.org_id = p.org_id
LEFT JOIN org AS o2 ON o2.mgr_id = p.person_id
WHERE p.email NOT LIKE '%@halil.com'
ORDER BY p.person_id;
