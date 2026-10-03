# Evaluation Lab: scope

Turn the Agent QA Lab (`/lab`) into one page that shows **how well the agents do, measured honestly**, and the
loop behind it: **test → failure → cause → fix → retest**.

This extends what exists. It is not a new dashboard.

## What already exists (don't rebuild)

| Piece | Where | What it gives us |
|---|---|---|
| 12 regression tests, 3 agents, run x3 | `app/qa_lab.py`, ElevenLabs Agent Testing | Pass/fail per test, an example reply, and the judge's reason |
| Call check (9 checks per real call) | `app/evaluation.py`, cached in `ns_calls.evaluation` | Customer identified, confirmed first (AI-judged), location, emergency, priority, unsupported promises (AI-judged), escalation needed/performed, follow-up |
| Turn-by-turn timing | `evaluation.turn_trace()` | `convai_llm_service_ttfb`, `convai_tts_service_ttfb`, `convai_ttf_audio_since_silence`, ASR latency, tool latency |
| Tool log | `ns_tool_calls` (with `duration_ms`) | Every tool call on real calls |
| Failure injection | `app/injection.py`, `/api/lab/inject/*` | Duplicate caller, alerts down |
| Impact counts | `ns_impact()` | `calls_without_ticket`, `specialist_calls`, etc. |

## Rules

1. **Nothing made up.** Every number comes from a test run or a recorded call. Every fix-log entry is something that really happened.
2. **Show the sample size next to every number** ("92% · 13 calls"). The numbers are small, so say so.
3. **Tests and real calls stay separate.** Tests are controlled; real calls are messy. Don't blend them into one score.
4. **AI-judged results are labeled AI-judged**, as on the call check today.
5. **Say what isn't measured.** A "Not measured yet" box lists it, with the reason.
6. **No caller words on the page**, same as Engineering Mode. Only counts and the agent's side.

## E1: Scorecard

A row of metric tiles at the top of `/lab`, in two groups.

**In tests** (from `qa_lab.lab_results()`):

| Metric | Definition |
|---|---|
| Test pass rate | Passed runs / finished runs (already computed) |
| Intent accuracy | Tool-check tests whose expected `category` / priority matched / tool-check tests that set one. Needs an `expects` field in `TESTS` (e.g. `{"category": "cannot_secure_site", "priority": "emergency"}`) |

**On real calls** (from `ns_calls.evaluation` + `ns_tool_calls` + ElevenLabs conversation data):

| Metric | Definition | Source |
|---|---|---|
| Escalation accuracy | "Escalation performed" pass / (pass + fail) | `evaluation` items |
| Priority matched the rules | "Set the correct ticket priority" pass / (pass + fail) | `evaluation` items |
| Transfer success | Calls that needed a specialist and reached one / calls that needed one | `evaluation` items (hand-off rows) |
| Tool-call success | Tool calls with no error / all tool calls | `ns_tool_calls` (confirm the error/outcome field in E1) |
| Avoided unsupported promises *(AI-judged)* | Pass / graded | `no_unsupported_promises` |
| Confirmed details first *(AI-judged)* | Pass / graded | `confirmed_details_first` |
| Conversation completion | Calls that ended with a ticket, message, or lead / all calls | tickets + `ns_routing_tasks` + `ns_tool_calls` |
| Response time | Median and slowest-10% of `convai_ttf_audio_since_silence` (caller stops talking → agent audio starts) | ElevenLabs turn metrics |
| Cost per conversation | Median dollars per call (credits × plan rate, rate shown). **Only if** the ElevenLabs conversation record has a cost field; check first, otherwise leave it out | ElevenLabs conversation metadata |

**Build notes**
- New `app/scorecard.py` with pure functions over rows, so it's unit-testable without network calls.
- Response time and cost need the conversation record from ElevenLabs. Save them once the grade is final, in the same step that caches the grade (new `ns_calls.timing jsonb`, migration `2026xxxx_call_timing.sql`). Never fetch them per page view.
- Only count real conversations: skip `scenario` tickets and sandbox/injection runs, the same way the duplicate check does.
- `/api/lab` gains `scorecard: {tests: {...}, calls: {...}}`, each metric shaped as `{value, n, definition}`.
- Cache like `lab_results()` (60 s).

**Done when** the tiles show live numbers with sample sizes, and `tests/test_scorecard.py` covers the math (including n = 0 → "No data yet", not 0%).

## E2: Fixes log

A "What broke and how it was fixed" section. One card per real failure:

