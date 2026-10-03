// Engineering Mode: header switch, pipeline strip, timed live feed, server steps, after-call trace.
const puppeteer = require('puppeteer-core');
const path = require('path');
const BASE = process.env.BASE || 'http://127.0.0.1:8765';
const CONV = 'conv_engtest_' + Date.now();
const FAKE = `
export const Conversation = { async startSession(o) {
  const at = (ms, f) => setTimeout(f, ms);
  at(30, () => o.onConnect && o.onConnect({ conversationId: '${CONV}' }));
  at(100, () => o.onMessage({ source: 'ai', message: 'Thanks for calling, this is Sam.' }));
  at(300, () => o.onMessage({ source: 'user', message: 'My phone number is 424 555 0119' }));
  at(500, async () => {
    o.onAgentToolRequest({ tool_name: 'lookup_customer', tool_call_id: 'tc1' });
    await fetch('/tools/lookup-customer', { method: 'POST', headers: { 'Content-Type': 'application/json', 'x-tool-secret': 'local-test' },
      body: JSON.stringify({ query: '4245550119', conversation_id: '${CONV}' }) });
    setTimeout(() => o.onAgentToolResponse({ tool_name: 'lookup_customer', tool_call_id: 'tc1', is_error: false }), 120);
  });
  at(1200, () => o.onModeChange({ mode: 'speaking' }));
  at(1250, () => o.onMessage({ source: 'ai', message: 'I have Priya Shah at 424 555 0119. Is that right?' }));
  at(1600, () => o.onModeChange({ mode: 'listening' }));
  return new Proxy({ getId: () => '${CONV}', endSession: async () => o.onDisconnect({ reason: 'user' }), getInputVolume: () => 0, getOutputVolume: () => 0 }, { get: (t, k) => k in t ? t[k] : k === 'then' ? undefined : () => {} });
} };`;
const DONE = (tools) => JSON.stringify({ call_ref: 'x', tools, grade: { status: 'done', results: {
  no_unsupported_promises: { result: 'success', rationale: '' }, confirmed_details_first: { result: 'failure', rationale: '' } } },
  turns: [
    { t: 0, who: 'Sam', kind: 'reply', text: 'Thanks for calling, this is Sam.', first_word_ms: 210, voice_ms: 80 },
    { t: 4, who: 'Caller', kind: 'spoke', text: 'Spoke (7 words)', stt_ms: 143 },
    { t: 5, who: 'Sam', kind: 'tool', text: 'Tool: lookup_customer()', decide_ms: 400 },
    { t: 5, who: 'Sam', kind: 'tool_result', text: 'Result: lookup_customer', tool_ms: 218 },
  ] });
let pass = 0, fail = 0;
const ok = (c, m) => { if (c) { pass++; console.log('  ok  ', m); } else { fail++; console.log('  FAIL', m); } };
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  const p = await b.newPage();
  const errors = []; p.on('pageerror', (e) => errors.push(String(e))); p.on('console', (m) => m.type() === 'error' && errors.push('console: ' + m.text()));
  let ended = false, realTools = [];
  await p.setRequestInterception(true);
  p.on('request', async (r) => {
    if (r.url().includes('@elevenlabs/client')) return r.respond({ status: 200, contentType: 'application/javascript', headers: { 'Access-Control-Allow-Origin': '*' }, body: FAKE });
    if (ended && r.url().includes('/api/trace/')) {
      const real = await (await fetch(r.url())).json();
      realTools = real.tools;
      return r.respond({ status: 200, contentType: 'application/json', body: DONE(real.tools) });
    }
    r.continue();
  });
  await p.setViewport({ width: 1280, height: 1000 });
  await p.goto(BASE + '/demo', { waitUntil: 'networkidle0' });
  ok(await p.$eval('#tech', (n) => n.hidden), 'Simple view by default: no Engineering panel');
  ok(!(await p.$eval('#pref-tech', (n) => n.offsetParent)), 'old checkbox is not shown');
  await p.click('.view-switch button[data-view="eng"]');
  ok(!(await p.$eval('#tech', (n) => n.hidden)), 'Engineering switch opens the panel');
  ok(await p.$eval('.view-switch button[data-view="eng"]', (n) => n.getAttribute('aria-pressed')) === 'true', 'switch shows Engineering pressed');
  await p.evaluate(() => { document.getElementById('options').open = true; });
  await p.click('.mode button[data-mode="text"]');
  await p.click('#call');
  await wait(800);
  ok(await p.$eval('#pipe li.on', (n) => n.dataset.stage).catch(() => null) !== null, 'a pipeline stage is lit during the call');
  await p.waitForFunction(() => /Voice reply/.test(document.getElementById('tech-log').innerText), { timeout: 10000 }).catch(() => {}); await wait(600);
  const log = await p.$eval('#tech-log', (n) => n.innerText);
  console.log(log); console.log("ERRORS", errors); console.log("TRANSCRIPT", await p.$eval("#transcript", (n) => n.innerText), "| STATUS", await p.$eval("#status-title", (n) => n.textContent), "| CALL", await p.$eval("#call", (n) => n.textContent));
  ok(/Typed\s+7 words sent to Sam/.test(log), 'caller turn logged as a word count, not the words');
  ok(!/424 555/.test(log), "caller's words not in the feed");
  ok(/← lookup_customer.*\d+ ms round trip/.test(log), 'tool round trip timed');
  ok(/Server: lookup_customer\s+(<1|\d+) ms on the server · Found/.test(log), 'server time and outcome shown');
  ok(/Voice reply\s+audio started \d+ ms/.test(log), 'voice reply timed');
  ended = true;
  await p.click('#call');
  await p.waitForFunction(() => document.querySelectorAll('#eng-trace-list li').length >= 6, { timeout: 15000 });
  const trace = await p.$eval('#eng-trace', (n) => n.innerText);
  console.log(trace);
  ok(/Graded: Confirmed name and number first · fail/.test(trace), 'grades shown');
  ok(/speech to text 143 ms/.test(trace) && /model chose the tool 400 ms/.test(trace), 'turn timings shown');
  ok(realTools.length === 1 && Number.isInteger(realTools[0].duration_ms), 'real /api/trace has server timing');
  ok(await p.$$eval('#pipe li.on', (n) => n.length) === 0, 'strip clears once grading is in');
  await (await p.$('#tech')).screenshot({ path: path.join(__dirname, 'na-eng-panel.png') });
  await p.screenshot({ path: path.join(__dirname, 'na-eng-top.png'), clip: { x: 0, y: 0, width: 1280, height: 120 } });
  await p.click('.view-switch button[data-view="simple"]');
  ok(await p.$eval('#tech', (n) => n.hidden), 'Simple hides the panel again');
  await p.setViewport({ width: 390, height: 844, deviceScaleFactor: 2 });
  await p.goto(BASE + '/demo', { waitUntil: 'networkidle0' });
  ok(await p.evaluate(() => document.documentElement.scrollWidth - innerWidth) <= 0, 'no sideways scrolling on a phone');
  await p.screenshot({ path: path.join(__dirname, 'na-eng-phone.png'), clip: { x: 0, y: 0, width: 390, height: 200 } });
  ok(errors.length === 0, 'no page errors' + (errors.length ? ': ' + errors.join(' | ') : ''));
  console.log(`\n${pass} passed, ${fail} failed`);
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
