#!/usr/bin/env python3
"""Background daemon for voice prompts.

It keeps listening to the mic and appends one JSON line to the log every time an
utterance settles. On the Claude Code side, Monitor tails this log and treats
each line that arrives as a prompt.

    python voice_daemon.py --language Japanese

Log format is one utterance per line, JSONL. Only the body goes in.
    {"text": "run the tests"}

The control commands are as follows.
    python voice_daemon.py --status    # check whether it is running
    python voice_daemon.py --stop      # stop it
"""
import argparse
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

# fcntl is POSIX only (Windows does not have it). The only use here is the lock
# that stops a second instance, so on Windows msvcrt.locking stands in.
if sys.platform.startswith("win"):
    import msvcrt

    def _lock_exclusive_nb(f):
        f.write("x")
        f.flush()
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
else:
    import fcntl

    def _lock_exclusive_nb(f):
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)

import asr_mic

# The "/tmp" that voice-shell.sh (bash) sees and the "/tmp" this Python process
# resolves on its own can be different real directories (on Windows the former is
# the MSYS mount point, the latter is C:\tmp at the drive root). voice-shell.sh
# passes the cygpath-resolved real path in VOICE_SHELL_STATE_DIR, so prefer that.
if os.environ.get("VOICE_SHELL_STATE_DIR"):
    STATE_DIR = Path(os.environ["VOICE_SHELL_STATE_DIR"])
else:
    # This used to be named "qwen-voice" after the recognition model. The name
    # follows the tool now, but so nothing already running breaks, keep using the
    # old one when it is there and the new one is not (once /tmp is cleared it
    # moves to the new name on its own).
    _base = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp"))
    STATE_DIR = _base / "voice-shell"
    _legacy = _base / "qwen-voice"
    if not STATE_DIR.exists() and _legacy.exists():
        STATE_DIR = _legacy

# User dictionary. It has to survive restarts, so it lives in the config dir.
# The web UI can edit it and edits land from the next utterance (no daemon restart).
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME",
                                 Path.home() / ".config")) / "voice-shell"
DICT_FILE = CONFIG_DIR / "dictionary.json"
# Mic sensitivity and how many seconds of silence settles an utterance. Like the
# dictionary it lives in the config dir and the viewer can change it. The daemon
# re-reads it every 0.5 seconds, so no restart is needed.
TUNING_FILE = CONFIG_DIR / "tuning.json"
# Where "start with this next time" is remembered. Like the dictionary and the
# thresholds it goes in the config dir (in /tmp it would vanish on reboot and you
# would have to pick again every time).
CONFIG_FILE = CONFIG_DIR / "config.json"
PID_FILE = STATE_DIR / "daemon.pid"
LOG_FILE = STATE_DIR / "utterances.jsonl"
# Text while recognition is still running. Overwritten, no history kept (for the
# viewer).
PARTIAL_FILE = STATE_DIR / "partial.txt"
# The volume being picked up right now. The viewer draws it as a bar.
# When no text shows up, this tells a dead mic apart from a room that is just quiet.
LEVEL_FILE = STATE_DIR / "level.txt"
# While this file exists, utterances are held. Recognition keeps going but nothing
# goes to Claude. It piles up in the hold tray so you can fix it before sending.
PAUSE_FILE = STATE_DIR / "paused"
# Where utterances that settled while held are kept.
HOLD_FILE = STATE_DIR / "held.jsonl"
# While this file exists the mic counts as off. Results are thrown away, kept nowhere.
# Starting the daemon again takes 1 to 2 minutes, so this only ignores what comes in.
MUTE_FILE = STATE_DIR / "muted"
# The mic to use. The viewer writes it, the daemon reads it and swaps out only the
# recording (the model stays loaded, so there is no waiting).
MIC_FILE = STATE_DIR / "mic"

# Stock phrases that tend to come out when only a noise or a breath got picked up.
# An utterance that is nothing but one of these is not an instruction, so drop it.
# (The model fits a backchannel onto input that is close to silence.)
NOISE_ONLY = {
    # Replies and backchannels
    "はい", "はいはい", "はーい", "うん", "うんうん", "ううん", "ええ", "ええと",
    "そう", "そうそう", "そうか", "そうね", "そうですね", "なるほど", "たしかに",
    "オーケー", "オッケー", "よし", "よしよし", "わかった", "了解",
    # Breaths and hesitations
    "あ", "あー", "ああ", "あっ", "い", "う", "うー", "うーん", "え", "えー",
    "えっ", "お", "おー", "おお", "おっ", "ん", "んー", "んん", "は", "はっ",
    "ふ", "ふう", "ふん", "ふーん", "ふむ", "へ", "へえ", "ほう", "ほー",
    "まあ", "ねえ", "あの", "あのー", "えっと", "えーと", "なんか",
    # Stock video phrases (the Japanese "thanks for watching" sign-off and such)
    # do not go here. People in any country use this tool, and a list that opens
    # with turns of phrase from Japanese videos leaves a first-time reader unable
    # to tell what it is for. Whoever needs them can add them in the dictionary.
    # The same kind of backchannel comes out in English
    "yeah", "yes", "yep", "ok", "okay", "uh", "uh-huh", "um", "umm",
    "hmm", "hm", "mm", "mhm", "oh", "ah", "ahh", "eh", "huh",
    "right", "so", "well", "sure", "wow", "hey",
}

# Characters stripped before comparing, punctuation and symbols and whitespace
_TRIM = "。、．，！？!?.…・ 　\n"

# When a noise gets picked up it is sometimes misrecognized as something other than
# Japanese (measured, Chinese came out). If the text holds characters Japanese never
# uses, treat that utterance as a misrecognition and drop it.
_NON_JA = re.compile(
    "["
    "ㄅ-ㄯ"      # Bopomofo
    "가-힯"      # Hangul
    "Ѐ-ӿ"      # Cyrillic
    "฀-๿"      # Thai
    "؀-ۿ"      # Arabic
    "嗯呢吗吧咱您们这那哪儿铁东车马门问题时间说话谢没儿"  # Simplified, specific to Chinese
    "]"
)


def looks_non_japanese(text: str) -> bool:
    """Whether characters that are neither Japanese nor English are mixed in."""
    return bool(_NON_JA.search(text))


DEFAULT_DICT = {
    # Dropped when the whole utterance is just this (adds on top of NOISE_ONLY)
    "ignore": [],
    # Replaces what came out of recognition. Technical terms break down easily into
    # katakana or shorthand. Longer entries are matched first, so overlaps are fine.
    "replace": {
        # Claude
        "クロードコード": "Claude Code",
        "クラウドコード": "Claude Code",
        "クロード": "Claude",
        "アンソロピック": "Anthropic",
        "エージェントスキルズ": "Agent Skills",
        "スキルズドットエムディー": "SKILL.md",
        "スキルズドットM.D.": "SKILL.md",
        "スキルドットエムディー": "SKILL.md",
        "スキルズドットエスエイチ": "skills.sh",
        "スキルズドットS.H.": "skills.sh",
        # Abbreviations that often break down (periods get inserted)
        "A.I.": "AI",
        "エーアイ": "AI",
        "L.L.M.": "LLM",
        "エルエルエム": "LLM",
        "A.P.I.": "API",
        "エーピーアイ": "API",
        "C.L.I.": "CLI",
        "U.I.": "UI",
        "O.S.": "OS",
        "C.S.V.": "CSV",
        "J.S.O.N.": "JSON",
        "G.P.U.": "GPU",
        "C.P.U.": "CPU",
        "M.C.P.": "MCP",
        "P.R.": "PR",
        # Models and services from other companies (the ones that come out in katakana)
        "ジェミニ": "Gemini",
        "オープンエーアイ": "OpenAI",
        "チャットジーピーティー": "ChatGPT",
        "コーデックス": "Codex",
        "コパイロット": "Copilot",
        # 「カーソル」 (Cursor) is left out, the same word also means the text cursor
        # Tools and services
        "ギットハブ": "GitHub",
        "ギットいーぶ": "GitHub",
        "ヴイエスコード": "VS Code",
        "ブイエスコード": "VS Code",
        "V.S.コード": "VS Code",
        "パイソン": "Python",
        "ドッカー": "Docker",
        "ノードジェイエス": "Node.js",
        "タイプスクリプト": "TypeScript",
        "ジャバスクリプト": "JavaScript",
        # This project
        "ボイスシェル": "voice-shell",
    },
}


_dict_cache = (None, None)   # (mtime, contents)


