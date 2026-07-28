-- ============================================================
-- People DB Mock Schema v13
-- HALIL팀 2팀 - DB halil 기준
--
-- 테이블명/컬럼명은 표준 축약어 위주로 짧게 썼다(글로서리는 peopleHR.md
-- 참고). 단, 축약이 모호해질 수 있는 이름(proficiency/confidence 등)은
-- 그대로 뒀다.
-- PK는 전부 테이블별 고정 접두사 + 일련번호(VARCHAR(5) 내외)다:
--   org=A001~, level=L1~L8, skill=S001~, sched=W001~, absence=B001~,
--   link=I001~.
-- person만 예외로 "P + 팀문자 + 3자리 일련번호" 형식이다(예: PB001 =
-- 백엔드파트 1번). 팀문자: X=경영진(회사/개발본부), B=백엔드, F=프론트엔드,
-- N=기획, D=디자인, Q=QA, M=마케팅. 사람이 늘어나도 팀별로 번호가 묶여서
-- 어느 팀 소속인지 id만 보고 바로 알 수 있다.
-- REFERENCES(실제 FK 제약)는 걸려있지 않다. 관계는 컬럼명과 주석으로만
-- 표시하고, DB 레벨 참조무결성 검사는 하지 않는다 -- 삽입/삭제 순서
-- 제약 없이 자유롭게 다루기 위한 선택이다. 트레이드오프: 존재하지 않는
-- id를 참조 컬럼에 넣어도 DB가 막지 못한다 (자세한 설명은 peopleHR.md).
-- ============================================================

DROP TABLE IF EXISTS link;
DROP TABLE IF EXISTS absence;
DROP TABLE IF EXISTS sched;
DROP TABLE IF EXISTS person_skill;
DROP TABLE IF EXISTS skill;
DROP TABLE IF EXISTS person;
DROP TABLE IF EXISTS level;
DROP TABLE IF EXISTS org;

-- ------------------------------------------------------------
-- 1. org  (up_org_id/mgr_id: FK 아님, 설계상 참조만 표시)
-- ------------------------------------------------------------
CREATE TABLE org (
    org_id        VARCHAR(5) PRIMARY KEY,           -- A001, A002 ...
    org_type      VARCHAR(20) NOT NULL
        CHECK (org_type IN ('COMPANY','DEPARTMENT','COST_CENTER','SUPERVISORY')),
    name          VARCHAR(100) NOT NULL,
    up_org_id     VARCHAR(5),                        -- org.org_id 참조(설계상, FK 없음)
    mgr_id        VARCHAR(5),                        -- person.person_id 참조(설계상, FK 없음)
    status        VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    created_at    TIMESTAMP DEFAULT now()
);

-- ------------------------------------------------------------
-- 2. level  (level_id 자체가 L1~L8 코드라 code와 값이 겹침 -- 의도된 중복)
-- ------------------------------------------------------------
CREATE TABLE level (
    level_id     VARCHAR(5) PRIMARY KEY,             -- L1 ~ L8
    code         VARCHAR(20) NOT NULL UNIQUE,
    name         VARCHAR(50) NOT NULL,
    rank_ord     INT NOT NULL,
    status       VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'
);

-- ------------------------------------------------------------
-- 3. person  (org_id/level_id: FK 아님, 설계상 참조만 표시)
-- emp_status는 ACTIVE/TERMINATED만 사용한다. 휴직/안식월 같은
-- 일시적 상태는 absence의 날짜 범위로 표현한다.
-- ------------------------------------------------------------
CREATE TABLE person (
    person_id       VARCHAR(5) PRIMARY KEY,          -- PX001(대표이사) ~ (팀문자별 3자리 일련번호)
    emp_id          VARCHAR(20) NOT NULL UNIQUE,
    name            VARCHAR(100) NOT NULL,
    email           VARCHAR(150) NOT NULL,
    phone           VARCHAR(30),
    job_role        VARCHAR(100),
    org_id          VARCHAR(5),                      -- org.org_id 참조(설계상, FK 없음)
    level_id        VARCHAR(5),                      -- level.level_id 참조(설계상, FK 없음)
    is_mgr          BOOLEAN DEFAULT false,
    loc             VARCHAR(100),
    wk_type         VARCHAR(30),                      -- Employee/Contingent (Workday 원본 enum 값 그대로)
    emp_status      VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'
        CHECK (emp_status IN ('ACTIVE','TERMINATED')),
    yos             INT,                               -- years of service. Workday가 계산 제공, 재계산 안 함
    wd_worker_id    VARCHAR(30),                       -- Workday 원본 worker id 참조용 (person_id를 대체하지 않음)
    created_at      TIMESTAMP DEFAULT now()
);

-- ------------------------------------------------------------
-- 4. skill / person_skill  (person_skill의 person_id/skill_id: FK 아님, 설계상 참조만 표시)
-- ------------------------------------------------------------
CREATE TABLE skill (
    skill_id     VARCHAR(5) PRIMARY KEY,             -- S001 ~
    name         VARCHAR(50) NOT NULL UNIQUE,
    category     VARCHAR(30),                         -- 자유 텍스트 (CHECK 미적용, v8에서 되돌림)
    descr        TEXT,                                -- 스킬 설명(임베딩 매칭용, v9 추가)
    status       VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'
);

CREATE TABLE person_skill (
    person_id        VARCHAR(5),                      -- person.person_id 참조(설계상, FK 없음)
    skill_id         VARCHAR(5),                      -- skill.skill_id 참조(설계상, FK 없음)
    proficiency      VARCHAR(20),
    source           VARCHAR(20)
        CHECK (source IN ('HR','RESUME','AI_INFERRED','USER_ADDED')),
    verify_status    VARCHAR(20) NOT NULL DEFAULT 'UNKNOWN'
        CHECK (verify_status IN ('VERIFIED','SELF_REPORTED','UNKNOWN')),
    confidence       NUMERIC(5,4),
    verified_at      TIMESTAMP,
    PRIMARY KEY (person_id, skill_id)
);

-- ------------------------------------------------------------
-- 5. sched  (person_id: FK 아님, 설계상 참조만 표시)
-- ------------------------------------------------------------
CREATE TABLE sched (
    sched_id        VARCHAR(5) PRIMARY KEY,           -- W001 ~
    person_id       VARCHAR(5),                       -- person.person_id 참조(설계상, FK 없음)
    wk_hours        DECIMAL(5,2) NOT NULL,             -- 실제 주당 근무시간 (Workday scheduled_Weekly_Hours 대응)
    def_wk_hours    DECIMAL(5,2) NOT NULL,             -- 포지션 기준 주당 근무시간 (Workday default_Weekly_Hours 대응)
    fte             DECIMAL(3,2) NOT NULL,             -- FTE 비율(0~1). Workday는 percentage(0~100) 반환
    tz              VARCHAR(50) NOT NULL DEFAULT 'Asia/Seoul',
    eff_from        DATE NOT NULL,
    eff_to          DATE
);

