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
    """The Draft loanword switches only when said alone, or with nothing but a
    filler ahead of it. A draft is something people talk about, and a sentence
    that ends on it has to go through."""

    def test_alone_switches(self):
        for w in ("ドラフト", "どらふと", "ドラフトモード", "드래프트 모드"):
            self.assertEqual(mode_command_shape(w), "hold", w)

    def test_only_a_filler_ahead_still_switches(self):
        for s in ("えーとドラフト", "あのドラフト", "うんドラフトモード", "はい、ドラフト",
                  "えーと、あのー、ドラフト。", "음 드래프트 모드", "어, 드래프트 모드"):
            self.assertEqual(mode_command_shape(s), "hold", s)

    def test_sentences_ending_on_it_go_through(self):
        for s in ("PRをドラフトにして", "このメールをドラフトにして", "今年のドラフト",
                  "PR을 드래프트 모드", "ドラフトにして", "えーと今年のドラフト",
                  "はいPRをドラフト", "이번 드래프트 모드"):
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
                  "インスタンスを止めて", "このカメラはインスタント", "えーとインスタント麺"):
            self.assertIsNone(mode_command_shape(s), s)

    def test_instant_loanword_after_a_filler(self):
        for s in ("はいインスタント", "えーと、インスタントモード", "うん、インスタント"):
            self.assertEqual(mode_command_shape(s), "live", s)


class CommonWordsNeedAWholeUtteranceTest(unittest.TestCase):
    """The loanwords and the English (and other) names of the modes turn up in
    ordinary talk. They switch only said alone or after nothing but fillers,
    the same as ドラフト, and anything else ahead of them leaves the utterance
    as ordinary text."""

    HOLD = ("エディット", "えでぃっと", "エディットモード", "draft", "draft mode",
            "edit mode", "hold", "hold mode", "borrador", "modo borrador",
            "brouillon", "Entwurf", "초안 모드", "草稿模式")
    LIVE = ("live", "live mode", "instant", "instant mode", "send live")

    def test_alone_switches(self):
        for w in self.HOLD:
            self.assertEqual(mode_command_shape(w), "hold", w)
        for w in self.LIVE:
            self.assertEqual(mode_command_shape(w), "live", w)

    def test_only_fillers_ahead_still_switch(self):
        for s in ("えーとエディット", "はい、エディットモード", "um, draft", "Uh draft mode",
                  "okay, edit mode", "hmm hold", "eh, borrador", "euh brouillon",
                  "Ähm, Entwurf", "음 초안 모드", "嗯，草稿模式"):
            self.assertEqual(mode_command_shape(s), "hold", s)
        for s in ("um live", "uh, live mode", "okay instant", "yeah, send live"):
            self.assertEqual(mode_command_shape(s), "live", s)

    def test_fillers_ending_in_a_long_vowel(self):
        # 「えー」 had its ー trimmed before the comparison and matched nothing
        for s in ("えードラフト", "そのードラフト", "えーーードラフト", "えー、エディット"):
            self.assertEqual(mode_command_shape(s), "hold", s)
        self.assertEqual(mode_command_shape("あーインスタント"), "live")
        self.assertIsNone(mode_command_shape("え、ドラフト"))

    def test_anything_else_ahead_stays_text(self):
        for s in ("記事をエディット", "写真をえでぃっと", "このページをエディットモード",
                  "save a draft", "a draft", "the draft", "write a draft mode",
                  "put it on hold", "withhold", "please hold",
                  "un borrador", "le brouillon", "der Entwurf", "이메일 초안 모드",
                  "邮件草稿模式"):
            self.assertIsNone(mode_command_shape(s), s)
        for s in ("go live", "we are live", "the site is live", "an instant",
                  "make it instant", "umbrella live"):
            self.assertIsNone(mode_command_shape(s), s)

    def test_not_in_the_tail(self):
        for w in self.HOLD:
            self.assertNotIn(w, HOLD_MODE_TAIL)

    def test_native_words_keep_their_lead_in(self):
        self.assertEqual(mode_command_shape("はい手直し"), "hold")
        self.assertEqual(mode_command_shape("それで手直しモード"), "hold")
        self.assertEqual(mode_command_shape("溜めて"), "hold")

    def test_edit_is_no_longer_a_trailing_signal(self):
        # 「記事をエディット」 was cut down to 「記事を」 and parked in the draft
        from voice_daemon import HOLD_TAIL, take_tail
        self.assertIsNone(take_tail("記事をエディット", HOLD_TAIL))
        self.assertEqual(take_tail("記事を直して、手直し", HOLD_TAIL), "記事を直して")


class MoreFillersAheadTest(unittest.TestCase):
    """Fillers that were missing, so the mode word after them went nowhere."""

    def test_hold_after_a_filler(self):
        for s in ("えーっとドラフト", "ええっと、ドラフト", "umm, draft", "ah draft mode",
                  "oh, draft", "well, draft mode", "那个草稿模式", "este borrador",
                  "pues, borrador", "bueno, borrador", "o sea, borrador",
                  "ben, brouillon", "bah brouillon", "alors, brouillon", "heu brouillon",
                  "also, Entwurf", "naja Entwurf", "öhm Entwurf",
                  "저기 초안 모드", "그러니까 초안 모드", "아 초안 모드"):
            self.assertEqual(mode_command_shape(s), "hold", s)

    def test_real_words_are_not_deleted_from_a_sentence(self):
        from voice_daemon import strip_fillers
        self.assertEqual(strip_fillers("ええっと、これを開いて", "ja"), "これを開いて")
        self.assertEqual(strip_fillers("えーっと、これを開いて", "ja"), "これを開いて")
        self.assertEqual(strip_fillers("umm, open it", "en"), "open it")
        self.assertEqual(strip_fillers("it works well", "en"), "it works well")
        self.assertEqual(strip_fillers("abre este archivo", "es"), "abre este archivo")
        self.assertEqual(strip_fillers("打开那个文件", "zh"), "打开那个文件")


class InstantWordsInOtherLanguagesTest(unittest.TestCase):
    """The live words of every language take a filler-only lead-in, like Draft."""

    def test_after_a_filler(self):
        for s in ("eh directo", "eh, modo directo", "este, en directo", "euh en direct",
                  "euh, mode direct", "ähm Sofortmodus", "äh, Direkt senden",
                  "呃即时模式", "嗯，直接发送", "嗯，即時模式", "음 즉시 모드",
                  "어, 바로 전달"):
            self.assertEqual(mode_command_shape(s), "live", s)

    def test_anything_else_ahead_stays_text(self):
        for s in ("el partido en directo", "je suis en direct", "bitte Direkt senden",
                  "请直接发送", "지금 바로 전달"):
            self.assertIsNone(mode_command_shape(s), s)


if __name__ == "__main__":
    unittest.main()
