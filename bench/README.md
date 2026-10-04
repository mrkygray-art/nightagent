# Jargon Bench

**How well do speech-to-text providers hear physical-security vocabulary, and how much does vocabulary boosting help?**

Field techs, sales engineers, and customers say things like "the Verkada cameras dropped off the PoE switch in the IDF." General-purpose speech-to-text often mangles those words, and in a voice agent like NightAgent's Sam, a misheard brand or part name becomes a wrong ticket. Jargon Bench measures that on a fixed dataset, for Deepgram and ElevenLabs, with and without each provider's vocabulary-boosting feature.

**The claim is narrow on purpose:** results apply to this dataset, these audio conditions, and the models and prices on the run date. This is not a general speech-to-text leaderboard.

> **Status: in progress (build step 6 of 8).** Human, noisy, and TTS runs are done (results below). Still to do: the scorecard page and one-page readout, CI, and the portfolio section. Every number here comes from a `summary.json` in `bench/results/`.

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

### Reference corrections (after the first run)

After the first baseline run (`2026-10-04T02-20-47-223Z`), Ky listened to every clip where both providers, on every repeat, disagreed with the reference on an ordinary word. Five references were changed to match what was actually said (u020, u027, u029, u034, u042). For example, the script said "interior hallways" but the recording says "exterior hallways". Six clips were left unchanged because the recording matched the script (u011, u012, u035, u039, u043, u044), so those misses still count, including the muffled "swap" in u012. No jargon term or alias was changed, so jargon accuracy was unaffected; WER went down slightly for both providers. Every change is listed in [`data/reference-corrections.json`](data/reference-corrections.json). That run's original scores are kept in its `summary.original-references.json`, and each `summary.json` records the dataset hash it was scored against.

### Audio sources (to be recorded)

Each source is reported separately and never averaged together.

| Source | How | Count |
|---|---|---|
| `human` | Ky's own voice, Windows Sound Recorder, uncompressed WAV, one sitting, same mic and room. **The headline uses only this source.** | 44 of 45 (u037 not recorded) |
| `tts` | ElevenLabs voices Roger, Jessica, and Charlie (premade), `eleven_multilingual_v2`, rotated by line; logged in [`data/tts-manifest.json`](data/tts-manifest.json) | 45 of 45 |
| `noisy` | `human` audio mixed with seeded synthetic pink noise (steady, HVAC-like hiss) at 10 dB SNR per clip; regenerates byte-identically; logged in [`data/noisy-manifest.json`](data/noisy-manifest.json) | 44 of 45 |

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
- **Inserted terms:** any term the transcript contains more often than the reference (a false positive, the known risk of vocabulary boosting) is counted separately, since term accuracy only checks terms that were said.
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
- One human speaker (Ky), recorded in one sitting on one device; u037 has no human recording.
- One noise profile: steady synthetic pink noise at 10 dB SNR. Real job sites add speech, tools, and alarms, which are usually harder.
- TTS clips come only from ElevenLabs voices, so they can favor ElevenLabs speech-to-text.
- Noisy and TTS clips were each sent once (human clips three times).
- Batch (prerecorded) transcription only; no streaming.
- Models, settings, and prices are as of the run date recorded in each result file.

## Results

**Snapshot: human audio only, runs of 2026-10-04 (UTC).** 44 clips (u037 not recorded), each sent 3 times per provider and condition, so each cell below covers 132 requests and 174 jargon-term occurrences (58 x 3). Baseline run [`2026-10-04T02-20-47-223Z`](results/2026-10-04T02-20-47-223Z/summary.json), boosted run [`2026-10-04T02-40-00-605Z`](results/2026-10-04T02-40-00-605Z/summary.json); both scored against the same dataset version (after the reference corrections above).

**Jargon term accuracy (the headline)**

| Provider (model) | Baseline | Boosted |
|---|---|---|
| Deepgram (`nova-3`) | 108 of 174 (62.1%) | **156 of 174 (89.7%)** |
| ElevenLabs (`scribe_v2`) | 138 of 174 (79.3%) | **166 of 174 (95.4%)** |

**Everything else**

