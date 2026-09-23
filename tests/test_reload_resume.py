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
/* The fold itself comes along, since what comes back out of storage is folded
   on the way in (a page that went away before the fold existed wrote the
   snapshot wide). */
const fold = source.slice(source.indexOf('// Full-width Latin letters and digits'),
                          source.indexOf('const TAIL_IDS = '));
const make = new Function('env', `
  ${fold}
  let {route, recWanted, draftTouched, seeded} = env;
  let sendingDraft = !!env.sendingDraft;
  let discardingDraft = !!env.discardingDraft;
  const el = env.el;
  const browserStreamText = () => env.stream;
  const paintDraft = () => {}, grow = () => {};
  ${body}
  return {resumeSnapshot, takeResume, restoreDraft, mergeHeld,
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
    def test_snapshot_records_live_draft_and_pending(self):
        run(r'''
const env = {route: 'live', recWanted: true, draftTouched: true, seeded: false,
             el: {draft: {value: 'typed'}}, stream: 'still waiting'};
const h = make(env);
let s = h.resumeSnapshot();
assert(s.live === true && s.draft === 'typed' && s.touched === true, 'fields');
assert(s.pending === 'still waiting', 'pending');
assert(typeof s.at === 'number', 'at');
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
assert(h.state().draftTouched === true, 'touched');
// The held lines from the server still get their one look (mergeHeld)
assert(h.state().seeded === false, 'seeding left to refreshState');

const el2 = {draft: {value: ''}};
const h2 = make({el: el2, draftTouched: false, seeded: false});
h2.restoreDraft({draft: '', pending: '  ', touched: false});
assert(el2.draft.value === '' && h2.state().seeded === false, 'nothing to restore');
''')

    def test_box_being_sent_is_not_carried_across(self):
        run(r'''
const env = {route: 'live', recWanted: true, draftTouched: true,
             el: {draft: {value: 'on its way'}}, stream: 'next words',
             sendingDraft: true};
const s = make(env).resumeSnapshot();
assert(s.draft === '' && s.touched === false, 'sent box left out: ' + s.draft);
assert(s.pending === 'next words', 'what is still being said stays');
''')

    def test_box_being_discarded_is_not_carried_across(self):
        run(r'''
const env = {route: 'live', recWanted: true, draftTouched: true,
             el: {draft: {value: 'thrown away'}}, stream: 'next words',
             discardingDraft: true};
const s = make(env).resumeSnapshot();
assert(s.draft === '' && s.touched === false, 'discarded box left out: ' + s.draft);
assert(s.pending === 'next words', 'what is still being said stays');
// And the reload after it has nothing of the discarded box to put back
const el = {draft: {value: ''}};
make({el, draftTouched: false, seeded: false}).restoreDraft(s);
assert(el.draft.value === 'next words', 'only the pending words: ' + el.draft.value);
''')

    def test_held_lines_merge_without_doubling(self):
        run(r'''
const el = {draft: {value: 'a\nb'}};
const h = make({el});
h.mergeHeld([{text: 'b'}, {text: ' c '}, {text: ''}, null]);
assert(el.draft.value === 'a\nb\nc', 'only the new one added: ' + JSON.stringify(el.draft.value));
h.mergeHeld([{text: 'a'}]);
assert(el.draft.value === 'a\nb\nc', 'nothing new, nothing changes');
const el2 = {draft: {value: ''}};
make({el: el2}).mergeHeld([{text: 'x'}, {text: 'y'}]);
assert(el2.draft.value === 'x\ny', 'empty box takes them all');
''')

    def test_what_comes_back_into_the_box_is_folded(self):
        """The box is filled from three places that are not the live stream.

        All three carry text written somewhere else (the snapshot the page that
        went away left behind, and the lines the server held), so a full-width
        「ｗｉ－ｆｉ」 from either of them sat in the unsent card while the live
        transcript above it had already folded the same words.
        """
        run(r'''
const el = {draft: {value: ''}};
const h = make({el, draftTouched: false, seeded: false});
h.restoreDraft({draft: 'ｗｉ－ｆｉ', pending: 'ＰＲ ｔｅｓｔ', touched: false});
assert(el.draft.value === 'wi-fi\nPR test', 'restored folded: ' + el.draft.value);

// The box already holds the folded line, so its full-width twin is the same
// line and must not be added a second time.
const el2 = {draft: {value: 'wi-fi'}};
const h2 = make({el: el2});
h2.mergeHeld([{text: 'ｗｉ－ｆｉ'}, {text: 'ＰＲ'}]);
assert(el2.draft.value === 'wi-fi\nPR', 'merged folded, once: ' + el2.draft.value);
''')

    def test_startup_and_route_paths_share_side_effects(self):
        source = VIEWER_JS.read_text(encoding="utf-8")
        # Held off at startup is a real off, not only on screen
        startup = source.split("loadEngines().then(() => {", 1)[1].split("\n});\n", 1)[0]
        self.assertIn("if (resume?.live)", startup)
        self.assertIn("autoResumed = true", startup)
        held = startup.split("armPending = true;", 1)[1]
        self.assertIn("applyRouteSideEffects('off')", held)
        # Polling out of off goes through the same side effects
        refresh = source.split("async function refreshState()", 1)[1].split("\n}\n", 1)[0]
        self.assertIn("if (prevRoute === 'off' && route !== 'off') applyRouteSideEffects(route)",
                      refresh)
        # And into off too (muted from another screen during the reload)
        self.assertIn("else if (prevRoute !== 'off' && route === 'off') applyRouteSideEffects('off')",
                      refresh)
        # The held lines are merged, not skipped when the box was restored
        self.assertIn("mergeHeld(s.held)", refresh)
        # sendDraft marks the box as on its way for the whole POST
        send = source.split("async function sendDraft(", 1)[1].split("\n}\n", 1)[0]
        self.assertLess(send.index("sendingDraft = true"), send.index("await post('/api/send'"))
        self.assertIn("finally {\n    sendingDraft = false;", send)
        # Discard marks the box as on its way out for the whole POST too
        discard = source.split("el.discard.onclick = async () => {", 1)[1].split("\n};\n", 1)[0]
        self.assertLess(discard.index("discardingDraft = true"),
                        discard.index("await post('/api/discard')"))
        self.assertIn("finally {\n    discardingDraft = false;", discard)
        self.assertLess(discard.index("discardingDraft = false"),
                        discard.index("el.draft.value = ''"))
        # The touch asks the server rather than starting against a local off
        arm = source.split("const arm = ev => {", 1)[1].split("};", 1)[0]
        self.assertIn("refreshState()", arm)
        # A touch ends the unattended start, so a later refusal is shown as one
        self.assertIn("autoResumed = false", arm)
        # So does a start that gives up before recognition opens
        start = source.split("async function startRecognition()", 1)[1].split("\n}\n", 1)[0]
        self.assertIn("if (!canBrowserASR || !recWanted) autoResumed = false;", start)
        self.assertGreaterEqual(start.count("autoResumed = false"), 3)
        # A refusal of the unattended start falls back to touch-to-start
        denied = source.split("ev.error === 'not-allowed'", 1)[1].split("disableBrowserASR", 1)[0]
        self.assertIn("if (autoResumed)", denied)
        self.assertIn("armPending = true", denied)


if __name__ == "__main__":
    unittest.main()
