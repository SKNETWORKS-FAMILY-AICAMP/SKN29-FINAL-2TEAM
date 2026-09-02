(() => {
  const text = (name, bbox, value, size, color = '#0A1020', bold = false, alignment = 'left') => ({
    kind: 'shape', geometry: 'rect', bbox, lineWidth: 0, text: value,
    paragraphs: value.split('\n').map((line, index) => ({
      index: index + 1, text: line,
      resolvedTextStyle: { fontSize: size, typeface: 'Pretendard', color, bold, alignment },
      runs: [{ index: 1, text: line, fontSize: size, typeface: 'Pretendard', color, bold }],
      bulletCharacter: '', marginLeft: 0
    })),
    textStyle: { fontSize: size, typeface: 'Pretendard', color, alignment, verticalAlignment: 'middle', autoFit: 'shrinkText', insets: { top: 0, right: 0, bottom: 0, left: 0 } },
    name
  });
  const box = (name, bbox, fillColor, lineColor = 'transparent', lineWidth = 0, geometry = 'rect') => ({ kind: 'shape', geometry, bbox, fillColor, lineColor, lineWidth, name });
  const line = (name, bbox, lineColor, lineWidth = 1) => ({ kind: 'shape', geometry: 'straightConnector1', bbox, lineColor, lineWidth, name });
  const image = (name, bbox, media) => ({ kind: 'image', bbox, name, media, fit: 'contain' });

  const chrome = (page, section, title) => [
    box(`top-accent-${page}`, [0, 0, 1280, 5], '#F8C944'),
    line(`top-rule-${page}`, [56, 38, 1168, 0], '#D9DEE8'),
    text(`context-${page}`, [58, 48, 416, 28], 'halil   ·   01 프로젝트 개요', 13, '#0A1020', true),
    text(`section-${page}`, [504, 51, 420, 22], section, 11, '#6C7482', true, 'center'),
    text(`page-${page}`, [1160, 50, 62, 22], String(page).padStart(2, '0'), 13, '#6C7482', true, 'right'),
    text(`title-${page}`, [58, 94, 1160, 58], title, 40, '#0A1020', true),
    box(`signal-${page}`, [58, 660, 78, 4], '#2878D1'),
    text(`signal-label-${page}`, [150, 651, 470, 22], section, 12, '#6C7482', true),
    image(`logo-koreatech-${page}`, [1019.56, 647, 78.89, 25], 'image2.png'),
    image(`logo-moel-${page}`, [1138.95, 647, 84.09, 25], 'image3.png')
  ];
  const stat = (name, x, value, label, color) => [
    text(`${name}-value`, [x, 194, 176, 76], value, 58, color, true),
    text(`${name}-label`, [x + 190, 204, 340, 54], label, 18, '#172033', true)
  ];
  const problem = (name, x, no, title, body) => [
    box(`${name}-panel`, [x, 380, 548, 178], '#FFFFFF', '#D9DEE8', 1, 'roundRect'),
    text(`${name}-no`, [x + 24, 396, 90, 24], no, 13, '#2878D1', true),
    text(`${name}-title`, [x + 24, 426, 500, 34], title, 22, '#101728', true),
    text(`${name}-body`, [x + 24, 474, 500, 62], body, 16, '#52657D')
  ];
  const compactProblem = (name, x, no, title, body) => [
    box(`${name}-panel`, [x, 414, 350, 142], '#FFFFFF', '#D9DEE8', 1, 'roundRect'),
    text(`${name}-no`, [x + 22, 430, 42, 22], no, 12, '#2878D1', true),
    text(`${name}-title`, [x + 22, 458, 306, 32], title, 19, '#101728', true),
    text(`${name}-body`, [x + 22, 500, 306, 38], body, 14, '#52657D')
  ];
  const axisHeader = (name, x, value) => [
    line(`${name}-line`, [x, 206, 60, 0], '#2878D1', 4),
    text(name, [x + 72, 190, 258, 34], value, 18, '#172033', true)
  ];
  const platformAxis = (name, x, number, title, body, tech, fill) => [
    box(`${name}-panel`, [x, 242, 350, 298], fill, '#D9DEE8', 1, 'roundRect'),
    text(`${name}-number`, [x + 24, 264, 52, 32], number, 15, '#2878D1', true),
    text(`${name}-title`, [x + 24, 310, 302, 64], title, 22, '#101728', true),
    text(`${name}-body`, [x + 24, 390, 302, 72], body, 16, '#52657D'),
    line(`${name}-divider`, [x + 24, 478, 302, 0], '#CBD4E1'),
    text(`${name}-tech`, [x + 24, 494, 302, 28], tech, 13, '#2878D1', true)
  ];

  const slide3 = {
    number: 3, background: '#EEF2F7', width: 1280, height: 720,
    elements: [
      box('divider-top-accent', [0, 0, 1280, 5], '#F8C944'),
      box('divider-left-accent', [0, 0, 18, 720], '#557FC8'),
      text('divider-number', [62, 82, 260, 100], '01', 66, '#557FC8', true),
      text('divider-title', [62, 236, 760, 86], '프로젝트 개요', 48, '#0A1020', true),
      line('divider-bottom-rule', [62, 566, 1136, 0], '#CDD5E0'),
      text('divider-flow', [62, 586, 820, 30], '시장 변화  ·  업무 확장 과제  ·  시장 확인  ·  플랫폼 방향', 14, '#557FC8', true),
      text('divider-page', [1128, 586, 70, 24], '03', 13, '#6C7482', true, 'right'),
      image('divider-logo-koreatech', [1019.56, 647, 78.89, 25], 'image2.png'),
      image('divider-logo-moel', [1138.95, 647, 84.09, 25], 'image3.png')
    ]
  };

  const slide4 = {
    number: 4, background: '#F7F6F1', width: 1280, height: 720,
    elements: [
      ...chrome(4, '시장 변화 · 업무 확장 과제', 'AI Agent 도입과 업무 확장'),
      text('adoption-value', [72, 184, 238, 82], '62%', 64, '#2878D1', true),
      text('adoption-label', [282, 194, 286, 60], 'AI Agent\n최소 실험 단계 이상', 18, '#172033', true),
      line('metric-divider', [624, 184, 0, 86], '#CBD4E1', 2),
      text('scaling-value', [684, 184, 216, 82], '23%', 64, '#17845E', true),
      text('scaling-label', [884, 194, 324, 60], '최소 1개 업무 기능에서\n확장 중', 18, '#172033', true),
      text('metric-note-label', [398, 278, 282, 28], '개별 업무 영역 기준', 16, '#52657D', true, 'right'),
      text('metric-note-value', [696, 272, 190, 38], '10% 이하', 25, '#B26A1B', true),
      text('source-4', [72, 312, 1136, 18], '출처: McKinsey, The State of AI 2025', 10, '#7B8492', false, 'center'),
      line('divider-4', [72, 344, 1136, 0], '#D3DCE8'),
      text('problem-kicker', [72, 364, 1136, 28], '업무 확장의 핵심 과제', 16, '#52657D', true),
      ...compactProblem('problem-1', 72, '01', '분산된 정보와 업무 도구', '문서와 업무 시스템이 여러 환경에 분산'),
      ...compactProblem('problem-2', 465, '02', '개인에게 머무는 업무 방식', '업무 절차와 경험을 공유·재사용하기 어려움'),
      ...compactProblem('problem-3', 858, '03', '조직 차원의 운영 통제', '권한·승인·실행 이력 관리 필요')
    ]
  };

  const slide5 = {
    number: 5, background: '#F7F6F1', width: 1280, height: 720,
    elements: [
      ...chrome(5, '시장 확인', 'AI Agent 시장과 선도 서비스'),
      text('market-kicker', [72, 164, 500, 26], '글로벌 시장 전망', 15, '#52657D', true),
      text('market-year-2025', [94, 224, 112, 24], '2025', 14, '#52657D', true, 'center'),
      box('market-circle-2025', [114, 266, 72, 72], '#DCE9F8', '#9DBCE2', 1, 'ellipse'),
      text('market-value-2025', [104, 279, 92, 46], '$7.8B', 18, '#215FA8', true, 'center'),
      box('market-growth-arrow', [206, 290, 96, 24], '#718DB7', 'transparent', 0, 'rightArrow'),
      text('market-year-2030', [326, 196, 188, 24], '2030', 14, '#52657D', true, 'center'),
      box('market-circle-2030', [326, 228, 188, 188], '#2878D1', '#2878D1', 1, 'ellipse'),
      text('market-value-2030', [338, 291, 164, 56], '$52.6B', 28, '#FFFFFF', true, 'center'),
      text('growth-label', [154, 458, 92, 38], '연평균', 17, '#52657D', true, 'right'),
      text('growth-value', [256, 446, 132, 52], '46.3%', 34, '#17845E', true, 'center'),
      text('growth-caption', [398, 458, 96, 38], '성장 전망', 17, '#172033', true),
      line('market-divider', [602, 166, 0, 410], '#D3DCE8'),
      text('service-kicker', [638, 164, 570, 26], '선도 서비스의 공통 영역', 15, '#52657D', true),
      text('service-glean', [638, 214, 256, 32], 'Glean', 17, '#172033', true),
      text('service-copilot', [920, 214, 288, 32], 'Copilot Studio', 17, '#172033', true),
      line('service-line-1', [638, 252, 570, 0], '#D8E0EA'),
      text('service-cohere', [638, 272, 256, 32], 'Cohere North', 17, '#172033', true),
      text('service-ibm', [920, 272, 288, 32], 'IBM watsonx Orchestrate', 17, '#172033', true),
      text('common-label', [638, 338, 570, 26], '공통적으로 확인된 제공 영역', 14, '#557FC8', true),
      box('common-connect-band', [638, 378, 570, 54], '#EEF4FC'),
      text('common-connect-index', [658, 392, 46, 26], '01', 14, '#557FC8', true),
      text('common-connect', [716, 390, 456, 30], '정보·도구 연결', 18, '#172033', true),
      box('common-run-band', [638, 442, 570, 54], '#E7F0FB'),
      text('common-run-index', [658, 456, 46, 26], '02', 14, '#557FC8', true),
      text('common-run', [716, 454, 456, 30], 'Agent 생성·실행', 18, '#172033', true),
      box('common-manage-band', [638, 506, 570, 54], '#DEEAF8'),
      text('common-manage-index', [658, 520, 46, 26], '03', 14, '#557FC8', true),
      text('common-manage', [716, 518, 456, 30], '운영·통제', 18, '#172033', true),
      text('source-5', [72, 602, 1136, 18], '출처: MarketsandMarkets AI Agents Market · 각 서비스 공식 제품 문서', 10, '#7B8492', false, 'center')
    ]
  };

  const slide6 = {
    number: 6, background: '#F7F6F1', width: 1280, height: 720,
    elements: [
      ...chrome(6, '플랫폼 방향', '기업 Agent 플랫폼, HALIL'),
      image('halil-brand-logo', [568, 168, 144, 54], 'halil-logo.png'),
      line('flow-connector', [166, 390, 948, 0], '#9DB3D3', 3),
      ...platformAxis('platform-connect', 72, '01', '정보·도구 연결', '흩어진 문서와\n업무 시스템을 연결', 'Connector · MCP · 문서 처리', '#EEF4FC'),
      ...platformAxis('platform-run', 465, '02', '에이전트 생성·실행', '업무 노하우를 Agent로\n구성하고 실행·재사용', 'Agent Builder · Tool · Sub-agent', '#FFFFFF'),
      ...platformAxis('platform-manage', 858, '03', '운영·관리', '권한과 승인, 실행 결과를\n조직 단위로 관리', '권한 · 승인 · OPS · 실행 추적', '#F2F7F4'),
      text('platform-close', [72, 566, 1136, 42], '기업 Agent의 연결  ·  실행  ·  운영을 하나의 플랫폼에서', 23, '#173F7A', true, 'center')
    ]
  };

  window.HALIL_OVERVIEW_SLIDES = [slide3, slide4, slide5, slide6];
  window.HALIL_DECK = { title: 'halil · 프로젝트 개요', slideSize: { width: 1280, height: 720 }, slides: window.HALIL_OVERVIEW_SLIDES };
})();