```
FIX-03  Sam skipped the read-back when the caller gave everything up front
Found in:   live call (NS-xxxx)
Cause:      Instruction following: the prompt rule alone wasn't reliable
Fix:        The lookup tool's next_step now forces the read-back with an exact sentence
Retest:     QA-01 3/3 · QA-02 3/3 (live, last run Oct 3) · NS-2431 call check 100%
```

**Data:** `app/fix_log.py`, a list of dicts (`id, date, title, found_in, cause, fix, tests[], calls[]`), written by hand.
**The retest line is live.** It reads the current results for the linked tests from `lab_results()`. If a fixed test starts failing again, the card shows it.

**Cause categories** (a short fixed list, so they can be counted later): Intent / priority, Instruction following, Tool contract, Bad data from the model, Persona / voice, Server logic.

**Seed entries.** These are all real; take dates, ticket numbers, and commits from git log and the call records, not from memory:
1. Gate stuck open suggested at medium → emergency (QA-03)
2. Billing line left out / wrongly added (QA-04, QA-05)
3. Read-back skipped when the caller gave everything up front → forced via lookup `next_step` (QA-01, QA-02, NS-2431)
4. Prompt-only rules unreliable with the model → steer through tool results (NS-1504, NS-5975, NS-8906)
5. Jordan spoke in the third person (QA-08)
6. Riley filled in "not specified" → server drops placeholders (QA-12)
7. Supervisor complaint hid the repair (QA-07)
8. Second report opened a duplicate ticket and re-alerted (injection, QA-09, QA-10)
9. Alert service down (injection, paging-down)

**Done when** the section renders 6–9 cards with live retest results, and each card links to its test row on the same page.

## E3: New edge-case tests

Add three or four ElevenLabs tests aimed at ambiguity, where the agent is most likely to fail. (Off-topic is already QA-06.)

| Test | Expected |
|---|---|
| QA-13 "My cat keeps staring at the electrical panel" | Asks what's wrong; no emergency ticket |
| QA-14 "The panel is buzzing and smells like burning" | Emergency (the counterpart to QA-13, so we know the agent isn't just refusing everything) |
| QA-15 Caller won't give a name | Still gets enough to help (callback number, site), no made-up name in `create_ticket` |
| QA-16 Caller changes topic mid-call (repair → billing) | Repair ticket first, then billing hand-off/message |

Run each x3 (about 27–37 credits per full run). **If a new test fails, that's a real FIX entry for E2.** Don't tune the test until it passes.
Back them up with the existing ElevenLabs backup script and add them to `qa_lab.TESTS` with `why` text.

## Not measured yet (shown on the page)

| Metric | Why not |
|---|---|
| Interruption handling | ElevenLabs tests are text-only; barge-in needs real audio |
| Silence handling | Same: needs a voice call with deliberate silence |
| Speech-to-text confidence | ElevenLabs doesn't give us a confidence score for each turn |
| Hallucination rate (in general) | We measure one specific thing, unsupported promises, and call it that |

*Optional later (E4):* scripted voice calls through the real demo page with Puppeteer and a fake mic playing a WAV file (silence, talking over Sam). Treat this as research; it may be too flaky to publish.

## Page layout (top to bottom)

1. Heading + one-line intro
2. Scorecard: "In tests" tiles, then "On real calls" tiles, each with n and a short definition
3. What broke and how it was fixed (E2)
4. The tests (existing list, plus the expected intent where set)
5. Failure injection (existing)
6. Not measured yet

Plain words throughout, matching the rest of the app. Engineering detail (metric names, sources) goes in a small "How it's measured" note under each tile.

## Testing

- `tests/test_scorecard.py`: metric math, n = 0, excluding scenario/sandbox calls
- `tests/test_fix_log.py`: every entry's test ids exist in `TESTS`, and the cause is in the fixed list
- `e2e/`: update the lab page check (tiles render, fixes link to tests, no caller words on the page)
- Live: `/api/lab` returns a scorecard on production before the README and portfolio are updated

## Decisions (2026-10-03)

1. **Rename** "Agent QA Lab" → **"Evaluation Lab"** everywhere it's shown (page title, heading, README, portfolio). The URL stays `/lab`.
2. **Cost is shown in dollars.** Converted from credits with a `USD_PER_1K_CREDITS` setting taken from the ElevenLabs plan, and the page states the rate used ("at $X per 1,000 credits, Creator plan"). If the plan rate isn't known, show credits until it is.
3. **Order: E3 → E1 → E2.** New tests first, so the Fixes log can open with a fresh failure if one turns up.
