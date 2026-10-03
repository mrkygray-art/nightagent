// Voice tests: a scripted caller phones the live Sam over the same WebSocket the demo page uses and
// streams recorded speech in real time, 20 ms at a time, like a microphone would.
//
//   node run.js                      run everything, print results
//   node run.js --save               ...and write ../app/voice_lab.json for the /lab page
//   node run.js --only numbers --conditions clean,phone --callers maria
//
// Each call is a real conversation (it uses call minutes). Calls end before a ticket is made; the
// conversation ids are saved so the server leaves these calls out of the real-call numbers.
const fs = require('fs');
const path = require('path');
const WebSocket = require('ws');
const A = require('./audio');

const AGENT = 'agent_0301m3ws1zwae8ya6j72bcv7a193'; // Sam
const ORIGIN = 'https://nightshift-dispatch.vercel.app';
const FRAME = 320; // 20 ms at 16 kHz

const CALLERS = {
  maria: { clip: 'maria-full', name: 'Lopez', digits: '3105550142', business: 'Sunset Dental' },
  james: { clip: 'james-full', name: 'Carter', digits: '3105550178', business: 'Westside Self Storage' },
  priya: { clip: 'priya-full', name: 'Shah', digits: '4245550119', business: 'Harbor Logistics' },
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const WORDS = { zero: '0', oh: '0', o: '0', one: '1', two: '2', three: '3', four: '4', five: '5', six: '6',
  seven: '7', eight: '8', nine: '9' };
// Digits in the order they were said, whether written as numerals or words ("double five" too)
function digitsIn(text) {
  const out = [];
  const tokens = (text || '').toLowerCase().replace(/[^a-z0-9 ]+/g, ' ').split(/\s+/).filter(Boolean);
  for (let i = 0; i < tokens.length; i++) {
    const t = tokens[i];
    if ((t === 'double' || t === 'triple') && WORDS[tokens[i + 1]]) {
      out.push(WORDS[tokens[i + 1]].repeat(t === 'double' ? 2 : 3)); i++;
    } else if (/^\d+$/.test(t)) out.push(t);
    else if (WORDS[t] && (t !== 'o' || out.length)) out.push(WORDS[t]);
  }
  return out.join('');
}

// Index of the last sample of speech: the end of the last 20 ms window louder than 40 dB below the peak
function lastVoiced(x) {
  let peak = 0;
  for (const v of x) peak = Math.max(peak, Math.abs(v));
  const floor = (peak * 0.01) ** 2;
  for (let i = x.length - FRAME; i >= 0; i -= FRAME) {
    let s = 0;
    for (let j = i; j < i + FRAME; j++) s += x[j] * x[j];
    if (s / FRAME > floor) return i + FRAME - 1;
  }
  return x.length - 1;
}

class Call {
  constructor(cond) {
    this.cond = cond;
    this.events = [];
    this.queue = [];
    this.agentAudioEnd = 0;
    this.lastAudioAt = 0;
    this.closed = false;
  }

  t() { return Date.now() - this.t0; }

  open() {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(`wss://api.elevenlabs.io/v1/convai/conversation?agent_id=${AGENT}`, { headers: { Origin: ORIGIN } });
      this.ws.on('error', reject);
      this.ws.on('close', (code, reason) => { this.closed = true; this.closedAt = this.t(); this.closeInfo = { code, reason: String(reason), by_us: Boolean(this.closing) }; clearInterval(this.timer); });
      this.ws.on('message', (raw) => this.onMessage(JSON.parse(raw), resolve));
      this.ws.on('open', () => {
        this.t0 = Date.now();
        this.ws.send(JSON.stringify({ type: 'conversation_initiation_client_data' }));
        this.startMic();
      });
    });
  }

  onMessage(m, ready) {
    const now = this.t();
    switch (m.type) {
      case 'conversation_initiation_metadata':
        this.conversationId = m.conversation_initiation_metadata_event.conversation_id;
        ready();
        break;
      case 'ping':
        this.ws.send(JSON.stringify({ type: 'pong', event_id: m.ping_event.event_id }));
        break;
      case 'audio': {
        const bytes = Buffer.from(m.audio_event.audio_base_64, 'base64').length;
        // Playback model: each chunk plays after the one before it finishes, as a speaker would
        if (now > this.agentAudioEnd) this.events.push({ t: now, type: 'agent_audio_start' });
        this.agentAudioEnd = Math.max(this.agentAudioEnd, now) + (bytes / 2 / A.RATE) * 1000;
        this.lastAudioAt = now;
        break;
      }
      case 'agent_response':
        this.events.push({ t: now, type: 'agent', text: m.agent_response_event.agent_response });
        break;
      case 'user_transcript':
        this.events.push({ t: now, type: 'heard', text: m.user_transcription_event.user_transcript });
        break;
      case 'interruption':
        this.agentAudioEnd = now; // the client stops playback
        this.events.push({ t: now, type: 'interruption' });
        break;
      default:
        if (/tool/.test(m.type)) {
          const ev = Object.values(m).find((v) => v && typeof v === 'object') || {};
          this.events.push({ t: now, type: 'tool', tool: ev.tool_name || m.type });
        }
    }
  }

  // The "microphone": every 20 ms send the next frame of speech, or the room's noise bed when quiet
  startMic() {
    const bed = A.condition(this.cond, this.clips).bed(A.RATE * 120);
    let sent = 0, bedPos = 0;
    this.timer = setInterval(() => {
      const due = Math.floor(this.t() / 20);
      while (sent < due && !this.closed) {
        let frame;
        if (this.queue.length) { const q = this.queue.shift(); frame = q.f; if (q.mark) q.mark(this.t()); }
        else { frame = bed.subarray(bedPos, bedPos + FRAME); bedPos = (bedPos + FRAME) % (bed.length - FRAME); }
        this.ws.send(JSON.stringify({ user_audio_chunk: A.toPcm16(frame).toString('base64') }));
        sent++;
        if (!this.queue.length && this.speaking) { this.speaking(); this.speaking = null; }
      }
    }, 10);
  }

  // Queue a rendered clip; resolves when its last frame has gone out. `voicedEnd` is when the frame
  // with the last spoken sound went out (found on the clean clip, so noise can't hide it): the moment the
  // caller stopped talking, which is where response time is measured from.
  speak(samples, clean = samples) {
    const last = lastVoiced(clean);
    const said = { start: this.t() };
    for (let i = 0; i < samples.length; i += FRAME) {
      const f = new Float32Array(FRAME); f.set(samples.subarray(i, i + FRAME));
      this.queue.push({ f, mark: i <= last && last < i + FRAME ? (t) => { said.voicedEnd = t + 20; } : null });
    }
    return new Promise((r) => { this.speaking = () => r({ ...said, end: this.t() }); });
  }

  agentSpeaking() { return this.t() < this.agentAudioEnd; }

  async until(pred, timeoutMs) {
    const end = Date.now() + timeoutMs;
    while (Date.now() < end && !this.closed) { if (pred()) return true; await sleep(25); }
    return pred();
  }

  // Sam finished talking: nothing playing and no new audio for a moment
  quiet(ms = 500) { return !this.agentSpeaking() && this.t() - this.lastAudioAt > ms; }

  after(t, type) { return this.events.filter((e) => e.t >= t && (!type || e.type === type)); }

  async greeting() {
    await this.until(() => this.after(0, 'agent').length && this.quiet(), 15000);
  }

  close() { this.closing = true; if (!this.closed) this.ws.close(); return sleep(300); }
}

