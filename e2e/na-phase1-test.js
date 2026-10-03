// Phase 1 browser test: scenarios, Advance/Reset, timeline, board selection, view-only, live-call claim.
const puppeteer = require('puppeteer-core');
const path = require('path');
const BASE = process.env.BASE || 'http://127.0.0.1:8765';
const TOOL = process.env.TOOL_SECRET || 'local-test';
let pass = 0, fail = 0;
const ok = (c, m) => { if (c) { pass++; console.log('  ok  ', m); } else { fail++; console.log('  FAIL', m); } };
const shot = (p, n) => p.screenshot({ path: path.join(__dirname, n), fullPage: false });

(async () => {
  const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  const p = await b.newPage();
  const errors = [];
  p.on('pageerror', (e) => errors.push(String(e)));
  p.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  await p.setViewport({ width: 1280, height: 1000 });
  await p.goto(BASE + '/demo', { waitUntil: 'networkidle0' });

  ok(await p.$eval('title', (n) => n.textContent.includes('NightAgent')), 'page is named NightAgent');
  ok(await p.$eval('.life-banner strong', (n) => n.textContent.includes('DEMO MODE')), 'Demo Mode banner shows');
  await p.waitForSelector('#scenarios button');
  ok((await p.$$('#scenarios button')).length === 4, 'four scenarios listed');

  // Start scenario 1
  await (await p.$$('#scenarios button'))[0].click();
  await p.waitForSelector('#event-panel .running');
  ok(true, 'scenario starts running on its own');
  await p.click('#event-panel .step'); // Pause, to step through by hand
  await p.waitForSelector('#event-panel .advance');
  const head = await p.$eval('#event-panel .ev-head', (n) => n.textContent);
  ok(head.includes('High priority') && head.includes('Waiting for a technician'), 'scenario ticket is high priority and waiting for a technician');
  ok((await p.$$('#event-panel .timeline li.sim')).length === 3, 'three simulated events at start');
  const tid = await p.$eval('#event-panel .ev-head .id', (n) => n.textContent);
  await p.waitForFunction((id) => [...document.querySelectorAll('.ticket')].some((n) => n.dataset.id === id), {}, tid);
  ok(true, 'scenario ticket appears on the board');
  await p.evaluate(() => document.getElementById('lifecycle').scrollIntoView());
  await shot(p, 'na-desk-start.png');

  // Advance through every step
  const labels = [];
  for (let i = 0; i < 6; i++) {
    labels.push(await p.$eval('#event-panel .step', (n) => n.textContent));
    await p.click('#event-panel .step');
    await p.waitForFunction((n) => document.querySelectorAll('#event-panel .timeline li').length === n, {}, 4 + i);
  }
  ok(labels[0].includes('Technician notified') && labels[1].includes('Technician assigned'), 'Next step button names the next step');
  const final = await p.$eval('#event-panel', (n) => n.textContent);
  ok(final.includes('Mike Rodriguez') && final.includes('fictional'), 'technician shown and labeled fictional');
  ok(final.includes('Check-in call next'), 'ends at Check-in call next');
  ok(await p.$eval('#event-panel .advance', (n) => n.textContent === 'Take the check-in call' && !n.disabled), 'at the end, the button takes the follow-up call');
  ok((await p.$$('#event-panel .stages li.done')).length === 6, 'stage strip shows six done stages');
  await shot(p, 'na-desk-done.png');

  // Reset
  await p.click('#event-panel .reset');
  await p.waitForFunction(() => document.querySelectorAll('#event-panel .timeline li').length === 3);
  ok((await p.$eval('#event-panel .ev-head', (n) => n.textContent)).includes('Waiting for a technician'), 'Reset returns to waiting for a technician');

  // Survives a reload (key kept in localStorage), and board selection works
  await p.reload({ waitUntil: 'networkidle0' });
  await p.waitForSelector('.ticket');
  await p.click(`.ticket[data-id="${tid}"]`);
  await p.waitForSelector('#event-panel .advance');
  ok(true, 'after reload, clicking the board ticket restores the controls');

  // A different browser profile sees it view-only
  const ctx = await b.createBrowserContext();
  const q = await ctx.newPage();
  await q.goto(BASE + '/demo', { waitUntil: 'networkidle0' });
  await q.waitForSelector(`.ticket[data-id="${tid}"]`);
  await q.click(`.ticket[data-id="${tid}"]`);
  await q.waitForSelector('#event-panel .ev-note');
  ok(!(await q.$('#event-panel .advance')), 'other visitors get view-only (no Advance)');

  if (process.env.SKIP_TOOLS) { console.log('  skip  live-call claim checks (no tool secret)'); } else {
  // Live call path: a ticket from a "call" is claimed by the browser that knows the conversation id
  const conv = 'conv_test_' + Date.now();
  const made = await (await fetch(BASE + '/tools/create-ticket', {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'x-tool-secret': TOOL },
    body: JSON.stringify({ customer_id: 'C-1001', caller_name: 'Maria', callback_number: '3105550142',
      issue_summary: 'Back door will not lock', category: 'door_wont_lock', conversation_id: conv }),
  })).json();
  await p.evaluate((c) => { window.__conv = c; }, conv);
  // Simulate the SDK having connected: set the module's conversation id through a fresh page load hook
  const r = await p.evaluate(async (c, id) => {
    const res = await fetch('/api/demo/claim', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ticket_id: id, conversation_id: c }) });
    return res.status;
  }, conv, made.ticket_id);
  ok(r === 200, 'claim with the right conversation id works');
  const r2 = await q.evaluate(async (id) => (await fetch('/api/demo/claim', { method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ticket_id: id, conversation_id: 'conv_guess_123' }) })).status, made.ticket_id);
  ok(r2 === 403 || r2 === 409, 'a guessed conversation id is refused');
  const live = await (await fetch(BASE + '/api/tickets/' + made.ticket_id)).json();
  ok(live.events.length === 3 && !live.events.some((e) => e.simulated), 'live call history is real (not simulated)');
  }

  // Phone width
  await p.setViewport({ width: 390, height: 844, deviceScaleFactor: 2 });
  await p.goto(BASE + '/demo', { waitUntil: 'networkidle0' });
  await p.waitForSelector('#scenarios button');
  await (await p.$$('#scenarios button'))[3].click();
  await p.waitForSelector('#event-panel .running');
  await p.click('#event-panel .step');
  await p.waitForSelector('#event-panel .advance');
  for (const n of [4, 5]) {
    await p.click('#event-panel .step');
    await p.waitForFunction((k) => document.querySelectorAll('#event-panel .timeline li').length === k, {}, n);
  }
  const overflow = await p.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  ok(overflow <= 0, `no sideways scrolling on a phone (overflow ${overflow}px)`);
  ok((await p.$eval('#event-panel .ev-head', (n) => n.textContent)).includes('Medium priority'), 'scenario 4 is medium priority');
  await p.evaluate(() => document.getElementById('event-panel').scrollIntoView());
  await shot(p, 'na-phone.png');

  ok(errors.length === 0, 'no page errors' + (errors.length ? ': ' + errors.join(' | ') : ''));
  console.log(`\n${pass} passed, ${fail} failed`);
  await b.close();
  process.exit(fail ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
