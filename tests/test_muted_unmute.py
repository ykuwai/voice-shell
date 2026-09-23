"""Muted, and still listening, on the entry that recognizes on this device.

Chrome releases the microphone the moment a page stops recognition, so under
the plain browser entry the spoken "unmute" can never be heard. That is not
true of the on-device entry (processLocally): nothing leaves the machine, so
recognition can keep running through the mute exactly as the local engines do.

What it hears there is thrown away where it is heard. Nothing is posted,
nothing is logged, nothing reaches the screen or the draft box, and the one
thing acted on is the word that brings the mic back. The wordings, the lead-in
it tolerates, the kinds and single wordings switched off and the machine name
in front all follow the daemon, so the same sentence does the same thing
however it was recognized. That parity is what most of this file checks.
"""
import json
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/voice-shell/scripts"
VIEWER_JS = SCRIPTS / "viewer.js"
sys.path.insert(0, str(SCRIPTS))
if "aiohttp" not in sys.modules:
    _aiohttp = types.ModuleType("aiohttp")
    _aiohttp.web = types.SimpleNamespace()
    _aiohttp.WSCloseCode = object()
    sys.modules["aiohttp"] = _aiohttp

import voice_daemon as vd  # noqa: E402

# The eight the screen speaks. The page gathers its tables one language at a
# time from /api/commands and joins them, so this is the whole table it holds.
UI_LANGS = ("en", "ja", "es", "fr", "de", "zh", "zh-TW", "ko")


def page_unmute_words():
    out = []
    for lang in UI_LANGS:
        words = vd.builtin_words("unmute", lang) or vd.builtin_words("unmute", "en")
        out.extend(w.lower() for w in words)
    return sorted(set(out))


# ── The matcher, lifted out of the page and run on its own ──
PURE = r"""
const fs = require('fs');
const source = fs.readFileSync(process.argv[1], 'utf8');
const start = source.indexOf("// Full-width Latin letters and digits");
const end = source.indexOf("\n/* Whether what has been heard so far", start);
if (start < 0 || end < 0) process.exit(2);
const body = source.slice(start, end)
  .replace(/async function loadTailWords[\s\S]*?\n}\n/, '');
const make = new Function('words', 'off', `
  ${body}
  tailWords = words;
  takeCmdOff(off);
  return {unmuteCommand, matchingTailWord, stripMachineName};
`);
const sets = table => {
  const out = {};
  for (const k of Object.keys(table || {})) out[k] = new Set(table[k]);
  return out;
};
const assert = (cond, what) => { if (!cond) { console.error(what); process.exit(1); } };
"""


def run_node(script, *args):
    subprocess.run(["node", "-e", PURE + script, str(VIEWER_JS), *args], check=True)


