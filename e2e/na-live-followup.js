// Real typed follow-up chat on the live site: scenario -> advance -> Start follow-up call -> talk -> check outcome.
// Usage: node na-live-followup.js <scenarioIndex> "<line 1>" "<line 2>" ...
const puppeteer = require('puppeteer-core');
const path = require('path');
const BASE = 'https://nightshift-dispatch.vercel.app';
const idx = Number(process.argv[2] || 0);
const lines = process.argv.slice(3);

(async () => {
  const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  const p = await b.newPage();
  const errors = [];
  p.on('pageerror', (e) => errors.push(String(e)));
  await p.setViewport({ width: 1280, height: 1000 });
  await p.goto(BASE + '/demo', { waitUntil: 'networkidle0' });
  await p.evaluate(() => { document.getElementById('options').open = true; }); await p.click('.mode button[data-mode="text"]');
  await p.waitForSelector('#scenarios button');
  await (await p.$$('#scenarios button'))[idx].click();
  await p.waitForSelector('#event-panel .advance');
  for (let n = 4; n <= 9; n++) {
    await p.click('#event-panel .advance');
    await p.waitForFunction((k) => document.querySelectorAll('#event-panel .timeline li').length === k, {}, n);
  }
  const tid = await p.$eval('#event-panel .ev-head .id', (n) => n.textContent);
  console.log('TICKET', tid);
  await p.click('#event-panel .advance'); // Start follow-up call
  await p.waitForFunction(() => document.querySelectorAll('.msg.sam').length > 0, { timeout: 45000 });
  const sam = () => p.$$eval('.msg.sam', (n) => n.at(-1)?.textContent || '');
  console.log('SAM:', (await sam()).slice(3));

  for (const line of lines) {
    if (!(await p.$eval('#call', (n) => n.dataset.live === 'true'))) break;
    const before = await p.$$eval('.msg.sam', (n) => n.length);
    await p.type('#message', line);
    await p.click('.composer button');
    try { await p.waitForFunction((k) => document.querySelectorAll('.msg.sam').length > k, { timeout: 45000 }, before); } catch {}
    await new Promise((r) => setTimeout(r, 3000));
    console.log('YOU:', line, '\nSAM:', (await sam()).slice(3));
  }
  // Wait for the outcome to land on the ticket
  let detail = null;
  for (let i = 0; i < 20; i++) {
    detail = await (await fetch(`${BASE}/api/tickets/${tid}`)).json();
    if (detail.ticket.resolution) break;
    await new Promise((r) => setTimeout(r, 3000));
  }
  console.log('\nSTATUS:', detail.ticket.status, '| resolution:', detail.ticket.resolution, '| csat:', detail.ticket.csat);
  console.log('EVENTS:', detail.events.slice(-7).map((e) => `${e.event_type}${e.simulated ? '*' : ''}`).join(' > '));
  for (const o of detail.actions.opportunities) console.log('OPP:', JSON.stringify(o));
  for (const t of detail.actions.tasks) console.log('TASK:', t.task_id, t.destination, '|', t.reason, '|', t.summary);
  for (const t of detail.actions.tickets) console.log('NEW TICKET:', t.ticket_id, t.priority, t.issue_summary);
  if (await p.$eval('#call', (n) => n.dataset.live === 'true')) await p.click('#call');
  await new Promise((r) => setTimeout(r, 3000));
  await p.evaluate(() => document.getElementById('lifecycle').scrollIntoView());
  await p.screenshot({ path: path.join(__dirname, `na-live-fu-${idx}.png`) });
  console.log('page errors:', errors.length ? errors : 'none');
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
