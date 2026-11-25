/** Run against ./start.sh debug. Requires Playwright and an installed Chrome; no app build needed. */
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.SIDEBAR_TEST_URL || 'http://127.0.0.1:8730';
const routes = ['heatmap', 'yearly', 'detail', 'backtest', 'etf', 'etf-market', 'knowledge/value-investing'];
const tileData = { market_type: 'stock', period: 'today', data: [
  { symbol: 'AAPL', name: 'Apple', return_pct: 1.2, turnover: 2000000, price: 100 },
  { symbol: 'MSFT', name: 'Microsoft', return_pct: -0.8, turnover: 1000000, price: 150 },
] };
let scenarios = 0;
async function setup(browser, options = {}) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, ...options });
  // UI fixtures keep upstream market changes and analytics writes outside these checks.
  await context.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/config')) return route.continue();
    let json = {};
    if (path.startsWith('/api/site-config/')) json = [];
    else if (path.endsWith('/heatmap')) json = tileData;
    else if (path.endsWith('/market-pulse')) json = { markets: [] };
    else if (path.endsWith('/vix-comparison')) json = { latest_vix: 20 };
    else if (path.includes('/visits')) json = { count: 42 };
    else if (path.endsWith('/quote')) json = { quotes: [] };
    await route.fulfill({ json });
  });
  return context;
}
async function checkLayout(page, width, expectedMode = 'expanded') {
  await page.setViewportSize({ width, height: 900 });
  await page.waitForTimeout(70);
  const state = await page.evaluate(() => {
    const main = document.querySelector('main');
    const h1 = document.querySelector('h1');
    const sidebar = document.querySelector('aside');
    return {
      width: innerWidth, scrollWidth: document.documentElement.scrollWidth,
      x: main.getBoundingClientRect().left, top: h1.getBoundingClientRect().top,
      headings: document.querySelectorAll('h1').length, insideMain: main.contains(h1),
      links: sidebar.querySelectorAll('.tab-btn').length, hidden: sidebar.inert,
      mode: document.documentElement.dataset.sidebarMode,
      untranslated: /\[nav\./.test(document.body.innerText),
    };
  });
  const label = `${page.url()} @ ${width}: ${JSON.stringify(state)}`;
  assert.equal(state.headings, 1, label);
  assert.equal(state.insideMain, true, label);
  assert.equal(state.links, 13, label);
  assert.ok(state.scrollWidth <= width + 1, label);
  assert.ok(state.top >= (width <= 768 ? 56 : 0), label);
  assert.equal(state.untranslated, false, label);
  assert.equal(state.mode, expectedMode, label);
  assert.equal(state.x, width <= 768 ? 0 : { expanded: 240, compact: 64, immersive: 0 }[expectedMode], label);
  assert.equal(state.hidden, width <= 768 || expectedMode === 'immersive', label);
  scenarios++;
}
(async () => {
  const browser = await chromium.launch({ headless: true, channel: process.env.SIDEBAR_BROWSER_CHANNEL || 'chrome' });
  const errors = [];
  try {
    for (const colorScheme of ['light', 'dark']) {
      const context = await setup(browser, { colorScheme });
      const page = await context.newPage();
      page.on('pageerror', error => errors.push(error.message));
      for (const lang of ['zh', 'zh-TW', 'en']) {
        for (const route of routes) {
          const response = await page.goto(`${base}/${lang}/${route}`, { waitUntil: 'domcontentloaded' });
          assert.equal(response.status(), 200);
          assert.equal(await page.evaluate(() => document.documentElement.getAttribute('data-theme')), colorScheme === 'light' ? 'light' : null);
          for (const width of [1440, 769, 768, 390]) await checkLayout(page, width);
        }
      }
      await context.close();
    }
    const context = await setup(browser);
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    await page.setViewportSize({ width: 900, height: 900 });
    await page.goto(`${base}/zh/heatmap`, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => document.querySelector('#hmTreemapSvg').getAttribute('viewBox'));
    let requests = 0;
    page.on('request', request => { if (new URL(request.url()).pathname.endsWith('/heatmap')) requests++; });
    const viewBox = await page.locator('#hmTreemapSvg').getAttribute('viewBox');
    await page.locator('#sidebarToggle').click();
    await checkLayout(page, 900, 'compact');
    assert.notEqual(await page.locator('#hmTreemapSvg').getAttribute('viewBox'), viewBox);
    assert.equal(requests, 0, 'Sidebar reflow must use cached heatmap data');
    await page.reload({ waitUntil: 'domcontentloaded' });
    await checkLayout(page, 1440, 'compact');
    assert.ok(await page.locator('.tab-btn').first().getAttribute('title'));
    await page.locator('#sidebarToggle').click();
    await checkLayout(page, 1440, 'immersive');
    await page.locator('#sidebarRestore').click();
    await checkLayout(page, 1440);
    await page.locator('#sidebarToggle').click();
    await checkLayout(page, 390, 'compact');
    await page.locator('#mobileMenuToggle').click();
    assert.equal(await page.locator('main').evaluate(el => el.inert), true);
    assert.equal(await page.locator('#sidebarToggle').evaluate(el => el === document.activeElement), true);
    await page.keyboard.press('Shift+Tab');
    assert.equal(await page.locator('#headerSettingsBtn').evaluate(el => el === document.activeElement), true);
    await page.keyboard.press('Tab');
    assert.equal(await page.locator('#sidebarToggle').evaluate(el => el === document.activeElement), true);
    await page.locator('#headerSettingsBtn').click();
    assert.equal(new URL(page.url()).pathname, '/zh/settings');
    const box = await page.locator('#headerSettingsMenu').boundingBox();
    assert.ok(box.x >= 0 && box.y >= 0 && box.x + box.width <= 390 && box.y + box.height <= 900);
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('#headerSettingsMenu').isVisible(), false);
    assert.equal(await page.locator('#siteSidebar').evaluate(el => el.inert), false);
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('#mobileMenuToggle').evaluate(el => el === document.activeElement), true);
    assert.equal(await page.locator('main').evaluate(el => el.inert), false);
    await page.locator('#mobileMenuToggle').click();
    await page.locator('#sidebarScrim').click({ position: { x: 380, y: 500 } });
    assert.equal(await page.locator('#siteSidebar').evaluate(el => el.inert), true);
    await page.locator('#mobileMenuToggle').click();
    await page.locator('.tab-btn[data-tab="yearly"]').click();
    await page.waitForURL('**/zh/yearly');
    assert.equal(await page.locator('#siteSidebar').evaluate(el => el.inert), true);
    await page.goBack({ waitUntil: 'domcontentloaded' });
    assert.equal(new URL(page.url()).pathname, '/zh/heatmap');
    await page.goForward({ waitUntil: 'domcontentloaded' });
    assert.equal(new URL(page.url()).pathname, '/zh/yearly');
    await checkLayout(page, 1440, 'compact');
    for (const route of ['detail', 'etf-market']) {
      await page.goto(`${base}/en/${route}`, { waitUntil: 'domcontentloaded' });
      await page.locator('#headerSettingsBtn').click();
      await page.goBack();
      assert.equal(await page.locator('#headerSettingsMenu').isVisible(), false);
      await page.goForward();
      assert.equal(new URL(page.url()).pathname, '/en/settings');
      assert.equal(await page.locator('#headerSettingsMenu').isVisible(), true);
      await page.keyboard.press('Escape');
      assert.equal(new URL(page.url()).pathname, `/en/${route}`);
    }
    await page.setViewportSize({ width: 390, height: 900 });
    await page.goto(`${base}/zh/settings`, { waitUntil: 'domcontentloaded' });
    assert.equal(await page.locator('#siteSidebar').evaluate(el => el.inert), false);
    assert.equal(await page.locator('#headerSettingsMenu').isVisible(), true);
    await context.close();
    const blocked = await setup(browser);
    await blocked.addInitScript(() => {
      Object.defineProperty(window, 'localStorage', { get() { throw new DOMException('Storage blocked', 'SecurityError'); } });
    });
    const blockedPage = await blocked.newPage();
    blockedPage.on('pageerror', error => errors.push(error.message));
    await blockedPage.goto(`${base}/en/yearly`, { waitUntil: 'domcontentloaded' });
    await blockedPage.locator('#sidebarToggle').click();
    await checkLayout(blockedPage, 1440, 'compact');
    await blockedPage.locator('#sidebarToggle').click();
    await checkLayout(blockedPage, 1440, 'immersive');
    await blocked.close();
    assert.deepEqual(errors, [], 'Uncaught browser errors');
    console.log(`PASS: ${scenarios} responsive layouts; state persistence, cached heatmap reflow, drawer keyboard/focus, settings history, navigation, and blocked storage.`);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
