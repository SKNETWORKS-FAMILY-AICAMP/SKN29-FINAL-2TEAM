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
for (const f of ['deck-data.js', 'wonbin-deck-data.js', 'ops-4pages-data.js', 'agent-v2-eval-data.js', 'agent-v2-lifecycle-data.js', 'content-updates.js']) {
  vm.runInContext(fs.readFileSync(path.join(dir, f), 'utf8'), ctx);
}
const slides = ctx.window.HALIL_DECK.slides;
const norm = (v) => String(v || '').replace(/\s+/g, ' ').trim();
const sig = (sl) => norm((sl.elements.find((e) => /^(signal-label-|section-)/.test(e.name || '') && norm(e.text)) || {}).text);
const sigOf = (n) => sig(slides[n - 1]);
const titleOf = (n) => norm((slides[n - 1].elements.find((e) => /^(title-|div-title-)/.test(e.name || '') && norm(e.text)) || {}).text);
const allTitles = new Set(slides.map((_, i) => titleOf(i + 1)));
const has = (t) => allTitles.has(norm(t));

// --- 전체 규모 ---
assert.equal(slides.length, 46, '48 − 패스7 삭제 2장 = 46장');
assert.deepEqual(
  Array.from(slides, (s) => s.number),
  Array.from({ length: 46 }, (_, i) => i + 1),
  '재배치 후 번호는 1~46 연속',
);
assert.equal(slides.filter((s) => s.elements.some((e) => e.kind === 'html')).length, 0, 'iframe 슬라이드는 없어야 한다');

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

// --- 패스2 합치기 결과 제목 존재 ---
for (const t of [
  '시장은 AX로 가고 있지만, 두 가지 문제가 발목을 잡습니다',
  '두 문제를 HALIL은 이렇게 해결하려 했습니다',
  '206개 문서로 검증해 보니, Docling만으로는 부족했습니다',
  '계층 구조를 유지해 직렬화하고 EmbeddingGemma로 임베딩합니다',
]) assert.ok(has(t), `합치기 결과 제목이 없음: ${t}`);

// --- 패스3: 5·6p 순서 교체 ---
assert.equal(titleOf(4), '시장은 AX로 가고 있지만, 두 가지 문제가 발목을 잡습니다', '4는 시장+문제');
assert.equal(titleOf(5), '두 문제를 HALIL은 이렇게 해결하려 했습니다', '5는 HALIL 해결 (구 6p)');
assert.equal(titleOf(6), '먼저 나선 서비스들은 같은 방향으로 수렴합니다', '6은 선도 서비스 (구 5p)');

// --- 04장 진입: 챕터 표지 → 시연 영상 → 시스템 구조 재노출 ---
assert.equal(titleOf(12), '프로젝트 수행 결과', '12는 04 챕터 표지');
assert.ok(slides[12].elements.some((e) => e.kind === 'video' && /시연영상/.test(e.media || '')), '13은 시연 영상');
assert.equal(titleOf(14), 'UI부터 실행·통제까지 연결된 시스템 구조', '14는 시스템 구조 상세(이미지) 재노출');
// 패스12: 11p(03장)은 네이티브 단순화 개요, 14p(04장)은 상세 이미지 — 제목·구성이 다르다.
assert.equal(titleOf(11), '화면·실행·검색·검증을 하나의 흐름으로', '11은 시스템 구조 단순화 개요');
assert.ok(slides[10].elements.some((e) => e.name === 'arc11-z0'), '11은 네이티브 단순화 다이어그램(arc11-*)');
assert.ok(!slides[10].elements.some((e) => e.name === 'architecture-diagram'), '11에 상세 이미지는 없다');
assert.ok(slides[13].elements.some((e) => e.name === 'architecture-diagram'), '14는 상세 아키텍처 이미지 유지');

// --- Agent 상세 3장 (패스11: 섹션 라벨 한글화) ---
assert.deepEqual([15, 16, 17].map(sigOf), ['에이전트 생애주기', '에이전트 하네스', '에이전트 런타임'], '15~17 Agent 상세');
assert.equal(titleOf(15), '에이전트 생성과 사용자 질의 요청', '15는 agent_v2 16p로 교체됨');

// --- 원빈 파싱: 18~31 (패스11: context 헤더를 halil 04로 통일) ---
const wonbin = slides.slice(17, 31);
assert.equal(wonbin.length, 14, '18~31이 원빈 파싱 14장');
wonbin.forEach((s, i) => {
  const c = s.elements.find((e) => /^context-/.test(e.name || ''));
  assert.ok((c?.text || '').includes('04 프로젝트 수행 결과'), `원빈 ${18 + i}장 컨텍스트 헤더는 halil 04로 통일`);
});

