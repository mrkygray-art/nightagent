// Sam on Deepgram, end to end in a real browser against a mock Deepgram agent socket: the page sends the
// Settings, streams the fake mic as 16 kHz PCM, plays audio, runs Sam's tools through the real backend,
// hangs up on end_call, and the call is saved with its ticket on the board as a Deepgram call.
// Needs the local server with the in-memory store (no Supabase, so nothing live is touched), e.g. on :8767:
//   SUPABASE_URL= SUPABASE_SERVICE_KEY= ZENDESK_SUBDOMAIN= TWILIO_ACCOUNT_SID= TOOL_SECRET=local-test \
//     .venv/Scripts/python -m uvicorn main:app --port 8767
// and the signed session it would hand out, from scripts/deepgram_test_session.py (passed in as DG_START).
const puppeteer = require('puppeteer-core');
const { WebSocketServer } = require('ws');

const BASE = process.env.BASE || 'http://localhost:8767';
const START = JSON.parse(process.env.DG_START);  // {session, settings}
let fails = 0;
const check = (ok, name, extra = '') => { if (!ok) fails++; console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${extra ? ' — ' + extra : ''}`); };

const wss = new WebSocketServer({ port: 8799, handleProtocols: (protocols) => protocols.has('bearer') ? 'bearer' : false });
const seen = { protocols: null, settings: null, audioFrames: 0, audioBytes: 0, responses: [] };
let waitFor = null;
const nextResponse = () => new Promise((resolve) => { waitFor = resolve; });

wss.on('connection', async (ws, req) => {
  seen.protocols = req.headers['sec-websocket-protocol'];
  ws.on('message', (data, isBinary) => {
    if (isBinary) { seen.audioFrames++; seen.audioBytes += data.length; return; }
    const m = JSON.parse(data.toString());
    if (m.type === 'Settings') {
      seen.settings = m;
      ws.send(JSON.stringify({ type: 'Welcome', request_id: 'test' }));
      ws.send(JSON.stringify({ type: 'SettingsApplied' }));
      script(ws).catch((e) => { console.log('mock script failed', e); ws.close(); });
    } else if (m.type === 'FunctionCallResponse') {
      seen.responses.push(m);
      if (waitFor) { const w = waitFor; waitFor = null; w(m); }
    }
  });
});

const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const call = (ws, id, name, args) => {
  const got = nextResponse();
  ws.send(JSON.stringify({ type: 'FunctionCallRequest', functions: [{ id, name, arguments: JSON.stringify(args), client_side: true }] }));
  return got;
};

async function script(ws) {
  ws.send(JSON.stringify({ type: 'ConversationText', role: 'assistant', content: 'Thanks for calling, this is Sam.' }));
  ws.send(JSON.stringify({ type: 'AgentStartedSpeaking', total_latency: 0.82, ttt_latency: 0.41, tts_latency: 0.19 }));
  ws.send(Buffer.alloc(24000 * 2 * 0.3));  // 0.3 s of 24 kHz silence
  ws.send(JSON.stringify({ type: 'AgentAudioDone' }));
  await wait(1200);  // let the mic stream a bit
  ws.send(JSON.stringify({ type: 'UserStartedSpeaking' }));
  ws.send(JSON.stringify({ type: 'ConversationText', role: 'user', content: 'Westside Self Storage, 310 555 0178. The keypad has a trouble light.' }));
  const lookup = await call(ws, 'fc_1', 'lookup_customer', { query: '310-555-0178' });
  seen.lookup = JSON.parse(lookup.content);
  const made = await call(ws, 'fc_2', 'create_ticket', { customer_id: 'C-1002', caller_name: 'James Carter', callback_number: '3105550178',
    issue_summary: 'Keypad trouble light since 9 pm', category: 'panel_trouble', suggested_priority: 'urgent' });
  seen.ticket = JSON.parse(made.content);
  ws.send(JSON.stringify({ type: 'AgentStartedSpeaking', total_latency: 1.04, ttt_latency: 0.66, tts_latency: 0.21 }));
  ws.send(JSON.stringify({ type: 'ConversationText', role: 'assistant', content: 'Your ticket is in. Goodbye!' }));
  await call(ws, 'fc_3', 'end_call', {});
  ws.send(Buffer.alloc(24000 * 2 * 0.2));
  ws.send(JSON.stringify({ type: 'AgentAudioDone' }));
}

(async () => {
  const browser = await puppeteer.launch({
    executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: 'new',
    args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', '--autoplay-policy=no-user-gesture-required'],
  });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.setRequestInterception(true);
  let ended = null;
  page.on('request', (r) => {
    if (r.url().endsWith('/api/deepgram/session')) {
      return r.respond({ status: 200, contentType: 'application/json', body: JSON.stringify({
        token: 'fake-jwt', url: 'ws://localhost:8799', settings: START.settings, session: START.session, call_ref: 'x', max_call_seconds: 60 }) });
    }
    if (r.url().endsWith('/api/deepgram/end')) ended = JSON.parse(r.postData());
    r.continue();
  });
  await page.goto(`${BASE}/deepgram`, { waitUntil: 'networkidle0' });
  check(errors.length === 0, 'page loads with no script errors', errors.join('; '));
  await page.click('#call');
  await page.waitForFunction(() => document.querySelector('#call').textContent === 'Start a call' && document.querySelector('#status').textContent.includes('ended'), { timeout: 20000 });

  check(seen.protocols && seen.protocols.includes('bearer') && seen.protocols.includes('fake-jwt'), 'browser authenticates with the bearer subprotocol', seen.protocols);
  check(seen.settings && seen.settings.agent.listen.provider.model === 'flux-general-en', 'Settings ask for Flux');
  check(seen.settings && seen.settings.agent.speak.provider.model.startsWith('aura-2-'), 'Settings ask for Aura-2');
  check(seen.audioFrames > 5 && seen.audioBytes % 2 === 0, 'mic audio streams as 16-bit PCM after SettingsApplied', `${seen.audioFrames} frames`);
  // ~50 ms frames at 16 kHz = 1600 bytes, so the downsampling is right
  check(seen.audioFrames > 0 && Math.abs(seen.audioBytes / seen.audioFrames - 1600) < 40, 'frames are 16 kHz (about 1600 bytes per 50 ms)', String(seen.audioBytes / seen.audioFrames));
  check(seen.lookup && JSON.stringify(seen.lookup).includes('Westside'), 'lookup_customer ran on the real backend');
  check(seen.ticket && /^NS-\d+$/.test(seen.ticket.ticket_id || ''), 'create_ticket made a board ticket', JSON.stringify(seen.ticket).slice(0, 120));
  check(seen.responses.every((r) => r.type === 'FunctionCallResponse' && r.id && r.name && typeof r.content === 'string'), 'FunctionCallResponses have id, name, content');
  const turns = await page.$$eval('#transcript .turn', (els) => els.map((e) => e.className));
  check(turns.filter((c) => c.includes('assistant')).length === 2 && turns.some((c) => c.includes('user')), 'transcript shows both sides', turns.join(','));
  const rows = await page.$$eval('#latency tr', (els) => els.length);
  check(rows === 2, 'latency table has a row per Sam turn', String(rows));
  check(ended && ended.transcript.length === 3 && ended.latencies.length === 2, 'end of call posts transcript and latencies');

  await wait(800);
  const board = await (await fetch(`${BASE}/api/tickets`)).json();
  const list = Array.isArray(board) ? board : (board.tickets || []);
  const mine = list.find((t) => seen.ticket && t.ticket_id === seen.ticket.ticket_id);
  check(mine && mine.voice === 'deepgram', 'board shows the ticket as a Deepgram call', mine ? mine.voice : 'not found');
  await page.goto(`${BASE}/demo`, { waitUntil: 'networkidle0' });
  await wait(1500);
  const chip = await page.$$eval('.chip.deepgram', (els) => els.map((e) => e.textContent));
  check(chip.includes('Deepgram'), 'board card has the Deepgram chip', chip.join(','));

  await browser.close();
  wss.close();
  console.log(fails ? `${fails} failed` : 'all passed');
  process.exit(fails ? 1 : 0);
})();
