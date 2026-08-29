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
    tighter noise ceiling (3 chars, not 7) and a narrower wordlist. 「解除」/
    「かいじょ」 on their own used to be in that list too, exact-match only (never
    through the tail fallback, they were excluded from that from the start). Real
    use showed the exact-match side was not narrow enough either, someone saying
    just that one word as a complete reply to something unrelated, muted at the
    time, had it read as a command anyway. Pulled out entirely now, only wordings
    that name 「ミュート」 or 「マイク」 somewhere remain."""

    def test_bare_phrase(self):
        self.assertEqual(mic_command_shape("ミュート解除", True), "unmute")

    def test_generic_bare_word_no_longer_matches(self):
        # Used to exact-match on their own. Pulled from the wordlist after a
        # report of unrelated speech (muted at the time) firing this, since
        # both stand on their own as ordinary words, not only as a reply to
        # this tool.
        self.assertIsNone(mic_command_shape("解除", True))
        self.assertIsNone(mic_command_shape("かいじょ", True))

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
        # A generic sentence that merely ends in 「解除」 should not fire
        # through the tail fallback either, now that the word carries no
        # match of its own to fall back from.
        self.assertIsNone(mic_command_shape("その契約を解除", True))

    def test_already_unmuted_does_nothing(self):
        self.assertIsNone(mic_command_shape("ミュート解除", False))


if __name__ == "__main__":
    unittest.main()
