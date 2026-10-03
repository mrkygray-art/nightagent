// Stand-in SDK: the specialist never says its name. Labels must come from Sam's handoff line or the tools used.
const puppeteer = require('puppeteer-core');
const BASE = 'http://127.0.0.1:8765';
const fake = (samLine, tool) => `
export const Conversation = { async startSession(o) {
  const at = (ms, f) => setTimeout(f, ms);
  at(30, () => o.onConnect && o.onConnect({ conversationId: 'conv_fake_2' }));
  at(100, () => o.onMessage({ source: 'ai', message: '${samLine}' }));
  at(200, () => o.onAgentToolRequest({ tool_name: 'transfer_to_agent' }));
  at(250, () => o.onAgentToolResponse({ tool_name: 'transfer_to_agent', is_error: false }));
  at(300, () => o.onMessage({ source: 'ai', message: '[warm] Hi there, let me take a look for you.' }));
  at(400, () => o.onAgentToolRequest({ tool_name: '${tool}' }));
  at(450, () => o.onAgentToolResponse({ tool_name: '${tool}', is_error: false }));
  at(500, () => o.onMessage({ source: 'ai', message: 'All set.' }));
  return new Proxy({ getId: () => 'conv_fake_2', endSession: async () => o.onDisconnect({ reason: 'user' }), getInputVolume: () => 0, getOutputVolume: () => 0 }, { get: (t, k) => k in t ? t[k] : () => {} });
} };`;
let pass = 0, fail = 0;
const ok = (c, m) => { if (c) { pass++; console.log('  ok  ', m); } else { fail++; console.log('  FAIL', m); } };
async function run(b, samLine, tool) {
  const p = await b.newPage();
  const errors = []; p.on('pageerror', (e) => errors.push(String(e)));
  await p.setRequestInterception(true);
  p.on('request', (r) => r.url().includes('@elevenlabs/client') ? r.respond({ status: 200, contentType: 'application/javascript', headers: { 'Access-Control-Allow-Origin': '*' }, body: fake(samLine, tool) }) : r.continue());
  await p.goto(BASE + '/demo', { waitUntil: 'networkidle0' });
  await p.evaluate(() => { document.getElementById('options').open = true; });
  await p.click('.mode button[data-mode="text"]');
  await p.click('#call');
  await p.waitForFunction(() => document.querySelectorAll('.msg.sam').length >= 3, { timeout: 15000 });
  await new Promise((r) => setTimeout(r, 300));
  const labels = await p.$$eval('.msg.sam b', (n) => n.map((x) => x.textContent));
  await p.close();
  return { labels, errors };
}
(async () => {
  const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] });
  let r = await run(b, "One moment, I will bring in Riley, our sales assistant.", 'record_sales_interest');
  console.log(r.labels);
  ok(r.labels[0] === 'Sam' && r.labels[1] === 'Riley · sales assistant' && r.labels[2] === 'Riley · sales assistant', "named from Sam's handoff line");
  r = await run(b, 'Let me bring in our specialist.', 'billing_lookup');
  console.log(r.labels);
  ok(r.labels[1] === 'Jordan · billing assistant' && r.labels[2] === 'Jordan · billing assistant', 'named from the tool used, earlier line relabeled');
  ok(!r.errors.length, 'no page errors');
  console.log(`\n${pass} passed, ${fail} failed`);
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
