# Setup

The procedure Claude Code follows when it walks someone through this. Look at the
environment first and **ask the user which way to go before running anything**
(do not install everything on your own).

**Most of the time there is nothing to install.** The default is Chrome's Web Speech
API, and `pip install numpy aiohttp` is enough to run it. No model to load, nothing
to wait for. The catch is that **the audio is sent to Google's servers to be
recognized**.

What follows is for when you want everything to stay on your machine, or when you
want to use it without opening the window.

## 1. Look at the environment

```bash
uname -s -m
sw_vers -productVersion 2>/dev/null      # on macOS
```

| Environment | Which section |
|---|---|
| Just trying it out, or a weak machine | **Nothing to install** (the default browser recognition) |
| macOS 26 or later | **A**. The recognition that ships with the OS, no model to download |
| Anything else, or you want it strong on proper nouns | **B**. Run Whisper on your own machine |

With A and B the audio never leaves the machine. **Those two are the only ways to
run it locally.**

## A. macOS 26 or later (the recognition that ships with the OS)

Uses `SpeechAnalyzer` and `SpeechTranscriber` (`engine_apple.py`).
Runs with `--engine apple`.

```bash
cd <this repository>
python3 -m venv .venv                    # Python 3.10 to 3.13
.venv/bin/pip install -U numpy aiohttp soxr sounddevice
```

The Swift helper (`speech_helper.swift`) is built automatically on the first run,
so Xcode or the Command Line Tools have to be there.

```bash
xcode-select --install                   # if you do not have them
swiftc --version                         # check that the macOS 26 SDK is visible
```

The OS pulls down the speech model for the language by itself on the first run
(tens of seconds). It stays on the machine after that, so there is no wait.

The memory is held by the OS, not by us. Startup is under a second, and a 3.5 second
utterance takes about 0.1 seconds to recognize (measured on Apple Silicon).

**macOS 25 and earlier have no `SpeechTranscriber`.** Go to B in that case.

## B. Whisper (faster-whisper)

Runs with `--engine whisper` (`whisper_engine.py`). Inside it is
[faster-whisper](https://github.com/SYSTRAN/faster-whisper), the CTranslate2 build
of Whisper, which runs on any OS.

```bash
cd <this repository>
python3 -m venv .venv                    # Python 3.10 to 3.13
.venv/bin/pip install -U faster-whisper aiohttp soxr numpy sounddevice
```

If `nvidia-smi` shows an NVIDIA GPU on the machine, the defaults are fine as they are.

```bash
voice-shell.sh whisper
```

With only a CPU, shrink the model and say where you want to give up accuracy.

```bash
voice-shell.sh whisper --model base --whisper-device cpu --whisper-compute int8
```

The model comes down from Hugging Face on the first run (tens of MB up to about
100MB for `base`). `--whisper-compute` is the trade between accuracy and speed, so
use `int8` on a CPU and `float16` on a GPU.

### Which model to use

The default is `large-v3-turbo`. It is **far too heavy on a CPU with no GPU**, and
on a 4 core CPU the measured result was that `base` is the practical one (RTF about
0.15). `small` is a bit heavy at RTF about 0.76.

`--model` takes a Hugging Face name as well as the path of a folder on your machine.
If you have a model tuned for your language, hand it over as it is.

```bash
voice-shell.sh whisper --model kotoba-tech/kotoba-whisper-v2.0
voice-shell.sh whisper --model /path/to/my-model
```

A model you hand over once is remembered, so `start` is enough after that
(`~/.config/voice-shell/config.json`). Pass `--model ""` to go back to the default.

Only the model is remembered. `--whisper-device` and `--whisper-compute` are not,
so pass them every time if you are on a CPU.

Compared with Apple's on-device recognition, Whisper is stronger on proper nouns
and holds up better in a noisy room or with several voices. In exchange it starts
slower and uses the memory the model needs.

## Common to both

`voice-shell.sh` finds the `.venv` at the root of the repository by itself, so there
is no need to set `VOICE_SHELL_PYTHON`.

`sounddevice` in the pip line above is what records on macOS and Windows, and it
arrives as a ready built wheel, so there is nothing else to install there.

Linux records through `arecord`, which is a separate program.

```bash
sudo apt install alsa-utils      # Linux
```

On macOS a dialog asks the terminal for mic permission on the first run, so have
the user allow it. The recognition itself never touches the mic, so nothing else
has to be allowed.

## 2. Make the skill visible

```bash
ln -s "$(pwd)/skills/voice-shell" ~/.claude/skills/voice-shell
```

Not needed if it went in with `npx skills add ykuwai/voice-shell`.

## 3. Run it

```bash
${CLAUDE_SKILL_DIR}/scripts/voice-shell.sh start
${CLAUDE_SKILL_DIR}/scripts/voice-shell.sh wait-ready
```

Once `READY` shows up, have the user open http://127.0.0.1:8090 and talk.

## When you get stuck

| Symptom | What to do |
|---|---|
| `No Python it can run was found` | `export VOICE_SHELL_PYTHON=/path/to/.venv/bin/python` |
| Nothing here can record | `pip install sounddevice`. On Linux `sudo apt install alsa-utils` |
| Startup says `FAILED` | Look at `voice-shell.sh status` and the tail of `daemon.out` |
| Whisper is slow | Shrink the model (`--model base`). On a CPU add `--whisper-compute int8` |
| You talk and nothing arrives | The trigger level is too high. Lower the mark under the mic in the viewer until the bar crosses it when you speak |
| Noises send things on their own | The trigger level is too low. Raise that same mark until only your voice gets past it |
| You want a different mic | Pick it in the viewer, or pass its name to `--device`. On Linux `--device` takes the `-D` of `arecord` (`arecord -L` lists them) |
