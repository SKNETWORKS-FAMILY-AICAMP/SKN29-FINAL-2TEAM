// Generates deck-data.js in the same schema as ../halil_html/deck-data.js
// Run: node build_deck.js
const fs = require('fs');
const path = require('path');

const COLOR = {
  ink: '#0A1020',
  body: '#20283A',
  muted: '#6C7482',
  faint: '#8792A6',
  rule: '#D9DEE8',
  accentYellow: '#F8C944',
  blue: '#2878D1',
  blueSoft: '#EAF2FB',
  blueLine: '#D8E5F6',
  purple: '#5F6FE8',
  purpleSoft: '#EAF0FF',
  green: '#17845E',
  greenSoft: '#E9FAF4',
  greenLine: '#B8E8D4',
  orange: '#D88628',
  orangeSoft: '#FFF4E6',
  orangeLine: '#F6DDB8',
  teal: '#0EA5B7',
  tealSoft: '#E6F9FB',
};

function text(name, bbox, str, opts = {}) {
  const {
    fontSize = 16, color = COLOR.body, bold = false, alignment = 'left',
    verticalAlignment = 'top', lineSpacingPercent = 128000,
  } = opts;
  const lines = String(str).split('\n');
  return {
    kind: 'shape', geometry: 'rect', bbox, lineWidth: 0, text: str,
    paragraphs: lines.map((line, i) => ({
      index: i + 1, text: line, lineSpacingPercent,
      resolvedTextStyle: { fontSize, typeface: 'Pretendard', color, bold, alignment },
      runs: [{ index: 1, text: line, fontSize, typeface: 'Pretendard', color, bold }],
      bulletCharacter: '', marginLeft: 0,
    })),
    textStyle: {
      anchor: 1, fontSize: 24, typeface: 'Calibri', color: 'tx1', alignment,
      verticalAlignment, wrap: 'square', autoFit: 'shrinkText',
      insets: { top: 0, right: 0, bottom: 0, left: 0 },
    },
    name,
  };
}

function rect(name, bbox, fillColor, opts = {}) {
  const { lineColor, lineWidth = 0, radius } = opts;
  return {
    kind: 'shape', geometry: radius ? 'roundRect' : 'rect', bbox,
    fillColor, lineColor, lineWidth,
    textStyle: { fontSize: 24, typeface: 'Calibri', color: 'tx1', alignment: 'left', insets: { top: 4.8, right: 9.6, bottom: 4.8, left: 9.6 } },
    name,
  };
}

function hline(name, bbox, lineColor, lineWidth = 1) {
  return { kind: 'shape', geometry: 'straightConnector1', bbox, lineColor, lineWidth, name };
}

function image(name, bbox, media) {
  return { kind: 'image', bbox, name, media, fit: 'contain' };
}

function fitBox(naturalW, naturalH, maxW, maxH) {
  const scale = Math.min(maxW / naturalW, maxH / naturalH);
  const w = naturalW * scale, h = naturalH * scale;
  return [w, h];
}

let counter = 0;
function uid() { return ++counter; }

function header(n, ctxLabel, sectionTag) {
  return [
    rect(`top-accent-${n}`, [0, 0, 1280, 5], COLOR.accentYellow),
    hline(`top-rule-${n}`, [56, 38, 1168, 0], COLOR.rule, 1),
    text(`context-${n}`, [58, 48, 640, 28], `wonbin   ·   ${ctxLabel}`, { fontSize: 13, color: COLOR.ink, bold: true }),
    text(`section-${n}`, [780, 51, 340, 22], sectionTag, { fontSize: 11, color: COLOR.muted, bold: true, alignment: 'right' }),
    text(`page-${n}`, [1160, 50, 62, 22], String(n).padStart(2, '0'), { fontSize: 13, color: COLOR.muted, bold: true, alignment: 'right' }),
  ];
}

