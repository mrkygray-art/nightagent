// Builds the scorecard/readout data model from summary.json files only.
// No number in the report is typed by hand: every figure comes from this model.
const fs = require('fs');
const path = require('path');

const PROVIDERS = ['deepgram', 'elevenlabs'];
const CONDITIONS = ['baseline', 'boosted'];
const SOURCES = ['human', 'noisy', 'tts'];

function loadModel({ resultsDir, dataDir, runIds }) {
  const groups = {};
  const datasets = new Set();
  const runs = [];
  for (const runId of runIds) {
    const summary = JSON.parse(fs.readFileSync(path.join(resultsDir, runId, 'summary.json'), 'utf8'));
    const snapshot = JSON.parse(fs.readFileSync(path.join(resultsDir, runId, 'config.snapshot.json'), 'utf8'));
    datasets.add(JSON.stringify(summary.scoredDataset));
    runs.push({ runId, startedAt: snapshot.startedAt, datasetChangedSinceRun: summary.datasetChangedSinceRun, pricing: snapshot.config.pricing });
    for (const g of summary.groups) {
      const key = `${g.source}/${g.provider}/${g.condition}`;
      if (groups[key]) throw new Error(`${key} appears in both ${groups[key].runId} and ${runId}`);
      groups[key] = { ...g, runId };
    }
  }
  if (datasets.size !== 1) throw new Error('The runs were scored against different dataset versions; re-score them first.');

  const terms = JSON.parse(fs.readFileSync(path.join(dataDir, 'terms.json'), 'utf8'));
  const utterances = JSON.parse(fs.readFileSync(path.join(dataDir, 'utterances.json'), 'utf8'));
  const get = (source, provider, condition) => groups[`${source}/${provider}/${condition}`] || null;
  const clips = (g) => g.utterances.filter((u) => u.runs.some((r) => !r.error)).length;
  const repeats = (g) => Math.max(...g.utterances.map((u) => u.runs.length));

  const headline = PROVIDERS.map((provider) => {
    const b = get('human', provider, 'baseline');
    const x = get('human', provider, 'boosted');
    return {
      provider, model: b?.model ?? x?.model,
      baseline: b?.termAccuracy ?? null, boosted: x?.termAccuracy ?? null,
      werBaseline: b?.werPct ?? null, werBoosted: x?.werPct ?? null,
      latencyBaseline: b?.latencyMs ?? null, latencyBoosted: x?.latencyMs ?? null,
      costPerHourBaseline: b?.estCost?.perAudioHourUsd ?? null, costPerHourBoosted: x?.estCost?.perAudioHourUsd ?? null,
    };
  });

  const bySource = SOURCES.map((source) => ({
    source,
    cells: PROVIDERS.flatMap((provider) => CONDITIONS.map((condition) => {
      const g = get(source, provider, condition);
      return g && { provider, condition, termAccuracy: g.termAccuracy, werPct: g.werPct, wordErrors: g.wordErrors, latencyMs: g.latencyMs,
        failures: g.failures, requests: g.requests, clips: clips(g), repeats: repeats(g),
        inserted: g.insertedTerms?.count ?? 0, inconsistent: g.inconsistentTranscripts.length, runId: g.runId };
    })).filter(Boolean),
  })).filter((s) => s.cells.length);

  // Most-missed terms on recorded human speech at baseline, both providers combined.
  // Ranked by misses (descending), ties alphabetical, so the choice is mechanical.
  const missCount = {};
  const heard = {};
  for (const provider of PROVIDERS) {
    const g = get('human', provider, 'baseline');
    if (!g) continue;
    for (const [term, t] of Object.entries(g.perTerm)) {
      missCount[term] = (missCount[term] || 0) + (t.expected - t.hits);
      for (const m of t.misses) if (m.heardAs) (heard[term] ||= {})[`${provider}|${m.heardAs}`] = ((heard[term] || {})[`${provider}|${m.heardAs}`] || 0) + 1;
    }
  }
  const mostCommonHeard = (term, provider) => {
    const entries = Object.entries(heard[term] || {}).filter(([k]) => k.startsWith(`${provider}|`)).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
    return entries.length ? entries[0][0].split('|')[1] : null;
  };
  const termCell = (term, source, provider, condition) => {
    const t = get(source, provider, condition)?.perTerm[term];
    return t ? { hits: t.hits, expected: t.expected } : null;
  };
  const topTerms = Object.entries(missCount).filter(([, n]) => n > 0)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, 5)
    .map(([term, misses]) => ({
      term, misses,
      providers: PROVIDERS.map((provider) => ({
        provider, heardAs: mostCommonHeard(term, provider),
        baseline: termCell(term, 'human', provider, 'baseline'), boosted: termCell(term, 'human', provider, 'boosted'),
      })),
    }));

  const perTerm = Object.keys(terms).map((term) => ({
    term,
    cells: Object.fromEntries(SOURCES.flatMap((s) => PROVIDERS.flatMap((p) => CONDITIONS.map((c) => [`${s}/${p}/${c}`, termCell(term, s, p, c)])))),
    heardAs: Object.fromEntries(PROVIDERS.map((p) => [p, mostCommonHeard(term, p)])),
  }));

  const falsePositives = [];
  for (const g of Object.values(groups)) {
    const seen = new Map();
    for (const item of g.insertedTerms?.items || []) {
      const k = `${item.id}|${item.term}`;
      if (!seen.has(k)) seen.set(k, { ...item, provider: g.provider, condition: g.condition, source: g.source, runs: 0 });
      seen.get(k).runs++;
    }
    falsePositives.push(...seen.values());
  }
  falsePositives.sort((a, b) => a.source.localeCompare(b.source) || a.provider.localeCompare(b.provider) || a.id.localeCompare(b.id));

  const human = get('human', PROVIDERS[0], 'baseline');
  return {
    runs, groups, headline, bySource, topTerms, perTerm, falsePositives,
    dataset: { utterances: utterances.length, terms: Object.keys(terms).length, sha256: JSON.parse([...datasets][0]) },
    human: human ? { clips: clips(human), repeats: repeats(human), termOccurrences: human.termAccuracy.expected / repeats(human), missing: human.missingIds } : null,
    pricesRetrievedOn: runs[0].pricing.retrieved_on,
    runDate: runs.map((r) => r.startedAt).sort()[0].slice(0, 10),
  };
}

module.exports = { loadModel, PROVIDERS, CONDITIONS, SOURCES };
