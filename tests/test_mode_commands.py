import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/voice-shell/scripts"
sys.path.insert(0, str(SCRIPTS))

from voice_daemon import HOLD_MODE_TAIL, mode_command_shape


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


class DraftLoanwordIsExactOnlyTest(unittest.TestCase):
    """The Draft loanword switches only when said alone. A draft is something
    people talk about, and a sentence that ends on it has to go through."""

    def test_alone_switches(self):
        for w in ("ドラフト", "どらふと", "ドラフトモード", "드래프트 모드"):
            self.assertEqual(mode_command_shape(w), "hold", w)

    def test_sentences_ending_on_it_go_through(self):
        for s in ("PRをドラフトにして", "このメールをドラフトにして", "今年のドラフト",
                  "PR을 드래프트 모드", "ドラフトにして", "はいドラフト"):
            self.assertIsNone(mode_command_shape(s), s)

    def test_not_in_the_tail(self):
        for w in ("ドラフト", "どらふと", "ドラフトモード", "드래프트 모드", "ドラフトにして"):
            self.assertNotIn(w, HOLD_MODE_TAIL)


class LiveModeStaysExactTest(unittest.TestCase):
    """Switching back to instant stays exact only, a false hit there means
    speech during a call goes straight through again, unlike a false hold
    which only parks one utterance for review."""

    def test_bare_word(self):
        self.assertEqual(mode_command_shape("即時"), "live")

    def test_noise_prefix_is_not_swallowed(self):
        self.assertIsNone(mode_command_shape("はい即時"))

    def test_instant_loanword_alone_only(self):
        self.assertEqual(mode_command_shape("インスタント"), "live")
        self.assertEqual(mode_command_shape("インスタントモード"), "live")
        for s in ("インスタント麺", "インスタント麺を買って", "インスタンスを起動して",
                  "インスタンスを止めて", "はいインスタント"):
            self.assertIsNone(mode_command_shape(s), s)


if __name__ == "__main__":
    unittest.main()