function footer(n, sectionTag) {
  return [
    rect(`signal-${n}`, [58, 660, 78, 4], COLOR.blue),
    text(`foot-${n}`, [150, 655, 640, 22], sectionTag, { fontSize: 12, color: COLOR.muted, bold: true }),
  ];
}

function titleBlock(n, titleStr, subtitleStr, opts = {}) {
  const { titleSize = 34, y = 92 } = opts;
  const els = [
    text(`title-${n}`, [58, y, 1160, 58], titleStr, { fontSize: titleSize, color: COLOR.ink, bold: true, lineSpacingPercent: 112000 }),
  ];
  if (subtitleStr) {
    els.push(text(`sub-${n}`, [60, y + 62, 1080, 34], subtitleStr, { fontSize: 16, color: COLOR.muted }));
  }
  return els;
}

function slideBase(n, bg, ctxLabel, sectionTag) {
  const els = [];
  if (ctxLabel) els.push(...header(n, ctxLabel, sectionTag));
  if (ctxLabel) els.push(...footer(n, sectionTag));
  return els;
}

function chip(name, bbox, str, fg, bg2, opts = {}) {
  const { fontSize = 13 } = opts;
  return [
    rect(`${name}-bg`, bbox, bg2, { radius: true }),
    text(name, [bbox[0] + 14, bbox[1] + (bbox[3] - fontSize * 1.3) / 2, bbox[2] - 28, fontSize * 1.6], str, { fontSize, color: fg, bold: true, alignment: 'center', verticalAlignment: 'middle' }),
  ];
}

function numberedRow(n, idx, y, num, title, desc) {
  const rowH = 74;
  return [
    hline(`div-${n}-${idx}`, [60, y, 1160, 0], COLOR.rule, 1),
    text(`num-${n}-${idx}`, [60, y + 16, 56, 30], num, { fontSize: 20, color: COLOR.blue, bold: true }),
    text(`rowt-${n}-${idx}`, [138, y + 12, 260, 40], title, { fontSize: 16, color: COLOR.ink, bold: true }),
    text(`rowd-${n}-${idx}`, [420, y + 12, 800, 46], desc, { fontSize: 14, color: COLOR.body }),
  ];
}

const slides = [];

/* ---------------- Slide 1: Title ---------------- */
slides.push({
  number: 1, background: '#071426', width: 1280, height: 720,
  elements: [
    rect('t1-accent', [0, 0, 1280, 6], COLOR.accentYellow),
    text('t1-eyebrow', [120, 240, 800, 30], 'DOCLING PARSING PIPELINE', { fontSize: 14, color: '#7FA6E8', bold: true }),
    text('t1-title', [118, 276, 1044, 160], '도클링 기반 문서 파싱\n파이프라인 보완 설계', { fontSize: 52, color: '#F4F8FF', bold: true, lineSpacingPercent: 118000 }),
    text('t1-sub', [120, 452, 900, 60], '읽기 순서 · 제목 · 표 · 이미지 보완 레이어와 청킹·임베딩', { fontSize: 18, color: '#9FB3D6' }),
    hline('t1-rule', [120, 540, 300, 0], '#2A4166', 2),
    text('t1-owner', [120, 560, 500, 26], 'wonbin', { fontSize: 14, color: '#5F87C7', bold: true }),
  ],
});

/* ---------------- Slide 2: 01 도클링 선택 배경 ---------------- */
{
  const n = 2, ctx = '01 도클링 선택 배경', tag = 'WHY DOCLING';
  const [iw, ih] = fitBox(1400, 430, 1000, 300);
  slides.push({
    number: n, background: '#F7F6F1', width: 1280, height: 720,
    elements: [
      ...slideBase(n, '#F7F6F1', ctx, tag),
      ...titleBlock(n, '왜 도클링인가', '여러 문서처리 오픈소스 중 커뮤니티가 가장 크게 형성된 프로젝트'),
      image(`img-${n}`, [(1280 - iw) / 2, 190, iw, ih], 'github_activity.svg'),
      text(`cap-${n}`, [58, 190 + ih + 16, 1160, 60], '플랫폼을 운영하는 입장에서 유지보수와 지속가능성을 고려했을 때, 도클링을 사용하는 것이 적합하다고 판단했습니다.', { fontSize: 15, color: COLOR.body }),
    ],
  });
}

