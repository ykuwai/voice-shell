# README screenshots

`make_screenshots.py` regenerates the viewer screenshots used by the READMEs,
in every UI language, from the code as it is right now. Run it again
whenever the viewer's look changes.

```sh
# Windows (Git Bash)
.venv/Scripts/python.exe docs/readme/tools/make_screenshots.py
# macOS / Linux
.venv/bin/python docs/readme/tools/make_screenshots.py
```

It writes one PNG per language into `docs/readme/images/`, `screen-<lang>.png`,
at 380x640 CSS pixels and twice that in real pixels, dark theme: Instant mode,
two listening sessions with the first one chosen, text being recognized in the
Unsent card, and three sent cards (one of them marked as edited).

Options: `--lang ja` (repeatable) to do only some languages, `--out DIR` to
write somewhere else, `--keep-temp` to keep the temp folder (state, config and
`viewer.log`) for a look afterwards. The sample sentences live in `SAMPLES` at
the top of the script.

## Requirements

- The repo's `.venv`, the same one the viewer runs on. The DevTools connection
  uses aiohttp, which the viewer already needs, so there is nothing extra to
  install.
- Google Chrome (Chromium or Edge also work). It is looked for in the usual
  places on Windows, macOS and Linux. Set `CHROME_PATH` to point at a
  different one.

## What it does, and does not touch

Everything runs in a temp folder of its own and is removed at the end, error
or not:

- Its own viewer (`skills/voice-shell/scripts/viewer.py`) on a free port,
  never 47865. `VOICE_SHELL_STATE_DIR`, `XDG_CONFIG_HOME` and the home
  directory all point into the temp folder, so a voice-shell you are using at
  the same time, its state in `/tmp/voice-shell` and your settings in
  `~/.config/voice-shell`, are neither read nor changed.
- A few do-nothing Python processes. The viewer only shows a session whose
  PID is alive, so each sample chip is registered under one of these.
- A headless Chrome with a throwaway profile, driven over the DevTools
  protocol.

## What is staged rather than real

- Browser speech recognition is removed from the page before it loads.
  Headless Chrome has no microphone, and the page would otherwise sit muted
  waiting for a first click and then report the mic as denied. Without it the
  viewer takes its existing path for browsers that cannot recognize speech and
  shows what the server reports.
- The recognition engine is reported as running by pointing the viewer's
  `daemon.pid` at one of the do-nothing processes. Nothing is listening.
- The text being recognized is written to `partial.txt`, which the viewer
  shows exactly as it shows a real partial result.
- The level meter is therefore flat.
- The "Keep this window on top" bubble, which an ordinary tab shows on every
  load, is put away before each shot, as a click elsewhere would.
