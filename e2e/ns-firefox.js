const puppeteer = require('puppeteer-core');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  const b = await puppeteer.launch({
    browser: 'firefox', headless: true,
    executablePath: 'C:/Program Files/Mozilla Firefox/firefox.exe',
    extraPrefsFirefox: { 'media.navigator.streams.fake': true, 'media.navigator.permission.disabled': true },
  });
  const p = await b.newPage();
  const errs = [];
  p.on('pageerror', (e) => errs.push(e.message));
  await p.goto('http://127.0.0.1:5192/demo/', { waitUntil: 'load' });
  await sleep(1500);
  const before = await p.evaluate(() => ({ row: !document.querySelector('#mic-row').hidden, opts: [...document.querySelectorAll('#mic option')].map((o) => o.textContent), btn: document.querySelector('#mic-names').hidden ? '' : document.querySelector('#mic-names').textContent, ua: navigator.userAgent }));
  console.log('Firefox before:', JSON.stringify(before));
  await p.evaluate(() => document.querySelector('#mic-names').click());
  await sleep(1500);
  const after = await p.evaluate(() => ({ opts: [...document.querySelectorAll('#mic option')].map((o) => o.textContent), btnHidden: document.querySelector('#mic-names').hidden, err: document.querySelector('#error').hidden ? '' : document.querySelector('#error').textContent }));
  console.log('Firefox after Find microphones:', JSON.stringify(after));
  // choose the first real mic and confirm it's remembered across a reload
  const chosen = await p.evaluate(() => { const s = document.querySelector('#mic'); if (s.options.length < 2) return null; s.value = s.options[1].value; s.dispatchEvent(new Event('change')); return s.options[1].textContent; });
  await p.reload({ waitUntil: 'load' });
  await sleep(1500);
  const reloaded = await p.evaluate(() => ({ value: document.querySelector('#mic').value !== '', label: document.querySelector('#mic').selectedOptions[0].textContent, saved: localStorage.getItem('nightshift-mic') }));
  console.log('chosen:', chosen, '| after reload selected:', reloaded.label, '| kept:', reloaded.value);
  console.log('page errors:', errs.length ? errs : 'none');
  await b.close();
})().catch((e) => { console.error('FIREFOX TEST ERROR', e.message); process.exit(1); });
