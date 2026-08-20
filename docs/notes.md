# Implementation notes

What we found out while building this. No need to read it if you only use the tool.
It is kept so nobody falls into the same holes twice.

When you write down a measurement, write the **condition**, not the model name.
"0.1 seconds on an M-something Pro" only means something to people who own that
machine, but "RTF 0.03 on Apple Silicon" is something you can compare your own
environment against. The numbers are worth keeping, so do not drop them. Only the
way they are written changes.

## Getting it to run on Windows (Git Bash) took several fixes

`voice_daemon.py` and `voice-shell.sh` originally assumed Linux and macOS only, and
running them on Windows (bash under Git Bash) hit every one of the following. All
of them are fixed now.

- **`import fcntl`** is a POSIX-only module. Windows does not have it, so the thing
  dies with `ModuleNotFoundError` right after startup. On Windows the lock that
  prevents a second instance is done with `msvcrt.locking` instead
- **`os.kill(pid, 0)`** (the liveness check) is unsupported on Windows and raises
  `SystemError`. Replaced by checking whether `OpenProcess` succeeds
- **`pgrep`, `pkill`, `setsid`** are not in Git Bash. `voice-shell.sh` relied on them
  for listing listeners, for the double-start check, and for stopping, so a guard
  was added that gives up on just that feature and passes through when they are
  missing (if pgrep is gone, the viewer's startup check falls back to whether the
  port answers)
- **bash and Python read `/tmp` differently.** In Git Bash (MSYS) `/tmp` is mount
  translated to a real Windows path (somewhere like `...\AppData\Local\Temp`), but
  plain Windows Python that receives the same string `"/tmp"` reads it as `C:\tmp`.
  The two of them think they mean the same thing while looking at different
  directories, and where the daemon writes drifts away from where Monitor is
  running `tail -F`, so **nothing you say arrives anywhere**. Solved by having
  `voice-shell.sh` convert to the real path with `cygpath -w` and hand it to child
  processes explicitly through the `VOICE_SHELL_STATE_DIR` environment variable
- **The character encoding disagrees too.** Python on Windows uses the system locale
  for file I/O by default (cp932 on a Japanese install). It hits
  `UnicodeDecodeError` trying to read JSON and logs written as UTF-8, and the string
  comparisons that check state (`grep -q 稼働中` and friends) stop matching too.
  Worked around by forcing `PYTHONUTF8=1` in `voice-shell.sh` (harmless on
  macOS and Linux)
- **ffmpeg's dshow mic names are different as well.** The original default
  `audio=default` is not actually recognized. You have to run
  `ffmpeg -list_devices true -f dshow -i dummy` and pass the real device name it
  prints, as `--device audio=<name>`

## On macOS the recognition that ships with the OS is the default

On a Mac the default is `--engine apple` (`engine_apple.py`). It uses macOS 26's
`SpeechAnalyzer` and `SpeechTranscriber`, so there is no extra model to download and
no memory to reserve. Measured (Apple Silicon, macOS 26), 3.1 seconds of Japanese
speech took 0.10 seconds and came out correct down to the punctuation (RTF 0.03).
Startup is 0.83 seconds too, which is nothing like the 1 to 2 minutes of downloading
a model and loading it in. The audio is processed on that machine only.

Only a Swift API exists, so `speech_helper.swift` stays resident, we hand it the
path of a WAV, and we get the result back as JSON. The helper is built automatically
with `swiftc` on the first run (it goes in `scripts/build/` and is kept out of git).

### Handing over a file instead of feeding a stream

`SpeechAnalyzer` also has an API where you push audio into an `AsyncStream` with
`start(inputSequence:)`, but called from an unsigned CLI it died with `nilError`
(it works in `LiveDictation`, which is packaged as an `.app`).
`analyzeSequence(from: AVAudioFile)` works fine under the same conditions, so we
write one utterance's worth to a WAV and hand it over. At RTF 0.03 there is time to
re-recognize the whole thing again and again just to show progress.

### The mic belongs to the Python side

The helper only takes audio and turns it into text, it never touches the mic. That
is why it needs no TCC permission and no `.app` packaging, and runs as the plain
executable `swiftc` produced. Recording and cutting utterances apart (VAD) stay the
job of `asr_mic.py`.

(This shape comes out of what we learned in
[live-dictation](https://github.com/ykuwai/live-dictation), which tried the same API
first.)

## Push recognition out to a worker thread

If you recognize the in-progress text on the main loop, you cannot read the mic
while it runs, ffmpeg's pipe (about 0.7 seconds' worth) overflows and recording gets
dropped. Threading brought feed down to 15ms or less (it was stalling about 500ms
per chunk when it ran on the main loop).

## Cleaning up the recording process is needed no matter which engine

When the parent dies on Ctrl-C or a kill, the recording ffmpeg or arecord is left
holding the mic. `_kill_engine_on_exit()` in `asr_mic.py` cleans up its own children
via atexit (SIGTERM does not go through atexit by default, so it is converted into
a sys.exit).

**Register it before the branch on the engine.** It used to sit inside the branch
that loads a model, so on apple, which loads no model, the registration was never
reached and every stop left the recording process behind as an orphan.

## On Linux the mic is taken through arecord

In an environment where PipeWire holds the mic, if PortAudio was built without the
PulseAudio backend, `sounddevice` sees no input devices at all (some distributions
default to exactly that combination). Recording with `arecord -D pipewire` and
converting to 16kHz with soxr avoids both problems.

Reuse `soxr.ResampleStream` for the resampling. Calling `soxr.resample()` per block
builds and tears down the filter every time, which measured about 5 times slower.

