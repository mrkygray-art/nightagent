// Prints the lines to record, one per file name.   node scripts/reading-list.js
const utterances = require('../data/utterances.json');
for (const u of utterances) console.log(`${u.id}  ${u.reference}`);