-- ------------------------------------------------------------
-- 6. absence  (person_id: FK 아님, 설계상 참조만 표시)
-- ------------------------------------------------------------
CREATE TABLE absence (
    absence_id      VARCHAR(5) PRIMARY KEY,           -- B001 ~
    person_id       VARCHAR(5),                       -- person.person_id 참조(설계상, FK 없음)
    absence_type    VARCHAR(30) NOT NULL,
    start_at        DATE NOT NULL,
    end_at          DATE NOT NULL,
    status          VARCHAR(20) DEFAULT 'APPROVED'
);

-- ------------------------------------------------------------
-- 7. link  (person_id: FK 아님, 설계상 참조만 표시)
-- 마이페이지에서 본인이 Jira/Google 이메일을 직접 등록하는 방식.
-- HR 이메일은 person.email에 이미 있으므로 여기 포함하지 않음.
-- ------------------------------------------------------------
CREATE TABLE link (
    link_id         VARCHAR(5) PRIMARY KEY,           -- I001 ~
    person_id       VARCHAR(5),                       -- person.person_id 참조(설계상, FK 없음)
    sys_type        VARCHAR(20) NOT NULL CHECK (sys_type IN ('JIRA','GOOGLE')),
    ext_email       VARCHAR(150) NOT NULL,
    reg_at          TIMESTAMP DEFAULT now(),
    UNIQUE (sys_type, ext_email),
    UNIQUE (person_id, sys_type)
);


-- ============================================================
-- 목업 데이터
-- ============================================================

-- 1. org -------------------------------------------
INSERT INTO org (org_id, org_type, name, up_org_id, mgr_id) VALUES
('A001', 'COMPANY', 'HALIL테크', NULL, NULL),
('A002', 'DEPARTMENT', '개발팀', 'A001', 'PX002'),
('A003', 'SUPERVISORY', '백엔드파트', 'A002', 'PB001'),
('A004', 'SUPERVISORY', '프론트엔드파트', 'A002', 'PF001'),
('A005', 'DEPARTMENT', '기획팀', 'A001', 'PN001'),
('A006', 'DEPARTMENT', '디자인팀', 'A001', 'PD001'),
('A007', 'DEPARTMENT', 'QA팀', 'A001', 'PQ001'),
('A008', 'DEPARTMENT', '마케팅팀', 'A001', 'PM001'),
('A009', 'COST_CENTER', 'R&D비용센터', 'A001', NULL);

-- 2. level -------------------------------------
INSERT INTO level (level_id, code, name, rank_ord) VALUES
('L1', 'L1', '사원', 1),
('L2', 'L2', '주임', 2),
('L3', 'L3', '대리', 3),
('L4', 'L4', '과장', 4),
('L5', 'L5', '차장', 5),
('L6', 'L6', '부장', 6),
('L7', 'L7', '이사', 7),
('L8', 'L8', '대표이사', 8);

-- 3. person -----------------------------------------------------
INSERT INTO person (person_id, emp_id, name, email, phone, job_role,
                    org_id, level_id, is_mgr, loc,
                    wk_type, emp_status, yos, wd_worker_id) VALUES
