"""Full-width Latin letters and digits are folded to half-width.

Chrome's on-device Japanese recognition writes 「ＰＲ」 and 「２０２６」 full-width,
where what was meant is code and numbers. The fold runs at the point every engine's
text comes in, above the dictionary and the command matching, so what reaches Claude,
the screen and the log is the same either way.

The JS half is cut out of viewer.js and run under node, the way test_on_device.py
does it.
"""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/voice-shell/scripts"
sys.path.insert(0, str(SCRIPTS))

from voice_daemon import (apply_replacements, collapse_letter_acronyms,
                          command_key, is_allowed_short, is_noise, polish,
                          to_halfwidth)

VIEWER_JS = SCRIPTS / "viewer.js"
DAEMON_PY = SCRIPTS / "voice_daemon.py"
VIEWER_PY = SCRIPTS / "viewer.py"

HARNESS = r"""
const fs = require('fs');
const source = fs.readFileSync(process.argv[1], 'utf8');
const start = source.indexOf('// Full-width Latin letters and digits');
const end = source.indexOf('const TAIL_IDS = ', start);
if (start < 0 || end < 0) process.exit(2);
const h = new Function(`${source.slice(start, end)}
  return {toHalfWidth};`)();
const assert = (cond, what) => { if (!cond) { console.error(what); process.exit(1); } };
"""


def run(script):
    subprocess.run(["node", "-e", HARNESS + script, str(VIEWER_JS)], check=True)


class ToHalfWidthTest(unittest.TestCase):
    def test_latin_letters_and_digits_fold(self):
        self.assertEqual(to_halfwidth("ＰＲを２０２６年に出す"), "PRを2026年に出す")
        self.assertEqual(to_halfwidth("ｇｉｔ　ｐｕｓｈ"), "git　push")

    def test_the_symbols_that_only_ever_mean_code_fold(self):
        self.assertEqual(to_halfwidth("＠＃＆％＋＝／＼＿＜＞＄＊＾｜｀［］｛｝"),
                         r"@#&%+=/\_<>$*^|`[]{}")

    def test_japanese_punctuation_is_left_alone(self):
        for s in ["、", "。", "「", "」", "・", "？", "！", "：", "；", "，", "．",
                  "（", "）", "〜", "～", "ー", "　", "あア亜"]:
            self.assertEqual(to_halfwidth(s), s, s)
        self.assertEqual(to_halfwidth("これは「ＰＲ」です。ー〜"), "これは「PR」です。ー〜")

    def test_half_width_katakana_is_written_full_width(self):
        self.assertEqual(to_halfwidth("ｱｲｳ"), "アイウ")
        # A dakuten is its own character half-width, so the run composes as a whole
        self.assertEqual(to_halfwidth("ｶﾞｷﾞ ﾊﾟ"), "ガギ パ")
        self.assertEqual(to_halfwidth("ｺｰﾋｰ"), "コーヒー")

    def test_it_changes_nothing_in_plain_text(self):
        for s in ["git push origin main", "これでお願いします。", ""]:
            self.assertEqual(to_halfwidth(s), s, s)


class FoldedTextFlowsOnTest(unittest.TestCase):
    """Everything downstream sees half-width, because the fold runs above it."""

    def test_command_key_folds_letters_as_well_as_digits(self):
        self.assertEqual(command_key("ＰＲ"), "pr")
        self.assertEqual(command_key("ｍｕｔｅ"), "mute")
        self.assertEqual(command_key("２番"), "2番")
        self.assertEqual(command_key("ﾐｭｰﾄ"), "ミュート")

    def test_the_tail_match_folds_the_same_way(self):
        from voice_daemon import _folded_chars
        self.assertEqual("".join(f for f, _ in _folded_chars("ＲＯＵＴｅ２")), "route2")

    def test_an_acronym_read_out_letter_by_letter_folds_then_collapses(self):
        self.assertEqual(collapse_letter_acronyms(to_halfwidth("Ｇ Ｐ Ｕ")), "GPU")


