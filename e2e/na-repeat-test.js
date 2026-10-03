// Repeat caller: the page says the call joined the open ticket and marks it "Your call"; /lab runs both scenarios.
const puppeteer = require('puppeteer-core'); const fs = require('fs'); const path = require('path');
const BASE = 'http://127.0.0.1:8765';
const CONV = 'conv_repeat_' + Date.now();
const H = { 'Content-Type': 'application/json', 'x-tool-secret': 'local-test' };
const GATE = { customer_id: 'C-1002', callback_number: '3105550178', category: 'cannot_secure_site', suggested_priority: 'emergency' };
const FAKE = `
export const Conversation = { async startSession(o) {
  const at = (ms, f) => setTimeout(f, ms);
  at(30, () => o.onConnect && o.onConnect({ conversationId: '${CONV}' }));
  at(100, () => o.onMessage({ source: 'ai', message: 'Thanks for calling, this is Sam.' }));
  at(500, async () => {
    o.onAgentToolRequest({ tool_name: 'create_ticket', tool_call_id: 't1' });
    await fetch('/tools/create-ticket', { method: 'POST', headers: ${JSON.stringify(H)},
      body: JSON.stringify({ ...${JSON.stringify(GATE)}, caller_name: 'Dana Carter', issue_summary: 'Gate still stuck open', conversation_id: '${CONV}' }) });
    o.onAgentToolResponse({ tool_name: 'create_ticket', tool_call_id: 't1', is_error: false });
  });
  at(900, () => o.onMessage({ source: 'ai', message: 'I found your open ticket and added this call to it.' }));
  return new Proxy({ getId: () => '${CONV}', endSession: async () => o.onDisconnect({ reason: 'user' }), getInputVolume: () => 0, getOutputVolume: () => 0 }, { get: (t, k) => k in t ? t[k] : k === 'then' ? undefined : () => {} });
} };`;
let pass = 0, fail = 0; const ok = (c, m) => { if (c) { pass++; console.log('  ok  ', m); } else { fail++; console.log('  FAIL', m); } };
(async () => {
  const first = await (await fetch(BASE + '/tools/create-ticket', { method: 'POST', headers: H,
    body: JSON.stringify({ ...GATE, caller_name: 'James Carter', issue_summary: 'Front gate stuck open', conversation_id: 'conv_first_' + Date.now() }) })).json();
  const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  const p = await b.newPage(); const errors = []; p.on('pageerror', (e) => errors.push(String(e)));
  await p.setRequestInterception(true);
  p.on('request', (r) => r.url().includes('@elevenlabs/client') ? r.respond({ status: 200, contentType: 'application/javascript', headers: { 'Access-Control-Allow-Origin': '*' }, body: FAKE }) : r.continue());
  await p.setViewport({ width: 1280, height: 1000 });
  await p.goto(BASE + '/demo', { waitUntil: 'networkidle0' });
  await p.evaluate(() => { document.getElementById('options').open = true; });
  await p.click('.mode button[data-mode="text"]');
  await p.click('#call');
  await p.waitForFunction(() => /already on ticket/.test(document.getElementById('transcript').innerText), { timeout: 20000 }).catch(() => {});
  const transcript = await p.$eval('#transcript', (n) => n.innerText);
  ok(transcript.includes(`already on ticket ${first.ticket_id}`), 'page says the call joined the open ticket');
  const card = await p.$eval(`.ticket[data-id="${first.ticket_id}"]`, (n) => n.innerText).catch(() => '');
  ok(/Your call/.test(card), '"Your call" chip on the joined ticket');
  ok(!/already on ticket/.test(transcript.replace(/already on ticket[^\n]*/, '')), 'note shown once');
  const board = await (await fetch(BASE + '/api/tickets')).json();
  ok(board.filter((t) => t.customer_id === 'C-1002' && !t.scenario).length === 1, 'still one ticket for the gate');
  await p.goto(BASE + '/lab', { waitUntil: 'networkidle0' });
  for (const name of ['duplicate-caller', 'paging-down']) {
    await p.click(`.inject[data-scenario="${name}"] button`);
    await p.waitForFunction((n) => /checks/.test(document.querySelector(`.inject[data-scenario="${n}"] .out`).innerText), { timeout: 15000 }, name);
    const out = await p.$eval(`.inject[data-scenario="${name}"] .out`, (n) => n.innerText);
    ok(/^Passed: (\d+) of \1 checks/.test(out), `${name}: ${out.split('\n')[0]}`);
  }
  await (await p.$$('.inject'))[1].screenshot({ path: path.join(__dirname, 'na-inject-down.png') });
  await p.setViewport({ width: 390, height: 844 });
  ok(await p.evaluate(() => document.documentElement.scrollWidth - innerWidth) <= 0, 'lab: no sideways scrolling on a phone');
  ok(errors.length === 0, 'no page errors ' + errors.join(' | '));
  console.log(`\n${pass} passed, ${fail} failed`); await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
