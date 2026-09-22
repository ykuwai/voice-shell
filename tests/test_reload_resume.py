"""A reload carries on where it left off (#118).

The viewer writes what it had going to sessionStorage on pagehide and reads
it back once on startup. The pieces that do that are cut out of viewer.js and
run under node with stand-ins for the page, the same way test_asr_lease.py
does it.
"""
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIEWER_JS = ROOT / "skills/voice-shell/scripts/viewer.js"

HARNESS = r'''
const fs = require('fs');
const source = fs.readFileSync(process.argv[1], 'utf8');
const start = source.indexOf("const RESUME_KEY = 'vs.resume';");
const end = source.indexOf("addEventListener('pagehide'", start);
if (start < 0 || end < 0) process.exit(2);
const body = source.slice(start, end);
const make = new Function('env', `
  let {route, recWanted, draftTouched, seeded} = env;
  const el = env.el;
  const browserStreamText = () => env.stream;
  const floatingWindow = () => env.floating;
  const paintDraft = () => {}, grow = () => {};
  ${body}
  return {resumeSnapshot, takeResume, restoreDraft,
          setFloatAtReload: v => { floatAtReload = v; },
          state: () => ({draftTouched, seeded})};
`);
class Store {
  constructor() { this.m = new Map(); }
  getItem(k) { return this.m.has(k) ? this.m.get(k) : null; }
  setItem(k, v) { this.m.set(k, String(v)); }
  removeItem(k) { this.m.delete(k); }
}
const assert = (cond, what) => { if (!cond) { console.error(what); process.exit(1); } };
'''


def run(script):
    subprocess.run(["node", "-e", HARNESS + script, str(VIEWER_JS)], check=True)


class ReloadResumeTest(unittest.TestCase):
    def test_snapshot_records_live_draft_pending_and_float(self):
        run(r'''
const env = {route: 'live', recWanted: true, draftTouched: true, seeded: false,
             el: {draft: {value: 'typed'}}, stream: 'still waiting', floating: null};
const h = make(env);
let s = h.resumeSnapshot();
assert(s.live === true && s.draft === 'typed' && s.touched === true, 'fields');
assert(s.pending === 'still waiting' && s.float === false, 'pending/float');
assert(typeof s.at === 'number', 'at');
// The button closes the small window before the reload, so what it noted wins
h.setFloatAtReload(true);
assert(h.resumeSnapshot().float === true, 'float noted by the button');
// Muted, or on a local engine (the daemon listens, recWanted is false): not live
assert(make({...env, route: 'off'}).resumeSnapshot().live === false, 'off');
assert(make({...env, recWanted: false}).resumeSnapshot().live === false, 'daemon');
''')

    def test_take_reads_once_and_drops_stale_or_broken(self):
        run(r'''
const h = make({el: {draft: {value: ''}}});
const st = new Store();
st.setItem('vs.resume', JSON.stringify({live: true, at: 1000}));
const r = h.takeResume(st, 1000 + 29000);
assert(r && r.live === true, 'fresh one is read');
assert(st.getItem('vs.resume') === null, 'removed after reading');
assert(h.takeResume(st, 1000) === null, 'nothing the second time');
st.setItem('vs.resume', JSON.stringify({live: true, at: 1000}));
assert(h.takeResume(st, 1000 + 31000) === null, 'older than 30s is ignored');
assert(st.getItem('vs.resume') === null, 'stale one is removed too');
st.setItem('vs.resume', '{nope');
assert(h.takeResume(st, 0) === null, 'junk is ignored');
st.setItem('vs.resume', JSON.stringify({live: true}));
assert(h.takeResume(st, 0) === null, 'no timestamp is ignored');
const broken = {getItem() { throw new Error('denied'); }, removeItem() {}};
assert(h.takeResume(broken, 0) === null, 'storage that throws');
''')

    def test_restore_puts_draft_back_with_pending_after_it(self):
        run(r'''
const el = {draft: {value: ''}};
const h = make({el, draftTouched: false, seeded: false});
h.restoreDraft({draft: 'first line\n', pending: 'not sent yet', touched: true});
assert(el.draft.value === 'first line\nnot sent yet', 'joined: ' + el.draft.value);
assert(h.state().draftTouched === true && h.state().seeded === true, 'flags');

const el2 = {draft: {value: ''}};
const h2 = make({el: el2, draftTouched: false, seeded: false});
h2.restoreDraft({draft: '', pending: '  ', touched: false});
assert(el2.draft.value === '' && h2.state().seeded === false,
       'nothing to restore leaves the held-line seeding alone');
''')

    def test_startup_and_route_paths_share_side_effects(self):
        source = VIEWER_JS.read_text(encoding="utf-8")
        # Held off at startup is a real off, not only on screen
        startup = source.split("loadEngines().then(() => {", 1)[1].split("});", 1)[0]
        self.assertIn("if (resume?.live)", startup)
        self.assertIn("autoResumed = true", startup)
        held = startup.split("armPending = true;", 1)[1]
        self.assertIn("applyRouteSideEffects('off')", held)
        # Polling out of off goes through the same side effects
        refresh = source.split("async function refreshState()", 1)[1].split("\n}\n", 1)[0]
        self.assertIn("if (prevRoute === 'off' && route !== 'off') applyRouteSideEffects(route)",
                      refresh)
        # The touch asks the server rather than starting against a local off
        arm = source.split("const arm = ev => {", 1)[1].split("};", 1)[0]
        self.assertIn("refreshState()", arm)
        # A refusal of the unattended start falls back to touch-to-start
        denied = source.split("ev.error === 'not-allowed'", 1)[1].split("disableBrowserASR", 1)[0]
        self.assertIn("if (autoResumed && !vizArmed)", denied)
        self.assertIn("armPending = true", denied)


if __name__ == "__main__":
    unittest.main()
