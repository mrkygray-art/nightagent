// ElevenLabs Scribe batch transcription (POST /v1/speech-to-text), model and settings from config.json.
// Boosted condition: one `keyterms` multipart field per term, as the official SDK sends it.
const fs = require('fs');
const path = require('path');
const config = require('../config.json');
const { requestWithRetry } = require('../lib/http');
const { requireKey } = require('../lib/env');

function buildForm(cfg, audio, filename, keyterms) {
  const form = new FormData();
  form.append('model_id', cfg.model);
  form.append('file', new Blob([audio]), filename);
  for (const [k, v] of Object.entries(cfg.baseline)) form.append(k, String(v));
  for (const t of keyterms || []) form.append('keyterms', t);
  return form;
}

// options: { keyterms?: string[], apiKey?, fetch?, sleep?, config? }
async function transcribe(audioPath, options = {}) {
  const cfg = options.config?.providers?.elevenlabs ?? config.providers.elevenlabs;
  const retry = options.config?.retry ?? config.retry;
  const key = requireKey('ELEVENLABS_API_KEY', options);
  const audio = fs.readFileSync(audioPath);
  const res = await requestWithRetry(() => ({
    url: cfg.endpoint,
    init: { method: 'POST', headers: { 'xi-api-key': key }, body: buildForm(cfg, audio, path.basename(audioPath), options.keyterms) },
  }), retry, options);

  const base = { latencyMs: res.latencyMs, attempts: res.attempts, raw: res.body };
  if (!res.ok) return { ...base, text: null, error: res.error };
  const text = res.body?.text;
  if (typeof text !== 'string') return { ...base, text: null, error: 'unexpected response: no text field' };
  return { ...base, text, error: null, audioSeconds: null };
}

module.exports = { transcribe, buildForm, name: 'elevenlabs' };
