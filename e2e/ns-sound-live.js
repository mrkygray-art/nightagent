// Real call on the live demo: is Sam's voice actually flowing to the speakers?
const puppeteer = require('puppeteer-core');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const which = process.argv[2] || 'chrome';
(async () => {
  const b = which === 'firefox'
    ? await puppeteer.launch({ browser: 'firefox', headless: true, protocolTimeout: 120000, executablePath: 'C:/Program Files/Mozilla Firefox/firefox.exe',
        extraPrefsFirefox: { 'media.navigator.streams.fake': true, 'media.navigator.permission.disabled': true, 'media.autoplay.default': 0 } })
    : await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true,
        args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', '--autoplay-policy=no-user-gesture-required'] });
  const p = await b.newPage();
  // Watch every analyser the page creates, to measure the sound passing through
  await p.evaluateOnNewDocument(() => {
    window.__an = [];
    const orig = AudioContext.prototype.createAnalyser;
    AudioContext.prototype.createAnalyser = function () { const a = orig.call(this); window.__an.push({ a, ctx: this }); return a; };
  });
  await p.goto('https://nightshift-dispatch.vercel.app/demo', { waitUntil: 'load' });
  await sleep(2500);
  await p.evaluate(() => document.querySelector('#call').click());
  let peak = 0, ctxState = '', muted = null, sam = '';
  for (let i = 0; i < 30; i++) {
    await sleep(400);
    const r = await p.evaluate(() => {
      let peak = 0, state = '';
      for (const { a, ctx } of window.__an) {
        const d = new Uint8Array(a.frequencyBinCount); a.getByteFrequencyData(d);
        peak = Math.max(peak, ...d); state = ctx.state;
      }
      const el = [...document.querySelectorAll('audio')].find((x) => x.srcObject);
      return { peak, state, muted: el ? el.muted : null, sam: [...document.querySelectorAll('.msg.sam')].map((m) => m.textContent).join(' '), sound: !document.querySelector('#sound').hidden, err: document.querySelector('#error').hidden ? '' : document.querySelector('#error').textContent };
    });
    peak = Math.max(peak, r.peak); ctxState = r.state; muted = r.muted; sam = r.sam;
    if (r.err) { console.log('error shown:', r.err); break; }
    if (sam && peak > 0 && i > 18) break;
  }
  console.log(`${which}: Sam greeted=${!!sam} | sound level peak=${peak} (0 = silent) | audio engine=${ctxState} | hidden player muted=${muted}`);
  if (await p.evaluate(() => document.querySelector('#call').dataset.live === 'true')) { await p.evaluate(() => document.querySelector('#call').click()); await sleep(1500); }
  await b.close();
})().catch((e) => { console.error(which, 'ERROR', e.message); process.exit(1); });
