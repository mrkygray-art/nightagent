// Checks the dataset before anything is sent to a provider.
// Errors stop the run; warnings are printed but allowed.
const fs = require('fs');
const path = require('path');
const { normalize, countPhrase } = require('./normalize');

const CATEGORIES = ['cctv', 'access_control', 'networking', 'vendors', 'dispatch'];
const UTTERANCE_FIELDS = ['id', 'category', 'reference', 'terms'];

function readJson(file, errors) {
  let text;
  try { text = fs.readFileSync(file, 'utf8'); }
  catch (e) { errors.push(`${path.basename(file)}: can't read (${e.code || e.message})`); return null; }
  try { return JSON.parse(text); }
  catch (e) { errors.push(`${path.basename(file)}: not valid JSON (${e.message})`); return null; }
}

function validateTerms(terms, errors, warnings) {
  if (!terms || typeof terms !== 'object' || Array.isArray(terms) || !Object.keys(terms).length) {
    errors.push('terms.json: must be a non-empty object of { "Canonical": ["alias", ...] }');
    return {};
  }
  const aliases = {}; // canonical -> normalized aliases
  const owner = {};   // normalized alias -> canonical
  for (const [canonical, list] of Object.entries(terms)) {
    if (!Array.isArray(list) || !list.length || list.some((a) => typeof a !== 'string' || !a.trim())) {
      errors.push(`terms.json: "${canonical}" needs a non-empty list of alias strings`);
      continue;
    }
    aliases[canonical] = [];
    for (const alias of list) {
      if (/\d/.test(alias)) errors.push(`terms.json: alias "${alias}" (${canonical}) has a digit; write it as spoken`);
      const n = normalize(alias);
      if (aliases[canonical].includes(n)) { warnings.push(`terms.json: "${canonical}" lists "${alias}" twice after normalization`); continue; }
      if (owner[n]) errors.push(`terms.json: alias "${alias}" belongs to both "${owner[n]}" and "${canonical}"`);
      owner[n] = canonical;
      aliases[canonical].push(n);
    }
  }
  return aliases;
}

const occurrences = (ref, list) => Math.max(0, ...list.map((a) => countPhrase(ref, a)));

function validateUtterances(utterances, aliases, errors, warnings) {
  const stats = { utterances: 0, byCategory: Object.fromEntries(CATEGORIES.map((c) => [c, 0])), termOccurrences: 0, termsUsed: new Set() };
  if (!Array.isArray(utterances) || !utterances.length) {
    errors.push('utterances.json: must be a non-empty array');
    return stats;
  }
  const seen = new Set();
  utterances.forEach((u, i) => {
    const where = `utterances.json[${i}]${u && u.id ? ` (${u.id})` : ''}`;
    if (!u || typeof u !== 'object' || Array.isArray(u)) { errors.push(`${where}: must be an object`); return; }
    for (const f of UTTERANCE_FIELDS) if (!(f in u)) errors.push(`${where}: missing "${f}"`);
    for (const f of Object.keys(u)) if (!UTTERANCE_FIELDS.includes(f)) warnings.push(`${where}: unknown field "${f}"`);

    if (typeof u.id !== 'string' || !/^u\d{3}$/.test(u.id)) errors.push(`${where}: id must look like "u001"`);
    else if (seen.has(u.id)) errors.push(`${where}: duplicate id`);
    else seen.add(u.id);

    if (!CATEGORIES.includes(u.category)) errors.push(`${where}: category must be one of ${CATEGORIES.join(', ')}`);
    else stats.byCategory[u.category]++;

    if (typeof u.reference !== 'string' || !u.reference.trim()) { errors.push(`${where}: reference must be non-empty text`); return; }
    if (/\d/.test(u.reference)) errors.push(`${where}: reference has a digit; write numbers as spoken ("twelve")`);
    const ref = normalize(u.reference);
    const words = ref.split(' ').length;
    if (words < 6 || words > 40) warnings.push(`${where}: ${words} words; aim for 5 to 15 seconds spoken`);

    if (!Array.isArray(u.terms) || !u.terms.length) { errors.push(`${where}: terms must list at least one term`); return; }
    if (new Set(u.terms).size !== u.terms.length) errors.push(`${where}: terms lists a term twice`);
    for (const t of u.terms) {
      if (!aliases[t]) { errors.push(`${where}: term "${t}" is not in terms.json`); continue; }
      const n = occurrences(ref, aliases[t]);
      if (!n) errors.push(`${where}: term "${t}" is listed but no alias of it appears in the reference`);
      stats.termOccurrences += n;
      stats.termsUsed.add(t);
    }
    // A term spoken in the reference but not listed would be silently left out of the score
    for (const [t, list] of Object.entries(aliases)) {
      if (!u.terms.includes(t) && occurrences(ref, list)) errors.push(`${where}: reference contains "${t}" but terms doesn't list it`);
    }
    stats.utterances++;
  });
  for (const t of Object.keys(aliases)) if (!stats.termsUsed.has(t)) warnings.push(`terms.json: "${t}" isn't used by any utterance`);
  return stats;
}

function validateData(dataDir) {
  const errors = [];
  const warnings = [];
  const terms = readJson(path.join(dataDir, 'terms.json'), errors);
  const utterances = readJson(path.join(dataDir, 'utterances.json'), errors);
  if (errors.length) return { errors, warnings, stats: null };
  const aliases = validateTerms(terms, errors, warnings);
  const stats = validateUtterances(utterances, aliases, errors, warnings);
  stats.terms = Object.keys(aliases).length;
  stats.termsUsed = stats.termsUsed.size;
  return { errors, warnings, stats };
}

module.exports = { validateData, CATEGORIES };
