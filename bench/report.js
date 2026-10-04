// Builds the scorecard page and the one-page readout from the runs in report-runs.json.
//
//   node report.js                 writes report/scorecard.html, report/readout.html, report/readout.pdf
//   node report.js --no-pdf        skip the PDF (no Chrome needed)
//
// Every figure comes from the runs' summary.json files via lib/report-data.js.
// The PDF is printed with headless Chrome (CHROME env var, or the default Windows path).
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');
const { loadModel, PROVIDERS, SOURCES } = require('./lib/report-data');

const REPO = 'https://github.com/mrkygray-art/nightagent/tree/main/bench';
const NAMES = { deepgram: 'Deepgram', elevenlabs: 'ElevenLabs' };
const SOURCE_NAMES = { human: 'Recorded speech', noisy: 'Recorded speech + noise (10 dB SNR)', tts: 'TTS (ElevenLabs-generated)' };

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
// Percentages are computed from exact counts (never from already-rounded values), rounded half up.
const round1 = (num, den) => (Math.round((num * 1000) / den) / 10).toFixed(1);
const pct = (a) => (a && a.expected ? `${round1(a.hits, a.expected)}%` : '—');
const werPct = (c) => (c.wordErrors ? `${round1(c.wordErrors.edits, c.wordErrors.refWords)}%` : '—');
const pctNum = (a) => a.hits / a.expected;
const frac = (a) => (a ? `${a.hits} of ${a.expected}` : '—');
const ms = (n) => (n == null ? '—' : `${Math.round(n)} ms`);
const usd = (n) => (n == null ? '—' : `$${n.toFixed(2)}`);
const cell = (c) => (c ? `${c.hits}/${c.expected}` : '—');

function recommendation(m) {
  const [a, b] = m.headline;
  const lines = [];
  lines.push(`Turn on keyterm boosting for field audio. On recorded speech it raised jargon accuracy from ${pct(a.baseline)} to ${pct(a.boosted)} with ${NAMES[a.provider]} and from ${pct(b.baseline)} to ${pct(b.boosted)} with ${NAMES[b.provider]}.`);
  lines.push(`The cost was small: median latency changed by ${Math.round(a.latencyBoosted.median - a.latencyBaseline.median)} ms and ${Math.round(b.latencyBoosted.median - b.latencyBaseline.median)} ms, and list price rose from ${usd(a.costPerHourBaseline)} to ${usd(a.costPerHourBoosted)} and from ${usd(b.costPerHourBaseline)} to ${usd(b.costPerHourBoosted)} per audio hour.`);
  const better = pctNum(a.boosted) >= pctNum(b.boosted) ? [a, b] : [b, a];
  const faster = a.latencyBoosted.median <= b.latencyBoosted.median ? [a, b] : [b, a];
  lines.push(`On this dataset ${NAMES[better[0].provider]} was more accurate (${pct(better[0].boosted)} vs ${pct(better[1].boosted)} boosted) and ${NAMES[faster[0].provider]} answered faster (median ${ms(faster[0].latencyBoosted.median)} vs ${ms(faster[1].latencyBoosted.median)}).`);
  const fpTerms = [...new Set(m.falsePositives.map((f) => f.term))];
  if (fpTerms.length) lines.push(`Review the boost list for terms that sound like everyday words: boosting wrote ${fpTerms.map((t) => `"${t}"`).join(' and ')} where it wasn't said (${m.falsePositives.length} clip-level cases across all audio).`);
  return lines;
}

function caveats(m) {
  return [
    `${m.human.clips} recorded clips from one speaker, each sent ${m.human.repeats} times; ${m.human.termOccurrences} jargon-term occurrences.`,
    'Noise is steady synthetic pink noise; real job sites are usually harder. TTS audio came from ElevenLabs voices and is excluded from the headline.',
    `Batch transcription only. Models and list prices as of ${m.pricesRetrievedOn}; runs on ${m.runDate} (UTC).`,
  ];
}

