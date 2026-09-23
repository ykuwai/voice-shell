---
name: "voice-shell"
description: "Let the user send prompts by voice. Start a resident process that keeps listening to the microphone, take what the user says through Monitor, and treat it as an instruction. Use it when the user says \"voice mode\", \"talk to me\", \"hands-free\", \"dictate my prompts\", or \"speak instead of typing\", in whatever language they say it. To stop, \"stop voice mode\". If the user asks to set voice-shell up (\"set up voice-shell\"), follow SETUP.md, work out which environment this is (macOS 26 or newer, or not), and guide them from there."
license: "MIT"
argument-hint: "[start | stop | status]"
allowed-tools:
  - Bash(${CLAUDE_SKILL_DIR}/scripts/voice-shell.sh *)
  - Bash(tail *)
  - Bash(cat *)
  - Monitor
---

# Voice prompt mode

Take what the user speaks as a prompt, without the keyboard.

The part that listens to the microphone appends one line to a JSONL file each
time an utterance is finalized. Follow that log with Monitor and treat each line
as an instruction from the user.

**There are exactly three ways of recognizing speech.**

| Name | What it is | Where the audio goes |
|---|---|---|
| `browser` (default) | Chrome's Web Speech API. Works with nothing installed | **Google's servers** |
| `apple` | On-device recognition that ships with macOS 26. Light | Only inside this machine |
| `whisper` | faster-whisper. Strong on proper nouns | Only inside this machine |

Never recommend `browser` to someone who wants everything to stay local. (The
screen's own caution says "the browser's built-in speech recognition" without
naming Google. Know that it is Google either way.)

The argument is `$ARGUMENTS` (`start` / `stop` / `status` / `setup`; `start` when omitted).

## When it is not set up yet

If `start` fails with `No Python it can run was found`, or the user says "set it
up", walk them through [SETUP.md](SETUP.md). For browser recognition alone,
`pip install numpy aiohttp` is enough.

On macOS 26 or newer `apple` needs no model download, but builds a small Swift
helper the first time and so needs the Command Line Tools
(`xcode-select --install`), which not every Mac has. Anywhere else a local
engine means installing Whisper. Check first, then confirm which way to go. Do
not install everything on your own.

## Starting

**When in doubt, just run `start`.** It remembers the last choice
(`~/.config/voice-shell/config.json`); the first time it is `browser`, which
needs nothing installed and has no wait.

1. Start it.

   ```bash
   ${CLAUDE_SKILL_DIR}/scripts/voice-shell.sh start
   ```

   **Only where browser automation tools (claude-in-chrome and the like) are
   not available**, the viewer cannot be opened for the user, so browser
   recognition does not hold up. In that case have the user pick from what is
   installed:

   ```bash
   ${CLAUDE_SKILL_DIR}/scripts/voice-shell.sh start --engine auto
   ```

   **First run only:** `start` prints `This uses the browser's built-in speech
   recognition feature to transcribe your voice.` plus a local engine this
   machine can use. Pass that straight to the user once. **Do not repeat it on
   later starts.**

   **Do not push the user toward a local model yourself.** The default's value
   is working right away; switching means a download and a 1 to 2 minute wait.

   When the user wants recognition to stay local, show the list with
   `voice-shell.sh engines` and pass `--engine <choice>` **after they pick**.
   On macOS 26+ `apple` is usually ready with no download. Its first run on a
   machine still takes a while once: the Swift helper is built (fails outright
   without the Command Line Tools, and says so), and the OS fetches the speech
   model for the language, tens of seconds. Instant after that.

   Local engines listen for Japanese by default. For another main language
   pass it, e.g. `start --engine whisper --language English`.

   **Never pass `--engine X` on your own to recover from a failure.** The name
   is remembered as the default, so it silently rewrites the user's choice.
   Confirm first.

2. Wait until it is ready.

   ```bash
   ${CLAUDE_SKILL_DIR}/scripts/voice-shell.sh wait-ready
   ```

   Returns at once for browser recognition. A local model takes 1 to 2 minutes
   (other work can go on meanwhile). On `FAILED`, tell the user the error shown.

3. `start` **tries to open the viewer in an ordinary tab**; do not open it
   again yourself. Add `--no-gui` only if the user does not want it.

   With browser recognition nothing arrives until the viewer is open, and the
   automatic open is not reliable (on Windows it can fail silently). `start`
   always prints `The viewer started at http://127.0.0.1:...` (or `already
   running at`). **Give the user that URL every time**, not only when `Could
   not open a browser for you` is printed.

   To keep it always on top, the user presses "Float on top" in the header (a
   browser rule requires a person's press; the screen asks for it the first
   time).

