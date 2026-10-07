// Evaluation Lab: the safety watchdog and the AI-judge section render, and the page has no errors.
// Run against a local server with TOOL_SECRET set (see e2e/README.md); it makes one emergency ticket.
const puppeteer = require('puppeteer-core');
const path = require('path');
const BASE = process.env.BASE || 'http://127.0.0.1:8765';
let pass = 0, fail = 0;
const ok = (c, m) => { if (c) { pass++; console.log('  ok  ', m); } else { fail++; console.log('  FAIL', m); } };

(async () => {
  const post = (u, body) => fetch(BASE + u, { method: 'POST', headers: { 'Content-Type': 'application/json', 'x-tool-secret': process.env.TOOL_SECRET || '' }, body: JSON.stringify(body) }).then((r) => r.json());
  const t = await post('/tools/create-ticket', { customer_id: 'C-1003', caller_name: 'Priya', callback_number: '4245550119',
    issue_summary: 'Main entrance will not unlock', category: 'entry_blocked', conversation_id: 'conv_e2e_quality' });
  await post('/tools/page-on-call', { ticket_id: t.ticket_id });

  const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  const p = await b.newPage();
  const errors = [];
  p.on('pageerror', (e) => errors.push(String(e)));
  await p.setViewport({ width: 1280, height: 900 });
  await p.goto(BASE + '/lab', { waitUntil: 'networkidle0' });
  await p.waitForFunction(() => !document.querySelector('#watchdog-box').innerText.includes('Loading'));
  const wd = await p.$eval('#watchdog-box', (n) => n.innerText);
  ok(/1 of 1/.test(wd) && /live emergencies alerted/.test(wd), 'watchdog counts the live emergency as alerted');
  const judge = await p.$eval('#judge', (n) => n.innerText);
  ok(/Not measured yet|agreement/.test(judge), 'AI-judge section renders');
  ok(await p.$('a[href="#watchdog"]') !== null, 'lab menu links to the watchdog');
  await p.evaluate(() => document.querySelector('#watchdog').scrollIntoView());
  await p.screenshot({ path: path.join(__dirname, 'na-quality-lab.png') });
  await p.setViewport({ width: 390, height: 844, deviceScaleFactor: 2 });
  const overflow = await p.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  ok(overflow <= 0, `no sideways scrolling on a phone (overflow ${overflow}px)`);
  await p.goto(BASE + '/demo', { waitUntil: 'networkidle0' });
  await p.waitForSelector('#metrics .metric');
  ok(errors.length === 0, 'no page errors' + (errors.length ? ': ' + errors.join(' | ') : ''));
  console.log(`\n${pass} passed, ${fail} failed`);
  await b.close();
  process.exit(fail ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
