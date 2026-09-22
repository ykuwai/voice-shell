"""Browser recognition kept on this device (Chrome's processLocally).

The pieces with no page in them sit together at the head of that part of
viewer.js. They are cut out and run under node, the same way
test_reload_resume.py does it. The rest is read off the source, since what
matters there is the order things happen in.
"""
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIEWER_JS = ROOT / "skills/voice-shell/scripts/viewer.js"
I18N_JS = ROOT / "skills/voice-shell/scripts/i18n.js"

HARNESS = r'''
const fs = require('fs');
const source = fs.readFileSync(process.argv[1], 'utf8');
const start = source.indexOf("const BROWSER_LOCAL = 'browser-local';");
const end = source.indexOf("// Whether the local entry can be offered here at all.", start);
if (start < 0 || end < 0) process.exit(2);
const body = source.slice(start, end);
const make = new Function('env', `
  const BROWSER_ENGINE = 'browser';
  ${body}
  return {readOnDeviceFlag, writeOnDeviceFlag, engineShown, enginePicked,
          onDeviceStatusKey, onDeviceMayStart, onDeviceRefusal, BROWSER_LOCAL};
`);
// The same shape as viewer.js's own store, over a storage that can throw
const storeOver = storage => ({
  get(k, d) { try { return storage.getItem('vs.' + k) ?? d; } catch { return d; } },
  set(k, v) { try { storage.setItem('vs.' + k, v); } catch {} },
});
class Storage {
  constructor() { this.m = new Map(); }
  getItem(k) { return this.m.has(k) ? this.m.get(k) : null; }
  setItem(k, v) { this.m.set(k, String(v)); }
}
const assert = (cond, what) => { if (!cond) { console.error(what); process.exit(1); } };
const h = make({});
'''


def run(script):
    subprocess.run(["node", "-e", HARNESS + script, str(VIEWER_JS)], check=True)


class OnDevicePureTest(unittest.TestCase):
    def test_flag_is_kept_and_survives_a_storage_that_throws(self):
        run(r'''
const st = new Storage(), s = storeOver(st);
assert(h.readOnDeviceFlag(s) === false, 'off until chosen');
h.writeOnDeviceFlag(s, true);
assert(st.getItem('vs.asrLocal') === '1', 'written under vs.asrLocal');
assert(h.readOnDeviceFlag(storeOver(st)) === true, 'read back by a fresh page');
h.writeOnDeviceFlag(s, false);
assert(h.readOnDeviceFlag(s) === false, 'cleared');
const broken = storeOver({getItem() { throw new Error('denied'); },
                          setItem() { throw new Error('denied'); }});
h.writeOnDeviceFlag(broken, true);
assert(h.readOnDeviceFlag(broken) === false, 'a storage that throws reads as off');
''')

    def test_dropdown_maps_both_ways_and_the_poll_cannot_snap_it_back(self):
        run(r'''
// The server only ever says browser. The flag decides which entry shows.
assert(h.engineShown('browser', true) === 'browser-local', 'local shown');
assert(h.engineShown('browser', false) === 'browser', 'plain shown');
assert(h.engineShown('whisper', true) === 'whisper', 'other engines untouched by the flag');
assert(h.engineShown('', true) === '', 'nothing read yet');
const a = h.enginePicked('browser-local');
assert(a.engine === 'browser' && a.local === true, 'local is browser to the server');
const b = h.enginePicked('browser');
assert(b.engine === 'browser' && b.local === false, 'plain');
const c = h.enginePicked('apple');
assert(c.engine === 'apple' && c.local === false, 'apple');
// Round trip: what the server is told, shown back through the 5s poll
for (const v of ['browser', 'browser-local', 'whisper']) {
  const p = h.enginePicked(v);
  assert(h.engineShown(p.engine, p.local) === v, 'round trip ' + v);
}
''')

    def test_status_lines(self):
        run(r'''
const k = h.onDeviceStatusKey;
assert(k('available', false) === 'onDeviceReady', 'available');
assert(k('downloadable', false) === 'onDeviceNeedsDownload', 'downloadable');
assert(k('downloading', false) === 'onDeviceDownloading', 'downloading');
assert(k('unavailable', false) === 'onDeviceUnavailable', 'unavailable');
assert(k('', false) === 'onDeviceChecking', 'not asked yet');
assert(k('something-new', false) === 'onDeviceChecking', 'an answer nobody worded');
assert(k('available', true) === 'onDeviceRefused', 'a refusal outranks available');
''')

    def test_never_falls_back_to_the_cloud(self):
        run(r'''
const may = h.onDeviceMayStart;
// Off the local entry, nothing is held here
for (const st of ['', 'downloadable', 'unavailable'])
  assert(may(false, st, false) === true, 'plain entry ' + st);
// On it, only a model that is here lets recognition start
assert(may(true, 'available', false) === true, 'available');
for (const st of ['', 'downloadable', 'downloading', 'unavailable', 'bogus'])
  assert(may(true, st, false) === false, 'held on ' + JSON.stringify(st));
assert(may(true, 'available', true) === false, 'held after Chrome refused');
// Both names for "no model": Chromium's and the spec's
assert(h.onDeviceRefusal('language-not-supported', false), 'chromium');
assert(h.onDeviceRefusal('service-not-allowed', false), 'spec');
assert(h.onDeviceRefusal('language-not-supported', true), 'chromium, even unattended');
// Unattended after a reload, service-not-allowed is left to the touch-to-start path
assert(!h.onDeviceRefusal('service-not-allowed', true), 'unattended');
for (const e of ['no-speech', 'aborted', 'network', 'not-allowed'])
  assert(!h.onDeviceRefusal(e, false), e);
''')



