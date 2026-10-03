// Audio for the voice tests: decode the recorded caller lines, resample to the agent's 16 kHz input,
// and build the listening conditions (background noise at a set loudness, a narrowband phone line).
// Everything is seeded, so a condition sounds the same on every run.
const fs = require('fs');
const path = require('path');
const { MPEGDecoder } = require('mpg123-decoder');

const RATE = 16000;

async function decodeMp3(file) {
  const decoder = new MPEGDecoder();
  await decoder.ready;
  const { channelData, sampleRate } = decoder.decode(new Uint8Array(fs.readFileSync(file)));
  decoder.free();
  const mono = channelData.length > 1
    ? channelData[0].map((v, i) => (v + channelData[1][i]) / 2) : channelData[0];
  return resample(mono, sampleRate, RATE);
}

// Windowed-sinc low-pass, then linear interpolation: good enough for speech, and no aliasing on the way down.
function lowpass(x, rate, cutoff, taps = 101) {
  const h = new Float32Array(taps), mid = (taps - 1) / 2, fc = cutoff / rate;
  let sum = 0;
  for (let i = 0; i < taps; i++) {
    const n = i - mid;
    const sinc = n === 0 ? 2 * fc : Math.sin(2 * Math.PI * fc * n) / (Math.PI * n);
    h[i] = sinc * (0.54 - 0.46 * Math.cos((2 * Math.PI * i) / (taps - 1)));
    sum += h[i];
  }
  const y = new Float32Array(x.length);
  for (let i = 0; i < x.length; i++) {
    let acc = 0;
    for (let k = 0; k < taps; k++) {
      const j = i + k - mid;
      if (j >= 0 && j < x.length) acc += x[j] * h[k];
    }
    y[i] = acc / sum;
  }
  return y;
}

function resample(x, from, to) {
  if (from === to) return Float32Array.from(x);
  const src = to < from ? lowpass(x, from, to * 0.45) : x;
  const out = new Float32Array(Math.floor((src.length * to) / from));
  for (let i = 0; i < out.length; i++) {
    const p = (i * from) / to, j = Math.floor(p), f = p - j;
    out[i] = (src[j] || 0) * (1 - f) + (src[j + 1] || 0) * f;
  }
  return out;
}

function highpass(x, rate, cutoff) {
  const low = lowpass(x, rate, cutoff);
  return x.map((v, i) => v - low[i]);
}

function rng(seed) {
  let s = seed >>> 0;
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
}

function gaussian(rand) {
  return Math.sqrt(-2 * Math.log(rand() + 1e-12)) * Math.cos(2 * Math.PI * rand());
}

// Pink-ish noise (Paul Kellet's filter): the hiss of a busy room
function pink(n, seed) {
  const r = rng(seed), y = new Float32Array(n);
  let b0 = 0, b1 = 0, b2 = 0;
  for (let i = 0; i < n; i++) {
    const w = gaussian(r);
    b0 = 0.99765 * b0 + w * 0.099046; b1 = 0.963 * b1 + w * 0.2965164; b2 = 0.57 * b2 + w * 1.0526913;
    y[i] = b0 + b1 + b2 + w * 0.1848;
  }
  return y;
}

// Brown noise: low traffic rumble
function brown(n, seed) {
  const r = rng(seed), y = new Float32Array(n);
  let last = 0;
  for (let i = 0; i < n; i++) { last = (last + 0.02 * gaussian(r)) * 0.998; y[i] = last; }
  return y;
}

// Crowd babble from other recorded voices played backwards: speech-shaped, but no real words or digits
function babble(n, voices, seed) {
  const r = rng(seed), y = new Float32Array(n);
  for (let v = 0; v < 4; v++) {
    const src = voices[v % voices.length], off = Math.floor(r() * src.length);
    for (let i = 0; i < n; i++) y[i] += src[src.length - 1 - ((i + off) % src.length)];
  }
  return y;
}

function power(x, onlyLoud = false) {
  let peak = 0;
  for (const v of x) peak = Math.max(peak, Math.abs(v));
  let s = 0, c = 0;
  for (const v of x) if (!onlyLoud || Math.abs(v) > peak * 0.05) { s += v * v; c++; }
  return s / Math.max(c, 1);
}

