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
  const t = key => 'said(' + key + ')';
  const post = (url, body) => { env.posted.push(body); return Promise.resolve(env.res); };
  const setAsrConflict = () => { asrConflict = {}; };
  const loadEngines = () => {};
  const spokenLang = () => 'en';
  const tabId = 'one-tab';
  ${slice("/* Why an utterance the server took in went nowhere",
          "/* Tell the server that we really are listening right now.")}
  return {sendUtterance, hint: () => el.hint.textContent, chain: () => sendChain};
`);
const stalling = new Function(`
  ${slice("const REC_STALL_MS = 30000;", "function recWatchdogTick")}
  return {recStalledFor, REC_STALL_MS};
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
    def test_wanted_but_never_running_counts_up(self):
        run(r"""
const h = stalling();
const s = {recWanted: true, recRunning: false, conflict: false, denied: false, aliveAt: 0};
assert(h.recStalledFor(1000, s) === 1000, 'it counts from the last time it ran');
assert(h.recStalledFor(h.REC_STALL_MS + 1, s) > h.REC_STALL_MS, 'past the limit');
""")

    def test_every_other_state_counts_as_alive(self):
        run(r"""
const h = stalling();
const s = {recWanted: true, recRunning: false, conflict: false, denied: false, aliveAt: 0};
const now = h.REC_STALL_MS * 10;
assert(h.recStalledFor(now, {...s, recRunning: true}) === 0, 'running');
assert(h.recStalledFor(now, {...s, recWanted: false}) === 0, 'not wanted');
assert(h.recStalledFor(now, {...s, conflict: true}) === 0, 'another tab holds it');
assert(h.recStalledFor(now, {...s, denied: true}) === 0, 'the microphone was refused');
""")


if __name__ == "__main__":
    unittest.main()
