import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

// halil_html_통합 = base(halil_html) + 지훈 Agent·Skill + 원빈 파싱·청킹·임베딩 (전부 네이티브).
// 패스1: 삭제 20장 + 49p → 빈 '플랫폼 평가'.
// 패스2: 합치기·문구 수정 (지훈 presentation.html "플랫폼 평가" 이관은 제외) → 45장.
// 패스3: 5·6p 순서 교체, 34~40p·43·44p 삭제 (스킬 3장 + 운영·보안·확장 + 시연 흐름 + 향후 과제·자체 평가) → 36장.
// 패스4: 지훈 presentation.html 49·50p("등록 검증"·"스킬 사용 전후 비교")를 DEMO RESULT 뒤에 이미지로 추가 → 38장.
// 패스5: halil_html_ops_4pages(운영 콘솔 4장)를 "스킬 사용 전후 비교" 뒤에 네이티브로 추가 → 42장.
// 패스6: halil_html_agent_v2 21~27p(평가 섹션 7장)로 빈 '플랫폼 평가' 자리표시자를 교체 → 48장.
// 패스7: '사용자 편의 기능' 챕터 표지 + 지훈 '등록 검증' 이미지 슬라이드 삭제 → 46장.
// 패스8: 15p(CORE TECHNOLOGY 전환)를 agent_v2 16p(AGENT LIFECYCLE)로 교체.
// 패스9: 40p('스킬 사용 전후 비교' 풀블리드 이미지)를 통합 디자인 네이티브 슬라이드로 재구성 (표 영역만 이미지로 유지).

const dir = path.dirname(fileURLToPath(import.meta.url));
const ctx = vm.createContext({ window: {}, console });
for (const f of ['deck-data.js', 'wonbin-deck-data.js', 'ops-4pages-data.js', 'agent-v2-eval-data.js', 'agent-v2-lifecycle-data.js', 'juyeon-slides.js', 'juneok-overview.js', 'docling20.js', 'content-updates.js']) {
  vm.runInContext(fs.readFileSync(path.join(dir, f), 'utf8'), ctx);
}
const slides = ctx.window.HALIL_DECK.slides;
const norm = (v) => String(v || '').replace(/\s+/g, ' ').trim();
const sig = (sl) => norm((sl.elements.find((e) => /^(signal-label-|section-)/.test(e.name || '') && norm(e.text)) || {}).text);
const sigOf = (n) => sig(slides[n - 1]);
const titleOf = (n) => norm((slides[n - 1].elements.find((e) => /^(title-|div-title-)/.test(e.name || '') && norm(e.text)) || {}).text);
const allTitles = new Set(slides.map((_, i) => titleOf(i + 1)));
const has = (t) => allTitles.has(norm(t));

// --- 전체 규모 --- (51 + 부록 A 8장 = 59장)
assert.equal(slides.length, 60, '51 + 부록 A 8장 + 핵심 과제→HALIL 해결 1장 = 60장');
assert.deepEqual(
  Array.from(slides, (s) => s.number),
  Array.from({ length: 60 }, (_, i) => i + 1),
  '재배치 후 번호는 1~60 연속',
);
assert.ok(!slides.some((_, i) => titleOf(i + 1) === '이미지 설명의 세 문제'), '29p(세 문제)는 삭제됨');
assert.ok(!slides.some((_, i) => titleOf(i + 1) === '전체 기능 시연 영상'), "'전체 기능 시연 영상'은 삭제됨");
// 패스17: 20p 만 kind:'html'(in-document 주입, iframe 아님) 1개 허용.
(() => {
  const htmlSlides = slides.filter((s) => s.elements.some((e) => e.kind === 'html'));
  assert.equal(htmlSlides.length, 1, 'kind:html 슬라이드는 20p 하나뿐');
  const s = htmlSlides[0];
  assert.equal(titleOf(slides.indexOf(s) + 1), '문서를 읽기 순서와 요소별 구조로 저장합니다', '20p 는 DoclingDocument 인터랙티브');
  assert.ok(s.doclingInteractive === true && s.elements.some((e) => e.name === 'dl20'), '20p 에 dl20 요소 + doclingInteractive 플래그');
  assert.ok(s.elements.some((e) => /^context-/.test(e.name || '')) && s.elements.some((e) => /^ctx-logo/.test(e.name || '')), '20p 크롬(context·로고) 유지');
})();

