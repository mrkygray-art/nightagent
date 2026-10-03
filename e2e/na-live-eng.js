// Live: a short typed chat on the real page with Engineering Mode on; prints the live feed and the after-call trace.
const puppeteer = require('puppeteer-core');
const path = require('path');
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  const p = await b.newPage();
  const errors = []; p.on('pageerror', (e) => errors.push(String(e)));
  await p.setViewport({ width: 1280, height: 1100 });
  await p.goto('https://nightshift-dispatch.vercel.app/demo?v=2', { waitUntil: 'networkidle0' });
  await p.click('.view-switch button[data-view="eng"]');
  await p.evaluate(() => { document.getElementById('options').open = true; });
  await p.click('.mode button[data-mode="text"]');
  await p.click('#call');
  await p.waitForFunction(() => document.querySelectorAll('.msg.sam').length >= 1, { timeout: 30000 });
  await wait(1500);
  await p.type('#message', 'Hi, this is Priya Shah, my number is 424-555-0119. Quick question: what are your after-hours support hours?');
  await p.keyboard.press('Enter');
  await p.waitForFunction(() => /Server: lookup_customer/.test(document.getElementById('tech-log').innerText), { timeout: 60000 }).catch(() => console.log('no server line yet'));
  await wait(6000);
  console.log('--- LIVE FEED\n' + await p.$eval('#tech-log', (n) => n.innerText));
  console.log('--- TRANSCRIPT\n' + await p.$eval('#transcript', (n) => n.innerText));
  await p.click('#call');
  await p.waitForFunction(() => /From ElevenLabs|aren't available|taking a while/.test(document.getElementById('eng-trace-status').innerText), { timeout: 200000 });
  console.log('--- AFTER THE CALL\n' + await p.$eval('#eng-trace', (n) => n.innerText));
  await (await p.$('#tech')).screenshot({ path: path.join(__dirname, 'na-live-eng.png') });
  console.log('errors', errors);
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
