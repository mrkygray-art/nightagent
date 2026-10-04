// Noise mixing and TTS request tests: no network, keys, or cost.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { rms, mixAtSnr, measuredSnrDb } = require('../lib/mix');
const { voiceFor, estimateUsd, synthesize } = require('../lib/tts');
const { silentWav } = require('../lib/wav');
const config = require('../config.json');

// Deterministic pseudo-random signal
function signal(n, amp, seed = 1) {
  let s = seed;
  const out = new Int16Array(n);
  for (let i = 0; i < n; i++) { s = (s * 1103515245 + 12345) % 2147483648; out[i] = Math.round(((s / 2147483648) * 2 - 1) * amp); }
  return out;
}

test('mixAtSnr hits the target SNR', () => {
  const speech = signal(16000, 8000, 1);
  const noise = signal(16000, 20000, 2);
  for (const snr of [0, 10, 20]) {
    const { out, clipped } = mixAtSnr(speech, noise, snr);
    assert.equal(clipped, 0);
    assert.ok(Math.abs(measuredSnrDb(speech, out) - snr) < 0.05, `snr ${snr}`);
  }
});

test('mixAtSnr is independent of the noise file loudness', () => {
  const speech = signal(8000, 6000, 3);
  const a = mixAtSnr(speech, signal(8000, 1000, 4), 10).out;
  const b = mixAtSnr(speech, signal(8000, 30000, 4), 10).out;
  assert.ok(Math.abs(measuredSnrDb(speech, a) - measuredSnrDb(speech, b)) < 0.05);
});

test('mixAtSnr counts clipped samples instead of hiding them', () => {
  const loud = new Int16Array(100).fill(32000);
  const { out, clipped } = mixAtSnr(loud, new Int16Array(100).fill(20000), 0);
  assert.equal(clipped, 100);
  assert.ok(out.every((v) => v === 32767));
});

test('mixAtSnr rejects silent or too-short input', () => {
  assert.throws(() => mixAtSnr(new Int16Array(10), signal(10, 100), 10), /silent/);
  assert.throws(() => mixAtSnr(signal(10, 100), signal(5, 100), 10), /shorter/);
  assert.equal(rms(new Int16Array([3, -3, 3, -3])), 3);
});

test('tts: voices rotate by utterance order', () => {
  const names = [0, 1, 2, 3, 4].map((i) => voiceFor(config.tts, i).name);
  assert.deepEqual(names, ['Roger', 'Jessica', 'Charlie', 'Roger', 'Jessica']);
});

test('tts: cost estimate uses the configured price per 1K characters', () => {
  assert.equal(estimateUsd(config.tts, ['a'.repeat(1500), 'b'.repeat(500)]), 2 * config.tts.pricing.per_1k_chars);
});

const audioResponse = (buf) => ({ ok: true, status: 200, headers: { get: () => null }, arrayBuffer: async () => buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.length), text: async () => '' });

test('tts: request matches config (voice in URL, output format, model, seed, key)', async () => {
  const calls = [];
  const wav = silentWav(1);
  const fetch = async (url, init) => { calls.push({ url, init }); return audioResponse(wav); };
  const r = await synthesize('The NVR is down.', config.tts.voices[1], { tts: config.tts, retry: config.retry, apiKey: 'k', fetch, sleep: async () => {} });
  assert.equal(r.ok, true);
  assert.equal(r.audio.length, wav.length);
  const u = new URL(calls[0].url);
  assert.equal(u.pathname, `/v1/text-to-speech/${config.tts.voices[1].voice_id}`);
  assert.equal(u.searchParams.get('output_format'), 'wav_16000');
  assert.deepEqual(JSON.parse(calls[0].init.body), { text: 'The NVR is down.', model_id: 'eleven_multilingual_v2', seed: config.tts.seed });
  assert.equal(calls[0].init.headers['xi-api-key'], 'k');
});

test('tts: a non-WAV body or an HTTP error is a failure', async () => {
  const notWav = async () => audioResponse(Buffer.from('ID3 mp3 data'));
  assert.match((await synthesize('x', config.tts.voices[0], { tts: config.tts, retry: config.retry, apiKey: 'k', fetch: notWav, sleep: async () => {} })).error, /not a WAV/);
  const denied = async () => ({ ok: false, status: 401, headers: { get: () => null }, text: async () => '{"detail":"missing_permissions"}' });
  const r = await synthesize('x', config.tts.voices[0], { tts: config.tts, retry: config.retry, apiKey: 'k', fetch: denied, sleep: async () => {} });
  assert.equal(r.ok, false);
  assert.match(r.error, /^HTTP 401/);
});