| | Deepgram baseline | Deepgram boosted | ElevenLabs baseline | ElevenLabs boosted |
|---|---|---|---|---|
| Word error rate | 11.7% | 8.6% | 5.8% | 3.5% |
| Median latency | 119 ms | 128 ms | 451 ms | 472 ms |
| p95 latency | 598 ms | 597 ms | 711 ms | 703 ms |
| Failed requests | 0 of 132 | 0 of 132 | 0 of 132 | 0 of 132 |
| Clips whose transcript changed between repeats | 0 of 44 | 0 of 44 | 5 of 44 | 3 of 44 |
| Terms written where they weren't said | 0 | 3 (1 clip x 3) | 0 | 3 (1 clip x 3) |
| Est. cost per audio hour (list price, 2026-10-03) | $0.26 | $0.34 | $0.22 | $0.27 |

Latency is measured from a home internet connection and includes uploading the clip.

**What boosting fixed, what it didn't, and what it broke**

- **Deepgram** now gets every occurrence of NVR, WDR, varifocal, ONVIF, Avigilon, electric strike, Verkada, Hanwha, Genetec, Lenel, and Brivo (all missed at baseline) and of VMS and IDF (half right at baseline). Still missed when boosted: Wiegand ("the weekend"), Axis ("access"), fail safe ("failed safe"), Aiphone, glass break, and PoE in one clip (6 of 9).
- **ElevenLabs** fixed Avigilon, fail safe, electric strike, Wiegand, Axis, Hanwha, Genetec, Lenel, Brivo, and PoE in one more repeat (7 of 9). Still missed when boosted: Aiphone and glass break.
- **No term got worse with boosting, but each provider produced one false positive**, on all 3 repeats: Deepgram wrote "access control panels" as "**Axis** Control Panel" (u036), and ElevenLabs wrote "supervision" as "**supervisory**" (u013). Term accuracy can't see these (it only checks terms that were said), so the scorer counts them separately (`insertedTerms` in `summary.json`).

With one speaker and 44 clips, treat these as directional, not definitive.

### Other audio sources (1 run each, never averaged with the human results)

Noisy run [`2026-10-04T02-52-00-161Z`](results/2026-10-04T02-52-00-161Z/summary.json) (44 clips, 58 term occurrences) and TTS run [`2026-10-04T02-53-18-454Z`](results/2026-10-04T02-53-18-454Z/summary.json) (45 clips, 59 term occurrences). Each clip was sent once, so these can't show run-to-run variation, and one term is worth about 1.7 points.

| Jargon terms correct | Human (from above) | Noisy, 10 dB SNR | TTS (ElevenLabs-generated) |
|---|---|---|---|
| Deepgram baseline | 62.1% | 27 of 58 (46.6%) | 49 of 59 (83.1%) |
| Deepgram boosted | 89.7% | 50 of 58 (86.2%) | 58 of 59 (98.3%) |
| ElevenLabs baseline | 79.3% | 44 of 58 (75.9%) | 57 of 59 (96.6%) |
| ElevenLabs boosted | 95.4% | 56 of 58 (96.6%) | 59 of 59 (100%) |

| Word error rate | Human | Noisy | TTS |
|---|---|---|---|
| Deepgram baseline / boosted | 11.7% / 8.6% | 17.7% / 13.7% | 3.1% / 0.7% |
| ElevenLabs baseline / boosted | 5.8% / 3.5% | 9.1% / 5.5% | 0.7% / 0.4% |

- **Noise hurt both baselines, and boosting recovered most of it.** Deepgram's baseline fell the most (to 46.6%). Boosted, both providers landed close to their human results. Failed requests: 0 of 176.
- **TTS audio made every condition look better than real speech**, and ElevenLabs' own voices gave ElevenLabs its only perfect score. That is the bias this source exists to show, which is why the headline uses human audio only. Failed requests: 0 of 180.
- **Boosting false positives showed up again in noise:** both providers turned "access point" into "Axis" (u023), and ElevenLabs again wrote "supervisory" for "supervision" (u013). No TTS false positives.
- **A scoring edge case:** in TTS, Deepgram (boosted) wrote "backdoor contact" for "back door contact" (u038). Because terms match as whole words and aliases are frozen, that counts as a miss of "door contact" even though the meaning is right.
