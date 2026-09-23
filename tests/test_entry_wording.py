"""The wording of the two browser recognition entries.

Chrome decides for itself where it recognizes. A page can only forbid the
cloud (`processLocally`), which is what the second entry does, so the screen
must not promise a choice the browser no longer honours. These are the keys
that carry that story, in every language, and the prose in them follows the
house style of no colons and no dashes.
"""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
I18N_JS = ROOT / "skills/voice-shell/scripts/i18n.js"

# The entries themselves, their notes, the caution, and the two sentences that
# used to say the audio always goes to Google.
ENTRY_KEYS = [
    "engineBrowser", "engineBrowserLocal",
    "browserAsrNote", "browserAsrNoteHere", "browserAsrNoteCloud",
    "browserAsrWarn", "browserAsrWarnHere", "browserAsrWarnCloud",
    "localAsrNote", "onDeviceReady", "onDeviceUnavailable", "onDeviceRefused",
    "onDeviceHold", "idleMuteNote", "idleMuteNoteLocal", "cmdUnmuteOnDevice",
]

LANGS = ["en", "ja", "es", "fr", "de", "zh", "zh-TW", "ko"]

# Colons and dashes the prose does not use. A bare "-" is left alone, since
# "on-device" needs it, and so is the Japanese long vowel mark.
BANNED = ["：", ":", "—", "–", "―", "─", " - "]


def load():
    script = ("const fs = require('fs');"
              "const I18N = new Function(fs.readFileSync(process.argv[1], 'utf8')"
              " + ';return I18N;')();"
              "console.log(JSON.stringify(I18N));")
    out = subprocess.run(["node", "-e", script, str(I18N_JS)],
                         capture_output=True, text=True, encoding="utf-8",
                         check=True)
    return json.loads(out.stdout)


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class EntryWordingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.i18n = load()

    def test_every_language_is_there(self):
        self.assertEqual(sorted(self.i18n), sorted(LANGS))

    # The one string a state is allowed to leave empty, which hides the
    # caution there and folds the point into the note. Empty, not absent:
    # t() falls back to the key name for a key that is not there.
    MAY_BE_EMPTY = {"browserAsrWarnHere"}

    def test_every_language_carries_the_keys(self):
        for lang in LANGS:
            for key in ENTRY_KEYS:
                self.assertIn(key, self.i18n[lang], f"{lang} is missing {key}")
                if key in self.MAY_BE_EMPTY:
                    continue
                self.assertTrue(self.i18n[lang][key].strip(), f"{lang}.{key} is empty")

    def test_a_string_left_empty_is_empty_everywhere(self):
        """Half the languages hiding the caution and half showing it would be
        two different screens, so an empty one has to be empty in all 8."""
        for key in self.MAY_BE_EMPTY:
            empty = {lang for lang in LANGS if not self.i18n[lang][key].strip()}
            self.assertIn(len(empty), (0, len(LANGS)), f"{key} is empty in {empty}")

    def test_fill_ins_match_english(self):
        def fills(s):
            return sorted(set(p for p in ("{plain}", "{local}", "{size}", "{back}")
                              if p in s))
        for lang in LANGS:
            for key in ENTRY_KEYS:
                self.assertEqual(fills(self.i18n[lang][key]),
                                 fills(self.i18n["en"][key]), f"{lang}.{key}")

    def test_no_colons_and_no_dashes(self):
        for lang in LANGS:
            for key in ENTRY_KEYS:
                text = self.i18n[lang][key]
                for bad in BANNED:
                    self.assertNotIn(bad, text, f"{lang}.{key} carries {bad!r}")

    def test_the_plain_entry_reports_the_state_it_is_in(self):
        """Each of the three answers the disk can give has its own wording,
        and none of them talks about Chrome deciding anything."""
        en = self.i18n["en"]
        self.assertIn("recognized locally", en["browserAsrNoteHere"])
        self.assertNotIn("Google", en["browserAsrNoteHere"])
        self.assertIn("Google", en["browserAsrNoteCloud"])
        # The hedge is only for when nothing could be told
        self.assertIn("if it is not", en["browserAsrNote"])
        ja = self.i18n["ja"]
        self.assertIn("ローカル", ja["browserAsrNoteHere"])
        self.assertIn("Google", ja["browserAsrNoteCloud"])
        for key in ("browserAsrNote", "browserAsrNoteHere", "browserAsrNoteCloud",
                    "browserAsrWarn", "browserAsrWarnHere", "browserAsrWarnCloud"):
            for lang in LANGS:
                self.assertNotIn("Chrome", self.i18n[lang][key], f"{lang}.{key}")

    def test_nothing_to_install_is_gone(self):
        """It meant nothing to a reader. What it works without is setup."""
        for lang in LANGS:
            for key in ("browserAsrNote", "browserAsrNoteHere", "browserAsrNoteCloud"):
                self.assertNotIn("Nothing to install", self.i18n[lang][key])
        self.assertNotIn("入れるものはありません",
                         self.i18n["ja"]["browserAsrNote"])

    def test_the_caution_is_not_shown_wrong_when_the_model_is_here(self):
        """With the model on the machine, the flat warning about Google is
        false, so that state either says something of its own or says
        nothing. What it must not do is repeat the other one."""
        for lang in LANGS:
            here = self.i18n[lang]["browserAsrWarnHere"].strip()
            if not here:
                continue
            self.assertNotEqual(here, self.i18n[lang]["browserAsrWarnCloud"].strip(), lang)
            self.assertNotEqual(here, self.i18n[lang]["browserAsrWarn"].strip(), lang)

    def test_the_on_device_entry_is_the_one_that_guarantees_it(self):
        """It says what the language can do and what happens to the audio,
        in that order, and nothing about what is or is not permitted."""
        self.assertEqual(
            self.i18n["en"]["onDeviceReady"],
            "This language can be recognized locally. "
            "Your audio is not sent anywhere outside.")
        self.assertEqual(
            self.i18n["ja"]["onDeviceReady"],
            "この言語はローカルで"
            "認識できます。"
            "音声は外部に送信されません。")

    def test_the_here_caution_is_one_plain_sentence(self):
        """Condition then result, and nothing else. It points at no other
        choice, since there is nothing to act on while the model is here,
        and it says nothing about the model being deleted, since Chrome
        re-arms that timer every time it starts and any figure we gave
        would be wrong."""
        for lang in LANGS:
            here = self.i18n[lang]["browserAsrWarnHere"]
            self.assertTrue(here.strip(), lang)
            for bad in ("30", "削除", "delete", "unused"):
                self.assertNotIn(bad, here, f"{lang} carries {bad!r}")
        self.assertEqual(
            self.i18n["en"]["browserAsrWarnHere"],
            "While the speech model is downloaded, "
            "your audio is recognized locally.")
        self.assertEqual(
            self.i18n["ja"]["browserAsrWarnHere"],
            "音声認識モデルが"
            "ダウンロードされている"
            "場合は、ローカルで"
            "認識します。")

    def test_one_vocabulary_across_the_group(self):
        """The whole group says local in one word, so a reader meets the
        same idea under the same name wherever the state lands them."""
        keys = ("browserAsrNoteHere", "browserAsrWarnHere", "browserAsrWarnCloud",
                "browserAsrNote", "browserAsrWarn", "engineBrowserLocal",
                "localAsrNote", "onDeviceReady")
        for key in keys:
            en = self.i18n["en"][key]
            if en:
                self.assertIn("local", en.lower(), f"en.{key}")
            ja = self.i18n["ja"][key]
            if ja:
                self.assertIn("ローカル", ja, f"ja.{key}")
        # The Japanese lines take the audio as their subject
        for key in ("browserAsrNoteHere", "browserAsrNoteCloud", "browserAsrNote",
                    "browserAsrWarnCloud", "browserAsrWarn", "onDeviceReady"):
            self.assertIn("音声", self.i18n["ja"][key], f"ja.{key}")
