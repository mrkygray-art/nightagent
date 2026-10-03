// Live: typed call with Repeat that + Start over + thinking state + tool log; then a short voice
// call with "Sam speaks slower" on to confirm ElevenLabs accepts the speed override.
const puppeteer = require('puppeteer-core');
const path = require('path');
const BASE = 'https://nightshift-dispatch.vercel.app';
let pass = 0, fail = 0;
const ok = (c, m) => { if (c) { pass++; console.log('  ok  ', m); } else { fail++; console.log('  FAIL', m); } };
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', '--autoplay-policy=no-user-gesture-required'] });
  const p = await b.newPage();
  const errors = [];
  p.on('pageerror', (e) => errors.push(String(e)));
  await p.setViewport({ width: 1280, height: 1000 });
  await p.goto(BASE + '/demo', { waitUntil: 'networkidle0' });
  await p.evaluate(() => localStorage.removeItem('nightagent-prefs'));
  await p.reload({ waitUntil: 'networkidle0' });
  await p.evaluate(() => { document.getElementById('options').open = true; }); await p.click('#pref-tech');
  await p.evaluate(() => { document.getElementById('options').open = true; }); await p.click('.mode button[data-mode="text"]');

  const samCount = () => p.$$eval('.msg.sam', (n) => n.length);
  const lastSam = () => p.$$eval('.msg.sam', (n) => (n.at(-1)?.textContent || '').slice(3));
  const say = async (text) => {
    const before = await samCount();
    await p.type('#message', text);
    await p.click('.composer button');
    const thinking = await p.$eval('#orb-label', (n) => n.textContent);
    await p.waitForFunction((k) => document.querySelectorAll('.msg.sam').length > k, { timeout: 45000 }, before).catch(() => {});
    await wait(2500);
    return thinking;
  };

  // 1) Typed call
  await p.click('#call');
  await p.waitForFunction(() => document.querySelectorAll('.msg.sam').length > 0, { timeout: 45000 });
  ok(await p.$eval('#incall', (n) => !n.hidden), 'Start over and Repeat that appear during the call');
  console.log('SAM:', await lastSam());
  const thinking = await say("Hi, this is Sunset Dental, 310-555-0142.");
  ok(/thinking|looking that up/i.test(thinking), `circle shows "${thinking}" right after you send`);
  console.log('SAM:', await lastSam());
  const tools = await p.$$eval('#tech-log li', (n) => n.map((x) => x.textContent));
  ok(tools.some((t) => t.includes('→ lookup_customer')) && tools.some((t) => t.includes('← lookup_customer')), 'behind-the-scenes shows the lookup_customer request and answer');
  console.log('TECH LOG:\n  ' + tools.slice(-4).join('\n  '));

  // Repeat that
  const before = await samCount();
  await p.click('#repeat');
  await p.waitForFunction((k) => document.querySelectorAll('.msg.sam').length > k, { timeout: 45000 }, before).catch(() => {});
  await wait(2000);
  ok((await samCount()) > before, 'Repeat that: Sam answered again');
  console.log('SAM (repeat):', await lastSam());
  ok(await p.$$eval('.msg.you b', (n) => n.some((x) => x.textContent === 'Sam heard you say')), 'your lines are labeled "Sam heard you say"');

  // Start over
  await p.click('#restart');
  await p.waitForFunction(() => /Started over/.test(document.getElementById('transcript').textContent), { timeout: 15000 }).catch(() => {});
  await p.waitForFunction(() => document.querySelectorAll('.msg.sam').length === 1, { timeout: 45000 }).catch(() => {});
  const afterRestart = await p.$$eval('#transcript .msg', (n) => n.map((x) => x.className + ':' + x.textContent.slice(0, 40)));
  ok(afterRestart.length >= 2 && afterRestart.some((t) => t.includes('Started over')) && afterRestart.filter((t) => t.startsWith('msg sam')).length === 1,
     'Start over: old conversation cleared, Sam greets you fresh');
  ok(await p.$eval('#call', (n) => n.dataset.live === 'true'), 'Start over: a new call is connected');
  await p.evaluate(() => document.querySelector('.console').scrollIntoView());
  await p.screenshot({ path: path.join(__dirname, 'na-live-friendly-text.png') });
  await p.click('#call'); // hang up
  await wait(1500);

  // 2) Voice call with slower speech
  await p.evaluate(() => { document.getElementById('options').open = true; }); await p.click('.mode button[data-mode="voice"]');
  await p.evaluate(() => { document.getElementById('options').open = true; }); await p.click('#pref-slow');
  const t0 = Date.now();
  await p.click('#call');
  const connected = await p.waitForFunction(() => document.getElementById('call').dataset.live === 'true', { timeout: 30000 }).then(() => true).catch(() => false);
  ok(connected, `voice call with slower speech connected in ${Math.round((Date.now() - t0) / 1000)} s`);
  await p.waitForFunction(() => document.getElementById('orb').dataset.state === 'speaking', { timeout: 20000 }).catch(() => {});
  const orb = await p.$eval('#orb', (n) => ({ state: n.dataset.state, label: document.getElementById('orb-label').textContent, lvl: n.style.getPropertyValue('--lvl') }));
  ok(orb.state === 'speaking' && orb.label === 'Sam is speaking…', `circle shows "${orb.label}" while Sam talks`);
  await wait(1500);
  const lvl = await p.$eval('#orb', (n) => Number(n.style.getPropertyValue('--lvl') || 0));
  ok(lvl > 0, `circle moves with Sam's real voice level (${lvl})`);
  const err = await p.$eval('#error', (n) => n.hidden ? '' : n.textContent);
  ok(!err, 'no error from the slower-speech setting' + (err ? `: ${err}` : ''));
  await p.evaluate(() => document.querySelector('.console').scrollIntoView());
  await p.screenshot({ path: path.join(__dirname, 'na-live-friendly-voice.png') });
  try { if (await p.$eval('#call', (n) => n.dataset.live === 'true')) await p.click('#call'); } catch {}
  await wait(1500);

  ok(errors.length === 0, 'no page errors' + (errors.length ? ': ' + errors.join(' | ') : ''));
  console.log(`\n${pass} passed, ${fail} failed`);
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
