// Hands-free flow: scenario runs itself -> phone rings (sound + green button) -> missed call -> Call back;
// Pause / Next step / Resume; Answer starts the follow-up; scrolling board.
const puppeteer = require('puppeteer-core');
const path = require('path');
const BASE = process.env.BASE || 'http://127.0.0.1:8765';
const SKIP_ANSWER = Boolean(process.env.SKIP_ANSWER);
let pass = 0, fail = 0;
const ok = (c, m) => { if (c) { pass++; console.log('  ok  ', m); } else { fail++; console.log('  FAIL', m); } };
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    args: ['--autoplay-policy=no-user-gesture-required'] });
  const p = await b.newPage();
  const errors = [];
  p.on('pageerror', (e) => errors.push(String(e)));
  let followUpPosts = 0;
  p.on('request', (r) => { if (r.url().includes('/api/demo/follow-up') && r.method() === 'POST') followUpPosts++; });
  // Record ring-tone oscillators the page creates
  await p.evaluateOnNewDocument(() => {
    window.__tones = [];
    const AC = window.AudioContext;
    window.AudioContext = class extends AC {
      createOscillator() { const o = super.createOscillator(); setTimeout(() => window.__tones.push(o.frequency.value), 0); return o; }
    };
  });
  await p.setViewport({ width: 1280, height: 1000 });
  await p.goto(BASE + '/demo', { waitUntil: 'networkidle0' });
  ok(await p.$eval('.top nav', (n) => !n.textContent.includes('Jump to Demo Mode')), 'header has no Jump to Demo Mode link');

  // 1) A scenario runs itself all the way to the ring
  await p.waitForSelector('#scenarios button');
  const t0 = Date.now();
  await (await p.$$('#scenarios button'))[0].click();
  await p.waitForSelector('#event-panel .running');
  ok((await p.$eval('#event-panel .running', (n) => n.textContent)).includes('Moving along on its own'), 'shows "Moving along on its own"');
  await p.waitForFunction(() => document.getElementById('call').dataset.ring === 'true', { timeout: 60000 });
  const secs = Math.round((Date.now() - t0) / 1000);
  ok(secs < 35, `reached the follow-up and rang in ${secs} s with no clicks`);
  ok((await p.$$('#event-panel .timeline li')).length === 9, 'all six simulated steps were added');
  ok(await p.$eval('#call', (n) => n.textContent === 'Incoming call · Answer'), 'call button says "Incoming call · Answer"');
  ok(await p.$eval('#status-title', (n) => n.textContent === 'NightAgent is calling'), 'status says NightAgent is calling');
  ok(Boolean(await p.$('#event-panel .advance.answer')), 'panel shows "Answer the call" too');
  const tones = await p.evaluate(() => window.__tones);
  ok(tones.includes(440) && tones.includes(480), `ring tone playing (${tones.join(' + ')} Hz)`);
  await p.evaluate(() => document.querySelector('.console').scrollIntoView());
  await p.screenshot({ path: path.join(__dirname, 'na-ringing.png') });

  // 2) Not answered -> missed call -> Call back
  await p.waitForFunction(() => document.getElementById('call').dataset.ring === 'false', { timeout: 40000 });
  ok(await p.$eval('#status-title', (n) => n.textContent === 'Missed call from NightAgent'), 'missed call after 30 s');
  ok(await p.$eval('#event-panel .advance', (n) => n.textContent === 'Call back'), 'panel offers "Call back"');
  ok(await p.$eval('#call', (n) => n.textContent.startsWith('Start')), 'call button back to normal');

  // 3) Pause / Next step / Resume on a second scenario
  await (await p.$$('#scenarios button'))[2].click();
  await p.waitForSelector('#event-panel .running');
  await p.click('#event-panel .step'); // Pause
  await p.waitForSelector('#event-panel .advance');
  const paused = await p.$$eval('#event-panel .timeline li', (n) => n.length);
  await wait(4500);
  ok((await p.$$eval('#event-panel .timeline li', (n) => n.length)) === paused, 'Pause stops the automatic steps');
  await p.click('#event-panel .step'); // Next step
  await p.waitForFunction((k) => document.querySelectorAll('#event-panel .timeline li').length === k + 1, {}, paused);
  ok(true, 'Next step adds exactly one step');
  ok(await p.$eval('#event-panel .advance', (n) => n.textContent === 'Resume'), 'button offers Resume');
  await p.click('#event-panel .advance');
  await p.waitForFunction(() => document.getElementById('call').dataset.ring === 'true', { timeout: 60000 });
  ok(true, 'Resume runs to the end and rings');

  // 4) Answer starts the follow-up call (locally the agent refuses the connection; on the live site it talks)
  await p.click('#call');
  await wait(2500);
  ok(followUpPosts >= 1, 'Answer asks the server to start the follow-up');
  ok(await p.$eval('#call', (n) => n.dataset.ring === 'false'), 'ringing stops on Answer');
  if (!SKIP_ANSWER) {
    try { if (await p.$eval('#call', (n) => n.dataset.live === 'true')) await p.click('#call'); } catch {}
  }

  // 5) The dispatch board scrolls inside itself
  const board = await p.$eval('#tickets', (n) => ({ h: n.clientHeight, sh: n.scrollHeight, ov: getComputedStyle(n).overflowY }));
  ok(board.ov === 'auto' && board.h <= 640, `board is a scroll area (${board.h}px tall, ${board.sh}px of tickets)`);
  await p.setViewport({ width: 390, height: 844, deviceScaleFactor: 2 });
  await wait(500);
  const phone = await p.$eval('#tickets', (n) => n.clientHeight);
  ok(phone <= 430, `phone board is at most 430px (${phone}px)`);
  const overflow = await p.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  ok(overflow <= 0, `no sideways scrolling on a phone (overflow ${overflow}px)`);
  await p.evaluate(() => document.querySelector('.board').scrollIntoView());
  await p.screenshot({ path: path.join(__dirname, 'na-board-phone.png') });

  const real = errors.filter((e) => !/origin|allowlist|authorization|not allowed/i.test(e));
  ok(real.length === 0, 'no page errors' + (real.length ? ': ' + real.join(' | ') : ''));
  console.log(`\n${pass} passed, ${fail} failed`);
  await b.close();
  process.exit(fail ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
