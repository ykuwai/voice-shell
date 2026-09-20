import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/voice-shell/scripts"
sys.path.insert(0, str(SCRIPTS))

import asr_mic
import voice_daemon as vd


class AvailableEnginesTest(unittest.TestCase):
    """`apple` runs through a Swift helper built on the spot, so a Mac without
    the Command Line Tools cannot use it, and most Macs do not have them. It
    stays in the list all the same, marked not ready and carrying the one
    command that changes that (hiding it leaves nobody any way of finding out).

    The probe is `xcode-select -p` on purpose. A stock Mac carries
    /usr/bin/swiftc before the tools are installed, as an xcode-select shim, so
    `which("swiftc")` answers yes on every Mac and would quietly make all of
    this dead code."""

    def engines(self, clt):
        with mock.patch.object(asr_mic.sys, "platform", "darwin"), \
             mock.patch.object(asr_mic, "_mac_version", return_value=26), \
             mock.patch.object(asr_mic, "_clt_installed", return_value=clt):
            return {e["id"]: e for e in asr_mic.available_engines()}

    def test_apple_is_ready_with_the_tools(self):
        apple = self.engines(clt=True)["apple"]
        self.assertTrue(apple["ready"])
        self.assertEqual(apple["need"], "")

    def test_apple_is_listed_but_not_ready_without_them(self):
        apple = self.engines(clt=False)["apple"]
        self.assertFalse(apple["ready"])
        self.assertEqual(apple["need"], "xcode-select --install")


class ResolveEngineTest(unittest.TestCase):
    """Named outright, a not-ready engine is let through: the caller asked for
    it, and being told what is missing beats being turned away. Coming from the
    remembered choice or from `auto`, it is not, since there nobody asked."""

    NOT_READY = [{"id": "apple", "label": "Apple", "ready": False,
                  "need": "xcode-select --install"}]

    def setUp(self):
        vd._SAID_UNUSABLE = False

    def resolve(self, want, engines, remembered=None):
        with mock.patch.object(asr_mic, "available_engines", return_value=engines), \
             mock.patch.object(vd, "read_config",
                               return_value={"engine": remembered} if remembered else {}):
            return vd.resolve_engine(want)

    def test_named_outright_is_let_through(self):
        self.assertEqual(self.resolve("apple", self.NOT_READY), "apple")

    def test_remembered_falls_back_to_the_browser(self):
        self.assertEqual(
            self.resolve("", self.NOT_READY, remembered="apple"), "browser")

    def test_said_once_however_often_it_is_asked(self):
        # viewer's /api/engines resolves this every 5 seconds per open tab
        with mock.patch.object(asr_mic, "available_engines", return_value=self.NOT_READY), \
             mock.patch.object(vd, "read_config", return_value={"engine": "apple"}), \
             mock.patch("sys.stderr") as err:
            for _ in range(3):
                vd.resolve_engine("")
        self.assertEqual(sum("cannot be used now" in str(c) for c in err.write.call_args_list), 1)

    def test_auto_will_not_take_a_not_ready_one(self):
        with self.assertRaises(SystemExit):
            self.resolve("auto", self.NOT_READY)

    def test_auto_takes_a_ready_one(self):
        ready = [{"id": "whisper", "label": "Whisper", "ready": True, "need": ""}]
        self.assertEqual(self.resolve("auto", ready), "whisper")


if __name__ == "__main__":
    unittest.main()
