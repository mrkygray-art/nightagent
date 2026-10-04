// Jargon Bench runner.
//
//   node run.js --dry-run                         validate the dataset; no API calls
//   node run.js --providers deepgram,elevenlabs --sources human --conditions baseline
//                                                 print the plan and estimated cost; no API calls
//   node run.js ... --confirm                     run it, then score it into summary.json
//
// Options: --data <dir> (dataset), --audio <dir> (audio root), --results <dir> (output root).
// A paid run needs config.json budget.max_usd_per_run set, an estimate under it, and --confirm.
const fs = require('fs');
const path = require('path');
const config = require('./config.json');
const { validateData } = require('./lib/validate');
const { loadEnv } = require('./lib/env');
const { plan, execute, CONDITIONS } = require('./lib/runner');
const { scoreRun } = require('./score');

const arg = (name) => { const i = process.argv.indexOf(name); return i === -1 ? null : process.argv[i + 1]; };
const list = (name, fallback) => (arg(name) ? arg(name).split(',').map((s) => s.trim()).filter(Boolean) : fallback);
const usd = (n) => `$${n.toFixed(4)}`;

function dryRun(dataDir) {
  const { errors, warnings, stats } = validateData(dataDir);
  for (const w of warnings) console.warn(`warning: ${w}`);
  if (errors.length) {
    console.error(`\nDataset check FAILED with ${errors.length} error(s):`);
    for (const e of errors) console.error(`  - ${e}`);
    return 1;
  }
  const cats = Object.entries(stats.byCategory).map(([c, n]) => `${c} ${n}`).join(', ');
  console.log('Dataset OK');
  console.log(`  utterances:        ${stats.utterances} (${cats})`);
  console.log(`  terms:             ${stats.terms} defined, ${stats.termsUsed} used`);
  console.log(`  term occurrences:  ${stats.termOccurrences}`);
  console.log('No API calls were made.');
  return 0;
}

async function paidRun(dataDir) {
  const providers = list('--providers', Object.keys(config.providers));
  const sources = list('--sources', ['human']);
  const conditions = list('--conditions', CONDITIONS);
  for (const p of providers) if (!config.providers[p]) throw new Error(`Unknown provider "${p}"`);
  for (const c of conditions) if (!CONDITIONS.includes(c)) throw new Error(`Unknown condition "${c}"`);

  if (dryRun(dataDir) !== 0) return 1;
  const utterances = JSON.parse(fs.readFileSync(path.join(dataDir, 'utterances.json'), 'utf8'));
  const keyterms = Object.keys(JSON.parse(fs.readFileSync(path.join(dataDir, 'terms.json'), 'utf8')));
  const audioDir = path.resolve(arg('--audio') || path.join(__dirname, 'data', 'audio'));
  const planned = plan({ config, utterances, audioDir, providers, sources, conditions });

  console.log(`\nPlan: ${providers.join(', ')} x ${conditions.join(', ')} x ${sources.join(', ')}`);
  for (const [s, ids] of Object.entries(planned.missingAudio)) console.log(`  ${s}: no audio yet for ${ids.length} of ${utterances.length} utterances (skipped)`);
  console.log(`  requests:        ${planned.jobs.length}`);
  console.log(`  audio:           ${planned.audioMinutes.toFixed(2)} minutes`);
  console.log(`  estimated cost:  ${usd(planned.estUsd)} at list price (prices retrieved ${config.pricing.retrieved_on})`);
  const cap = config.budget.max_usd_per_run;
  console.log(`  spend cap:       ${cap == null ? 'NOT SET' : usd(cap)}`);

  if (!planned.jobs.length) { console.log('\nNothing to run.'); return 1; }
  if (cap == null) { console.error('\nSet budget.max_usd_per_run in config.json before a paid run. No API calls were made.'); return 1; }
  if (planned.estUsd > cap) { console.error('\nThe estimate is over the spend cap. No API calls were made.'); return 1; }
  if (!process.argv.includes('--confirm')) { console.log('\nNo API calls were made. Add --confirm to run.'); return 0; }

  loadEnv();
  const adapters = Object.fromEntries(providers.map((p) => [p, require(`./providers/${p}`)]));
  const runId = new Date().toISOString().replace(/[:.]/g, '-');
  const runDir = path.join(path.resolve(arg('--results') || path.join(__dirname, 'results')), runId);
  console.log(`\nRun ${runId}`);
  const { done, spentUsd } = await execute({ planned, config, adapters, keyterms, runDir, dataDir });
  const summary = scoreRun(runDir, dataDir);
  fs.writeFileSync(path.join(runDir, 'summary.json'), `${JSON.stringify(summary, null, 2)}\n`);
  console.log(`\n${done} of ${planned.jobs.length} requests made; estimated spend ${usd(spentUsd)}.`);
  console.log(`Raw results and summary.json are in ${runDir}`);
  return done === planned.jobs.length ? 0 : 1;
}

async function main() {
  const dataDir = path.resolve(arg('--data') || path.join(__dirname, 'data'));
  if (process.argv.includes('--dry-run')) return dryRun(dataDir);
  return paidRun(dataDir);
}

main().then((code) => process.exit(code), (e) => { console.error(e.message); process.exit(1); });
