# voice-shell

Read this in [日本語](README.ja.md).

An Agent Skill for giving Claude Code instructions with your voice. No keyboard.
You talk and the instruction goes through.

```
mic → speech recognition → one line of JSONL → Monitor → Claude Code
```

Say whatever comes to mind while you work and it arrives without you pressing Enter.
It works with Claude Code and with other agents such as Codex.

## Install

```bash
npx skills add ykuwai/voice-shell
pip install numpy aiohttp
```

If you have Chrome, that is all it takes. **No model to download, nothing to wait for.**

## Use

Type `/voice-shell` in Claude Code, or say "voice mode". After that you just talk.
Say "stop voice mode" to stop.

A window of its own opens at http://127.0.0.1:8090 and the words it hears grow
there as you speak. Float it in front and you can watch it while you work on
something else.

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

Recording needs `ffmpeg` (macOS and Windows) or `arecord` (Linux).

Which languages it can recognize is decided by the way you picked. The browser
offers what Chrome carries, Apple offers the locales installed in the OS, Whisper
offers what the model covers. The window itself comes in seven languages.

## Commands

```bash
voice-shell.sh start [--engine X] [--no-gui]   # start (it remembers your last choice)
voice-shell.sh stop                            # stop
voice-shell.sh status                          # what is running, and which session is listening
voice-shell.sh engines                         # the ways it can recognize speech
```

Everything you set stays in `~/.config/voice-shell/` and survives a restart.

## A little more

| What to read | What is in it |
|---|---|
| [SETUP.md](skills/voice-shell/SETUP.md) | How to install it per environment, and what to do when you get stuck |
| [SKILL.md](skills/voice-shell/SKILL.md) | The steps the agent reads. The fine behavior is here |
| [docs/notes.md](docs/notes.md) | What we found out while building it. Skip it if you only want to use the tool |
| [docs/viewer-design.md](docs/viewer-design.md) | Why the window turned out the way it did |

## References

- [Web Speech API (MDN)](https://developer.mozilla.org/docs/Web/API/SpeechRecognition)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)

## License

MIT
