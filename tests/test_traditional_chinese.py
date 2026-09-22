import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/voice-shell/scripts"
sys.path.insert(0, str(SCRIPTS))

import voice_daemon as vd


class LangCodeTest(unittest.TestCase):
    """Chinese is split by script, not by region. Taiwan, Hong Kong, Macau and
    an outright Hant go to the Traditional column, everything else stays on the
    Simplified one, and an outright Hans wins over its region."""

    def test_traditional(self):
        for tag in ("zh-TW", "zh_TW", "zh-HK", "zh-MO", "zh-Hant", "zh-Hant-TW",
                    "Traditional Chinese"):
            self.assertEqual(vd.lang_code(tag), "zh-TW", tag)

    def test_simplified(self):
        for tag in ("zh", "zh-CN", "zh-SG", "zh-Hans", "zh-Hans-TW", "Chinese"):
            self.assertEqual(vd.lang_code(tag), "zh", tag)

    def test_every_language_table_has_the_column(self):
        for table in (vd.NOISE_ONLY, vd.FILLERS, vd.ROUTE_PARTS, vd.ROUTE_EXAMPLES,
                      vd.NUMBER_WORDS):
            self.assertIn("zh-TW", table)
        for kind, langs in vd.COMMAND_WORDS.items():
            self.assertIn("zh-TW", langs, kind)


class CommandTest(unittest.TestCase):
    """The Traditional wordings work, and the "?" list shows them to a reader
    of the Traditional screen instead of falling back to English."""

    def test_mic(self):
        self.assertEqual(vd.mic_command_shape("靜音", False), "mute")
        self.assertEqual(vd.mic_command_shape("關閉麥克風", False), "mute")
        self.assertEqual(vd.mic_command_shape("取消靜音", True), "unmute")
        self.assertEqual(vd.mic_command_shape("解除靜音", True), "unmute")

    def test_mode(self):
        self.assertEqual(vd.mode_command_shape("草稿模式"), "hold")
        self.assertEqual(vd.mode_command_shape("即時模式"), "live")
        # An ordinary instruction ending on "fix it, then send" is not a switch
        self.assertIsNone(vd.mode_command_shape("這個檔案改完再傳"))

    def test_tails(self):
        self.assertEqual(vd.take_tail("幫我改一下登入流程，取消這句", vd.CANCEL_TAIL),
                         "幫我改一下登入流程")
        self.assertEqual(vd.take_tail("幫我改一下登入流程。這句我來改", vd.HOLD_TAIL),
                         "幫我改一下登入流程")
        # Cancelling something inside the instruction is not cancelling the sentence
        self.assertIsNone(vd.take_tail("把明天的會議取消", vd.CANCEL_TAIL))
        # "leave that bug for later" stays an instruction
        self.assertIsNone(vd.take_tail("那個 bug 先留著改", vd.HOLD_TAIL))

    def test_route(self):
        self.assertEqual(vd.route_shape("第二個"), 2)
        self.assertEqual(vd.route_shape("第兩個"), 2)
        self.assertEqual(vd.route_shape("第2號"), 2)
        self.assertEqual(vd.route_shape("切換到2號"), 2)
        self.assertEqual(vd.route_shape("工作階段3"), 3)
        # A number with only a word after it is an ordinary word, as in Simplified
        self.assertIsNone(vd.route_shape("兩個"))
        self.assertIsNone(vd.route_shape("2號"))

    def test_catalog(self):
        groups = vd.command_catalog("zh-TW")
        self.assertFalse(any(g["fallback"] for g in groups))
        mute = next(g for g in groups if g["id"] == "mute")
        self.assertEqual(mute["phrases"][0], "靜音")


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class ScreenTest(unittest.TestCase):
    """Every key English has, with the same fill-ins, and the browser's own
    language tag picks the right one of the two Chinese screens."""

    def node(self, body):
        script = (
            "const fs = require('fs');"
            "const I18N = new Function(fs.readFileSync(process.argv[1], 'utf8') + ';return I18N;')();"
            "const v = fs.readFileSync(process.argv[2], 'utf8');"
            "const pickLang = new Function('I18N', v.slice(v.indexOf('const ZH_TRADITIONAL'),"
            " v.indexOf('function resolveLang')) + ';return pickLang;')(I18N);"
            + body)
        out = subprocess.run(["node", "-e", script, str(SCRIPTS / "i18n.js"),
                              str(SCRIPTS / "viewer.js")],
                             capture_output=True, text=True, encoding="utf-8", check=True)
        return json.loads(out.stdout)

    def test_same_keys_and_fill_ins_as_english(self):
        got = self.node(
            "const ph = s => (s.match(/\\{\\w+\\}/g) || []).sort().join();"
            "const en = I18N.en, tw = I18N['zh-TW'];"
            "console.log(JSON.stringify({"
            " missing: Object.keys(en).filter(k => !(k in tw)),"
            " extra: Object.keys(tw).filter(k => !(k in en)),"
            " fills: Object.keys(en).filter(k => k in tw && ph(en[k]) !== ph(tw[k]))}));")
        self.assertEqual(got, {"missing": [], "extra": [], "fills": []})

    def test_pick_lang(self):
        tags = ["zh-TW", "zh-HK", "zh-Hant", "zh-Hant-TW", "zh-Hans-TW", "zh-CN",
                "zh", "ja-JP"]
        got = self.node(f"console.log(JSON.stringify({json.dumps(tags)}.map(pickLang)));")
        self.assertEqual(got, ["zh-TW", "zh-TW", "zh-TW", "zh-TW", "zh", "zh", "zh", "ja"])


if __name__ == "__main__":
    unittest.main()