# The real startRecognition and newRecognition, with the page around them
# stood in for, to watch what a start on the local entry actually does.
START_HARNESS = r"""
const fs = require('fs');
const source = fs.readFileSync(process.argv[1], 'utf8');
const pureFrom = source.indexOf("const BROWSER_LOCAL = 'browser-local';");
const pureTo = source.indexOf("// Whether the local entry can be offered here at all.", pureFrom);
const from = source.indexOf('function newRecognition(generation)');
const to = source.indexOf('\n// When it can no longer be used', from);
if (pureFrom < 0 || pureTo < 0 || from < 0 || to < 0) process.exit(2);
const pure = source.slice(pureFrom, pureTo), body = source.slice(from, to);
const makeHarness = new Function('SR', 'env', `
  const BROWSER_ENGINE = 'browser';
  ${pure}
  let canBrowserASR = true, recWanted = true, rec = null, recRunning = false;
  let recStarting = false, recGeneration = 0, recFails = 0, recStartedAt = 0;
  let route = 'on', asrDeniedFlag = false, lastVoiceAt = 0, autoResumed = false;
  let onDeviceLocal = true, onDeviceRefused = false, onDeviceStatus = '';
  const MAX_FAILS = 6;
  const browserLang = () => 'ja-JP';
  const onDeviceNow = () => onDeviceStatus;
  const askOnDevice = async () => { env.asked++; onDeviceStatus = env.status; return env.status; };
  const holdOnDevice = () => { env.held++; };
  const beat = async () => { env.beats++; return true; };
  const performance = {now: () => 0};
  const el = {stream: {textContent: ''}, tray: {classList: {toggle: () => {}}}, hint: {textContent: ''}};
  const withDict = value => value;
  const streamTail = () => {};
  const browserStreamText = () => '';
  let latestInterimForPaint = '', lastInterimHeard = '';
  const paintTinyButtons = () => {};
  const disableBrowserASR = () => { env.disabled++; };
  const t = () => '';
  ${body}
  return {startRecognition, state: () => ({rec, recStarting, recFails, onDeviceRefused})};
`);
const made = [];
class FakeRecognition {
  constructor() { made.push(this); }
  start() { this.started = true; }
  abort() {}
  stop() {}
}
const fresh = status => ({status, asked: 0, held: 0, beats: 0, disabled: 0});
const assert = (cond, what) => { if (!cond) { console.error(what); process.exit(1); } };
"""


def run_start(script):
    subprocess.run(["node", "-e", START_HARNESS + script, str(VIEWER_JS)], check=True)


