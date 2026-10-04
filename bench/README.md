# Jargon Bench

**How well do speech-to-text providers hear physical-security vocabulary, and how much does vocabulary boosting help?**

Field techs, sales engineers, and customers say things like "the Verkada cameras dropped off the PoE switch in the IDF." General-purpose speech-to-text often mangles those words, and in a voice agent like NightAgent's Sam, a misheard brand or part name becomes a wrong ticket. Jargon Bench measures that on a fixed dataset, for Deepgram and ElevenLabs, with and without each provider's vocabulary-boosting feature.

**The claim is narrow on purpose:** results apply to this dataset, these audio conditions, and the models and prices on the run date. This is not a general speech-to-text leaderboard.

> **Status: in progress (build step 4 of 8).** The dataset, its validation, the scorer, both provider adapters, and the runner are done, all with tests. The scorer was written and tested before any provider was called, and the adapters and runner are tested against fakes. Next: recording the human audio, then the first real run. No provider has been run yet, so there are no results. Every number that appears here later will come from a raw result file in `bench/results/`.

Full spec: [`docs/jargon-bench-spec.md`](../docs/jargon-bench-spec.md).

## Dataset

| | |
|---|---|
| Utterances | 45, in [`data/utterances.json`](data/utterances.json) |
| Categories | `cctv`, `access_control`, `networking`, `vendors`, `dispatch` (9 each) |
| Jargon terms | 44, in [`data/terms.json`](data/terms.json) |
| Term occurrences scored | 59 |

Each utterance is one or two sentences written the way a tech, SE, or customer would say it, with numbers written as spoken words ("port twelve"). Each lists the jargon terms it contains.

**Term aliases were fixed before any provider was run and will not be edited based on results.** An alias is another correct way to write the same term (`PoE` / `P o E` / `power over ethernet`), never a likely mishearing. Matching is whole-word, so "poem" does not count as "PoE". The dry-run check enforces that every term spoken in a reference is listed for it, so nothing is silently left out of the score.

### Audio sources (to be recorded)

Each source is reported separately and never averaged together.

| Source | How | Count |
|---|---|---|
| `human` | Ky's own voice, recorded on a phone or headset. **The headline uses only this source.** | not recorded yet |
| `tts` | ElevenLabs voices | not generated yet |
| `noisy` | `human` audio mixed with a documented background-noise file at a fixed SNR | not made yet |

**TTS bias caveat:** all TTS audio is generated with ElevenLabs voices. Audio from one vendor's TTS can score unusually well on the same vendor's speech-to-text, so `tts` results are labeled "ElevenLabs-generated" and are never used for the headline.

## Providers and conditions

Models, settings, and prices are pinned in [`config.json`](config.json) and copied into every result file. They were checked against each vendor's docs on 2026-10-03 (links are in the config).

| | Deepgram | ElevenLabs |
|---|---|---|
| Endpoint | `POST /v1/listen` (pre-recorded) | `POST /v1/speech-to-text` (batch) |
| Model | `nova-3` | `scribe_v2` |
| Baseline settings | English, `smart_format` on | English, audio-event tags off, no diarization |
| Boosted | adds one `keyterm` per term | adds one `keyterms` field per term |
| List price, baseline | $0.0043/min (Pay As You Go) | $0.22/hour |
| Boosting surcharge | +$0.0013/min | +$0.05/hour |

Prices as of 2026-10-03, from [deepgram.com/pricing](https://deepgram.com/pricing) and [elevenlabs.io/pricing/api](https://elevenlabs.io/pricing/api). They are used only for estimated cost; actual billing depends on the account's plan. ElevenLabs' API reference describes the keyterm surcharge as 20% of the base cost, while its pricing page lists $0.05/hour; this uses the pricing page.

**Baseline** uses each provider's default recognition with English pinned. **Boosted** changes only one thing: the 44 canonical names from `terms.json` are sent as the provider's keyterms, the same list for every utterance.

Each request is retried up to 2 times on rate limits (429), server errors (5xx), or network errors, with backoff; anything still failing is recorded as a failure.

## How it's scored

All scoring is in [`score.js`](score.js), and every rule below has a unit test in [`test/score.test.js`](test/score.test.js).

- **Normalization:** lowercase, punctuation removed, hyphens split words ("J-hook" becomes "j hook"). Digits in transcripts become spoken words ("port 12" becomes "port twelve", "Cat6" becomes "cat six", "2nd" becomes "second"), to match references, which are written as spoken.
- **Jargon term accuracy (the headline):** every occurrence of a term in a reference counts. Aliases count, whole words only. If a reference says a term twice and the transcript has it once, that's 1 of 2.
- **WER:** word error rate against the exact reference wording, counted over the whole set (total word errors / total reference words), not averaged per utterance. Aliases don't apply here, so "power over ethernet" in place of "PoE" is a word error even though the term is correct.
- **Misses:** for every missed term, the scorer records what the provider wrote in its place. For example, if a transcript had "Burke Otto" where "Verkada" was said, the miss would show "burke otto". (That example is from the tests, not a real result.)
- **Latency:** median and 95th percentile (nearest rank) over successful requests.
- **Failures:** counted in the failure rate and listed, never dropped. Failed requests aren't scored for accuracy; the summary shows how many requests were scored. Utterances with no result are listed as missing, and transcripts that change between repeat runs are flagged.

## How to reproduce

Requires Node 20 or later (no packages to install) and [ffmpeg](https://ffmpeg.org/) for audio conversion.

```bash
cd bench
npm test                       # unit tests (no keys, no network)
npm run dry-run                # validates the dataset; makes no API calls
node scripts/prepare-audio.js  # converts recordings/human/* to mono 16 kHz WAV (see RECORDING.md)

# Prints the plan and estimated cost; makes no API calls:
node run.js --providers deepgram,elevenlabs --sources human --conditions baseline,boosted
# Runs it, then scores it into results/<run-id>/summary.json:
node run.js --providers deepgram,elevenlabs --sources human --conditions baseline,boosted --confirm

node score.js --run <run-id>   # re-scores an existing run
```

Provider keys go in `bench/.env` (copy [`.env.example`](.env.example)); that file is git-ignored. A paid run refuses to start unless `budget.max_usd_per_run` is set in `config.json`, the estimate is under it, and `--confirm` is given; it also stops before any request that would pass the cap. Requests run one at a time, so latency isn't distorted by the bench's own concurrency.

Each run writes `results/<run-id>/config.snapshot.json` (models, settings, prices, keyterms, git commit, and SHA-256 hashes of the dataset files), one raw file per utterance under `raw/<provider>/<condition>/<source>/`, and `summary.json`. Raw files and audio are git-ignored; summaries are committed.

## Limitations (known in advance)

- Small sample: 45 utterances.
- One human speaker (Ky), one noise profile.
- Batch (prerecorded) transcription only; no streaming.
- Models, settings, and prices are as of the run date recorded in each result file.

## Results

None yet. No provider has been run.