('PX001', 'EMP001', '최서연', 'user001@halil.com', '010-1158-2832', '대표이사', 'A001', 'L8', true, '서울', 'Employee', 'ACTIVE', 11, 'WD-10001'),
('PX002', 'EMP002', '윤수아', 'user002@halil.com', '010-2232-3442', '본부장', 'A002', 'L6', true, '서울', 'Employee', 'ACTIVE', 11, 'WD-10002'),
('PB001', 'EMP003', '박승우', 'user003@halil.com', '010-9938-1590', '팀장', 'A003', 'L6', true, '서울', 'Employee', 'ACTIVE', 0, 'WD-10003'),
('PB002', 'EMP004', '윤유진', 'user004@halil.com', '010-7049-3426', '사원', 'A003', 'L1', false, '서울', 'Employee', 'ACTIVE', 8, 'WD-10004'),
('PB003', 'EMP005', '윤수빈', 'user005@halil.com', '010-8041-3088', '대리', 'A003', 'L3', false, '서울', 'Employee', 'ACTIVE', 12, 'WD-10005'),
('PB004', 'EMP006', '한준서', 'user006@halil.com', '010-1685-6050', '주임', 'A003', 'L2', false, '서울', 'Employee', 'ACTIVE', 3, 'WD-10006'),
('PB005', 'EMP007', '서지호', 'user007@halil.com', '010-6974-1653', '대리', 'A003', 'L3', false, '부산(원격)', 'Employee', 'ACTIVE', 5, 'WD-10007'),
('PB006', 'EMP008', '권다인', 'user008@halil.com', '010-6862-4441', '사원', 'A003', 'L1', false, '서울', 'Employee', 'ACTIVE', 6, 'WD-10008'),
('PB007', 'EMP009', '홍태희', 'user009@halil.com', '010-5088-2684', '대리', 'A003', 'L3', false, '서울', 'Employee', 'ACTIVE', 9, 'WD-10009'),
('PB008', 'EMP010', '윤현준', 'user010@halil.com', '010-6794-7658', '대리', 'A003', 'L3', false, '서울', 'Employee', 'ACTIVE', 1, 'WD-10010'),
('PB009', 'EMP011', '장동현', 'user011@halil.com', '010-3532-4878', '대리', 'A003', 'L3', false, '서울', 'Employee', 'ACTIVE', 2, 'WD-10011'),
('PF001', 'EMP012', '조재원', 'user012@halil.com', '010-3662-3900', '팀장', 'A004', 'L6', true, '경기(원격)', 'Employee', 'ACTIVE', 11, 'WD-10012'),
('PF002', 'EMP013', '송지원', 'user013@halil.com', '010-7755-1406', '주임', 'A004', 'L2', false, '서울', 'Employee', 'ACTIVE', 2, 'WD-10013'),
('PF003', 'EMP014', '송다은', 'user014@halil.com', '010-3938-6442', '대리', 'A004', 'L3', false, '서울', 'Employee', 'ACTIVE', 12, 'WD-10014'),
('PF004', 'EMP015', '한연우', 'user015@halil.com', '010-7745-5065', '대리', 'A004', 'L3', false, '서울', 'Contingent', 'ACTIVE', 1, 'WD-10015'),
('PF005', 'EMP016', '조시온', 'user016@halil.com', '010-5371-3608', '과장', 'A004', 'L4', false, '경기(원격)', 'Employee', 'ACTIVE', 6, 'WD-10016'),
('PF006', 'EMP017', '장수아', 'user017@halil.com', '010-2771-7267', '주임', 'A004', 'L2', false, '부산(원격)', 'Employee', 'ACTIVE', 11, 'WD-10017'),
('PF007', 'EMP018', '전서윤', 'user018@halil.com', '010-1634-8711', '과장', 'A004', 'L4', false, '서울', 'Employee', 'ACTIVE', 5, 'WD-10018'),
('PF008', 'EMP019', '황주원', 'user019@halil.com', '010-4644-4269', '사원', 'A004', 'L1', false, '서울', 'Employee', 'ACTIVE', 1, 'WD-10019'),
('PN001', 'EMP020', '신채원', 'user020@halil.com', '010-8541-6728', '팀장', 'A005', 'L5', true, '서울', 'Contingent', 'ACTIVE', 6, 'WD-10020'),
('PN002', 'EMP021', '안윤서', 'user021@halil.com', '010-6000-4728', '사원', 'A005', 'L1', false, '경기(원격)', 'Employee', 'ACTIVE', 10, 'WD-10021'),
('PN003', 'EMP022', '한예은', 'user022@halil.com', '010-4652-1387', '대리', 'A005', 'L3', false, '서울', 'Employee', 'ACTIVE', 6, 'WD-10022'),
('PN004', 'EMP023', '장유진', 'user023@halil.com', '010-4164-7528', '주임', 'A005', 'L2', false, '서울', 'Employee', 'ACTIVE', 8, 'WD-10023'),
('PN005', 'EMP024', '홍민서', 'user024@halil.com', '010-6378-5564', '주임', 'A005', 'L2', false, '서울', 'Employee', 'ACTIVE', 5, 'WD-10024'),
('PN006', 'EMP025', '김채원', 'user025@halil.com', '010-2137-5573', '대리', 'A005', 'L3', false, '서울', 'Employee', 'ACTIVE', 7, 'WD-10025'),
('PN007', 'EMP026', '임지우', 'user026@halil.com', '010-6753-9346', '사원', 'A005', 'L1', false, '부산(원격)', 'Employee', 'ACTIVE', 3, 'WD-10026'),
('PN008', 'EMP027', '황우빈', 'user027@halil.com', '010-7548-9785', '사원', 'A005', 'L1', false, '부산(원격)', 'Employee', 'ACTIVE', 12, 'WD-10027'),
('PN009', 'EMP028', '황현서', 'user028@halil.com', '010-6425-1452', '주임', 'A005', 'L2', false, '부산(원격)', 'Contingent', 'ACTIVE', 4, 'WD-10028'),
('PN010', 'EMP029', '조경민', 'user029@halil.com', '010-2889-5279', '주임', 'A005', 'L2', false, '서울', 'Employee', 'ACTIVE', 11, 'WD-10029'),
('PD001', 'EMP030', '오수빈', 'user030@halil.com', '010-3925-5349', '팀장', 'A006', 'L6', true, '서울', 'Employee', 'ACTIVE', 1, 'WD-10030'),
('PD002', 'EMP031', '한서연', 'user031@halil.com', '010-1626-2776', '주임', 'A006', 'L2', false, '서울', 'Employee', 'ACTIVE', 9, 'WD-10031'),
('PD003', 'EMP032', '이다은', 'user032@halil.com', '010-8119-6663', '사원', 'A006', 'L1', false, '서울', 'Employee', 'ACTIVE', 0, 'WD-10032'),
('PD004', 'EMP033', '윤준서', 'user033@halil.com', '010-6139-8149', '과장', 'A006', 'L4', false, '부산(원격)', 'Employee', 'ACTIVE', 3, 'WD-10033'),
('PD005', 'EMP034', '윤소민', 'user034@halil.com', '010-9379-2894', '과장', 'A006', 'L4', false, '서울', 'Employee', 'ACTIVE', 12, 'WD-10034'),
('PD006', 'EMP035', '최재원', 'user035@halil.com', '010-7311-4114', '과장', 'A006', 'L4', false, '서울', 'Employee', 'ACTIVE', 5, 'WD-10035'),
('PD007', 'EMP036', '이혜원', 'user036@halil.com', '010-5173-1727', '사원', 'A006', 'L1', false, '서울', 'Employee', 'ACTIVE', 0, 'WD-10036'),
('PD008', 'EMP037', '윤민서', 'user037@halil.com', '010-8144-1027', '주임', 'A006', 'L2', false, '서울', 'Employee', 'ACTIVE', 8, 'WD-10037'),
('PQ001', 'EMP038', '신서준', 'user038@halil.com', '010-9518-9821', '팀장', 'A007', 'L6', true, '서울', 'Employee', 'ACTIVE', 7, 'WD-10038'),
('PQ002', 'EMP039', '송지호', 'user039@halil.com', '010-4228-6967', '사원', 'A007', 'L1', false, '부산(원격)', 'Employee', 'ACTIVE', 10, 'WD-10039'),
('PQ003', 'EMP040', '윤은우', 'user040@halil.com', '010-8066-2146', '과장', 'A007', 'L4', false, '서울', 'Employee', 'ACTIVE', 7, 'WD-10040'),
('PQ004', 'EMP041', '이은우', 'user041@halil.com', '010-6409-6143', '과장', 'A007', 'L4', false, '서울', 'Employee', 'ACTIVE', 0, 'WD-10041'),
('PQ005', 'EMP042', '임서윤', 'user042@halil.com', '010-3041-5920', '과장', 'A007', 'L4', false, '서울', 'Employee', 'ACTIVE', 2, 'WD-10042'),
('PQ006', 'EMP043', '이승우', 'user043@halil.com', '010-9308-6067', '사원', 'A007', 'L1', false, '서울', 'Employee', 'ACTIVE', 11, 'WD-10043'),
('PQ007', 'EMP044', '전가은', 'user044@halil.com', '010-7691-6344', '주임', 'A007', 'L2', false, '부산(원격)', 'Employee', 'ACTIVE', 0, 'WD-10044'),
('PQ008', 'EMP045', '박채원', 'user045@halil.com', '010-7592-5844', '사원', 'A007', 'L1', false, '서울', 'Employee', 'ACTIVE', 10, 'WD-10045'),
('PQ009', 'EMP046', '전지우', 'user046@halil.com', '010-3085-4143', '사원', 'A007', 'L1', false, '서울', 'Employee', 'ACTIVE', 9, 'WD-10046'),
('PM001', 'EMP047', '전지안', 'user047@halil.com', '010-7888-7211', '팀장', 'A008', 'L6', true, '서울', 'Employee', 'ACTIVE', 4, 'WD-10047'),
('PM002', 'EMP048', '장연우', 'user048@halil.com', '010-3851-5930', '주임', 'A008', 'L2', false, '경기(원격)', 'Employee', 'ACTIVE', 10, 'WD-10048'),
('PM003', 'EMP049', '한경민', 'user049@halil.com', '010-7653-9977', '사원', 'A008', 'L1', false, '서울', 'Contingent', 'TERMINATED', 0, 'WD-10049'),
('PM004', 'EMP050', '박다인', 'user050@halil.com', '010-1006-5978', '주임', 'A008', 'L2', false, '서울', 'Employee', 'ACTIVE', 8, 'WD-10050'),
('PM005', 'EMP051', '박태희', 'user051@halil.com', '010-5700-4443', '주임', 'A008', 'L2', false, '서울', 'Employee', 'ACTIVE', 5, 'WD-10051'),
('PM006', 'EMP052', '송나윤', 'user052@halil.com', '010-8043-6279', '대리', 'A008', 'L3', false, '경기(원격)', 'Employee', 'ACTIVE', 9, 'WD-10052'),
('PM007', 'EMP053', '송예준', 'user053@halil.com', '010-8618-8238', '사원', 'A008', 'L1', false, '서울', 'Employee', 'ACTIVE', 2, 'WD-10053'),
('PM008', 'EMP054', '송지훈', 'user054@halil.com', '010-8244-4501', '대리', 'A008', 'L3', false, '부산(원격)', 'Employee', 'ACTIVE', 4, 'WD-10054'),
('PM009', 'EMP055', '조혜원', 'user055@halil.com', '010-9375-8752', '대리', 'A008', 'L3', false, '서울', 'Employee', 'ACTIVE', 8, 'WD-10055'),
('PM010', 'EMP056', '박은서', 'user056@halil.com', '010-3780-2389', '과장', 'A008', 'L4', false, '서울', 'Employee', 'ACTIVE', 4, 'WD-10056'),
('PM011', 'EMP057', '정은서', 'user057@halil.com', '010-5649-9445', '대리', 'A008', 'L3', false, '경기(원격)', 'Employee', 'ACTIVE', 2, 'WD-10057');