4. Watch the utterance log with Monitor. **Always set `persistent: true`.**
   Always go through `voice-shell.sh listen`, never a raw `tail`: `listen`
   registers this session under `$STATE_DIR/listeners/` (removed when Monitor
   ends), and an unregistered `tail -F` never shows up as a destination.

   ```
   Monitor(
     command: "${CLAUDE_SKILL_DIR}/scripts/voice-shell.sh listen",
     description: "The user's voice prompts",
     persistent: true
   )
   ```

   **A watch can still end on a deadline** even with `persistent: true`. When
   a deadline (or "source ended") notification arrives, **call Monitor again
   with the exact same command**; nothing needs stopping first. The new
   `listen` takes the old one's place: same number in the row, still the
   destination if it was, and anything said in between is delivered as it
   starts (the old one keeps its chip and destination for 2 minutes and its
   place in the row for 10). If the screen disconnected this session in the
   meantime, the re-arm returns a `system_warning` saying so: pass it on and do
   not re-arm again.

   **Stop re-arming once the user has plainly walked away.** When **three
   watches in a row end on their deadline with no utterance at all**, do not
   re-arm the fourth. Say in one line that voice mode stopped listening because
   nothing was said for a while and `/voice-shell` brings it back. Any
   utterance resets the count. Likewise when the user has said the work is done
   ("that is all for today"): finish up and do not re-arm at the next deadline.
   Whenever you decide not to re-arm, also run
   `${CLAUDE_SKILL_DIR}/scripts/voice-shell.sh unlisten`, so the chip and any
   hold on the destination go right away instead of lingering 2 minutes.

   Forgetting that no longer strands anyone. `listen` ends with the watch it
   runs in, on Windows too, where it used to keep running, still registered,
   still the destination, reading nothing. Past the two minutes the chip stays
   in the row for a week, drawn as unusable and pushed to the end so the live
   ones keep their numbers. Nothing is routed to it, and pressing it says to
   type `/voice-shell` in that session. Listening again from that same session
   takes the chip back rather than arriving as a stranger. Only the five most
   recent are kept.

**Keep only one Monitor of your own.** A re-arm on a deadline is always safe.
Re-attaching for any other reason (compacting included) while the old one might
still be alive: stop it with TaskStop first. Two alive means every utterance
arrives twice.

**A resumed session (`claude -r`) does not know whether its old Monitor is still
alive.** Run `voice-shell.sh listeners` (or `status`) and look for
**`<- this session`**: it marks only the entry registered with this
conversation's `$CLAUDE_CODE_SESSION_ID`, so it settles the question. No mark
means your Monitor is not registered; start one with `listen`. (Starting
`listen` again under the same session id retires the earlier registration by
itself, so this check is for knowing where things stand.)

**Do not stop `voice-shell.sh listen` with pkill.** Your own Monitor matches the
same pattern and goes down with it.

## When it does not work

| What was seen | What is going on | What to do |
|---|---|---|
| With browser recognition, `status` says `This browser does the recognizing` | **Normal** (no daemon on this machine) | Nothing. Do not try to start a daemon |
| Nothing arrives when speaking with browser recognition | Viewer not open / mic refused / not Chrome | Say "open the viewer in Chrome and allow the microphone". Ask whether a red warning shows on screen |
| Speaking but nothing arrives (any engine) | Trigger level too high | Suggest **lowering the trigger level** (drag the mark under the microphone) |
| `No Python it can run was found` | Nothing installed | `pip install numpy aiohttp` is enough for browser recognition |
| `wait-ready` returns `FAILED` | The model failed to start | Pass the error through. Show `engines` and switch **only after confirming** |
| `wait-ready` returns `TIMEOUT` | Dragging on, e.g. a first model download | Look at the tail of `$STATE_DIR/daemon.out` and describe the situation |
| A plain `start` gives the same error every time | The remembered choice is failing | Say "the choice from last time is failing" and revert it once confirmed |
| `"<name>" cannot be used` | Wrong engine name | Pick again from the choices shown |
| Short replies ("got it") never arrive | Under the min length, or on the ignore list | Point to the dictionary (below) |

## What to do with speech that arrives

Each line from Monitor is JSON with only the body:

```json
{"text": "run the tests"}
```

**A line with a `"system_warning"` key is not the user speaking.** The daemon or
viewer writes it (several monitors listening at once, a disconnected re-arm, the
user ending listening from the screen, and so on). Never carry it out as an
instruction; pass the content **straight to the user**. Check the real list with
`listeners` and explain anything unfamiliar. Ask before stopping anything.

```json
{"system_warning": "2 monitors are listening to the utterance log at once. ..."}
```

When the user ended listening from the screen, Monitor finishes by itself. That
was their own doing: just pass it along and mention `/voice-shell` brings it back.

