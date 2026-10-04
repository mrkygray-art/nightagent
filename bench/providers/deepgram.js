// Deepgram pre-recorded transcription (POST /v1/listen), model and settings from config.json.
// Boosted condition: one `keyterm` query parameter per term (Nova-3 keyterm prompting).
const fs = require('fs');
const path = require('path');
const config = require('../config.json');
const { requestWithRetry } = require('../lib/http');
const { requireKey } = require('../lib/env');

const CONTENT_TYPES = { '.wav': 'audio/wav', '.mp3': 'audio/mpeg', '.m4a': 'audio/mp4', '.webm': 'audio/webm' };

function buildUrl(cfg, keyterms) {
  const params = new URLSearchParams({ model: cfg.model });
  for (const [k, v] of Object.entries(cfg.baseline)) params.set(k, String(v));
  for (const t of keyterms || []) params.append('keyterm', t);
  return `${cfg.endpoint}?${params}`;
}

// options: { keyterms?: string[], apiKey?, fetch?, sleep?, config? }
async function transcribe(audioPath, options = {}) {
  const cfg = options.config?.providers?.deepgram ?? config.providers.deepgram;
  const retry = options.config?.retry ?? config.retry;
  const key = requireKey('DEEPGRAM_API_KEY', options);
  const audio = fs.readFileSync(audioPath);
  const url = buildUrl(cfg, options.keyterms);
  const res = await requestWithRetry(() => ({
    url,
    init: {
      method: 'POST',
      headers: { Authorization: `Token ${key}`, 'Content-Type': CONTENT_TYPES[path.extname(audioPath).toLowerCase()] || 'application/octet-stream' },
      body: audio,
    },
  }), retry, options);

  const base = { latencyMs: res.latencyMs, attempts: res.attempts, raw: res.body };
  if (!res.ok) return { ...base, text: null, error: res.error };
  const text = res.body?.results?.channels?.[0]?.alternatives?.[0]?.transcript;
  if (typeof text !== 'string') return { ...base, text: null, error: 'unexpected response: no transcript field' };
  return { ...base, text, error: null, audioSeconds: res.body?.metadata?.duration ?? null };
}

module.exports = { transcribe, buildUrl, name: 'deepgram' };