-- 4. skill / person_skill -----------------------------------
INSERT INTO skill (skill_id, name, category, descr) VALUES
('S001', 'Python', 'Technical', '범용 고급 프로그래밍 언어. 백엔드/데이터/자동화 스크립트에 광범위하게 사용.'),
('S002', 'Java', 'Technical', '객체지향 프로그래밍 언어. 엔터프라이즈 백엔드 시스템 개발에 사용.'),
('S003', 'React', 'Technical', 'UI 구축을 위한 자바스크립트 라이브러리. 프론트엔드 웹 개발에 사용.'),
('S004', 'Node.js', 'Technical', '자바스크립트 런타임. 서버사이드/API 개발에 사용.'),
('S005', 'SQL', 'Technical', '관계형 데이터베이스 질의 언어. 데이터 조회/조작에 사용.'),
('S006', 'AWS', 'Technical', '아마존 클라우드 컴퓨팅 플랫폼. 인프라 구축·운영에 사용.'),
('S007', 'Kubernetes', 'Technical', '컨테이너 오케스트레이션 플랫폼. 배포 자동화·스케일링에 사용.'),
('S008', 'Figma', 'Design', 'UI/UX 디자인 및 협업 툴. 화면 설계·프로토타이핑에 사용.'),
('S009', 'Sketch', 'Design', 'UI 디자인 툴. 화면 시안 제작에 사용.'),
('S010', 'Project Management', 'Management', '프로젝트 일정·범위·리소스를 계획하고 관리하는 역량.'),
('S011', 'Agile', 'Management', '반복적·점진적 개발 방법론(스크럼/칸반 등) 운영 역량.'),
('S012', 'SEO', 'Marketing', '검색엔진 최적화. 콘텐츠·웹사이트 노출도 향상에 사용.'),
('S013', 'Content Strategy', 'Marketing', '콘텐츠 기획 및 운영 전략 수립 역량.'),
('S014', 'QA Automation', 'Technical', '테스트 자동화 도구/프레임워크를 활용한 품질 검증 역량.');

