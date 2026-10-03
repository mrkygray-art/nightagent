// Stand-in SDK plays a handoff: the transcript should switch from Sam to Jordan and drop [tags].
const puppeteer = require('puppeteer-core');
const BASE = 'http://127.0.0.1:8765';
const FAKE = `
export const Conversation = { async startSession(o) {
  const say = (t, ms) => setTimeout(() => o.onMessage({ source: 'ai', message: t }), ms);
  setTimeout(() => o.onConnect && o.onConnect({ conversationId: 'conv_fake_handoff' }), 30);
  say('Thanks for calling, this is Sam. How can I help you tonight?', 100);
  setTimeout(() => o.onAgentToolRequest({ tool_name: 'transfer_to_agent' }), 200);
  setTimeout(() => o.onAgentToolResponse({ tool_name: 'transfer_to_agent', is_error: false }), 250);
  say('[excited] Hi Priya, I am Jordan, the billing assistant. Sam filled me in.', 300);
  say('[calm] I see the September invoice has the monitoring charge twice.', 400);
  return new Proxy({ getId: () => 'conv_fake_handoff', endSession: async () => o.onDisconnect({ reason: 'user' }), getInputVolume: () => 0, getOutputVolume: () => 0 }, { get: (t, k) => k in t ? t[k] : () => {} });
} };`;
let pass = 0, fail = 0;
const ok = (c, m) => { if (c) { pass++; console.log('  ok  ', m); } else { fail++; console.log('  FAIL', m); } };
(async () => {
  const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] });
  const p = await b.newPage();
  const errors = []; p.on('pageerror', (e) => errors.push(String(e)));
  await p.setRequestInterception(true);
  p.on('request', (r) => r.url().includes('@elevenlabs/client') ? r.respond({ status: 200, contentType: 'application/javascript', headers: { 'Access-Control-Allow-Origin': '*' }, body: FAKE }) : r.continue());
  await p.goto(BASE + '/demo', { waitUntil: 'networkidle0' });
  await p.evaluate(() => { document.getElementById('options').open = true; });
  await p.click('.mode button[data-mode="text"]');
  await p.click('#call');
  await p.waitForFunction(() => document.querySelectorAll('.msg.sam').length >= 3, { timeout: 15000 }); console.log('transcript:', await p.$eval('#transcript', (n) => n.innerText)); console.log('errors so far', errors, await p.$eval('#call', (n) => n.textContent), await p.$eval('#status-title', (n) => n.textContent), await p.$eval('#error', (n) => n.textContent));
  const msgs = await p.$$eval('.msg.sam', (n) => n.map((x) => [x.querySelector('b').textContent, x.textContent.replace(x.querySelector('b').textContent, '')]));
  console.log(msgs);
  ok(msgs[0][0] === 'Sam', 'Sam speaks first');
  ok(msgs[1][0] === 'Jordan · billing assistant' && msgs[2][0] === 'Jordan · billing assistant', 'Jordan is labeled after the handoff');
  ok(!msgs.some(([, t]) => /\[/.test(t)), 'voice tags removed from the transcript');
  ok(msgs[1][1].startsWith("Hi Priya, I am Jordan"), 'text kept intact');
  ok(errors.length === 0, 'no page errors' + (errors.length ? ': ' + errors.join(' | ') : ''));
  console.log(`\n${pass} passed, ${fail} failed`);
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
