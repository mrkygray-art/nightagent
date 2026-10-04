// Plans and executes a benchmark run. Adapters are passed in, so tests can use fakes.
//
// Order: repeat run -> utterance -> provider -> condition, so each provider sees the same
// audio at about the same time (less time-of-day bias in latency).
// Requests are sequential, so latency isn't distorted by our own concurrency.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { execSync } = require('child_process');
const { wavSeconds } = require('./wav');
const { estimateUsd } = require('./cost');

const CONDITIONS = ['baseline', 'boosted'];

function plan({ config, utterances, audioDir, providers, sources, conditions = CONDITIONS }) {
  const jobs = [];
  const missingAudio = {};
  for (const source of sources) {
    const runs = config.runs_per_source[source];
    if (!runs) throw new Error(`config.json has no runs_per_source for "${source}"`);
    for (let run = 1; run <= runs; run++) {
      for (const u of utterances) {
        const file = path.join(audioDir, source, `${u.id}.wav`);
        if (!fs.existsSync(file)) { if (run === 1) (missingAudio[source] ||= []).push(u.id); continue; }
        const seconds = wavSeconds(file);
        for (const provider of providers) {
          for (const condition of conditions) {
            if (condition === 'boosted' && !config.providers[provider].boost?.available) continue;
            jobs.push({ provider, condition, source, id: u.id, run, file, seconds });
          }
        }
      }
    }
  }
  const estUsd = jobs.reduce((sum, j) => sum + estimateUsd(config.pricing, j.provider, j.condition, j.seconds), 0);
  const audioMinutes = jobs.reduce((sum, j) => sum + j.seconds, 0) / 60;
  return { jobs, missingAudio, estUsd, audioMinutes };
}

function gitCommit(cwd) {
  try { return execSync('git rev-parse HEAD', { cwd, stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim(); }
  catch { return null; }
}

const sha256 = (file) => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');

async function execute({ planned, config, adapters, keyterms, runDir, dataDir, log = console.log }) {
  const startedAt = new Date().toISOString();
  fs.mkdirSync(runDir, { recursive: true });
  fs.writeFileSync(path.join(runDir, 'config.snapshot.json'), `${JSON.stringify({
    startedAt,
    gitCommit: gitCommit(dataDir),
    dataset: { utterancesSha256: sha256(path.join(dataDir, 'utterances.json')), termsSha256: sha256(path.join(dataDir, 'terms.json')) },
    keyterms,
    estimate: { requests: planned.jobs.length, audioMinutes: planned.audioMinutes, usd: planned.estUsd },
    config,
  }, null, 2)}\n`);

  const files = {}; // raw file path -> contents, flushed after every request so a crash keeps results
  let spent = 0;
  let done = 0;
  for (const j of planned.jobs) {
    const cost = estimateUsd(config.pricing, j.provider, j.condition, j.seconds);
    if (config.budget.max_usd_per_run != null && spent + cost > config.budget.max_usd_per_run) {
      log(`Stopped: the next request would pass the $${config.budget.max_usd_per_run} cap.`);
      break;
    }
    const r = await adapters[j.provider].transcribe(j.file, { keyterms: j.condition === 'boosted' ? keyterms : undefined });
    if (!r.error) spent += cost;
    const out = path.join(runDir, 'raw', j.provider, j.condition, j.source, `${j.id}.json`);
    const p = config.providers[j.provider];
    files[out] ||= { id: j.id, provider: j.provider, model: p.model, condition: j.condition, source: j.source,
      settings: { ...p.baseline, keyterms: j.condition === 'boosted' ? keyterms.length : 0 }, audioSeconds: j.seconds, runs: [] };
    files[out].runs.push({ run: j.run, at: new Date().toISOString(), text: r.text, latencyMs: r.latencyMs, attempts: r.attempts, error: r.error, response: r.raw });
    fs.mkdirSync(path.dirname(out), { recursive: true });
    fs.writeFileSync(out, `${JSON.stringify(files[out], null, 2)}\n`);
    done++;
    log(`[${done}/${planned.jobs.length}] ${j.provider}/${j.condition}/${j.source} ${j.id} run ${j.run}: ${r.error ? `FAILED (${r.error.slice(0, 80)})` : `${r.latencyMs} ms`}`);
  }
  return { done, spentUsd: spent };
}

module.exports = { plan, execute, CONDITIONS };