/* ---------------- Slide 3: 02 기본 파싱 파이프라인 ---------------- */
{
  const n = 3, ctx = '02 기본 파싱 파이프라인', tag = 'BASE PIPELINE';
  const els = [
    ...slideBase(n, '#F7F6F1', ctx, tag),
    ...titleBlock(n, 'PDF는 12단계를 거쳐 DoclingDocument가 됩니다', '문서 입력부터 최종 구조화 출력까지 이어지는 처리 흐름'),
  ];
  const [r1w, r1h] = fitBox(1159.81, 133.70, 1160, 150);
  const [r2w, r2h] = fitBox(1342.83, 79.00, 1160, 90);
  const [r3w, r3h] = fitBox(1649.89, 74.00, 1160, 90);
  let y = 194;
  els.push(image(`pr1-${n}`, [58, y, r1w, r1h], 'pipeline_row1.svg'));
  y += r1h + 34;
  els.push(image(`pr2-${n}`, [58, y, r2w, r2h], 'pipeline_row2.svg'));
  y += r2h + 34;
  els.push(image(`pr3-${n}`, [58, y, r3w, r3h], 'pipeline_row3.svg'));
  y += r3h + 30;
  els.push(text(`plabel-${n}`, [58, y, 1100, 24], 'DOCX · PPTX · Markdown은 형식별 Backend를 거쳐 같은 DoclingDocument로 합류합니다.', { fontSize: 14, color: COLOR.muted }));
  slides.push({ number: n, background: '#F7F6F1', width: 1280, height: 720, elements: els });
}

/* ---------------- Slide 4: 02 DoclingDocument 결과 ---------------- */
{
  const n = 4, ctx = '02 DoclingDocument 결과', tag = 'PARSED RESULT';
  const [iw, ih] = fitBox(1600, 900, 620, 380);
  const els = [
    ...slideBase(n, '#F7F6F1', ctx, tag),
    ...titleBlock(n, '실제 파싱 결과 예시', 'body 안에 텍스트·표·그림이 읽기 순서대로 정렬됩니다'),
    image(`img-${n}`, [58, 190, iw, ih], 'docling_json.png'),
  ];
  const chipsX = 58 + iw + 32;
  const rows = [
    ['TEXT', COLOR.blue, COLOR.blueSoft, '역할(label) · 원문 · 좌표값'],
    ['TABLE', COLOR.orange, COLOR.orangeSoft, '셀 정보와 페이지 좌표'],
    ['PICTURE', COLOR.teal, COLOR.tealSoft, '분류·신뢰도·캡션·좌표'],
  ];
  rows.forEach((r, i) => {
    const y = 200 + i * 130;
    els.push(...chip(`jc-${n}-${i}`, [chipsX, y, 150, 34], r[0], r[1], r[2], { fontSize: 13 }));
    els.push(text(`jt-${n}-${i}`, [chipsX, y + 44, 460, 60], r[3], { fontSize: 14, color: COLOR.body }));
  });
  slides.push({ number: n, background: '#F7F6F1', width: 1280, height: 720, elements: els });
}

