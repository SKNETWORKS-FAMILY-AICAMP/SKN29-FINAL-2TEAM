import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'file:///C:/Users/Playdata/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs';

const currentDir = path.dirname(fileURLToPath(import.meta.url));
const presentationRoot = path.resolve(currentDir, '..');

const mimeTypes = {
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.png': 'image/png',
};

const server = http.createServer(async (request, response) => {
  try {
    const pathname = decodeURIComponent(new URL(request.url, 'http://127.0.0.1').pathname);
    const filePath = path.resolve(presentationRoot, `.${pathname}`);
    if (!filePath.startsWith(presentationRoot + path.sep)) throw new Error('invalid path');

    if (
      pathname.endsWith('/Jihun_발표준비/halil_eval_deck.html')
      || pathname.endsWith('/Jihun_발표준비/deep_agent_deck.html')
    ) {
      await new Promise((resolve) => setTimeout(resolve, 700));
    }

    let body = await fs.readFile(filePath);
    const requestUrl = new URL(request.url, 'http://127.0.0.1');
    if (
      pathname.endsWith('/Jihun_발표준비/halil_eval_deck.html')
      && requestUrl.searchParams.get('embed') !== '9'
    ) {
      body = Buffer.from(
        body.toString()
          .replace(
            "  const initialSlide = +(location.hash.match(/slide=(\\d+)/) || [])[1] || 1;\n  let idx = Math.max(0, Math.min(total - 1, initialSlide - 1));",
            '  let idx = 0;',
          )
          .replace('  render(idx);', '  render(0);'),
      );
    }
    const contentType = pathname.endsWith('/Jihun_발표준비/deep_agent_deck.html')
      ? 'text/html'
      : mimeTypes[path.extname(filePath)] || 'application/octet-stream';
    response.writeHead(200, { 'content-type': contentType });
    response.end(body);
  } catch {
    response.writeHead(404);
    response.end('not found');
  }
});

await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
const address = server.address();
const browser = await chromium.launch({ headless: true });

