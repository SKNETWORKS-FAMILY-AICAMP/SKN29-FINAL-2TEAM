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

  // 표지는 흰색 카드 없이 reverse wordmark와 투명 mark만 사용한다.
  removeNames(1, ['cover-brand', 'cover-product-brand-plate', 'cover-product-favicon', 'cover-product-logo', 'institution-logo-plate']);
  slide(1).elements.push(imageElement(
    'cover-product-mark-contour',
    [57, 103, 56, 56],
    'halil-mark.png',
    'contain',
    'brightness(0) invert(1)'
  ));
  slide(1).elements.push(imageElement(
    'cover-product-mark',
    [58, 104, 54, 54],
    'halil-mark.png',
    'contain'
  ));
  slide(1).elements.push(imageElement(
    'cover-product-logo-contour-bg',
    [122, 100, 182, 63],
    'halil-logo.png',
    'contain',
    'brightness(0) invert(1)'
  ));
  slide(1).elements.push(imageElement(
    'cover-product-logo-contour',
    [124, 101, 178, 61],
    'halil-logo.png',
    'contain'
  ));
  const coverInstitutionA = slide(1).elements.find((element) => element.name === '그림 194');
  const coverInstitutionB = slide(1).elements.find((element) => element.name === '그림 195');
  if (coverInstitutionA) {
    coverInstitutionA.bbox = [985, 642, 105, 33];
    coverInstitutionA.filter = 'brightness(1.55)';
  }
  if (coverInstitutionB) {
    coverInstitutionB.bbox = [1105, 642, 112, 33];
    coverInstitutionB.filter = 'brightness(2.1)';
  }
  slide(1).sources = ['frontend/src/assets/mark.png', 'frontend/src/assets/logo.png'];

  // 목차는 왼쪽 번호 열을 사용하므로 제목에서는 중복 번호를 제거한다.
  byName(3, 'row-text-3-0', '프로젝트 개요');
  byName(3, 'row-text-3-1', '프로젝트 팀 구성 및 역할');
  byName(3, 'row-text-3-2', '프로젝트 수행 절차 및 방법');
  byName(3, 'row-text-3-3', '프로젝트 수행 결과');
  byName(3, 'row-text-3-4', '자체 평가 의견');
  removeNames(3, ['section-3']);
  byName(3, 'signal-label-3', '목차');

  // 도입부는 시장 근거 → 선도 사례 → 운영 전환 간극 → HALIL 범위 → 사용자 흐름으로 전개한다.
  byName(4, 'div-title-4', '프로젝트 개요');
  byName(4, 'div-sub-4', 'AX 시장의 변화에서 출발해 우리가 주목한 문제와 해결 방향을 설명합니다.');
  byName(4, 'div-key-4', '시장 변화 · 프로젝트 출발 · 문제 정의 · 해결 방향');

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
  slide(47).elements.push(videoElement('demo-video-player', [66, 220, 1148, 370], '../halil_프로젝트_운영_AI_시연영상_v11_피드백반영.mp4'));

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

  function byNameFor(targetSlide, name, value, options) {
    setElementText(targetSlide.elements.find((element) => element.name === name), value, options);
  }
})();
