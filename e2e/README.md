# Browser test scripts

Automated checks written while building NightAgent. Each script drives headless Chrome with
[puppeteer-core](https://pptr.dev) and prints PASS/FAIL (or ok/FAIL) lines. They are not part of
the app and are never published.

**Setup (once):** `npm install --no-save puppeteer-core` in this folder. The scripts launch
Chrome from `C:/Program Files/Google/Chrome/Application/chrome.exe`; change that path on
other machines.

**Running:** `node <script>.js`. Most expect the local server: `TOOL_SECRET=local-test .venv/Scripts/python.exe -m uvicorn main:app --port 8765`. Many replace the ElevenLabs SDK with a stand-in so no real call is made (the stand-in session must return `undefined` for `then`).

Scripts with "live" in the name talk to the deployed site (and may create real data or use paid
services); the rest use a local server or emulator. Screenshot scripts write PNGs next to
themselves.
