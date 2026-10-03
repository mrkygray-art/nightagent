# CLAUDE.md

Guidance for Claude Code in this repository.

## What this is

NightAgent: an after-hours AI voice agent demo for a security integrator. Four ElevenLabs agents (Sam front desk, Jordan billing, Riley sales, and the follow-up call) call tools on a Python FastAPI backend (`main.py`, `app/`) that keeps tickets, history, and routing rules in Supabase. Public pages: `/demo` (the call and ticket board) and `/lab` (the Evaluation Lab: scorecard, regression tests, fixes log, failure injection). The README is the full tour.

## Commands

- Tests: `.venv/Scripts/python -m pytest -q` (in-memory store, no keys needed)
- Local server: `TOOL_SECRET=local-test .venv/Scripts/python -m uvicorn main:app --port 8765`
- Deploy: the Vercel project is connected to GitHub (since 2026-10-03), so a push to `main` deploys to production. Run the tests before pushing. A manual deploy is `npx vercel deploy --prod --yes` (on the user's Windows PowerShell use `npx.cmd`, because `npx.ps1` is blocked). `.vercelignore` allowlists what is uploaded.
- Back up the ElevenLabs setup: `.venv/Scripts/python scripts/export_elevenlabs.py` (needs an ElevenLabs key with ElevenAgents Read; secrets are redacted into `elevenlabs/`).
- Browser test scripts: `e2e/` (see `e2e/README.md`).
- Voice tests (real audio, real calls to the live Sam, uses call minutes and counts toward Sam's 40-calls-a-day limit): `cd voicelab && npm install && node run.js` (about 24 calls; `--only numbers|interruption|silence`, `--conditions clean,phone`, `--callers maria`). Then `.venv/Scripts/python scripts/save_voice_lab.py voicelab/out/run-<n>.json` writes `app/voice_lab.json`, which `/lab` reads. The test caller connects with the site's Origin header (the agent allowlists origins). Caller clips are ElevenLabs TTS in `voicelab/clips/`.
- Voice-test calls run Sam's real tools (account lookups land in `ns_tool_calls`). Their conversation ids live in `app/voice_lab.json` and are left out of the calls list, scorecard, and Business Impact via `voice_lab.is_test()`; add any new view of real calls to that filter.

## Things to know

- Steer the model through tool results (`next_step`, `tell_the_caller`) rather than the prompt alone; that has proven more reliable with this model.
- Business rules live in code (`app/triage.py`, `app/follow_up.py`, `app/lifecycle.py`); the model may raise a priority but never downgrade an emergency.
- New Evaluation Lab tests: add the ElevenLabs test to `qa_lab.TESTS` with its `why`, and real fixes to `app/fix_log.py` (only things that really happened, with the commit or prompt that changed).
- Public pages never show real callers' words, full phone numbers, or the tool secret. (The voice tests show what the speech-to-text heard from their own recorded test lines, which use the fictional demo accounts.)

## Keeping the public README current

This repo is public (github.com/mrkygray-art/nightagent), and `README.md` is what recruiters and hiring engineers read. When a change is something a user would notice or changes how the system works (an agent, a tool, a rule, a test, a scorecard metric, a limit, a command), update `README.md` in the same commit, and check that "The Agents", "Evaluation Lab" (test table, fixes, "Not measured yet"), "Safety, Privacy, and Limits", and "Run It Locally" still match the code.

- Every claim must be true to the code. Don't write numbers that drift (test counts, live metrics); leave them out, link to `/lab`, or date them as a snapshot.
- Never put keys, the tool secret, real customer data, or personal contact details in the README.
- The same project is described in two other places. If the summary changed, tell the user they may need updating (don't edit them unasked): the NightAgent section of the GitHub profile README (repo `mrkygray-art/mrkygray-art`) and, in `~/projects/ky-gray-portfolio`, the `#nightagent` case study in `index.html` plus the Ask Ky entries `[proj-nightagent*]` in `api/_askky-knowledge.js`.