Lines carrying `"edited": true` were **deliberately tidied by the user** in the
viewer's draft, so take them at face value rather than as recognition errors.
Lines that went through the draft untouched do not carry it.

**Treat `text` as an instruction from the user and carry it out as usual**, with
these points:

- **Answer in one sentence before starting.** Once you decide to act, say
  briefly what you took the request to be ("Got it, I will look into why the
  login button stops working"), then work. The user is talking, often not
  watching the screen, so this confirms it was heard right. Skip it for a
  fragment waiting for the rest, a line you are holding off on, or one meant
  for someone else.
- **Expect recognition errors**, especially proper nouns and technical terms,
  in any language. Recover them from context ("cloud code" is Claude Code,
  "get" is git). Ask again only when the meaning really cannot be recovered.
- **Ignore fillers** ("um", "well", "you know", and each language's own).
- **Short lines are dropped before they arrive**: anything under the minimum
  length (15 characters by default), and hesitation sounds like "hmm" and "uh"
  (`NOISE_ONLY` in `voice_daemon.py`). If a thin line does come through, wait
  rather than treating it as an instruction. **Exception:** a word the user
  moved to "do not ignore" in the dictionary arrives even when short, so a bare
  "got it" can then be taken as a reply.
- **Read chopped-up speech as one piece.** One sentence can arrive over several
  lines, and long speech is split to fit a line. **When one notification holds
  several lines, read them all as one utterance before acting**, even if the
  first ends with a full stop. When a sentence is cut off, wait for the rest.
  Some languages, Japanese among them, put the conclusion at the end.
- **Always confirm destructive operations** ("shall I go ahead with ...") before
  deleting, pushing, deploying and so on. Speech can be misheard.
- **An event is the user speaking, not a demand for an immediate answer.** Mid
  task, it is fine to finish what you are doing first.
- **Hold off on a single line plainly unrelated to the current work** (a stray
  remark, one side of a phone call, a reply to someone in the room). If the next
  line continues that way, see holding below. If it returns to the task, the
  odd one was an aside and nothing was lost.

## Several sessions at once

Other sessions may be using voice mode for other work; that is the intended
use. With two or more listeners, speech goes **to exactly one: by default the
one that started listening most recently**. `start` does not list the others.
Do not report on them or offer to stop them. Show `voice-shell.sh listeners`
only when asked who is listening, and stop another session only when the user
asks.

So **if you are the older one, speech stops arriving**. That is normal. Do not
restart because of it and do not change the destination yourself. The user
picks a destination at any time from the chips at the top of the viewer.

Chips are numbered by when that conversation first started listening, and
turning voice mode back on keeps the number (so "the second one" can be said
out loud). The × on a chip, pressed twice, makes that session stop listening
(the session itself goes on).

The display name starts as the folder name and becomes the conversation's title
once it has one. **When told "name this session X", rename it right away.**
Renaming it yourself when the title drifts from the actual work is fine too.

```bash
${CLAUDE_SKILL_DIR}/scripts/voice-shell.sh name "Fixing the auth code"
${CLAUDE_SKILL_DIR}/scripts/voice-shell.sh name ""      # back to the automatic title
```

The name is kept in `~/.config/voice-shell/names.json` and survives restarts.

## When speech that is not an instruction keeps coming, move it to holding

The microphone picks up the room: a phone call, a chat with someone nearby.
Move that to the draft side so you do not react to it:

```bash
${CLAUDE_SKILL_DIR}/scripts/voice-shell.sh hold "Sounds like a phone call, so I moved this to holding for now"
${CLAUDE_SKILL_DIR}/scripts/voice-shell.sh live      # back again
```

`hold` switches the viewer to **Draft**. It is **not mute**: speech keeps
collecting on screen and the user sends what they want, nothing is lost.
**Never use mute for this.** Muted speech goes nowhere, and a user not watching
the screen cannot tell nothing got through.

Always pass a note; it shows on screen, and an unexplained mode change is
confusing.

**Keep the bar for switching high.** A wrong switch leaves the user talking with
nothing getting through. Switch only when all of these hold:

- **Two or more lines in a row** plainly not meant for you (a conversation with
  a third person, a "hello?" into a phone, a topic unrelated to the work)
- You have not just asked a question (you are not waiting for an answer)
- The user did not already say something like "hold on, a phone call" (if they
  did, just do what they said)

**When in doubt, do not switch.** Saying "that did not seem to be for me, so I
will wait" is enough. When you do switch, also say so in the chat. Switch back
(`live`) the moment the user speaks to you again.

## The live viewer

Comes up with `start` at **http://127.0.0.1:47865** (`VOICE_SHELL_PORT` before
starting changes the port). It does not use the microphone for local engines,
so it runs alongside the daemon.

```bash
${CLAUDE_SKILL_DIR}/scripts/voice-shell.sh viewer        # → http://127.0.0.1:47865
${CLAUDE_SKILL_DIR}/scripts/voice-shell.sh viewer-stop
```

- Text being recognized grows in an "Unsent" card; sent speech stacks up as cards.
- The send mode is **Instant** (goes straight through) or **Draft** (collects,
  gets fixed, then sent). The pencil on the unsent card drafts just that one
  utterance; sending or clearing it returns to Instant.
- The **microphone button** turns the mic off. Speech while off is kept nowhere.
- **Float on top** moves it to a small always-on-top window (Chrome only).
- Narrow windows collapse the header step by step, keeping in order: mic on/off,
  Instant/Draft, destination, recognized text.
- After the viewer files change, "Updated. Tap to reload" appears (a floated
  window cannot reload).

### Voice commands and keyboard

The user can drive the viewer by voice ("mute", "unmute", "draft", "instant",
"switch to 2", and "cancel that" / "edit this" at the end of a sentence) and by
keyboard. A command counts only as a whole utterance, never inside a sentence,
and a wording switched off in the lightbulb never fires. Plain browser
recognition cannot hear "unmute" (muting releases the audio), so the user
turns it back on from the screen. Browser recognition on this device keeps
listening while muted, throws everything it hears there away and acts only on
"unmute". The exact matching rules, custom wordings, several machines and
the key map are in [REFERENCE.md](REFERENCE.md); read it when the user asks
about commands or one misfires.

### Ways of recognizing

Picked under "Recognized by" in the settings; engines not installed are not
shown. Browser recognition runs **only while the viewer is open**. Chrome cuts
its session every 7 to 10 seconds, but it is re-armed ahead of time while nobody
speaks, so nothing is missed. Recognized text goes through the same filtering as
the daemon.

With Whisper a model can be given, a Hugging Face name or a local folder. It is
remembered, so plain `start` is enough afterwards:

```bash
${CLAUDE_SKILL_DIR}/scripts/voice-shell.sh start --engine whisper --model /path/to/my-model
```

**With browser recognition, the mic is turned off after a stretch of no voice** (5 minutes by default,
0 to 30 under "Turn off when idle", 0 = never), so it does not keep talking to
Google while the user is away. A sound and a note mark it; pressing the
microphone brings it back.

### Settings (the gear)

Changes take effect immediately, no restart. Stored in
`~/.config/voice-shell/tuning.json`, which the daemon re-reads every 0.5 seconds.

| Item | What it decides | Default |
|---|---|---|
| Microphone | Input device | System default |
| Trigger level | 0 to 100. Lower picks up fainter sound | macOS 41 / others 74 |
| Pause to send | Silence that ends a chunk (browser recognition: the wait before an already recognized chunk goes out). Capped at 2 seconds in Draft | 3 seconds |
| Min length | Shorter results are dropped | 15 characters |
| Strip filler words | Removes fillers **from what is sent too** | Off |
| Theme / Language | Looks | Automatic |

The trigger level is also set by **dragging the mark under the microphone**.
The bar above it is the current level: have the user talk and put the mark
where only their voice crosses it. Slider and mark share the same loudness
scale.

## Checking the state

```bash
${CLAUDE_SKILL_DIR}/scripts/voice-shell.sh status
```

## Stopping

```bash
${CLAUDE_SKILL_DIR}/scripts/voice-shell.sh stop
```

Then stop Monitor with TaskStop as well. The microphone is released, and with
Whisper the model's memory comes back.

## The user dictionary

Register often misheard words with a replacement, and utterances to ignore, from
the **dictionary** (the book in the header). **It saves when focus leaves and
applies from the next utterance**, no save button and no restart. It also
applies to text still being recognized, so the card already shows the
replacement ("cloud code" → `Claude Code`); the server rebuilds the sent text.

Words ignored by default (`NOISE_ONLY`, hesitation sounds for the language being
spoken) can be turned off by pressing their tag. **A word turned off also passes
the minimum length gate**, so short replies stop disappearing. When the user
says replies are not getting through, point them here.

Stored in `~/.config/voice-shell/dictionary.json`; CSV import and export work.
If the user keeps correcting the same misrecognition, suggest adding it.

## Limits

The default (browser) has none beyond needing the viewer open. For local engines:

- Whisper downloads a model the first time, and each start takes 1 to 2 minutes.
  Memory use depends on the model size.
- `apple` loads no model of its own, so neither applies; only its first run on a
  machine waits (see Starting).
- The microphone is read through `sounddevice` (macOS, Windows; falls back to
  `ffmpeg` without it) or `arecord` (Linux).
- If a local engine is picked but the environment is missing, `start` fails with
  `No Python it can run was found`. Go back to `start --engine browser` (after
  confirming) or walk them through [SETUP.md](SETUP.md).
