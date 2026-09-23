"""#110: a session whose listen ended must stop being a place speech can land.

Overnight a Monitor watch ended, the `listen` behind it stayed up on Windows
with nothing reading it, and its registration kept being touched. Hours later
the chip was still lit, still the destination, and what was said went to it and
was lost. The listen exits on its own now (test_listen_filter.py), which turns
the leftover into a tombstone. These are about what the row shows from then on:
the entry may stay, but it has to be plain that it cannot be used.
"""
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/voice-shell/scripts"
sys.path.insert(0, str(SCRIPTS))

import voice_daemon as vd


class ListenerGoneTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        state = Path(self.tmp.name)
        self.log = state / "utterances.jsonl"
        self.log.write_text("", encoding="utf-8")
        (state / "listeners").mkdir()
        (state / "listeners-gone").mkdir()
        self.route = state / "route"

    def tearDown(self):
        self.tmp.cleanup()

    def live(self, session="s2", pid=None):
        """A registration for a process that really is running (this one)."""
        import os
        pid = pid or str(os.getpid())
        now = time.time()
        (Path(self.tmp.name) / "listeners" / pid).write_text(json.dumps({
            "cwd": "/work", "started": "2026-09-23 10:00:00",
            "since": now, "order": now, "session": session}), encoding="utf-8")
        return pid

    def tomb(self, left_ago, pid="40856", session="s1"):
        vd.write_atomic(vd._gone_file(self.log, session), json.dumps({
            "session": session, "pid": pid, "left": time.time() - left_ago,
            "offset": 0, "epoch": "-",
            "reg": {"cwd": "/work", "started": "2026-09-23 00:34:03",
                    "since": time.time() - left_ago, "session": session},
        }))
        return pid

    def test_between_two_watches_is_away_and_still_chosen(self):
        # Inside the hold nothing has changed. The chip stays, speech is kept
        # for it, and its next watch replays what it missed.
        pid = self.tomb(5)
        entry, = vd.list_active_listeners(self.log)
        self.assertTrue(entry["away"])
        self.assertFalse(entry.get("gone"))
        self.assertEqual(vd.resolve_target(self.log), pid)

    def test_past_the_hold_it_is_marked_gone(self):
        self.tomb(vd.AWAY_HOLD + 30)
        entry, = vd.list_active_listeners(self.log)
        self.assertTrue(entry.get("gone"))
        self.assertTrue(entry["away"])

    def test_nothing_is_routed_to_one_that_is_gone(self):
        self.tomb(vd.AWAY_HOLD + 30)
        # Nobody named means every listener drops the line. Better than
        # handing it to a listen no one is reading.
        self.assertIsNone(vd.resolve_target(self.log))

    def test_a_gone_one_named_in_the_route_file_is_let_go(self):
        # The shape of the incident itself: the route file still held the PID
        # of a session that had stopped reading hours earlier.
        pid = self.tomb(vd.AWAY_HOLD + 30)
        vd.write_atomic(self.route, pid)
        self.assertIsNone(vd.resolve_target(self.log))
        self.assertEqual(self.route.read_text(encoding="utf-8").strip(), "")

    def test_a_live_listener_is_still_preferred_over_a_gone_one(self):
        self.tomb(vd.AWAY_HOLD + 30)
        mine = self.live()
        self.assertEqual(vd.resolve_target(self.log), mine)

    def test_it_stays_in_the_row_long_after_the_grace(self):
        # Someone who steps away and comes back hours later still has to see
        # that the session is there and is not listening. LEAVE_GRACE is only
        # how long it can be adopted, which is a different question.
        self.tomb(vd.LEAVE_GRACE + 3600)
        entry, = vd.list_active_listeners(self.log)
        self.assertTrue(entry.get("gone"))

    def test_it_goes_for_good_once_the_showing_is_over(self):
        self.tomb(vd.GONE_SHOW + 60)
        self.assertEqual(vd.list_active_listeners(self.log), [])

    def test_only_the_most_recent_few_are_kept(self):
        # The row cannot grow without bound. Older than the newest few, and
        # the file goes too rather than sit there unseen.
        for i in range(vd.GONE_KEEP + 3):
            self.tomb(vd.AWAY_HOLD + 60 + i * 60, pid=str(50000 + i),
                      session="s-old-%d" % i)
        out = vd.list_active_listeners(self.log)
        self.assertEqual(len(out), vd.GONE_KEEP)
        # The newest ones, which are the ones that left least long ago.
        self.assertEqual({e["pid"] for e in out},
                         {str(50000 + i) for i in range(vd.GONE_KEEP)})

    def test_a_gone_one_does_not_hold_a_number_a_live_one_should_have(self):
        # The tombstone registered long before the live session did, so by
        # plain order it would come first and take number 1.
        self.tomb(vd.LEAVE_GRACE + 3600)
        mine = self.live()
        order = [str(e["pid"]) for e in vd.list_active_listeners(self.log)]
        self.assertEqual(order, [mine, "40856"])

    def test_one_between_two_watches_keeps_its_place(self):
        # Away is not gone. Its next watch takes the same number back, so it
        # must not be pushed to the end the way a gone one is.
        self.tomb(5)
        mine = self.live()
        order = [str(e["pid"]) for e in vd.list_active_listeners(self.log)]
        self.assertEqual(order, ["40856", mine])


if __name__ == "__main__":
    unittest.main()
