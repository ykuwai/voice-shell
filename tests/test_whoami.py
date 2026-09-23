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

        Only this process's own pid is alive to register under, so a test that
        needs a second entry uses a tombstone for the other one, which is what
        a session between two watches really looks like anyway.
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

    def test_a_chip_of_a_session_between_two_watches_says_so(self):
        # #110 again if this read as "listening". The chip is there, keeps its
        # number, and nothing is reading through it, so the caller has to be
        # able to tell that apart and start `listen`.
        self.tomb(5, pid="40856", session="s-mine")
        found = vd.whoami_of(self.log, "s-mine")
        self.assertEqual(found["no"], 1)
        self.assertEqual(found["state"], "away")

    def test_a_chip_whose_listen_ended_for_good_says_so(self):
        self.tomb(vd.LEAVE_GRACE + 3600, pid="40856", session="s-mine")
        self.assertEqual(vd.whoami_of(self.log, "s-mine")["state"], "gone")

    def test_one_that_is_really_listening_says_live(self):
        self.live("s-mine")
        self.assertEqual(vd.whoami_of(self.log, "s-mine")["state"], "live")

    def test_a_chip_holding_a_place_is_not_counted_as_listening(self):
        # The row is two chips deep, but the other one is between two watches
        # and nobody is reading through it. Handing the row size over as the
        # number listening would tell the user two sessions can hear them.
        self.tomb(5, pid="40856", session="s-old")
        self.live("s-mine")
        found = vd.whoami_of(self.log, "s-mine")
        self.assertEqual(found["total"], 2)
        self.assertEqual(found["live"], 1)

    def test_a_gone_chip_is_not_counted_as_listening_either(self):
        self.tomb(vd.LEAVE_GRACE + 3600, pid="40856", session="s-old")
        self.live("s-mine")
        found = vd.whoami_of(self.log, "s-mine")
        self.assertEqual(found["total"], 2)
        self.assertEqual(found["live"], 1)

    def test_a_renamed_session_is_told_its_new_name(self):
        # "name this session X" writes the name into the registration, and the
        # chip is drawn with it. That is the name to say out loud, not the
        # folder it happens to be running in.
        pid = self.live("s-mine", cwd="/work/auth")
        reg = Path(self.tmp.name) / "listeners" / pid
        info = json.loads(reg.read_text(encoding="utf-8"))
        info["name"] = "認証まわりの修正"
        reg.write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(vd.whoami_of(self.log, "s-mine")["label"],
                         "認証まわりの修正")

    def test_a_renamed_session_keeps_the_suffix_the_chip_shows(self):
        # Renamed onto a name another chip already has. The screen writes
        # "docs (2)", so that is what has to be said.
        self.tomb(5, pid="40856", session="s-old", cwd="/a/docs")
        pid = self.live("s-mine", cwd="/work/auth")
        reg = Path(self.tmp.name) / "listeners" / pid
        info = json.loads(reg.read_text(encoding="utf-8"))
        info["name"] = "docs"
        reg.write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
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