/* ---------------- Slide 5: 03 검증과 문제 발견 ---------------- */
{
  const n = 5, ctx = '03 검증과 문제 발견', tag = 'VALIDATION';
  const els = [
    ...slideBase(n, '#F7F6F1', ctx, tag),
    ...titleBlock(n, '206개 문서로 파싱 정확도를 검증했습니다', '기획서 · 보고서 · 브로슈어 등 다양한 실제 기업 문서'),
    text(`p1-${n}`, [60, 210, 1080, 60], '정형화된 보고서·가이드 문서는 비교적 안정적으로 파싱됐지만, 브로슈어형 PDF에서는 정확도가 크게 낮아지는 사례가 집중적으로 확인됐습니다.', { fontSize: 16, color: COLOR.body }),
    text(`p2-${n}`, [60, 270, 1080, 80], '브로슈어는 페이지마다 글꼴·글자 크기가 다르고, 문단·그림·표·장식이 자유롭게 배치되며, 읽는 방향과 제목 경계가 디자인마다 달라집니다.', { fontSize: 16, color: COLOR.body }),
    rect(`refbox-${n}`, [58, 400, 1160, 150], '#FFFFFF', { lineColor: COLOR.rule, lineWidth: 1 }),
    text(`refl-${n}`, [82, 420, 300, 22], 'REFERENCE', { fontSize: 11, color: COLOR.muted, bold: true }),
    text(`ref1-${n}`, [82, 448, 1080, 44], 'DocLayNet — 학술 문서로 학습한 모델을 다양한 문서 배치에 적용하면 영역 구분 정확도가 크게 낮아진다 (arXiv:2206.01062)', { fontSize: 14, color: COLOR.body }),
    text(`ref2-${n}`, [82, 494, 1080, 44], 'ICDAR 2023 기업 문서 배치 분석 대회 — 복잡한 구조와 형식의 다양성을 문서 변환의 핵심 난제로 정의 (arXiv:2305.14962)', { fontSize: 14, color: COLOR.body }),
  ];
  slides.push({ number: n, background: '#F7F6F1', width: 1280, height: 720, elements: els });
}

/* ---------------- Slide 6: 04 네 가지 문제 ---------------- */
{
  const n = 6, ctx = '04 네 가지 문제', tag = 'FOUR ISSUES';
  const items = [
    ['01', '제목 미검출', 'section_header 인식 실패로 섹션 경계가 사라지고 맥락이 뒤섞입니다'],
    ['02', '읽기 순서 오류', '문장 연결이 끊겨 원래 의미와 다른 결과가 만들어집니다'],
    ['03', '표 오검출 · 구조 붕괴', '표가 아닌 디자인을 표로 오인하거나 행·열·셀 관계가 손상됩니다'],
    ['04', '이미지 설명 부족', '검색에 활용할 수 있는 이미지 설명 정보가 없습니다'],
  ];
  const els = [
    ...slideBase(n, '#F7F6F1', ctx, tag),
    ...titleBlock(n, '문서 파싱 결과에서 확인된 네 가지 문제', ''),
  ];
  items.forEach((it, i) => {
    els.push(...numberedRow(n, i, 220 + i * 92, it[0], it[1], it[2]));
  });
  slides.push({ number: n, background: '#F7F6F1', width: 1280, height: 720, elements: els });
}

/* ---------------- Slide 7: 05 보완 레이어 설계 ---------------- */
{
  const n = 7, ctx = '05 보완 레이어 설계', tag = 'LAYER DESIGN';
  const [iw, ih] = fitBox(641.24, 587.80, 480, 400);
  const els = [
    ...slideBase(n, '#F7F6F1', ctx, tag),
    ...titleBlock(n, '네 개의 보완 레이어', 'DoclingDocument를 입력받아 DoclingDocument를 갱신하는 후처리 체인'),
    image(`img-${n}`, [58, 190, iw, ih], 'diagram_layers_overview.svg'),
  ];
  const px = 58 + iw + 40;
  const principles = [
    ['01', '규칙 기반 우선', '읽기 순서·제목·표는 명확한 규칙으로 먼저 보완합니다'],
    ['02', 'Docling 비침습', '내부 모델은 그대로 두고 후처리 레이어로만 구성합니다'],
    ['03', '검증 가능한 범위부터', '반복 확인된 오류부터 안정적으로 줄이는 것을 목표로 합니다'],
  ];
  principles.forEach((p, i) => {
    const y = 210 + i * 130;
    els.push(text(`pn-${n}-${i}`, [px, y, 40, 30], p[0], { fontSize: 18, color: COLOR.blue, bold: true }));
    els.push(text(`pt-${n}-${i}`, [px + 44, y, 560, 30], p[1], { fontSize: 16, color: COLOR.ink, bold: true }));
    els.push(text(`pd-${n}-${i}`, [px + 44, y + 32, 560, 60], p[2], { fontSize: 14, color: COLOR.body }));
  });
  slides.push({ number: n, background: '#F7F6F1', width: 1280, height: 720, elements: els });
}

