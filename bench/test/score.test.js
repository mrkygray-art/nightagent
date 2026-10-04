const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');
const { normalize, findPhrases, words } = require('../lib/normalize');
const { wer, aliasMap, scoreUtterance, scoreGroup, median, p95 } = require('../score');

const ALIASES = aliasMap({
  PoE: ['PoE', 'P o E', 'power over ethernet'],
  'Cisco Catalyst': ['Cisco Catalyst'],
  Verkada: ['Verkada'],
  Cat6: ['cat six', 'category six'],
  'J-hook': ['J hook', 'jhook'],
});
const U019 = { id: 'u019', category: 'networking', reference: 'The Cisco Catalyst nine thousand switch is out of PoE budget on port twelve.', terms: ['Cisco Catalyst', 'PoE'] };

// ---------- WER (spec section 12 fixtures) ----------

test('WER: identical transcript is 0', () => {
  const r = wer('the nvr is down', 'The NVR is down.');
  assert.equal(r.wer, 0);
  assert.equal(r.edits, 0);
});

test('WER: one substitution', () => {
  const r = wer('the nvr is down', 'the nbr is down');
  assert.deepEqual([r.substitutions, r.deletions, r.insertions], [1, 0, 0]);
  assert.equal(r.wer, 0.25);
});

test('WER: one insertion', () => {
  const r = wer('the nvr is down', 'the nvr is down now');
  assert.deepEqual([r.substitutions, r.deletions, r.insertions], [0, 0, 1]);
  assert.equal(r.wer, 0.25);
});

test('WER: one deletion', () => {
  const r = wer('the nvr is down', 'the nvr down');
  assert.deepEqual([r.substitutions, r.deletions, r.insertions], [0, 1, 0]);
  assert.equal(r.wer, 0.25);
});

test('WER: empty transcript is all deletions (1.0)', () => {
  const r = wer('the nvr is down', '');
  assert.equal(r.deletions, 4);
  assert.equal(r.wer, 1);
});

test('WER: can exceed 1 when the transcript adds many words', () => {
  assert.equal(wer('nvr down', 'the nvr box is down again').wer, 2);
});

test('WER: digits in the transcript match spoken numbers in the reference', () => {
  assert.equal(wer(U019.reference, 'The Cisco Catalyst 9000 switch is out of PoE budget on port 12.').wer, 0);
});

test('WER is strict: an alias spelled differently is still a word error', () => {
  const r = wer('out of poe budget', 'out of power over ethernet budget');
  assert.ok(r.wer > 0);
});

// ---------- Normalization edge cases ----------

test('normalize: casing, punctuation, whitespace', () => {
  assert.equal(normalize('  The NVR,   is DOWN!! '), 'the nvr is down');
});

test('normalize: hyphens and slashes split words; apostrophes join', () => {
  assert.equal(normalize('J-hook / fail-safe, won\'t'), 'j hook fail safe wont');
});

test('normalize: numbers to words', () => {
  assert.equal(normalize('port 12'), 'port twelve');
  assert.equal(normalize('9,000'), 'nine thousand');
  assert.equal(normalize('9300'), 'nine thousand three hundred');
  assert.equal(normalize('100 meters'), 'one hundred meters');
  assert.equal(normalize('0'), 'zero');
  assert.equal(normalize('007'), 'zero zero seven');
});

test('normalize: decimals, ordinals, times, percent', () => {
  assert.equal(normalize('2.8mm'), 'two point eight mm');
  assert.equal(normalize('2nd floor'), 'second floor');
  assert.equal(normalize('21st 40th 12th'), 'twenty first fortieth twelfth');
  assert.equal(normalize('at 2:00'), 'at two');
  assert.equal(normalize('at 2:30'), 'at two thirty');
  assert.equal(normalize('90%'), 'ninety percent');
});

test('normalize: letter-digit tokens split', () => {
  assert.equal(normalize('Cat6'), 'cat six');
  assert.equal(normalize('Cat-6'), 'cat six');
  assert.equal(normalize('C9300'), 'c nine thousand three hundred');
});

// ---------- Term matching ----------

