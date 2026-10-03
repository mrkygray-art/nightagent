// /lab after the card navigator: script runs, data sections fill, cards jump to sections, phone layout fits.
// Usage: node e2e/na-lab-cards-test.js [lab.json] [base]  (lab.json = a saved /api/lab response; default: live API)
const puppeteer = require('puppeteer-core'); const fs = require('fs');
const DATA = process.argv[2] ? fs.readFileSync(process.argv[2], 'utf8') : null;
const BASE = process.argv[3] || 'http://127.0.0.1:8765';
let pass = 0, fail = 0; const ok = (c, m) => { if (c) { pass++; console.log('  ok  ', m); } else { fail++; console.log('  FAIL', m); } };
(async () => {
  const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  const p = await b.newPage(); const errors = []; p.on('pageerror', (e) => errors.push(String(e)));
  if (DATA) {
    await p.setRequestInterception(true);
    p.on('request', (r) => r.url().endsWith('/api/lab') ? r.respond({ status: 200, contentType: 'application/json', body: DATA }) : r.continue());
  }
  await p.setViewport({ width: 1100, height: 900 });
  await p.goto(BASE + '/lab', { waitUntil: 'networkidle0' });
  const loading = await p.evaluate(() => [...document.querySelectorAll('#sc-tests,#sc-calls,#fixes,#summary')].filter((n) => /Loading/.test(n.innerText)).map((n) => n.id));
  ok(loading.length === 0, 'no section stuck on Loading… ' + loading.join(','));
  ok(await p.$$eval('#sc-tests tr', (r) => r.length) > 1, 'scorecard (tests) filled');
  ok(await p.$$eval('#fixes tbody tr', (r) => r.length) > 0, 'fixes table filled');
  ok(await p.$$eval('#tests .test', (r) => r.length) > 0, 'regression test cards filled');
  const cards = await p.$$eval('.nav-card', (cs) => cs.map((c) => ({ tag: c.tagName, go: c.querySelector('a.go')?.getAttribute('href') })));
  ok(cards.length === 6, '6 navigator cards');
  ok(cards.every((c) => c.tag === 'ARTICLE' && c.go), 'each card is an article with its own button');
  for (const c of cards) ok(await p.$(c.go) !== null, `button target ${c.go} exists`);
  ok(await p.$eval('.nav-card .go', (a) => getComputedStyle(a).backgroundColor) === 'rgb(245, 165, 36)', 'buttons are orange');
  await p.click('a.go[href="#failure"]'); await new Promise((r) => setTimeout(r, 2000));
  ok(Math.abs(await p.$eval('#failure', (s) => s.getBoundingClientRect().top)) < 60, 'Failure Injection button scrolls to its section');
  await p.click('.inject[data-scenario="duplicate-caller"] button');
  await p.waitForFunction(() => /checks/.test(document.querySelector('.inject[data-scenario="duplicate-caller"] .out').innerText), { timeout: 15000 });
  ok(/Passed: \d+ of \d+ checks/.test(await p.$eval('.inject[data-scenario="duplicate-caller"] .out', (n) => n.innerText)), 'failure injection scenario runs');
  await p.setViewport({ width: 390, height: 844 }); await new Promise((r) => setTimeout(r, 300));
  ok(await p.evaluate(() => document.documentElement.scrollWidth - innerWidth) <= 0, 'no sideways scrolling on a phone');
  const btn = await p.$eval('.nav-card .go', (a) => { const r = a.getBoundingClientRect(), c = a.closest('.nav-card').getBoundingClientRect(); return { h: r.height, w: r.width, cw: c.width }; });
  ok(btn.h >= 46 && btn.w > btn.cw * 0.8, `phone buttons full-width and ≥46px tall (${Math.round(btn.w)}/${Math.round(btn.cw)}, ${Math.round(btn.h)}px)`);
  await p.screenshot({ path: __dirname + '/na-lab-cards-phone.png', fullPage: false });
  ok(errors.length === 0, 'no page errors ' + errors.join(' | '));
  console.log(`\n${pass} passed, ${fail} failed`); await b.close(); process.exit(fail ? 1 : 0);
})();