async function newCall(cond, clips) {
  const c = new Call(cond); c.clips = clips;
  await c.open();
  return c;
}

const ms = (x) => (x === undefined || x === null ? null : Math.round(x));

// 1. Phone numbers and names in noise
async function numbersTest(cond, who, clips) {
  const caller = CALLERS[who];
  const c = await newCall(cond, clips);
  await c.greeting();
  const said = await c.speak(A.condition(cond, clips).render(clips[caller.clip]), clips[caller.clip]);
  const readBack = () => c.after(said.voicedEnd, 'agent').some((e) => digitsIn(e.text).length >= 7 || /confirm|is that right|correct\?/i.test(e.text));
  // Sam's words arrive before its audio: wait for the sound too, or the reply can't be timed
  await c.until(() => readBack() && c.after(said.start, 'agent_audio_start').length && c.quiet(), 30000);
  await c.close();
  const heard = c.after(said.start, 'heard').map((e) => e.text).join(' ');
  const replies = c.after(said.voicedEnd, 'agent').map((e) => e.text);
  const firstAudio = c.after(said.voicedEnd, 'agent_audio_start')[0];
  // Sam's voice starting while the caller is still talking: the turn was ended too early
  const starts = c.after(said.start, 'agent_audio_start');
  return {
    test: 'numbers', condition: cond.id, caller: who, conversation_id: c.conversationId,
    heard, replies,
    number_heard: digitsIn(heard).includes(caller.digits),
    name_heard: heard.toLowerCase().includes(caller.name.toLowerCase()),
    read_back_right: replies.some((t) => digitsIn(t).includes(caller.digits)),
    response_ms: firstAudio ? ms(firstAudio.t - said.voicedEnd) : null,
    first_sound_ms: starts[0] ? ms(starts[0].t - said.voicedEnd) : null,
    started_before_caller_finished: starts.some((e) => e.t < said.voicedEnd - 100),
    turn_split: c.after(said.start, 'heard').length > 1,
    tools: c.events.filter((e) => e.type === 'tool').map((e) => e.tool),
    ended_early: c.closeInfo && !c.closeInfo.by_us ? c.closeInfo : null,
  };
}

