// Real typed call on the live site, then check the call report and tool steps.
const puppeteer = require('puppeteer-core');
const path = require('path');
const BASE = 'https://nightshift-dispatch.vercel.app';
const lines = process.env.LINES ? JSON.parse(process.env.LINES) : [
  "Hi, this is Maria at Sunset Dental Group. Our phone number is 310-555-0142.",
  "Our back door won't lock and we're trying to close up for the night. Nobody is in danger.",
  "My name is Maria Lopez and the best callback number is 310-555-0142.",
  "Yes, that's correct.",
  "Yes, please go ahead.",
  "No, that's everything. Thank you.",
];
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
  for (const line of lines) {
    const before = await samCount();
    await p.type('#message', line);
    await p.click('.composer button');
    try { await p.waitForFunction((n) => document.querySelectorAll('.msg.sam').length > n, { timeout: 45000 }, before); } catch { console.log('  (no reply in 45 s)'); }
    await new Promise((r) => setTimeout(r, 2500));
    console.log('YOU:', line, '\nSAM:', (await p.$$eval('.msg.sam', (n) => n.at(-1)?.textContent || '')).slice(0, 400));
    if (/Your ticket NS-\d+/.test(await notes())) break;
  }
  try { await p.waitForFunction(() => /Your ticket NS-\d+/.test(document.getElementById('transcript').textContent), { timeout: 40000 }); } catch {}
  const tid = ((await notes()).match(/NS-\d{4}/) || [])[0];
  console.log('\nTICKET:', tid);
  const all = await p.$$eval('.msg.sam', (n) => n.map((x) => x.textContent).join(' '));
  console.log('BILLING MENTIONED:', /billed|after-hours rate/i.test(all));
  try { await p.click('#call'); } catch {}
  await new Promise((r) => setTimeout(r, 4000));
  const d = await (await fetch(`${BASE}/api/tickets/${tid}`)).json();
  for (const r of d.report.rows) console.log(' ', r.label, '|', r.value);
  console.log('tool_calls:', d.tool_calls.map((t) => `${t.tool} (${t.outcome})`).join(' ; '));
  // The shared link, with behind the scenes on
  await p.goto(`${BASE}/demo?ticket=${tid}&view=report`, { waitUntil: 'networkidle0' });
  await p.waitForSelector('#call-report');
  await p.evaluate(() => { document.getElementById('options').open = true; const c = document.getElementById('pref-tech'); if (!c.checked) c.click(); });
  await new Promise((r) => setTimeout(r, 800));
  await (await p.$('#call-report')).screenshot({ path: path.join(__dirname, 'na-live-report.png') });
  await (await p.$('.timeline')).screenshot({ path: path.join(__dirname, 'na-live-report-timeline.png') });
  console.log('page errors:', errors.length ? errors : 'none');
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