INSERT INTO person_skill (person_id, skill_id, proficiency, source, verify_status, confidence, verified_at) VALUES
('PB001', 'S004', 'BEGINNER', 'HR', 'VERIFIED', 0.9818, '2026-06-01 09:00:00'),
('PB001', 'S007', 'BEGINNER', 'AI_INFERRED', 'UNKNOWN', 0.3562, '2026-02-01 09:00:00'),
('PB001', 'S005', 'INTERMEDIATE', 'HR', 'VERIFIED', 0.9046, '2026-05-01 09:00:00'),
('PB002', 'S006', 'ADVANCED', 'USER_ADDED', 'SELF_REPORTED', 0.8215, '2026-02-01 09:00:00'),
('PB003', 'S004', 'ADVANCED', 'USER_ADDED', 'SELF_REPORTED', 0.661, '2026-06-01 09:00:00'),
('PB003', 'S006', 'BEGINNER', 'HR', 'VERIFIED', 0.9893, '2026-04-01 09:00:00'),
('PB003', 'S007', 'ADVANCED', 'RESUME', 'SELF_REPORTED', 0.644, '2026-05-01 09:00:00'),
('PB004', 'S001', 'BEGINNER', 'RESUME', 'SELF_REPORTED', 0.8294, '2026-04-01 09:00:00'),
('PB004', 'S007', 'ADVANCED', 'RESUME', 'SELF_REPORTED', 0.8004, '2026-05-01 09:00:00'),
('PB005', 'S007', 'ADVANCED', 'USER_ADDED', 'SELF_REPORTED', 0.8076, '2026-04-01 09:00:00'),
('PB005', 'S005', 'INTERMEDIATE', 'RESUME', 'SELF_REPORTED', 0.7859, '2026-04-01 09:00:00'),
('PB005', 'S006', 'ADVANCED', 'AI_INFERRED', 'UNKNOWN', 0.4879, '2026-03-01 09:00:00'),
('PB006', 'S006', 'INTERMEDIATE', 'USER_ADDED', 'SELF_REPORTED', 0.6194, '2026-02-01 09:00:00'),
('PB006', 'S002', 'ADVANCED', 'AI_INFERRED', 'UNKNOWN', 0.384, '2026-01-01 09:00:00'),
('PB006', 'S005', 'INTERMEDIATE', 'RESUME', 'SELF_REPORTED', 0.6377, '2026-06-01 09:00:00'),
('PB007', 'S004', 'INTERMEDIATE', 'RESUME', 'SELF_REPORTED', 0.6161, '2026-03-01 09:00:00'),
('PB008', 'S006', 'INTERMEDIATE', 'RESUME', 'SELF_REPORTED', 0.8082, '2026-05-01 09:00:00'),
('PB008', 'S004', 'ADVANCED', 'HR', 'VERIFIED', 0.9857, '2026-04-01 09:00:00'),
('PB008', 'S001', 'INTERMEDIATE', 'USER_ADDED', 'SELF_REPORTED', 0.6015, '2026-03-01 09:00:00'),
('PB009', 'S006', 'INTERMEDIATE', 'RESUME', 'SELF_REPORTED', 0.7221, '2026-04-01 09:00:00'),
('PB009', 'S007', 'INTERMEDIATE', 'USER_ADDED', 'SELF_REPORTED', 0.6073, '2026-06-01 09:00:00'),
('PF001', 'S004', 'ADVANCED', 'RESUME', 'SELF_REPORTED', 0.8452, '2026-01-01 09:00:00'),
('PF001', 'S003', 'ADVANCED', 'USER_ADDED', 'SELF_REPORTED', 0.748, '2026-01-01 09:00:00'),
('PF001', 'S005', 'BEGINNER', 'HR', 'VERIFIED', 0.9643, '2026-04-01 09:00:00'),
('PF002', 'S003', 'BEGINNER', 'AI_INFERRED', 'UNKNOWN', 0.3948, '2026-04-01 09:00:00'),
('PF003', 'S004', 'INTERMEDIATE', 'AI_INFERRED', 'UNKNOWN', 0.488, '2026-03-01 09:00:00'),
('PF003', 'S005', 'ADVANCED', 'HR', 'VERIFIED', 0.947, '2026-05-01 09:00:00'),
('PF004', 'S004', 'ADVANCED', 'RESUME', 'SELF_REPORTED', 0.7625, '2026-01-01 09:00:00'),
('PF005', 'S003', 'ADVANCED', 'RESUME', 'SELF_REPORTED', 0.8098, '2026-02-01 09:00:00'),
('PF006', 'S003', 'ADVANCED', 'USER_ADDED', 'SELF_REPORTED', 0.7674, '2026-02-01 09:00:00'),
('PF007', 'S005', 'ADVANCED', 'AI_INFERRED', 'UNKNOWN', 0.3419, '2026-06-01 09:00:00'),
('PF007', 'S004', 'BEGINNER', 'HR', 'VERIFIED', 0.9778, '2026-03-01 09:00:00'),
('PF008', 'S005', 'ADVANCED', 'HR', 'VERIFIED', 0.9929, '2026-06-01 09:00:00'),
('PN001', 'S011', 'ADVANCED', 'HR', 'VERIFIED', 0.9592, '2026-02-01 09:00:00'),
('PN001', 'S010', 'INTERMEDIATE', 'HR', 'VERIFIED', 0.9697, '2026-06-01 09:00:00'),
('PN002', 'S010', 'BEGINNER', 'USER_ADDED', 'SELF_REPORTED', 0.7654, '2026-05-01 09:00:00'),
('PN002', 'S005', 'INTERMEDIATE', 'AI_INFERRED', 'UNKNOWN', 0.3032, '2026-04-01 09:00:00'),
('PN002', 'S011', 'INTERMEDIATE', 'HR', 'VERIFIED', 0.9434, '2026-06-01 09:00:00'),
('PN003', 'S005', 'ADVANCED', 'USER_ADDED', 'SELF_REPORTED', 0.644, '2026-06-01 09:00:00'),
('PN003', 'S010', 'ADVANCED', 'AI_INFERRED', 'UNKNOWN', 0.454, '2026-04-01 09:00:00'),
('PN004', 'S011', 'BEGINNER', 'AI_INFERRED', 'UNKNOWN', 0.5129, '2026-03-01 09:00:00'),
('PN004', 'S005', 'INTERMEDIATE', 'USER_ADDED', 'SELF_REPORTED', 0.661, '2026-05-01 09:00:00'),
('PN005', 'S005', 'INTERMEDIATE', 'HR', 'VERIFIED', 0.9494, '2026-02-01 09:00:00'),
('PN005', 'S011', 'INTERMEDIATE', 'USER_ADDED', 'SELF_REPORTED', 0.653, '2026-03-01 09:00:00'),
('PN005', 'S010', 'ADVANCED', 'AI_INFERRED', 'UNKNOWN', 0.5201, '2026-03-01 09:00:00'),
('PN006', 'S010', 'INTERMEDIATE', 'RESUME', 'SELF_REPORTED', 0.78, '2026-05-01 09:00:00'),
('PN006', 'S005', 'ADVANCED', 'RESUME', 'SELF_REPORTED', 0.7727, '2026-06-01 09:00:00'),
('PN006', 'S011', 'BEGINNER', 'USER_ADDED', 'SELF_REPORTED', 0.712, '2026-01-01 09:00:00'),
('PN007', 'S010', 'ADVANCED', 'RESUME', 'SELF_REPORTED', 0.6766, '2026-03-01 09:00:00'),
('PN007', 'S011', 'INTERMEDIATE', 'USER_ADDED', 'SELF_REPORTED', 0.7384, '2026-04-01 09:00:00'),
('PN008', 'S005', 'INTERMEDIATE', 'USER_ADDED', 'SELF_REPORTED', 0.6677, '2026-02-01 09:00:00'),
('PN008', 'S011', 'INTERMEDIATE', 'HR', 'VERIFIED', 0.9721, '2026-01-01 09:00:00'),
('PN008', 'S010', 'ADVANCED', 'RESUME', 'SELF_REPORTED', 0.6479, '2026-04-01 09:00:00'),
('PN009', 'S005', 'INTERMEDIATE', 'HR', 'VERIFIED', 0.9833, '2026-02-01 09:00:00'),
('PN009', 'S011', 'BEGINNER', 'AI_INFERRED', 'UNKNOWN', 0.3449, '2026-06-01 09:00:00'),
('PN010', 'S010', 'ADVANCED', 'HR', 'VERIFIED', 0.9553, '2026-02-01 09:00:00'),
('PN010', 'S011', 'BEGINNER', 'USER_ADDED', 'SELF_REPORTED', 0.6256, '2026-05-01 09:00:00'),
('PN010', 'S005', 'INTERMEDIATE', 'AI_INFERRED', 'UNKNOWN', 0.4173, '2026-03-01 09:00:00'),
('PD001', 'S008', 'INTERMEDIATE', 'AI_INFERRED', 'UNKNOWN', 0.5353, '2026-01-01 09:00:00'),
('PD002', 'S009', 'ADVANCED', 'USER_ADDED', 'SELF_REPORTED', 0.6185, '2026-06-01 09:00:00'),
('PD003', 'S008', 'INTERMEDIATE', 'RESUME', 'SELF_REPORTED', 0.8028, '2026-01-01 09:00:00'),
('PD004', 'S008', 'ADVANCED', 'USER_ADDED', 'SELF_REPORTED', 0.7516, '2026-02-01 09:00:00'),
('PD005', 'S009', 'ADVANCED', 'USER_ADDED', 'SELF_REPORTED', 0.6743, '2026-04-01 09:00:00'),
('PD005', 'S008', 'BEGINNER', 'AI_INFERRED', 'UNKNOWN', 0.4422, '2026-05-01 09:00:00'),
('PD006', 'S008', 'BEGINNER', 'RESUME', 'SELF_REPORTED', 0.6662, '2026-02-01 09:00:00'),
('PD006', 'S009', 'BEGINNER', 'RESUME', 'SELF_REPORTED', 0.6435, '2026-02-01 09:00:00'),
('PD007', 'S009', 'INTERMEDIATE', 'USER_ADDED', 'SELF_REPORTED', 0.7723, '2026-03-01 09:00:00'),
('PD008', 'S008', 'ADVANCED', 'AI_INFERRED', 'UNKNOWN', 0.4767, '2026-04-01 09:00:00'),
('PQ001', 'S011', 'ADVANCED', 'RESUME', 'SELF_REPORTED', 0.831, '2026-05-01 09:00:00'),
('PQ002', 'S014', 'INTERMEDIATE', 'RESUME', 'SELF_REPORTED', 0.7619, '2026-02-01 09:00:00'),
('PQ002', 'S005', 'INTERMEDIATE', 'HR', 'VERIFIED', 0.906, '2026-05-01 09:00:00'),
('PQ002', 'S011', 'INTERMEDIATE', 'AI_INFERRED', 'UNKNOWN', 0.4098, '2026-06-01 09:00:00'),
('PQ003', 'S011', 'INTERMEDIATE', 'AI_INFERRED', 'UNKNOWN', 0.4251, '2026-04-01 09:00:00'),
('PQ003', 'S005', 'INTERMEDIATE', 'HR', 'VERIFIED', 0.9598, '2026-06-01 09:00:00'),
('PQ004', 'S011', 'ADVANCED', 'HR', 'VERIFIED', 0.9091, '2026-05-01 09:00:00'),
('PQ004', 'S005', 'ADVANCED', 'HR', 'VERIFIED', 1.0, '2026-03-01 09:00:00'),
('PQ005', 'S014', 'BEGINNER', 'USER_ADDED', 'SELF_REPORTED', 0.829, '2026-05-01 09:00:00'),
('PQ005', 'S011', 'INTERMEDIATE', 'USER_ADDED', 'SELF_REPORTED', 0.7587, '2026-01-01 09:00:00'),
('PQ005', 'S005', 'INTERMEDIATE', 'USER_ADDED', 'SELF_REPORTED', 0.687, '2026-03-01 09:00:00'),
('PQ006', 'S014', 'INTERMEDIATE', 'USER_ADDED', 'SELF_REPORTED', 0.7734, '2026-06-01 09:00:00'),
('PQ006', 'S011', 'ADVANCED', 'USER_ADDED', 'SELF_REPORTED', 0.8034, '2026-01-01 09:00:00'),
('PQ006', 'S005', 'INTERMEDIATE', 'USER_ADDED', 'SELF_REPORTED', 0.622, '2026-03-01 09:00:00'),
('PQ007', 'S005', 'ADVANCED', 'HR', 'VERIFIED', 0.9658, '2026-04-01 09:00:00'),
('PQ008', 'S014', 'INTERMEDIATE', 'AI_INFERRED', 'UNKNOWN', 0.4557, '2026-06-01 09:00:00'),
('PQ008', 'S011', 'BEGINNER', 'USER_ADDED', 'SELF_REPORTED', 0.79, '2026-03-01 09:00:00'),
('PQ009', 'S014', 'ADVANCED', 'USER_ADDED', 'SELF_REPORTED', 0.6304, '2026-05-01 09:00:00'),
('PQ009', 'S005', 'INTERMEDIATE', 'RESUME', 'SELF_REPORTED', 0.7774, '2026-05-01 09:00:00'),
('PQ009', 'S011', 'BEGINNER', 'HR', 'VERIFIED', 0.9552, '2026-02-01 09:00:00'),
('PM001', 'S013', 'BEGINNER', 'HR', 'VERIFIED', 0.9648, '2026-04-01 09:00:00'),
('PM002', 'S013', 'BEGINNER', 'USER_ADDED', 'SELF_REPORTED', 0.8451, '2026-04-01 09:00:00'),
('PM002', 'S010', 'ADVANCED', 'RESUME', 'SELF_REPORTED', 0.6959, '2026-05-01 09:00:00'),
('PM002', 'S012', 'INTERMEDIATE', 'RESUME', 'SELF_REPORTED', 0.816, '2026-04-01 09:00:00'),
('PM003', 'S010', 'INTERMEDIATE', 'HR', 'VERIFIED', 0.9283, '2026-05-01 09:00:00'),
('PM003', 'S013', 'INTERMEDIATE', 'USER_ADDED', 'SELF_REPORTED', 0.8163, '2026-05-01 09:00:00'),
('PM004', 'S013', 'INTERMEDIATE', 'USER_ADDED', 'SELF_REPORTED', 0.7138, '2026-02-01 09:00:00'),
('PM004', 'S010', 'BEGINNER', 'RESUME', 'SELF_REPORTED', 0.7429, '2026-04-01 09:00:00'),
('PM005', 'S013', 'INTERMEDIATE', 'USER_ADDED', 'SELF_REPORTED', 0.7763, '2026-04-01 09:00:00'),
('PM006', 'S010', 'ADVANCED', 'HR', 'VERIFIED', 0.9126, '2026-03-01 09:00:00'),
('PM006', 'S012', 'INTERMEDIATE', 'HR', 'VERIFIED', 0.9874, '2026-01-01 09:00:00'),
('PM006', 'S013', 'BEGINNER', 'USER_ADDED', 'SELF_REPORTED', 0.6038, '2026-04-01 09:00:00'),
('PM007', 'S012', 'ADVANCED', 'AI_INFERRED', 'UNKNOWN', 0.3846, '2026-04-01 09:00:00'),
('PM007', 'S010', 'ADVANCED', 'HR', 'VERIFIED', 0.9852, '2026-05-01 09:00:00'),
('PM007', 'S013', 'ADVANCED', 'USER_ADDED', 'SELF_REPORTED', 0.8385, '2026-06-01 09:00:00'),
('PM008', 'S010', 'ADVANCED', 'HR', 'VERIFIED', 0.9235, '2026-03-01 09:00:00'),
('PM008', 'S012', 'INTERMEDIATE', 'RESUME', 'SELF_REPORTED', 0.7867, '2026-01-01 09:00:00'),
('PM009', 'S010', 'BEGINNER', 'RESUME', 'SELF_REPORTED', 0.7735, '2026-01-01 09:00:00'),
('PM009', 'S012', 'INTERMEDIATE', 'AI_INFERRED', 'UNKNOWN', 0.499, '2026-03-01 09:00:00'),
('PM009', 'S013', 'BEGINNER', 'AI_INFERRED', 'UNKNOWN', 0.4077, '2026-05-01 09:00:00'),
('PM010', 'S010', 'ADVANCED', 'RESUME', 'SELF_REPORTED', 0.6438, '2026-04-01 09:00:00'),
('PM010', 'S012', 'ADVANCED', 'RESUME', 'SELF_REPORTED', 0.7244, '2026-02-01 09:00:00'),
('PM011', 'S013', 'ADVANCED', 'AI_INFERRED', 'UNKNOWN', 0.4149, '2026-01-01 09:00:00');

