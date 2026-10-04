// Runner, cost, and WAV tests with fake adapters: no network, keys, or cost.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');
const { wavSeconds, silentWav } = require('../lib/wav');
const { perMinute, estimateUsd, perAudioHourUsd } = require('../lib/cost');
const { plan, execute } = require('../lib/runner');
const { scoreRun } = require('../score');
const realConfig = require('../config.json');

const DATA = path.join(__dirname, '..', 'data');
const UTTS = JSON.parse(fs.readFileSync(path.join(DATA, 'utterances.json'), 'utf8')).slice(0, 3);
const config = (overrides = {}) => ({ ...structuredClone(realConfig), ...overrides });

// Audio folder with 6-second clips for the given ids
function audioDir(source, ids) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'jb-wav-'));
  fs.mkdirSync(path.join(root, source));
  for (const id of ids) fs.writeFileSync(path.join(root, source, `${id}.wav`), silentWav(6));
  return root;
}

function fakeAdapter(name, { failIds = [] } = {}) {
  const calls = [];
  return {
    calls,
    transcribe: async (file, opts) => {
      calls.push({ file, keyterms: opts.keyterms });
      const id = path.parse(file).name;
      if (failIds.includes(id)) return { text: null, latencyMs: 50, attempts: 3, error: 'HTTP 500: boom', raw: 'boom' };
      const u = UTTS.find((x) => x.id === id);
      return { text: u.reference, latencyMs: 100, attempts: 1, error: null, raw: { text: u.reference, from: name } };
    },
  };
}

test('wavSeconds reads the duration from the header', () => {
  const f = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'jb-')), 'a.wav');
  fs.writeFileSync(f, silentWav(7.5));
  assert.equal(wavSeconds(f), 7.5);
  fs.writeFileSync(f, 'not audio');
  assert.throws(() => wavSeconds(f), /not a WAV/);
});

test('cost uses config prices, including the boosting surcharge', () => {
  const p = realConfig.pricing;
  assert.equal(perMinute(p, 'deepgram', false), p.deepgram.per_minute);
  assert.equal(perMinute(p, 'deepgram', true), p.deepgram.per_minute + p.deepgram.boost_per_minute);
  assert.equal(perMinute(p, 'elevenlabs', false), p.elevenlabs.per_hour / 60);
  assert.equal(perAudioHourUsd(p, 'elevenlabs', 'boosted'), p.elevenlabs.per_hour + p.elevenlabs.boost_per_hour);
  assert.equal(estimateUsd(p, 'deepgram', 'baseline', 120), 2 * p.deepgram.per_minute);
});

test('plan: runs per source, both providers and conditions, missing audio listed', () => {
  const dir = audioDir('human', ['u001', 'u002']); // u003 not recorded
  const pl = plan({ config: config(), utterances: UTTS, audioDir: dir, providers: ['deepgram', 'elevenlabs'], sources: ['human'] });
  assert.equal(pl.jobs.length, 2 * 2 * 2 * realConfig.runs_per_source.human);
  assert.deepEqual(pl.missingAudio, { human: ['u003'] });
  assert.equal(pl.audioMinutes, (pl.jobs.length * 6) / 60);
  assert.ok(pl.estUsd > 0);
});

test('plan: a provider without boosting gets no boosted jobs (recorded as not available)', () => {
  const c = config();
  c.providers.elevenlabs.boost.available = false;
  const pl = plan({ config: c, utterances: UTTS, audioDir: audioDir('human', ['u001']), providers: ['elevenlabs'], sources: ['human'] });
  assert.ok(pl.jobs.every((j) => j.condition === 'baseline'));
});

