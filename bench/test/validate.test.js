const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');
const { validateData } = require('../lib/validate');

const RUN = path.join(__dirname, '..', 'run.js');
const TERMS = { PoE: ['PoE', 'power over ethernet'], NVR: ['NVR', 'N V R'], 'Cisco Catalyst': ['Cisco Catalyst'] };
const GOOD = [
  { id: 'u001', category: 'networking', reference: 'The Cisco Catalyst switch is out of PoE budget on port twelve.', terms: ['Cisco Catalyst', 'PoE'] },
  { id: 'u002', category: 'cctv', reference: 'The NVR in the back office stopped recording last night.', terms: ['NVR'] },
];

// Writes a data folder; pass a string to write raw (possibly broken) JSON.
function dataDir({ terms = TERMS, utterances = GOOD } = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'jb-'));
  const write = (name, v) => fs.writeFileSync(path.join(dir, name), typeof v === 'string' ? v : JSON.stringify(v));
  write('terms.json', terms);
  write('utterances.json', utterances);
  return dir;
}
const errorsFor = (opts) => validateData(dataDir(opts)).errors;
const withUtterance = (patch) => ({ utterances: [{ ...GOOD[0], ...patch }, GOOD[1]] });

test('valid data passes with stats', () => {
  const { errors, stats } = validateData(dataDir());
  assert.deepEqual(errors, []);
  assert.equal(stats.utterances, 2);
  assert.equal(stats.termOccurrences, 3);
  assert.equal(stats.byCategory.networking, 1);
});

test('the real dataset passes', () => {
  const { errors } = validateData(path.join(__dirname, '..', 'data'));
  assert.deepEqual(errors, []);
});

test('malformed JSON is reported, not thrown', () => {
  const errors = errorsFor({ utterances: '[{ "id": "u001", ' });
  assert.match(errors[0], /utterances\.json: not valid JSON/);
});

test('missing fields and bad ids', () => {
  const errors = errorsFor({ utterances: [{ id: 'x1', category: 'cctv', reference: 'The NVR is down again tonight.' }] });
  assert.ok(errors.some((e) => /missing "terms"/.test(e)));
  assert.ok(errors.some((e) => /id must look like/.test(e)));
});

test('duplicate ids', () => {
  const errors = errorsFor({ utterances: [GOOD[0], { ...GOOD[1], id: 'u001' }] });
  assert.ok(errors.some((e) => /duplicate id/.test(e)));
});

test('unknown category', () => {
  assert.ok(errorsFor(withUtterance({ category: 'hvac' })).some((e) => /category must be one of/.test(e)));
});

test('digits in a reference must be spoken words', () => {
  const errors = errorsFor(withUtterance({ reference: 'The Cisco Catalyst switch is out of PoE budget on port 12.' }));
  assert.ok(errors.some((e) => /has a digit/.test(e)));
});

test('a listed term must be defined in terms.json', () => {
  const errors = errorsFor(withUtterance({ terms: ['Cisco Catalyst', 'PoE', 'VLAN'] }));
  assert.ok(errors.some((e) => /"VLAN" is not in terms\.json/.test(e)));
});

test('a listed term must appear in the reference', () => {
  const errors = errorsFor(withUtterance({ reference: 'The Cisco Catalyst switch is out of power budget on port twelve.' }));
  assert.ok(errors.some((e) => /"PoE" is listed but no alias/.test(e)));
});

test('a term spoken but not listed is an error', () => {
  const errors = errorsFor(withUtterance({ terms: ['Cisco Catalyst'] }));
  assert.ok(errors.some((e) => /contains "PoE" but terms doesn't list it/.test(e)));
});

test('aliases match whole words only', () => {
  // "poem" contains "poe" but must not count as PoE
  const errors = errorsFor(withUtterance({ reference: 'The Cisco Catalyst switch closet has a poem taped to it.', terms: ['Cisco Catalyst'] }));
  assert.deepEqual(errors, []);
});

test('an alias may not belong to two terms', () => {
  const errors = errorsFor({ terms: { ...TERMS, PoweredEthernet: ['power over ethernet'] } });
  assert.ok(errors.some((e) => /belongs to both "PoE" and "PoweredEthernet"/.test(e)));
});

test('aliases must be written as spoken (no digits)', () => {
  const errors = errorsFor({ terms: { ...TERMS, Cat6: ['Cat6'] } });
  assert.ok(errors.some((e) => /has a digit/.test(e)));
});

test('--dry-run fails loudly with exit code 1 on bad data', () => {
  const r = spawnSync(process.execPath, [RUN, '--dry-run', '--data', dataDir({ utterances: '{oops' })], { encoding: 'utf8' });
  assert.equal(r.status, 1);
  assert.match(r.stderr, /Dataset check FAILED/);
  assert.match(r.stderr, /not valid JSON/);
});

test('--dry-run exits 0 on good data and makes no API calls', () => {
  const r = spawnSync(process.execPath, [RUN, '--dry-run', '--data', dataDir()], { encoding: 'utf8' });
  assert.equal(r.status, 0);
  assert.match(r.stdout, /Dataset OK/);
  assert.match(r.stdout, /No API calls/);
});
