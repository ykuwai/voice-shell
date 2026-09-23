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

    def test_every_language_carries_the_keys(self):
        for lang in LANGS:
            for key in ENTRY_KEYS:
                self.assertIn(key, self.i18n[lang], f"{lang} is missing {key}")
                self.assertTrue(self.i18n[lang][key].strip(), f"{lang}.{key} is empty")

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
        self.assertIn("is on this machine", en["browserAsrNoteHere"])
        self.assertIn("recognized right here", en["browserAsrNoteHere"])
        self.assertNotIn("Google", en["browserAsrNoteHere"])
        self.assertIn("Google", en["browserAsrNoteCloud"])
        self.assertIn("no model for this language", en["browserAsrNoteCloud"])
        # The hedge is only for when nothing could be told
        self.assertIn("when it is not", en["browserAsrNote"])
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
        """With the model on the machine, a flat warning about Google is
        false, so that state gets its own wording."""
        here = self.i18n["en"]["browserAsrWarnHere"]
        self.assertIn("does not forbid it", here)
        self.assertIn("only on this device", here)

    def test_the_on_device_entry_is_the_one_that_guarantees_it(self):
        ready = self.i18n["en"]["onDeviceReady"]
        self.assertIn("never leaves this machine", ready)
        self.assertIn("cloud is not allowed", ready)
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
