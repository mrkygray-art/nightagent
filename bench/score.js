// Jargon Bench scorer.
//
//   node score.js --run <run-id>           score results/<run-id>/raw, write results/<run-id>/summary.json
//   node score.js --run <run-id> --results <dir> --data <dir>    (other folders; used by tests)
//
// Raw file layout (written by run.js): raw/<provider>/<condition>/<source>/<id>.json
//   { id, provider, model, condition, source, audioSeconds,
//     runs: [{ run, text, latencyMs, attempts, error }] }     error is null on success
//
// Metrics (spec sections 7, 8, 18):
//   WER            corpus-level: total edits / total reference words, strict reference wording
//   term accuracy  each occurrence counts; a term found k times where the reference has it n
//                  times scores min(k, n) of n; aliases count, whole words only
//   latency        median and p95 (nearest rank) over successful requests
//   failure rate   failed requests / all requests; failed requests are not scored for
//                  accuracy, and the summary says how many requests were scored
const fs = require('fs');
const path = require('path');
const { normalize, words, findPhrases } = require('./lib/normalize');
const { estimateUsd, perAudioHourUsd } = require('./lib/cost');

// ---------- WER with alignment ----------

// Word-level edit distance with a backtrace. Ties prefer match/substitution, then deletion.
function align(refTokens, hypTokens) {
  const R = refTokens.length;
  const H = hypTokens.length;
  const d = Array.from({ length: R + 1 }, (_, i) => Array.from({ length: H + 1 }, (_, j) => (i === 0 ? j : j === 0 ? i : 0)));
  for (let i = 1; i <= R; i++) {
    for (let j = 1; j <= H; j++) {
      const cost = refTokens[i - 1] === hypTokens[j - 1] ? 0 : 1;
      d[i][j] = Math.min(d[i - 1][j - 1] + cost, d[i - 1][j] + 1, d[i][j - 1] + 1);
    }
  }
  const ops = [];
  let i = R;
  let j = H;
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && d[i][j] === d[i - 1][j - 1] + (refTokens[i - 1] === hypTokens[j - 1] ? 0 : 1)) {
      ops.push({ op: refTokens[i - 1] === hypTokens[j - 1] ? 'eq' : 'sub', ref: i - 1, hyp: j - 1 });
      i--; j--;
    } else if (i > 0 && d[i][j] === d[i - 1][j] + 1) {
      ops.push({ op: 'del', ref: i - 1, hyp: null }); i--;
    } else {
      ops.push({ op: 'ins', ref: null, hyp: j - 1 }); j--;
    }
  }
  ops.reverse();
  const count = (o) => ops.filter((x) => x.op === o).length;
  return { ops, substitutions: count('sub'), deletions: count('del'), insertions: count('ins'), refWords: R };
}

function wer(reference, transcript) {
  const a = align(words(normalize(reference)), words(normalize(transcript)));
  const edits = a.substitutions + a.deletions + a.insertions;
  return { ...a, edits, wer: a.refWords ? edits / a.refWords : null };
}

// Transcript words aligned to reference words [start, end), plus inserted words inside or
// right next to that span ("Verkada" heard as "Burke Otto" is one substitution + one insertion).
function heardAs(ops, hypTokens, start, end) {
  const idx = ops.map((o, k) => (o.ref !== null && o.ref >= start && o.ref < end ? k : -1)).filter((k) => k >= 0);
  if (!idx.length) return '';
  let first = idx[0];
  let last = idx[idx.length - 1];
  while (first > 0 && ops[first - 1].op === 'ins') first--;
  while (last < ops.length - 1 && ops[last + 1].op === 'ins') last++;
  // Equal-cost alignments can pair the term with nothing (a deletion) and its misheard word
  // with a neighbor ("the NVR in" -> "the MBR and"). Then show the substituted neighbors.
  if (ops.slice(first, last + 1).every((o) => o.hyp === null)) {
    if (first > 0 && ops[first - 1].op === 'sub') first--;
    if (last < ops.length - 1 && ops[last + 1].op === 'sub') last++;
  }
  return ops.slice(first, last + 1).filter((o) => o.hyp !== null).map((o) => hypTokens[o.hyp]).join(' ');
}

// ---------- Term accuracy ----------

function aliasMap(terms) {
  return Object.fromEntries(Object.entries(terms).map(([t, list]) => [t, list.map(normalize)]));
}