## Decide mute by a generation number (a flag breaks)

Recognition only settles after the utterance ends, so if you check for mute only at
the moment it settles, **everything said while the mic was off comes flooding out
together once it is back on.**

The simple "raise a flag the moment it is ever muted" approach breaks too, in two
different ways.

- Muting during silence raises the flag on its own, and **the first utterance after
  unmuting disappears**
- If a noise settles as an utterance while muted, the flag is consumed there, and
  the real utterance right after it gets dropped

`voice_daemon.py` counts how many times the mic has been turned off
(`mute_generation`), remembers the value from when the utterance started, and throws
the utterance away if it changed by the time it settles. What we checked was five
cases. Mute in silence then unmute then speak, a noise while muted then unmute then
speak, mute while speaking, an utterance that straddles a mute, and the normal case.

## Even silence produces backchannels

Given only noise or breath, the model outputs things like 「はい」, 「うん」, and
「ご視聴ありがとうございました」 ("yes", "uh-huh", "thanks for watching").
`NOISE_ONLY` in `voice_daemon.py` throws away utterances that are nothing but these
(turn it off with `--keep-noise`). An utterance with content in it
(「はい、それでは始めます」) is kept.

「ありがとうございました」 and 「お疲れ様でした」 are things people actually say, so
they are not excluded.

## Misrecognition into languages other than Japanese (nothing is done by default)

Picking up a noise sometimes gets misrecognized as Chinese or another language (we
measured `嗯，那嗯嗯。` coming out). But people do speak other languages on purpose,
so **by default it passes straight through**. Adding `--drop-non-japanese` throws
away utterances that contain simplified Chinese, Hangul, Cyrillic and so on (kanji
Japanese shares, like 「時間」, 「問題」 and 「東京」, pass, so it does not fire on
those).

This check looks at the whole utterance, so Japanese with Chinese mixed in at the
end gets through. It is deliberately not implemented as dropping part of a sentence
(losing the body of an instruction to a false positive is the worse outcome).

## Streaming re-feeds the whole audio every time

`streaming_transcribe()` re-feeds "all the audio so far" to the model on every chunk.
The amount of audio encoded for one utterance is proportional to
`utterance length² / (2 × chunk length)`. The table below is how that grows.

| Utterance | Chunk | Audio encoded | Amplification |
|---|---|---|---|
| 30s | 1.0s | 465s | 15.5x |
| 30s | 2.0s | 240s | 8.0x |
| 15s | 1.0s | 120s | 8.0x |

The longer you keep talking, the heavier one chunk gets. It used to be cut at a
maximum number of seconds, but **being cut off mid-way when you meant to say it all
in one breath is the worse problem**, so now nothing is cut while you are still
talking. The only brake left is `HARD_UTTERANCE_CAP` (300 seconds), and talking that
long without a pause does not actually happen. Stretch the chunk length if the
latency bothers you.

## Monitor has to be `tail -F`

The log file is recreated when the daemon restarts, so with `-f` (lowercase) it
keeps watching the old inode and the voice stops arriving. Watch out for keeping two
monitors alive as well, since the same utterance then arrives twice.

## For a small window, rearrange rather than shrink

The viewer is used as a small window floating in front, so both width and height
change a lot. The first attempt shrank the text and the buttons in stages, but
unreadable and unhittable is no use. The three things that actually worked are
below, and none of them touch the sizes themselves.

- **Put the mic and the send mode side by side** (`max-height: 559px`). Stacked
  vertically, those two alone eat more than 200px. Mic on the left and the two
  circles on the right fits in 95 to 120px
- **Cut the top strip down to just the name tag**. Neither the title nor the volume
  wave has to be seen when it is small
- **Let the history absorb both the slack and the shortfall**. Fix `.page` to the
  height of the screen and give only the history `flex:1 1 0; min-height:0`, and the
  history is what goes first as things get tight

You need `flex:none` on `.page > *`. The flex default is `0 1 auto`, so left alone
even a small row like the status line gets squashed and its text is cut off inside
`overflow:hidden` (a 32px row became 8px). As a last way out, `.page` itself is
`overflow-y:auto`, so nothing gets chopped when it truly will not fit.

The text being recognized is capped at the top with `max-height` and scrolls to the
tail as it grows (`streamTail`). People use this by talking at length in one breath,
so without a cap the unsent card alone fills the screen.

## Where to touch when you add a language

**There are 7 places. Miss one and either that spot stays English or a key shows up
on screen as it is.**

Three of them are the on-screen text, in `viewer.html`.

- Add the language's block to `I18N`. **Every language needs the same number of keys.** Miss one and the name of the key goes on screen as it is
- Add it to `UI_LANGS`. The name in the dropdown goes **in that language's own script**. Nobody can pick a language written in letters they cannot read
- Add it to `TIME_LOCALE`. Every language writes the time differently

Four of them are the spoken triggers, in `voice_daemon.py`.

- `COMMAND_WORDS`, `NUMBER_WORDS`, `ROUTE_PARTS`, `ROUTE_EXAMPLES`

**When you add to `UI_LANGS`, check that it is in `ASR_LANGS` too.** Translating the screen but not being able to speak that language makes the screen a lie.

**Adding the unmute trigger is the one that needs a different kind of care.** The reason the mic is off is usually a call, so a phrase people commonly say during a call in that language will open the mic on a word meant for the other person. What you lose is not one utterance, it is the whole stretch of time you thought was off. **If you do not know how that language is spoken, ship it without the unmute.** The English wording works as it is.
