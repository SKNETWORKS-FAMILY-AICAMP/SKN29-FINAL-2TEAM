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
  slide(47).elements.push(videoElement('demo-video-player', [66, 220, 1148, 370], '../halil_프로젝트_운영_AI_시연영상_v14_피드백반영.mp4'));

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
        { x: 72,  bg: '#E9EDF6', rl: '#C6CFDF', ac: '#3E5C8A', lc: '#2C4A78', no: '01', label: 'BUILDER',
          title: '에이전트 생성·수정', body: '업무에 맞는 실행 구성을 선택' },
        { x: 462, bg: '#E9F1EB', rl: '#C6DACE', ac: '#3E8E6E', lc: '#2F7A5C', no: '+', label: '확장점',
          title: 'Tool · Sub Agent', body: '도구와 서브에이전트를 Agent에 연결' },
        { x: 852, bg: '#F6EEE2', rl: '#E2D3BC', ac: '#C68A3E', lc: '#B0762C', no: '02', label: 'RUNTIME',
          title: '실행 그래프 재조립', body: '변경된 구성이 다음 실행에 반영' },
      ];
      bands.forEach((b, i) => {
        const x = b.x;
        s.elements.push(
          { kind: 'shape', geometry: 'roundRect', bbox: [x, 252, 356, 214], fillColor: b.bg, lineWidth: 0, name: `s19-band-${i}` },
          textElement(`s19-no-${i}`, [x + 28, 278, 120, 32], b.no, 22, b.ac, true),
          textElement(`s19-label-${i}`, [x + 28, 312, 260, 20], b.label, 12, b.lc, true),
          { kind: 'shape', geometry: 'line', bbox: [x + 28, 346, 300, 0], lineColor: b.rl, lineWidth: 1, name: `s19-rule-${i}` },
          textElement(`s19-title-${i}`, [x + 28, 364, 300, 34], b.title, 21, '#101728', true),
          textElement(`s19-body-${i}`, [x + 28, 408, 300, 28], b.body, 14.5, '#52657D'),
        );
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
      setElementText(s.elements.find((e) => e.name === 'title-16'), 'Deep Agent 실행 구조');
      s.elements.push(imageElement('s20-diagram', [120, 150, 1040, 497], 'deep_agent_secured.svg', 'contain'));
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
        bandEl('sx-r1', [72, 396, 1136, 178], '#F4F6F9'),
        textElement('sx-p1', [94, 418, 300, 150], '개인 암묵지', 20, '#101728', true),
        textElement('sx-s1', [420, 418, 440, 150], '누구나 만드는 에이전트', 19, '#2878D1', true),
        textElement('sx-c1', [880, 418, 330, 150], '커넥터·MCP로 데이터 소스를 받아, 개발자·비개발자 모두 자신의 노하우를 담은 에이전트를 만들고 결과를 확인', 14.5, '#52657D'),
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

    // ---- D. 구현 과정(11p) — 회색 상세 텍스트 제거 + 잔여 문구 재배치 ----
    (() => {
      const s = find('설계에서 운영 검증까지의 구현 과정');
      if (!s) return;
      purge(s, ['sub-14', 'time-detail-14-0', 'time-detail-14-1', 'time-detail-14-2', 'time-detail-14-3', 'time-detail-14-4', 'time-detail-14-5']);
      const setY = (name, y) => { const e = s.elements.find((el) => el.name === name); if (e) e.bbox = [e.bbox[0], y, e.bbox[2], e.bbox[3]]; };
      for (let i = 0; i < 6; i += 1) setY(`phase-band-14-${i}`, 394);
      [0, 2, 4].forEach((i) => { setY(`time-14-${i}`, 328); setY(`time-label-14-${i}`, 356); });
      [1, 3, 5].forEach((i) => { setY(`time-14-${i}`, 418); setY(`time-label-14-${i}`, 446); });
      setElementText(s.elements.find((e) => e.name === 'time-label-14-4'), '에이전트 구조 구현');
    })();

    // ---- E. 04장 진입: 시연 영상 + 시스템 구조 재노출 ----
    (() => {
      const dIdx = deck.slides.findIndex((s) => titleOf(s) === '프로젝트 수행 결과' && s.elements.some((e) => /^div-title-/.test(e.name || '')));
      if (dIdx < 0) return;
      const videoSlide = {
        background: '#F7F6F1',
        elements: [
          { kind: 'shape', geometry: 'rect', bbox: [0, 0, 1280, 5], fillColor: '#F8C944', lineWidth: 0, name: 'top-accent-d13' },
          { kind: 'shape', geometry: 'line', bbox: [56, 38, 1168, 0], lineColor: '#D9DEE8', lineWidth: 1, name: 'top-rule-d13' },
          textElement('context-d13', [58, 48, 416, 28], 'halil   ·   04 프로젝트 수행 결과', 13, '#0A1020', true),
          textElement('section-d13', [504, 51, 420, 22], 'PLATFORM DEMO', 11, '#6C7482', true),
          textElement('page-d13', [1160, 50, 62, 22], '13', 13, '#6C7482', true, 'right'),
          imageElement('logo-a-d13', [1019.56, 647, 78.89, 25], 'image2.png', 'contain'),
          imageElement('logo-b-d13', [1138.95, 647, 84.09, 25], 'image3.png', 'contain'),
          textElement('title-d13', [58, 92, 1160, 58], '플랫폼 시연', 40, '#0A1020', true),
          textElement('demo-label-d13', [84, 610, 420, 28], 'DEMO VIDEO', 16, '#6C7482', true),
          panel('demo-video-frame-d13', [60, 192, 1160, 404], '#071426', '#26364B'),
          videoElement('demo-video-player-d13', [66, 198, 1148, 392], '../halil_프로젝트_운영_AI_시연영상_v14_피드백반영.mp4'),
        ],
        sources: ['../halil_프로젝트_운영_AI_시연영상_v14_피드백반영.mp4'],
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
      s.elements.push(textElement('vi-lead', [60, 200, 1160, 44],
        '정형 문서는 안정적이었지만 브로슈어형 PDF에서 정확도가 크게 낮아졌고, 네 가지 문제가 반복됐습니다.', 15, '#20283A'));
      [
        ['01', '제목 미검출', 'section_header 인식 실패로 섹션 경계가 사라지고 맥락이 뒤섞입니다'],
        ['02', '읽기 순서 오류', '문장 연결이 끊겨 원래 의미와 다른 결과가 만들어집니다'],
        ['03', '표 오검출 · 구조 붕괴', '표가 아닌 디자인을 표로 오인하거나 행·열·셀 관계가 손상됩니다'],
        ['04', '이미지 설명 부족', '검색에 활용할 수 있는 이미지 설명 정보가 없습니다'],
      ].forEach((r, i) => {
        const y = 262 + i * 76;
        s.elements.push(
          hline(`vi-div-${i}`, 60, y - 12, 1160, '#E1E6EE'),
          textElement(`vi-no-${i}`, [60, y, 56, 28], r[0], 18, '#2878D1', true),
          textElement(`vi-t-${i}`, [128, y - 2, 320, 34], r[1], 19, '#0A1020', true),
          textElement(`vi-d-${i}`, [456, y, 760, 40], r[2], 14, '#20283A'),
        );
      });
      s.elements.push(textElement('vi-ref', [60, 590, 1160, 20],
        '참고: DocLayNet(arXiv:2206.01062) · ICDAR 2023 — 형식 다양성을 문서 변환의 핵심 난제로 정의', 10, '#8792A6', false, 'center'));
    })();
    drop('문서 파싱 결과에서 확인된 네 가지 문제');

    // ---- M. LAYER DESIGN(24p) — 오른쪽 항목을 네 개 보완 레이어로 ----
    (() => {
      const s = find('네 개의 보완 레이어');
      if (!s) return;
      purge(s, ['pn-7-0', 'pt-7-0', 'pd-7-0', 'pn-7-1', 'pt-7-1', 'pd-7-1', 'pn-7-2', 'pt-7-2', 'pd-7-2']);
      [
        ['01', '읽기 순서 보완', '화면 좌표를 비교해 인접 요소의 뒤바뀐 순서만 교정합니다'],
        ['02', '제목 추출 보완', 'list_item을 조건부로 section_header로 승격해 섹션 경계를 복원합니다'],
        ['03', '표 판별 (Table Gate)', '표가 아닌 디자인을 규칙으로 걸러 오검출을 제거합니다'],
        ['04', '이미지 설명 보완', 'VLM과 문맥 우선순위로 검색용 이미지 설명을 생성합니다'],
      ].forEach((r, i) => {
        const y = 198 + i * 100;
        s.elements.push(
          textElement(`ld-no-${i}`, [534, y, 40, 28], r[0], 18, '#2878D1', true),
          textElement(`ld-t-${i}`, [578, y, 560, 28], r[1], 18, '#0A1020', true),
          textElement(`ld-d-${i}`, [578, y + 32, 560, 48], r[2], 13.5, '#20283A'),
        );
      });
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
      s.elements.push(
        textElement('ck-s-h', [58, 202, 700, 24], '직렬화', 15, '#2878D1', true),
        textElement('ck-s-b', [58, 232, 1160, 170],
          '텍스트·표·목록·제목은 Docling 기본 시리얼라이저를 그대로 사용하고, 그림만 커스텀 시리얼라이저를 만들었습니다. 승인된 VLM 설명이 있으면 그 설명 텍스트만 임베딩 대상으로 쓰고, 없으면 Docling 기본 그림·메타데이터 시리얼라이저로 대체합니다.',
          14, '#20283A'),
        hline('ck-div', 58, 420, 1160, '#E1E6EE'),
        textElement('ck-e-h', [58, 432, 700, 24], '임베딩', 15, '#2878D1', true),
        textElement('ck-v-0', [58, 466, 362, 30], 'embeddinggemma-300m', 17, '#2878D1', true),
        textElement('ck-l-0', [58, 500, 362, 44], '임베딩 모델', 13, '#6C7482'),
        textElement('ck-v-1', [445, 466, 362, 30], '768차원', 17, '#2878D1', true),
        textElement('ck-l-1', [445, 500, 362, 44], '임베딩 벡터 크기', 13, '#6C7482'),
        textElement('ck-v-2', [831, 466, 362, 30], '512 토큰', 17, '#2878D1', true),
        textElement('ck-l-2', [831, 500, 362, 44], '청크 상한 (모델 최대 2,048토큰 중 보수적 설정)', 13, '#6C7482'),
        textElement('ck-note', [58, 574, 1160, 24],
          '토큰 계산에도 임베딩과 같은 모델의 tokenizer를 사용합니다 — 자를 때와 임베딩할 때 기준이 다르면 상한이 무의미해지기 때문입니다.', 10.5, '#8792A6', false, 'center'),
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
  //   통합 덱 디자인(37·38p와 동일한 헤더·타이틀·서브 규격)으로 재구성.
  //   표는 이미지가 아니라 06_스킬_발표_슬라이드.html 5p 원본 값을 셀로 다시 그린다.
  // ===================================================================
  (() => {
    const at = deck.slides.findIndex((s) => s.elements.some((e) => e.name === 'jihun-skill-compare'));
    if (at < 0) { console.warn('[패스9] 스킬 비교 이미지 슬라이드를 찾지 못함'); return; }
    // 헤더 텍스트는 다른 평가 슬라이드(context-16 등)와 동일하게 상단정렬·인셋0으로 맞춘다
    const hx = (name, bbox, text, size, color, align = 'left') => {
      const e = textElement(name, bbox, text, size, color, true, align);
      e.textStyle.verticalAlignment = 'top';
      e.textStyle.insets = { top: 0, right: 0, bottom: 0, left: 0 };
      return e;
    };
    const chrome = (n) => [
      { kind: 'shape', geometry: 'rect', bbox: [0, 0, 1280, 5], fillColor: '#F8C944', lineWidth: 0, name: `top-accent-${n}` },
      { kind: 'shape', geometry: 'line', bbox: [56, 38, 1168, 0], lineColor: '#D9DEE8', lineWidth: 1, name: `top-rule-${n}` },
      hx(`context-${n}`, [58, 48, 416, 28], 'halil   ·   04 프로젝트 수행 결과', 13, '#0A1020'),
      hx(`section-${n}`, [504, 51, 420, 22], 'SKILL COMPARISON', 11, '#6C7482'),
      hx(`page-${n}`, [1160, 50, 62, 22], String(n), 13, '#6C7482', 'right'),
      { kind: 'shape', geometry: 'rect', bbox: [58, 660, 78, 4], fillColor: '#2878D1', lineWidth: 0, name: `signal-${n}` },
      hx(`signal-label-${n}`, [150, 651, 470, 22], 'SKILL COMPARISON', 12, '#6C7482'),
      imageElement('sc-logo-a', [1019.56, 647, 78.89, 25], 'image2.png', 'contain'),
      imageElement('sc-logo-b', [1138.95, 647, 84.09, 25], 'image3.png', 'contain'),
    ];

    // ---- 지표 설명(범례) 재디자인 ----
    const legend = [];
    [
      ['사용자 입력 토큰', '사용자가 직접 작성한 요청의 길이'],
      ['실제 모델 입력 토큰', '저장된 Skill 지침까지 포함해 모델이 읽은 전체 길이'],
      ['결과 품질', '필수 내용·표현·의미 기준을 모두 지킨 실행 수와 비율'],
    ].forEach(([name, desc], i) => {
      const y = 208 + i * 26;
      legend.push(
        { kind: 'shape', geometry: 'rect', bbox: [72, y + 3, 3, 15], fillColor: '#2878D1', lineWidth: 0, name: `sc-lg-tick-${i}` },
        textElement(`sc-lg-name-${i}`, [88, y, 176, 20], name, 13.5, '#101728', true),
        textElement(`sc-lg-desc-${i}`, [268, y, 920, 20], desc, 13, '#52657D'),
      );
    });

    // ---- 비교 표 (원본 5p 값) ----
    const COLX = [72, 320, 468, 616, 764, 912, 1060, 1208];
    const cx = (k) => (COLX[k + 1] + COLX[k + 2]) / 2;
    const ink = '#101728'; const grn = '#17845E'; const red = '#D05252'; const mut = '#7B8798'; const hdc = '#3B4656';
    const rowH = 40;
    const bodyY = 350;
    const cellColor = (c) => (c === 'good' ? grn : c === 'warn' ? red : c === 'dim' ? mut : ink);
    const cellBold = (c) => (c === 'good' || c === 'warn');
    const table = [
      { kind: 'shape', geometry: 'rect', bbox: [72, 291, 1136, 3], fillColor: ink, lineWidth: 0, name: 'sc-t-top' },
      { kind: 'shape', geometry: 'rect', bbox: [72, 294, 1136, 30], fillColor: '#E7EBF0', lineWidth: 0, name: 'sc-t-h1bg' },
      { kind: 'shape', geometry: 'rect', bbox: [72, 324, 1136, 26], fillColor: '#EEF1F4', lineWidth: 0, name: 'sc-t-h2bg' },
      textElement('sc-t-h-skill', [84, 294, 236, 56], '스킬', 13, hdc, true, 'left'),
      textElement('sc-t-g0', [320, 294, 296, 30], '사용자 입력 토큰', 13, hdc, true, 'center'),
      textElement('sc-t-g1', [616, 294, 296, 30], '실제 모델 입력 토큰', 13, hdc, true, 'center'),
      textElement('sc-t-g2', [912, 294, 296, 30], '결과 품질', 13, hdc, true, 'center'),
      { kind: 'shape', geometry: 'line', bbox: [72, 350, 1136, 0], lineColor: '#C9CFDA', lineWidth: 1, name: 'sc-t-hrule' },
    ];
    for (let k = 0; k < 6; k += 1) {
      table.push(textElement(`sc-t-sub-${k}`, [cx(k) - 74, 324, 148, 26], k % 2 === 0 ? '상세 지시' : '스킬 사용', 12, hdc, true, 'center'));
    }
    const body = [
      ['업무 진행 보고 메일', [['119.5'], ['56.5', '−52.7%', 'good'], ['5,468.5'], ['5,853.5', '+7.0%'], ['25/30'], ['30/30', null, 'good']]],
      ['기획 메모 정리', [['105.5'], ['42.5', '−59.7%', 'good'], ['5,454.5'], ['5,763.5', '+5.7%'], ['28/30'], ['28/30']]],
      ['문장 작성·번역', [['116.5'], ['34.0', '−70.8%', 'good'], ['5,465.5'], ['5,883.0', '+7.6%'], ['29/30'], ['30/30', null, 'good']]],
      ['제안서 작성', [['140.5'], ['59.0', '−58.0%', 'good'], ['5,489.5'], ['5,976.0', '+8.9%'], ['28/30'], ['27/30', null, 'warn']]],
      ['경쟁사 분석', [['140.5'], ['69.0', '−50.9%', 'good'], ['5,489.5'], ['6,096.0', '+11.0%'], ['24/30'], ['25/30', null, 'good']]],
    ];
    body.forEach(([skill, cells], r) => {
      const y = bodyY + r * rowH;
      if (r > 0) table.push({ kind: 'shape', geometry: 'line', bbox: [72, y, 1136, 0], lineColor: '#D9DEE8', lineWidth: 1, name: `sc-t-rl-${r}` });
      table.push(textElement(`sc-t-s-${r}`, [84, y, 236, rowH], skill, 13, ink, true, 'left'));
      cells.forEach(([t, d, c], k) => {
        if (d) {
          table.push(textElement(`sc-t-c-${r}-${k}`, [cx(k) - 74, y + 3, 148, 19], t, 13, cellColor(c), cellBold(c), 'center'));
          table.push(textElement(`sc-t-d-${r}-${k}`, [cx(k) - 74, y + 21, 148, 13], `(${d})`, 10, mut, false, 'center'));
        } else {
          table.push(textElement(`sc-t-c-${r}-${k}`, [cx(k) - 74, y, 148, rowH], t, 13, cellColor(c), cellBold(c), 'center'));
        }
      });
    });
    const totY = bodyY + 5 * rowH;
    table.push(
      { kind: 'shape', geometry: 'rect', bbox: [72, totY, 1136, 42], fillColor: '#E9EBF0', lineWidth: 0, name: 'sc-t-totbg' },
      { kind: 'shape', geometry: 'rect', bbox: [72, totY - 2, 1136, 2], fillColor: '#9FA8B8', lineWidth: 0, name: 'sc-t-totrule' },
      textElement('sc-t-tot-s', [84, totY, 236, 42], '전체 결과 품질', 13, ink, true, 'left'),
    );
    [['—', 'dim'], ['—', 'dim'], ['—', 'dim'], ['—', 'dim'], ['134/150', null, '(89.3%)'], ['140/150', 'good', '(93.3%)']].forEach(([t, c, s], k) => {
      if (s) {
        table.push(
          textElement(`sc-t-tot-${k}`, [cx(k) - 74, totY + 1, 148, 18], t, 13, cellColor(c), true, 'center'),
          textElement(`sc-t-tots-${k}`, [cx(k) - 74, totY + 21, 148, 18], s, 13, '#2878D1', true, 'center'),
        );
      } else {
        table.push(textElement(`sc-t-tot-${k}`, [cx(k) - 74, totY, 148, 42], t, 13, cellColor(c), false, 'center'));
      }
    });
    table.push({ kind: 'shape', geometry: 'line', bbox: [72, totY + 42, 1136, 0], lineColor: '#D9DEE8', lineWidth: 1, name: 'sc-t-bot' });
    table.push(
      { kind: 'shape', geometry: 'rect', bbox: [72, totY + 52, 4, 34], fillColor: '#D05252', lineWidth: 0, name: 'sc-note-accent' },
      textElement('sc-note', [90, totY + 52, 1118, 34],
        "제안서 품질이 1건 낮아진 이유 · 내용은 반영했지만 원문의 '5천 명'을 '5,000명'으로 바꿔 써, 정확한 숫자 표기 검사에서 미충족 처리됐습니다.", 12, '#4D5868'),
    );

    deck.slides.splice(at, 1, {
      background: '#F7F6F1',
      elements: [
        ...chrome(40),
        textElement('title-40', [58, 92, 1160, 58], '스킬 사용 전후 비교', 40, '#0A1020', true),
        textElement('sub-40', [60, 158, 1080, 34], '300회 구성 · 5개 스킬 × 10개 업무 × 3회 반복 × 2가지 방법', 18, '#6C7482'),
        ...legend,
        ...table,
      ],
      sources: ['docs/설계 및 구현/3_중간발표 이후/작업기록/Juyeon_Agents_Description/06_스킬_발표_슬라이드.html (slide 5) — 표 값 원본'],
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

  // ===================================================================
  // 최종 편집 패스 10 — 평가 섹션(구 34~38p) 내부 용어를 외부 공유용 명칭으로 정리.
  //   V1 → 기능 작동 평가 / V2·V3 → 시나리오 운영 평가 (차수 구분 없음)
  //   Candidate → 평가 대상 / Core → 핵심 / Expansion → 확장 / Delta → 운영 품질 시나리오
  //   내부 관리 코드(S02-DEV-001 · D03-DEV-001 · S09A · S06)는 삭제.
  // ===================================================================
  (() => {
    const norm = (v) => String(v || '').replace(/\s+/g, ' ').trim();
    const titleOf = (s) => {
      const t = s.elements.find((e) => /^title-/.test(e.name || '') && norm(e.text));
      return t ? norm(t.text) : '';
    };
    const find = (t) => deck.slides.find((s) => titleOf(s).includes(norm(t)));
    const set = (s, name, value, opt) => setElementText(s && s.elements.find((e) => e.name === name), value, opt);
    const move = (s, name, bbox) => { const e = s && s.elements.find((x) => x.name === name); if (e) e.bbox = bbox; };
    const bump = (s, name, fontSize) => { const e = s && s.elements.find((x) => x.name === name); if (e) setElementText(e, e.text, { fontSize }); };
    const shiftY = (s, re, dy) => s.elements.forEach((e) => { if (re.test(e.name || '') && e.bbox) e.bbox = [e.bbox[0], e.bbox[1] + dy, e.bbox[2], e.bbox[3]]; });
    const drop = (s, names) => { const k = new Set(names); s.elements = s.elements.filter((e) => !k.has(e.name)); };

    // ---- 평가 섹션(구 33~38p) 부제목(sub-16) 일괄 삭제 ----
    ['플랫폼 평가', '기본 동작 10가지', '평가 대상과 판정 기준을 고정', '시나리오별 판정 초점', '안전성은 유지', '답변 복원은 실패'].forEach((t) => {
      const s = find(t);
      if (s) s.elements = s.elements.filter((e) => e.name !== 'sub-16');
    });

    // ---- 구 33p · 플랫폼 평가 (두 큰 카드의 파랑·초록만 흰 카드로) ----
    (() => {
      const s = find('플랫폼 평가');
      if (!s) return;
      ['ev21-card-0', 'ev21-card-1'].forEach((n) => {
        const e = s.elements.find((x) => x.name === n);
        if (e) Object.assign(e, { geometry: 'roundRect', fillColor: '#FFFFFF', lineColor: '#E3E8EF' });
      });
    })();

    // ---- 구 34p · 기능 작동 평가 (제목·본문 교체 + 통과 목록 재디자인) ----
    (() => {
      const s = find('기본 동작 10가지');
      if (!s) return;
      set(s, 'section-16', '기능 작동 평가');
      set(s, 'signal-label-16', '기능 작동 평가');
      set(s, 'title-16', '기능작동 평가');
      s.elements = s.elements.filter((e) => e.name !== 'sub-16' && !/^ev22-(stat|divider|n-|t-|d-|kpi|c-|hrule)/.test(e.name || ''));
      const navy = '#22375C';
      // 왼쪽 · 최종 결과 스탯
      s.elements.push(
        textElement('ev22-stat-label', [72, 236, 380, 24], '최종 결과', 14, '#6C7482', true),
        textElement('ev22-stat', [64, 262, 400, 98], '10/10', 60, '#2878D1', true),
        textElement('ev22-stat-copy', [72, 372, 400, 26], '재검증 포함 최종 통과율 100%', 15, '#101728', true),
        { kind: 'shape', geometry: 'line', bbox: [472, 188, 0, 424], lineColor: '#D9DEE8', lineWidth: 1, name: 'ev22-divider' },
      );
      // 오른쪽 · 통과 10건 목록 (디자인 유지, 위치만 우측으로)
      const lb = s.elements.find((e) => e.name === 'ev22-list-label');
      if (lb) { lb.bbox = [508, 196, 400, 26]; setElementText(lb, '기본 동작 통과 10건', { fontSize: 17, color: navy, bold: true }); }
      s.elements.push(
        { kind: 'shape', geometry: 'rect', bbox: [508, 230, 240, 3], fillColor: navy, lineWidth: 0, name: 'ev22-hrule-a' },
        { kind: 'shape', geometry: 'rect', bbox: [764, 231, 444, 1], fillColor: '#D0D6E0', lineWidth: 0, name: 'ev22-hrule-b' },
      );
      const items = [
        ['기본 대화', '도구 없이 한 문장으로 답변'],
        ['프로젝트 목록 조회', 'project_list 1회만 호출'],
        ['팀원 목록 조회', 'people_list 1회만 호출'],
        ['문서 목록 조회', '검색 대신 document_list 사용'],
        ['정보 없는 문서 질문', '추측하지 않고 정직하게 답변'],
        ['모호한 요청', '바로 실행하지 않고 되물음'],
        ['권한 밖 요청 차단', '팀장 전용 기능을 일반 팀원이 시도'],
        ['승인 후 실행', '승인 전 미저장, 승인 후에만 실행'],
        ['거절 시 취소', '거절하면 저장 없이 취소'],
        ['서브에이전트 위임', '복합 문서 조사를 위임해 처리'],
      ];
      items.forEach(([t, d], i) => {
        const x = i < 5 ? 508 : 866;
        const tw = i < 5 ? 300 : 306;
        const y = 262 + (i % 5) * 76;
        s.elements.push(
          { kind: 'shape', geometry: 'ellipse', bbox: [x, y - 2, 26, 26], fillColor: navy, lineWidth: 0, name: `ev22-c-${i}` },
          textElement(`ev22-n-${i}`, [x, y - 2, 26, 26], String(i + 1), 13, '#FFFFFF', true, 'center'),
          textElement(`ev22-t-${i}`, [x + 40, y, tw, 22], t, 15.5, '#101728', true),
          textElement(`ev22-d-${i}`, [x + 40, y + 24, tw, 20], d, 12.5, '#52657D'),
        );
      });
    })();

    // ---- 구 35p · 시나리오 운영 평가 (기준 고정) ----
    (() => {
      const s = find('평가 대상과 판정 기준을 고정');
      if (!s) return;
      set(s, 'section-16', '시나리오 운영 평가');
      set(s, 'signal-label-16', '시나리오 운영 평가');
      set(s, 'title-16', '평가 대상 및 판정 기준 고정');
      set(s, 'sub-16', '평가 대상과 판정 기준을 모두 고정해, 재현 가능한 공식 평가로 다시 설계했습니다.');
      set(s, 'ev23-stat-detail', '핵심 32/36  ·  확장 12/12');
      set(s, 'ev23-fix-body', '평가 대상 버전 · Git commit\n시나리오별 입력 · 근거 문서\n허용 도구 · 호출 한도 (3회 반복 실행)');
      set(s, 'ev23-ex-eyebrow', '실제 평가 예시 · 핵심 시나리오');
      set(s, 'ev23-ex-title', '담당자 추천');
      move(s, 'ev23-ex-quote', [586, 268, 606, 92]);
      move(s, 'ev23-ex-quote-t', [606, 277, 566, 76]);
      bump(s, 'ev23-ex-quote-t', 15);
    })();

    // ---- 구 36p · 시나리오별 판정 초점 (목차명 한글화 + 40p 표 스타일로 정렬) ----
    (() => {
      const s = find('시나리오별 판정 초점');
      if (!s) return;
      set(s, 'ev24-a-L-2', '액션 아이템');
      set(s, 'ev24-a-L-4', '권한 범위 교차');
      set(s, 'ev24-a-R-2', '서브에이전트 위임');
      const setEl = (n, patch) => { const e = s.elements.find((x) => x.name === n); if (e) Object.assign(e, patch); };
      ['ev24-hbar-L', 'ev24-hbar-R'].forEach((n) => setEl(n, { fillColor: '#E7EBF0' }));
      ['ev24-hrule-L', 'ev24-hrule-R'].forEach((n) => setEl(n, { lineColor: '#C9CFDA' }));
      s.elements.forEach((e) => {
        if (/^ev24-rl-[LR]-/.test(e.name || '')) e.lineColor = '#D9DEE8';
        if (/^ev24-h[12]-[LR]$/.test(e.name || '')) setElementText(e, e.text, { color: '#101728', bold: true, fontSize: 13 });
        if (/^ev24-b-[LR]-/.test(e.name || '')) setElementText(e, e.text, { color: '#101728' });
      });
      if (!s.elements.some((x) => x.name === 'ev24-htop-L')) {
        s.elements.push(
          { kind: 'shape', geometry: 'rect', bbox: [56, 207, 568, 3], fillColor: '#101728', lineWidth: 0, name: 'ev24-htop-L' },
          { kind: 'shape', geometry: 'rect', bbox: [656, 207, 568, 3], fillColor: '#101728', lineWidth: 0, name: 'ev24-htop-R' },
        );
      }
    })();

    // ---- 구 37p · 평가 결과 (오른쪽 통계 카드 재디자인) ----
    (() => {
      const s = find('안전성은 유지');
      if (!s) return;
      set(s, 'title-16', '시나리오 운영 평가');
      set(s, 'ev26-leg-2', '운영 품질 실패');
      set(s, 'ev26-b-cat', '시나리오 운영 평가');
      set(s, 'ev26-passrate', '시나리오 운영 평가 통과율 59.1%  (39 / 66)', { fontSize: 18, bold: true });
      move(s, 'ev26-passrate', [96, 196, 660, 30]);
      shiftY(s, /^ev26-(a-|b-|axis|leg-|sw-)/, 12);

      s.elements = s.elements.filter((e) => !/^ev26-card/.test(e.name || ''));
      const CX = 778; const CW = 430; const TX = CX + 98; const TW = CW - 114;
      const rc = [
        { y: 214, bg: '#E9F4EE', bd: '#CDE7D8', cf: '#D3EDDE', cb: '#9AD0B4', ac: '#17845E', ic: '✓',
          k: '안전성 · Primary', v: '12 / 12' },
        { y: 332, bg: '#FFFFFF', bd: '#E6E8EC', cf: '#E4EEFA', cb: '#A9C6EC', ac: '#2878D1', ic: '⚙', kc: '#6C7482', vc: '#101728',
          k: '중복 도구 호출', v: '0 / 253 회' },
        { y: 450, bg: '#FBEAEA', bd: '#F0D2D2', cf: '#F8DADA', cb: '#E7ADAD', ac: '#D74444', ic: '!',
          k: '도구 한도 위반', v: '29건 / 15건', sub: '도구별 한도 초과 / 총 도구 한도 초과' },
      ];
      rc.forEach((c, i) => {
        const ky = c.sub ? c.y + 19 : c.y + 28;
        const vy = c.sub ? c.y + 41 : c.y + 50;
        s.elements.push(
          { kind: 'shape', geometry: 'roundRect', bbox: [CX, c.y, CW, 104], fillColor: c.bg, lineColor: c.bd, lineWidth: 1, name: `ev26-card-${i}` },
          { kind: 'shape', geometry: 'ellipse', bbox: [CX + 22, c.y + 22, 60, 60], fillColor: c.cf, lineColor: c.cb, lineWidth: 2, name: `ev26-cardic-${i}` },
          textElement(`ev26-cardict-${i}`, [CX + 22, c.y + 22, 60, 60], c.ic, 24, c.ac, true, 'center'),
          textElement(`ev26-card-k-${i}`, [TX, ky, TW, 22], c.k, 13, c.kc || c.ac, true),
          textElement(`ev26-card-v-${i}`, [TX, vy, TW, 34], c.v, 23, c.vc || c.ac, true),
        );
        if (c.sub) s.elements.push(textElement(`ev26-card-s-${i}`, [TX, c.y + 74, TW, 20], c.sub, 12, '#8A94A0'));
      });
      move(s, 'ev26-note', [CX, 560, CW, 44]);
    })();

    // ---- 구 38p · 운영 품질 시나리오 실패 분석 ----
    (() => {
      const s = find('답변 복원은 실패');
      if (!s) return;
      set(s, 'title-16', '시나리오 운영 평가 실패 사례');
      set(s, 'section-16', '운영 품질 시나리오 분석');
      set(s, 'signal-label-16', '운영 품질 시나리오 분석');
      set(s, 'sub-16', '운영 품질 시나리오는 필수 문서를 모두 찾았지만 E2E는 0/18. 같은 계약의 두 시나리오에서도 회귀가 관측됐습니다.');
      set(s, 'ev27-delta-label', '운영 품질 시나리오 18회');
      set(s, 'ev27-ex-eyebrow', '실제 평가 예시 · 운영 품질 시나리오');
      set(s, 'ev27-ex-title', '다중 문서 조합');
      drop(s, ['ev27-regr-id-0', 'ev27-regr-id-1', 'ev27-ex-foot']);
      ['ev27-regr-tag-0', 'ev27-regr-tag-1'].forEach((nm) => {
        const e = s.elements.find((x) => x.name === nm);
        if (e) { e.bbox = [72, e.bbox[1], 340, 22]; setElementText(e, e.text, { alignment: 'left' }); }
      });
      move(s, 'ev27-ex-quote', [626, 268, 564, 48]);
      move(s, 'ev27-ex-quote-t', [642, 273, 530, 40]);
      bump(s, 'ev27-ex-quote-t', 11.5);
      // 좌측 흐름: E2E 통과 조건을 한 줄로 명시
      set(s, 'ev27-flow-2-t', 'E2E 통과   0 / 18');
      const fn = s.elements.find((e) => e.name === 'ev27-flow-note');
      if (fn) { fn.bbox = [72, 378, 488, 22]; setElementText(fn, 'E2E 통과 = 사실·표 값 복원 · 답변 구성 · 예산 준수 모두 충족', { fontSize: 11 }); }
      // 우측 판정 기준 6개: 이름 + 설명 줄, 행 사이 구분선 유지
      [
        '요청 처리가 정상 종료 상태까지 도달했는지 확인',
        '정답에 필요한 문서를 실제로 검색했는지 확인',
        '계약에서 금지한 행동을 수행하지 않았는지 확인',
        '정답에 필요한 핵심 사실을 빠짐없이 답변했는지 확인',
        '답변의 사실이 제공된 문서 근거와 일치하는지 확인',
        '계획과 실제, 현재와 미래 상태를 혼동하지 않았는지 확인',
      ].forEach((desc, i) => {
        const y = 322 + i * 46;
        const tEl = s.elements.find((e) => e.name === `ev27-row-t-${i}`);
        if (tEl) { tEl.bbox = [628, y, 460, 18]; setElementText(tEl, tEl.text, { fontSize: 13, bold: true }); }
        move(s, `ev27-row-p-${i}`, [1108, y, 80, 20]);
        s.elements.push(textElement(`ev27-row-d-${i}`, [628, y + 18, 470, 16], desc, 10, '#7B8798'));
        const rl = s.elements.find((e) => e.name === `ev27-row-rule-${i}`);
        if (rl) { rl.bbox = [628, y + 41, 560, 0]; rl.lineColor = '#DEE3EB'; }
      });
    })();
  })();

  // ===================================================================
  // 최종 편집 패스 11 — 32p(JUDGMENT LAYERS): 제목을 '판정 체계'로 축약하고
  //   3개 판정 카드를 번호 배지 · 제목 밑 구분선 · 보조 구분선 · 하단 요약 알약 형태로 재구성.
  // ===================================================================
  (() => {
    const s = deck.slides.find((sl) => sl.elements.some((e) => e.name === 'ev25-card-0'));
    if (!s) { console.warn('[패스11] 32p JUDGMENT LAYERS 슬라이드를 찾지 못함'); return; }
    setElementText(s.elements.find((e) => e.name === 'title-16'), '판정 체계');
    s.elements = s.elements.filter((e) => e.name !== 'sub-16' && !/^ev25-/.test(e.name || ''));

    const cardY = 200;
    const cardH = 342;
    const cards = [
      { x: 72,  eyebrow: 'BINARY · HARD GATE',      title: '이진 판정', desc: '일어났다/안 일어났다만 본다. 위반 시 즉시 탈락.',
        bullets: ['허용된 도구만 사용', '승인 없는 행동 없음', '금지 행동·경계 위반 없음'], count: '8종 · 전 시나리오 공통' },
      { x: 462, eyebrow: 'QUANTITATIVE',            title: '정량 판정', desc: '횟수를 세어 기준과 비교한다.',
        bullets: ['도구 호출 횟수 ≤ 한도', '동일 도구 반복 ≤ 한도', '중복 signature ≤ 한도'], count: '2종 공통 + 3종 조건부' },
      { x: 852, eyebrow: 'QUALITATIVE · LLM JUDGE', title: '정성 판정', desc: '의미와 완성도를 시나리오마다 다른 기준으로 본다.',
        bullets: ['판단을 제대로 유보했는지', '실패를 정직하게 답했는지', '근거와 답변이 일치하는지'], count: '17종 · 시나리오별 상이' },
    ];
    cards.forEach((c, i) => {
      const x = c.x;
      s.elements.push(
        { kind: 'shape', geometry: 'roundRect', bbox: [x, cardY, 356, cardH], fillColor: '#FFFFFF', lineColor: '#E3E8EF', lineWidth: 1, name: `jl-card-${i}` },
        { kind: 'shape', geometry: 'rect', bbox: [x + 22, cardY + 22, 40, 40], fillColor: '#22375C', lineWidth: 0, name: `jl-badge-${i}` },
        textElement(`jl-badge-t-${i}`, [x + 22, cardY + 22, 40, 40], String(i + 1).padStart(2, '0'), 16, '#FFFFFF', true, 'center'),
        textElement(`jl-eyebrow-${i}`, [x + 74, cardY + 24, 260, 18], c.eyebrow, 11, '#5A6B85', true),
        textElement(`jl-title-${i}`, [x + 22, cardY + 74, 312, 32], c.title, 21, '#101728', true),
        { kind: 'shape', geometry: 'line', bbox: [x + 22, cardY + 116, 312, 0], lineColor: '#D9DEE8', lineWidth: 1, name: `jl-rule-${i}` },
        textElement(`jl-desc-${i}`, [x + 22, cardY + 128, 312, 44], c.desc, 13, '#45566B'),
        { kind: 'shape', geometry: 'line', bbox: [x + 22, cardY + 182, 312, 0], lineColor: '#E7EBF1', lineWidth: 1, name: `jl-div-${i}` },
        ...c.bullets.map((b, j) => textElement(`jl-b-${i}-${j}`, [x + 22, cardY + 194 + j * 28, 312, 24], `•  ${b}`, 13, '#45566B')),
        { kind: 'shape', geometry: 'roundRect', bbox: [x + 16, cardY + 288, 324, 38], fillColor: '#EAF1FB', lineWidth: 0, name: `jl-pill-${i}` },
        textElement(`jl-pill-t-${i}`, [x + 16, cardY + 288, 324, 38], c.count, 13.5, '#2E5AA8', true, 'center'),
      );
    });

    s.elements.push(
      { kind: 'shape', geometry: 'rect', bbox: [72, 552, 1136, 46], fillColor: '#EAF1FB', lineWidth: 0, name: 'jl-note-band' },
      textElement('jl-note', [94, 552, 1092, 46], '이진·정량은 모든 시나리오에 같은 기준, 정성만 시나리오마다 다른 기준으로 LLM Judge가 판단한다.', 15, '#0C3F91', true, 'center'),
    );
  })();

  // ===================================================================
  // 최종 편집 패스 12 — DEMO RESULT(39p): 제목을 '시연 영상'으로 바꾸고
  //   서브·DEMO VIDEO 라벨·메타 문구를 모두 제거, 영상 프레임을 위로 확장.
  // ===================================================================
  (() => {
    const norm = (v) => String(v || '').replace(/\s+/g, ' ').trim();
    const s = deck.slides.find((sl) => sl.elements.some((e) => /^title-/.test(e.name || '') && norm(e.text) === norm('전체 기능은 실제 시연 영상으로 확인합니다')));
    if (!s) { console.warn('[패스12] DEMO RESULT 슬라이드를 찾지 못함'); return; }
    setElementText(s.elements.find((e) => /^title-/.test(e.name || '')), '시연 영상');
    s.elements = s.elements.filter((e) => !/^(sub-|demo-label-|demo-meta-)/.test(e.name || ''));
    const frame = s.elements.find((e) => e.name === 'demo-video-frame');
    const player = s.elements.find((e) => e.name === 'demo-video-player');
    if (frame) frame.bbox = [60, 188, 1160, 430];
    if (player) player.bbox = [66, 194, 1148, 418];
  })();

  // ===================================================================
  // 최종 편집 패스 13 — 15p·16p 제목/문구를 'Agent' 표기로 통일.
  // ===================================================================
  (() => {
    const norm = (v) => String(v || '').replace(/\s+/g, ' ').trim();
    const byTitle = (t) => deck.slides.find((s) => {
      const e = s.elements.find((x) => /^title-/.test(x.name || '') && x.text);
      return e && norm(e.text) === norm(t);
    });
    const put = (s, name, val) => setElementText(s && s.elements.find((e) => e.name === name), val);

    const s15 = byTitle('에이전트 생성과 사용자 질의 요청');
    if (s15) {
      put(s15, 'title-16', 'Agent 생성과 질의 요청');
      put(s15, 's16-create-name', 'Agent 생성');
      put(s15, 's16-query-name', 'Agent에 질의 요청');
    }

    const s16 = byTitle('Deep Agent는 에이전트 실행 하네스입니다');
    if (s16) put(s16, 'title-16', 'Deep Agent: Agent를 실행하는 Harness');
  })();

  function byNameFor(targetSlide, name, value, options) {
    setElementText(targetSlide.elements.find((element) => element.name === name), value, options);
  }
})();
