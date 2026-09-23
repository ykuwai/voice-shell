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


class _Row:
    """A state folder with a log, a listeners folder and a tombstone folder."""

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


class ListenerGoneTest(_Row, unittest.TestCase):
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

    def test_it_is_still_there_days_later(self):
        # A machine left alone over a long weekend. Half a day used to drop the
        # session out of sight while it was still perfectly resumable.
        self.tomb(3 * 24 * 3600)
        entry, = vd.list_active_listeners(self.log)
        self.assertTrue(entry.get("gone"))


class AdoptAfterDaysTest(_Row, unittest.TestCase):
    """The same conversation coming back after a while takes its own entry
    back, so it is one thing on screen from beginning to end rather than a
    stranger arriving beside its own greyed out chip."""

    def test_the_same_session_can_still_take_its_entry_back_days_later(self):
        self.tomb(3 * 24 * 3600, session="s1")
        found = vd.adopt_tombstone(self.log, "s1")
        self.assertIsInstance(found, dict)
        self.assertEqual(found["pid"], "40856")

    def test_a_stranger_gets_nothing(self):
        self.tomb(3 * 24 * 3600, session="s1")
        self.assertIsNone(vd.adopt_tombstone(self.log, "somebody-else"))

    def test_past_the_showing_there_is_nothing_left_to_take_back(self):
        self.tomb(vd.ADOPT_GRACE + 60, session="s1")
        self.assertIsNone(vd.adopt_tombstone(self.log, "s1"))

    def test_nothing_is_replayed_after_a_long_gap(self):
        # Reading days of log back at once would bury whatever is said next,
        # and nothing has been addressed to it since it went anyway.
        self.tomb(3 * 24 * 3600, session="s1")
        self.assertEqual(vd.adopt_tombstone(self.log, "s1")["offset"], "")

    def test_a_re_arm_between_two_watches_still_replays(self):
        self.tomb(30, session="s1")
        found = vd.adopt_tombstone(self.log, "s1")
        self.assertEqual(found["offset"], 0)
        self.assertNotEqual(found["order"], "-")

    def test_a_long_gap_does_not_take_the_old_place_in_the_row_back(self):
        # While it was gone the chip sat at the end. An order from days ago
        # would jump it to the front and renumber every live one under the
        # person, which is the shuffle the row is arranged to avoid.
        self.tomb(3 * 24 * 3600, session="s1")
        self.assertEqual(vd.adopt_tombstone(self.log, "s1")["order"], "-")

    def test_the_three_values_survive_being_read_back_as_words(self):
        # voice-shell.sh reads them with `read -r pid order offset`, which
        # swallows a blank field in the middle. "-" is what keeps the offset
        # from being read as the order.
        self.tomb(3 * 24 * 3600, session="s1")
        f = vd.adopt_tombstone(self.log, "s1")
        line = f"{f['pid']} {f['order']} {f['offset']}"
        self.assertEqual(line.split(), ["40856", "-"])

    def test_a_deliberate_stop_still_goes_quickly(self):
        # unlisten and the x on a chip are unchanged. Nothing is kept for them
        # beyond long enough to turn away the one re-arm a disconnect causes.
        vd.write_atomic(vd._gone_file(self.log, "s1"), json.dumps({
            "session": "s1", "pid": "40856",
            "stopped": time.time() - (vd.LEAVE_GRACE + 60)}))
        self.assertEqual(vd.list_active_listeners(self.log), [])
        self.assertFalse(vd._gone_file(self.log, "s1").exists())

    def test_the_x_on_a_gone_chip_still_clears_it_quickly(self):
        # The chip is struck through but the x is still on it, and pressing it
        # has to mean the same as always. The row holds a gone one for a week
        # now, so a stop that left "left" in place behind "stopped" would park
        # it there for the whole week instead.
        self.tomb(vd.AWAY_HOLD + 30, session="s1")
        vd.mark_stopped(self.log, "s1", disconnected=True)
        data = json.loads(vd._gone_file(self.log, "s1").read_text(encoding="utf-8"))
        self.assertNotIn("left", data)
        # Off the row at once, the way a deliberate stop always has been. What
        # is kept for LEAVE_GRACE is only enough to turn away the one re-arm.
        self.assertEqual(vd.list_active_listeners(self.log), [])
        data["stopped"] -= vd.LEAVE_GRACE + 60
        vd.write_atomic(vd._gone_file(self.log, "s1"), json.dumps(data))
        self.assertEqual(vd.list_active_listeners(self.log), [])
        self.assertFalse(vd._gone_file(self.log, "s1").exists())

    def test_unlisten_on_one_already_gone_still_clears_it_quickly(self):
        self.tomb(vd.AWAY_HOLD + 30, session="s1")
        vd.unlisten(self.log, "s1")
        data = json.loads(vd._gone_file(self.log, "s1").read_text(encoding="utf-8"))
        self.assertNotIn("left", data)
        data["stopped"] -= vd.LEAVE_GRACE + 60
        vd.write_atomic(vd._gone_file(self.log, "s1"), json.dumps(data))
        self.assertEqual(vd.list_active_listeners(self.log), [])

    def test_a_disconnect_still_blocks_the_one_re_arm_it_causes(self):
        vd.write_atomic(vd._gone_file(self.log, "s1"), json.dumps({
            "session": "s1", "pid": "40856", "disconnected": True,
            "stopped": time.time() - 5}))
        self.assertEqual(vd.adopt_tombstone(self.log, "s1"), "blocked")


if __name__ == "__main__":
    unittest.main()
