"""Muting means the words already in flight do not go out.

A clause that finalized before the mute sat in pendingBrowserSends and waited
out its quiet stretch there. Pressing the microphone never touched that queue,
so the send gate flushed it seconds later, after the person had deliberately
cut the mic. The server kept nothing of it (dropped as muted), but only after
running apply_voice_command on it first, so a clause that happened to end in an
unmute wording opened the mic again from inside the mute.

The spoken mute used to flush the same queue out on purpose, on the reasoning
that those words were going out regardless. That reasoning does not survive the
pressed mute dropping them, so both ways of muting now drop, and the mute word
itself still goes out ungated.

The same text also flashed back onto a muted screen. paintPendingBrowserSends
and onend write browserStreamText() into el.stream between paint() ticks, and
both built it from state the mute had not cleared, so the pre-mute line showed
up again every few seconds until the next paint wiped it. browserStreamText
answers that for every writer at once, resumeSnapshot included.

The pieces are cut out of viewer.js and run under node, the same way
test_send_gate_lag.py and test_reload_resume.py cut theirs out. The clause text
is kept to plain letters: node reads the script off the command line and the
console encoding mangles anything else.
"""
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIEWER_JS = ROOT / "skills/voice-shell/scripts/viewer.js"

# ── The send gate and the mute's side effects, driven together ──
# Both slices go into one body so the mute really calls the real
# dropPendingBrowserSends rather than a stand-in for it.
HARNESS = r'''
const fs = require('fs');
const source = fs.readFileSync(process.argv[1], 'utf8');
const cut = (from, to) => {
  const start = source.indexOf(from);
  const end = source.indexOf(to, start);
  if (start < 0 || end < 0) process.exit(2);
  return source.slice(start, end);
};
const gate = cut('const BROWSER_SEND_GATE_MS = 100;',
                 '/* Settled utterances go to the server.');
const sideEffects = cut('function applyRouteSideEffects(next) {',
                        '/* The floating window is a separate document');

const make = new Function(`
  let clock = 0;
  const performance = {now: () => clock};
  const setInterval = () => 0;
  const sent = [], said = [];
  let rms = 0, engine = 'browser', onDeviceLocal = false, route = 'live';
  let carryDraft = false, recWanted = true, recRunning = true, recStarting = false;
  let dropNextLocal = false, asrPausedByRoute = false, vizArmed = false;
  let interimThrottleTimer = 0, latestInterimForPaint = '';
  let lastVoiceAt = 0, rec = null, onDevice = false;
  // Declared beside muteHint in the page, so the harness holds it here.
  let mutedDropNote = false;
  const tuning = {silence_duration: 3.0, silence_threshold: 0.015};
  const computeBrowserRms = () => rms;
  const asrActive = () => true;
  const paintGauge = () => {};
  const clauseJoin = () => ' ';
  // The real one, in miniature: the queue joined, and empty while muted.
  const browserStreamText = () =>
    route === 'off' ? '' : pendingBrowserSends.map(p => p.text).join(' ');
  // Word for word, as the page does it: an unmute wording at the end is not a
  // mute. The real matchingTailWord is tested in test_muted_unmute.py.
  const matchingTailWord = text => (/(^| )mute$/.test(text) ? {id: 'mute'} : null);
  const sendUtterance = text => sent.push(text);
  const say = text => said.push(text);
  const muteHint = () => (mutedDropNote ? 'threw it away. muted' : 'muted');
  const el = {stream: {textContent: ''}, tray: {classList: {remove() {}, add() {}}},
              multiOn: {checked: false}};
  // Several machines listening at once. The real pair is tested against the
  // daemon's own in test_machine_name.py; here they only have to pick the
  // name off the front the way _strip_name does.
  let names = [];
  const machineNames = () => names;
  const stripMachineName = (text, list) => {
    for (const n of list) {
      if (!text.startsWith(n)) continue;
      return text.slice(n.length).replace(/^[ ,]*/, '');
    }
    return null;
  };
  const streamTail = () => {};
  const listensWhileMuted = () => onDevice;
  const stopRecognition = () => { recRunning = false; };
  const startRecognition = () => { recRunning = true; };
  const resetBrowserGesture = () => {};
  const startViz = () => {}, vizDeviceLabel = () => '';
  const syncVizCapture = () => {}, paintBrowserAsr = () => {};
  const clearTimeout = () => {};
  \${gate}
  \${sideEffects}
  return {
    run(ms, opts = {}) {
      for (let i = 0; i < Math.round(ms / BROWSER_SEND_GATE_MS); i++) {
        clock += BROWSER_SEND_GATE_MS;
        rms = opts.loud ? 0.1 : 0;
        if (opts.interim) lastLoudAt = lastInterimChangeAt = clock;
        browserGateTick();
      }
    },
    final(text) { queueOrSendFinal(text); },
    pressed() { route = 'off'; },
    multi(on, list) { el.multiOn.checked = on; names = list || []; },
    mute() { route = 'off'; el.stream.textContent = ''; applyRouteSideEffects('off'); },
    unmute() { route = 'live'; applyRouteSideEffects('live'); },
    drop: () => dropPendingBrowserSends(),
    note: () => mutedDropNote,
    stream: () => el.stream.textContent,
    onDevice(v) { onDevice = v; },
    sent, said,
    pending: () => pendingBrowserSends.map(p => p.text),
  };
`.replace('${gate}', gate).replace('${sideEffects}', sideEffects));
const assert = (cond, what) => { if (!cond) { console.error(what); process.exit(1); } };
const h = make();
'''