try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 820 } });
  await page.goto(`http://127.0.0.1:${address.port}/halil_html/index.html#slide=16`, {
    waitUntil: 'domcontentloaded',
  });

  const frame = page.locator('#canvas iframe.html-frame');
  await frame.waitFor({ state: 'attached' });
  assert.equal(
    await frame.evaluate((element) => getComputedStyle(element).opacity),
    '0',
    '대상 페이지 적용 전에는 iframe이 보이지 않아야 한다',
  );

  await page.waitForSelector('#canvas iframe.html-frame[data-ready="true"]');
  assert.equal(
    await frame.evaluate((element) => getComputedStyle(element).opacity),
    '1',
    '대상 페이지 적용 후에는 iframe이 보여야 한다',
  );

  const innerText = await frame.contentFrame().locator('.slide.active').innerText();
  assert.match(innerText, /에이전트를 만들 때, 쿼리를 보낼 때/);

  await page.evaluate(() => {
    window.__initialEmbeddedFrame = document.querySelector('#canvas iframe.html-frame');
  });
  await page.locator('#next').click();
  await page.waitForFunction(() => document.getElementById('now').textContent === '17');
  await page.waitForSelector('#canvas iframe.html-frame[data-ready="true"]');
  assert.equal(
    await page.evaluate(() => window.__initialEmbeddedFrame === document.querySelector('#canvas iframe.html-frame')),
    true,
    'Deep Agent 구간의 연속 페이지는 같은 iframe을 재사용해야 한다',
  );
  assert.equal(await frame.contentFrame().locator('#counterNow').innerText(), '02');

  for (let slideNumber = 18; slideNumber <= 26; slideNumber += 1) {
    await page.locator('#next').click();
    await page.waitForFunction((expected) => document.getElementById('now').textContent === String(expected), slideNumber);
  }
  await page.waitForFunction(
    () => document.querySelector('#canvas iframe.html-frame')?.contentDocument?.getElementById('counterNow')?.textContent === '12',
  );
  assert.equal(await frame.contentFrame().locator('#counterNow').innerText(), '12');
  await page.evaluate(() => {
    window.__lastDeepAgentFrame = document.querySelector('#canvas iframe.html-frame');
  });
  await page.locator('#next').click();
  await page.waitForFunction(() => document.getElementById('now').textContent === '27');
  await page.waitForSelector('#canvas iframe.html-frame[data-ready="true"]');
  assert.equal(
    await page.evaluate(() => window.__lastDeepAgentFrame === document.querySelector('#canvas iframe.html-frame')),
    false,
    '다른 HTML 덱으로 넘어갈 때는 iframe을 교체해야 한다',
  );
  assert.equal(
    await page.locator('#canvas iframe.html-frame').contentFrame().locator('#counterNow').innerText(),
    '02',
  );

  await page.goto(`http://127.0.0.1:${address.port}/halil_html/index.html?appendix=1#slide=65`, { waitUntil: 'load' });
  assert.match(await page.locator('#canvas').innerText(), /부록/);
  await page.locator('#next').click();
  await page.waitForFunction(() => document.getElementById('now').textContent === '66');
  await page.waitForSelector('#canvas iframe.html-frame[data-ready="true"]');
  assert.equal(
    await page.locator('#canvas iframe.html-frame').contentFrame().locator('#counterNow').innerText(),
    '07',
  );
  await page.evaluate(() => {
    window.__appendixFrame = document.querySelector('#canvas iframe.html-frame');
  });
  await page.locator('#next').click();
  await page.waitForFunction(() => document.getElementById('now').textContent === '67');
  await page.waitForFunction(
    () => document.querySelector('#canvas iframe.html-frame')?.contentDocument?.getElementById('counterNow')?.textContent === '08',
  );
  assert.equal(
    await page.evaluate(() => window.__appendixFrame === document.querySelector('#canvas iframe.html-frame')),
    true,
  );
  assert.equal(
    await page.locator('#canvas iframe.html-frame').contentFrame().locator('#counterNow').innerText(),
    '08',
  );

  const deepAgentDirectPage = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  await deepAgentDirectPage.goto(
    `http://127.0.0.1:${address.port}/Jihun_발표준비/deep_agent_deck.html?embed=9#slide=2`,
    { waitUntil: 'load' },
  );
  assert.equal(await deepAgentDirectPage.locator('#counterNow').innerText(), '02');
  assert.match(await deepAgentDirectPage.locator('.slide.active').innerText(), /Agent Builder/);
  await deepAgentDirectPage.evaluate(() => { location.hash = 'slide=3'; });
  await deepAgentDirectPage.waitForTimeout(50);
  assert.equal(await deepAgentDirectPage.locator('#counterNow').innerText(), '03');
  await deepAgentDirectPage.evaluate(() => { location.hash = 'slide=9'; });
  await deepAgentDirectPage.waitForTimeout(50);
  const pipelineText = await deepAgentDirectPage.locator('.slide.active').innerText();
  assert.doesNotMatch(pipelineText, /승인 대기는 종료가 아니라 잠깐 멈춘 상태/);
  assert.equal(
    await deepAgentDirectPage.locator('.slide.active .pill').count(),
    0,
    '답변 완료 · 승인 대기 · 오류 결과 배지는 모두 없어야 한다',
  );
  assert.match(
    await deepAgentDirectPage.locator('.slide.active .note-card.red').innerText(),
    /가드레일 검사 실패 시/,
  );
  const activeSlideBox = await deepAgentDirectPage.locator('.slide.active').boundingBox();
  const resultGridBox = await deepAgentDirectPage.locator('.slide.active .result-grid').boundingBox();
  const guardrailBox = await deepAgentDirectPage.locator('.slide.active .note-card.red').boundingBox();
  assert.ok(guardrailBox.width < resultGridBox.width / 2, '가드레일 안내는 원래의 왼쪽 열 너비로 복원되어야 한다');
  assert.ok(guardrailBox.y + guardrailBox.height <= activeSlideBox.y + activeSlideBox.height, '가드레일 안내가 슬라이드 밖으로 잘리면 안 된다');
  await deepAgentDirectPage.evaluate(() => { location.hash = 'slide=10'; });
  await deepAgentDirectPage.waitForTimeout(50);
  const architectureSlide = deepAgentDirectPage.locator('.slide.active');
  const architectureImage = architectureSlide.locator('img.architecture-image');
  assert.equal(await architectureImage.count(), 1, 'Deep Agent Architecture 페이지는 제공 이미지 한 장만 표시해야 한다');
  assert.equal(await architectureSlide.locator('.eyebrow').count(), 1, '상단 소제목 영역이 보여야 한다');
  assert.equal(await architectureSlide.locator('.eyebrow').innerText(), '에이전트 파트 · Agent Runtime', '상단 소제목이 보여야 한다');
  assert.equal(await architectureSlide.locator('.title').innerText(), 'Deep Agent Architecture', '대제목이 보여야 한다');
  assert.equal(await architectureSlide.locator('.hr').count(), 1, '제목 아래 구분선이 보여야 한다');
  assert.equal(await architectureSlide.locator('.subtitle, .mermaid-wrap, .note-panel').count(), 0, '부제목·기존 다이어그램·발표 메모는 없어야 한다');
  assert.equal(await architectureImage.evaluate((image) => image.complete && image.naturalWidth === 4960 && image.naturalHeight === 2588), true, '제공된 원본 이미지가 정상 로드되어야 한다');
  const architectureSlideBox = await architectureSlide.boundingBox();
  const architectureImageBox = await architectureImage.boundingBox();
  const architectureDividerBox = await architectureSlide.locator('.hr').boundingBox();
  assert.ok(architectureImageBox.y >= architectureDividerBox.y + architectureDividerBox.height, '이미지는 제목 구분선 아래에 배치되어야 한다');
  assert.ok(architectureImageBox.x >= architectureSlideBox.x && architectureImageBox.y >= architectureSlideBox.y, '이미지 시작점이 슬라이드 밖으로 나가면 안 된다');
  assert.ok(architectureImageBox.x + architectureImageBox.width <= architectureSlideBox.x + architectureSlideBox.width, '이미지 오른쪽이 잘리면 안 된다');
  assert.ok(architectureImageBox.y + architectureImageBox.height <= architectureSlideBox.y + architectureSlideBox.height, '이미지 아래쪽이 잘리면 안 된다');
  await deepAgentDirectPage.evaluate(() => { location.hash = 'slide=13'; });
  await deepAgentDirectPage.waitForTimeout(50);
  const harnessSlide = deepAgentDirectPage.locator('.slide.active');
  const harnessText = await harnessSlide.innerText();
  assert.match(harnessText, /Deep Agent는 에이전트 실행 하네스다/);
  assert.match(harnessText, /도구를 붙인다/);
  assert.match(harnessText, /서브에이전트를 붙인다/);
  assert.match(harnessText, /실행 그래프 재조립/);
  assert.match(harnessText, /코드적으로 그래프에 반영/);
  assert.match(harnessText, /우리는 Deep Agent 하네스 위에 제품을 얹었다/);
  const harnessSlideBox = await harnessSlide.boundingBox();
  const harnessInnerBox = await harnessSlide.locator('.slide-inner').boundingBox();
  assert.ok(harnessInnerBox.y + harnessInnerBox.height <= harnessSlideBox.y + harnessSlideBox.height, '하네스 설명이 슬라이드 아래로 잘리면 안 된다');
  await deepAgentDirectPage.close();

  const directPage = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  await directPage.addInitScript(() => {
    window.__activeSlidesSeen = [];
    const recordActiveSlide = () => {
      const slides = Array.from(document.querySelectorAll('.slide'));
      const activeIndex = slides.findIndex((slide) => slide.classList.contains('active'));
      const activeSlide = activeIndex + 1;
      const history = window.__activeSlidesSeen;
      if (activeSlide > 0 && history.at(-1) !== activeSlide) history.push(activeSlide);
    };
    new MutationObserver(recordActiveSlide).observe(document, {
      attributes: true,
      attributeFilter: ['class'],
      childList: true,
      subtree: true,
    });
  });
  await directPage.goto(
    `http://127.0.0.1:${address.port}/Jihun_발표준비/halil_eval_deck.html?embed=9#slide=2`,
    { waitUntil: 'load' },
  );
  assert.equal(
    await directPage.locator('#counterNow').innerText(),
    '02',
    '원본 페이지는 #slide 주소를 처음 표시 장으로 사용해야 한다',
  );
  assert.match(await directPage.locator('.slide.active').innerText(), /평가는 세 단계로 발전했다/);
  assert.deepEqual(
    await directPage.evaluate(() => window.__activeSlidesSeen),
    [2],
    '대상 페이지가 표시되기 전에 원본 1번이 활성화되면 안 된다',
  );
  await directPage.evaluate(() => { location.hash = 'slide=3'; });
  await directPage.waitForTimeout(50);
  assert.equal(
    await directPage.locator('#counterNow').innerText(),
    '03',
    '원본 페이지는 #slide 변경을 재로딩 없이 반영해야 한다',
  );
  await directPage.close();
  console.log('iframe first-slide flash: ok');
} finally {
  await browser.close();
  await new Promise((resolve) => server.close(resolve));
}
