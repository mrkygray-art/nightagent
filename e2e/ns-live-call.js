const puppeteer = require('puppeteer-core');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true,
    args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', '--autoplay-policy=no-user-gesture-required'] });
  const p = await b.newPage();
  const logs = [];
  p.on('console', (m) => logs.push(`${m.type()}: ${m.text()}`.slice(0, 200)));
  p.on('pageerror', (e) => logs.push('PAGEERROR: ' + e.message));
  await p.goto('https://nightshift-dispatch.vercel.app/demo', { waitUntil: 'networkidle2' });
  await sleep(1000);
  const mics = await p.$$eval('#mic option', (o) => o.map((x) => x.textContent));
  console.log('mic list before call:', mics.join(' | '), '| row visible:', await p.$eval('#mic-row', (e) => !e.hidden));
  await p.click('#call');
  const t0 = Date.now();
  let samSaid = '', status = '', live = '';
  for (let i = 0; i < 30; i++) {
    await sleep(500);
    const s = await p.evaluate(() => ({ status: document.querySelector('#status-title').textContent, live: document.querySelector('#call').dataset.live, sam: [...document.querySelectorAll('.msg.sam')].map((m) => m.textContent).join(' '), err: document.querySelector('#error').hidden ? '' : document.querySelector('#error').textContent }));
    status = s.status; live = s.live; samSaid = s.sam;
    if (s.err) { console.log('ERROR SHOWN:', s.err); break; }
    if (samSaid && Date.now() - t0 > 12000) break;
  }
  console.log('status:', status, '| call live:', live, '| seconds:', Math.round((Date.now() - t0) / 1000));
  console.log('Sam said:', samSaid.slice(0, 200));
  const stillLive = await p.$eval('#call', (c) => c.dataset.live);
  if (stillLive === 'true') { await p.click('#call'); await sleep(1500); }
  console.log('after hang-up:', await p.$eval('#status-title', (e) => e.textContent));
  console.log('mic list after call:', (await p.$$eval('#mic option', (o) => o.map((x) => x.textContent))).join(' | '));
  console.log(logs.filter((l) => /error|PAGEERROR/i.test(l)).slice(0, 6).join('\n') || 'no console errors');
  await b.close();
})();
