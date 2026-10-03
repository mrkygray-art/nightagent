// Front desk: a message on the board, its panel and report, the share link, and tool steps.
const puppeteer = require('puppeteer-core');
const path = require('path');
const BASE = process.env.BASE || 'http://127.0.0.1:8765';
let pass = 0, fail = 0;
const ok = (c, m) => { if (c) { pass++; console.log('  ok  ', m); } else { fail++; console.log('  FAIL', m); } };
const post = async (p, body) => (await fetch(BASE + p, { method: 'POST', headers: { 'Content-Type': 'application/json', 'x-tool-secret': 'local-test' }, body: JSON.stringify(body) })).json();
const rows = (p) => p.$$eval('#call-report dt', (dts) => Object.fromEntries(dts.map((d) => [d.textContent, d.nextElementSibling.textContent])));
(async () => {
  const conv = 'conv_desktest_' + Date.now();
  await post('/tools/lookup-customer', { query: '4245550119', conversation_id: conv });
  const msg = await post('/tools/take-message', { department: 'billing', reason: 'Question about last month\'s invoice: charged twice for monitoring.', caller_name: 'Priya Shah', callback_number: '4245550119', customer_id: 'C-1003', best_time: 'tomorrow after 10 AM', conversation_id: conv });
  console.log('Sam is told:', msg.tell_the_caller);
  await post('/api/demo/voice', { ticket_id: msg.message_id, conversation_id: conv, voice: 'Chris' });
  // and a normal ticket, so the board has both
  await post('/api/demo/scenario', { scenario: 'expansion' });

  const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  const p = await b.newPage();
  const errors = []; p.on('pageerror', (e) => errors.push(String(e)));
  await p.setViewport({ width: 1280, height: 1000 });
  await p.goto(BASE + '/demo', { waitUntil: 'networkidle0' });
  await p.waitForSelector(`.ticket[data-id="${msg.message_id}"]`, { timeout: 15000 });
  const card = await p.$eval(`.ticket[data-id="${msg.message_id}"]`, (n) => n.innerText);
  console.log(card.replace(/\n/g, ' | '));
  ok(/Message for Billing/.test(card), 'message card on the board');
  ok(/For: Morgan Lee, Billing/.test(card) && /•••-0119/.test(card), 'card shows who and a masked number');
  ok((await p.$$('.ticket')).length >= 2, 'tickets and messages share the board');
  await p.click(`.ticket[data-id="${msg.message_id}"]`);
  await p.waitForSelector('#call-report');
  await new Promise((r) => setTimeout(r, 600));
  const r = await rows(p);
  console.log(JSON.stringify(r, null, 1));
  ok(r['Agent'].endsWith('(voice: Chris)'), 'voice shown');
  ok(r['Tools Sam used'] === '2: Looked up the account; Took a message', 'two tools counted');
  ok(r['Service ticket'] === 'None: not a service problem', 'no ticket, said plainly');
  ok(r['Callback'].includes('tomorrow after 10 AM'), 'best time shown');
  ok(!(await p.$('#event-panel .advance')), 'no Demo Mode buttons on a message');
  await (await p.$('#event-panel')).screenshot({ path: path.join(__dirname, 'na-desk-panel.png') });
  await (await p.$(`.ticket[data-id="${msg.message_id}"]`)).screenshot({ path: path.join(__dirname, 'na-desk-card.png') });
  // behind the scenes
  await p.evaluate(() => { document.getElementById('options').open = true; });
  await p.click('.view-switch button[data-view="eng"]');
  await new Promise((r) => setTimeout(r, 400));
  ok((await p.$$('#event-panel .tool-row')).length === 2, 'tool steps shown behind the scenes');
  await p.click('.view-switch button[data-view="eng"]');
  // share link
  await p.goto(`${BASE}/demo?ticket=${msg.message_id}&view=report`, { waitUntil: 'networkidle0' });
  await p.waitForSelector('#call-report');
  ok((await rows(p))['Handed to'].startsWith('Morgan Lee'), 'share link opens the message report');
  // clicking a ticket after a message still works
  await p.goto(BASE + '/demo', { waitUntil: 'networkidle0' });
  await p.waitForSelector('.ticket:not(.message)');
  await p.click(`.ticket[data-id="${msg.message_id}"]`); await p.waitForSelector('#call-report');
  await p.click('.ticket:not(.message)'); await new Promise((r) => setTimeout(r, 1200));
  ok(Boolean(await p.$('#event-panel .stages')), 'switching to a ticket shows the ticket view');
  await p.setViewport({ width: 390, height: 844, deviceScaleFactor: 2 });
  await p.goto(BASE + '/demo', { waitUntil: 'networkidle0' });
  ok(await p.evaluate(() => document.documentElement.scrollWidth - innerWidth) <= 0, 'no sideways scrolling on a phone');
  ok(errors.length === 0, 'no page errors' + (errors.length ? ': ' + errors.join(' | ') : ''));
  console.log(`\n${pass} passed, ${fail} failed`);
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
