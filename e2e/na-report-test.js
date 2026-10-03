// Call report: card, tool rows in behind-the-scenes, voice, share link.
const puppeteer = require('puppeteer-core');
const path = require('path');
const BASE = process.env.BASE || 'http://127.0.0.1:8765';
const TOOL = process.env.TOOL_SECRET || 'local-test';
let pass = 0, fail = 0;
const ok = (c, m) => { if (c) { pass++; console.log('  ok  ', m); } else { fail++; console.log('  FAIL', m); } };
const post = async (p, body, tool) => (await fetch(BASE + p, { method: 'POST', headers: { 'Content-Type': 'application/json', ...(tool ? { 'x-tool-secret': TOOL } : {}) }, body: JSON.stringify(body) })).json();
const rows = (p) => p.$$eval('#call-report dt', (dts) => Object.fromEntries(dts.map((d) => [d.textContent, d.nextElementSibling.textContent])));
(async () => {
  // A "live" call made straight through the tool endpoints
  const conv = 'conv_reporttest_' + Date.now();
  await post('/tools/lookup-customer', { query: '4245550119', conversation_id: conv }, true);
  const made = await post('/tools/create-ticket', { customer_id: 'C-1003', caller_name: 'Priya Shah', callback_number: '4245550119', issue_summary: 'Main entrance will not unlock.', category: 'entry_blocked', suggested_priority: 'emergency', conversation_id: conv }, true);
  await post('/tools/page-on-call', { ticket_id: made.ticket_id }, true);
  const v = await post('/api/demo/voice', { ticket_id: made.ticket_id, conversation_id: conv, voice: 'Matilda' });
  ok(v.ok, 'voice saved for the live call');

  const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  const p = await b.newPage();
  const errors = []; p.on('pageerror', (e) => errors.push(String(e)));
  await p.setViewport({ width: 1280, height: 1000 });

  // Shared link opens the report
  await p.goto(`${BASE}/demo?ticket=${made.ticket_id}&view=report`, { waitUntil: 'networkidle0' });
  await p.waitForSelector('#call-report');
  await new Promise((r) => setTimeout(r, 1200));
  const r = await rows(p);
  console.log(JSON.stringify(r, null, 1));
  ok(r['Agent'] === 'Sam, after-hours dispatcher (voice: Matilda)', 'agent and voice shown');
  ok(r['Tools Sam used'].startsWith('3:'), 'three tools counted');
  ok(r['Escalated'].startsWith('Yes'), 'escalation shown');
  const top = await p.$eval('#call-report', (n) => Math.round(n.getBoundingClientRect().top));
  ok(top >= -20 && top < 200, `share link scrolls to the report (top ${top}px)`);
  ok((await p.$$('.timeline li.tool-row')).length === 0, 'tool steps hidden for everyday visitors');
  await p.screenshot({ path: path.join(__dirname, 'na-report-desk.png') });

  // Behind the scenes on: tool rows join the timeline in time order
  await p.evaluate(() => { document.getElementById('options').open = true; });
  await p.click('.view-switch button[data-view="eng"]');
  await new Promise((r) => setTimeout(r, 400));
  const tl = await p.$$eval('.timeline li', (lis) => lis.map((l) => (l.classList.contains('tool-row') ? 'T:' : '') + l.querySelector('.what b').textContent));
  console.log(tl.join(' | '));
  ok(tl.filter((x) => x.startsWith('T:')).length === 3, 'three tool steps shown behind the scenes');
  ok(tl[0] === 'T:Tool: lookup_customer', 'account lookup comes first');
  ok(tl.indexOf('T:Tool: create_ticket') < tl.indexOf('Ticket created'), 'create_ticket appears before "Ticket created"');
  await (await p.$('#call-report')).screenshot({ path: path.join(__dirname, 'na-report-card.png') });
  await (await p.$('.timeline')).screenshot({ path: path.join(__dirname, 'na-report-timeline.png') });
  await p.click('.view-switch button[data-view="simple"]'); // back off

  // Example scenario: honest report
  await p.goto(BASE + '/demo', { waitUntil: 'networkidle0' });
  await p.waitForSelector('#scenarios button');
  await (await p.$$('#scenarios button'))[2].click();
  await p.waitForSelector('#call-report');
  const r2 = await rows(p);
  ok(r2['Call'].startsWith('Example call (simulated'), 'example labeled simulated');
  ok(r2['Tools Sam used'] === 'None: this example skips the call', 'example claims no tools');

  // Phone width
  await p.setViewport({ width: 390, height: 844, deviceScaleFactor: 2 });
  await p.goto(`${BASE}/demo?ticket=${made.ticket_id}&view=report`, { waitUntil: 'networkidle0' });
  await p.waitForSelector('#call-report'); await new Promise((r) => setTimeout(r, 1200));
  ok(await p.evaluate(() => document.documentElement.scrollWidth - innerWidth) <= 0, 'no sideways scrolling on a phone');
  await (await p.$('#call-report')).screenshot({ path: path.join(__dirname, 'na-report-phone.png') });

  ok(errors.length === 0, 'no page errors' + (errors.length ? ': ' + errors.join(' | ') : ''));
  console.log(`\n${pass} passed, ${fail} failed`);
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
