// Loads bench/.env into process.env (variables already set win). Keys come from here only.
const fs = require('fs');
const path = require('path');

function loadEnv(file = path.join(__dirname, '..', '.env')) {
  let text;
  try { text = fs.readFileSync(file, 'utf8'); } catch { return; }
  for (const line of text.split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$/);
    if (m && !(m[1] in process.env)) process.env[m[1]] = m[2].replace(/^(['"])(.*)\1$/, '$2');
  }
}

function requireKey(name, options = {}) {
  const key = options.apiKey ?? process.env[name];
  if (!key) throw new Error(`${name} is not set. Copy bench/.env.example to bench/.env and add it.`);
  return key;
}

module.exports = { loadEnv, requireKey };