class UnmuteMatchTest(unittest.TestCase):
    """The shape of the match, read straight off the page's own tables."""

    def test_wordings_lead_ins_and_the_everyday_words(self):
        run_node(r"""
const h = make(sets({unmute: ['ミュート解除', 'マイクオン', 'unmute', '解除']}), {});
const said = s => h.unmuteCommand(s, {});
for (const s of ['ミュート解除', 'はいミュート解除', 'えーとミュート解除', 'ミュート解除。', 'unmute'])
  assert(said(s), 'heard: ' + s);
// Three characters is the whole allowance (voice_daemon.UNMUTE_TAIL_NOISE_MAX)
assert(!said('そうですねミュート解除'), 'a real clause ahead of it is not noise');
// An everyday word only as the whole utterance, never with a lead-in
assert(said('解除'), 'the bare word said alone');
assert(!said('ロックを解除'), 'the bare word inside a sentence');
assert(!said('はい解除'), 'the bare word with a lead-in');
// It is asked for by name. The tail sweep the drawing uses must not pick it up,
// or a sentence ending in it would show as about to be thrown away.
assert(h.matchingTailWord('これを直して、ミュート解除') === null, 'stays out of the tail sweep');
""")

    def test_the_switch_offs_and_the_machine_name(self):
        run_node(r"""
const words = sets({unmute: ['ミュート解除', 'マイクオン']});
let h = make(words, {off: ['unmute']});
for (const s of ['ミュート解除', 'はいミュート解除', 'マイクオン'])
  assert(!h.unmuteCommand(s, {}), 'the kind is off: ' + s);
h = make(words, {off_words: {unmute: ['ミュート解除']}});
for (const s of ['ミュート解除', 'はいミュート解除'])
  assert(!h.unmuteCommand(s, {}), 'that one wording is off: ' + s);
assert(h.unmuteCommand('マイクオン', {}), 'the rest of the kind still brings it back');

h = make(words, {});
const opts = {multi: true, names: ['開発用', 'Ｍａｃ']};
assert(h.unmuteCommand('開発用ミュート解除', opts), 'this machine was named');
assert(h.unmuteCommand('開発用のミュート解除', opts), 'and the separator after the name comes off');
assert(h.unmuteCommand('macミュート解除', opts), 'a name typed full-width matches the folded text');
assert(!h.unmuteCommand('会議用ミュート解除', opts), 'the box next door is not this one');
assert(!h.unmuteCommand('ミュート解除', opts), 'and a name that is missing moves nothing');
assert(h.unmuteCommand('ミュート解除', {multi: false, names: ['開発用']}),
       'with the setting off the name is not wanted');

// The dictionary-rewritten form is asked about too, the same as the daemon
const fixup = s => s.split('ミュート回収').join('ミュート解除');
assert(!h.unmuteCommand('ミュート回収', {}), 'the garbled form on its own is nothing');
assert(h.unmuteCommand('ミュート回収', {fixup}), 'and is brought back by registering it');
""")


class DaemonParityTest(unittest.TestCase):
    """The page and the daemon answer the same for the same sentence.

    Every built-in wording, in every language the screen speaks, with and
    without a lead-in, and under each way of switching the signal off.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.patches = [
            mock.patch.object(vd, "COMMANDS_FILE", self.dir / "commands.json"),
            mock.patch.object(vd, "_cmd_cache", (None, None)),
            mock.patch.object(vd, "machine_config", lambda: (False, [])),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def switch_off(self, off):
        vd.COMMANDS_FILE.write_text(json.dumps(off, ensure_ascii=False),
                                    encoding="utf-8")
        vd._cmd_cache = (None, None)

    def test_every_wording_and_lead_in_agrees(self):
        words = page_unmute_words()
        leads = ["", "はい", "えーと", "um ", "それはもういいから"]
        scenarios = [
            {},
            {"off": ["unmute"]},
            {"off_words": {"unmute": ["ミュート解除", "unmute"]}},
        ]
        cases = []
        for off in scenarios:
            self.switch_off(off)
            wanted = []
            for w in words:
                for lead in leads:
                    text = lead + w
                    wanted.append([text, vd.voice_command(text, True) == "unmute"])
            cases.append({"off": off, "words": words, "cases": wanted})
        self.assertTrue(any(c[1] for s in cases for c in s["cases"]),
                        "the table cannot be empty or this proves nothing")
        path = self.dir / "cases.json"
        path.write_text(json.dumps(cases, ensure_ascii=False), encoding="utf-8")
        run_node(r"""
const sets2 = require('fs').readFileSync(process.argv[2], 'utf8');
for (const s of JSON.parse(sets2)) {
  const h = make(sets({unmute: s.words}), s.off);
  for (const [text, wanted] of s.cases) {
    const got = !!h.unmuteCommand(text, {});
    assert(got === wanted,
           'page ' + got + ' but daemon ' + wanted + ' for ' + JSON.stringify(text)
           + ' under ' + JSON.stringify(s.off));
  }
}
""", str(path))

    def test_the_machine_name_agrees(self):
        names = ["開発用", "mac"]
        with mock.patch.object(vd, "machine_config", lambda: (True, names)):
            texts = ["開発用ミュート解除", "開発用のミュート解除",
                     "macミュート解除", "会議用ミュート解除", "ミュート解除",
                     "開発用はいミュート解除"]
            wanted = [[s, vd.apply_voice_command(s, self.dir / "utterances.jsonl",
                                                 True, {"replace": {}}) == "unmute"]
                      for s in texts]
        path = self.dir / "named.json"
        path.write_text(json.dumps(
            [{"off": {}, "words": page_unmute_words(), "cases": wanted}],
            ensure_ascii=False), encoding="utf-8")
        run_node(r"""