// --- 사라져야 하는 원본 제목 (패스1·2·3 누적) ---
for (const t of [
  '배포 구성', 'Deep Agent는 계획·위임·기억을 하나의 실행 루프로 연결합니다',
  '새 Agent는 정의·연결·버전 저장을 거쳐 Graph에 조립됩니다', 'Query는 Graph 조립부터 근거 응답까지 통제된 순서로 실행됩니다',
  '에이전트 생성 파이프라인', '실행 과정을 숨기지 않고 단계별로 보여줍니다', 'Versioning은 개발·검증·운영 설정을 분리합니다',
  '쓰기 호출별 승인·편집·거절', '쓰기 전에 멈추고, 같은 작업은 한 번만 실행합니다', '기준 문서가 프로젝트의 검색 범위를 결정합니다',
  'Docling을 선택했지만, 비정형 PDF는 그대로 쓰기 어려웠습니다', 'Docling 기본 결과를 단계별 게이트로 보정합니다',
  '읽기 순서 보정은 문서 구조를 실제 순서로 복원합니다', '이미지는 설명과 메타데이터로 검색 문맥에 연결합니다',
  '평가는 기준선을 쌓고 실패를 다음 실행에 반영했습니다', '성공률보다 실패 원인이 다음 개선점을 만들었습니다',
  'Skill은 명시적으로 호출하고, 검증된 절차만 재사용합니다', '자연어 한 문장으로 Skill 초안을 시작합니다',
  '검증된 Skill은 개인·팀 카탈로그에서 관리합니다', '현재 동작과 다음 개선을 분리해 설명합니다',
  '기업 업무의 두 가지 문제에 주목했습니다', '정보는 연결, 업무 방식은 스킬로',
  '요청 도착부터 실행까지 파이프라인', '문서 파싱 결과에서 확인된 네 가지 문제',
  'EmbeddingGemma로 토큰을 계산하고 임베딩합니다', 'AX 흐름에서 시작한 HALIL',
  'AI Agent 도입은 늘지만, 실제 업무 적용은 아직 초기입니다', '206개 문서로 파싱 정확도를 검증했습니다',
  // 패스3
  '검증한 Skill만 등록해 반복 업무에 재사용', '필요한 요청과 불필요한 요청을 검증한 뒤 등록',
  '개인이 만든 업무 방식을 팀이 같은 절차로 실행', '운영 정책과 실행 이력을 제품과 분리해 관리합니다',
  '제품과 운영의 통제 경계', '연동과 확장 지점', '시연은 구성·근거·승인의 한 흐름으로 진행합니다',
  '다음 단계는 근거 정밀도·라우팅·운영 검증입니다', '강점은 연결성, 남은 과제는 검증 범위입니다',
]) assert.ok(!has(t), `사라져야 하는 제목이 남아 있음: ${t}`);

// --- 패스2 합치기 + 패스14 축약 제목 존재 ---
for (const t of [
  'AI Agent 도입과 업무 확장',
  'AI Agent 시장과 선도 서비스',
  '검증 결과, Docling의 한계',
  '직렬화와 임베딩',
]) assert.ok(has(t), `합치기 결과 제목이 없음: ${t}`);

// --- 패스10.6: 개요 4·5·6p 를 juneok(프로젝트개요_v4) 재설계 본문으로 교체 ---
assert.equal(titleOf(4), 'AI Agent 도입과 업무 확장', '4는 도입·업무 확장 (juneok)');
assert.equal(titleOf(5), 'AI Agent 시장과 선도 서비스', '5는 시장·선도 서비스 (juneok)');
assert.equal(titleOf(6), '기업 Agent 플랫폼, HALIL', '6은 플랫폼 방향 (juneok)');

