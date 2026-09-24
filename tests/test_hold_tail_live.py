"""A trailing 「手直し」 said on instant opens Edit this one around it.

The server held the line (held.jsonl) and told the screen so (voice_cmd
"held", the purple flash), but appendHeld threw away anything that arrived
outside hold mode, so the words vanished from the screen instead of landing in
the box. The held line now says it came from the tail, and only that one opens
the box on instant. A line held by the pause is still only taken in while the
page is already holding.

The server half is the one line both writers share and the watcher that
forwards it. The page half is cut out of viewer.js and run under node, the same
way test_mute_drops_queue.py does it. The text is kept to plain letters, since
node reads the script off the command line and the console encoding mangles
anything else.
"""
import asyncio
import json
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/voice-shell/scripts"
VIEWER_JS = SCRIPTS / "viewer.js"
sys.path.insert(0, str(SCRIPTS))
if "aiohttp" not in sys.modules:
    _aiohttp = types.ModuleType("aiohttp")
    _aiohttp.web = types.SimpleNamespace()
    _aiohttp.WSCloseCode = object()
    sys.modules["aiohttp"] = _aiohttp

import viewer  # noqa: E402
import voice_daemon as vd  # noqa: E402


class HeldLineTest(unittest.TestCase):
    def test_a_line_held_by_the_tail_says_so(self):
        rec = json.loads(vd.held_line("12:00:00", "fix this", True))
        self.assertEqual(rec, {"time": "12:00:00", "text": "fix this", "tail": True})

    def test_a_line_held_by_the_pause_looks_as_it_always_has(self):
        line = vd.held_line("12:00:00", "while paused")
        self.assertTrue(line.endswith("\n"))
        self.assertEqual(json.loads(line), {"time": "12:00:00", "text": "while paused"})
        self.assertEqual(json.loads(vd.held_line("12:00:00", "x", False)),
                         {"time": "12:00:00", "text": "x"})

    def test_both_writers_mark_it_by_force_hold(self):
        """The daemon's loop and handle_utterance sit inside functions that do
        not run on their own, so what they hand the helper is read off the
        source. force_hold is the trailing 「手直し」; the pause alone is not."""
        daemon = (SCRIPTS / "voice_daemon.py").read_text(encoding="utf-8")
        page_server = (SCRIPTS / "viewer.py").read_text(encoding="utf-8")
        self.assertIn("h.write(held_line(stamp, text, force_hold))", daemon)
        self.assertIn("vd.held_line(stamp, text, force_hold))", page_server)


class WatchHeldTest(unittest.TestCase):
    def test_only_the_tail_line_is_forwarded_with_tail(self):
        with tempfile.TemporaryDirectory() as d:
            state = Path(d)
            (state / "held.jsonl").write_text(
                vd.held_line("12:00:00", "while paused")
                + vd.held_line("12:00:01", "fix this", True), encoding="utf-8")
            tail = viewer.Tail(state / "utterances.jsonl")
            sent = []

            async def collect(rec):
                sent.append(rec)
                return True
            tail.broadcast_result = collect

            async def one_pass():
                try:
                    await asyncio.wait_for(tail.watch_held(), 0.1)
                except asyncio.TimeoutError:
                    pass
            asyncio.run(one_pass())
        self.assertEqual(sent, [{"held": "while paused"},
                                {"held": "fix this", "tail": True}])


# ── The WebSocket handler and appendHeld, driven together ──
HARNESS = r'''
const fs = require('fs');
const source = fs.readFileSync(process.argv[1], 'utf8');
const cut = (from, to) => {
  const start = source.indexOf(from);
  const end = source.indexOf(to, start);
  if (start < 0 || end < 0) process.exit(2);
  return source.slice(start, end);
};
const handler = cut('async function handleWsMessage(', '// Grow the height to fit');
const append = cut('function appendHeld(text) {', 'let engine = ');

const make = new Function('env', `
  let route = env.route, lastMode = 'live', oneShot = !!env.oneShot;
  let carryDraft = !!env.carryDraft, voiceSinceCarry = !!env.voiceSinceCarry;
  let routeQueue = Promise.resolve(), routeRevision = 0;
  let discardResultCutoff = 0;
  const dropBarriers = new Set();
  const routes = [], posts = [], sends = [];
  let scrolled = 0;
  // The real setRoute turns route over at once, and changeRoute rolls it
  // back (with oneShot, for live -> hold) once the server cannot be told.
  const setRoute = next => {
    const prev = route;
    routes.push(next);
    route = next;
    return Promise.resolve().then(() => {
      if (!env.failSwitch) return;
      route = prev;
      if (prev === 'live' && next === 'hold') oneShot = false;
    });
  };
  const post = (url, body) => { posts.push([url, body]); return Promise.resolve({ok: true}); };
  const sendDraft = opts => { sends.push(opts); carryDraft = false; };
  const clearSendCountdown = () => {};
  const asrActive = () => false, browserStreamText = () => '';
  const paintDraft = () => {}, grow = () => {};
  const timeLocale = () => 'en';
  const uiDoc = () => ({activeElement: null});
  const cls = {toggle() {}, add() {}, remove() {}};
  const el = {
    draft: {value: env.draft || '', scrollTop: 0, scrollHeight: 0},
    draftTime: {textContent: ''},
    stream: {textContent: ''},
    tray: {classList: cls, scrollIntoView() { scrolled++; }},
  };
  \${handler}
  \${append}
  return {
    held: (text, tail) => handleWsMessage({message: tail ? {held: text, tail: true} : {held: text},
                                           number: 1, discardInProgress: false}),
    state: () => ({route, oneShot, carryDraft, draft: el.draft.value, scrolled}),
    routes, posts, sends,
  };
`.replace('${handler}', handler).replace('${append}', append));
const assert = (cond, what) => { if (!cond) { console.error(what); process.exit(1); } };
(async () => {
'''
FOOTER = r'''
})().catch(e => { console.error(e); process.exit(1); });
'''


