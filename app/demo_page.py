"""The public /demo page: talk to Sam (voice or text), watch the dispatch board update, and
follow a ticket through its whole service lifecycle in Demo Mode.

Kept as a Python string so it always ships with the serverless function.
__AGENT_ID__ is replaced at request time with the configured agent ID.
"""

DEMO_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>NightAgent: AI service lifecycle demo</title>
<meta name="description" content="Talk to Sam, the NightAgent voice, report a problem, and follow the service ticket from the first call through dispatch, repair, and follow-up.">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' fill='%23101a2e'/%3E%3Ccircle cx='16' cy='16' r='7' fill='%23f5a524'/%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700&family=Barlow:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root {
    --night: #101a2e;
    --panel: #172440;
    --panel-2: #1d2d4f;
    --line: #2b3d63;
    --text: #e9edf5;
    --muted: #a3afc6;
    --sodium: #f5a524;
    --sodium-soft: rgba(245, 165, 36, 0.16);
    --alarm: #e5484d;
    --clear: #4cb782;
    --radius-lg: 18px;
    --radius-sm: 8px;
    --body: "Barlow", system-ui, -apple-system, "Segoe UI", sans-serif;
    --display: "Barlow Condensed", "Arial Narrow", system-ui, sans-serif;
    color-scheme: dark;
  }
  * { box-sizing: border-box; }
  html { scroll-padding-top: env(safe-area-inset-top, 0px); }
  body {
    margin: 0;
    background: var(--night);
    color: var(--text);
    font-family: var(--body);
    font-size: 16px;
    line-height: 1.5;
    padding-top: env(safe-area-inset-top, 0px);
    padding-bottom: env(safe-area-inset-bottom, 0px);
    font-variant-numeric: tabular-nums;
  }
  a { color: var(--sodium); }
  a:focus-visible, button:focus-visible, input:focus-visible, summary:focus-visible {
    outline: 2px solid var(--sodium);
    outline-offset: 2px;
  }
  .sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }

  .wrap { max-width: 1180px; margin: 0 auto; padding: 0 20px; }
  .top { display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 18px 0; border-bottom: 1px solid var(--line); }
  .brand { font-family: var(--display); font-weight: 700; font-size: 22px; letter-spacing: 0.02em; color: var(--text); text-decoration: none; }
  .top nav { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 6px 18px; }
  .top nav a { font-weight: 500; text-decoration: none; }
  .top nav a:hover { text-decoration: underline; }

  .intro { padding: 40px 0 28px; max-width: 64ch; }
  h1 {
    font-family: var(--display);
    font-weight: 700;
    font-size: clamp(40px, 7vw, 72px);
    line-height: 0.95;
    margin: 0 0 16px;
    letter-spacing: -0.01em;
  }
  .nowrap { white-space: nowrap; }
  .intro p { margin: 0; color: var(--muted); font-size: 18px; }

  .grid { display: grid; grid-template-columns: minmax(0, 5fr) minmax(0, 7fr); gap: 24px; align-items: start; }
  @media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }

  .console, .board { background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius-lg); }
  .console { padding: 22px; display: flex; flex-direction: column; gap: 18px; }

  /* The one memorable element: the call key and its lamp. */
  .callbar { display: flex; align-items: center; gap: 14px; }
  .lamp {
    flex: none; width: 14px; height: 14px; border-radius: 50%;
    background: #3a4a6b; box-shadow: inset 0 0 0 2px rgba(0,0,0,.25);
    transition: background .2s, box-shadow .2s;
  }
  .lamp[data-state="connecting"] { background: var(--muted); }
  .lamp[data-state="listening"] { background: var(--clear); box-shadow: 0 0 0 4px rgba(76,183,130,.18); }
  .lamp[data-state="speaking"] { background: var(--sodium); box-shadow: 0 0 0 6px var(--sodium-soft), 0 0 22px rgba(245,165,36,.55); animation: glow 1.2s ease-in-out infinite; }
  @keyframes glow { 50% { box-shadow: 0 0 0 10px var(--sodium-soft), 0 0 30px rgba(245,165,36,.7); } }
  .status { display: flex; flex-direction: column; min-width: 0; flex: 1; }
  .status strong { font-weight: 600; }
  .status span { color: var(--muted); font-size: 14px; }

  .mode { display: inline-flex; background: var(--night); border: 1px solid var(--line); border-radius: 999px; padding: 3px; flex: none; }
  .mode button {
    font: 500 14px var(--body); color: var(--muted); background: transparent; border: 0;
    padding: 6px 14px; border-radius: 999px; cursor: pointer;
  }
  .mode button[aria-pressed="true"] { background: var(--panel-2); color: var(--text); }
  .mode button:disabled { cursor: not-allowed; opacity: .6; }

  .call {
    width: 100%; border: 0; cursor: pointer;
    font-family: var(--display); font-weight: 700; font-size: 26px; letter-spacing: 0.02em;
    padding: 18px 20px; border-radius: 14px;
    background: var(--sodium); color: #1a1205;
    box-shadow: inset 0 -4px 0 rgba(0,0,0,.18);
    transition: transform .08s, background .2s;
  }
  .call:hover { background: #ffb43b; }
  .call:active { transform: translateY(2px); box-shadow: inset 0 -2px 0 rgba(0,0,0,.18); }
  .call[data-live="true"] { background: var(--alarm); color: #fff; }
  .call[data-ring="true"] { background: var(--clear); color: #04210f; animation: ring-shake 1.2s ease-in-out infinite, ring-glow 1.2s ease-in-out infinite; }
  @keyframes ring-shake { 0%, 50%, 100% { transform: rotate(0); } 5%, 15%, 25% { transform: rotate(-1.4deg); } 10%, 20%, 30% { transform: rotate(1.4deg); } }
  @keyframes ring-glow { 0%, 100% { box-shadow: 0 0 0 0 rgba(76,183,130,.55); } 50% { box-shadow: 0 0 0 12px rgba(76,183,130,0); } }
  .lamp[data-state="ringing"] { background: var(--clear); box-shadow: 0 0 0 6px rgba(76,183,130,.25); animation: glow 1.2s ease-in-out infinite; }
  .call:disabled { opacity: .65; cursor: progress; }

  .mic { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .mic[hidden] { display: none; }
  .mic label { color: var(--muted); font-size: 14px; flex: none; }
  .mic select {
    flex: 1; min-width: 0; font: 500 15px var(--body); color: var(--text);
    background: var(--night); border: 1px solid var(--line); border-radius: 10px; padding: 9px 12px;
  }
  .mic select:disabled { opacity: .6; }
  .mic button {
    font: 500 14px var(--body); color: var(--sodium); background: transparent; border: 0;
    padding: 6px 2px; cursor: pointer; text-decoration: underline;
  }

  .sound {
    width: 100%; border: 2px solid var(--sodium); cursor: pointer;
    font: 600 17px var(--body); padding: 12px 16px; border-radius: 12px;
    background: var(--sodium-soft); color: var(--text);
  }
  .sound[hidden] { display: none; }

  .error { margin: 0; padding: 10px 12px; border-radius: var(--radius-sm); background: rgba(229,72,77,.14); border: 1px solid rgba(229,72,77,.45); color: #ffd7d8; font-size: 14px; }
  .error[hidden] { display: none; }

  details.accounts { border: 1px solid var(--line); border-radius: 12px; padding: 4px 14px; background: var(--night); }
  details.accounts summary { cursor: pointer; padding: 10px 0; font-weight: 600; }
  .accounts ul { list-style: none; margin: 0 0 10px; padding: 0; display: grid; gap: 10px; }
  .accounts li { display: grid; gap: 2px; padding: 10px 0; border-top: 1px solid var(--line); }
  .accounts li:first-child { border-top: 0; }
  .accounts .who { display: flex; justify-content: space-between; gap: 10px; flex-wrap: wrap; font-weight: 600; }
  .accounts .who span { color: var(--muted); font-weight: 500; }
  .accounts .say { color: var(--muted); font-size: 14px; }

  .transcript {
    min-height: 180px; max-height: 360px; overflow-y: auto;
    display: flex; flex-direction: column; gap: 10px;
    padding: 4px 2px;
  }
  @media (max-width: 900px) { .transcript { min-height: 110px; } }
  .empty { color: var(--muted); font-size: 15px; margin: auto 0; text-align: center; padding: 24px 8px; }
  .msg { max-width: 88%; padding: 10px 14px; border-radius: 14px; font-size: 15px; }
  .msg b { display: block; font-size: 12px; font-weight: 600; color: var(--muted); margin-bottom: 2px; }
  .msg.sam { align-self: flex-start; background: var(--panel-2); border-bottom-left-radius: 4px; }
  .msg.you { align-self: flex-end; background: var(--sodium-soft); border: 1px solid rgba(245,165,36,.35); border-bottom-right-radius: 4px; }
  .msg.note { align-self: center; background: transparent; color: var(--muted); font-size: 13px; padding: 2px 8px; }

  .composer { display: flex; gap: 8px; }
  .composer input {
    flex: 1; min-width: 0; font: 400 16px var(--body); color: var(--text);
    background: var(--night); border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px;
  }
  .composer input::placeholder { color: #7f8aa3; }
  .composer button {
    font: 600 15px var(--body); color: var(--text); background: var(--panel-2);
    border: 1px solid var(--line); border-radius: 10px; padding: 0 18px; cursor: pointer;
  }
  .fine { margin: 0; color: var(--muted); font-size: 13px; }

  .board { padding: 22px; }
  .board-head { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; margin-bottom: 14px; }
  h2 { font-family: var(--display); font-weight: 700; font-size: 30px; margin: 0; letter-spacing: 0.01em; }
  .live { color: var(--muted); font-size: 14px; display: inline-flex; align-items: center; gap: 8px; }
  .live::before { content: ""; width: 8px; height: 8px; border-radius: 50%; background: var(--clear); }

  .tickets {
    list-style: none; margin: 0; padding: 0 4px 0 0; display: grid; gap: 12px; align-content: start;
    max-height: 640px; overflow-y: auto; overscroll-behavior: contain; scrollbar-width: thin;
    scrollbar-color: var(--line) transparent;
  }
  @media (max-width: 900px) { .tickets { max-height: 430px; } }
  .ticket {
    display: grid; grid-template-columns: 6px 1fr; border-radius: 12px; overflow: hidden;
    background: var(--night); border: 1px solid var(--line);
  }
  .ticket .bar { background: var(--muted); }
  .ticket[data-priority="emergency"] .bar { background: var(--alarm); }
  .ticket[data-priority="urgent"] .bar { background: var(--sodium); }
  .ticket[data-priority="routine"] .bar { background: var(--clear); }
  .ticket .body { padding: 14px 16px; display: grid; gap: 8px; min-width: 0; }
  .ticket .row1 { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; }
  .ticket .id { font-family: var(--display); font-weight: 700; font-size: 22px; }
  .chip { font-size: 13px; font-weight: 600; padding: 2px 10px; border-radius: 999px; border: 1px solid var(--line); color: var(--muted); }
  .chip.emergency { background: var(--alarm); border-color: var(--alarm); color: #fff; }
  .chip.urgent { border-color: var(--sodium); color: var(--sodium); }
  .chip.routine { border-color: var(--clear); color: var(--clear); }
  .chip.mine { border-color: var(--sodium); background: var(--sodium-soft); color: var(--text); }
  .ticket .when { color: var(--muted); font-size: 14px; margin-left: auto; }
  .ticket .issue { margin: 0; }
  .ticket .meta { color: var(--muted); font-size: 14px; display: flex; flex-wrap: wrap; gap: 4px 16px; }
  .ticket .summary { margin: 0; font-size: 14px; color: var(--muted); border-top: 1px dashed var(--line); padding-top: 8px; }
  .ticket.fresh { animation: arrive 2.4s ease-out; }
  @keyframes arrive { 0% { border-color: var(--sodium); box-shadow: 0 0 0 3px var(--sodium-soft); } 100% { border-color: var(--line); box-shadow: none; } }
  .board .empty { border: 1px dashed var(--line); border-radius: 12px; }

  .ticket { cursor: pointer; }
  .ticket:hover { border-color: #3b5288; }
  .ticket[aria-current="true"] { border-color: var(--sodium); box-shadow: 0 0 0 1px var(--sodium); }
  .chip.stage { border-color: #3b5288; color: var(--text); white-space: nowrap; }
  .chip.demo { border-style: dashed; }

  /* ---------- Demo Mode: the service lifecycle ---------- */
  .life { margin-top: 28px; background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius-lg); overflow: hidden; scroll-margin-top: 12px; }
  .life-banner {
    display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 14px; padding: 12px 22px;
    background: repeating-linear-gradient(135deg, rgba(245,165,36,.16) 0 14px, rgba(245,165,36,.08) 14px 28px);
    border-bottom: 1px solid rgba(245,165,36,.45);
  }
  .life-banner strong { font-family: var(--display); font-size: 20px; letter-spacing: .06em; color: var(--sodium); }
  .life-banner span { color: var(--muted); font-size: 14px; }
  .life-body { display: grid; grid-template-columns: minmax(0, 4fr) minmax(0, 8fr); gap: 24px; padding: 22px; }
  @media (max-width: 900px) { .life-body { grid-template-columns: 1fr; } }
  .life h2 { margin-bottom: 4px; }
  .life .lead { margin: 0 0 14px; color: var(--muted); font-size: 15px; }
  .scenarios { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; }
  .scenarios button {
    width: 100%; text-align: left; cursor: pointer; display: grid; gap: 2px;
    background: var(--night); color: var(--text); border: 1px solid var(--line); border-radius: 12px; padding: 12px 14px;
    font: 400 14px var(--body);
  }
  .scenarios button:hover { border-color: var(--sodium); }
  .scenarios button:disabled { opacity: .6; cursor: progress; }
  .scenarios b { font-size: 16px; font-weight: 600; }
  .scenarios span { color: var(--muted); }

  .event-panel { background: var(--night); border: 1px solid var(--line); border-radius: 14px; padding: 18px; min-height: 260px; display: grid; gap: 14px; align-content: start; min-width: 0; }
  .event-panel .empty { margin: auto; }
  .ev-head { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; }
  .ev-head .id { font-family: var(--display); font-weight: 700; font-size: 28px; }
  .ev-issue { margin: 0; }
  .ev-meta { color: var(--muted); font-size: 14px; display: flex; flex-wrap: wrap; gap: 4px 16px; }

  .stages { list-style: none; margin: 0; padding: 0 0 4px; display: flex; gap: 4px; overflow-x: auto; }
  .stages li {
    flex: 1 0 auto; min-width: 74px; text-align: center; font-size: 12px; font-weight: 600; color: var(--muted);
    padding: 8px 6px 0; border-top: 4px solid var(--line);
  }
  .stages li.done { border-top-color: var(--clear); color: var(--text); }
  .stages li.now { border-top-color: var(--sodium); color: var(--sodium); }

  .ev-actions { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
  .advance {
    border: 0; cursor: pointer; font-family: var(--display); font-weight: 700; font-size: 20px; letter-spacing: .02em;
    padding: 10px 18px; border-radius: 12px; background: var(--sodium); color: #1a1205; box-shadow: inset 0 -3px 0 rgba(0,0,0,.18);
  }
  .advance:disabled { opacity: .55; cursor: not-allowed; }
  .reset, .step { font: 500 14px var(--body); color: var(--muted); background: transparent; border: 1px solid var(--line); border-radius: 10px; padding: 9px 14px; cursor: pointer; }
  .reset:hover, .step:hover { color: var(--text); }
  .advance.answer { background: var(--clear); color: #04210f; animation: ring-glow 1.2s ease-in-out infinite; }
  .running { display: inline-flex; align-items: center; gap: 8px; color: var(--text); font-size: 15px; font-weight: 600; }
  .running::before { content: ""; width: 10px; height: 10px; border-radius: 50%; background: var(--sodium); animation: glow 1.2s ease-in-out infinite; }
  .ev-note { color: var(--muted); font-size: 14px; margin: 0; }

  .timeline { list-style: none; margin: 0; padding: 0; display: grid; }
  .timeline li { display: grid; grid-template-columns: 74px 18px 1fr; gap: 0 10px; }
  .timeline time { color: var(--muted); font-size: 13px; text-align: right; padding-top: 1px; white-space: nowrap; }
  .timeline .dot { position: relative; }
  .timeline .dot::before { content: ""; position: absolute; left: 4px; top: 5px; width: 10px; height: 10px; border-radius: 50%; background: var(--clear); }
  .timeline .dot::after { content: ""; position: absolute; left: 8px; top: 17px; bottom: -3px; width: 2px; background: var(--line); }
  .timeline li:last-child .dot::after { display: none; }
  .timeline li.sim .dot::before { background: transparent; border: 2px solid var(--sodium); }
  .timeline li.latest .dot::before { box-shadow: 0 0 0 4px var(--sodium-soft); }
  .timeline .what { padding-bottom: 14px; min-width: 0; }
  .timeline .what b { font-weight: 600; }
  .timeline .what p { margin: 2px 0 0; color: var(--muted); font-size: 14px; }
  .tag-sim { font-size: 11px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; color: var(--sodium); border: 1px solid rgba(245,165,36,.5); border-radius: 999px; padding: 0 7px; margin-left: 6px; vertical-align: 1px; }
  @media (max-width: 560px) { .timeline li { grid-template-columns: 60px 16px 1fr; gap: 0 8px; } }

  .follow-box { border: 1px solid rgba(245,165,36,.45); background: var(--sodium-soft); border-radius: 12px; padding: 12px 14px; display: grid; gap: 8px; }
  .follow-box p { margin: 0; font-size: 14px; }
  .follow-box .say { font-style: italic; color: var(--text); }
  .follow-box ul { margin: 0; padding-left: 18px; color: var(--muted); font-size: 14px; }
  .actions { display: grid; gap: 10px; }
  .actions h3 { margin: 0; font-family: var(--display); font-size: 22px; letter-spacing: .01em; }
  .action { border: 1px solid var(--line); border-left: 4px solid var(--clear); border-radius: 10px; padding: 10px 12px; display: grid; gap: 2px; font-size: 14px; }
  .action.high { border-left-color: var(--alarm); }
  .action.opp { border-left-color: var(--sodium); }
  .action b { font-size: 15px; }
  .action span { color: var(--muted); }
  .action button { justify-self: start; font: 600 14px var(--body); color: var(--sodium); background: transparent; border: 0; padding: 2px 0; cursor: pointer; text-decoration: underline; }

  .impact { margin-top: 28px; }
  .impact-head { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: baseline; gap: 6px 16px; margin-bottom: 6px; }
  .impact-note { margin: 0 0 16px; color: var(--muted); font-size: 14px; max-width: 80ch; }
  .metrics { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 12px; }
  .metric { background: var(--panel); border: 1px solid var(--line); border-radius: 14px; padding: 14px 16px; display: grid; gap: 2px; align-content: start; }
  .metric b { font-family: var(--display); font-size: 34px; line-height: 1; }
  .metric span { font-weight: 600; font-size: 14px; }
  .metric small { color: var(--muted); font-size: 13px; }
  .metric.key { border-color: rgba(245,165,36,.55); }
  .metric.key b { color: var(--sodium); }
  @media (max-width: 560px) {
    .metrics { grid-template-columns: 1fr 1fr; gap: 8px; }
    .metric { padding: 12px; }
    .metric b { font-size: 28px; }
    .metric span { font-size: 13px; }
    .metric small { font-size: 12px; }
    .metric:last-child:nth-child(odd) { grid-column: 1 / -1; }
  }

  .how { padding: 48px 0 24px; }
  .how ol { list-style: none; margin: 18px 0 0; padding: 0; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; counter-reset: step; }
  @media (max-width: 900px) { .how ol { grid-template-columns: 1fr 1fr; } }
  @media (max-width: 560px) { .how ol { grid-template-columns: 1fr; } }
  .how li { counter-increment: step; border-top: 2px solid var(--line); padding-top: 12px; }
  .how li::before { content: counter(step); font-family: var(--display); font-weight: 700; font-size: 28px; color: var(--sodium); display: block; line-height: 1; margin-bottom: 6px; }
  .how h3 { margin: 0 0 4px; font-size: 17px; font-weight: 600; }
  .how p { margin: 0; color: var(--muted); font-size: 15px; }

  footer { border-top: 1px solid var(--line); margin-top: 32px; padding: 20px 0 32px; color: var(--muted); font-size: 14px; display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px 20px; }

  @media (prefers-reduced-motion: reduce) {
    .lamp[data-state="speaking"], .ticket.fresh, .call[data-ring="true"], .advance.answer, .running::before,
    .lamp[data-state="ringing"] { animation: none; }
    .timeline li.latest .dot::before { box-shadow: none; }
    * { transition: none !important; }
  }
</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <a class="brand" href="/demo">NightAgent</a>
    <nav><a href="https://ky-gray-portfolio.vercel.app/">Back to Ky Gray's portfolio</a></nav>
  </header>

  <section class="intro">
    <h1>Call the <span class="nowrap">after-hours</span> line.</h1>
    <p>Sam, the NightAgent voice, answers the night desk for a security integrator. Report a problem as one of the demo customers and watch the dispatch board fill in while you're still on the call. Then follow the ticket through dispatch, repair, and follow-up in <a href="#lifecycle">Demo Mode</a>.</p>
  </section>

  <div class="grid">
    <section class="console" aria-labelledby="console-title">
      <h2 id="console-title" class="sr-only">Talk to Sam</h2>
      <div class="callbar">
        <div class="lamp" id="lamp" data-state="idle" aria-hidden="true"></div>
        <div class="status" aria-live="polite">
          <strong id="status-title">Sam is available</strong>
          <span id="status-detail">Calls end automatically after 5 minutes.</span>
        </div>
        <div class="mode" role="group" aria-label="How to talk to Sam">
          <button type="button" data-mode="voice" aria-pressed="true">Voice</button>
          <button type="button" data-mode="text" aria-pressed="false">Text</button>
        </div>
      </div>

      <div class="mic" id="mic-row">
        <label for="mic">Microphone</label>
        <select id="mic"><option value="">Browser default</option></select>
        <button type="button" id="mic-names">Find microphones</button>
      </div>

      <button type="button" class="call" id="call" data-live="false">Start call</button>
      <button type="button" class="sound" id="sound" hidden>Can't hear Sam? Tap here to turn on sound</button>
      <p class="error" id="error" role="alert" hidden></p>

      <details class="accounts" open>
        <summary>Demo customers you can call as</summary>
        <ul>
          <li>
            <div class="who">Sunset Dental Group <span>310-555-0142</span></div>
            <div class="say">Try: "Our back door won't lock and we're closing up."</div>
          </li>
          <li>
            <div class="who">Westside Self Storage <span>310-555-0178</span></div>
            <div class="say">Try: "The front gate is stuck open." This plan has no after-hours coverage.</div>
          </li>
          <li>
            <div class="who">Harbor Logistics Warehouse <span>424-555-0119</span></div>
            <div class="say">Try: "One employee's badge stopped working."</div>
          </li>
        </ul>
      </details>

      <div class="transcript" id="transcript" aria-live="polite" aria-label="Conversation transcript">
        <p class="empty" id="transcript-empty">The conversation will appear here as you talk.</p>
      </div>

      <form class="composer" id="composer" autocomplete="off">
        <label for="message" class="sr-only">Type a message to Sam</label>
        <input id="message" type="text" placeholder="Type to Sam instead of talking" maxlength="400">
        <button type="submit">Send</button>
      </form>

      <p class="fine">Made-up demo data. Please don't share real names, numbers, or alarm codes. Conversations are processed and recorded by ElevenLabs.</p>
    </section>

    <section class="board" aria-labelledby="board-title">
      <div class="board-head">
        <h2 id="board-title">Dispatch board</h2>
        <span class="live" id="board-status">Updates live</span>
      </div>
      <ol class="tickets" id="tickets">
        <li class="empty">No tickets yet. Start a call and report a problem; the ticket shows up here before you hang up.</li>
      </ol>
    </section>
  </div>

  <section class="life" id="lifecycle" aria-labelledby="life-title">
    <div class="life-banner">
      <strong>DEMO MODE — Accelerated Service Lifecycle</strong>
      <span>Steps after the call are simulated so you can see hours of field work in a minute. Technicians and times are made up.</span>
    </div>
    <div class="life-body">
      <div>
        <h2 id="life-title">Follow a ticket</h2>
        <p class="lead">Make a call above, or pick a scenario to skip it. The ticket then runs through dispatch and repair on its own, and NightAgent calls you back when the work is done. Click any ticket on the board to see its history.</p>
        <ul class="scenarios" id="scenarios"></ul>
      </div>
      <div class="event-panel" id="event-panel" aria-live="polite">
        <p class="empty">Pick a scenario or make a call to follow a ticket from the first call to the follow-up.</p>
      </div>
    </div>
  </section>

  <section class="impact" aria-labelledby="impact-title">
    <div class="impact-head">
      <h2 id="impact-title">NightAgent Business Impact</h2>
      <span class="live" id="impact-status">Demo metrics</span>
    </div>
    <p class="impact-note">Counted live from this demo's own records: every visitor's calls, scenarios, and follow-ups. Demo data, not customer data, and no revenue figures.</p>
    <ol class="metrics" id="metrics"></ol>
  </section>

  <section class="how" aria-labelledby="how-title">
    <h2 id="how-title">What happens on a call</h2>
    <ol>
      <li><h3>Sam answers</h3><p>ElevenLabs handles speech recognition, the conversation, and Sam's voice in real time.</p></li>
      <li><h3>Account lookup</h3><p>Sam calls a Python tool on this server to find the customer by phone number or business name.</p></li>
      <li><h3>Triage and ticket</h3><p>Sam suggests a priority, but server-side rules make the final call. An emergency can't be downgraded.</p></li>
      <li><h3>Dispatch and follow-up</h3><p>Emergencies page the on-call technician. Every step after that is written to the ticket's history, through repair and NightAgent's follow-up.</p></li>
    </ol>
  </section>

  <footer>
    <span>NightAgent, built by Ky Gray with ElevenLabs Agents, Python and FastAPI, Supabase, and Vercel.</span>
    <a href="/">Open the full ticket log</a>
  </footer>
</div>

<script type="module">
const AGENT_ID = "__AGENT_ID__";
const $ = (id) => document.getElementById(id);
const els = {
  lamp: $("lamp"), title: $("status-title"), detail: $("status-detail"), call: $("call"),
  error: $("error"), transcript: $("transcript"), empty: $("transcript-empty"),
  composer: $("composer"), input: $("message"), tickets: $("tickets"), boardStatus: $("board-status"),
  modeButtons: document.querySelectorAll(".mode button"),
  micRow: $("mic-row"), mic: $("mic"), micNames: $("mic-names"), sound: $("sound"),
  scenarios: $("scenarios"), panel: $("event-panel"), metrics: $("metrics"), impactStatus: $("impact-status"),
};

let Conversation = null;
let session = null;
let mode = "voice";
let connecting = false;
let conversationId = null;
let lastTyped = null;
let seen = new Set();
let firstLoad = true;
let pollTimer = null;
let fastPollUntil = 0;
let followUpTicket = null; // set while a follow-up call is running

async function loadSdk() {
  if (Conversation) return Conversation;
  const sources = [
    "https://cdn.jsdelivr.net/npm/@elevenlabs/client@1.26.0/+esm",
    "https://esm.sh/@elevenlabs/client@1.26.0",
  ];
  for (const src of sources) {
    try {
      const mod = await import(src);
      if (mod.Conversation) { Conversation = mod.Conversation; return Conversation; }
    } catch (err) { console.warn("SDK load failed from", src, err); }
  }
  throw new Error("The voice library didn't load. Check your connection and reload the page.");
}

function showError(message) {
  els.error.textContent = message;
  els.error.hidden = !message;
}

function setStatus(state, title, detail) {
  els.lamp.dataset.state = state;
  if (title) els.title.textContent = title;
  if (detail !== undefined) els.detail.textContent = detail;
}

function render() {
  const live = Boolean(session);
  els.call.dataset.live = String(live);
  els.call.disabled = connecting;
  const noun = mode === "voice" ? "call" : "chat";
  const ring = Boolean(ringing) && !live && !connecting;
  els.call.dataset.ring = String(ring);
  els.call.textContent = connecting ? "Connecting…" : live ? `End ${noun}` : ring ? "Incoming call · Answer" : `Start ${noun}`;
  els.modeButtons.forEach((b) => {
    b.setAttribute("aria-pressed", String(b.dataset.mode === mode));
    b.disabled = live || connecting;
  });
  els.micRow.hidden = mode !== "voice";
  els.mic.disabled = live || connecting;
}

/* ---------- Microphone choice (remembered on this device) ---------- */

const MIC_KEY = "nightshift-mic";
function savedMic() {
  try { return JSON.parse(localStorage.getItem(MIC_KEY)) || null; } catch { return null; }
}
function saveMic(mic) {
  try {
    if (mic && mic.id) localStorage.setItem(MIC_KEY, JSON.stringify(mic));
    else localStorage.removeItem(MIC_KEY);
  } catch {}
}

async function listMics() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return [];
  const devices = await navigator.mediaDevices.enumerateDevices();
  return devices
    .filter((d) => d.kind === "audioinput" && d.deviceId && !["default", "communications"].includes(d.deviceId))
    .map((d, i) => ({ id: d.deviceId, label: d.label || `Microphone ${i + 1}` }));
}

// Names seen so far on this page. Firefox can hide device names again once the microphone
// is released, so the list keeps the names it already learned.
const knownLabels = new Map();

async function refreshMics() {
  let mics = [];
  try { mics = await listMics(); } catch {}
  for (const m of mics) {
    if (!/^Microphone \d+$/.test(m.label)) knownLabels.set(m.id, m.label);
    else if (knownLabels.has(m.id)) m.label = knownLabels.get(m.id);
  }
  // Browser hid the list again (Firefox after the mic is released): keep the mics we've seen
  if (!mics.length && knownLabels.size) mics = [...knownLabels].map(([id, label]) => ({ id, label }));
  const saved = savedMic();
  const named = mics.some((m) => !/^Microphone \d+$/.test(m.label));
  // Keep the saved mic in the list even while the browser isn't showing it
  if (saved && saved.id && !mics.some((m) => m.id === saved.id || m.label === saved.label)) {
    mics.push({ id: saved.id, label: saved.label || "Saved microphone" });
  }
  els.mic.replaceChildren();
  const def = document.createElement("option");
  def.value = "";
  def.textContent = "Browser default";
  els.mic.appendChild(def);
  for (const m of mics) {
    const o = document.createElement("option");
    o.value = m.id;
    o.textContent = m.label;
    els.mic.appendChild(o);
  }
  // Keep the saved choice selected, matching by name if the device id changed
  let pick = saved && mics.find((m) => m.id === saved.id);
  if (!pick && saved) pick = mics.find((m) => m.label === saved.label);
  if (pick && saved && pick.id !== saved.id) saveMic(pick);
  els.mic.value = pick ? pick.id : "";
  els.micNames.hidden = named;
  els.micNames.textContent = mics.length ? "Show names" : "Find microphones";
  render();
}

// Ask for mic permission once, so the list can show device names
async function unlockMicNames() {
  showError("");
  let stream = null;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    showError("Microphone access is blocked. Allow it from your browser's address bar to see your microphones.");
  }
  await refreshMics();
  if (stream) stream.getTracks().forEach((t) => t.stop());
}

/* Open the chosen microphone once to make sure it works, and return the device id to use.
   If the saved mic is gone, fall back to the browser's default and say so. */
async function prepareMic() {
  const chosen = els.mic.value;
  const chosenLabel = els.mic.selectedOptions[0] ? els.mic.selectedOptions[0].textContent : "";
  const tryOpen = async (id) => {
    const s = await navigator.mediaDevices.getUserMedia({ audio: id ? { deviceId: { exact: id } } : true });
    await refreshMics(); // the mic is open, so the names are visible
    s.getTracks().forEach((t) => t.stop());
  };
  if (chosen) {
    try { await tryOpen(chosen); return chosen; }
    catch (err) {
      if (err && err.name === "NotAllowedError") throw err;
      addMessage("note", `${chosenLabel || "Your saved microphone"} isn't available, so the browser default is being used.`);
      saveMic(null);
      els.mic.value = "";
    }
  }
  await tryOpen("");
  return "";
}

/* ---------- Sam's voice ----------
   The voice library plays Sam through a hidden <audio> element fed by a media stream.
   Some Android browsers built on WebView (DuckDuckGo, in-app browsers) play no sound
   that way, so Sam's audio is also sent straight to the speakers through Web Audio and
   the hidden element is muted (so Chrome doesn't play it twice). If the browser still
   keeps sound off until a tap, a button asks for one. */
let soundCleanup = null;

function voiceOutput() {
  const out = session && session.output;
  return out && out.context && out.analyser ? out : null;
}

function routeSoundToSpeakers() {
  const out = voiceOutput();
  if (!out) return;
  try {
    out.analyser.connect(out.context.destination);
    if (out.audioElement) out.audioElement.muted = true;
  } catch (err) {
    console.warn("Direct sound route not available; keeping the library's own", err);
    return;
  }
  const update = () => { els.sound.hidden = !session || out.context.state === "running"; };
  out.context.addEventListener("statechange", update);
  // Any tap during the call also wakes the sound up, in case the browser held it back
  const wake = () => { if (out.context.state !== "running") out.context.resume().catch(() => {}); };
  document.addEventListener("pointerdown", wake, true);
  soundCleanup = () => {
    out.context.removeEventListener("statechange", update);
    document.removeEventListener("pointerdown", wake, true);
    els.sound.hidden = true;
  };
  update();
}

async function turnOnSound() {
  const out = voiceOutput();
  if (!out) return;
  try {
    await out.context.resume();
    // A short silent sound inside the tap unlocks playback in stricter browsers
    const buf = out.context.createBuffer(1, 1, out.context.sampleRate);
    const src = out.context.createBufferSource();
    src.buffer = buf;
    src.connect(out.context.destination);
    src.start(0);
  } catch (err) { console.warn(err); }
  els.sound.hidden = out.context.state === "running";
}

function addMessage(who, text) {
  if (!text) return;
  els.empty.hidden = true;
  const div = document.createElement("div");
  div.className = `msg ${who}`;
  if (who !== "note") {
    const b = document.createElement("b");
    b.textContent = who === "sam" ? "Sam" : "You";
    div.appendChild(b);
  }
  div.appendChild(document.createTextNode(text));
  els.transcript.appendChild(div);
  els.transcript.scrollTop = els.transcript.scrollHeight;
}

function clearTranscript() {
  els.transcript.querySelectorAll(".msg").forEach((n) => n.remove());
  els.empty.hidden = false;
}

const handlers = {
  onConnect: (info) => {
    if (info && info.conversationId) conversationId = info.conversationId;
    const who = followUpTicket ? `Sam is following up on ${followUpTicket}` : (mode === "voice" ? "Connected to Sam" : "Chatting with Sam");
    setStatus("listening", who,
      mode === "voice" ? "Speak naturally. You can interrupt Sam anytime." : "Type your messages below.");
    fastPollUntil = Date.now() + 10 * 60 * 1000;
    schedulePoll(1500);
  },
  onDisconnect: (details) => {
    session = null;
    if (soundCleanup) { soundCleanup(); soundCleanup = null; }
    const why = details && details.reason === "error" ? (details.message || "The connection to Sam failed.") : "";
    if (why) showError(`The call couldn't continue: ${why}`);
    setStatus("idle", "Call ended", autoId
      ? "Your ticket is moving through dispatch below. NightAgent will call you back when the work is done."
      : "The ticket stays on the board. Start another call anytime.");
    addMessage("note", mode === "voice" ? "Call ended" : "Chat ended");
    if (pendingRing && !followUpTicket) { const id = pendingRing; pendingRing = null; setTimeout(() => startRinging(id), 1500); }
    if (followUpTicket) {
      const id = followUpTicket;
      followUpTicket = null;
      addMessage("note", `See what NightAgent did with ${id} in Demo Mode below.`);
      setTimeout(() => { loadTicket(id, { scroll: true }); loadImpact(true); }, 1200);
    }
    fastPollUntil = Date.now() + 90 * 1000;
    schedulePoll(1000);
    render();
  },
  onMessage: ({ message, source }) => {
    if (source === "user") {
      if (lastTyped && message && message.trim() === lastTyped) { lastTyped = null; return; }
      addMessage("you", message);
    } else {
      addMessage("sam", message);
      schedulePoll(800);
    }
  },
  onModeChange: ({ mode: m }) => {
    if (!session) return;
    if (m === "speaking") setStatus("speaking", "Sam is talking", "Jump in anytime.");
    else setStatus("listening", "Sam is listening", mode === "voice" ? "Go ahead and speak." : "Type your reply below.");
  },
  onError: (message) => {
    console.error(message);
    const text = typeof message === "string" ? message : (message && message.message) || "Something went wrong with the connection.";
    showError(text);
  },
};

async function startSession(nextMode, opts = {}) {
  if (session || connecting) return;
  mode = nextMode || mode;
  connecting = true;
  showError("");
  setStatus("connecting", "Connecting to Sam…", "This takes a second or two.");
  render();
  try {
    const C = await loadSdk();
    clearTranscript();
    conversationId = null;
    myCallRef = null;
    let inputDeviceId = "";
    if (mode === "voice") {
      try {
        inputDeviceId = await prepareMic();
      } catch {
        throw new Error("Microphone access is blocked. Allow it from your browser's address bar, or switch to Text.");
      }
    }
    const base = {
      agentId: opts.agentId || AGENT_ID,
      ...(opts.dynamicVariables ? { dynamicVariables: opts.dynamicVariables } : {}),
      ...handlers,
    };
    if (mode === "text") {
      session = await C.startSession({ ...base, textOnly: true, overrides: { conversation: { textOnly: true } } });
    } else {
      // WebSocket sends the page's origin, which the agent's allowed-sites list requires.
      // (A WebRTC call is rejected for a missing origin header after it connects, so it
      // just hangs up.)
      session = await C.startSession({
        ...base,
        connectionType: "websocket",
        ...(inputDeviceId ? { inputDeviceId } : {}),
      });
      routeSoundToSpeakers();
    }
    try { conversationId = conversationId || (session.getId && session.getId()) || null; } catch {}
  } catch (err) {
    session = null;
    followUpTicket = null;
    const msg = (err && err.message) || String(err);
    showError(/quota|credit/i.test(msg)
      ? "The demo has used up its call minutes for now. Please check back later."
      : msg);
    setStatus("idle", "Sam is available", "Calls end automatically after 5 minutes.");
  } finally {
    connecting = false;
    render();
  }
}

async function endSession() {
  if (!session) return;
  try { await session.endSession(); } catch (err) { console.warn(err); }
}

els.call.addEventListener("click", () => (session ? endSession() : ringing ? answerRing() : startSession()));

els.modeButtons.forEach((b) => b.addEventListener("click", () => {
  if (session || connecting) return;
  mode = b.dataset.mode;
  render();
}));

els.mic.addEventListener("change", () => {
  const o = els.mic.selectedOptions[0];
  saveMic(els.mic.value ? { id: els.mic.value, label: o ? o.textContent : "" } : null);
});
els.micNames.addEventListener("click", unlockMicNames);
els.sound.addEventListener("click", turnOnSound);
if (navigator.mediaDevices && navigator.mediaDevices.addEventListener) {
  navigator.mediaDevices.addEventListener("devicechange", refreshMics);
}

els.composer.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = els.input.value.trim();
  if (!text) return;
  if (!session) {
    mode = "text";
    await startSession("text");
    if (!session) return;
  }
  els.input.value = "";
  lastTyped = text;
  addMessage("you", text);
  try { session.sendUserMessage(text); } catch (err) { showError("That message didn't send. Try again."); }
});

/* ---------- Dispatch board ---------- */

function timeAgo(iso) {
  const t = Date.parse(iso);
  if (!t) return "";
  const s = Math.max(0, Math.round((Date.now() - t) / 1000));
  if (s < 60) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} hr ago`;
  return new Date(t).toLocaleDateString();
}

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined && text !== null) n.textContent = text;
  return n;
}

function renderTickets(list) {
  els.tickets.replaceChildren();
  if (!list.length) {
    els.tickets.appendChild(el("li", "empty", "No tickets yet. Start a call and report a problem; the ticket shows up here before you hang up."));
    return;
  }
  for (const t of list) {
    const li = el("li", "ticket");
    li.dataset.priority = t.priority || "";
    li.dataset.id = t.ticket_id;
    li.tabIndex = 0;
    li.setAttribute("aria-label", `${t.ticket_id}: open its history`);
    if (t.ticket_id === selectedId) li.setAttribute("aria-current", "true");
    if (!firstLoad && !seen.has(t.ticket_id)) li.classList.add("fresh");
    seen.add(t.ticket_id);

    li.appendChild(el("div", "bar"));
    const body = el("div", "body");

    const row1 = el("div", "row1");
    row1.appendChild(el("span", "id", t.ticket_id));
    row1.appendChild(el("span", `chip ${t.priority}`, t.priority));
    if (myCallRef && t.call_ref === myCallRef) row1.appendChild(el("span", "chip mine", "Your call"));
    if (t.scenario) row1.appendChild(el("span", "chip demo", "Demo scenario"));
    row1.appendChild(el("span", "when", timeAgo(t.created_at)));
    body.appendChild(row1);

    body.appendChild(el("p", "issue", t.issue_summary || ""));

    const meta = el("div", "meta");
    meta.appendChild(el("span", "", `Caller: ${t.caller_name || "Unknown"} ${t.callback_number || ""}`));
    meta.appendChild(el("span", "", `Status: ${t.status_label || t.status || "Open"}`));
    if (t.priority_reason) meta.appendChild(el("span", "", t.priority_reason));
    body.appendChild(meta);

    if (t.call_summary) body.appendChild(el("p", "summary", `Call summary: ${t.call_summary}`));

    li.appendChild(body);
    els.tickets.appendChild(li);
  }
  firstLoad = false;
}

async function refreshTickets() {
  try {
    const res = await fetch("/api/tickets", { cache: "no-store" });
    if (!res.ok) throw new Error(res.status);
    const list = await res.json();
    renderTickets(list);
    els.boardStatus.textContent = "Updates live";
    await claimMyCallTicket(list);
    if (selectedId && !busy) loadTicket(selectedId, { quiet: true });
    loadImpact();
  } catch (err) {
    els.boardStatus.textContent = "Reconnecting…";
  }
}

function schedulePoll(delay) {
  clearTimeout(pollTimer);
  pollTimer = setTimeout(async () => {
    await refreshTickets();
    const fast = session || Date.now() < fastPollUntil;
    schedulePoll(fast ? 3000 : 20000);
  }, delay);
}

/* ---------- Demo Mode: follow one ticket through its lifecycle ---------- */

const KEYS_KEY = "nightagent-demo-keys";
let selectedId = null;
let selectedDetail = null;
let myCallRef = null;
let busy = false;
const STAGES = [
  ["awaiting_dispatch", "Ticket"], ["dispatched", "Dispatched"], ["technician_assigned", "Assigned"],
  ["en_route", "En route"], ["onsite", "Onsite"], ["work_completed", "Completed"], ["follow_up_pending", "Follow-up"],
  ["outcome", "Outcome"],
];
const OUTCOME_STATES = ["resolved", "closed", "reopened", "escalated"];
const GENERIC_HINTS = [
  "It's working great now.",
  "It stopped working again last night.",
  "It never really worked after the technician left.",
  "That's fixed, but another reader isn't working.",
  "We're thinking about upgrading our cameras next year.",
  "Can someone from sales call me?",
];
const scenarioHints = {};

// Demo keys prove this browser started a ticket. Kept in memory too, for when storage is blocked.
const memoryKeys = {};
function demoKeys() {
  try { return JSON.parse(localStorage.getItem(KEYS_KEY)) || {}; } catch { return {}; }
}
function saveDemoKey(ticketId, key) {
  memoryKeys[ticketId] = key;
  const all = { ...demoKeys(), [ticketId]: key };
  const newest = Object.fromEntries(Object.entries(all).slice(-30)); // so the list can't grow forever
  try { localStorage.setItem(KEYS_KEY, JSON.stringify(newest)); } catch {}
}
function keyFor(ticketId) { return memoryKeys[ticketId] || demoKeys()[ticketId] || null; }

async function sha16(text) {
  try {
    const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
    return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("").slice(0, 16);
  } catch { return null; }
}

async function api(path, body) {
  const res = await fetch(path, body ? {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  } : { cache: "no-store" });
  let data = null;
  try { data = await res.json(); } catch {}
  if (!res.ok) throw new Error((data && typeof data.detail === "string" && data.detail) || "Something went wrong. Please try again.");
  return data;
}

function clock(iso) {
  const t = new Date(iso);
  return isNaN(t) ? "" : t.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function button(cls, text, onClick, disabled) {
  const b = el("button", cls, text);
  b.type = "button";
  b.disabled = Boolean(disabled);
  b.addEventListener("click", onClick);
  return b;
}

function renderPanel(detail, message) {
  selectedDetail = detail;
  const p = els.panel;
  p.replaceChildren();
  if (!detail) {
    p.appendChild(el("p", "empty", "Pick a scenario or make a call to follow a ticket from the first call to the follow-up."));
    if (message) p.appendChild(el("p", "error", message));
    return;
  }
  const t = detail.ticket;
  const head = el("div", "ev-head");
  head.appendChild(el("span", "id", t.ticket_id));
  head.appendChild(el("span", `chip ${t.priority}`, t.priority_label || t.priority));
  head.appendChild(el("span", "chip stage", t.status_label));
  if (myCallRef && t.call_ref === myCallRef) head.appendChild(el("span", "chip mine", "Your call"));
  p.appendChild(head);
  p.appendChild(el("p", "ev-issue", t.issue_summary || ""));
  const meta = el("div", "ev-meta");
  meta.appendChild(el("span", "", `Caller: ${t.caller_name || "Unknown"}`));
  if (t.priority_reason) meta.appendChild(el("span", "", t.priority_reason));
  if (t.technician_name) meta.appendChild(el("span", "", `Technician: ${t.technician_name} (demo)`));
  p.appendChild(meta);

  // Where the ticket is now
  const stage = OUTCOME_STATES.includes(t.status) ? "outcome" : t.status;
  const at = STAGES.findIndex(([s]) => s === stage);
  const strip = el("ol", "stages");
  strip.setAttribute("aria-label", "Service stages");
  STAGES.forEach(([s, label], i) => {
    const text = s === "outcome" && stage === "outcome" ? t.status_label : label;
    const li = el("li", at < 0 ? "" : i < at ? "done" : i === at ? "now" : "", text);
    if (i === at) li.setAttribute("aria-current", "step");
    strip.appendChild(li);
  });
  p.appendChild(strip);
  // On narrow screens the strip scrolls sideways; keep the current stage in view
  const now = strip.querySelector(".now");
  if (now) strip.scrollLeft = Math.max(0, now.offsetLeft - strip.offsetLeft - (strip.clientWidth - now.offsetWidth) / 2);

  // Controls only for the browser holding this ticket's demo key
  const key = keyFor(t.ticket_id);
  const actions = el("div", "ev-actions");
  const id = t.ticket_id;
  if (key && detail.follow_up_ready) {
    if (ringing === id) {
      actions.appendChild(button("advance answer", "Answer the call", answerRing, connecting));
    } else {
      actions.appendChild(button("advance", missed.has(id) ? "Call back" : "Take the follow-up call",
        () => startFollowUp(t), busy || session || connecting));
    }
    actions.appendChild(button("reset", "Reset", () => resetTicket(id), busy || session));
  } else if (key && detail.next_step) {
    if (autoId === id && !autoPaused) {
      actions.appendChild(el("span", "running", `Running on its own · next: ${detail.next_step}`));
      actions.appendChild(button("step", "Pause", pauseAuto));
    } else {
      actions.appendChild(button("advance", autoId === id ? "Resume" : "Run it for me", () => resumeAuto(id), busy));
      actions.appendChild(button("step", `Next step → ${detail.next_step}`, () => demoAction("advance"), busy));
    }
    if (!t.resolution) actions.appendChild(button("reset", "Reset", () => resetTicket(id), busy));
  } else if (key) {
    if (!t.resolution) actions.appendChild(button("reset", "Reset", () => resetTicket(id), busy));
  } else if (t.demo) {
    actions.appendChild(el("p", "ev-note", "Viewing only. This demo ticket can be advanced from the browser that started it."));
  } else {
    actions.appendChild(el("p", "ev-note", "Viewing only. Start a scenario, or make a call, to step through a ticket yourself."));
  }
  if (actions.childNodes.length) p.appendChild(actions);
  if (key && detail.follow_up_ready) p.appendChild(followUpBox(t));
  if (message) p.appendChild(el("p", "error", message));

  // Customer journey, oldest first
  const tl = el("ol", "timeline");
  tl.setAttribute("aria-label", "Customer journey");
  detail.events.forEach((e, i) => {
    const li = el("li", e.simulated ? "sim" : "");
    if (i === detail.events.length - 1) li.classList.add("latest");
    const time = el("time", "", clock(e.occurred_at));
    time.dateTime = e.occurred_at || "";
    li.appendChild(time);
    li.appendChild(el("span", "dot"));
    const what = el("div", "what");
    what.appendChild(el("b", "", e.label));
    if (e.simulated) what.appendChild(el("span", "tag-sim", "Simulated"));
    if (e.description) what.appendChild(el("p", "", e.description));
    li.appendChild(what);
    tl.appendChild(li);
  });
  if (!detail.events.length) tl.appendChild(el("li", "ev-note", "No history was recorded for this ticket. It was created before NightAgent kept a timeline."));
  const acts = businessActions(detail, key);
  if (acts) p.appendChild(acts);
  p.appendChild(tl);
}

function followUpBox(t) {
  const box = el("div", "follow-box");
  box.appendChild(el("p", "", "NightAgent calls the customer to confirm the fix. You're the customer: answer by voice or text (pick at the top of the page). What you say decides what NightAgent does next."));
  const hint = t.scenario && scenarioHints[t.scenario];
  if (hint) {
    box.appendChild(el("p", "", "For this scenario, try saying:"));
    box.appendChild(el("p", "say", `"${hint}"`));
  } else {
    box.appendChild(el("p", "", "Try one of these:"));
    const ul = el("ul");
    GENERIC_HINTS.forEach((h) => ul.appendChild(el("li", "", `"${h}"`)));
    box.appendChild(ul);
  }
  return box;
}

function businessActions(detail, key) {
  const a = detail.actions || {};
  const items = [];
  for (const tk of a.tickets || []) {
    if (key && !keyFor(tk.ticket_id)) saveDemoKey(tk.ticket_id, key); // same browser owns follow-on tickets
    const n = el("div", "action");
    n.appendChild(el("b", "", `New ticket ${tk.ticket_id} · ${tk.priority_label}`));
    n.appendChild(el("span", "", tk.issue_summary || ""));
    n.appendChild(button("", "Open this ticket", () => loadTicket(tk.ticket_id)));
    items.push(n);
  }
  for (const o of a.opportunities || []) {
    const n = el("div", "action opp");
    n.appendChild(el("b", "", `${o.opportunity_id} · ${o.type}`));
    n.appendChild(el("span", "", o.interest || ""));
    const bits = [o.scope, o.device_count && `${o.device_count} devices`, o.timeline].filter(Boolean).join(" · ");
    if (bits) n.appendChild(el("span", "", bits));
    n.appendChild(el("span", "", `Estimated value: ${o.estimated_value}`));
    n.appendChild(el("span", "", `Assigned to ${o.assigned_to}`));
    items.push(n);
  }
  for (const k of a.tasks || []) {
    const n = el("div", `action${k.priority === "high" ? " high" : ""}`);
    n.appendChild(el("b", "", `${k.task_id} · ${k.reason}`));
    if (k.summary) n.appendChild(el("span", "", k.summary));
    n.appendChild(el("span", "", `For ${k.assigned_to}${k.requested_follow_up ? ` · ${k.requested_follow_up}` : ""}`));
    items.push(n);
  }
  if (!items.length) return null;
  const box = el("div", "actions");
  box.appendChild(el("h3", "", "Business actions"));
  items.forEach((n) => box.appendChild(n));
  return box;
}

async function startFollowUp(t) {
  if (busy || session || connecting) return;
  busy = true;
  renderPanel(selectedDetail);
  try {
    const fu = await api("/api/demo/follow-up", { ticket_id: t.ticket_id, demo_key: keyFor(t.ticket_id) });
    busy = false;
    followUpTicket = t.ticket_id;
    document.querySelector(".console").scrollIntoView({ behavior: "smooth", block: "start" });
    await startSession(mode, { agentId: fu.agent_id, dynamicVariables: fu.dynamic_variables });
    loadTicket(t.ticket_id, { quiet: true });
  } catch (err) {
    busy = false;
    followUpTicket = null;
    renderPanel(selectedDetail, err.message);
  }
}

function markSelected() {
  els.tickets.querySelectorAll(".ticket").forEach((n) => {
    if (n.dataset.id === selectedId) n.setAttribute("aria-current", "true");
    else n.removeAttribute("aria-current");
  });
}

async function loadTicket(id, { quiet = false, scroll = false } = {}) {
  selectedId = id;
  markSelected();
  try {
    const detail = await api(`/api/tickets/${encodeURIComponent(id)}`);
    if (selectedId !== id || busy) return;
    // Background refreshes only redraw when something changed, so a click is never lost mid-redraw
    if (quiet && JSON.stringify(detail) === JSON.stringify(selectedDetail)) return;
    renderPanel(detail);
    if (scroll) document.getElementById("lifecycle").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    if (!quiet) renderPanel(selectedDetail, err.message);
  }
}

async function demoAction(kind) {
  const t = selectedDetail && selectedDetail.ticket;
  if (!t || busy) return;
  busy = true;
  renderPanel(selectedDetail);
  try {
    const detail = await api(`/api/demo/${kind}`, { ticket_id: t.ticket_id, demo_key: keyFor(t.ticket_id) });
    busy = false;
    renderPanel(detail);
    refreshTickets();
    impactAt = 0;
  } catch (err) {
    busy = false;
    renderPanel(selectedDetail, err.message);
  }
}

async function startScenario(id, btn) {
  if (busy) return;
  busy = true;
  els.scenarios.querySelectorAll("button").forEach((b) => { b.disabled = true; });
  btn.querySelector("b").textContent += " · starting…";
  try {
    const { demo_key: key, ...detail } = await api("/api/demo/scenario", { scenario: id });
    saveDemoKey(detail.ticket.ticket_id, key);
    selectedId = detail.ticket.ticket_id;
    busy = false;
    startAutoRun(detail.ticket.ticket_id);
    renderPanel(detail);
    impactAt = 0;
    refreshTickets();
  } catch (err) {
    busy = false;
    renderPanel(selectedDetail, err.message);
  } finally {
    loadScenarios();
  }
}

async function loadScenarios() {
  try {
    const list = await api("/api/demo/scenarios");
    els.scenarios.replaceChildren();
    for (const s of list) {
      scenarioHints[s.id] = s.follow_up_hint;
      const li = el("li");
      const b = el("button");
      b.type = "button";
      b.appendChild(el("b", "", s.title));
      b.appendChild(el("span", "", s.story));
      b.addEventListener("click", () => startScenario(s.id, b));
      li.appendChild(b);
      els.scenarios.appendChild(li);
    }
  } catch {
    els.scenarios.replaceChildren(el("li", "ev-note", "Scenarios didn't load. Reload the page to try again."));
  }
}

// When your own call creates a ticket, take it into Demo Mode once. Proof: the conversation id,
// which only this browser knows.
const claimed = new Set();
async function claimMyCallTicket(list) {
  if (!conversationId) return;
  myCallRef = myCallRef || await sha16(conversationId);
  const mine = myCallRef && list.find((t) => t.call_ref === myCallRef);
  if (!mine || claimed.has(mine.ticket_id)) return;
  claimed.add(mine.ticket_id);
  if (!keyFor(mine.ticket_id)) {
    try {
      const data = await api("/api/demo/claim", { ticket_id: mine.ticket_id, conversation_id: conversationId });
      saveDemoKey(mine.ticket_id, data.demo_key);
    } catch (err) { console.warn(err); }
  }
  addMessage("note", `Your ticket ${mine.ticket_id} is in Demo Mode below. It starts moving through dispatch when this call ends.`);
  if (keyFor(mine.ticket_id)) startAutoRun(mine.ticket_id);
  loadTicket(mine.ticket_id);
}

/* ---------- Hands-free: the ticket runs itself, then NightAgent calls you ---------- */

const STEP_MS = 3000;   // time between simulated steps
const RING_MS = 30000;  // how long the phone rings before it's a missed call
let autoId = null;      // the ticket stepping on its own
let autoPaused = false;
let autoTimer = null;
let ringing = null;     // ticket id while NightAgent is "calling"
let pendingRing = null; // ring as soon as the current call ends
let ringTimer = null;
let ringStop = null;
const missed = new Set();

function startAutoRun(id) {
  autoId = id;
  autoPaused = false;
  scheduleAuto(1500);
}
function scheduleAuto(ms) {
  clearTimeout(autoTimer);
  autoTimer = setTimeout(autoStep, ms);
}
async function autoStep() {
  const id = autoId;
  if (!id || autoPaused) return;
  if (session || connecting || busy) { scheduleAuto(1500); return; } // wait for the current call to end
  try {
    const detail = await api("/api/demo/advance", { ticket_id: id, demo_key: keyFor(id) });
    if (autoId !== id) return;
    if (detail.next_step) {
      scheduleAuto(STEP_MS);
    } else {
      autoId = null;
      if (detail.follow_up_ready) startRinging(id);
    }
    if (selectedId === id && !busy) renderPanel(detail);
    impactAt = 0;
    refreshTickets();
  } catch (err) {
    autoId = null;
    if (selectedId === id) renderPanel(selectedDetail, err.message);
  }
}
function pauseAuto() {
  autoPaused = true;
  clearTimeout(autoTimer);
  renderPanel(selectedDetail);
}
function resumeAuto(id) {
  autoId = id;
  autoPaused = false;
  scheduleAuto(300);
  renderPanel(selectedDetail);
}
function resetTicket(id) {
  if (autoId === id) { autoId = null; clearTimeout(autoTimer); }
  if (ringing === id) stopRinging(false);
  if (pendingRing === id) pendingRing = null;
  missed.delete(id);
  demoAction("reset");
}

// A classic two-tone phone ring, made by the page (no sound file). Browsers only allow sound
// after the visitor has clicked something, so the audio is unlocked on the first click.
let ringCtx = null;
function unlockAudio() {
  try {
    if (!ringCtx) ringCtx = new (window.AudioContext || window.webkitAudioContext)();
    if (ringCtx.state === "suspended") ringCtx.resume().catch(() => {});
  } catch {}
}
document.addEventListener("pointerdown", unlockAudio, true);
document.addEventListener("keydown", unlockAudio, true);

function playRing() {
  unlockAudio();
  if (!ringCtx) return () => {};
  const ctx = ringCtx;
  const gain = ctx.createGain();
  gain.gain.value = 0;
  gain.connect(ctx.destination);
  const oscs = [440, 480].map((f) => {
    const o = ctx.createOscillator();
    o.frequency.value = f;
    o.connect(gain);
    o.start();
    return o;
  });
  const t0 = ctx.currentTime + 0.05;
  for (let i = 0; i < Math.ceil(RING_MS / 4000); i++) { // 2 s ring, 2 s quiet
    gain.gain.setTargetAtTime(0.12, t0 + i * 4, 0.015);
    gain.gain.setTargetAtTime(0, t0 + i * 4 + 2, 0.015);
  }
  return () => {
    oscs.forEach((o) => { try { o.stop(); } catch {} });
    try { gain.disconnect(); } catch {}
  };
}

function startRinging(id) {
  if (session || connecting) { pendingRing = id; return; } // don't ring over a call in progress
  if (ringing) stopRinging(false);
  ringing = id;
  missed.delete(id);
  ringStop = playRing();
  try { if (navigator.vibrate) navigator.vibrate([400, 200, 400, 1600, 400, 200, 400]); } catch {}
  setStatus("ringing", "NightAgent is calling", `Tap Answer to talk to Sam about ${id}.`);
  clearTimeout(ringTimer);
  ringTimer = setTimeout(() => stopRinging(true), RING_MS);
  render();
  if (selectedDetail && selectedDetail.ticket.ticket_id === id) renderPanel(selectedDetail);
}

function stopRinging(missedIt) {
  if (!ringing) return;
  const id = ringing;
  ringing = null;
  clearTimeout(ringTimer);
  if (ringStop) { ringStop(); ringStop = null; }
  try { if (navigator.vibrate) navigator.vibrate(0); } catch {}
  if (missedIt) {
    missed.add(id);
    setStatus("idle", "Missed call from NightAgent", `Tap Call back on ${id} in Demo Mode to take it.`);
  }
  render();
  if (selectedDetail && selectedDetail.ticket.ticket_id === id) renderPanel(selectedDetail);
}

async function answerRing() {
  const id = ringing;
  if (!id) return;
  stopRinging(false);
  await startFollowUp({ ticket_id: id });
}

function pickFromBoard(e) {
  const li = e.target.closest(".ticket");
  if (!li || !li.dataset.id) return;
  if (e.type === "keydown") {
    if (e.key !== "Enter" && e.key !== " ") return;
    e.preventDefault();
  }
  loadTicket(li.dataset.id, { scroll: true });
}
els.tickets.addEventListener("click", pickFromBoard);
els.tickets.addEventListener("keydown", pickFromBoard);

/* ---------- Business Impact ---------- */

function metric(value, label, note, key) {
  const li = el("li", `metric${key ? " key" : ""}`);
  li.appendChild(el("b", "", String(value)));
  li.appendChild(el("span", "", label));
  if (note) li.appendChild(el("small", "", note));
  return li;
}

let impactAt = 0;
async function loadImpact(force) {
  if (!force && Date.now() - impactAt < 30000) return;
  impactAt = Date.now();
  try {
    const m = await api("/api/impact");
    const hours = m.minutes_saved >= 120 ? `${(m.minutes_saved / 60).toFixed(1)} hr` : `${m.minutes_saved} min`;
    const a = m.assumptions;
    els.metrics.replaceChildren(
      metric(m.calls_handled, "Calls handled", `${m.live_calls} live, ${m.scenario_calls} demo scenario${m.scenario_calls === 1 ? "" : "s"}`, true),
      metric(m.emergencies, "Emergencies triaged", "P1 by the priority rules"),
      metric(m.tickets, "Service tickets created"),
      metric(m.needed_a_person, "After-hours calls that paged a technician", `${m.handled_without_waking_anyone} handled without waking anyone`),
      metric(m.follow_ups, "Follow-up calls completed", "", true),
      metric(m.resolved, "Issues confirmed resolved", "The customer said so on the follow-up"),
      metric(m.reopened, "Tickets reopened"),
      metric(m.escalated, "Escalations created"),
      metric(m.opportunities, "AE opportunities discovered", "Value TBD until the AE qualifies it", true),
      metric(m.tasks, "Tasks routed to people"),
      metric(hours, "Estimated admin time saved", `Real conversations only: ${a.minutes_per_intake_call} min per intake call, ${a.minutes_per_follow_up} min per follow-up`),
    );
    els.impactStatus.textContent = "Demo metrics · updates live";
  } catch {
    els.impactStatus.textContent = "Demo metrics · reconnecting…";
  }
}

render();
refreshMics();
loadScenarios();
loadImpact(true);
schedulePoll(0);
</script>
</body>
</html>
"""
