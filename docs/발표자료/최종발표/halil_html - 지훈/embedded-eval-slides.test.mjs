import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const deckDataPath = new URL('./deck-data.js', import.meta.url);
const contentUpdatesPath = new URL('./content-updates.js', import.meta.url);

const context = vm.createContext({ window: {}, console });
vm.runInContext(fs.readFileSync(deckDataPath, 'utf8'), context);
vm.runInContext(fs.readFileSync(contentUpdatesPath, 'utf8'), context);

const slides = context.window.HALIL_DECK.slides;
const deepAgentSlides = slides.slice(15, 26);
const evaluationSlides = slides.slice(26, 36);
const appendixDivider = slides[64];
const appendixSlides = slides.slice(65, 67);

assert.equal(slides.length, 67, '하네스 설명 추가 후 전체 슬라이드는 67장이어야 한다');
assert.equal(deepAgentSlides.length, 11, '16~26번에 Deep Agent 본문 11장이 있어야 한다');
assert.equal(evaluationSlides.length, 10, '27~36번에 평가 슬라이드 10장이 있어야 한다');

const expectedDeepAgentSources = [1, 2, 3, 4, 5, 6, 9, 13, 10, 11, 12];

deepAgentSlides.forEach((slide, index) => {
  const frame = slide.elements[0];
  assert.equal(frame.kind, 'html', `새 ${index + 16}번 슬라이드는 HTML 프레임이어야 한다`);
  assert.equal(frame.src, '../Jihun_발표준비/deep_agent_deck.html');
  assert.equal(frame.sourceSlide, expectedDeepAgentSources[index], 'Deep Agent 본문에서 원본 7~8번은 빠져야 한다');
});

evaluationSlides.forEach((slide, index) => {
  const frame = slide.elements[0];
  assert.equal(frame.kind, 'html', `새 ${index + 26}번 슬라이드는 HTML 프레임이어야 한다`);
  assert.equal(frame.src, '../Jihun_발표준비/halil_eval_deck.html');
  assert.equal(frame.sourceSlide, index + 2, '원본 2~11번만 순서대로 참조해야 한다');
});

assert.notEqual(slides[14].elements[0]?.kind, 'html', '15번 슬라이드는 기존 내용을 유지해야 한다');
assert.equal(slides[21].elements[0].sourceSlide, 9, '22번은 전체 요청 파이프라인을 유지해야 한다');
assert.equal(slides[22].elements[0].sourceSlide, 13, '23번은 새 하네스 설명이어야 한다');
assert.equal(slides[23].elements[0].sourceSlide, 10, '기존 Deep Agent Architecture는 24번으로 이동해야 한다');
assert.notEqual(slides[36].elements[0]?.kind, 'html', '기존 16번 슬라이드는 새 37번으로 이동해야 한다');
assert.equal(appendixDivider.elements.some((element) => element.text === '부록'), true, '65번은 부록 구분 페이지여야 한다');
assert.deepEqual(
  Array.from(appendixSlides, (slide) => slide.elements[0].sourceSlide),
  [7, 8],
  '66~67번에 기존 22~23번 슬라이드가 순서대로 와야 한다',
);
assert.deepEqual(
  Array.from(slides, (slide) => slide.number),
  Array.from({ length: 67 }, (_, index) => index + 1),
  '재배치 후 페이지 번호는 1부터 67까지 연속적이어야 한다',
);

console.log('embedded Deep Agent and evaluation slides: ok');
