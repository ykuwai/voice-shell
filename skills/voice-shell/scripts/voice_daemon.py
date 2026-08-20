#!/usr/bin/env python3
"""音声プロンプト用の常駐デーモン。

マイクを聞き続け、発話が確定するたびに1行 JSON をログに追記する。
Claude Code 側は Monitor でこのログを tail し、行が来たらプロンプトとして扱う。

    python voice_daemon.py --language Japanese

ログ形式（1行1発話、JSONL）。本文だけを載せる:
    {"text": "テストを実行して"}

制御コマンド:
    python voice_daemon.py --status    # 動いているか確認
    python voice_daemon.py --stop      # 停止する
"""
import argparse
import contextlib
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

# fcntl は POSIX 専用（Windows に無い）。二重起動防止のロックだけの用途なので、
# Windows では msvcrt.locking で代替する。
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

# voice-shell.sh(bash) 側の "/tmp" と、この Python プロセスが単独で解釈する
# "/tmp" は実ディレクトリが食い違いうる（Windows では前者が MSYS のマウント先、
# 後者はドライブ直下の C:\tmp になる）。voice-shell.sh は cygpath で解決した
# 実パスを VOICE_SHELL_STATE_DIR で渡してくるので、あればそちらを使う。
if os.environ.get("VOICE_SHELL_STATE_DIR"):
    STATE_DIR = Path(os.environ["VOICE_SHELL_STATE_DIR"])
else:
    # 以前は "qwen-voice" という名前だった。Qwen3-ASR は数ある選択肢の
    # ひとつになったので名前を改めたが、動いているものを壊さないよう、
    # 古い方が残っていて新しい方が無ければそちらを使い続ける
    # （/tmp が空けば自然に新しい名前へ移る）。
    _base = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp"))
    STATE_DIR = _base / "voice-shell"
    _legacy = _base / "qwen-voice"
    if not STATE_DIR.exists() and _legacy.exists():
        STATE_DIR = _legacy

# ユーザー辞書。再起動をまたいで残したいので設定ディレクトリに置く。
# Web UI から編集でき、変更は次の発話からすぐ効く（デーモン再起動は不要）。
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME",
                                 Path.home() / ".config")) / "voice-shell"
DICT_FILE = CONFIG_DIR / "dictionary.json"
# 手元だけに置く辞書。社名・取引先・個人的な語など、公開したくないものを入れる。
# リポジトリには入らない（.gitignore で除外）。
PRIVATE_DICT_FILE = CONFIG_DIR / "dictionary.private.json"
# マイクの感度と「何秒黙ったら確定するか」。辞書と同じく設定ディレクトリに
# 置き、ビューアから変えられる。デーモンが 0.5 秒おきに読み直すので再起動は要らない。
TUNING_FILE = CONFIG_DIR / "tuning.json"
# 「次もこれで起動する」を覚えておく場所。辞書やしきい値と同じく
# 設定ディレクトリに置く（/tmp だと再起動で消え、毎回選び直しになる）。
CONFIG_FILE = CONFIG_DIR / "config.json"
PID_FILE = STATE_DIR / "daemon.pid"
LOG_FILE = STATE_DIR / "utterances.jsonl"
# 認識途中のテキスト。上書きし続けるだけで履歴は残さない（ビューアの表示用）。
PARTIAL_FILE = STATE_DIR / "partial.txt"
# いま拾えている音量。ビューアがバーとして出す。
# 文字が出ないとき、マイクが死んでいるのか黙っているだけなのかを見分ける。
LEVEL_FILE = STATE_DIR / "level.txt"
# このファイルがあると発話を保留する。認識は続くが Claude には送らず、
# 保留トレイに溜めて手直ししてから送れる。
PAUSE_FILE = STATE_DIR / "paused"
# 保留中に確定した発話の置き場。
HOLD_FILE = STATE_DIR / "held.jsonl"
# このファイルがあるとマイクを切った扱い。認識結果をどこにも残さず捨てる。
# デーモンを止めると再起動に1〜2分かかるので、こちらで無視するだけにする。
MUTE_FILE = STATE_DIR / "muted"
# 使いたいマイク。ビューアが書き、デーモンが読んで録音だけ差し替える
# （モデルは載せたままなので待たされない）。
MIC_FILE = STATE_DIR / "mic"

# 物音や息だけを拾ったときに出やすい定型句。これ単独の発話は指示ではないので捨てる。
# （モデルが無音に近い入力へ相槌を当ててしまうため）
NOISE_ONLY = {
    # 返事・相槌
    "はい", "はいはい", "はーい", "うん", "うんうん", "ううん", "ええ", "ええと",
    "そう", "そうそう", "そうか", "そうね", "そうですね", "なるほど", "たしかに",
    "オーケー", "オッケー", "よし", "よしよし", "わかった", "了解",
    # 息・言い淀み
    "あ", "あー", "ああ", "あっ", "い", "う", "うー", "うーん", "え", "えー",
    "えっ", "お", "おー", "おお", "おっ", "ん", "んー", "んん", "は", "はっ",
    "ふ", "ふう", "ふん", "ふーん", "ふむ", "へ", "へえ", "ほう", "ほー",
    "まあ", "ねえ", "あの", "あのー", "えっと", "えーと", "なんか",
    # 無音のときに ASR が出しがちな定型句。本人が言うことはまず無いものだけ。
    # （「ありがとうございました」「お疲れ様でした」は実際に言うので入れない）
    "ご視聴ありがとうございました", "チャンネル登録をお願いします",
    "最後までご視聴ありがとうございました", "ご覧いただきありがとうございます",
    # 英語でも同種の相槌が出る
    "yeah", "yes", "yep", "ok", "okay", "uh", "uh-huh", "um", "umm",
    "hmm", "hm", "mm", "mhm", "oh", "ah", "ahh", "eh", "huh",
    "right", "so", "well", "sure", "wow", "hey",
}

# 句読点・記号・空白を落として比較するための文字
_TRIM = "。、．，！？!?.…・ 　\n"

# 物音を拾ったとき、日本語以外に誤認識されることがある（実測で中国語が出た）。
# 日本語で使わない文字が含まれていれば、その発話は誤認識と判断して捨てる。
_NON_JA = re.compile(
    "["
    "ㄅ-ㄯ"      # 注音符号
    "가-힯"      # ハングル
    "Ѐ-ӿ"      # キリル
    "฀-๿"      # タイ文字
    "؀-ۿ"      # アラビア文字
    "嗯呢吗吧咱您们这那哪儿铁东车马门问题时间说话谢没儿"  # 簡体字・中国語特有
    "]"
)


def looks_non_japanese(text: str) -> bool:
    """日本語でも英語でもない文字が混ざっているか。"""
    return bool(_NON_JA.search(text))