test('term match: alias forms count', () => {
  for (const t of ['out of PoE budget', 'out of P.O.E. budget', 'out of power-over-Ethernet budget']) {
    assert.equal(findPhrases(words(normalize(t)), ALIASES.PoE).length, 1, t);
  }
});

test('term match: no false positive inside a longer word', () => {
  assert.equal(findPhrases(words(normalize('a poem and poetry')), ALIASES.PoE).length, 0);
  assert.equal(findPhrases(words(normalize('verkadas')), ALIASES.Verkada).length, 0);
});

test('term match: "Cat6" in a transcript matches the spoken alias', () => {
  assert.equal(findPhrases(words(normalize('Run Cat6 to the IDF')), ALIASES.Cat6).length, 1);
});

test('term match: overlapping aliases are not double-counted', () => {
  // "p o e" spelled out must count once, not also as anything shorter
  assert.equal(findPhrases(words(normalize('P O E')), ALIASES.PoE).length, 1);
});

// ---------- Scoring an utterance ----------

test('scoreUtterance: perfect transcript hits every term', () => {
  const s = scoreUtterance(U019, 'The Cisco Catalyst 9000 switch is out of PoE budget on port 12.', ALIASES);
  assert.equal(s.wer, 0);
  assert.deepEqual(s.terms.map((t) => [t.term, t.hits, t.expected]), [['Cisco Catalyst', 1, 1], ['PoE', 1, 1]]);
});

test('scoreUtterance: a missed term reports what was heard', () => {
  const s = scoreUtterance(U019, 'The Cisco Catalyst 9000 switch is out of pony budget on port 12.', ALIASES);
  const poe = s.terms.find((t) => t.term === 'PoE');
  assert.equal(poe.hits, 0);
  assert.deepEqual(poe.heardAs, ['pony']);
});

test('scoreUtterance: a term split into several words is shown whole', () => {
  const u = { ...U019, reference: 'The Verkada cameras are back online.', terms: ['Verkada'] };
  const s = scoreUtterance(u, 'The Burke Otto cameras are back online.', ALIASES);
  assert.deepEqual(s.terms[0].heardAs, ['burke otto']);
});

test('scoreUtterance: a miss the alignment pairs with nothing still shows the nearby misheard word', () => {
  // Real case from the first run: "The NVR in the back office" -> "The MBR and back office"
  const aliases = aliasMap({ NVR: ['NVR', 'N V R'] });
  const u = { id: 'u001', reference: 'The NVR in the back office stopped recording.', terms: ['NVR'] };
  const s = scoreUtterance(u, 'The MBR and back office stopped recording.', aliases);
  assert.equal(s.terms[0].hits, 0);
  assert.notEqual(s.terms[0].heardAs[0], '');
  assert.match(s.terms[0].heardAs[0], /mbr/);
});

test('scoreUtterance: a term that was really dropped shows as empty', () => {
  const aliases = aliasMap({ NVR: ['NVR'] });
  const u = { id: 'x', reference: 'The NVR is down tonight.', terms: ['NVR'] };
  assert.deepEqual(scoreUtterance(u, 'The is down tonight.', aliases).terms[0].heardAs, ['']);
});

test('scoreUtterance: repeated terms score min(found, expected)', () => {
  const u = { ...U019, reference: 'PoE on port one and PoE on port two.', terms: ['PoE'] };
  const once = scoreUtterance(u, 'PoE on port one and pony on port two.', ALIASES).terms[0];
  assert.deepEqual([once.hits, once.expected], [1, 2]);
  const extra = scoreUtterance(u, 'PoE PoE PoE on port one and two.', ALIASES).terms[0];
  assert.deepEqual([extra.hits, extra.expected], [2, 2]);
});

test('scoreUtterance: a term written where it was not said is reported as inserted', () => {
  const aliases = aliasMap({ Axis: ['Axis'], Avigilon: ['Avigilon'] });
  const u = { id: 'u036', reference: 'We quoted Avigilon for the access control panels.', terms: ['Avigilon'] };
  const s = scoreUtterance(u, 'We quoted Avigilon for the Axis Control Panel.', aliases);
  assert.deepEqual(s.insertedTerms, [{ term: 'Axis', extra: 1 }]);
  assert.equal(s.terms[0].hits, 1); // term accuracy alone can't see it
  assert.deepEqual(scoreUtterance(u, u.reference, aliases).insertedTerms, []);
});

