// Generates the `tts` source with ElevenLabs voices (settings in config.json `tts`).
//
//   node scripts/generate-tts.js             print the plan and estimated cost; no API calls
//   node scripts/generate-tts.js --confirm   generate into recordings/tts/, then run
//                                            prepare-audio.js --source tts
//
// Writes recordings/tts/<id>.wav (git-ignored) and data/tts-manifest.json (committed: voice,
// model, seed, characters, SHA-256 of each file). Skips clips that already exist, so a rerun only fills gaps.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const config = require('../config.json');
const { loadEnv, requireKey } = require('../lib/env');
const { voiceFor, estimateUsd, synthesize } = require('../lib/tts');

const root = path.join(__dirname, '..');
const outDir = path.join(root, 'recordings', 'tts');
const manifestPath = path.join(root, 'data', 'tts-manifest.json');
const tts = config.tts;

async function main() {
  const utterances = JSON.parse(fs.readFileSync(path.join(root, 'data', 'utterances.json'), 'utf8'));
  const jobs = utterances.map((u, i) => ({ id: u.id, text: u.reference, voice: voiceFor(tts, i) }))
    .filter((j) => !fs.existsSync(path.join(outDir, `${j.id}.wav`)));
  const usd = estimateUsd(tts, jobs.map((j) => j.text));
  const chars = jobs.reduce((n, j) => n + j.text.length, 0);

  console.log(`TTS plan: ${jobs.length} of ${utterances.length} clips to generate (${utterances.length - jobs.length} already exist)`);
  console.log(`  model ${tts.model}, ${tts.output_format}, seed ${tts.seed}`);
  console.log(`  voices: ${tts.voices.map((v) => v.name).join(', ')} (rotating)`);
  console.log(`  characters: ${chars}`);
  console.log(`  estimated cost: $${usd.toFixed(4)} at list price (retrieved ${tts.pricing.retrieved_on})`);
  if (!jobs.length) return 0;
  if (!process.argv.includes('--confirm')) { console.log('\nNo API calls were made. Add --confirm to generate.'); return 0; }

  loadEnv();
  const apiKey = requireKey('ELEVENLABS_API_KEY');
  fs.mkdirSync(outDir, { recursive: true });
  const manifest = fs.existsSync(manifestPath) ? JSON.parse(fs.readFileSync(manifestPath, 'utf8'))
    : { generator: tts.generator, model: tts.model, output_format: tts.output_format, seed: tts.seed, clips: {} };
  let failures = 0;
  for (const [n, j] of jobs.entries()) {
    const r = await synthesize(j.text, j.voice, { tts, retry: config.retry, apiKey });
    if (!r.ok) { failures++; console.log(`[${n + 1}/${jobs.length}] ${j.id} ${j.voice.name}: FAILED ${r.error.slice(0, 120)}`); continue; }
    fs.writeFileSync(path.join(outDir, `${j.id}.wav`), r.audio);
    manifest.clips[j.id] = { voice: j.voice.name, voice_id: j.voice.voice_id, chars: j.text.length,
      sha256: crypto.createHash('sha256').update(r.audio).digest('hex'), generatedAt: new Date().toISOString() };
    fs.writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
    console.log(`[${n + 1}/${jobs.length}] ${j.id} ${j.voice.name}: ok`);
  }
  console.log(`\nGenerated ${jobs.length - failures} of ${jobs.length}. Next: node scripts/prepare-audio.js --source tts`);
  return failures ? 1 : 0;
}

main().then((c) => process.exit(c), (e) => { console.error(e.message); process.exit(1); });
