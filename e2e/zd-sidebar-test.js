// The "NightAgent Call" Zendesk sidebar app (zendesk-app/), loaded from disk with a stand-in for Zendesk's
// SDK, so no Zendesk account or secret is needed. Checks the request it makes, every state it draws, that
// transcript text can't inject markup, and saves a 320px screenshot.
const puppeteer = require('puppeteer-core');
const path = require('path');
const APP = 'file:///' + path.resolve(__dirname, '../zendesk-app/assets/iframe.html').replace(/\\/g, '/');
let pass = 0, fail = 0;
const ok = (c, m) => { if (c) { pass++; console.log('  ok  ', m); } else { fail++; console.log('  FAIL', m); } };

// Stands in for zaf_sdk.min.js. window.__scenario says what the request returns.
const FAKE_SDK = `
window.__requests = []; window.__resizes = [];
window.ZAFClient = { init: function () { return {
  on: function (name, cb) { if (name === 'app.registered') setTimeout(cb, 0); },
  get: function () { return Promise.resolve({ 'ticket.id': window.__scenario.ticketId }); },
  invoke: function (name, arg) { if (name === 'resize') window.__resizes.push(arg); return Promise.resolve(); },
  request: function (opts) {
    window.__requests.push(opts);
    var s = window.__scenario;
    return s.status === 200 ? Promise.resolve(JSON.parse(JSON.stringify(s.body))) : Promise.reject({ status: s.status });
  }
}; } };`;

const CALL = {
  zendesk_ticket_id: 3, nightagent_ticket_id: 'NS-8670', caller_name: 'Dave Matura',
  priority: 'emergency', priority_label: 'High priority',
  board_status_label: 'Technician assigned', zendesk_status: 'open', zendesk_assignee_name: 'Morgan Reyes',
  call_summary: 'Dave Matura reported a side door that would not lock; the on-call technician was paged.',
  analysis_status: 'done',
  tool_calls: [
    { name: 'lookup_customer', ok: true, agent: 'Sam', seconds_into_call: 25, source: 'elevenlabs' },
    { name: 'create_ticket', ok: false, agent: 'Sam', seconds_into_call: 70, source: 'elevenlabs' },
    { name: 'create_ticket', ok: true, agent: 'Sam', seconds_into_call: 75, source: 'elevenlabs' },
    { name: 'page_on_call_tech', ok: true, agent: 'Sam', seconds_into_call: 76, source: 'elevenlabs' },
  ],
  call_check: { score: 71, passed: 5, applicable: 7, checks: [
    { label: 'Identified the customer', status: 'fail', detail: 'The account lookup found no match', judged_by: 'rules' },
    { label: 'Confirmed name and number before acting', status: 'pass', detail: 'Read back •••1212 first.', judged_by: 'ai' },
    { label: 'Avoided unsupported promises', status: 'pass', detail: 'Only the tool’s window.', judged_by: 'ai' },
    { label: 'Escalation needed', status: 'info', detail: 'Yes: an emergency needs the on-call technician', judged_by: 'rules' },
    { label: 'Follow-up completed', status: 'pending', detail: 'The check-in call comes after the repair', judged_by: 'rules' },
  ] },
  transcript: [
    { speaker: 'Agent', text: 'Thanks for calling, this is Sam.' },
    { speaker: 'Caller', text: 'My number is •••1212. <img src=x onerror="window.__xss=1"><b>bold</b>' },
  ],
};

async function open(browser, scenario) {
  const page = await browser.newPage();
  await page.setViewport({ width: 320, height: 900 });
  await page.setRequestInterception(true);
  page.on('request', (req) => {
    if (req.url().startsWith('https://static.zdassets.com/')) {
      req.respond({ status: 200, contentType: 'application/javascript', body: FAKE_SDK });
    } else if (req.url().startsWith('file:')) {
      req.continue();
    } else {
      req.abort();  // nothing else may load
    }
  });
  await page.evaluateOnNewDocument((s) => { window.__scenario = s; }, scenario);
  await page.goto(APP);
  await page.waitForFunction(() => !document.body.innerText.includes('Loading'), { timeout: 5000 });
  return page;
}

