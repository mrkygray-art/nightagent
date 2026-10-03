// Multi-turn conversation straight through the SDK from the live origin. LINES = caller lines, TEXT=1 for text-only.
const puppeteer = require('puppeteer-core');
const AGENT = process.env.AGENT || 'agent_1901m3zfgv1je6m9j1w035zg46ne';
const TEXT = process.env.TEXT === '1';
const LINES = JSON.parse(process.env.LINES);
(async () => {
  const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', '--autoplay-policy=no-user-gesture-required'] });
  const p = await b.newPage();
  p.on('console', (m) => { if (m.type() === 'log') console.log(m.text()); });
  await p.goto('https://nightshift-dispatch.vercel.app/demo', { waitUntil: 'networkidle0' });
  const out = await p.evaluate(async (agentId, text, lines) => {
    const { Conversation } = await import('https://cdn.jsdelivr.net/npm/@elevenlabs/client@1.26.0/+esm');
    let ai = 0, done = false, speaking = false;
    const s = await Conversation.startSession({ agentId, connectionType: 'websocket',
      ...(text ? { textOnly: true, overrides: { conversation: { textOnly: true } } } : { overrides: { tts: { voiceId: 'EXAVITQu4vr4xnSDxMaL' } } }),
      onMessage: (m) => { if (m.source === 'ai') { ai++; console.log('AI : ' + m.message); } },
      onModeChange: (m) => { speaking = m.mode === 'speaking'; },
      onAgentToolRequest: (t) => console.log('   [tool → ' + t.tool_name + ']'),
      onAgentToolResponse: (t) => console.log('   [tool ← ' + t.tool_name + (t.is_error ? ' ERROR' : '') + ']'),
      onError: (e) => console.log('ERROR: ' + String(e && (e.message || e))),
      onDisconnect: (d) => { done = true; console.log('DISCONNECT ' + JSON.stringify(d).slice(0, 150)); } });
    const wait = (ms) => new Promise((r) => setTimeout(r, ms));
    // wait until the agent has replied and gone quiet for a moment
    const settle = async (before, ms) => { const t0 = Date.now(); while (Date.now() - t0 < ms && !done) { if (ai > before && !speaking) { await wait(text ? 2500 : 3500); if (!speaking) return; } await wait(300); } };
    await settle(0, 20000);
    for (const line of lines) {
      if (done) break;
      console.log('YOU: ' + line);
      const before = ai;
      s.sendUserMessage(line);
      await settle(before, 60000);
    }
    const conv = s.getId();
    try { await s.endSession(); } catch {}
    return conv;
  }, AGENT, TEXT, LINES);
  console.log('CONV', out);
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
