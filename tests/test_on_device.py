"""Browser recognition kept on this device (Chrome's processLocally).

The pieces with no page in them sit together at the head of that part of
viewer.js. They are cut out and run under node, the same way
test_reload_resume.py does it. The rest is read off the source, since what
matters there is the order things happen in.
"""
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/voice-shell/scripts"
sys.path.insert(0, str(SCRIPTS))
if "aiohttp" not in sys.modules:
    _aiohttp = types.ModuleType("aiohttp")
    _aiohttp.web = types.SimpleNamespace()
    _aiohttp.WSCloseCode = object()
    sys.modules["aiohttp"] = _aiohttp

import viewer


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
          onDeviceStatusKey, onDeviceMayStart, onDeviceRefusal, BROWSER_LOCAL,
          onDeviceHasModel, onDeviceSizeText, onDeviceMayAutoInstall};
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

    def test_a_model_on_the_disk_is_not_called_a_download(self):
        run(r"""
const here = {engine: true, pack: true, packBytes: 173923475};
const gone = {engine: true, pack: false, packBytes: 0};
const dunno = {engine: null, pack: null, packBytes: 0};
assert(h.onDeviceHasModel(here) === true, 'engine and pack both there');
assert(h.onDeviceHasModel(gone) === false, 'the engine alone is not the model');
assert(h.onDeviceHasModel(dunno) === false, 'unknown is not a yes');
assert(h.onDeviceHasModel(null) === false, 'nothing asked yet is not a yes');
// downloadable means nothing on its own: Chrome says it to every site that
// has not called install() itself, model on disk or not
assert(h.onDeviceStatusKey('downloadable', false, here) === 'onDeviceEnable', 'on the disk');
assert(h.onDeviceStatusKey('downloadable', false, gone) === 'onDeviceNeedsDownload', 'really missing');
assert(h.onDeviceStatusKey('downloadable', false, dunno) === 'onDeviceNeedsDownload', 'unknown hedges to a download');
assert(h.onDeviceStatusKey('downloadable', false) === 'onDeviceNeedsDownload', 'nothing asked yet');
// And the wait is seconds, not the minutes of a real download
assert(h.onDeviceStatusKey('downloading', false, here) === 'onDeviceEnabling', 'switching on');
assert(h.onDeviceStatusKey('downloading', false, gone) === 'onDeviceDownloading', 'really downloading');
// Everything else reads the same whatever the disk says
for (const disk of [here, gone, dunno, null]) {
  assert(h.onDeviceStatusKey('available', false, disk) === 'onDeviceReady', 'ready');
  assert(h.onDeviceStatusKey('unavailable', false, disk) === 'onDeviceUnavailable', 'unavailable');
  assert(h.onDeviceStatusKey('downloadable', true, disk) === 'onDeviceRefused', 'a refusal outranks the disk');
  assert(h.onDeviceStatusKey('', false, disk) === 'onDeviceChecking', 'not asked yet');
}
assert(h.onDeviceSizeText(here) === '166 MB', 'the size the server found, got ' + h.onDeviceSizeText(here));
assert(h.onDeviceSizeText(gone) === '', 'nothing to say');
assert(h.onDeviceSizeText(null) === '', 'nothing asked');
""")

    def test_only_a_model_already_here_rides_along_on_any_press(self):
        run(r"""
const here = {engine: true, pack: true, packBytes: 1}, gone = {engine: true, pack: false};
const may = (...a) => h.onDeviceMayAutoInstall(...a);
assert(may(true, true, 'downloadable', false, false, here) === true, 'nothing to fetch, any press does it');
// A real download is never slipped into a press meant for something else
assert(may(true, true, 'downloadable', false, false, gone) === false, 'a real download stays the button');
assert(may(true, true, 'downloadable', false, false, null) === false, 'unknown stays the button');
// Not off the local entry, where none of this was asked for
assert(may(false, true, 'downloadable', false, false, here) === false, 'plain browser entry');
assert(may(true, false, 'downloadable', false, false, here) === false, 'another engine');
// And nothing to do on any other answer
for (const s of ['available', 'downloading', 'unavailable', '']) {
  assert(may(true, true, s, false, false, here) === false, 'nothing to start on ' + s);
}
assert(may(true, true, 'downloadable', true, false, here) === false, 'Chrome already refused');
assert(may(true, true, 'downloadable', false, true, here) === false, 'one is already running');
""")

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
  // The page's own hooks, stood in for. env.listeners is what is armed right
  // now, env.press(type) is somebody pressing something.
  const addEventListener = (type, fn) => env.listeners.push({type, fn});
  const removeEventListener = (type, fn) => {
    const at = env.listeners.findIndex(l => l.type === type && l.fn === fn);
    if (at >= 0) env.listeners.splice(at, 1);
  };
  const fetch = url => env.fetch ? env.fetch(url) : new Promise(() => {});
  // The page's own, which live outside the slices taken here
  const setLabel = (n, text) => { n.textContent = text; };
  const setIcon = (n, name) => { n.icon = name; };
  const navigator = env.navigator || {userActivation: {isActive: true}};
  ${source.slice(stateFrom, stateTo)}
  ${source.slice(clickFrom, clickTo)}
  return {startOnDeviceInstall, paintOnDevice, askOnDevice,
          setChosen: v => { asrChosen = v; paintOnDevice(); },
          setLocal: v => { onDeviceLocal = v; paintOnDevice(); },
          state: () => ({onDeviceInstalling, onDeviceInstallLang, onDeviceDisk,
                         armed: !!onDeviceArmed})};
