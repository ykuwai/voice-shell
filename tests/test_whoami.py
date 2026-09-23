"""Which chip this session is, asked for by the session itself.

With several sessions listening the user cannot tell which one they are talking
to, so the agent says the number and the name in its first message. The number
has to be the one drawn on screen, counted the one way the row is already
counted, and it must never be guessed for a session that is not in the row.
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


class _Row:
    """A state folder with a log, a listeners folder and a tombstone folder."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        state = Path(self.tmp.name)
        self.log = state / "utterances.jsonl"
        self.log.write_text("", encoding="utf-8")
        (state / "listeners").mkdir()
        (state / "listeners-gone").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def live(self, session, pid=None, cwd="/work/auth", order=None):
        """A registration for a process that really is running (this one).

        Only one pid can be alive to register under, so a second live entry is
        faked by writing the same pid under a different name is not possible.
        Tests that need two entries use a tombstone for the other one, which is
        what a session between two watches really looks like.
        """
        pid = pid or str(os.getpid())
        now = time.time()
        (Path(self.tmp.name) / "listeners" / pid).write_text(json.dumps({
            "cwd": cwd, "started": "2026-09-23 10:00:00",
            "since": now, "order": order if order is not None else now,
            "session": session}), encoding="utf-8")
        return pid

    def tomb(self, left_ago, pid, session, cwd="/work/docs"):
        vd.write_atomic(vd._gone_file(self.log, session), json.dumps({
            "session": session, "pid": pid, "left": time.time() - left_ago,
            "offset": 0, "epoch": "-",
            "reg": {"cwd": cwd, "started": "2026-09-23 00:34:03",
                    "since": time.time() - left_ago, "order": time.time() - left_ago,
                    "session": session},
        }))
        return pid


class WhoamiTest(_Row, unittest.TestCase):
    def test_the_only_session_is_number_one(self):
        self.live("s-mine")
        found = vd.whoami_of(self.log, "s-mine")
        self.assertEqual(found["no"], 1)
        self.assertEqual(found["total"], 1)

    def test_the_name_is_the_one_drawn_on_the_chip(self):
        # Nobody has named it, so it is the folder name, exactly as
        # `listeners` and the viewer both show it.
        self.live("s-mine", cwd="/work/auth")
        self.assertEqual(vd.whoami_of(self.log, "s-mine")["label"], "auth")

    def test_the_number_counts_the_row_the_viewer_draws(self):
        # An earlier session between two watches keeps its place, so this one
        # is the second chip and has to be told so.
        self.tomb(5, pid="40856", session="s-old")
        self.live("s-mine")
        found = vd.whoami_of(self.log, "s-mine")
        self.assertEqual(found["no"], 2)
        self.assertEqual(found["total"], 2)
        # The same count the row itself is numbered by, not a second one.
        row = vd.list_active_listeners(self.log)
        self.assertEqual(row[found["no"] - 1]["session"], "s-mine")

    def test_a_gone_one_does_not_hold_the_number_back(self):
        # Gone entries sort to the end of the row, so a live session is
        # number 1 even though the gone one registered first.
        self.tomb(vd.LEAVE_GRACE + 3600, pid="40856", session="s-old")
        self.live("s-mine")
        self.assertEqual(vd.whoami_of(self.log, "s-mine")["no"], 1)

    def test_a_duplicated_name_carries_its_suffix(self):
        # Two sessions in folders of the same name. The chip says "docs (2)",
        # so that is what the user has to be told, not a bare "docs".
        self.tomb(5, pid="40856", session="s-old", cwd="/a/docs")
        self.live("s-mine", cwd="/b/docs")
        self.assertEqual(vd.whoami_of(self.log, "s-mine")["label"], "docs (2)")

    def test_a_session_that_is_not_listening_gets_nothing(self):
        self.live("s-mine")
        self.assertIsNone(vd.whoami_of(self.log, "somebody-else"))

    def test_no_session_id_at_all_gets_nothing(self):
        # A tool that hands over no conversation id must not be handed the
        # first chip in the row by accident.
        self.live("s-mine")
        self.assertIsNone(vd.whoami_of(self.log, ""))


if __name__ == "__main__":
    unittest.main()