test('scoreUtterance: empty transcript misses every term', () => {
  const s = scoreUtterance(U019, '', ALIASES);
  assert.equal(s.wer, 1);
  assert.ok(s.terms.every((t) => t.hits === 0));
});

// ---------- Stats ----------

test('median and p95 (nearest rank)', () => {
  assert.equal(median([3, 1, 2]), 2);
  assert.equal(median([4, 1, 3, 2]), 2.5);
  assert.equal(p95([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]), 19);
  assert.equal(p95([5]), 5);
  assert.equal(median([]), null);
});

// ---------- Groups and the CLI ----------

const raw = (id, runs) => ({ id, provider: 'fake', model: 'fake-1', condition: 'baseline', source: 'human', audioSeconds: 5, runs });

test('scoreGroup: failures are counted, not scored, and not dropped', () => {
  const u2 = { ...U019, id: 'u020', reference: 'The Verkada cameras are back online.', terms: ['Verkada'] };
  const g = scoreGroup([
    raw('u019', [{ run: 1, text: U019.reference, latencyMs: 100, error: null }, { run: 2, text: null, latencyMs: null, error: 'HTTP 500' }]),
  ], [U019, u2], ALIASES);
  assert.equal(g.requests, 2);
  assert.equal(g.failures, 1);
  assert.equal(g.failureRate, 50);
  assert.equal(g.scoredRequests, 1);
  assert.deepEqual(g.missingIds, ['u020']);
  assert.equal(g.termAccuracy.pct, 100);
  assert.deepEqual(g.latencyMs, { median: 100, p95: 100, n: 1 });
});

test('scoreGroup: transcripts that differ across runs are flagged', () => {
  const g = scoreGroup([raw('u019', [
    { run: 1, text: U019.reference, latencyMs: 100, error: null },
    { run: 2, text: 'The Cisco Catalyst 9000 switch is out of pony budget on port 12.', latencyMs: 120, error: null },
  ])], [U019], ALIASES);
  assert.deepEqual(g.inconsistentTranscripts, ['u019']);
  assert.deepEqual(g.termAccuracy, { hits: 3, expected: 4, pct: 75 });
  assert.deepEqual(g.perTerm.PoE.misses, [{ id: 'u019', run: 2, heardAs: 'pony' }]);
});

test('score.js --run writes summary.json from raw files', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'jb-run-'));
  const data = path.join(root, 'data');
  const dir = path.join(root, 'results', 'r1', 'raw', 'fake', 'baseline', 'human');
  fs.mkdirSync(data); fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(data, 'utterances.json'), JSON.stringify([U019]));
  fs.writeFileSync(path.join(data, 'terms.json'), JSON.stringify({ PoE: ['PoE'], 'Cisco Catalyst': ['Cisco Catalyst'] }));
  fs.writeFileSync(path.join(dir, 'u019.json'), JSON.stringify(raw('u019', [{ run: 1, text: 'The Cisco Catalog 9000 switch is out of PoE budget on port 12.', latencyMs: 250, error: null }])));
  const r = spawnSync(process.execPath, [path.join(__dirname, '..', 'score.js'), '--run', 'r1', '--results', path.join(root, 'results'), '--data', data], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr);
  const summary = JSON.parse(fs.readFileSync(path.join(root, 'results', 'r1', 'summary.json'), 'utf8'));
  const g = summary.groups[0];
  assert.deepEqual([g.provider, g.condition, g.source, g.model], ['fake', 'baseline', 'human', 'fake-1']);
  assert.deepEqual(g.termAccuracy, { hits: 1, expected: 2, pct: 50 });
  assert.deepEqual(g.perTerm['Cisco Catalyst'].misses, [{ id: 'u019', run: 1, heardAs: 'cisco catalog' }]);
});
