// Add to home screen: Chrome sees an installable app, the service worker opens /demo with no
// signal (and never serves /api/ from its cache), and the link shows the right steps per browser.
// Needs the local server on :8765.
const puppeteer = require('puppeteer-core');
const BASE = 'http://localhost:8765';
let fails = 0;
const check = (ok, name, extra = '') => { if (!ok) fails++; console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${extra ? ' — ' + extra : ''}`); };

const UAS = {
  duckduckgo: ['Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/129.0 Mobile DuckDuckGo/5 Safari/537.36', 'Add to Home Screen'],
  firefox: ['Mozilla/5.0 (Android 14; Mobile; rv:131.0) Gecko/131.0 Firefox/131.0', 'Add app to Home screen'],
  iphone: ['Mozilla/5.0 (iPhone; CPU iPhone OS 27_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/27.0 Mobile/15E148 Safari/604.1', 'Open as Web App'],
  'iphone-chrome': ['Mozilla/5.0 (iPhone; CPU iPhone OS 27_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/140.0 Mobile/15E148 Safari/604.1', 'address bar'],
  chrome: ['Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Mobile Safari/537.36', 'Install app'],
};

(async () => {
  const browser = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: 'new' });
  const page = await browser.newPage();
  const cdp = await page.createCDPSession();

  await page.goto(`${BASE}/demo`, { waitUntil: 'networkidle0' });
  const { errors: manifestErrors } = await cdp.send('Page.getAppManifest');
  check(manifestErrors.length === 0, 'manifest parses with no errors', JSON.stringify(manifestErrors));
  await page.waitForFunction(() => navigator.serviceWorker.controller || navigator.serviceWorker.ready.then(() => true), { timeout: 10000 });
  await page.reload({ waitUntil: 'networkidle0' });
  check(await page.evaluate(() => !!navigator.serviceWorker.controller), 'service worker controls the page');
  const { installabilityErrors } = await cdp.send('Page.getInstallabilityErrors');
  check(installabilityErrors.length === 0, 'Chrome says the app is installable', JSON.stringify(installabilityErrors));
  // Chrome made its install offer, so the link is there and opens Chrome's own install dialog
  check(await page.$eval('#install', (el) => !el.hidden), 'Chrome install offer: link shown');

  // No signal: page and the SW both offline
  await page.setOfflineMode(true);
  const sw = await browser.waitForTarget((t) => t.type() === 'service_worker');
  const swCdp = await sw.createCDPSession();
  await swCdp.send('Network.enable');
  await swCdp.send('Network.emulateNetworkConditions', { offline: true, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });
  await page.reload({ waitUntil: 'domcontentloaded' });
  check((await page.$eval('.brand', (el) => el.textContent)) === 'NightAgent', 'offline: /demo opens from the saved copy');
  const api = await page.evaluate(() => fetch('/api/tickets').then(() => 'answered', () => 'failed'));
  check(api === 'failed', 'offline: /api/ is never answered from the cache');
  const cached = await page.evaluate(async () => (await caches.keys()).length ? (await (await caches.open((await caches.keys())[0])).keys()).map((r) => new URL(r.url).pathname) : []);
  check(!cached.some((p) => p.startsWith('/api/')), 'cache holds no /api/ responses', cached.join(' '));
  await page.setOfflineMode(false);
  await swCdp.send('Network.emulateNetworkConditions', { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });

  // Phones: the link shows the steps for each browser
  for (const [name, [ua, expect]] of Object.entries(UAS)) {
    const p = await browser.newPage();
    // These browsers never make Chrome's install offer, so block it to act like them
    await p.evaluateOnNewDocument(() => addEventListener('beforeinstallprompt', (e) => e.stopImmediatePropagation(), true));
    await p.emulate({ userAgent: ua, viewport: { width: 390, height: 844, isMobile: true, hasTouch: true, deviceScaleFactor: 2 } });
    await p.goto(`${BASE}/demo`, { waitUntil: 'domcontentloaded' });
    const visible = await p.$eval('#install', (el) => !el.hidden);
    check(visible, `${name}: link visible on a phone`);
    if (visible) {
      await p.$eval('#install-btn', (b) => b.scrollIntoView());
      await p.click('#install-btn');
      // The steps open in install-help.js's guide, with pictures of the buttons
      await new Promise((r) => setTimeout(r, 300));
      const text = await p.$eval('.ih-sheet', (el) => el.innerText).catch(() => '');
      check(text.includes(expect) && /Home Screen/i.test(text), `${name}: guide says "${expect}"`, text.replace(/\s+/g, ' ').slice(0, 120));
      const wide = await p.evaluate(() => document.documentElement.scrollWidth > innerWidth);
      check(!wide, `${name}: no sideways scroll`);
    }
    await p.close();
  }

  // Desktop Firefox (no install offer, mouse): no link
  const d = await browser.newPage();
  await d.evaluateOnNewDocument(() => addEventListener('beforeinstallprompt', (e) => e.stopImmediatePropagation(), true));
  await d.goto(`${BASE}/demo`, { waitUntil: 'domcontentloaded' });
  check(await d.$eval('#install', (el) => el.hidden), 'computer with no install offer: link hidden');
  await d.close();

  // Already on the home screen: no link
  const p = await browser.newPage();
  await p.emulate({ userAgent: UAS.chrome[0], viewport: { width: 390, height: 844, isMobile: true, hasTouch: true } });
  try {
    await p.emulateMediaFeatures([{ name: 'display-mode', value: 'standalone' }]);
    await p.goto(`${BASE}/demo`, { waitUntil: 'domcontentloaded' });
    check(await p.$eval('#install', (el) => el.hidden), 'opened from the home screen: link hidden');
  } catch (e) {
    console.log('SKIP standalone check —', e.message);
  }

  await browser.close();
  console.log(fails ? `${fails} FAILED` : 'ALL PASS');
  process.exit(fails ? 1 : 0);
})();
