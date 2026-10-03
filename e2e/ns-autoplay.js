// Real call with a strict "sound only on a tap" rule (like Android WebView browsers).
const puppeteer = require('puppeteer-core');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true,
    args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', '--autoplay-policy=user-gesture-required'] });
  const p = await b.newPage();
  // Like a person reading the microphone prompt: the first permission takes 6 seconds
  await p.evaluateOnNewDocument(() => {
    const orig = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    let first = true;
    window.__ctx = [];
    const AC = window.AudioContext;
    window.AudioContext = class extends AC { constructor(...a) { super(...a); window.__ctx.push(this); } };
    navigator.mediaDevices.getUserMedia = async (c) => { if (first) { first = false; await new Promise((r) => setTimeout(r, 0)); } return orig(c); };
  });
  await p.goto('https://nightshift-dispatch.vercel.app/demo', { waitUntil: 'networkidle2' });
  await sleep(800);
  await p.click('#call');
  let sam = '';
  for (let i = 0; i < 40 && !sam; i++) { await sleep(500); sam = await p.evaluate(() => [...document.querySelectorAll('.msg.sam')].map((m) => m.textContent).join(' ')); }
  await sleep(2500);
  const st = await p.evaluate(() => ({
    audioEls: [...document.querySelectorAll('audio')].map((a) => ({ paused: a.paused, hasStream: !!a.srcObject })),
    sam: [...document.querySelectorAll('.msg.sam')].map((m) => m.textContent).join(' ').slice(0, 80),
    button: !!document.querySelector('#sound'),
    contexts: (window.__ctx || []).map((c) => ({ state: c.state, rate: c.sampleRate })),
  }));
  console.log(JSON.stringify(st));
  if (await p.$eval('#call', (c) => c.dataset.live) === 'true') { await p.click('#call'); await sleep(1500); }
  await b.close();
})();
