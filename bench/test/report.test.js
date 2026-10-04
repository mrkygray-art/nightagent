// Report tests: the model is built only from summaries, and every percentage published in the
// README, scorecard, and readout equals an exact result (rounded half up from counts).
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { loadModel } = require('../lib/report-data');
const { scorecard, readout, pdfPages } = require('../report');

const ROOT = path.join(__dirname, '..');
const runIds = JSON.parse(fs.readFileSync(path.join(ROOT, 'report-runs.json'), 'utf8')).runs;
const model = () => loadModel({ resultsDir: path.join(ROOT, 'results'), dataDir: path.join(ROOT, 'data'), runIds });

function exactValues() {
  const vals = new Set();
  for (const r of runIds) {
    for (const g of JSON.parse(fs.readFileSync(path.join(ROOT, 'results', r, 'summary.json'), 'utf8')).groups) {
      vals.add((Math.round((g.termAccuracy.hits * 1000) / g.termAccuracy.expected) / 10).toFixed(1));
      vals.add((Math.round((g.wordErrors.edits * 1000) / g.wordErrors.refWords) / 10).toFixed(1));
    }
  }
  return vals;
}

test('every published percentage traces to an exact result', () => {
  const vals = exactValues();
  const m = model();
  const docs = { 'README.md': fs.readFileSync(path.join(ROOT, 'README.md'), 'utf8'), scorecard: scorecard(m), readout: readout(m) };
  for (const [name, text] of Object.entries(docs)) {
    const found = [...text.matchAll(/(\d+\.\d)%/g)].map((x) => x[1]);
    assert.ok(found.length > 0, name);
    assert.deepEqual(found.filter((v) => !vals.has(v)), [], `${name} has a percentage that isn't an exact result`);
  }
});

test('headline comes straight from the human baseline and boosted summaries', () => {
  const m = model();
  for (const h of m.headline) {
    const b = m.groups[`human/${h.provider}/baseline`];
    const x = m.groups[`human/${h.provider}/boosted`];
    assert.deepEqual(h.baseline, b.termAccuracy);
    assert.deepEqual(h.boosted, x.termAccuracy);
    assert.equal(h.model, b.model);
  }
});

test('top terms are ranked mechanically: most baseline misses, ties alphabetical', () => {
  const m = model();
  assert.equal(m.topTerms.length, 5);
  for (let i = 1; i < m.topTerms.length; i++) {
    const [a, b] = [m.topTerms[i - 1], m.topTerms[i]];
    assert.ok(a.misses > b.misses || (a.misses === b.misses && a.term < b.term), `${a.term} before ${b.term}`);
  }
});

test('false positives come from the summaries insertedTerms', () => {
  const m = model();
  const total = Object.values(m.groups).reduce((n, g) => n + (g.insertedTerms?.items.length ?? 0), 0);
  assert.equal(m.falsePositives.reduce((n, f) => n + f.runs, 0), total);
});

test('the same (source, provider, condition) in two runs is an error', () => {
  assert.throws(() => loadModel({ resultsDir: path.join(ROOT, 'results'), dataDir: path.join(ROOT, 'data'), runIds: [runIds[0], runIds[0]] }), /appears in both/);
});

test('runs scored against different dataset versions are an error', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'jb-rep-'));
  for (const r of runIds.slice(0, 2)) {
    fs.mkdirSync(path.join(dir, r));
    fs.copyFileSync(path.join(ROOT, 'results', r, 'config.snapshot.json'), path.join(dir, r, 'config.snapshot.json'));
    const s = JSON.parse(fs.readFileSync(path.join(ROOT, 'results', r, 'summary.json'), 'utf8'));
    if (r === runIds[1]) s.scoredDataset.utterancesSha256 = 'different';
    fs.writeFileSync(path.join(dir, r, 'summary.json'), JSON.stringify(s));
  }
  assert.throws(() => loadModel({ resultsDir: dir, dataDir: path.join(ROOT, 'data'), runIds: runIds.slice(0, 2) }), /different dataset versions/);
});

test('the committed readout PDF is one page', { skip: !fs.existsSync(path.join(ROOT, 'report', 'readout.pdf')) }, () => {
  assert.equal(pdfPages(path.join(ROOT, 'report', 'readout.pdf')), 1);
});
