// Real text chat with Sam on the live site: the call's ticket should get history and open in Demo Mode.
const puppeteer = require('puppeteer-core');
const path = require('path');
const BASE = 'https://nightshift-dispatch.vercel.app';
const lines = [
  "Hi, this is Maria at Sunset Dental Group. Our phone number is 310-555-0142.",
  "Our back door won't lock and we're trying to close up for the night. Nobody is in danger.",
  "My name is Maria Lopez and the best callback number is 310-555-0142.",
  "Yes, that's correct.",
  "Yes, please go ahead.",
  "No, that's everything. Thank you.",
];

(async () => {
  const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  const p = await b.newPage();
  const errors = [];
  p.on('pageerror', (e) => errors.push(String(e)));
  await p.setViewport({ width: 1280, height: 1000 });
  await p.goto(BASE + '/demo', { waitUntil: 'networkidle0' });
  await p.evaluate(() => { document.getElementById('options').open = true; }); await p.click('.mode button[data-mode="text"]');
  const samCount = () => p.$$eval('.msg.sam', (n) => n.length);
  const note = () => p.$$eval('.msg.note', (n) => n.map((x) => x.textContent).join(' | '));

  for (const line of lines) {
    const before = await samCount();
    await p.type('#message', line);
    await p.click('.composer button');
    try {
      await p.waitForFunction((n) => document.querySelectorAll('.msg.sam').length > n, { timeout: 45000 }, before);
    } catch { console.log('  (no reply in 45 s)'); }
    await new Promise((r) => setTimeout(r, 2500));
    const last = await p.$$eval('.msg.sam', (n) => n.at(-1)?.textContent || '');
    console.log('YOU:', line, '\nSAM:', last.slice(0, 220));
    if (/your ticket .* is ready in demo mode/i.test(await note())) break;
  }
  try {
    await p.waitForFunction(() => /is ready in Demo Mode/.test(document.getElementById('transcript').textContent), { timeout: 30000 });
  } catch {}
  console.log('\nNOTES:', await note());
  const panel = await p.$eval('#event-panel', (n) => n.innerText);
  console.log('\nPANEL:\n' + panel.slice(0, 900));
  console.log('\nHas Advance button:', Boolean(await p.$('#event-panel .advance')));
  if (await p.$('#event-panel .advance')) {
    await p.click('#event-panel .advance');
    await new Promise((r) => setTimeout(r, 2500));
    console.log('After one Advance:', await p.$eval('#event-panel .ev-head', (n) => n.textContent));
  }
  await p.evaluate(() => document.getElementById('lifecycle').scrollIntoView());
  await p.screenshot({ path: path.join(__dirname, 'na-live-call.png') });
  try { await p.click('#call'); } catch {}
  console.log('page errors:', errors.length ? errors : 'none');
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