def _read_one(path: Path) -> dict:
    """Read one dictionary file. Empty when it is missing or broken."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"ignore": [], "unignore": [], "replace": {}}
    except (json.JSONDecodeError, OSError) as e:
        print(f"{path.name} を読めませんでした ({e})。無視します", file=sys.stderr)
        return {"ignore": [], "unignore": [], "replace": {}}
    return {
        "ignore": [s for s in data.get("ignore", []) if isinstance(s, str)],
        # Of the words the built-in list ignores, the ones the user decided not to
        # ignore. Words people really do say back to you, like 「わかった」 or
        # 「了解」 (got it, roger), are in the built-in list. Which ones get in the
        # way depends on the person, so they can be taken out.
        "unignore": [s for s in data.get("unignore", []) if isinstance(s, str)],
        "replace": {k: v for k, v in data.get("replace", {}).items()
                    if isinstance(k, str) and isinstance(v, str)},
    }


def _mtime():
    try:
        return DICT_FILE.stat().st_mtime
    except OSError:
        return None


def load_dictionary() -> dict:
    """Return the dictionary.

    This is called for every utterance, so it re-reads only when the mtime changed.
    That is what makes web UI edits show up without restarting the daemon.
    """
    global _dict_cache
    mtime = _mtime()
    # Rule out the missing case first. The cache also starts at None, so in the
    # other order "nothing read yet" and "no file" would look the same.
    if mtime is None:
        return DEFAULT_DICT
    if _dict_cache[0] == mtime:
        return _dict_cache[1]

    d = _read_one(DICT_FILE)
    _dict_cache = (mtime, d)
    return d


def save_default_dictionary():
    """Create the dictionary from the defaults when there is none (the starting point
    for editing from the web UI).

    When one already exists, add only the entries the defaults gained. What the user
    edited or deleted is respected, so nothing gets overwritten.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    if not DICT_FILE.exists():
        # Note down the shipped words at the moment of creation. Skip this and the
        # words shipped on the first run come right back at the next update for
        # anyone who deleted them.
        first = dict(DEFAULT_DICT)
        first["_seen"] = sorted(DEFAULT_DICT["replace"])
        first["_seen_ignore"] = sorted(DEFAULT_DICT["ignore"])
        DICT_FILE.write_text(json.dumps(first, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return

    try:
        cur = json.loads(DICT_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return                      # Broken, so leave it alone (the user can fix it)

    # Fill in only the words newly added to the defaults. Values the user changed
    # stay put. Words ever shipped as a default are noted separately for replacements
    # and for ignores. In one bucket, when the same word sits in both, deleting it
    # from one side would stop the other from being shipped too. Noting only the
    # replacements would bring back a deleted default ignore word at every update.
    known = set(cur.get("_seen", []))
    known_ignore = set(cur.get("_seen_ignore", []))
    replace = dict(cur.get("replace", {}))
    ignore = list(cur.get("ignore", []))
    added = 0
    for k, v in DEFAULT_DICT["replace"].items():
        if k not in replace and k not in known:
            replace[k] = v
            added += 1
    for w in DEFAULT_DICT["ignore"]:
        if w not in ignore and w not in known_ignore:
            ignore.append(w)
            added += 1

    if not added:
        return

    cur["replace"] = replace
    cur["ignore"] = ignore
    cur["_seen"] = sorted(known | set(DEFAULT_DICT["replace"]))
    cur["_seen_ignore"] = sorted(known_ignore | set(DEFAULT_DICT["ignore"]))
    DICT_FILE.write_text(json.dumps(cur, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"辞書に既定の項目を {added} 件追加しました", file=sys.stderr)


# Kanji numerals. Rewrites place-value forms (三十二 → 32) as digits.
_KANJI_DIGIT = {"〇": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
                "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_KANJI_SMALL = {"十": 10, "百": 100, "千": 1000}
_KANJI_BIG = {"万": 10**4, "億": 10**8, "兆": 10**12}

# Pick up only runs that read as a number. To keep 「一部」 and 「一気に」 intact,
# forms followed by a counter or a particle are excluded separately in _NOT_NUMBER.
_KANJI_NUM_RE = re.compile(r"[〇零一二三四五六七八九十百千万億兆]+")

# Words whose meaning changes if turned into digits (idioms, compounds). Not converted.
_NOT_NUMBER = {
    "一部", "一気", "一緒", "一応", "一旦", "一度", "一体", "一番", "一通り",
    "一方", "一見", "一切", "一人", "二人", "三人", "一日", "一言", "一杯",
    "一瞬", "一生", "一件", "一種", "一定", "一致", "一連", "一覧", "一環",
    "十分", "百歩", "千差", "万一", "万能", "億劫",
}


def _kanji_to_int(s: str):
    """Turn a kanji numeral into an int. None when it does not read as one."""
    total = 0        # Sum across the 万 and 億 boundaries
    section = 0      # Value of the current section (below 万)
    digit = None     # The single digit just before

    for ch in s:
        if ch in _KANJI_DIGIT:
            digit = _KANJI_DIGIT[ch]
        elif ch in _KANJI_SMALL:
            section += (digit if digit is not None else 1) * _KANJI_SMALL[ch]
            digit = None
        elif ch in _KANJI_BIG:
            section += digit or 0
            if section == 0:
                section = 1
            total += section * _KANJI_BIG[ch]
            section = 0
            digit = None
        else:
            return None

    return total + section + (digit or 0)


def kanji_numbers_to_arabic(text: str) -> str:
    """Rewrite kanji numerals as Arabic ones (「三十秒」 → 「30秒」).

    Compounds and idioms (一部, 十分 and the like) are left alone. A bare 「一」 or
    「二」 is left alone too, since there is no telling whether it was said as a number.
    """
    def sub(m):
        s = m.group(0)
        if s in _NOT_NUMBER or len(s) == 1:
            return s
        n = _kanji_to_int(s)
        return str(n) if n is not None else s

    return _KANJI_NUM_RE.sub(sub, text)


# Written in caps and still not an acronym. Do not turn "A vs B" into "A VS B".
# Lowercase shorthand like e.g. / i.e. / a.m. is already rejected by the uppercase
# test, so it is not listed here.
_NOT_ACRONYM = {"vs"}

# A run of letters split one at a time. Catches "G.U.I.", "G U I" and "T.T.S".
# The separator right after each letter is a period or a space. Only the last letter
# may go without one. Requiring two or more letters keeps a lone "I" or "a" out.
_SPELLED_RE = re.compile(
    r"(?<![A-Za-z])"              # A letter just before means part of another word, leave it
    r"((?:[A-Za-z][.　 ]){1,}[A-Za-z]\.?)"
    r"(?![A-Za-z])"               # Same when a letter comes just after
)


def collapse_letter_acronyms(text: str) -> str:
    """Squeeze an acronym read out one letter at a time ("G.U.I.", "S S H" → "GUI", "SSH").

    Speech recognition sometimes returns an acronym split letter by letter. The
    dictionary can fix that too, but it does nothing for unregistered words (AWS,
    JWT and so on), so this collapses them mechanically by shape.

    A legitimately dotted word like "Node.js" and a period ending a sentence are left
    alone. Only runs with two or more separators in a row are targeted, so a lone
    "I." or an ordinary sentence like "it. Some" is not affected.
    """
    def sub(m):
        s = m.group(1)
        letters = re.sub(r"[.　 ]", "", s)
        # Acronyms returned by speech recognition are uppercase. A lowercase run
        # ("a b c", "e.g.") is ordinary prose or shorthand, so leave it. This test
        # alone protects e.g. / i.e. / a.m. (an uppercase 「A M 三時」 can safely
        # squeeze down to AM).
        if not letters.isupper():
            return s
        # Uppercase but not an acronym (the V S in "A vs B") stays as it is
        if letters.lower() in _NOT_ACRONYM:
            return s
        return letters

    return _SPELLED_RE.sub(sub, text)


def apply_replacements(text: str, replace: dict) -> str:
    """Apply the dictionary replacements. Longest first, to catch partial matches."""
    for src in sorted(replace, key=len, reverse=True):
        if src:
            text = text.replace(src, replace[src])
    return text


# Filler words that carry no meaning. Turned on and off in the viewer settings. Removing
# them here takes them out of the body that reaches Claude, not just the screen.
FILLERS = ["えーと", "えっと", "ええと", "あのー", "あの", "えー", "えっ",
           "まあ", "なんか", "そのー", "うーん", "んー"]
# Longest first (so 「あのー」 is not eaten by 「あの」 beforehand)
_FILLER_RE = re.compile("|".join(re.escape(w) for w in
                                 sorted(FILLERS, key=len, reverse=True)))


def strip_fillers(text: str) -> str:
    """Drop the filler words and tidy up the punctuation they leave behind."""
    text = _FILLER_RE.sub("", text)
    text = re.sub("、{2,}", "、", text)
    text = re.sub(r"^[、。\s]+", "", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def fix_latin_commas(text: str) -> str:
    """Undo the Japanese comma inserted between English words in Japanese mode."""
    return re.sub(r"([A-Za-z])、(?=[A-Za-z])", r"\1 ", text)


def read_config() -> dict:
    """The previous choice. Empty when there is none."""
    try:
        d = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def write_config(**kw) -> dict:
    """Remember a choice. Only the keys passed in get replaced.

    None means leave it alone. An empty string or False means clear it or turn it
    off, so those go through.
    """
    cur = read_config()
    cur.update({k: v for k, v in kw.items() if v is not None})
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cur, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return cur


def resolve_engine(want: str = "") -> str:
    """Decide which engine to use from here on.

    Explicit > previous choice > automatic. Automatic picks the browser, the one that
    runs with nothing installed. Only when the browser cannot be used (no screen to
    open) does the caller pass --engine auto, and then the pick comes from the models
    that are installed.
    """
    known = {"browser"} | {e["id"] for e in asr_mic.available_engines()}

    if want and want != "auto":
        if want not in known:
            sys.exit(f"「{want}」は使えません。"
                     f"選べるのは {', '.join(sorted(known))} です。\n"
                     f"  一覧は voice-shell.sh engines")
        return want
    if not want:
        remembered = read_config().get("engine")
        if remembered in known:
            return remembered
        # What was remembered is no longer usable (the model got deleted, say).
        # Falling back to the one that needs nothing beats failing silently.
        if remembered:
            print(f"前回選んだ「{remembered}」は今使えないので、"
                  f"このブラウザで認識します。", file=sys.stderr)
        return "browser"
    # For want == "auto", pick from among the models that are installed
    have = [e["id"] for e in asr_mic.available_engines()]
    for pick in ("apple", "whisper"):
        if pick in have:
            return pick
    # auto means "no screen to open, so use a local model". Falling back to browser
    # when there is not a single one would betray that premise.
    sys.exit("手元で使える認識モデルがありません。\n"
             "  SETUP.md の手順で入れるか、画面を開けるなら\n"
             "  voice-shell.sh start --engine browser をお使いください。")


def polish(text: str, user_dict: dict, keep_kanji_numbers: bool = False,
           drop_fillers: bool = False) -> str:
    """Tidy the recognized text so it reads well.

    Acronyms get squeezed first because the dictionary matches exactly. Left as
    「G P U」 it never hits the registered 「G.P.U.」.
    """
    text = collapse_letter_acronyms(text)
    text = apply_replacements(text, user_dict["replace"])
    if not keep_kanji_numbers:
        text = kanji_numbers_to_arabic(text)
    text = fix_latin_commas(text)
    if drop_fillers:
        text = strip_fillers(text)
    return text


def is_noise(text: str, extra=(), allow=()) -> bool:
    """Whether the utterance is nothing but a backchannel.

    A word merely repeated with a break, like 「はい、はい」, counts as a backchannel
    too. An utterance with substance (「はい、それでは始めます」) is kept.

    Pass the dictionary's ignore list as extra. It is treated the same as the built-in
    list, so words the user added also work in the 「〜、〜」 repeat test.

    Pass words to take out of the built-in list as allow. Words people really do say
    back to you, like 「わかった」 or 「了解」, are in the built-in list.
    """
    off = {w.strip().lower() for w in allow}
    words = ({w for w in NOISE_ONLY if w.lower() not in off}
             | {w.lower() for w in extra})
    core = text.strip().strip(_TRIM)
    if core.lower() in words:
        return True
    # Split on punctuation, drop it when every part is a backchannel
    # (「はい、はい」 「うん、うん。」)
    parts = [p.strip().strip(_TRIM) for p in re.split(r"[、。,.\s]+", core) if p.strip(_TRIM)]
    return bool(parts) and all(p.lower() in words for p in parts)


def is_allowed_short(text: str, allow=()) -> bool:
    """Whether a short utterance is one the minimum length must not drop.

    The minimum length (15 characters by default) is there to throw away misrecognized
    noise, and lowering it starts letting 「はい」 and 「うん」 through. Instead of
    lowering it, let through only what the user picked as **this word specifically
    should get through**.

    What goes into allow is the dictionary's unignore, the built-in ignore words the
    person took out themselves. Words people really do say in answer to a question,
    like 「わかった」 or 「了解」, end up in there. If they get taken out and then
    vanish on length, making them removable meant nothing.

    Misrecognized noise comes out as words that are not on the list, so this loophole
    does not widen. The test matches the shape of is_noise (compare with symbols
    stripped, and treat a repeat like 「了解、了解」 the same way).
    """
    off = {w.strip().strip(_TRIM).lower() for w in allow}
    off.discard("")
    if not off:
        return False
    core = text.strip().strip(_TRIM).lower()
    if not core:
        return False
    if core in off:
        return True
    parts = [p.strip().strip(_TRIM).lower()
             for p in re.split(r"[、。,.\s]+", core) if p.strip(_TRIM)]
    return bool(parts) and all(p in off for p in parts)


# ── Words for the voice commands ─────────────────
#
# The command words are gathered here in one place. Scattered around, both putting
# the list on screen and adding a language would mean hunting through the file.
#
# They are split by language because translating is not enough. English for 「ミュート」
# may well be mute, but the phrasing that actually comes out of a mouth in that
# language does not turn up in a dictionary. Adding a language just means adding a
# column, and existing columns are never deleted (someone speaking English and
# someone speaking Japanese talk to the same machine).
#
# Command words are short, so they are checked before the minimum length and the
# backchannel test. A false hit leaves you talking with nothing getting through, so
# it only counts when that phrase alone was spoken (no partial matches).
#
# Commands work in any language. **They follow neither the recognition language nor
# the screen language.** Some people leave the screen in Spanish and speak Japanese,
# some say 「ミュート」 to an English screen. Narrowing by either one would silently
# kill those people's commands. The screen language narrows only the "?" list, which
# is the one place that answers "what do I say" with a single answer, so it shows the
# ones in a language the reader can read (command_catalog).
#
# **Everything but Japanese and English is a draft.** No speaker of those languages
# has looked it over yet. The list on screen says so too (cmdDraft in viewer.html).
COMMAND_WORDS = {
    # Turn the mic off.
    # Recognition keeps running while it is off (it records but does not send), so
    # the unmute command still gets through. Browser recognition lets go of the audio
    # when it is turned off, so voice cannot bring it back.
    "mute": {
        # The order is for the screen. Matching uses a set so order means nothing
        # there, but the list only shows the first few, so similar phrasings are not
        # bunched at the front (six variants of 「ミュート」 in a row would not get
        # across that there are other ways to turn the mic off). Forms that came out
        # garbled (「みゅーと」 and such) go to the back, nobody says them on purpose.
        "ja": [
            "ミュート", "ミュートして", "ミュートオン",
            "マイクオフ", "マイクを切って", "マイクを切る",
            "みゅーと", "ミュートしてください", "ミュートお願い",
            "ミュートオンにして", "ミュートします",
            "マイクをオフ", "マイクをオフにして", "マイク切って", "マイク切る",
        ],
        "en": [
            "mute", "mute me", "mute the mic", "mic off",
            "turn off the mic", "turn the mic off",
        ],
        # Words aimed at people in the room, like "silencio" or "silence", are left
        # out. Only phrasings aimed at a machine go in (infinitives, button wording).
        "es": [
            "silenciar", "silenciar el micro", "silenciar el micrófono",
            "apagar el micro", "apagar el micrófono",
        ],
        "fr": [
            "couper le micro", "couper le microphone", "coupe le micro",
            "micro off", "mode muet",
        ],
        # German is written capitalized. Matching still hits because command_key
        # folds the case, and the list on screen shows the form as written.
        "de": [
            "Mikro aus", "Mikrofon aus", "Stumm", "Stummschalten",
            "Mikrofon ausschalten",
        ],
        "zh": [
            "静音", "开启静音", "关闭麦克风", "关掉麦克风", "麦克风静音",
        ],
        # Forms said to a person, like 「마이크 꺼」, are left out. Noun forms only.
        "ko": [
            "음소거", "음소거 켜기", "마이크 끄기", "마이크 음소거",
        ],
    },
    # Turn the mic on.
    # Unmute words are limited to **things you would only ever say to this tool**. The
    # mic is usually off because of a call or someone sitting with you, so putting in
    # ordinary words like 「戻して」 or 「再開」 means one sentence meant for a person
    # opens the mic, and the conversation after that starts flowing out as instructions.
    # A false hit costs not one utterance but the whole stretch you thought was muted.
    "unmute": {
        "ja": [
            "ミュート解除", "ミュート解除して", "アンミュート", "解除",
            "マイクオン", "マイクを入れて",
            "ミュートかいじょ", "ミュート解除してください",
            "ミュートを解除", "ミュートを解除して", "ミュートオフ", "ミュートオフにして",
            "あんみゅーと", "かいじょ", "解除して", "かいじょして",
            "マイクをオン", "マイクをオンにして", "マイクをつけて", "マイク付けて",
            "マイク入れて",
        ],
        "en": [
            "unmute", "unmute me", "unmute the mic", "mic on",
            "turn on the mic", "turn the mic on",
        ],
        # This is the one place where the bar for adding a language is set higher.
        # Anything that means 「マイクを入れて」 is also a sentence you say to the
        # person on a call, and opening on that word costs not one utterance but the
        # whole stretch you thought was muted.
        #
        # What is in here is only forms that are not a second-person imperative.
        # Infinitives (activar / réactiver / einschalten) and the noun forms written
        # on a button (解除静音 / 음소거 해제) are things almost nobody says straight
        # at a person. Forms that ask someone to do it, like 「enciende el micro」,
        # 「마이크 켜줘」 or 「打开麦克风」, are not in here.
        "es": [
            "quitar silencio", "quitar el silencio", "dejar de silenciar",
            "activar el micro", "activar el micrófono", "reactivar el micro",
        ],
        "fr": [
            "réactiver le micro", "réactiver le microphone",
            "rouvrir le micro", "activer le micro", "micro on",
        ],
        "de": [
            "Stummschaltung aufheben", "Stumm aus", "Mikrofon einschalten",
            "Mikro einschalten", "Mikrofon an",
        ],
        # Chinese and Korean are held to the wording on a button, nothing more.
        # What people actually say on an everyday call has not been checked, so
        # widening can wait until someone really uses them.
        "zh": ["解除静音", "取消静音"],
        "ko": ["음소거 해제", "음소거 풀기"],
    },
    # Back to the side where speech goes straight through. Switching between live and
    # hold can be done by voice too. Both are words you would only ever say to this
    # tool, so a phrase said alone can be taken as a command.
    "live": {
        "ja": [
            "即時", "即時にして", "即時モード", "即時に戻して",
            "そのまま送る", "そのまま送って",
            "そくじ", "そくじもーど", "即時に",
            # 「そくじ」 easily becomes 「食事」 (measured). Alone, same command.
            "食事", "しょくじ", "食事モード", "速時", "則時",
        ],
        "en": ["live", "live mode", "instant", "instant mode", "send live"],
        "es": ["directo", "modo directo", "en directo", "enviar directo"],
        "fr": ["direct", "mode direct", "en direct", "envoi direct"],
        # 「Sofort」 and 「Direkt」 are not in on their own because both come straight
        # out of a mouth as a reply (「Sofort.」 means "right away").
        "de": ["Sofortmodus", "Direktmodus", "Direkt senden", "Sofort senden"],
        "zh": ["即时模式", "直接发送", "实时发送", "立刻发送"],
        "ko": ["바로 전달", "바로 보내기", "즉시 모드", "바로 전달 모드"],
    },
    # Send it over to the side that piles up for editing.
    "hold": {
        "ja": [
            "手直し", "手直しにして", "手直しモード", "手直しに回して", "溜めて", "保留",
            "てなおし", "てなおしもーど", "手直しに", "ためて", "溜める", "ためる",
        ],
        "en": ["hold", "hold mode", "draft", "draft mode"],
        # Verbs you would plausibly say straight out as an instruction to Claude,
        # like 「guardar」, 「Prüfen」 or 「存下来」, are left out.
        "es": ["revisar", "modo revisar", "modo revisión", "borrador",
               "modo borrador"],
        "fr": ["relecture", "mode relecture", "brouillon", "mode brouillon"],
        "de": ["Entwurf", "Entwurfsmodus", "Sammelmodus", "Zum Ändern sammeln"],
        "zh": ["草稿模式", "暂存模式", "先存着改", "改完再发"],
        "ko": ["모아 두기", "초안 모드", "모으기 모드", "고쳐서 보내기"],
    },
    # After finishing a sentence you sometimes think 「やっぱりなし」 or "I want to
    # fix this before it goes". When the command lands at the **end** of an utterance,
    # that sentence is treated that way. One that turns up mid-sentence stays an
    # ordinary word (people do just talk about the commands).
    #
    # The words are kept few. Put in phrasings that also end an ordinary sentence,
    # like 「やめて」 or 「なし」, and instructions you meant to send get taken too.
    #
    # **A word has to clear that bar in every language, not just the column it sits
    # in.** Matching never narrows by language (the head of this table says why), so a
    # word that closes no Japanese sentence still eats every Chinese one it happens to
    # close. 「取消」 sat in the Japanese column and took 「把会议取消」 whole, and the
    # speaker never got that sentence back.
    #
    # The order matters. Matching runs from the tail and strips the first hit, so they
    # are checked in written order (so a long phrasing is not eaten by a short one).
    "cancel_tail": {
        # Single-verb forms (cancel / cancelar / annuler / abbrechen / 取消 / 취소)
        # are in no column. This command matches the end of a sentence, so an ordinary
        # instruction closing on that verb (「これはキャンセルしたい」, "I want to
        # cancel") would vanish whole. Only forms that read as "I do not want this"
        # go in. 「キャンセル」 stays because a bare katakana noun almost never closes a
        # Japanese sentence, and "cancel that" because the trailing "that" points back
        # at what was just said.
        "ja": [
            "キャンセル", "きゃんせる", "キャンセルで", "キャンセルして",
            "取り消し", "取り消して", "とりけし", "とりけして",
            "なかったことに", "なかったことにして", "やっぱなし", "やっぱりなし",
        ],
        "en": ["cancel that", "scratch that", "never mind", "nevermind"],
        "es": ["cancela eso", "cancelar eso", "olvida eso", "olvídalo"],
        "fr": ["annule ça", "annuler ça", "oublie ça"],
        "de": ["streich das", "vergiss das", "vergiss es"],
        "zh": ["刚才那句取消", "取消刚才那句", "取消这句", "这句不要了"],
        "ko": ["방금 말 취소", "방금 건 취소", "지금 말 취소", "이건 취소"],
    },
    # This one is not thrown away, it goes to the draft on screen (fix it, then send)
    "hold_tail": {
        "ja": [
            "手直し", "てなおし", "手直しで", "手直しして", "手直ししたい",
            # 「てなおし」 easily comes out as 「出直し」 (measured)
            "出直し", "でなおし", "出直して",
            "直してから", "なおしてから", "あとで直す", "ちょっと直す",
        ],
        "en": ["edit this", "let me edit", "hold this"],
        # Bare "edit" is in no column either, for the same reason as bare "cancel".
        # "please edit" reached the draft as the single word "please" and the rest of
        # the instruction was gone. Every form kept carries something after the verb,
        # and that trailing part is what marks it as spoken at this tool.
        #
        # Forms that trail an object, like 「à corriger」 or 「para editar」, are left
        # out. A sentence meaning "the list to fix" would vanish as it stands. Use the
        # forms that say the speaker will do the fixing.
        "es": ["déjame editarlo", "lo edito yo", "quiero editarlo"],
        "fr": ["je corrige", "je le corrige", "laisse-moi corriger"],
        "de": ["das ändere ich", "lass mich das ändern"],
        "zh": ["这句我来改", "这句留着改", "先留着改"],
        "ko": ["고쳐서 보낼게", "내가 고칠게", "이건 고쳐서"],
    },
}

# The order they line up in on screen. Routing is a pattern rather than a word
# table, so it is shown through the examples below.
COMMAND_KINDS = ("mute", "unmute", "live", "hold", "route",
                 "cancel_tail", "hold_tail")


def builtin_words(kind: str, lang: str = None) -> list:
    """Return the built-in phrasings. Pass lang to get just that language.

    With no language, everything is joined in written order. Commands work in
    whatever language they are said, so this is the one matching uses. Narrowing by
    the reader's language happens only for the list on screen.
    """
    langs = COMMAND_WORDS.get(kind) or {}
    if lang is not None:
        return list(langs.get(lang) or [])
    out = []
    for words in langs.values():
        out.extend(words)
    return out


# Compare after dropping symbols and the spaces in between. 「ミュート。」, 「mute me」
# and 「マイク、オン」 should all land on the same key. Full-width digits fold to
# half-width here. The long vowel mark ー is not dropped. Drop it and 「ミュート」
# becomes 「ミュト」 and never matches.
_CMD_DROP = str.maketrans("１２３４５６７８９０", "1234567890",
                          " \t\u3000。、．，・…！？!?.,-~〜\"'「」『』()（）")


def command_key(text: str) -> str:
    """The shape used when comparing commands. Symbols and the spaces in between are
    dropped and the text is lowercased.

    Phrasings the user adds are remembered in this same shape. Remember them without
    going through here and a word registered with a comma in it, like 「ミュート、して」,
    will never match.
    """
    return text.strip().translate(_CMD_DROP).lower()


# Folded into the shape matching uses.
#
# Commands said on their own become a set of keys with spaces and symbols dropped.
# The table above keeps them written readably as 「mute the mic」 and the folding
# happens here. Write 「mutethemic」 in the table and the list on screen shows exactly
# that, and the English becomes unreadable.
#
# Commands that attach to the end of a sentence are not folded. Those are compared
# raw against the tail of an utterance (「cancel that」 is needed with its space), so
# they stay a tuple in written order. The order they are matched in matters too.
MUTE_WORDS = {command_key(w) for w in builtin_words("mute")}
UNMUTE_WORDS = {command_key(w) for w in builtin_words("unmute")}
LIVE_WORDS = {command_key(w) for w in builtin_words("live")}
HOLD_WORDS = {command_key(w) for w in builtin_words("hold")}
CANCEL_TAIL = tuple(builtin_words("cancel_tail"))
HOLD_TAIL = tuple(builtin_words("hold_tail"))


# ── Phrasings the user adds ────────────────────
#
# Same style as the dictionary, it lives in the config dir and the daemon re-reads
# it, so no restart is needed. It stays out of the dictionary itself because
# rewriting a misrecognition and adding a command for the machine are separate
# matters. Lined up on one screen, even the person who wrote 「ミュート解除」 could no
# longer tell whether that line was a rewrite or an added command.
COMMANDS_FILE = CONFIG_DIR / "commands.json"

# What can be added is limited to commands that work when that phrase alone is said.
#
# unmute is left out because the cost of a false hit does not balance. The mic is
# usually off because of a call, so if a sentence meant for the other person opens
# the mic, the whole conversation after it flows out as instructions. What is lost is
# not one utterance but the whole stretch you thought was muted.
#
# Commands that attach to the end of a sentence (cancel_tail / hold_tail) are left
# out too. Those match the **end** of an ordinary sentence, so adding a common
# phrasing makes instructions you never meant to lose disappear. Same reason the
# built-in words are kept few.
USER_COMMAND_KINDS = ("mute", "live", "hold", "route")
ROUTE_SLOT = "{n}"           # Where the number goes in a routing phrase
_USER_PHRASE_MAX = 24        # Matches the length route_command looks at
_USER_PHRASE_MIN = 2         # One character cannot be told apart from ordinary speech
_USER_PHRASE_LIMIT = 50      # Per kind. Growing without limit only grows false hits


def clean_user_phrase(kind: str, phrase) -> str:
    """Turn an added phrasing into a usable shape. Empty when it is not usable.

    Both the screen and the daemon go through here. Reject in only one of them and
    you get words the screen accepted that do nothing, which reads as "I registered
    it and it does not work".
    """
    if kind not in USER_COMMAND_KINDS or not isinstance(phrase, str):
        return ""
    key = command_key(phrase)
    slots = key.count(ROUTE_SLOT)
    if kind == "route":
        if slots != 1:       # Exactly one slot for the number is required
            return ""
    elif slots:              # No number goes into the other commands
        return ""
    bare = key.replace(ROUTE_SLOT, "")
    if not _USER_PHRASE_MIN <= len(bare) <= _USER_PHRASE_MAX:
        return ""
    return key


def _clean_phrase_list(data: dict, kind: str) -> list:
    """Take one kind's phrasings and lay them out in the remembered shape."""
    raw = data.get(kind) or []
    out = []
    for p in raw if isinstance(raw, list) else []:
        k = clean_user_phrase(kind, p)
        if k and k not in out:
            out.append(k)
    return out[:_USER_PHRASE_LIMIT]


_NO_COMMANDS = {"mute": frozenset(), "live": frozenset(), "hold": frozenset(),
                "route": ()}
_cmd_cache = (None, None)   # (mtime, contents)


def load_commands() -> dict:
    """Return the phrasings the user added.

    This is called for every utterance, so it re-reads only when the mtime changed.
    Same build as the dictionary, so what is added on screen works without a daemon
    restart.
    """
    global _cmd_cache
    try:
        mtime = COMMANDS_FILE.stat().st_mtime
    except OSError:
        return _NO_COMMANDS
    if _cmd_cache[0] == mtime:
        return _cmd_cache[1]
    try:
        data = json.loads(COMMANDS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError) as e:
        print(f"{COMMANDS_FILE.name} を読めませんでした ({e})。無視します",
              file=sys.stderr)
        _cmd_cache = (mtime, _NO_COMMANDS)
        return _NO_COMMANDS
    if not isinstance(data, dict):
        _cmd_cache = (mtime, _NO_COMMANDS)
        return _NO_COMMANDS

    out = {}
    for kind in USER_COMMAND_KINDS:
        keys = _clean_phrase_list(data, kind)
        out[kind] = (tuple(_route_rx(k) for k in keys) if kind == "route"
                     else frozenset(keys))
    _cmd_cache = (mtime, out)
    return out


def clean_user_commands(data) -> dict:
    """Take the whole set as received, put it in the remembered shape and sort it by kind.

    Saving from the screen goes through here too. Tidy in only one place and the shape
    the screen holds drifts from the shape the daemon reads, which makes words that
    were registered but do nothing.
    """
    if not isinstance(data, dict):
        data = {}
    return {kind: _clean_phrase_list(data, kind) for kind in USER_COMMAND_KINDS}


def user_command_phrases() -> dict:
    """Return the phrasings remembered right now, by kind (for handing to the screen)."""
    try:
        data = json.loads(COMMANDS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError):
        data = {}
    return clean_user_commands(data)


def voice_command(text: str, muted: bool):
    """Return "mute" / "unmute" when the utterance itself is an on or off command.

    Only the side that means something in the current state is checked. 「ミュート」
    while already off and 「ミュート解除」 while already on both do nothing. Half as
    many words to check means half as many false hits.
    """
    key = command_key(text)
    if not key:
        return None
    if muted:
        # Added unmute phrasings are not checked (they cannot be added anyway)
        return "unmute" if key in UNMUTE_WORDS else None
    return "mute" if key in MUTE_WORDS or key in load_commands()["mute"] else None


# How a number is said drifts with every recognition. Say 「2」 and out comes 「に」,
# 「ツー」 or 「二」, and 「送信先に」 can mean 「送信先2」. All the readings are listed
# so any of them gets picked up. A single hiragana (に, し, ご, く) cannot be told
# apart from a particle, so it does nothing on its own. Every pattern below demands
# the shape 「番」, 「送信先」 or 「〜に切り替え」.
#
# Nothing from 11 up is held. Eleven sessions listening at once is not going to
# happen, and every one added only raises the risk of eating ordinary speech.
NUMBER_WORDS = {
    # Arabic digits come out in the same shape whatever language is spoken
    "any": {"0": 0, "1": 1, "2": 2, "3": 3, "4": 4, "5": 5,
            "6": 6, "7": 7, "8": 8, "9": 9, "10": 10},
    "ja": {
        "〇": 0, "ぜろ": 0, "れい": 0, "ゼロ": 0,
        "一": 1, "いち": 1, "ワン": 1, "わん": 1,
        "二": 2, "に": 2, "ツー": 2, "つー": 2, "トゥー": 2, "とぅー": 2,
        "三": 3, "さん": 3, "スリー": 3, "すりー": 3,
        "四": 4, "よん": 4, "し": 4, "フォー": 4, "ふぉー": 4,
        "五": 5, "ご": 5, "ファイブ": 5, "ふぁいぶ": 5,
        "六": 6, "ろく": 6, "シックス": 6, "しっくす": 6,
        "七": 7, "なな": 7, "しち": 7, "セブン": 7, "せぶん": 7,
        "八": 8, "はち": 8, "エイト": 8, "えいと": 8,
        "九": 9, "きゅう": 9, "く": 9, "ナイン": 9, "ないん": 9,
        "十": 10, "じゅう": 10, "テン": 10, "てん": 10,
    },
    "en": {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
           "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10},
    "es": {"cero": 0, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4,
           "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9,
           "diez": 10},
    # Spelling drift (zéro and zero) is held both ways. Recognition never settles.
    "fr": {"zéro": 0, "zero": 0, "un": 1, "une": 1, "deux": 2, "trois": 3,
           "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8, "neuf": 9,
           "dix": 10},
    "de": {"null": 0, "eins": 1, "zwei": 2, "drei": 3, "vier": 4, "fünf": 5,
           "funf": 5, "sechs": 6, "sieben": 7, "acht": 8, "neun": 9,
           "zehn": 10},
    "zh": {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
           "六": 6, "七": 7, "八": 8, "九": 9, "十": 10},
    # Korean readings (일 이 삼 and so on) are not listed. 「이번」 is an everyday
    # word meaning "this time", so reading it as number 2 would turn ordinary talk
    # into a routing switch. Only digits get picked up (「2번」 goes through
    # ROUTE_PARTS below).
}
# Native Japanese readings that stand only in front of the 「ひとつ目」 shape. Words
# put here read as a number only when 「つ目」 follows. Mixed into the table above,
# 「いつに変更」 would become a switch to number 5 (「いつ」 is 5). Narrowing where
# they can read as a number is what prevents it.
NUMBER_WORDS_ORDINAL = {
    "ja": {"ひと": 1, "ふた": 2, "みっ": 3, "よっ": 4, "いつ": 5,
           "むっ": 6, "やっ": 8, "ここの": 9},
}

# The parts a routing phrase is built from. Unlike the number itself, the words around
# it change shape by language (Japanese puts a counter after, English a lead-in only).
ROUTE_PARTS = {
    "ja": {
        # In front of the number. 「送信先2」 「セッション2」 「ナンバー2」 「番号2」
        "prefix": ["送信先", "宛先", "あて先", "セッション", "せっしょん",
                   "ナンバー", "なんばー", "番号", "ばんごう"],
        # Words after the number. 「2番」 「1番目」
        "counter": ["番目", "ばんめ", "番", "ばん"],
        # The 「1つ目」 shape. The only place a native reading (ひとつ目) can stand
        "ordinal": ["つ目", "つめ"],
    },
    "en": {
        # 「switch to 2」 「number one」. English is settled by the leading word alone.
        # This compares against the folded key (spaces dropped), so it is written
        # without spaces.
        "prefix": ["switchto", "sendto", "routeto", "goto", "target",
                   "session", "destination", "route", "number"],
    },
    # The rest also compares against the folded key, so it is written without spaces.
    # Symbols drop out but accents (é à ü) do not, so both the form recognition puts
    # them on and the form without them are held.
    "es": {
        "prefix": ["sesión", "sesion", "destino", "número", "numero",
                   "objetivo", "cambiaa", "cambiara", "vea", "envíaa",
                   "enviaa", "mandaa", "pasaa"],
    },
    "fr": {
        "prefix": ["session", "destination", "cible", "numéro", "numero",
                   "passeà", "passea", "passerà", "passera", "basculevers",
                   "envoieà", "envoiea", "vaà", "vaa"],
    },
    "de": {
        "prefix": ["sitzung", "ziel", "nummer", "wechslezu", "wechselzu",
                   "gehzu", "sendean", "sendezu", "schaltezu"],
    },
    "zh": {
        # 「切换到2」 「会话2」 「第2个」. Shapes made only of a word after the number
        # (「一个」 「十号」) are not held. Both come out as ordinary words.
        "prefix": ["切换到", "切换成", "切到", "换到", "发送到", "发到",
                   "发给", "会话", "目标", "第"],
        "tail": ["个", "号", "会话", "吧"],
    },
    "ko": {
        # 「2번」 「세션 2」 「2번으로 보내」. There are no number readings, so a number
        # goes through only when it arrives as Arabic digits (see the Korean column
        # in NUMBER_WORDS).
        "prefix": ["세션", "대상", "목적지", "번호"],
        "counter": ["번", "번째"],
        "tail": ["으로", "로", "으로보내", "로보내", "으로보내줘", "로보내줘",
                 "으로바꿔", "로바꿔", "보내줘", "보내"],
    },
}

# Representative examples for the list on screen. Routing alone is a pattern rather
# than a word table, so lining up the built-in words as they are does not tell a
# reader what to say. That the ones written here really work has been checked one by
# one in testing.
ROUTE_EXAMPLES = {
    "ja": ["2番", "2番目", "2つ目", "送信先を2", "セッション2", "ナンバー2",
           "2に切り替え"],
    "en": ["switch to 2", "session 2", "number two", "send to 2"],
    "es": ["sesión 2", "número dos", "cambia a 2", "destino 2"],
    "fr": ["session 2", "numéro deux", "passe à 2", "destination 2"],
    "de": ["Sitzung 2", "Nummer zwei", "wechsle zu 2", "Ziel 2"],
    "zh": ["切换到2", "会话2", "第2个", "发送到2"],
    "ko": ["2번", "세션 2", "2번으로 보내", "번호 2"],
}

_NUM_WORDS = {w: n for tbl in NUMBER_WORDS.values() for w, n in tbl.items()}
# Lookup table with the readings that count as a number only before 「つ目」 added in
_NUM_LOOKUP = dict(_NUM_WORDS)
for _tbl in NUMBER_WORDS_ORDINAL.values():
    _NUM_LOOKUP.update(_tbl)


def _alt(words) -> str:
    """Longest first, so 「じゅう」 is not broken up into 「じ」 「ゅ」 and so on."""
    return "(?:" + "|".join(
        sorted((re.escape(w) for w in words), key=len, reverse=True)) + ")"


_NUM_ALT = _alt(_NUM_WORDS)
_NUM_ORDINAL_ALT = _alt(_NUM_LOOKUP)
_COUNTER = _alt(ROUTE_PARTS["ja"]["counter"])
_ORDINAL = _alt(ROUTE_PARTS["ja"]["ordinal"])
# When a phrasing just barely misses, it falls short of min_chars (15 characters by
# default) and vanishes without a word. "Neither a command nor a prompt" is the worst
# outcome of all, so the sentence endings are taken generously.
_VERB_CORE = (r"(?:切り替え|切替|きりかえ|変更|へんこう|送る|おくる|送って|おくって|"
              r"送信|そうしん|して|お願い|おねがい|頼む|たのむ|"
              r"switchto|sendto|goto)")
_TAIL = r"(?:て|る|して|ください|下さい|お願い|おねがい|します|ます|ましょう|な|ね)*"
_VERB = rf"(?:{_VERB_CORE}{_TAIL})"
_PREFIX = _alt(ROUTE_PARTS["ja"]["prefix"])
_PREFIX_EN = _alt(ROUTE_PARTS["en"]["prefix"])
_PART = r"(?:に|へ|で)?"

_ROUTE_RXS = [re.compile(rx) for rx in (
    # 送信先2 / 送信先を2に / セッション2に切り替えて / セッショントゥー
    # 「送信先に」 is in too (に is 2). A 「送信先に」 with no number is not language.
    rf"^{_PREFIX}を?({_NUM_ALT}){_COUNTER}?{_PART}{_VERB}?$",
    # 2番 / 1番目 / 2番にして / 2番でお願い (a number at the front is recognized more easily)
    rf"^({_NUM_ALT}){_COUNTER}{_PART}{_VERB}?$",
    # 1つ目 / 一つ目 / ひとつ目 / 3つ目に切り替え
    # Native readings (ひと, ふた and so on) pass as a number only inside this pattern.
    rf"^({_NUM_ORDINAL_ALT}){_ORDINAL}{_PART}{_VERB}?$",
    # 2に切り替え / 2へ送って (a verb is always required after the number)
    rf"^({_NUM_ALT})(?:に|へ){_VERB}$",
    # switch to 2 / session two / route 3 / number one
    rf"^{_PREFIX_EN}(?:session)?({_NUM_ALT})$",
)]


def _lang_num_alt(lang: str) -> str:
    """An alternation drawing only that language's number readings and Arabic digits.

    The tables are not all mixed together because when another language's reading
    collides with an everyday word, every extra pattern being matched just widens the
    false hits.
    """
    words = dict(NUMBER_WORDS["any"])
    words.update(NUMBER_WORDS.get(lang) or {})
    return _alt(words)


def _route_patterns(lang: str, parts: dict) -> list:
    """Build the patterns for an added language out of the parts.

    Only two things are checked, a leading word plus a number, and a number plus a
    trailing word. Shapes that pile on particles and endings the way Japanese does
    differ from language to language, so folding them into one pattern makes it
    unreadable. Widening can wait until someone actually uses that language.
    """
    num = _lang_num_alt(lang)
    tail = f"{_alt(parts['tail'])}?" if parts.get("tail") else ""
    counter = _alt(parts["counter"]) if parts.get("counter") else ""
    out = []
    if parts.get("prefix"):
        opt = f"{counter}?" if counter else ""
        out.append(rf"^{_alt(parts['prefix'])}({num}){opt}{tail}$")
    if counter:
        out.append(rf"^({num}){counter}{tail}$")
    return out


# The Japanese and English patterns are left as they are above. Touch them and
# phrasings that work today quietly stop working. Added languages are appended here
# at the back.
_ROUTE_RXS += [re.compile(rx)
               for lang, parts in ROUTE_PARTS.items() if lang not in ("ja", "en")
               for rx in _route_patterns(lang, parts)]


def _route_rx(key: str):
    """Build a pattern that pulls the number out of an added phrasing. {n} marks its spot."""
    head, _, tail = key.partition(ROUTE_SLOT)
    return re.compile(rf"^{re.escape(head)}({_NUM_ALT}){re.escape(tail)}$")


def mode_command(text: str):
    """Return "live" / "hold" when this is a command to switch how speech gets sent."""
    key = command_key(text)
    if not key:
        return None
    user = load_commands()
    if key in LIVE_WORDS or key in user["live"]:
        return "live"
    return "hold" if key in HOLD_WORDS or key in user["hold"] else None


def route_command(text: str):
    """Return the number when this command chooses a target (the first on screen is 1)."""
    key = command_key(text)
    if not key or len(key) > 24:      # Commands are all short. No need to read a long one
        return None
    for rx in _ROUTE_RXS:
        m = rx.match(key)
        if m:
            return _NUM_LOOKUP[m.group(1)]
    # Added phrasings come after the built-ins. They never override built-in behavior.
    for rx in load_commands()["route"]:
        m = rx.match(key)
        if m:
            return _NUM_WORDS[m.group(1)]
    return None


def command_catalog(lang: str = "en") -> list:
    """The list shown on screen. Only phrasings in the reader's language are laid out.

    A command with no column for that language comes out in English with fallback
    raised. The screen sees that and adds "there is no phrasing in your language yet,
    this English works as it is". Show English silently and the reader cannot tell
    whether a phrasing in their language exists and just was not read, or does not
    exist at all.

    Matching passes on words in any language, so phrasings not shown here work too.
    The list is there to give one answer to "what do I say", not to be the place that
    enumerates everything.
    """
    out = []
    for kind in COMMAND_KINDS:
        words = (ROUTE_EXAMPLES.get(lang) if kind == "route"
                 else builtin_words(kind, lang))
        fallback = not words
        if fallback:
            words = (ROUTE_EXAMPLES["en"] if kind == "route"
                     else builtin_words(kind, "en"))
        out.append({"id": kind, "phrases": list(words), "fallback": fallback,
                    "editable": kind in USER_COMMAND_KINDS})
    return out
# Some people say 「コマンド◯◯」 so it reads as a command. The lead-in is dropped.
_TAIL_PREFIX = ("コマンド", "こまんど", "command")
_TAIL_TRIM = " \t\u3000。、．，・！？!?.,"


def take_tail(text: str, tails):
    """When the tail is a command, return the body with it removed. None when it is not."""
    body = text.strip().rstrip(_TAIL_TRIM)
    low = body.lower()
    for w in tails:
        # The table side is lowercased for the comparison too. In a language that
        # capitalizes nouns, like German, comparing against the form as written in
        # the table would never match.
        if not low.endswith(w.lower()):
            continue
        rest = body[: len(body) - len(w)].rstrip(_TAIL_TRIM)
        for pre in _TAIL_PREFIX:          # The lead-in in 「〜。コマンド手直し」
            if rest.lower().endswith(pre):
                rest = rest[: len(rest) - len(pre)].rstrip(_TAIL_TRIM)
                break
        return rest
    return None


# ── Using several machines at once ───────────────
#
# With the work Windows box and this Mac both listening, saying 「ミュート」 turns
# both of them off. Give a machine a name and put it at the front, as in
# 「開発用ミュート」, and only that machine responds.
#
# A command with no name cannot be pinned to a machine, so **none of them act**. It
# is dropped silently though (something said to another machine arriving here as an
# instruction would be trouble).
_NAME_SEP = " \t\u3000、,。．，:：・のはでをへに"


def machine_config() -> tuple:
    """Return (whether multi-machine mode is on, what this machine is called).

    The name can be written any number of ways separated by commas. A name whose
    spelling drifts with every recognition, like 「Mac, マック, まっく」, can be listed
    out in full.
    """
    cfg = read_config()
    raw = cfg.get("machine_name") or ""
    names = [n.strip() for n in re.split(r"[,、]", raw) if n.strip()]
    return bool(cfg.get("multi_machine")), names


def _strip_name(text: str, names):
    """When the head is this machine's name, return the rest. None otherwise."""
    body = text.strip()
    low = body.lower()
    for name in sorted(names or [], key=len, reverse=True):
        if low.startswith(name.lower()):
            return body[len(name):].lstrip(_NAME_SEP)
    return None


def looks_like_any_command(text: str) -> bool:
    """Whether that phrase, taken whole, looks like some command."""
    t = text.strip()
    if not t:
        return False
    if (voice_command(t, False) or voice_command(t, True)
            or mode_command(t) or route_command(t)):
        return True
    # A tail command that arrived on its own (no body, just 「キャンセル」)
    return any(take_tail(t, tails) == "" for tails in (CANCEL_TAIL, HOLD_TAIL))


# When a tail command (「〜、手直し」 「〜、キャンセル」) carries a body at least this
# long, it is the close of a dictation, not a command aimed at another machine.
_TAIL_BODY_MIN = 5


def looks_like_other_command(text: str) -> bool:
    """Whether this looks like a command said to another machine.

    There is no way to know what the other one is called, so this shaves the head off
    bit by bit and watches for a command shape to appear. Short phrases only (a long
    sentence whose tail happens to match a command shape is not picked up).
    """
    t = text.strip()
    if not t or len(t) > 24:
        return False
    # The close of a dictation like 「認証まわりを直して、手直し」 is a command, but
    # one aimed at this machine. It is the kind that needs no name, so it is not
    # dropped here.
    for tails in (CANCEL_TAIL, HOLD_TAIL):
        body = take_tail(t, tails)
        if body and len(body) >= _TAIL_BODY_MIN:
            return False
    return any(looks_like_any_command(t[i:].lstrip(_NAME_SEP))
               for i in range(min(len(t), 11)))


def apply_voice_command(text: str, log_path, muted: bool, user_dict=None):
    """Run the command when the utterance is one and return its kind. None when it is not.

    Both the daemon (a local model) and the viewer (browser recognition) go through
    here. Present in only one of them, a command would work or not work depending on
    how recognition is being done.
    """
    log_path = Path(log_path)
    d = log_path.parent
    mute_path = d / MUTE_FILE.name
    pause_path = d / PAUSE_FILE.name
    if user_dict is None:
        user_dict = load_dictionary()

    # With several machines at once, only what carries this machine's name at the front.
    multi, names = machine_config()
    cmd_text = text
    if multi:
        named = _strip_name(text, names)
        if named is not None:
            cmd_text = named
        elif looks_like_other_command(text):
            return "other_machine"       # Said to another machine. Drop it silently
        else:
            cmd_text = ""                # A command with no name moves nothing
    if not cmd_text:
        return None

    # The dictionary-applied form is checked too. A word that comes through garbled
    # can be picked up by registering it, as in 「ミュート回収 → ミュート解除」.
    fixed = apply_replacements(cmd_text, user_dict["replace"])

    cmd = voice_command(cmd_text, muted) or voice_command(fixed, muted)
    if cmd:
        if cmd == "mute":
            mute_path.touch()
        else:
            mute_path.unlink(missing_ok=True)
        note_voice_cmd(log_path, cmd, "", text)
        return cmd

    mode = mode_command(cmd_text)
    if mode:
        if mode == "hold":
            pause_path.touch()
        else:
            pause_path.unlink(missing_ok=True)
        note_voice_cmd(log_path, "mode_" + mode, "", text)
        return "mode_" + mode

    # Routing. With only one listener there is nobody to choose, so it is not taken
    # as a command (so a plain numeric answer like 「2番」 does not get eaten).
    n = route_command(cmd_text) or route_command(fixed)
    if n:
        live = list_active_listeners(log_path)
        if len(live) > 1:
            if 1 <= n <= len(live):
                write_atomic(route_file(log_path), str(live[n - 1]["pid"]))
                note_voice_cmd(log_path, "route",
                               f"{n}. {live[n - 1]['label']}", text)
                return "route"
            # A number that is not there. Dropped silently it reads as "I said it and
            # nothing changed".
            note_voice_cmd(log_path, "route_missing", str(n), text)
            return "route_missing"
    return None


def note_voice_cmd(log_path, kind: str, label: str = "", said: str = "") -> None:
    """Hand the screen what happened with a voice command.

    A command is not sent as an utterance, so the user cannot see whether it went
    through. The viewer watches this file, plays a sound and puts up a line.

    Put the utterance that was judged a command into said. Something meant as an
    instruction sometimes disappears as a command, so show what disappeared.
    """
    try:
        # Without encoding, Windows opens with the locale (cp932). One character in
        # the title that cp932 does not have and it dies with UnicodeEncodeError.
        # That is not an OSError, so what catches it is widened as well.
        (Path(log_path).parent / "voice_cmd.json").write_text(
            json.dumps({"at": time.time(), "kind": kind,
                        "label": label, "said": said[:60]},
                       ensure_ascii=False), encoding="utf-8")
    except (OSError, ValueError):
        pass


def parse_args():
    p = argparse.ArgumentParser(description="音声プロンプト常駐デーモン")
    asr_mic.add_common_args(p)
    p.add_argument("--log-file", default=str(LOG_FILE),
                   help="発話を書き出す JSONL のパス")
    p.add_argument("--strip-fillers", action="store_true",
                   help="「えーと」などのつなぎ言葉を送る前に落とす")
    p.add_argument("--min-chars", type=int, default=15,
                   help="この文字数未満の発話は無視する（相槌や雑音よけ）。"
                        "短い発話はほとんどが物音の誤認識なので厚めに切る。"
                        "ただし辞書で「無視しない」側へ回した語は、短くても通る。"
                        "本当に短く指示したいときはビューアから送る")
    p.add_argument("--keep-noise", action="store_true",
                   help="「はい」「うん」等の相槌も送る（既定では捨てる）")
    p.add_argument("--keep-kanji-numbers", action="store_true",
                   help="漢数字をそのまま送る（既定は「三十秒」→「30秒」に直す）")
    p.add_argument("--drop-non-japanese", action="store_true",
                   help="中国語・韓国語等を含む発話を捨てる（既定では送る。"
                        "意図して他言語を話すことがあるため既定は無効）")
    p.add_argument("--status", action="store_true", help="稼働状況を表示して終了")
    p.add_argument("--stop", action="store_true", help="常駐プロセスを停止して終了")
    p.add_argument("--listeners", action="store_true",
                   help="発話ログを聞いているセッションを一覧して終了")
    p.add_argument("--resolve-engine", metavar="WANT", default=None,
                   help="使うエンジンを決めて表示する（指定 > 前回 > 自動）")
    p.add_argument("--remember-engine", metavar="ENGINE", default=None,
                   help="次回もこのエンジンで起動するよう覚える")
    p.add_argument("--list-engines", action="store_true",
                   help="選べるエンジンを一覧して終了")
    # The Whisper model is remembered the same as the engine. The start button on
    # screen does not know the original command, so without remembering it, things
    # fall back to the default the moment it is brought back up.
    p.add_argument("--resolve-model", action="store_true",
                   help="覚えている Whisper のモデルを表示して終了する")
    p.add_argument("--remember-model", metavar="NAME", default=None,
                   help="次回もこのモデルで起動するよう覚える（空文字で既定に戻す）")
    return p.parse_args()


def _pid_alive(pid):
    """Check whether a process is alive without sending it a signal."""
    if sys.platform.startswith("win"):
        # os.kill(pid, 0) is unsupported on Windows (it raises SystemError).
        # Whether a handle can be taken stands in for it.
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # The PID got reused by somebody else's process. Every PID looked at here
        # was written by us, so somebody else's is not the process we are after.
        # Return True and status stays "running" forever and start never goes
        # through again (the real brake on a second instance is on the flock side).
        return False


def read_pid():
    try:
        pid = int(PID_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return None
    return pid if _pid_alive(pid) else None


def _proc_started_at(pid):
    """How many seconds since that process started. None when it cannot be told.

    PIDs get reused, so a process that started after the registration file is taken
    to be somebody else. Elapsed seconds (etime from ps) is what gets read because it
    stays simple across digit counts, unlike a start time whose format drifts between
    "MM:SS" and "DD-HH:MM:SS". Where ps is missing, None comes back and the test is
    waved through.
    """
    if sys.platform.startswith("win"):
        return None
    try:
        r = subprocess.run(["ps", "-o", "etime=", "-p", str(pid)],
                           capture_output=True, timeout=5)
        text = r.stdout.decode(errors="replace").strip()
        if not text:
            return None
        days, _, clock = text.rpartition("-")
        parts = [int(x) for x in clock.split(":")]
        while len(parts) < 3:
            parts.insert(0, 0)            # Line up "MM:SS" into "0:MM:SS" form
        secs = parts[0] * 3600 + parts[1] * 60 + parts[2]
        return secs + (int(days) * 86400 if days else 0)
    except Exception:
        return None


# The routing target. The viewer writes it, the daemon reads it every time.
#   no file        … nothing chosen yet (goes to whichever started later)
#   <PID>          … to that one
# "everyone" cannot be chosen. Two sessions taking the same instruction and setting
# off in different directions had no use, and picking it by mistake was only hard to
# notice.
def route_file(log_path):
    return Path(log_path).parent / "route"


def write_atomic(path, text: str) -> None:
    """Write under another name, then replace.

    Read in between the truncate and the write and what gets handed over is missing
    pieces. For the routing target that reads as "no matching PID" and one utterance
    goes to a different listener.
    """
    tmp = Path(path).with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def resolve_target(log_path):
    """Decide where things go right now. None means everyone.

    The default is whichever started later, since starting another job alongside
    naturally turns attention that way. Deciding it here is what makes it **work even
    with no screen open** (this used to live only on the screen side, and with it
    closed everything arrived twice, to everyone).
    """
    try:
        raw = route_file(log_path).read_text(encoding="utf-8").strip()
    except OSError:
        raw = ""

    # The chosen listener is judged purely by whether its registration file exists.
    # The liveness sweep sometimes miscounts for a moment, and rerouting on every one
    # of those slips utterances to a listener nobody chose (not arriving is safer).
    if raw and (listeners_dir(log_path) / raw).exists():
        return raw

    # Nothing chosen yet, or the chosen listener exited. The default is whichever
    # just started, so the pick uses the re-registration time rather than the display
    # order (first_seen). With only one listener there is no point writing a target.
    live = list_active_listeners(log_path)
    if len(live) <= 1:
        return None
    return str(max(live, key=lambda e: e.get("since", 0))["pid"])


# ── Listener names ─────────────────────────
#
# At startup the work has no shape yet, so the folder name comes first. Once the
# agent gives the conversation a title, it switches to that. Where the title lives
# differs from tool to tool, so the ways of finding it are lined up and tried from
# the top. For a tool none of them hit, the environment variable (VOICE_SHELL_NAME)
# and `voice-shell.sh name` are still there.

_title_cache = {}      # path -> (mtime, title)


def _claude_title(session_id):
    """The title Claude Code gave it. Updated as the conversation goes on."""
    import glob
    hits = glob.glob(str(Path.home() / ".claude/projects/*" / f"{session_id}.jsonl"))
    if not hits:
        return None
    path = hits[0]
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    hit = _title_cache.get(path)
    if hit and hit[0] == mtime:
        return hit[1]

    title = None
    try:
        with open(path, errors="replace") as f:
            for line in f:
                # Parsing every line as JSON is heavy. Only look at marked lines.
                if '"ai-title"' not in line:
                    continue
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if d.get("type") == "ai-title" and d.get("aiTitle"):
                    title = d["aiTitle"]
    except OSError:
        return None
    _title_cache[path] = (mtime, title)
    return title


def _codex_title(session_id):
    """The title Codex gave it (thread_name)."""
    path = Path.home() / ".codex" / "session_index.jsonl"
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    key = f"{path}:{session_id}"
    hit = _title_cache.get(key)
    if hit and hit[0] == mtime:
        return hit[1]

    title = None
    try:
        for line in path.read_text(errors="replace").splitlines():
            if session_id not in line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("id") == session_id and d.get("thread_name"):
                title = d["thread_name"]
    except OSError:
        return None
    _title_cache[key] = (mtime, title)
    return title


def saved_names() -> dict:
    """Names set with `voice-shell.sh name` (conversation id to display name)."""
    try:
        return json.loads((CONFIG_DIR / "names.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def listener_title(entry):
    """What to call that listener right now. None falls back to the folder name."""
    if entry.get("name"):
        return entry["name"]              # A hand-set name wins over everything
    sid, agent = entry.get("session"), entry.get("agent")
    if not sid:
        return None
    # Voice mode off and on rebuilds the registration file, so check the config too
    named = saved_names().get(sid)
    if named:
        return named
    if agent == "claude":
        return _claude_title(sid)
    if agent == "codex":
        return _codex_title(sid)
    return None


def label_listeners(entries):
    """Decide the display names. When the same name lines up more than once, the
    duplicates get (2), (3) and so on, counted in order of earliness.

    The order is when that conversation first started listening. Order by the
    re-registration time and the numbers shift every time voice mode goes off and on,
    which makes the number you say out loud unreliable.
    """
    # When the times tie, the PID decides. Leave this undecided and the numbers swap
    # around with the order the registration files get read (left to the OS).
    entries = sorted(entries,
                     key=lambda e: (e.get("first_seen") or e.get("since", 0),
                                    e.get("pid", 0)))
    seen = {}
    for e in entries:
        base = listener_title(e) or os.path.basename(e.get("cwd", "")) or "?"
        n = seen.get(base, 0) + 1
        seen[base] = n
        e["label"] = base if n == 1 else f"{base} ({n})"
    return entries


def listeners_dir(log_path):
    return Path(log_path).parent / "listeners"


def list_active_listeners(log_path):
    """List the sessions listening to the utterance log.

    This does not lean on `pgrep` (Git Bash on Windows does not have it). Instead it
    looks at the file `voice-shell.sh listen` registers for itself at startup. The
    ones that are not alive get cleaned up along the way.
    """
    d = listeners_dir(log_path)
    if not d.is_dir():
        return []
    out = []
    for f in d.iterdir():
        try:
            pid = int(f.name)
        except ValueError:
            continue
        try:
            raw = f.read_text(encoding="utf-8")
        except OSError:
            raw = ""
        try:
            info = json.loads(raw)
        except ValueError:
            info = {}
        # A process that started after the registration file is somebody else who
        # merely got the recycled PID. Without this check, warnings keep getting
        # written about a session that is not there.
        stale = False
        age = _proc_started_at(pid)
        if age is not None:
            try:
                registered_ago = time.time() - f.stat().st_mtime
                stale = age < registered_ago - 5      # 5 seconds of measurement slack
            except OSError:
                stale = False
        if _pid_alive(pid) and not stale:
            info["pid"] = pid
            info.setdefault("cwd", "不明")
            info.setdefault("started", "不明")
            try:
                info.setdefault("since", f.stat().st_mtime)
            except OSError:
                info.setdefault("since", 0)
            out.append(info)
        else:
            try:
                f.unlink(missing_ok=True)   # Clear away the dead ones
            except PermissionError:
                pass                        # Somebody else's. Leave it
    return label_listeners(out)


def main():
    args = parse_args()

    if args.remember_engine is not None:
        write_config(engine=args.remember_engine)
        return

    if args.resolve_engine is not None:
        print(resolve_engine(args.resolve_engine))
        return

    if args.remember_model is not None:
        write_config(whisper_model=args.remember_model.strip())
        return

    if args.resolve_model:
        # Print nothing when nothing is remembered. The caller can decide whether
        # to add --model from whether this comes back empty.
        print(read_config().get("whisper_model") or "")
        return

    if args.list_engines:
        remembered = read_config().get("engine", "")
        have = asr_mic.available_engines()
        print("  browser   このブラウザ（何も入れずに動く）")
        for e in have:
            print(f"  {e['id']:<9} {e['label']}")
        print(f"\n  前回の選択は {remembered or '(まだ無い)'}")
        return

    if args.listeners:
        # Whether anything is printed is left to the caller (voice-shell.sh). Print
        # a fixed line here and the caller can no longer tell an empty result apart.
        for l in list_active_listeners(args.log_file):
            print(f"  {l['label']}  （PID {l['pid']}）")
            print(f"    起動した時刻  {l['started']}")
            print(f"    場所          {l['cwd']}")
        return

    if args.status:
        pid = read_pid()
        if pid:
            n = sum(1 for _ in open(args.log_file)) if Path(args.log_file).exists() else 0
            print(f"稼働中 (PID {pid}) / これまでの発話 {n} 件")
            print(f"ログは {args.log_file}")
        else:
            print("停止しています。")
        return

    if args.stop:
        pid = read_pid()
        if not pid:
            print("動いていません。")
            return
        os.kill(pid, signal.SIGTERM)
        # Wait a little for it to really end. Return right away here and the caller
        # (/api/engine in viewer.py) decides it stopped, but the process can in fact
        # still be alive for a few hundred ms up to a few seconds. If browser
        # recognition (Web Speech API) sends an utterance in that gap, it trips the
        # "do not accept while the daemon is running" test in /api/utterance, and the
        # very first utterance alone gets thrown away silently (measured).
        for _ in range(50):        # 5 seconds at most
            if not _pid_alive(pid):
                break
            time.sleep(0.1)
        print(f"停止しました (PID {pid})")
        return

    if read_pid():
        sys.exit("すでに動いています。停止するには --stop を使ってください。")

    STATE_DIR.mkdir(parents=True, exist_ok=True)

    # Reliably stop a second instance. The PID file is written only after loading
    # finishes, so during startup (about a minute) the check above slips through.
    # With two running they fight over the mic and both end up half broken. The lock
    # holds from the instant of startup, and the OS releases it even on a crash, so
    # nothing gets left behind.
    _lock = open(STATE_DIR / "daemon.lock", "w")
    try:
        _lock_exclusive_nb(_lock)
    except OSError:
        sys.exit("すでに起動しています（読み込み中かもしれません）。")
    globals()["_daemon_lock"] = _lock   # Closing it releases the lock, so keep holding on

    log_path = Path(args.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    # Emptied on every startup (so last time's utterances are not picked up)
    log_path.write_text("", encoding="utf-8")

    save_default_dictionary()

    # Check the mic the viewer specified every time (switching swaps only the recording)
    # Remember the mic picked last time. Files in /tmp vanish on reboot, so with only
    # those it would fall back to the system default every single time.
    saved_mic = read_config().get("mic")
    if saved_mic and args.device == asr_mic.DEFAULT_DEVICE:
        args.device = saved_mic
    mic_path = Path(args.log_file).parent / MIC_FILE.name
    mic_path.write_text(args.device, encoding="utf-8")

    def want_device():
        try:
            return mic_path.read_text(encoding="utf-8").strip() or None
        except OSError:
            return None

    args.want_device = want_device

    # The device name the switch actually completed on. When the viewer says it
    # switched, that is an optimistic display at the instant the button was pressed
    # and it has no idea whether the switch really happened underneath. The settled
    # information is written here, and only on seeing this file change does the
    # viewer show the settled state.
    mic_active_path = Path(args.log_file).parent / "mic_active"
    mic_active_path.write_text(args.device, encoding="utf-8")

    def on_switch(dev):
        mic_active_path.write_text(dev, encoding="utf-8")
        write_config(mic=dev)      # Use the same mic on the next startup too

    args.on_switch = on_switch

    # The discard button on screen writes the time it was pressed here, and the
    # judging is done inside the VAD loop (asr_mic), not down where the settled
    # text arrives. Judge it down there and only the words are thrown away while
    # the sound stays joined, so anything said right after the press falls inside
    # the same utterance and goes out with it, and the redo is silently eaten
    # until a pause finally settles the line.
    #
    # The file is read and left in place, the way the mic choice and the tuning
    # are, with the time inside it compared against. Deleting it here would tear
    # it out from under the loop that has to see it.
    drop_path = Path(args.log_file).parent / "drop_at"

    def want_drop():
        try:
            return float(drop_path.read_text(encoding="utf-8") or 0)
        except (OSError, ValueError):
            return 0.0      # Not there yet, or read mid-write. Seen next round

    args.want_drop = want_drop

    # Mic sensitivity and the seconds of silence before settling are reachable from
    # the viewer too. Not even a recording swap is needed, they take effect from the
    # next re-read. With no file, one is made from the current values.
    def want_tuning():
        try:
            return json.loads(TUNING_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None      # Just read mid-write. Picked up again on the next cycle

    args.want_tuning = want_tuning

    # When saved values exist, apply them from startup onward
    saved = want_tuning() or {}
    for key in ("silence_threshold", "silence_duration"):
        if isinstance(saved.get(key), (int, float)):
            setattr(args, key, float(saved[key]))
    if isinstance(saved.get("min_chars"), (int, float)):
        args.min_chars = int(saved["min_chars"])
    if isinstance(saved.get("strip_fillers"), bool):
        args.strip_fillers = saved["strip_fillers"]
    # Recognition language (Whisper only). Other engines use spellings like
    # "Japanese", so overwriting here breaks them. An empty string means auto-detect.
    if args.engine == "whisper" and isinstance(saved.get("language"), str):
        args.language = saved["language"] or None

    # Fill missing keys with the current values, so new keys reach people who
    # already have the file (left missing, the viewer's sliders do nothing).
    filled = dict(saved)
    for key in ("silence_threshold", "silence_duration", "min_chars",
                "strip_fillers"):
        filled.setdefault(key, getattr(args, key))
    if args.engine == "whisper":
        # Left as a CLI-default spelling like "Japanese", it does not match the
        # viewer's dropdown (which holds two-letter codes), so normalize it.
        import whisper_engine
        filled.setdefault("language", whisper_engine._lang_code(args.language) or "")
    if filled != saved:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        TUNING_FILE.write_text(json.dumps(filled, indent=2) + "\n", encoding="utf-8")

    # The settled information the viewer uses to know which engine is running (the
    # recognition language dropdown only shows for Whisper).
    (Path(args.log_file).parent / "engine_active").write_text(args.engine, encoding="utf-8")

    print("モデルを読み込み中… (初回は数分かかります)", file=sys.stderr)
    model = asr_mic.load_model(args)

    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    print(f"\n  聞いています。喋ると {log_path} に追記します"
          f"\n  Ctrl-C で終了\n", file=sys.stderr, flush=True)

    # Once two or more sessions are listening, write a warning into the utterance
    # log itself to tell Claude Code (the side watching this log with Monitor). A
    # session from 8 days earlier really was still listening once, and the same
    # utterance was going out to two of them. `voice-shell.sh listen` registers
    # itself at startup, so counting them is all that is needed here (no pgrep
    # required, works on Windows).
    def watch_listeners():
        last_count = None
        while True:
            time.sleep(5)
            count = len(list_active_listeners(log_path))
            # With a target chosen, nothing arrives twice even with several
            # listening. That is the intended way to use it, so stay quiet.
            # With a target settled nothing arrives twice (the default settles one too)
            routed = resolve_target(log_path) is not None
            if routed:
                last_count = count
                continue
            if count > 1 and count != last_count:
                try:
                    with open(log_path, "a", buffering=1, encoding="utf-8") as wf:
                        wf.write(json.dumps({
                            "system_warning":
                                f"モニターが{count}個同時に発話ログを聞いています。"
                                "送信先を選んでいないため、同じ発話が全部のセッションへ"
                                "二重に届きます。ビューアの送信先で1つ選ぶか、"
                                "`voice-shell.sh listeners` で確認して"
                                "使っていないものを停止してください。"
                        }, ensure_ascii=False) + "\n")
                except OSError:
                    pass
            last_count = count

    threading.Thread(target=watch_listeners, daemon=True).start()

    try:
        partial_path = log_path.parent / PARTIAL_FILE.name
        level_path = log_path.parent / LEVEL_FILE.name
        pause_path = log_path.parent / PAUSE_FILE.name
        hold_path = log_path.parent / HOLD_FILE.name
        mute_path = log_path.parent / MUTE_FILE.name
        partial_path.write_text("", encoding="utf-8")
        level_path.write_text("0 0", encoding="utf-8")
        pause_path.unlink(missing_ok=True)   # Always start from the sending state
        mute_path.unlink(missing_ok=True)
        hold_path.write_text("", encoding="utf-8")

        # Looking only at the mute state at settle time lets audio spoken while
        # muted flow in after unmuting. Count how many times it was turned off,
        # compare against the value when the utterance began, and drop utterances
        # that span a mute (with a plain flag, a noise picked up while muted consumes
        # the flag and takes the utterance right after it down with it).
        mute_generation = 0
        was_muted = False
        speaking_since = None   # The generation when the utterance in progress began

        # Stated outright so it does not disagree with the readers (the viewer and
        # Monitor). Left unspecified, Windows opens with the locale (cp932).
        with open(log_path, "a", buffering=1, encoding="utf-8") as f:
            for ev in asr_mic.stream_utterances(model, args):
                muted_now = mute_path.exists()

                if muted_now and not was_muted:
                    mute_generation += 1      # Turned off
                was_muted = muted_now

                # Catch the start of an utterance (the instant silence turns into voice)
                if ev["type"] == "level":
                    # Hand the volume to the viewer. When no text shows up, we
                    # want to tell a dead mic apart from a room that is just quiet.
                    level_path.write_text(
                        f"{ev.get('rms', 0):.4f} {int(bool(ev.get('speaking')))}",
                        encoding="utf-8")
                    if ev.get("speaking") and speaking_since is None:
                        speaking_since = mute_generation
                    if muted_now:
                        if partial_path.read_text(encoding="utf-8"):
                            partial_path.write_text("", encoding="utf-8")
                        continue
                    continue

                # The discard button on screen. asr_mic cut the phrase off, audio
                # and all, so nothing settles for it and this is the last word on
                # it. Erase the on-screen text here and now. Wait for a settle
                # that is never coming and the text sits there looking un-erased.
                #
                # This sits above the mute check on purpose. Swallowed while
                # muted, speaking_since would keep the generation of a phrase that
                # no longer exists, and the next real utterance would be counted
                # as one that spanned a mute and thrown away as 「マイク切」.
                if ev["type"] == "dropped":
                    partial_path.write_text("", encoding="utf-8")
                    print(f"(消した) {ev.get('text', '')[:40]}",
                          file=sys.stderr, flush=True)
                    speaking_since = None
                    continue

                if muted_now:
                    # No partials are kept while muted. Settling is judged below.
                    if ev["type"] != "final":
                        if partial_path.read_text(encoding="utf-8"):
                            partial_path.write_text("", encoding="utf-8")
                        continue

                if ev["type"] == "partial":
                    # Partials overwrite a separate file (the prompt log stays clean)
                    partial_path.write_text(ev["text"], encoding="utf-8")
                    continue
                if ev["type"] != "final":
                    continue

                partial_path.write_text("", encoding="utf-8")
                text = ev["text"].strip()

                # The dictionary is read every time, so web UI edits land next utterance.
                user_dict = load_dictionary()

                # Voice-only commands (on and off, how to send, where to send).
                # Commands are all short, so they are checked before the minimum
                # length and the backchannel test.
                kind = apply_voice_command(text, log_path, muted_now, user_dict)
                if kind:
                    print(f"(合図 {kind}) {text[:40]}", file=sys.stderr, flush=True)
                    # A command is not an utterance, so it is not sent. was_muted
                    # is left alone, to be recounted at the top of the next loop
                    # (get ahead of it here and the generation never rises, and
                    # utterances that began before the mute can no longer be dropped).
                    speaking_since = None
                    continue

                # If a mute fell between the start of the utterance and now, or the
                # mic is still off, that utterance is not sent.
                started_at, speaking_since = speaking_since, None
                if muted_now or (started_at is not None and started_at != mute_generation):
                    print(f"(マイク切) {text[:40]}", file=sys.stderr, flush=True)
                    continue

                # When 「キャンセル」 lands at the end, throw the whole phrase away.
                if take_tail(text, CANCEL_TAIL) is not None:
                    note_voice_cmd(log_path, "cancelled", "", text)
                    print(f"(取り消し) {text[:40]}", file=sys.stderr, flush=True)
                    continue

                # When 「手直し」 lands at the end, it goes to the draft instead of
                # being sent. Short ones are not dropped (the person meant that).
                body = take_tail(text, HOLD_TAIL)
                force_hold = body is not None
                if force_hold:
                    if not body:
                        note_voice_cmd(log_path, "cancelled", "", text)
                        print(f"(手直し・空) {text[:40]}", file=sys.stderr, flush=True)
                        continue
                    text = body

                # Short utterances are thrown away as a rule, but words moved to the
                # do-not-ignore side of the dictionary go through (meaningful replies
                # like 「わかった」 or 「了解」).
                if not force_hold and len(text) < args.min_chars \
                        and not is_allowed_short(text,
                                                 user_dict.get("unignore", ())):
                    continue

                def drop(kind: str):
                    """Note in the terminal that it was not sent (nothing goes to Claude)."""
                    print(f"({kind}) {text[:40]}", file=sys.stderr, flush=True)

                # Built-ins and dictionary judged together (dictionary read every time)
                if not force_hold and not args.keep_noise \
                        and is_noise(text, user_dict["ignore"],
                                     user_dict.get("unignore", ())):
                    drop("無視")
                    continue
                if args.drop_non_japanese and looks_non_japanese(text):
                    drop("日本語以外")
                    continue

                text = polish(text, user_dict, args.keep_kanji_numbers,
                              args.strip_fillers)
                stamp = time.strftime("%H:%M:%S")

                # While paused it goes to the hold file. Nothing reaches Claude.
                # (The viewer shows the time, so the timestamp is kept here.)
                if force_hold or pause_path.exists():
                    with open(hold_path, "a") as h:
                        h.write(json.dumps({"time": stamp, "text": text},
                                           ensure_ascii=False) + "\n")
                    print(f"[{stamp}] (保留) {text}", file=sys.stderr, flush=True)
                    if force_hold:
                        note_voice_cmd(log_path, "held", "", text)
                    continue

                # The line that reaches Claude carries the body alone. Time and
                # language go unused, so they do not go in. The target is attached
                # only when one is chosen (a line without it goes to everyone).
                rec = {"text": text}
                to = resolve_target(log_path)
                if to:
                    rec["to"] = to
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                print(f"[{stamp}] {text}", file=sys.stderr, flush=True)

    except KeyboardInterrupt:
        print("\n終了します。", file=sys.stderr)
    finally:
        PID_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