const STYLE = `
:root { --bg:#ffffff; --fg:#14171f; --muted:#5b6474; --line:#e3e6eb; --card:#f6f7f9; --accent:#2557d6; --good:#1d7a46; --bad:#b4322a; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg:#101318; --fg:#e8eaee; --muted:#9aa3b2; --line:#2a2f38; --card:#171b22; --accent:#7aa2ff; --good:#5cc98c; --bad:#ff8a80; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--fg); font: 15px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
main { max-width: 980px; margin: 0 auto; padding: 28px 16px 48px; }
h1 { font-size: 26px; margin: 0 0 4px; } h2 { font-size: 18px; margin: 32px 0 10px; } h3 { font-size: 15px; margin: 18px 0 6px; }
p { margin: 6px 0; } .muted { color: var(--muted); } a { color: var(--accent); }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin-top: 14px; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; }
.big { font-size: 28px; font-weight: 650; } .arrow { color: var(--muted); margin: 0 6px; }
.scroll { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
th { font-weight: 600; color: var(--muted); } td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.miss { color: var(--bad); } .hit { color: var(--good); } code { font-size: 13px; }
`;

function scorecard(m) {
  const runLinks = m.runs.map((r) => `<a href="${REPO}/results/${r.runId}/summary.json">${esc(r.runId)}</a>`).join(', ');
  const headlineCards = m.headline.map((h) => `
    <div class="card"><div class="muted">${NAMES[h.provider]} <code>${esc(h.model)}</code></div>
      <div class="big">${pct(h.baseline)}<span class="arrow">→</span>${pct(h.boosted)}</div>
      <div class="muted">${frac(h.baseline)} → ${frac(h.boosted)} jargon terms, baseline → boosted</div></div>`).join('');
  const sourceTables = m.bySource.map((s) => `
    <h3>${esc(SOURCE_NAMES[s.source])}</h3>
    <div class="scroll"><table><thead><tr><th>Provider</th><th>Condition</th><th class="num">Jargon terms</th><th class="num">WER</th><th class="num">Median</th><th class="num">p95</th><th class="num">Failed</th><th class="num">False positives</th><th class="num">Clips × repeats</th></tr></thead><tbody>
    ${s.cells.map((c) => `<tr><td>${NAMES[c.provider]}</td><td>${c.condition}</td><td class="num">${pct(c.termAccuracy)} <span class="muted">(${frac(c.termAccuracy)})</span></td><td class="num">${werPct(c)}</td><td class="num">${ms(c.latencyMs.median)}</td><td class="num">${ms(c.latencyMs.p95)}</td><td class="num">${c.failures} of ${c.requests}</td><td class="num">${c.inserted}</td><td class="num">${c.clips} × ${c.repeats}</td></tr>`).join('')}
    </tbody></table></div>`).join('');
  const termRows = m.perTerm.map((t) => {
    const cols = PROVIDERS.flatMap((p) => ['baseline', 'boosted'].map((c) => {
      const v = t.cells[`human/${p}/${c}`];
      return `<td class="num ${v && v.hits < v.expected ? 'miss' : 'hit'}">${cell(v)}</td>`;
    })).join('');
    const heard = PROVIDERS.map((p) => (t.heardAs[p] ? `${NAMES[p]}: “${esc(t.heardAs[p])}”` : '')).filter(Boolean).join('<br>');
    return `<tr><td>${esc(t.term)}</td>${cols}<td class="muted">${heard}</td></tr>`;
  }).join('');
  const fpRows = m.falsePositives.map((f) => `<tr><td>${esc(SOURCE_NAMES[f.source])}</td><td>${NAMES[f.provider]} ${f.condition}</td><td>${esc(f.id)}</td><td>“${esc(f.term)}”</td><td class="num">${f.runs}</td><td class="muted">${esc(f.text)}</td></tr>`).join('');

  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Jargon Bench Scorecard</title><style>${STYLE}</style></head><body><main>
<h1>Jargon Bench scorecard</h1>
<p class="muted">How well Deepgram and ElevenLabs speech-to-text hear physical-security vocabulary, with and without vocabulary boosting. Runs on ${m.runDate} (UTC); list prices as of ${m.pricesRetrievedOn}.</p>
<h2>Headline: jargon accuracy on recorded speech</h2>
<p>${m.human.clips} clips from one speaker, each sent ${m.human.repeats} times per provider and condition (${m.human.termOccurrences} term occurrences per pass).</p>
<div class="cards">${headlineCards}</div>
<h2>Recommendation</h2>${recommendation(m).map((l) => `<p>${esc(l)}</p>`).join('')}
<h2>All results by audio source</h2>
<p class="muted">Sources are never averaged together. TTS audio was generated with ElevenLabs voices, so it can favor ElevenLabs speech-to-text.</p>
${sourceTables}
<h2>Every term, recorded speech</h2>
<p class="muted">Occurrences heard correctly across all repeats. "Heard as" is the most common baseline mistake.</p>
<div class="scroll"><table><thead><tr><th>Term</th><th class="num">Deepgram baseline</th><th class="num">Deepgram boosted</th><th class="num">ElevenLabs baseline</th><th class="num">ElevenLabs boosted</th><th>Heard as (baseline)</th></tr></thead><tbody>${termRows}</tbody></table></div>
<h2>False positives</h2>
<p class="muted">A term written where it wasn't said. Jargon accuracy can't see these, so they're counted separately.</p>
<div class="scroll"><table><thead><tr><th>Audio</th><th>Provider</th><th>Clip</th><th>Term</th><th class="num">Repeats</th><th>Transcript</th></tr></thead><tbody>${fpRows || '<tr><td colspan="6">None</td></tr>'}</tbody></table></div>
<h2>Caveats</h2><ul>${caveats(m).map((c) => `<li>${esc(c)}</li>`).join('')}</ul>
<p class="muted">Built from ${runLinks}. Dataset: ${m.dataset.utterances} utterances, ${m.dataset.terms} terms. Method, code, and raw-result format: <a href="${REPO}">${REPO.replace('https://', '')}</a>.</p>
</main></body></html>
`;
}

function readout(m) {
  const head = m.headline.map((h) => `<tr><td>${NAMES[h.provider]} <span class="muted">(${esc(h.model)})</span></td><td class="num">${pct(h.baseline)}</td><td class="num"><b>${pct(h.boosted)}</b></td><td class="num">${ms(h.latencyBoosted.median)}</td><td class="num">${usd(h.costPerHourBoosted)}</td></tr>`).join('');
  const top = m.topTerms.map((t) => `<tr><td><b>${esc(t.term)}</b></td>${t.providers.map((p) => `<td>${p.heardAs ? `“${esc(p.heardAs)}”` : '<span class="muted">heard right</span>'}</td><td class="num">${cell(p.baseline)} → ${cell(p.boosted)}</td>`).join('')}</tr>`).join('');
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Jargon Bench Readout</title><style>
@page { size: Letter; margin: 0.55in; }
body { font: 11.5px/1.45 system-ui, "Segoe UI", Roboto, sans-serif; color: #14171f; margin: 0; }
h1 { font-size: 20px; margin: 0 0 2px; } h2 { font-size: 13px; margin: 14px 0 5px; text-transform: uppercase; letter-spacing: .04em; color: #2557d6; }
p { margin: 4px 0; } .muted { color: #5b6474; } table { border-collapse: collapse; width: 100%; }
th, td { text-align: left; padding: 4px 7px; border-bottom: 1px solid #e3e6eb; } th { color: #5b6474; font-weight: 600; }
td.num, th.num { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; } ul { margin: 4px 0; padding-left: 18px; }
</style></head><body>
<h1>Speech-to-text on security jargon: readout</h1>
<p class="muted">Jargon Bench · runs on ${m.runDate} (UTC) · prepared by Ky Gray</p>
<h2>1. What we tested and why</h2>
<p>Field techs and customers use brand and part names (Verkada, PoE, Wiegand, NVR) that general speech-to-text often mishears, and a misheard word becomes a wrong ticket. We measured how often Deepgram and ElevenLabs get those terms right on ${m.human.clips} recorded field-style sentences, with and without each provider's keyterm boosting.</p>
<h2>2. Headline: jargon terms heard correctly (recorded speech)</h2>
<table><thead><tr><th>Provider</th><th class="num">Default</th><th class="num">Boosted</th><th class="num">Median latency (boosted)</th><th class="num">List price / audio hr (boosted)</th></tr></thead><tbody>${head}</tbody></table>
<h2>3. Top 5 mangled terms, and what boosting did</h2>
<table><thead><tr><th>Term</th><th>Deepgram heard</th><th class="num">Deepgram default → boosted</th><th>ElevenLabs heard</th><th class="num">ElevenLabs default → boosted</th></tr></thead><tbody>${top}</tbody></table>
<p class="muted">Ranked by misses on recorded speech without boosting, both providers combined; ties alphabetical. Counts are correct occurrences across ${m.human.repeats} repeats.</p>
<h2>4. Latency and cost</h2>
<p>${m.headline.map((h) => `${NAMES[h.provider]}: median ${ms(h.latencyBaseline.median)} default, ${ms(h.latencyBoosted.median)} boosted; ${usd(h.costPerHourBaseline)} → ${usd(h.costPerHourBoosted)} per audio hour at list price.`).join(' ')} Latency was measured from a home connection and includes upload.</p>
<h2>5. Recommendation and caveats</h2>
<ul>${recommendation(m).map((l) => `<li>${esc(l)}</li>`).join('')}</ul>
<p class="muted">${caveats(m).map(esc).join(' ')} Full scorecard and method: ${REPO.replace('https://', '')}</p>
</body></html>
`;
}

