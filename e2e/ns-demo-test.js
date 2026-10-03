// NightShift demo page: voice over WebSocket with the chosen microphone. Stand-in SDK, pretend mics.
const puppeteer = require('puppeteer-core');
const fs = require('fs');
const HTML = fs.readFileSync('C:/Users/mrkyg/AppData/Local/Temp/claude/c--Users-mrkyg-projects-pictalk/601f8bfc-ec0a-4e1d-a5aa-089c57fe4dd3/scratchpad/ns/demo-new.html', 'utf8');
const results = [];
const check = (name, ok, detail = '') => { results.push(ok); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `  (${detail})` : ''}`); };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const FAKE_SDK = `
export const Conversation = {
  async startSession(opts) {
    window.__calls.push({ connectionType: opts.connectionType, inputDeviceId: opts.inputDeviceId, textOnly: !!opts.textOnly });
    setTimeout(() => opts.onConnect && opts.onConnect({ conversationId: 'conv_test' }), 30);
    if (window.__failAfterConnect) setTimeout(() => opts.onDisconnect && opts.onDisconnect({ reason: 'error', message: 'Client did not provide the origin header' }), 80);
    // Like the real library's voice output: an audio engine, an analyser, and a hidden player
    let output;
    if (!opts.textOnly) {
      const context = new AudioContext();
      const analyser = context.createAnalyser();
      const realConnect = analyser.connect.bind(analyser);
      window.__connected = [];
      analyser.connect = (dest) => { window.__connected.push(dest === context.destination ? 'speakers' : 'other'); return realConnect(dest); };
      const audioElement = new Audio();
      document.body.appendChild(audioElement);
      if (window.__holdSound) await context.suspend();
      window.__out = { context, audioElement };
      output = { context, analyser, audioElement };
    }
    return { output, endSession: async () => opts.onDisconnect && opts.onDisconnect({ reason: 'user' }), sendUserMessage() {}, getId: () => 'conv_test' };
  },
};`;

const fakeMics = (named, style) => {
  window.__calls = [];
  window.__asked = [];
  window.__granted = named;
  window.__open = 0;
  const MICS = [
    { deviceId: 'default', kind: 'audioinput', label: 'Default' },
    { deviceId: 'id-desk', kind: 'audioinput', label: 'Desk Mic (USB)' },
    { deviceId: 'id-cam', kind: 'audioinput', label: 'Webcam Microphone' },
    { deviceId: 'spk', kind: 'audiooutput', label: 'Speakers' },
  ];
  navigator.mediaDevices.enumerateDevices = async () => {
    if (style === 'firefox') {
      // Firefox without a remembered permission: details only while a mic is open
      const visible = window.__open > 0;
      return MICS.map((m) => ({ ...m, deviceId: visible ? m.deviceId : '', label: visible ? m.label : '' }));
    }
    return MICS.map((m) => ({ ...m, label: window.__granted ? m.label : '' }));
  };
  navigator.mediaDevices.getUserMedia = async (c) => {
    const id = c && c.audio && c.audio.deviceId ? c.audio.deviceId.exact : 'default';
    window.__asked.push(id);
    if (id !== 'default' && !MICS.some((m) => m.deviceId === id)) { const e = new Error('gone'); e.name = 'OverconstrainedError'; throw e; }
    window.__granted = true;
    window.__open++;
    return { getTracks: () => [{ stop() { window.__open = Math.max(0, window.__open - 1); } }] };
  };
};

async function open(browser, opts = {}) {
  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 900 });
  const errors = [];
  const sdkUrls = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.setRequestInterception(true);
  page.on('request', (req) => {
    const u = req.url();
    if (u.startsWith('https://ns.test/demo')) return req.respond({ status: 200, contentType: 'text/html', body: HTML });
    if (u.startsWith('https://ns.test/api/tickets')) return req.respond({ status: 200, contentType: 'application/json', body: '[]' });
    if (u.includes('@elevenlabs/client')) { sdkUrls.push(u); return req.respond({ status: 200, contentType: 'application/javascript', headers: { 'access-control-allow-origin': '*' }, body: FAKE_SDK }); }
    if (u.includes('fonts.g')) return req.respond({ status: 200, body: '' });
    req.continue();
  });
  await page.evaluateOnNewDocument(fakeMics, opts.named !== false, opts.style || 'chrome');
  if (opts.storage) await page.evaluateOnNewDocument((v) => { localStorage.setItem('nightshift-mic', v); }, opts.storage);
  await page.goto('https://ns.test/demo', { waitUntil: 'networkidle0' });
  await sleep(300);
  page.errors = errors;
  page.sdkUrls = sdkUrls;
  return page;
}
const options = (p) => p.$$eval('#mic option', (o) => o.map((x) => x.textContent));
const startAndEnd = async (p) => {
  await p.click('#call');
  await sleep(400);
  const r = await p.evaluate(() => ({ calls: window.__calls.slice(), live: document.querySelector('#call').dataset.live, asked: window.__asked.slice(), micLocked: document.querySelector('#mic').disabled }));
  if (r.live === 'true') { await p.click('#call'); await sleep(200); }
  return r;
};

(async () => {
  const browser = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true });

  // 1. Choose a mic, call, and it's remembered
  let p = await open(browser);
  check('Voice mode shows a Microphone list: Browser default + each mic', JSON.stringify(await options(p)) === JSON.stringify(['Browser default', 'Desk Mic (USB)', 'Webcam Microphone']), (await options(p)).join(' | '));
  check('Mic list is visible in voice mode', await p.$eval('#mic-row', (e) => !e.hidden));
  await p.select('#mic', 'id-desk');
  check('Choice is saved on this device', (await p.evaluate(() => localStorage.getItem('nightshift-mic'))).includes('id-desk'));
  let r = await startAndEnd(p);
  check('Voice call uses WebSocket, never WebRTC', r.calls.length === 1 && r.calls[0].connectionType === 'websocket', JSON.stringify(r.calls));
  check('Voice call uses the chosen microphone', r.calls[0].inputDeviceId === 'id-desk' && r.asked.includes('id-desk'), JSON.stringify(r.calls[0]));
  check('Call connects and the button turns into End call', r.live === 'true');
  check('Mic list is locked during the call', r.micLocked === true);
  check('ElevenLabs library is pinned to 1.26.0', p.sdkUrls.length > 0 && p.sdkUrls.every((u) => u.includes('@1.26.0')), p.sdkUrls[0]);
  await p.close();

  // 2. Reload: the choice is still selected
  p = await open(browser, { storage: JSON.stringify({ id: 'id-desk', label: 'Desk Mic (USB)' }) });
  check('After reload, the saved microphone is still selected', (await p.$eval('#mic', (s) => s.value)) === 'id-desk');
  await p.close();

  // 3. Device id changed (plugged back in): found by name
  p = await open(browser, { storage: JSON.stringify({ id: 'old-id', label: 'Webcam Microphone' }) });
  check('If the mic\'s id changed, it is found again by name', (await p.$eval('#mic', (s) => s.value)) === 'id-cam');
  r = await startAndEnd(p);
  check('...and the call uses it', r.calls[0].inputDeviceId === 'id-cam');
  await p.close();

  // 4. Saved mic unplugged: browser default, with a note
  p = await open(browser, { storage: JSON.stringify({ id: 'gone', label: 'Unplugged Mic' }) });
  r = await startAndEnd(p);
  check('Unplugged saved mic: the call uses the browser default mic', r.calls.length === 1 && !r.calls[0].inputDeviceId && r.calls[0].connectionType === 'websocket', JSON.stringify(r.calls));
  check('...says so in the conversation', (await p.evaluate(() => document.querySelector('#transcript').innerText)).includes("Unplugged Mic isn't available"));
  check('...and the list goes back to Browser default', (await p.$eval('#mic', (s) => s.value)) === '' && !(await p.evaluate(() => localStorage.getItem('nightshift-mic'))));
  await p.close();

  // 5. Text mode unchanged
  p = await open(browser);
  await p.click('.mode button[data-mode="text"]');
  await sleep(100);
  check('Text mode hides the microphone list', await p.$eval('#mic-row', (e) => e.hidden));
  r = await startAndEnd(p);
  check('Text chat still starts as text only, with no mic request', r.calls[0].textOnly === true && r.asked.length === 0, JSON.stringify(r));
  await p.close();

  // 6. A call that drops right away explains why
  p = await open(browser);
  await p.evaluate(() => { window.__failAfterConnect = true; });
  await p.click('#call');
  await sleep(500);
  const err = await p.$eval('#error', (e) => (e.hidden ? '' : e.textContent));
  check('A call that drops right away shows the reason', err.includes('origin header'), err);
  await p.close();

  // 7. Before mic permission: names unknown, "Show names" reveals them
  p = await open(browser, { named: false });
  const before = await options(p);
  const btn = await p.$eval('#mic-names', (b) => !b.hidden);
  await p.click('#mic-names');
  await sleep(300);
  const after = await options(p);
  check('Before permission, mics show as Microphone 1/2 with a Show names button', btn && before.includes('Microphone 2'), before.join(' | '));
  check('Show names lists the real names', after.includes('Desk Mic (USB)') && (await p.$eval('#mic-names', (b) => b.hidden)), after.join(' | '));
  await p.screenshot({ path: 'C:/Users/mrkyg/AppData/Local/Temp/claude/c--Users-mrkyg-projects-pictalk/601f8bfc-ec0a-4e1d-a5aa-089c57fe4dd3/scratchpad/ns/mic-ui.png', clip: { x: 0, y: 150, width: 1280, height: 600 } });
  const allErrors = p.errors;
  await p.close();

  // 8. Firefox-style: choose a mic before the first call, and it sticks
  p = await open(browser, { style: 'firefox', named: false });
  check('Firefox: Microphone row shows before any call', await p.$eval('#mic-row', (e) => !e.hidden));
  check('Firefox: before permission it offers Find microphones', (await p.$eval('#mic-names', (b) => !b.hidden && b.textContent === 'Find microphones')) && JSON.stringify(await options(p)) === JSON.stringify(['Browser default']), (await options(p)).join(' | '));
  await p.click('#mic-names');
  await sleep(300);
  check('Firefox: Find microphones lists the real names', (await options(p)).includes('Desk Mic (USB)') && (await p.$eval('#mic-names', (b) => b.hidden)), (await options(p)).join(' | '));
  await p.select('#mic', 'id-desk');
  await p.evaluate(() => navigator.mediaDevices.dispatchEvent && navigator.mediaDevices.dispatchEvent(new Event('devicechange')));
  await sleep(300);
  check('Firefox: all names stay after the browser hides them again', JSON.stringify(await options(p)) === JSON.stringify(['Browser default', 'Desk Mic (USB)', 'Webcam Microphone']) && (await p.$eval('#mic', (s) => s.value)) === 'id-desk', (await options(p)).join(' | '));
  r = await startAndEnd(p);
  check('Firefox: the first call already uses the chosen mic', r.calls.length === 1 && r.calls[0].inputDeviceId === 'id-desk' && r.calls[0].connectionType === 'websocket', JSON.stringify(r.calls));
  await p.close();
  p = await open(browser, { style: 'firefox', named: false, storage: JSON.stringify({ id: 'id-desk', label: 'Desk Mic (USB)' }) });
  check('Firefox: after reload, the saved mic is still selected though the browser hides the list', (await p.$eval('#mic', (s) => s.value)) === 'id-desk' && (await options(p)).includes('Desk Mic (USB)'), (await options(p)).join(' | '));
  r = await startAndEnd(p);
  check('Firefox: ...and the call uses it', r.calls[0].inputDeviceId === 'id-desk', JSON.stringify(r.calls));
  await p.close();

  // 9. Sam's voice goes straight to the speakers; a tap button appears if sound is held back
  p = await open(browser);
  await p.click('#call');
  await sleep(500);
  let snd = await p.evaluate(() => ({ connected: window.__connected, muted: window.__out.audioElement.muted, state: window.__out.context.state, button: !document.querySelector('#sound').hidden }));
  check('Sound: Sam is sent straight to the speakers', snd.connected.includes('speakers'), JSON.stringify(snd.connected));
  check('Sound: the hidden player is muted, so Sam isn\'t heard twice', snd.muted === true);
  check('Sound: no button when sound is already on', snd.state === 'running' && snd.button === false, JSON.stringify(snd));
  await p.click('#call');
  await sleep(300);
  await p.close();
  p = await open(browser);
  await p.evaluate(() => { window.__holdSound = true; });
  await p.click('#call');
  await sleep(500);
  snd = await p.evaluate(() => ({ state: window.__out.context.state, button: !document.querySelector('#sound').hidden, text: document.querySelector('#sound').textContent }));
  check('Sound held back: the "turn on sound" button appears', snd.state === 'suspended' && snd.button, JSON.stringify(snd));
  await p.click('#sound');
  await sleep(400);
  snd = await p.evaluate(() => ({ state: window.__out.context.state, button: !document.querySelector('#sound').hidden }));
  check('Tapping it turns the sound on and hides the button', snd.state === 'running' && !snd.button, JSON.stringify(snd));
  await p.click('#call');
  await sleep(300);
  check('After the call, the sound button is gone', await p.$eval('#sound', (b) => b.hidden));
  await p.close();
  // Text chats never show it
  p = await open(browser);
  await p.click('.mode button[data-mode="text"]');
  await p.click('#call');
  await sleep(400);
  check('Text chat: no sound button', await p.$eval('#sound', (b) => b.hidden));
  await p.close();

  check('No page errors', allErrors.length === 0, allErrors.join(' | '));
  console.log(`\n${results.filter(Boolean).length}/${results.length} passed`);
  await browser.close();
  process.exit(results.every(Boolean) ? 0 : 1);
})().catch((e) => { console.error(e); process.exit(1); });