# ── browserStreamText on its own ──
STREAM = r'''
const fs = require('fs');
const source = fs.readFileSync(process.argv[1], 'utf8');
const start = source.indexOf('function browserStreamText() {');
const end = source.indexOf('function paintInterimNow', start);
if (start < 0 || end < 0) process.exit(2);
const body = source.slice(start, end);
const make = new Function('env', `
  const route = env.route;
  const pendingBrowserSends = env.pending.map(text => ({text}));
  const latestInterimForPaint = env.interim;
  const clauseJoin = () => ' ';
  const withDict = s => s;
  ${body}
  return browserStreamText;
`);
const assert = (cond, what) => { if (!cond) { console.error(what); process.exit(1); } };
'''


def run(script, harness=HARNESS, js=VIEWER_JS):
    subprocess.run(["node", "-e", harness + script, str(js)], check=True)


class PressedMuteTest(unittest.TestCase):
    def test_a_clause_queued_before_the_mute_never_goes_out(self):
        """The shape the user hit. Say something, press mute, and it still went."""
        run(r'''
h.run(2000, {loud: true});
h.final('one more thing');
assert(h.pending().length === 1, 'queued, waiting out the quiet');
h.mute();
assert(h.pending().length === 0, 'the mute throws the queue away');
h.run(20000);              // quiet, far past the wait and past the cap
assert(h.sent.length === 0, 'nothing may go out after the mute, got ' + JSON.stringify(h.sent));
''')

    def test_a_clause_that_ends_in_an_unmute_wording_cannot_open_the_mic(self):
        """viewer.py runs apply_voice_command before it drops what came in as
        muted, so a flushed clause ending in the unmute wording unmuted the
        screen the person had just muted. Nothing is posted now, so there is
        nothing for that check to act on."""
        run(r'''
h.run(2000, {loud: true});
h.final('and then unmute');
h.mute();
assert(h.pending().length === 0, 'the mute throws it away');
// Long enough for the outer cap to trip as well, which is how this one used to
// get out while the microphone sat cut and recognition was not even running.
h.run(40000);
assert(h.sent.length === 0, 'nothing reaches the server to be read as unmute, got ' + JSON.stringify(h.sent));
''')

    def test_the_gate_stops_the_moment_the_button_is_pressed(self):
        """The window between the press and the drop.

        route goes to off the instant the button is pressed, but the drop runs
        in applyRouteSideEffects, which changeRoute only reaches after two round
        trips to the server. The gate keeps ticking through them, so a queue one
        tick away from clearing its wait went out inside that window, before
        anything had a chance to throw it away."""
        run('''
h.run(2000, {loud: true});
h.final('one more thing');
h.pressed();               // route goes off, the server has not answered yet
h.run(6000);
assert(h.sent.length === 0, 'the gate holds while the screen says off, got ' + JSON.stringify(h.sent));
h.mute();                  // the answer lands and the side effects run
assert(h.pending().length === 0, 'and then it is thrown away');
''')

    def test_a_route_change_that_rolls_back_keeps_the_queue(self):
        """Only a mute that really landed throws anything away. changeRoute
        rolls a failed switch back through applyRouteSideEffects(prev), and the
        clauses waiting out their quiet are still wanted there."""
        run('''
h.run(2000, {loud: true});
h.final('one more thing');
h.unmute();                // the rollback path, with nothing muted
assert(h.pending().length === 1, 'nothing is thrown away, got ' + JSON.stringify(h.pending()));
h.run(4000);
assert(h.sent.length === 1 && h.sent[0] === 'one more thing', 'and it still goes out');
''')

    def test_the_on_device_entry_drops_it_too(self):
        """That entry keeps recognizing through the mute, so it takes the other
        branch of applyRouteSideEffects. The queue is dropped ahead of both."""
        run(r'''
h.onDevice(true);
h.run(2000, {loud: true});
h.final('still here');
h.mute();
assert(h.pending().length === 0, 'dropped on the on-device entry as well');
h.run(20000);
assert(h.sent.length === 0, 'nothing goes out, got ' + JSON.stringify(h.sent));
''')

    def test_what_was_dropped_is_said_and_said_once(self):
        run(r'''
h.run(2000, {loud: true});
h.final('one more thing');
h.mute();
assert(h.said.length === 1, 'the line goes up once, got ' + JSON.stringify(h.said));
assert(/threw it away/.test(h.said[0]), 'it says what happened: ' + h.said[0]);
assert(/muted/.test(h.said[0]), 'and still says how to come back: ' + h.said[0]);
assert(h.drop() === false, 'an empty queue drops nothing');
assert(h.said.length === 1, 'and says nothing the second time');
h.unmute();
assert(h.note() === false, 'the note is done once the mic is back');
''')

    def test_muting_with_nothing_queued_says_nothing(self):
        run(r'''
h.run(2000, {loud: true});
h.mute();
assert(h.said.length === 0, 'no line when there was nothing to throw away');
''')

    def test_the_gate_still_sends_when_no_one_muted(self):
        """The cost of the above, which must be none."""
        run(r'''
h.run(2000, {loud: true});
h.final('first');
h.final('second');
h.run(4000);
assert(h.sent.length === 1 && h.sent[0] === 'first second',
       'quiet still sends, joined, got ' + JSON.stringify(h.sent));
''')


