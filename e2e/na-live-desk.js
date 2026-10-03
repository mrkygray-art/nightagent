// Real typed call on the live site; prints the conversation and the resulting report (ticket or message).
const puppeteer = require('puppeteer-core');
const BASE = 'https://nightshift-dispatch.vercel.app';
const lines = JSON.parse(process.env.LINES);
(async () => {
  const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  const p = await b.newPage();
  const errors = []; p.on('pageerror', (e) => errors.push(String(e)));
  await p.setViewport({ width: 1280, height: 1000 });
  await p.goto(BASE + '/demo', { waitUntil: 'networkidle0' });
  await p.evaluate(() => { document.getElementById('options').open = true; });
  await p.click('.mode button[data-mode="text"]');
  const samCount = () => p.$$eval('.msg.sam', (n) => n.length);
  const notes = () => p.$$eval('.msg.note', (n) => n.map((x) => x.textContent).join(' | '));
  const done = (t) => /Your ticket NS-\d+|passed your message/.test(t);
  for (const line of lines) {
    const before = await samCount();
    await p.type('#message', line);
    await p.click('.composer button');
    try { await p.waitForFunction((n) => document.querySelectorAll('.msg.sam').length > n, { timeout: 45000 }, before); } catch { console.log('  (no reply in 45 s)'); }
    await new Promise((r) => setTimeout(r, 2500));
    console.log('YOU:', line, '\nSAM:', (await p.$$eval('.msg.sam', (n) => n.at(-1)?.textContent || '')).replace(/^(Sam|Jordan · billing assistant|Riley · sales assistant|Specialist assistant)/, '[$1] ').slice(0, 400));
  }
  try { await p.waitForFunction(() => /Your ticket NS-\d+|passed your message/.test(document.getElementById('transcript').textContent), { timeout: 40000 }); } catch {}
  const n = await notes();
  console.log('NOTES:', n);
  try { await p.click('#call'); } catch {}
  await new Promise((r) => setTimeout(r, 5000));
  const ids = [...new Set([...(await p.evaluate(() => document.getElementById('transcript').textContent)).matchAll(/(NS|TASK)-\d{4}/g)].map((m) => m[0]))];
  const msgs = await (await fetch(`${BASE}/api/messages?x=${Date.now()}`)).json();
  console.log('ids seen:', ids.join(', '), '| newest message on board:', msgs[0] && msgs[0].message_id, msgs[0] && msgs[0].assigned_to);
  for (const id of ids) {
    const d = await (await fetch(`${BASE}/api/${id.startsWith('TASK') ? 'messages' : 'tickets'}/${id}?x=${Date.now()}`)).json();
    console.log(`--- report ${id}`);
    for (const r of (d.report || { rows: [] }).rows) console.log('  ', r.label, '|', r.value);
  }
  console.log('page errors:', errors.length ? errors : 'none');
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