class OnDeviceStartTest(unittest.TestCase):
    def test_no_model_means_no_recognition_at_all(self):
        run_start(r"""
(async () => {
  for (const status of ['downloadable', 'downloading', 'unavailable']) {
    const env = fresh(status);
    const h = makeHarness(FakeRecognition, env);
    await h.startRecognition();
    assert(made.length === 0, 'nothing built on ' + status);
    assert(env.beats === 0, 'the lease is not claimed on ' + status);
    assert(env.held === 1, 'held and said on ' + status);
    assert(!h.state().recStarting && h.state().recFails === 0, 'left clean on ' + status);
  }
})().then(() => process.exit(0), e => { console.error(e); process.exit(1); });
""")

    def test_a_model_here_starts_it_on_the_device(self):
        run_start(r"""
(async () => {
  const env = fresh('available');
  const h = makeHarness(FakeRecognition, env);
  await h.startRecognition();
  assert(made.length === 1 && made[0].started, 'started');
  assert(made[0].processLocally === true, 'on the device');
  assert(made[0].quality === undefined, 'quality left alone');
  assert(env.beats === 1 && env.held === 0, 'went through as usual');
})().then(() => process.exit(0), e => { console.error(e); process.exit(1); });
""")

    def test_a_refusal_holds_rather_than_retrying_or_switching_off(self):
        run_start(r"""
(async () => {
  const env = fresh('available');
  const h = makeHarness(FakeRecognition, env);
  await h.startRecognition();
  const r = made[0];
  r.onstart();
  r.onerror({error: 'language-not-supported'});
  assert(h.state().onDeviceRefused === true, 'marked refused');
  assert(env.disabled === 0, 'browser recognition not switched off');
  assert(h.state().recFails === 0, 'not counted as a failure');
  r.onend();
  await new Promise(resolve => setTimeout(resolve, 20));
  assert(made.length === 1, 'no second session, not even a cloud one');
  assert(env.held >= 1, 'held instead');
})().then(() => process.exit(0), e => { console.error(e); process.exit(1); });
""")

# The download button and the status line, run for real with the page around
# them stood in for, to watch what a language switched mid download shows.
INSTALL_HARNESS = r"""
const fs = require('fs');
const source = fs.readFileSync(process.argv[1], 'utf8');
const pureFrom = source.indexOf("const BROWSER_LOCAL = 'browser-local';");
const pureTo = source.indexOf("// Whether the local entry can be offered here at all.", pureFrom);
const stateFrom = source.indexOf('let onDeviceLocal = canLocalASR');
const stateTo = source.indexOf('\nlet rec = null;', stateFrom);
const clickFrom = source.indexOf('function startOnDeviceInstall() {');
const clickTo = source.indexOf('\n/* ── Floating on top', clickFrom);
if ([pureFrom, pureTo, stateFrom, stateTo, clickFrom, clickTo].some(i => i < 0)) process.exit(2);
const make = new Function('env', `
  const BROWSER_ENGINE = 'browser';
  ${source.slice(pureFrom, pureTo)}
  const SR = env.SR, canLocalASR = true, store = {get: () => '1', set() {}};
  const browserLang = () => env.lang;
  let asrChosen = true, recWanted = false, rec = null, recStarting = false;
  const asrActive = () => true;
  const el = env.el, t = key => key, say = () => {}, paint = () => {};
  const startRecognition = () => {};
  const setTimeout = () => 0;
  ${source.slice(stateFrom, stateTo)}
  ${source.slice(clickFrom, clickTo)}
  return {startOnDeviceInstall, paintOnDevice, askOnDevice};
`);
const assert = (cond, what) => { if (!cond) { console.error(what); process.exit(1); } };
const tick = () => new Promise(resolve => global.setTimeout(resolve, 0));
"""


def run_install(script):
    subprocess.run(["node", "-e", INSTALL_HARNESS + script, str(VIEWER_JS)], check=True)


class OnDeviceInstallTest(unittest.TestCase):
    def test_a_language_switched_mid_download_is_not_greyed_out(self):
        run_install(r"""
(async () => {
  const answers = {'ja-JP': 'downloading', 'en-US': 'downloadable'};
  const el = {onDeviceField: {}, onDeviceStatus: {}, onDeviceRow: {}, onDeviceDownload: {}};
  const env = {lang: 'ja-JP', el, SR: {
    available: async ({langs}) => answers[langs[0]],
    install: () => new Promise(() => {}),   // a download that goes on for minutes
  }};
  const h = make(env);
  h.startOnDeviceInstall();
  await h.askOnDevice(); await tick();
  assert(el.onDeviceDownload.disabled === true, 'greyed out while its own language downloads');
  assert(el.onDeviceStatus.textContent === 'onDeviceDownloading', 'says downloading');
  env.lang = 'en-US';
  await h.askOnDevice(); await tick();
  assert(el.onDeviceStatus.textContent === 'onDeviceNeedsDownload',
         'the other language says it needs a download, got ' + el.onDeviceStatus.textContent);
  assert(el.onDeviceRow.hidden === false, 'with the button shown');
  assert(el.onDeviceDownload.disabled === false, 'and pressable');
  env.lang = 'ja-JP';
  await h.askOnDevice(); await tick();
  assert(el.onDeviceDownload.disabled === true, 'back on the first one, still downloading');
})().then(() => process.exit(0), e => { console.error(e); process.exit(1); });
""")


