import subprocess
import sys
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


if __name__ == "__main__":
    unittest.main()
