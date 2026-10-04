# Jargon Bench

**How well do speech-to-text providers hear physical-security vocabulary, and how much does vocabulary boosting help?**

Field techs, sales engineers, and customers say things like "the Verkada cameras dropped off the PoE switch in the IDF." General-purpose speech-to-text often mangles those words, and in a voice agent like NightAgent's Sam, a misheard brand or part name becomes a wrong ticket. Jargon Bench measures that on a fixed dataset, for Deepgram and ElevenLabs, with and without each provider's vocabulary-boosting feature.

**The claim is narrow on purpose:** results apply to this dataset, these audio conditions, and the models and prices on the run date. This is not a general speech-to-text leaderboard.

> **Status: in progress (build step 1 of 8).** The dataset and its validation are done. No provider has been run yet, so there are no results. Every number that appears here later will come from a raw result file in `bench/results/`.

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

## How to reproduce

Requires Node 20 or later. No packages to install so far.

```bash
cd bench
npm test             # unit tests (no keys, no network)
npm run dry-run      # validates the dataset; makes no API calls
```

Provider keys go in `bench/.env` (copy [`.env.example`](.env.example)); that file is git-ignored. Keys are only needed once provider runs exist (build step 3). Paid runs will print the request count and audio minutes and require `--confirm` before calling any API.

## Limitations (known in advance)

- Small sample: 45 utterances.
- One human speaker (Ky), one noise profile.
- Batch (prerecorded) transcription only; no streaming.
- Models, settings, and prices are as of the run date recorded in each result file.

## Results

None yet. No provider has been run.