class SpokenMuteTest(unittest.TestCase):
    def test_the_spoken_mute_drops_what_is_queued_and_still_goes_out_at_once(self):
        """It used to flush those clauses out ahead of the mute word. The same
        queue in the same state now ends the same way whichever way the mute was
        made, and the mute itself is still ungated."""
        run(r'''
h.run(2000, {loud: true});
h.final('the part before it');
h.final('mute');
assert(h.sent.length === 1 && h.sent[0] === 'mute',
       'only the mute goes out, and without waiting, got ' + JSON.stringify(h.sent));
assert(h.pending().length === 0, 'nothing left waiting');
assert(h.stream() === '', 'and nothing of it left on screen');
assert(h.said.length === 1 && /threw it away/.test(h.said[0]), 'said: ' + JSON.stringify(h.said));
h.run(20000);
assert(h.sent.length === 1, 'and nothing follows it out, got ' + JSON.stringify(h.sent));
''')

    def test_a_mute_for_another_machine_leaves_the_queue_alone(self):
        """With several machines listening, the name at the front is what picks
        the one that moves. matchingTailWord knows the wordings and not the
        names, so a mute said to the machine across the room reads as a mute
        here as well, and throwing the queue away on it loses the words for a
        mute that never happens on this screen."""
        run(r'''
h.multi(true, ['dev']);
h.run(2000, {loud: true});
h.final('the part before it');
h.final('other mute');                 // a name that is not ours
assert(h.pending().length === 1, 'the queue is untouched, got ' + JSON.stringify(h.pending()));
assert(h.note() === false, 'and nothing says anything was thrown away');
h.run(4000);
assert(h.sent.includes('the part before it'), 'and it still goes out, got ' + JSON.stringify(h.sent));
''')

    def test_a_bare_mute_with_several_machines_leaves_the_queue_alone(self):
        """A wording carrying no name moves nothing at all over there
        (apply_voice_command leaves cmd_text empty), so it must move nothing
        here either."""
        run(r'''
h.multi(true, ['dev']);
h.run(2000, {loud: true});
h.final('the part before it');
h.final('mute');
assert(h.pending().length === 1, 'the queue is untouched, got ' + JSON.stringify(h.pending()));
h.run(4000);
assert(h.sent.includes('the part before it'), 'and it still goes out, got ' + JSON.stringify(h.sent));
''')

    def test_a_mute_carrying_this_machines_name_still_drops(self):
        """The one that really is about to cut this microphone."""
        run(r'''
h.multi(true, ['dev']);
h.run(2000, {loud: true});
h.final('the part before it');
h.final('dev mute');
assert(h.pending().length === 0, 'thrown away, got ' + JSON.stringify(h.pending()));
assert(h.sent.length === 1 && h.sent[0] === 'dev mute', 'sent: ' + JSON.stringify(h.sent));
assert(h.note() === true, 'and it is said');
''')

    def test_the_note_does_not_outlive_a_mute_that_never_landed(self):
        """The wording goes out before anything is known about it, so the note
        is set for a mute the server may never act on (the lease had moved on,
        the send failed). More speech queued afterwards is the mic plainly
        still being live, and a later mute with nothing waiting would otherwise
        say that something was thrown away when nothing was."""
        run(r'''
h.multi(true, ['dev']);
h.run(2000, {loud: true});
h.final('the part before it');
h.final('dev mute');                   // dropped, and the note goes up
assert(h.note() === true, 'the note is up');
h.final('still talking');              // nothing muted, so this queues as usual
assert(h.note() === false, 'and the note is gone again');
h.run(4000);
assert(h.sent.includes('still talking'), 'sent: ' + JSON.stringify(h.sent));
h.mute();                              // a real mute now, with nothing waiting
assert(h.said.filter(s => /threw it away/.test(s)).length === 1,
       'only the first one said it, got ' + JSON.stringify(h.said));
''')



class MutedScreenTest(unittest.TestCase):
    def test_the_line_is_empty_while_muted(self):
        """paintPendingBrowserSends and onend both read this. Answered here, the
        pre-mute text cannot flash back between paints, and resumeSnapshot
        (pending) cannot carry it into the draft box across a reload either."""
        run(r'''
const live = make({route: 'live', pending: ['queued'], interim: 'being said'});
assert(live() === 'queued being said', 'live: ' + live());
const off = make({route: 'off', pending: ['queued'], interim: 'being said'});
assert(off() === '', 'muted shows nothing, got ' + JSON.stringify(off()));
''', harness=STREAM)


if __name__ == "__main__":
    unittest.main()
