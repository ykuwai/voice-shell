"""Clearing the history says so once it is done.

The button asks for a second press and then goes back to its own wording, so
until now nothing on screen told a clearing that went through from one that
never did. The note under the button says it, and it is said where the server's
answer lands, so every open screen that just lost its list says it rather than
only the one that was pressed.
"""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/voice-shell/scripts"
VIEWER_JS = SCRIPTS / "viewer.js"
VIEWER_HTML = SCRIPTS / "viewer.html"
I18N_JS = SCRIPTS / "i18n.js"

LANGS = ["en", "ja", "es", "fr", "de", "zh", "zh-TW", "ko"]


class NoteTest(unittest.TestCase):
    def test_the_note_is_on_the_page_and_read_out(self):
        html = VIEWER_HTML.read_text(encoding="utf-8")
        line = next(l for l in html.splitlines() if 'id="clearHistoryDone"' in l)
        # A line that appears on its own has to announce itself to a reader who
        # is not looking at that corner of the sheet.
        self.assertIn('role="status"', line)
        js = VIEWER_JS.read_text(encoding="utf-8")
        self.assertIn("'clearHistoryDone'", js)

    def test_it_is_said_where_the_clearing_actually_happens(self):
        js = VIEWER_JS.read_text(encoding="utf-8")
        handler = js.split("if (m.history_cleared) {", 1)[1].split("return;", 1)[0]
        self.assertIn("flashHistoryCleared();", handler)
        flash = js.split("function flashHistoryCleared() {", 1)[1].split("\n}\n", 1)[0]
        self.assertIn("t('historyCleared')", flash)
        # Said for a moment, not left sitting there afterwards
        self.assertIn("el.clearHistoryDone.textContent = ''", flash)


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class WordingTest(unittest.TestCase):
    def words(self):
        script = ("const fs = require('fs');"
                  "const I18N = new Function(fs.readFileSync(process.argv[1], 'utf8')"
                  " + ';return I18N;')();"
                  "console.log(JSON.stringify(Object.fromEntries("
                  + json.dumps(LANGS) + ".map(l => [l, I18N[l].historyCleared]))));")
        out = subprocess.run(["node", "-e", script, str(I18N_JS)],
                             capture_output=True, text=True, encoding="utf-8", check=True)
        return json.loads(out.stdout)

    def test_every_screen_says_it_in_its_own_words(self):
        got = self.words()
        for lang in LANGS:
            self.assertTrue(got[lang] and got[lang].strip(), lang)
            for ch in [":", "：", " - ", "—", "–"]:
                self.assertNotIn(ch, got[lang], f"{lang}: {got[lang]}")
        self.assertEqual(got["ja"], "画面の履歴を消しました。")


if __name__ == "__main__":
    unittest.main()
