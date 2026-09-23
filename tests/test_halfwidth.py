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


# foldChars sits below the tail tables, so it needs the wider slice the switch-off
# test cuts. loadTailWords goes out with it, since it would reach for fetch.
HARNESS_FOLD = r"""
const fs = require('fs');
const source = fs.readFileSync(process.argv[1], 'utf8');
const start = source.indexOf('// Full-width Latin letters and digits');
const end = source.indexOf('function endsWithTailCmd', start);
if (start < 0 || end < 0) process.exit(2);
const body = source.slice(start, end).replace(/async function loadTailWords[\s\S]*?\n}\n/, '');
const h = new Function(`${body}
  return {toHalfWidth, foldChars, cmdKey, cmdNormal: null};`)();
const assert = (cond, what) => { if (!cond) { console.error(what); process.exit(1); } };
"""


def run_fold(script):
    subprocess.run(["node", "-e", HARNESS_FOLD + script, str(VIEWER_JS)], check=True)


# The fold and the invented-space strip together, the pair onresult runs, with
# the spoken language it reads off browserLang stubbed so a test can move it.
HARNESS_SPACES = r"""
const fs = require('fs');
const source = fs.readFileSync(process.argv[1], 'utf8');
const cut = (from, to) => {
  const start = source.indexOf(from), end = source.indexOf(to, start);
  if (start < 0 || end < 0) process.exit(2);
  return source.slice(start, end);
};
const h = new Function(`let spoken = 'ja-JP';
  const browserLang = () => spoken;
  ${cut('// Full-width Latin letters and digits', 'const TAIL_IDS = ')}
  ${cut('const NO_SPACE_LANGS', '/* The one string both writers')}
  return {toHalfWidth, stripInventedSpaces, speak: l => { spoken = l; }};`)();
// What onresult itself does with one result's transcript
const heard = t => h.toHalfWidth(h.stripInventedSpaces(t));
const codes = s => [...s].map(c => c.codePointAt(0).toString(16)).join(' ');
const assert = (cond, what) => { if (!cond) { console.error(what); process.exit(1); } };
"""


def run_spaces(script):
    subprocess.run(["node", "-e", HARNESS_SPACES + script, str(VIEWER_JS)], check=True)