// Scale noise so speech sits snrDb above it (speech power measured over the voiced part only)
function mixAt(speech, noise, snrDb) {
  const k = Math.sqrt(power(speech, true) / (power(noise) * 10 ** (snrDb / 10)));
  return noise.map((v) => v * k);
}

// A narrowband phone line: 300-3400 Hz, 8 kHz, 8-bit mu-law, back up to 16 kHz
function phoneLine(x) {
  const band = lowpass(highpass(x, RATE, 300), RATE, 3400);
  const narrow = resample(band, RATE, 8000).map((v) => muDecode(muEncode(v)));
  return resample(narrow, 8000, RATE);
}
function muEncode(v) {
  const c = Math.max(-1, Math.min(1, v));
  return Math.round(((Math.sign(c) * Math.log1p(255 * Math.abs(c))) / Math.log1p(255)) * 127);
}
function muDecode(q) {
  const y = q / 127;
  return (Math.sign(y) * ((1 + 255) ** Math.abs(y) - 1)) / 255;
}

// Conditions, mildest first. `bed` is noise that keeps going before and after the caller speaks,
// like a real room; `line` runs everything through the phone line.
const CONDITIONS = [
  { id: 'clean', label: 'Quiet room', snr: null, kind: null, line: false },
  { id: 'cafe-10', label: 'Busy café (10 dB)', snr: 10, kind: 'babble', line: false },
  { id: 'street-5', label: 'Street traffic (5 dB)', snr: 5, kind: 'street', line: false },
  { id: 'phone', label: 'Phone line (8 kHz)', snr: null, kind: null, line: true },
  { id: 'phone-cafe-10', label: 'Phone line + café (10 dB)', snr: 10, kind: 'babble', line: true },
  { id: 'cafe-0', label: 'Loud café (0 dB)', snr: 0, kind: 'babble', line: false },
];

async function loadClips(dir) {
  const clips = {};
  for (const f of fs.readdirSync(dir).filter((f) => f.endsWith('.mp3'))) {
    clips[path.basename(f, '.mp3')] = await decodeMp3(path.join(dir, f));
  }
  return clips;
}

// Returns a function that renders any clip in this condition, plus the noise bed for the gaps
function condition(cond, clips, seed = 7) {
  const voices = Object.values(clips);
  const noiseFor = (n, ref, s) => {
    if (!cond.kind) return new Float32Array(n);
    const hiss = pink(n, s + 1);
    const raw = cond.kind === 'babble'
      ? babble(n, voices, s).map((v, i) => v + 0.3 * hiss[i])
      : brown(n, s).map((v, i) => v + 0.15 * hiss[i]);
    return mixAt(ref, raw, cond.snr);
  };
  const ref = clips['maria-full'];
  const finish = (x) => {
    const y = cond.line ? phoneLine(x) : x;
    return y.map((v) => Math.max(-1, Math.min(1, v)));
  };
  return {
    render(clip, s = seed) {
      const noise = noiseFor(clip.length, clip, s);
      return finish(clip.map((v, i) => v + noise[i]));
    },
    bed(n, s = seed + 100) {
      return finish(noiseFor(n, ref, s));
    },
  };
}

function toPcm16(x) {
  const b = Buffer.alloc(x.length * 2);
  for (let i = 0; i < x.length; i++) b.writeInt16LE(Math.round(Math.max(-1, Math.min(1, x[i])) * 32767), i * 2);
  return b;
}

function writeWav(file, x) {
  const pcm = toPcm16(x), h = Buffer.alloc(44);
  h.write('RIFF', 0); h.writeUInt32LE(36 + pcm.length, 4); h.write('WAVE', 8); h.write('fmt ', 12);
  h.writeUInt32LE(16, 16); h.writeUInt16LE(1, 20); h.writeUInt16LE(1, 22); h.writeUInt32LE(RATE, 24);
  h.writeUInt32LE(RATE * 2, 28); h.writeUInt16LE(2, 32); h.writeUInt16LE(16, 34); h.write('data', 36);
  h.writeUInt32LE(pcm.length, 40);
  fs.writeFileSync(file, Buffer.concat([h, pcm]));
}

module.exports = { RATE, CONDITIONS, loadClips, condition, toPcm16, writeWav };