// --- 04장 진입: 챕터 표지 → 시연 영상(표준 크롬) → 시스템 구조 재노출 ---
assert.equal(titleOf(12), '프로젝트 수행 결과', '12는 04 챕터 표지');
assert.ok(slides[12].elements.some((e) => e.kind === 'video' && /시연영상/.test(e.media || '')), '13은 시연 영상');
assert.equal(titleOf(13), '플랫폼 시연 영상', '13은 표준 크롬 + 영상 (문구 삭제)');
assert.ok(!slides[12].elements.some((e) => e.name === 'demo2-title'), '13에 옛 demo2-title 문구는 없어야 한다');
assert.equal(titleOf(14), '전체 시스템 구조', '14는 시스템 구조 상세(이미지) 재노출');
// --- 패스31: 04장 서브 표지 4장 (04-1~04-4) ---
assert.deepEqual([15, 19, 34, 43].map(titleOf), ['Agent', '문서 처리', '플랫폼 평가', '운영자 콘솔'], '15·19·34·43은 04-1~04-4 서브 표지');
assert.deepEqual(
  [15, 19, 34, 43].map((n) => norm(slides[n - 1].elements.find((e) => /^div-no-/.test(e.name || '')).text)),
  ['04-1', '04-2', '04-3', '04-4'],
  '서브 표지 번호는 04-1~04-4',
);
// --- 패스32+34: '직렬화와 임베딩' 뒤 '문서 처리 파이프라인 평가' + 4레이어 검증 2×2 표(패스34) ---
assert.equal(titleOf(33), '문서 처리 파이프라인 평가', '33은 문서 처리 파이프라인 평가');
assert.ok(
  slides[32].elements.some((e) => e.name === 'dpe-sub') && [1, 2, 3, 4].every((q) => slides[32].elements.some((e) => e.name === `dpe${q}-pan`)),
  '33은 4개 레이어 검증 카드(dpe1~4)로 구성',
);
// 패스12: 11p(03장)은 네이티브 단순화 개요, 14p(04장)은 상세 이미지 — 제목·구성이 다르다.
assert.equal(titleOf(11), '시스템 흐름 한눈에', '11은 시스템 구조 단순화 개요');
assert.ok(slides[10].elements.some((e) => e.name === 'arc11-z0'), '11은 네이티브 단순화 다이어그램(arc11-*)');
assert.ok(!slides[10].elements.some((e) => e.name === 'architecture-diagram'), '11에 상세 이미지는 없다');
assert.ok(slides[13].elements.some((e) => e.name === 'architecture-diagram'), '14는 상세 아키텍처 이미지 유지');

// --- 패스15: 상단(section)·하단(signal 선·signal-label·foot) 라벨 전면 삭제 ---
assert.equal(
  slides.filter((s) => s.elements.some((e) => /^(section-|signal-\d|signal-label-|foot-)/.test(e.name || ''))).length,
  0, 'section·signal·signal-label·foot 라벨은 전부 삭제됨',
);

// --- Agent 상세 3장 (04-1 서브 표지 뒤) ---
assert.deepEqual([16, 17, 18].map(titleOf), ['Agent 생성과 질의 요청', 'Deep Agent Harness', 'Deep Agent 실행 구조'], '16~18 제목');

// --- 원빈 파싱: 20~32 (패스27 '세 문제' 삭제 + 패스31 서브 표지 2장 앞당김 → 13장) ---
const wonbin = slides.slice(19, 32);
assert.equal(wonbin.length, 13, '20~32가 원빈 파싱 13장');
wonbin.forEach((s, i) => {
  const c = s.elements.find((e) => /^context-/.test(e.name || ''));
  assert.ok((c?.text || '').includes('04 프로젝트 수행 결과'), `원빈 ${20 + i}장 컨텍스트 헤더는 halil 04로 통일`);
});

// --- 27p 표 오인식 사례: 합성 격자 예시로 재구성 (수치 sv-12-* 는 삭제됨) ---
(() => {
  const s = slides.find((_, i) => titleOf(i + 1) === '표 오인식 사례');
  assert.ok(s, '표 게이트 사례 슬라이드 존재');
  assert.ok(!s.elements.some((e) => /^sv-12-/.test(e.name || '')), '27p 하단 수치(sv-12-*)는 제거됨');
})();

// --- 패스6: 빈 '플랫폼 평가' 자리표시자가 agent_v2 평가 7장으로 교체됨 ---
assert.ok(
  !slides.some((s) => s.elements.some((e) => e.name === 'title-48')),
  '빈 플랫폼 평가 자리표시자(title-48)는 더 이상 없어야 한다',
);
assert.deepEqual(
  [35, 36, 37, 38, 39, 40, 41].map(titleOf),
  ['판정 체계', '플랫폼 평가', '기능 작동 평가', '평가 대상과 기준', '시나리오별 판정 초점', '시나리오 운영 평가', '운영 평가 실패 사례'],
  '35~41은 평가 섹션 7장 (04-3 서브 표지 뒤)',
);
assert.ok(slides.slice(34, 41).every((s) => {
  const c = s.elements.find((e) => /^context-/.test(e.name || ''));
  return (c?.text || '').includes('04 프로젝트 수행 결과');
}), '평가 7장 context 헤더는 04 프로젝트 수행 결과');

