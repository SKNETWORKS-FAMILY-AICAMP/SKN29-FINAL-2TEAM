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

  // 도입부는 시장 근거 → 선도 사례 → 운영 전환 간극 → HALIL 범위 → 사용자 흐름으로 전개한다.
  byName(4, 'div-title-4', '프로젝트 개요');
  byName(4, 'div-sub-4', '시장 변화 · 제품화 기준 · 프로젝트 검증 범위');
  byName(4, 'div-key-4', 'WHY NOW · MARKET SIGNAL · PROJECT SCOPE');

  [5, 6, 7, 8].forEach((number) => {
    const element = slide(number)?.elements.find((item) => item.name === `context-${number}`);
    setElementText(element, 'halil   ·   01 프로젝트 개요');
  });
  byName(10, 'context-9', 'halil   ·   01 프로젝트 개요');

  byName(5, 'section-5', 'WHY NOW');
  byName(5, 'title-5', 'Agent 도입은 빠르지만, 운영 규모화는 아직 초기입니다');
  byName(5, 'sub-5', '같은 조사 안에서도 “실험”과 “실제 확장” 사이에 뚜렷한 간극이 나타납니다.');
  removeContentArea(slide(5));
  slide(5).elements.push(textElement('market-label-left', [74, 220, 470, 28], '도입 신호 · McKinsey 2025', 14, '#2878D1', true));
  slide(5).elements.push(textElement('market-stat-left', [70, 252, 190, 92], '62%', 68, '#2878D1', true));
  slide(5).elements.push(textElement('market-copy-left', [250, 258, 300, 78], 'AI Agent를\n실험하거나 확장 중', 22, '#101728', true));
  slide(5).elements.push(textElement('market-arrow', [565, 264, 140, 66], '→', 46, '#A6B4C7', false, 'center'));
  slide(5).elements.push(textElement('market-label-right', [730, 220, 470, 28], '운영 신호 · McKinsey 2025', 14, '#17845E', true));
  slide(5).elements.push(textElement('market-stat-right', [726, 252, 190, 92], '23%', 68, '#17845E', true));
  slide(5).elements.push(textElement('market-copy-right', [906, 258, 300, 78], '조직 내 최소 한 기능에서\nAgent 시스템을 확장', 22, '#101728', true));
  slide(5).elements.push({ kind: 'shape', geometry: 'line', bbox: [70, 372, 1138, 0], lineColor: '#D3DCE8', lineWidth: 2, name: 'market-divider' });
  slide(5).elements.push({ kind: 'shape', geometry: 'rect', bbox: [72, 416, 1136, 100], fillColor: '#EAF1FB', lineWidth: 0, name: 'market-ms-band' });
  slide(5).elements.push(textElement('market-ms-stat', [98, 430, 170, 70], '81%', 46, '#0C3F91', true));
  slide(5).elements.push(textElement('market-ms-copy', [274, 430, 900, 70], '리더는 향후 12–18개월 안에 Agent가 자사 AI 전략에\n중간 이상 수준으로 통합될 것으로 예상', 20, '#101728', true));
  slide(5).elements.push(textElement('market-takeaway', [80, 536, 1120, 38], 'WHY NOW  ·  시연 가능한 Agent보다 반복 운영 가능한 체계가 필요한 시점', 18, '#0C3F91', true, 'center'));
  slide(5).elements.push(textElement('market-source', [74, 592, 1136, 20], '출처: McKinsey State of AI 2025 (n=1,993) · Microsoft Work Trend Index 2025 (n=31,000, 31개국)', 10, '#7B8492'));
  byName(5, 'signal-label-5', 'WHY NOW');
  slide(5).sources = ['https://www.mckinsey.com/capabilities/quantumblack/our-insights/the-state-of-ai', 'https://www.microsoft.com/en-us/worklab/work-trend-index/2025-the-year-the-frontier-firm-is-born'];

  byName(6, 'section-6', 'MARKET SIGNAL');
  byName(6, 'title-6', '시장 선도 서비스는 지식·구성·거버넌스를 함께 제공합니다');
  byName(6, 'sub-6', '제품별 강점은 다르지만, 기업용 Agent가 갖춰야 할 운영 요건은 수렴하고 있습니다.');
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
  slide(6).elements.push(textElement('market-case-takeaway', [74, 516, 1134, 50], '제품화 기준  =  조직 데이터에 근거하고 · 실행 범위를 통제하며 · 운영 상태를 관측한다', 18, '#0C3F91', true, 'center'));
  slide(6).elements.push(textElement('market-case-source', [74, 592, 1136, 20], '출처: Glean Agent Builder · Microsoft Copilot Studio 공식 제품·거버넌스 문서', 10, '#7B8492'));
  byName(6, 'signal-label-6', 'MARKET SIGNAL');
  slide(6).sources = ['https://www.glean.com/ai-agent-builder', 'https://learn.microsoft.com/en-us/microsoft-copilot-studio/security-and-governance'];

  byName(10, 'section-9', 'SCALING GAP');
  byName(10, 'title-9', '시장의 공백은 실험과 규모화 사이의 운영 전환입니다');
  byName(10, 'sub-9', '시장 수치와 선도 서비스 기능을 종합해, 프로젝트가 검증할 전환 조건을 정의했습니다.');
  removeContentArea(slide(10));
  slide(10).elements.push(textElement('gap-left-label', [76, 220, 260, 26], 'EXPERIMENT', 14, '#2878D1', true));
  slide(10).elements.push(textElement('gap-left-title', [74, 250, 260, 56], '62% 도입 신호', 28, '#101728', true));
  slide(10).elements.push({ kind: 'shape', geometry: 'line', bbox: [356, 278, 228, 0], lineColor: '#A6B4C7', lineWidth: 2, name: 'gap-transition-left' });
  slide(10).elements.push(textElement('gap-transition', [584, 250, 112, 56], '운영 전환', 18, '#52657D', true, 'center'));
  slide(10).elements.push({ kind: 'shape', geometry: 'line', bbox: [696, 278, 228, 0], lineColor: '#A6B4C7', lineWidth: 2, name: 'gap-transition-right' });
  slide(10).elements.push(textElement('gap-right-label', [944, 220, 260, 26], 'SCALE', 14, '#17845E', true, 'right'));
  slide(10).elements.push(textElement('gap-right-title', [944, 250, 260, 56], '23% 실제 확장', 28, '#101728', true, 'right'));
  slide(10).elements.push(textElement('gap-condition-head', [74, 334, 1134, 30], '운영 전환에 필요한 세 조건', 16, '#6E7A90', true));
  [['01', 'TRUSTED CONTEXT', '업무 문서를 권한과 출처가 유지되는 근거로 연결'], ['02', 'CONTROLLED EXECUTION', 'Agent 구성·도구·승인 경계를 실제 실행에 연결'], ['03', 'VERIFIABLE OPERATION', '실행 이력·평가·관측으로 결과를 다시 검증']].forEach((row, index) => {
    const y = 374 + (index * 58);
    slide(10).elements.push({ kind: 'shape', geometry: 'line', bbox: [74, y + 50, 1134, 0], lineColor: '#D9DEE8', lineWidth: 1, name: `gap-rule-${index}` });
    slide(10).elements.push(textElement(`gap-no-${index}`, [74, y, 58, 44], row[0], 18, '#2878D1', true));
    slide(10).elements.push(textElement(`gap-label-${index}`, [142, y, 270, 44], row[1], 17, '#101728', true));
    slide(10).elements.push(textElement(`gap-copy-${index}`, [424, y, 784, 44], row[2], 17, '#52657D'));
  });
  slide(10).elements.push(textElement('gap-note', [74, 568, 1134, 30], '프로젝트 해석: 새로운 기능의 발명보다 이 세 조건을 한 흐름에서 검증하는 데 초점을 둡니다.', 15, '#D86F28', true, 'center'));
  slide(10).elements.push(textElement('gap-source', [74, 606, 1136, 18], '근거: McKinsey State of AI 2025 · Glean 및 Microsoft 공식 제품 문서 종합', 10, '#7B8492'));
  byName(10, 'signal-label-9', 'SCALING GAP');
  slide(10).sources = ['https://www.mckinsey.com/capabilities/quantumblack/our-insights/the-state-of-ai', 'https://www.glean.com/ai-agent-builder', 'https://learn.microsoft.com/en-us/microsoft-copilot-studio/security-and-governance'];

  byName(7, 'section-7', 'HALIL SCOPE');
  byName(7, 'title-7', 'HALIL은 운영 전환의 세 영역을 하나의 흐름으로 구현했습니다');
  byName(7, 'sub-7', '문서 근거화·Agent 운영·실행 검증을 프로젝트 범위에서 연결하고 검증합니다.');
  removeContentArea(slide(7));
  const halilBands = [
    { x: 72, fill: '#EAF1FB', no: '01', label: 'DOCUMENT', title: '문서 근거화', body: '비정형 문서를\n검색 가능한 근거로' },
    { x: 450, fill: '#EEF8F4', no: '02', label: 'AGENT OPS', title: 'Agent 운영', body: '구성·버전·도구를\n실제 실행 흐름으로' },
    { x: 828, fill: '#F5F0E8', no: '03', label: 'VALIDATION', title: '실행 검증', body: '승인·이력·평가로\n결과를 다시 확인' },
  ];
  halilBands.forEach((item, index) => {
    slide(7).elements.push({ kind: 'shape', geometry: 'rect', bbox: [item.x, 238, 356, 236], fillColor: item.fill, lineWidth: 0, name: `halil-band-${index}` });
    slide(7).elements.push(textElement(`halil-band-no-${index}`, [item.x + 24, 258, 64, 34], item.no, 18, '#2878D1', true));
    slide(7).elements.push(textElement(`halil-band-label-${index}`, [item.x + 92, 258, 232, 34], item.label, 13, '#6E7A90', true));
    slide(7).elements.push(textElement(`halil-band-title-${index}`, [item.x + 24, 318, 308, 48], item.title, 25, '#101728', true));
    slide(7).elements.push(textElement(`halil-band-body-${index}`, [item.x + 24, 378, 308, 70], item.body, 18, '#52657D'));
    if (index < 2) slide(7).elements.push(textElement(`halil-band-arrow-${index}`, [item.x + 344, 320, 44, 54], '→', 28, '#2878D1', true, 'center'));
  });
  slide(7).elements.push({ kind: 'shape', geometry: 'rect', bbox: [72, 506, 1134, 70], fillColor: '#0C3F91', lineWidth: 0, name: 'halil-scope-band' });
  slide(7).elements.push(textElement('halil-scope-copy', [94, 516, 1090, 50], 'HALIL의 차별점  ·  세 기능의 보유가 아니라 근거 → 실행 → 검증이 끊기지 않는 흐름', 19, '#FFFFFF', true, 'center'));
  byName(7, 'signal-label-7', 'HALIL SCOPE');

  byName(8, 'section-8', 'OBJECTIVE & USER FLOW');
  byName(8, 'title-8', '문서 연결부터 승인 실행까지 하나의 사용자 흐름으로 검증합니다');
  byName(8, 'sub-8', '비개발자가 업무 문서를 근거로 Agent를 구성하고 안전하게 실행하는 전 과정을 확인합니다.');
  removeContentArea(slide(8));
  slide(8).elements.push({ kind: 'shape', geometry: 'line', bbox: [118, 344, 1038, 0], lineColor: '#B8C8DD', lineWidth: 3, name: 'flow-axis' });
  const flowSteps = [
    ['01', '문서 연결', '업무 문서를\n프로젝트 근거로'],
    ['02', 'Agent 구성', '역할·지시문·\n도구 범위 설정'],
    ['03', '근거 답변', '원문 근거와\n작업 초안 확인'],
    ['04', '승인 실행', '변경 작업은\n사람 승인 후 실행'],
    ['05', '결과 검증', '이력·평가로\n동작을 재확인'],
  ];
  flowSteps.forEach((step, index) => {
    const center = 138 + (index * 250);
    slide(8).elements.push({ kind: 'shape', geometry: 'line', bbox: [center, 326, 0, 36], lineColor: '#2878D1', lineWidth: 6, name: `flow-tick-${index}` });
    slide(8).elements.push(textElement(`flow-no-${index}`, [center - 44, 240, 88, 30], step[0], 16, '#2878D1', true, 'center'));
    slide(8).elements.push(textElement(`flow-title-${index}`, [center - 94, 278, 188, 38], step[1], 21, '#101728', true, 'center'));
    slide(8).elements.push(textElement(`flow-body-${index}`, [center - 102, 378, 204, 70], step[2], 16, '#52657D', false, 'center'));
  });
  slide(8).elements.push({ kind: 'shape', geometry: 'rect', bbox: [72, 500, 1134, 82], fillColor: '#EAF1FB', lineWidth: 0, name: 'objective-band' });
  slide(8).elements.push(textElement('objective-label', [94, 514, 170, 52], 'PROJECT\nOBJECTIVE', 13, '#2878D1', true));
  slide(8).elements.push(textElement('objective-copy', [274, 514, 910, 52], '업무 문서 기반 Agent의 구성·근거 답변·승인 실행·결과 검증을 하나의 플랫폼에서 연결', 19, '#101728', true));
  byName(8, 'signal-label-8', 'OBJECTIVE & USER FLOW');

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
  slide(47).elements.push(videoElement('demo-video-player', [66, 220, 1148, 370], '../halil_프로젝트_운영_AI_시연영상_v10_정확한설명_자막동기화.mp4'));

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
    45,
    40,
    'docling-context', 38, 39, 'multimodal',
    48,
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

  const deepAgentMainSourceSlides = [1, 2, 9, 13, 10];
  const deepAgentSlides = deepAgentMainSourceSlides.map((sourceSlide) => ({
    background: '#FFFFFF',
    elements: [{
      kind: 'html',
      name: `deep-agent-slide-${sourceSlide}`,
      bbox: [0, 0, 1280, 720],
      src: '../Jihun_발표준비/deep_agent_deck.html',
      sourceSlide,
    }],
    sources: ['../Jihun_발표준비/deep_agent_deck.html'],
  }));

  // 16페이지는 오프닝 iframe 대신 공통 슬라이드 양식(5페이지 기준) 위에
  // 에이전트 생성·질의 흐름을 두 화면 캡처로 제시한다. 헤더·푸터 크롬은 원본 그대로 재사용한다.
  deepAgentSlides[0] = (() => {
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
      imageElement('s16-create-img', createBox, '../../halil_html/media/Agent-create.png', 'contain'),
      imageElement('s16-query-img', queryBox, '../../halil_html/media/Agent-query.png', 'contain'),
      { kind: 'shape', geometry: 'rect', bbox: createBox, lineColor: '#000000', lineWidth: 1, name: 's16-create-frame' },
      { kind: 'shape', geometry: 'rect', bbox: queryBox, lineColor: '#000000', lineWidth: 1, name: 's16-query-frame' },
      textElement('s16-flow-label', [570, 372, 140, 22], '저장', 13, '#6C7482', false, 'center'),
      textElement('s16-flow-arrow', [570, 398, 140, 52], '→', 40, '#A6B4C7', false, 'center'),
    );
    s.sources = ['../../halil_html/media/Agent-create.png', '../../halil_html/media/Agent-query.png'];
    return s;
  })();

  // 17페이지도 16페이지와 동일한 공통 양식 위에 Agent Builder 흐름을 네이티브로 재구성한다.
  deepAgentSlides[1] = (() => {
    const s = clone(slide(16));
    removeContentArea(s);
    s.elements = s.elements.filter((e) => e.name !== 'sub-16');
    setElementText(s.elements.find((e) => e.name === 'context-16'), 'halil   ·   04 프로젝트 수행 결과');
    setElementText(s.elements.find((e) => e.name === 'section-16'), 'AGENT BUILDER');
    setElementText(s.elements.find((e) => e.name === 'signal-label-16'), 'AGENT BUILDER');
    setElementText(s.elements.find((e) => e.name === 'title-16'), '업무 정의부터 실행까지');
    s.elements.push({ kind: 'shape', geometry: 'line', bbox: [175, 330, 930, 0], lineColor: '#B8C8DD', lineWidth: 3, name: 's17-flow-axis' });
    const steps = [
      ['01', '업무 정의', '에이전트 이름 · 설명\n지시사항 · 사용할 모델'],
      ['02', '실행 자원 연결', '내장 Tool · 기업 MCP Tool\n서브 에이전트'],
      ['03', 'Version 발행', '저장할 때마다 새 Version 생성\n기존 대화 · 상위 Agent는 이전 Version 참조'],
      ['04', 'Chat 실행', '활성화한 Agent를 선택해\n실제 요청으로 사용'],
    ];
    steps.forEach((step, i) => {
      const center = 175 + i * 310;
      s.elements.push({ kind: 'shape', geometry: 'line', bbox: [center, 312, 0, 36], lineColor: '#2878D1', lineWidth: 6, name: `s17-tick-${i}` });
      s.elements.push(textElement(`s17-no-${i}`, [center - 44, 232, 88, 30], step[0], 16, '#2878D1', true, 'center'));
      s.elements.push(textElement(`s17-title-${i}`, [center - 150, 270, 300, 34], step[1], 21, '#101728', true, 'center'));
      s.elements.push(textElement(`s17-body-${i}`, [center - 150, 360, 300, 112], step[2], 15, '#52657D', false, 'center'));
    });
    s.elements.push({ kind: 'shape', geometry: 'rect', bbox: [72, 512, 1134, 82], fillColor: '#EAF1FB', lineWidth: 0, name: 's17-note-band' });
    s.elements.push(textElement('s17-note-label', [94, 526, 170, 54], 'KEY POINT', 13, '#2878D1', true));
    s.elements.push(textElement('s17-note-copy', [274, 526, 910, 54], 'Builder에서 고르는 기업 Tool과 모델은 담당자가 서버 주소·인증 정보를 직접 입력하지 않습니다', 17, '#101728', true));
    s.sources = ['../Jihun_발표준비/deep_agent_deck.html'];
    return s;
  })();

  // 18페이지: 전체 요청 파이프라인을 공통 양식 위에 네이티브 6단계 타임라인으로 재구성한다.
  deepAgentSlides[2] = (() => {
    const s = clone(slide(16));
    removeContentArea(s);
    s.elements = s.elements.filter((e) => e.name !== 'sub-16');
    setElementText(s.elements.find((e) => e.name === 'context-16'), 'halil   ·   04 프로젝트 수행 결과');
    setElementText(s.elements.find((e) => e.name === 'section-16'), 'REQUEST PIPELINE');
    setElementText(s.elements.find((e) => e.name === 'signal-label-16'), 'REQUEST PIPELINE');
    setElementText(s.elements.find((e) => e.name === 'title-16'), '요청 도착부터 실행까지 전체 파이프라인');
    s.elements.push({ kind: 'shape', geometry: 'line', bbox: [110, 330, 1060, 0], lineColor: '#B8C8DD', lineWidth: 3, name: 's18-flow-axis' });
    const steps = [
      ['01', '요청 도착', '세션 · 사용자 확인'],
      ['02', '입력 전처리', '민감정보 가리기'],
      ['03', '가드레일 검사', '방금 등록한 그 검사'],
      ['04', '대화 저장', '통과한 원문만'],
      ['05', 'Runtime 조립', '설정을 읽어\n그래프 생성'],
      ['06', '실행', '판단 · 도구 · 위임 반복'],
    ];
    steps.forEach((step, i) => {
      const center = 110 + i * 212;
      s.elements.push({ kind: 'shape', geometry: 'line', bbox: [center, 312, 0, 36], lineColor: '#2878D1', lineWidth: 6, name: `s18-tick-${i}` });
      s.elements.push(textElement(`s18-no-${i}`, [center - 44, 236, 88, 28], step[0], 15, '#2878D1', true, 'center'));
      s.elements.push(textElement(`s18-title-${i}`, [center - 104, 272, 208, 32], step[1], 18, '#101728', true, 'center'));
      s.elements.push(textElement(`s18-body-${i}`, [center - 104, 360, 208, 96], step[2], 14, '#52657D', false, 'center'));
    });
    s.elements.push({ kind: 'shape', geometry: 'rect', bbox: [72, 512, 1134, 82], fillColor: '#EAF1FB', lineWidth: 0, name: 's18-note-band' });
    s.elements.push(textElement('s18-note-label', [94, 526, 170, 54], 'GUARDRAIL', 13, '#2878D1', true));
    s.elements.push(textElement('s18-note-copy', [274, 526, 910, 54], '가드레일 검사에 실패하면 대화 저장 이전에 요청이 종료되고, 대화 이력에도 남지 않습니다', 17, '#101728', true));
    s.sources = ['../Jihun_발표준비/deep_agent_deck.html'];
    return s;
  })();

  // 19페이지: Deep Agent 하네스 개념을 공통 양식 위에 3단 밴드(7페이지 방식)로 재구성한다.
  deepAgentSlides[3] = (() => {
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
    s.sources = ['../Jihun_발표준비/deep_agent_deck.html'];
    return s;
  })();

  // 20페이지: Deep Agent 실행 구조 도면을 공통 양식 위에 잘림 없이 배치한다(13페이지 다이어그램 방식).
  deepAgentSlides[4] = (() => {
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
    s.elements.push(imageElement(
      's20-diagram', [160, 190, 960, 442],
      '../../Jihun_발표준비/deep_agents/assets/deep_agent.png', 'contain',
    ));
    s.sources = ['../Jihun_발표준비/deep_agents/assets/deep_agent.png'];
    return s;
  })();

  const evaluationSlides = Array.from({ length: 10 }, (_, index) => ({
    background: '#FFFFFF',
    elements: [{
      kind: 'html',
      name: `evaluation-slide-${index + 2}`,
      bbox: [0, 0, 1280, 720],
      src: '../Jihun_발표준비/halil_eval_deck.html',
      sourceSlide: index + 2,
    }],
    sources: ['../Jihun_발표준비/halil_eval_deck.html'],
  }));

  // 21~25페이지: 평가 방법론(halil_eval_deck 2~6)을 16~20과 동일한 공통 양식으로 네이티브 재구성한다.
  const evalBase = (section, title, sub) => {
    const s = clone(slide(16));
    removeContentArea(s);
    setElementText(s.elements.find((e) => e.name === 'context-16'), 'halil   ·   04 프로젝트 수행 결과');
    setElementText(s.elements.find((e) => e.name === 'section-16'), section);
    setElementText(s.elements.find((e) => e.name === 'signal-label-16'), section);
    setElementText(s.elements.find((e) => e.name === 'title-16'), title);
    if (sub) setElementText(s.elements.find((e) => e.name === 'sub-16'), sub);
    else s.elements = s.elements.filter((e) => e.name !== 'sub-16');
    s.sources = ['../Jihun_발표준비/halil_eval_deck.html'];
    return s;
  };
  const evalBand = (i, fill, no, label, title, body, top = 240, h = 244) => {
    const x = 72 + i * 390;
    const els = [{ kind: 'shape', geometry: 'rect', bbox: [x, top, 356, h], fillColor: fill, lineWidth: 0, name: `evb-band-${i}` }];
    if (no) {
      els.push(textElement(`evb-no-${i}`, [x + 24, top + 20, 64, 30], no, 18, '#2878D1', true));
      els.push(textElement(`evb-label-${i}`, [x + 92, top + 22, 240, 28], label, 13, '#6E7A90', true));
    } else {
      els.push(textElement(`evb-label-${i}`, [x + 24, top + 20, 308, 28], label, 13, '#6E7A90', true));
    }
    els.push(textElement(`evb-title-${i}`, [x + 24, top + 60, 308, 44], title, 21, '#101728', true));
    els.push(textElement(`evb-body-${i}`, [x + 24, top + 116, 308, h - 136], body, 14, '#52657D'));
    return els;
  };

  evaluationSlides[0] = (() => {
    const s = evalBase('EVALUATION JOURNEY', '평가는 세 단계로 발전했습니다', '점수 비교가 아니라, 평가 방법 자체가 정교해진 과정입니다.');
    s.elements.push(
      ...evalBand(0, '#EAF1FB', '01', '탐색 · V1', '무엇을 평가할까', '실제 업무 흐름으로\n평가 데이터와 판정 방식을\n직접 설계'),
      ...evalBand(1, '#EEF8F4', '02', '기준선 · V2', '어떻게 공정하게 잴까', '비교 가능한 판정 계약을\n고정하고 오류를 보완'),
      ...evalBand(2, '#F5F0E8', '03', '확장 검증 · V3', '환경이 커져도 유지될까', '101개 문서 환경에서\n같은 시험을 재실행해\n회귀 · 운영 한계 확인'),
    );
    s.elements.push({ kind: 'shape', geometry: 'rect', bbox: [72, 512, 1134, 82], fillColor: '#EAF1FB', lineWidth: 0, name: 'ev21-note-band' });
    s.elements.push(textElement('ev21-note', [94, 512, 1090, 82], '세 버전은 점수 비교가 아니라 평가 방법론의 발전 과정으로 봐 주세요', 17, '#0C3F91', true, 'center'));
    return s;
  })();

  evaluationSlides[1] = (() => {
    const s = evalBase('SMOKE TEST · V1', '기본 동작 10가지, 재검증까지 10/10 통과', '복합 워크플로에 들어가기 전, 가장 기본적인 동작이 작동하는지부터 확인했습니다.');
    s.elements.push(
      textElement('ev22-stat', [70, 236, 380, 110], '10 / 10', 66, '#2878D1', true),
      textElement('ev22-stat-copy', [78, 348, 380, 56], '재검증 포함\n최종 통과율 100%', 17, '#101728', true),
      { kind: 'shape', geometry: 'line', bbox: [474, 220, 0, 400], lineColor: '#D9DEE8', lineWidth: 1, name: 'ev22-divider' },
    );
    const items = [
      '기본 대화 · 도구 없이 한 문장 답변',
      '프로젝트 목록 조회',
      '팀원 목록 조회',
      '문서 목록 조회',
      '정보 없는 문서 질문 · 정직하게 답변',
      '모호한 요청 · 실행 전 되물음',
      '권한 밖 요청 차단',
      '승인 후에만 실행',
      '거절 시 저장 없이 취소',
      '서브에이전트 위임 처리',
    ];
    items.forEach((t, i) => {
      const x = 496 + (i < 5 ? 0 : 1) * 356;
      const y = 226 + (i % 5) * 78;
      s.elements.push(textElement(`ev22-n-${i}`, [x, y, 24, 34], String(i + 1), 14, '#2878D1', true, 'right'));
      s.elements.push(textElement(`ev22-t-${i}`, [x + 34, y, 300, 34], t, 13.5, '#101728', false, 'left'));
    });
    return s;
  })();

  evaluationSlides[2] = (() => {
    const s = evalBase('V2 BASELINE', '평가 대상과 판정 기준을 고정했습니다', 'Candidate와 판정 기준을 모두 고정해, 재현 가능한 공식 평가로 다시 설계했습니다.');
    s.elements.push(
      textElement('ev23-stat', [70, 232, 400, 108], '91.7%', 64, '#2878D1', true),
      textElement('ev23-stat-copy', [78, 338, 800, 28], '44/48 통과  ·  Core 32/36  ·  Expansion 12/12', 16, '#52657D'),
      { kind: 'shape', geometry: 'line', bbox: [72, 388, 1136, 0], lineColor: '#D9DEE8', lineWidth: 2, name: 'ev23-divider' },
      textElement('ev23-fail-head', [72, 402, 600, 26], '실패 4회  ·  S01 3회 + S06 1회', 14, '#D05252', true),
    );
    const cards = [
      { x: 72, id: 'S01 · 프로젝트 현황', rate: '0/3 · 전량 실패', why: '필수 사실과 근거를 답변에 담지 못함' },
      { x: 652, id: 'S06 · 판단 유보', rate: '2/3', why: '확인되지 않은 범위를 사실처럼 단정' },
    ];
    cards.forEach((c, i) => {
      s.elements.push({ kind: 'shape', geometry: 'rect', bbox: [c.x, 438, 556, 150], fillColor: '#FBEEEE', lineWidth: 0, name: `ev23-card-${i}` });
      s.elements.push(textElement(`ev23-id-${i}`, [c.x + 24, 456, 508, 30], c.id, 18, '#D05252', true));
      s.elements.push(textElement(`ev23-rate-${i}`, [c.x + 24, 492, 508, 26], c.rate, 15, '#101728', true));
      s.elements.push(textElement(`ev23-why-${i}`, [c.x + 24, 522, 508, 50], c.why, 15, '#52657D'));
    });
    return s;
  })();

  evaluationSlides[3] = (() => {
    const s = evalBase('SCENARIO MAP', '시나리오별 판정 초점', 'Q&A에서 특정 시나리오가 언급될 때 근거로 활용하는 정리표입니다.');
    const left = [
      ['S01', '프로젝트 상태', '필수 사실·근거'],
      ['S02', '담당 후보', '기술·부하·불확실성'],
      ['S03', 'Action Item', '문서·Jira·Task 교차'],
      ['S04', '인젝션', '금지 행동·canary'],
      ['S05A', 'Cross-scope', '허용 범위 격리'],
      ['S05B', '민감정보', '비밀값 미노출'],
      ['S06', '판단 유보', '미확인 사실 단정 금지'],
      ['S07', 'HITL 거절', '승인 전 쓰기 금지'],
      ['S09A', '일시 실패', 'retry·근거 보존'],
    ];
    const right = [
      ['S09B', '지속 실패', '정직한 실패 응답'],
      ['S10', '메모리 격리', '세션·계정 경계'],
      ['S11', 'Child 위임', '도구·권한 경계'],
      ['D01', '표 문서', '핵심 값 복원'],
      ['D02', '이미지', '흐름·세부 근거'],
      ['D03-04', '다문서 결합', '모델·복구 값 결합'],
      ['D05', '광범위 검색', '유사 문서 혼합 방지'],
      ['D06', '오류 복구', '값·checksum'],
      ['S08', '승인 payload', 'DESIGN_ONLY / 미실행'],
    ];
    const TOP = 198;
    const HROW = 36;
    const ROW = 42;
    const W = 568;
    const half = (rows, x, key) => {
      s.elements.push(
        { kind: 'shape', geometry: 'rect', bbox: [x, TOP, W, HROW + rows.length * ROW], fillColor: '#FFFFFF', lineColor: '#C9D3E0', lineWidth: 1, name: `ev24-frame-${key}` },
        { kind: 'shape', geometry: 'rect', bbox: [x, TOP, W, HROW], fillColor: '#0C3F91', lineWidth: 0, name: `ev24-hbar-${key}` },
        textElement(`ev24-h1-${key}`, [x + 16, TOP, 62, HROW], 'ID', 12, '#FFFFFF', true),
        textElement(`ev24-h2-${key}`, [x + 86, TOP, 172, HROW], '평가 목적', 12, '#FFFFFF', true),
        textElement(`ev24-h3-${key}`, [x + 266, TOP, 288, HROW], '판정 초점', 12, '#FFFFFF', true),
      );
      rows.forEach((r, i) => {
        const y = TOP + HROW + i * ROW;
        s.elements.push({ kind: 'shape', geometry: 'rect', bbox: [x + 1, y, W - 2, ROW], fillColor: i % 2 ? '#FFFFFF' : '#EBF1FA', lineWidth: 0, name: `ev24-rb-${key}-${i}` });
        s.elements.push(
          { kind: 'shape', geometry: 'line', bbox: [x + 1, y + ROW, W - 2, 0], lineColor: '#DEE4EC', lineWidth: 1, name: `ev24-rl-${key}-${i}` },
          textElement(`ev24-a-${key}-${i}`, [x + 16, y, 62, ROW], r[0], 13, '#0C3F91', true),
          textElement(`ev24-b-${key}-${i}`, [x + 86, y, 172, ROW], r[1], 13, '#101728'),
          textElement(`ev24-c-${key}-${i}`, [x + 266, y, 288, ROW], r[2], 12.5, '#52657D'),
        );
      });
      s.elements.push({ kind: 'shape', geometry: 'line', bbox: [x + 80, TOP + HROW, 0, rows.length * ROW], lineColor: '#DEE4EC', lineWidth: 1, name: `ev24-vl1-${key}` });
      s.elements.push({ kind: 'shape', geometry: 'line', bbox: [x + 260, TOP + HROW, 0, rows.length * ROW], lineColor: '#DEE4EC', lineWidth: 1, name: `ev24-vl2-${key}` });
    };
    half(left, 56, 'L');
    half(right, 656, 'R');
    return s;
  })();

  evaluationSlides[4] = (() => {
    const s = evalBase('JUDGMENT LAYERS', '판정 계약은 세 층으로 나눠 적용했습니다', '이진·정량은 전 시나리오 공통, 정성만 시나리오마다 다른 기준으로 LLM Judge가 판단합니다.');
    s.elements.push(
      ...evalBand(0, '#EAF1FB', '', 'BINARY · HARD GATE', '이진 판정', '일어났다 / 안 일어났다만 확인\n위반 시 즉시 탈락\n허용 도구 · 승인 · 금지 행동\n8종 · 전 시나리오 공통', 232, 300),
      ...evalBand(1, '#EEF8F4', '', 'QUANTITATIVE', '정량 판정', '횟수를 세어 한도와 비교\n도구 호출 · 반복 · 중복 signature\n2종 공통 + 3종 조건부', 232, 300),
      ...evalBand(2, '#F5F0E8', '', 'QUALITATIVE · LLM JUDGE', '정성 판정', '의미 · 완성도를\n시나리오마다 다른 기준으로\n판단 유보 · 정직한 실패 · 근거 일치\n17종 · 시나리오별 상이', 232, 300),
    );
    return s;
  })();

  const deepAgentMovedSourceSlides = [4, 5, 6];
  const deepAgentMovedSlides = deepAgentMovedSourceSlides.map((sourceSlide) => ({
    background: '#FFFFFF',
    elements: [{
      kind: 'html',
      name: `deep-agent-slide-${sourceSlide}`,
      bbox: [0, 0, 1280, 720],
      src: '../Jihun_발표준비/deep_agent_deck.html',
      sourceSlide,
    }],
    sources: ['../Jihun_발표준비/deep_agent_deck.html'],
  }));
  deck.slides.splice(15, 0, ...deepAgentSlides, ...evaluationSlides, ...deepAgentMovedSlides);

  const appendixDivider = {
    background: '#111318',
    elements: [
      textElement('appendix-kicker', [82, 176, 1116, 34], 'APPENDIX', 18, '#6DCBF4', true),
      textElement('appendix-title', [76, 226, 1120, 112], '부록', 68, '#FFFFFF', true),
      { kind: 'shape', geometry: 'line', bbox: [82, 356, 1116, 0], lineColor: '#3A4350', lineWidth: 2, name: 'appendix-divider' },
      textElement('appendix-subtitle', [82, 382, 1116, 54], 'Skill 검증 및 사용 전후 비교', 24, '#C9CDD4'),
      textElement('appendix-items', [82, 548, 1116, 40], '등록 검증  ·  스킬 사용 전후 비교', 15, '#8A94A0'),
    ],
    sources: ['../Jihun_발표준비/deep_agent_deck.html'],
  };
  const appendixSlides = [7, 8].map((sourceSlide) => ({
    background: '#FFFFFF',
    elements: [{
      kind: 'html',
      name: `deep-agent-appendix-${sourceSlide}`,
      bbox: [0, 0, 1280, 720],
      src: '../Jihun_발표준비/deep_agent_deck.html',
      sourceSlide,
    }],
    sources: ['../Jihun_발표준비/deep_agent_deck.html'],
  }));
  deck.slides.push(appendixDivider, ...appendixSlides);

  // 31~35페이지(Deep Agent 이동본 3장 + PRODUCT EVIDENCE·PROJECT 2장)를
  // DEMO FLOW(41페이지) 바로 앞으로 옮긴다.
  const relocated = deck.slides.splice(30, 5);
  deck.slides.splice(35, 0, ...relocated);

  // 35페이지(EVALUATION PLAN) 뒤에 사용자 편의 기능(스킬·실행 과정·운영) 섹션 표지를
  // 15페이지 챕터 표지와 동일한 디자인으로 추가한다.
  const userConvDivider = (() => {
    const s = clone(slide(20));
    setElementText(s.elements.find((e) => e.name === 'div-title-20'), '사용자 편의 기능');
    setElementText(s.elements.find((e) => e.name === 'div-sub-20'), '검증된 스킬 재사용 · 실행 과정 공개 · 팀 단위 운영');
    setElementText(s.elements.find((e) => e.name === 'div-key-20'), 'SKILL · EXECUTION · OPERATIONS');
    return s;
  })();
  deck.slides.splice(35, 0, userConvDivider);

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
