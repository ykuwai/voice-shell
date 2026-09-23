"""A second session starting must not empty the log under the first one.

Browser recognition has no daemon, so `voice-shell.sh start --engine browser`
is what empties the utterance log. Emptied without asking, a second session
starting a moment after something was said threw that utterance away before
the session it was addressed to had read it, and nothing on screen or in the
log said so. Measured live: the log was 0 bytes with the mtime of the moment
the second session started, and no log_epoch was ever written next to it, so
the byte offsets recorded against the old log still read as current.
"""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/voice-shell/scripts"
sys.path.insert(0, str(SCRIPTS))

import voice_daemon as vd


class EmptyLogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)
        self.log = self.state / "utterances.jsonl"
        self.log.write_text('{"text": "said a moment ago", "to": "1"}\n',
                            encoding="utf-8")
        (self.state / "listeners").mkdir()
        (self.state / "listeners-gone").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def listening(self):
        """A registration for a process that really is running (this one)."""
        now = time.time()
        (self.state / "listeners" / str(os.getpid())).write_text(json.dumps({
            "cwd": "/work", "started": "2026-09-23 10:00:00",
            "since": now, "order": now, "session": "first"}), encoding="utf-8")

    def test_nobody_listening_so_the_log_is_emptied_with_a_new_epoch(self):
        vd.write_atomic(self.state / "log_epoch", "111")
        self.assertTrue(vd.empty_log_for_start(self.log))
        self.assertEqual(self.log.read_text(encoding="utf-8"), "")
        self.assertNotEqual(vd.log_epoch(self.log), "111")
        self.assertTrue(vd.log_epoch(self.log))

    def test_a_session_already_listening_keeps_what_it_has_not_read(self):
        self.listening()
        was = self.log.read_text(encoding="utf-8")
        self.assertFalse(vd.empty_log_for_start(self.log))
        self.assertEqual(self.log.read_text(encoding="utf-8"), was)
        # And nothing was stamped either. The log did not start over, so every
        # offset recorded against it still points where it did.
        self.assertFalse((self.state / "log_epoch").exists())

    def test_emptying_always_leaves_an_epoch_to_measure_against(self):
        # The one the daemon takes on startup. Without the epoch, a listen's
        # progress file and the viewer's clear-history mark are read against a
        # log that has started over from zero.
        vd.empty_log(self.log)
        first = vd.log_epoch(self.log)
        self.assertTrue(first)
        vd.empty_log(self.log)
        self.assertNotEqual(vd.log_epoch(self.log), first)

    def test_a_session_that_is_really_gone_does_not_hold_the_log(self):
        # A listen that is really over (past AWAY_HOLD, so nothing is routed
        # to it and no re-arm is waited on). Holding the log for it would
        # line last time's utterances up again, which is the one thing
        # emptying is for. One only between two watches does hold it, since
        # it comes back and replays from where its progress file stands.
        vd.write_atomic(vd._gone_file(self.log, "yesterday"), json.dumps({
            "session": "yesterday", "pid": "40856",
            "left": time.time() - vd.AWAY_HOLD * 2, "offset": 0, "epoch": "-",
            "reg": {"cwd": "/work", "started": "2026-09-22 00:34:03",
                    "since": time.time() - vd.AWAY_HOLD * 2, "session": "yesterday"}}))
        self.assertTrue(any(l.get("gone") for l in vd.list_active_listeners(self.log)))
        self.assertTrue(vd.empty_log_for_start(self.log))
        self.assertEqual(self.log.read_text(encoding="utf-8"), "")

    def test_a_session_between_two_watches_still_holds_it(self):
        vd.write_atomic(vd._gone_file(self.log, "between"), json.dumps({
            "session": "between", "pid": "40857", "left": time.time() - 5,
            "offset": 0, "epoch": "-",
            "reg": {"cwd": "/work", "started": "2026-09-23 00:34:03",
                    "since": time.time() - 5, "session": "between"}}))
        self.log.write_text('{"text": "said a moment ago", "to": "40857"}\n',
                            encoding="utf-8")
        self.assertFalse(vd.empty_log_for_start(self.log))
        self.assertTrue(self.log.read_text(encoding="utf-8"))

    def test_a_progress_offset_from_the_old_log_is_no_longer_read(self):
        (self.state / "listeners-gone" / "4321.progress").write_text(
            f"{vd.log_epoch(self.log) or '-'} 0", encoding="utf-8")
        self.assertEqual(vd.progress_of(self.log, "4321"), 0)
        vd.empty_log(self.log)
        self.assertIsNone(vd.progress_of(self.log, "4321"))


if __name__ == "__main__":
    unittest.main()
