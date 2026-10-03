// Starts a short real voice session from the live demo origin for each voice and checks Sam speaks.
const puppeteer = require('puppeteer-core');
const VOICES = { Matilda: 'XrExE9yKIg1WjnnlVkGX' };
const AGENT = process.env.AGENT || 'agent_0301m3ws1zwae8ya6j72bcv7a193';
(async () => {
  const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', '--autoplay-policy=no-user-gesture-required'] });
  const p = await b.newPage();
  await p.goto('https://nightshift-dispatch.vercel.app/demo', { waitUntil: 'networkidle0' });
  for (const [name, id] of Object.entries(VOICES)) {
    const r = await p.evaluate(async (agentId, voiceId) => {
      const { Conversation } = await import('https://cdn.jsdelivr.net/npm/@elevenlabs/client@1.26.0/+esm');
      const log = { modes: [], errors: [], audioChunks: 0, firstText: '', maxVol: 0, convId: null, disconnect: null };
      let s;
      await new Promise(async (resolve) => {
        const t = setTimeout(resolve, 15000);
        try {
          s = await Conversation.startSession({ agentId, connectionType: 'websocket',
            overrides: { tts: { voiceId } }, dynamicVariables: { customer_first_name: 'Test', technician_name: 'Dana Brooks', ticket_number_spoken: 'N S 1 2 3 4', ticket_id: 'NS-1234', follow_up_token: '' },
            onModeChange: (m) => log.modes.push(m.mode),
            onMessage: (m) => { if (!log.firstText && m.source === 'ai') log.firstText = m.message; },
            onAudio: () => { log.audioChunks++; },
            onError: (e) => log.errors.push(String(e && (e.message || e))),
            onDisconnect: (d) => { log.disconnect = JSON.stringify(d); clearTimeout(t); resolve(); } });
          log.convId = s.getId();
          const iv = setInterval(() => { try { log.maxVol = Math.max(log.maxVol, s.getOutputVolume()); } catch {} }, 200);
          setTimeout(() => { clearInterval(iv); clearTimeout(t); resolve(); }, 9000);
        } catch (e) { log.errors.push(String(e.message || e)); clearTimeout(t); resolve(); }
      });
      try { await s.endSession(); } catch {}
      return log;
    }, AGENT, id);
    const ok = r.modes.includes('speaking') && !r.errors.length && r.maxVol > 0.01;
    console.log(ok ? 'ok  ' : 'FAIL', name, JSON.stringify({ speaking: r.modes.includes('speaking'), vol: +r.maxVol.toFixed(3), chunks: r.audioChunks, errors: r.errors, disconnect: r.disconnect, conv: r.convId, said: r.firstText.slice(0, 60) }));
  }
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