(async () => {
  const browser = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: 'new',
    args: ['--allow-file-access-from-files'] });
  try {
    // 1. A NightAgent ticket
    let page = await open(browser, { ticketId: 3, status: 200, body: CALL });
    const req = await page.evaluate(() => window.__requests[0]);
    ok(req.url === 'https://nightshift-dispatch.vercel.app/api/zendesk/tickets/3', 'asks NightAgent for this ticket: ' + req.url);
    ok(req.type === 'GET' && req.secure === true && req.cors === false, 'GET through Zendesk\'s secure proxy');
    ok(req.headers['X-Sidebar-Secret'] === '{{setting.sidebar_secret}}', 'secret is the placeholder, never the value');
    const text = await page.evaluate(() => document.body.innerText);
    ok(text.includes('High priority') && text.includes('NS-8670') && text.includes('Dave Matura'), 'header: priority, ticket, caller');
    ok(text.includes('side door that would not lock'), 'call summary');
    ok(text.includes('On the NightAgent board: Technician assigned') && text.includes('Assigned to Morgan Reyes'), 'board status and Zendesk assignee');
    ok(text.includes('TOOL CALLS (4, 1 failed)') || text.includes('Tool calls (4, 1 failed)'), 'tool count with failures');
    const tools = await page.$$eval('ol.tools li', (lis) => lis.map((li) => [li.className, li.innerText.replace(/\s+/g, ' ')]));
    ok(tools.length === 4 && tools[1][0] === 'failed' && tools[1][1].includes('Created the ticket (failed)'), 'failed tool call marked');
    ok(tools[0][1].includes('lookup_customer') && tools[0][1].includes('0:25') && tools[3][1].includes('1:16'), 'tool names and times into the call');
    const checks = await page.$$eval('ul.checks li', (lis) => lis.map((li) => li.className));
    ok(JSON.stringify(checks) === JSON.stringify(['fail', 'pass', 'pass', 'info', 'pending']), 'every check with its status');
    ok((await page.$$eval('.tag', (t) => t.length)) === 2, 'the two AI-judged checks are tagged');
    ok(text.includes('71% · 5 of 7'), 'call check score');
    ok(!(await page.$eval('details.transcript', (d) => d.open)), 'transcript starts closed');
    const resizesBefore = await page.evaluate(() => window.__resizes.length);
    await page.click('details.transcript summary');
    await page.waitForFunction((n) => window.__resizes.length > n, {}, resizesBefore);
    ok(true, 'opening the transcript resizes the app');
    const line = await page.$eval('.caller-line', (p) => p.textContent);
    ok(line.includes('<img src=x') && line.includes('<b>bold</b>'), 'transcript markup shown as text');
    ok(await page.evaluate(() => !document.querySelector('main img, main b') && window.__xss === undefined), 'no injected element or script ran');
    ok(text.includes('cut to the last four digits') || (await page.evaluate(() => document.body.innerText)).includes('cut to the last four digits'), 'redaction note');
    await page.screenshot({ path: path.join(__dirname, 'zd-sidebar.png'), fullPage: true });
    // Refresh asks again
    await page.click('button.refresh');
    await page.waitForFunction(() => window.__requests.length === 2);
    ok(true, 'Refresh asks NightAgent again');
    await page.close();

    // 2. Analysis not in yet: tool calls from NightAgent's own log
    page = await open(browser, { ticketId: 5, status: 200, body: { ...CALL, analysis_status: 'pending', call_summary: null, transcript: [],
      tool_calls: [{ name: 'lookup_customer', ok: true, called_at: '2026-10-21T06:10:00Z', source: 'nightagent_log' }] } });
    const t2 = await page.evaluate(() => document.body.innerText);
    ok(t2.includes('No summary yet') && t2.includes('still analyzing'), 'pending analysis says so');
    ok(t2.includes("From NightAgent's own log"), 'log fallback explained');
    await page.close();

    // 3. Errors
    const cases = [[404, 'No NightAgent call on this ticket', false], [401, "secret doesn't match", true],
      [429, 'Too many requests', true], [503, "isn't switched on yet", true], [500, "Couldn't reach NightAgent", true]];
    for (const [status, words, retry] of cases) {
      page = await open(browser, { ticketId: 9, status });
      const t = await page.evaluate(() => document.body.innerText);
      ok(t.includes(words) && !!(await page.$('button.refresh')) === retry, `${status}: "${words}"${retry ? ' + Refresh' : ', no Refresh'}`);
      await page.close();
    }

    // 4. A new ticket that isn't saved yet has no id: no request at all
    page = await open(browser, { ticketId: null, status: 200, body: CALL });
    ok((await page.evaluate(() => window.__requests.length)) === 0, 'unsaved ticket: no request');
    await page.close();
  } finally {
    await browser.close();
  }
  console.log(`\n${pass} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
})();
