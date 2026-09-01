import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

// halil_html_통합 = base(halil_html) + 지훈 Agent·Skill + 원빈 파싱·청킹·임베딩 (전부 네이티브).
// 병존(c) 방식이므로 base 요약 장표는 그대로 두고 상세본을 각 주제 뒤에 삽입한다.

const dir = path.dirname(fileURLToPath(import.meta.url));
const ctx = vm.createContext({ window: {}, console });
for (const f of ['deck-data.js', 'wonbin-deck-data.js', 'content-updates.js']) {
  vm.runInContext(fs.readFileSync(path.join(dir, f), 'utf8'), ctx);
}
const slides = ctx.window.HALIL_DECK.slides;
const sig = (sl) => (sl.elements.find((e) => /^(signal-label-|section-)/.test(e.name || '') && (e.text || '').trim()) || {}).text?.trim() || '';
const sigOf = (n) => sig(slides[n - 1]);

// --- 전체 규모 ---
assert.equal(slides.length, 68, 'base 43 + Agent 5 + 원빈 16 + Skill(표지1+3) 4 = 68장');
assert.deepEqual(
  Array.from(slides, (s) => s.number),
  Array.from({ length: 68 }, (_, i) => i + 1),
  '재배치 후 번호는 1~68 연속',
);

// --- iframe 미사용 (방식 B) ---
assert.equal(
  slides.filter((s) => s.elements.some((e) => e.kind === 'html')).length,
  0,
  'kind:html(iframe) 슬라이드는 없어야 한다',
);

// --- 지훈 Agent 5장: base RUNTIME 요약(16~18) 바로 뒤 ---
assert.deepEqual(
  [19, 20, 21, 22, 23].map(sigOf),
  ['AGENT LIFECYCLE', 'AGENT BUILDER', 'REQUEST PIPELINE', 'AGENT HARNESS', 'AGENT RUNTIME'],
  '19~23이 지훈 Agent 상세 5장',
);
assert.equal(sigOf(18), 'RUNTIME', '18은 기존 base 요약 장표 유지 (병존)');
assert.equal(sigOf(24), 'PRODUCT EVIDENCE', 'Agent 상세 뒤는 기존 24장(PRODUCT EVIDENCE)');

// --- 원빈 파싱·청킹·임베딩 16장: base MULTIMODAL 요약 바로 뒤 ---
assert.equal(sigOf(32), 'MULTIMODAL', '32는 기존 base 파싱 요약 유지 (병존)');
const wonbin = slides.slice(32, 48);
assert.equal(wonbin.length, 16, '33~48이 원빈 16장');
wonbin.forEach((s, i) => {
  const ctxEl = s.elements.find((e) => /^context-/.test(e.name || ''));
  assert.ok((ctxEl?.text || '').includes('wonbin'), `원빈 ${33 + i}장은 wonbin 컨텍스트 헤더를 가진다 (헤더 통일은 후속 편집)`);
});
assert.ok(/청킹|임베딩|CHUNK|EMBED/i.test(JSON.stringify(slides[47].elements)), '48장은 청킹·임베딩');
assert.equal(sigOf(49), 'EVALUATION PLAN', '원빈 상세 뒤는 기존 EVALUATION PLAN');

// --- 지훈 Skill 표지+3장: base SKILL STATUS 요약 바로 뒤 ---
assert.equal(sigOf(55), 'SKILL STATUS', '55는 기존 base 스킬 요약 유지 (병존)');
assert.ok(
  slides[55].elements.some((e) => (e.text || '').includes('사용자 편의 기능')),
  '56은 사용자 편의 기능 섹션 표지',
);
assert.deepEqual([57, 58, 59].map(sigOf), ['SKILL', 'SKILL PROCESS', 'TEAM SKILL'], '57~59가 지훈 스킬 상세 3장');

// --- 모든 이미지·비디오 참조 파일이 폴더 안에서 해결되는가 ---
const missing = [];
slides.forEach((s, i) => s.elements.forEach((e) => {
  if (e.kind !== 'image' && e.kind !== 'video') return;
  const rel = e.kind === 'image' ? path.join('media', e.media) : e.media;
  if (!fs.existsSync(path.resolve(dir, rel))) missing.push(`${i + 1}장 ${e.media}`);
}));
assert.deepEqual(missing, [], `누락 에셋 없음 (누락: ${missing.join(', ')})`);

console.log(`ok — 통합 덱 ${slides.length}장, 이미지 참조 전부 해결, iframe 0`);