const raw = require('fs').readFileSync(process.argv[2], 'utf8');
const names = ['開発用', 'mac'];
for (const s of JSON.parse(raw)) {
  const h = make(sets({unmute: s.words}), s.off);
  for (const [text, wanted] of s.cases) {
    const got = !!h.unmuteCommand(text, {multi: true, names});
    assert(got === wanted, 'named: ' + JSON.stringify(text) + ' page ' + got);
  }
}
""", str(path))


# ── What a settled utterance does while the mic is off ──
HEARD = r"""
const fs = require('fs');
const source = fs.readFileSync(process.argv[1], 'utf8');
const pureFrom = source.indexOf("// Full-width Latin letters and digits");
const pureTo = source.indexOf("\n/* Whether what has been heard so far", pureFrom);
const recFrom = source.indexOf('function newRecognition(generation)');
const recTo = source.indexOf('\n// When it can no longer be used', recFrom);
const sideFrom = source.indexOf('function applyRouteSideEffects(next)');
const sideTo = source.indexOf('\n/* The floating window is a separate document', sideFrom);
if ([pureFrom, pureTo, recFrom, recTo, sideFrom, sideTo].some(i => i < 0)) process.exit(2);
const pure = source.slice(pureFrom, pureTo)
  .replace(/async function loadTailWords[\s\S]*?\n}\n/, '');
const make = new Function('SR', 'env', `
  ${pure}
  tailWords = {unmute: new Set(env.words)};
  let canBrowserASR = true, recWanted = true, rec = null, recRunning = false;
  let recStarting = false, recGeneration = 0, recFails = 0, recStartedAt = 0;
  let route = env.route, asrDeniedFlag = false, lastVoiceAt = 0, autoResumed = false;
  let asrChosen = true, asrPausedByRoute = false, inFlight = false;
  let lastMode = 'live', onDeviceLocal = env.local;
  let lastLoudAt = 0, lastInterimChangeAt = 0, carryDraft = false, voiceSinceCarry = false;
  let lastFinalAt = 0, pendingBrowserSends = [];
  let latestInterimForPaint = '', lastInterimHeard = '';
  const MAX_FAILS = 6;
  const browserLang = () => 'ja-JP';
  const performance = {now: () => 1};
  const el = {stream: {textContent: ''}, tray: {classList: {toggle: () => {}, remove: () => {}, add: () => {}}},
              hint: {textContent: ''}, multiOn: {checked: false},
              machineName: {value: ''}};
  const machineNames = () => [];
  const withDict = v => v;
  const stripInventedSpaces = v => v;
  const streamTail = () => { env.painted.push('streamTail'); };
  const browserStreamText = () => '';
  const paintInterimThrottled = v => { env.painted.push('interim:' + v); };
  const paintTinyButtons = () => { env.painted.push('buttons'); };
  const paintPendingBrowserSends = () => { env.painted.push('pending'); };
  const flushPendingBrowserSends = () => {};
  const sendUtterance = t => { env.sent.push(t); };
  const queueOrSendFinal = t => { env.sent.push(t); };
  const disableBrowserASR = () => {};
  const holdOnDevice = () => {};
  const askOnDevice = async () => 'available';
  const onDeviceNow = () => 'available';
  const onDeviceRefused = false;
  const beat = async () => true;
  const setRoute = m => { env.routes.push(m); route = m; return Promise.resolve(); };
  const chime = s => { env.chimes.push(s); };
  const say = s => { env.said.push(s); };
  const flashCommand = (s, k) => { env.flashed.push([s, k]); };
  const t = k => k;
  const listensWhileMuted = () => asrChosen && onDeviceLocal;
  let interimThrottleTimer = null, vizArmed = false;
  const resetBrowserGesture = () => {};
  const startViz = () => {};
  const syncVizCapture = () => {};
  const paintBrowserAsr = () => {};
  ${source.slice(recFrom, recTo)}
  ${source.slice(sideFrom, sideTo)}
  return {make: () => { rec = newRecognition(0); return rec; },
          stream: () => el.stream.textContent,
          mute: () => { route = 'off'; applyRouteSideEffects('off'); },
          held: () => ({recWanted, live: !!rec, timer: interimThrottleTimer}),
          paintedAs: v => {
            el.stream.textContent = v;
            interimThrottleTimer = setTimeout(() => { el.stream.textContent = v; }, 1000);
          }};
`);
class FakeRecognition {
  constructor() { this.aborted = false; }
  start() {}
  stop() {}
  abort() { this.aborted = true; }
}
const finals = texts => ({
  resultIndex: 0,
  results: texts.map(text => { const r = [{transcript: text}]; r.isFinal = true; return r; }),
});
const interim = text => ({
  resultIndex: 0,
  results: [Object.assign([{transcript: text}], {isFinal: false})],
});
const freshEnv = (over) => Object.assign({
  route: 'off', local: true, words: ['ミュート解除'],
  sent: [], painted: [], routes: [], chimes: [], said: [], flashed: [],
}, over || {});
const assert = (cond, what) => { if (!cond) { console.error(what); process.exit(1); } };
"""


class HeardWhileMutedTest(unittest.TestCase):
    def run_heard(self, script):
        subprocess.run(["node", "-e", HEARD + script, str(VIEWER_JS)], check=True)

    def test_an_ordinary_sentence_leaves_no_trace(self):
        self.run_heard(r"""
