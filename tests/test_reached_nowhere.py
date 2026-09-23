"""An utterance that reached nowhere says so.

With nothing listening, the line is written with no destination on it and every
listener drops it (resolve_target, #73). Until now the screen said nothing
about that: the card looked like every other sent card, and the notice that
fires when the chosen session ends went as far as claiming the words were now
going to everyone, which is the one thing that cannot be true when there is
nobody left to go to.

The card is cut out of viewer.js and built against a stand-in page, the way
test_route_gone_ui.py does it. The wording is read out of i18n.js under node.
"""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/voice-shell/scripts"
VIEWER_JS = SCRIPTS / "viewer.js"
VIEWER_PY = SCRIPTS / "viewer.py"
I18N_JS = SCRIPTS / "i18n.js"

# The eight screens. English is the base every other one falls back to.
LANGS = ["en", "ja", "es", "fr", "de", "zh", "zh-TW", "ko"]

HARNESS = r'''
const fs = require('fs');
// Read with one kind of line ending whatever the checkout wrote, so the cut
// below lands the same on Windows as it does anywhere else.
const source = fs.readFileSync(process.argv[1], 'utf8').replace(/\r\n/g, '\n');
const assert = (cond, what) => { if (!cond) { console.error(what); process.exit(1); } };

/* A page that is only as much of a page as addEntry touches. */
function makeEl(tag) {
  return {
    tag, className: '', title: '', textContent: '', hidden: false,
    dataset: {}, style: {}, children: [], scrollTop: 0,
    append(...kids) { this.children.push(...kids); },
    prepend(...kids) { this.children.unshift(...kids); },
    querySelector(sel) {
      const want = sel.replace('.', '');
      const hit = c => (c.className || '').split(' ').includes(want);
      for (const c of this.children) {
        if (hit(c)) return c;
        const deep = c.querySelector ? c.querySelector(sel) : null;
        if (deep) return deep;
      }
      return null;
    },
  };
}

const addEntryBody = (() => {
  const a = source.indexOf('function addEntry(rec) {');
  const b = source.indexOf('\n}\n', a);
  if (a < 0 || b < 0) process.exit(2);
  return source.slice(a, b + 3);
})();

const make = env => new Function('env', `
  const {t, el} = env;
  const document = {createElement: env.makeEl};
  const format = raw => raw;
  const toHalfWidth = s => s;
  const buildToControl = () => env.makeEl('span');
  const atLogTop = () => true;
  const logWrap = {scrollTop: 1};
  const retally = () => {};
  const timeLocale = () => 'en';
  ${addEntryBody}
  return addEntry;
`)(env);
'''


def run(script):
    subprocess.run(["node", "-e", HARNESS + script, str(VIEWER_JS)], check=True)


def words(body):
    """Read the wording tables under node and hand back what the script asked for."""
    script = ("const fs = require('fs');"
              "const I18N = new Function(fs.readFileSync(process.argv[1], 'utf8')"
              " + ';return I18N;')();" + body)
    out = subprocess.run(["node", "-e", script, str(I18N_JS)],
                         capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(out.stdout)


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class CardTest(unittest.TestCase):
    def test_a_card_with_no_destination_says_it_reached_nowhere(self):
        run(r'''
const el = {log: makeEl('div'), logJumpWrap: makeEl('div')};
const addEntry = make({t: k => k, el, makeEl});
addEntry({text: 'ok', time: '10:00:00'});
const row = el.log.children[0];
assert(row.querySelector('.nowhere'), 'a line with no destination says so');
assert(row.querySelector('.nowhere').textContent === 'sentNowhere',
       'in words: ' + row.querySelector('.nowhere').textContent);
''')

    def test_a_card_that_went_somewhere_says_nothing_extra(self):
        run(r'''
const el = {log: makeEl('div'), logJumpWrap: makeEl('div')};
const addEntry = make({t: k => k, el, makeEl});
addEntry({text: 'ok', time: '10:00:00', to: 4321});
assert(!el.log.children[0].querySelector('.nowhere'), 'nothing said when it arrived');
''')


class StatusLineTest(unittest.TestCase):
    """Said at the moment it happens too, but not once per card on a reload."""

    def test_the_arrival_of_a_line_with_no_destination_is_said_out_loud(self):
        src = VIEWER_JS.read_text(encoding="utf-8")
        self.assertIn("if (!m.to && !m.replay) say(t('sentNowhereHint'), 8);", src)

    def test_the_replayed_history_is_marked_as_history(self):
        # Without the mark, every old card of a session spent working alone
        # would announce itself again on every reload.
        src = VIEWER_PY.read_text(encoding="utf-8")
        self.assertIn('json.dumps({**rec, "replay": True}, ensure_ascii=False)', src)


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class WordingTest(unittest.TestCase):
    def test_every_screen_has_both_lines(self):
        got = words("console.log(JSON.stringify(Object.fromEntries("
                    + json.dumps(LANGS) + ".map(l => [l, ["
                    "I18N[l].sentNowhere, I18N[l].sentNowhereHint, I18N[l].routeGoneAll]]))));")
        for lang in LANGS:
            for line in got[lang]:
                self.assertTrue(line and line.strip(), lang)

    def test_nothing_in_the_wording_says_a_person_missed_it(self):
        """The user's own words: 「どこにも届いていません」, not 「誰にも届いていません」.

        Nobody was ever meant to be listening. What is on the other end is a
        session, so saying it in terms of people reads as an accusation of
        somebody, and in every language the same thing goes.
        """
        got = words("console.log(JSON.stringify(Object.fromEntries("
                    + json.dumps(LANGS) + ".map(l => [l, ["
                    "I18N[l].sentNowhere, I18N[l].sentNowhereHint, I18N[l].routeGoneAll]]))));")
        people = ["誰", "谁", "誰", "nobody", "no one", "anyone", "everyone",
                  "nadie", "personne", "niemand", "jemand", "아무도", "모두",
                  "所有人", "任何人", "todos", "tout le monde", "alle"]
        for lang in LANGS:
            joined = " ".join(got[lang]).lower()
            for word in people:
                self.assertNotIn(word.lower(), joined, f"{lang}: {joined}")
        self.assertEqual(got["ja"][0], "どこにも届いていません")
        self.assertIn("どこにも届いていません", got["ja"][1])

    def test_no_colons_or_dashes_in_any_of_it(self):
        got = words("console.log(JSON.stringify(Object.fromEntries("
                    + json.dumps(LANGS) + ".map(l => [l, ["
                    "I18N[l].sentNowhere, I18N[l].sentNowhereHint, I18N[l].routeGoneAll]]))));")
        for lang in LANGS:
            for line in got[lang]:
                for ch in [":", "：", " - ", "—", "–"]:
                    self.assertNotIn(ch, line, f"{lang}: {line}")

    def test_the_ended_notice_no_longer_claims_it_goes_anywhere(self):
        """With the last session gone there is nowhere for it to go.

        It used to say it was sending to everyone, which read as "nothing was
        lost" at the one moment when everything said next is.
        """
        got = words("console.log(JSON.stringify(Object.fromEntries("
                    + json.dumps(LANGS) + ".map(l => [l, I18N[l].routeGoneAll]))));")
        for lang in LANGS:
            self.assertIn("{gone}", got[lang], lang)
        self.assertNotIn("everyone", got["en"])
        self.assertNotIn("全員", got["ja"])
        self.assertIn("どこにも届きません", got["ja"])


if __name__ == "__main__":
    unittest.main()