DEFAULT_DICT = {
    # これ単独の発話なら捨てる（NOISE_ONLY に上乗せする）
    "ignore": [],
    # 認識結果を置き換える。技術用語はカタカナや略記で崩れやすい。
    # 長い語から当てるので、部分が重なっていてもよい。
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
        # よく崩れる略語（ピリオドが入ってしまう）
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
        # 他社のモデル・サービス（カタカナで出やすいもの）
        "ジェミニ": "Gemini",
        "オープンエーアイ": "OpenAI",
        "チャットジーピーティー": "ChatGPT",
        "コーデックス": "Codex",
        "コパイロット": "Copilot",
        # 「カーソル」は文字カーソルの意味でも使うので入れない
        # ツール・サービス
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
        # このプロジェクト
        "ボイスシェル": "voice-shell",
        "クエンエーエスアール": "Qwen3-ASR",
        "クエンASR": "Qwen3-ASR",
    },
}


_dict_cache = (None, None)   # (更新時刻の組, 中身)


def _read_one(path: Path) -> dict:
    """辞書ファイル1つを読む。無い・壊れているときは空。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"ignore": [], "replace": {}}
    except (json.JSONDecodeError, OSError) as e:
        print(f"{path.name} を読めませんでした ({e}) — 無視します", file=sys.stderr)
        return {"ignore": [], "replace": {}}
    return {
        "ignore": [s for s in data.get("ignore", []) if isinstance(s, str)],
        "replace": {k: v for k, v in data.get("replace", {}).items()
                    if isinstance(k, str) and isinstance(v, str)},
    }


def _mtimes():
    out = []
    for p in (DICT_FILE, PRIVATE_DICT_FILE):
        try:
            out.append(p.stat().st_mtime)
        except OSError:
            out.append(None)
    return tuple(out)


def load_dictionary() -> dict:
    """共有辞書と手元辞書を合わせて返す。

    発話ごとに呼ばれるので、更新時刻が変わったときだけ読み直す。
    これにより Web UI での編集がデーモン再起動なしで反映される。
    手元辞書（private）が優先される。
    """
    global _dict_cache
    mtimes = _mtimes()
    if _dict_cache[0] == mtimes:
        return _dict_cache[1]

    if mtimes == (None, None):
        return DEFAULT_DICT

    shared = _read_one(DICT_FILE)
    private = _read_one(PRIVATE_DICT_FILE)

    d = {
        "ignore": shared["ignore"] + private["ignore"],
        "replace": {**shared["replace"], **private["replace"]},
    }
    _dict_cache = (mtimes, d)
    return d


def save_default_dictionary():
    """辞書が無ければ既定値で作る（Web UI から編集する起点になる）。

    すでにある場合は、既定に増えた項目だけを足す。ユーザーが直した内容や
    消した項目は尊重するため、上書きはしない。
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    if not DICT_FILE.exists():
        DICT_FILE.write_text(json.dumps(DEFAULT_DICT, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return

    try:
        cur = json.loads(DICT_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return                      # 壊れていれば触らない（ユーザーが直せる）

    # 既定に新しく増えた語だけを補う。ユーザーが値を変えたものは変えない。
    known = set(cur.get("_seen", []))
    replace = dict(cur.get("replace", {}))
    added = 0
    for k, v in DEFAULT_DICT["replace"].items():
        if k not in replace and k not in known:
            replace[k] = v
            added += 1

    if not added:
        return

    cur["replace"] = replace
    cur["_seen"] = sorted(known | set(DEFAULT_DICT["replace"]))
    DICT_FILE.write_text(json.dumps(cur, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"辞書に既定の項目を {added} 件追加しました", file=sys.stderr)


# 漢数字。位取りのある表記（三十二 → 32）を数字に直す。
_KANJI_DIGIT = {"〇": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
                "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_KANJI_SMALL = {"十": 10, "百": 100, "千": 1000}
_KANJI_BIG = {"万": 10**4, "億": 10**8, "兆": 10**12}

# 数として読める並びだけを拾う。「一部」「一気に」を壊さないよう、
# 直後が助数詞・助詞になっているものは別途 _NOT_NUMBER で除く。
_KANJI_NUM_RE = re.compile(r"[〇零一二三四五六七八九十百千万億兆]+")

# 数字にすると意味が変わる語（慣用句・熟語）。これらは変換しない。
_NOT_NUMBER = {
    "一部", "一気", "一緒", "一応", "一旦", "一度", "一体", "一番", "一通り",
    "一方", "一見", "一切", "一人", "二人", "三人", "一日", "一言", "一杯",
    "一瞬", "一生", "一件", "一種", "一定", "一致", "一連", "一覧", "一環",
    "十分", "百歩", "千差", "万一", "万能", "億劫",
}


def _kanji_to_int(s: str):
    """漢数字を整数にする。読めなければ None。"""
    total = 0        # 万・億をまたいだ合計
    section = 0      # いまの区切り（万未満）の値
    digit = None     # 直前の一桁

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
    """漢数字をアラビア数字に直す（「三十秒」→「30秒」）。

    熟語や慣用句（一部・十分など）は変えない。単独の「一」「二」も、
    数として言ったのか判別できないので変えない。
    """
    def sub(m):
        s = m.group(0)
        if s in _NOT_NUMBER or len(s) == 1:
            return s
        n = _kanji_to_int(s)
        return str(n) if n is not None else s

    return _KANJI_NUM_RE.sub(sub, text)


# 大文字で書かれても略語ではないもの。「A vs B」を「A VS B」にしない。
# e.g. / i.e. / a.m. のような小文字の略記は大文字判定で弾かれるので入れない。
_NOT_ACRONYM = {"vs"}

# 1文字ずつ区切られたアルファベットの並び。「G.U.I.」「G U I」「T.T.S」を捉える。
# 各文字の直後の区切りはピリオドか空白。最後の1文字だけ区切りが無くてもよい。
# 2文字以上を条件にして、単独の「I」や「a」を巻き込まないようにする。
_SPELLED_RE = re.compile(
    r"(?<![A-Za-z])"              # 直前が英字なら別の語の一部なので触らない
    r"((?:[A-Za-z][.　 ]){1,}[A-Za-z]\.?)"
    r"(?![A-Za-z])"               # 直後が英字でも同様
)


def collapse_letter_acronyms(text: str) -> str:
    """1文字ずつ読み上げられた略語を詰める（「G.U.I.」「S S H」→「GUI」「SSH」）。

    音声認識は略語を一文字ずつ区切って返すことがある。辞書でも直せるが、
    未登録の語（AWS, JWT など）には効かないので、形で機械的に潰す。

    「Node.js」のような正当なドット付きの語や、文末のピリオドには触れない。
    区切りが2つ以上連続する並びだけを対象にするため、「I.」単独や
    「it. Some」のような普通の文は影響を受けない。
    """
    def sub(m):
        s = m.group(1)
        letters = re.sub(r"[.　 ]", "", s)
        # 音声認識が返す略語は大文字。小文字の並び（「a b c」「e.g.」）は
        # 普通の文章か略記なので触らない。この判定だけで e.g. / i.e. /
        # a.m. は守れる（大文字の「A M 三時」は AM に詰めてよい）。
        if not letters.isupper():
            return s
        # 大文字でも略語でないもの（「A vs B」の V S など）は残す
        if letters.lower() in _NOT_ACRONYM:
            return s
        return letters

    return _SPELLED_RE.sub(sub, text)


class LockedModel:
    """モデルへの呼び出しを1つずつに並べる。

    streaming_transcribe は共有の vllm.LLM を素で呼んでおり、ロックが無い。
    ローカルマイクと LAN からの接続が同時に触ると壊れるので、モデルに
    触る経路をここへ集める。asr_mic 側は元のモデルと同じ顔で使える。

    推論は1発話 0.1〜0.5 秒で、人は喋り続けない（GPU 利用率は 1% 程度）。
    数人であれば直列でも待ちは体感できない。
    """

    def __init__(self, model):
        self._model = model
        self._lock = threading.Lock()

    def __getattr__(self, name):
        """包んでいないメソッドはそのまま通す（設定値の参照など）。"""
        return getattr(self._model, name)

    def init_streaming_state(self, *a, **kw):
        with self._lock:
            return self._model.init_streaming_state(*a, **kw)

    def streaming_transcribe(self, *a, **kw):
        with self._lock:
            return self._model.streaming_transcribe(*a, **kw)

    def finish_streaming_transcribe(self, *a, **kw):
        with self._lock:
            return self._model.finish_streaming_transcribe(*a, **kw)

    def transcribe(self, *a, **kw):
        with self._lock:
            return self._model.transcribe(*a, **kw)


def apply_replacements(text: str, replace: dict) -> str:
    """辞書の置換を適用する。長い語から当てて部分一致の取りこぼしを防ぐ。"""
    for src in sorted(replace, key=len, reverse=True):
        if src:
            text = text.replace(src, replace[src])
    return text


# 意味を持たないつなぎ言葉。ビューアの設定で入切する。
# ここで消すことで、画面の見た目だけでなく Claude に渡る本文からも消える。
FILLERS = ["えーと", "えっと", "ええと", "あのー", "あの", "えー", "えっ",
           "まあ", "なんか", "そのー", "うーん", "んー"]
# 長いものから当てる（「あのー」を「あの」で先に食われないように）
_FILLER_RE = re.compile("|".join(re.escape(w) for w in
                                 sorted(FILLERS, key=len, reverse=True)))


def strip_fillers(text: str) -> str:
    """つなぎ言葉を落として、句読点の乱れを整える。"""
    text = _FILLER_RE.sub("", text)
    text = re.sub("、{2,}", "、", text)
    text = re.sub(r"^[、。\s]+", "", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def fix_latin_commas(text: str) -> str:
    """日本語モードで英語を話すと単語ごとに読点が入るのを戻す。"""
    return re.sub(r"([A-Za-z])、(?=[A-Za-z])", r"\1 ", text)


def read_config() -> dict:
    """前回の選択。無ければ空。"""
    try:
        d = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def write_config(**kw) -> dict:
    """選択を覚える。渡した項目だけ差し替える。"""
    cur = read_config()
    cur.update({k: v for k, v in kw.items() if v is not None})
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cur, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return cur


def resolve_engine(want: str = "") -> str:
    """これから使うエンジンを決める。

    指定 > 前回の選択 > 自動。自動は「何も入れずに動く」ブラウザを選ぶ。
    ブラウザが使えない状況（画面を開けない）だけは呼び出し側が
    --engine auto を渡してくるので、そのときは入っているモデルから選ぶ。
    """
    known = {"browser"} | {e["id"] for e in asr_mic.available_engines()}
    # クラウド/LAN のエンジンは import では見えないので名前で通す
    known |= {"cloud", "home-lan"}

    if want and want != "auto":
        if want not in known:
            sys.exit(f"「{want}」は使えません。"
                     f"選べるのは: {', '.join(sorted(known))}\n"
                     f"  一覧は voice-shell.sh engines")
        return want
    if not want:
        remembered = read_config().get("engine")
        if remembered in known:
            return remembered
        # 覚えていたものが使えなくなっている（モデルを消した等）。
        # 黙って失敗し続けるより、何もいらない方へ戻す。
        if remembered:
            print(f"前回選んだ「{remembered}」は今使えないので、"
                  f"このブラウザで認識します。", file=sys.stderr)
        return "browser"
    # want == "auto": 入っているモデルの中から選ぶ
    have = [e["id"] for e in asr_mic.available_engines()]
    for pick in ("apple", "whisper", "local", "mlx", "home-lan"):
        if pick in have:
            return pick
    # auto は「画面を開けないので手元のモデルで」という意味。
    # 1つも無いのに browser へ落とすと、その前提を裏切る。
    sys.exit("手元で使える認識モデルがありません。\n"
             "  SETUP.md の手順で入れるか、画面を開けるなら\n"
             "  voice-shell.sh start --engine browser をお使いください。")


def polish(text: str, user_dict: dict, keep_kanji_numbers: bool = False,
           drop_fillers: bool = False) -> str:
    """認識したテキストを読みやすく整える。ローカルと LAN の両方で通す。

    辞書はクラウドの API に対するこちらの取り柄なので、リモートでも効かせる。
    略語を先に詰めるのは、辞書が完全一致で当たるため。「G P U」のまま
    だと登録済みの「G.P.U.」に当たらない。
    """
    text = collapse_letter_acronyms(text)
    text = apply_replacements(text, user_dict["replace"])
    if not keep_kanji_numbers:
        text = kanji_numbers_to_arabic(text)
    text = fix_latin_commas(text)
    if drop_fillers:
        text = strip_fillers(text)
    return text


@contextlib.contextmanager
def _remote_tokens(model, limit: int):
    """この中だけ生成トークンの上限を伸ばす。

    モデルは max_new_tokens=64 で読み込んである。ローカルは 2 秒ごとに
    区切って認識するので足りるが、LAN 経由は発話をまとめて渡すため
    100 文字あたりで頭打ちになる。ロックの内側で呼ぶので、差し替えて
    いる間に他のスレッドが割り込むことはない。
    """
    sp = getattr(model, "sampling_params", None)
    if sp is None or getattr(sp, "max_tokens", None) is None:
        yield                      # 触れないなら何もしない
        return
    before = sp.max_tokens
    sp.max_tokens = limit
    try:
        yield
    finally:
        sp.max_tokens = before


def start_remote_server(model, args) -> None:
    """LAN からの接続を受けるサーバを別スレッドで立てる。

    認識はこのプロセスのモデルを使う。GPU に載るモデルは1つだけなので、
    別プロセスにはできない（voice-shell.sh の二重起動ガードにも掛かる）。
    """
    import remote_server

    conf = remote_server.load_conf()

    def make_session():
        """接続1本ぶんの認識係を作る。

        ローカルマイクと同じく streaming_transcribe を回す。溜めてから
        一度に投げると喋り終わるまで何も返せず、届いているのかどうかが
        手元で分からない。state は接続ごとに持つので混ざらない。
        """
        state = model.init_streaming_state(
            language=args.language,
            unfixed_chunk_num=args.unfixed_chunk_num,
            unfixed_token_num=args.unfixed_token_num,
            chunk_size_sec=args.chunk_size_sec,
        )

        def feed(pcm):
            """届いた音を認識に流して、現時点のテキストを返す。"""
            model.streaming_transcribe(pcm, state)
            return state.text or ""

        def finish():
            """発話の終わり。確定させて後処理を通す。"""
            model.finish_streaming_transcribe(state)
            text = (state.text or "").strip()
            # 次の発話のために作り直す（state は使い回せない）
            state.__dict__.update(model.init_streaming_state(
                language=args.language,
                unfixed_chunk_num=args.unfixed_chunk_num,
                unfixed_token_num=args.unfixed_token_num,
                chunk_size_sec=args.chunk_size_sec,
            ).__dict__)
            if not text:
                return ""
            # ローカルと同じ後処理を通す。辞書は毎回読むので編集が即効く。
            return polish(text, load_dictionary(), args.keep_kanji_numbers,
                          getattr(args, "strip_fillers", False))

        return feed, finish

    ready = threading.Event()
    t = threading.Thread(
        target=lambda: remote_server.serve(conf, make_session, ready=ready),
        name="remote-server", daemon=True)
    t.start()
    # 待ち受けに入るまで待つ。失敗しても本体は動かしたいので通す。
    ready.wait(timeout=10)


def is_noise(text: str, extra=()) -> bool:
    """相槌だけの発話かどうか。

    「はい、はい」のように区切って繰り返しただけのものも相槌とみなす。
    中身のある発話（「はい、それでは始めます」）は残す。

    extra には辞書の「無視する発話」を渡す。組み込みと同じ扱いにするので、
    ユーザーが足した語も「〜、〜」の繰り返し判定に効く。
    """
    words = NOISE_ONLY | {w.lower() for w in extra}
    core = text.strip().strip(_TRIM)
    if core.lower() in words:
        return True
    # 句読点で分割して、全部が相槌なら捨てる（「はい、はい」「うん、うん。」）
    parts = [p.strip().strip(_TRIM) for p in re.split(r"[、。,.\s]+", core) if p.strip(_TRIM)]
    return bool(parts) and all(p.lower() in words for p in parts)


# ── 声だけでマイクを入切する ──────────────────────
#
# 合図の語は短いので、最小文字数や相槌の判定より前に見る。誤爆すると
# 話しかけているのに届かない状態になるので、その一言だけを喋ったときに
# 限る（部分一致はしない）。
#
# 切っている間も認識は動いている（録ってはいるが送らない）ので解除の
# 合図は届く。ブラウザ認識は切ると音声を手放すので、声では戻せない。
MUTE_WORDS = {
    "ミュート", "みゅーと", "ミュートして", "ミュートしてください", "ミュートお願い",
    "ミュートオン", "ミュートオンにして", "ミュートします",
    "マイクオフ", "マイクをオフ", "マイクをオフにして",
    "マイクを切って", "マイク切って", "マイクを切る", "マイク切る",
    "mute", "muteme", "mutethemic", "micoff", "turnoffthemic", "turnthemicoff",
}
# 解除の語は、**この道具にしか言わない言葉**に限る。切っている理由はたいてい
# 通話や同席者との会話なので、「戻して」「再開」のような普通の言葉を入れると、
# 相手に言ったつもりの一言でマイクが開き、そのあとの会話が指示として流れ出す。
# 誤爆で失うのが「発話1つ」ではなく「切っていたつもりの時間ぜんぶ」になる。
UNMUTE_WORDS = {
    "ミュート解除", "ミュートかいじょ", "ミュート解除して", "ミュート解除してください",
    "ミュートを解除", "ミュートを解除して", "ミュートオフ", "ミュートオフにして",
    "アンミュート", "あんみゅーと", "解除", "かいじょ", "解除して", "かいじょして",
    "マイクオン", "マイクをオン", "マイクをオンにして", "マイクをつけて", "マイク付けて",
    "マイクを入れて", "マイク入れて",
    "unmute", "unmuteme", "unmutethemic", "micon", "turnonthemic", "turnthemicon",
}

# 記号と間の空白を落としてから比べる。「ミュート。」「mute me」「マイク、オン」
# のどれも同じ鍵になるようにする。全角数字はここで半角へ畳む。
# ー（長音）は落とさない。落とすと「ミュート」が「ミュト」になって当たらない。
_CMD_DROP = str.maketrans("１２３４５６７８９０", "1234567890",
                          " \t\u3000。、．，・…！？!?.,-~〜\"'「」『』()（）")


def voice_command(text: str, muted: bool):
    """発話そのものが入切の合図なら "mute" / "unmute" を返す。

    いまの状態で意味のある方だけを見る。切っている最中の「ミュート」も、
    入っている最中の「ミュート解除」も何も起こさない。見る語が半分になる分、
    誤爆も半分になる。
    """
    key = text.strip().translate(_CMD_DROP).lower()
    if not key:
        return None
    if muted:
        return "unmute" if key in UNMUTE_WORDS else None
    return "mute" if key in MUTE_WORDS else None


# 数の言い方は認識のたびに揺れる。「2」と言っても「に」「ツー」「二」と出るし、
# 「送信先に」は「送信先2」のことがある。読みを一通り並べて、どれで来ても拾う。
# ひらがな1文字（に・し・ご・く）は助詞と見分けが付かないので、単独では効かない
# — 下の型はどれも「番」「送信先」「〜に切り替え」の形を要求する。
_NUM_WORDS = {
    "0": 0, "〇": 0, "ぜろ": 0, "れい": 0, "ゼロ": 0, "zero": 0,
    "1": 1, "一": 1, "いち": 1, "ワン": 1, "わん": 1, "one": 1,
    "2": 2, "二": 2, "に": 2, "ツー": 2, "つー": 2, "トゥー": 2, "とぅー": 2, "two": 2,
    "3": 3, "三": 3, "さん": 3, "スリー": 3, "すりー": 3, "three": 3,
    "4": 4, "四": 4, "よん": 4, "し": 4, "フォー": 4, "ふぉー": 4, "four": 4,
    "5": 5, "五": 5, "ご": 5, "ファイブ": 5, "ふぁいぶ": 5, "five": 5,
    "6": 6, "六": 6, "ろく": 6, "シックス": 6, "しっくす": 6, "six": 6,
    "7": 7, "七": 7, "なな": 7, "しち": 7, "セブン": 7, "せぶん": 7, "seven": 7,
    "8": 8, "八": 8, "はち": 8, "エイト": 8, "えいと": 8, "eight": 8,
    "9": 9, "九": 9, "きゅう": 9, "く": 9, "ナイン": 9, "ないん": 9, "nine": 9,
    "10": 10, "十": 10, "じゅう": 10, "テン": 10, "てん": 10, "ten": 10,
}
# 長いものから当てる。「じゅう」を「じ」「ゅ」…と崩されないように。
_NUM_ALT = "(?:" + "|".join(
    sorted((re.escape(k) for k in _NUM_WORDS), key=len, reverse=True)) + ")"
_COUNTER = r"(?:番目|ばんめ|番|ばん)"
# 言い方が惜しく外れると、min_chars（既定15字）に届かず黙って消える。
# 「合図でもプロンプトでもない」が一番たちが悪いので、語尾は広めに取る。
_VERB_CORE = (r"(?:切り替え|切替|きりかえ|変更|へんこう|送る|おくる|送って|おくって|"
              r"送信|そうしん|して|お願い|おねがい|頼む|たのむ|"
              r"switchto|sendto|goto)")
_TAIL = r"(?:て|る|して|ください|下さい|お願い|おねがい|します|ます|ましょう|な|ね)*"
_VERB = rf"(?:{_VERB_CORE}{_TAIL})"
_PREFIX = r"(?:送信先|宛先|あて先|セッション|せっしょん)"
_PART = r"(?:に|へ|で)?"

_ROUTE_RXS = [re.compile(rx) for rx in (
    # 送信先2 / 送信先を2に / セッション2に切り替えて / セッショントゥー
    # 「送信先に」も入る（に＝2）。番号の無い「送信先に」は言葉として成り立たない。
    rf"^{_PREFIX}を?({_NUM_ALT}){_COUNTER}?{_PART}{_VERB}?$",
    # 2番 / 1番目 / 2番にして / 2番でお願い（頭に数が来る方が認識されやすい）
    rf"^({_NUM_ALT}){_COUNTER}{_PART}{_VERB}?$",
    # 2に切り替え / 2へ送って（数のあとに必ず動詞が要る）
    rf"^({_NUM_ALT})(?:に|へ){_VERB}$",
    # switch to 2 / session two / route 3
    rf"^(?:switchto|sendto|routeto|goto|target|session|destination|route)"
    rf"(?:session)?({_NUM_ALT})$",
)]


# 即時 / 手直しの切り替えも声でできるようにする。どちらもこの道具に対して
# しか言わない言葉なので、単独で言われたら合図として扱ってよい。
LIVE_WORDS = {
    "即時", "そくじ", "即時モード", "そくじもーど", "即時に", "即時にして",
    "即時に戻して", "そのまま送る", "そのまま送って",
    # 「そくじ」は「食事」に化けやすい（実測）。単独で来たら同じ合図とみなす。
    "食事", "しょくじ", "食事モード", "速時", "則時",
    "live", "livemode", "instant", "instantmode", "sendlive",
}
HOLD_WORDS = {
    "手直し", "てなおし", "手直しモード", "てなおしもーど", "手直しに", "手直しにして",
    "手直しに回して", "溜めて", "ためて", "溜める", "ためる", "保留",
    "hold", "holdmode", "draft", "draftmode",
}


def mode_command(text: str):
    """送り方を切り替える合図なら "live" / "hold" を返す。"""
    key = text.strip().translate(_CMD_DROP).lower()
    if not key:
        return None
    if key in LIVE_WORDS:
        return "live"
    return "hold" if key in HOLD_WORDS else None


def route_command(text: str):
    """送信先を選ぶ合図なら番号を返す（画面に並ぶ順の1番目から）。"""
    key = text.strip().translate(_CMD_DROP).lower()
    if not key or len(key) > 24:      # 合図はどれも短い。長い文は見るまでもない
        return None
    for rx in _ROUTE_RXS:
        m = rx.match(key)
        if m:
            return _NUM_WORDS[m.group(1)]
    return None


# 言い終わってから「やっぱりなし」「これは直してから送りたい」と思うことが
# ある。発話の**終わり**に合図が来たら、その一言をそのように扱う。途中に
# 出てきた分は普通の言葉のまま（合図の話をしているだけのことがある）。
#
# 語は絞る。「やめて」「なし」のような、普通の文の終わりにも来る言い方を
# 入れると、そのつもりのない指示まで持っていかれる。
CANCEL_TAIL = (
    "キャンセル", "きゃんせる", "キャンセルで", "キャンセルして",
    "取り消し", "取消", "取り消して", "とりけし", "とりけして",
    "なかったことに", "なかったことにして", "やっぱなし", "やっぱりなし",
    "cancel", "cancel that", "scratch that", "never mind", "nevermind",
)
# こちらは捨てずに、画面の下書きへ回す（直してから送れる）
HOLD_TAIL = (
    "手直し", "てなおし", "手直しで", "手直しして", "手直ししたい",
    # 「てなおし」は「出直し」に化けやすい（実測）
    "出直し", "でなおし", "出直して",
    "直してから", "なおしてから", "あとで直す", "ちょっと直す",
    "edit", "edit this", "let me edit", "hold this",
)
# 合図だと分かるように「コマンド◯◯」と言う人がいる。前置きは落とす。
_TAIL_PREFIX = ("コマンド", "こまんど", "command")
_TAIL_TRIM = " \t\u3000。、．，・！？!?.,"


def take_tail(text: str, tails):
    """末尾が合図なら、それを取り除いた本文を返す。合図でなければ None。"""
    body = text.strip().rstrip(_TAIL_TRIM)
    low = body.lower()
    for w in tails:
        if not low.endswith(w):
            continue
        rest = body[: len(body) - len(w)].rstrip(_TAIL_TRIM)
        for pre in _TAIL_PREFIX:          # 「〜。コマンド手直し」の前置き
            if rest.lower().endswith(pre):
                rest = rest[: len(rest) - len(pre)].rstrip(_TAIL_TRIM)
                break
        return rest
    return None


def note_voice_cmd(log_path, kind: str, label: str = "", said: str = "") -> None:
    """声の合図に何が起きたかを画面へ渡す。

    合図は発話として送らないので、通ったかどうかがユーザーに見えない。
    ビューアがこのファイルを見て、音を鳴らし、一言を出す。

    said には合図と判定した発話そのものを入れる。指示のつもりで言ったものが
    合図として消えることがあるので、何が消えたのかは見せておく。
    """
    try:
        # encoding を書かないと Windows はロケール（cp932）で開く。題名に
        # cp932 に無い字が1つでもあると UnicodeEncodeError で落ちる。これは
        # OSError ではないので、捕まえる側も広げておく。
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
                        "本当に短く指示したいときはビューアから送る")
    p.add_argument("--keep-noise", action="store_true",
                   help="「はい」「うん」等の相槌も送る（既定では捨てる）")
    p.add_argument("--keep-kanji-numbers", action="store_true",
                   help="漢数字をそのまま送る（既定は「三十秒」→「30秒」に直す）")
    p.add_argument("--drop-non-japanese", action="store_true",
                   help="中国語・韓国語等を含む発話を捨てる（既定では送る。"
                        "意図して他言語を話すことがあるため既定は無効）")
    p.add_argument("--remote-max-tokens", type=int, default=512,
                   help="LAN 経由の認識で生成するトークンの上限。"
                        "既定の 64 だと長い発話が 100 文字ほどで切れる")
    p.add_argument("--remote", action="store_true",
                   help="LAN の端末から音声を受ける（~/.config/voice-shell/"
                        "remote.json の設定で待ち受ける）")
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
    return p.parse_args()


def _pid_alive(pid):
    """シグナルを送らずに生存確認する。"""
    if sys.platform.startswith("win"):
        # os.kill(pid, 0) は Windows では未対応（SystemError になる）。
        # ハンドルが取れるかどうかで代用する。
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
        # 他人のプロセスに PID が再利用されている。ここで見る PID は
        # すべて自分が書いたものなので、他人のもの＝目的のプロセスではない。
        # True にすると status が永久に「稼働中」になり、start も
        # 二度と通らなくなる（二重起動の本当の歯止めは flock 側にある）。
        return False


def read_pid():
    try:
        pid = int(PID_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return None
    return pid if _pid_alive(pid) else None


def _proc_started_at(pid):
    """そのプロセスが始まってから何秒経ったか。分からなければ None。

    PID は使い回されるので、登録ファイルより後に始まったプロセスは別人と
    みなす。経過秒（ps の etime）で見るのは、書式が "分:秒" や
    "日-時:分:秒" と揺れる開始時刻より、桁を跨いでも解釈が単純なため。
    ps が無い環境では None を返し、判定を素通りさせる。
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
            parts.insert(0, 0)            # "分:秒" を "0:分:秒" に揃える
        secs = parts[0] * 3600 + parts[1] * 60 + parts[2]
        return secs + (int(days) * 86400 if days else 0)
    except Exception:
        return None


# 送信先の指定。ビューアが書き、デーモンが毎回読む。
#   ファイルが無い  … まだ選んでいない（あとで起動した方へ届ける）
#   <PID>          … その相手へ
# 「全員へ」は選べない。2つのセッションが同じ指示を受け取って別々に動き出す
# 状況に使い道が無く、間違って選ぶと気づきにくいだけだった。
def route_file(log_path):
    return Path(log_path).parent / "route"


def write_atomic(path, text: str) -> None:
    """別名で書いてから置き換える。

    truncate と write のあいだに読まれると、欠けた内容が渡る。送信先の
    場合は「一致する PID が無い」と見なされて別の相手へ1発話行く。
    """
    tmp = Path(path).with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def resolve_target(log_path):
    """いまの届け先を決める。None なら全員へ。

    既定は「あとで起動した方」。並行して別の作業を始めたら、そちらへ
    向くのが自然なため。ここで決めるので、**画面を開いていなくても効く**
    （以前は画面側だけの処理で、開いていないと全員に二重に届いていた）。
    """
    try:
        raw = route_file(log_path).read_text(encoding="utf-8").strip()
    except OSError:
        raw = ""

    # 選んだ相手は、登録ファイルの有無だけで判断する。生存確認の走査は
    # 一時的に数え損なうことがあり、そのたびに別の相手へ回すと、選んだ
    # つもりのない相手へ発話が紛れ込む（届かない方がまだ安全）。
    if raw and (listeners_dir(log_path) / raw).exists():
        return raw

    # まだ選んでいない、または選んだ相手が終了した。既定は「いま起動した方」
    # なので、並び順（first_seen）ではなく登録し直した時刻で選ぶ。
    # 聞き手が1つだけなら宛先を書く意味がない。
    live = list_active_listeners(log_path)
    if len(live) <= 1:
        return None
    return str(max(live, key=lambda e: e.get("since", 0))["pid"])


# ── 聞き手の名前 ──────────────────────────
#
# 起動時点では作業の中身が決まっていないので、まずフォルダ名。エージェントが
# 会話に題名を付けたらそちらへ切り替える。題名の在り処は道具ごとに違うため、
# 探し方を並べて上から試す。どれにも当たらない道具のために、環境変数
# （VOICE_SHELL_NAME）と `voice-shell.sh name` も残してある。

_title_cache = {}      # path -> (mtime, title)


def _claude_title(session_id):
    """Claude Code が付けた題名。会話が進むと更新される。"""
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
                # 全行を JSON に起こすと重い。目印のある行だけ見る。
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
    """Codex が付けた題名（thread_name）。"""
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
    """`voice-shell.sh name` で付けた名前（会話の id → 表示名）。"""
    try:
        return json.loads((CONFIG_DIR / "names.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def listener_title(entry):
    """その聞き手をいま何と呼ぶか。無ければ None（フォルダ名に落とす）。"""
    if entry.get("name"):
        return entry["name"]              # 手で付けた名前が最優先
    sid, agent = entry.get("session"), entry.get("agent")
    if not sid:
        return None
    # 音声モードを入れ直すと登録ファイルは作り直されるので、設定側も見る
    named = saved_names().get(sid)
    if named:
        return named
    if agent == "claude":
        return _claude_title(sid)
    if agent == "codex":
        return _codex_title(sid)
    return None


def label_listeners(entries):
    """表示名を決める。同じ名前が並んだら早い順に (2) (3) と付ける。

    並びは「その会話が最初に聞き始めた時刻」。登録し直した時刻で並べると、
    音声モードを入れ直すたびに番号が動いて、声で指す番号が当てにならない。
    """
    # 同じ時刻で並んだときは PID で決める。ここを決めておかないと、
    # 登録ファイルを読む順（OS 任せ）で番号が入れ替わる。
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
    """発話ログを聞いているセッションを一覧する。

    `pgrep` に頼らない（Windows の Git Bash には無い）。代わりに
    `voice-shell.sh listen` が起動時に自分で登録するファイルを見る。
    生きていないものはついでに掃除する。
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
        # 登録ファイルより後に始まったプロセスなら、PID が使い回されただけの
        # 別人。これを見ないと、居ないセッションについて警告を書き続ける。
        stale = False
        age = _proc_started_at(pid)
        if age is not None:
            try:
                registered_ago = time.time() - f.stat().st_mtime
                stale = age < registered_ago - 5      # 5秒は測り方のぶれ
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
                f.unlink(missing_ok=True)   # 死んでいるものは片付ける
            except PermissionError:
                pass                        # 他人のもの。触らない
    return label_listeners(out)


def main():
    args = parse_args()

    if args.remember_engine is not None:
        write_config(engine=args.remember_engine)
        return

    if args.resolve_engine is not None:
        print(resolve_engine(args.resolve_engine))
        return

    if args.list_engines:
        remembered = read_config().get("engine", "")
        have = asr_mic.available_engines()
        print("  browser   このブラウザ（何も入れずに動く）")
        for e in have:
            print(f"  {e['id']:<9} {e['label']}")
        print(f"\n  前回の選択: {remembered or '(まだ無い)'}")
        return

    if args.listeners:
        # 何も出さない/出す は呼び出し側（voice-shell.sh）に判断させる。
        # ここで固定文言を出すと「呼び出し側が空かどうかを見分けられない」ため。
        for l in list_active_listeners(args.log_file):
            print(f"  {l['label']}  （PID {l['pid']}）")
            print(f"    起動 : {l['started']}")
            print(f"    場所 : {l['cwd']}")
        return

    if args.status:
        pid = read_pid()
        if pid:
            n = sum(1 for _ in open(args.log_file)) if Path(args.log_file).exists() else 0
            print(f"稼働中 (PID {pid}) / これまでの発話 {n} 件")
            print(f"ログ: {args.log_file}")
        else:
            print("停止しています。")
        return

    if args.stop:
        pid = read_pid()
        if not pid:
            print("動いていません。")
            return
        os.kill(pid, signal.SIGTERM)
        # 本当に終わるまで少し待つ。ここで即座に返ると、呼び出し元
        # （viewer.py の /api/engine）は「止めた」と判断してしまうが、
        # 実際にはまだ数百ms〜数秒プロセスが生きていることがある。
        # その隙にブラウザ認識（Web Speech API）が発話を送ると、
        # /api/utterance の「デーモンが動いているなら受けない」判定に
        # 引っかかり、最初の1件だけ発話が黙って捨てられる（実測）。
        for _ in range(50):        # 最大5秒
            if not _pid_alive(pid):
                break
            time.sleep(0.1)
        print(f"停止しました (PID {pid})")
        return

    if read_pid():
        sys.exit("すでに動いています。停止するには --stop を使ってください。")

    STATE_DIR.mkdir(parents=True, exist_ok=True)

    # 二重起動を確実に防ぐ。PID ファイルは読み込みが終わってから書かれるので、
    # 起動中（1分ほど）は上の確認をすり抜けてしまう。GPU を 12GB 使うため
    # 二つ動くと両方とも中途半端に壊れる。ロックは起動の瞬間から効き、
    # 異常終了しても OS が解放するので取り残しの心配がない。
    _lock = open(STATE_DIR / "daemon.lock", "w")
    try:
        _lock_exclusive_nb(_lock)
    except OSError:
        sys.exit("すでに起動しています（読み込み中かもしれません）。")
    globals()["_daemon_lock"] = _lock   # 閉じると解放されるので握り続ける

    log_path = Path(args.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    # 起動のたびに空にする（前回の発話を拾わせない）
    log_path.write_text("", encoding="utf-8")

    save_default_dictionary()

    # ビューアから指定されたマイクを毎回見る（切り替えは録音だけ入れ替える）
    # 前回選んだマイクを覚えておく。/tmp のファイルは再起動で消えるので、
    # そこだけだと毎回「システムの既定」に戻ってしまう。
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

    # 実際に切り替えが完了したデバイス名。ビューアが「切り替えました」と
    # 表示するのはボタンを押した瞬間の楽観的な表示で、裏で本当に切り替わった
    # かは分からない。ここに確定情報を書き、ビューアはこのファイルの変化を
    # 見て初めて確定の表示をする。
    mic_active_path = Path(args.log_file).parent / "mic_active"
    mic_active_path.write_text(args.device, encoding="utf-8")

    def on_switch(dev):
        mic_active_path.write_text(dev, encoding="utf-8")
        write_config(mic=dev)      # 次の起動でも同じマイクを使う

    args.on_switch = on_switch

    # マイク感度と確定までの無音秒数もビューアから触れる。録音の入れ替えすら
    # 要らず、次に読み直した時点から効く。ファイルが無ければ今の値で作る。
    def want_tuning():
        try:
            return json.loads(TUNING_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None      # 書き換え途中で読んだだけ。次の周期で拾い直す

    args.want_tuning = want_tuning

    # 保存済みの値があれば、起動時点から反映しておく
    saved = want_tuning() or {}
    for key in ("silence_threshold", "silence_duration"):
        if isinstance(saved.get(key), (int, float)):
            setattr(args, key, float(saved[key]))
    if isinstance(saved.get("min_chars"), (int, float)):
        args.min_chars = int(saved["min_chars"])
    if isinstance(saved.get("strip_fillers"), bool):
        args.strip_fillers = saved["strip_fillers"]
    # 認識言語（Whisper 限定）。他のエンジンは "Japanese" のような綴りを
    # 使うため、ここで上書きすると壊れる。空文字は自動判定を意味する。
    if args.engine == "whisper" and isinstance(saved.get("language"), str):
        args.language = saved["language"] or None

    # 足りない項目を今の値で埋める。ファイルが既にある人にも新しい項目が
    # 行き渡るようにする（無いままだとビューアのつまみが効かない）。
    filled = dict(saved)
    for key in ("silence_threshold", "silence_duration", "min_chars",
                "strip_fillers"):
        filled.setdefault(key, getattr(args, key))
    if args.engine == "whisper":
        # CLI 既定の "Japanese" のような綴りのままだと、ビューアの
        # プルダウン（2文字コードで持つ）と一致しないので正規化する。
        import whisper_engine
        filled.setdefault("language", whisper_engine._lang_code(args.language) or "")
    if filled != saved:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        TUNING_FILE.write_text(json.dumps(filled, indent=2) + "\n", encoding="utf-8")

    # ビューアが「今どのエンジンか」を知るための確定情報（認識言語の
    # プルダウンは Whisper のときだけ出す）。
    (Path(args.log_file).parent / "engine_active").write_text(args.engine, encoding="utf-8")

    print("モデルを読み込み中… (初回は数分かかります)", file=sys.stderr)
    model = asr_mic.load_model(args)

    # LAN からの接続とローカルマイクが同じモデルを触るので、ロックで並べる。
    # クラウドのエンジンを使うときは接続情報しか持たないので包まない。
    if args.remote and args.engine == "local":
        model = LockedModel(model)

    if args.remote:
        start_remote_server(model, args)

    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    print(f"\n  聞いています — 喋ると {log_path} に追記します"
          f"\n  Ctrl-C で終了\n", file=sys.stderr, flush=True)

    # 聞いているセッションが2つ以上になったら、発話ログ自体に警告を書いて
    # Claude Code（Monitor でこのログを見ている側）へ知らせる。8日前の
    # セッションが聞いたままで、同じ発話が2つに配られていたことが実際に
    # あった。`voice-shell.sh listen` が起動時に自分を登録するので、
    # ここではその数を数えるだけでよい（pgrep 不要、Windows でも動く）。
    def watch_listeners():
        last_count = None
        while True:
            time.sleep(5)
            count = len(list_active_listeners(log_path))
            # 送信先を選んでいるなら、複数聞いていても二重には届かない。
            # 意図した使い方なので黙っている。
            # 宛先が決まっていれば二重には届かない（既定でも決まる）
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
        pause_path.unlink(missing_ok=True)   # 起動時は必ず送信状態から
        mute_path.unlink(missing_ok=True)
        hold_path.write_text("", encoding="utf-8")

        # 確定時のミュート状態だけを見ると、切っている間に話した音声が解除後に
        # 流れ込む。切られた回数を数え、発話が始まった時点の値と比べて、
        # ミュートをまたいだ発話を捨てる（単純なフラグだと、ミュート中に拾った
        # 物音がフラグを消費して直後の発話を巻き込む）。
        mute_generation = 0
        was_muted = False
        speaking_since = None   # いま進行中の発話が始まった時点の generation
        # いま進行中の発話が始まった時刻。画面の「消す」は、押した時点で
        # 喋っていた一言だけを落としたい。確定より後に押されたものが次の
        # 発話を巻き込まないよう、始まりの時刻と押した時刻を比べる。
        speaking_at = None
        drop_path = log_path.parent / "drop_at"

        # 読み手（ビューア・Monitor）と食い違わないよう明示する。
        # Windows は指定しないとロケール（cp932）で開いてしまう。
        with open(log_path, "a", buffering=1, encoding="utf-8") as f:
            for ev in asr_mic.stream_utterances(model, args):
                muted_now = mute_path.exists()
                if muted_now and not was_muted:
                    mute_generation += 1      # 切られた
                was_muted = muted_now

                # 発話の始まりを捉える（無音から声に変わった瞬間）
                if ev["type"] == "level":
                    # 音量をビューアに渡す。文字が出ないとき、マイクが
                    # 死んでいるのか黙っているだけなのかを見分けたい。
                    level_path.write_text(
                        f"{ev.get('rms', 0):.4f} {int(bool(ev.get('speaking')))}",
                        encoding="utf-8")
                    if ev.get("speaking") and speaking_since is None:
                        speaking_since = mute_generation
                        speaking_at = time.time()
                    if muted_now:
                        if partial_path.read_text(encoding="utf-8"):
                            partial_path.write_text("", encoding="utf-8")
                        continue
                    continue

                if muted_now:
                    # ミュート中の途中経過は残さない。確定は下でまとめて判定する。
                    if ev["type"] != "final":
                        if partial_path.read_text(encoding="utf-8"):
                            partial_path.write_text("", encoding="utf-8")
                        continue

                if ev["type"] == "partial":
                    # 途中経過は別ファイルに上書き（プロンプトのログは汚さない）
                    partial_path.write_text(ev["text"], encoding="utf-8")
                    continue
                if ev["type"] != "final":
                    continue

                partial_path.write_text("", encoding="utf-8")
                text = ev["text"].strip()

                # 画面の「消す」。押した時点で進行中だった一言だけ落とす。
                started_at_wall, speaking_at = speaking_at, None
                if drop_path.exists():
                    try:
                        asked = float(drop_path.read_text(encoding="utf-8") or 0)
                    except (OSError, ValueError):
                        asked = 0.0
                    drop_path.unlink(missing_ok=True)
                    if started_at_wall is not None and asked >= started_at_wall:
                        print(f"(消した) {text[:40]}", file=sys.stderr, flush=True)
                        speaking_since = None
                        continue

                # 辞書は毎回読む。Web UI で直した内容が次の発話から効くようにする。
                user_dict = load_dictionary()

                # 声だけの入切。合図はどれも短いので、最小文字数より前に見る。
                # 辞書を通した形でも見るため、崩れて聞こえる語は
                # 「ミュート回収 → ミュート解除」のように登録すれば拾える。
                cmd = voice_command(text, muted_now) or voice_command(
                    apply_replacements(text, user_dict["replace"]), muted_now)
                if cmd:
                    if cmd == "mute":
                        mute_path.touch()
                    else:
                        mute_path.unlink(missing_ok=True)
                    note_voice_cmd(log_path, cmd)
                    print(f"(声で{'切' if cmd == 'mute' else '入'}) {text[:40]}",
                          file=sys.stderr, flush=True)
                    # 合図そのものは発話ではないので送らない。was_muted は
                    # 触らない — 次の周回の頭で数え直させる（ここで先回りすると
                    # 世代が上がらず、切る前に始まった発話を落とせなくなる）。
                    speaking_since = None
                    continue

                # 送り方（即時 / 手直し）も声で切り替える。
                mode = mode_command(text)
                if mode:
                    if mode == "hold":
                        pause_path.touch()
                    else:
                        pause_path.unlink(missing_ok=True)
                    note_voice_cmd(log_path, "mode_" + mode, "", text)
                    print(f"(声で{mode}) {text[:40]}", file=sys.stderr, flush=True)
                    speaking_since = None
                    continue

                # 送信先も声で選ぶ。番号は画面に並ぶ順（「すべて」を除いた1番目から）。
                # 切っている間も効かせる — どのみち短い語は聞いているので、
                # 切ったまま次の相手を決めておける（解除するまで何も届かない）。
                # 辞書を通した形でも見る（ミュートの合図と揃える）。
                n = route_command(text) or route_command(
                    apply_replacements(text, user_dict["replace"]))
                live = list_active_listeners(log_path) if n is not None else []
                # 聞き手が1つなら選ぶ相手がいない。ここで抜けないと、番号で
                # 答えただけの「2番」まで合図として消えてしまう。
                if n is not None and len(live) > 1:
                    if 1 <= n <= len(live):
                        write_atomic(route_file(log_path),
                                     str(live[n - 1]["pid"]))
                        note_voice_cmd(log_path, "route",
                                       f"{n}. {live[n - 1]['label']}", text)
                    else:
                        # 無い番号。黙って捨てると「言ったのに変わらない」に
                        # なるので、画面に出して知らせる。
                        note_voice_cmd(log_path, "route_missing", str(n), text)
                    print(f"(声で送信先) {text[:40]}", file=sys.stderr, flush=True)
                    speaking_since = None
                    continue

                # 発話が始まった時点から今までにミュートを挟んだか、
                # あるいは今なお切られているなら、その発話は送らない。
                started_at, speaking_since = speaking_since, None
                if muted_now or (started_at is not None and started_at != mute_generation):
                    print(f"(マイク切) {text[:40]}", file=sys.stderr, flush=True)
                    continue

                # 終わりに「キャンセル」が来たら、その一言ごと捨てる。
                if take_tail(text, CANCEL_TAIL) is not None:
                    note_voice_cmd(log_path, "cancelled", "", text)
                    print(f"(取り消し) {text[:40]}", file=sys.stderr, flush=True)
                    continue

                # 終わりに「手直し」が来たら、送らずに下書きへ回す。
                # 短くても落とさない（本人が意図して回しているため）。
                body = take_tail(text, HOLD_TAIL)
                force_hold = body is not None
                if force_hold:
                    if not body:
                        note_voice_cmd(log_path, "cancelled", "", text)
                        print(f"(手直し・空) {text[:40]}", file=sys.stderr, flush=True)
                        continue
                    text = body

                if not force_hold and len(text) < args.min_chars:
                    continue

                def drop(kind: str):
                    """送らなかったことを端末に残す（Claude には渡さない）。"""
                    print(f"({kind}) {text[:40]}", file=sys.stderr, flush=True)

                # 組み込みと辞書をまとめて判定する（辞書は毎回読むので即反映）
                if not force_hold and not args.keep_noise \
                        and is_noise(text, user_dict["ignore"]):
                    drop("無視")
                    continue
                if args.drop_non_japanese and looks_non_japanese(text):
                    drop("日本語以外")
                    continue

                text = polish(text, user_dict, args.keep_kanji_numbers,
                              args.strip_fillers)
                stamp = time.strftime("%H:%M:%S")

                # 一時停止中は保留ファイルへ。Claude には送られない。
                # （ビューアが時刻を表示するので、こちらには残す）
                if force_hold or pause_path.exists():
                    with open(hold_path, "a") as h:
                        h.write(json.dumps({"time": stamp, "text": text},
                                           ensure_ascii=False) + "\n")
                    print(f"[{stamp}] (保留) {text}", file=sys.stderr, flush=True)
                    if force_hold:
                        note_voice_cmd(log_path, "held", "", text)
                    continue

                # Claude に渡る行は本文だけにする。時刻や言語は使わないので載せない。
                # 送信先が選ばれているときだけ宛先を添える（無い行は全員へ）。
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
