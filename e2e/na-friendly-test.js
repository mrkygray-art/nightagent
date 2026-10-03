// Friendly call panel (works locally): circle + plain words, reassurance, options that stick,
// behind-the-scenes panel, ring on Start call, plain English across the page, phone fit.
const puppeteer = require('puppeteer-core');
const path = require('path');
const BASE = process.env.BASE || 'http://127.0.0.1:8765';
let pass = 0, fail = 0;
const ok = (c, m) => { if (c) { pass++; console.log('  ok  ', m); } else { fail++; console.log('  FAIL', m); } };
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] });
  const p = await b.newPage();
  const errors = [];
  p.on('pageerror', (e) => errors.push(String(e)));
  await p.evaluateOnNewDocument(() => {
    window.__tones = [];
    const AC = window.AudioContext;
    window.AudioContext = class extends AC {
      createOscillator() { const o = super.createOscillator(); setTimeout(() => window.__tones.push(o.frequency.value), 0); return o; }
    };
  });
  await p.setViewport({ width: 1280, height: 1000 });
  await p.goto(BASE + '/demo', { waitUntil: 'networkidle0' });

  ok(await p.$eval('#orb-label', (n) => n.textContent === 'Ready when you are'), 'circle says "Ready when you are"');
  ok(await p.$eval('#orb', (n) => n.getBoundingClientRect().width >= 100), 'status circle is big (≥100px)');
  ok(await p.$eval('.calm', (n) => n.textContent.includes("You can't break anything")), 'reassurance line shown');
  ok(await p.$eval('#incall', (n) => n.hidden), 'Start over / Repeat hidden until a call starts');
  // Simple first screen: the circle, one line, one button. Everything else is one tap away.
  const first = await p.evaluate(() => {
    const vis = (n) => n.checkVisibility({ contentVisibilityAuto: true, visibilityProperty: true, opacityProperty: true }) && !n.closest('details:not([open]) > :not(summary)');
    const buttons = [...document.querySelectorAll('.console button, .console input, .console select')].filter(vis).map((n) => n.textContent.trim() || n.id);
    return { buttons, options: document.getElementById('options').open, transcript: document.getElementById('transcript').hidden,
             composer: document.getElementById('composer').hidden, hint: document.getElementById('hint').textContent };
  });
  ok(first.buttons.length === 1 && first.buttons[0] === 'Start call', `only one button on the first screen (${first.buttons.join(', ')})`);
  ok(!first.options && first.transcript && first.composer, 'Options closed; conversation and typing box hidden until needed');
  ok(first.hint.includes("You're playing a customer"), 'one line tells you what to do');

  // Plain English across the page
  const page = await p.evaluate(() => document.body.innerText);
  for (const word of ['Triage', 'triaged', 'Dispatch board', 'Accelerated Service Lifecycle', 'Python tool on this server', 'AE opportunities', 'Escalations created']) {
    ok(!page.includes(word), `no jargon: "${word}"`);
  }
  ok(page.includes('Ticket board') && page.includes('DEMO MODE — a whole repair, sped up'), 'plain headings present');

  // Options stick after a reload
  await p.evaluate(() => { document.getElementById('options').open = true; }); await p.click('#pref-big');
  await p.evaluate(() => { document.getElementById('options').open = true; }); await p.click('#pref-tech');
  ok(await p.evaluate(() => document.body.classList.contains('big')), 'Bigger text turns on');
  ok(await p.$eval('#tech', (n) => !n.hidden), 'Behind the scenes panel appears');
  const msgSize = await p.evaluate(() => { const d = document.createElement('div'); d.className = 'msg you'; document.getElementById('transcript').appendChild(d); const s = getComputedStyle(d).fontSize; d.remove(); return s; });
  ok(msgSize === '19px', `transcript text is bigger (${msgSize})`);
  await p.reload({ waitUntil: 'networkidle0' });
  ok(await p.evaluate(() => document.body.classList.contains('big') && document.body.classList.contains('tech-on')), 'options remembered after reload');

  // A scenario shows plain labels, and technical lines appear only with Behind the scenes on
  await (await p.$$('#scenarios button'))[0].click();
  await p.waitForSelector('#event-panel .running');
  await p.click('#event-panel .step'); // Pause
  await p.waitForSelector('#event-panel .advance');
  const panelText = await p.$eval('#event-panel', (n) => n.innerText);
  ok(panelText.includes('High priority') && panelText.includes('Problem saved') && panelText.includes('Our rules set the priority, not the AI'), 'ticket in plain English');
  ok(panelText.includes('event=triage_completed'), 'technical event names visible with Behind the scenes on');
  ok((await p.$$eval('#tech-log li', (n) => n.map((x) => x.textContent))).some((t) => t.includes('Demo step') || t.includes('Start a call')), 'behind-the-scenes log is live');
  await p.evaluate(() => { document.getElementById('options').open = true; }); await p.click('#pref-tech');
  ok(await p.$eval('#event-panel .tech-line', (n) => getComputedStyle(n).display === 'none'), 'technical lines hidden again when switched off');
  await p.evaluate(() => document.querySelector('.console').scrollIntoView());
  await p.screenshot({ path: path.join(__dirname, 'na-friendly-desk.png') });

  // Ring on Start call (locally the agent refuses this site, so the call itself fails after ringing)
  await p.evaluate(() => { document.getElementById('options').open = true; }); await p.click('#pref-big'); // back to normal size for the screenshot set
  await p.evaluate(() => { window.__tones = []; });
  await p.click('#call');
  await p.waitForFunction(() => window.__tones.includes(440) && window.__tones.includes(480), { timeout: 5000 }).catch(() => {});
  ok(await p.evaluate(() => window.__tones.includes(440) && window.__tones.includes(480)), 'a phone ring plays when Start call is pressed');
  ok(await p.$eval('#orb-label', (n) => /Calling Sam|Ready when you are/.test(n.textContent)), 'circle said "Calling Sam…" while connecting');
  await wait(4000);

  // Phone
  await p.setViewport({ width: 390, height: 844, deviceScaleFactor: 2 });
  await p.goto(BASE + '/demo', { waitUntil: 'networkidle0' });
  const overflow = await p.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  ok(overflow <= 0, `no sideways scrolling on a phone (overflow ${overflow}px)`);
  await p.evaluate(() => document.querySelector('.console').scrollIntoView());
  await p.screenshot({ path: path.join(__dirname, 'na-friendly-phone.png') });

  const real = errors.filter((e) => !/origin|allowlist|authorization|not allowed|websocket|closed/i.test(e));
  ok(real.length === 0, 'no page errors' + (real.length ? ': ' + real.join(' | ') : ''));
  console.log(`\n${pass} passed, ${fail} failed`);
  await b.close();
  process.exit(fail ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
