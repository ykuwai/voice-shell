# Voice Shell

English · [日本語](docs/readme/README.ja.md) · [Español](docs/readme/README.es.md) · [Français](docs/readme/README.fr.md) · [Deutsch](docs/readme/README.de.md) · [简体中文](docs/readme/README.zh.md) · [한국어](docs/readme/README.ko.md)

An Agent Skill for giving Claude Code instructions with your voice. No keyboard.
You talk and the instruction goes through.

> mic → speech recognition → one line of JSONL → Monitor → Claude Code

Say whatever comes to mind while you work and it arrives without you pressing Enter.
It works with Claude Code and with other agents such as Codex.

## Install

```bash
npx skills add ykuwai/voice-shell
pip install numpy aiohttp "sounddevice>=0.5.6"
```

If you have Chrome, that is all it takes. **No model to download, nothing to wait for.**

## Use

Type `/voice-shell` in Claude Code, or say "voice mode". After that you just talk.
Say "stop voice mode" to stop.

A window of its own opens at http://127.0.0.1:47865 and the words it hears grow
there as you speak. Float it in front and you can watch it while you work on
something else.

Set `VOICE_SHELL_PORT` before starting it to choose another port. Setting
`VOICE_SHELL_PORT=8090` keeps the previous address.

| How it sends | What happens |
|---|---|
| Live | What you say goes straight through |
| Hold | It piles up, so you can fix it before sending |
| Paused | Nothing you say while paused is kept anywhere |

Even with your hands full, **you can switch by voice alone.** "Mute" and "unmute"
turn the mic off and on, "hold" and "live" change how it sends. End a sentence with
"cancel that" and that one utterance is dropped instead of sent. (Only with browser
recognition, muting lets go of the audio itself, so turn the mic back on from the
window.)

You can leave a voice mode running for each piece of work and **pick which one
gets your words from the window.** Your voice picks too ("session 2").

Proper nouns that get misheard can go in a dictionary (`cloud code → Claude Code`).
Replacements you register also hit the words while they are still being recognized.

## Where your voice goes

**The default is browser recognition, so the audio is sent to Google's servers.**
When you want it to stay on your machine, pick another way from the settings in
the window. The same warning is written there on the spot.

| Way | What it needs | Where the audio goes |
|---|---|---|
| **This browser** (default) | Chrome. Works only while the window is open | **Google's servers** |
| Apple on-device | macOS 26 or later. Nothing extra to install | Stays on the machine |
| Whisper | `faster-whisper`. Strong on proper nouns | Stays on the machine |

It remembers the way you picked, so next time it starts the same way. The two ways
that keep everything local are in [SETUP.md](skills/voice-shell/SETUP.md).

Which languages it can recognize is decided by the way you picked. The browser
offers what Chrome carries, Apple offers the locales installed in the OS, Whisper
offers what the model covers. The window itself comes in seven languages.

## Commands

```bash
voice-shell.sh start [--engine X] [--no-gui]
voice-shell.sh stop
voice-shell.sh status
voice-shell.sh engines
```

| Command | What it does |
|---|---|
| `start` | Starts it, and remembers the way you picked last time |
| `stop` | Stops it |
| `status` | What is running, and which session is listening |
| `engines` | The ways it can recognize speech |

Everything you set stays in `~/.config/voice-shell/` and survives a restart.

## When something goes wrong

Recording on Linux needs `arecord`.

```bash
sudo apt install alsa-utils      # Linux
```

| What you see | What to do |
|---|---|
| You talk and nothing arrives | The trigger level is too high. Lower the mark under the mic in the window until the bar crosses it when you speak |
| Noises send things on their own | The trigger level is too low. Raise that same mark until only your voice gets past it |
| `No Python it can run was found` | `export VOICE_SHELL_PYTHON=/path/to/.venv/bin/python` |
| Startup says `FAILED` | Run `voice-shell.sh status` and read the tail of `daemon.out` |

## A little more

The two below are in English only. What most people need is already above.

| What to read | What is in it |
|---|---|
| [SETUP.md](skills/voice-shell/SETUP.md) | How to install it per environment, and what to do when you get stuck |
| [SKILL.md](skills/voice-shell/SKILL.md) | The steps the agent reads. The fine behavior is here |

## References

- [Web Speech API (MDN)](https://developer.mozilla.org/docs/Web/API/SpeechRecognition)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)

## License

MIT

This file is the source. The six translations beside it are made from it, so when
you change something here, change them too in the same pull request. Where a
translation and this file disagree, this file is right.
