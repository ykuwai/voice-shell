"""The send gate against a recognizer that runs behind the speech.

Chrome's on device recognition (processLocally) hands back a clause seconds
after the audio it covers. The gate read that quiet as the end of the thought,
sent what it already had, and let the late tail go out on its own as a second
prompt. The whole gate block is cut out of viewer.js and driven under node on a
made up clock, the same way test_on_device.py and test_reload_resume.py cut
theirs out. The clause text is kept to plain letters here: node reads the
script off the command line and the console encoding mangles anything else.
"""
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIEWER_JS = ROOT / "skills/voice-shell/scripts/viewer.js"

HARNESS = r'''
const fs = require('fs');
const source = fs.readFileSync(process.argv[1], 'utf8');
const start = source.indexOf('const BROWSER_SEND_GATE_MS = 100;');
const end = source.indexOf('/* Settled utterances go to the server.', start);
if (start < 0 || end < 0) process.exit(2);
const body = source.slice(start, end);

// Everything the block reaches for that lives elsewhere in the page. The clock
// is ours, so a test spends seconds without waiting any.
const make = new Function(`
  let clock = 0;
  const performance = {now: () => clock};
  const setInterval = () => 0;
  const sent = [];
  let rms = 0, engine = 'browser', onDeviceLocal = true, route = 'live';
  let carryDraft = false, recWanted = true, recRunning = true, recStarting = false;
  let dropNextLocal = false;
  const tuning = {silence_duration: 3.0, silence_threshold: 0.015};
  const computeBrowserRms = () => rms;
  const asrActive = () => true;
  const paintGauge = () => {};
  const clauseJoin = () => '+';
  const browserStreamText = () => '';
  const matchingTailWord = () => null;
  const sendUtterance = text => sent.push(text);
  const el = {stream: {}, tray: {classList: {remove() {}}}};
  const streamTail = () => {};
  \${body}
  return {
    // the clock moves in gate sized steps, ticking the gate at each one
    run(ms, opts = {}) {
      for (let i = 0; i < Math.round(ms / BROWSER_SEND_GATE_MS); i++) {
        clock += BROWSER_SEND_GATE_MS;
        rms = opts.loud ? 0.1 : 0;
        if (opts.interim) lastLoudAt = lastInterimChangeAt = clock;
        browserGateTick();
      }
    },
    final(text) { queueOrSendFinal(text); },
    now: () => clock,
    sent,
    pending: () => pendingBrowserSends.map(p => p.text),
    set(k, v) { eval(k + ' = v'); },
  };
`.replace('${body}', body));
const assert = (cond, what) => { if (!cond) { console.error(what); process.exit(1); } };
const h = make();
'''


def run(script):
    subprocess.run(["node", "-e", HARNESS + script, str(VIEWER_JS)], check=True)


class SendGateLagTest(unittest.TestCase):
    def test_a_tail_that_arrives_after_the_quiet_joins_what_it_belongs_with(self):
        """The on device case the user hit: one thought split into two prompts.

        Recognition runs about four seconds behind. The first clause comes back
        while the second is still being spoken. Then the speaking stops, and the
        three second wait runs out before the recognizer has handed over the
        rest of the sentence at all.
        """
        run(r'''
h.run(4000, {loud: true});
h.final('first half');          // said four seconds ago
h.run(3000, {loud: true});      // the second half is being spoken
h.run(3200);                    // quiet, and the wait runs out
assert(h.sent.length === 0, 'nothing may go out while the recognizer still owes words, got ' + JSON.stringify(h.sent));
h.final('second half');         // the tail, late
h.run(3000);
assert(h.sent.length === 1, 'one prompt, not one per clause, got ' + JSON.stringify(h.sent));
assert(h.sent[0] === 'first half+second half', 'joined in order, got ' + h.sent[0]);
''')

    def test_the_ordinary_browser_path_is_left_alone(self):
        """The same timeline off the local entry, sending on the old schedule."""
        run(r'''
h.set('onDeviceLocal', false);
h.run(4000, {loud: true});
h.final('first half');
h.run(3000, {loud: true});
h.run(2500);
assert(h.sent.length === 0, 'still inside the wait');
h.run(1000);
assert(h.sent.length === 1, 'the cloud path sends on quiet alone, got ' + JSON.stringify(h.sent));
assert(h.sent[0] === 'first half', 'the one clause it had');
''')

    def test_a_noise_after_the_last_word_does_not_hold_it_forever(self):
        """A clack with no words behind it waits out the bound, not the cap."""
        run(r'''
h.run(2000, {loud: true});
h.final('all said');
h.run(500);
h.run(100, {loud: true});       // one loud tick the recognizer has nothing to say about
h.run(3000);
assert(h.sent.length === 0, 'inside the bound it waits for the words that never come');
h.run(3500);
assert(h.sent.length === 1, 'released within twice the wait, got ' + JSON.stringify(h.sent));
''')

    def test_draft_mode_still_lands_on_its_own_short_wait(self):
        run(r'''
h.set('route', 'hold');
h.run(2000, {loud: true});
h.final('to the box');
h.run(4500);
assert(h.sent.length === 1, 'draft mode lands within twice its two second cap, got ' + JSON.stringify(h.sent));
''')

    def test_the_cap_still_trips_on_a_level_that_never_drops(self):
        run(r'''
// A noise floor above the trigger mark: loud forever, no words at all.
h.final('stuck');
h.run(40000, {loud: true});
assert(h.sent.length === 1, 'the cap released it, got ' + JSON.stringify(h.sent));
''')


if __name__ == "__main__":
    unittest.main()