// Scores one transcript of one utterance.
function scoreUtterance(utterance, transcript, aliases) {
  const refTokens = words(normalize(utterance.reference));
  const hypTokens = words(normalize(transcript));
  const a = wer(utterance.reference, transcript);
  const terms = utterance.terms.map((term) => {
    const refSpans = findPhrases(refTokens, aliases[term]);
    const found = findPhrases(hypTokens, aliases[term]).length;
    const expected = refSpans.length;
    const hits = Math.min(found, expected);
    // Show what was heard where a missed occurrence was spoken
    const missed = refSpans
      .map((s) => heardAs(a.ops, hypTokens, s.start, s.end))
      .filter((h) => !findPhrases(words(h), aliases[term]).length)
      .slice(0, expected - hits);
    return { term, expected, found, hits, heardAs: missed };
  });
  // Any term (listed or not) written more often than it was said: a false positive that
  // term accuracy can't see, and the known risk of vocabulary boosting
  const insertedTerms = [];
  for (const [term, list] of Object.entries(aliases)) {
    const extra = findPhrases(hypTokens, list).length - findPhrases(refTokens, list).length;
    if (extra > 0) insertedTerms.push({ term, extra });
  }
  return { wer: a.wer, edits: a.edits, refWords: a.refWords, terms, insertedTerms };
}

// ---------- Stats ----------

