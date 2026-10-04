// Mixes noise into speech at a target signal-to-noise ratio (16-bit PCM samples).
// SNR is measured over the whole clip: 20*log10(rms(speech) / rms(scaled noise)).

function rms(samples) {
  let sum = 0;
  for (const v of samples) sum += v * v;
  return Math.sqrt(sum / (samples.length || 1));
}

function mixAtSnr(speech, noise, snrDb) {
  if (noise.length < speech.length) throw new Error('noise is shorter than speech');
  const speechRms = rms(speech);
  const noiseRms = rms(noise.subarray(0, speech.length));
  if (!speechRms || !noiseRms) throw new Error('speech or noise is silent');
  const scale = speechRms / (noiseRms * 10 ** (snrDb / 20));
  const out = new Int16Array(speech.length);
  let clipped = 0;
  for (let i = 0; i < speech.length; i++) {
    const v = Math.round(speech[i] + noise[i] * scale);
    if (v > 32767 || v < -32768) clipped++;
    out[i] = Math.max(-32768, Math.min(32767, v));
  }
  return { out, scale, clipped };
}

// Actual SNR of a mix, given the original speech (for verification and tests).
function measuredSnrDb(speech, mixed) {
  const noise = new Float64Array(speech.length);
  for (let i = 0; i < speech.length; i++) noise[i] = mixed[i] - speech[i];
  return 20 * Math.log10(rms(speech) / rms(noise));
}

module.exports = { rms, mixAtSnr, measuredSnrDb };
