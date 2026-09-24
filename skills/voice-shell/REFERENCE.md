# voice-shell reference

Detail the agent rarely needs, linked from [SKILL.md](SKILL.md).

## Voice commands

The lightbulb in the header lists every wording, in every language the screen
supports. The seven kinds, with English examples:

| Kind | Example |
|---|---|
| Mic off / on | "mute" / "unmute" |
| Draft / Instant | "draft" / "instant" |
| Destination | "switch to 2", "number two" |
| Drop the utterance | "cancel that" **at the end** of a sentence |
| Draft the utterance | "edit this" **at the end** of a sentence |

- The whole-utterance kinds count **only when the phrase is the whole
  utterance**; said inside a sentence it does nothing. Allowed lead-ins:
  - Mute and the native draft words (手直し) tolerate a short burst of noise
    ahead of them ("はいミュート", "はい手直し").
  - Unmute tolerates only a couple of characters, and only wordings that name
    the mic ("えーとミュート解除"; a bare 解除 must be exact).
  - Everyday loanwords and English names (エディット, ドラフト, インスタント,
    draft, hold, instant, live), and the draft and instant words of the other
    languages (borrador, directo, en direct, Sofortmodus, 即时模式, 즉시 모드, ...)
    switch only when said alone or after fillers only ("えーとドラフト",
    "um, live mode"). "PRをドラフトにして" is sent as a prompt.
  - Japanese native instant words (即時) must be exact.
- Destination phrases work only with two or more listeners, follow the chip
  order, and work while the mic is off. Spoken number variants are absorbed.
- A short sound plays when a command takes effect.
- Muting throws away whatever had been recognized but not yet sent, whichever way it was muted (the button, the key, or the spoken word), and the screen says so.
- Users can add wordings for every kind except unmute
  (`~/.config/voice-shell/commands.json`, edited from the lightbulb).
- **Each kind, and each single wording, can be switched off there.** A switched
  off wording never fires, with or without a lead-in.
- **Several machines** (in the lightbulb): name each machine, and only phrases
  prefixed with the name ("work mute") are taken. Without it one phrase affects
  every machine.
- **Plain browser recognition cannot hear "unmute"**: muting releases the
  audio. Turn it back on from the screen (or, if enabled in settings, with a
  few loud sounds).
- **On-device browser recognition can**: nothing leaves the machine, so it
  keeps recognizing while muted. Everything heard there is thrown away (not
  sent, not logged, not shown, not drafted) and only "unmute" is acted on,
  matched in the page with the same wordings, lead-in, switch-offs and machine
  name as the daemon.
- Browser and local engines use the same matching code.

## Keyboard

Nothing works while typing in a field. Bare keys: `,` settings, `.` dictionary,
`?` voice commands, `Esc` closes. With `Shift`: `M` mic on/off, `L` Instant,
`H` Draft, `E` draft this one utterance, `Backspace` discard the unsent text,
`1` to `9` pick the destination. `Ctrl`/`Cmd`+`Enter` sends the draft.