class ToHalfWidthTest(unittest.TestCase):
    def test_latin_letters_and_digits_fold(self):
        self.assertEqual(to_halfwidth("ＰＲを２０２６年に出す"), "PRを2026年に出す")
        self.assertEqual(to_halfwidth("ｇｉｔ　ｐｕｓｈ"), "git　push")

    def test_the_symbols_that_only_ever_mean_code_fold(self):
        self.assertEqual(to_halfwidth("＠＃＆％＋＝／＼＿＜＞＄＊＾｜｀［］｛｝"),
                         r"@#&%+=/\_<>$*^|`[]{}")

    def test_the_hyphen_in_a_name_folds(self):
        """A hyphen inside a word is half-width wherever it is written down.

        Said as one word, Wi-Fi came back 「Ｗｉ－Ｆｉ」 and only the letters folded,
        so what was sent carried a full-width hyphen in the middle of a name
        nobody writes that way.
        """
        self.assertEqual(to_halfwidth("Ｗｉ－Ｆｉ"), "Wi-Fi")
        self.assertEqual(to_halfwidth("ｖｏｉｃｅ－ｓｈｅｌｌ"), "voice-shell")
        self.assertEqual(to_halfwidth("－－ｈｅｌｐ"), "--help")
        # The long vowel mark is a different character and a word of Japanese
        self.assertEqual(to_halfwidth("コーヒーとｗｉ－ｆｉ"), "コーヒーとwi-fi")

    def test_japanese_punctuation_is_left_alone(self):
        # ＂ and ＇ are left wide on purpose, the same reasoning as 〜. They turn
        # up in quoted prose at least as often as in code, and folding them
        # would rewrite a sentence someone quoted rather than a line of code.
        for s in ["、", "。", "「", "」", "・", "？", "！", "：", "；", "，", "．",
                  "（", "）", "〜", "～", "ー", "　", "＂", "＇", "あア亜"]:
            self.assertEqual(to_halfwidth(s), s, s)
        self.assertEqual(to_halfwidth("これは「ＰＲ」です。ー〜"), "これは「PR」です。ー〜")

    def test_half_width_katakana_is_written_full_width(self):
        self.assertEqual(to_halfwidth("ｱｲｳ"), "アイウ")
        # A dakuten is its own character half-width, so the run composes as a whole
        self.assertEqual(to_halfwidth("ｶﾞｷﾞ ﾊﾟ"), "ガギ パ")
        self.assertEqual(to_halfwidth("ｺｰﾋｰ"), "コーヒー")

    def test_folding_twice_changes_nothing(self):
        # The browser road folds on the page and again in /api/asr. Both ends
        # only agree because the second fold is a no-op.
        for s in ["ＰＲを２０２６年に", "ｶﾞｷﾞ ﾊﾟ", "これは「PR」です。ー〜", "　"]:
            self.assertEqual(to_halfwidth(to_halfwidth(s)), to_halfwidth(s), s)

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

    def test_a_dakuten_written_half_width_folds_as_one_letter(self):
        """_folded_chars has to land on the same string command_key does.

        The dakuten is a character of its own half-width, so folded one character
        at a time 「ｺﾞｰ」 came out as コ+゛ where command_key says ゴー, and the tail
        stopped matching. Where each folded character came from still points at the
        base, so the cut takes the whole pair off.
        """
        from voice_daemon import _folded_chars
        for s in ["ｺﾞｰ", "ｶﾞｷﾞ", "ﾊﾟｿｺﾝ", "ﾐｭｰﾄ", "ｺﾚ｡"]:
            self.assertEqual("".join(f for f, _ in _folded_chars(s)),
                             command_key(s), s)
        from voice_daemon import take_tail_word
        self.assertEqual(take_tail_word("これをｺﾞｰ", ["ゴー"]), ("これを", "ゴー"))

    def test_an_acronym_read_out_letter_by_letter_folds_then_collapses(self):
        self.assertEqual(collapse_letter_acronyms(to_halfwidth("Ｇ Ｐ Ｕ")), "GPU")


class MachineNameTest(unittest.TestCase):
    """The name at the head is matched folded, like every other written-down word."""

    def test_a_name_typed_full_width_still_matches(self):
        from voice_daemon import _strip_name
        self.assertEqual(_strip_name("Macミュート", ["Ｍａｃ"]), "ミュート")
        self.assertEqual(_strip_name("Macミュート", ["Mac"]), "ミュート")
        self.assertEqual(_strip_name("開発用、ミュート", ["開発用"]), "ミュート")
        self.assertIsNone(_strip_name("Winミュート", ["Mac"]))


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

    def test_voice_daemon_is_imported_above_its_first_use(self):
        """viewer.py imports voice_daemon inside each handler, and a name imported
        anywhere in a function is local to the whole of it. Use it above the import
        and the line reads an unbound local, so the handler raises on every call
        instead of doing its work. The fold is the first thing /api/asr does, which
        is exactly where that bit.
        """
        import ast
        tree = ast.parse(VIEWER_PY.read_text(encoding="utf-8"))

        def own_nodes(fn):
            """Every node of that function's own scope, nested defs left out."""
            stack, out = list(fn.body), []
            while stack:
                node = stack.pop()
                out.append(node)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                     ast.Lambda)):
                    continue
                stack.extend(ast.iter_child_nodes(node))
            return out

        bad = []
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            nodes = own_nodes(fn)
            lines = [n.lineno for n in nodes if isinstance(n, ast.Import)
                     and any(a.asname == "vd" for a in n.names)]
            if not lines:
                continue
            first = min(lines)
            bad += [f"{fn.name}: vd used at line {n.lineno}, imported at {first}"
                    for n in nodes
                    if isinstance(n, ast.Name) and n.id == "vd"
                    and isinstance(n.ctx, ast.Load) and n.lineno < first]
        self.assertEqual(bad, [])


