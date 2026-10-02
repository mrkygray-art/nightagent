"""The public /demo page: talk to Sam (voice or text) and watch the dispatch board update.

Kept as a Python string so it always ships with the serverless function.
__AGENT_ID__ is replaced at request time with the configured agent ID.
"""

DEMO_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>NightShift Dispatch: live voice agent demo</title>
<meta name="description" content="Talk to Sam, an after-hours dispatch voice agent built on ElevenLabs Agents with a Python FastAPI backend, and watch tickets appear live.">
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

  .tickets { list-style: none; margin: 0; padding: 0; display: grid; gap: 12px; }
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
    .lamp[data-state="speaking"], .ticket.fresh { animation: none; }
    * { transition: none !important; }
  }
</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <a class="brand" href="/demo">NightShift Dispatch</a>
    <nav><a href="https://ky-gray-portfolio.vercel.app/">Back to Ky Gray's portfolio</a></nav>
  </header>

  <section class="intro">
    <h1>Call the <span class="nowrap">after-hours</span> line.</h1>
    <p>Sam answers the night desk for a security integrator. Report a problem as one of the demo customers, and watch the dispatch board fill in while you're still on the call.</p>
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

  <section class="how" aria-labelledby="how-title">
    <h2 id="how-title">What happens on a call</h2>
    <ol>
      <li><h3>Sam answers</h3><p>ElevenLabs handles speech recognition, the conversation, and Sam's voice in real time.</p></li>
      <li><h3>Account lookup</h3><p>Sam calls a Python tool on this server to find the customer by phone number or business name.</p></li>
      <li><h3>Triage and ticket</h3><p>Sam suggests a priority, but server-side rules make the final call. An emergency can't be downgraded.</p></li>
      <li><h3>Dispatch</h3><p>Emergencies page the on-call technician. Other tickets wait for the morning crew.</p></li>
    </ol>
  </section>

  <footer>
    <span>Built by Ky Gray with ElevenLabs Agents, Python and FastAPI, Supabase, and Vercel.</span>
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
  els.call.textContent = connecting ? "Connecting…" : live ? `End ${noun}` : `Start ${noun}`;
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
    setStatus("listening", mode === "voice" ? "Connected to Sam" : "Chatting with Sam",
      mode === "voice" ? "Speak naturally. You can interrupt Sam anytime." : "Type your messages below.");
    fastPollUntil = Date.now() + 10 * 60 * 1000;
    schedulePoll(1500);
  },
  onDisconnect: (details) => {
    session = null;
    if (soundCleanup) { soundCleanup(); soundCleanup = null; }
    const why = details && details.reason === "error" ? (details.message || "The connection to Sam failed.") : "";
    if (why) showError(`The call couldn't continue: ${why}`);
    setStatus("idle", "Call ended", "The ticket stays on the board. Start another call anytime.");
    addMessage("note", mode === "voice" ? "Call ended" : "Chat ended");
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

async function startSession(nextMode) {
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
    let inputDeviceId = "";
    if (mode === "voice") {
      try {
        inputDeviceId = await prepareMic();
      } catch {
        throw new Error("Microphone access is blocked. Allow it from your browser's address bar, or switch to Text.");
      }
    }
    const base = { agentId: AGENT_ID, ...handlers };
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

els.call.addEventListener("click", () => (session ? endSession() : startSession()));

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
    if (!firstLoad && !seen.has(t.ticket_id)) li.classList.add("fresh");
    seen.add(t.ticket_id);

    li.appendChild(el("div", "bar"));
    const body = el("div", "body");

    const row1 = el("div", "row1");
    row1.appendChild(el("span", "id", t.ticket_id));
    row1.appendChild(el("span", `chip ${t.priority}`, t.priority));
    if (conversationId && t.conversation_id === conversationId) row1.appendChild(el("span", "chip mine", "Your call"));
    row1.appendChild(el("span", "when", timeAgo(t.created_at)));
    body.appendChild(row1);

    body.appendChild(el("p", "issue", t.issue_summary || ""));

    const meta = el("div", "meta");
    meta.appendChild(el("span", "", `Caller: ${t.caller_name || "Unknown"} ${t.callback_number || ""}`));
    meta.appendChild(el("span", "", `Status: ${t.status || "open"}`));
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
    renderTickets(await res.json());
    els.boardStatus.textContent = "Updates live";
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

render();
refreshMics();
schedulePoll(0);
</script>
</body>
</html>
"""
