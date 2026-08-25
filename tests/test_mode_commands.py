import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/voice-shell/scripts"
sys.path.insert(0, str(SCRIPTS))

from voice_daemon import mode_command_shape


class HoldModeTailTest(unittest.TestCase):
    """The word alone still works, and so does a short noise prefix ahead of it
    (same class of bug as #76 for mute): a burst the room picked up landing in
    front of the real word used to fail the exact match and go nowhere, leaving
    the session stuck taking unrelated chatter as instructions instead of
    parking it for review."""

    def test_bare_word(self):
        self.assertEqual(mode_command_shape("手直し"), "hold")
        self.assertEqual(mode_command_shape("手直しモード"), "hold")

    def test_short_noise_prefix(self):
        self.assertEqual(mode_command_shape("はい手直し"), "hold")

    def test_ordinary_sentence_is_not_swallowed(self):
        # Ends with a real HOLD_MODE_TAIL wording ("溜める"), but the clause
        # ahead of it is well past the noise ceiling, so this stays a prompt.
        self.assertEqual(mode_command_shape("今月は頑張ってお金を溜める"), None)

    def test_english(self):
        self.assertEqual(mode_command_shape("hold"), "hold")
        self.assertEqual(mode_command_shape("draft mode"), "hold")


class LiveModeStaysExactTest(unittest.TestCase):
    """Switching back to instant stays exact only, a false hit there means
    speech during a call goes straight through again, unlike a false hold
    which only parks one utterance for review."""

    def test_bare_word(self):
        self.assertEqual(mode_command_shape("即時"), "live")

    def test_noise_prefix_is_not_swallowed(self):
        self.assertIsNone(mode_command_shape("はい即時"))


if __name__ == "__main__":
    unittest.main()
