// Builds the `noisy` source: each human clip mixed with seeded synthetic noise at a fixed SNR
// (settings in config.json `noise`). No API calls.
//
//   node scripts/make-noisy.js
//
// Reads data/audio/<from_source>/<id>.wav, writes data/audio/noisy/<id>.wav and
// data/noisy-manifest.json (committed: seed, measured SNR, clipped samples per clip, ffmpeg version).
// Uses `ffmpeg` on PATH, or the FFMPEG environment variable.
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');
const config = require('../config.json');
const { wavSeconds, readPcm16, silentWav } = require('../lib/wav');
const { mixAtSnr, measuredSnrDb } = require('../lib/mix');

const root = path.join(__dirname, '..');
const noise = config.noise;
const inDir = path.join(root, 'data', 'audio', noise.from_source);
const outDir = path.join(root, 'data', 'audio', 'noisy');
const ffmpeg = process.env.FFMPEG || 'ffmpeg';

function makeNoise(seconds, seed) {
  const r = spawnSync(ffmpeg, ['-loglevel', 'error', '-f', 'lavfi', '-i',
    `anoisesrc=color=${noise.type}:seed=${seed}:sample_rate=16000:duration=${(seconds + 0.1).toFixed(3)}:amplitude=0.5`,
    '-f', 's16le', '-ac', '1', '-'], { maxBuffer: 64 * 1024 * 1024 });
  if (r.status !== 0) throw new Error(`ffmpeg noise failed: ${r.stderr.toString().slice(0, 200)}`);
  return new Int16Array(r.stdout.buffer.slice(r.stdout.byteOffset, r.stdout.byteOffset + r.stdout.length));
}

const version = spawnSync(ffmpeg, ['-version']);
if (version.status !== 0) { console.error('ffmpeg not found. Install it (winget install Gyan.FFmpeg) or set FFMPEG.'); process.exit(1); }
if (!fs.existsSync(inDir)) { console.error(`No ${noise.from_source} audio in ${inDir}; run prepare-audio.js first.`); process.exit(1); }
fs.mkdirSync(outDir, { recursive: true });

const ids = JSON.parse(fs.readFileSync(path.join(root, 'data', 'utterances.json'), 'utf8')).map((u) => u.id);
const manifest = { from_source: noise.from_source, type: noise.type, generator: noise.generator, snr_db: noise.snr_db,
  base_seed: noise.seed, ffmpeg: version.stdout.toString().split('\n')[0], clips: {} };
for (const [i, id] of ids.entries()) {
  const file = path.join(inDir, `${id}.wav`);
  if (!fs.existsSync(file)) continue;
  const speech = readPcm16(file);
  const seed = noise.seed + i + 1;
  const { out, clipped } = mixAtSnr(speech, makeNoise(wavSeconds(file), seed), noise.snr_db);
  const wav = silentWav(out.length / 16000);
  Buffer.from(out.buffer).copy(wav, 44);
  fs.writeFileSync(path.join(outDir, `${id}.wav`), wav);
  manifest.clips[id] = { seed, measured_snr_db: Math.round(measuredSnrDb(speech, out) * 100) / 100, clipped_samples: clipped };
}
fs.writeFileSync(path.join(root, 'data', 'noisy-manifest.json'),`${JSON.stringify(manifest, null, 2)}\n`);
const clips = Object.values(manifest.clips);
const snrs = clips.map((c) => c.measured_snr_db);
console.log(`Made ${clips.length} noisy clips at ${noise.snr_db} dB SNR (${noise.type} noise) in ${outDir}`);
console.log(`  measured SNR ${Math.min(...snrs)} to ${Math.max(...snrs)} dB; clipped samples total ${clips.reduce((n, c) => n + c.clipped_samples, 0)}`);