VIEWER_JS = ROOT / "skills/voice-shell/scripts/viewer.js"

# plainAsrWhere sits in the part of viewer.js with no page in it, the same
# piece test_on_device.py cuts out and runs under node.
HARNESS = r"""
const fs = require('fs');
const source = fs.readFileSync(process.argv[1], 'utf8');
const start = source.indexOf("const BROWSER_LOCAL = 'browser-local';");
const end = source.indexOf("// Whether the local entry can be offered here at all.", start);
if (start < 0 || end < 0) process.exit(2);
const make = new Function('env', `
  const BROWSER_ENGINE = 'browser';
  ${source.slice(start, end)}
  return {plainAsrWhere};
`);
const h = make({});
const assert = (cond, what) => { if (!cond) { console.error(what); process.exit(1); } };
"""


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class PlainStateTest(unittest.TestCase):
    """The plain entry reads its state off the same look at the disk the
    local entry already does, rather than describing what Chrome might do."""

    def run_js(self, script):
        subprocess.run(["node", "-e", HARNESS + script, str(VIEWER_JS)], check=True)

    def test_the_three_answers(self):
        self.run_js(r"""
assert(h.plainAsrWhere({lang:'ja-JP', engine:true, pack:true}) === 'here', 'model here');
assert(h.plainAsrWhere({lang:'ja-JP', engine:true, pack:false}) === 'cloud', 'no pack');
assert(h.plainAsrWhere({lang:'ja-JP', engine:false, pack:false}) === 'cloud', 'nothing there');
// Nothing could be told, so nothing is claimed
assert(h.plainAsrWhere(null) === '', 'not asked yet');
assert(h.plainAsrWhere({lang:'ja-JP', engine:null, pack:null}) === '', 'unreadable');
assert(h.plainAsrWhere({lang:'ja-JP', engine:true, pack:null}) === '', 'half unreadable');
""")


class PlainNoteWiringTest(unittest.TestCase):
    """One look at the disk per language, not one per repaint."""

    def test_the_disk_is_asked_from_the_plain_entry_and_is_cached(self):
        src = VIEWER_JS.read_text(encoding="utf-8")
        self.assertIn("if (plain) checkOnDeviceDisk(browserLang());", src)
        # checkOnDeviceDisk returns at once for a language already known or
        # already under way, which is what keeps repainting free.
        self.assertIn(
            "if (onDeviceDiskAsk === lang || (onDeviceDisk && onDeviceDisk.lang === lang)) return;",
            src)

    def test_the_answer_repaints_the_plain_entry(self):
        """paintOnDevice returns at once on the plain entry, so the answer
        landing has to repaint the note and the caution itself. Without this
        they would keep the hedge they were painted with before it came."""
        src = VIEWER_JS.read_text(encoding="utf-8")
        start = src.index("function checkOnDeviceDisk")
        end = src.index("function keepPollingOnDevice", start)
        self.assertIn("paintBrowserAsr(", src[start:end])

    def test_a_state_with_nothing_to_warn_about_hides_the_caution(self):
        """A wording left empty means that state folds its point into the
        note, and the red rule keeps out of the way instead of framing
        nothing. t() falls back to the key name for a missing key, so such a
        state carries an empty string rather than no key at all."""
        src = VIEWER_JS.read_text(encoding="utf-8")
        self.assertIn("el.browserAsrWarn.hidden = !asrChosen || onDeviceLocal || !warn;", src)
