"""An utterance that goes nowhere has to say so, and a dead recognizer restarts.

The server takes an utterance in and lets it go again for reasons the page
never showed (under the floor on length, a word on the ignore list, a cut
microphone, nothing left after the dictionary). It answers 200 either way, so
the words simply vanished off the screen with nothing said about them. And
browser recognition that dies without an end event leaves the page wanting to
listen with nothing listening, where only a reload used to help.

The pieces are cut out of viewer.js and run under node with stand-ins for the
page, the same way test_reload_resume.py does it.
"""
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIEWER_JS = ROOT / "skills/voice-shell/scripts/viewer.js"

HARNESS = r"""
const fs = require('fs');
const source = fs.readFileSync(process.argv[1], 'utf8');
function slice(from, to) {
  const start = source.indexOf(from);
  const end = source.indexOf(to, start);
  if (start < 0 || end < 0) process.exit(2);
  return source.slice(start, end);
}
const assert = (cond, what) => { if (!cond) { console.error(what); process.exit(1); } };
const sending = new Function('env', `
  let asrOwnsLease = env.asrOwnsLease !== false;
  let asrConflict = env.asrConflict || null;
  let dropNextLocal = false, lastVoiceAt = 0;
  const el = {hint: {textContent: ''}};
  // The real one holds the line against paint(), which rewrites it every 3
  // seconds. Recorded here so a test can tell a held line from a bare write.
  let held = 0;
  const say = (text, sec = 6) => { el.hint.textContent = text; held = sec; };
  const t = key => 'said(' + key + ')';
  const post = (url, body) => { env.posted.push(body); return Promise.resolve(env.res); };
  const setAsrConflict = () => { asrConflict = {}; };
  const loadEngines = () => {};
  const spokenLang = () => 'en';
  const tabId = 'one-tab';
  ${slice("/* Why an utterance the server took in went nowhere",
          "/* Tell the server that we really are listening right now.")}
  return {sendUtterance, hint: () => el.hint.textContent,
          held: () => held, chain: () => sendChain};
`);
const stalling = new Function(`
  ${slice("const REC_STALL_MS = 30000;", "function recWatchdogTick")}
  return {recStalledFor, REC_STALL_MS};
`);
/* The watch itself, with the page state it reads standing in as plain
   variables. recAliveAt lives with the rest of the recognition state in
   viewer.js (out of this slice on purpose: a start is what sets it), so it is
   declared here the same way the others are. */
const watching = new Function('env', `
  let rec = env.rec || null, recStarting = !!env.recStarting;
  let recWanted = env.recWanted !== false, recRunning = !!env.recRunning;
  let asrConflict = null, asrDeniedFlag = false;
  let recAliveAt = 0;
  const el = {hint: {textContent: ''}};
  let restarts = 0;
  const t = key => 'said(' + key + ')';
  const say = text => { el.hint.textContent = text; };
  const stopRecognition = () => { rec = null; recStarting = false; };
  // The real one stamps recAliveAt with performance.now() on its way in. The
  // watch has just stamped it with the same moment under its own name for the
  // clock, so under the fake clock here that write is left out rather than
  // dragged back to real time.
  const startRecognition = () => { restarts++; rec = {}; recStarting = true; };
  ${slice("const REC_STALL_MS = 30000;", "setInterval(() => recWatchdogTick")}
  return {
    tick: now => recWatchdogTick(now),
    // A start beginning, the way startRecognition marks it.
    startedAt: now => { rec = {}; recStarting = true; recAliveAt = now; },
    cameUp: () => { recStarting = false; recRunning = true; },
    restarts: () => restarts, REC_STALL_MS,
  };
`);
"""


def run(script):
    subprocess.run(["node", "-e", HARNESS + script, str(VIEWER_JS)], check=True)


