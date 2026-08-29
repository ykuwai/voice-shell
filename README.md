# Voice Shell

English · [日本語](docs/readme/README.ja.md) · [Español](docs/readme/README.es.md) · [Français](docs/readme/README.fr.md) · [Deutsch](docs/readme/README.de.md) · [简体中文](docs/readme/README.zh.md) · [한국어](docs/readme/README.ko.md)

<p align="center">
  <img src="https://img.shields.io/github/license/ykuwai/voice-shell" alt="License">
  <img src="https://img.shields.io/github/last-commit/ykuwai/voice-shell" alt="Last commit">
</p>

**Talk to Claude Code. No keyboard.**

You think out loud while you work, and the sentence lands as a prompt, no
Enter key involved. Not dictation bolted onto a text box. Mute, review, undo,
and pick which session hears you, all by voice, while your hands stay on
whatever you were doing.

<p align="center">
  <img src="docs/readme/images/viewer.png" alt="The Voice Shell viewer, a floating window showing live transcription, session routing, and send mode" width="360">
</p>

## 💡 Why Voice Shell

- **Nothing to press to send it.** Most voice tools fill a text box and wait
  for you to hit send. Here the sentence goes straight through the moment
  it's heard, no button, no confirmation step, no window to click into.
- **Nothing to install to try it.** The default recognizer is your browser.
  No model download, no wait. When you want it fully private, switch to
  on-device recognition (Apple, or Whisper) with one setting, no re-learning
  anything.
- **A full voice UI, not a microphone icon.** Muting, switching between live
  and hold, undoing what you just said, picking which session hears you, all
  of it works hands-free too. See "What you can say" below. The floating
  window shows exactly what it heard as you say it.
- **Run it for more than one thing at once.** Keep voice mode on in several
  Claude Code sessions and choose which one gets your words, from the window
  or by voice.
- **Misheard names fix themselves.** Teach it once ("cloud code → Claude
  Code") and the correction applies from then on, even to text still being
  recognized.

## 📦 Installing Voice Shell

```bash
pip install numpy aiohttp "sounddevice>=0.5.6"
npx skills add ykuwai/voice-shell -g -a claude-code -y
```

If you have Chrome, that is all it takes. `-g` puts it in `~/.claude/skills/`,
so it is there for every project. Only want to try it out inside one project?
Drop the `-g` and it lands in `.claude/skills/` for that project alone.
`-a claude-code` names Claude Code directly instead of leaving `npx` to guess,
and `-y` skips the confirmation it would otherwise ask for.

Type `/voice-shell` in Claude Code, or say "voice mode", to start. The steps
an agent follows from there are in [SKILL.md](skills/voice-shell/SKILL.md).

## 🔄 Updating Voice Shell

```bash
npx skills update voice-shell -y
```

Leave off `-y` and it asks first. Drop the name and it updates every skill
you have installed, this one included.

## 🔒 Where your voice goes

Two of the three ways never send your voice anywhere outside this machine,
and switching to one takes a single setting. Which way is picked is always
visible in the window.

> [!NOTE]
> The default is browser recognition, so the audio is sent to Google's servers.
> When you want it to stay on your machine, pick another way from the settings
> in the window. The same warning is written there on the spot.

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

## 🗣️ What you can say

Say one of these on its own, with nothing else in the sentence, and it
happens right away.

| Say this | What happens |
|---|---|
| "mute" | Microphone off |
| "unmute" | Microphone back on (only while a model on this machine is listening, not the browser) |
| "hold" or "draft" | What you say from here piles up instead of going out, so you can fix it before it sends |
| "live" or "instant" | Back to going straight through |
| "session 2" or "switch to 2" | Picks which listening session your words go to, when more than one is listening |

Add one of these to the end of what you are saying and it applies to that
one sentence alone.

| Say this | What happens |
|---|---|
| "cancel that" | The sentence you just said is thrown away |
| "edit this" | The sentence lands in the box instead of going out, so you can fix it first |

Every phrase above can be switched off, and you can teach it your own
wording, both from the settings in the window. The full list, in all seven
languages the window comes in, is behind the lightbulb icon on screen.

## 📖 Reading more

The two below are in English only. What most people need is already above.

| What to read | What is in it |
|---|---|
| [SETUP.md](skills/voice-shell/SETUP.md) | How to install it per environment, and what to do when you get stuck |
| [SKILL.md](skills/voice-shell/SKILL.md) | The steps the agent reads. The fine behavior is here |

## 🔗 References

- [Web Speech API (MDN)](https://developer.mozilla.org/docs/Web/API/SpeechRecognition)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)

## 📄 License

MIT

This file is the source. The six translations beside it are made from it, so when
you change something here, change them too in the same pull request. Where a
translation and this file disagree, this file is right.
