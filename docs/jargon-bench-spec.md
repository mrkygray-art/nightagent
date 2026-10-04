# Jargon Bench: Spec (NightAgent module)

Location in repo: `docs/jargon-bench-spec.md`
Code location: `bench/` (inside the NightAgent repo; not deployed, since `.vercelignore` uploads only the app)
Status: v1 draft

---

## 1. Purpose

Measure how well speech-to-text providers handle **physical-security domain vocabulary** (Verkada, PoE, NVR, Cisco Catalyst, door hardware, etc.), show a measurable fix, and produce a one-page customer-facing readout.

This is a pre-sales POC in miniature: a customer's domain words get mangled, here is the evidence, here is the fix, here is the cost and latency tradeoff.

## 2. Non-goals

- Not a general STT leaderboard. The claim is limited to this domain and this dataset.
- Not a real-time/streaming benchmark in v1 (batch/prerecorded only).
- No UI beyond a static results page and a PDF readout.
- No claims about vendor quality outside the tested conditions.

## 3. Success criteria

1. One command runs the whole benchmark and writes reproducible results.
2. Every number in the scorecard traces to a raw result file in `bench/results/`.
3. The scoring code has unit tests that pass in CI.
4. The README states sample size, audio sources, and limitations plainly.
5. A reviewer can clone the repo, add their own API keys, and reproduce the results.

## 4. Dataset

### 4.1 Utterances
File: `bench/data/utterances.json`

~45 short utterances (5 to 15 seconds spoken), each written the way a field tech, SE, or customer would actually say it.

```json
{
  "id": "u017",
  "category": "networking",
  "reference": "The Cisco Catalyst nine thousand switch is out of PoE budget on port twelve.",
  "terms": ["Cisco Catalyst", "PoE"]
}
```

