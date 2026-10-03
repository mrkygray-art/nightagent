// Feasibility: does Sam hand off to a specialist agent mid-call, from the browser SDK, and does the voice change?
const puppeteer = require('puppeteer-core');
const AGENT = process.env.AGENT || 'agent_1901m3zfgv1je6m9j1w035zg46ne';
const TEXT = process.env.TEXT === '1';
(async () => {
  const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', '--autoplay-policy=no-user-gesture-required'] });
  const p = await b.newPage();
  p.on('console', (m) => { if (m.type() === 'log') console.log('   ', m.text()); });
  await p.goto('https://nightshift-dispatch.vercel.app/demo', { waitUntil: 'networkidle0' });
  const out = await p.evaluate(async (agentId, text) => {
    const { Conversation } = await import('https://cdn.jsdelivr.net/npm/@elevenlabs/client@1.26.0/+esm');
    const log = []; let ai = 0; let disconnect = null; let maxVol = 0;
    const s = await Conversation.startSession({ agentId, connectionType: 'websocket',
      ...(text ? { textOnly: true, overrides: { conversation: { textOnly: true } } } : { overrides: { tts: { voiceId: 'EXAVITQu4vr4xnSDxMaL' } } }),
      onMessage: (m) => { if (m.source === 'ai') ai++; console.log(`${m.source}: ${m.message.slice(0, 160)}`); log.push(m); },
      onAgentToolRequest: (t) => console.log('TOOL REQUEST: ' + JSON.stringify(t).slice(0, 200)),
      onAgentToolResponse: (t) => console.log('TOOL RESPONSE: ' + JSON.stringify(t).slice(0, 200)),
      onError: (e) => console.log('ERROR: ' + String(e && (e.message || e))),
      onDisconnect: (d) => { disconnect = d; console.log('DISCONNECT: ' + JSON.stringify(d).slice(0, 200)); } });
    const iv = setInterval(() => { try { maxVol = Math.max(maxVol, s.getOutputVolume()); } catch {} }, 200);
    const wait = (ms) => new Promise((r) => setTimeout(r, ms));
    const waitAi = async (n, ms) => { const t0 = Date.now(); while (ai < n && Date.now() - t0 < ms && !disconnect) await wait(300); };
    await waitAi(1, 15000); await wait(text ? 500 : 7000);
    s.sendUserMessage('Hi, this is Priya at Harbor Logistics Warehouse. Our number is 424-555-0119.');
    await waitAi(2, 30000); await wait(text ? 1500 : 9000);
    s.sendUserMessage("I have a question about last month's invoice. I think we were charged twice for monitoring.");
    await waitAi(ai + 2, 40000); await wait(text ? 3000 : 15000);
    const conv = s.getId();
    clearInterval(iv);
    try { await s.endSession(); } catch {}
    return { conv, ai, maxVol, disconnect };
  }, AGENT, TEXT);
  console.log('RESULT', JSON.stringify(out));
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
