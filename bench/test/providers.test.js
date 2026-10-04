// Adapter tests with a fake fetch: no network, no keys, no cost.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const deepgram = require('../providers/deepgram');
const elevenlabs = require('../providers/elevenlabs');
const config = require('../config.json');

const AUDIO = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'jb-audio-')), 'u001.wav');
fs.writeFileSync(AUDIO, Buffer.from('RIFF....WAVEfake'));
const KEY = 'test-key-SECRET';

const response = (status, body, headers = {}) => ({
  ok: status >= 200 && status < 300,
  status,
  headers: { get: (h) => headers[h.toLowerCase()] ?? null },
  text: async () => (typeof body === 'string' ? body : JSON.stringify(body)),
});
const DG_OK = { metadata: { duration: 5.2 }, results: { channels: [{ alternatives: [{ transcript: 'the nvr is down' }] }] } };
const EL_OK = { text: 'The NVR is down.' };

// Fake fetch that returns the queued responses in order and records each call.
function fakeFetch(...queue) {
  const calls = [];
  const fn = async (url, init) => {
    calls.push({ url, init });
    const next = queue.shift();
    if (next instanceof Error) throw next;
    return next;
  };
  fn.calls = calls;
  return fn;
}
function fakeSleep() {
  const waits = [];
  const fn = async (ms) => { waits.push(ms); };
  fn.waits = waits;
  return fn;
}

for (const [name, adapter, ok, expectedText] of [
  ['deepgram', deepgram, DG_OK, 'the nvr is down'],
  ['elevenlabs', elevenlabs, EL_OK, 'The NVR is down.'],
]) {
  test(`${name}: success returns text, latency, and raw body`, async () => {
    const fetch = fakeFetch(response(200, ok));
    const r = await adapter.transcribe(AUDIO, { apiKey: KEY, fetch, sleep: fakeSleep() });
    assert.equal(r.text, expectedText);
    assert.equal(r.error, null);
    assert.equal(r.attempts, 1);
    assert.equal(typeof r.latencyMs, 'number');
    assert.deepEqual(r.raw, ok);
  });

  test(`${name}: 429 is retried, honoring Retry-After`, async () => {
    const fetch = fakeFetch(response(429, { error: 'rate limited' }, { 'retry-after': '2' }), response(200, ok));
    const sleep = fakeSleep();
    const r = await adapter.transcribe(AUDIO, { apiKey: KEY, fetch, sleep });
    assert.equal(r.text, expectedText);
    assert.equal(r.attempts, 2);
    assert.deepEqual(sleep.waits, [2000]);
  });

  test(`${name}: 500 is retried twice with backoff, then recorded as a failure`, async () => {
    const fetch = fakeFetch(response(500, 'boom'), response(502, 'boom'), response(503, 'boom'));
    const sleep = fakeSleep();
    const r = await adapter.transcribe(AUDIO, { apiKey: KEY, fetch, sleep });
    assert.equal(r.text, null);
    assert.equal(r.attempts, 3);
    assert.match(r.error, /^HTTP 503/);
    assert.deepEqual(sleep.waits, config.retry.backoff_ms);
    assert.equal(fetch.calls.length, 3);
  });

  test(`${name}: other 4xx errors are not retried`, async () => {
    const fetch = fakeFetch(response(401, { detail: 'invalid api key' }));
    const r = await adapter.transcribe(AUDIO, { apiKey: KEY, fetch, sleep: fakeSleep() });
    assert.equal(r.attempts, 1);
    assert.match(r.error, /^HTTP 401/);
  });

  test(`${name}: network errors are retried`, async () => {
    const fetch = fakeFetch(new TypeError('fetch failed'), response(200, ok));
    const r = await adapter.transcribe(AUDIO, { apiKey: KEY, fetch, sleep: fakeSleep() });
    assert.equal(r.text, expectedText);
    assert.equal(r.attempts, 2);
  });

  test(`${name}: an unexpected response shape is a failure, not an empty transcript`, async () => {
    const fetch = fakeFetch(response(200, { something: 'else' }));
    const r = await adapter.transcribe(AUDIO, { apiKey: KEY, fetch, sleep: fakeSleep() });
    assert.equal(r.text, null);
    assert.match(r.error, /unexpected response/);
  });

  test(`${name}: errors never contain the API key`, async () => {
    const fetch = fakeFetch(response(400, { detail: 'bad request' }));
    const r = await adapter.transcribe(AUDIO, { apiKey: KEY, fetch, sleep: fakeSleep() });
    assert.ok(!JSON.stringify(r).includes(KEY));
  });

  test(`${name}: a missing key fails before any request`, async () => {
    const saved = { DEEPGRAM_API_KEY: process.env.DEEPGRAM_API_KEY, ELEVENLABS_API_KEY: process.env.ELEVENLABS_API_KEY };
    delete process.env.DEEPGRAM_API_KEY; delete process.env.ELEVENLABS_API_KEY;
    const fetch = fakeFetch();
    try {
      await assert.rejects(adapter.transcribe(AUDIO, { fetch }), /is not set/);
      assert.equal(fetch.calls.length, 0);
    } finally {
      for (const [k, v] of Object.entries(saved)) if (v !== undefined) process.env[k] = v;
    }
  });
}

