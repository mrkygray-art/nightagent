"""The public /lab page: the Agent QA Lab. Regression tests built from real problems found in
live calls, with their latest real results from ElevenLabs Agent Testing (read via /api/lab).
"""

LAB_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>NightAgent: Agent QA Lab</title>
<meta name="description" content="Regression tests for NightAgent's voice agents, each built from a real problem found in a live call, with their latest results.">
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
  @media (max-width: 560px) { .test dl { grid-template-columns: 1fr; gap: 0; } .test dd { margin-bottom: 8px; } }
</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <a class="brand" href="/demo">NightAgent</a>
    <nav><a href="/demo">Talk to Sam</a><a href="https://ky-gray-portfolio.vercel.app/">Back to Ky Gray's portfolio</a></nav>
  </header>

  <h1>Agent QA Lab</h1>
  <p class="intro">Every test here started as a real problem found in a live call with Sam or Jordan. Each one replays
    the conversation up to that moment and checks what the agent does next. They run in ElevenLabs Agent Testing against
    the live agents, three times each, because the same model can answer differently from one run to the next.</p>

  <div class="summary" id="summary" aria-live="polite"><div class="stat"><b>…</b><span>Loading the latest results</span></div></div>
  <div class="tests" id="tests"></div>

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
async function load() {
  const summary = document.getElementById("summary"), list = document.getElementById("tests");
  let data;
  try { data = await (await fetch("/api/lab", { cache: "no-store" })).json(); } catch { data = { status: "unavailable" }; }
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
</script>
</body>
</html>
"""