class DictionaryTest(unittest.TestCase):
    """An entry registered with full-width letters still matches the folded text."""

    def test_a_full_width_key_matches(self):
        self.assertEqual(apply_replacements("AWSを使う", {"ＡＷＳ": "Amazon Web Services"}),
                         "Amazon Web Servicesを使う")

    def test_the_replacement_itself_is_left_as_written(self):
        self.assertEqual(apply_replacements("まるしー", {"まるしー": "Ⓒ ＡＢＣ"}), "Ⓒ ＡＢＣ")

    def test_polish_runs_the_folded_key(self):
        d = {"replace": {"ＰＲ": "pull request"}, "ignore": [], "unignore": []}
        self.assertEqual(polish(to_halfwidth("ＰＲを出して"), d), "pull requestを出して")

    def test_a_full_width_ignore_word_still_ignores(self):
        self.assertTrue(is_noise("ok", extra=["ＯＫ"]))

    def test_a_full_width_unignore_word_still_gets_through(self):
        self.assertTrue(is_allowed_short("OK", allow=["ＯＫ"]))


class OrderTest(unittest.TestCase):
    """The fold sits above the command matching, the floor on length and the
    dictionary, on both roads in. Below any of them and the same words would
    arrive or not depending on how they were recognized."""

    def test_the_daemon_folds_before_it_decides_anything(self):
        src = DAEMON_PY.read_text(encoding="utf-8")
        fold = src.index('text = to_halfwidth(ev["text"]).strip()')
        self.assertLess(fold, src.index("kind = apply_voice_command(text, log_path"))
        self.assertLess(fold, src.index("len(text) < args.min_chars"))
        self.assertLess(fold, src.index("polished = polish(text, user_dict"))

    def test_the_daemon_folds_the_partial_it_shows(self):
        src = DAEMON_PY.read_text(encoding="utf-8")
        self.assertIn('partial_path.write_text(to_halfwidth(ev["text"])', src)

    def test_the_browser_road_folds_before_it_decides_anything(self):
        src = VIEWER_PY.read_text(encoding="utf-8")
        fold = src.index('vd.to_halfwidth((body.get("text") or "")).strip()')
        self.assertLess(fold, src.index("kind = vd.apply_voice_command(text"))
        self.assertLess(fold, src.index("len(text) < int(min_chars)"))
        self.assertLess(fold, src.index("polished = vd.polish(text, user_dict"))


class ViewerJsTest(unittest.TestCase):
    def test_to_half_width_matches_the_python_one(self):
        run(r"""
assert(h.toHalfWidth('ＰＲを２０２６年に出す') === 'PRを2026年に出す', 'letters and digits');
assert(h.toHalfWidth('＠＃＆％＋＝／＼＿＜＞') === '@#&%+=/\\_<>', 'code symbols');
assert(h.toHalfWidth('これは「ＰＲ」です。ー〜') === 'これは「PR」です。ー〜', 'prose left alone');
assert(h.toHalfWidth('　') === '　', 'the full-width space stays');
assert(h.toHalfWidth('ｶﾞｷﾞ ﾊﾟ') === 'ガギ パ', 'half-width kana composes');
assert(h.toHalfWidth('git push') === 'git push', 'plain text untouched');
""")

    def test_the_interim_on_screen_is_already_folded(self):
        src = VIEWER_JS.read_text(encoding="utf-8")
        self.assertIn("toHalfWidth(stripInventedSpaces(res[0].transcript))", src)
        # The preview's own copy of the dictionary matches on the folded side too
        self.assertIn("toHalfWidth(k), v", src)
        # and so do the two screen-side copies of the server's command_key
        self.assertIn("toHalfWidth(c).toLowerCase()", src)
        self.assertIn("cmdNormal = s => toHalfWidth(s.trim())", src)


if __name__ == "__main__":
    unittest.main()
