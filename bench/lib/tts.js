// ElevenLabs text-to-speech for the `tts` source. Settings come from config.json `tts`.
const { requestWithRetry } = require('./http');

const voiceFor = (tts, index) => tts.voices[index % tts.voices.length];

const estimateUsd = (tts, texts) => (texts.reduce((n, t) => n + t.length, 0) / 1000) * tts.pricing.per_1k_chars;

// Returns { ok, audio (Buffer), attempts, error }. Never throws on HTTP errors.
async function synthesize(text, voice, { tts, retry, apiKey, fetch, sleep }) {
  const url = `${tts.endpoint.replace('{voice_id}', encodeURIComponent(voice.voice_id))}?output_format=${encodeURIComponent(tts.output_format)}`;
  const res = await requestWithRetry(() => ({
    url,
    init: {
      method: 'POST',
      headers: { 'xi-api-key': apiKey, 'Content-Type': 'application/json', Accept: 'audio/wav' },
      body: JSON.stringify({ text, model_id: tts.model, seed: tts.seed }),
    },
  }), retry, { fetch: fetch ?? globalThis.fetch, sleep, binary: true });
  if (!res.ok) return { ok: false, audio: null, attempts: res.attempts, error: res.error };
  const audio = Buffer.from(res.body);
  if (audio.toString('ascii', 0, 4) !== 'RIFF') return { ok: false, audio: null, attempts: res.attempts, error: 'response is not a WAV file' };
  return { ok: true, audio, attempts: res.attempts, error: null };
}

module.exports = { voiceFor, estimateUsd, synthesize };
