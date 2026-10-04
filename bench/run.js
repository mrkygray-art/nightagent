// Jargon Bench runner.
//
//   node run.js --dry-run                 validate the dataset; no API calls
//   node run.js --dry-run --data <dir>    validate another data folder (used by tests)
//
// Provider runs are added in build step 3.
const path = require('path');
const { validateData } = require('./lib/validate');

function arg(name) {
  const i = process.argv.indexOf(name);
  return i === -1 ? null : process.argv[i + 1];
}

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

function main() {
  const dataDir = path.resolve(arg('--data') || path.join(__dirname, 'data'));
  if (process.argv.includes('--dry-run')) process.exit(dryRun(dataDir));
  console.error('Provider runs are not built yet (build step 3). Use --dry-run.');
  process.exit(1);
}

main();