const env = freshEnv();
const h = make(FakeRecognition, env);
const r = h.make();
r.onresult(interim('認証まわりを'));
r.onresult(finals(['認証まわりを直してください']));
assert(env.sent.length === 0, 'nothing was sent or queued');
assert(env.painted.length === 0, 'nothing was painted');
assert(h.stream() === '', 'nothing was left in the transcript box');
assert(env.routes.length === 0, 'and the mic stayed off');
assert(r.aborted === false, 'the session on this device keeps running');
""")

    def test_the_word_brings_the_mic_back_the_way_it_does_elsewhere(self):
        self.run_heard(r"""
const env = freshEnv();
const h = make(FakeRecognition, env);
h.make().onresult(finals(['はいミュート解除']));
assert(env.routes.join() === 'live', 'it went back to the mode it was in');
assert(env.chimes.join() === 'up', 'with the rising sound');
assert(env.said.join() === 'voiceUnmuted', 'and the line the local engines put up');
assert(env.flashed.length === 1 && env.flashed[0][1] === 'live', 'and the word lit up');
assert(env.sent.length === 0, 'the utterance itself still went nowhere');
""")

    def test_a_session_that_is_not_on_this_device_is_dropped_not_heard(self):
        # The promise hangs on the session, not on a flag somewhere else: if a
        # plain-entry session is somehow still open while the mic is off, what it
        # heard is thrown away and the session with it, rather than going to Google.
        self.run_heard(r"""
const env = freshEnv({local: false});
const h = make(FakeRecognition, env);
const r = h.make();
r.onresult(finals(['認証まわりを直して', 'ミュート解除']));
assert(r.aborted === true, 'the session is aborted');
assert(env.sent.length === 0 && env.routes.length === 0, 'and nothing it heard is acted on');
""")

    def test_muting_takes_what_was_on_screen_with_it(self):
        # Folding the session up was what used to clear the box. It is not
        # folded up any more, so the last words heard before the mute would sit
        # there under a screen that says muted, and a throttled paint still
        # waiting its turn would put them back a moment later.
        self.run_heard(r"""
const env = freshEnv({route: 'live'});
const h = make(FakeRecognition, env);
h.make();
h.paintedAs('\u8a8d\u8a3c\u307e\u308f\u308a\u3092');
assert(h.stream() !== '', 'something was on screen');
h.mute();
assert(h.stream() === '', 'the mute took it with it');
assert(h.held().timer === null, 'and the paint waiting its turn was dropped');
assert(h.held().recWanted === true && h.held().live === true,
       'while the session itself stays open');
""")

    def test_with_the_mic_on_everything_goes_through_as_before(self):
        self.run_heard(r"""
