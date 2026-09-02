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
      text('divider-flow', [62, 586, 760, 30], '시장 변화  ·  문제 정의  ·  시장 확인  ·  플랫폼 방향', 14, '#557FC8', true),
      text('divider-page', [1128, 586, 70, 24], '03', 13, '#6C7482', true, 'right'),
      image('divider-logo-koreatech', [1019.56, 647, 78.89, 25], 'image2.png'),
      image('divider-logo-moel', [1138.95, 647, 84.09, 25], 'image3.png')
    ]
  };

  const slide4 = {
    number: 4, background: '#F7F6F1', width: 1280, height: 720,
    elements: [
      ...chrome(4, '시장 변화 · 문제 정의', '기업 AI Agent의 업무 확장 과제'),
      ...stat('experiment', 72, '39%', 'AI Agent\n실험 중', '#2878D1'),
      ...stat('scaling', 704, '23%', '최소 1개 업무에서\n확장 중', '#17845E'),
      text('source-4', [72, 286, 1136, 22], '출처: McKinsey, The State of AI 2025', 11, '#7B8492'),
      line('divider-4', [72, 328, 1136, 0], '#D3DCE8'),
      text('problem-kicker', [72, 344, 1136, 28], '우리가 주목한 두 가지 과제', 16, '#52657D', true),
      ...problem('problem-1', 72, '01', '흩어진 정보와 업무 환경', '문서와 업무 시스템이 여러 곳에 흩어져\n필요한 정보를 한 번에 활용하기 어려움'),
      ...problem('problem-2', 660, '02', '개인에게 머무는 업무 노하우', '업무 절차와 경험이 개인에게 남아\n공유하고 재사용하기 어려움')
    ]
  };

  const slide5 = {
    number: 5, background: '#F7F6F1', width: 1280, height: 720,
    elements: [
      ...chrome(5, '시장 확인', '선도 서비스 공통 요소'),
      box('header-band', [304, 184, 904, 62], '#EEF4FC'),
      text('service-header', [78, 190, 210, 42], '서비스', 15, '#6C7482', true),
      ...axisHeader('axis-connect', 328, '정보·도구 연결'),
      ...axisHeader('axis-run', 642, '에이전트 생성·실행'),
      ...axisHeader('axis-manage', 956, '운영·관리'),
      line('table-top', [72, 246, 1136, 0], '#AEBAC9'),
      line('column-1', [304, 184, 0, 316], '#D1D9E4'),
      line('column-2', [618, 184, 0, 316], '#D1D9E4'),
      line('column-3', [932, 184, 0, 316], '#D1D9E4'),
      text('service-glean', [78, 266, 210, 84], 'Glean', 23, '#101728', true),
      text('glean-connect', [328, 266, 270, 84], '사내 정보와\n접근 권한 연결', 16, '#394A60'),
      text('glean-run', [642, 266, 270, 84], '자연어 기반\n에이전트 구성·실행', 16, '#394A60'),
      text('glean-manage', [956, 266, 252, 84], '공유와\n접근 권한 관리', 16, '#394A60'),
      line('row-divider', [72, 370, 1136, 0], '#D9DEE8'),
      text('service-copilot', [78, 392, 210, 84], 'Copilot Studio', 23, '#101728', true),
      text('copilot-connect', [328, 392, 270, 84], '기업 데이터와\n업무 도구 연결', 16, '#394A60'),
      text('copilot-run', [642, 392, 270, 84], '에이전트와\n업무 흐름 구성', 16, '#394A60'),
      text('copilot-manage', [956, 392, 252, 84], '보안 정책과\n환경 단위 관리', 16, '#394A60'),
      line('table-bottom', [72, 500, 1136, 0], '#BFC9D6'),
      text('market-summary', [72, 538, 1136, 38], '공통 핵심   |   연결  ·  실행  ·  관리', 21, '#0C3F91', true, 'center'),
      text('source-5', [72, 604, 1136, 18], '출처: Glean · Microsoft Copilot Studio 공식 제품 및 거버넌스 문서', 10, '#7B8492', false, 'center')
    ]
  };

  const slide6 = {
    number: 6, background: '#F7F6F1', width: 1280, height: 720,
    elements: [
      ...chrome(6, '플랫폼 방향', '기업 업무 활용 Agent 플랫폼'),
      image('halil-brand-logo', [568, 168, 144, 54], 'halil-logo.png'),
      line('flow-connector', [166, 390, 948, 0], '#9DB3D3', 3),
      ...platformAxis('platform-connect', 72, '01', '정보·도구 연결', '흩어진 문서와\n업무 시스템을 연결', 'Connector · MCP · 문서 처리', '#EEF4FC'),
      ...platformAxis('platform-run', 465, '02', '에이전트 생성·실행', '업무 노하우를 Agent로\n구성하고 실행·재사용', 'Agent Builder · Tool · Sub-agent', '#FFFFFF'),
      ...platformAxis('platform-manage', 858, '03', '운영·관리', '권한과 승인, 실행 결과를\n조직 단위로 관리', '권한 · 승인 · OPS · 실행 추적', '#F2F7F4'),
      text('platform-close', [72, 570, 1136, 34], '연결  ·  실행  ·  관리를 하나의 업무 흐름으로', 18, '#52657D', true, 'center')
    ]
  };

  window.HALIL_OVERVIEW_SLIDES = [slide3, slide4, slide5, slide6];
  window.HALIL_DECK = { title: 'halil · 프로젝트 개요', slideSize: { width: 1280, height: 720 }, slides: window.HALIL_OVERVIEW_SLIDES };
})();