// --- 꼬리(패스7·29 이후): DEMO RESULT → 지훈 '스킬 사용 전후 비교' 1장 → 운영 콘솔 4장 → 자체 평가 표지 → 클로징 ---
assert.ok(!has('사용자 편의 기능'), "'사용자 편의 기능' 표지는 삭제됨");
assert.ok(!slides.some((s) => s.elements.some((e) => e.name === 'jihun-skill-eval')), "지훈 '등록 검증' 이미지 슬라이드는 삭제됨");
// 패스10.5: 42p는 juyeon 변형본의 완전 네이티브 표(sc-t-*)로 교체 (이미지 크롭 아님)
assert.equal(titleOf(42), '스킬 사용 전후 비교', '42는 스킬 사용 전후 비교 (네이티브)');
assert.ok(
  slides[41].elements.some((e) => e.name === 'sc-t-c-0-0') && slides[41].elements.some((e) => e.name === 'sc-t-tot-4'),
  '42는 juyeon 네이티브 표 셀(sc-t-*)로 구성',
);
assert.ok(
  !slides[41].elements.some((e) => e.name === 'sc-table' || e.name === 'jihun-skill-compare'),
  '42에 표 이미지(sc-table)·풀블리드 원본은 없어야 한다',
);
assert.ok(slides[41].elements.some((e) => e.name === 'title-40' && norm(e.text) === '스킬 사용 전후 비교'), '42 타이틀 요소');
assert.deepEqual(
  [44, 45, 46, 47].map(titleOf),
  ['운영 상태 통합 관리', '연결 서비스·모델 구성', '커스텀 도구·가드레일 관리', '실행 현황·도구 사용 추적'],
  '44~47은 운영 콘솔 4장 (04-4 서브 표지 뒤)',
);
assert.equal(titleOf(48), '자체 평가 의견', '48은 05 챕터 표지');
// --- 패스38: '자체 평가 의견' 뒤 "업무 확장의 핵심 과제 → HALIL의 해결" 1장 ---
assert.equal(titleOf(49), '업무 확장의 핵심 과제 → HALIL의 해결', '49는 4p 핵심 과제 3개 해결 슬라이드');
assert.ok(
  [0, 1, 2].every((c) => slides[48].elements.some((e) => e.name === `pv${c}-pan`)) && slides[48].elements.some((e) => e.name === 'pv-hl'),
  '49는 과제 3행(pv0~2) + 헤드라인(pv-hl)으로 구성',
);
assert.equal(titleOf(50), '향후 과제', '50은 개선 계획 표 (juyeon 패스30 이식)');
assert.ok(
  slides[49].elements.some((e) => e.name === 'fw-hbar') && [0, 1, 2].every((i) => slides[49].elements.some((e) => e.name === `fw-area-${i}`)),
  '50은 Future Work 표(fw-*) 3행으로 구성',
);
assert.ok(slides[50].elements.some((e) => (e.text || '').includes('Q&A')), '51은 클로징/Q&A 슬라이드');
assert.ok(slides[51].elements.some((e) => norm(e.text) === '감사합니다'), '52는 클로징 인사');
// --- 패스33: '감사합니다' 뒤 부록 A 8장 (표준 크롬 + title + .content 캡처 이미지) ---
const apxTitles = ['시스템 처리 흐름도', '그래프 조립', 'Root 반복 루프', '미들웨어가 붙는 지점',
  '보안과 가드레일', 'Todo 미들웨어', '직접 구현한 코드 — 파싱·에이전트', '직접 구현한 코드 — MCP·Tool 호출'];
for (let i = 1; i <= 8; i++) {
  const s = slides[51 + i];
  assert.equal(titleOf(52 + i), apxTitles[i - 1], `${52 + i}은 부록 A-${i} (${apxTitles[i - 1]})`);
  assert.ok(s.elements.some((e) => e.name === `apx-img-${i}` && e.media === `appendix_a_0${i}.png`), `${52 + i}에 부록 본문 이미지`);
  assert.ok(s.elements.some((e) => e.name === 'title-16') && s.elements.some((e) => /^context-/.test(e.name || '')), `${52 + i}은 표준 크롬`);
}

// --- 이미지·비디오 참조 파일이 폴더 안에서 해결되는가 ---
const missing = [];
slides.forEach((s, i) => s.elements.forEach((e) => {
  if (e.kind !== 'image' && e.kind !== 'video') return;
  const rel = e.kind === 'image' ? path.join('media', e.media) : e.media;
  if (!fs.existsSync(path.resolve(dir, rel))) missing.push(`${i + 1}장 ${e.media}`);
}));
assert.deepEqual(missing, [], `누락 에셋 없음 (누락: ${missing.join(', ')})`);

console.log(`ok — 통합 덱 ${slides.length}장, 이미지·영상 참조 전부 해결, iframe 0`);