const env = freshEnv({route: 'live'});
const h = make(FakeRecognition, env);
const r = h.make();
r.onresult(finals(['認証まわりを直してください']));
assert(env.sent.length === 1, 'the clause is queued as it always was');
r.onresult(interim('つづき'));
assert(env.painted.some(p => p.startsWith('interim:')), 'and what is being said is drawn');
""")


class MutedSessionWiringTest(unittest.TestCase):
    """Where the decision "is a session open right now" is taken.

    Every one of these used to read route === 'off' on its own. Read that way
    in even one of them, the 5 second poll or an entry switch from another tab
    puts a cut mic back, or worse, opens a plain-entry session while the screen
    says muted.
    """

    def setUp(self):
        self.src = VIEWER_JS.read_text(encoding="utf-8")

    def test_one_predicate_decides_it(self):
        self.assertIn("const listensWhileMuted = () => asrChosen && onDeviceLocal;", self.src)
        self.assertIn("recWanted = asrChosen && (route !== 'off' || listensWhileMuted());",
                      self.src)
        # Nobody works it out for themselves any more
        self.assertNotIn("asrPausedByRoute = asrChosen && route === 'off';", self.src)
        self.assertNotIn("asrPausedByRoute = route === 'off';", self.src)

    def test_muting_keeps_the_on_device_session(self):
        self.assertIn("if (recWanted && !listensWhileMuted()) { asrPausedByRoute = true; stopRecognition(); }",
                      self.src)

    def test_a_session_may_open_while_muted_only_there(self):
        self.assertIn("|| (route === 'off' && !listensWhileMuted()) || rec) {", self.src)

    def test_the_entry_switch_from_another_tab_is_answered(self):
        follow = self.src.split("function followOnDeviceFlag()", 1)[1]
        follow = follow.split("restartRecognition();", 1)[0]
        self.assertIn("syncRecWanted();", follow)

    def test_the_five_second_poll_is_answered(self):
        engines = self.src.split("async function loadEngines()", 1)[1]
        engines = engines.split("if (was && !asrChosen)", 1)[0]
        self.assertIn("syncRecWanted();", engines)

    def test_what_is_heard_while_off_never_reaches_the_rest_of_the_page(self):
        on_result = self.src.split("r.onresult = ev => {", 1)[1]
        muted = on_result.split("let interim = '';", 1)[0]
        # The whole muted branch, and nothing in it but the one call
        self.assertIn("if (r.processLocally !== true) { try { r.abort(); } catch {} return; }",
                      muted)
        self.assertIn("heardWhileMuted(", muted)
        for leak in ("queueOrSendFinal", "paintInterimThrottled", "el.stream",
                     "lastVoiceAt", "lastLoudAt", "pendingBrowserSends"):
            self.assertNotIn(leak, muted)

    def test_the_screen_says_what_is_true_of_the_entry_in_use(self):
        self.assertIn("t(asrChosen && !listensWhileMuted() ? 'voiceMutedBrowser' : 'voiceMuted')",
                      self.src)
        self.assertIn("const deadHere = g.id === 'unmute' && asrChosen && !onDeviceLocal;",
                      self.src)


class WordingTest(unittest.TestCase):
    """The line that says the word cannot be heard is now only about one entry."""

    def test_every_language_carries_both_halves(self):
        i18n = (SCRIPTS / "i18n.js").read_text(encoding="utf-8")
        self.assertEqual(i18n.count("cmdUnmuteBrowserOff:"), 8)
        self.assertEqual(i18n.count("cmdUnmuteOnDevice:"), 8)
        self.assertEqual(i18n.count("{local}"), 8)
        # Nothing left saying it of browser recognition as a whole
        self.assertNotIn("cmdUnmuteBrowserOff:'This browser’s recognition cuts", i18n)

    def test_the_docs_no_longer_say_it_of_both_entries(self):
        for path in (ROOT / "skills/voice-shell/SKILL.md",
                     ROOT / "skills/voice-shell/REFERENCE.md"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("Browser recognition cannot hear \"unmute\"", text)
            self.assertIn("Plain browser recognition cannot hear", text.replace(
                "recognition\ncannot hear", "recognition cannot hear").replace(
                "Plain browser\nrecognition cannot", "Plain browser recognition cannot"))


if __name__ == "__main__":
    unittest.main()
