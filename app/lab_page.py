"""The public /lab page: the Evaluation Lab. A scorecard from tests and real calls, then regression
tests built from real problems found in live calls, with their latest results from ElevenLabs Agent
Testing (read via /api/lab).
"""

LAB_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>NightAgent: Evaluation Lab</title>
<meta name="description" content="How well NightAgent's voice agents do, measured honestly: a scorecard from tests and real calls, and regression tests built from real problems.">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' fill='%23101a2e'/%3E%3Ccircle cx='16' cy='16' r='7' fill='%23f5a524'/%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700&family=Barlow:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root {
    --night: #101a2e; --panel: #172440; --line: #2b3d63; --text: #e9edf5; --muted: #a3afc6;
    --sodium: #f5a524; --alarm: #e5484d; --clear: #4cb782;
    --body: "Barlow", system-ui, -apple-system, "Segoe UI", sans-serif;
    --display: "Barlow Condensed", "Arial Narrow", system-ui, sans-serif;
    color-scheme: dark;
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--night); color: var(--text); font: 16px/1.5 var(--body); font-variant-numeric: tabular-nums; }
  a { color: var(--sodium); }
  a:focus-visible { outline: 2px solid var(--sodium); outline-offset: 2px; }
  .wrap { max-width: 980px; margin: 0 auto; padding: 0 16px 48px; }
  .top { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 10px 16px; padding: 18px 0; border-bottom: 1px solid var(--line); }
  .brand { font-family: var(--display); font-weight: 700; font-size: 22px; color: var(--text); text-decoration: none; }
  .top nav { display: flex; flex-wrap: wrap; gap: 6px 18px; }
  .top nav a { font-weight: 500; text-decoration: none; }
  .top nav a:hover { text-decoration: underline; }
  h1 { font-family: var(--display); font-size: clamp(34px, 6vw, 48px); line-height: 1.05; margin: 28px 0 10px; }
  .intro { color: var(--muted); max-width: 68ch; margin: 0 0 20px; }
  .summary { display: flex; flex-wrap: wrap; gap: 12px; margin: 0 0 24px; }
  .stat { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 12px 16px; min-width: 150px; }
  .stat b { display: block; font-family: var(--display); font-size: 30px; line-height: 1.1; }
  .stat span { color: var(--muted); font-size: 14px; }
  .tests { display: grid; grid-template-columns: minmax(0, 1fr); gap: 14px; }
  .test { min-width: 0; background: var(--panel); border: 1px solid var(--line); border-radius: 14px; padding: 16px 18px; display: grid; gap: 8px; }
  .test-head { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-start; gap: 8px 12px; }
  .test h2 { margin: 0; font-size: 18px; line-height: 1.3; }
  .meta { color: var(--muted); font-size: 14px; }
  .score { flex: none; font-weight: 600; font-size: 14px; border-radius: 999px; padding: 4px 10px; border: 1px solid var(--line); white-space: nowrap; }
  .score.all { color: #0d2a1b; background: var(--clear); border-color: var(--clear); }
  .score.some { color: #2a1a00; background: var(--sodium); border-color: var(--sodium); }
  .score.none { color: #fff; background: var(--alarm); border-color: var(--alarm); }
  .test dl { margin: 0; display: grid; grid-template-columns: 150px 1fr; gap: 6px 14px; }
  .test dt { color: var(--muted); font-size: 14px; }
  .test dd { margin: 0; min-width: 0; overflow-wrap: anywhere; }
  .said { font: 13.5px/1.5 ui-monospace, SFMono-Regular, Consolas, monospace; color: #cfd6e4; word-break: break-word; }
  .judge { display: block; color: var(--muted); font-size: 14px; margin-top: 2px; }
  .fine { color: var(--muted); font-size: 14px; max-width: 72ch; }
  h2.section { font-family: var(--display); font-size: 30px; margin: 36px 0 6px; }
  .inject { background: var(--panel); border: 1px solid var(--line); border-radius: 14px; padding: 16px 18px; display: grid; gap: 10px; min-width: 0; }
  .inject button {
    justify-self: start; font: inherit; font-weight: 600; color: #1a1200; background: var(--sodium);
    border: 0; border-radius: 999px; padding: 9px 18px; cursor: pointer;
  }
  .inject button:disabled { opacity: 0.6; cursor: default; }
  .inject button:focus-visible { outline: 2px solid var(--text); outline-offset: 2px; }
  .inject ol { margin: 0; padding-left: 20px; display: grid; gap: 6px; }
  .inject li { min-width: 0; overflow-wrap: anywhere; }
  .inject ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; }
  table.grid { width: 100%; border-collapse: collapse; background: var(--panel); border: 1px solid var(--line); border-radius: 12px; overflow: hidden; margin: 0 0 8px; }
  .grid th, .grid td { text-align: left; vertical-align: top; padding: 10px 14px; border-bottom: 1px solid var(--line); }
  .grid tr:last-child td { border-bottom: 0; }
  .grid th { font-size: 13px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; background: #13203a; }
  .grid td.val { font-family: var(--display); font-size: 24px; font-weight: 700; white-space: nowrap; }
  .grid td.basis { color: var(--muted); }
  .grid .lbl { font-weight: 600; }
  .grid details { color: var(--muted); font-size: 13.5px; margin-top: 2px; }
  .grid summary { cursor: pointer; color: var(--sodium); font-size: 13.5px; }
  .grid summary:focus-visible { outline: 2px solid var(--sodium); outline-offset: 2px; }
  .tag { font-size: 12px; font-weight: 600; border: 1px solid var(--line); border-radius: 999px; padding: 1px 8px; color: var(--muted); margin-left: 6px; white-space: nowrap; }
  table.score { table-layout: fixed; }
  .score th:nth-child(1) { width: 50%; } .score th:nth-child(2) { width: 18%; }
  .fixes td { font-size: 15px; }
  .fixes .fid { color: var(--muted); font-size: 13px; display: block; }
  .fixes .src { color: var(--muted); font-size: 13px; display: block; margin-top: 4px; }
  .now { display: block; margin-top: 4px; font-weight: 600; }
  @media (max-width: 640px) {
    .fixes thead { display: none; }
    .fixes tr { display: block; padding: 12px 14px; border-bottom: 1px solid var(--line); }
    .fixes tr:last-child { border-bottom: 0; }
    .fixes td { display: block; border: 0; padding: 3px 0; }
    .fixes td[data-h]::before { content: attr(data-h); display: block; font-size: 12px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; }
    .grid td.val { font-size: 20px; }
    .grid th, .grid td { padding: 9px 10px; }
  }
  h3.group { font-size: 15px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.06em; margin: 18px 0 8px; }
  .gaps { margin: 0; padding-left: 20px; display: grid; gap: 6px; max-width: 72ch; }
  .ok { color: var(--clear); font-weight: 600; } .bad { color: var(--alarm); font-weight: 600; }
  @media (max-width: 560px) { .test dl { grid-template-columns: 1fr; gap: 0; } .test dd { margin-bottom: 8px; } }
</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <a class="brand" href="/demo">NightAgent</a>
    <nav><a href="/demo">Talk to Sam</a><a href="https://ky-gray-portfolio.vercel.app/">Back to Ky Gray's portfolio</a></nav>
  </header>

  <h1>Evaluation Lab</h1>
  <p class="intro">How well Sam, Jordan, and Riley do, measured from what really happened: test runs and real calls.
    Every number shows how many runs or calls it's based on. Tests and real calls are kept apart, because tests are
    controlled and real calls aren't. Anything judged by an AI grader is labeled that way.</p>

  <h2 class="section">Scorecard</h2>
  <h3 class="group">In tests</h3>
  <div id="sc-tests" aria-live="polite"><p class="fine">Loading…</p></div>
  <h3 class="group">On real calls</h3>
  <div id="sc-calls" aria-live="polite"><p class="fine">Loading…</p></div>

  <h2 class="section">What broke and how it was fixed</h2>
  <p class="intro">Every problem below really happened: in a live call, in a new test, or when we broke something on
    purpose. "Now" is read from the latest test runs, so if a fix stops holding, it shows here.</p>
  <div id="fixes" aria-live="polite"><p class="fine">Loading…</p></div>

  <h2 class="section">Regression tests</h2>
  <p class="intro">Most tests here started as a real problem found in a live call with Sam, Jordan, or Riley; the rest
    try something unexpected. Each one replays the conversation up to that moment and checks what the agent does next. They run in ElevenLabs Agent Testing against
    the live agents, three times each, because the same model can answer differently from one run to the next.</p>

  <div class="summary" id="summary" aria-live="polite"><div class="stat"><b>…</b><span>Loading the latest results</span></div></div>
  <div class="tests" id="tests"></div>

  <h2 class="section">Failure injection</h2>
  <p class="intro">Break something on purpose and check the system copes. Each scenario replays a known failure through
    the real server code, in a sandbox: nothing reaches the live board and no real texts are sent. How Sam talks about
    it is covered by the tests above.</p>
  <div class="tests">
    <section class="inject" data-scenario="duplicate-caller" aria-labelledby="dup-title">
      <h2 id="dup-title" style="margin:0;font-size:18px">Same caller twice</h2>
      <p class="meta" style="margin:0">A gate is stuck open. James calls; an emergency ticket is opened and the technician
        alerted. Twenty minutes later Dana, at the same site, calls about the same gate. Then the replay forces the mistake
        a model might make: alerting the technician a second time.</p>
      <p class="meta before" style="margin:0"></p>
      <button type="button">Run it</button>
      <div class="out" aria-live="polite"></div>
    </section>
    <section class="inject" data-scenario="paging-down" aria-labelledby="down-title">
      <h2 id="down-title" style="margin:0;font-size:18px">Alert service down</h2>
      <p class="meta" style="margin:0">Priya's main entrance won't unlock, so it's an emergency. The service that texts
        the on-call technician fails, twice. Later it comes back and the alert is sent.</p>
      <p class="meta before" style="margin:0"></p>
      <button type="button">Run it</button>
      <div class="out" aria-live="polite"></div>
    </section>
  </div>

  <h2 class="section">Not measured yet</h2>
  <ul class="gaps fine">
    <li><b>How Sam recovers when interrupted.</b> The scorecard counts interruptions, but grading the recovery needs tests with real audio; these tests are text.</li>
    <li><b>Silence.</b> What Sam does when a caller goes quiet also needs a real voice call to test.</li>
    <li><b>Speech-to-text confidence.</b> ElevenLabs doesn't give a confidence score for each thing the caller says.</li>
    <li><b>Hallucination in general.</b> One specific kind is measured, promises the tools didn't back up, and it's called that.</li>
  </ul>

  <p class="fine">Results are read from ElevenLabs. Tools aren't really called during a test, so tests never put tickets
    or messages on the live board. A reply check is judged by an AI grader against a written pass condition; a tool
    check compares the exact tool and values the agent chose.</p>
</div>
<script>
function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined && text !== null) n.textContent = text;
  return n;
}
function stat(big, small) { const d = el("div", "stat"); d.append(el("b", "", big), el("span", "", small)); return d; }
function row(dl, label, value) { if (!value) return; dl.append(el("dt", "", label)); const dd = el("dd"); dd.append(value); dl.append(dd); }
function said(example) {
  const box = el("span");
  box.append(el("span", "said", example.reply || "(no reply)"));
  if (example.judge) box.append(el("span", "judge", "Grader: " + example.judge));
  return box;
}
function when(unix) {
  if (!unix) return "";
  return new Date(unix * 1000).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}
function fmt(m) {
  if (m.value === null || m.value === undefined) return "–";
  if (m.unit === "%") return `${m.value}%`;
  if (m.unit === "ms") return `${(m.value / 1000).toFixed(1)} s`;
  if (m.unit === "usd") return `$${m.value.toFixed(3)}`;
  return String(m.value);
}
function sample(m) {
  if (!m.n) return "No data yet";
  if (m.unit === "%") return `${m.hits} of ${m.n}`;
  if (m.unit === "ms") return `typical of ${m.n} replies · slowest 10%: ${(m.slow / 1000).toFixed(1)} s`;
  if (m.unit === "usd") return `typical of ${m.n} calls · $${m.total.toFixed(2)} in all`;
  return `${m.n}`;
}
function scoreTable(box, metrics) {
  if (!metrics || !metrics.length) { box.replaceChildren(el("p", "fine", "Not available right now.")); return; }
  const t = el("table", "grid score"), head = el("tr");
  for (const h of ["Metric", "Value", "Based on"]) head.append(el("th", "", h));
  const thead = el("thead"); thead.append(head); const body = el("tbody");
  for (const m of metrics) {
    const tr = el("tr"), name = el("td");
    name.append(el("span", "lbl", m.label));
    if (m.how === "ai") name.append(el("span", "tag", "AI-judged"));
    const d = el("details"); d.append(el("summary", "", "How it's measured"), document.createTextNode(m.definition));
    name.append(d);
    tr.append(name, el("td", "val", fmt(m)), el("td", "basis", sample(m)));
    body.append(tr);
  }
  t.append(thead, body); box.replaceChildren(t);
}
function fixTable(box, fixes) {
  if (!fixes || !fixes.length) { box.replaceChildren(el("p", "fine", "Not available right now.")); return; }
  const t = el("table", "grid fixes"), head = el("tr");
  for (const h of ["What broke", "Why", "The fix", "Before → Now"]) head.append(el("th", "", h));
  const thead = el("thead"); thead.append(head); const body = el("tbody");
  for (const f of fixes) {
    const tr = el("tr");
    const what = el("td"); what.dataset.h = "What broke";
    what.append(el("span", "fid", `${f.id} · found in: ${f.found}`), el("span", "lbl", f.title));
    const why = el("td"); why.dataset.h = "Why";
    why.append(el("span", "lbl", f.cause_label), el("span", "src", f.why));
    const fix = el("td"); fix.dataset.h = "The fix";
    fix.append(document.createTextNode(f.fix), el("span", "src", f.where));
    const ba = el("td"); ba.dataset.h = "Before → Now";
    ba.append(el("span", "", "Before: " + f.before));
    const n = f.now;
    if (n.finished) {
      ba.append(el("span", "now " + (n.holding ? "ok" : "bad"),
        `Now: ${n.passed} of ${n.finished} test runs pass` + (n.holding ? "" : " (needs a look)")));
    } else if (f.scenario) {
      ba.append(el("span", "now", `Now: run "${f.scenario}" below`));
    }
    if (f.scenario && n.finished) ba.append(el("span", "src", `Also: "${f.scenario}" below`));
    if (f.proof) ba.append(el("span", "src", f.proof));
    tr.append(what, why, fix, ba); body.append(tr);
  }
  t.append(thead, body); box.replaceChildren(t);
}
async function load() {
  const summary = document.getElementById("summary"), list = document.getElementById("tests");
  let data;
  try { data = await (await fetch("/api/lab", { cache: "no-store" })).json(); } catch { data = { status: "unavailable" }; }
  const sc = data.scorecard || {};
  scoreTable(document.getElementById("sc-tests"), sc.tests);
  scoreTable(document.getElementById("sc-calls"), sc.calls);
  fixTable(document.getElementById("fixes"), data.fixes);
  if (data.status !== "ok") {
    summary.replaceChildren(stat("–", data.reason || "Results aren't available right now."));
    return;
  }
  const last = data.last_run;
  summary.replaceChildren(
    stat(data.pass_rate === null ? "–" : `${data.pass_rate}%`, "pass rate, latest runs"),
    stat(`${data.passed} of ${data.finished}`, "test runs passed"),
    stat(String(data.tests.length), "regression tests"),
    stat(when(last) || "–", "last run"),
  );
  if (data.pending) summary.append(stat(String(data.pending), "runs still in progress"));
  list.replaceChildren();
  for (const t of data.tests) {
    const card = el("article", "test");
    const head = el("div", "test-head");
    const title = el("div");
    title.append(el("h2", "", t.name.replace(/^QA-\d+\s*/, "")),
      el("div", "meta", `${t.agent} · ${t.kind}${t.ran_at ? " · run " + when(t.ran_at) : ""}`));
    const done = t.passed + t.failed;
    const cls = !done ? "" : t.failed === 0 ? "all" : t.passed === 0 ? "none" : "some";
    head.append(title, el("span", `score ${cls}`, done ? `${t.passed} of ${done} passed` : "Not run yet"));
    const dl = el("dl");
    row(dl, "Why it exists", t.why);
    row(dl, "What it checks", t.checks);
    if (t.example) row(dl, "What the agent did", said(t.example));
    if (t.failure) row(dl, "A failed run", said(t.failure));
    card.append(head, dl);
    list.append(card);
  }
}
load();

async function runScenario(box) {
  const btn = box.querySelector("button"), out = box.querySelector(".out");
  btn.disabled = true; btn.textContent = "Running…";
  try {
    const res = await fetch(`/api/lab/inject/${box.dataset.scenario}`, { method: "POST" });
    if (!res.ok) throw new Error();
    const r = await res.json();
    box.querySelector(".before").textContent = r.before;
    const steps = el("ol");
    for (const s of r.steps) {
      const li = el("li");
      li.append(el("b", "", `${s.who}: `), document.createTextNode(s.did));
      li.append(el("span", "said", " → " + JSON.stringify(s.result)));
      steps.append(li);
    }
    const checks = el("ul");
    for (const c of r.checks) {
      const li = el("li");
      li.append(el("span", c.passed ? "ok" : "bad", c.passed ? "✓ " : "✗ "), document.createTextNode(c.label),
        el("span", "judge", c.detail));
      checks.append(li);
    }
    const passed = r.checks.filter((c) => c.passed).length;
    const head = el("p", r.passed ? "ok" : "bad", `${r.passed ? "Passed" : "Failed"}: ${passed} of ${r.checks.length} checks`);
    out.replaceChildren(head, el("h3", "meta", "What happened"), steps, el("h3", "meta", "Checks"), checks);
    btn.textContent = "Run it again";
  } catch {
    out.replaceChildren(el("p", "bad", "Couldn't run the scenario just now."));
    btn.textContent = "Run it";
  }
  btn.disabled = false;
}
document.querySelectorAll(".inject").forEach((box) =>
  box.querySelector("button").addEventListener("click", () => runScenario(box)));
</script>
</body>
</html>
"""