class ViewerJsTest(unittest.TestCase):
    def test_to_half_width_matches_the_python_one(self):
        run(r"""
assert(h.toHalfWidth('ＰＲを２０２６年に出す') === 'PRを2026年に出す', 'letters and digits');
assert(h.toHalfWidth('＠＃＆％＋＝／＼＿＜＞') === '@#&%+=/\\_<>', 'code symbols');
assert(h.toHalfWidth('これは「ＰＲ」です。ー〜') === 'これは「PR」です。ー〜', 'prose left alone');
assert(h.toHalfWidth('　') === '　', 'the full-width space stays');
assert(h.toHalfWidth('ｶﾞｷﾞ ﾊﾟ') === 'ガギ パ', 'half-width kana composes');
assert(h.toHalfWidth('git push') === 'git push', 'plain text untouched');
assert(h.toHalfWidth('Ｗｉ－Ｆｉ') === 'Wi-Fi', 'the hyphen in a name folds');
assert(h.toHalfWidth('コーヒーとｗｉ－ｆｉ') === 'コーヒーとwi-fi', 'the long vowel mark stays');
assert(h.toHalfWidth('＂＇') === '＂＇', 'the full-width quotes stay');
""")

    def test_the_fold_runs_where_text_arrives_and_nowhere_after(self):
        """Folded once, on the way in, above the dictionary. Never again after.

        The server's own order settles it: to_halfwidth runs at the top of the
        loop, then polish calls apply_replacements, which leaves a replacement
        at the width it was typed in on purpose. Fold a second time further down
        and that deliberate width is undone, on a card that is supposed to be
        the record of what went out, or worse, in the draft box, whose contents
        are posted to /api/send word for word.

        So the fold sits where text comes in (the browser's own result and the
        daemon's partial, both before withDict) and on none of the roads that
        only carry text that has already been through it.
        """
        src = VIEWER_JS.read_text(encoding="utf-8")
        # Where it comes in. Both are read by worthSending and the send cue, so
        # they have to be the string the server judges.
        self.assertIn("livePartial = toHalfWidth(m.partial).trim();", src)
        self.assertIn("toHalfWidth(stripInventedSpaces(res[0].transcript))", src)

        def body_of(head):
            return src.split(head, 1)[1].split("\n}\n", 1)[0]

        # And nowhere after. paintStream is handed the text withDict has already
        # rewritten; the other three feed the draft box or the log card.
        for head in ("function paintStream(s) {", "function appendHeld(text) {",
                     "function mergeHeld(held) {", "function restoreDraft(r) {"):
            self.assertNotIn("toHalfWidth", body_of(head), head)
        entry = body_of("function addEntry(rec) {")
        self.assertNotIn("toHalfWidth", entry)
        # What the card shows and what a resend posts are the line as written.
        self.assertIn("const body = rec.text || '';", entry)
        self.assertIn("text.dataset.raw = body;", entry)

    def test_a_full_width_replacement_survives_the_screen(self):
        """A dictionary told to write 「ＡＷＳ」 means it, all the way to the card.

        apply_replacements folds the side it matches on and leaves the side it
        produces exactly as typed. The screen has to keep that promise, or the
        card would read AWS under words that reached Claude wide.
        """
        # What the daemon sends out, in its own order: fold, then the dictionary.
        spoken = to_halfwidth("エーダブリューエス を使う")
        sent = apply_replacements(spoken, {"エーダブリューエス": "ＡＷＳ"})
        self.assertEqual(sent, "ＡＷＳ を使う")
        # A second fold anywhere downstream is exactly what would break it, which
        # is why the card, the held lines and the draft box do not run one.
        self.assertEqual(to_halfwidth(sent), "AWS を使う")
        # The page matches the same way: keys folded, what they become as typed.
        run_fold(r"""
const pairs = [['エーダブリューエス', 'ＡＷＳ']].map(([k, v]) => [h.toHalfWidth(k), v]);
const withDict = t => { for (const [f, o] of pairs) t = t.split(f).join(o); return t; };
assert(withDict('エーダブリューエス を使う') === 'ＡＷＳ を使う',
       'the replacement keeps its width');
""")

    def test_fold_chars_lands_on_the_same_string_cmd_key_does(self):
        run_fold(r"""
const j = s => h.foldChars(s).chars.join('');
assert(j('ＲＯＵＴｅ２') === 'route2', 'letters and digits');
assert(j('ｺﾞｰ') === 'ゴー', 'a half-width dakuten composes: ' + j('ｺﾞｰ'));
assert(j('ﾊﾟｿｺﾝ') === 'パソコン', 'handakuten');
assert(j('ｺﾚ｡') === 'コレ', 'a half-width 。 drops the way it does folded');
// where each folded character came from still points at the base it was read on
const f = h.foldChars('これをｺﾞｰ');
assert(f.at[f.chars.indexOf('ゴ')] === 3, 'the cut lands on the base: ' + f.at.join(','));
""")

    def test_a_word_spelled_a_letter_at_a_time_comes_back_as_one_word(self):
        """Chrome writes Latin inside Japanese one letter at a time.

        「ＩＰｈｏｎｅ」 arrives as 「Ｉ Ｐ ｈ ｏ ｎ ｅ」, every letter with a space after
        it, full-width on this device and half-width from Google's servers.
        Read only between two non-ASCII characters, none of those spaces is
        touched once the letters have been folded, so the live line said
        "I P h o n e" (49 20 50 20 68…), which is what full-width looks like at
        a glance, and the card that came back a few seconds later from a server
        that never spaces read iPhone. Both widths of the line the page was
        caught showing are below, codepoint for codepoint.
        """
        src = VIEWER_JS.read_text(encoding="utf-8")
        self.assertIn("toHalfWidth(stripInventedSpaces(res[0].transcript))", src)
        run_spaces(r"""
for (const spelled of ['はい、こちらを。Ｉ Ｐ ａ ｄ ｉ Ｐ ｈ ｏ ｎ ｅ Ｍ ａ ｃ ｍ ｉ ｎ',
                       'はい、こちらを。I P a d i P h o n e M a c m i n']) {
  const got = heard(spelled);
  assert(got === 'はい、こちらを。IPadiPhoneMacmin', 'one word again, got ' + got);
  assert(codes(got).endsWith('49 50 61 64 69 50 68 6f 6e 65 4d 61 63 6d 69 6e'),
         'letter after letter, no gaps: ' + codes(got));
}
// What the live page showed instead, and why: the rule that only read a space
// between two non-ASCII characters, handed text the fold had already made ASCII.
const wasRe = /(?<=[^\x00-\x7F\s])[ \t]+(?=[^\x00-\x7F\s])/g;
const was = h.toHalfWidth('Ｉ Ｐ ａ ｄ').replace(wasRe, '');
assert(codes(was) === '49 20 50 20 61 20 64', 'every space survived: ' + codes(was));
""")

    def test_the_space_between_two_folded_words_survives(self):
        # A run of two or more letters is a word the recognizer wrote as a word,
        # not a letter it spelled out, and the space between two of those is
        # real. Stripped anyway, 「ＰＲ ｔｅｓｔ」 went out as PRtest.
        run_spaces(r"""
assert(heard('ＰＲ ｔｅｓｔ') === 'PR test', 'two words stay two words');
assert(heard('PR test') === 'PR test', 'and so do they half-width');
assert(heard('Ｍａｃ ｍｉｎｉ') === 'Mac mini', 'and so does this one');
assert(heard('Claude Code を使う') === 'Claude Code を使う', 'the everyday case');
assert(heard('これは テスト') === 'これはテスト', 'japanese still loses it');
// Pre-#127 behaviour, deliberately back: the recognizer invented that gap too,
// and folding first had been keeping it only because P turned into ASCII.
assert(heard('テスト ＰＲ') === 'テストPR', 'nothing was said in that gap either');
h.speak('en-US');
assert(heard('PR test') === 'PR test', 'a language that writes spaces keeps all of them');
assert(heard('I P a d') === 'I P a d', 'and spells things out if it wants to');
""")

    def test_the_interim_on_screen_is_already_folded(self):
        src = VIEWER_JS.read_text(encoding="utf-8")
        self.assertIn("toHalfWidth(stripInventedSpaces(res[0].transcript))", src)
        # The preview's own copy of the dictionary matches on the folded side too
        self.assertIn("toHalfWidth(k), v", src)
        # and so do the two screen-side copies of the server's command_key
        self.assertIn("for (const x of toHalfWidth(unit))", src)
        self.assertIn("cmdNormal = s => toHalfWidth(s.trim())", src)


if __name__ == "__main__":
    unittest.main()