`);
const assert = (cond, what) => { if (!cond) { console.error(what); process.exit(1); } };
const tick = () => new Promise(resolve => global.setTimeout(resolve, 0));
"""


def run_install(script):
    subprocess.run(["node", "-e", INSTALL_HARNESS + INSTALL_ENV + script, str(VIEWER_JS)],
                   check=True)


# The four pieces every install test needs around it
INSTALL_ENV = r"""
const freshEnv = (answers, disk, lang) => {
  const el = {onDeviceField: {}, onDeviceStatus: {}, onDeviceRow: {}, onDeviceDownload: {}};
  const env = {lang: lang || 'ja-JP', el, listeners: [], installs: [],
    fetch: url => Promise.resolve({json: async () => (
      disk === undefined ? {lang: new URL(url, 'http://x').searchParams.get('lang'),
                            engine: null, pack: null, packBytes: 0}
                         : {lang: new URL(url, 'http://x').searchParams.get('lang'), ...disk})}),
    SR: {
      available: async ({langs}) => answers[langs[0]],
      install: ({langs}) => { env.installs.push(langs[0]); return new Promise(() => {}); },
    }};
  env.press = type => {
    const armed = env.listeners.filter(l => l.type === type);
    for (const l of armed) l.fn({});
    return armed.length;
  };
  return env;
};
"""


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


    def test_a_press_anywhere_finishes_it_when_the_model_is_already_here(self):
        run_install(r"""
(async () => {
  const env = freshEnv({'ja-JP': 'downloadable'}, {engine: true, pack: true, packBytes: 173923475});
  const h = make(env);
  await h.askOnDevice(); await tick(); await tick();
  assert(env.el.onDeviceStatus.textContent === 'onDeviceEnable',
         'says it only has to be turned on, got ' + env.el.onDeviceStatus.textContent);
  assert(env.el.onDeviceDownload.textContent === 'onDeviceEnableBtn', 'and so does the button');
  assert(env.el.onDeviceDownload.icon === 'bolt', 'and a download arrow over nothing downloading is gone');
  assert(env.el.onDeviceRow.hidden === false, 'the button is still there');
  assert(h.state().armed === true, 'armed');
  assert(env.installs.length === 0, 'nothing has been pressed yet');
  // Somebody presses the mute button, the send button, anything at all
  assert(env.press('pointerdown') === 1, 'one listener waiting');
  assert(env.installs.length === 1 && env.installs[0] === 'ja-JP', 'that press did the install');
  assert(h.state().armed === false, 'and it is off again');
  assert(env.listeners.length === 0, 'the keyboard one came off with it');
  assert(env.el.onDeviceStatus.textContent === 'onDeviceEnabling', 'seconds, not minutes');
  // A second press does not start a second one
  env.press('pointerdown');
  assert(env.installs.length === 1, 'only the once');
})().then(() => process.exit(0), e => { console.error(e); process.exit(1); });
""")

    def test_a_real_download_is_left_to_the_button(self):
        run_install(r"""
(async () => {
  // The engine is here but not this language, so this really would fetch it
  const env = freshEnv({'ja-JP': 'downloadable'}, {engine: true, pack: false, packBytes: 0});
  const h = make(env);
  await h.askOnDevice(); await tick(); await tick();
  assert(env.el.onDeviceStatus.textContent === 'onDeviceNeedsDownload', 'says it downloads');
  assert(env.el.onDeviceDownload.textContent === 'onDeviceDownload', 'and the button says download');
  assert(env.el.onDeviceDownload.icon === 'download', 'with the download arrow');
  assert(h.state().armed === false, 'no press rides along');
  assert(env.press('pointerdown') === 0, 'nothing is listening');
  assert(env.installs.length === 0, 'so a press somewhere else fetches nothing');
  // The button itself still does
  h.startOnDeviceInstall();
  assert(env.installs.length === 1, 'a deliberate press does');
})().then(() => process.exit(0), e => { console.error(e); process.exit(1); });
""")

    def test_a_server_that_cannot_tell_is_left_to_the_button_too(self):
        run_install(r"""
(async () => {
  const env = freshEnv({'ja-JP': 'downloadable'}, undefined);   // engine and pack null
  const h = make(env);
  await h.askOnDevice(); await tick(); await tick();
  assert(env.el.onDeviceStatus.textContent === 'onDeviceNeedsDownload', 'hedges to a download');
  assert(h.state().armed === false, 'and nothing rides along on a press');
})().then(() => process.exit(0), e => { console.error(e); process.exit(1); });
""")

    def test_it_comes_off_when_the_language_moves_to_one_that_must_be_fetched(self):
        run_install(r"""
(async () => {
  const answers = {'ja-JP': 'downloadable', 'en-US': 'downloadable'};
  const packs = {'ja-JP': {engine: true, pack: true, packBytes: 173923475},
                 'en-US': {engine: true, pack: false, packBytes: 0}};
  const env = freshEnv(answers, {});
  env.fetch = url => {
    const lang = new URL(url, 'http://x').searchParams.get('lang');
    return Promise.resolve({json: async () => ({lang, ...packs[lang]})});
  };
  const h = make(env);
  await h.askOnDevice(); await tick(); await tick();
  assert(h.state().armed === true, 'armed for the one already here');
  env.lang = 'en-US';
  await h.askOnDevice(); await tick(); await tick();
  assert(h.state().armed === false, 'off for the one that would really download');
  assert(env.el.onDeviceStatus.textContent === 'onDeviceNeedsDownload', 'and the line says so');
  env.lang = 'ja-JP';
  await h.askOnDevice(); await tick(); await tick();
  assert(h.state().armed === true, 'back on for the first one');
  assert(env.press('keydown') === 1, 'a key counts as a press too');
  assert(env.installs.length === 1 && env.installs[0] === 'ja-JP', 'for the language chosen now');
})().then(() => process.exit(0), e => { console.error(e); process.exit(1); });
""")

    def test_it_is_asked_once_per_language_and_never_off_the_local_entry(self):
        run_install(r"""
(async () => {
  const env = freshEnv({'ja-JP': 'downloadable'}, {engine: true, pack: true, packBytes: 1});
  let asked = [];
  const under = env.fetch;
  env.fetch = url => { asked.push(url); return under(url); };
  const h = make(env);
  for (let i = 0; i < 3; i++) { await h.askOnDevice(); await tick(); await tick(); }
  assert(asked.length === 1, 'the disk is looked at once, not on every 2 second poll, got ' + asked.length);
  assert(asked[0].includes('lang=ja-JP'), 'for the language chosen');
  assert(h.state().armed === true, 'armed while the local entry is the one chosen');
  // Moved off browser recognition altogether, or off the local entry onto the
  // plain one. Neither is somewhere a press should be installing anything.
  h.setChosen(false);
  assert(h.state().armed === false, 'off when browser recognition is not chosen');
  assert(env.listeners.length === 0, 'nothing left listening');
  h.setChosen(true);
  assert(h.state().armed === true, 'back');
  h.setLocal(false);
  assert(h.state().armed === false, 'off on the plain browser entry');
  assert(env.press('pointerdown') === 0, 'a press there installs nothing');
})().then(() => process.exit(0), e => { console.error(e); process.exit(1); });
""")


    def test_the_press_that_lands_on_the_button_does_not_install_twice(self):
        run_install(r"""
(async () => {
  const env = freshEnv({'ja-JP': 'downloadable'}, {engine: true, pack: true, packBytes: 1});
  const h = make(env);
  await h.askOnDevice(); await tick(); await tick();
  // Armed, a press on the button itself arrives twice: the capture listener
  // on pointerdown, then the button's own click. The second would take over
  // the id the first is waiting on and strand the line on downloading.
  env.press('pointerdown');
  h.startOnDeviceInstall();
  assert(env.installs.length === 1, 'installed once, got ' + env.installs.length);
  assert(h.state().onDeviceInstalling === true, 'and the first one is still the one running');
})().then(() => process.exit(0), e => { console.error(e); process.exit(1); });
""")

    def test_a_key_that_hands_out_no_activation_leaves_it_armed(self):
        run_install(r"""
(async () => {
  // Escape closing the settings sheet, a modifier on its own. Chrome hands
  // out no activation for those, install() would throw, and the line would
  // tell you to go back to the tab and press again, about a keypress.
  const env = freshEnv({'ja-JP': 'downloadable'}, {engine: true, pack: true, packBytes: 1});
  env.navigator = {userActivation: {isActive: false}};
  const h = make(env);
  await h.askOnDevice(); await tick(); await tick();
  assert(h.state().armed === true, 'armed');
  env.press('keydown');
  assert(env.installs.length === 0, 'nothing tried');
  assert(h.state().armed === true, 'and still waiting for a press that really is one');
  env.navigator.userActivation.isActive = true;
  env.press('pointerdown');
  assert(env.installs.length === 1, 'which then does it');
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
        # The armed press landing on the button itself gets here twice
        self.assertIn("if (onDeviceInstalling && onDeviceInstallLang === lang) return;", head)
        self.assertIn("NotAllowedError", click)
        # A download Chrome never starts gives the button back instead of
        # leaving it greyed out on "downloading" for good
        self.assertIn("if (!onDeviceSawDownloading && onDeviceNow() !== 'available') settle('onDeviceDownloadFailed');", click)
        self.assertIn("if (id !== onDeviceInstallId || !onDeviceInstalling) return;", click)
        self.assertIn("el.onDeviceDownload.onclick = () => startOnDeviceInstall();", self.source)

    def test_the_press_that_rides_along_installs_before_anything_else_sees_it(self):
        arm = self.section("function armOnDeviceInstall() {")
        # Capture, so the button or field under the finger does not get there
        # first and have its own work sit between the press and install()
        self.assertIn("addEventListener('pointerdown', fire, true);", arm)
        self.assertIn("addEventListener('keydown', fire, true);", arm)
        # Read again at the moment of the press, which can land at any time
        self.assertIn("onDeviceMayAutoInstall(onDeviceLocal, asrChosen, onDeviceNow(), onDeviceRefused,", arm)
        head = arm.split("startOnDeviceInstall()", 1)[0]
        self.assertNotIn("await", head)
        self.assertNotIn(".then", head)
        self.assertIn("navigator.userActivation && !navigator.userActivation.isActive", arm)
        off = self.section("function disarmOnDeviceInstall() {")
        self.assertIn("removeEventListener('pointerdown', fire, true);", off)
        self.assertIn("removeEventListener('keydown', fire, true);", off)
        # One place decides whether it is armed, so no path can forget to
        paint = self.section("function paintOnDevice() {")
        self.assertIn("disarmOnDeviceInstall(); return;", paint)
        self.assertIn("armOnDeviceInstall();", paint)
        import re
        self.assertEqual(len(re.findall(r"(?<![a-zA-Z])armOnDeviceInstall\(\);", self.source)), 1)

    def test_the_disk_is_looked_at_only_for_the_answer_that_is_ambiguous(self):
        ask = self.section("function askOnDevice() {")
        self.assertIn("if (status === 'downloadable') checkOnDeviceDisk(lang);", ask)
        look = self.section("function checkOnDeviceDisk(lang) {")
        self.assertIn("fetch('/api/ondevice?lang=' + encodeURIComponent(lang))", look)
        # Once per language, or the 2 second poll would hammer it
        self.assertIn("if (onDeviceDiskAsk === lang || (onDeviceDisk && onDeviceDisk.lang === lang)) return;", look)
        # An answer for a language no longer chosen is dropped, like available()'s
        self.assertIn("if (onDeviceDiskAsk !== lang) return;", look)
        self.assertIn(".catch(", look)

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
                "onDeviceEnable", "onDeviceEnableBtn", "onDeviceEnabling",
                "onDeviceSizeGuess",
                "idleMuteNoteLocal"]
        for key in keys:
            self.assertEqual(i18n.count(f"\n    {key}:'"), 8, key)



class OnDeviceDiskTest(unittest.TestCase):
    """The server's look at the disk (viewer.on_device_model).

    Chrome tells every site downloadable until that site has called install()
    itself, model on disk or not, so the page cannot tell a 170 MB download
    from a switch on that takes seconds. The server can, by looking, and this
    is that look, run over a directory tree built to look like Chrome's.
    """

    def tree(self, engine="1.2.5", engine_bytes=64, packs=(("ja-JP", 4096),)):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(root, ignore_errors=True))
        if engine:
            files = root / "SODA" / engine / "SODAFiles"
            files.mkdir(parents=True)
            (files / "SODA.dll").write_bytes(b"x" * engine_bytes)
        for name, size in packs:
            pack = root / "SODALanguagePacks" / name
            pack.mkdir(parents=True)
            (pack / "manifest.json").write_bytes(b"y" * size)
        return root

    def test_the_engine_and_this_language_both_being_there_is_the_yes(self):
        root = self.tree()
        got = viewer.on_device_model("ja-JP", [root])
        self.assertEqual((got["engine"], got["pack"]), (True, True))
        self.assertEqual(got["engineBytes"], 64)
        self.assertEqual(got["packBytes"], 4096)
        self.assertEqual(got["root"], str(root))
        self.assertEqual(got["lang"], "ja-JP")

    def test_the_engine_alone_is_not_this_language(self):
        got = viewer.on_device_model("en-US", [self.tree()])
        self.assertEqual((got["engine"], got["pack"]), (True, False))
        self.assertEqual(got["packBytes"], 0)

    def test_an_empty_engine_directory_does_not_count(self):
        root = self.tree()
        for f in (root / "SODA/1.2.5/SODAFiles").iterdir():
            f.unlink()
        got = viewer.on_device_model("ja-JP", [root])
        self.assertIs(got["engine"], False)

    def test_the_language_tag_is_matched_loosely(self):
        root = self.tree(packs=(("ja-JP", 10),))
        for lang in ("ja-JP", "ja", "JA-jp", "ja-jp", "ja_JP"):
            self.assertIs(viewer.on_device_model(lang, [root])["pack"], True, lang)
        for lang in ("en-US", "jv-ID", ""):
            self.assertIs(viewer.on_device_model(lang, [root])["pack"], False, lang)
        # One region of a language is not another. Chrome ships a pack each,
        # and the dropdown offers both, so a loose read here would have the
        # page promise en-GB is already here and then really download it.
        for folder, asked in (("en-US", "en-GB"), ("en-GB", "en-US"),
                              ("zh-CN", "zh-TW"), ("zh-TW", "zh-HK")):
            got = viewer.on_device_model(asked, [self.tree(packs=((folder, 10),))])
            self.assertIs(got["pack"], False, folder + " is not " + asked)
        # And the other way round, a folder named without the region
        bare = self.tree(packs=(("ja", 10),))
        self.assertIs(viewer.on_device_model("ja-JP", [bare])["pack"], True)

    def test_nowhere_to_look_is_unknown_rather_than_a_no(self):
        """No Chrome directory at all says nothing either way.

        A no here would have the page promise there is nothing to download
        when it simply could not see. Unknown makes it hedge, which is what
        it did before any of this.
        """
        missing = Path(tempfile.gettempdir()) / "voice-shell-no-such-chrome-dir"
        got = viewer.on_device_model("ja-JP", [missing])
        self.assertIsNone(got["engine"])
        self.assertIsNone(got["pack"])
        self.assertEqual(got["root"], "")

    def test_a_second_chrome_holding_it_is_not_masked_by_the_first(self):
        """Chrome, Chrome Beta and Chromium are all looked at.

        The one with the engine but not this language must not stand in for
        the one that has both, whichever order they are looked at in.
        """
        engine_only = self.tree(packs=())
        both = self.tree()
        for roots in ([engine_only, both], [both, engine_only]):
            got = viewer.on_device_model("ja-JP", roots)
            self.assertEqual((got["engine"], got["pack"]), (True, True), roots)
            self.assertEqual(got["root"], str(both))

    def test_a_pack_without_the_engine_is_still_not_a_yes(self):
        root = self.tree(engine=None)
        got = viewer.on_device_model("ja-JP", [root])
        self.assertEqual((got["engine"], got["pack"]), (False, True))

    def test_it_never_raises_whatever_it_is_handed(self):
        for roots in ([None], [object()], [1], [chr(0) + "bad"]):
            got = viewer.on_device_model("ja-JP", roots)
            self.assertIn(got["engine"], (None, False))
        # And the real platform list, whatever this machine happens to have
        real = viewer.on_device_model("ja-JP")
        self.assertIn(real["engine"], (None, True, False))
        self.assertIsInstance(real["packBytes"], int)

    def test_the_places_looked_at_are_this_platform_s_chrome_family(self):
        dirs = [str(p) for p in viewer._chrome_user_data_dirs()]
        self.assertTrue(dirs)
        joined = " ".join(dirs).lower()
        self.assertIn("chromium", joined)
        if sys.platform.startswith("win"):
            self.assertTrue(any("chrome" + os.sep + "user data" in d.lower() for d in dirs))
            self.assertTrue(any("chrome beta" in d.lower() for d in dirs))
            self.assertTrue(any("chrome sxs" in d.lower() for d in dirs))
        elif sys.platform == "darwin":
            self.assertTrue(any("application support/google/chrome" in d.lower() for d in dirs))
            self.assertTrue(any("canary" in d.lower() for d in dirs))
        else:
            self.assertTrue(any(d.endswith("google-chrome") for d in dirs))


if __name__ == "__main__":
    unittest.main()
