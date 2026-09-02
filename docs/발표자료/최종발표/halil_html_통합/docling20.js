// 20p — DoclingDocument 구조화 인터랙티브. 팀원 전달 HTML(docling_document_structure_slide.html)을
// 네이티브 덱에 in-document 로 이식. iframe·외부 스크립트(getunicorn) 없음. 존재하지 않던 그림은 CSS 패턴으로 대체.
// index.html 이 kind:'html' 요소로 markup 을 주입한 뒤 HALIL_DOCLING20.init(rootEl) 로 동작을 연결한다.
(() => {
  const CSS = `
#dl20{position:absolute;inset:0;font-family:"Pretendard","Malgun Gothic","Apple SD Gothic Neo",Arial,sans-serif;color:#101828}
#dl20 .stage{position:absolute;inset:0;display:grid;grid-template-columns:392px 372px 1fr;gap:22px;align-items:start}
#dl20 .section-label{height:22px;margin-bottom:10px;color:#667085;font-size:12px;font-weight:850;letter-spacing:.10em}
#dl20 .paper-area{position:relative;padding-left:16px}
#dl20 .paper{position:relative;width:360px;height:438px;padding:24px 26px 22px;background:#fff;border:1px solid #cbd5e1}
#dl20 .paper::before{content:"PDF · 1 PAGE";position:absolute;right:12px;top:10px;color:#98a2b3;font-size:8px;font-weight:800;letter-spacing:.12em}
#dl20 .doc-item{position:relative;border:2px solid transparent;transition:.22s ease;cursor:pointer}
#dl20 .doc-item::before{content:attr(data-order);position:absolute;left:-38px;top:50%;width:24px;height:24px;display:grid;place-items:center;border-radius:50%;background:#d0d5dd;color:#fff;font-size:12px;font-weight:900;transform:translateY(-50%);transition:.22s ease}
#dl20 .doc-item::after{content:"";position:absolute;left:-14px;top:50%;width:12px;border-top:2px solid #d0d5dd;transition:.22s ease}
#dl20 .doc-title{margin:4px 0 14px;padding:6px 8px;color:#172033;font-size:18px;font-weight:900;letter-spacing:-.04em}
#dl20 .doc-copy{margin:0 0 15px;padding:7px 8px;color:#475467;font-size:11.5px;line-height:1.6}
#dl20 .doc-copy strong{color:#155eef}
#dl20 .doc-table{margin-bottom:15px;padding:4px}
#dl20 table{width:100%;border-collapse:collapse;font-size:10.5px;text-align:center}
#dl20 th{padding:6px 4px;background:#eef4ff;color:#344054;font-weight:850;border:1px solid #b8c8e8}
#dl20 td{padding:6px 4px;color:#475467;border:1px solid #ccd5e3}
#dl20 .doc-picture{position:relative;height:104px;overflow:hidden;background:
  radial-gradient(circle at 22% 30%,#b8f34a 0 3px,transparent 4px) 0 0/24px 24px,
  radial-gradient(circle at 22% 30%,#b8f34a 0 3px,transparent 4px) 12px 12px/24px 24px,
  linear-gradient(135deg,#0891a8,#06a9c7)}
#dl20 .doc-picture .caption{position:absolute;left:0;right:0;bottom:0;padding:6px 9px;background:#101828c9;color:#fff;font-size:10px;font-weight:700}
#dl20 .doc-page{position:absolute;left:0;right:0;bottom:10px;text-align:center;color:#98a2b3;font-size:9px}
#dl20 .doc-item.active{border-color:#155eef;background:#eef4ff;box-shadow:0 0 0 4px #155eef12}
#dl20 .doc-item.active::before{background:#155eef;box-shadow:0 3px 10px #155eef38}
#dl20 .doc-item.active::after{border-color:#155eef}
#dl20 .paper.dim .doc-item:not(.active){opacity:.44}
#dl20 .paper.intro .doc-item{border-color:transparent;background:transparent;box-shadow:none;opacity:1}
#dl20 .paper.intro .doc-item::before,#dl20 .paper.intro .doc-item::after{opacity:0}
#dl20 .tree-area{position:relative}
#dl20 .code-pane{position:relative;height:438px;padding:16px 20px;border-radius:14px;background:#0c172a;color:#d7e1f3;font-family:Consolas,"Courier New",monospace;overflow:hidden}
#dl20 .tree-area.intro .code-pane>*{opacity:.12}
#dl20 .tree-area.intro .code-pane{background:#16233a}
#dl20 .intro-message{display:none;position:absolute;left:30px;right:30px;top:164px;z-index:2;color:#fff;text-align:center;font-size:21px;font-weight:900;letter-spacing:-.03em}
#dl20 .intro-message span{display:block;margin-top:9px;color:#b9c7dc;font-size:12px;font-weight:650;line-height:1.5}
#dl20 .tree-area.intro .intro-message{display:block}
#dl20 .window-bar{display:flex;align-items:center;gap:7px;margin-bottom:10px}
#dl20 .window-bar i{width:9px;height:9px;border-radius:50%}
#dl20 .window-bar i:nth-child(1){background:#ff6b6b}#dl20 .window-bar i:nth-child(2){background:#ffd166}#dl20 .window-bar i:nth-child(3){background:#34d399}
#dl20 .window-bar b{margin-left:auto;color:#8fa0bd;font:10px/1.2 "Malgun Gothic",sans-serif}
#dl20 .schema{margin-bottom:10px;color:#b8f34a;font-size:13.5px;font-weight:800}
#dl20 .tree-key{margin-bottom:6px;color:#c9bbff;font-size:12.5px;font-weight:800}
#dl20 .refs{margin-left:8px;padding-left:16px;border-left:1px solid #42516d}
#dl20 .ref{position:relative;width:100%;margin:0 0 6px;padding:7px 10px;border:0;border-radius:6px;background:#15233b;color:#bac7dc;text-align:left;font:11.5px/1.4 Consolas,monospace;cursor:pointer;transition:.2s ease}
#dl20 .ref::before{content:"";position:absolute;left:-17px;top:50%;width:16px;border-top:1px solid #42516d}
#dl20 .ref b{display:inline-grid;place-items:center;width:19px;height:19px;margin-right:7px;border-radius:50%;background:#40516f;color:#fff;font-size:11px}
#dl20 .ref.active{background:#203b73;color:#fff;box-shadow:inset 3px 0 0 #7aa2ff}
#dl20 .ref.active b{background:#155eef}
#dl20 .read-flow{margin:10px 0 12px 26px;color:#c9bbff;font:750 11.5px/1.4 "Malgun Gothic",sans-serif}
#dl20 .read-flow strong{margin-right:6px;color:#fff;font:850 12px/1 Consolas,monospace}
#dl20 .arrays{padding-top:9px;border-top:1px solid #35445f}
#dl20 .array{padding:4px 0;color:#aebbd0;font-size:11.5px}
#dl20 .array .t{color:#83c5ff}#dl20 .array .tb{color:#ffc46b}#dl20 .array .p{color:#72dbea}
#dl20 .detail-area{position:relative;min-width:0}
#dl20 .detail-head{display:flex;align-items:flex-start;justify-content:space-between;padding-bottom:12px;border-bottom:2px solid #101828}
#dl20 .kind-wrap{display:flex;align-items:center;gap:10px}
#dl20 .kind-index{width:31px;height:31px;display:grid;place-items:center;border-radius:50%;background:#155eef;color:#fff;font-size:14px;font-weight:900}
#dl20 .kind-title{font-size:20px;font-weight:900;letter-spacing:-.03em}
#dl20 .kind-path{padding-top:6px;color:#98a2b3;font:11px/1.3 Consolas,monospace}
#dl20 .detail-body{padding-top:14px}
#dl20 .field{display:grid;grid-template-columns:112px 1fr;gap:12px;padding:10px 0;border-bottom:1px solid #d0d7e4}
#dl20 .field:last-child{border-bottom:0}
#dl20 .field code{color:#344054;font:750 12px/1.45 Consolas,monospace}
#dl20 .field-value{min-width:0;color:#475467;font-size:13.5px;line-height:1.46;word-break:keep-all}
#dl20 .field-value strong{color:#101828}
#dl20 .coord{display:inline-block;padding:2px 6px;background:#f2f4f7;color:#475467;font:700 11px/1.3 Consolas,monospace}
#dl20 .cell-grid{display:grid;grid-template-columns:repeat(3,1fr);margin-top:6px;border-left:1px solid #cbd5e1;border-top:1px solid #cbd5e1}
#dl20 .cell-grid span{padding:4px 3px;border-right:1px solid #cbd5e1;border-bottom:1px solid #cbd5e1;text-align:center;font-size:9.5px}
#dl20 .cell-grid span:nth-child(-n+3){background:#fff4e5;color:#9a4e00;font-weight:800}
#dl20 .enrichment{display:inline-block;margin-left:6px;padding:2px 6px;background:#e9f9fc;color:#087f8c;font-size:9.5px;font-weight:850}
#dl20 .detail-summary{margin-top:14px;padding:12px 14px;border-left:5px solid #155eef;background:linear-gradient(90deg,#eef4ff,transparent);color:#344054;font-size:13px;line-height:1.5}
#dl20 .detail-summary strong{color:#155eef}
#dl20 .fade{animation:dl20fade .24s ease-out}
@keyframes dl20fade{from{opacity:.2;transform:translateY(4px)}}
`;

  const HTML = `<div class="stage">
  <div class="paper-area">
    <div class="section-label">01 · 단순한 예시 PDF</div>
    <div class="paper" data-role="paper">
      <div class="doc-item doc-title" data-order="1" data-index="0">2026 사업 실적 요약</div>
      <div class="doc-item doc-copy" data-order="2" data-index="1">상반기 매출은 전년 대비 <strong>18% 증가</strong>했습니다.<br>AI 사업부가 전체 성장을 견인했습니다.</div>
      <div class="doc-item doc-table" data-order="3" data-index="2">
        <table aria-label="사업부별 매출 표">
          <thead><tr><th>사업부</th><th>매출</th><th>증감</th></tr></thead>
          <tbody><tr><td>AI</td><td>120억</td><td>+24%</td></tr><tr><td>Cloud</td><td>85억</td><td>+11%</td></tr></tbody>
        </table>
      </div>
      <div class="doc-item doc-picture" data-order="4" data-index="3">
        <div class="caption">그림 1 · 브랜드 그래픽 패턴</div>
      </div>
      <div class="doc-page">1</div>
    </div>
  </div>
  <div class="tree-area">
    <div class="section-label">02 · BODY가 1 → 2 → 3 → 4 순서로 연결</div>
    <div class="intro-message">문서 인식<span>PDF 페이지 전체를 먼저 읽고<br>텍스트·표·이미지 영역을 탐지합니다.</span></div>
    <div class="code-pane">
      <div class="window-bar"><i></i><i></i><i></i><b>DoclingDocument</b></div>
      <div class="schema">"schema_name": "DoclingDocument"</div>
      <div class="tree-key">"body.children" : [</div>
      <div class="refs">
        <button class="ref" data-index="0"><b>1</b>{ "$ref": "#/texts/0" }</button>
        <button class="ref" data-index="1"><b>2</b>{ "$ref": "#/texts/1" }</button>
        <button class="ref" data-index="2"><b>3</b>{ "$ref": "#/tables/0" }</button>
        <button class="ref" data-index="3"><b>4</b>{ "$ref": "#/pictures/0" }</button>
      </div>
      <div class="tree-key" style="margin-left:0">]</div>
      <div class="read-flow"><strong>1 → 2 → 3 → 4</strong> 사람이 읽는 문서 흐름</div>
      <div class="arrays">
        <div class="array"><span class="t">"texts"</span> : [ 원문 · 역할 · 페이지 · 좌표 ]</div>
        <div class="array"><span class="tb">"tables"</span> : [ 행 · 열 · 셀 · 페이지 · 좌표 ]</div>
        <div class="array"><span class="p">"pictures"</span> : [ 분류 · 설명 · 페이지 · 좌표 ]</div>
      </div>
    </div>
  </div>
  <div class="detail-area">
    <div class="section-label">03 · 선택한 요소에 저장되는 정보</div>
    <div data-role="detail"></div>
  </div>
</div>`;

  const DETAILS = [
    { type: 'TEXT', path: '#/texts/0', summary: '제목을 일반 문장이 아닌 <strong>섹션의 시작점</strong>으로 활용할 수 있습니다.', fields: [
      ['label', '<strong>section_header</strong> · 문서 요소의 역할'],
      ['text', '“2026 사업 실적 요약” · 추출된 원문'],
      ['prov.page_no', '<strong>1</strong> · 원본 페이지'],
      ['prov.bbox', '<span class="coord">[34, 50, 316, 91]</span> · 원본 좌표'],
    ] },
    { type: 'TEXT', path: '#/texts/1', summary: '본문 원문과 위치가 함께 저장되어 <strong>검색 결과를 원본 문장으로 연결</strong>할 수 있습니다.', fields: [
      ['label', '<strong>text</strong> · 일반 본문'],
      ['text', '“상반기 매출은 전년 대비 18% 증가했습니다. AI 사업부가 전체 성장을 견인했습니다.”'],
      ['prov.page_no', '<strong>1</strong> · 원본 페이지'],
      ['prov.bbox', '<span class="coord">[34, 110, 316, 171]</span> · 원본 좌표'],
    ] },
    { type: 'TABLE', path: '#/tables/0', summary: '표를 문자열로 평탄화하지 않고 <strong>행·열·셀 관계를 보존</strong>해 수치 질의에 활용합니다.', fields: [
      ['num_rows · num_cols', '<strong>3 × 3</strong> · 헤더를 포함한 표 크기'],
      ['table_cells[]', '셀별 text · row/col 위치 · span 정보<div class="cell-grid"><span>사업부</span><span>매출</span><span>증감</span><span>AI</span><span>120억</span><span>+24%</span></div>'],
      ['prov.page_no', '<strong>1</strong> · 표가 존재하는 페이지'],
      ['prov.bbox', '<span class="coord">[34, 193, 316, 306]</span> · 표 전체 좌표'],
    ] },
    { type: 'PICTURE', path: '#/pictures/0', summary: '이미지의 위치뿐 아니라 <strong>유형과 자연어 설명</strong>을 저장해 이미지도 검색 대상으로 만듭니다.', fields: [
      ['classification', '<strong>graphic</strong> · 신뢰도 0.97 <span class="enrichment">분류 옵션</span>'],
      ['description', '“청록색 배경 위에 연두색 점이 배열된 그래픽” <span class="enrichment">설명 옵션</span>'],
      ['captions', '“그림 1 · 브랜드 그래픽 패턴” · 연결 캡션'],
      ['prov', 'page_no <strong>1</strong> · <span class="coord">bbox [34, 329, 316, 495]</span>'],
    ] },
  ];

  const INTRO = `
    <div class="detail-head">
      <div class="kind-wrap"><div class="kind-index">0</div><div class="kind-title">DOCUMENT INPUT</div></div>
      <div class="kind-path">sample.pdf</div>
    </div>
    <div class="detail-body">
      <div class="field"><code>input_format</code><div class="field-value"><strong>PDF</strong> · 원본 문서 입력</div></div>
      <div class="field"><code>page_count</code><div class="field-value"><strong>1 page</strong> · 페이지 단위 인식</div></div>
      <div class="field"><code>first_step</code><div class="field-value">페이지 전체를 읽고 텍스트·표·이미지 후보 영역을 탐지</div></div>
      <div class="detail-summary">이 단계에서는 아직 번호나 구조를 표시하지 않고 <strong>원본 문서 자체를 먼저 인식</strong>합니다.</div>
    </div>`;

  // root: kind:'html' 요소가 만든 <div id="dl20">. state: -1(intro) ~ 3. onState(next) 로 상태 변경 요청.
  function init(root, state, onState) {
    const paper = root.querySelector('[data-role="paper"]');
    const treeArea = root.querySelector('.tree-area');
    const detail = root.querySelector('[data-role="detail"]');
    const items = [...root.querySelectorAll('.doc-item')];
    const refs = [...root.querySelectorAll('.ref')];

    const apply = (i) => {
      const intro = i < 0;
      paper.classList.toggle('intro', intro);
      paper.classList.toggle('dim', !intro);
      treeArea.classList.toggle('intro', intro);
      items.forEach((el, k) => el.classList.toggle('active', k === i));
      refs.forEach((el, k) => el.classList.toggle('active', k === i));
      detail.classList.remove('fade');
      void detail.offsetWidth;
      if (intro) {
        detail.innerHTML = INTRO;
      } else {
        const d = DETAILS[i];
        detail.innerHTML = `
          <div class="detail-head">
            <div class="kind-wrap"><div class="kind-index">${i + 1}</div><div class="kind-title">${d.type}</div></div>
            <div class="kind-path">${d.path}</div>
          </div>
          <div class="detail-body">
            ${d.fields.map(([k, v]) => `<div class="field"><code>${k}</code><div class="field-value">${v}</div></div>`).join('')}
            <div class="detail-summary">${d.summary}</div>
          </div>`;
      }
      detail.classList.add('fade');
    };

    [...items, ...refs].forEach((el) => el.addEventListener('click', () => onState(Number(el.dataset.index))));
    apply(state);
    return { apply, count: DETAILS.length };
  }

  window.HALIL_DOCLING20 = { CSS, HTML, init };
})();