/* ---------------- Slide 8: 05-1a 읽기 순서 — 사례 ---------------- */
{
  const n = 8, ctx = '05-1 읽기 순서 보완', tag = 'READING ORDER · 사례';
  const [iw, ih] = fitBox(1100, 575, 560, 420);
  const els = [
    ...slideBase(n, '#F7F6F1', ctx, tag),
    ...titleBlock(n, '읽기 순서가 뒤바뀐 실제 사례', '삼성SDS 검증범위 문서(p.156) — 인접한 두 항목이 4·5에서 5·4로 역전'),
    text(`bl-${n}`, [58, 190, iw, 20], 'BEFORE', { fontSize: 12, color: '#B42318', bold: true }),
    image(`imgb-${n}`, [58, 214, iw, ih], 'ro_before.png'),
    text(`al-${n}`, [58 + iw + 40, 190, iw, 20], 'AFTER', { fontSize: 12, color: '#085D3A', bold: true }),
    image(`imga-${n}`, [58 + iw + 40, 214, iw, ih], 'ro_after.png'),
  ];
  slides.push({ number: n, background: '#F7F6F1', width: 1280, height: 720, elements: els });
}

/* ---------------- Slide 9: 05-1b 읽기 순서 — 판단 로직 ---------------- */
{
  const n = 9, ctx = '05-1 읽기 순서 보완', tag = 'READING ORDER · 로직';
  const [dw, dh] = fitBox(862.76, 430.20, 1160, 420);
  const els = [
    ...slideBase(n, '#F7F6F1', ctx, tag),
    ...titleBlock(n, '인접 요소 좌표 비교로 순서를 보정합니다', '핵심: 화면상 더 아래 있는 요소가 읽기 순서상 더 앞서면, 그 둘의 순서만 맞바꿉니다'),
    image(`diag-${n}`, [(1280 - dw) / 2, 200, dw, dh], 'diagram_reading_order.svg'),
  ];
  slides.push({ number: n, background: '#F7F6F1', width: 1280, height: 720, elements: els });
}

/* ---------------- Slide 10: 05-2a 제목 추출 — 사례 ---------------- */
{
  const n = 10, ctx = '05-2 제목 추출 보완', tag = 'HEADING · 사례';
  const [iw1, ih1] = fitBox(221, 152, 420, 300);
  const [iw2, ih2] = fitBox(557, 401, 620, 420);
  const els = [
    ...slideBase(n, '#F7F6F1', ctx, tag),
    ...titleBlock(n, '한화 브로슈어에서 확인된 오분류', 'Asia-Pacific — 사람은 명확한 제목인데 Docling은 list_item으로 판정'),
    text(`l1-${n}`, [58, 190, iw1, 20], '문서 원본', { fontSize: 12, color: COLOR.muted, bold: true }),
    image(`img1-${n}`, [58, 214, iw1, ih1], 'hanwha_doc.png'),
    text(`l2-${n}`, [58 + iw1 + 40, 190, iw2, 20], 'Docling 레이아웃 판정', { fontSize: 12, color: COLOR.muted, bold: true }),
    image(`img2-${n}`, [58 + iw1 + 40, 214, iw2, ih2], 'hanwha_layout.png'),
  ];
  slides.push({ number: n, background: '#F7F6F1', width: 1280, height: 720, elements: els });
}

