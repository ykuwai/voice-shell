import sys
import subprocess
import tempfile
import time
import types
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/voice-shell/scripts"
VIEWER_JS = SCRIPTS / "viewer.js"
I18N = SCRIPTS / "i18n.js"
sys.path.insert(0, str(SCRIPTS))
if "aiohttp" not in sys.modules:
    aiohttp = types.ModuleType("aiohttp")
    aiohttp.web = types.SimpleNamespace()
    aiohttp.WSCloseCode = object()
    sys.modules["aiohttp"] = aiohttp

import viewer
from viewer import append_asr_owned, live_asr_beats, owns_asr_lease, update_asr_lease


class AsrLeaseTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.beats = root / "asr-heartbeat.json"
        self.owner = root / "asr-owner.json"

    def tearDown(self):
        self.temp.cleanup()

    def update(self, tab, state, now):
        return update_asr_lease(self.beats, self.owner, tab, state, now)

    def test_first_listener_acquires_owner(self):
        beats, owner, owns = self.update("first", "listening", 100)
        self.assertTrue(owns)
        self.assertEqual(owner["tab"], "first")
        self.assertEqual(beats["first"]["state"], "listening")

    def test_second_listener_is_denied_while_owner_is_fresh(self):
        self.update("first", "listening", 100)
        beats, owner, owns = self.update("second", "listening", 101)
        self.assertFalse(owns)
        self.assertEqual(owner["tab"], "first")
        self.assertEqual(beats["second"]["state"], "conflict")

    def test_gone_releases_owner_for_conflicting_tab(self):
        self.update("first", "listening", 100)
        self.update("second", "conflict", 101)
        _, owner, owns = self.update("first", "gone", 102)
        self.assertFalse(owns)
        self.assertEqual(owner, {})
        _, owner, owns = self.update("second", "conflict", 103)
        self.assertTrue(owns)
        self.assertEqual(owner["tab"], "second")

    def test_expired_owner_can_be_replaced(self):
        self.update("first", "listening", 100)
        _, owner, owns = self.update("second", "listening", 116)
        self.assertTrue(owns)
        self.assertEqual(owner["tab"], "second")

    def test_status_counts_keep_existing_heartbeat_states(self):
        self.update("one", "listening", 100)
        self.update("two", "denied", 101)
        self.update("three", "idle", 102)
        beats = live_asr_beats(self.beats, 103)
        states = [beat["state"] for beat in beats.values()]
        self.assertEqual(len(beats), 3)
        self.assertEqual(states.count("listening"), 1)
        self.assertEqual(states.count("denied"), 1)

    def test_lock_failure_does_not_update_lease(self):
        with mock.patch.object(viewer, "_asr_lease_lock") as lock:
            lock.return_value.__enter__.return_value = False
            self.assertIsNone(self.update("first", "listening", 100))
        self.assertFalse(self.beats.exists())
        self.assertFalse(self.owner.exists())

    def test_only_the_owner_can_send_browser_utterances(self):
        self.update("owner", "listening", 100)
        owns, owner = owns_asr_lease(self.beats, self.owner, "owner", 101)
        self.assertTrue(owns)
        self.assertEqual(owner["tab"], "owner")
        owns, owner = owns_asr_lease(self.beats, self.owner, "other", 101)
        self.assertFalse(owns)
        self.assertEqual(owner["tab"], "owner")

    def test_unavailable_lease_rejects_browser_utterances(self):
        with mock.patch.object(viewer, "_asr_lease_lock") as lock:
            lock.return_value.__enter__.return_value = False
            owns, owner = owns_asr_lease(self.beats, self.owner, "owner")
        self.assertIsNone(owns)
        self.assertIsNone(owner)

    def test_browser_write_checks_owner_while_holding_lease_lock(self):
        output = self.beats.parent / "utterances.jsonl"
        self.update("owner", "listening", time.time())
        written, owner = append_asr_owned(self.owner, "other", output, "late\n")
        self.assertFalse(written)
        self.assertEqual(owner["tab"], "owner")
        self.assertFalse(output.exists())
        written, _ = append_asr_owned(self.owner, "owner", output, "kept\n")
        self.assertTrue(written)
        self.assertEqual(output.read_text(encoding="utf-8"), "kept\n")
        with mock.patch.object(viewer, "_asr_lease_lock") as lock:
            lock.return_value.__enter__.return_value = False
            written, owner = append_asr_owned(self.owner, "owner", output, "blocked\n")
        self.assertIsNone(written)
        self.assertIsNone(owner)
        self.assertEqual(output.read_text(encoding="utf-8"), "kept\n")

    def test_stopped_start_cannot_create_a_late_recognition(self):
        script = r'''
const fs = require('fs');
const source = fs.readFileSync(process.argv[1], 'utf8');
const from = source.indexOf('function newRecognition(generation)');
const to = source.indexOf('\n// When it can no longer be used', from);
const body = source.slice(from, to);
const makeHarness = new Function('SR', 'beat', `
  let canBrowserASR = true, recWanted = true, rec = null, recRunning = false;
  let recStarting = false, recGeneration = 0, recFails = 0, recStartedAt = 0;
  let route = 'on', asrDeniedFlag = false, lastVoiceAt = 0;
  const MAX_FAILS = 6;
  const browserLang = () => 'en-US';
  const performance = {now: () => 0};
  const el = {stream: {textContent: ''}, tray: {classList: {toggle: () => {}}}, hint: {textContent: ''}};
  const withDict = value => value;
  const streamTail = () => {};
  const paintTinyButtons = () => {};
  const disableBrowserASR = () => {};
  const t = () => '';
  ${body}
  return {startRecognition, stopRecognition, state: () => ({rec, recStarting, recGeneration})};
`);
let starts = 0;
class FakeRecognition {
  start() { starts++; }
  abort() {}
}
const waits = [];
const harness = makeHarness(FakeRecognition, () => new Promise(resolve => waits.push(resolve)));
const oldStart = harness.startRecognition();
harness.stopRecognition(true);
const newStart = harness.startRecognition();
waits[0](true);
Promise.resolve().then(() => {
  if (starts !== 0) process.exit(1);
  waits[1](true);
  return newStart;
}).then(() => {
  harness.startRecognition();
  if (starts !== 1 || !harness.state().recStarting) process.exit(1);
  return oldStart;
}).then(() => process.exit(0)).catch(() => process.exit(1));
'''
        subprocess.run(["node", "-e", script, str(VIEWER_JS)], check=True)

    def test_gone_beacon_falls_back_to_post_when_not_queued(self):
        script = r'''
const fs = require('fs');
const source = fs.readFileSync(process.argv[1], 'utf8');
const start = source.indexOf('async function beat(state)');
const end = source.indexOf('\n}\n\nsetInterval', start) + 2;
const body = source.slice(start, end);
const makeBeat = new Function('navigator', 'Blob', 'post', 'tabId',
  'setAsrConflict', 'stopRecognition', 'el', 't', 'paintBrowserAsr',
  `let asrOwnsLease = true; let asrConflict = null; ${body}; return beat;`);
let posts = 0;
const beat = makeBeat({sendBeacon: () => false}, Blob, async () => {
  posts++;
  return {ok: true, status: 200, json: async () => ({owner: null})};
}, 'tab', () => {}, () => {}, {hint: {}}, () => '', () => {});
beat('gone').then(() => process.exit(posts === 1 ? 0 : 1));
'''
        subprocess.run(["node", "-e", script, str(VIEWER_JS)], check=True)

    def test_lease_writes_use_a_lock_file(self):
        self.update("first", "listening", 100)
        self.assertTrue((self.owner.parent / "asr-lease.lock").exists())

    def test_viewer_stops_and_retries_for_lease_conflicts(self):
        source = VIEWER_JS.read_text(encoding="utf-8")
        self.assertIn("if (!await beat('listening')", source)
        self.assertIn("recStarting = true", source)
        self.assertIn("r.onstart", source)
        self.assertIn("recStarting = false", source)
        self.assertIn("|| rec ||", source)
        self.assertIn("setAsrConflict(data.owner)", source)
        self.assertIn("if (!asrOwnsLease || asrConflict)", source)
        send = source.split("function sendUtterance(text)", 1)[1].split("const tabId", 1)[0]
        self.assertGreaterEqual(send.count("if (!asrOwnsLease || asrConflict)"), 2)
        stand_down = source.split("function standDown()", 1)[1].split("function claimSole", 1)[0]
        self.assertIn("standingDown = true", stand_down)
        self.assertIn("beat('gone')", stand_down)
        self.assertIn("if (!asrChosen || standingDown) return", source)
        self.assertIn("{text, lang: spokenLang(), tab: tabId}", send)
        self.assertIn("if (navigator.sendBeacon('/api/asr-heartbeat'", source)
        self.assertIn("(asrConflict ? 'conflict'", source)
        self.assertIn("owns_asr_lease(beat_file, asr_owner_file, tab)",
                      Path(SCRIPTS / "viewer.py").read_text(encoding="utf-8"))
        self.assertIn('"error": "asr_owner_conflict"',
                      Path(SCRIPTS / "viewer.py").read_text(encoding="utf-8"))
        self.assertIn('"error": "daemon_running"',
                      Path(SCRIPTS / "viewer.py").read_text(encoding="utf-8"))
        self.assertEqual(I18N.read_text(encoding="utf-8").count("asrConflict:"), 7)


if __name__ == "__main__":
    unittest.main()
