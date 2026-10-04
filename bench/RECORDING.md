# Recording the human audio

The `human` source is the headline, so it's worth ten careful minutes. Record only your own voice (or people who agreed).

1. **Get the lines.** In `bench/`, run `node scripts/reading-list.js`. Each line starts with its file name (`u001` ...).
2. **Record.** One file per line, on your phone's voice memo app or a headset. Aim for at least 25 lines; all 45 is better.
   - Read each line once, the way you'd say it on a call: normal speed, no extra-careful pronunciation of the jargon.
   - Same room, same device, same distance for every file. A quiet room (the `noisy` source adds noise later, on purpose).
   - If you stumble, re-record that file. Don't edit the words.
3. **Name each file by its id**: `u001.m4a`, `u002.m4a`, ... Any format is fine (m4a, mp3, wav, webm).
4. **Copy them into `bench/recordings/human/`.** That folder is git-ignored.
5. **Convert:** `node scripts/prepare-audio.js`. It writes mono 16 kHz WAV files into `bench/data/audio/human/` and lists anything missing or suspiciously short or long.

Note the device you used (for example "iPhone voice memo, quiet office"); it goes in the README.