// --- 표 게이트 수치 %  ---
(() => {
  const s = slides.find((_, i) => titleOf(i + 1) === '표로 오인식된 비표 사례');
  assert.ok(s, '표 게이트 사례 슬라이드 존재');
  const vals = s.elements.filter((e) => /^sv-12-/.test(e.name || '')).map((e) => norm(e.text)).join(' · ');
  assert.equal(vals, '100% · 0.46% · 0%', '표 게이트 대표 수치는 %');
})();

// --- 패스6: 빈 '플랫폼 평가' 자리표시자가 agent_v2 평가 7장으로 교체됨 ---
assert.ok(
  !slides.some((s) => s.elements.some((e) => e.name === 'title-48')),
  '빈 플랫폼 평가 자리표시자(title-48)는 더 이상 없어야 한다',
);
assert.deepEqual(
  [32, 33, 34, 35, 36, 37, 38].map(sigOf),
  ['판정 계층', '플랫폼 평가', '스모크 테스트 · V1', 'V2 기준선', '시나리오 맵', '평가 결과', 'V3 실패 분석'],
  '32~38은 agent_v2 평가 섹션 7장 (패스11: 라벨 한글화)',
);
assert.ok(slides.slice(31, 38).every((s) => {
  const c = s.elements.find((e) => /^context-/.test(e.name || ''));
  return (c?.text || '').includes('04 프로젝트 수행 결과');
}), '평가 7장 context 헤더는 04 프로젝트 수행 결과');

// --- 꼬리(패스7 이후): DEMO RESULT → 지훈 '스킬 사용 전후 비교' 1장 → 운영 콘솔 4장 → 자체 평가 표지 → 클로징 ---
assert.ok(!has('사용자 편의 기능'), "'사용자 편의 기능' 표지는 삭제됨");
assert.ok(!slides.some((s) => s.elements.some((e) => e.name === 'jihun-skill-eval')), "지훈 '등록 검증' 이미지 슬라이드는 삭제됨");
assert.equal(sigOf(39), '시연 결과', '39는 시연 결과 (패스11: 라벨 한글화)');
// 패스9: 40p는 네이티브 재구성 (표는 잘라낸 이미지로만 유지)
assert.equal(titleOf(40), '스킬 사용 전후 비교', '40은 스킬 사용 전후 비교 (네이티브)');
assert.equal(sigOf(40), '스킬 사용 비교', '40 섹션 라벨 (패스11: 한글화)');
assert.equal(
  (slides[39].elements.find((e) => e.name === 'sc-table') || {}).media, 'skill-compare-table.png',
  '40은 잘라낸 표 이미지를 프레임 안에 배치',
);
assert.ok(
  !slides[39].elements.some((e) => e.name === 'jihun-skill-compare'),
  '40에 풀블리드 원본 이미지는 없어야 한다',
);
assert.ok(slides[39].elements.some((e) => e.name === 'title-40' && norm(e.text) === '스킬 사용 전후 비교'), '40 타이틀 요소');
assert.deepEqual(
  [41, 42, 43, 44].map(titleOf),
  ['운영 상태 통합 관리', '연결 서비스·모델 구성', '커스텀 도구·가드레일 관리', '실행 현황·도구 사용 추적'],
  '41~44는 운영 콘솔 4장',
);
assert.deepEqual([41, 42, 43, 44].map(sigOf), ['플랫폼 운영', '연결 환경', '실행 통제', '운영 모니터링'], '41~44 운영 콘솔 섹션 라벨');
assert.equal(titleOf(45), '자체 평가 의견', '45는 05 챕터 표지');
assert.ok(slides[45].elements.some((e) => (e.text || '').includes('Q&A')), '46은 클로징/Q&A 슬라이드');

// --- 이미지·비디오 참조 파일이 폴더 안에서 해결되는가 ---
const missing = [];
slides.forEach((s, i) => s.elements.forEach((e) => {
  if (e.kind !== 'image' && e.kind !== 'video') return;
  const rel = e.kind === 'image' ? path.join('media', e.media) : e.media;
  if (!fs.existsSync(path.resolve(dir, rel))) missing.push(`${i + 1}장 ${e.media}`);
}));
assert.deepEqual(missing, [], `누락 에셋 없음 (누락: ${missing.join(', ')})`);

console.log(`ok — 통합 덱 ${slides.length}장, 이미지·영상 참조 전부 해결, iframe 0`);