test('execute: writes the spec layout, a config snapshot, and scorable raw files', async () => {
  const dir = audioDir('human', ['u001', 'u002', 'u003']);
  const c = config({ runs_per_source: { human: 2 }, budget: { max_usd_per_run: 1 } });
  const pl = plan({ config: c, utterances: UTTS, audioDir: dir, providers: ['deepgram', 'elevenlabs'], sources: ['human'], conditions: ['baseline', 'boosted'] });
  const adapters = { deepgram: fakeAdapter('deepgram', { failIds: ['u002'] }), elevenlabs: fakeAdapter('elevenlabs') };
  const runDir = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'jb-res-')), 'r1');
  const out = await execute({ planned: pl, config: c, adapters, keyterms: ['PoE', 'NVR'], runDir, dataDir: DATA, log: () => {} });
  assert.equal(out.done, pl.jobs.length);

  const snap = JSON.parse(fs.readFileSync(path.join(runDir, 'config.snapshot.json'), 'utf8'));
  assert.equal(snap.config.providers.deepgram.model, 'nova-3');
  assert.equal(snap.dataset.utterancesSha256.length, 64);
  assert.deepEqual(snap.keyterms, ['PoE', 'NVR']);

  const raw = JSON.parse(fs.readFileSync(path.join(runDir, 'raw', 'deepgram', 'boosted', 'human', 'u002.json'), 'utf8'));
  assert.equal(raw.model, 'nova-3');
  assert.equal(raw.settings.keyterms, 2);
  assert.equal(raw.audioSeconds, 6);
  assert.deepEqual(raw.runs.map((r) => [r.run, r.error]), [[1, 'HTTP 500: boom'], [2, 'HTTP 500: boom']]);

  // Keyterms go only to boosted requests
  assert.ok(adapters.elevenlabs.calls.some((x) => x.keyterms === undefined));
  assert.ok(adapters.elevenlabs.calls.some((x) => x.keyterms?.length === 2));

  const summary = scoreRun(runDir, DATA);
  const g = summary.groups.find((x) => x.provider === 'deepgram' && x.condition === 'boosted');
  assert.equal(g.failures, 2);
  assert.equal(g.scoredRequests, 4);
  assert.equal(g.termAccuracy.pct, 100);
  assert.equal(g.estCost.pricesRetrievedOn, realConfig.pricing.retrieved_on);
  assert.equal(g.estCost.usd, Math.round(estimateUsd(realConfig.pricing, 'deepgram', 'boosted', 24) * 1e6) / 1e6);
});

test('execute: stops before passing the spend cap', async () => {
  const dir = audioDir('human', ['u001', 'u002', 'u003']);
  const c = config({ runs_per_source: { human: 1 } });
  const pl = plan({ config: c, utterances: UTTS, audioDir: dir, providers: ['deepgram'], sources: ['human'], conditions: ['baseline'] });
  c.budget = { max_usd_per_run: estimateUsd(c.pricing, 'deepgram', 'baseline', 6) * 2.5 }; // room for 2 of 3
  const adapter = fakeAdapter('deepgram');
  const logs = [];
  const out = await execute({ planned: pl, config: c, adapters: { deepgram: adapter }, keyterms: [], runDir: fs.mkdtempSync(path.join(os.tmpdir(), 'jb-cap-')), dataDir: DATA, log: (m) => logs.push(m) });
  assert.equal(out.done, 2);
  assert.equal(adapter.calls.length, 2);
  assert.ok(logs.some((m) => /Stopped/.test(m)));
});

test('run.js without --confirm makes no API calls and writes no results', () => {
  const results = fs.mkdtempSync(path.join(os.tmpdir(), 'jb-cli-'));
  const r = spawnSync(process.execPath, [path.join(__dirname, '..', 'run.js'), '--providers', 'deepgram', '--sources', 'human',
    '--audio', audioDir('human', ['u001']), '--results', results], { encoding: 'utf8', env: { ...process.env, DEEPGRAM_API_KEY: '' } });
  assert.match(r.stdout + r.stderr, /No API calls were made/);
  assert.match(r.stdout, /estimated cost:/);
  assert.deepEqual(fs.readdirSync(results), []);
});
