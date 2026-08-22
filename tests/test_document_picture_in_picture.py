import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIEWER_JS = ROOT / "skills/voice-shell/scripts/viewer.js"


class DocumentPictureInPictureTest(unittest.TestCase):
    def test_feature_detection_requires_a_secure_callable_api(self):
        script = r'''
const assert = require('assert');
const source = require('fs').readFileSync(process.argv[1], 'utf8');
const start = source.indexOf('function detectFloatingApi');
const end = source.indexOf('\nconst documentPip', start);
const detectFloatingApi = new Function(`${source.slice(start, end)}; return detectFloatingApi;`)();
const supported = {isSecureContext:true, documentPictureInPicture:{requestWindow() {}}};
assert.equal(detectFloatingApi(supported), supported.documentPictureInPicture);
assert.equal(detectFloatingApi({isSecureContext:false, documentPictureInPicture:{requestWindow() {}}}), null);
assert.equal(detectFloatingApi({isSecureContext:true, documentPictureInPicture:{}}), null);
assert.equal(detectFloatingApi({isSecureContext:true}), null);
const throwing = {isSecureContext:true};
Object.defineProperty(throwing, 'documentPictureInPicture', {get() { throw new Error('blocked'); }});
assert.equal(detectFloatingApi(throwing), null);
'''
        subprocess.run(["node", "-e", script, str(VIEWER_JS)], check=True, cwd=ROOT)

    def test_request_failure_disables_the_controls(self):
        source = VIEWER_JS.read_text(encoding="utf-8")
        click = source[source.index("el.floatBtn.onclick"):source.index("/* A page cannot open", source.index("el.floatBtn.onclick"))]
        self.assertIn("win = await documentPip.requestWindow", click)
        self.assertIn("catch {\n    disableFloat();", click)
        disable = source[source.index("function disableFloat"):source.index("function floatingWindow")]
        self.assertIn("el.floatBtn.disabled = true;", disable)
        self.assertIn("el.floatBtn.hidden = true;", disable)
        self.assertIn("el.floatAsk.hidden = true;", disable)

    def test_float_paths_use_the_detected_api(self):
        source = VIEWER_JS.read_text(encoding="utf-8")
        self.assertIn("const w = floatingWindow();", source)
        self.assertNotIn("documentPictureInPicture.window", source)
        self.assertIn("await documentPip.requestWindow", source)


if __name__ == "__main__":
    unittest.main()