// 2a. Talking over Sam: does Sam stop, and use what the caller just said?
async function interruptionTest(clips) {
  const cond = A.CONDITIONS[0];
  const c = await newCall(cond, clips);
  await c.greeting();
  const opener = await c.speak(clips['maria-opener']);
  const isReadBack = (e) => /confirm|is that right|have you as|correct\?/i.test(e.text);
  await c.until(() => c.after(opener.voicedEnd, 'agent').some(isReadBack), 25000);
  const rb = c.after(opener.voicedEnd, 'agent').find(isReadBack);
  let result = { test: 'interruption', conversation_id: c.conversationId, read_back: rb ? rb.text : null };
  if (rb) {
    await c.until(() => c.after(rb.t, 'agent_audio_start').length, 8000);
    const audioStart = (c.after(rb.t, 'agent_audio_start')[0] || {}).t;
    await c.until(() => c.t() >= audioStart + 1500, 3000);
    const stillTalking = c.agentSpeaking();
    const barge = c.speak(clips['maria-bargein']);
    const bargeStart = c.t();
    await c.until(() => c.after(bargeStart, 'interruption').length, 4000);
    const stop = c.after(bargeStart, 'interruption')[0];
    const said = await barge;
    await c.until(() => c.after(said.voicedEnd, 'agent').length && c.quiet(), 20000);
    const reply = c.after(said.voicedEnd, 'agent').map((e) => e.text).join(' ');
    const firstAudio = c.after(said.voicedEnd, 'agent_audio_start')[0];
    result = {
      ...result,
      talking_when_cut_in: stillTalking,
      stopped: Boolean(stop),
      stop_ms: stop ? ms(stop.t - bargeStart) : null,
      heard: c.after(bargeStart, 'heard').map((e) => e.text).join(' '),
      reply,
      used_new_detail: /door|lock/i.test(reply),
      response_ms: firstAudio ? ms(firstAudio.t - said.voicedEnd) : null,
    };
  }
  await c.close();
  result.passed = Boolean(result.talking_when_cut_in && result.stopped && result.used_new_detail);
  return result;
}

// 2b. Going quiet mid-sentence: does Sam check in (not hang up, not invent anything), then carry on?
async function silenceTest(clips, quietMs = 25000) {
  const cond = A.CONDITIONS[0];
  const c = await newCall(cond, clips);
  await c.greeting();
  const opener = await c.speak(clips['silence-opener']);
  await c.until(() => false, quietMs);
  const during = c.after(opener.voicedEnd, 'agent');
  const hungUp = c.closed;
  let reply = '';
  if (!hungUp) {
    const said = await c.speak(clips['silence-followup']);
    await c.until(() => c.after(said.voicedEnd, 'agent').length && c.quiet(), 15000);
    reply = c.after(said.voicedEnd, 'agent').map((e) => e.text).join(' ');
  }
  await c.close();
  // The first thing Sam says answers the half-finished sentence; anything after that, with the caller
  // still silent, is Sam checking in
  const result = {
    test: 'silence', conversation_id: c.conversationId, quiet_ms: quietMs,
    spoke_during_silence: during.map((e) => ({ after_ms: ms(e.t - opener.voicedEnd), text: e.text })),
    first_reply_ms: during[0] ? ms(during[0].t - opener.voicedEnd) : null,
    check_in_ms: during[1] ? ms(during[1].t - opener.voicedEnd) : null,
    hung_up: hungUp,
    close_info: hungUp ? c.closeInfo : null,
    tools: c.events.filter((e) => e.type === 'tool').map((e) => e.tool),
    reply,
    carried_on: /beep|trouble|code|panel|alarm/i.test(reply),
  };
  result.passed = Boolean(result.check_in_ms && !hungUp && result.carried_on && !result.tools.includes('create_ticket'));
  return result;
}

function arg(name, fallback) {
  const i = process.argv.indexOf(`--${name}`);
  return i > -1 ? process.argv[i + 1] : fallback;
}

(async () => {
  const clips = await A.loadClips(path.join(__dirname, 'clips'));
  const only = arg('only', 'numbers,interruption,silence').split(',');
  const conds = A.CONDITIONS.filter((c) => arg('conditions', A.CONDITIONS.map((x) => x.id).join(',')).split(',').includes(c.id));
  const callers = arg('callers', Object.keys(CALLERS).join(',')).split(',');
  const repeats = Number(arg('repeats', 3));
  const results = [];
  const started = Date.now();
  const log = (r) => { results.push(r); console.log(JSON.stringify(r)); };
  try {
    if (only.includes('numbers')) {
      for (const cond of conds) for (const who of callers) { log(await numbersTest(cond, who, clips)); await sleep(1500); }
    }
    if (only.includes('interruption')) for (let i = 0; i < repeats; i++) { log(await interruptionTest(clips)); await sleep(1500); }
    if (only.includes('silence')) for (let i = 0; i < repeats; i++) { log(await silenceTest(clips)); await sleep(1500); }
  } catch (e) {
    console.error('stopped:', e.message);
  }
  console.log(`\n${results.length} calls in ${Math.round((Date.now() - started) / 1000)} s`);
  const out = path.join(__dirname, 'out', `run-${Date.now()}.json`);
  fs.mkdirSync(path.dirname(out), { recursive: true });
  fs.writeFileSync(out, JSON.stringify({ run_at: Math.round(started / 1000), results }, null, 1));
  console.log('raw results:', out);
})();