def run(script):
    subprocess.run(["node", "-e", HARNESS + script + FOOTER, str(VIEWER_JS)], check=True)


class InstantTailTest(unittest.TestCase):
    def test_the_tail_on_instant_opens_edit_this_one_with_the_words_in_it(self):
        """The shape the user hit: purple flash, and the words gone."""
        run(r'''
const h = make({route: 'live'});
await h.held('fix this part', true);
const s = h.state();
assert(JSON.stringify(h.routes) === '["hold"]', 'switched to hold once, got ' + JSON.stringify(h.routes));
assert(s.oneShot === true, 'as Edit this one, so sending goes back to instant');
assert(s.route === 'hold', 'holding, so what is said next lands in the same box');
assert(s.draft === 'fix this part', 'the words are in the box, got ' + JSON.stringify(s.draft));
assert(s.scrolled === 1, 'the box is brought into view the way editThisOne does');
''')

    def test_the_next_tail_joins_the_same_box(self):
        run(r'''
const h = make({route: 'live'});
await h.held('first', true);
await h.held('second', true);
assert(JSON.stringify(h.routes) === '["hold"]', 'no second switch');
assert(h.state().draft === 'first\nsecond', 'appended, got ' + JSON.stringify(h.state().draft));
''')

    def test_a_line_without_the_tail_on_instant_is_still_left_alone(self):
        """A held line nobody explains (left over from a pause) never opens the box."""
        run(r'''
const h = make({route: 'live'});
await h.held('from a pause', false);
const s = h.state();
assert(h.routes.length === 0, 'no switch');
assert(s.oneShot === false && s.route === 'live', 'still instant');
assert(s.draft === '', 'nothing in the box');
''')

    def test_on_hold_every_held_line_goes_in_as_before(self):
        run(r'''
const h = make({route: 'hold'});
await h.held('plain', false);
await h.held('with tail', true);
const s = h.state();
assert(h.routes.length === 0, 'already holding, no switch');
assert(s.oneShot === false, 'draft mode stays draft mode, not Edit this one');
assert(s.draft === 'plain\nwith tail', 'both in, got ' + JSON.stringify(s.draft));
''')

    def test_muted_it_is_not_opened(self):
        """The server drops a muted utterance before the tail is looked at, so
        none should come. One that slips in all the same opens nothing."""
        run(r'''
const h = make({route: 'off'});
await h.held('while muted', true);
assert(h.routes.length === 0 && h.state().draft === '' && !h.state().oneShot, 'left alone');
''')

    def test_a_switch_that_fails_keeps_the_words_on_screen(self):
        run(r'''
const h = make({route: 'live', failSwitch: true});
await h.held('fix this part', true);
const s = h.state();
assert(s.route === 'live' && s.oneShot === false, 'rolled back');
assert(s.draft === 'fix this part', 'but the words stay in the box, got ' + JSON.stringify(s.draft));
''')

    def test_the_tail_during_a_carry_keeps_the_box_open(self):
        """Back on instant with a draft still in the box, the next utterance
        takes it out. Ending that one in 「手直し」 asks for the opposite."""
        run(r'''
const h = make({route: 'hold', oneShot: true, carryDraft: true, voiceSinceCarry: true,
                draft: 'earlier draft'});
await h.held('and this', true);
const s = h.state();
assert(h.sends.length === 0, 'nothing sent, got ' + JSON.stringify(h.sends));
assert(s.carryDraft === false && s.oneShot === true, 'Edit this one, carry over');
assert(s.draft === 'earlier draft\nand this', 'both in the box');
assert(JSON.stringify(h.posts) === '[["/api/pause",{"paused":true}]]',
       'the daemon is told it is drafting again, not carrying, got ' + JSON.stringify(h.posts));
''')

    def test_without_the_tail_the_carry_goes_out_as_before(self):
        run(r'''
const h = make({route: 'hold', oneShot: true, carryDraft: true, voiceSinceCarry: true,
                draft: 'earlier draft'});
await h.held('and this', false);
assert(h.sends.length === 1 && h.sends[0].carry === true, 'sent with the carry');
''')


if __name__ == "__main__":
    unittest.main()
