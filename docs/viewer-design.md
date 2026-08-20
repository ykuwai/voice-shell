# Viewer design notes

What was decided in the voice session of 2026-08-18. Written down so that whoever
picks the implementation up builds the same thing. It records the decisions and the
reasons for them, not preferences about looks.

## What this screen is

**A long thin panel you leave floating next to the terminal.** Not a browser tab,
always on top. It sits at the edge of your vision all day, so being quiet when
things are quiet is a requirement.

## What was decided

### Pause is the waveform itself, not a button

Putting a round button in the middle was rejected. There is no obvious place to
press, and on top of that you would need a separate indicator to show that it is
stopped.

**Tapping anywhere on the waveform panel toggles it.** When it stops, the wave sinks
and the color drains, and that doubles as the state display. You press the place
that shows it listening in order to stop it listening, which is a match nobody has
to think about. There is a pause button in the header too, and the two point at the
same state (discoverability and speed at once).

### No mic icon

A picture of a mic cannot tell you whether it means "muted right now" or "press to
mute". A pause icon makes the action and the state agree.

**Filled means you are in that state. Outline means you can pick it but you are not
in it.** Hold to this rule across the whole screen. Count the filled things and you
know the entire current state.

- Live and hold ... only the selected side is filled. On top of that the button
  itself is filled and the text and icon are knocked out
- Power ... filled while running
- Settings ... always outline (it is a doorway, not a state)

### The wave does not flow

A display that scrolls sideways looks like "we are recording" and does not convey
what you are saying right now. **Make it open outward from the center** so it reacts
in the moment. Weight the bars so the center is taller (an even row of bars looks
like noise).

The ring display is not a single circle. **Several ellipses at different tilts are
stacked and wobbled semi-transparently.** The line width wobbles too. One circle
swelling on its own looks like a gauge and gives no sense of speech.

### Draw the threshold as a line

While you are talking, the only thing you want to know is whether it is getting
through right now. Only the bars past the line change color. Adjusting sensitivity
is then finished on this screen alone.

### Integrate the volume before showing it (important)

**Never put raw rms straight into the height.** Consonants, /s/ above all, peg it.
Show a value integrated over roughly 250ms.

The reason is backed up by the LiveKit investigation further down. As real
confirmation, a user reported that the screen fills up on the sound of an S even in
a quiet room.