class DroppedIsVisibleTest(unittest.TestCase):
    def test_every_silent_reason_lands_on_screen(self):
        run(r"""
const reasons = {too_short: 'dropTooShort', noise: 'dropNoise',
                 muted: 'dropMuted', empty: 'dropEmpty'};
(async () => {
  for (const [why, key] of Object.entries(reasons)) {
    const env = {posted: [], res: {status: 200, ok: true,
                                   json: async () => ({dropped: why})}};
    const h = sending(env);
    h.sendUtterance('something that went nowhere');
    await h.chain();
    assert(env.posted.length === 1, 'it was sent for ' + why);
    assert(h.hint() === 'said(' + key + ')', why + ' says ' + h.hint());
    // Held, not written straight onto the line. paint() puts the ordinary
    // wording back every 3 seconds, so a bare write is a line the person
    // talking rather than watching never gets to see.
    assert(h.held() > 3, why + ' is held only ' + h.held() + 's');
  }
})();
""")

    def test_one_that_arrived_says_nothing_new(self):
        run(r"""
(async () => {
  const env = {posted: [], res: {status: 200, ok: true,
                                 json: async () => ({time: '10:00:00', text: 'hello'})}};
  const h = sending(env);
  h.sendUtterance('a long enough utterance');
  await h.chain();
  assert(h.hint() === '', 'nothing is said about one that arrived');
})();
""")


class RecognitionStallTest(unittest.TestCase):
    def test_a_session_that_is_open_and_never_came_up_counts_up(self):
        run(r"""
const h = stalling();
const s = {held: true, recWanted: true, recRunning: false, conflict: false,
           denied: false, aliveAt: 0};
assert(h.recStalledFor(1000, s) === 1000, 'it counts from the last time it ran');
assert(h.recStalledFor(h.REC_STALL_MS + 1, s) > h.REC_STALL_MS, 'past the limit');
""")

    def test_every_other_state_counts_as_alive(self):
        run(r"""
const h = stalling();
const s = {held: true, recWanted: true, recRunning: false, conflict: false,
           denied: false, aliveAt: 0};
const now = h.REC_STALL_MS * 10;
// Nothing was ever opened: a page nobody has touched yet is exactly this,
// and starting there would ask for a microphone with no gesture behind it
// and be refused, which switches browser recognition off altogether.
assert(h.recStalledFor(now, {...s, held: false}) === 0, 'nothing started yet');
assert(h.recStalledFor(now, {...s, recRunning: true}) === 0, 'running');
assert(h.recStalledFor(now, {...s, recWanted: false}) === 0, 'not wanted');
assert(h.recStalledFor(now, {...s, conflict: true}) === 0, 'another tab holds it');
assert(h.recStalledFor(now, {...s, denied: true}) === 0, 'the microphone was refused');
""")

    def test_a_start_is_measured_from_when_it_began_not_from_the_last_tick(self):
        # The watch is a plain setInterval, and this page is meant to be worked
        # beside, so it spends most of its life in a hidden tab where the
        # browser stretches those intervals out. Counted from the previous tick
        # instead of from the start itself, an ordinary session opened just
        # after one tick and sampled a minute later reads as a minute-old
        # stall, and a person mid-sentence has it folded up under them.
        run(r"""
const w = watching({});
assert(w.tick(0) === false, 'nothing open yet');
w.startedAt(55000);           // a session opens, well after that tick
assert(w.tick(60000) === false, 'a 5 second old start is not a stall');
assert(w.restarts() === 0, 'nothing was restarted');
w.cameUp();
assert(w.tick(65000) === false, 'and it came up');
""")

    def test_the_start_itself_is_what_stamps_the_moment_it_began(self):
        """Read off the source, since the arithmetic above is only right while
        something other than the watch's own tick stamps recAliveAt.

        startRecognition is the one way into the state the watch counts (rec is
        assigned nowhere else), so the stamp belongs beside the flag that opens
        that state. Left to the tick alone, the count measures the gap between
        two ticks instead of the age of the session, and a hidden tab stretches
        those gaps well past the limit.
        """
        source = VIEWER_JS.read_text(encoding="utf-8")
        at = source.index("recStarting = true;")
        after = source[at:at + 400]
        self.assertIn("recAliveAt = performance.now();", after)
        # And nowhere else does a session get opened behind its back.
        self.assertEqual(source.count("\n    rec = r;\n"), 1)

    def test_one_that_really_never_came_up_is_started_again_and_said_out_loud(self):
        run(r"""
const w = watching({});
w.startedAt(1000);
assert(w.tick(1000 + w.REC_STALL_MS - 1) === false, 'just inside the limit');
assert(w.tick(1000 + w.REC_STALL_MS) === true, 'past the limit it restarts');
assert(w.restarts() === 1, 'once, not over and over in the same tick');
// The next one is measured from this restart, not from the old start.
assert(w.tick(1000 + w.REC_STALL_MS + 1) === false, 'the count begins again');
""")


if __name__ == "__main__":
    unittest.main()
