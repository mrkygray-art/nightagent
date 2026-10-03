// Fake ElevenLabs SDK: records the voice each call asks for.
const puppeteer = require('puppeteer-core');
const BASE = 'http://127.0.0.1:8765';
const FAKE = `
const calls = (window.__calls = window.__calls || []);
export const Conversation = { async startSession(o) {
  calls.push({ agentId: o.agentId, voice: o.overrides && o.overrides.tts && o.overrides.tts.voiceId, speed: o.overrides && o.overrides.tts && o.overrides.tts.speed, textOnly: !!o.textOnly });
  setTimeout(() => { o.onConnect && o.onConnect({ conversationId: 'conv_fake' + calls.length }); o.onModeChange && o.onModeChange({ mode: 'listening' }); }, 50);
  return new Proxy({ getId: () => 'conv_fake' + calls.length, endSession: async () => { o.onDisconnect && o.onDisconnect({ reason: 'user' }); }, getInputVolume: () => 0, getOutputVolume: () => 0 }, { get: (t, k) => k in t ? t[k] : () => {} });
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
  // One call per page load; the last voice is remembered across reloads.
  const call = async (url) => { await p.goto(url, { waitUntil: 'networkidle0' }); await p.click('#call'); await p.waitForFunction(() => (window.__calls || []).length > 0, { timeout: 15000 }); await new Promise(r => setTimeout(r, 300)); return p.evaluate(() => window.__calls[0]); };
  const calls = [];
  for (let i = 0; i < 10; i++) calls.push(await call(BASE + '/demo'));
  const voices = calls.map((c) => c.voice);
  console.log('voices:', voices.map(v => v && v.slice(0, 6)).join(' '));
  ok(voices.every(Boolean), 'every voice call asks for a voice');
  ok(voices.every((v, i) => i === 0 || v !== voices[i - 1]), 'never the same voice twice in a row');
  ok(new Set(voices).size >= 3, `several different voices across 10 calls (${new Set(voices).size})`);
  const log = await p.evaluate(() => document.getElementById('tech-log').textContent);
  ok(/Voice/.test(log) && /picked at random/.test(log), 'behind-the-scenes log names the voice');
  // ?voice= picks on purpose
  ok((await call(BASE + '/demo?voice=lauren')).voice === 'DODLEQrClDo8wCz460ld', '?voice=lauren uses Lauren');
  ok((await call(BASE + '/demo?voice=lauren')).voice === 'DODLEQrClDo8wCz460ld', '?voice=lauren works twice in a row');
  ok(errors.length === 0, 'no page errors' + (errors.length ? ': ' + errors.join(' | ') : ''));
  console.log(`\n${pass} passed, ${fail} failed`);
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