The judging side (the daemon's utterance splitting) looks at the same rms, so it has
the same problem. Fix the display first, watch how it goes, then touch the judging
side.

### Automatic mic tuning (built, then taken out)

> **Deleted on 2026-08-20.** Used for real, whatever you say in order to tune it
> gets sent to Claude as it is (you have to open the mic to measure, and while it
> is open that voice settles as an utterance). On top of that, even in a normally
> quiet room it sometimes ends with 「声が小さすぎます」 ("your voice is too
> quiet"), and there is no way to tell what to do from there.
>
> **Dragging the mark on the meter** is the official way instead. The bar right
> above it is the current volume, so while talking you put the mark where "only my
> voice crosses it", which is more direct than measuring and estimating, and there
> is nothing to get wrong. What follows is the record of the design as it was.

Three seconds of quiet, then five seconds in a normal voice, measured to put the
threshold between the room and the voice. The result is shown as one scale with
"room", "threshold" and "voice" laid out along it.

**When the gap is not big enough, do not pick a value.** No number will fix that
state, so it says 「マイクを近づけてください」 ("move closer to the mic") instead.
The fact that the value comes out outside the safe range of the existing
`tuning.json` (0.003 to 0.06) is itself usable as that signal.

Collect the `rms` the daemon is already streaming. Measuring with **the very number
the judging uses** means "I tuned it and nothing changed" cannot happen. If the
panel opened its own mic to measure, the sound measured and the sound judged would
be different things, and this feature would become something you cannot trust.

### A dictionary just for this machine (built, then taken out)

> **Deleted on 2026-08-20.** The dictionary could be split into "shared" and "only
> on this machine", but in practice a shared dictionary did not exist for anybody.
> Both files sit in `~/.config/voice-shell/` and never go into the repository, so
> the "it will not be published" distinction was not doing anything to begin with.
> With nothing to gain from the split, a toggle sat at the top of the settings and
> made everyone opening it for the first time stop and wonder which one to write to.
>
> The dictionary is now a single `dictionary.json`. Words you want other people to
> have and words only you need go to the same place.

### What goes in the settings

Mic to connect to, sensitivity, silence before sending, minimum characters,
dictionary, language, theme, how the wave is shown. None of them get touched often,
so they stay out of the main screen.

`viewer.py` already has the APIs (`/api/mics`, `/api/tuning`, `/api/dictionary`,
`/api/mute`, `/api/pause`, `/api/send`, `/api/discard`). The daemon re-reads
`tuning.json` every 0.5 seconds, so writing it takes effect without a restart.

### Multiple languages

**English is the original and Japanese is carried as the translation.** In a narrow
tall layout English runs longer ("Silence before sending" against 「送信までの無音」),
so a settings row stacks the label and the description vertically. Side by side
breaks in English.

### Dark by default

It gets used in a dark room. A white screen is glaring. Light is fully provided too,
but the default is dark. The choice is remembered (going back to white on every
reload does real damage).

### Icons and lines

Round overall, lines on the thick side. Thin lines look lazy. No font is loaded.
SVGs go into a sprite and are called with `<use>` (this is a local tool, so never
create a moment where icons are missing while a fetch finishes).

### The text being recognized

It flows into the unsent card. The live display and the draft are not separated
(the same sentence appearing twice is redundant).

**If a person touches it mid-recognition, stop appending and give the person's edit
priority.** Being able to say "no, not that" and fix it while still talking suits
this tool. Making them wait for the text to settle is the safe option but it is
maddening for those few seconds.

### Filler removal

When it is on, **remove them from the body sent to the shell as well**. Right now
they only vanish from the display and have no effect on what gets sent. That is
pointless.

## How to float it on top

**Chrome's Document Picture-in-Picture** (implemented). The picture_in_picture icon
in the header moves the whole screen into an always-on-top window.

- Always on top is the API's own default behavior. No extra runtime, no build step
- It just moves `#page` and `#sheet` and copies the `<style>`. The JS is untouched
- Opens at 400x664 and is resizable. Closing it puts it back in the original tab

Two alternatives were considered.

- **A thin Swift and WKWebView shell.** Setting the `NSWindow` level to `.floating`
  gives you a real always-on-top window that works with Chrome closed. It was
  written once, then deleted because PiP was enough (it survives in `13e1bac`)
- **Electron (over 100MB) or Tauri (needs Rust).** Neither is worth bringing in

## Icons

**Material Symbols Rounded (Apache-2.0) embedded directly in viewer.html.** The 30
glyphs in use are kept as outline and filled pairs and swapped by state.

Putting the sprite in a separate file was considered, but the PiP window is a
separate document, so an external reference would need a delivery path added to
resolve it. Embedding has none of that worry, and it never creates a moment where
icons are missing while a fetch finishes.

## What came out of looking at LiveKit's volume display

Someone asked to use LiveKit's Agent UI, so the internals were read.
**The conclusion is that we do not use it.** There are two reasons.

### 1. The shape does not fit

`BarVisualizer` demands an audio Track. The local viewer has no mic, it only watches
the `rms` the daemon streams. Making the panel open a mic would technically work,
but the volume shown would be a different thing from the sound the judging uses, and
the threshold line would become a lie.

(For the record, connecting a Room is not required, you can hand it a
`LocalAudioTrack` directly. No server needed. The reason we do not use it is the
shape, not the weight.)

### 2. LiveKit has the same S pegging problem

Reading the implementation (`livekit/components-js`, `livekit/client-sdk-js`) gives
the following.

- The band `BarVisualizer` watches is **2.34 to 4.69kHz only**. Neither the
  fundamental of the voice (85 to 255Hz) nor the first formant is in there.
  **That is exactly the band of /s/, /ʃ/ and /t/**
- `loPass` and `hiPass` are **FFT bin numbers**, not Hz, and the names are the
  reverse of what they do (`loPass: 100` means "throw away bins 0 to 99", so it is a
  high pass). The biggest trap when porting
- Normalization clamps to -100 to -10dB, maps linearly, then takes `sqrt`.
  **It averages values in the log domain**, so small bins get lifted
- **There is no attack and release envelope.** The only smoothing over time is the
  AnalyserNode's `smoothingTimeConstant` (0.8 in multiband)
- No perceptual weighting (A-weighting or similar) and no logarithmic band split

So vowels only reach that window through their upper harmonics, while /s/ puts its
main energy right in it. **Copying LiveKit's look as it is means reproducing the S
problem the user pointed out.**

As a side effect, a noise floor of -85dB/bin normalizes to 0.39, and together with
`minHeight: 20` that means **the bars wobble at 40 percent height even in a quiet
room**. It also explains "it moves a lot even when it is quiet".

### What is worth taking

- Switching the animation on `state` (listening, thinking, speaking) is a good idea.
  LiveKit's thinking is only the same row as listening blinking at 150ms intervals
  though
- Gen2's radial is the same multiband laid around a circle
- Gen2's aura is a WebGL shader, and **the volume feeds exactly one thing, the SDF
  radius of the circle** (0.2 to 0.4). Everything else comes from state and has
  nothing to do with the sound

**The design to take is this one.** Do not narrow the band, use the overall volume,
integrate over 250ms, attack fast and release slow. Make the richness of the look
out of stacked ellipses and wobble.

The sources are the following files.

`packages/react/src/hooks/useTrackVolume.ts`,
`packages/react/src/components/participant/BarVisualizer.tsx`,
`createAudioAnalyser` in `src/room/utils.ts`,
`packages/shadcn/{hooks,components}/agents-ui/*`

## Mockup

At the start, one page that could switch light and dark, English and Japanese, and
bars and ring was built, and the decisions were made on it (the wave motion was a
dummy and no mic was used). What it contains is in `viewer.html` now, so nothing
this note refers to is kept around.

## How buttons are handled (leaning on the Material principles)

The policy is "**say what matters with a fill. Always give buttons contrast against
each other**".

- **Confirming actions are filled**, things like save, send and create. Not outline
  and not text only
- Buttons standing side by side on one screen have **a difference in weight you can
  see at a glance** between primary, secondary and dismiss. When they all look the
  same, you have to read them to work out which one to press
- Text-only buttons (「完了」, "Done", and the like) do not convey what they do.
  **If it can be an icon, make it an icon**

### How the settings screen closes

A button labeled "Done" in the top right is hard to read. You cannot tell whether
pressing it saves, discards, or just closes.

The options are as follows.

- Put a **back arrow** at the top left that takes you home (settings apply the
  moment they change, so no confirming action is needed in the first place)
- For the few items that do need confirming, put a **filled "Save" button** right
  there

That combination is the straightforward one. At the very least, do not put a text
button there whose only job is to close.

### Text size

The contents of the settings are small. Narrow panel or not, settings are a screen
you read, so do not pack them tighter than the main screen.

## How it floats

Chrome's Document Picture-in-Picture (the "float in front" button in the settings,
already implemented in the viewer itself). No extra runtime is needed, and because
whole elements are moved, the JS references survive the move. Chrome or Edge
required.

A window from the OS side (`NSWindow.level = .floating` on macOS) was another
option, but no implementation is kept. It can be thought about when someone asks to
use this without opening a browser.

## About getting the volume on the page side (correction)

The current `viewer.html` opens the mic with `getUserMedia` and draws the waveform
with its own FFT (`micStream` and `analyser`). The user's report that the screen
fills up on the sound of an S in a quiet room is most likely the behavior of
**this page's own FFT**, not the daemon's rms. It is the same failure pattern the
LiveKit investigation turned up, caused by the band being skewed and the envelope
being absent.

**Make the daemon's rms the main path so it holds up with no mic.** Treat the FFT on
the page side as an extra that only exists when it runs in a browser. In any setup
where the mic cannot be handed over, this route (`vizFailed → daemonLevel`) is
always the one used.