function median(values) {
  if (!values.length) return null;
  const s = [...values].sort((x, y) => x - y);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

function p95(values) {
  if (!values.length) return null;
  const s = [...values].sort((x, y) => x - y);
  return s[Math.ceil(0.95 * s.length) - 1];
}

const pct = (num, den) => (den ? Math.round((num / den) * 10000) / 100 : null);

// ---------- Aggregation ----------

// files: parsed raw files for one (provider, condition, source) group
function scoreGroup(files, utterances, aliases) {
  const byId = Object.fromEntries(utterances.map((u) => [u.id, u]));
  const g = { requests: 0, failures: 0, scored: 0, audioSeconds: 0, edits: 0, refWords: 0, hits: 0, expected: 0, latencies: [], perTerm: {}, inserted: [], inconsistent: [], unknownIds: [], utterances: [] };
  for (const f of files) {
    const u = byId[f.id];
    if (!u) { g.unknownIds.push(f.id); continue; }
    const texts = new Set();
    const runs = [];
    for (const r of f.runs || []) {
      g.requests++;
      if (r.error) { g.failures++; runs.push({ run: r.run, error: r.error }); continue; }
      g.scored++;
      g.audioSeconds += f.audioSeconds || 0;
      g.latencies.push(r.latencyMs);
      texts.add(normalize(r.text));
      const s = scoreUtterance(u, r.text, aliases);
      g.edits += s.edits;
      g.refWords += s.refWords;
      for (const t of s.terms) {
        g.hits += t.hits;
        g.expected += t.expected;
        const pt = (g.perTerm[t.term] ||= { expected: 0, hits: 0, misses: [] });
        pt.expected += t.expected;
        pt.hits += t.hits;
        for (const h of t.heardAs) pt.misses.push({ id: f.id, run: r.run, heardAs: h });
      }
      for (const x of s.insertedTerms) g.inserted.push({ id: f.id, run: r.run, term: x.term, extra: x.extra, text: r.text });
      runs.push({ run: r.run, wer: s.wer, termHits: s.terms.reduce((n, t) => n + t.hits, 0), termExpected: s.terms.reduce((n, t) => n + t.expected, 0) });
    }
    if (texts.size > 1) g.inconsistent.push(f.id);
    g.utterances.push({ id: f.id, runs });
  }
  const seen = new Set(files.map((f) => f.id));
  return {
    model: files[0]?.model ?? null,
    requests: g.requests,
    failures: g.failures,
    failureRate: pct(g.failures, g.requests),
    scoredRequests: g.scored,
    scoredAudioSeconds: Math.round(g.audioSeconds * 100) / 100,
    missingIds: utterances.map((u) => u.id).filter((id) => !seen.has(id)),
    unknownIds: g.unknownIds,
    werPct: pct(g.edits, g.refWords),
    termAccuracy: { hits: g.hits, expected: g.expected, pct: pct(g.hits, g.expected) },
    insertedTerms: { count: g.inserted.reduce((n, x) => n + x.extra, 0), items: g.inserted },
    latencyMs: { median: median(g.latencies), p95: p95(g.latencies), n: g.latencies.length },
    inconsistentTranscripts: g.inconsistent,
    perTerm: g.perTerm,
    utterances: g.utterances,
  };
}

function readRaw(rawDir) {
  const groups = {};
  if (!fs.existsSync(rawDir)) return groups;
  for (const provider of fs.readdirSync(rawDir)) {
    for (const condition of fs.readdirSync(path.join(rawDir, provider))) {
      for (const source of fs.readdirSync(path.join(rawDir, provider, condition))) {
        const dir = path.join(rawDir, provider, condition, source);
        const files = fs.readdirSync(dir).filter((n) => n.endsWith('.json')).sort()
          .map((n) => JSON.parse(fs.readFileSync(path.join(dir, n), 'utf8')));
        groups[`${provider}/${condition}/${source}`] = { provider, condition, source, files };
      }
    }
  }
  return groups;
}

function scoreRun(runDir, dataDir) {
  const utterances = JSON.parse(fs.readFileSync(path.join(dataDir, 'utterances.json'), 'utf8'));
  const aliases = aliasMap(JSON.parse(fs.readFileSync(path.join(dataDir, 'terms.json'), 'utf8')));
  const raw = readRaw(path.join(runDir, 'raw'));
  // Prices come from the run's own config snapshot, so a later price change can't alter old results
  const snapPath = path.join(runDir, 'config.snapshot.json');
  const snapshot = fs.existsSync(snapPath) ? JSON.parse(fs.readFileSync(snapPath, 'utf8')) : null;
  const pricing = snapshot?.config.pricing ?? null;
  // Record which dataset version was scored, and whether it differs from the one the run used
  const sha = (f) => require('crypto').createHash('sha256').update(fs.readFileSync(path.join(dataDir, f))).digest('hex');
  const scoredDataset = { utterancesSha256: sha('utterances.json'), termsSha256: sha('terms.json') };
  const datasetChangedSinceRun = snapshot ? (snapshot.dataset.utterancesSha256 !== scoredDataset.utterancesSha256 || snapshot.dataset.termsSha256 !== scoredDataset.termsSha256) : null;
  const groups = Object.values(raw).map(({ provider, condition, source, files }) => {
    const g = { provider, condition, source, ...scoreGroup(files, utterances, aliases) };
    if (pricing?.[provider]) {
      g.estCost = {
        usd: Math.round(estimateUsd(pricing, provider, condition, g.scoredAudioSeconds) * 1e6) / 1e6,
        perAudioHourUsd: Math.round(perAudioHourUsd(pricing, provider, condition) * 1e4) / 1e4,
        pricesRetrievedOn: pricing.retrieved_on,
        source: pricing[provider].source,
      };
    }
    return g;
  });
  return { runId: path.basename(runDir), scoredAt: new Date().toISOString(), utterances: utterances.length, scoredDataset, datasetChangedSinceRun, groups };
}

function main() {
  const arg = (name) => { const i = process.argv.indexOf(name); return i === -1 ? null : process.argv[i + 1]; };
  const runId = arg('--run');
  if (!runId) { console.error('Usage: node score.js --run <run-id>'); process.exit(1); }
  const runDir = path.resolve(arg('--results') || path.join(__dirname, 'results'), runId);
  const dataDir = path.resolve(arg('--data') || path.join(__dirname, 'data'));
  if (!fs.existsSync(path.join(runDir, 'raw'))) { console.error(`No raw results in ${runDir}`); process.exit(1); }
  const summary = scoreRun(runDir, dataDir);
  fs.writeFileSync(path.join(runDir, 'summary.json'), `${JSON.stringify(summary, null, 2)}\n`);
  for (const g of summary.groups) {
    const flags = [g.missingIds.length && `${g.missingIds.length} missing`, g.inconsistentTranscripts.length && `${g.inconsistentTranscripts.length} inconsistent`].filter(Boolean);
    console.log(`${g.provider}/${g.condition}/${g.source}: terms ${g.termAccuracy.pct}% (${g.termAccuracy.hits}/${g.termAccuracy.expected}), WER ${g.werPct}%, ` +
      `failures ${g.failures}/${g.requests}, median ${g.latencyMs.median} ms${flags.length ? `  [${flags.join(', ')}]` : ''}`);
  }
  console.log(`Wrote ${path.join(runDir, 'summary.json')}`);
}

if (require.main === module) main();

module.exports = { align, wer, heardAs, aliasMap, scoreUtterance, scoreGroup, scoreRun, median, p95 };
