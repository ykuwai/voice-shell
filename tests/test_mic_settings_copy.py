"""Pressing the chrome://settings address always answers.

The copy is refused outright in the small floating window when the clipboard of
the wrong document is asked, and the old handler swallowed that refusal, so the
press looked like nothing at all. The piece that decides what is said is cut out
of viewer.js and run under node, the way test_on_device.py does it. The rest is
read off the source, since what matters there is which window is asked and where
the answer is written.
"""
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIEWER_JS = ROOT / "skills/voice-shell/scripts/viewer.js"
VIEWER_HTML = ROOT / "skills/voice-shell/scripts/viewer.html"
I18N_JS = ROOT / "skills/voice-shell/scripts/i18n.js"

HARNESS = r'''
const assert = require('assert');
const source = require('fs').readFileSync(process.argv[1], 'utf8');
const start = source.indexOf('async function pressMicSettings');
const end = source.indexOf('el.micSettingsLink.onclick', start);
if (start < 0 || end < 0) process.exit(2);
const pressMicSettings = new Function(`${source.slice(start, end)}; return pressMicSettings;`)();
const URL = 'chrome://settings/content/microphone';
const tr = (key, vars) => key + (vars && vars.url ? ' ' + vars.url : '');
'''


def run(script):
    subprocess.run(["node", "-e", HARNESS + script, str(VIEWER_JS)], check=True, cwd=ROOT)


class MicSettingsCopyTest(unittest.TestCase):
    def test_a_copy_that_works_says_so(self):
        run(r'''
const said = [];
const clip = {writeText(v) { said.push(['wrote', v]); return Promise.resolve(); }};
pressMicSettings(clip, URL, (ok, line) => said.push([ok, line]), tr).then(r => {
  assert.equal(r, true);
  assert.deepEqual(said, [['wrote', URL], [true, 'micSettingsCopied']]);
});
''')

    def test_a_refused_copy_says_so_and_keeps_the_address_readable(self):
        run(r'''
const seen = [];
const clip = {writeText() { return Promise.reject(new Error('Document is not focused')); }};
pressMicSettings(clip, URL, (ok, line) => seen.push([ok, line]), tr).then(r => {
  assert.equal(r, false);
  assert.equal(seen.length, 1, 'never silent');
  assert.equal(seen[0][0], false);
  assert.ok(seen[0][1].includes(URL), 'the address is there to be read, got ' + seen[0][1]);
});
''')

    def test_no_clipboard_at_all_still_answers(self):
        run(r'''
const seen = [];
pressMicSettings(undefined, URL, (ok, line) => seen.push([ok, line]), tr).then(r => {
  assert.equal(r, false);
  assert.equal(seen.length, 1, 'a missing clipboard is not a silent press');
  assert.ok(seen[0][1].includes(URL));
});
''')

    def test_the_window_the_button_lives_in_is_the_one_asked(self):
        # Moved into the floating window, the button's own document is the one
        # Chrome counts as focused. Asking this document's navigator is what
        # made the copy fail there.
        source = VIEWER_JS.read_text(encoding="utf-8")
        click = source[source.index("el.micSettingsLink.onclick"):]
        click = click[:click.index("/* ── The user dictionary")]
        self.assertIn("el.micSettingsLink.ownerDocument.defaultView", click)
        self.assertIn("win.navigator.clipboard", click)
        self.assertNotIn("await navigator.clipboard", click)

    def test_the_answer_sits_beside_the_address_not_on_the_covered_hint_line(self):
        html = VIEWER_HTML.read_text(encoding="utf-8")
        self.assertIn('id="micSettingsSaid"', html)
        self.assertLess(html.index('id="micSettingsLink"'), html.index('id="micSettingsSaid"'))
        source = VIEWER_JS.read_text(encoding="utf-8")
        self.assertIn("'micSettingsSaid'", source)      # in the element registry
        self.assertIn("el.micSettingsSaid.hidden = false;", source)

    def test_every_language_has_both_lines(self):
        i18n = I18N_JS.read_text(encoding="utf-8")
        keys = ("micChromeLead", "micChromeDefault", "micSettingsCopied", "micSettingsCopyFailed")
        for key in keys:
            self.assertEqual(i18n.count(f"    {key}:'"), 8, key)
        # The wording carries no colon and no dash anywhere
        for line in i18n.splitlines():
            for key in keys:
                if line.strip().startswith(key + ":'"):
                    body = line.strip()[len(key) + 2:].rstrip("',")
                    self.assertNotIn(":", body, line)
                    self.assertNotIn("—", body, line)


if __name__ == "__main__":
    unittest.main()
