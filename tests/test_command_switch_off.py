"""A signal or a single wording the user switched off stays off, however it is said.

The switch-offs used to be checked against the whole utterance. Said exactly,
「ミュート」 matched the struck 「ミュート」 and stayed quiet, but with anything
ahead of it (「はいミュート」, 「えーとドラフト」) the whole utterance was no longer
the struck wording, and the lead-in path fired the command anyway.

Nothing here touches the real ~/.config/voice-shell/commands.json. The daemon the
user is running re-reads that file on every change, so each test points
COMMANDS_FILE at a file of its own.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/voice-shell/scripts"
sys.path.insert(0, str(SCRIPTS))

import voice_daemon as vd  # noqa: E402

VIEWER_JS = SCRIPTS / "viewer.js"


class SwitchOffCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.log = self.dir / "utterances.jsonl"
        self.patches = [
            mock.patch.object(vd, "COMMANDS_FILE", self.dir / "commands.json"),
            mock.patch.object(vd, "_cmd_cache", (None, None)),
            mock.patch.object(vd, "machine_config", lambda: (False, [])),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def switch_off(self, kinds=(), words=None, **added):
        data = {"off": list(kinds), "off_words": words or {}}
        data.update(added)
        vd.COMMANDS_FILE.write_text(json.dumps(data, ensure_ascii=False),
                                    encoding="utf-8")
        vd._cmd_cache = (None, None)

    def apply(self, text, muted=False):
        return vd.apply_voice_command(text, self.log, muted, {"replace": {}})


class MuteSwitchOffTest(SwitchOffCase):
    FORMS = ("ミュート", "はいミュート", "えーとミュート", "えーと、ミュート。")

    def test_all_forms_fire_while_on(self):
        for s in self.FORMS:
            self.assertEqual(vd.voice_command(s, False), "mute", s)

    def test_kind_off(self):
        self.switch_off(kinds=["mute"])
        for s in self.FORMS:
            self.assertIsNone(vd.voice_command(s, False), s)
            self.assertIsNone(self.apply(s), s)

    def test_word_off(self):
        self.switch_off(words={"mute": ["ミュート"]})
        for s in self.FORMS:
            self.assertIsNone(vd.voice_command(s, False), s)
            self.assertIsNone(self.apply(s), s)
        # The rest of the kind still bites, with a lead-in too
        self.assertEqual(vd.voice_command("はいマイクオフ", False), "mute")

    def test_struck_long_wording_does_not_fall_to_a_short_one_inside(self):
        # Said exactly, a struck 「麦克风静音」 does nothing. With a lead-in it must
        # not fire through the shorter 「静音」 sitting at its end either.
        self.switch_off(words={"mute": ["麦克风静音"]})
        for s in ("麦克风静音", "嗯麦克风静音"):
            self.assertIsNone(vd.voice_command(s, False), s)
        self.assertEqual(vd.voice_command("静音", False), "mute")

    def test_english_word_off_with_spaces(self):
        self.switch_off(words={"mute": ["mic off"]})
        for s in ("mic off", "uh mic off"):
            self.assertIsNone(vd.voice_command(s, False), s)

    def test_typed_back_in_by_hand_wins(self):
        self.switch_off(words={"mute": ["ミュート"]}, mute=["ミュート"])
        self.assertEqual(vd.voice_command("ミュート", False), "mute")


class UnmuteSwitchOffTest(SwitchOffCase):
    FORMS = ("ミュート解除", "はいミュート解除", "えーとミュート解除")

    def test_kind_off(self):
        self.switch_off(kinds=["unmute"])
        for s in self.FORMS:
            self.assertIsNone(vd.voice_command(s, True), s)
            self.assertIsNone(self.apply(s, muted=True), s)

    def test_word_off(self):
        self.assertEqual(vd.voice_command("はいミュート解除", True), "unmute")
        self.switch_off(words={"unmute": ["ミュート解除"]})
        for s in self.FORMS:
            self.assertIsNone(vd.voice_command(s, True), s)


class ModeSwitchOffTest(SwitchOffCase):
    HOLD = ("手直し", "はい手直し", "えーと手直し")
    DRAFT = ("ドラフト", "えーとドラフト", "はい、ドラフト")
    LIVE = ("インスタント", "えーとインスタント")

    def test_all_forms_fire_while_on(self):
        for s in self.HOLD + self.DRAFT:
            self.assertEqual(vd.mode_command(s), "hold", s)
        for s in self.LIVE:
            self.assertEqual(vd.mode_command(s), "live", s)

    def test_kind_off(self):
        self.switch_off(kinds=["hold", "live"])
        for s in self.HOLD + self.DRAFT + self.LIVE:
            self.assertIsNone(vd.mode_command(s), s)
            self.assertIsNone(self.apply(s), s)

    def test_word_off(self):
        self.switch_off(words={"hold": ["手直し", "ドラフト"],
                               "live": ["インスタント"]})
        for s in self.HOLD + self.DRAFT + self.LIVE:
            self.assertIsNone(vd.mode_command(s), s)
            self.assertIsNone(self.apply(s), s)
        # Wordings not struck go on working
        self.assertEqual(vd.mode_command("はい手直しモード"), "hold")
        self.assertEqual(vd.mode_command("即時"), "live")


class RouteSwitchOffTest(SwitchOffCase):
    def test_kind_off(self):
        self.switch_off(kinds=["route"])
        for s in ("2番", "セッション2", "switch to 2"):
            self.assertIsNone(vd.route_command(s), s)


class TailSwitchOffTest(SwitchOffCase):
    def test_kind_off(self):
        self.switch_off(kinds=["cancel_tail", "hold_tail"])
        for s in ("キャンセル", "えーとキャンセル", "これを直して、キャンセル"):
            self.assertIsNone(vd.take_tail(s, vd.active_tail("cancel_tail")), s)
        for s in ("手直し", "えーと手直し", "これを直して、手直し"):
            self.assertIsNone(vd.take_tail(s, vd.active_tail("hold_tail")), s)

    def test_word_off(self):
        self.switch_off(words={"cancel_tail": ["キャンセル"],
                               "hold_tail": ["手直し"]})
        for s in ("キャンセル", "えーとキャンセル", "これを直して、キャンセル"):
            self.assertIsNone(vd.take_tail(s, vd.active_tail("cancel_tail")), s)
        for s in ("手直し", "えーと手直し", "これを直して、手直し"):
            self.assertIsNone(vd.take_tail(s, vd.active_tail("hold_tail")), s)
        self.assertEqual(vd.take_tail("これを直して、取り消し",
                                      vd.active_tail("cancel_tail")), "これを直して")


class MachineNameSwitchOffTest(SwitchOffCase):
    def setUp(self):
        super().setUp()
        p = mock.patch.object(vd, "machine_config", lambda: (True, ["開発用"]))
        p.start()
        self.patches.append(p)

    def test_named_forms_honor_word_off(self):
        self.assertEqual(self.apply("開発用ミュート"), "mute")
        self.switch_off(words={"mute": ["ミュート"], "hold": ["ドラフト"]})
        for s in ("開発用ミュート", "開発用、はいミュート", "開発用えーとミュート",
                  "開発用ドラフト", "開発用えーとドラフト"):
            self.assertIsNone(self.apply(s), s)

    def test_named_forms_honor_kind_off(self):
        self.switch_off(kinds=["mute"])
        for s in ("開発用ミュート", "開発用はいミュート"):
            self.assertIsNone(self.apply(s), s)

    def test_other_machine_still_dropped(self):
        # What the box next door switched off cannot be seen from here, so a
        # command aimed at it is still dropped rather than sent to Claude.
        self.switch_off(words={"mute": ["ミュート"]})
        self.assertEqual(self.apply("会議用ミュート"), "other_machine")


HARNESS = r'''
const fs = require('fs');
const source = fs.readFileSync(process.argv[1], 'utf8');
const start = source.indexOf("const TAIL_IDS = ");
const end = source.indexOf("function endsWithTailCmd", start);
if (start < 0 || end < 0) process.exit(2);
const body = source.slice(start, end).replace(/async function loadTailWords[\s\S]*?\n}\n/, '');
const make = new Function('words', 'off', `
  ${body}
  tailWords = words;
  takeCmdOff(off);
  return matchingTailWord;
`);
const assert = (cond, what) => { if (!cond) { console.error(what); process.exit(1); } };
const words = {cancel_tail: new Set(['キャンセル']), hold_tail: new Set(['手直し']),
               mute: new Set(['ミュート', '静音', '麦克风静音'])};
let m = make(words, {});
for (const s of ['ミュート', 'はいミュート', 'えーとミュート', '嗯麦克风静音'])
  assert(m(s)?.id === 'mute', 'on: ' + s);
m = make(words, {off: ['mute']});
for (const s of ['ミュート', 'はいミュート', 'えーとミュート'])
  assert(m(s) === null, 'kind off: ' + s);
m = make(words, {off_words: {mute: ['ミュート', '麦克风静音']}});
for (const s of ['ミュート', 'はいミュート', 'えーとミュート', '麦克风静音', '嗯麦克风静音'])
  assert(m(s) === null, 'word off: ' + s);
assert(m('静音')?.id === 'mute', 'the rest still bites');
m = make(words, {off_words: {cancel_tail: ['キャンセル']}});
assert(m('えーとキャンセル') === null, 'tail word off');
'''


class ViewerJsSwitchOffTest(unittest.TestCase):
    def test_matching_tail_word_honors_switch_offs(self):
        subprocess.run(["node", "-e", HARNESS, str(VIEWER_JS)], check=True)


if __name__ == "__main__":
    unittest.main()
