"""The microphone sits with the engine, and goes inert when the browser listens.

The pick used to be at the very top of the settings sheet while the sentence
explaining it sat a whole screen below, in the recognition group, so the two
were never on screen together. It now sits at the head of that same group, and
under browser recognition it holds one entry naming Chrome's own setting and
takes no presses, which is what the sentence used to say.

paintMicPick is cut out of viewer.js and run under node with its surroundings
handed in, the way test_mic_settings_copy.py does with pressMicSettings. The
placement is read off the source, since what matters there is the order things
appear in.
"""
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIEWER_JS = ROOT / "skills/voice-shell/scripts/viewer.js"
VIEWER_HTML = ROOT / "skills/voice-shell/scripts/viewer.html"
VIEWER_CSS = ROOT / "skills/voice-shell/scripts/viewer.css"
I18N_JS = ROOT / "skills/voice-shell/scripts/i18n.js"

# A select with just enough of one to be painted, and a document that hands
# back bare options.
HARNESS = r'''
const assert = require('assert');
const source = require('fs').readFileSync(process.argv[1], 'utf8');
const start = source.indexOf('function paintMicPick()');
const end = source.indexOf('async function loadMics', start);
if (start < 0 || end < 0) process.exit(2);
const make = new Function('asrChosen', 'el', 'document', 't', 'micList', 'micCurrent', 'micLabel',
  `${source.slice(start, end)}; return paintMicPick;`);

const document = {createElement: () => ({value:'', textContent:'', selected:false})};
const t = k => '<' + k + '>';
const micLabel = m => m.label || m.id;
function freshPick() {
  return {
    options: [], hidden: null, disabled: null,
    replaceChildren(...kids) { this.options = kids; },
    prepend(kid) { this.options.unshift(kid); },
    get value() { const s = this.options.find(o => o.selected); return s ? s.value : ''; },
  };
}
const paint = (asrChosen, mic, list, current) =>
  make(asrChosen, {mic}, document, t, list, current, micLabel)();
'''


def run(script):
    subprocess.run(["node", "-e", HARNESS + script, str(VIEWER_JS)], check=True, cwd=ROOT)


class MicInEngineGroupTest(unittest.TestCase):
    def test_the_pick_sits_at_the_head_of_the_recognition_group(self):
        html = VIEWER_HTML.read_text(encoding="utf-8")
        group = html.index('id="engineGroup"')
        mic = html.index('id="mic"')
        engine = html.index('id="enginePick"')
        self.assertLess(group, mic, "the microphone is inside the recognition group")
        self.assertLess(mic, engine, "and at the head of it, above the engine")
        # One control, not two
        self.assertEqual(html.count('id="mic"'), 1)

    def test_the_sentence_that_misled_is_gone_from_every_language(self):
        i18n = I18N_JS.read_text(encoding="utf-8")
        self.assertNotIn("browserMicNote", i18n)
        self.assertNotIn("browserMicNote", VIEWER_HTML.read_text(encoding="utf-8"))
        self.assertNotIn("browserMicNote", VIEWER_JS.read_text(encoding="utf-8"))
        # The address stayed, with a lead-in
        self.assertIn('id="micSettingsLink"', VIEWER_HTML.read_text(encoding="utf-8"))

    def test_only_the_microphone_wears_the_inert_look(self):
        # The engine pick is disabled too, for the moment a switch takes, and
        # there the grey would read as broken rather than as out of play.
        css = VIEWER_CSS.read_text(encoding="utf-8")
        self.assertIn("#mic:disabled", css)
        self.assertNotIn("\n  select:disabled", css)

    def test_under_the_browser_it_names_chromes_setting_and_takes_no_presses(self):
        run(r'''
const mic = freshPick();
paint(true, mic, [{id:'usb', label:'USB mic'}], 'usb');
assert.equal(mic.options.length, 1, 'one entry, nothing to choose between');
assert.equal(mic.options[0].textContent, '<micChromeDefault>');
assert.equal(mic.disabled, true, 'inert');
assert.equal(mic.hidden, false, 'still there to be read');
''')

    def test_the_local_engines_get_the_real_list_back(self):
        run(r'''
const mic = freshPick();
const list = [{id:'default', label:''}, {id:'usb', label:'USB mic'}];
paint(true, mic, list, 'usb');
paint(false, mic, list, 'usb');
assert.equal(mic.disabled, false);
assert.equal(mic.options.length, 2);
assert.equal(mic.value, 'usb', 'what was picked before is still picked');
''')


if __name__ == "__main__":
    unittest.main()