function chromePath() {
  const candidates = [process.env.CHROME, 'C:/Program Files/Google/Chrome/Application/chrome.exe', '/usr/bin/google-chrome', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'];
  return candidates.find((c) => c && fs.existsSync(c));
}

const pdfPages = (file) => (fs.readFileSync(file).toString('latin1').match(/\/Type\s*\/Page(?!s)/g) || []).length;

function main() {
  const runIds = JSON.parse(fs.readFileSync(path.join(__dirname, 'report-runs.json'), 'utf8')).runs;
  const m = loadModel({ resultsDir: path.join(__dirname, 'results'), dataDir: path.join(__dirname, 'data'), runIds });
  const out = path.join(__dirname, 'report');
  fs.mkdirSync(out, { recursive: true });
  fs.writeFileSync(path.join(out, 'scorecard.html'), scorecard(m));
  fs.writeFileSync(path.join(out, 'readout.html'), readout(m));
  console.log(`Wrote report/scorecard.html and report/readout.html from ${runIds.length} runs`);
  if (process.argv.includes('--no-pdf')) return 0;
  const chrome = chromePath();
  if (!chrome) { console.error('Chrome not found; set CHROME or use --no-pdf.'); return 1; }
  const pdf = path.join(out, 'readout.pdf');
  const r = spawnSync(chrome, ['--headless=new', '--disable-gpu', '--no-pdf-header-footer', `--print-to-pdf=${pdf}`,
    `file:///${path.join(out, 'readout.html').replace(/\\/g, '/')}`], { encoding: 'utf8' });
  if (!fs.existsSync(pdf)) { console.error(`PDF failed: ${r.stderr.slice(0, 300)}`); return 1; }
  const pages = pdfPages(pdf);
  console.log(`Wrote report/readout.pdf (${pages} page${pages === 1 ? '' : 's'})`);
  if (pages !== 1) { console.error('The readout must fit on one page.'); return 1; }
  return 0;
}

if (require.main === module) process.exit(main());

module.exports = { scorecard, readout, recommendation, caveats, pdfPages };
