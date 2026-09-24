"""The minimum length is a count of characters, in every language.

viewer.py drops an utterance on `len(text) < min_chars`, 15 by default, and
nothing there looks at which language was spoken. The English, Spanish, French
and German READMEs said "about three words or fewer", which reads as a rule
that knows what you are speaking, and the note in the settings said only that
shorter results are dropped, never shorter than what. These check that the
number is named and that no page counts words instead.
"""
import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
I18N_JS = ROOT / "skills/voice-shell/scripts/i18n.js"
VIEWER_PY = ROOT / "skills/voice-shell/scripts/viewer.py"

LANGS = ["en", "ja", "es", "fr", "de", "zh", "zh-TW", "ko"]

# Every page the number appears on, and the word for a character in it.
READMES = {
    "README.md": "characters",
    "docs/readme/README.ja.md": "文字",
    "docs/readme/README.es.md": "caracteres",
    "docs/readme/README.fr.md": "caractères",
    "docs/readme/README.de.md": "Zeichen",
    "docs/readme/README.zh.md": "字",
    "docs/readme/README.zh-TW.md": "字",
    "docs/readme/README.ko.md": "자",
}

# Ways of counting that the setting does not do.
WORD_COUNTS = [
    re.compile(r"three words"),
    re.compile(r"tres palabras"),
    re.compile(r"trois mots"),
    re.compile(r"drei Wörter"),
]


def load():
    script = ("const fs = require('fs');"
              "const I18N = new Function(fs.readFileSync(process.argv[1], 'utf8')"
              " + ';return I18N;')();"
              "console.log(JSON.stringify(I18N));")
    out = subprocess.run(["node", "-e", script, str(I18N_JS)],
                         capture_output=True, text=True, encoding="utf-8",
                         check=True)
    return json.loads(out.stdout)


class MinLengthWordingTest(unittest.TestCase):
    def test_the_floor_is_a_character_count_in_the_code(self):
        # What the pages describe. If this ever counts words, the pages are
        # the ones that have to move, not this test.
        source = VIEWER_PY.read_text(encoding="utf-8")
        self.assertIn("len(text) < int(min_chars)", source)
        self.assertIn('tuning.get("min_chars", 15)', source)

    def test_every_readme_names_the_number_and_counts_characters(self):
        for rel, word in READMES.items():
            page = (ROOT / rel).read_text(encoding="utf-8")
            line = [l for l in page.splitlines() if "15" in l and word in l]
            self.assertTrue(line, f"{rel} never says 15 {word}")

    def test_no_readme_counts_words_instead(self):
        for rel in READMES:
            page = (ROOT / rel).read_text(encoding="utf-8")
            for pattern in WORD_COUNTS:
                self.assertIsNone(pattern.search(page),
                                  f"{rel} counts words, which the setting does not")

    def test_the_note_says_what_happens_to_what_is_shorter(self):
        i18n = load()
        for lang in LANGS:
            note = i18n[lang]["minCharsNote"]
            self.assertTrue(note.strip(), lang)
            for banned in ("：", ":", "—", "–"):
                self.assertNotIn(banned, note, (lang, note))


if __name__ == "__main__":
    unittest.main()
