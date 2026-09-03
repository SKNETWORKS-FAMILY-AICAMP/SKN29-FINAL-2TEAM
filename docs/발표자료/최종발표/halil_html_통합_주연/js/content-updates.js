(() => {
  const deck = window.HALIL_DECK;
  if (!deck?.slides?.length) return;

  const original = new Map(deck.slides.map((slide) => [slide.number, slide]));
  const clone = (value) => JSON.parse(JSON.stringify(value));
  const slide = (number) => original.get(number);

  function setElementText(element, value, options = {}) {
    if (!element) return;
    const text = String(value ?? '');
    element.text = text;

    const baseParagraph = clone(element.paragraphs?.[0] || {});
    const baseRun = clone(baseParagraph.runs?.[0] || {});
    const resolved = clone(baseParagraph.resolvedTextStyle || {});

    if (options.fontSize) {
      resolved.fontSize = options.fontSize;
      baseRun.fontSize = options.fontSize;
    }
    if (options.color) {
      resolved.color = options.color;
      baseRun.color = options.color;
    }
    if (options.bold !== undefined) {
      resolved.bold = options.bold;
      baseRun.bold = options.bold;
    }
    if (options.alignment) resolved.alignment = options.alignment;

    element.paragraphs = text.split('\n').map((line, index) => ({
      ...baseParagraph,
      index: index + 1,
      text: line,
      resolvedTextStyle: clone(resolved),
      runs: [{ ...baseRun, index: 1, text: line }],
      bulletCharacter: '',
      marginLeft: 0,
    }));
  }

  function byName(number, name, value, options) {
    const target = slide(number)?.elements.find((element) => element.name === name);
    setElementText(target, value, options);
  }

  function replaceExact(number, before, after, options) {
    slide(number)?.elements
      .filter((element) => element.text === before)
      .forEach((element) => setElementText(element, after, options));
  }

  function removeNames(number, names) {
    const target = slide(number);
    if (!target) return;
    const removals = new Set(names);
    target.elements = target.elements.filter((element) => !removals.has(element.name));
  }

  function removeContentArea(target, keepNames = []) {
    const keep = new Set(keepNames);
    target.elements = target.elements.filter((element) => {
      if (keep.has(element.name)) return true;
      const [, y] = element.bbox || [0, 0];
      return y < 185 || y >= 635;
    });
  }

  function resizeText(number, name, bbox, fontSize) {
    const element = slide(number)?.elements.find((item) => item.name === name);
    if (!element) return;
    if (bbox) element.bbox = bbox;
    setElementText(element, element.text, fontSize ? { fontSize } : {});
  }

  function textElement(name, bbox, text, size = 18, color = '#101728', bold = false, alignment = 'left') {
    return {
      kind: 'shape', geometry: 'rect', bbox, lineWidth: 0, name, text,
      paragraphs: text.split('\n').map((line, index) => ({
        index: index + 1,
        text: line,
        resolvedTextStyle: { fontSize: size, typeface: 'Pretendard', color, bold, alignment },
        runs: [{ index: 1, text: line, fontSize: size, typeface: 'Pretendard', color, bold }],
        bulletCharacter: '', marginLeft: 0,
      })),
      textStyle: {
        fontSize: size, typeface: 'Pretendard', color, alignment,
        verticalAlignment: 'middle', autoFit: 'shrinkText',
        insets: { top: 4, right: 6, bottom: 4, left: 6 },
      },
    };
  }

  function panel(name, bbox, fill = '#FFFFFF', lineColor = '#D9DEE8', radius = 'roundRect') {
    return { kind: 'shape', geometry: radius, bbox, fillColor: fill, lineColor, lineWidth: 1, name };
  }

  function imageElement(name, bbox, media, fit = 'contain', filter = '') {
    return { kind: 'image', bbox, name, media, fit, filter };
  }

  function videoElement(name, bbox, media) {
    return { kind: 'video', bbox, name, media, controls: true };
  }

  // 표지: 좌상단 브랜드 마크·로고와 부제 문구 없이 배경 이미지의 워드마크만 사용한다.
  removeNames(1, ['cover-brand', 'cover-product-brand-plate', 'cover-product-favicon', 'cover-product-logo', 'institution-logo-plate', 'cover-title']);
  byName(1, 'cover-formal', '프로젝트 운영을 위한\nAI Agent 플랫폼');
  // 첫 줄(수식어)은 제품명 줄보다 작게 — 56 → 41.
  (() => {
    const lead = slide(1).elements.find((e) => e.name === 'cover-formal')?.paragraphs?.[0];
    if (lead) { lead.resolvedTextStyle.fontSize = 41; lead.runs[0].fontSize = 41; }
  })();
  // 기관 로고(직업능력심사평가원·고용노동부)는 좌하단 팀원 이름 아래로 옮긴다.
  const coverInstitutionA = slide(1).elements.find((element) => element.name === '그림 194');
  const coverInstitutionB = slide(1).elements.find((element) => element.name === '그림 195');
  if (coverInstitutionA) {
    coverInstitutionA.bbox = [62, 586, 95, 30];
    coverInstitutionA.filter = 'brightness(1.55)';
  }
  if (coverInstitutionB) {
    coverInstitutionB.bbox = [173, 586, 101, 30];
    coverInstitutionB.filter = 'brightness(2.1)';
  }
  // 팀원 순서는 '프로젝트 팀 구성 및 역할' 장표와 동일하게 맞춘다.
  byName(1, 'cover-members', '임준 · 김지훈 · 임준억 · 성주연 · 최원빈  |  멘토 김유진');

  // 목차는 왼쪽 번호 열을 사용하므로 제목에서는 중복 번호를 제거한다.
  byName(3, 'row-text-3-0', '프로젝트 개요');
  byName(3, 'row-text-3-1', '프로젝트 팀 구성 및 역할');
  byName(3, 'row-text-3-2', '프로젝트 수행 절차 및 방법');
  byName(3, 'row-text-3-3', '프로젝트 수행 결과');
  byName(3, 'row-text-3-4', '자체 평가 의견');
  removeNames(3, ['section-3', 'sub-3']);
  byName(3, 'signal-label-3', '목차');
  // 좌측 쏠림 완화 — 제목과 목록을 슬라이드 가로 중앙으로 모으고, 부제 삭제분만큼 목록을 위로 당겨 세로 균형을 맞춘다.
  byName(3, 'title-3', '목차', { alignment: 'center' });
  {
    const tocLeft = 320;      // 번호 열 시작
    const tocTextLeft = 398;  // 항목 텍스트 시작
    const tocWidth = 640;     // 구분선 폭 (중앙: 320 → 960)
    const firstRuleY = 182;   // 첫 구분선 y (기존 214 → 위로)
    const rowPitch = 84;      // 행 간격 (기존 72 → 늘려 세로 여백 균등 배분)
    for (let i = 0; i < 5; i += 1) {
      const ruleY = firstRuleY + rowPitch * i;
      const rule = slide(3).elements.find((e) => e.name === `row-rule-3-${i}`);
      if (rule) rule.bbox = [tocLeft, ruleY, tocWidth, rule.bbox[3]];
      const no = slide(3).elements.find((e) => e.name === `row-no-3-${i}`);
      if (no) no.bbox = [tocLeft, ruleY + 18, no.bbox[2], no.bbox[3]];
      const txt = slide(3).elements.find((e) => e.name === `row-text-3-${i}`);
      if (txt) txt.bbox = [tocTextLeft, ruleY + 14, tocLeft + tocWidth - tocTextLeft, txt.bbox[3]];
    }
  }

  // 도입부는 시장 근거 → 선도 사례 → 운영 전환 간극 → HALIL 범위 → 사용자 흐름으로 전개한다.
  byName(4, 'div-title-4', '프로젝트 개요');
  byName(4, 'div-key-4', '시장 변화 · 프로젝트 출발 · 문제 정의 · 해결 방향');

  // 챕터 표지 5장(01~05) — 소제목(div-sub)·하단 마커(div-key) 삭제, 구분선(div-line)은 유지.
  //   제목은 키우고(68 → 84) 슬라이드 정중앙(가로·세로)으로 옮긴다. 번호·구분선·페이지는 그대로.
  [4, 12, 15, 20, 51].forEach((n) => {
    removeNames(n, [`div-sub-${n}`, `div-key-${n}`]);
    const title = slide(n).elements.find((e) => e.name === `div-title-${n}`);
    if (!title) return;
    title.bbox = [62, 300, 1156, 120];
    title.textStyle.verticalAlignment = 'middle';
    title.textStyle.alignment = 'center';
    title.paragraphs.forEach((p) => {
      p.resolvedTextStyle.fontSize = 84;
      p.resolvedTextStyle.alignment = 'center';
      p.runs.forEach((r) => { r.fontSize = 84; });
    });
  });

  [5, 6, 7, 8].forEach((number) => {
    const element = slide(number)?.elements.find((item) => item.name === `context-${number}`);
    setElementText(element, 'halil   ·   01 프로젝트 개요');
  });
  byName(10, 'context-9', 'halil   ·   01 프로젝트 개요');

  removeNames(5, ['section-5']);
  byName(5, 'title-5', 'AI Agent 도입은 늘지만, 실제 업무 적용은 아직 초기입니다');
  byName(5, 'sub-5', '도입을 검토·실험하는 기업은 빠르게 늘지만, 실제 업무로 확장한 기업과의 간극이 뚜렷합니다.');
  removeContentArea(slide(5));
  slide(5).elements.push(textElement('market-label-left', [74, 236, 460, 28], '검토·실험 · McKinsey 2025', 14, '#2878D1', true));
  slide(5).elements.push(textElement('market-stat-left', [70, 268, 200, 96], '62%', 72, '#2878D1', true));
  slide(5).elements.push(textElement('market-copy-left', [258, 280, 300, 80], 'AI Agent 도입을\n검토·실험 중인 기업', 21, '#101728', true));
  slide(5).elements.push(textElement('market-arrow', [590, 284, 110, 60], '→', 44, '#A6B4C7', false, 'center'));
  slide(5).elements.push(textElement('market-gap-label', [560, 372, 172, 24], '실험 ↔ 규모화 간극', 13, '#D86F28', true, 'center'));
  slide(5).elements.push(textElement('market-label-right', [726, 236, 460, 28], '확장 운영 · McKinsey 2025', 14, '#17845E', true));
  slide(5).elements.push(textElement('market-stat-right', [722, 268, 200, 96], '23%', 72, '#17845E', true));
  slide(5).elements.push(textElement('market-copy-right', [910, 280, 300, 80], '한 개 이상 업무 기능에서\n확장 운영 중인 기업', 21, '#101728', true));
  slide(5).elements.push({ kind: 'shape', geometry: 'line', bbox: [70, 410, 1138, 0], lineColor: '#D3DCE8', lineWidth: 2, name: 'market-divider' });
  slide(5).elements.push(textElement('market-takeaway', [90, 452, 1100, 84], '관심과 실험은 빠르게 늘고 있지만,\n실제 업무로 확장한 기업은 아직 일부입니다.', 22, '#0C3F91', true, 'center'));
  slide(5).elements.push(textElement('market-source', [74, 596, 1136, 20], '출처: McKinsey Global Survey on the state of AI, 2025 (n=1,993 · 105개국)', 10, '#7B8492'));
  byName(5, 'signal-label-5', '시장 변화');
  slide(5).sources = ['https://www.mckinsey.com/capabilities/quantumblack/our-insights/the-state-of-ai'];

  removeNames(6, ['section-6']);
  byName(6, 'title-6', '먼저 나선 서비스들은 같은 방향으로 수렴합니다');
  byName(6, 'sub-6', '제품별 강점은 다르지만, 기업용 Agent가 갖춰야 할 요건은 지식 연결·업무 도구·사람 통제로 모입니다.');
  removeContentArea(slide(6));
  slide(6).elements.push(textElement('market-case-head-0', [74, 214, 190, 30], '시장 사례', 13, '#6E7A90', true));
  slide(6).elements.push(textElement('market-case-head-1', [292, 214, 270, 30], '지식 · 맥락', 13, '#6E7A90', true));
  slide(6).elements.push(textElement('market-case-head-2', [594, 214, 270, 30], 'Agent 구성', 13, '#6E7A90', true));
  slide(6).elements.push(textElement('market-case-head-3', [896, 214, 310, 30], '운영 통제', 13, '#6E7A90', true));
  slide(6).elements.push({ kind: 'shape', geometry: 'rect', bbox: [72, 250, 1136, 112], fillColor: '#EEF4FC', lineWidth: 0, name: 'glean-row' });
  slide(6).elements.push(textElement('glean-name', [92, 270, 166, 72], 'GLEAN', 22, '#0C3F91', true));
  slide(6).elements.push(textElement('glean-context', [292, 270, 270, 72], '권한을 반영한\n기업 지식·맥락 연결', 17, '#101728', true));
  slide(6).elements.push(textElement('glean-builder', [594, 270, 270, 72], 'No-code Builder와\n다단계 Agent 구성', 17, '#101728', true));
  slide(6).elements.push(textElement('glean-governance', [896, 270, 290, 72], '권한·로그·평가 기반\nAgent 운영 가시성', 17, '#101728', true));
  slide(6).elements.push({ kind: 'shape', geometry: 'rect', bbox: [72, 374, 1136, 112], fillColor: '#F4F6F9', lineWidth: 0, name: 'copilot-row' });
  slide(6).elements.push(textElement('copilot-name', [92, 394, 174, 72], 'COPILOT\nSTUDIO', 18, '#2878D1', true));
  slide(6).elements.push(textElement('copilot-context', [292, 394, 270, 72], 'Knowledge Source와\nConnector 연결', 17, '#101728', true));
  slide(6).elements.push(textElement('copilot-builder', [594, 394, 270, 72], 'Agent 제작·배포와\n환경별 생명주기 관리', 17, '#101728', true));
  slide(6).elements.push(textElement('copilot-governance', [896, 394, 290, 72], 'DLP·인증·환경 정책과\n사용·보안 관측', 17, '#101728', true));
  slide(6).elements.push(textElement('market-case-takeaway', [74, 516, 1134, 50], '시장이 수렴하는 공통 방향  =  조직 지식을 연결하고 · 업무 도구로 실행하며 · 사람이 통제한다', 18, '#0C3F91', true, 'center'));
  slide(6).elements.push(textElement('market-case-source', [74, 592, 1136, 20], '출처: Glean Agent Builder · Microsoft Copilot Studio 공식 제품·거버넌스 문서', 10, '#7B8492'));
  byName(6, 'signal-label-6', '선도 서비스');
  slide(6).sources = ['https://www.glean.com/ai-agent-builder', 'https://learn.microsoft.com/en-us/microsoft-copilot-studio/security-and-governance'];

  removeNames(10, ['section-9']);
  byName(10, 'title-9', 'AX 흐름에서 시작한 HALIL');
  byName(10, 'sub-9', '‘다중 에이전트 기반 업무 활용 플랫폼’이라는 대주제에서 기업 업무에 필요한 방향을 구체화했습니다.');
  removeContentArea(slide(10));
  slide(10).elements.push(textElement('origin-left-label', [74, 226, 470, 28], '처음 받은 프로젝트 대주제', 14, '#6E7A90', true));
  slide(10).elements.push(panel('origin-topic-card', [72, 260, 470, 300], '#EEF4FC', '#2878D1'));
  slide(10).elements.push(textElement('origin-topic-text', [100, 300, 414, 140], '다중 에이전트 기반\n업무 활용 플랫폼', 30, '#0C3F91', true));
  slide(10).elements.push(textElement('origin-topic-sub', [100, 452, 414, 96], '시장에서 확인된 AX·Agent 흐름을 실제 기업 업무 환경에서 확인해 보자는 출발점', 15, '#52657D'));
  slide(10).elements.push(textElement('origin-right-label', [604, 226, 604, 28], 'HALIL로 구체화한 방향', 14, '#6E7A90', true));
  [
    ['기업 업무에 적용', '범용 데모가 아니라 회사가 실제로 겪는 업무에 초점'],
    ['비개발자도 구성', '업무를 아는 사람이 직접 Agent를 만들고 공유'],
    ['아직 출발 단계', '기능·성과 이전에 방향을 잡고 검증하는 단계'],
  ].forEach((row, index) => {
    const y = 260 + (index * 104);
    slide(10).elements.push(panel(`origin-dir-${index}`, [604, y, 604, 92], '#FFFFFF', '#D9DEE8'));
    slide(10).elements.push(textElement(`origin-dir-title-${index}`, [626, y + 16, 560, 30], row[0], 18, '#101728', true));
    slide(10).elements.push(textElement(`origin-dir-body-${index}`, [626, y + 50, 560, 30], row[1], 14, '#52657D'));
  });
  slide(10).elements.push(textElement('origin-market-note', [74, 578, 1134, 22], '참고: 앞서 본 선도 서비스의 공통 방향을 프로젝트의 출발 기준으로 삼았습니다.', 11, '#7B8492', false, 'center'));
  byName(10, 'signal-label-9', '프로젝트 출발');
  slide(10).sources = [];

  removeNames(7, ['section-7']);
  byName(7, 'title-7', '기업 업무의 두 가지 문제에 주목했습니다');
  byName(7, 'sub-7', '정보는 여러 곳에 흩어져 있고, 업무 방식은 개인의 경험에 머물러 있습니다.');
  removeContentArea(slide(7));
  slide(7).elements.push(panel('problem-1', [72, 226, 560, 322], '#FFFFFF', '#D9DEE8'));
  slide(7).elements.push(textElement('problem-1-no', [96, 250, 200, 28], '문제 1', 15, '#2878D1', true));
  slide(7).elements.push(textElement('problem-1-title', [96, 286, 512, 40], '흩어진 정보와 작업 환경', 24, '#101728', true));
  slide(7).elements.push(textElement('problem-1-body', [96, 344, 512, 176], '문서·웹·업무 시스템이 여러 곳에 분산되어\n필요한 정보를 한 번에 확인하고\n활용하기 어렵습니다.', 17, '#52657D'));
  slide(7).elements.push(panel('problem-2', [648, 226, 560, 322], '#FFFFFF', '#D9DEE8'));
  slide(7).elements.push(textElement('problem-2-no', [672, 250, 200, 28], '문제 2', 15, '#2878D1', true));
  slide(7).elements.push(textElement('problem-2-title', [672, 286, 512, 40], '개인에게 머무는 업무 노하우', 24, '#101728', true));
  slide(7).elements.push(textElement('problem-2-body', [672, 344, 512, 176], '업무 절차와 경험이 개인의 암묵지로 남아\n공유하기 어렵고, 특히 신규 구성원은\n업무를 익히는 데 더 많은 시간이 필요합니다.', 17, '#52657D'));
  slide(7).elements.push(textElement('problem-note', [74, 566, 1134, 30], 'HALIL은 이 두 문제를 각각 정보의 연결과 업무 방식의 재사용으로 해결하려 했습니다.', 15, '#0C3F91', true, 'center'));
  byName(7, 'signal-label-7', '문제 정의');

  removeNames(8, ['section-8']);
  byName(8, 'title-8', '정보는 연결, 업무 방식은 스킬로');
  byName(8, 'sub-8', '앞의 두 문제를 각각 정보 연결과 스킬화로 해결합니다.');
  removeContentArea(slide(8));
  slide(8).elements.push(textElement('sol-head-0', [94, 214, 260, 24], '문제', 12, '#6E7A90', true));
  slide(8).elements.push(textElement('sol-head-1', [392, 214, 430, 24], 'HALIL의 해결 방향', 12, '#6E7A90', true));
  slide(8).elements.push(textElement('sol-head-2', [840, 214, 366, 24], '기대 변화', 12, '#6E7A90', true));
  [
    ['흩어진 정보와 도구', 'Chat에서 문서·웹·업무 도구를 연결', '검색부터 결과 생성까지 한 흐름', '#EEF4FC'],
    ['개인에게 머무는 노하우', '반복 업무 절차를 스킬로 생성·공유', '팀원이 같은 방식으로 재사용', '#F4F6F9'],
  ].forEach((row, index) => {
    const y = 244 + (index * 116);
    slide(8).elements.push({ kind: 'shape', geometry: 'rect', bbox: [72, y, 1136, 104], fillColor: row[3], lineWidth: 0, name: `sol-row-${index}` });
    slide(8).elements.push(textElement(`sol-p-${index}`, [94, y + 18, 284, 68], row[0], 18, '#101728', true));
    slide(8).elements.push(textElement(`sol-s-${index}`, [392, y + 18, 430, 68], row[1], 17, '#2878D1', true));
    slide(8).elements.push(textElement(`sol-c-${index}`, [840, y + 18, 366, 68], row[2], 16, '#52657D'));
  });
  slide(8).elements.push({ kind: 'shape', geometry: 'rect', bbox: [72, 484, 1136, 58], fillColor: '#0C3F91', lineWidth: 0, name: 'sol-scope-band' });
  slide(8).elements.push(textElement('sol-scope', [94, 496, 1092, 34], 'HALIL이 연결하는 세 영역  ·  문서 근거화  →  Agent 운영  →  실행 검증', 17, '#FFFFFF', true, 'center'));
  slide(8).elements.push(textElement('sol-closing', [74, 556, 1134, 30], '흩어진 정보와 개인의 업무 방식을 하나의 업무 흐름으로 연결한 플랫폼이 HALIL입니다.', 15, '#52657D', false, 'center'));
  byName(8, 'signal-label-8', '해결 방향');

  // 숫자 중심 설명을 구현 흐름 중심으로 정리한다.
  replaceExact(14, 'Builder · 도구 32종\nRuntime · Streaming\nMemory · 버전 관리', 'Builder · Runtime\nStreaming · Memory\n버전 관리');
  replaceExact(14, 'side_effect 메타 15개\nHITL · 멱등 · 동시성\nSkill 12×3 검증', '쓰기 작업 승인 경계\nHITL · 멱등 · 동시성\nSkill 검증 흐름');
  replaceExact(14, '검색 37 · Agent 36\n최종 파싱 단위 검증\n배포 · 시연 준비', '검색·Agent DEV 평가\n파싱 보정 검증\n배포 · 시연 준비');
  replaceExact(14, '승인·통제·Skills', '에이전트 기능 구현');
  // 구현 과정 타임라인 — 중앙 바 기준 위·아래 간격을 대칭으로 (기존 위 96 / 아래 22 → 각 38).
  for (let i = 0; i < 6; i += 1) {
    const numberY = i % 2 === 0 ? 278 : 426; // 짝수 = 바 위, 홀수 = 바 아래
    const num = slide(14).elements.find((e) => e.name === `time-14-${i}`);
    if (num) num.bbox = [num.bbox[0], numberY, num.bbox[2], num.bbox[3]];
    const lab = slide(14).elements.find((e) => e.name === `time-label-14-${i}`);
    if (lab) lab.bbox = [lab.bbox[0], numberY + 32, lab.bbox[2], lab.bbox[3]];
  }

  // 13페이지는 공통 양식을 유지하고 최신 아키텍처 다이어그램만 본문에 배치한다.
  slide(16).background = '#F7F6F1';
  byName(16, 'section-16', 'SYSTEM ARCHITECTURE');
  byName(16, 'title-16', 'UI부터 실행·통제까지 연결된 시스템 구조');
  byName(16, 'sub-16', '사용자 화면·Agent Runtime·문서 검색·검증 Worker를 하나의 구조로 연결했습니다.');
  removeContentArea(slide(16));
  slide(16).elements.push({
    kind: 'shape', geometry: 'rect', bbox: [174, 188, 932, 438],
    fillColor: '#FFFFFF', lineColor: '#D9DEE8', lineWidth: 1,
    name: 'architecture-canvas',
  });
  slide(16).elements.push(imageElement(
    'architecture-diagram',
    [184, 194, 912, 426],
    'Architecture-diagram-only.png',
    'contain'
  ));
  byName(16, 'signal-label-16', 'SYSTEM ARCHITECTURE');
  slide(16).sources = ['media/Architecture-diagram-only.png'];

  byName(23, 'title-23', '새 Agent는 정의·연결·버전 저장을 거쳐 Graph에 조립됩니다');
  byName(23, 'loop-title-23-0', 'DEFINE');
  byName(23, 'loop-body-23-0', '비개발자가 역할·목표·지시문 정의');
  byName(23, 'loop-title-23-1', 'ATTACH');
  byName(23, 'loop-body-23-1', '필요한 Tool·Sub-agent·Skill 연결');
  byName(23, 'loop-title-23-2', 'VERSION');
  byName(23, 'loop-body-23-2', '구성을 새 버전으로 저장하고 팀에 공유');
  byName(23, 'loop-title-23-3', 'ASSEMBLE');
  byName(23, 'loop-body-23-3', 'Query 시 선택한 구성으로 Runtime Graph 조립');

  byName(24, 'title-24', 'Versioning은 개발·검증·운영 설정을 분리합니다');
  byName(24, 's24-activate-label', '검증 →');
  byName(24, 's24-toggle-label', '배포 →');
  byName(24, 's24-reactivate-label', '← 되돌리기');
  byName(24, 's24-state-name-0', 'BUILD');
  byName(24, 's24-state-label-0', '새 구성 작성');
  byName(24, 's24-state-detail-0', '운영 버전에 영향 없이 Tool·Prompt 수정');
  byName(24, 's24-state-name-1', 'VALIDATE');
  byName(24, 's24-state-label-1', '팀 검증');
  byName(24, 's24-state-detail-1', '권한·도구·Sub-agent 구성 확인');
  byName(24, 's24-state-name-2', 'RUN');
  byName(24, 's24-state-label-2', '실행 버전');
  byName(24, 's24-state-detail-2', '검증한 버전만 채팅 Runtime에 연결');
  resizeText(24, 's24-state-detail-0', [96, 352, 228, 58], 13);
  resizeText(24, 's24-state-detail-1', [506, 352, 228, 58], 13);
  resizeText(24, 's24-state-detail-2', [896, 352, 228, 58], 13);
  byName(24, 's24-rule', '현재는 팀별 실행 버전을 관리하고, 향후 Dev·Stage·Prod 배포 정책으로 확장할 수 있습니다.');

  // Deep Agent의 실제 구성 요소를 중심으로 런타임 슬라이드를 재작성한다.
  byName(27, 'title-27', 'Deep Agent는 계획·위임·기억을 하나의 실행 루프로 연결합니다');
  byName(27, 's27-node-title-0', 'TODO / PLAN');
  byName(27, 's27-node-body-0', '작업을 분해하고 다음 행동을 계획');
  byName(27, 's27-node-title-1', 'SUB-AGENT');
  byName(27, 's27-node-body-1', '전문 Agent에 위임하고 도구 범위를 분리');
  byName(27, 's27-node-title-2', 'MEMORY / SKILL');
  byName(27, 's27-node-body-2', '대화 Memory와 명시적 Skill을 문맥에 결합');
  byName(27, 's27-node-title-3', 'CONTEXT');
  byName(27, 's27-node-body-3', '요약과 Filesystem으로 긴 문맥을 압축·보존');
  byName(27, 's27-final-title', 'CONTROLLED RESULT');
  byName(27, 's27-final-body', '근거·승인·실행 상태 반환');
  resizeText(27, 's27-node-body-0', [112, 318, 216, 42], 13);
  resizeText(27, 's27-node-body-1', [530, 274, 216, 42], 13);
  resizeText(27, 's27-node-body-2', [940, 318, 216, 42], 13);
  resizeText(27, 's27-node-body-3', [530, 494, 216, 42], 13);
  resizeText(27, 's27-final-body', [940, 544, 208, 28], 11);

  byName(28, 'title-28', 'Query는 Graph 조립부터 근거 응답까지 통제된 순서로 실행됩니다');
  byName(28, 's28-model-label-text', 'QUERY & GRAPH');
  byName(28, 's28-model-title', '요청마다 실행 Graph를 구성');
  byName(28, 's28-model-k-0', '문맥 로드');
  byName(28, 's28-model-v-0', '대화·Project·Memory·Skill을 불러옴');
  byName(28, 's28-model-k-1', 'Graph 조립');
  byName(28, 's28-model-v-1', '선택한 Tool·Sub-agent를 Runtime에 연결');
  byName(28, 's28-model-k-2', '계획·위임');
  byName(28, 's28-model-v-2', 'Todo를 만들고 필요한 작업을 위임');
  byName(28, 's28-server-label-text', 'CONTROLLED EXECUTION');
  byName(28, 's28-server-title', '서버가 실행 경계와 결과를 보장');
  byName(28, 's28-server-k-0', '도구 실행');
  byName(28, 's28-server-v-0', '권한과 project context를 서버가 주입');
  byName(28, 's28-server-k-1', '기록·재개');
  byName(28, 's28-server-v-1', '이벤트·Checkpoint·멱등 결과를 저장');
  byName(28, 's28-server-k-2', '쓰기 통제');
  byName(28, 's28-server-v-2', '변경 작업은 HITL 승인 전 중단');
  byName(28, 's28-server-k-3', '근거 응답');
  byName(28, 's28-server-v-3', 'Tool 결과와 출처를 최종 답변에 연결');
  byName(28, 's28-note', '사용자 행동 → 백엔드 Graph 조립 → Tool·Sub-agent 실행 → 근거 응답을 하나의 흐름으로 추적합니다.');

  byName(30, 'title-30', '쓰기 전에 멈추고, 같은 작업은 한 번만 실행합니다');
  replaceExact(30, 'side_effect 플래그 15개 · 되묻기·조회·조건부 변환은 별도 판정', 'side_effect 메타데이터로 쓰기 작업을 구분하고 실행 전 중단');
  replaceExact(30, '모델 상한 min(10, 50) · 동시 Tool 4개 · MCP 480초', '요청별 반복 상한 · 동시 Tool 제한 · MCP timeout 적용');

  resizeText(29, 's29-preview-body', [84, 370, 220, 46], 13);
  resizeText(29, 's29-decision-body', [522, 362, 126, 66], 11);
  resizeText(29, 's29-approve-body', [866, 302, 296, 48], 13);
  resizeText(29, 's29-reject-body', [866, 506, 296, 48], 13);

  // Skill은 현재 명시 호출, 자동 트리거는 향후 기능으로 구분한다.
  byName(32, 'title-32', 'Skill은 명시적으로 호출하고, 검증된 절차만 재사용합니다');
  byName(32, 's32-title-0', '/SKILL CALL');
  byName(32, 's32-body-0', '/skill-name으로 실행 의도를 명확히 지정');
  byName(32, 's32-title-1', 'CLARIFY');
  byName(32, 's32-body-1', '필요 입력과 실행 경계를 한 번씩 확인');
  byName(32, 's32-title-2', 'VALIDATE');
  byName(32, 's32-body-2', '사용자 승인 후 Background Job으로 검증');
  byName(32, 's32-title-3', 'CATALOG');
  byName(32, 's32-body-3', '검증본만 개인·팀 카탈로그에 게시');
  byName(32, 's32-note', '현재: 명시적 /Skill 호출  ·  향후: 사용자 의도 기반 Skill 추천·자동 트리거');
  resizeText(32, 's32-body-0', [82, 370, 230, 58], 13);
  resizeText(32, 's32-body-1', [372, 370, 230, 58], 13);
  resizeText(32, 's32-body-2', [662, 370, 230, 58], 13);
  resizeText(32, 's32-body-3', [952, 370, 230, 58], 13);

  byName(33, 'title-33', '자연어 한 문장으로 Skill 초안을 시작합니다');
  removeNames(33, ['s33-screen', 's33-browser-bar', 's33-dot-0', 's33-dot-1', 's33-dot-2', 's33-screen-title', 's33-screen-body', 's33-screen-note']);
  slide(33).elements.push(panel('skill-create-frame', [58, 196, 824, 408], '#FFFFFF'));
  slide(33).elements.push(imageElement('skill-create-capture', [64, 202, 812, 396], 'skill-create.png', 'contain'));
  byName(33, 's33-note-title-0', '요청 정의');
  byName(33, 's33-note-body-0', '반복 업무와 기대 결과를 자연어로 설명');
  byName(33, 's33-note-title-1', '조건 보완');
  byName(33, 's33-note-body-1', '필요한 입력과 실행 경계를 확인');
  byName(33, 's33-note-title-2', '등록 전 확인');
  byName(33, 's33-note-body-2', '검증을 거쳐 개인·팀 카탈로그에 등록');

  byName(34, 'title-34', 'Skill 검증은 라우팅과 행동을 분리해 확인합니다');
  byName(34, 's34-body-0', '긍정·부정 입력을 만들고 의미와 경계를 확인');
  byName(34, 's34-body-1', '호출 여부와 도구 인자·순서를 분리해 검사');
  byName(34, 's34-body-2', '결정적 검사와 LLM Reviewer를 함께 적용');
  byName(34, 's34-body-3', 'Runtime·Tool 버전을 재확인한 뒤 게시');
  byName(34, 's34-fail-body', '기준에 미달하면 기존 스킬을 유지하고, 수정한 초안을 처음부터 다시 검증');
  resizeText(34, 's34-fail-body', [490, 502, 416, 48], 12);

  // 기존 관리 설명 슬라이드는 실제 Skill 카탈로그 화면으로 교체한다.
  byName(35, 'title-35', '검증된 Skill은 개인·팀 카탈로그에서 관리합니다');
  removeContentArea(slide(35));
  slide(35).elements.push(panel('skill-list-frame', [56, 188, 1168, 430], '#FFFFFF'));
  slide(35).elements.push(imageElement('skill-list-capture', [62, 194, 1156, 418], 'skill-list.png', 'cover'));

  byName(36, 'title-36', '현재 동작과 다음 개선을 분리해 설명합니다');
  byName(36, 's36-current-title', '현재: 검증 Job·Worker·결과 저장');
  byName(36, 's36-current-body', '명시적 /Skill 호출 · 개인/팀 카탈로그 · 검증 상태 관리');
  byName(36, 's36-limit-0-label-text', 'NEXT: AUTO TRIGGER');
  byName(36, 's36-limit-0-title', '의도 기반 자동 추천');
  byName(36, 's36-limit-0-body', '사용자 문맥에서 적절한 Skill을 안전하게 추천·호출하는 정책 필요');
  byName(36, 's36-limit-1-label-text', 'NEXT: REAL E2E');
  byName(36, 's36-limit-1-title', '실모델 전체 Job 재검증');
  byName(36, 's36-limit-1-body', 'Provider·Worker·실제 도구 경계를 포함한 운영 조건 재검증 필요');
  byName(36, 's36-limit-2-label-text', 'CURRENT: SAFE TEST');
  byName(36, 's36-limit-2-title', '쓰기 도구는 Stub으로 격리');
  byName(36, 's36-limit-2-body', '검증 과정에서 외부 시스템을 변경하지 않고 인자·순서·승인을 확인');
  resizeText(36, 's36-limit-0-body', [60, 508, 350, 72], 13);
  resizeText(36, 's36-limit-1-body', [450, 508, 350, 72], 13);
  resizeText(36, 's36-limit-2-body', [840, 508, 350, 72], 13);

  // 파싱 흐름은 실패 지점과 보정 게이트가 보이도록 재구성한다.
  byName(38, 'title-38', 'Docling 기본 결과를 단계별 게이트로 보정합니다');
  byName(38, 'time-label-38-0', 'DOCLING\n기본 파싱');
  byName(38, 'time-label-38-1', 'ORDER\n읽기 순서');
  byName(38, 'time-label-38-2', 'HEADING\n제목 보정');
  byName(38, 'time-label-38-3', 'TABLE GATE\n오탐 차단');
  byName(38, 'time-label-38-4', 'DESCRIPTION\n이미지 설명');
  byName(38, 'time-label-38-5', 'SERIALIZE\n구조 보존');
  byName(38, 'time-label-38-6', 'RETRIEVE\n근거 검색');
  slide(38).elements.push(panel('parser-param-note-bg', [80, 540, 1120, 54], '#EEF4FC', '#D6E3F4'));
  slide(38).elements.push(textElement('parser-param-note', [100, 548, 1080, 38], '대표 설정  max_new_tokens=224 · do_sample=false  |  제한된 브로슈어 관찰에서 정한 휴리스틱으로, 대규모 문서에서 재튜닝이 필요합니다.', 14, '#52657D', false, 'center'));

  const doclingContext = clone(original.get(39));
  doclingContext.number = 37.5;
  byNameFor(doclingContext, 'title-39', 'Docling을 선택했지만, 비정형 PDF는 그대로 쓰기 어려웠습니다');
  byNameFor(doclingContext, 'section-39', 'DOCLING CONTEXT');
  byNameFor(doclingContext, 'signal-label-39', 'WHY DOCLING · WHY EXTEND');
  removeContentArea(doclingContext);
  doclingContext.elements.push(textElement('docling-why-label', [64, 210, 430, 34], 'WHY DOCLING', 15, '#2878D1', true));
  doclingContext.elements.push(textElement('docling-why-title', [64, 252, 430, 46], '빠르게 시작하고 직접 보완할 수 있는 기반', 22, '#101728', true));
  doclingContext.elements.push(textElement('docling-why-body', [64, 316, 430, 142], '큰 커뮤니티와 활발한 유지보수\n빠른 커스터마이징\nIBM 기반의 지속 가능성', 17, '#6E7A90'));
  doclingContext.elements.push(textElement('docling-gap-label', [64, 480, 430, 34], 'AS-IS GAP', 15, '#D05252', true));
  doclingContext.elements.push(textElement('docling-gap-body', [64, 516, 430, 72], '브로슈어형 PDF에서 읽기 순서·Heading·이미지·표 구조 오류가 반복', 16, '#6E7A90'));
  doclingContext.elements.push(panel('docling-before-frame', [534, 202, 686, 386], '#FFFFFF'));
  doclingContext.elements.push(imageElement('docling-before-evidence', [540, 208, 674, 374], 'reading-order-before.png', 'contain'));
  doclingContext.sources = ['runpod_worker/README.md', 'reading_order_nexty_page6_before.png'];

  byName(39, 'title-39', '읽기 순서 보정은 문서 구조를 실제 순서로 복원합니다');
  removeContentArea(slide(39));
  slide(39).elements.push(textElement('before-label', [60, 190, 530, 30], 'BEFORE · Docling 기본 순서', 16, '#D05252', true));
  slide(39).elements.push(textElement('after-label', [690, 190, 530, 30], 'AFTER · 동일 부모의 인접 역전만 보정', 16, '#17845E', true));
  slide(39).elements.push(panel('before-frame', [56, 224, 548, 338], '#FFFFFF'));
  slide(39).elements.push(panel('after-frame', [676, 224, 548, 338], '#FFFFFF'));
  slide(39).elements.push(imageElement('reading-order-before', [62, 230, 536, 326], 'reading-order-before.png', 'contain'));
  slide(39).elements.push(imageElement('reading-order-after', [682, 230, 536, 326], 'reading-order-after.png', 'contain'));
  slide(39).elements.push(textElement('parsing-caption', [110, 574, 1060, 38], '전체를 재정렬하지 않고, 검증 가능한 인접 역전만 제한적으로 교정합니다.', 16, '#6E7A90', false, 'center'));

  const multimodal = clone(original.get(39));
  multimodal.number = 39.5;
  byNameFor(multimodal, 'title-39', '이미지는 설명과 메타데이터로 검색 문맥에 연결합니다');
  byNameFor(multimodal, 'section-39', 'MULTIMODAL');
  byNameFor(multimodal, 'signal-label-39', 'MULTIMODAL DOCUMENT');
  removeContentArea(multimodal);
  multimodal.elements.push(panel('multimodal-frame', [58, 200, 624, 382], '#FFFFFF'));
  multimodal.elements.push(imageElement('multimodal-evidence', [64, 206, 612, 370], 'parsing-result.png', 'contain'));
  multimodal.elements.push(textElement('mm-step-1', [730, 220, 430, 46], '01  DESCRIPTION', 18, '#2878D1', true));
  multimodal.elements.push(textElement('mm-body-1', [730, 266, 430, 54], '구조 보정 후 이미지 설명을 생성', 16, '#6E7A90'));
  multimodal.elements.push(textElement('mm-step-2', [730, 342, 430, 46], '02  METADATA', 18, '#2878D1', true));
  multimodal.elements.push(textElement('mm-body-2', [730, 388, 430, 54], '허용된 설명만 meta.description에 저장', 16, '#6E7A90'));
  multimodal.elements.push(textElement('mm-step-3', [730, 464, 430, 46], '03  CROP + VLM ROUTING', 18, '#D88628', true));
  multimodal.elements.push(textElement('mm-body-3', [730, 510, 430, 66], '원본 crop 전달과 모델 capability routing은 추가 통합 검증 대상', 16, '#6E7A90'));
  multimodal.sources = ['runpod_worker/context_picture_description.py', 'runpod_worker/picture_description_serializer.py'];

  // 프로젝트 문서 화면을 실제 제품 캡처로 교체한다.
  byName(40, 'title-40', '기준 문서가 프로젝트의 검색 범위를 결정합니다');
  removeContentArea(slide(40));
  slide(40).elements.push(panel('documents-frame', [56, 188, 1168, 430], '#FFFFFF'));
  slide(40).elements.push(imageElement('documents-capture', [62, 194, 1156, 418], 'documents.png', 'cover'));

  // 근거 없는 로컬 스냅샷 수치를 제거한다.
  byName(42, 'title-42', '운영 정책과 실행 이력을 제품과 분리해 관리합니다');
  byName(42, 's42-critical-label', '구현 메뉴');
  byName(42, 's42-critical-body', 'Overview · Accounts · Teams · Models · MCP · Guardrails · Usage · Audit');
  replaceExact(44, '내장 32종 · 팀 MCP 도구', '내장 도구 · 팀 MCP 확장');

  // 실제 채팅 화면과 시연 영상을 사용한다.
  byName(45, 'title-45', '실행 과정을 숨기지 않고 단계별로 보여줍니다');
  removeContentArea(slide(45));
  slide(45).elements.push(panel('chat-frame', [56, 188, 1168, 430], '#FFFFFF'));
  slide(45).elements.push(imageElement('chat-capture', [62, 194, 1156, 418], 'chat-ui.png', 'cover'));

  byName(46, 'title-46', '시연은 구성·근거·승인의 한 흐름으로 진행합니다');
  replaceExact(46, 'Agent·버전·모델·도구·Subagent 구성', 'Agent 역할·모델·도구·Subagent 구성');
  replaceExact(46, 'Hybrid 근거 확인 → 후보 추출 → 결과 검토', '기준 문서 선택 → 근거 답변 → 실행 과정 확인');
  replaceExact(46, 'HITL 승인 → 내부·외부 반영 → Skill 검증·재사용', '쓰기 전 HITL 승인 → 결과 확인 → /Skill 재사용');

  byName(47, 'title-47', '전체 기능은 실제 시연 영상으로 확인합니다');
  byName(47, 'sub-47', '채팅 → 에이전트 → 프로젝트 → 문서 → 설정·스킬 순서의 연속 시연');
  removeNames(47, ['demo-frame-47', 'play-47', 'play-icon-47']);
  slide(47).elements.push(panel('demo-video-frame', [60, 214, 1160, 382], '#071426', '#26364B'));
  slide(47).elements.push(videoElement('demo-video-player', [66, 220, 1148, 370], 'media/halil_프로젝트_운영_AI_시연영상_v21_챕터카드_자막.mp4'));

  // 공식 규칙 평가를 먼저 보여 주고, 정량·정성 지표를 보조로 배치한다.
  byName(48, 'title-48', '플랫폼 규칙을 먼저 통과한 뒤 응답 품질을 측정합니다');
  byName(48, 'sub-48', '1차 Rule·Assertion  →  2차 정량 지표  →  3차 정성 평가');
  byName(48, 'headtxt-48-0', '평가 단계');
  byName(48, 'headtxt-48-1', '판정 기준');
  byName(48, 'headtxt-48-2', '역할');
  byName(48, 'mc0-48-0', '행동 규칙');
  byName(48, 'mc1-48-0', '권한·HITL·도구 순서·최종 상태 Assertion');
  byName(48, 'mc2-48-0', '공식 Pass / Fail');
  byName(48, 'mc0-48-1', '검색 품질');
  byName(48, 'mc1-48-1', '8문서·294청크·37질의 · Recall·MRR·Anchor');
  byName(48, 'mc2-48-1', '정식 DEV 기준선');
  byName(48, 'mc0-48-2', '응답 품질');
  byName(48, 'mc1-48-2', 'Ragas Faithfulness · DeepEval Answer Relevancy');
  byName(48, 'mc2-48-2', '보조 품질 지표');
  byName(48, 'mc0-48-3', '남은 검증');
  byName(48, 'mc1-48-3', '비공개 HOLDOUT · 대규모 부하 · RunPod 운영 E2E');
  byName(48, 'mc2-48-3', '추가 측정 필요');

  byName(49, 'title-49', '성공률보다 실패 원인이 다음 개선점을 만들었습니다');
  byName(49, 'sub-49', 'V2 공식 48건: 44 PASS(91.7%) · Core 36건: 32 PASS(88.9%)');
  byName(49, 'metric-title-1', 'Agent Eval V2');
  byName(49, 'metric-sub-1', '공식 Rule·Assertion 48건');
  byName(49, 'metric-empty-1', '44 / 48 PASS · 91.7%');
  byName(49, 'metric-placeholder-t-1', 'Core 32 / 36');
  byName(49, 'metrics-note', '실패: S01 도구 순서 3건 · S06 답변 계약 1건  →  계획·최종 응답 검증 강화');

  const evaluationEvolution = clone(original.get(49));
  evaluationEvolution.number = 48.5;
  byNameFor(evaluationEvolution, 'title-49', '평가는 기준선을 쌓고 실패를 다음 실행에 반영했습니다');
  byNameFor(evaluationEvolution, 'sub-49', '단일 의미 Query 기준선 → Core 반복 시나리오 → 안전·확장 시나리오');
  byNameFor(evaluationEvolution, 'section-49', 'EVALUATION EVOLUTION');
  byNameFor(evaluationEvolution, 'signal-label-49', 'EVALUATION EVOLUTION');
  removeContentArea(evaluationEvolution);
  evaluationEvolution.elements.push(panel('eval-stage-1', [60, 228, 340, 288], '#FFFFFF', '#D9DEE8'));
  evaluationEvolution.elements.push(textElement('eval-stage-1-label', [82, 250, 296, 30], '01 · BASELINE', 14, '#2878D1', true));
  evaluationEvolution.elements.push(textElement('eval-stage-1-title', [82, 296, 296, 52], 'Core 36회 반복', 22, '#101728', true));
  evaluationEvolution.elements.push(textElement('eval-stage-1-body', [82, 360, 296, 118], '32 PASS / 4 FAIL\nS01 사실 누락 3건\nS07 불필요 승인 1건', 16, '#6E7A90'));
  evaluationEvolution.elements.push(panel('eval-stage-2', [470, 228, 340, 288], '#EEF4FC', '#2878D1'));
  evaluationEvolution.elements.push(textElement('eval-stage-2-label', [492, 250, 296, 30], '02 · RE-EVALUATE', 14, '#2878D1', true));
  evaluationEvolution.elements.push(textElement('eval-stage-2-title', [492, 296, 296, 52], '평가 환경과 계약 보정', 22, '#101728', true));
  evaluationEvolution.elements.push(textElement('eval-stage-2-body', [492, 360, 296, 118], 'S07 3/3 PASS로 회복\nS01은 알려진 한계로 유지\nS06 실행 간 변동 1건 발견', 16, '#6E7A90'));
  evaluationEvolution.elements.push(panel('eval-stage-3', [880, 228, 340, 288], '#FFFFFF', '#D9DEE8'));
  evaluationEvolution.elements.push(textElement('eval-stage-3-label', [902, 250, 296, 30], '03 · V2 EXTEND', 14, '#17845E', true));
  evaluationEvolution.elements.push(textElement('eval-stage-3-title', [902, 296, 296, 52], '안전·확장 시나리오 추가', 22, '#101728', true));
  evaluationEvolution.elements.push(textElement('eval-stage-3-body', [902, 360, 296, 118], 'Core 36 + Expansion 12\n총 48회 중 44 PASS\n정성 평가는 보조 지표로 분리', 16, '#6E7A90'));
  evaluationEvolution.elements.push(textElement('eval-evolution-note', [120, 544, 1040, 44], '실패를 점수에서 숨기지 않고 문서 전처리·답변 계약·HOLDOUT 검증의 다음 과제로 연결했습니다.', 16, '#D86F28', true, 'center'));
  evaluationEvolution.sources = ['2026-08-27_Core_DEV_36건_Phase8_결과.md', '2026-08-28_AV073_Core_DEV_36건_재평가.md', '2026-08-28_V2_Ragas_DeepEval_평가지표.md'];

  byName(52, 'title-52', '강점은 연결성, 남은 과제는 검증 범위입니다');
  byName(52, 'sub-52', '확인된 구현과 다음 검증 대상을 분리');
  byName(52, 's52-0-title', '하나로 연결된 실행 흐름');
  byName(52, 's52-0-body', 'Deep Agent·근거 검색·HITL·Ops를 하나의 사용자 흐름으로 연결');
  byName(52, 's52-1-title', '근거 정밀도와 멀티모달');
  byName(52, 's52-1-body', 'page/block provenance · 표 false negative · 설명 과삭제 · vision routing 보완 필요');
  byName(52, 's52-2-title', '운영 조건에서 재검증');
  byName(52, 's52-2-body', '대형 문서·HOLDOUT·MCP 예산·자동 Skill trigger를 실제 부하에서 검증');
  byName(52, 's52-note', '현재 구현과 향후 기능을 분리하고, 수치는 재현 가능한 DEV 결과만 사용합니다.');

  const futureWork = clone(original.get(52));
  futureWork.number = 51.5;
  byNameFor(futureWork, 'title-52', '다음 단계는 근거 정밀도·라우팅·운영 검증입니다');
  byNameFor(futureWork, 'sub-52', '현재 구현 범위에서 확인한 여덟 가지 후속 과제');
  byNameFor(futureWork, 'section-52', 'FUTURE WORK');
  byNameFor(futureWork, 'signal-label-52', 'FUTURE WORK');
  removeContentArea(futureWork);
  futureWork.elements.push(textElement('future-left-label', [70, 210, 500, 34], 'EVIDENCE & DOCUMENT', 15, '#2878D1', true));
  futureWork.elements.push(textElement('future-left-title', [70, 252, 500, 44], '근거를 더 정확하게 연결', 24, '#101728', true));
  futureWork.elements.push(textElement('future-left-list', [70, 318, 500, 224], '01  문장 단위 Citation\n02  Table False Negative 보완\n03  Description Gate 과삭제 Fallback\n04  표 복잡도별 Serialization Routing', 18, '#52657D'));
  futureWork.elements.push({ kind: 'shape', geometry: 'line', bbox: [630, 214, 0, 350], lineColor: '#BAC8DB', lineWidth: 2, name: 'future-divider' });
  futureWork.elements.push(textElement('future-right-label', [690, 210, 500, 34], 'RUNTIME & OPERATIONS', 15, '#17845E', true));
  futureWork.elements.push(textElement('future-right-title', [690, 252, 500, 44], '실행 범위와 검증 규모를 확장', 24, '#101728', true));
  futureWork.elements.push(textElement('future-right-list', [690, 318, 500, 224], '05  Vision Capability Routing\n06  MCP Context Budget 제어\n07  Query 의도 기반 Skill Trigger\n08  대규모 문서·질문 Evaluation', 18, '#52657D'));
  futureWork.elements.push(textElement('future-note', [160, 566, 960, 36], '설계 목표를 현재 구현처럼 말하지 않고, 운영 조건에서 검증된 뒤 단계적으로 적용합니다.', 15, '#D86F28', true, 'center'));
  futureWork.sources = ['최종발표_PPT_피드백_정리.md'];

  // 슬라이드별 근거 메타데이터. 화면에는 노출하지 않지만 검증 출처를 유지한다.
  slide(27).sources = ['services/agent_runtime/middleware/factory.py', 'services/agent_runtime/factory.py'];
  slide(32).sources = ['services/agent_runtime/skills/invocation.py'];
  slide(38).sources = ['runpod_worker/README.md'];
  slide(39).sources = ['docs/설계 및 구현/3_중간발표 이후/작업기록/문서처리_파이프라인/Docling_후처리_고도화/순서_보정'];
  slide(42).sources = ['frontend/src/App.tsx'];
  slide(48).sources = ['docs/설계 및 구현/3_중간발표 이후/작업기록/Jihun_eval_v2/2026-08-28_V2_Ragas_DeepEval_평가지표.md'];
  slide(49).sources = ['docs/설계 및 구현/3_중간발표 이후/작업기록/Jihun_eval_v2/2026-08-28_AV073_Core_DEV_36건_재평가.md'];

  // 목차와 01~05 챕터 표지는 유지하고, 챕터 내부의 중복·기능 개수 나열만 정리한다.
  const order = [
    1,
    3,
    4,
    5, 6, 10, 7, 8,
    12,
    13, 14,
    15,
    16, 19,
    20,
    27, 23, 28, 45, 24, 29, 30,
    40,
    'docling-context', 38, 39, 'multimodal',
    48, 'evaluation-evolution', 49,
    32, 33, 35, 36,
    42, 43, 44,
    46, 47,
    51,
    'future-work', 52, 53,
  ];

  deck.slides = order.map((number) => {
    if (number === 'multimodal') return multimodal;
    if (number === 'docling-context') return doclingContext;
    if (number === 'evaluation-evolution') return evaluationEvolution;
    if (number === 'future-work') return futureWork;
    return slide(number);
  });
  deck.slides.forEach((item, index) => {
    item.number = index + 1;
    item.elements.forEach((element) => {
      if (/^(page-|div-page-)/.test(element.name || '')) {
        setElementText(element, String(index + 1).padStart(2, '0'));
      }
    });
  });

  // ===================================================================
  // 통합 병합 — 지훈 Agent·Skill + 원빈 파싱·청킹·임베딩 (전부 네이티브, iframe 미사용)
  //   · 방식 B: 지훈 content-updates.js 의 네이티브 빌더를 이식 (이미지 경로만 로컬 media/ 로 교정)
  //   · 원빈: wonbin-deck-data.js 의 슬라이드 객체(동일 스키마)를 그대로 주입
  //   · (c) 병존: base 요약 장표는 유지하고 상세본을 각 주제 뒤에 삽입
  //   · 후속 편집 예정: 원빈 장표 헤더(wonbin·01 → halil·04) 통일, 페이지 번호 연동, 요약↔상세 중복 정리
  // ===================================================================
  (() => {
    const topText = (name, bbox, text, size, color, bold = false) => {
      const el = textElement(name, bbox, text, size, color, bold, 'left');
      el.textStyle.verticalAlignment = 'top';
      return el;
    };
    const evalBase = (section, title, sub) => {
      const s = clone(slide(16));
      removeContentArea(s);
      setElementText(s.elements.find((e) => e.name === 'context-16'), 'halil   ·   04 프로젝트 수행 결과');
      setElementText(s.elements.find((e) => e.name === 'section-16'), section);
      setElementText(s.elements.find((e) => e.name === 'signal-label-16'), section);
      setElementText(s.elements.find((e) => e.name === 'title-16'), title);
      if (sub) setElementText(s.elements.find((e) => e.name === 'sub-16'), sub);
      else s.elements = s.elements.filter((e) => e.name !== 'sub-16');
      return s;
    };
    const daShot = (name, bbox, file) => ([
      imageElement(name, bbox, file, 'contain'),
      { kind: 'shape', geometry: 'rect', bbox, lineColor: '#C9D3E0', lineWidth: 1, name: name + '-frame' },
    ]);
    const daSlimNote = (s, text) => {
      s.elements.push({ kind: 'shape', geometry: 'rect', bbox: [72, 600, 1136, 48], fillColor: '#EAF1FB', lineWidth: 0, name: 'da-slimnote-band' });
      s.elements.push(textElement('da-slimnote', [94, 600, 1092, 48], text, 14.5, '#0C3F91', true, 'center'));
    };

    // ---- 지훈: Agent 5장 (LIFECYCLE / BUILDER / PIPELINE / HARNESS / RUNTIME) ----
    const agentSlides = [];
    agentSlides[0] = (() => {
      const s = clone(slide(16));
      removeContentArea(s);
      s.elements = s.elements.filter((e) => e.name !== 'sub-16');
      setElementText(s.elements.find((e) => e.name === 'context-16'), 'halil   ·   04 프로젝트 수행 결과');
      setElementText(s.elements.find((e) => e.name === 'section-16'), 'AGENT LIFECYCLE');
      setElementText(s.elements.find((e) => e.name === 'signal-label-16'), 'AGENT LIFECYCLE');
      setElementText(s.elements.find((e) => e.name === 'title-16'), '에이전트 생성과 사용자 질의 요청');
      const createBox = [196, 186, 372, 452];
      const queryBox = [712, 186, 372, 452];
      s.elements.push(
        textElement('s16-create-name', [196, 150, 372, 30], '에이전트 생성', 20, '#000000', true, 'center'),
        textElement('s16-query-name', [712, 150, 372, 30], '에이전트에 질의 요청', 20, '#000000', true, 'center'),
        imageElement('s16-create-img', createBox, 'Agent-create.png', 'contain'),
        imageElement('s16-query-img', queryBox, 'Agent-query.png', 'contain'),
        { kind: 'shape', geometry: 'rect', bbox: createBox, lineColor: '#000000', lineWidth: 1, name: 's16-create-frame' },
        { kind: 'shape', geometry: 'rect', bbox: queryBox, lineColor: '#000000', lineWidth: 1, name: 's16-query-frame' },
        textElement('s16-flow-label', [570, 372, 140, 22], '저장', 13, '#6C7482', false, 'center'),
        textElement('s16-flow-arrow', [570, 398, 140, 52], '→', 40, '#A6B4C7', false, 'center'),
      );
      return s;
    })();
    agentSlides[1] = (() => {
      const s = clone(slide(16));
      removeContentArea(s);
      setElementText(s.elements.find((e) => e.name === 'context-16'), 'halil   ·   04 프로젝트 수행 결과');
      setElementText(s.elements.find((e) => e.name === 'section-16'), 'AGENT BUILDER');
      setElementText(s.elements.find((e) => e.name === 'signal-label-16'), 'AGENT BUILDER');
      setElementText(s.elements.find((e) => e.name === 'title-16'), '에이전트 생성 파이프라인');
      setElementText(s.elements.find((e) => e.name === 'sub-16'), '업무 담당자가 역할과 실행 자원을 정의하고, Version을 발행해 Chat 실행까지 이어간다.');
      const cards = [
        ['01', '업무 정의', ['에이전트 이름', '에이전트 설명', '지시사항 (프롬프트)', '사용할 모델']],
        ['02', '실행 자원 연결', ['내장 Tool', '기업 MCP Tool', '서브 에이전트']],
        ['03', 'Version 발행', ['저장할 때마다 새 Version 생성', '기존 대화 · 상위 Agent는', '이전 Version 그대로 참조']],
        ['04', 'Chat 실행', ['활성화한 Agent를 선택해', '실제 요청으로 사용']],
      ];
      const BW = 266;
      cards.forEach((c, i) => {
        const x = 56 + i * 300;
        s.elements.push(
          { kind: 'shape', geometry: 'roundRect', bbox: [x, 218, BW, 92], fillColor: '#FFFFFF', lineColor: '#D3DBE6', lineWidth: 1, name: `s17-box-${i}` },
          textElement(`s17-no-${i}`, [x + 22, 234, BW - 44, 20], c[0], 13, '#2878D1', true),
          textElement(`s17-title-${i}`, [x + 22, 256, BW - 44, 30], c[1], 18, '#101728', true),
        );
        c[2].forEach((b, j) => {
          s.elements.push(topText(`s17-b-${i}-${j}`, [x + 8, 330 + j * 30, BW + 20, 28], '·  ' + b, 13.5, '#52657D'));
        });
        if (i < 3) s.elements.push(textElement(`s17-arw-${i}`, [x + BW, 246, 34, 36], '→', 24, '#8FA0B5', false, 'center'));
      });
      s.elements.push({ kind: 'shape', geometry: 'roundRect', bbox: [72, 512, 1136, 74], fillColor: '#EAF1FB', lineColor: '#D5E2F4', lineWidth: 1, name: 's17-note-band' });
      s.elements.push(textElement('s17-note', [96, 512, 1088, 74], 'Builder에서 고르는 기업 Tool과 모델은 현업 담당자가 직접 서버 주소와 인증 정보를 입력하는 방식이 아니다.', 15, '#0C3F91', true, 'center'));
      return s;
    })();
    agentSlides[2] = (() => {
      const s = clone(slide(16));
      removeContentArea(s);
      setElementText(s.elements.find((e) => e.name === 'context-16'), 'halil   ·   04 프로젝트 수행 결과');
      setElementText(s.elements.find((e) => e.name === 'section-16'), 'REQUEST PIPELINE');
      setElementText(s.elements.find((e) => e.name === 'signal-label-16'), 'REQUEST PIPELINE');
      setElementText(s.elements.find((e) => e.name === 'title-16'), '요청 도착부터 실행까지 파이프라인');
      setElementText(s.elements.find((e) => e.name === 'sub-16'), '요청 하나가 도착해서 답변 완료 · 승인 대기 · 오류 중 하나로 끝나기까지의 전체 경로.');
      const steps = [
        ['01', '요청 도착', '세션 · 사용자 확인'],
        ['02', '입력 전처리', '민감정보 가리기'],
        ['03', '가드레일 검사', '방금 등록한 그 검사'],
        ['04', '대화 저장', '통과한 원문만'],
        ['05', 'Runtime 조립', '설정을 읽어 그래프 생성'],
        ['06', '실행', '판단 → 도구 · 위임 반복'],
      ];
      const SX = 56;
      const SW = 1168;
      const CW = SW / 6;
      s.elements.push({ kind: 'shape', geometry: 'roundRect', bbox: [SX, 250, SW, 200], fillColor: '#FFFFFF', lineColor: '#DDE3EC', lineWidth: 1, name: 's18-strip' });
      steps.forEach((st, i) => {
        const cx = SX + i * CW;
        if (i > 0) s.elements.push({ kind: 'shape', geometry: 'line', bbox: [cx, 274, 0, 152], lineColor: '#E7EBF1', lineWidth: 1, name: `s18-div-${i}` });
        s.elements.push(
          textElement(`s18-no-${i}`, [cx + 18, 274, CW - 40, 22], st[0], 13, '#2878D1', true),
          textElement(`s18-title-${i}`, [cx + 18, 300, CW - 40, 28], st[1], 15.5, '#101728', true),
          topText(`s18-body-${i}`, [cx + 18, 336, CW - 34, 96], st[2], 12.5, '#52657D'),
        );
        if (i < 5) s.elements.push(textElement(`s18-arw-${i}`, [cx + CW - 18, 388, 36, 34], '→', 22, '#4E5E78', true, 'center'));
      });
      s.elements.push({ kind: 'shape', geometry: 'roundRect', bbox: [72, 486, 1136, 76], fillColor: '#FBEEEE', lineColor: '#F0D9D7', lineWidth: 1, name: 's18-note-band' });
      s.elements.push(textElement('s18-note', [96, 486, 1088, 76], '가드레일 검사 실패 시 — 대화 저장 이전에 요청이 그 자리에서 끝난다. 대화 이력에 남지 않는다.', 15, '#B4433B', true, 'center'));
      return s;
    })();
    agentSlides[3] = (() => {
      const s = clone(slide(16));
      removeContentArea(s);
      setElementText(s.elements.find((e) => e.name === 'context-16'), 'halil   ·   04 프로젝트 수행 결과');
      setElementText(s.elements.find((e) => e.name === 'section-16'), 'AGENT HARNESS');
      setElementText(s.elements.find((e) => e.name === 'signal-label-16'), 'AGENT HARNESS');
      setElementText(s.elements.find((e) => e.name === 'title-16'), 'Deep Agent는 에이전트 실행 하네스입니다');
      setElementText(s.elements.find((e) => e.name === 'sub-16'), 'Codex · Claude Code처럼, Deep Agent도 에이전트를 실제로 실행시키는 프레임워크입니다.');
      const bands = [
        { x: 72, fill: '#EAF1FB', no: '01', label: 'BUILDER', title: '에이전트 생성·수정', body: '업무에 맞는\n실행 구성을 선택' },
        { x: 462, fill: '#EEF8F4', no: '+', label: '확장점', title: 'Tool · Sub Agent', body: '도구와 서브에이전트를\nAgent에 연결' },
        { x: 852, fill: '#F5F0E8', no: '02', label: 'RUNTIME', title: '실행 그래프 재조립', body: '변경된 구성이\n다음 실행에 반영' },
      ];
      bands.forEach((b, i) => {
        s.elements.push({ kind: 'shape', geometry: 'rect', bbox: [b.x, 252, 356, 214], fillColor: b.fill, lineWidth: 0, name: `s19-band-${i}` });
        s.elements.push(textElement(`s19-no-${i}`, [b.x + 24, 272, 64, 32], b.no, 18, '#2878D1', true));
        s.elements.push(textElement(`s19-label-${i}`, [b.x + 92, 274, 240, 30], b.label, 13, '#6E7A90', true));
        s.elements.push(textElement(`s19-title-${i}`, [b.x + 24, 320, 308, 40], b.title, 22, '#101728', true));
        s.elements.push(textElement(`s19-body-${i}`, [b.x + 24, 372, 308, 72], b.body, 16, '#52657D'));
      });
      s.elements.push({ kind: 'shape', geometry: 'rect', bbox: [72, 500, 1134, 82], fillColor: '#EAF1FB', lineWidth: 0, name: 's19-note-band' });
      s.elements.push(textElement('s19-note-copy', [94, 500, 1090, 82], 'halil은 Deep Agent 하네스 위에 제품을 얹어, 구성 변경이 다음 실행에 그대로 반영되도록 했습니다', 17, '#0C3F91', true, 'center'));
      return s;
    })();
    agentSlides[4] = (() => {
      const s = clone(slide(16));
      removeContentArea(s);
      s.elements = s.elements.filter((e) => e.name !== 'sub-16');
      setElementText(s.elements.find((e) => e.name === 'context-16'), 'halil   ·   04 프로젝트 수행 결과');
      setElementText(s.elements.find((e) => e.name === 'section-16'), 'AGENT RUNTIME');
      setElementText(s.elements.find((e) => e.name === 'signal-label-16'), 'AGENT RUNTIME');
      setElementText(s.elements.find((e) => e.name === 'title-16'), 'Deep Agent 실행 구조 전체 도면');
      s.elements.push({
        kind: 'shape', geometry: 'rect', bbox: [150, 180, 980, 462],
        fillColor: '#FFFFFF', lineColor: '#D9DEE8', lineWidth: 1, name: 's20-canvas',
      });
      s.elements.push(imageElement('s20-diagram', [160, 190, 960, 442], 'deep_agent.png', 'contain'));
      return s;
    })();

    // ---- 지훈: 스킬 섹션 표지 + 3장 (SKILL / SKILL PROCESS / TEAM SKILL) ----
    const skillDivider = (() => {
      const s = clone(slide(20));
      setElementText(s.elements.find((e) => e.name === 'div-title-20'), '사용자 편의 기능');
      setElementText(s.elements.find((e) => e.name === 'div-sub-20'), '검증된 스킬 재사용 · 실행 과정 공개 · 팀 단위 운영');
      setElementText(s.elements.find((e) => e.name === 'div-key-20'), 'SKILL · EXECUTION · OPERATIONS');
      return s;
    })();
    const skillSlides = [];
    skillSlides[0] = (() => {
      const s = evalBase('SKILL', '검증한 Skill만 등록해 반복 업무에 재사용');
      s.elements.push(
        textElement('s37-cap-l', [92, 198, 600, 22], '새 스킬 등록 화면', 16, '#6C7482', true),
        ...daShot('s37-img-register', [92, 224, 600, 362], 'skill-register.png'),
        textElement('s37-cap-r', [744, 198, 464, 22], '/스킬이름 직접 호출', 16, '#6C7482', true),
        ...daShot('s37-img-slash', [744, 224, 430, 207], 'skill-slash.png'),
        textElement('s37-points', [744, 452, 464, 130],
          '향후 요청·업무 상황을 보고 자동 선택하도록 개선', 14.5, '#52657D'),
      );
      return s;
    })();
    skillSlides[1] = (() => {
      const s = evalBase('SKILL PROCESS', '필요한 요청과 불필요한 요청을 검증한 뒤 등록');
      s.elements.push(
        textElement('s38-cap', [72, 198, 620, 22], '스킬 검증 상세 화면', 16, '#6C7482', true),
        ...daShot('s38-img', [72, 224, 620, 368], 'skill-validate.png'),
      );
      const steps = [
        ['01', '스킬 설명', '만들 스킬 내용을 한 문장으로 정의'],
        ['02', '검증 환경 준비', '실제 환경과 분리된 곳에 테스트 케이스 준비'],
        ['03', '동작 확인', '필요한 요청·불필요한 요청을 각각 테스트'],
        ['04', '스킬 등록', '검증을 통과한 스킬만 개인 스킬로 게시'],
      ];
      steps.forEach((step, i) => {
        const y = 226 + i * 92;
        s.elements.push(
          textElement(`s38-no-${i}`, [740, y, 36, 26], step[0], 14, '#2878D1', true),
          textElement(`s38-title-${i}`, [784, y, 424, 26], step[1], 17, '#101728', true),
          textElement(`s38-body-${i}`, [740, y + 30, 468, 44], step[2], 13.5, '#52657D'),
        );
        if (i < 3) s.elements.push({ kind: 'shape', geometry: 'line', bbox: [740, y + 80, 468, 0], lineColor: '#E4E9F0', lineWidth: 1, name: `s38-rule-${i}` });
      });
      daSlimNote(s, '등록된 스킬은 이후 여러 요청에 영향을 주므로, 잘못 실행되지 않는지 먼저 확인합니다');
      return s;
    })();
    skillSlides[2] = (() => {
      const s = evalBase('TEAM SKILL', '개인이 만든 업무 방식을 팀이 같은 절차로 실행');
      s.elements.push(
        textElement('s39-cap', [360, 190, 560, 22], '팀 스킬 공유 화면', 16, '#6C7482', true),
        ...daShot('s39-img', [360, 214, 560, 252], 'skill-team-share.png'),
      );
      const fx = [
        ['업무 표준화', '팀원이 같은 절차와 기준으로 업무를 처리'],
        ['중복 작업 감소', '이미 검증한 방식을 각자 다시 만들지 않음'],
        ['담당자 의존도 완화', '담당자가 바뀌어도 저장된 업무 절차 유지'],
      ];
      fx.forEach((f, i) => {
        const x = 72 + i * 390;
        s.elements.push({ kind: 'shape', geometry: 'rect', bbox: [x, 500, 356, 116], fillColor: '#EEF3FA', lineWidth: 0, name: `s39-fx-${i}` });
        s.elements.push(textElement(`s39-fx-t-${i}`, [x + 22, 514, 312, 28], f[0], 17, '#0C3F91', true));
        s.elements.push(textElement(`s39-fx-b-${i}`, [x + 22, 546, 312, 56], f[1], 13.5, '#52657D'));
      });
      return s;
    })();

    // ---- 원빈: 파싱·청킹·임베딩 (wonbin-deck-data.js 의 2~17장, 동일 스키마 그대로 주입) ----
    const W = window.WONBIN_DECK;
    const wonbinSlides = (W && Array.isArray(W.slides)) ? W.slides.slice(1, 17).map((w) => clone(w)) : [];
    if (!wonbinSlides.length) console.warn('[통합] WONBIN_DECK 를 찾지 못해 원빈 파싱 슬라이드가 빠졌습니다 (wonbin-deck-data.js 로드 확인).');

    // ---- 삽입 위치: base 요약 장표 뒤 (병존). 앵커의 마지막 등장 지점 기준 ----
    const anchorLastIndex = (labels) => {
      let idx = -1;
      deck.slides.forEach((s, i) => {
        if (s.elements.some((e) => /^(signal-label-|section-)/.test(e.name || '') && labels.includes((e.text || '').trim()))) idx = i;
      });
      return idx;
    };
    const agentAt = anchorLastIndex(['RUNTIME', 'AGENT PLATFORM']) + 1;
    const parsingAt = anchorLastIndex(['MULTIMODAL']) + 1;
    const skillAt = anchorLastIndex(['SKILL STATUS']) + 1;
    if (!agentAt || !parsingAt || !skillAt) {
      throw new Error(`[통합] 삽입 앵커를 찾지 못함 (agent=${agentAt}, parsing=${parsingAt}, skill=${skillAt}). base 덱 구조 변경 여부 확인.`);
    }
    // 인덱스가 큰 것부터 splice 해야 앞쪽 위치가 밀리지 않는다 (skillAt > parsingAt > agentAt).
    deck.slides.splice(skillAt, 0, skillDivider, ...skillSlides);
    deck.slides.splice(parsingAt, 0, ...wonbinSlides);
    deck.slides.splice(agentAt, 0, ...agentSlides);

    // ---- 전체 재번호 (base 의 page-/div-page- 규칙 재적용) ----
    deck.slides.forEach((item, index) => {
      item.number = index + 1;
      item.elements.forEach((element) => {
        if (/^(page-|div-page-)/.test(element.name || '')) {
          setElementText(element, String(index + 1).padStart(2, '0'));
        }
      });
    });
  })();

  // ===================================================================
  // 최종 편집 패스 1 — 삭제 지시만 반영 (합치기·문구수정·지훈 데크 이관은 이후 패스)
  //   렌더 순서에 의존하지 않도록 제목 텍스트 시그니처로 매칭한다.
  //   · 현재 렌더 기준 삭제: 14 / 16 17 18 / 20 / 24~32 / 50 51 52 53 54 55
  //   · 현재 49p(EVALUATION PLAN)는 슬라이드 골격만 남기고 본문을 비운다.
  // ===================================================================
  (() => {
    const norm = (v) => String(v || '').replace(/\s+/g, ' ').trim();
    const titleOf = (s) => {
      const t = s.elements.find((e) => /^(title-|div-title-)/.test(e.name || '') && norm(e.text));
      return t ? norm(t.text) : '';
    };

    // 49p → '플랫폼 평가' 골격만 남긴 빈 슬라이드 (수치는 이후 직접 채움)
    const evalPlan = deck.slides.find(
      (s) => titleOf(s) === norm('플랫폼 규칙을 먼저 통과한 뒤 응답 품질을 측정합니다'),
    );
    if (evalPlan) {
      removeContentArea(evalPlan);
      setElementText(evalPlan.elements.find((e) => e.name === 'title-48'), '플랫폼 평가');
      setElementText(evalPlan.elements.find((e) => e.name === 'sub-48'), '');
      setElementText(evalPlan.elements.find((e) => e.name === 'section-48'), 'EVALUATION');
      setElementText(evalPlan.elements.find((e) => e.name === 'signal-label-48'), 'EVALUATION');
      evalPlan.sources = [];
    }

    const drop = new Set([
      '배포 구성',
      'Deep Agent는 계획·위임·기억을 하나의 실행 루프로 연결합니다',
      '새 Agent는 정의·연결·버전 저장을 거쳐 Graph에 조립됩니다',
      'Query는 Graph 조립부터 근거 응답까지 통제된 순서로 실행됩니다',
      '에이전트 생성 파이프라인',
      '실행 과정을 숨기지 않고 단계별로 보여줍니다',
      'Versioning은 개발·검증·운영 설정을 분리합니다',
      '쓰기 호출별 승인·편집·거절',
      '쓰기 전에 멈추고, 같은 작업은 한 번만 실행합니다',
      '기준 문서가 프로젝트의 검색 범위를 결정합니다',
      'Docling을 선택했지만, 비정형 PDF는 그대로 쓰기 어려웠습니다',
      'Docling 기본 결과를 단계별 게이트로 보정합니다',
      '읽기 순서 보정은 문서 구조를 실제 순서로 복원합니다',
      '이미지는 설명과 메타데이터로 검색 문맥에 연결합니다',
      '평가는 기준선을 쌓고 실패를 다음 실행에 반영했습니다',
      '성공률보다 실패 원인이 다음 개선점을 만들었습니다',
      'Skill은 명시적으로 호출하고, 검증된 절차만 재사용합니다',
      '자연어 한 문장으로 Skill 초안을 시작합니다',
      '검증된 Skill은 개인·팀 카탈로그에서 관리합니다',
      '현재 동작과 다음 개선을 분리해 설명합니다',
    ].map(norm));

    const before = deck.slides.length;
    deck.slides = deck.slides.filter((s) => !drop.has(titleOf(s)));
    const removed = before - deck.slides.length;
    if (removed !== drop.size) {
      console.warn(`[삭제 패스] 예상 ${drop.size}장 중 ${removed}장만 제거됨 — 제목 시그니처 불일치 확인`);
    }

    deck.slides.forEach((item, index) => {
      item.number = index + 1;
      item.elements.forEach((element) => {
        if (/^(page-|div-page-)/.test(element.name || '')) {
          setElementText(element, String(index + 1).padStart(2, '0'));
        }
      });
    });
  })();

  // ===================================================================
  // 최종 편집 패스 2 — 합치기 · 문구 수정 (지훈 presentation.html 이관은 제외)
  //   렌더 순서에 의존하지 않도록 제목 텍스트로 슬라이드를 찾는다.
  //   A 4+7 합치기 / B 6+8 합치기 / C 5p But / D 11p 회색 제거
  //   E 04장 진입 영상+구조 재노출 / F 15p 핵심기술 전환 / G 17p 문구 / H 16p 삭제·아키텍처 통합
  //   I 왜 파서 / J layout 근거 / K 결과 제목 / L 검증+4문제 합치기 / M 네 보완 레이어
  //   N 읽기순서 레이어 라벨 / O 제목 오분류 / P 표 게이트 수치 %화 / Q 청킹+임베딩 합치기
  // ===================================================================
  (() => {
    const norm = (v) => String(v || '').replace(/\s+/g, ' ').trim();
    const titleOf = (s) => {
      const t = s.elements.find((e) => /^(title-|div-title-)/.test(e.name || '') && norm(e.text));
      return t ? norm(t.text) : '';
    };
    const find = (t) => deck.slides.find((s) => titleOf(s) === norm(t));
    const drop = (t) => { const s = find(t); if (s) deck.slides.splice(deck.slides.indexOf(s), 1); };
    const set = (s, name, value, opt) => setElementText(s && s.elements.find((e) => e.name === name), value, opt);
    const purge = (s, names) => { const k = new Set(names); s.elements = s.elements.filter((e) => !k.has(e.name)); };
    const bandEl = (name, bbox, fill) => ({ kind: 'shape', geometry: 'rect', bbox, fillColor: fill, lineWidth: 0, name });
    const hline = (name, x, y, w, color = '#D3DCE8') => ({ kind: 'shape', geometry: 'line', bbox: [x, y, w, 0], lineColor: color, lineWidth: 1, name });

    // ---- A. 시장 변화(4p) + 문제 정의(7p) 합치기 ----
    (() => {
      const s = find('AI Agent 도입은 늘지만, 실제 업무 적용은 아직 초기입니다');
      if (!s) return;
      removeContentArea(s);
      set(s, 'title-5', '시장은 AX로 가고 있지만, 두 가지 문제가 발목을 잡습니다');
      set(s, 'sub-5', '도입·실험은 빠르게 늘지만 실제 업무 확장은 더딥니다. 그 사이에 기업 현장의 두 문제가 있습니다.');
      set(s, 'signal-label-5', '시장 변화 · 문제 정의');
      s.elements.push(
        textElement('mm-stat-l', [74, 210, 210, 80], '62%', 58, '#2878D1', true),
        textElement('mm-copy-l', [292, 228, 300, 60], 'AI Agent 도입을\n검토·실험 중', 16, '#101728', true),
        textElement('mm-arrow', [600, 220, 90, 60], '→', 40, '#A6B4C7', false, 'center'),
        textElement('mm-stat-r', [706, 210, 210, 80], '23%', 58, '#17845E', true),
        textElement('mm-copy-r', [924, 228, 300, 60], '한 개 이상 업무에서\n확장 운영 중', 16, '#101728', true),
        textElement('mm-src', [74, 298, 1000, 18], '출처: McKinsey Global Survey on the state of AI, 2025', 10, '#7B8492'),
        hline('mm-div', 70, 338, 1138),
        panel('mm-p1', [72, 356, 560, 196], '#FFFFFF', '#D9DEE8'),
        textElement('mm-p1-no', [96, 372, 200, 24], '문제 1', 14, '#2878D1', true),
        textElement('mm-p1-t', [96, 400, 512, 32], '흩어진 정보와 작업 환경', 21, '#101728', true),
        textElement('mm-p1-b', [96, 442, 512, 96], '문서·웹·업무 시스템이 여러 곳에 분산되어\n필요한 정보를 한 번에 활용하기 어렵습니다.', 15, '#52657D'),
        panel('mm-p2', [648, 356, 560, 196], '#FFFFFF', '#D9DEE8'),
        textElement('mm-p2-no', [672, 372, 200, 24], '문제 2', 14, '#2878D1', true),
        textElement('mm-p2-t', [672, 400, 512, 32], '개인에게 머무는 업무 노하우', 21, '#101728', true),
        textElement('mm-p2-b', [672, 442, 512, 96], '업무 절차와 경험이 개인의 암묵지로 남아\n공유가 어렵고 신규 구성원의 학습이 오래 걸립니다.', 15, '#52657D'),
        bandEl('mm-bridge-bg', [72, 566, 1136, 50], '#0C3F91'),
        textElement('mm-bridge', [94, 566, 1092, 50], '시장은 AX로 가는데 이 두 문제가 실제 적용을 늦춥니다 — 그래서 이를 가능하게 하는 플랫폼을 만들고자 했습니다.', 14.5, '#FFFFFF', true, 'center'),
      );
    })();
    drop('기업 업무의 두 가지 문제에 주목했습니다');

    // ---- B. 프로젝트 출발(6p) + 해결 방향(8p) 합치기 ----
    (() => {
      const s = find('AX 흐름에서 시작한 HALIL');
      if (!s) return;
      removeContentArea(s);
      set(s, 'title-9', '두 문제를 HALIL은 이렇게 해결하려 했습니다');
      set(s, 'sub-9', '흩어진 정보는 연결로, 개인의 암묵지는 누구나 만드는 에이전트로 풉니다.');
      set(s, 'signal-label-9', '해결 방향');
      s.elements.push(
        textElement('sx-h0', [94, 200, 300, 24], '문제', 12, '#6E7A90', true),
        textElement('sx-h1', [420, 200, 430, 24], 'HALIL의 해결', 12, '#6E7A90', true),
        textElement('sx-h2', [880, 200, 330, 24], '방식', 12, '#6E7A90', true),
        bandEl('sx-r0', [72, 232, 1136, 150], '#EEF4FC'),
        textElement('sx-p0', [94, 254, 300, 110], '흩어진 정보', 20, '#101728', true),
        textElement('sx-s0', [420, 254, 440, 110], '커넥터와 MCP로 연결', 19, '#2878D1', true),
        textElement('sx-c0', [880, 254, 330, 110], '문서·웹·업무 도구를 한 곳에서 검색·활용', 14.5, '#52657D'),
        bandEl('sx-r1', [72, 410, 1136, 150], '#F4F6F9'),
        textElement('sx-p1', [94, 432, 300, 110], '개인 암묵지', 20, '#101728', true),
        textElement('sx-s1', [420, 432, 440, 110], '누구나 만드는 에이전트', 19, '#2878D1', true),
        textElement('sx-c1', [880, 432, 330, 110], '커넥터·MCP로 데이터 소스를 받아, 개발자·비개발자 모두 자신의 노하우를 담은 에이전트를 만들고 결과를 확인', 14.5, '#52657D'),
        textElement('sx-close', [74, 586, 1134, 28], '흩어진 정보와 개인의 업무 방식을 하나의 업무 흐름으로 연결한 플랫폼이 HALIL입니다.', 13.5, '#52657D', false, 'center'),
      );
    })();
    drop('정보는 연결, 업무 방식은 스킬로');

    // ---- C. 선도 서비스(5p) — GLEAN·Copilot도 겨냥, "But" ----
    (() => {
      const s = find('먼저 나선 서비스들은 같은 방향으로 수렴합니다');
      if (s) set(s, 'market-case-takeaway',
        'GLEAN · Copilot Studio 같은 서비스도 같은 문제를 겨냥합니다\n다만 우리는 기업 현장의 실제 업무를, 비개발자가 직접 만들고 검증하는 데 집중했습니다', { fontSize: 16 });
    })();

    // ---- D. 구현 과정(11p) — 회색 상세 텍스트 제거 ----
    (() => {
      const s = find('설계에서 운영 검증까지의 구현 과정');
      if (s) purge(s, ['sub-14', 'time-detail-14-0', 'time-detail-14-1', 'time-detail-14-2', 'time-detail-14-3', 'time-detail-14-4', 'time-detail-14-5']);
    })();

    // ---- E. 04장 진입: 시연 영상 + 시스템 구조 재노출 ----
    (() => {
      const dIdx = deck.slides.findIndex((s) => titleOf(s) === '프로젝트 수행 결과' && s.elements.some((e) => /^div-title-/.test(e.name || '')));
      if (dIdx < 0) return;
      const videoSlide = {
        background: '#F7F6F1',
        elements: [
          { kind: 'shape', geometry: 'rect', bbox: [0, 0, 1280, 5], fillColor: '#F8C944', lineWidth: 0, name: 'top-accent-16' },
          { kind: 'shape', geometry: 'straightConnector1', bbox: [56, 38, 1168, 0], lineColor: '#D9DEE8', lineWidth: 1, name: 'top-rule-16' },
          textElement('context-16', [96, 44, 378, 30], 'halil   ·   04 프로젝트 수행 결과', 13, '#0A1020', true),
          textElement('page-16', [1160, 44, 62, 30], '13', 13, '#6C7482', true, 'right'),
          textElement('title-16', [58, 92, 1160, 58], '플랫폼 시연 영상', 40, '#0A1020', true),
          panel('demo2-frame', [60, 166, 1160, 486], '#071426', '#26364B'),
          videoElement('demo2-player', [66, 172, 1148, 474], 'media/halil_프로젝트_운영_AI_시연영상_v21_챕터카드_자막.mp4'),
          { kind: 'shape', geometry: 'rect', bbox: [58, 693, 78, 4], fillColor: '#2878D1', lineWidth: 0, name: 'accent-16' },
          { kind: 'image', bbox: [1019.56, 680, 78.89, 25], media: 'image2.png', name: 'inst-logo-a-13' },
          { kind: 'image', bbox: [1138.95, 680, 84.09, 25], media: 'image3.png', name: 'inst-logo-b-13' },
        ],
        sources: ['media/halil_프로젝트_운영_AI_시연영상_v21_챕터카드_자막.mp4'],
      };
      const archSlide = clone(find('UI부터 실행·통제까지 연결된 시스템 구조'));
      if (archSlide) set(archSlide, 'context-16', 'halil   ·   04 프로젝트 수행 결과');
      deck.slides.splice(dIdx + 1, 0, ...(archSlide ? [videoSlide, archSlide] : [videoSlide]));
    })();

    // ---- F. AGENT LIFECYCLE(15p) → 핵심 기술 전환 슬라이드 ----
    (() => {
      const s = find('에이전트 생성과 사용자 질의 요청');
      if (!s) return;
      purge(s, ['s16-create-name', 's16-query-name', 's16-create-img', 's16-query-img', 's16-create-frame', 's16-query-frame', 's16-flow-label', 's16-flow-arrow']);
      set(s, 'title-16', '이제, 이 흐름을 가능하게 한 핵심 기술입니다');
      set(s, 'section-16', 'CORE TECHNOLOGY');
      set(s, 'signal-label-16', 'CORE TECHNOLOGY');
      s.elements.push(
        textElement('frm-lead', [80, 236, 1120, 110], '방금 보신 것처럼, HALIL은 문서와 도구를 연결하고 · Agent를 만들고 · 실제 업무 요청을 수행합니다.', 21, '#20283A'),
        panel('frm-q-bg', [80, 388, 1120, 168], '#EEF4FC', '#2878D1'),
        textElement('frm-q', [112, 412, 1056, 120], 'Agent가 Tool을 선택하고 실행하고, 실패하면 다시 판단하고,\n필요하면 다른 Agent에게 위임하는 이 흐름 — 누가 관리하는가?', 20, '#0C3F91', true),
      );
    })();

    // ---- G. AGENT HARNESS(17p) 문구 ----
    (() => {
      const s = find('Deep Agent는 에이전트 실행 하네스입니다');
      if (s) set(s, 's19-note-copy', '이 판단–실행–재시도 흐름을 관리하는 구조가 Agent Harness이며, 프로젝트에서는 LangChain Deep Agents를 활용했습니다.');
    })();

    // ---- H. REQUEST PIPELINE(16p) 삭제 → AGENT RUNTIME(18p)에 아키텍처 통합 ----
    drop('요청 도착부터 실행까지 파이프라인');
    (() => {
      const s = find('Deep Agent 실행 구조 전체 도면');
      if (!s) return;
      const c = s.elements.find((e) => e.name === 's20-canvas');
      const d = s.elements.find((e) => e.name === 's20-diagram');
      if (c) c.bbox = [150, 214, 980, 428];
      if (d) d.bbox = [160, 224, 960, 408];
      s.elements.push(textElement('rt-cap', [58, 158, 1160, 44],
        'Agent Harness / Deep Agent — 판단·실행·재시도·위임을 관리하는 이 구조가 플랫폼의 핵심 뼈대입니다.', 14.5, '#52657D', false, 'center'));
    })();

    // ---- I. WHY DOCLING(19p) — 파서를 쓰는 이유로 재프레이밍 ----
    (() => {
      const s = find('왜 도클링인가');
      if (!s) return;
      set(s, 'title-2', '엔터프라이즈가 파서를 쓰는 이유');
      set(s, 'sub-2', '다양한 형식의 문서를 검색 가능한 구조로 바꾸려면 파서가 필요합니다. 그중 커뮤니티가 가장 큰 프로젝트가 Docling입니다.');
    })();

    // ---- J. BASE PIPELINE(20p) — Layout 단계 집중 근거 ----
    (() => {
      const s = find('PDF는 12단계를 거쳐 DoclingDocument가 됩니다');
      if (!s) return;
      const pl = s.elements.find((e) => e.name === 'plabel-3');
      if (pl) pl.bbox = [58, 516, 1100, 20];
      s.elements.push(
        panel('bp-note-bg', [58, 542, 1160, 72], '#FFF4E6', '#F0D9B8'),
        textElement('bp-note', [80, 548, 1120, 60],
          '집중한 단계는 Layout입니다. Docling Layout 모델은 논문·정형 문서로 학습돼 형식이 다양한 문서에서는 정확도가 떨어집니다. 기업 문서는 정형만 있지 않기에 자유도가 높은 브로슈어 문서로 개선했습니다.',
          13, '#8A5A1A', false, 'center'),
      );
    })();

    // ---- K. PARSED RESULT(21p) 제목 ----
    (() => { const s = find('실제 파싱 결과 예시'); if (s) set(s, 'title-4', 'Docling 기본 파이프라인의 실제 결과'); })();

    // ---- L. VALIDATION(22p) + FOUR ISSUES(23p) 합치기 ----
    (() => {
      const s = find('206개 문서로 파싱 정확도를 검증했습니다');
      if (!s) return;
      removeContentArea(s);
      set(s, 'title-5', '206개 문서로 검증해 보니, Docling만으로는 부족했습니다');
      set(s, 'section-5', 'VALIDATION · ISSUES');
      set(s, 'foot-5', 'VALIDATION · ISSUES');
      // 이미지(좌) + 목록(우) 그룹을 슬라이드 가로 중앙에 배치.
      const IW = 348, IH = 428, LW = 512, GAP = 76;
      const GX = 58 + (1160 - (IW + GAP + LW)) / 2; // 그룹 좌측 시작
      const LX = GX + IW + GAP;                     // 목록 좌측 시작
      const IY = 214;

      s.elements.push(textElement('vi-lead', [GX, 178, 1160 - (GX - 58) * 2, 22],
        '정형 문서는 안정적이었지만 브로슈어형 PDF에서 정확도가 크게 낮아졌고, 네 가지 문제가 반복됐습니다.', 13.5, '#20283A'));

      // 좌측: 실제 검증에 쓴 브로슈어형 PDF (좌측 절반 크롭) — 복잡한 다단·혼합 레이아웃 예시
      s.elements.push(
        { kind: 'shape', geometry: 'rect', bbox: [GX - 1, IY - 1, IW + 2, IH + 2], fillColor: 'transparent', lineColor: '#C9D3E0', lineWidth: 1, name: 'vi-img-frame' },
        imageElement('vi-img', [GX, IY, IW, IH], 'pdf_sample_left.png', 'cover'),
        textElement('vi-img-cap', [GX, IY + IH + 6, IW + 40, 18], '검증에 사용한 브로슈어형 PDF 예시 (한화파워)', 10, '#8792A6'),
      );

      // 우측: 네 가지 문제 목록 (번호 + 제목 한 줄, 설명 아래 줄)
      [
        ['01', '읽기 순서 오류', '문장을 잘못된 순서로 연결해 원래 의미와 다른 결과가 됩니다'],
        ['02', '제목 미검출', '제목이 다른 문서 요소로 분류돼 섹션 경계가 사라집니다'],
        ['03', '표 오검출 및 구조 붕괴', '표가 아닌 영역을 표로 인식하거나 행·열·셀 관계가 깨집니다'],
        ['04', '이미지 설명 부족', '이미지의 의미가 검색 데이터에 충분히 반영되지 않습니다'],
      ].forEach((r, i) => {
        const y = 236 + i * 106;
        s.elements.push(
          hline(`vi-div-${i}`, LX, y - 20, LW, '#E1E6EE'),
          textElement(`vi-no-${i}`, [LX, y, 46, 26], r[0], 17, '#2878D1', true),
          textElement(`vi-t-${i}`, [LX + 48, y - 2, LW - 48, 28], r[1], 18, '#0A1020', true),
          textElement(`vi-d-${i}`, [LX + 48, y + 30, LW - 48, 44], r[2], 13.5, '#52657D'),
        );
      });
    })();
    drop('문서 파싱 결과에서 확인된 네 가지 문제');

    // ---- M. LAYER DESIGN(22p) — 21p 와 반대 배치: 설명(좌) + 네이티브 다이어그램(우) ----
    (() => {
      const s = find('네 개의 보완 레이어');
      if (!s) return;
      purge(s, ['pn-7-0', 'pt-7-0', 'pd-7-0', 'pn-7-1', 'pt-7-1', 'pd-7-1', 'pn-7-2', 'pt-7-2', 'pd-7-2']);
      s.elements = s.elements.filter((e) => e.name !== 'img-7'); // diagram_layers_overview.svg 제거

      // 그룹(설명+다이어그램)을 가로 중앙에 배치. 21p 와 좌우만 반대.
      const LW = 480, DW = 400, GAP = 60;
      const LX = 58 + (1160 - (LW + GAP + DW)) / 2; // 설명 좌측
      const DX = LX + LW + GAP;                     // 다이어그램 좌측

      // 좌측: 설명 목록 — 21p(vi-*) 와 동일 양식
      [
        ['01', '읽기 순서 보완', '화면 좌표를 비교해 인접 요소의 뒤바뀐 순서만 교정합니다'],
        ['02', '제목 추출 보완', 'list_item을 조건부로 section_header로 승격해 섹션 경계를 복원합니다'],
        ['03', '표 판별 (Table Gate)', '표가 아닌 디자인을 규칙으로 걸러 오검출을 제거합니다'],
        ['04', '이미지 설명 보완', 'VLM과 문맥 우선순위로 검색용 이미지 설명을 생성합니다'],
      ].forEach((r, i) => {
        const y = 236 + i * 106;
        s.elements.push(
          hline(`ld-div-${i}`, LX, y - 20, LW, '#E1E6EE'),
          textElement(`ld-no-${i}`, [LX, y, 46, 26], r[0], 17, '#2878D1', true),
          textElement(`ld-t-${i}`, [LX + 48, y - 2, LW - 48, 28], r[1], 18, '#0A1020', true),
          textElement(`ld-d-${i}`, [LX + 48, y + 30, LW - 48, 44], r[2], 13.5, '#52657D'),
        );
      });

      // 우측: 보완 파이프라인 네이티브 다이어그램 (DoclingDocument → 4레이어 → 최종)
      const box = (name, y, h, title, sub, fill, lc) => {
        s.elements.push({ kind: 'shape', geometry: 'roundRect', bbox: [DX, y, DW, h], fillColor: fill, lineColor: lc, lineWidth: 1.5, name });
        s.elements.push(textElement(`${name}-t`, [DX + 16, sub ? y + 8 : y, DW - 32, sub ? 22 : h], title, 13.5, '#0A1020', true, 'center'));
        if (sub) s.elements.push(textElement(`${name}-s`, [DX + 16, y + 30, DW - 32, 18], sub, 10.5, '#52657D', false, 'center'));
      };
      const arrow = (i, y) => s.elements.push(textElement(`dg-a${i}`, [DX + DW / 2 - 12, y, 24, 20], '↓', 15, '#98A2B3', true, 'center'));

      s.elements.push(textElement('dg-kick', [DX, 186, DW, 20], '보완 파이프라인', 12, '#52657D', true));
      let y = 214;
      box('dg-head', y, 54, 'DoclingDocument', 'Docling 변환 직후', '#F2F4F7', '#667085'); y += 54;
      const layers = [
        ['dg-l0', '읽기 순서 보완', '#EAF2FF', '#155EEF'],
        ['dg-l1', '제목 추출 보완', '#F4EBFF', '#7F56D9'],
        ['dg-l2', '표 판별 (Table Gate)', '#FFF4E5', '#F79009'],
        ['dg-l3', '이미지 설명 보완', '#E6F9FB', '#06AED4'],
      ];
      layers.forEach(([nm, t, fill, lc], i) => {
        arrow(i, y + 4); y += 26;
        box(nm, y, 44, t, '', fill, lc); y += 44;
      });
      arrow(4, y + 4); y += 26;
      box('dg-foot', y, 54, '최종 DoclingDocument', '네 보완이 모두 반영됨', '#F2F4F7', '#667085');
    })();

    // ---- N. 읽기 순서 사례(25p) — 보완 레이어 라벨 ----
    (() => {
      const s = find('읽기 순서가 뒤바뀐 실제 사례');
      if (s) { set(s, 'section-8', 'LAYER 01 · READING ORDER'); set(s, 'foot-8', 'LAYER 01 · READING ORDER'); }
    })();

    // ---- O. 제목 추출(26·27p) — 오분류 프레이밍 ----
    (() => {
      const s = find('한화 브로슈어에서 확인된 오분류');
      if (s) { set(s, 'section-10', 'HEADING · 오분류 사례'); set(s, 'foot-10', 'HEADING · 오분류 사례'); }
    })();
    (() => {
      const s = find('list_item을 section_header로 승격하는 조건');
      if (s) { set(s, 'title-11', '제목 오분류를 바로잡는 승격 조건'); set(s, 'section-11', 'HEADING · 보정 로직'); set(s, 'foot-11', 'HEADING · 보정 로직'); }
    })();

    // ---- P. 표 게이트 사례(29p) — 건수를 %로 ----
    (() => {
      const s = find('표로 오인식된 비표 사례');
      if (!s) return;
      set(s, 'sv-12-0', '100%'); set(s, 'sl-12-0', '전체 TableItem 대조 (28,885건)');
      set(s, 'sv-12-1', '0.46%'); set(s, 'sl-12-1', '확실한 비표로 확정 제거 (134건)');
      set(s, 'sv-12-2', '0%'); set(s, 'sl-12-2', '실제 표를 잘못 제거 (0건)');
    })();

    // ---- Q. CHUNKING 직렬화(33p) + 임베딩(34p) 합치기 ----
    (() => {
      const s = find('계층 구조를 유지한 채 직렬화합니다');
      if (!s) return;
      removeContentArea(s);
      set(s, 'title-16', '계층 구조를 유지해 직렬화하고 EmbeddingGemma로 임베딩합니다');
      set(s, 'sub-16', '파싱 데이터를 일직선으로 직렬화한 뒤, 같은 tokenizer로 자르고 임베딩합니다');
      set(s, 'section-16', 'CHUNKING · 임베딩');
      set(s, 'foot-16', 'CHUNKING · 임베딩');
      const EW = 362, EG = [58, 58 + EW + 24, 58 + 2 * (EW + 24)]; // 임베딩 3열
      s.elements.push(
        textElement('ck-s-h', [58, 232, 700, 24], '직렬화', 15, '#2878D1', true),
        textElement('ck-s-b', [58, 266, 1124, 66],
          '텍스트·표·목록·제목은 Docling 기본 시리얼라이저를 그대로 사용하고, 그림만 커스텀 시리얼라이저를 만들었습니다. 승인된 VLM 설명이 있으면 그 설명 텍스트만 임베딩 대상으로 쓰고, 없으면 Docling 기본 그림·메타데이터 시리얼라이저로 대체합니다.',
          15, '#20283A', false, 'left'),
        hline('ck-div', 58, 360, 1124, '#E1E6EE'),
        textElement('ck-e-h', [58, 384, 700, 24], '임베딩', 15, '#2878D1', true),
        panel('ck-c-0', [EG[0], 424, EW, 120], '#F5F7FA', '#E4E8EF'),
        panel('ck-c-1', [EG[1], 424, EW, 120], '#F5F7FA', '#E4E8EF'),
        panel('ck-c-2', [EG[2], 424, EW, 120], '#F5F7FA', '#E4E8EF'),
        textElement('ck-v-0', [EG[0] + 22, 446, EW - 44, 30], 'embeddinggemma-300m', 18, '#2878D1', true),
        textElement('ck-l-0', [EG[0] + 22, 482, EW - 44, 50], '임베딩 모델', 12.5, '#6C7482'),
        textElement('ck-v-1', [EG[1] + 22, 446, EW - 44, 30], '768차원', 18, '#2878D1', true),
        textElement('ck-l-1', [EG[1] + 22, 482, EW - 44, 50], '임베딩 벡터 크기', 12.5, '#6C7482'),
        textElement('ck-v-2', [EG[2] + 22, 446, EW - 44, 30], '512 토큰', 18, '#2878D1', true),
        textElement('ck-l-2', [EG[2] + 22, 482, EW - 44, 50], '청크 상한 (모델 최대 2,048토큰 중 보수적 설정)', 12.5, '#6C7482'),
        textElement('ck-note', [58, 566, 1124, 24],
          '토큰 계산에도 임베딩과 같은 모델의 tokenizer를 사용합니다 — 자를 때와 임베딩할 때 기준이 다르면 상한이 무의미해지기 때문입니다.', 11, '#8792A6', false, 'center'),
      );
    })();
    drop('EmbeddingGemma로 토큰을 계산하고 임베딩합니다');

    deck.slides.forEach((item, index) => {
      item.number = index + 1;
      item.elements.forEach((element) => {
        if (/^(page-|div-page-)/.test(element.name || '')) {
          setElementText(element, String(index + 1).padStart(2, '0'));
        }
      });
    });
  })();

  // ===================================================================
  // 최종 편집 패스 3 — 5·6p 순서 교체, 34~40p·43·44p 삭제
  // ===================================================================
  (() => {
    const norm = (v) => String(v || '').replace(/\s+/g, ' ').trim();
    const titleOf = (s) => {
      const t = s.elements.find((e) => /^(title-|div-title-)/.test(e.name || '') && norm(e.text));
      return t ? norm(t.text) : '';
    };
    const at = (t) => deck.slides.findIndex((s) => titleOf(s) === norm(t));

    // 5p(선도 서비스) ↔ 6p(HALIL 해결) 순서 교체
    const a = at('먼저 나선 서비스들은 같은 방향으로 수렴합니다');
    const b = at('두 문제를 HALIL은 이렇게 해결하려 했습니다');
    if (a >= 0 && b >= 0) {
      const tmp = deck.slides[a];
      deck.slides[a] = deck.slides[b];
      deck.slides[b] = tmp;
    }

    // 34~40p(스킬 3장 + 운영·보안·확장 + 시연 흐름), 43·44p(향후 과제·자체 평가) 삭제
    const dropSet = new Set([
      '검증한 Skill만 등록해 반복 업무에 재사용',
      '필요한 요청과 불필요한 요청을 검증한 뒤 등록',
      '개인이 만든 업무 방식을 팀이 같은 절차로 실행',
      '운영 정책과 실행 이력을 제품과 분리해 관리합니다',
      '제품과 운영의 통제 경계',
      '연동과 확장 지점',
      '시연은 구성·근거·승인의 한 흐름으로 진행합니다',
      '다음 단계는 근거 정밀도·라우팅·운영 검증입니다',
      '강점은 연결성, 남은 과제는 검증 범위입니다',
    ].map(norm));
    const before = deck.slides.length;
    deck.slides = deck.slides.filter((s) => !dropSet.has(titleOf(s)));
    if (before - deck.slides.length !== dropSet.size) {
      console.warn(`[패스3] 예상 ${dropSet.size}장 중 ${before - deck.slides.length}장만 삭제됨 — 제목 시그니처 확인`);
    }

    deck.slides.forEach((item, index) => {
      item.number = index + 1;
      item.elements.forEach((element) => {
        if (/^(page-|div-page-)/.test(element.name || '')) {
          setElementText(element, String(index + 1).padStart(2, '0'));
        }
      });
    });
  })();

  // ===================================================================
  // 최종 편집 패스 4 — 지훈 presentation.html 49·50p(= deep_agent_deck 7·8:
  //   "등록 검증" · "스킬 사용 전후 비교")를 34p(DEMO RESULT) 뒤에 이미지로 추가.
  //   원본이 별도 HTML/CSS 프레임워크라 렌더 그대로 캡처해 full-bleed 이미지로 삽입.
  // ===================================================================
  (() => {
    const norm = (v) => String(v || '').replace(/\s+/g, ' ').trim();
    const titleOf = (s) => {
      const t = s.elements.find((e) => /^(title-|div-title-)/.test(e.name || '') && norm(e.text));
      return t ? norm(t.text) : '';
    };
    const at = deck.slides.findIndex((s) => titleOf(s) === norm('전체 기능은 실제 시연 영상으로 확인합니다'));
    if (at < 0) { console.warn('[패스4] DEMO RESULT 슬라이드를 찾지 못함'); return; }
    const shot = (name, media) => ({
      background: '#F7F6F1',
      elements: [imageElement(name, [0, 0, 1280, 720], media, 'contain')],
      sources: ['docs/발표자료/최종발표/halil_html - 지훈/presentation.html (49·50p)',
        'docs/발표자료/최종발표/Jihun_발표준비/deep_agent_deck.html (slide 7·8)'],
    });
    deck.slides.splice(at + 1, 0,
      shot('jihun-skill-eval', 'jihun-skill-eval.png'),
      shot('jihun-skill-compare', 'jihun-skill-compare.png'),
    );

    deck.slides.forEach((item, index) => {
      item.number = index + 1;
      item.elements.forEach((element) => {
        if (/^(page-|div-page-)/.test(element.name || '')) {
          setElementText(element, String(index + 1).padStart(2, '0'));
        }
      });
    });
  })();

  // ===================================================================
  // 최종 편집 패스 5 — halil_html_ops_4pages(운영 콘솔 4장, 동일 스키마)를
  //   36p("스킬 사용 전후 비교") 뒤에 네이티브로 추가. (ops-4pages-data.js 필요)
  // ===================================================================
  (() => {
    const src = window.HALIL_OPS_SLIDES;
    if (!Array.isArray(src) || !src.length) { console.warn('[패스5] HALIL_OPS_SLIDES 미로드 — ops-4pages-data.js 확인'); return; }
    const norm = (v) => String(v || '').replace(/\s+/g, ' ').trim();
    const titleOf = (s) => {
      const t = s.elements.find((e) => /^(title-|div-title-)/.test(e.name || '') && norm(e.text));
      return t ? norm(t.text) : '';
    };
    let at = deck.slides.findIndex((s) => s.elements.some((e) => e.name === 'jihun-skill-compare'));
    if (at < 0) at = deck.slides.findIndex((s) => titleOf(s) === norm('전체 기능은 실제 시연 영상으로 확인합니다')) + 2;
    if (at < 1) { console.warn('[패스5] 삽입 기준 슬라이드를 찾지 못함'); return; }
    deck.slides.splice(at + 1, 0, ...src.map((s) => clone(s)));

    deck.slides.forEach((item, index) => {
      item.number = index + 1;
      item.elements.forEach((element) => {
        if (/^(page-|div-page-)/.test(element.name || '')) {
          setElementText(element, String(index + 1).padStart(2, '0'));
        }
      });
    });
  })();

  // ===================================================================
  // 최종 편집 패스 6 — halil_html_agent_v2 21~27p(평가 섹션 7장, 동일 스키마)로
  //   비어 있던 '플랫폼 평가' 자리표시자(패스1의 title-48 슬라이드)를 교체.
  //   (agent-v2-eval-data.js 필요)
  // ===================================================================
  (() => {
    const src = window.HALIL_AGENTV2_SLIDES;
    if (!Array.isArray(src) || !src.length) { console.warn('[패스6] HALIL_AGENTV2_SLIDES 미로드 — agent-v2-eval-data.js 확인'); return; }
    const at = deck.slides.findIndex((s) => s.elements.some((e) => e.name === 'title-48'));
    if (at < 0) { console.warn('[패스6] 플랫폼 평가 자리표시자를 찾지 못함'); return; }
    deck.slides.splice(at, 1, ...src.map((s) => clone(s)));

    deck.slides.forEach((item, index) => {
      item.number = index + 1;
      item.elements.forEach((element) => {
        if (/^(page-|div-page-)/.test(element.name || '')) {
          setElementText(element, String(index + 1).padStart(2, '0'));
        }
      });
    });
  })();

  // ===================================================================
  // 최종 편집 패스 7 — '사용자 편의 기능' 챕터 표지(내용 슬라이드는 패스3에서 삭제됨)
  //   와 지훈 '등록 검증' 이미지 슬라이드 삭제.
  // ===================================================================
  (() => {
    const norm = (v) => String(v || '').replace(/\s+/g, ' ').trim();
    const before = deck.slides.length;
    deck.slides = deck.slides.filter((s) => {
      const isConvDivider = s.elements.some((e) => /^div-title-/.test(e.name || '') && norm(e.text) === '사용자 편의 기능');
      const isSkillEvalImg = s.elements.some((e) => e.name === 'jihun-skill-eval');
      return !isConvDivider && !isSkillEvalImg;
    });
    if (before - deck.slides.length !== 2) {
      console.warn(`[패스7] 예상 2장 중 ${before - deck.slides.length}장만 삭제됨`);
    }

    deck.slides.forEach((item, index) => {
      item.number = index + 1;
      item.elements.forEach((element) => {
        if (/^(page-|div-page-)/.test(element.name || '')) {
          setElementText(element, String(index + 1).padStart(2, '0'));
        }
      });
    });
  })();

  // ===================================================================
  // 최종 편집 패스 8 — 15p(패스2에서 만든 'CORE TECHNOLOGY' 전환 슬라이드)를
  //   halil_html_agent_v2 16p(AGENT LIFECYCLE: 에이전트 생성과 사용자 질의 요청)로 교체.
  //   (agent-v2-lifecycle-data.js 필요)
  // ===================================================================
  (() => {
    const s16 = window.HALIL_AGENTV2_S16;
    if (!s16 || !Array.isArray(s16.elements)) { console.warn('[패스8] HALIL_AGENTV2_S16 미로드 — agent-v2-lifecycle-data.js 확인'); return; }
    const at = deck.slides.findIndex((s) => s.elements.some((e) => e.name === 'frm-q'));
    if (at < 0) { console.warn('[패스8] 핵심기술 전환 슬라이드를 찾지 못함'); return; }
    deck.slides.splice(at, 1, clone(s16));

    deck.slides.forEach((item, index) => {
      item.number = index + 1;
      item.elements.forEach((element) => {
        if (/^(page-|div-page-)/.test(element.name || '')) {
          setElementText(element, String(index + 1).padStart(2, '0'));
        }
      });
    });
  })();

  // ===================================================================
  // 최종 편집 패스 9 — '스킬 사용 전후 비교' 풀블리드 이미지 슬라이드를
  //   통합 덱 디자인(표준 헤더·타이틀·범례 + 흰 프레임)으로 재구성.
  //   ※ 표 자체와 표 색은 손대지 않음 — 원본 캡처에서 표 영역만 잘라 그대로 배치.
  // ===================================================================
  (() => {
    const at = deck.slides.findIndex((s) => s.elements.some((e) => e.name === 'jihun-skill-compare'));
    if (at < 0) { console.warn('[패스9] 스킬 비교 이미지 슬라이드를 찾지 못함'); return; }
    const chrome = (n) => [
      { kind: 'shape', geometry: 'rect', bbox: [0, 0, 1280, 5], fillColor: '#F8C944', lineWidth: 0, name: `top-accent-${n}` },
      { kind: 'shape', geometry: 'line', bbox: [56, 38, 1168, 0], lineColor: '#D9DEE8', lineWidth: 1, name: `top-rule-${n}` },
      textElement(`context-${n}`, [58, 48, 416, 28], 'halil   ·   04 프로젝트 수행 결과', 13, '#0A1020'),
      textElement(`section-${n}`, [504, 51, 420, 22], 'SKILL COMPARISON', 12, '#6C7482'),
      textElement(`page-${n}`, [1160, 50, 62, 22], String(n), 12, '#6C7482', false, 'right'),
      { kind: 'shape', geometry: 'rect', bbox: [58, 660, 78, 4], fillColor: '#2878D1', lineWidth: 0, name: `signal-${n}` },
      textElement(`signal-label-${n}`, [150, 651, 470, 22], 'SKILL COMPARISON', 12, '#6C7482'),
      imageElement('sc-logo-a', [1019.56, 647, 78.89, 25], 'image2.png', 'contain'),
      imageElement('sc-logo-b', [1138.95, 647, 84.09, 25], 'image3.png', 'contain'),
    ];
    deck.slides.splice(at, 1, {
      background: '#F7F6F1',
      elements: [
        ...chrome(40),
        textElement('title-40', [58, 92, 860, 58], '스킬 사용 전후 비교', 34, '#0A1020', true),
        textElement('sub-40', [60, 158, 720, 26], '300회 구성 · 5개 스킬 × 10개 업무 × 3회 반복 × 2가지 방법', 13, '#6C7482'),
        textElement('sc-stat-label', [740, 148, 480, 18], '결과 요구사항 충족', 11, '#7B8492', false, 'right'),
        textElement('sc-stat', [740, 166, 480, 32], '274 / 300  ·  91.3%', 20, '#2878D1', true, 'right'),
        textElement('sc-lg-0', [72, 202, 1140, 24], '·  사용자 입력 토큰 — 사용자가 직접 작성한 요청의 길이', 13, '#52657D'),
        textElement('sc-lg-1', [72, 228, 1140, 24], '·  실제 모델 입력 토큰 — 저장된 Skill 지침까지 포함해 모델이 읽은 전체 길이', 13, '#52657D'),
        textElement('sc-lg-2', [72, 254, 1140, 24], '·  결과 품질 — 필수 내용·표현·의미 기준을 모두 지킨 실행 수와 비율', 13, '#52657D'),
        panel('sc-table-frame', [113, 286, 1054, 360], '#FFFFFF', '#D9DEE8'),
        imageElement('sc-table', [121, 294, 1038, 344], 'skill-compare-table.png', 'contain'),
      ],
      sources: ['docs/발표자료/최종발표/Jihun_발표준비/deep_agent_deck.html (slide 8) — 표 영역만 사용'],
    });

    deck.slides.forEach((item, index) => {
      item.number = index + 1;
      item.elements.forEach((element) => {
        if (/^(page-|div-page-)/.test(element.name || '')) {
          setElementText(element, String(index + 1).padStart(2, '0'));
        }
      });
    });
  })();

  function byNameFor(targetSlide, name, value, options) {
    setElementText(targetSlide.elements.find((element) => element.name === name), value, options);
  }

  // ===================================================================
  // 최종 편집 패스 10 — '설계에서 운영 검증까지의 구현 과정'(SCHEDULE 타임라인)을
  //   02장 팀 구성 뒤 → 03장 '프로젝트 수행 절차 및 방법' 챕터 표지 바로 뒤로 이동.
  // ===================================================================
  (() => {
    const norm = (v) => String(v || '').replace(/\s+/g, ' ').trim();
    const isCh03Cover = (s) => s.elements.some(
      (e) => /^div-title-/.test(e.name || '') && norm(e.text) === '프로젝트 수행 절차 및 방법',
    );
    const from = deck.slides.findIndex((s) => s.elements.some((e) => e.name === 'phase-band-14-0'));
    if (from < 0) { console.warn('[패스10] 구현 과정 타임라인 슬라이드를 찾지 못함'); return; }
    if (deck.slides.findIndex(isCh03Cover) < 0) { console.warn('[패스10] 03장 챕터 표지를 찾지 못함'); return; }

    const [moved] = deck.slides.splice(from, 1);
    deck.slides.splice(deck.slides.findIndex(isCh03Cover) + 1, 0, moved);
    // 챕터가 바뀌었으므로 컨텍스트 헤더를 03장으로 교정.
    byNameFor(moved, 'context-14', 'halil   ·   03 프로젝트 수행 절차 및 방법');

    deck.slides.forEach((item, index) => {
      item.number = index + 1;
      item.elements.forEach((element) => {
        if (/^(page-|div-page-)/.test(element.name || '')) {
          setElementText(element, String(index + 1).padStart(2, '0'));
        }
      });
    });
  })();

  // ===================================================================
  // 최종 편집 패스 10.5 — juyeon 변형 덱(halil_html_통합__에이전트_0902)의
  //   15·16·17·32·33·34·35·36·37·38·40p 본문을 그대로 이식.
  //   크롬·제목은 내 덱 것을 유지(패스11 크롬 통일, 패스13 제목이 뒤에서 처리).
  //   대상 슬라이드는 이식 시점의 현재 제목으로 매칭한다.
  // ===================================================================
  (() => {
    const J = window.HALIL_JUYEON_SLIDES;
    if (!J) { console.warn('[juyeon 이식] HALIL_JUYEON_SLIDES 미로드 — juyeon-slides.js 확인'); return; }
    const norm = (v) => String(v || '').replace(/\s+/g, ' ').trim();
    const KEEP = /^(top-accent|top-rule|context-|section-|page-|signal-|signal-label-|foot-|title-|div-)/;
    const MAP = {
      '에이전트 생성과 사용자 질의 요청': '15',
      'Deep Agent는 에이전트 실행 하네스입니다': '16',
      'Deep Agent 실행 구조 전체 도면': '17',
      '판정 계약은 세 층으로 나눠 적용했다': '32',
      '플랫폼 평가': '33',
      '기본 동작 10가지, 재검증까지 포함해 10/10 최종 통과': '34',
      '평가 대상과 판정 기준을 고정했습니다': '35',
      '시나리오별 판정 초점': '36',
      '안전성은 유지, 운영 품질은 다음 보완 과제': '37',
      '검색은 성공, 답변 복원은 실패했다': '38',
      '스킬 사용 전후 비교': '40',
    };
    Object.entries(MAP).forEach(([title, key]) => {
      const s = deck.slides.find((sl) => sl.elements.some(
        (e) => /^(title-|div-title-)/.test(e.name || '') && norm(e.text) === title,
      ));
      if (!s || !Array.isArray(J[key])) { console.warn(`[juyeon 이식] ${key}p("${title}") 대상/데이터 없음`); return; }
      s.elements = s.elements.filter((e) => KEEP.test(e.name || '')).concat(clone(J[key]));
    });
  })();

  // ===================================================================
  // 최종 편집 패스 10.6 — 개요 4·5·6p 를 juneok(프로젝트개요_v4) 재설계 본문으로 교체.
  //   4=AI Agent 도입과 업무 확장 / 5=시장과 선도 서비스 / 6=플랫폼 방향(HALIL).
  //   크롬은 내 덱 것 유지(패스11), 제목은 juneok 것으로.
  // ===================================================================
  (() => {
    const O = window.HALIL_JUNEOK_OVERVIEW;
    if (!O) { console.warn('[juneok 개요 이식] HALIL_JUNEOK_OVERVIEW 미로드 — juneok-overview.js 확인'); return; }
    const KEEP = /^(top-accent|top-rule|context-|section-|page-|title-|accent-|ctx-logo|inst-logo|signal-|foot-)/;
    const SRC = { 4: 4, 5: 5, 6: 6 }; // 물리 페이지 → juneok 원본 슬라이드
    [4, 5, 6].forEach((pg) => {
      const j = O[SRC[pg]];
      const s = deck.slides[pg - 1]; // 1~6p 는 재배치 대상이 아님 → 인덱스 고정
      if (!s || !j || !Array.isArray(j.els)) { console.warn(`[juneok 개요 이식] ${pg}p 대상/데이터 없음`); return; }
      s.background = j.bg || s.background;
      s.elements = s.elements.filter((e) => KEEP.test(e.name || '')).concat(clone(j.els));
      const t = s.elements.find((e) => /^title-/.test(e.name || ''));
      if (t) setElementText(t, j.title);
    });

    // 4p 미세 조정
    const s4 = deck.slides[3];
    if (s4) {
      const g = (name) => s4.elements.find((e) => e.name === name);
      // ① '개별 업무 영역 기준 10% 이하' 쌍을 페이지 정중앙(x=640)으로
      const lbl = g('metric-note-label'); if (lbl) lbl.bbox = [366, 278, 282, 28];
      const val = g('metric-note-value'); if (val) val.bbox = [664, 272, 190, 38];
      // ② '업무 확장의 핵심 과제' 위 구분선 (juneok 원본 divider-4 복원)
      if (!g('divider-4')) {
        const anchor = g('problem-kicker');
        const idx = anchor ? s4.elements.indexOf(anchor) : s4.elements.length;
        s4.elements.splice(idx, 0, { kind: 'shape', geometry: 'line', bbox: [72, 344, 1136, 0], lineColor: '#D3DCE8', lineWidth: 1, name: 'divider-4' });
      }
    }
  })();

  // ===================================================================
  // 최종 편집 패스 11 — 전 내용 장표의 상단·하단 크롬 통일.
  //   · 좌측 context: wonbin → 'halil · 04 프로젝트 수행 결과'
  //   · 중앙 section: 한글 라벨 + 중앙정렬(bbox [430,51,420,22]), 없으면 생성
  //   · 하단 signal-label: 중앙 라벨과 동일 텍스트, 파란 선이 있는 장표에 없으면 생성
  //   (재번호가 모두 끝난 뒤라 페이지 번호로 매핑)
  // ===================================================================
  (() => {
    const LABEL = {
      2: '목차', 4: '시장 변화', 5: '해결 방향', 6: '선도 서비스',
      8: '팀 구성', 10: '구현 과정', 11: '시스템 구조', 14: '시스템 구조',
      15: '에이전트 생애주기', 16: '에이전트 하네스', 17: '에이전트 런타임',
      18: '파서 선택', 19: '기본 파이프라인', 20: '파싱 결과', 21: '검증 · 문제',
      22: '보완 레이어', 23: '읽기 순서 · 사례', 24: '읽기 순서 · 로직',
      25: '제목 추출 · 사례', 26: '제목 추출 · 로직', 27: '표 판별 · 사례', 28: '표 판별 · 로직',
      29: '이미지 설명 · 문제', 30: '이미지 설명 · 해결', 31: '청킹 · 임베딩',
      32: '판정 계층', 33: '플랫폼 평가',
      // 평가 섹션은 juyeon 재편안대로 2그룹: 기능 작동 평가(34) / 시나리오 운영 평가(35~38).
      34: '기능 작동 평가', 35: '시나리오 운영 평가', 36: '시나리오 운영 평가',
      37: '시나리오 운영 평가', 38: '시나리오 운영 평가', 39: '시연 결과', 40: '스킬 사용 비교',
      41: '플랫폼 운영', 42: '연결 환경', 43: '실행 통제', 44: '운영 모니터링',
    };
    // 상단 크롬 3요소(context·section·page)는 같은 세로 박스 + 세로 중앙정렬으로 baseline 을 맞춘다.
    const CY = 44;
    const CH = 30;
    const vmid = (el) => {
      if (!el) return;
      el.bbox = [el.bbox[0], CY, el.bbox[2], CH];
      (el.textStyle || (el.textStyle = {})).verticalAlignment = 'middle';
    };

    deck.slides.forEach((s, i) => {
      const label = LABEL[i + 1];
      if (!label) return;
      const findEl = (re) => s.elements.find((e) => re.test(e.name || ''));

      const ctx = findEl(/^context-/);
      if (ctx && /^\s*wonbin/.test(String(ctx.text || ''))) {
        setElementText(ctx, 'halil   ·   04 프로젝트 수행 결과');
      }
      vmid(ctx);
      vmid(findEl(/^page-/));

      let sec = findEl(/^section-/);
      if (sec) {
        setElementText(sec, label, { alignment: 'center', fontSize: 13 });
      } else {
        sec = textElement(`section-u${i + 1}`, [430, CY, 420, CH], label, 13, '#6C7482', true, 'center');
        s.elements.push(sec);
      }
      sec.bbox = [430, CY, 420, CH];
      vmid(sec);

      // 하단 라벨 — halil 장표는 signal-label-*, wonbin 장표는 foot-* 를 쓴다. 둘 다 인식해 중복 생성 방지.
      const foot = findEl(/^(signal-label-|foot-)/);
      if (foot) {
        setElementText(foot, label);
        foot.bbox = [150, 651, 470, 22];
      } else if (findEl(/^signal-\d/)) {
        s.elements.push(textElement(`signal-label-u${i + 1}`, [150, 651, 470, 22], label, 12, '#6C7482', true, 'left'));
      }
    });
  })();

  // ===================================================================
  // 최종 편집 패스 12 — 시스템 구조 장표 분리.
  //   · 11p(03장): 상세 이미지 → 네이티브 단순화 다이어그램 (6개 존 + 주요 흐름).
  //   · 14p(04장): 상세 이미지 유지하되 흰 프레임 제거 + 크림 배경으로 이음새 제거.
  //   · 부제목(제목 아래 한 줄, sub-*)은 전 장표에서 삭제.
  // ===================================================================
  (() => {
    const ctxText = (s) => (s.elements.find((e) => /^context-/.test(e.name || '')) || {}).text || '';
    const hasArch = (s) => s.elements.some((e) => e.name === 'architecture-diagram');
    const p11 = deck.slides.find((s) => hasArch(s) && ctxText(s).includes('03'));
    const p14 = deck.slides.find((s) => hasArch(s) && ctxText(s).includes('04'));

    // 제목 아래 부제목 한 줄은 전 장표에서 제거.
    deck.slides.forEach((s) => {
      s.elements = s.elements.filter((e) => !/^sub-\d+$/.test(e.name || ''));
    });

    if (p14) {
      // 가독성 높인 v2 다이어그램(상단 제목 문구는 크롭 제거)으로 교체. 흰 프레임 없이 크림 배경에 얹는다.
      p14.background = '#F7F6F1';
      p14.elements = p14.elements.filter((e) => e.name !== 'architecture-canvas' && e.name !== 'sub-16');
      const img = p14.elements.find((e) => e.name === 'architecture-diagram');
      if (img) { img.media = 'Architecture-v2-cream.png'; img.bbox = [40, 158, 1200, 510]; img.fit = 'contain'; }
    }

    if (p11) {
      p11.elements = p11.elements.filter((e) => !['architecture-canvas', 'architecture-diagram'].includes(e.name));
      byNameFor(p11, 'title-16', '화면·실행·검색·검증을 하나의 흐름으로');

      // 상단: 요청이 지나는 4개 영역 (Agent Runtime = 핵심, 강조)
      const zones = [
        ['사용자 화면', '채팅 · 빌더 · 프로젝트\n운영자 콘솔', 'ic-ux.svg', false],
        ['API · 서비스', 'Django 5 · 인증 / 팀 권한\n문서 · 업무 인테이크', 'ic-api.svg', false],
        ['Agent Runtime', '도구 · 서브에이전트 조립·실행\nHITL 승인 · Skills · Memory', 'ic-agent.svg', true],
        ['외부 연동', 'Drive · Jira · MCP\nOpenAI / Anthropic · Guardrails', 'ic-link.svg', false],
      ];
      zones.forEach(([t, b, ic, core], i) => {
        const x = 64 + i * 296;
        p11.elements.push(panel(`arc11-z${i}`, [x, 196, 264, 162], core ? '#E8F1FC' : '#FFFFFF', core ? '#2878D1' : '#D9DEE8'));
        p11.elements.push(imageElement(`arc11-zi${i}`, [x + 22, 220, 26, 26], ic, 'contain'));
        p11.elements.push(textElement(`arc11-zt${i}`, [x + 56, 220, 190, 26], t, 16, '#0A1020', true));
        const body = textElement(`arc11-zb${i}`, [x + 22, 258, 224, 84], b, 12.5, '#3A4658');
        p11.elements.push(body);
        if (i < 3) p11.elements.push(textElement(`arc11-ar${i}`, [x + 264, 262, 32, 30], '→', 26, '#2878D1', true, 'center'));
      });

      // 하단: 흐름을 받쳐 주는 두 프로세스
      const supp = [
        ['arc11-skill', '스킬 검증 워커', 'Queue → 검사 → 시험 실행 → 발행\nHTTP와 분리된 상시 프로세스', 64, 'ic-shield.svg'],
        ['arc11-doc', '문서 인덱싱 · 검색', 'Docling 파싱 · 청킹 · 768D 임베딩\n→ pgvector → Hybrid Search', 656, 'ic-search.svg'],
      ];
      supp.forEach(([nm, t, b, x, ic]) => {
        p11.elements.push(panel(nm, [x, 378, 560, 120], '#F4F6F9', '#D9DEE8'));
        p11.elements.push(imageElement(`${nm}-i`, [x + 26, 398, 24, 24], ic, 'contain'));
        p11.elements.push(textElement(`${nm}-t`, [x + 58, 398, 476, 24], t, 15, '#0A1020', true));
        p11.elements.push(textElement(`${nm}-b`, [x + 26, 434, 508, 50], b, 12.5, '#3A4658'));
      });

      p11.elements.push(panel('arc11-infra', [64, 522, 1152, 62], '#0C3F91', '#0C3F91'));
      p11.elements.push(imageElement('arc11-infra-i', [92, 541, 24, 24], 'ic-infra.svg', 'contain'));
      p11.elements.push(textElement('arc11-infra-t', [104, 522, 1072, 62],
        '인프라   ·   EC2 · Docker Compose   ·   RDS PostgreSQL 17 + pgvector   ·   S3 Object Storage   ·   RunPod Serverless GPU',
        15, '#FFFFFF', true, 'center'));
    }
  })();

  // ===================================================================
  // 최종 편집 패스 13 — juyeon 측 제목 수정 반영 (15·16·17·32·34·35·37·38p).
  //   섹션 라벨은 패스11(전 장표 한글 통일 + 평가 2그룹 재편)이 담당하므로 여기선 제목만.
  // ===================================================================
  (() => {
    const norm = (v) => String(v || '').replace(/\s+/g, ' ').trim();
    const byTitle = (t) => deck.slides.find((s) => {
      const e = s.elements.find((x) => /^(title-|div-title-)/.test(x.name || '') && x.text);
      return e && norm(e.text) === norm(t);
    });
    const retitle = (from, to) => {
      const s = byTitle(from);
      if (s) setElementText(s.elements.find((e) => /^(title-|div-title-)/.test(e.name || '') && e.text), to);
    };

    retitle('에이전트 생성과 사용자 질의 요청', 'Agent 생성과 질의 요청');
    const s15 = byTitle('Agent 생성과 질의 요청');
    if (s15) {
      setElementText(s15.elements.find((e) => e.name === 's16-create-name'), 'Agent 생성');
      setElementText(s15.elements.find((e) => e.name === 's16-query-name'), 'Agent에 질의 요청');
      s15.elements.forEach((e) => { if (/^s16-(create|query)-frame$/.test(e.name || '')) e.lineColor = '#AAAAAA'; });
    }
    retitle('Deep Agent는 에이전트 실행 하네스입니다', 'Deep Agent: Agent를 실행하는 Harness');
    retitle('Deep Agent 실행 구조 전체 도면', 'Deep Agent 실행 구조');
    retitle('판정 계약은 세 층으로 나눠 적용했다', '판정 체계');
    retitle('기본 동작 10가지, 재검증까지 포함해 10/10 최종 통과', '기능 작동 평가');
    retitle('평가 대상과 판정 기준을 고정했습니다', '평가 대상 및 판정 기준 고정');
    retitle('안전성은 유지, 운영 품질은 다음 보완 과제', '시나리오 운영 평가');
    retitle('검색은 성공, 답변 복원은 실패했다', '시나리오 운영 평가 실패 사례');

    // 40p — juyeon 처럼 상단 결과 콜아웃(sc-stat) 제거 (표에 수치가 이미 있음)
    const s40 = deck.slides.find((s) => s.elements.some((e) => e.name === 'title-40'));
    if (s40) s40.elements = s40.elements.filter((e) => e.name !== 'sc-stat' && e.name !== 'sc-stat-label');
  })();

  // ===================================================================
  // 최종 편집 패스 14 — 내용 장표 제목 통일.
  //   · 폰트 40px · 볼드 · #0A1020 · bbox [58,92,1160,58] 로 통일 (챕터 표지 div-title 은 제외)
  //   · 서술형·장문 → 짧은 명사구 (juyeon 작업 페이지 스타일, 2~5어절)
  // ===================================================================
  (() => {
    const norm = (v) => String(v || '').replace(/\s+/g, ' ').trim();
    const REWRITE = {
      // 개요 4·5·6p 제목은 패스10.6(juneok 재설계 이식)에서 확정 — 여기서 손대지 않음
      '설계에서 운영 검증까지의 구현 과정': '구현 과정 6단계',
      '화면·실행·검색·검증을 하나의 흐름으로': '시스템 흐름 한눈에',
      'UI부터 실행·통제까지 연결된 시스템 구조': '전체 시스템 구조',
      'Deep Agent: Agent를 실행하는 Harness': 'Deep Agent Harness',
      '엔터프라이즈가 파서를 쓰는 이유': '파서가 필요한 이유',
      'PDF는 12단계를 거쳐 DoclingDocument가 됩니다': '12단계 파싱 파이프라인',
      'Docling 기본 파이프라인의 실제 결과': '기본 파이프라인 결과',
      '206개 문서로 검증해 보니, Docling만으로는 부족했습니다': '검증 결과, Docling의 한계',
      '읽기 순서가 뒤바뀐 실제 사례': '읽기 순서 오류 사례',
      '인접 요소 좌표 비교로 순서를 보정합니다': '읽기 순서 보정 로직',
      '한화 브로슈어에서 확인된 오분류': '제목 오분류 사례',
      '제목 오분류를 바로잡는 승격 조건': '제목 승격 조건',
      '표로 오인식된 비표 사례': '표 오인식 사례',
      '실제 표인지 판단하는 기준': '표 판별 기준',
      '기존 Docling 이미지 설명의 세 가지 문제': '이미지 설명의 세 문제',
      'Qwen2.5-VL과 문맥 우선순위로 해결했습니다': '이미지 설명 개선',
      '계층 구조를 유지해 직렬화하고 EmbeddingGemma로 임베딩합니다': '직렬화와 임베딩',
      '평가 대상 및 판정 기준 고정': '평가 대상과 기준',
      '시나리오 운영 평가 실패 사례': '운영 평가 실패 사례',
      '전체 기능은 실제 시연 영상으로 확인합니다': '전체 기능 시연 영상',
    };
    deck.slides.forEach((s) => {
      const t = s.elements.find((e) => /^title-/.test(e.name || '') && norm(e.text));
      if (!t) return; // div-title-*(챕터 표지)는 제외
      const next = REWRITE[norm(t.text)] || norm(t.text);
      setElementText(t, next, { fontSize: 40, bold: true, color: '#0A1020' });
      t.bbox = [58, 92, 1160, 58];
    });
  })();

  // ===================================================================
  // 최종 편집 패스 15 — 상단·하단 '텍스트 라벨'만 삭제(section-*·signal-label-*·foot-*).
  //   좌하단 파란 강조선은 밋밋함 방지를 위해 살리되, 위치를 [58,660,78,4]로 통일.
  //   context(좌상단 breadcrumb)·page(우상단 번호)는 유지.
  // ===================================================================
  (() => {
    const RM = /^(section-|signal-\d|signal-label-|foot-)/;
    deck.slides.forEach((s, i) => {
      s.elements = s.elements.filter((e) => !RM.test(e.name || ''));
      // 표준 내용 장표(title-* 보유, 챕터 표지 아님)에 파란 강조선 재부여
      const isContent = s.elements.some((e) => /^title-/.test(e.name || ''));
      if (isContent) {
        s.elements.push({ kind: 'shape', geometry: 'rect', bbox: [58, 660, 78, 4], fillColor: '#2878D1', lineWidth: 0, name: `accent-${i + 1}` });
      }
    });
  })();

  // ===================================================================
  // 최종 편집 패스 15.5 — 좌상단 breadcrumb 의 'halil' 텍스트를 워드마크 로고로 교체.
  //   "halil · 04 …" → [halil-logo.png] · 04 …
  // ===================================================================
  (() => {
    deck.slides.forEach((s, i) => {
      const ctx = s.elements.find((e) => /^context-/.test(e.name || ''));
      if (!ctx) return;
      const rest = String(ctx.text || '').replace(/^\s*halil\s*[·]?\s*/, '').trim();
      setElementText(ctx, `·   ${rest}`, { fontSize: 13, bold: true, color: '#0A1020' });
      ctx.bbox = [96, 44, 378, 30];
      (ctx.textStyle || (ctx.textStyle = {})).insets = { top: 0, right: 0, bottom: 0, left: 0 };
      ctx.textStyle.verticalAlignment = 'middle';
      if (!s.elements.some((e) => e.name === 'ctx-logo')) {
        s.elements.push(imageElement(`ctx-logo-${i + 1}`, [58, 51, 34, 16], 'halil-logo.png', 'contain'));
      }
    });
    // 챕터 표지 좌상단 halil 워드마크 — 크기는 다른 장표와 동일(34×16),
    // x 는 큰 챕터 번호(div-no, x=64)에 맞춰 세로로 정렬.
    deck.slides.forEach((s, i) => {
      if (!s.elements.some((e) => /^div-title-/.test(e.name || ''))) return;
      if (s.elements.some((e) => /^cover-logo/.test(e.name || ''))) return;
      const no = s.elements.find((e) => /^div-no-/.test(e.name || ''));
      const x = no ? no.bbox[0] : 64;
      s.elements.push(imageElement(`cover-logo-${i + 1}`, [x, 46, 34, 16], 'halil-logo.png', 'contain'));
    });
  })();

  // ===================================================================
  // 최종 편집 패스 16.5 — 마지막 Q&A 장표 단순화 + '감사합니다' 장표 추가.
  // ===================================================================
  (() => {
    // 마감 2장도 본문과 같은 밝은 배경 → 모든 로고를 원본 색 그대로(실루엣·배지 없이).
    const BG = '#F7F6F1';
    const chrome = () => [
      { kind: 'shape', geometry: 'rect', bbox: [0, 0, 1280, 5], fillColor: '#F8C944', lineWidth: 0, name: 'cl-top' },
      { kind: 'shape', geometry: 'rect', bbox: [0, 0, 18, 720], fillColor: '#2878D1', lineWidth: 0, name: 'cl-side' },
      imageElement('cl-halil-logo', [58, 51, 34, 16], 'halil-logo.png', 'contain'),
      imageElement('cl-inst-a', [1019.56, 647, 78.89, 25], 'image2.png', 'contain'),
      imageElement('cl-inst-b', [1138.95, 647, 84.09, 25], 'image3.png', 'contain'),
    ];

    const qa = deck.slides.find((s) => s.elements.some((e) => e.name === 'closing-qa'));
    if (qa) {
      qa.background = BG;
      qa.elements = [
        ...chrome(),
        textElement('qa-big', [0, 250, 1280, 180], 'Q&A', 128, '#0C3F91', true, 'center'),
        textElement('qa-brand', [0, 600, 1280, 30], 'halil · 프로젝트 운영 Agent Platform', 14, '#6E7A90', false, 'center'),
      ];
    }
    const thanks = {
      background: BG,
      elements: [
        ...chrome(),
        textElement('thanks-big', [0, 232, 1280, 180], '감사합니다', 118, '#0A1020', true, 'center'),
        textElement('thanks-team', [0, 424, 1280, 34], 'TEAM 2 · HALIL', 20, '#2878D1', true, 'center'),
        textElement('thanks-brand', [0, 464, 1280, 30], '프로젝트 운영 Agent Platform', 15, '#6E7A90', false, 'center'),
      ],
    };
    deck.slides.push(thanks);
    deck.slides.forEach((item, index) => { item.number = index + 1; });
  })();

  // ===================================================================
  // 최종 편집 패스 16 — 직업능력심사평가원·고용노동부 로고가 빠진 장표에 추가.
  //   (Agent·파싱·평가 섹션은 다른 소스 덱에서 와서 우하단 기관 로고가 없었음)
  //   기존 장표와 동일 위치·크기.
  // ===================================================================
  (() => {
    const BOX_A = [1019.56, 647, 78.89, 25];
    const BOX_B = [1138.95, 647, 84.09, 25];
    deck.slides.forEach((s, i) => {
      const hasA = s.elements.some((e) => e.kind === 'image' && e.media === 'image2.png');
      const hasB = s.elements.some((e) => e.kind === 'image' && e.media === 'image3.png');
      if (!hasA) s.elements.push(imageElement(`inst-logo-a-${i + 1}`, BOX_A.slice(), 'image2.png', 'contain'));
      if (!hasB) s.elements.push(imageElement(`inst-logo-b-${i + 1}`, BOX_B.slice(), 'image3.png', 'contain'));
    });
  })();

  // ===================================================================
  // 최종 편집 패스 17 — 20p 를 팀원 전달 인터랙티브(DoclingDocument 구조화)로 재구성.
  //   레이아웃·동작은 docling20.js. 여기선 골격만: 크롬 유지 + 제목 교체 + html 요소 1개.
  //   index.html 이 kind:'html' 을 in-document 로 주입하고 HALIL_DOCLING20.init 로 ←→ 동작 연결.
  // ===================================================================
  (() => {
    const norm = (v) => String(v || '').replace(/\s+/g, ' ').trim();
    const s = deck.slides.find((sl) => {
      const t = sl.elements.find((e) => /^title-/.test(e.name || ''));
      return t && norm(t.text) === '기본 파이프라인 결과';
    });
    if (!s) { console.warn('[패스17] 20p 슬라이드를 찾지 못함'); return; }
    const KEEP = /^(top-accent|top-rule|context-|page-|title-|accent-|ctx-logo|inst-logo)/;
    s.elements = s.elements.filter((e) => KEEP.test(e.name || ''));
    setElementText(s.elements.find((e) => /^title-/.test(e.name || '')), '문서를 읽기 순서와 요소별 구조로 저장합니다');
    if (window.HALIL_DOCLING20) {
      s.elements.push({ kind: 'html', name: 'dl20', bbox: [34, 178, 1212, 474], html: window.HALIL_DOCLING20.HTML });
      s.doclingInteractive = true;
    } else {
      console.warn('[패스17] HALIL_DOCLING20 미로드 — docling20.js 확인');
    }
  })();

  // ===================================================================
  // 최종 편집 패스 18 — 전 장표 하단 푸터를 더 아래로 내림.
  //   기관 로고(image2/image3) top 647 → 680, 좌하단 파란 강조선 top 660 → 693
  //   (둘의 세로 중심 관계는 그대로: delta +33). 표지(1p)는 원위치 유지.
  // ===================================================================
  (() => {
    deck.slides.forEach((s, i) => {
      if (i === 0) return; // 첫 장(표지)은 제외
      s.elements.forEach((e) => {
        if (e.kind === 'image' && (e.media === 'image2.png' || e.media === 'image3.png')) {
          e.bbox = [e.bbox[0], 680, e.bbox[2], e.bbox[3]];
        } else if (/^accent-/.test(e.name || '')) {
          e.bbox = [e.bbox[0], 693, e.bbox[2], e.bbox[3]];
        }
      });
    });
  })();

  // ===================================================================
  // 최종 편집 패스 19 — 18p('파서가 필요한 이유') 재구성.
  //   A. 파서가 필요한 이유 3가지 (제목이 요구하는 설명) — 컴팩트 패널.
  //   B. 도클링 채택 근거 — 깃허브 활동 지표 + 릴리즈 타임라인 (github_activity.svg 대체).
  //   하단: 크림 노트 밴드. 덱 팔레트/컨벤션(21p vi-*, 19p bp-note).
  // ===================================================================
  (() => {
    const s = deck.slides.find((sl) =>
      sl.elements.some((e) => e.kind === 'image' && e.media === 'github_activity.svg'));
    if (!s) { console.warn('[패스19] 18p(github_activity.svg) 슬라이드를 찾지 못함'); return; }
    s.elements = s.elements.filter((e) => e.name !== 'img-2');

    const line = (name, bbox, color, wpx) => ({ kind: 'shape', geometry: 'line', bbox, lineColor: color, lineWidth: wpx, name });
    const dot = (name, bbox, fill, stroke, sw) => ({ kind: 'shape', geometry: 'ellipse', bbox, fillColor: fill, lineColor: stroke, lineWidth: sw, name });

    const L = 58, W = 1160, R = L + W; // 1218
    const els = [];

    // ---- A. 파서가 필요한 이유 ----
    els.push(textElement('s18n-whyhead', [L, 182, 900, 22], '왜 문서 파서가 필요한가', 13, '#52657D', true));
    const rw = (W - 40) / 3; // 373.3
    const reasons = [
      ['다양한 문서 형식', '기업 문서는 PDF · DOCX · 엑셀 등 형식이 제각각입니다'],
      ['단순 텍스트 추출의 한계', '표·이미지·레이아웃 구조가 사라져 RAG 정확도가 떨어집니다'],
      ['구조까지 보존하는 파서', '표·이미지·페이지 좌표를 유지한 채 추출해야 합니다'],
    ];
    reasons.forEach(([t, b], i) => {
      const x = L + i * (rw + 20), y = 208, h = 104;
      els.push(panel(`s18n-rp${i}`, [x, y, rw, h], '#F1F4FA', '#DCE3EE'));
      els.push(textElement(`s18n-rn${i}`, [x + 18, y + 14, 40, 16], String(i + 1).padStart(2, '0'), 11, '#2878D1', true));
      els.push(textElement(`s18n-rt${i}`, [x + 18, y + 32, rw - 32, 22], t, 13.5, '#0A1020', true));
      els.push(textElement(`s18n-rb${i}`, [x + 18, y + 56, rw - 28, 40], b, 11, '#52657D'));
    });

    // ---- B. 도클링 채택 근거 (깃허브 활동) ----
    els.push(line('s18n-div-mid', [L, 336, W, 0], '#E1E6EE', 1));
    els.push(textElement('s18n-kick', [L, 350, 900, 22], '도클링을 택한 이유 · 깃허브 활동', 13, '#52657D', true));

    const cw = W / 4;
    const cols = [
      ['관심도', '65.8K', '스타'],
      ['확장·재사용', '4.7K', '포크'],
      ['사용자 피드백', '904', '공개 이슈'],
      ['코드 검토', '86', '진행 중인 변경 제안'],
    ];
    cols.forEach(([label, value, unit], i) => {
      const x = L + i * cw;
      els.push(textElement(`s18n-l${i}`, [x, 378, cw - 20, 20], label, 12, '#52657D', true));
      els.push(textElement(`s18n-v${i}`, [x, 398, cw - 12, 44], value, 30, '#2878D1', true));
      els.push(textElement(`s18n-u${i}`, [x, 440, cw - 20, 18], unit, 10.5, '#6E7A90'));
      if (i > 0) els.push(line(`s18n-vd${i}`, [x - 22, 374, 0, 86], '#E1E6EE', 1));
    });

    els.push(textElement('s18n-relhead', [L, 470, 220, 20], '최근 릴리즈', 12, '#52657D', true));
    const dw = 150;
    const nodeX = cols.map((_, i) => L + i * cw + cw / 2);
    els.push(line('s18n-tl', [nodeX[0] - 40, 508, nodeX[3] - nodeX[0] + 80, 0], '#C7D6EE', 3));
    const rel = [['8월 25일', '2.122.0'], ['8월 26일', '2.123.0'], ['8월 28일', '2.123.1'], ['8월 31일', '2.124.0']];
    rel.forEach(([date, ver], i) => {
      const cx = nodeX[i];
      const last = i === rel.length - 1;
      els.push(last
        ? dot('s18n-n3', [cx - 8, 501, 16, 16], '#0C3F91', '#F8C944', 3)
        : dot(`s18n-n${i}`, [cx - 5, 504, 10, 10], '#2878D1', '#2878D1', 1));
      els.push(textElement(`s18n-d${i}`, [cx - dw / 2, 522, dw, 18], date, 11, '#0A1020', true, 'center'));
      els.push(textElement(`s18n-r${i}`, [cx - dw / 2, 542, dw, 14], ver, 10, '#2878D1', false, 'center'));
    });

    // ---- 하단 노트 밴드 ----
    els.push(panel('s18n-note-bg', [L, 566, W, 56], '#FFF4E6', '#F0D9B8'));
    const cap = s.elements.find((e) => e.name === 'cap-2');
    if (cap) {
      cap.bbox = [L + 24, 566, W - 48, 56];
      setElementText(cap, '도클링은 오픈소스라 비용 없이 자체 인프라에 통합할 수 있고, 활발한 업데이트와 피드백으로 확장성·유지보수에 적합합니다.',
        { fontSize: 14.5, bold: true, color: '#173F7A', alignment: 'center' });
      (cap.textStyle || (cap.textStyle = {})).verticalAlignment = 'middle';
    }

    const at = s.elements.findIndex((e) => /^title-/.test(e.name || ''));
    s.elements.splice(at < 0 ? s.elements.length : at + 1, 0, ...els);
  })();

  // ===================================================================
  // 최종 편집 패스 20 — 19p('12단계 파싱 파이프라인') 의 mermaid SVG 3장(pipeline_row1~3)을
  //   네이티브 카드(3행×4단계 + 번호 + 행내 화살표)로 재구성. 핵심 단계는 강조.
  // ===================================================================
  (() => {
    const s = deck.slides.find((sl) =>
      sl.elements.some((e) => e.kind === 'image' && /^pipeline_row/.test(e.media || '')));
    if (!s) { console.warn('[패스20] 19p(pipeline_row*.svg) 슬라이드를 찾지 못함'); return; }
    s.elements = s.elements.filter((e) => !['pr1-3', 'pr2-3', 'pr3-3', 'plabel-3'].includes(e.name || ''));

    const L = 58, W = 1160, GAP = 22, CW = 273, CH = 96;
    const xs = [0, 1, 2, 3].map((i) => L + i * (CW + GAP));
    const rowY = [194, 316, 438];

    const steps = [
      ['PDF Backend', '페이지 이미지와 내장 텍스트 추출'],
      ['Page Pre-processing', '페이지 이미지와 텍스트 정보 준비'],
      ['Layout Detection', '제목·본문·목록·표·그림 영역 찾기'],
      ['OCR 실행', '찾아낸 영역의 한국어·영어 글자 인식'],
      ['Text Cell Merge', 'PDF 내장 텍스트와 OCR 결과 결합'],
      ['Layout Post-processing', '텍스트를 영역에 배치하고 중복 제거'],
      ['TableFormer', '표의 행·열·셀 구조 복원'],
      ['Page Assemble', '텍스트·표·그림 요소 생성'],
      ['ReadingOrderModel', '읽기 순서와 캡션 관계 결정'],
      ['HeadingHierarchyModel', '제목과 소제목의 계층 정리'],
      ['Picture Crop·Classification', '그림 영역을 잘라 유형 분류'],
      ['DoclingDocument', '하나의 공통 문서 구조'],
    ];
    const HOT = new Set([0, 2, 3, 6, 8, 10]); // 01·03·04·07·09·11 강조

    const els = [];
    steps.forEach(([en, ko], i) => {
      const r = Math.floor(i / 4), c = i % 4;
      const x = xs[c], y = rowY[r];
      const hot = HOT.has(i);
      const card = panel(`s19n-c${i}`, [x, y, CW, CH], hot ? '#CFE1FA' : '#F1F4FA', hot ? '#1E6FD0' : '#DCE3EE');
      if (hot) card.lineWidth = 2;
      els.push(card);
      els.push(textElement(`s19n-n${i}`, [x + 18, y + 12, 60, 18], String(i + 1).padStart(2, '0'), 11.5, hot ? '#0C3F91' : '#2878D1', true));
      els.push(textElement(`s19n-t${i}`, [x + 18, y + 30, CW - 34, 22], en, 12, '#0A1020', true));
      els.push(textElement(`s19n-s${i}`, [x + 18, y + 52, CW - 32, 38], ko, 10.5, hot ? '#3A4C64' : '#52657D'));
      if (c < 3) els.push(textElement(`s19n-a${i}`, [x + CW, y + 32, GAP + 2, 30], '→', 16, '#2878D1', true, 'center'));
    });

    // 하단 노트 밴드 — 문구 교체 후 재배치
    const noteBg = s.elements.find((e) => e.name === 'bp-note-bg');
    if (noteBg) noteBg.bbox = [L, 552, W, 66];
    const note = s.elements.find((e) => e.name === 'bp-note');
    if (note) {
      note.bbox = [L + 22, 552, W - 44, 66]; // 18p 노트 밴드와 동일 규격·폰트
      setElementText(note, 'DOCX · PPTX · Markdown 등의 문서는 형식별 PipeLine 을 거쳐 같은 DoclingDocument 형식으로 생성 됩니다.',
        { fontSize: 15.5, bold: true, color: '#173F7A', alignment: 'center' });
      (note.textStyle || (note.textStyle = {})).verticalAlignment = 'middle';
    }

    const at = s.elements.findIndex((e) => /^title-/.test(e.name || ''));
    s.elements.splice(at < 0 ? s.elements.length : at + 1, 0, ...els);
  })();

  // ===================================================================
  // 최종 편집 패스 21 — 28p('표 판별 기준') diagram_table.svg 를
  //   Table Gate 플로우차트(전달 이미지 기준)로 네이티브 재구성.
  // ===================================================================
  (() => {
    const s = deck.slides.find((sl) =>
      sl.elements.some((e) => e.kind === 'image' && e.media === 'diagram_table.svg'));
    if (!s) { console.warn('[패스21] 28p(diagram_table.svg) 슬라이드를 찾지 못함'); return; }
    s.elements = s.elements.filter((e) => e.name !== 'diag-13');

    const CX = 640;
    const rrect = (name, bbox, fill, lc, lw = 1.4) => ({ kind: 'shape', geometry: 'roundRect', bbox, fillColor: fill, lineColor: lc, lineWidth: lw, name });
    const ln = (name, bbox) => ({ kind: 'shape', geometry: 'line', bbox, lineColor: '#8892A3', lineWidth: 1.8, name });
    const dn = (name, x, y) => textElement(name, [x - 11, y, 22, 16], '▼', 12, '#5B6676', true, 'center');
    const els = [];

    // 1) 입력 (24·26·30p 와 동일 팔레트)
    els.push(rrect('tg-in', [CX - 140, 190, 280, 52], '#F2F4F7', '#B9C0CC'));
    els.push(textElement('tg-in-t', [CX - 140, 190, 280, 52], 'TableItem 입력', 14, '#3A4658', true, 'center'));
    els.push(ln('tg-l0', [CX, 244, 0, 20]), dn('tg-a0', CX, 256));

    // 2) 비표 패턴 확인 컨테이너 + 6개 규칙
    els.push(rrect('tg-cont', [190, 274, 900, 160], '#FBFCFE', '#D8DEE8', 1));
    els.push(textElement('tg-cont-h', [190, 284, 900, 22], '비표 패턴 확인 (6개 규칙)', 13, '#123D7A', true, 'center'));
    ['점선 목차', '제목·페이지목록', '단일 셀조각', '불릿 텍스트', '서술문 조각', '전폭 페이지목록']
      .forEach((t, i) => {
        const x = 214 + (i % 3) * 290, y = 318 + Math.floor(i / 3) * 56;
        els.push(rrect(`tg-r${i}`, [x, y, 270, 42], '#F5F7FB', '#CDD6E4', 1.2));
        els.push(textElement(`tg-rt${i}`, [x, y, 270, 42], t, 12, '#1A2740', false, 'center'));
      });

    // 3) 분기 (컨테이너 → REJECT / PASS)
    els.push(ln('tg-f-v0', [CX, 434, 0, 16]));
    els.push(ln('tg-f-h', [475, 450, 330, 0]));
    els.push(ln('tg-f-vl', [475, 450, 0, 12]), dn('tg-fa-l', 475, 452));
    els.push(ln('tg-f-vr', [805, 450, 0, 12]), dn('tg-fa-r', 805, 452));

    els.push(rrect('tg-rej', [325, 470, 300, 66], '#FDECEC', '#DC5B5B'));
    els.push(textElement('tg-rej-t', [325, 478, 300, 24], 'REJECT', 15, '#B23A3A', true, 'center'));
    els.push(textElement('tg-rej-s', [325, 506, 300, 18], '해당 → 비표 제외', 11, '#B23A3A', false, 'center'));

    els.push(rrect('tg-pass', [655, 470, 300, 66], '#E7F4EC', '#3FA46B'));
    els.push(textElement('tg-pass-t', [655, 478, 300, 24], 'PASS', 15, '#17603C', true, 'center'));
    els.push(textElement('tg-pass-s', [655, 506, 300, 18], '미해당 → 표 유지', 11, '#17603C', false, 'center'));

    // 4) PASS → 저장 (엘보)
    els.push(ln('tg-e-v', [805, 536, 0, 16]));
    els.push(ln('tg-e-h', [CX, 552, 165, 0]));
    els.push(ln('tg-e-v2', [CX, 552, 0, 16]), dn('tg-a2', CX, 558));
    els.push(rrect('tg-out', [CX - 140, 576, 280, 52], '#F2F4F7', '#B9C0CC'));
    els.push(textElement('tg-out-t', [CX - 140, 576, 280, 52], '보완된 표 정보 저장', 13.5, '#3A4658', true, 'center'));

    const at = s.elements.findIndex((e) => /^title-/.test(e.name || ''));
    s.elements.splice(at < 0 ? s.elements.length : at + 1, 0, ...els);
  })();

  // ===================================================================
  // 최종 편집 패스 22 — 23~30p(보완 레이어 4개 상세) 에 진행 표시 스텝퍼 추가.
  //   22p 의 네 레이어 색상과 맞춰, 현재 설명 중인 레이어를 강조해 청중이 위치를 알 수 있게.
  // ===================================================================
  (() => {
    const LAYER = {
      '읽기 순서 오류 사례': 0, '읽기 순서 보정 로직': 0,
      '제목 오분류 사례': 1, '제목 승격 조건': 1,
      '표 오인식 사례': 2, '표 판별 기준': 2,
      '이미지 설명의 세 문제': 3, '이미지 설명 개선': 3,
    };
    const LABEL = ['읽기 순서', '제목 추출', '표 판별', '이미지 설명'];
    const COLOR = ['#155EEF', '#7F56D9', '#F79009', '#06AED4'];
    const LIGHT = ['#EAF2FF', '#F4EBFF', '#FFF4E5', '#E6F9FB'];
    const DARK = ['#0B1F44', '#3E1C76', '#7A2E0E', '#064E5B'];
    const norm = (v) => String(v || '').replace(/\s+/g, ' ').trim();

    deck.slides.forEach((s) => {
      const t = s.elements.find((e) => /^title-/.test(e.name || '') && norm(e.text));
      if (!t) return;
      const cur = LAYER[norm(t.text)];
      if (cur === undefined) return;

      const els = [];
      const PW = 152, PITCH = 160, X0 = 58, Y = 152, H = 26;
      for (let k = 0; k < 4; k++) {
        const x = X0 + k * PITCH;
        const on = k === cur;
        els.push({
          kind: 'shape', geometry: 'roundRect', bbox: [x, Y, PW, H],
          fillColor: on ? LIGHT[k] : '#F4F5F7', lineColor: on ? COLOR[k] : '#E1E4EA',
          lineWidth: on ? 1.5 : 1, name: `lp-box-${k}`,
        });
        const te = textElement(`lp-t-${k}`, [x, Y, PW, H], `${k + 1}  ${LABEL[k]}`,
          11, on ? DARK[k] : '#9AA1AD', on, 'center');
        te.textStyle.insets = { top: 0, right: 6, bottom: 0, left: 6 };
        els.push(te);
      }
      const at = s.elements.indexOf(t);
      s.elements.splice(at + 1, 0, ...els);

      // 스텝퍼와 본문이 붙지 않도록 본문 요소를 아래로 밀어 최소 y 확보 (스텝퍼 하단 178 + 여백 30).
      const CHROME = /^(top-|top-rule|context-|page-|title-|accent-|ctx-logo|inst-logo|lp-)/;
      const body = s.elements.filter((e) => e.bbox && !CHROME.test(e.name || ''));
      const minY = Math.min(...body.map((e) => e.bbox[1]));
      const dy = Math.max(0, 208 - minY);
      if (dy) body.forEach((e) => { e.bbox = [e.bbox[0], e.bbox[1] + dy, e.bbox[2], e.bbox[3]]; });
    });

    // 스텝퍼 라벨: 한글 line-height(normal≈1.7) 탓에 글자가 박스 상단으로 쏠림 →
    // line-height 를 1 로 눌러 flex 세로 중앙정렬이 실제 글자에 맞도록 강제.
    if (typeof document !== 'undefined') {
      const st = document.createElement('style');
      st.textContent = '.el[title^="lp-t-"] .text-inner,.el[title^="lp-t-"] .text-inner p{line-height:12px}'
        + '.el[title*="-nt"] .text-inner,.el[title*="-nt"] .text-inner p,.el[title*="-nt"] .text-inner span,'
        + '.el[title*="-lb"] .text-inner,.el[title*="-lb"] .text-inner p,.el[title*="-lb"] .text-inner span,'
        + '.el[title*="-tag"] .text-inner,.el[title*="-tag"] .text-inner p,.el[title*="-tag"] .text-inner span{line-height:1}'
        + '.el[title^="ro24-"] .text-inner p,.el[title^="hd26-"] .text-inner p,.el[title^="im30-"] .text-inner p,.el[title^="idp-"] .text-inner p,'
        + '.el[title^="ro24-"] .text-inner span,.el[title^="hd26-"] .text-inner span,.el[title^="im30-"] .text-inner span,.el[title^="idp-"] .text-inner span{line-height:16px}'
        + '.el[title^="idpL-"] .text-inner p,.el[title^="idpL-"] .text-inner span{line-height:15px}';
      document.head.appendChild(st);
    }
  })();

  // ===================================================================
  // 최종 편집 패스 23 — 23p('읽기 순서 오류 사례') 를 합성 네이티브 BEFORE/AFTER 로.
  //   실제 문서 스크린샷(ro_before/after.png) 대신, 같은 4줄이 순서만 뒤바뀌어
  //   문장 의미가 깨지는 과정을 명확히 보여준다.
  // ===================================================================
  (() => {
    const s = deck.slides.find((sl) =>
      sl.elements.some((e) => e.kind === 'image' && /^ro_(before|after)\.png$/.test(e.media || '')));
    if (!s) { console.warn('[패스23] 23p(ro_*.png) 슬라이드를 찾지 못함'); return; }
    s.elements = s.elements.filter((e) => !['imgb-8', 'imga-8'].includes(e.name || ''));

    const FRAG = [
      '검증 범위는 2024년 보고 기간 전체입니다.',
      '먼저 성과 데이터를 수집합니다.',
      '다음으로 내부 검토 절차를 점검합니다.',
      '마지막으로 근거의 신뢰성을 확인합니다.',
    ];
    const dot = (name, bbox, fill) => ({ kind: 'shape', geometry: 'ellipse', bbox, fillColor: fill, lineColor: fill, lineWidth: 1, name });
    const ln = (name, bbox) => ({ kind: 'shape', geometry: 'line', bbox, lineColor: '#E1E6EE', lineWidth: 1, name });

    // 헤더 라벨 재작성 + 패널 위로 살짝 띄우기
    const lab = (nm, text, x) => {
      const e = s.elements.find((el) => el.name === nm);
      if (!e) return;
      e.bbox = [x, 198, 560, 20];
      setElementText(e, text, { fontSize: 13, bold: true });
    };
    lab('bl-8', 'BEFORE · Docling이 매긴 읽기 순서', 58);
    lab('al-8', 'AFTER · 좌표 재비교로 보정', 658);

    const PANW = 560, PY = 222, PANH = 372, RY = PY + 44, RP = 46;
    const side = (x, order, accent, verdict, vColor, resultTxt) => {
      const els = [];
      const pf = x === 58 ? 'b' : 'a';
      els.push({ kind: 'shape', geometry: 'roundRect', bbox: [x, PY, PANW, PANH], fillColor: '#FFFFFF', lineColor: '#D9DEE8', lineWidth: 1, name: `ro-${pf}-pan` });
      els.push(textElement(`ro-${pf}-h`, [x + 24, PY + 12, PANW - 48, 18], '원문 4줄 (위 → 아래)', 11, '#6E7A90'));
      FRAG.forEach((frag, i) => {
        const y = RY + i * RP;
        const n = order[i];
        const swapped = accent && n !== i + 1;
        if (swapped) els.push({ kind: 'shape', geometry: 'roundRect', bbox: [x + 16, y - 7, PANW - 32, 40], fillColor: '#FDECEC', lineColor: '#F6D5D5', lineWidth: 1, name: `ro-${pf}-hl${i}` });
        els.push(dot(`ro-${pf}-n${i}`, [x + 24, y, 28, 28], swapped ? '#DC5B5B' : accent ? '#9AA4B2' : '#2878D1'));
        els.push(textElement(`ro-${pf}-nt${i}`, [x + 24, y, 28, 28], String(n), 13, '#FFFFFF', true, 'center'));
        els.push(textElement(`ro-${pf}-l${i}`, [x + 66, y, PANW - 96, 28], frag, 13.5, '#0A1020'));
      });
      els.push(ln(`ro-${pf}-div`, [x + 24, PY + 228, PANW - 48, 0]));
      els.push(textElement(`ro-${pf}-sl`, [x + 24, PY + 240, 120, 16], '읽은 순서', 10.5, '#6E7A90'));
      els.push(textElement(`ro-${pf}-sq`, [x + 24, PY + 258, PANW - 48, 24], order.join('   →   '), 18, vColor, true));
      els.push(textElement(`ro-${pf}-rs`, [x + 24, PY + 292, PANW - 48, 18], resultTxt, 10.5, '#52657D'));
      els.push(textElement(`ro-${pf}-vd`, [x + 24, PY + 314, PANW - 48, 16], verdict, 12, vColor, true));
      return els;
    };

    s.elements.push(
      ...side(58, [1, 3, 2, 4], true, '→ 절차 순서가 뒤바뀌어 내용이 어긋납니다', '#B23A3A',
        '결과: “다음으로 …” 문장이 “먼저 …” 앞에 와 단계 순서가 뒤집힙니다.'),
      ...side(658, [1, 2, 3, 4], false, '→ 원래 문장 순서로 복원', '#17845E',
        '결과: 먼저 → 다음으로 → 마지막으로, 단계 순서가 그대로 유지됩니다.'),
    );
  })();

  // ===================================================================
  // 최종 편집 패스 24 — 25p('제목 오분류 사례') 합성 네이티브 (원문 vs Docling 파싱).
  //   좌: 사람 눈에 제목/본문 위계가 뚜렷한 원문.
  //   우: Docling 파싱 결과 — 같은 형식인데 위 제목은 text 로 분류돼 제목 지위를 잃음.
  // ===================================================================
  (() => {
    const s = deck.slides.find((sl) =>
      sl.elements.some((e) => e.kind === 'image' && /^hanwha_(doc|layout)\.png$/.test(e.media || '')));
    if (!s) { console.warn('[패스24] 25p(hanwha_*.png) 슬라이드를 찾지 못함'); return; }
    s.elements = s.elements.filter((e) => !['img1-10', 'img2-10', 'l1-10', 'l2-10'].includes(e.name || ''));

    const PANW = 560, PY = 214, PANH = 380;
    // 6줄 공통 y (좌·우 패널이 같은 높이에서 매칭되도록)
    const RY = [PY + 46, PY + 92, PY + 128, PY + 190, PY + 236, PY + 272];
    const BODY = [
      '상하이·톈진·베트남 3개 사무소 운영 · 주소와 연락처는 아래 정리',
      '지역 담당자와 대표 전화는 사내 인트라넷에서도 확인 가능',
      '베를린·뮌헨 2개 사무소 운영 · 주소와 연락처는 아래 정리',
      '지역 담당자와 대표 전화는 사내 인트라넷에서도 확인 가능',
    ];
    const HEAD_A = '아시아·태평양 지역 현황', HEAD_B = '유럽 지역 현황';
    const els = [];

    // ---- 좌: 원문 (제목 크고 굵게, 본문 작고 들여쓰기) ----
    els.push(
      { kind: 'shape', geometry: 'roundRect', bbox: [58, PY, PANW, PANH], fillColor: '#FFFFFF', lineColor: '#D9DEE8', lineWidth: 1, name: 'hd-l-pan' },
      textElement('hd-l-h', [58 + 24, PY + 14, PANW - 48, 16], '원문 — 제목·본문 위계가 뚜렷', 11, '#6E7A90'),
      textElement('hd-l-h0', [58 + 28, RY[0], PANW - 56, 28], HEAD_A, 18, '#0A1020', true),
      { kind: 'shape', geometry: 'line', bbox: [58 + 28, RY[0] + 30, 260, 0], lineColor: '#D9DEE8', lineWidth: 1, name: 'hd-l-u0' },
      textElement('hd-l-b0', [58 + 44, RY[1], PANW - 84, 24], BODY[0], 12, '#52657D'),
      textElement('hd-l-b1', [58 + 44, RY[2], PANW - 84, 24], BODY[1], 12, '#52657D'),
      textElement('hd-l-h1', [58 + 28, RY[3], PANW - 56, 28], HEAD_B, 18, '#0A1020', true),
      { kind: 'shape', geometry: 'line', bbox: [58 + 28, RY[3] + 30, 200, 0], lineColor: '#D9DEE8', lineWidth: 1, name: 'hd-l-u1' },
      textElement('hd-l-b2', [58 + 44, RY[4], PANW - 84, 24], BODY[2], 12, '#52657D'),
      textElement('hd-l-b3', [58 + 44, RY[5], PANW - 84, 24], BODY[3], 12, '#52657D'),
      textElement('hd-l-cap', [58 + 28, PY + PANH - 40, PANW - 56, 24],
        '→ 굵기·크기로 “제목 2개”가 한눈에 구분됩니다', 12, '#17845E', true),
    );

    // ---- 우: Docling 파싱 결과 (블록별 label) ----
    const X = 658;
    const pill = (name, y, txt, bg, bd, tc) => [
      { kind: 'shape', geometry: 'roundRect', bbox: [X + 22, y + 3, 122, 22], fillColor: bg, lineColor: bd, lineWidth: 1, name },
      textElement(`${name}-t`, [X + 22, y + 3, 122, 22], txt, 10, tc, true, 'center'),
    ];
    els.push(
      { kind: 'shape', geometry: 'roundRect', bbox: [X, PY, PANW, PANH], fillColor: '#FFFFFF', lineColor: '#D9DEE8', lineWidth: 1, name: 'hd-r-pan' },
      textElement('hd-r-h', [X + 24, PY + 14, PANW - 48, 16], 'Docling 파싱 결과 — 블록별 label', 11, '#6E7A90'),
    );
    // 위 제목: list_item 으로 분류(오류) → 본문과 같은 평범한 스타일로 렌더
    els.push({ kind: 'shape', geometry: 'roundRect', bbox: [X + 14, RY[0] - 6, PANW - 28, 34], fillColor: '#FDECEC', lineColor: '#F6D5D5', lineWidth: 1, name: 'hd-r-hl0' });
    els.push(...pill('hd-r-lb0', RY[0], 'list_item', '#FDECEC', '#DC5B5B', '#B23A3A'));
    els.push(textElement('hd-r-t0', [X + 156, RY[0], PANW - 186, 24], `• ${HEAD_A}`, 12, '#52657D'));
    els.push(textElement('hd-r-n0', [X + 156, RY[0] + 24, PANW - 186, 16], '제목인데 목록 항목(list_item)으로 분류됨', 9.5, '#B23A3A'));
    // 본문 2줄
    els.push(...pill('hd-r-lb1', RY[1], 'text', '#F1F3F6', '#DBE0E8', '#8A93A3'));
    els.push(textElement('hd-r-t1', [X + 156, RY[1], PANW - 186, 24], BODY[0], 11, '#52657D'));
    els.push(...pill('hd-r-lb2', RY[2], 'text', '#F1F3F6', '#DBE0E8', '#8A93A3'));
    els.push(textElement('hd-r-t2', [X + 156, RY[2], PANW - 186, 24], BODY[1], 11, '#52657D'));
    // 아래 제목: section_header 로 정상 → 굵게
    els.push(...pill('hd-r-lb3', RY[3], 'section_header', '#E7F4EC', '#17845E', '#17845E'));
    els.push(textElement('hd-r-t3', [X + 156, RY[3], PANW - 186, 24], HEAD_B, 14, '#0A1020', true));
    els.push(...pill('hd-r-lb4', RY[4], 'text', '#F1F3F6', '#DBE0E8', '#8A93A3'));
    els.push(textElement('hd-r-t4', [X + 156, RY[4], PANW - 186, 24], BODY[2], 11, '#52657D'));
    els.push(...pill('hd-r-lb5', RY[5], 'text', '#F1F3F6', '#DBE0E8', '#8A93A3'));
    els.push(textElement('hd-r-t5', [X + 156, RY[5], PANW - 186, 24], BODY[3], 11, '#52657D'));
    els.push({ kind: 'shape', geometry: 'line', bbox: [X + 24, PY + PANH - 58, PANW - 48, 0], lineColor: '#E1E6EE', lineWidth: 1, name: 'hd-r-div' });
    els.push(textElement('hd-r-cap', [X + 28, PY + PANH - 44, PANW - 56, 24],
      '→ 같은 형식인데 위 제목만 list_item 으로 분류돼 제목 지위를 잃습니다', 12, '#B23A3A', true));

    const at = s.elements.findIndex((e) => /^title-/.test(e.name || ''));
    s.elements.splice(at < 0 ? s.elements.length : at + 1, 0, ...els);
  })();

  // ===================================================================
  // 최종 편집 패스 25 — 27p('표 오인식 사례') 실제 오검출 문서 3건.
  //   격자·다단 정렬 편집 때문에 Docling 이 TableItem 으로 추출하는 실제 목차/목록.
  //   각 이미지에 붉은 표 박스 오버레이 + 판정/실제 캡션. 하단 통계(sv-12-*, sl-12-*)는 삭제.
  // ===================================================================
  (() => {
    const s = deck.slides.find((sl) =>
      sl.elements.some((e) => e.kind === 'image' && e.media === 'table_grid_examples.png'));
    if (!s) { console.warn('[패스25] 27p(table_grid_examples.png) 슬라이드를 찾지 못함'); return; }
    s.elements = s.elements.filter((e) => !/^(img-12|sv-12-|sl-12-|tm\d)/.test(e.name || ''));

    const RED = '#E04B4B', REDT = '#B23A3A';
    const line = (name, bbox, color, w) => ({ kind: 'shape', geometry: 'line', bbox, lineColor: color, lineWidth: w, name });
    const CW = 392, GAP = 16, CY = 208;
    const XS = [50, 50 + CW + GAP, 50 + 2 * (CW + GAP)]; // 50, 458, 866
    const FW = 356, FTOP = CY + 56;                      // 이미지 프레임(폭 고정, 높이는 원본 비율)
    const CH = 56 + Math.round(FW / (922 / 607)) + 42;   // 카드 높이 = 가장 큰 이미지 기준으로 고정

    const els = [];

    // media 는 흰 여백을 잘라낸 상태 → 프레임을 원본 비율에 정확히 맞춰 붉은 테두리가 콘텐츠에 밀착.
    // 카드 높이는 3장 모두 동일, 이미지 프레임만 원본 비율대로.
    const card = (x, tag, media, ar) => {
      const p = `tm${XS.indexOf(x)}`;
      const fh = Math.round(FW / ar);
      els.push({ kind: 'shape', geometry: 'roundRect', bbox: [x, CY, CW, CH], fillColor: '#FFFFFF', lineColor: '#D9DEE8', lineWidth: 1, name: `${p}-pan` });
      els.push(
        { kind: 'shape', geometry: 'roundRect', bbox: [x + 18, CY + 14, 200, 22], fillColor: '#F1F3F6', lineColor: '#DBE0E8', lineWidth: 1, name: `${p}-tag` },
        textElement(`${p}-tag-t`, [x + 18, CY + 14, 200, 22], tag, 10, '#52657D', true, 'center'),
      );
      // 프레임 = Docling 이 표(TableItem) 하나로 잡은 영역 → 콘텐츠에 밀착한 붉은 테두리
      els.push({ kind: 'shape', geometry: 'rect', bbox: [x + 18, FTOP, FW, fh], fillColor: '#FFFFFF', lineColor: RED, lineWidth: 2, name: `${p}-fr` });
      els.push(imageElement(`${p}-img`, [x + 18, FTOP, FW, fh], media, 'fill'));
      els.push(
        { kind: 'shape', geometry: 'rect', bbox: [x + 18 + FW - 66, FTOP - 15, 66, 15], fillColor: RED, lineWidth: 0, name: `${p}-btag` },
        textElement(`${p}-btag-t`, [x + 18 + FW - 66, FTOP - 15, 66, 15], 'TableItem', 8.5, '#FFFFFF', true, 'center'),
      );
      els.push(textElement(`${p}-vd`, [x + 18, FTOP + fh + 12, CW - 36, 16], '→ 표(TableItem) 하나로 추출됨', 11, REDT, true));
    };

    card(XS[0], 'IR 보고서 목차', 'table_error_1.png', 1106 / 510);
    card(XS[1], 'ESG 보고서 목차', 'table_error_2.png', 922 / 607);
    card(XS[2], '지속가능경영보고서 · 목록', 'table_error_3.png', 580 / 240);

    els.push({ kind: 'shape', geometry: 'roundRect', bbox: [300, 600, 680, 40], fillColor: '#FBF3F3', lineColor: '#EBC9C9', lineWidth: 1, name: 'tm-note' });
    els.push(textElement('tm-note-t', [300, 600, 680, 40],
      '공통 원인 — 셀 경계선이 없어도, 열이 격자처럼 정렬된 좌표만으로 Docling 이 표로 판정', 11.5, '#8A3B3B', true, 'center'));

    const at = s.elements.findIndex((e) => /^title-/.test(e.name || ''));
    s.elements.splice(at < 0 ? s.elements.length : at + 1, 0, ...els);
  })();

  // ===================================================================
  // 최종 편집 패스 26 — 24·26·30p 로직 다이어그램(mermaid SVG)을 네이티브 flow 로.
  //   공통 구조: 입력 → 판정 → 4개 기준(분기) → [제외] → 실행 → [품질검사] → 저장.
  // ===================================================================
  (() => {
    const LC = '#8892A3'; // 커넥터
    const vl = (nm, x, y, h) => ({ kind: 'shape', geometry: 'line', bbox: [x, y, 0, h], lineColor: LC, lineWidth: 1.8, name: nm });
    const hl = (nm, x, y, w) => ({ kind: 'shape', geometry: 'line', bbox: [x, y, w, 0], lineColor: LC, lineWidth: 1.8, name: nm });
    const arw = (nm, x, y) => textElement(nm, [x - 11, y, 22, 16], '▼', 12, '#5B6676', true, 'center');
    const KIND = {
      io: ['#F2F4F7', '#B9C0CC', '#3A4658'],
      decide: ['#EAF2FF', '#8FB4EF', '#123D7A'],
      crit: ['#F5F7FB', '#CDD6E4', '#1A2740'],
      filter: ['#FFF6E9', '#EAD3A8', '#7A5A1E'],
      act: ['#E7F4EC', '#3FA46B', '#17603C'],
    };
    const box = (nm, bbox, txt, kind, fs) => {
      const [f, l, t] = KIND[kind];
      return [
        { kind: 'shape', geometry: 'roundRect', bbox, fillColor: f, lineColor: l, lineWidth: 1.4, name: nm },
        textElement(`${nm}-t`, bbox, txt, fs || 13, t, kind !== 'crit', 'center'),
      ];
    };

    // 공통 빌더: 세로 flow. steps = [{txt,kind,h}], crits = [4 라벨]
    const build = (pfx, cx, top, boxW, crit, layout) => {
      const els = [];
      const { critCols, critW, critH, gap } = layout;
      let y = top;
      const step = (txt, kind, w, h) => {
        els.push(...box(`${pfx}-${step.n = (step.n || 0) + 1}`, [cx - w / 2, y, w, h], txt, kind));
        y += h;
      };
      const LH = layout.linkH || 20;
      const link = (h = LH) => {
        const n = link.n = (link.n || 0) + 1;
        els.push(vl(`${pfx}-v${n}`, cx, y, h - 6));           // 선은 박스 6px 앞에서 멈춤
        els.push(arw(`${pfx}-a${n}`, cx, y + h - 16));         // 삼각형은 선 끝 + 박스 위 여백에
        y += h;
      };

      step(layout.inTxt, 'io', boxW, layout.ioH || 48);
      link();
      step(layout.decideTxt, 'decide', layout.decideW || boxW - 20, layout.decideH || 40);

      // 분기: 판정 → 4 기준
      const rows = Math.ceil(4 / critCols);
      const totalW = critCols * critW + (critCols - 1) * gap;
      const cx0 = cx - totalW / 2;
      const critTop = y + 26;
      els.push(vl(`${pfx}-fanv`, cx, y, 14), hl(`${pfx}-fanh`, cx0 + critW / 2, y + 14, totalW - critW));
      crit.forEach((c, i) => {
        const col = i % critCols, row = Math.floor(i / critCols);
        const bx = cx0 + col * (critW + gap), by = critTop + row * (critH + 16);
        if (row === 0) els.push(vl(`${pfx}-cv${i}`, bx + critW / 2, y + 14, 12));
        els.push(...box(`${pfx}-c${i}`, [bx, by, critW, critH], c, 'crit', 12));
      });
      y = critTop + rows * critH + (rows - 1) * 16;
      // 수렴 (선 → 버스 → 아래로 → 삼각형)
      const conv = y + 14;
      crit.slice(0, critCols).forEach((_, i) => els.push(vl(`${pfx}-uv${i}`, cx0 + i * (critW + gap) + critW / 2, y, 14)));
      els.push(hl(`${pfx}-convh`, cx0 + critW / 2, conv, totalW - critW));
      els.push(vl(`${pfx}-convv`, cx, conv, 16), arw(`${pfx}-conva`, cx, conv + 8));
      y = conv + 24;

      (layout.after || []).forEach(([txt, kind, w, h]) => { step(txt, kind, w || boxW, h || 42); link(); });
      // 마지막 link 제거용: after 가 있으면 이미 link 붙음. 없으면 여기서.
      if (!(layout.after || []).length) link();
      step(layout.saveTxt, 'io', boxW - 10, layout.saveH || 42);
      return els;
    };

    // ---- 24p ----
    (() => {
      const s = deck.slides.find((sl) => sl.elements.some((e) => e.media === 'diagram_reading_order.svg'));
      if (!s) return;
      s.elements = s.elements.filter((e) => e.name !== 'diag-9');
      s.elements.push(...build('ro24', 640, 216, 340,
        ['같은 내용 묶음', '좌우 정렬이 유사함', '상하 위치·현재 순서 불일치', '사이에 다른 요소 없음'],
        {
          inTxt: 'DoclingDocument · 인접한 문서 요소 비교', ioH: 50, linkH: 32, decideH: 46, saveH: 48,
          decideTxt: '순서 교환 기준 확인', decideW: 300,
          critCols: 4, critW: 279, critH: 58, gap: 16,
          after: [['두 요소의 읽기 순서 교환', 'act', 340, 52]],
          saveTxt: '보완된 읽기 순서 저장',
        }));
    })();

    // ---- 26p ----
    (() => {
      const s = deck.slides.find((sl) => sl.elements.some((e) => e.media === 'diagram_heading.svg'));
      if (!s) return;
      s.elements = s.elements.filter((e) => !['diag-11', 'ref-11'].includes(e.name || ''));
      s.elements.push(...build('hd26', 640, 208, 320,
        ['짧은 문구', '주변 본문보다 큰 글자', '위쪽에 충분한 여백', '위·아래 텍스트 밀도'],
        {
          inTxt: '텍스트·목록 요소에서 제목 후보 선택', ioH: 48, linkH: 30, decideH: 44, saveH: 46,
          decideTxt: '승격 기준 확인', decideW: 280,
          critCols: 4, critW: 279, critH: 52, gap: 16,
          after: [
            ['제목이 아닌 요소 제외 (표·캡션·페이지 번호)', 'filter', 440, 48],
            ['section_header 로 승격', 'act', 280, 46],
          ],
          saveTxt: '보완된 제목 정보 저장',
        }));
    })();

    // ---- 30p → 패스28 에서 SVG(image_description_pipeline_flow) 기준으로 전면 재구성 (여기선 손대지 않음) ----
  })();

  // ===================================================================
  // 최종 편집 패스 27 — 29p('이미지 설명의 세 문제') 슬라이드 자체 삭제 후 전체 재번호.
  // ===================================================================
  (() => {
    const norm = (v) => String(v || '').replace(/\s+/g, ' ').trim();
    const i = deck.slides.findIndex((s) =>
      s.elements.some((e) => /^title-/.test(e.name || '') && norm(e.text) === '이미지 설명의 세 문제'));
    if (i < 0) { console.warn('[패스27] 29p(이미지 설명의 세 문제) 슬라이드를 찾지 못함'); return; }
    deck.slides.splice(i, 1);
    deck.slides.forEach((item, idx) => {
      item.number = idx + 1;
      item.elements.forEach((e) => {
        if (/^(page-|div-page-)/.test(e.name || '')) setElementText(e, String(idx + 1).padStart(2, '0'));
      });
    });
  })();

  // ===================================================================
  // 최종 편집 패스 28 — '이미지 설명 개선' 슬라이드를 image_description_pipeline_flow.svg
  //   구조대로 네이티브 재구성 (입력 → 생성 대상 판정 → 유형별 라우팅 → VLM 생성 →
  //   품질 게이트 → 저장/폐기). 기존 좌측 4단계 리스트(sd/stt/st-15-*)도 제거.
  // ===================================================================
  (() => {
    const norm = (v) => String(v || '').replace(/\s+/g, ' ').trim();
    const s = deck.slides.find((sl) =>
      sl.elements.some((e) => /^title-/.test(e.name || '') && norm(e.text) === '이미지 설명 개선'));
    if (!s) { console.warn('[패스28] 이미지 설명 개선 슬라이드를 찾지 못함'); return; }
    s.elements = s.elements.filter((e) => !/^(diag-15|im30-|sd-15-|stt-15-|st-15-)/.test(e.name || '')
      && e.media !== 'diagram_image.svg');

    const K = {
      io: ['#F2F4F7', '#B9C0CC', '#3A4658'],
      dec: ['#EAF2FF', '#8FB4EF', '#123D7A'],
      route: ['#FFF6E9', '#EAD3A8', '#7A5A1E'],
      no: ['#FDECEC', '#DC5B5B', '#B23A3A'],
      yes: ['#E7F4EC', '#3FA46B', '#17603C'],
    };
    const els = [];
    const box = (nm, x, y, w, h, kind, title, sub) => {
      const [f, l, t] = K[kind];
      els.push({ kind: 'shape', geometry: 'roundRect', bbox: [x, y, w, h], fillColor: f, lineColor: l, lineWidth: 1.4, name: nm });
      els.push(textElement(`${nm}-t`, [x, sub ? y + 6 : y, w, sub ? 20 : h], title, 12.5, t, true, 'center'));
      if (sub) els.push(textElement(`${nm}-s`, [x + 6, y + 25, w - 12, 16], sub, 9.5, t, false, 'center'));
    };
    const vl = (nm, x, y, h) => els.push({ kind: 'shape', geometry: 'line', bbox: [x, y, 0, h], lineColor: '#8892A3', lineWidth: 1.8, name: nm });
    const hl = (nm, x, y, w) => els.push({ kind: 'shape', geometry: 'line', bbox: [x, y, w, 0], lineColor: '#8892A3', lineWidth: 1.8, name: nm });
    const ar = (nm, x, y) => els.push(textElement(nm, [x - 11, y, 22, 16], '▼', 12, '#5B6676', true, 'center'));

    // ===== 좌·우를 하나의 중앙 그룹으로 (21·22p 참고). 좌: 설명 / 우: 흐름도 =====
    const LX = 236, LW = 384, LTOP = 222;
    els.push(textElement('idpL-h1', [LX, LTOP, LW, 20], '기존 이미지 설명의 문제', 14, '#B23A3A', true));
    [
      ['할루시네이션', '이미지·문맥에 없는 내용을 지어냄'],
      ['무효 응답 저장', '거부·무한 반복 응답이 그대로 저장'],
      ['무의미 이미지', '로고·아이콘 등에도 설명 생성'],
    ].forEach(([t, d], i) => {
      const y = LTOP + 34 + i * 54;
      els.push({ kind: 'shape', geometry: 'ellipse', bbox: [LX, y + 5, 8, 8], fillColor: '#DC5B5B', lineColor: '#DC5B5B', lineWidth: 1, name: `idpL-pb${i}` });
      els.push(textElement(`idpL-pt${i}`, [LX + 22, y, LW - 22, 20], t, 13.5, '#0A1020', true));
      els.push(textElement(`idpL-pd${i}`, [LX + 22, y + 21, LW - 22, 18], d, 11.5, '#52657D'));
    });
    els.push({ kind: 'shape', geometry: 'line', bbox: [LX, LTOP + 194, LW, 0], lineColor: '#E1E6EE', lineWidth: 1, name: 'idpL-div' });
    els.push(textElement('idpL-h2', [LX, LTOP + 210, LW, 20], '해결 — 3단계 보완', 14, '#17603C', true));
    [
      ['1', '생성 대상 선별', '카테고리로 설명 생성 여부 판단'],
      ['2', '유형별 프롬프트 매칭', '유형에 맞는 VLM 지시문 매칭'],
      ['3', '환각 검증', '환각 있으면 재검증 후 요약 확정'],
    ].forEach(([n, t, d], i) => {
      const y = LTOP + 244 + i * 60;
      els.push({ kind: 'shape', geometry: 'ellipse', bbox: [LX, y + 1, 24, 24], fillColor: '#2878D1', lineColor: '#2878D1', lineWidth: 1, name: `idpL-sb${i}` });
      els.push(textElement(`idpL-sn${i}`, [LX, y + 1, 24, 24], n, 13, '#FFFFFF', true, 'center'));
      els.push(textElement(`idpL-st${i}`, [LX + 38, y, LW - 38, 22], t, 14, '#0A1020', true));
      els.push(textElement(`idpL-sd${i}`, [LX + 38, y + 23, LW - 38, 18], d, 11.5, '#52657D'));
    });

    // ===== 우측: 파이프라인 흐름도 (SVG 구조) — 좌측 그룹 바로 옆에 붙임 =====
    const DX = LX + LW + 44;
    const CX = DX + 185;
    const FL = DX + 90, FR = DX + 280;
    box('idp-in', CX - 110, 198, 220, 34, 'io', 'PictureItem 입력');
    vl('idp-v1', CX, 232, 6); ar('idp-a1', CX, 232);
    box('idp-dec1', CX - 135, 244, 270, 44, 'dec', '생성 대상인가?', '카테고리(면적·분류)로 판단');
    vl('idp-f1v', CX, 288, 8); hl('idp-f1h', FL, 296, FR - FL);
    vl('idp-f1l', FL, 296, 6); ar('idp-f1la', FL, 298);
    vl('idp-f1r', FR, 296, 6); ar('idp-f1ra', FR, 298);
    box('idp-no1', FL - 90, 308, 180, 44, 'no', '제외', '로고·아이콘 등');
    box('idp-yes1', FR - 90, 308, 180, 44, 'yes', '대상', '차트·도면 등');
    vl('idp-e1v', FR, 352, 10); hl('idp-e1h', CX, 362, FR - CX);
    vl('idp-e1d', CX, 362, 10); ar('idp-e1a', CX, 368);
    box('idp-route', CX - 185, 378, 370, 46, 'route', '유형별 프롬프트 라우팅', '차트=축·단위 / 도면=치수·부품명 …');
    vl('idp-v2', CX, 424, 8); ar('idp-a2', CX, 426);
    box('idp-vlm', CX - 110, 438, 220, 34, 'io', 'VLM 설명 생성');
    vl('idp-v3', CX, 472, 8); ar('idp-a3', CX, 474);
    box('idp-dec2', CX - 135, 486, 270, 44, 'dec', '품질 게이트', '환각·반복·거부 응답 검사');
    vl('idp-f2v', CX, 530, 8); hl('idp-f2h', FL, 538, FR - FL);
    vl('idp-f2l', FL, 538, 6); ar('idp-f2la', FL, 540);
    vl('idp-f2r', FR, 538, 6); ar('idp-f2ra', FR, 540);
    box('idp-no2', FL - 90, 550, 180, 42, 'no', '폐기', '저장 안 함');
    box('idp-yes2', FR - 90, 550, 180, 42, 'yes', '저장', '설명 확정');
    vl('idp-e2v', FR, 592, 10); hl('idp-e2h', CX, 602, FR - CX);
    vl('idp-e2d', CX, 602, 8); ar('idp-e2a', CX, 606);
    box('idp-out', CX - 130, 616, 260, 36, 'io', '검증된 이미지 설명 저장');

    const at = s.elements.findIndex((e) => /^title-/.test(e.name || ''));
    s.elements.splice(at < 0 ? s.elements.length : at + 1, 0, ...els);
  })();

  // ===================================================================
  // 최종 편집 패스 29 — '전체 기능 시연 영상' 슬라이드 삭제 후 전체 재번호.
  // ===================================================================
  (() => {
    const norm = (v) => String(v || '').replace(/\s+/g, ' ').trim();
    const titles = ['전체 기능 시연 영상', '전체 기능은 실제 시연 영상으로 확인합니다'];
    const i = deck.slides.findIndex((s) =>
      s.elements.some((e) => /^title-/.test(e.name || '') && titles.includes(norm(e.text))));
    if (i < 0) { console.warn('[패스29] 전체 기능 시연 영상 슬라이드를 찾지 못함'); return; }
    deck.slides.splice(i, 1);
    deck.slides.forEach((item, idx) => {
      item.number = idx + 1;
      item.elements.forEach((e) => {
        if (/^(page-|div-page-)/.test(e.name || '')) setElementText(e, String(idx + 1).padStart(2, '0'));
      });
    });
  })();

  // ===================================================================
  // 최종 편집 패스 30 — FUTURE WORK: '자체 평가 의견'(05장 표지) 뒤에 개선 계획 표 1장 추가.
  //   juyeon 브랜치(56e61b38)의 패스14 를 통합 덱 크롬·표 스타일(35p)에 맞춰 이식.
  // ===================================================================
  (() => {
    const norm = (v) => String(v || '').replace(/\s+/g, ' ').trim();
    const titleOf = (s) => {
      const t = s.elements.find((e) => /^(title-|div-title-)/.test(e.name || '') && norm(e.text));
      return t ? norm(t.text) : '';
    };
    const baseIdx = deck.slides.findIndex((s) => titleOf(s) === '판정 체계');
    const atIdx = deck.slides.findIndex((s) => titleOf(s) === '자체 평가 의견');
    if (baseIdx < 0 || atIdx < 0) { console.warn('[패스30] 기준/삽입 위치 슬라이드를 찾지 못함'); return; }
    if (deck.slides.some((s) => titleOf(s) === '향후 과제')) return;

    const s = clone(deck.slides[baseIdx]);
    s.elements = s.elements.filter((e) => /^(top-accent-|top-rule-|context-|page-|title-|accent-|ctx-logo|inst-logo)/.test(e.name || ''));
    setElementText(s.elements.find((e) => e.name === 'context-16'), '·   05 자체 평가 의견');
    setElementText(s.elements.find((e) => e.name === 'title-16'), '향후 과제');
    s.sources = ['docs/설계 및 구현/3_중간발표 이후/작업기록/ (Parsing · Hybrid Search · Agent 개선 계획)'];

    const COLS = [
      { x: 56, w: 130, h: '영역' },
      { x: 186, w: 360, h: '현재 한계' },
      { x: 546, w: 430, h: '개선 방향' },
      { x: 976, w: 248, h: '기대 효과' },
    ];
    const HY = 200, HH = 40, RY = HY + HH, rowH = 132;
    const ROWS = [
      {
        area: 'Parsing', accent: '#2878D1', effClr: '#2878D1',
        limitKey: '읽기 순서 보정이 동일 parent 내 인접 요소에 한정',
        limitSub: '제목·표 구조 복원에도 미해결 사례가 남음',
        bullets: ['parent·섹션 단위 읽기 순서 재구성', '폰트 스타일까지 반영한 제목 판별', '표 셀 구조·병합 범위 자동 복원'],
        effect: '문서 구조 정보의\n정확성·완결성 향상',
      },
      {
        area: 'Hybrid\nSearch', accent: '#168A86', effClr: '#17845E',
        limitKey: 'Top-20 결과만으로 충분한 근거를 보장하지 못함',
        limitSub: '검색 결과와 답변 생성 사이에 정보 누락 발생',
        bullets: ['별도 reranker 적용', '핵심 근거 정보 보존', 'Agent 전달 인터페이스 보완 (누락 방지)'],
        effect: '근거 품질 향상 및\n정보 누락 최소화',
      },
      {
        area: 'Agent', accent: '#22375C', effClr: '#7A5CB0',
        limitKey: '검색에 성공해도 최종 답변 완결성이 부족',
        limitSub: '반복될수록 답변이 짧아지고 핵심 문장이 누락',
        bullets: ['표·이미지 등 구조 정보 보존', '답변 전 필수 사실 커버리지 검증', '호출 예산·종료 기준 강화'],
        effect: '답변 완결성 향상,\n불필요한 반복 검색 감소',
      },
    ];
    const tableBottom = RY + rowH * ROWS.length;

    s.elements.push(
      { kind: 'shape', geometry: 'rect', bbox: [56, HY - 3, 1168, 3], fillColor: '#101728', lineWidth: 0, name: 'fw-htop' },
      { kind: 'shape', geometry: 'rect', bbox: [56, HY, 1168, HH], fillColor: '#E7EBF0', lineWidth: 0, name: 'fw-hbar' },
    );
    COLS.forEach((c, i) => s.elements.push(
      textElement(`fw-h-${i}`, [c.x + 16, HY, c.w - 24, HH], c.h, 14, '#101728', true),
    ));
    [186, 546, 976].forEach((x, i) => s.elements.push(
      { kind: 'shape', geometry: 'line', bbox: [x, HY, 0, tableBottom - HY], lineColor: '#E7EBF1', lineWidth: 1, name: `fw-vl-${i}` },
    ));

    ROWS.forEach((r, ri) => {
      const y = RY + rowH * ri;
      s.elements.push(
        { kind: 'shape', geometry: 'rect', bbox: [66, y + 22, 4, 44], fillColor: r.accent, lineWidth: 0, name: `fw-acc-${ri}` },
        textElement(`fw-area-${ri}`, [82, y + 18, 104, 62], r.area, 17, '#101728', true),
        textElement(`fw-limk-${ri}`, [202, y + 16, 336, 46], r.limitKey, 14.5, '#101728', true),
        textElement(`fw-lims-${ri}`, [202, y + 64, 336, 40], r.limitSub, 12.5, '#5B6577'),
        textElement(`fw-bul-${ri}`, [562, y + 16, 404, rowH - 30], r.bullets.map((b) => `•  ${b}`).join('\n'), 13.5, '#20283A'),
        { kind: 'shape', geometry: 'ellipse', bbox: [992, y + 50, 26, 26], fillColor: r.effClr, lineWidth: 0, name: `fw-eff-ic-${ri}` },
        textElement(`fw-eff-ar-${ri}`, [992, y + 50, 26, 26], '→', 14, '#FFFFFF', true, 'center'),
        textElement(`fw-eff-${ri}`, [1028, y + 32, 192, 68], r.effect, 13.5, r.effClr, true),
      );
      if (ri > 0) s.elements.push({ kind: 'shape', geometry: 'line', bbox: [56, y, 1168, 0], lineColor: '#D9DEE8', lineWidth: 1, name: `fw-rl-${ri}` });
    });
    s.elements.push({ kind: 'shape', geometry: 'line', bbox: [56, tableBottom, 1168, 0], lineColor: '#101728', lineWidth: 1, name: 'fw-rl-bot' });

    deck.slides.splice(atIdx + 1, 0, s);
    deck.slides.forEach((item, idx) => {
      item.number = idx + 1;
      item.elements.forEach((e) => {
        if (/^(page-|div-page-)/.test(e.name || '')) setElementText(e, String(idx + 1).padStart(2, '0'));
      });
    });
  })();

  // ===================================================================
  // 최종 편집 패스 31 — 04장을 4개 소구간으로 나누는 서브 표지 슬라이드 추가.
  //   04-1 Agent(전체 시스템 구조 뒤) · 04-2 문서 처리(Deep Agent 실행 구조 뒤) ·
  //   04-3 플랫폼 평가(직렬화와 임베딩 뒤) · 04-4 운영자 콘솔(스킬 사용 전후 비교 뒤).
  //   스타일: 01~05 챕터 표지(div-*)와 동일, 번호만 04-N.
  // ===================================================================
  (() => {
    const norm = (v) => String(v || '').replace(/\s+/g, ' ').trim();
    const titleOf = (s) => {
      const t = s.elements.find((e) => /^(title-|div-title-)/.test(e.name || '') && norm(e.text));
      return t ? norm(t.text) : '';
    };
    const subDivider = (no, title, tag) => ({
      background: '#E8EEF6',
      elements: [
        { kind: 'shape', geometry: 'rect', bbox: [0, 0, 1280, 5], fillColor: '#F8C944', lineWidth: 0, name: `top-accent-${tag}` },
        { kind: 'shape', geometry: 'rect', bbox: [0, 693, 18, 720], fillColor: '#2878D1', lineWidth: 0, name: `accent-${tag}` },
        { kind: 'image', bbox: [64, 46, 34, 16], media: 'halil-logo.png', name: `cover-logo-${tag}` },
        textElement(`div-no-${tag}`, [64, 72, 640, 150], no, 88, '#2878D1', true),
        textElement(`div-title-${tag}`, [62, 300, 1156, 120], title, 84, '#0A1020', true, 'center'),
        { kind: 'shape', geometry: 'straightConnector1', bbox: [66, 566, 1120, 0], lineColor: '#BAC8DB', lineWidth: 1, name: `div-line-${tag}` },
        textElement(`div-page-${tag}`, [1140, 595, 50, 28], '00', 15, '#6C7482', true, 'right'),
        { kind: 'image', bbox: [1019.56, 680, 78.89, 25], media: 'image2.png', name: `inst-logo-a-${tag}` },
        { kind: 'image', bbox: [1138.95, 680, 84.09, 25], media: 'image3.png', name: `inst-logo-b-${tag}` },
      ],
    });
    const PLAN = [
      ['전체 시스템 구조', '04-1', 'Agent', 's041'],
      ['Deep Agent 실행 구조', '04-2', '문서 처리', 's042'],
      ['직렬화와 임베딩', '04-3', '플랫폼 평가', 's043'],
      ['스킬 사용 전후 비교', '04-4', '운영 ・ 통제', 's044'],
    ];
    PLAN.forEach(([anchor, no, title, tag]) => {
      if (deck.slides.some((s) => s.elements.some((e) => e.name === `div-no-${tag}`))) return;
      const i = deck.slides.findIndex((s) => titleOf(s) === norm(anchor));
      if (i < 0) { console.warn(`[패스31] 앵커('${anchor}')를 찾지 못함`); return; }
      deck.slides.splice(i + 1, 0, subDivider(no, title, tag));
    });

    deck.slides.forEach((item, idx) => {
      item.number = idx + 1;
      item.elements.forEach((e) => {
        if (/^(page-|div-page-)/.test(e.name || '')) setElementText(e, String(idx + 1).padStart(2, '0'));
      });
    });
  })();

  // ===================================================================
  // 최종 편집 패스 32 — '직렬화와 임베딩' 뒤에 '문서 처리 파이프라인 평가' 빈 슬라이드
  //   (표준 크롬 + 제목만, 본문은 이후 추가 예정).
  // ===================================================================
  (() => {
    const norm = (v) => String(v || '').replace(/\s+/g, ' ').trim();
    const titleOf = (s) => {
      const t = s.elements.find((e) => /^(title-|div-title-)/.test(e.name || '') && norm(e.text));
      return t ? norm(t.text) : '';
    };
    if (deck.slides.some((s) => titleOf(s) === '문서 처리 파이프라인 평가')) return;
    const baseIdx = deck.slides.findIndex((s) => titleOf(s) === '판정 체계');
    const atIdx = deck.slides.findIndex((s) => titleOf(s) === '직렬화와 임베딩');
    if (baseIdx < 0 || atIdx < 0) { console.warn('[패스32] 기준/삽입 위치 슬라이드를 찾지 못함'); return; }

    const s = clone(deck.slides[baseIdx]);
    s.elements = s.elements.filter((e) => /^(top-accent-|top-rule-|context-|page-|title-|accent-|ctx-logo|inst-logo)/.test(e.name || ''));
    setElementText(s.elements.find((e) => e.name === 'title-16'), '문서 처리 파이프라인 평가');
    s.sources = [];

    deck.slides.splice(atIdx + 1, 0, s);
    deck.slides.forEach((item, idx) => {
      item.number = idx + 1;
      item.elements.forEach((e) => {
        if (/^(page-|div-page-)/.test(e.name || '')) setElementText(e, String(idx + 1).padStart(2, '0'));
      });
    });
  })();

  // ===================================================================
  // 최종 편집 패스 33 — '감사합니다' 뒤에 부록 A 8장 삽입.
  //   통합 덱 표준 크롬(크롬만 클론) + title-16(부록 h1) + 본문은
  //   부록 HTML 의 .content 영역만 1172×472 로 캡처한 이미지.
  // ===================================================================
  (() => {
    const norm = (v) => String(v || '').replace(/\s+/g, ' ').trim();
    const titleOf = (s) => {
      const t = s.elements.find((e) => /^(title-|div-title-)/.test(e.name || '') && norm(e.text));
      return t ? norm(t.text) : '';
    };
    if (deck.slides.some((s) => s.elements.some((e) => e.name === 'apx-img-1'))) return;
    const baseIdx = deck.slides.findIndex((s) => titleOf(s) === '판정 체계');
    let at = deck.slides.findIndex((s) => s.elements.some((e) => norm(e.text) === '감사합니다'));
    if (baseIdx < 0) { console.warn('[패스33] 기준 슬라이드(판정 체계)를 찾지 못함'); return; }
    if (at < 0) at = deck.slides.length - 1;

    const TITLES = [
      '시스템 처리 흐름도', '그래프 조립', 'Root 반복 루프', '미들웨어가 붙는 지점',
      '보안과 가드레일', 'Todo 미들웨어', '직접 구현한 코드 — 파싱·에이전트', '직접 구현한 코드 — MCP·Tool 호출',
    ];
    const apx = TITLES.map((title, k) => {
      const s = clone(deck.slides[baseIdx]);
      s.elements = s.elements.filter((e) => /^(top-accent-|top-rule-|context-|page-|title-|accent-|ctx-logo|inst-logo)/.test(e.name || ''));
      setElementText(s.elements.find((e) => e.name === 'context-16'), `·   부록 A · ${k + 1} / 8`);
      setElementText(s.elements.find((e) => e.name === 'title-16'), title);
      s.elements.push(imageElement(`apx-img-${k + 1}`, [56, 158, 1168, 500], `appendix_a_0${k + 1}.png`, 'contain'));
      s.sources = ['부록/07_에이전트_발표_부록_A_슬라이드.html'];
      return s;
    });
    deck.slides.splice(at + 1, 0, ...apx);

    deck.slides.forEach((item, idx) => {
      item.number = idx + 1;
      item.elements.forEach((e) => {
        if (/^(page-|div-page-)/.test(e.name || '')) setElementText(e, String(idx + 1).padStart(2, '0'));
      });
    });
  })();

  // ===================================================================
  // 최종 편집 패스 34 — '문서 처리 파이프라인 평가' 슬라이드 본문 채우기.
  //   4개 보완 레이어(읽기순서·제목·표·이미지)의 hold-out 검증 수치를 2×2 표로.
  // ===================================================================
  (() => {
    const norm = (v) => String(v || '').replace(/\s+/g, ' ').trim();
    const s = deck.slides.find((sl) =>
      sl.elements.some((e) => /^title-/.test(e.name || '') && norm(e.text) === '문서 처리 파이프라인 평가'));
    if (!s) { console.warn('[패스34] 문서 처리 파이프라인 평가 슬라이드를 찾지 못함'); return; }
    if (s.elements.some((e) => e.name === 'dpe-sub')) return;

    const COLOR = ['#155EEF', '#7F56D9', '#F79009', '#06AED4'];
    const DARK = ['#0B1F44', '#3E1C76', '#7A2E0E', '#064E5B'];
    const LIGHT = ['#EAF2FF', '#F4EBFF', '#FFF4E5', '#E6F9FB'];
    const GRN = '#17845E', RED = '#B23A3A';
    const els = [];
    els.push(textElement('dpe-sub', [58, 150, 1160, 20],
      '4개 보완 레이어를 hold-out 문서로 각각 검증 — 실제 데이터 손상(오보정) 0건을 유지하며 오류 교정', 12, '#52657D', true));

    // quad: 카드 + 제목 + 헤드라인 + 표(+ 각주)
    const quad = (qi, x, y, w, h, li, title, headline, headers, colW, rows, foot) => {
      const p = `dpe${qi}`;
      els.push({ kind: 'shape', geometry: 'roundRect', bbox: [x, y, w, h], fillColor: '#FFFFFF', lineColor: '#DCE1E9', lineWidth: 1, name: `${p}-pan` });
      els.push({ kind: 'shape', geometry: 'rect', bbox: [x, y + 16, 4, 22], fillColor: COLOR[li], lineWidth: 0, name: `${p}-acc` });
      els.push(textElement(`${p}-h`, [x + 18, y + 11, w - 36, 22], title, 13.5, DARK[li], true));
      els.push(textElement(`${p}-hl`, [x + 18, y + 34, w - 36, 16], headline, 9.5, '#52657D', true));
      const tx = x + 16, tw = w - 32;
      let ty = y + 56;
      els.push({ kind: 'shape', geometry: 'rect', bbox: [tx, ty, tw, 22], fillColor: '#EEF1F5', lineWidth: 0, name: `${p}-hb` });
      let cx = tx;
      headers.forEach((hh, ci) => {
        els.push(textElement(`${p}-hc${ci}`, [cx + 5, ty, colW[ci] - 10, 22], hh, 8.5, '#3A4658', true, ci === 0 ? 'left' : 'center'));
        cx += colW[ci];
      });
      const rh = 33;
      rows.forEach((r, ri) => {
        const ry = ty + 22 + ri * rh;
        if (r.hl) els.push({ kind: 'shape', geometry: 'rect', bbox: [tx, ry, tw, rh], fillColor: r.hl, lineWidth: 0, name: `${p}-rhl${ri}` });
        els.push({ kind: 'shape', geometry: 'line', bbox: [tx, ry + rh, tw, 0], lineColor: '#E7EBF1', lineWidth: 1, name: `${p}-rl${ri}` });
        let rcx = tx;
        r.cells.forEach((c, ci) => {
          const cc = typeof c === 'string' ? { t: c } : c;
          const first = ci === 0;
          els.push(textElement(`${p}-c${ri}-${ci}`, [rcx + 5, ry, colW[ci] - 10, rh], cc.t,
            first ? 9.5 : 10, cc.c || (first ? '#20283A' : '#37414F'), first ? true : !!cc.b, first ? 'left' : 'center'));
          rcx += colW[ci];
        });
      });
      if (foot) els.push(textElement(`${p}-ft`, [x + 18, ty + 22 + rows.length * rh + 8, w - 36, 26], foot, 8.5, '#8A93A3'));
    };

    const g = (t) => ({ t, c: GRN, b: true });
    const QY1 = 178, QY2 = 422, QW = 576, QH = 232, QXL = 56, QXR = 648;

    quad(1, QXL, QY1, QW, QH, 0, '읽기 순서 복원', '복원 성공률 0% → 100% · 오복원 0건',
      ['구분', '검증 오류', '정상 복원', '오복원', '잔존', '성공률'],
      [120, 88, 88, 70, 70, 108],
      [
        { cells: ['기본 Docling', '60건', '0건', '–', '60건', '0%'] },
        { cells: [{ t: '읽기 순서 보정', c: DARK[0], b: true }, '60건', g('60건'), g('0건'), g('0건'), g('100%')], hl: LIGHT[0] },
      ],
      '※ 부록 A 인접 요소의 국소 역전 재현율 — 전체 읽기 순서 오류 재현율은 아님');

    quad(2, QXR, QY1, QW, QH, 1, '제목 추출 보완', 'F1 0 → 46.7% (정밀도 77.8% · 재현율 33.3%)',
      ['구분', '정확', '오승격', '미검출', '정밀도', '재현율', 'F1'],
      [104, 60, 66, 66, 78, 78, 92],
      [
        { cells: ['기본 Docling', '0건', '0건', '21건', '0%', '0%', '0%'] },
        { cells: [{ t: '제목 추출 보완', c: DARK[1], b: true }, g('7건'), { t: '2건', c: RED, b: true }, '14건', g('77.8%'), '33.3%', g('46.7%')], hl: LIGHT[1] },
      ],
      '※ 공개 문서 5개 · 19p · list_item 122건 전수 라벨링 · 실제 제목 21건');

    quad(3, QXL, QY2, QW, QH, 2, '표 판별 · 비표 오탐 게이트', '실제 표 오제거 0건 — 규칙 미해당 시 통과(fail-open)',
      ['평가 문서 (held-out)', '표', '비표(오염률)', '게이트 검출', 'FN'],
      [210, 46, 108, 96, 84],
      [
        { cells: ['현대모비스 지속가능경영보고서 (167p)', '217', '17건 (7.8%)', '0 / 17', '0'] },
        { cells: ['041_디지털헬스케어 보안모델 (34p)', '43', '0건 (0%)', '–', '0'] },
        { cells: ['011_공공분야 가명정보 안내서 (38p)', '21', '1건 (4.8%)', '1 / 1', '0'] },
      ],
      '※ 게이트 검출 = 알려진 비표 중 제외 판정 비율 · FN = 실제 표 오제거');

    quad(4, QXR, QY2, QW, QH, 3, '이미지 설명 품질', '믿고 쓸 수 있는 설명 48.5% → 63.2%',
      ['지표', 'Before', 'After', '개선'],
      [244, 98, 98, 104],
      [
        { cells: ['이미지–설명 유사도 (5점)', { t: '3.60', c: RED }, g('4.07'), g('▲ 0.47')] },
        { cells: ['신뢰 가능 설명 비율', { t: '48.5%', c: RED }, g('63.2%'), g('▲ 14.7%p')] },
        { cells: ['허위 서술(환각) 비율', { t: '35.3%', c: RED }, g('30.9%'), g('▼ 4.4%p')] },
      ],
      '※ 신뢰 가능 = 정확 + 무환각 + 고득점 모두 만족 · 환각 비율은 낮을수록 좋음');

    const at = s.elements.findIndex((e) => /^title-/.test(e.name || ''));
    s.elements.splice(at < 0 ? s.elements.length : at + 1, 0, ...els);
  })();

  // ===================================================================
  // 최종 편집 패스 35 — 운영 콘솔 4장 재구성 (juyeon b02a6b07 이식).
  //   흰 프레임 제거 · 새 고해상 스크린샷(ops_01~04) · 1px 회색 테두리 ·
  //   40·41p 좌우 2분할 · 42p 중앙 1장 + 단일 캡션.
  // ===================================================================
  (() => {
    const BORDER = '#B7BEC9';
    const findSlide = (elName) => deck.slides.find((sl) => sl.elements.some((e) => e.name === elName));
    const border = (bbox, name) => ({ kind: 'shape', geometry: 'rect', bbox: bbox.slice(), lineColor: BORDER, lineWidth: 1, name });
    const swap = (s, elName, media, bbox) => {
      const e = s.elements.find((x) => x.name === elName);
      if (!e) { console.warn(`[패스35] ${elName} 요소를 찾지 못함`); return; }
      e.media = media; e.bbox = bbox.slice(); e.fit = 'fill';
      s.elements.push(border(bbox, `${elName}-border`));
    };

    // 스크린샷 뒤 흰/둥근 프레임 전부 제거 (운영 콘솔 4장)
    deck.slides.forEach((sl) => {
      if (sl.elements.some((e) => /^ops-.*-frame$/.test(e.name || ''))) {
        sl.elements = sl.elements.filter((e) => !/^ops-.*-frame$/.test(e.name || ''));
      }
    });

    // 1) 운영 상태 통합 관리 — ops_01 크게 1장, 캡션 위로
    (() => {
      const s = findSlide('ops-overview');
      if (!s) { console.warn('[패스35] ops-overview 슬라이드 없음'); return; }
      ['caption-1', 'caption-1-line'].forEach((n) => {
        const e = s.elements.find((x) => x.name === n);
        if (e) e.bbox = [e.bbox[0], e.bbox[1] - 14, e.bbox[2], e.bbox[3]];
      });
      swap(s, 'ops-overview', 'ops_01.png', [282, 190, 716, 474]);
    })();

    // 2) 연결 서비스·모델 구성 — 좌 ops_02-1 / 우 ops_02-2
    (() => {
      const s = findSlide('ops-connectors');
      if (!s) { console.warn('[패스35] ops-connectors 슬라이드 없음'); return; }
      swap(s, 'ops-connectors', 'ops_02-1.png', [56, 206, 574, 352]);
      swap(s, 'ops-models', 'ops_02-2.png', [650, 206, 574, 352]);
    })();

    // 3) 커스텀 도구·가드레일 관리 — 좌 ops_03-1 / 우 ops_03-2
    (() => {
      const s = findSlide('ops-tools');
      if (!s) { console.warn('[패스35] ops-tools 슬라이드 없음'); return; }
      swap(s, 'ops-tools', 'ops_03-1.png', [56, 206, 574, 352]);
      swap(s, 'ops-guardrails', 'ops_03-2.png', [650, 206, 574, 352]);
    })();

    // 4) 실행 현황·도구 사용 추적 — 중앙 1장 + 단일 캡션
    (() => {
      const s = findSlide('ops-usage');
      if (!s) { console.warn('[패스35] ops-usage 슬라이드 없음'); return; }
      s.elements = s.elements.filter((e) => !/^(ops-tool-usage|caption-4-)/.test(e.name || ''));
      const src = deck.slides.flatMap((x) => x.elements).find((e) => e.name === 'caption-1');
      const srcTick = deck.slides.flatMap((x) => x.elements).find((e) => e.name === 'caption-1-line');
      if (src && srcTick) {
        const tick = clone(srcTick); tick.name = 'caption-4-line';
        const cap = clone(src); cap.name = 'caption-4';
        setElementText(cap, '팀・모델・도구별 사용 현황');
        s.elements.push(tick, cap);
      }
      swap(s, 'ops-usage', 'ops_04.png', [313, 190, 654, 471]);
    })();
  })();

  // ===================================================================
  // 최종 편집 패스 36 — 21p(12단계 파싱 파이프라인) 카드 디자인 순화 (juyeon _0903 이식).
  //   진한 파랑 강조 카드(#CFE1FA)를 은은한 파랑 + 굵은 테두리로, 단계명·번호 글자 확대.
  // ===================================================================
  (() => {
    const norm = (v) => String(v || '').replace(/\s+/g, ' ').trim();
    const s = deck.slides.find((sl) =>
      sl.elements.some((e) => /^title-/.test(e.name || '') && norm(e.text) === '12단계 파싱 파이프라인'));
    if (!s) { console.warn('[패스36] 12단계 파싱 파이프라인 슬라이드를 찾지 못함'); return; }
    if (s.elements.some((e) => (e.fillColor || '').toUpperCase() === '#E8F1FC')) return;
    s.elements.forEach((e) => {
      if ((e.fillColor || '').toUpperCase() === '#CFE1FA') {
        e.fillColor = '#E8F1FC'; e.lineColor = '#5E93D6'; e.lineWidth = 2;
      }
    });
    const bump = (rx, size, widen) => s.elements.forEach((e) => {
      if (!rx.test(e.name || '')) return;
      if (e.textStyle) e.textStyle.fontSize = size;
      (e.paragraphs || []).forEach((p) => {
        if (p.resolvedTextStyle) p.resolvedTextStyle.fontSize = size;
        (p.runs || []).forEach((r) => { r.fontSize = size; });
      });
      if (widen) e.bbox = [e.bbox[0], e.bbox[1], widen, e.bbox[3]];
    });
    bump(/^s19n-t\d+$/, 14, 245);
    bump(/^s19n-n\d+$/, 12.5);
  })();

  // ===================================================================
  // 최종 편집 패스 37 — 32p(직렬화와 임베딩) 본문을 juyeon _0903 레이아웃과 동일하게 재구성.
  //   직렬화 = 요소/방식 표, 임베딩 = 3카드(512토큰 카드 보조설명 2줄), 하단 tokenizer 콜아웃 밴드.
  // ===================================================================
  (() => {
    const norm = (v) => String(v || '').replace(/\s+/g, ' ').trim();
    const s = deck.slides.find((sl) =>
      sl.elements.some((e) => /^title-/.test(e.name || '') && norm(e.text) === '직렬화와 임베딩'));
    if (!s) { console.warn('[패스37] 직렬화와 임베딩 슬라이드를 찾지 못함'); return; }
    if (s.elements.some((e) => e.name === 'dz-t-hbg')) return;
    // 기존 본문(ck-*, dz-*) 제거, 크롬만 유지
    s.elements = s.elements.filter((e) => !/^(ck-|dz-)/.test(e.name || ''));

    const els = [];
    els.push(textElement('ck-s-h', [72, 198, 500, 26], '직렬화', 16, '#2878D1', true));
    // 직렬화 표
    els.push(
      { kind: 'shape', geometry: 'rect', bbox: [72, 228, 1136, 3], fillColor: '#101728', lineWidth: 0, name: 'dz-t-top' },
      { kind: 'shape', geometry: 'rect', bbox: [72, 231, 1136, 28], fillColor: '#E7EBF0', lineWidth: 0, name: 'dz-t-hbg' },
      textElement('dz-t-h0', [88, 231, 190, 28], '요소', 13, '#3B4656', true),
      textElement('dz-t-h1', [292, 231, 916, 28], '직렬화 방식', 13, '#3B4656', true),
      { kind: 'shape', geometry: 'line', bbox: [72, 259, 1136, 0], lineColor: '#D9DEE8', lineWidth: 1, name: 'dz-t-hrule' },
      textElement('dz-t-s0', [88, 259, 190, 32], '표 · 목록 · 제목', 13, '#101728', true),
      textElement('dz-t-c0', [292, 259, 916, 32], 'Docling 기본 시리얼라이저를 그대로 사용', 13, '#101728'),
      { kind: 'shape', geometry: 'line', bbox: [72, 291, 1136, 0], lineColor: '#E7EBF1', lineWidth: 1, name: 'dz-t-rl1' },
      textElement('dz-t-s1', [88, 289, 190, 70], '그림', 13, '#101728', true),
      textElement('dz-t-c1a', [292, 295, 916, 20], '커스텀 시리얼라이저', 13, '#101728', true),
      textElement('dz-t-c1o', [292, 319, 126, 20], '승인된 VLM 설명 O', 12.5, '#17845E', true),
      textElement('dz-t-c1ot', [420, 319, 788, 20], '→  그 설명 텍스트만 임베딩 대상으로 사용', 12.5, '#45566B'),
      textElement('dz-t-c1x', [292, 341, 126, 20], '승인된 VLM 설명 X', 12.5, '#D05252', true),
      textElement('dz-t-c1xt', [420, 341, 788, 20], '→  Docling 기본 그림·메타데이터 시리얼라이저로 대체', 12.5, '#45566B'),
      { kind: 'shape', geometry: 'line', bbox: [72, 365, 1136, 0], lineColor: '#101728', lineWidth: 1, name: 'dz-t-bot' },
    );
    // 임베딩 카드
    els.push(textElement('ck-e-h', [72, 380, 500, 26], '임베딩', 16, '#2878D1', true));
    const card = (i, x, v, l, l2) => {
      els.push({ kind: 'shape', geometry: 'roundRect', bbox: [x, 410, 360, 94], fillColor: '#FFFFFF', lineColor: '#E3E8EF', lineWidth: 1, name: `ck-card-${i}` });
      els.push(textElement(`ck-v-${i}`, [x + 24, l2 ? 424 : 428, 312, 28], v, 18, '#2878D1', true));
      els.push(textElement(`ck-l-${i}`, [x + 24, l2 ? 452 : 460, 312, 22], l, 13, '#6C7482'));
      if (l2) els.push(textElement(`ck-l-${i}b`, [x + 24, 474, 312, 20], l2, 11, '#9AA3B0'));
    };
    card(0, 72, 'embeddinggemma-300m', '임베딩 모델');
    card(1, 460, '768차원', '임베딩 벡터 크기');
    card(2, 848, '512 토큰', '청크 상한', '(모델 최대 2,048토큰 중 보수적 설정)');
    // 하단 tokenizer 콜아웃 밴드 (juyeon _0903 "1페이지" 리디자인)
    const y = 532, h = 68;
    els.push(
      { kind: 'shape', geometry: 'roundRect', bbox: [72, y, 1136, h], fillColor: '#EEF3FB', lineColor: '#DBE5F5', lineWidth: 1, name: 'ck-note-band' },
      { kind: 'shape', geometry: 'rect', bbox: [72, y, 5, h], fillColor: '#2878D1', lineWidth: 0, name: 'ck-note-accent' },
      textElement('ck-note', [100, y + 12, 1064, 24], '토큰 수는 임베딩에 사용하는 모델의 tokenizer로 계산', 15.5, '#1B2436', true),
      textElement('ck-note-2', [100, y + 38, 1064, 22], '→  분할 기준과 임베딩 기준을 동일하게 맞추기 위해', 14, '#5B6676'),
    );

    const at = s.elements.findIndex((e) => /^title-/.test(e.name || ''));
    s.elements.splice(at < 0 ? s.elements.length : at + 1, 0, ...els);
  })();

  // ===================================================================
  // 최종 편집 패스 38 — '자체 평가 의견'(05장) 뒤에 "우리가 푼 세 가지 과제" 슬라이드 추가.
  //   4p 의 업무 확장 핵심 과제 3개를 플랫폼이 어떻게 풀었는지.
  // ===================================================================
  (() => {
    const norm = (v) => String(v || '').replace(/\s+/g, ' ').trim();
    const titleOf = (s) => {
      const t = s.elements.find((e) => /^(title-|div-title-)/.test(e.name || '') && norm(e.text));
      return t ? norm(t.text) : '';
    };
    if (deck.slides.some((s) => titleOf(s) === 'HALIL이 해결한 과제')) return;
    const baseIdx = deck.slides.findIndex((s) => titleOf(s) === '판정 체계');
    const atIdx = deck.slides.findIndex((s) => titleOf(s) === '자체 평가 의견');
    if (baseIdx < 0 || atIdx < 0) { console.warn('[패스38] 기준/삽입 위치 슬라이드를 찾지 못함'); return; }

    const s = clone(deck.slides[baseIdx]);
    s.elements = s.elements.filter((e) => /^(top-accent-|top-rule-|context-|page-|title-|accent-|ctx-logo|inst-logo)/.test(e.name || ''));
    setElementText(s.elements.find((e) => e.name === 'context-16'), '·   05 자체 평가 의견');
    setElementText(s.elements.find((e) => e.name === 'title-16'), 'HALIL이 해결한 과제');
    s.sources = [];

    const CARDS = [
      {
        clr: '#155EEF', no: '01', task: '분산된 정보와 업무 도구',
        bullets: ['통합 검색으로 필요한 정보를 빠르게 탐색', 'MCP 커넥터로 외부 도구를 하나로 연결', '문서 · 도구를 하나의 업무 흐름으로 통합'],
        arrow: '정보 연결로 업무 흐름을 끊김 없이 통합',
      },
      {
        clr: '#17845E', no: '02', task: '개인에게 머무는 업무 방식',
        bullets: ['업무 방식을 스킬로 표준화', 'Agent가 조직 내에서 생성 · 공유 · 재사용', '조직 지식 자산으로 축적하고 확산'],
        arrow: '개인 경험을 조직 지식으로 전환 · 확산',
      },
      {
        clr: '#7A5CB0', no: '03', task: '조직 차원의 운영 통제',
        bullets: ['역할 · 권한 기반 접근 통제', 'HITL 승인으로 중요한 의사결정 보호', '운영 로그 · 감사로 투명성 확보'],
        arrow: '권한 · 이력 중심의 안전하고 투명한 운영',
      },
    ];
    const els = [];
    const CW = 372, CH = 496, CY = 168, GAP = 26;
    CARDS.forEach((c, ci) => {
      const x = 56 + ci * (CW + GAP);
      const p = `pv${ci}`;
      els.push(
        { kind: 'shape', geometry: 'roundRect', bbox: [x, CY, CW, CH], fillColor: '#FFFFFF', lineColor: '#E4E8EF', lineWidth: 1, name: `${p}-pan` },
        { kind: 'shape', geometry: 'roundRect', bbox: [x + 24, CY + 24, 40, 40], fillColor: c.clr, lineWidth: 0, name: `${p}-nobg` },
        textElement(`${p}-no`, [x + 24, CY + 24, 40, 40], c.no, 17, '#FFFFFF', true, 'center'),
        textElement(`${p}-task`, [x + 76, CY + 26, CW - 100, 38], c.task, 19, '#0A1020', true),
        { kind: 'shape', geometry: 'line', bbox: [x + 24, CY + 98, CW - 48, 0], lineColor: '#E7EBF1', lineWidth: 1, name: `${p}-div1` },
        textElement(`${p}-slh`, [x + 24, CY + 118, CW - 48, 26], 'HALIL의 해결', 15.5, c.clr, true),
      );
      c.bullets.forEach((b, bi) => {
        const by = CY + 162 + bi * 44;
        els.push(
          { kind: 'shape', geometry: 'ellipse', bbox: [x + 27, by + 15, 7, 7], fillColor: c.clr, lineWidth: 0, name: `${p}-dot${bi}` },
          textElement(`${p}-b${bi}`, [x + 46, by, CW - 70, 36], b, 14.5, '#37414F'),
        );
      });
      els.push(
        { kind: 'shape', geometry: 'line', bbox: [x + 24, CY + 404, CW - 48, 0], lineColor: '#E7EBF1', lineWidth: 1, name: `${p}-div2` },
        textElement(`${p}-arrow`, [x + 24, CY + 422, CW - 48, 58], `→  ${c.arrow}`, 15.5, c.clr, true),
      );
    });

    const at = s.elements.findIndex((e) => /^title-/.test(e.name || ''));
    s.elements.splice(at < 0 ? s.elements.length : at + 1, 0, ...els);
    deck.slides.splice(atIdx + 1, 0, s);
    deck.slides.forEach((item, idx) => {
      item.number = idx + 1;
      item.elements.forEach((e) => {
        if (/^(page-|div-page-)/.test(e.name || '')) setElementText(e, String(idx + 1).padStart(2, '0'));
      });
    });
  })();

  // ===================================================================
  // 최종 편집 패스 39 — 41p(운영 평가 실패 사례) 좌측 회귀 예시(ev27-regr-*) 삭제.
  // ===================================================================
  (() => {
    const norm = (v) => String(v || '').replace(/\s+/g, ' ').trim();
    const s = deck.slides.find((sl) =>
      sl.elements.some((e) => /^title-/.test(e.name || '') && norm(e.text) === '운영 평가 실패 사례'));
    if (!s) { console.warn('[패스39] 운영 평가 실패 사례 슬라이드를 찾지 못함'); return; }
    s.elements = s.elements.filter((e) => !/^ev27-regr-/.test(e.name || ''));
  })();
})();
