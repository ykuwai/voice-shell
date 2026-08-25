import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/voice-shell/scripts"
sys.path.insert(0, str(SCRIPTS))

from voice_daemon import mic_command_shape


class MuteTailTest(unittest.TestCase):
    """The word alone still works, and so does a short noise prefix ahead of it
    (#76): a burst the room picked up landing in front of the real word used to
    fail both the exact match and the length gate and go nowhere."""

    def test_bare_word(self):
        self.assertEqual(mic_command_shape("ミュート", False), "mute")

    def test_short_noise_prefix(self):
        self.assertEqual(mic_command_shape("はいミュート", False), "mute")

    def test_ordinary_sentence_is_not_swallowed(self):
        # Ends with a real MUTE_TAIL wording, but the clause ahead of it is well
        # past the noise ceiling, so this stays a prompt, not a command.
        self.assertIsNone(mic_command_shape("今からこの通話を静かにするためミュート", False))

    def test_already_muted_does_nothing(self):
        self.assertIsNone(mic_command_shape("ミュート", True))
        self.assertIsNone(mic_command_shape("はいミュート", True))


class UnmuteTailTest(unittest.TestCase):
    """Same idea, extended to unmute after the mute fix proved out, but held to a
    tighter noise ceiling (3 chars, not 7) and a narrower wordlist: bare, generic
    words like 「解除」/「かいじょ」 are excluded from the tail fallback since a false
    hit here costs the whole stretch the speaker thought was off, not one
    utterance. They still work as an exact match on their own."""

    def test_bare_phrase(self):
        self.assertEqual(mic_command_shape("ミュート解除", True), "unmute")

    def test_bare_word_still_exact_matches(self):
        self.assertEqual(mic_command_shape("解除", True), "unmute")
        self.assertEqual(mic_command_shape("かいじょ", True), "unmute")

    def test_short_noise_prefix(self):
        self.assertEqual(mic_command_shape("えーとミュート解除", True), "unmute")

    def test_noise_prefix_at_the_ceiling(self):
        # 3-character body, right at UNMUTE_TAIL_NOISE_MAX.
        self.assertEqual(mic_command_shape("まあねミュート解除", True), "unmute")

    def test_noise_prefix_over_the_ceiling_is_not_swallowed(self):
        # 4-character body, one over the ceiling.
        self.assertIsNone(mic_command_shape("いやまあねミュート解除", True))

    def test_trailing_punctuation_is_tolerated(self):
        self.assertEqual(mic_command_shape("はい、ミュート解除", True), "unmute")

    def test_excluded_bare_word_does_not_tail_match(self):
        # 「解除」 alone would exact-match (see above), but a generic sentence that
        # merely ends with it should not fire through the tail fallback, it is
        # excluded from UNMUTE_TAIL on purpose.
        self.assertIsNone(mic_command_shape("その契約を解除", True))

    def test_already_unmuted_does_nothing(self):
        self.assertIsNone(mic_command_shape("ミュート解除", False))


if __name__ == "__main__":
    unittest.main()
