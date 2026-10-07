// Business Impact panel and ticket view: grouped tiles, Live/Synthetic/All control, the "How these are
// counted" panel, the ticket's handoff sections, and a phone-width check.
// Run against a local server (see e2e/README.md). For a live ticket, first POST one call through the
// tools with the local TOOL_SECRET (this script does it when TOOL_SECRET is set).
const puppeteer = require('puppeteer-core');
const path = require('path');
const BASE = process.env.BASE || 'http://127.0.0.1:8765';
let pass = 0, fail = 0;
const ok = (c, m) => { if (c) { pass++; console.log('  ok  ', m); } else { fail++; console.log('  FAIL', m); } };
const contacts = (p) => p.$eval('#metrics .metric b', (n) => Number(n.textContent));
const pick = async (p, v) => { await p.click(`#impact-view button[data-v="${v}"]`); };

(async () => {
  let liveTicket = null;
  if (process.env.TOOL_SECRET) {
    const post = (u, body) => fetch(BASE + u, { method: 'POST', headers: { 'Content-Type': 'application/json', 'x-tool-secret': process.env.TOOL_SECRET }, body: JSON.stringify(body) }).then((r) => r.json());
    await post('/tools/lookup-customer', { query: '3105550142', conversation_id: 'conv_e2e_impact' });
    liveTicket = (await post('/tools/create-ticket', { customer_id: 'C-1001', caller_name: 'Maria Lopez', callback_number: '3105550142',
      issue_summary: 'Back door will not lock', category: 'door_wont_lock', conversation_id: 'conv_e2e_impact' })).ticket_id;
    await post('/tools/page-on-call', { ticket_id: liveTicket });
  }
  const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  const p = await b.newPage();
  const errors = [];
  p.on('pageerror', (e) => errors.push(String(e)));
  await p.setViewport({ width: 1280, height: 900 });
  await p.goto(BASE + '/demo', { waitUntil: 'networkidle0' });
  await p.waitForSelector('#metrics .metric');
  const groups = await p.$$eval('.metric-group h3', (n) => n.map((x) => x.textContent));
  ok(groups.join('|') === 'Volume|Automation|Escalation and handoff|Resolution quality|Efficiency|Revenue and operations', 'six headings');
  ok((await p.$$('#metrics .metric')).length === 16, 'sixteen tiles');
  ok(await p.$eval('#impact-view [aria-pressed="true"]', (n) => n.dataset.v) === 'live', 'Live is the default view');
  const text = await p.$eval('.impact', (n) => n.innerText);
  ok(text.includes('Demo data') && !/\$|revenue \d/i.test(text.replace('no revenue figures', '')), 'labeled demo, no money shown');
  ok(!/Cresta/i.test(text), 'no vendor branding');

  const live0 = await contacts(p);
  await pick(p, 'synthetic');
  const synth0 = await contacts(p);
  await (await p.$$('#scenarios button'))[0].click();
  await p.waitForSelector('#event-panel .advance');
  await p.waitForFunction((n) => Number(document.querySelector('#metrics .metric b').textContent) > n, { timeout: 30000 }, synth0);
  ok(true, 'a scenario raises Synthetic contacts');
  await pick(p, 'live');
  ok(await contacts(p) === live0, 'and leaves Live alone');
  await pick(p, 'all');
  ok(await contacts(p) === live0 + synth0 + 1, 'All = Live + Synthetic');
  const sums = await p.$$eval('.bars b', (n) => n.reduce((a, x) => a + Number(x.textContent), 0));
  ok(sums === await contacts(p), 'outcome buckets add up to contacts');

  await p.click('.how-counted summary');
  ok((await p.$$('#definitions dt')).length >= 15, 'How these are counted lists each definition');

  // Scenario ticket: synthetic badge, no call to summarize, no actions
  const panel = await p.$eval('#event-panel', (n) => n.innerText);
  ok(/Synthetic/.test(panel) && /no call to summarize/.test(panel) && /Account record/.test(panel), 'scenario ticket sections');
  ok(await p.$('#ticket-evaluation[hidden]') !== null, 'reserved Evaluation section is hidden');

  if (liveTicket) {
    await p.waitForSelector(`#tickets .ticket[data-id="${liveTicket}"]`, { timeout: 30000 });
    await p.click(`#tickets .ticket[data-id="${liveTicket}"]`);
    await p.waitForFunction((id) => document.querySelector('#event-panel .id')?.textContent === id, {}, liveTicket);
    const live = await p.$eval('#event-panel', (n) => n.innerText);
    ok(/Live/.test(live) && /Dispatched/.test(live) && /Handoff context 2\/5/.test(live), 'live dispatched ticket: badge, outcome, handoff 2/5');
    ok(/Looked up the account/.test(live) && /Emergency rule/.test(live) && !/3105550142|310-555-0142/.test(live), 'actions, escalation reason, masked phone');
  }

  await p.evaluate(() => document.querySelector('.impact').scrollIntoView());
  await p.screenshot({ path: path.join(__dirname, 'na-impact-desk.png') });
  await p.evaluate(() => document.querySelector('#event-panel').scrollIntoView());
  await p.screenshot({ path: path.join(__dirname, 'na-ticket-desk.png') });
  await p.setViewport({ width: 390, height: 844, deviceScaleFactor: 2 });
  await p.evaluate(() => document.querySelector('.impact').scrollIntoView());
  const overflow = await p.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  ok(overflow <= 0, `no sideways scrolling on a phone (overflow ${overflow}px)`);
  await p.screenshot({ path: path.join(__dirname, 'na-impact-phone.png') });
  ok(errors.length === 0, 'no page errors' + (errors.length ? ': ' + errors.join(' | ') : ''));
  console.log(`\n${pass} passed, ${fail} failed`);
  await b.close();
  process.exit(fail ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
