// Call check in the page: ticket view, message view, and a call handled on the phone.
const puppeteer = require('puppeteer-core');
const path = require('path');
const BASE = 'http://127.0.0.1:8765';
let pass = 0, fail = 0;
const ok = (c, m) => { if (c) { pass++; console.log('  ok  ', m); } else { fail++; console.log('  FAIL', m); } };
const post = async (p, body) => (await fetch(BASE + p, { method: 'POST', headers: { 'Content-Type': 'application/json', 'x-tool-secret': 'local-test' }, body: JSON.stringify(body) })).json();
(async () => {
  const t0 = Date.now();
  // a call handled on the phone
  await post('/tools/lookup-customer', { query: '3105550142', conversation_id: 'conv_phone_' + t0 });
  await post('/tools/billing-lookup', { customer_id: 'C-1001', conversation_id: 'conv_phone_' + t0 });
  // an emergency ticket
  const conv = 'conv_emerg_' + t0;
  await post('/tools/lookup-customer', { query: '4245550119', conversation_id: conv });
  const made = await post('/tools/create-ticket', { customer_id: 'C-1003', caller_name: 'Priya Shah', callback_number: '4245550119', issue_summary: 'Main entrance will not unlock', category: 'entry_blocked', suggested_priority: 'urgent', conversation_id: conv });
  await post('/tools/page-on-call', { ticket_id: made.ticket_id });

  const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  const p = await b.newPage();
  const errors = []; p.on('pageerror', (e) => errors.push(String(e)));
  await p.setViewport({ width: 1280, height: 1100 });
  await p.goto(BASE + '/demo', { waitUntil: 'networkidle0' });
  await p.waitForSelector('.ticket.phone-call', { timeout: 15000 });
  const card = await p.$eval('.ticket.phone-call', (n) => n.innerText.replace(/\n/g, ' | '));
  console.log('call card:', card);
  ok(/Handled on the call/.test(card) && /Sunset Dental Group/.test(card) && /Jordan/.test(card), 'phone-only call is on the board');
  await p.click('.ticket.phone-call');
  await p.waitForSelector('.check');
  const callCheck = await p.$eval('.check', (n) => n.innerText.replace(/\n/g, ' | '));
  console.log('call check:', callCheck);
  ok(/Call check/.test(callCheck) && /100%/.test(callCheck), 'phone-only call has a check with a score');
  ok(/Not applicable: No repair ticket/.test(callCheck), 'repair checks shown as not applicable');
  await (await p.$('#event-panel')).screenshot({ path: path.join(__dirname, 'na-check-call.png') });

  // ticket with the AI's priority corrected by the rules
  await p.click(`.ticket[data-id="${made.ticket_id}"]`);
  await p.waitForFunction((id) => document.querySelector('#event-panel .ev-head .id')?.textContent === id, {}, made.ticket_id);
  await p.waitForSelector('#event-panel .check');
  const tCheck = await p.$eval('#event-panel .check', (n) => n.innerText.replace(/\n/g, ' | '));
  console.log('ticket check:', tCheck);
  ok(/60%/.test(tCheck) && /3 of 5/.test(tCheck) && /rules corrected it/.test(tCheck), 'ticket check shows the AI was corrected (3 of 5 without the AI grade locally)');
  ok(/AI-judged · ElevenLabs/i.test(tCheck), 'AI-judged check is labeled');
  await (await p.$('#event-panel .report')).screenshot({ path: path.join(__dirname, 'na-check-ticket.png') });

  // shared link to the phone-only call
  const callId = await p.$eval('.ticket.phone-call', (n) => n.dataset.id);
  await p.goto(`${BASE}/demo?ticket=${callId}&view=report`, { waitUntil: 'networkidle0' });
  await p.waitForSelector('#event-panel .check');
  ok(true, 'share link opens the phone-only call');
  await p.setViewport({ width: 390, height: 844, deviceScaleFactor: 2 });
  await p.goto(`${BASE}/demo?ticket=${callId}&view=report`, { waitUntil: 'networkidle0' });
  await p.waitForSelector('#event-panel .check');
  ok(await p.evaluate(() => document.documentElement.scrollWidth - innerWidth) <= 0, 'no sideways scrolling on a phone');
  await (await p.$('#event-panel .check')).screenshot({ path: path.join(__dirname, 'na-check-phone.png') });
  ok(errors.length === 0, 'no page errors' + (errors.length ? ': ' + errors.join(' | ') : ''));
  console.log(`\n${pass} passed, ${fail} failed`);
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