/* ---------------- Slide 11: 05-2b 제목 추출 — 승격 로직 ---------------- */
{
  const n = 11, ctx = '05-2 제목 추출 보완', tag = 'HEADING · 로직';
  const [dw, dh] = fitBox(702.18, 564.80, 1160, 400);
  const dx = (1280 - dw) / 2;
  const els = [
    ...slideBase(n, '#F7F6F1', ctx, tag),
    ...titleBlock(n, 'list_item을 section_header로 승격하는 조건', '네 조건을 모두 만족해야만 승격합니다 (AND)'),
    image(`diag-${n}`, [dx, 186, dw, dh], 'diagram_heading.svg'),
    text(`ref-${n}`, [dx, 186 + dh + 14, dw, 20], 'Docling GitHub Issue #2246 — Inconsistent section_header vs list_item', { fontSize: 12, color: COLOR.faint, alignment: 'center' }),
  ];
  slides.push({ number: n, background: '#F7F6F1', width: 1280, height: 720, elements: els });
}

/* ---------------- Slide 12: 05-3a 표 보완 — 사례 ---------------- */
{
  const n = 12, ctx = '05-3 표 보완', tag = 'TABLE GATE · 사례';
  const [iw, ih] = fitBox(1398, 300, 1160, 300);
  const els = [
    ...slideBase(n, '#F7F6F1', ctx, tag),
    ...titleBlock(n, '표로 오인식된 비표 사례', '점선 목차 · 다단 박스형 목차 · 밑줄 구분선 목차 — 모두 표가 아닙니다'),
    image(`img-${n}`, [58, 198, iw, ih], 'table_grid_examples.png'),
  ];
  const statY = 198 + ih + 30;
  const stats = [
    ['28,885건', 'TableItem 직접 대조'],
    ['134건', '확실한 비표로 확정 제거'],
    ['0건', '실제 표를 잘못 제거한 사례'],
  ];
  const colW = 1160 / 3;
  stats.forEach((s, i) => {
    const x = 58 + i * colW;
    els.push(text(`sv-${n}-${i}`, [x, statY, colW - 20, 46], s[0], { fontSize: 32, color: COLOR.orange, bold: true }));
    els.push(text(`sl-${n}-${i}`, [x, statY + 48, colW - 20, 24], s[1], { fontSize: 14, color: COLOR.muted }));
  });
  slides.push({ number: n, background: '#F7F6F1', width: 1280, height: 720, elements: els });
}

/* ---------------- Slide 13: 05-3b 표 보완 — 판단 로직 ---------------- */
{
  const n = 13, ctx = '05-3 표 보완', tag = 'TABLE GATE · 로직';
  const [dw, dh] = fitBox(865.68, 453.40, 1160, 420);
  const els = [
    ...slideBase(n, '#F7F6F1', ctx, tag),
    ...titleBlock(n, '실제 표인지 판단하는 기준', '점선 목차·페이지 번호·긴 문장·단일 셀 같은 비표 패턴만 확실할 때 제거합니다'),
    image(`diag-${n}`, [(1280 - dw) / 2, 196, dw, dh], 'diagram_table.svg'),
  ];
  slides.push({ number: n, background: '#F7F6F1', width: 1280, height: 720, elements: els });
}

