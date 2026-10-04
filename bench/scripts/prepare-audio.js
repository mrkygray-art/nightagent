// Converts recordings to the format every provider gets: mono, 16 kHz, 16-bit WAV.
//
//   node scripts/prepare-audio.js [--source human]
//
// Reads bench/recordings/<source>/<id>.<ext> (any format ffmpeg reads: m4a, mp3, wav, webm, ...)
// and writes bench/data/audio/<source>/<id>.wav. Both folders are git-ignored.
// Uses `ffmpeg` on PATH, or the FFMPEG environment variable.
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');
const { wavSeconds } = require('../lib/wav');

const arg = (name) => { const i = process.argv.indexOf(name); return i === -1 ? null : process.argv[i + 1]; };
const source = arg('--source') || 'human';
const root = path.join(__dirname, '..');
const inDir = path.join(root, 'recordings', source);
const outDir = path.join(root, 'data', 'audio', source);
const ffmpeg = process.env.FFMPEG || 'ffmpeg';

const ids = new Set(JSON.parse(fs.readFileSync(path.join(root, 'data', 'utterances.json'), 'utf8')).map((u) => u.id));
if (!fs.existsSync(inDir)) { console.error(`Put recordings in ${inDir} named like u001.m4a`); process.exit(1); }
if (spawnSync(ffmpeg, ['-version']).status !== 0) { console.error('ffmpeg not found. Install it (winget install Gyan.FFmpeg) or set FFMPEG.'); process.exit(1); }
fs.mkdirSync(outDir, { recursive: true });

let converted = 0;
const problems = [];
for (const name of fs.readdirSync(inDir).sort()) {
  const id = path.parse(name).name.toLowerCase();
  if (!ids.has(id)) { problems.push(`${name}: not an utterance id (expected u001 to u0${ids.size})`); continue; }
  const out = path.join(outDir, `${id}.wav`);
  const r = spawnSync(ffmpeg, ['-y', '-loglevel', 'error', '-i', path.join(inDir, name), '-ac', '1', '-ar', '16000', '-sample_fmt', 's16', out]);
  if (r.status !== 0) { problems.push(`${name}: ffmpeg failed: ${r.stderr.toString().trim().slice(0, 200)}`); continue; }
  const secs = wavSeconds(out);
  if (secs < 2 || secs > 30) problems.push(`${name}: ${secs.toFixed(1)} s long; check it's the right clip`);
  converted++;
}

const have = new Set(fs.readdirSync(outDir).map((n) => path.parse(n).name));
const missing = [...ids].filter((id) => !have.has(id));
console.log(`Converted ${converted} file(s) into ${outDir}`);
console.log(`${source}: ${have.size} of ${ids.size} utterances have audio${missing.length ? `; missing: ${missing.join(', ')}` : ''}`);
for (const p of problems) console.log(`  check: ${p}`);
process.exit(problems.some((p) => p.includes('failed') || p.includes('not an utterance')) ? 1 : 0);
