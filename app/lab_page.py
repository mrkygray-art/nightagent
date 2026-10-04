"""The public /lab page: the Evaluation Lab. Six cards at the top jump to the sections below: a
scorecard from tests and real calls, what broke and how it was fixed, regression tests built from real
problems found in live calls (latest results from ElevenLabs Agent Testing, read via /api/lab), failure
injection, what isn't measured yet, and the planned Test Inspector.
"""

LAB_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>NightAgent: Evaluation Lab</title>
<meta name="description" content="How NightAgent's voice agents are evaluated across scorecards, incidents, regression tests, failure injection, and known measurement gaps.">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' fill='%23101a2e'/%3E%3Ccircle cx='16' cy='16' r='7' fill='%23f5a524'/%3E%3C/svg%3E">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<meta name="theme-color" content="#101a2e">
<meta name="apple-mobile-web-app-title" content="NightAgent">
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
  html { scroll-behavior: smooth; scroll-padding-top: 18px; }
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
  .intro { color: var(--muted); max-width: 72ch; margin: 0 0 20px; }
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
  .lab-nav-title { font-family: var(--display); font-size: 24px; margin: 28px 0 6px; }
  .lab-nav-copy { color: var(--muted); margin: 0 0 14px; }
  .lab-nav { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin: 0 0 30px; }
  .nav-card {
    display: flex; flex-direction: column; min-height: 205px; padding: 20px; color: var(--text);
    background: var(--panel); border: 1px solid var(--line); border-radius: 16px; box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  }
  .nav-card h2 { font-family: var(--display); font-size: 24px; margin: 0 0 9px; }
  .nav-card p { color: var(--muted); font-size: 15px; line-height: 1.5; margin: 0 0 20px; }
  .nav-card .go {
    display: inline-flex; align-items: center; justify-content: center; align-self: flex-start; margin-top: auto;
    min-height: 46px; padding: 10px 17px; border-radius: 999px; background: var(--sodium); color: #1a1200;
    font-weight: 700; font-size: 14px; text-decoration: none; transition: filter 0.15s ease, transform 0.15s ease;
  }
  .nav-card .go:hover { filter: brightness(1.08); transform: translateY(-1px); }
  .nav-card .go:focus-visible { outline: 2px solid var(--text); outline-offset: 3px; }
  .nav-card.future { border-style: dashed; grid-column: 1 / -1; min-height: 0; }
  .nav-card.future .go { background: transparent; color: var(--sodium); border: 1px solid var(--sodium); }
  .nav-card .soon { display: inline-block; color: var(--muted); font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; margin-left: 6px; }
  .section-block { scroll-margin-top: 18px; border-top: 1px solid var(--line); padding-top: 2px; margin-top: 38px; }
  .section-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
  .section-head a { font-size: 13px; text-decoration: none; margin-top: 45px; white-space: nowrap; }
  .section-head a:hover { text-decoration: underline; }
  .question { color: var(--sodium); font-size: 14px; font-weight: 600; margin: -10px 0 20px; }
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
  .voice td.num { font-family: var(--display); font-size: 20px; font-weight: 700; white-space: nowrap; }
  .voice .quote { display: block; color: #cfd6e4; font-size: 14px; margin-top: 4px; }
  .bad-note { border-left: 3px solid var(--alarm); padding-left: 10px; }
  @media (max-width: 640px) {
    .voice thead { display: none; }
    .voice tr { display: block; padding: 12px 14px; border-bottom: 1px solid var(--line); }
    .voice tr:last-child { border-bottom: 0; }
    .voice td { display: block; border: 0; padding: 3px 0; }
    .voice td[data-h]::before { content: attr(data-h); display: block; font-size: 12px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; }
  }
  @media (max-width: 640px) {
    .wrap { padding-left: 14px; padding-right: 14px; }
    .top { align-items: flex-start; }
    .top nav { gap: 6px 14px; }
    .lab-nav { grid-template-columns: 1fr; gap: 14px; }
    .nav-card { min-height: 0; padding: 18px; }
    .nav-card h2 { font-size: 23px; }
    .nav-card p { margin-bottom: 18px; }
    .nav-card .go { width: 100%; min-height: 48px; padding: 11px 16px; }
    .section-head a { display: none; }
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
  @media (max-width: 390px) {
    .nav-card { padding: 16px; }
    .nav-card h2 { font-size: 22px; }
    .nav-card .go { border-radius: 12px; }
  }
</style>
</head>
<body>
<div class="wrap" id="top">
  <header class="top">
    <a class="brand" href="/demo">NightAgent</a>
    <nav><a href="/demo">Talk to Sam</a><a href="https://ky-gray-portfolio.vercel.app/">Back to Ky Gray's portfolio</a></nav>
  </header>

  <h1>Evaluation Lab</h1>
  <p class="intro">How well Sam, Jordan, and Riley do, measured from what really happened: test runs and real calls.
    Every number shows how many runs or calls it's based on. Tests and real calls are kept apart because tests are
    controlled and real calls aren't. Anything judged by an AI grader is labeled that way.</p>

  <h2 class="lab-nav-title">Explore the lab</h2>
  <p class="lab-nav-copy">Each section answers a different engineering question about whether NightAgent can be trusted
    with real customer conversations.</p>
  <nav class="lab-nav" aria-label="Evaluation Lab sections">
    <article class="nav-card">
      <h2>Scorecard</h2>
      <p>See how NightAgent performs across controlled tests and real calls. This section keeps the evidence behind
        each metric visible so you can tell whether agent behavior is improving, stable, or regressing.</p>
      <a class="go" href="#scorecard">View Scorecard ↓</a>
    </article>
    <article class="nav-card">
      <h2>What Broke &amp; How We Fixed It</h2>
      <p>Review real problems uncovered by live calls, tests, or deliberate breakage. See what caused each issue, what
        changed, and whether the fix is still holding today.</p>
      <a class="go" href="#incidents">View Engineering Incidents ↓</a>
    </article>
    <article class="nav-card">
      <h2>Regression Tests</h2>
      <p>Replay known scenarios against the live agents to make sure changes to prompts, models, tools, or workflows do
        not bring previously solved failures back.</p>
      <a class="go" href="#regression">View Regression Tests ↓</a>
    </article>
    <article class="nav-card">
      <h2>Voice Tests</h2>
      <p>Real recorded speech sent to the live agent: phone numbers and names in noise and over a phone line, talking
        over Sam, going quiet, and how long the caller waits for an answer.</p>
      <a class="go" href="#voice">View Voice Tests ↓</a>
    </article>
    <article class="nav-card">
      <h2>Failure Injection</h2>
      <p>Intentionally break parts of the workflow in a controlled sandbox. These tests verify that NightAgent fails
        safely, avoids duplicate actions, and recovers when a dependency comes back.</p>
      <a class="go" href="#failure">Run Failure Tests ↓</a>
    </article>
    <article class="nav-card">
      <h2>Not Measured Yet</h2>
      <p>See where the Evaluation Lab still has blind spots. This section separates what NightAgent can actually prove
        from assumptions and identifies where better instrumentation is still needed.</p>
      <a class="go" href="#gaps">View Measurement Gaps ↓</a>
    </article>
    <article class="nav-card future">
      <h2>Test Inspector <span class="soon">planned</span></h2>
      <p>Coming next: drill into an individual evaluation to compare expected and actual behavior, inspect tool
        decisions, and understand exactly why a test passed or failed.</p>
      <a class="go" href="#next">See What's Coming Next ↓</a>
    </article>
  </nav>

  <section class="section-block" id="scorecard">
    <div class="section-head"><h2 class="section">Scorecard</h2><a href="#top">Back to lab menu ↑</a></div>
    <p class="intro">The Scorecard provides a high-level view of NightAgent's current quality. It keeps controlled test
      results separate from real-call outcomes so the evidence behind each metric stays clear.</p>
    <p class="question">Engineering question: Can we trust the current version?</p>
    <h3 class="group">In tests</h3>
    <div id="sc-tests" aria-live="polite"><p class="fine">Loading…</p></div>
    <h3 class="group">On real calls</h3>
    <div id="sc-calls" aria-live="polite"><p class="fine">Loading…</p></div>
  </section>

  <section class="section-block" id="incidents">
    <div class="section-head"><h2 class="section">Engineering Incidents</h2><a href="#top">Back to lab menu ↑</a></div>
    <p class="intro"><b>What broke and how it was fixed.</b> Real-world testing exposes problems scripted demos often
      miss. Every problem below happened in a live call, a new test, or when we broke something on purpose. "Now" is
      read from the latest test runs, so if a fix stops holding, it shows here.</p>
    <p class="question">Engineering question: What did we learn from failure?</p>
    <div id="fixes" aria-live="polite"><p class="fine">Loading…</p></div>
  </section>

  <section class="section-block" id="regression">
    <div class="section-head"><h2 class="section">Regression Tests</h2><a href="#top">Back to lab menu ↑</a></div>
    <p class="intro">Most tests here started as a real problem found in a live call with Sam, Jordan, or Riley; the rest
      try something unexpected. Each one replays the conversation up to that moment and checks what the agent does
      next. They run in ElevenLabs Agent Testing against the live agents, three times each, because the same model can
      answer differently from one run to the next.</p>
    <p class="question">Engineering question: Did our changes break something that previously worked?</p>
    <div class="summary" id="summary" aria-live="polite"><div class="stat"><b>…</b><span>Loading the latest results</span></div></div>
    <div class="tests" id="tests"></div>
  </section>

  <section class="section-block" id="voice">
    <div class="section-head"><h2 class="section">Voice Tests</h2><a href="#top">Back to lab menu ↑</a></div>
    <p class="intro">The tests above are text. These use real audio: a test caller phones the live Sam the same way the
      demo page does and plays recorded speech, 20 milliseconds at a time, like a microphone. The callers are ElevenLabs
      voices, so no real customer is involved. Each call stops before a ticket is made, and these calls are left out of
      the real-call numbers.</p>
    <p class="question">Engineering question: Does it still work when the caller is hard to hear, talks over Sam, or goes quiet?</p>
    <div id="voice-box" aria-live="polite"><p class="fine">Loading…</p></div>
  </section>

  <section class="section-block" id="failure">
    <div class="section-head"><h2 class="section">Failure Injection</h2><a href="#top">Back to lab menu ↑</a></div>
    <p class="intro">Break something on purpose and check the system copes. Each scenario replays a known failure through
      the real server code in a sandbox: nothing reaches the live board and no real texts are sent. How Sam talks about
      it is covered by the regression tests above.</p>
    <p class="question">Engineering question: What happens when something goes wrong?</p>
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
  </section>

  <section class="section-block" id="gaps">
    <div class="section-head"><h2 class="section">Known Measurement Gaps</h2><a href="#top">Back to lab menu ↑</a></div>
    <p class="intro"><b>What we don't measure yet.</b> Responsible evaluation means distinguishing measured results from
      assumptions. These are signals NightAgent cannot currently verify reliably and areas where better instrumentation
      is still needed.</p>
    <p class="question">Engineering question: What don't we know?</p>
    <ul class="gaps fine">
      <li><b>Interruptions and silence on real calls.</b> The voice tests check both with recorded callers. On real calls they're only counted, not graded.</li>
      <li><b>Speech-to-text confidence.</b> ElevenLabs doesn't give a confidence score for each thing the caller says. The voice tests check instead whether phone numbers and names come through exactly.</li>
      <li><b>Real accents and real phones.</b> The voice tests use three recorded voices and a simulated phone line, not callers on real phone networks.</li>
      <li><b>Hallucination in general.</b> One specific kind is measured—promises the tools didn't back up—and it's called that.</li>
    </ul>
    <p class="fine">Results are read from ElevenLabs. Tools aren't really called during an agent test, so tests never put
      tickets or messages on the live board. A reply check is judged by an AI grader against a written pass condition; a
      tool check compares the exact tool and values the agent chose.</p>
  </section>

  <section class="section-block" id="next">
    <div class="section-head"><h2 class="section">Next: Test Inspector</h2><a href="#top">Back to lab menu ↑</a></div>
    <p class="intro">The next Evaluation Lab feature will go beyond PASS or FAIL and make an individual test explainable:
      expected behavior, actual behavior, conversation context, tool choices, evaluator decisions, and any timing or
      execution data NightAgent can reliably capture.</p>
    <p class="question">Engineering question: Why did this test pass or fail?</p>
    <p class="fine">This section is intentionally labeled planned. No telemetry or execution details will be presented as
      measured until NightAgent actually captures them.</p>
  </section>
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
function secs(ms) { return ms === null || ms === undefined ? "–" : `${(ms / 1000).toFixed(1)} s`; }
function gridTable(cls, heads, rows) {
  const t = el("table", `grid ${cls}`), head = el("tr");
  for (const h of heads) head.append(el("th", "", h));
  const thead = el("thead"); thead.append(head); const body = el("tbody");
  for (const cells of rows) {
    const tr = el("tr");
    cells.forEach((c, i) => {
      const td = el("td", c.cls || "");
      td.dataset.h = heads[i];
      if (c.node) td.append(c.node); else td.textContent = c.text;
      tr.append(td);
    });
    body.append(tr);
  }
  t.append(thead, body);
  return t;
}
function voiceSection(box, v) {
  if (!v || v.status !== "ok") { box.replaceChildren(el("p", "fine", "No voice test run saved yet.")); return; }
  const of = (x, n) => ({ text: `${x} of ${n}`, cls: "num" });
  const out = [el("h3", "group", "Phone numbers and names in noise")];
  out.push(el("p", "fine", "Three callers say their name, business, and the phone number on the account. " +
    "\"Heard\" is the transcript from ElevenLabs' speech-to-text; \"read back\" is Sam saying the number back."));
  out.push(gridTable("voice", ["Condition", "Number heard exactly", "Name heard", "Sam read back the right number", "Caller waited (typical)"],
    v.numbers.map((r) => [{ text: r.condition, cls: "lbl" }, of(r.number_heard, r.calls), of(r.name_heard, r.calls),
      of(r.read_back_right, r.calls), { text: r.response.n ? secs(r.response.typical_ms) : "–", cls: "num" }])));
  const total = (k) => v.numbers.reduce((a, r) => a + r[k], 0);
  out.push(el("p", "fine", `In ${total("turn_split")} of ${total("calls")} calls the caller's short pause after the number ` +
    `ended their turn early, and in ${total("started_early")} of ${total("calls")} Sam started speaking before the caller ` +
    "had finished."));
  const misses = v.numbers.flatMap((r) => r.misses.map((m) => [`${r.condition}. Heard: "${m.heard}"`, `Sam: "${m.reply}"`]));
  if (misses.length) {
    const d = el("details", "fine"); d.append(el("summary", "", "The calls that missed something: what was heard, and what Sam said"));
    for (const [heard, reply] of misses.slice(0, 6)) { d.append(el("span", "quote", heard), el("span", "judge", reply)); }
    out.push(d);
  }
  out.push(el("h3", "group", "Talking over Sam and going quiet"));
  const i = v.interruption, s = v.silence;
  const quote = (label, text) => {
    const n = el("span"); n.append(document.createTextNode(label));
    if (text) n.append(el("span", "quote", `"${text}"`));
    return n;
  };
  const checkIn = ((s.example.spoke_during_silence || [])[1] || {}).text;
  out.push(gridTable("voice", ["Test", "Passed", "Timing", "What Sam did"], [
    [{ text: "Caller talks over Sam's read-back with the real problem", cls: "lbl" }, of(i.passed, i.runs),
     { text: `stopped in ${secs(i.timing.typical_ms)} (typical)` },
     { node: quote("Stopped, then answered about the door:", i.example.reply) }],
    [{ text: "Caller stops mid-sentence and goes quiet for 25 s", cls: "lbl" }, of(s.passed, s.runs),
     { text: `checked in after ${secs(s.timing.typical_ms)} of silence (typical)` },
     { node: quote("Waited, asked what was wrong, then checked in:", checkIn) }],
  ]));
  const failed = [...i.failures.map((f) => `Talking over Sam, a failed run. Sam stopped, then said: "${f.reply}"`),
    ...s.failures.map((f) => `Going quiet, a failed run. ${f.hung_up ? "The call ended." : `Sam said: "${f.reply}"`}`)];
  for (const f of failed) out.push(el("p", "fine bad-note", f));
  out.push(el("h3", "group", "How long the caller waits"));
  const rt = v.response_time;
  const rtRow = (label, x) => [{ text: label, cls: "lbl" }, { text: secs(x.typical_ms), cls: "num" },
    { text: secs(x.slow_ms), cls: "num" }, { text: `${x.n} replies` }];
  out.push(gridTable("voice", ["Replies", "Typical", "Slowest 10%", "Based on"],
    [rtRow("All voice-test replies", rt.all), rtRow("Quiet room", rt.quiet), rtRow("With noise or a phone line", rt.noisy)]));
  out.push(el("p", "fine", "From the end of the caller's last word to the first sound of Sam's reply, timed by the test " +
    "caller. It includes the network between the test computer and ElevenLabs and the time Sam spends looking up the " +
    "account. The scorecard's \"Response time\" on real calls is ElevenLabs' own timing."));
  out.push(el("p", "fine", `Last run ${when(v.run_at)}. Voices: ${v.voices.join("; ")}. Re-run with node voicelab/run.js.`));
  box.replaceChildren(...out);
}
async function load() {
  const summary = document.getElementById("summary"), list = document.getElementById("tests");
  let data;
  try { data = await (await fetch("/api/lab", { cache: "no-store" })).json(); } catch { data = { status: "unavailable" }; }
  const sc = data.scorecard || {};
  scoreTable(document.getElementById("sc-tests"), sc.tests);
  scoreTable(document.getElementById("sc-calls"), sc.calls);
  fixTable(document.getElementById("fixes"), data.fixes);
  voiceSection(document.getElementById("voice-box"), data.voice);
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
<script>
// Home-screen app: the service worker lets NightAgent open from its icon (see app/pwa.py)
if ("serviceWorker" in navigator) addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => {}));
</script>
</body>
</html>
"""