/* ---------------- Slide 14: 05-4a 이미지 설명 — 문제 ---------------- */
{
  const n = 14, ctx = '05-4 이미지 설명 보완', tag = 'IMAGE DESCRIPTION · 문제';
  const els = [
    ...slideBase(n, '#F7F6F1', ctx, tag),
    ...titleBlock(n, '기존 Docling 이미지 설명의 세 가지 문제', '한국어 안정성 · 할루시네이션 · 고정 프롬프트'),
  ];
  const problems = [
    ['한국어 안정성', '설명을 거부하거나 반복 생성이 끝나지 않는 무효 응답이 그대로 저장되는 사례가 확인됐습니다.'],
    ['할루시네이션', '국적·연령대·직업·생몰년도 등 이미지나 문맥에 없는 정보가 지어내듯 생성됐습니다.'],
    ['프롬프트 고정', '이미지 분류마다 봐야 할 정보가 다른데 지침이 고정돼 있어 설명 품질이 떨어졌습니다.'],
  ];
  const gap = 32, colW = (1160 - gap * 2) / 3;
  problems.forEach((p, i) => {
    const x = 58 + i * (colW + gap);
    els.push(rect(`pb-${n}-${i}`, [x, 210, colW, 300], '#FFFFFF', { lineColor: COLOR.rule, lineWidth: 1, radius: true }));
    els.push(rect(`pd-${n}-${i}`, [x + 24, 244, 36, 4], COLOR.blue));
    els.push(text(`pt-${n}-${i}`, [x + 24, 264, colW - 48, 30], p[0], { fontSize: 19, color: COLOR.ink, bold: true }));
    els.push(text(`pdesc-${n}-${i}`, [x + 24, 304, colW - 48, 180], p[1], { fontSize: 15, color: COLOR.body, lineSpacingPercent: 145000 }));
  });
  slides.push({ number: n, background: '#F7F6F1', width: 1280, height: 720, elements: els });
}

/* ---------------- Slide 15: 05-4b 이미지 설명 — 해결 ---------------- */
{
  const n = 15, ctx = '05-4 이미지 설명 보완', tag = 'IMAGE DESCRIPTION · 해결';
  const [dw, dh] = fitBox(728.89, 564.80, 520, 420);
  const dx = 1222 - dw;
  const solColW = dx - 58 - 40;
  const els = [
    ...slideBase(n, '#F7F6F1', ctx, tag),
    ...titleBlock(n, 'Qwen2.5-VL과 문맥 우선순위로 해결했습니다', ''),
    image(`diag-${n}`, [dx, 190, dw, dh], 'diagram_image.svg'),
  ];
  const sols = [
    ['모델 선택', 'Qwen2.5-VL 채택 — 여러 프리셋 모델을 같은 조건으로 비교해 한국어 안정성이 가장 우수한 모델을 선정했습니다.'],
    ['문맥 우선순위', '이미지에 직접 연결된 캡션·각주·참조를 최우선으로 쓰고, 가장 가까운 제목과 앞뒤 문맥은 보조로만 사용합니다.'],
    ['유형별 라우팅', '사진·도면·흐름도·차트마다 다른 관찰 지침을 적용해 필요한 정보만 보게 합니다.'],
    ['품질 검사', '언어·환각·반복 검사를 통과한 설명만 저장합니다.'],
  ];
  sols.forEach((s, i) => {
    const y = 198 + i * 100;
    els.push(rect(`sd-${n}-${i}`, [58, y + 5, 6, 6], COLOR.green, { radius: true }));
    els.push(text(`stt-${n}-${i}`, [78, y, solColW - 20, 24], s[0], { fontSize: 15, color: COLOR.ink, bold: true }));
    els.push(text(`st-${n}-${i}`, [78, y + 28, solColW - 20, 64], s[1], { fontSize: 13, color: COLOR.body, lineSpacingPercent: 140000 }));
  });
  slides.push({ number: n, background: '#F7F6F1', width: 1280, height: 720, elements: els });
}

