// Phase 2 page test: follow-up button + hints, then outcomes rendered as business actions.
// Locally the real follow-up call can't connect (agent is locked to the live site), so the test
// starts the follow-up through the API and posts the outcome the way the agent's tool would.
const puppeteer = require('puppeteer-core');
const path = require('path');
const BASE = process.env.BASE || 'http://127.0.0.1:8765';
const TOOL = process.env.TOOL_SECRET || 'local-test';
let pass = 0, fail = 0;
const ok = (c, m) => { if (c) { pass++; console.log('  ok  ', m); } else { fail++; console.log('  FAIL', m); } };

async function runScenario(p, index) {
  await p.goto(BASE + '/demo', { waitUntil: 'networkidle0' });
  await p.waitForSelector('#scenarios button');
  await (await p.$$('#scenarios button'))[index].click();
  await p.waitForSelector('#event-panel .running');
  await p.click('#event-panel .step'); // Pause, then step by hand
  await p.waitForSelector('#event-panel .advance');
  for (let n = 4; n <= 9; n++) {
    await p.click('#event-panel .step');
    await p.waitForFunction((k) => document.querySelectorAll('#event-panel .timeline li').length === k, {}, n);
  }
  return p.$eval('#event-panel .ev-head .id', (n) => n.textContent);
}

async function outcome(p, tid, body) {
  const fu = await p.evaluate(async (id) => {
    const keys = JSON.parse(localStorage.getItem('nightagent-demo-keys'));
    const r = await fetch('/api/demo/follow-up', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ticket_id: id, demo_key: keys[id] }) });
    return r.json();
  }, tid);
  const r = await fetch(BASE + '/tools/follow-up-outcome', { method: 'POST',
    headers: { 'Content-Type': 'application/json', 'x-tool-secret': TOOL },
    body: JSON.stringify({ follow_up_token: fu.dynamic_variables.follow_up_token, conversation_id: 'conv_page_test', ...body }) });
  const out = await r.json();
  await p.evaluate((id) => loadTicketForTest && loadTicketForTest(id), tid).catch(() => {});
  await p.click(`.ticket[data-id="${tid}"]`);
  await p.waitForFunction(() => {
    const chip = document.querySelector('#event-panel .chip.stage');
    return chip && chip.textContent !== 'Check-in call next' && document.querySelector('#event-panel .actions');
  });
  return out;
}

(async () => {
  const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  const p = await b.newPage();
  const errors = [];
  p.on('pageerror', (e) => errors.push(String(e)));
  await p.setViewport({ width: 1280, height: 1000 });

  // Scenario 3: expansion
  const t3 = await runScenario(p, 2);
  const btn = await p.$eval('#event-panel .advance', (n) => n.textContent);
  ok(btn === 'Take the check-in call', 'Check-in ready shows "Take the check-in call"');
  const hint = await p.$eval('#event-panel .follow-box', (n) => n.textContent);
  ok(hint.includes('14 doors'), 'scenario hint tells you what to say');
  await p.evaluate(() => document.getElementById('lifecycle').scrollIntoView());
  await p.screenshot({ path: path.join(__dirname, 'na2-ready.png') });

  const out = await outcome(p, t3, { resolution: 'resolved', satisfaction: 5,
    customer_comments: 'The readers work now.', sales_interest: 'Replace readers building-wide with mobile badges',
    sales_type: 'Access control modernization', sales_scope: 'About 14 doors', sales_device_count: '14', sales_timeline: '3 to 6 months' });
  ok(out.recorded === true, 'outcome recorded through the tool');
  const panel = await p.$eval('#event-panel', (n) => n.innerText);
  ok(/OPP-\d{4}/.test(panel) && panel.includes('not guessed'), 'opportunity shown with value not guessed');
  ok(panel.includes('Sarah Johnson') && panel.includes('fictional'), 'AE is named and labeled fictional');
  ok(panel.includes('Closed'), 'ticket shows Closed as the outcome');
  ok(!(await p.$('#event-panel .reset')), 'Reset is gone once the outcome is on record');
  ok((await p.$$('#event-panel .stages li.done')).length === 7, 'stage strip: seven done + outcome');
  await p.evaluate(() => document.getElementById('lifecycle').scrollIntoView());
  await p.screenshot({ path: path.join(__dirname, 'na2-expansion.png') });

  // Scenario 2: problem returns -> reopened + service task
  const t2 = await runScenario(p, 1);
  await outcome(p, t2, { resolution: 'problem_returned', current_category: 'cannot_secure_site',
    current_impact: 'Back door will not lock tonight', customer_comments: 'It stopped locking again.' });
  const p2 = await p.$eval('#event-panel', (n) => n.innerText);
  ok(p2.includes('Problem came back') && p2.includes('Priority checked again'), 'problem returned: reopened and re-triaged');
  ok(p2.includes('send a technician'), 'service task shown');

  // Scenario 1 with a new issue -> linked ticket that this browser can advance
  const t1 = await runScenario(p, 0);
  await outcome(p, t1, { resolution: 'resolved', new_issue_summary: 'Side door reader is not reading badges.', new_issue_category: 'access_issue' });
  ok(await p.$eval('#event-panel', (n) => /New ticket NS-\d{4}/.test(n.innerText)), 'new linked ticket shown');
  await p.click('#event-panel .action button');
  await p.waitForSelector('#event-panel .advance');
  ok((await p.$eval('#event-panel .advance', (n) => n.textContent)) === 'Run it for me', 'linked ticket opens and can be run');

  // Phone layout of a finished ticket
  await p.setViewport({ width: 390, height: 844, deviceScaleFactor: 2 });
  await p.click(`.ticket[data-id="${t3}"]`);
  await p.waitForFunction(() => /What happens next/.test(document.getElementById('event-panel').textContent));
  const overflow = await p.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  ok(overflow <= 0, `no sideways scrolling on a phone (overflow ${overflow}px)`);
  await p.evaluate(() => document.querySelector('#event-panel .actions').scrollIntoView());
  await p.screenshot({ path: path.join(__dirname, 'na2-phone.png') });

  ok(errors.length === 0, 'no page errors' + (errors.length ? ': ' + errors.join(' | ') : ''));
  console.log(`\n${pass} passed, ${fail} failed`);
  await b.close();
  process.exit(fail ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
