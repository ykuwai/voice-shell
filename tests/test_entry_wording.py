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
    "engineBrowser", "engineBrowserLocal", "browserAsrNote", "browserAsrWarn",
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

    def test_the_plain_entry_does_not_promise_a_choice(self):
        """It says Chrome decides, not that the audio always goes to Google."""
        note = self.i18n["en"]["browserAsrNote"]
        self.assertIn("Chrome chooses", note)
        self.assertIn("Google", note)
        self.assertIn("may recognize here", note)

    def test_the_on_device_entry_is_the_one_that_guarantees_it(self):
        ready = self.i18n["en"]["onDeviceReady"]
        self.assertIn("never leaves this machine", ready)
        self.assertIn("cloud is not allowed", ready)