test('deepgram: baseline request matches config (model, settings, auth, audio type)', async () => {
  const fetch = fakeFetch(response(200, DG_OK));
  await deepgram.transcribe(AUDIO, { apiKey: KEY, fetch, sleep: fakeSleep() });
  const { url, init } = fetch.calls[0];
  const u = new URL(url);
  assert.equal(`${u.origin}${u.pathname}`, 'https://api.deepgram.com/v1/listen');
  assert.equal(u.searchParams.get('model'), 'nova-3');
  assert.equal(u.searchParams.get('language'), 'en');
  assert.equal(u.searchParams.get('smart_format'), 'true');
  assert.deepEqual(u.searchParams.getAll('keyterm'), []);
  assert.equal(init.headers.Authorization, `Token ${KEY}`);
  assert.equal(init.headers['Content-Type'], 'audio/wav');
});

test('deepgram: boosted request sends one keyterm parameter per term', async () => {
  const fetch = fakeFetch(response(200, DG_OK));
  await deepgram.transcribe(AUDIO, { apiKey: KEY, fetch, sleep: fakeSleep(), keyterms: ['PoE', 'Cisco Catalyst', 'J-hook'] });
  const u = new URL(fetch.calls[0].url);
  assert.deepEqual(u.searchParams.getAll('keyterm'), ['PoE', 'Cisco Catalyst', 'J-hook']);
  assert.match(fetch.calls[0].url, /keyterm=Cisco(\+|%20)Catalyst/);
});

test('elevenlabs: baseline form matches config (model, settings, auth, file)', async () => {
  const fetch = fakeFetch(response(200, EL_OK));
  await elevenlabs.transcribe(AUDIO, { apiKey: KEY, fetch, sleep: fakeSleep() });
  const { url, init } = fetch.calls[0];
  assert.equal(url, 'https://api.elevenlabs.io/v1/speech-to-text');
  assert.equal(init.headers['xi-api-key'], KEY);
  const form = init.body;
  assert.equal(form.get('model_id'), 'scribe_v2');
  assert.equal(form.get('language_code'), 'en');
  assert.equal(form.get('tag_audio_events'), 'false');
  assert.equal(form.get('diarize'), 'false');
  assert.equal(form.get('timestamps_granularity'), 'none');
  assert.equal(form.get('file').name, 'u001.wav');
  assert.deepEqual(form.getAll('keyterms'), []);
});

test('elevenlabs: boosted form sends one keyterms field per term', async () => {
  const fetch = fakeFetch(response(200, EL_OK));
  await elevenlabs.transcribe(AUDIO, { apiKey: KEY, fetch, sleep: fakeSleep(), keyterms: ['PoE', 'Cisco Catalyst'] });
  assert.deepEqual(fetch.calls[0].init.body.getAll('keyterms'), ['PoE', 'Cisco Catalyst']);
});

test('every canonical term fits both providers\' keyterm limits', () => {
  const terms = Object.keys(require('../data/terms.json'));
  assert.ok(terms.length <= 1000);
  for (const t of terms) {
    assert.ok(t.length < 50, t);
    assert.ok(t.split(/\s+/).length <= 5, t);
    assert.ok(!/[<>{}[\]\\]/.test(t), t);
  }
});
