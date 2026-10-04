// Estimated cost at list price, from config.json pricing (never hardcoded).

function perMinute(pricing, provider, boosted) {
  const p = pricing[provider];
  if (!p) throw new Error(`No pricing for provider "${provider}" in config.json`);
  if (p.per_minute != null) return p.per_minute + (boosted ? p.boost_per_minute ?? 0 : 0);
  if (p.per_hour != null) return (p.per_hour + (boosted ? p.boost_per_hour ?? 0 : 0)) / 60;
  throw new Error(`Pricing for "${provider}" needs per_minute or per_hour`);
}

const estimateUsd = (pricing, provider, condition, audioSeconds) =>
  (audioSeconds / 60) * perMinute(pricing, provider, condition === 'boosted');

const perAudioHourUsd = (pricing, provider, condition) => perMinute(pricing, provider, condition === 'boosted') * 60;

module.exports = { perMinute, estimateUsd, perAudioHourUsd };
