"""The public /deepgram page: call Sam on the Deepgram Voice Agent API from the browser.

Kept as a Python string so it always ships with the serverless function. The browser talks to Deepgram
directly (a 30-second token from /api/deepgram/session opens the socket); this server only runs the tools.
"""

DEEPGRAM_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>NightAgent on Deepgram: talk to Sam</title>
<meta name="description" content="NightAgent's after-hours front desk, Sam, running on the Deepgram Voice Agent API: Flux listens, Aura-2 speaks, Claude thinks, and the same tools file tickets on the live board.">
<meta name="theme-color" content="#101a2e">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700&family=Barlow:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root {
    --night: #101a2e; --panel: #172440; --panel-2: #1d2d4f; --line: #2b3d63; --text: #e9edf5; --muted: #a3afc6;
    --sodium: #f5a524; --sodium-soft: rgba(245, 165, 36, 0.16); --alarm: #e5484d; --clear: #4cb782;
    --body: "Barlow", system-ui, -apple-system, "Segoe UI", sans-serif;
    --display: "Barlow Condensed", "Arial Narrow", system-ui, sans-serif;
    color-scheme: dark;
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--night); color: var(--text); font-family: var(--body); font-size: 16px; line-height: 1.5;
         font-variant-numeric: tabular-nums; }
  a { color: var(--sodium); }
  button:focus-visible, a:focus-visible { outline: 2px solid var(--sodium); outline-offset: 2px; }
  main { max-width: 860px; margin: 0 auto; padding: 28px 18px 60px; }
  h1 { font-family: var(--display); font-size: 2.4rem; line-height: 1.05; margin: 0 0 8px; letter-spacing: .01em; }
  h2 { font-family: var(--display); font-size: 1.35rem; margin: 0 0 10px; }
  .kicker { color: var(--sodium); font-weight: 600; text-transform: uppercase; letter-spacing: .08em; font-size: .8rem; }
  .lede { color: var(--muted); margin: 0 0 18px; max-width: 64ch; }
  .stack { display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 22px; padding: 0; list-style: none; }
  .stack li { background: var(--panel); border: 1px solid var(--line); border-radius: 999px; padding: 4px 12px; font-size: .9rem; }
  .stack b { color: var(--sodium); font-weight: 600; }
  .panel { background: var(--panel); border: 1px solid var(--line); border-radius: 18px; padding: 18px; margin-bottom: 16px; }
  .controls { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
  .call { font: 600 1.05rem var(--body); border: 0; border-radius: 999px; padding: 12px 24px; cursor: pointer;
          background: var(--sodium); color: #1a1205; }
  .call.end { background: var(--alarm); color: #fff; }
  .call:disabled { opacity: .55; cursor: wait; }
  #status { color: var(--muted); }
  .dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: var(--line); margin-right: 6px; vertical-align: middle; }
  .dot.live { background: var(--clear); box-shadow: 0 0 0 4px rgba(76, 183, 130, .2); }
  .dot.talk { background: var(--sodium); box-shadow: 0 0 0 4px var(--sodium-soft); }
  .mic { display: inline-flex; align-items: center; gap: 6px; color: var(--muted); font-size: .9rem; }
  .mic[hidden] { display: none; }
  .mic-track { width: 70px; height: 8px; border-radius: 4px; background: var(--line); overflow: hidden; }
  #mic-bar { display: block; height: 100%; width: 0; background: var(--clear); transition: width .1s; }
  .grid { display: grid; grid-template-columns: 1.6fr 1fr; gap: 16px; }
  @media (max-width: 720px) { .grid { grid-template-columns: 1fr; } h1 { font-size: 2rem; } }
  #transcript { min-height: 220px; max-height: 420px; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; }
  .turn { padding: 8px 12px; border-radius: 12px; max-width: 92%; }
  .turn.assistant { background: var(--panel-2); align-self: flex-start; }
  .turn.user { background: var(--sodium-soft); align-self: flex-end; }
  .turn .who { display: block; font-size: .75rem; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; }
  .turn.tool { background: none; border: 1px dashed var(--line); color: var(--muted); font-size: .88rem; align-self: center; }
  .empty { color: var(--muted); }
  table { width: 100%; border-collapse: collapse; font-size: .92rem; }
  th, td { text-align: left; padding: 4px 0; border-bottom: 1px solid var(--line); }
  th { color: var(--muted); font-weight: 500; }
  td:last-child, th:last-child { text-align: right; }
  td.empty { text-align: left; }
  .note { color: var(--muted); font-size: .9rem; }
  .accounts { margin: 6px 0 0; padding-left: 18px; color: var(--muted); font-size: .92rem; }
  .error { color: #ffb4b6; }
</style>
</head>
<body>
<main>
  <p class="kicker">NightAgent · Deepgram edition</p>
  <h1>Talk to Sam on Deepgram</h1>
  <p class="lede">The same after-hours front desk, the same tools, and the same live ticket board as the
    <a href="/demo">main demo</a>, with the voice layer moved to the Deepgram Voice Agent API. Report a problem with your
    security system and Sam files a real ticket. It lands on the board and in Zendesk, marked as a Deepgram call.</p>
  <ul class="stack" aria-label="What runs this call">
    <li><b>Listen</b> Flux (flux-general-en)</li>
    <li><b>Think</b> Claude via Deepgram</li>
    <li><b>Speak</b> Aura-2</li>
    <li><b>Tools</b> NightAgent's FastAPI backend</li>
  </ul>

  <section class="panel" aria-label="Call">
    <div class="controls">
      <button class="call" id="call" type="button">Start a call</button>
      <span class="mic" id="mic" hidden title="Your microphone level">Mic <span class="mic-track"><span id="mic-bar"></span></span></span>
      <span id="status" role="status"><span class="dot" id="dot"></span>Ready. Use headphones if you can, so Sam doesn't hear itself.</span>
    </div>
    <p class="note" style="margin:12px 0 0">Try one of the fictional demo accounts:</p>
    <ul class="accounts">
      <li>Sunset Dental Group, 310-555-0142</li>
      <li>Westside Self Storage, 310-555-0178 ("the keypad is showing a trouble light")</li>
      <li>Harbor Logistics Warehouse, 424-555-0119 ("the loading dock gate won't close")</li>
    </ul>
    <p class="note" id="limit" style="margin:10px 0 0">Calls end on their own after six minutes. This is a demo with made-up data: don't share real personal details.</p>
  </section>

  <div class="grid">
    <section class="panel" aria-label="Live transcript">
      <h2>Live transcript</h2>
      <div id="transcript" aria-live="polite"><p class="empty">The conversation shows here as Flux hears it.</p></div>
    </section>
    <section class="panel" aria-label="Latency">
      <h2>Response time</h2>
      <p class="note" style="margin-top:0">From Deepgram's AgentStartedSpeaking event: seconds from the end of your turn
        until Sam starts talking, and how much of that was the LLM (think) and the voice (speak).</p>
      <table>
        <thead><tr><th>Turn</th><th>Think</th><th>Speak</th><th>Total</th></tr></thead>
        <tbody id="latency"><tr><td colspan="4" class="empty">No turns yet</td></tr></tbody>
      </table>
      <p class="note" id="median"></p>
      <p class="note">After the call, <a href="/demo" id="board">open the board</a> to see your ticket.</p>
    </section>
  </div>
</main>
<script>
(() => {
  const $ = (id) => document.getElementById(id);
  const button = $("call"), statusEl = $("status"), dot = $("dot"), box = $("transcript"), latencyRows = $("latency");

  // Mic audio to 16 kHz 16-bit PCM, in ~50 ms frames
  const WORKLET = `
    class Pcm16 extends AudioWorkletProcessor {
      constructor() { super(); this.ratio = sampleRate / 16000; this.acc = []; this.pos = 0; }
      process(inputs) {
        const ch = inputs[0] && inputs[0][0];
        if (!ch) return true;
        for (; this.pos < ch.length; this.pos += this.ratio) {
          const s = Math.max(-1, Math.min(1, ch[Math.floor(this.pos)]));
          this.acc.push(s < 0 ? s * 0x8000 : s * 0x7fff);
        }
        this.pos -= ch.length;
        if (this.acc.length >= 800) { this.port.postMessage(Int16Array.from(this.acc).buffer, []); this.acc = []; }
        return true;
      }
    }
    registerProcessor("pcm16", Pcm16);`;

  let call = null;

  function setStatus(text, state) {
    statusEl.lastChild.textContent = text;
    dot.className = "dot" + (state ? " " + state : "");
  }

  function addTurn(role, text) {
    if (box.querySelector(".empty")) box.innerHTML = "";
    const div = document.createElement("div");
    div.className = "turn " + role;
    if (role !== "tool") {
      const who = document.createElement("span");
      who.className = "who";
      who.textContent = role === "assistant" ? "Sam" : "You";
      div.appendChild(who);
    }
    div.appendChild(document.createTextNode(text));
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
  }

  function addLatency(m) {
    if (latencyRows.querySelector(".empty")) latencyRows.innerHTML = "";
    call.latencies.push({ total_latency: m.total_latency, ttt_latency: m.ttt_latency, tts_latency: m.tts_latency });
    const fmt = (v) => typeof v === "number" ? v.toFixed(2) + " s" : "—";
    const tr = document.createElement("tr");
    [String(call.latencies.length), fmt(m.ttt_latency), fmt(m.tts_latency), fmt(m.total_latency)].forEach((t) => {
      const td = document.createElement("td"); td.textContent = t; tr.appendChild(td);
    });
    latencyRows.appendChild(tr);
    const totals = call.latencies.map((l) => l.total_latency).filter((v) => typeof v === "number").sort((a, b) => a - b);
    if (totals.length) $("median").textContent = `Median so far: ${totals[Math.floor(totals.length / 2)].toFixed(2)} s over ${totals.length} turns.`;
  }

  // Aura-2 audio: 24 kHz 16-bit PCM chunks, queued back to back
  function play(buf) {
    if (call.out.state === "suspended") call.out.resume();
    if (!call.talking) { call.talking = true; setStatus("Sam is talking", "talk"); }
    const pcm = new Int16Array(buf);
    if (!pcm.length) return;
    const audio = call.out.createBuffer(1, pcm.length, 24000);
    const ch = audio.getChannelData(0);
    for (let i = 0; i < pcm.length; i++) ch[i] = pcm[i] / 0x8000;
    const src = call.out.createBufferSource();
    src.buffer = audio;
    src.connect(call.out.destination);
    const at = Math.max(call.out.currentTime + 0.02, call.playAt);
    src.start(at);
    call.playAt = at + audio.duration;
    call.playing.add(src);
    src.onended = () => call && call.playing.delete(src);
  }

  function stopPlayback() {  // the caller started talking: Sam stops mid-sentence
    for (const src of call.playing) { try { src.stop(); } catch (e) {} }
    call.playing.clear();
    call.playAt = 0;
  }

  async function runTool(fn) {
    if (fn.name === "end_call") {
      call.ending = true;
      return "ok";
    }
    addTurn("tool", "Tool: " + fn.name.replace(/_/g, " "));
    try {
      const r = await fetch("/api/deepgram/tool", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session: call.session, name: fn.name, arguments: fn.arguments || "{}" }) });
      const data = await r.json();
      return data.content || JSON.stringify({ error: data.detail || "The tool failed." });
    } catch (e) {
      return JSON.stringify({ error: "The tool couldn't be reached. Follow the guardrail for a failed tool." });
    }
  }

  async function onMessage(ev) {
    if (typeof ev.data !== "string") { play(ev.data); return; }
    const m = JSON.parse(ev.data);
    switch (m.type) {
      case "SettingsApplied":
        call.ready = true;  // audio before this would be dropped by Deepgram
        setStatus("Connected. Sam is listening.", "live");
        break;
      case "ConversationText":
        call.transcript.push({ role: m.role, content: m.content });
        addTurn(m.role === "assistant" ? "assistant" : "user", m.content);
        break;
      case "UserStartedSpeaking":
        stopPlayback();
        call.talking = false;
        setStatus("Listening…", "live");
        break;
      case "AgentThinking":
        setStatus("Sam is thinking…", "live");
        break;
      case "AgentStartedSpeaking":
        if (typeof m.total_latency === "number") addLatency(m);  // older API versions put the figures here
        setStatus("Sam is talking", "talk");
        break;
      case "LatencyReport":  // Deepgram sends each figure in its own message; total_latency ends the turn's set
        if (typeof m.ttt_text_latency === "number") call.turn.ttt_latency = m.ttt_text_latency;
        if (typeof m.tts_latency === "number") call.turn.tts_latency = m.tts_latency;
        if (typeof m.total_latency === "number") {
          addLatency({ ...call.turn, total_latency: m.total_latency });
          call.turn = {};
        }
        break;
      case "AgentAudioDone":
        call.talking = false;
        setStatus("Sam is listening.", "live");
        if (call.ending) setTimeout(() => hangUp("Sam ended the call."), Math.max(0, (call.playAt - call.out.currentTime) * 1000) + 400);
        break;
      case "FunctionCallRequest":
        for (const fn of m.functions || []) {
          if (fn.client_side === false) continue;
          const content = await runTool(fn);
          if (call && call.ws.readyState === WebSocket.OPEN && !call.cancelled.has(fn.id)) {
            call.ws.send(JSON.stringify({ type: "FunctionCallResponse", id: fn.id, name: fn.name, content }));
          }
        }
        break;
      case "FunctionCallCancelled":
        (m.functions || [m]).forEach((f) => f.id && call.cancelled.add(f.id));
        break;
      case "Error":
        console.warn("Deepgram error", m);
        setStatus("Deepgram reported an error: " + (m.description || m.code || "unknown"), "");
        break;
    }
  }

  async function startCall() {
    button.disabled = true;
    setStatus("Starting…", "");
    // Sam's speaker is made in the click itself: Chrome keeps an AudioContext made after an await (mic
    // prompt, network) suspended, and the greeting played into silence until the caller spoke. The mic's
    // context is made after the mic is granted, though: made before, a real mic could feed it silence.
    const out = new AudioContext();
    out.resume();
    const fail = (text) => {
      out.close();
      setStatus(text, "");
      button.disabled = false;
    };
    let mic;
    try {
      mic = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    } catch (e) {
      fail("Sam needs your microphone. Allow it and try again.");
      return;
    }
    let start;
    try {
      const r = await fetch("/api/deepgram/session", { method: "POST" });
      start = await r.json();
      if (!r.ok) throw new Error(start.detail || "Couldn't start the call.");
    } catch (e) {
      mic.getTracks().forEach((t) => t.stop());
      fail(e.message);
      statusEl.classList.add("error");
      return;
    }
    statusEl.classList.remove("error");
    box.innerHTML = '<p class="empty">Connecting…</p>';
    latencyRows.innerHTML = '<tr><td colspan="4" class="empty">No turns yet</td></tr>';
    $("median").textContent = "";
    if (out.state !== "running") await out.resume().catch(() => {});
    const input = new AudioContext();
    if (input.state !== "running") await input.resume().catch(() => {});
    const url = URL.createObjectURL(new Blob([WORKLET], { type: "application/javascript" }));
    await input.audioWorklet.addModule(url);
    const node = new AudioWorkletNode(input, "pcm16");
    const source = input.createMediaStreamSource(mic);
    source.connect(node);
    const analyser = input.createAnalyser();
    analyser.fftSize = 512;
    source.connect(analyser);
    const level = new Float32Array(analyser.fftSize);
    $("mic").hidden = false;
    const meter = setInterval(() => {
      analyser.getFloatTimeDomainData(level);
      const rms = Math.sqrt(level.reduce((a, v) => a + v * v, 0) / level.length);
      $("mic-bar").style.width = Math.min(100, Math.round(rms * 400)) + "%";
    }, 100);
    const ws = new WebSocket(start.url, ["bearer", start.token]);
    ws.binaryType = "arraybuffer";  // sync, so audio chunks keep their order
    call = { ws, mic, input, out, node, meter, session: start.session, ready: false, transcript: [], latencies: [],
             playing: new Set(), playAt: 0, turn: {}, cancelled: new Set(), ending: false, startedAt: Date.now() };
    node.port.onmessage = (e) => { if (call && call.ready && ws.readyState === WebSocket.OPEN) ws.send(e.data); };
    ws.onopen = () => ws.send(JSON.stringify(start.settings));
    ws.onmessage = onMessage;
    ws.onclose = () => { if (call && call.ws === ws) hangUp("The call ended."); };
    ws.onerror = () => setStatus("Lost the connection to Deepgram.", "");
    call.timer = setTimeout(() => hangUp("Six minutes are up, so the call ended."), start.max_call_seconds * 1000);
    button.textContent = "Hang up";
    button.classList.add("end");
    button.disabled = false;
  }

  function hangUp(reason) {
    if (!call) return;
    const c = call;
    call = null;
    clearTimeout(c.timer);
    clearInterval(c.meter);
    $("mic").hidden = true;
    try { c.ws.close(); } catch (e) {}
    c.mic.getTracks().forEach((t) => t.stop());
    c.input.close();
    c.out.close();
    const body = JSON.stringify({ session: c.session, transcript: c.transcript.slice(-400), latencies: c.latencies.slice(-200),
                                  duration_secs: (Date.now() - c.startedAt) / 1000 });
    fetch("/api/deepgram/end", { method: "POST", headers: { "Content-Type": "application/json" }, body, keepalive: body.length < 60000 }).catch(() => {});
    setStatus(reason + " Your ticket, if Sam made one, is on the board.", "");
    button.textContent = "Start a call";
    button.classList.remove("end");
  }

  button.addEventListener("click", () => call ? hangUp("You hung up.") : startCall());
  window.addEventListener("pagehide", () => call && hangUp("The call ended."));
})();
</script>
</body>
</html>
"""