/* ---------------- Slide 16: 06a 청킹 — 직렬화 ---------------- */
{
  const n = 16, ctx = '06 청킹 · 임베딩', tag = 'CHUNKING · 직렬화';
  const [dw, dh] = fitBox(670.26, 680.84, 480, 420);
  const dx = 1222 - dw;
  const textColW = dx - 58 - 40;
  const els = [
    ...slideBase(n, '#F7F6F1', ctx, tag),
    ...titleBlock(n, '계층 구조를 유지한 채 직렬화합니다', '청킹을 위해서는 계층적으로 구성된 파싱 데이터를 일직선으로 직렬화해야 합니다'),
    image(`diag-${n}`, [dx, 190, dw, dh], 'diagram_serializer.svg'),
    text(`b1-${n}`, [58, 210, textColW, 100], '텍스트·표·목록·제목은 Docling 기본 시리얼라이저를 그대로 사용합니다.', { fontSize: 16, color: COLOR.body, lineSpacingPercent: 145000 }),
    text(`b2-${n}`, [58, 330, textColW, 160], '그림만 커스텀 시리얼라이저를 따로 만들었습니다. 승인된 VLM 설명이 있으면 그 설명 텍스트만 임베딩 대상으로 쓰고, 설명이 없는 경우에만 Docling 기본 그림·메타데이터 시리얼라이저로 대체합니다.', { fontSize: 16, color: COLOR.body, lineSpacingPercent: 145000 }),
  ];
  slides.push({ number: n, background: '#F7F6F1', width: 1280, height: 720, elements: els });
}

/* ---------------- Slide 17: 06b 청킹 — 임베딩 ---------------- */
{
  const n = 17, ctx = '06 청킹 · 임베딩', tag = 'CHUNKING · 임베딩';
  const [ew, eh] = fitBox(1047.79, 77.4, 1160, 110);
  const els = [
    ...slideBase(n, '#F7F6F1', ctx, tag),
    ...titleBlock(n, 'EmbeddingGemma로 토큰을 계산하고 임베딩합니다', '자르는 기준과 임베딩 기준이 같아야 상한이 의미를 가집니다'),
    image(`imge-${n}`, [58, 210, ew, eh], 'diagram_embedding.svg'),
  ];
  const statY = 210 + eh + 56;
  const stats = [
    ['google/embeddinggemma-300m', '임베딩 모델'],
    ['768차원', '임베딩 벡터 크기'],
    ['512 토큰', '청크 상한 (모델 최대 입력 2,048토큰 중 보수적으로 설정)'],
  ];
  const colW = 1160 / 3;
  stats.forEach((s, i) => {
    const x = 58 + i * colW;
    els.push(text(`sv-${n}-${i}`, [x, statY, colW - 24, 30], s[0], { fontSize: 20, color: COLOR.blue, bold: true }));
    els.push(text(`sl-${n}-${i}`, [x, statY + 36, colW - 24, 44], s[1], { fontSize: 13, color: COLOR.muted, lineSpacingPercent: 135000 }));
  });
  els.push(text(`note-${n}`, [58, statY + 116, 1160, 24], '토큰 계산에도 임베딩과 같은 모델의 tokenizer를 사용합니다 — 자를 때와 임베딩할 때 기준이 다르면 상한이 무의미해지기 때문입니다.', { fontSize: 13, color: COLOR.faint }));
  slides.push({ number: n, background: '#F7F6F1', width: 1280, height: 720, elements: els });
}

/* ---------------- Slide 18: Closing ---------------- */
slides.push({
  number: 18, background: '#071426', width: 1280, height: 720,
  elements: [
    rect('c1-accent', [0, 0, 1280, 6], COLOR.accentYellow),
    text('c1-title', [120, 300, 1044, 80], '감사합니다', { fontSize: 48, color: '#F4F8FF', bold: true }),
    text('c1-sub', [120, 380, 900, 40], 'wonbin · 도클링 파싱 파이프라인', { fontSize: 16, color: '#9FB3D6' }),
  ],
});

const out = `window.WONBIN_DECK = ${JSON.stringify({ slides }, null, 0)};\n`;
fs.writeFileSync(path.join(__dirname, 'deck-data.js'), out, 'utf-8');
console.log('wrote deck-data.js with', slides.length, 'slides');