Categories (aim for roughly 8 to 10 utterances each):
- `cctv`: camera models, NVR, VMS, retention, frame rate
- `access_control`: door hardware, strikes, REX, readers, controllers
- `networking`: PoE, VLAN, switch models, uplinks
- `vendors`: Verkada, Axis, Hanwha, Genetec, Milestone, Mercury, DMP
- `dispatch`: alarm and service-call phrasing (ties to NightAgent's after-hours calls)

### 4.2 Term list
File: `bench/data/terms.json`

Each jargon term has a canonical form and accepted aliases.

```json
{
  "PoE": ["PoE", "P o E", "power over ethernet"],
  "NVR": ["NVR", "N V R"]
}
```

Aliases are decided before running any provider and are not edited afterward based on results. Note this rule in the README.

### 4.3 Audio sources
Each utterance is produced up to three ways. Label every file and report each source separately.

| Source | How | Notes |
|---|---|---|
| `human` | Ky records the utterances (phone or headset) | The most honest condition. Record at least 25. |
| `tts` | Generated with TTS using 2 to 3 varied voices | **Bias warning:** TTS audio from one vendor fed to the same vendor's STT may score unusually well. State this in the README. |
| `noisy` | `human` audio mixed with background noise via ffmpeg (e.g. warehouse/HVAC noise at a fixed SNR) | Document the noise file and SNR. |

Audio goes in `bench/data/audio/<source>/<id>.wav`. Normalize to mono, 16 kHz WAV with ffmpeg. Audio files are gitignored by default. Commit only a few samples plus a script that regenerates the rest.

Consent note: only record your own voice, or people who agreed.

## 5. Providers

Adapter interface in `bench/providers/`:

```js
// every adapter exports:
async function transcribe(audioPath, options) {
  // returns { text, latencyMs, raw, error? }
}
```

v1 adapters:
- `deepgram.js`: prerecorded transcription endpoint
- `elevenlabs.js`: Scribe speech-to-text endpoint

Rules:
- **Verify current model names, endpoints, and parameters in each vendor's docs before coding.** Do not guess from memory.
- Pin the exact model ID in `bench/config.json` and write it into every result file.
- Retry transient errors (429/5xx) up to 2 times with backoff; record failures as failures, never silently drop them.
- Keys come from `.env` only (see section 11).

## 6. Conditions (the experiment)

For each provider, run:

1. **Baseline:** default settings, no domain help.
2. **Boosted:** the provider's vocabulary-boosting feature (e.g. keyterm/keyword prompting or custom vocabulary) loaded with the term list from `terms.json`. Confirm the feature exists for the chosen model in the docs. If a provider has no equivalent, record "not available" instead of faking one.

Run each (provider, condition, audio source) combination **3 times** to get stable latency numbers. Transcripts are expected to be near-identical across runs; flag any that aren't.

## 7. Metrics

| Metric | Definition |
|---|---|
| **WER** | Word error rate vs. reference after normalization (section 8) |
| **Jargon term accuracy** | Of all term occurrences in the references, the percentage present in the transcript (using aliases) |
| **Latency** | Wall-clock ms from request sent to response received; report median and p95 across runs |
| **Failure rate** | Failed requests / total requests |
| **Est. cost** | Audio minutes × per-minute price from `bench/config.json` |

Pricing lives in config with a `retrieved_on` date and a source URL. Never hardcode prices in code, and show the date next to any cost figure.

The headline is the **before/after on jargon term accuracy** (baseline vs. boosted), per provider.

## 8. Scoring and normalization

File: `bench/score.js`

- Lowercase, strip punctuation, collapse whitespace.
- Number handling: write references the way they are spoken ("nine thousand", "twelve"), and normalize digits in transcripts to words, or the reverse. Pick one rule and test it.
- WER via word-level edit distance (substitutions + deletions + insertions) / reference word count.
- Term match: a term counts as correct if the normalized transcript contains any alias as a whole-word/phrase match.
- Report per-term misses so the readout can show what was mangled (e.g. "Verkada" heard as something else).

## 9. Outputs

```
bench/results/<run-id>/
  config.snapshot.json     # models, settings, prices, date, git commit
  raw/<provider>/<condition>/<source>/<id>.json
  summary.json             # all aggregate metrics
  scorecard.html           # static results page
  readout.pdf              # one-page customer-facing summary
```

**Readout (one page, customer-facing tone):**
1. What we tested and why (two sentences)
2. Headline table: jargon accuracy baseline vs. boosted, per provider
3. Top 5 mangled terms and what fixed them
4. Latency and estimated cost per audio hour
5. Recommendation and caveats (sample size, sources, date)

## 10. CLI

```
node bench/run.js --providers deepgram,elevenlabs --sources human,tts,noisy
node bench/score.js --run <run-id>
node bench/report.js --run <run-id>
node bench/run.js --dry-run     # validates data files, no API calls
```

## 11. Security and hygiene

- Keys in `.env`, gitignored. Commit `.env.example` only.
- Never log full API responses containing keys or headers.
- Audio and raw results gitignored; commit only `summary.json` and sample files.
- Add a `.github/workflows/test.yml` that runs the unit tests on push.

## 12. Tests

Use Node's built-in test runner (or Jest if already in the repo).

- `score.test.js`: WER on known fixtures (identical, one substitution, one insertion, one deletion, empty transcript)
- Normalization edge cases (numbers, hyphens, casing)
- Term matching with aliases and false-positive checks (a term inside a longer word must not match)
- Adapter tests with mocked HTTP responses, including 429 and 500 handling
- `--dry-run` fails loudly on malformed `utterances.json`

## 13. README requirements

The bench README must include:
- One-paragraph purpose and the exact claim being made
- Dataset size, categories, and audio sources with counts
- The TTS bias caveat
- How to reproduce (install, keys, commands)
- **Limitations section:** small sample, one speaker, one noise profile, batch only, models and prices as of the run date
- Results snapshot with the run date

## 14. Portfolio integration

- Add a Jargon Bench section next to the NightAgent case study on the portfolio: scorecard, per-term misses, link to the PDF readout and the repo.
- Ask Ky gets a short factual description of the module (no numbers until real ones exist).
- Record a 3-minute walkthrough: dataset, one baseline miss, the boosted fix, the readout.

## 15. Build order

1. Data files and `--dry-run` validation
2. `score.js` with tests (before any API calls)
3. Deepgram adapter, then ElevenLabs adapter
4. Baseline run, human audio only
5. Boosted condition
6. TTS and noisy sources
7. Scorecard HTML, then PDF readout
8. README, CI, portfolio tab, walkthrough video

## 16. Acceptance checklist

- [ ] Fresh clone + keys reproduces `summary.json` (latency will vary, accuracy should not)
- [ ] All reported numbers come from real runs in `bench/results/`
- [ ] Unit tests pass in CI
- [ ] README limitations section is complete
- [ ] Readout fits on one page
- [ ] No secrets in git history
- [ ] Results page and video live on the portfolio

## 17. Honest talking points (only once true)

- "I built the scorer and tests first so I couldn't fool myself with the results."
- "I ran human, TTS, and noisy audio separately because TTS audio can flatter the vendor that made it."
- "Boosting improved jargon accuracy from X% to Y% on my dataset; with one speaker and ~45 utterances, I'd treat that as directional, not definitive."
- "Here's the readout I'd hand a customer."

## 18. Decisions (settled 2026-10-03)

These settle open points above. Where they differ from earlier sections, this section wins.

1. **Home:** `bench/` in the NightAgent repo (VoiceOps had no code yet). Node, CommonJS, Node's built-in test runner, no build step. The PDF readout is printed with headless Chrome.
2. **Numbers:** references are written the way they are spoken ("nine thousand", "twelve") and contain no digits. Transcripts are normalized digits-to-words. Letter-digit tokens are split ("Cat6" becomes "cat six"). Term aliases contain no digits.
3. **Repeated terms:** each occurrence in a reference counts. A term found k times in the transcript and n times in the reference scores min(k, n) of n.
4. **WER vs. aliases:** WER is strict against the reference wording. Aliases apply only to jargon term accuracy.
5. **Boosted list:** only the canonical term names are sent, and the same full list for every utterance (how a customer would configure it).
6. **TTS audio:** generated with ElevenLabs voices only, labeled `tts (ElevenLabs-generated)` everywhere. Because this favors ElevenLabs STT, the headline uses `human` audio only.
7. **Repeats:** `human` runs 3 times per (provider, condition); `tts` and `noisy` run once.
8. **Budget guard:** a paid run prints request count and total audio minutes first and needs `--confirm`; it stops at a spend cap set in `config.json`. STT and TTS calls use ElevenLabs account credits (shared with the live agents) but never call Sam, so they do not count toward Sam's daily call limit.
9. **Noise:** a redistributable noise recording at a fixed SNR, both documented in the README; ffmpeg is a prerequisite.
10. **Samples:** a few of Ky's own recordings may be committed as samples.

