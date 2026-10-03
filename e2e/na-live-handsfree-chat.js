// Live, hands-free: pick a scenario, touch nothing until the ring, Answer, chat by text, check the outcome.
const puppeteer = require('puppeteer-core');
const path = require('path');
const BASE = 'https://nightshift-dispatch.vercel.app';
const lines = [
  "Everything's working great now, thanks. I'd give the visit a 5.",
  "No, that's everything. Thank you!",
];
(async () => {
  const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  const p = await b.newPage();
  const errors = [];
  p.on('pageerror', (e) => errors.push(String(e)));
  await p.setViewport({ width: 1280, height: 1000 });
  await p.goto(BASE + '/demo', { waitUntil: 'networkidle0' });
  await p.evaluate(() => { document.getElementById('options').open = true; }); await p.click('.mode button[data-mode="text"]');
  await p.waitForSelector('#scenarios button');
  await (await p.$$('#scenarios button'))[0].click();
  await p.waitForSelector('#event-panel .running');
  const tid = await p.$eval('#event-panel .ev-head .id', (n) => n.textContent);
  console.log('TICKET', tid, '- no clicks until it rings…');
  const t0 = Date.now();
  await p.waitForFunction(() => document.getElementById('call').dataset.ring === 'true', { timeout: 60000 });
  console.log(`RANG after ${Math.round((Date.now() - t0) / 1000)} s`);
  await p.click('#call'); // Answer
  await p.waitForFunction(() => document.querySelectorAll('.msg.sam').length > 0, { timeout: 45000 });
  const sam = () => p.$$eval('.msg.sam', (n) => n.at(-1)?.textContent.slice(3) || '');
  console.log('SAM:', await sam());
  for (const line of lines) {
    if (!(await p.$eval('#call', (n) => n.dataset.live === 'true'))) break;
    const before = await p.$$eval('.msg.sam', (n) => n.length);
    await p.type('#message', line);
    await p.click('.composer button');
    try { await p.waitForFunction((k) => document.querySelectorAll('.msg.sam').length > k, { timeout: 45000 }, before); } catch {}
    await new Promise((r) => setTimeout(r, 3000));
    console.log('YOU:', line, '\nSAM:', await sam());
  }
  if (await p.$eval('#call', (n) => n.dataset.live === 'true')) await p.click('#call'); // hang up
  await p.waitForFunction(() => /Closed|Reopened|Escalated/.test(document.querySelector('#event-panel .chip.stage')?.textContent || ''), { timeout: 30000 }).catch(() => {});
  console.log('\nPANEL:', await p.$eval('#event-panel .ev-head', (n) => n.innerText.replace(/\n/g, ' | ')));
  const d = await (await fetch(`${BASE}/api/tickets/${tid}`)).json();
  console.log('STATUS:', d.ticket.status, '| csat:', d.ticket.csat, '| last events:', d.events.slice(-4).map((e) => e.event_type).join(' > '));
  await p.evaluate(() => document.getElementById('lifecycle').scrollIntoView());
  await p.screenshot({ path: path.join(__dirname, 'na-live-handsfree.png') });
  console.log('page errors:', errors.length ? errors : 'none');
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
