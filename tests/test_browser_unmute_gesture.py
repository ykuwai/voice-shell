import ast
import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIEWER = ROOT / "skills/voice-shell/scripts/viewer.py"
VIEWER_JS = ROOT / "skills/voice-shell/scripts/viewer.js"
I18N = ROOT / "skills/voice-shell/scripts/i18n.js"
HTML = ROOT / "skills/voice-shell/scripts/viewer.html"
GESTURE = ROOT / "skills/voice-shell/scripts/browser_unmute_gesture.js"


def assigned_literals(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    values = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            name = getattr(node.targets[0], "id", "")
            if name in {"TUNING_RANGE", "TUNING_FLAGS", "TUNING_INT"}:
                values[name] = ast.literal_eval(node.value)
    return values


class BrowserUnmuteGestureTuningTest(unittest.TestCase):
    def test_browser_unmute_settings_are_saved_and_clamped(self):
        values = assigned_literals(VIEWER)
        self.assertEqual(values["TUNING_RANGE"]["browser_unmute_peaks"], (1, 6))
        self.assertEqual(values["TUNING_RANGE"]["browser_unmute_window"], (0.5, 5.0))
        self.assertEqual(values["TUNING_RANGE"]["browser_unmute_threshold"], (0.65, 1.0))
        self.assertIn("browser_unmute_gesture", values["TUNING_FLAGS"])
        self.assertIn("browser_unmute_peaks", values["TUNING_INT"])

    def test_settings_and_each_translation_are_present(self):
        self.assertIn('id="browserGestureField"', HTML.read_text(encoding="utf-8"))
        text = I18N.read_text(encoding="utf-8")
        self.assertEqual(text.count("browserGestureNote:"), 7)

    def test_gesture_detection(self):
        script = """
const assert = require('assert');
const {emptyBrowserGestureState, nextBrowserGesture, shouldKeepVizCapture} = require(process.argv[1]);
const cfg = {enabled:true, active:true, inFlight:false, threshold:0.82,
  windowMs:2000, peakCount:3, minGapMs:300, minRise:0.28};
const step = (state, level, now, extra={}) => nextBrowserGesture(state, {...cfg, ...extra, level, now});
let state = emptyBrowserGestureState();
for (const [level, now] of [[0.81, 0], [0.1, 100], [0.81, 450], [0.1, 550], [0.81, 900]]) {
  const result = step(state, level, now); state = result.state; assert.equal(result.triggered, false);
}
state = emptyBrowserGestureState();
for (const [level, now, triggered] of [[0.1, 0, false], [0.95, 50, false], [0.1, 150, false], [0.95, 450, false], [0.1, 550, false], [0.95, 850, true]]) {
  const result = step(state, level, now); state = result.state; assert.equal(result.triggered, triggered);
}
state = emptyBrowserGestureState();
for (const [level, now] of [[0.1, 0], [0.95, 50], [0.1, 100], [0.95, 200]]) {
  const result = step(state, level, now); state = result.state; assert.equal(result.triggered, false);
}
state = emptyBrowserGestureState();
for (const [level, now] of [[0.1, 0], [0.95, 50], [0.1, 100], [0.95, 2300], [0.1, 2400], [0.95, 2700]]) {
  const result = step(state, level, now); state = result.state; assert.equal(result.triggered, false);
}
for (const extra of [{enabled:false}, {inFlight:true}]) {
  const result = step({peaks:[0, 400], above:true, lastPeakAt:400, lastLevel:0.9}, 0.95, 800, extra);
  assert.equal(result.triggered, false); assert.deepEqual(result.state.peaks, []);
}
assert.equal(shouldKeepVizCapture({route:'off', asrChosen:true, gestureEnabled:true, vizArmed:true}), true);
assert.equal(shouldKeepVizCapture({route:'off', asrChosen:false, gestureEnabled:true, vizArmed:true}), false);
assert.equal(shouldKeepVizCapture({route:'off', asrChosen:true, gestureEnabled:false, vizArmed:true}), false);
assert.equal(shouldKeepVizCapture({route:'on', asrChosen:false, gestureEnabled:false, vizArmed:true}), true);
assert.equal(shouldKeepVizCapture({route:'on', asrChosen:true, gestureEnabled:true, vizArmed:false}), false);
"""
        subprocess.run(["node", "-e", script, str(GESTURE)], check=True, cwd=ROOT)

    def test_engine_changes_resync_capture(self):
        text = VIEWER_JS.read_text(encoding="utf-8")
        load_engines = text[text.index("async function loadEngines()"):text.index("el.enginePick.onchange")]
        engine_pick = text[text.index("el.enginePick.onchange"):text.index("el.asrLang.onchange")]
        # Forced exactly when asrChosen actually flips (another tab or a voice
        # command switched engines), not on every 5s poll: a capture already
        # open keeps measuring whichever device it was opened for otherwise,
        # which is the wrong one the moment asrChosen (and so vizDeviceLabel's
        # answer) has changed underneath it.
        self.assertIn("syncVizCapture(was !== asrChosen);", load_engines)
        # Both branches of a manual switch force it too, same reasoning: the
        # local branch changes the device it should be measuring, the browser
        # branch stops naming one.
        self.assertEqual(engine_pick.count("syncVizCapture(true);"), 2)

    def test_viz_capture_cancels_stale_requests_and_mic_changes_resync(self):
        text = VIEWER_JS.read_text(encoding="utf-8")
        start = text[text.index("async function startViz"):text.index("function stopViz")]
        stop = text[text.index("function stopViz"):text.index("// Autoplay is restricted")]
        mic_change = text[text.index("el.mic.onchange"):text.index("// The recognition language")]
        sync = text[text.index("function syncVizCapture"):text.index("const MAX_FAILS")]
        self.assertIn("let vizGeneration = 0, vizStarting = false;", text)
        self.assertIn("const generation = ++vizGeneration;", start)
        self.assertIn("const outdated = () => generation !== vizGeneration;", start)
        self.assertGreaterEqual(start.count("stream.getTracks().forEach(tr => tr.stop());"), 2)
        self.assertIn("vizGeneration++;", stop)
        self.assertIn("syncVizCapture(true);", mic_change)
        self.assertNotIn("startViz(dev)", mic_change)
        self.assertIn("&& !vizStarting", sync)


if __name__ == "__main__":
    unittest.main()
