import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/voice-shell/scripts"


def run_filter(me, lines):
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "listen_filter.py"), me],
        input="\n".join(lines) + "\n",
        text=True,
        capture_output=True,
    )
    return [line for line in result.stdout.splitlines() if line]


class ListenFilterTest(unittest.TestCase):
    def test_utterance_addressed_to_me_passes(self):
        out = run_filter("111", ['{"text":"hello","to":"111"}'])
        self.assertEqual(out, ['{"text":"hello","to":"111"}'])

    def test_utterance_addressed_elsewhere_is_dropped(self):
        out = run_filter("111", ['{"text":"hello","to":"222"}'])
        self.assertEqual(out, [])

    def test_utterance_with_no_to_is_dropped(self):
        out = run_filter("111", ['{"text":"hello"}'])
        self.assertEqual(out, [])

    def test_broadcast_warning_with_no_to_reaches_everyone(self):
        # #91 predates this, the counting-listeners warning voice_daemon.py
        # writes for "N monitors listening at once" carries no "to" on purpose.
        out = run_filter("111", ['{"system_warning":"x"}'])
        self.assertEqual(out, ['{"system_warning":"x"}'])

    def test_targeted_warning_reaches_only_that_session(self):
        # The disconnect notice viewer.py writes carries "to". Before this, any
        # system_warning bypassed the "to" filter outright and reached every
        # session listening, not just the one that was disconnected.
        out = run_filter("111", ['{"system_warning":"x","to":"111"}'])
        self.assertEqual(out, ['{"system_warning":"x","to":"111"}'])

    def test_targeted_warning_for_someone_else_is_dropped(self):
        out = run_filter("111", ['{"system_warning":"x","to":"222"}'])
        self.assertEqual(out, [])


class ParentGoneTest(unittest.TestCase):
    """#110: a Monitor watch that ends takes down the shell the command ran in
    and, on Windows, nothing else. The listen left behind kept its
    registration warm, stayed the chosen destination and read nothing, so an
    utterance addressed to it was lost. The filter watches that shell now."""

    def test_exits_when_the_shell_it_was_started_from_goes(self):
        parent = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(120)"])
        env = dict(os.environ, VOICE_SHELL_PARENT_PID=str(parent.pid))
        proc = subprocess.Popen(
            [sys.executable, str(SCRIPTS / "listen_filter.py"), "111"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env)
        try:
            time.sleep(1)               # long enough for the watcher to arm
            parent.kill()
            parent.wait()               # reaped, or POSIX still answers for it
            # Nothing is addressed to 111, so the filter never writes and never
            # finds out that way. Without the watcher it waits on stdin forever.
            proc.wait(timeout=30)
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.stdin.close()
            proc.stdout.close()
            proc.wait()

    def test_stays_when_that_shell_is_still_there(self):
        parent = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"])
        env = dict(os.environ, VOICE_SHELL_PARENT_PID=str(parent.pid))
        proc = subprocess.Popen(
            [sys.executable, str(SCRIPTS / "listen_filter.py"), "111"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env)
        try:
            time.sleep(7)               # past one round of the watch
            self.assertIsNone(proc.poll())
        finally:
            proc.kill()
            proc.stdin.close()
            proc.stdout.close()
            proc.wait()
            parent.kill()
            parent.wait()


if __name__ == "__main__":
    unittest.main()