-- 5. sched --------------------------------------------
INSERT INTO sched (sched_id, person_id, wk_hours, def_wk_hours, fte, tz, eff_from) VALUES
('W001', 'PX001', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W002', 'PX002', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W003', 'PB001', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W004', 'PB002', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W005', 'PB003', 20.00, 40.00, 0.50, 'Asia/Seoul', '2026-01-01'),
('W006', 'PB004', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W007', 'PB005', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W008', 'PB006', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W009', 'PB007', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W010', 'PB008', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W011', 'PB009', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W012', 'PF001', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W013', 'PF002', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W014', 'PF003', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W015', 'PF004', 20.00, 40.00, 0.50, 'Asia/Seoul', '2026-01-01'),
('W016', 'PF005', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W017', 'PF006', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W018', 'PF007', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W019', 'PF008', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W020', 'PN001', 20.00, 40.00, 0.50, 'Asia/Seoul', '2026-01-01'),
('W021', 'PN002', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W022', 'PN003', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W023', 'PN004', 20.00, 40.00, 0.50, 'Asia/Seoul', '2026-01-01'),
('W024', 'PN005', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W025', 'PN006', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W026', 'PN007', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W027', 'PN008', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W028', 'PN009', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W029', 'PN010', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W030', 'PD001', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W031', 'PD002', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W032', 'PD003', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W033', 'PD004', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W034', 'PD005', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W035', 'PD006', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W036', 'PD007', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W037', 'PD008', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W038', 'PQ001', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W039', 'PQ002', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W040', 'PQ003', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W041', 'PQ004', 20.00, 40.00, 0.50, 'Asia/Seoul', '2026-01-01'),
('W042', 'PQ005', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W043', 'PQ006', 20.00, 40.00, 0.50, 'Asia/Seoul', '2026-01-01'),
('W044', 'PQ007', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W045', 'PQ008', 20.00, 40.00, 0.50, 'Asia/Seoul', '2026-01-01'),
('W046', 'PQ009', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W047', 'PM001', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W048', 'PM002', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W049', 'PM003', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W050', 'PM004', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W051', 'PM005', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W052', 'PM006', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W053', 'PM007', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W054', 'PM008', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W055', 'PM009', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W056', 'PM010', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01'),
('W057', 'PM011', 40.00, 40.00, 1.00, 'Asia/Seoul', '2026-01-01');

-- 6. absence ------------------------------------------
INSERT INTO absence (absence_id, person_id, absence_type, start_at, end_at, status) VALUES
('B001', 'PB005', '육아휴직', '2026-06-01', '2026-12-31', 'APPROVED'),
('B002', 'PB006', '육아휴직', '2026-06-01', '2026-12-31', 'APPROVED'),
('B003', 'PB008', '육아휴직', '2026-06-01', '2026-12-31', 'APPROVED'),
('B004', 'PF004', '육아휴직', '2026-06-01', '2026-12-31', 'APPROVED'),
('B005', 'PN004', '육아휴직', '2026-06-01', '2026-12-31', 'APPROVED'),
('B006', 'PN008', '육아휴직', '2026-06-01', '2026-12-31', 'APPROVED'),
('B007', 'PD002', '육아휴직', '2026-06-01', '2026-12-31', 'APPROVED'),
('B008', 'PD003', '육아휴직', '2026-06-01', '2026-12-31', 'APPROVED'),
('B009', 'PD006', '안식월', '2026-07-15', '2026-08-15', 'APPROVED'),
('B010', 'PD008', '안식월', '2026-07-15', '2026-08-15', 'APPROVED'),
('B011', 'PQ003', '육아휴직', '2026-06-01', '2026-12-31', 'APPROVED'),
('B012', 'PQ007', '육아휴직', '2026-06-01', '2026-12-31', 'APPROVED'),
('B013', 'PQ009', '안식월', '2026-07-15', '2026-08-15', 'APPROVED'),
('B014', 'PM004', '안식월', '2026-07-15', '2026-08-15', 'APPROVED'),
('B015', 'PM007', '육아휴직', '2026-06-01', '2026-12-31', 'APPROVED'),
('B016', 'PM008', '안식월', '2026-07-15', '2026-08-15', 'APPROVED'),
('B017', 'PM010', '육아휴직', '2026-06-01', '2026-12-31', 'APPROVED'),
('B018', 'PM007', '연차', '2026-08-04', '2026-08-04', 'APPROVED'),
('B019', 'PD002', '연차', '2026-08-15', '2026-08-15', 'APPROVED'),
('B020', 'PM006', '연차', '2026-08-03', '2026-08-03', 'APPROVED'),
('B021', 'PF008', '연차', '2026-08-05', '2026-08-05', 'APPROVED'),
('B022', 'PM002', '연차', '2026-08-08', '2026-08-08', 'APPROVED'),
('B023', 'PN003', '연차', '2026-08-13', '2026-08-13', 'APPROVED');

-- 7. link (마이페이지에서 본인이 등록한 예시) -----------------
INSERT INTO link (link_id, person_id, sys_type, ext_email) VALUES
('I001', 'PM009', 'JIRA', 'user055@halil.com'),
('I002', 'PM006', 'JIRA', 'user052@halil.com'),
('I003', 'PD007', 'JIRA', 'user036@halil.com'),
('I004', 'PN005', 'JIRA', 'user024@halil.com'),
('I005', 'PB004', 'JIRA', 'user006@halil.com'),
('I006', 'PM005', 'JIRA', 'user051@halil.com'),
('I007', 'PN007', 'JIRA', 'user026@halil.com'),
('I008', 'PX001', 'JIRA', 'user001@halil.com'),
('I009', 'PF006', 'JIRA', 'user017@halil.com'),
('I010', 'PD006', 'JIRA', 'user035@halil.com'),
('I011', 'PB006', 'JIRA', 'user008@halil.com'),
('I012', 'PD001', 'JIRA', 'user030@halil.com'),
('I013', 'PM008', 'JIRA', 'user054@halil.com'),
('I014', 'PQ007', 'JIRA', 'user044@halil.com'),
('I015', 'PM003', 'JIRA', 'user049@halil.com'),
('I016', 'PQ001', 'JIRA', 'user038@halil.com'),
('I017', 'PN006', 'JIRA', 'user025@halil.com'),
('I018', 'PQ008', 'JIRA', 'user045@halil.com'),
('I019', 'PB005', 'JIRA', 'user007@halil.com'),
('I020', 'PF004', 'JIRA', 'user015@halil.com'),
('I021', 'PD002', 'JIRA', 'user031@halil.com'),
('I022', 'PX002', 'JIRA', 'user002@halil.com'),
('I023', 'PN002', 'JIRA', 'user021@halil.com'),
('I024', 'PQ005', 'JIRA', 'user042@halil.com'),
('I025', 'PB003', 'JIRA', 'user005@halil.com'),
('I026', 'PQ009', 'JIRA', 'user046@halil.com'),
('I027', 'PD003', 'JIRA', 'user032@halil.com'),
('I028', 'PN004', 'JIRA', 'user023@halil.com'),
('I029', 'PB008', 'JIRA', 'user010@halil.com'),
('I030', 'PM002', 'JIRA', 'user048@halil.com'),
('I031', 'PF003', 'JIRA', 'user014@halil.com'),
('I032', 'PB002', 'JIRA', 'user004@halil.com'),
('I033', 'PD004', 'JIRA', 'user033@halil.com'),
('I034', 'PM011', 'JIRA', 'user057@halil.com'),
('I035', 'PQ003', 'JIRA', 'user040@halil.com'),
('I036', 'PN010', 'JIRA', 'user029@halil.com'),
('I037', 'PF005', 'JIRA', 'user016@halil.com'),
('I038', 'PM010', 'JIRA', 'user056@halil.com'),
('I039', 'PN001', 'JIRA', 'user020@halil.com'),
('I040', 'PM001', 'JIRA', 'user047@halil.com'),
('I041', 'PM011', 'GOOGLE', 'halil.user057@gmail.com'),
('I042', 'PD006', 'GOOGLE', 'halil.user035@gmail.com'),
('I043', 'PB007', 'GOOGLE', 'halil.user009@gmail.com'),
('I044', 'PN006', 'GOOGLE', 'halil.user025@gmail.com'),
('I045', 'PD001', 'GOOGLE', 'halil.user030@gmail.com'),
('I046', 'PN005', 'GOOGLE', 'halil.user024@gmail.com'),
('I047', 'PQ006', 'GOOGLE', 'halil.user043@gmail.com'),
('I048', 'PM002', 'GOOGLE', 'halil.user048@gmail.com'),
('I049', 'PQ008', 'GOOGLE', 'halil.user045@gmail.com'),
('I050', 'PM010', 'GOOGLE', 'halil.user056@gmail.com'),
('I051', 'PN008', 'GOOGLE', 'halil.user027@gmail.com'),
('I052', 'PQ001', 'GOOGLE', 'halil.user038@gmail.com'),
('I053', 'PB008', 'GOOGLE', 'halil.user010@gmail.com'),
('I054', 'PM001', 'GOOGLE', 'halil.user047@gmail.com'),
('I055', 'PQ005', 'GOOGLE', 'halil.user042@gmail.com'),
('I056', 'PB005', 'GOOGLE', 'halil.user007@gmail.com'),
('I057', 'PD003', 'GOOGLE', 'halil.user032@gmail.com'),
('I058', 'PQ003', 'GOOGLE', 'halil.user040@gmail.com'),
('I059', 'PQ007', 'GOOGLE', 'halil.user044@gmail.com'),
('I060', 'PF007', 'GOOGLE', 'halil.user018@gmail.com'),
('I061', 'PB001', 'GOOGLE', 'halil.user003@gmail.com'),
('I062', 'PM006', 'GOOGLE', 'halil.user052@gmail.com'),
('I063', 'PF003', 'GOOGLE', 'halil.user014@gmail.com'),
('I064', 'PN010', 'GOOGLE', 'halil.user029@gmail.com'),
('I065', 'PD005', 'GOOGLE', 'halil.user034@gmail.com'),
('I066', 'PF005', 'GOOGLE', 'halil.user016@gmail.com'),
('I067', 'PN009', 'GOOGLE', 'halil.user028@gmail.com'),
('I068', 'PF001', 'GOOGLE', 'halil.user012@gmail.com'),
('I069', 'PB002', 'GOOGLE', 'halil.user004@gmail.com'),
('I070', 'PN003', 'GOOGLE', 'halil.user022@gmail.com');