class OnDeviceWiringTest(unittest.TestCase):
    source = VIEWER_JS.read_text(encoding="utf-8").replace("\r\n", "\n")

    def section(self, head, tail="\n}\n"):
        return self.source.split(head, 1)[1].split(tail, 1)[0]

    def test_the_hold_comes_before_the_lease_and_the_session(self):
        start = self.section("async function startRecognition()")
        hold = start.index("if (onDeviceLocal) {")
        self.assertLess(start.index("askOnDevice()"), start.index("beat('listening')"))
        self.assertLess(hold, start.index("beat('listening')"))
        self.assertLess(hold, start.index("newRecognition(generation)"))
        self.assertIn("onDeviceMayStart(onDeviceLocal, onDeviceNow(), onDeviceRefused)", start)
        # Checked again after the await, like every other await in there
        after = start[hold:].split("onDeviceMayStart", 1)[0]
        self.assertIn("generation !== recGeneration", after)
        # A hold is not a failure (that would end in asrFailed)
        self.assertNotIn("recFails", start[hold:start.index("beat('listening')")])

    def test_process_locally_on_the_instance_and_quality_left_alone(self):
        make = self.section("function newRecognition(generation) {", "r.onstart")
        self.assertIn("if (onDeviceLocal) r.processLocally = true;", make)
        self.assertNotIn("r.quality", self.source)
        self.assertNotIn("r.phrases", self.source)

    def test_refusal_is_read_before_the_microphone_denial(self):
        onerror = self.section("r.onerror = ev => {", "\n  };\n")
        refusal = onerror.index("onDeviceRefusal(ev.error, autoResumed)")
        self.assertLess(refusal, onerror.index("ev.error === 'not-allowed'"))
        branch = onerror[refusal:onerror.index("ev.error === 'not-allowed'")]
        self.assertIn("onDeviceRefused = true", branch)
        self.assertNotIn("recFails", branch)
        self.assertNotIn("disableBrowserASR", branch)

    def test_install_is_the_first_thing_the_press_does(self):
        click = self.section("function startOnDeviceInstall() {")
        self.assertIn("SR.install({langs: [lang], processLocally: true})", click)
        head = click.split("SR.install(", 1)[0]
        self.assertNotIn("await", head)
        self.assertNotIn(".then", head)
        self.assertIn("NotAllowedError", click)
        # A download Chrome never starts gives the button back instead of
        # leaving it greyed out on "downloading" for good
        self.assertIn("if (!onDeviceSawDownloading && onDeviceNow() !== 'available') settle('onDeviceDownloadFailed');", click)
        self.assertIn("if (id !== onDeviceInstallId || !onDeviceInstalling) return;", click)
        self.assertIn("el.onDeviceDownload.onclick = () => startOnDeviceInstall();", self.source)

    def test_server_still_hears_browser(self):
        pick = self.section("el.enginePick.onchange = async () => {", "\n};\n")
        self.assertIn("enginePicked(el.enginePick.value)", pick)
        self.assertIn("{running: false, engine: BROWSER_ENGINE}", pick)
        self.assertNotIn("engine: BROWSER_LOCAL", self.source)
        self.assertIn("o.selected = id === engineShown(chosenEngine, onDeviceLocal);", self.source)

    def test_another_tab_switching_entries_is_followed(self):
        # The flag is per browser. A tab that kept what it read at load would
        # take over listening later on the plain entry, sending to Google.
        listener = self.section("addEventListener('storage', ev => {", "\n});\n")
        self.assertIn("'vs.' + ON_DEVICE_FLAG", listener)
        self.assertIn("onDeviceLocal = local;", listener)
        # A session built for the other entry is closed, so the next one goes
        # through the hold in startRecognition
        self.assertIn("if (rec) { try { rec.stop(); } catch {} }", listener)
        self.assertIn("paintEnginePick();", listener)

    def test_every_language_has_every_string(self):
        i18n = I18N_JS.read_text(encoding="utf-8").replace("\r\n", "\n")
        keys = ["engineBrowserLocal", "onDeviceChecking", "onDeviceReady",
                "onDeviceNeedsDownload", "onDeviceDownloading", "onDeviceUnavailable",
                "onDeviceRefused", "onDeviceDownload", "onDeviceDownloadFailed",
                "onDevicePressMain", "onDeviceHold",
                "idleMuteNoteLocal"]
        for key in keys:
            self.assertEqual(i18n.count(f"\n    {key}:'"), 8, key)


if __name__ == "__main__":
    unittest.main()
