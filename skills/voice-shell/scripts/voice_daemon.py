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
import fcntl
import json
import os
import re
import signal
import sys
import threading
import time
from pathlib import Path

import asr_mic

STATE_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "qwen-voice"

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
        data = json.loads(path.read_text())
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
        DICT_FILE.write_text(json.dumps(DEFAULT_DICT, ensure_ascii=False, indent=2) + "\n")
        return

    try:
        cur = json.loads(DICT_FILE.read_text())
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
    DICT_FILE.write_text(json.dumps(cur, ensure_ascii=False, indent=2) + "\n")
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
    return p.parse_args()


def read_pid():
    try:
        pid = int(PID_FILE.read_text())
        os.kill(pid, 0)          # 生存確認（シグナルは送らない）
        return pid
    except (FileNotFoundError, ValueError, ProcessLookupError):
        return None


def main():
    args = parse_args()

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
        fcntl.flock(_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        sys.exit("すでに起動しています（読み込み中かもしれません）。")
    globals()["_daemon_lock"] = _lock   # 閉じると解放されるので握り続ける

    log_path = Path(args.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    # 起動のたびに空にする（前回の発話を拾わせない）
    log_path.write_text("")

    save_default_dictionary()

    # ビューアから指定されたマイクを毎回見る（切り替えは録音だけ入れ替える）
    mic_path = Path(args.log_file).parent / MIC_FILE.name
    mic_path.write_text(args.device)

    def want_device():
        try:
            return mic_path.read_text().strip() or None
        except OSError:
            return None

    args.want_device = want_device

    # マイク感度と確定までの無音秒数もビューアから触れる。録音の入れ替えすら
    # 要らず、次に読み直した時点から効く。ファイルが無ければ今の値で作る。
    def want_tuning():
        try:
            return json.loads(TUNING_FILE.read_text())
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

    # 足りない項目を今の値で埋める。ファイルが既にある人にも新しい項目が
    # 行き渡るようにする（無いままだとビューアのつまみが効かない）。
    filled = dict(saved)
    for key in ("silence_threshold", "silence_duration", "min_chars",
                "strip_fillers"):
        filled.setdefault(key, getattr(args, key))
    if filled != saved:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        TUNING_FILE.write_text(json.dumps(filled, indent=2) + "\n")

    print("モデルを読み込み中… (初回は数分かかります)", file=sys.stderr)
    model = asr_mic.load_model(args)

    # LAN からの接続とローカルマイクが同じモデルを触るので、ロックで並べる。
    # クラウドのエンジンを使うときは接続情報しか持たないので包まない。
    if args.remote and args.engine == "local":
        model = LockedModel(model)

    if args.remote:
        start_remote_server(model, args)

    PID_FILE.write_text(str(os.getpid()))
    print(f"\n  聞いています — 喋ると {log_path} に追記します"
          f"\n  Ctrl-C で終了\n", file=sys.stderr, flush=True)

    try:
        partial_path = log_path.parent / PARTIAL_FILE.name
        level_path = log_path.parent / LEVEL_FILE.name
        pause_path = log_path.parent / PAUSE_FILE.name
        hold_path = log_path.parent / HOLD_FILE.name
        mute_path = log_path.parent / MUTE_FILE.name
        partial_path.write_text("")
        level_path.write_text("0 0")
        pause_path.unlink(missing_ok=True)   # 起動時は必ず送信状態から
        mute_path.unlink(missing_ok=True)
        hold_path.write_text("")

        # 認識は発話単位で確定するため、確定時点のミュート状態だけを見ると
        # 「切っている間に話した音声」が解除後に流れ込む（ところてん現象）。
        #
        # そこで「マイクが切られた回数」を数え、発話が始まった時点の値を覚えておく。
        # 確定時に値が変わっていれば、その発話はミュートをまたいだので捨てる。
        # 単純なフラグだと、ミュート中に拾った物音の確定がフラグを消費してしまい、
        # 直後の本当の発話が巻き込まれる／取りこぼす。
        mute_generation = 0
        was_muted = False
        speaking_since = None   # いま進行中の発話が始まった時点の generation

        with open(log_path, "a", buffering=1) as f:   # 行バッファで即 flush
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
                        f"{ev.get('rms', 0):.4f} {int(bool(ev.get('speaking')))}")
                    if ev.get("speaking") and speaking_since is None:
                        speaking_since = mute_generation
                    if muted_now:
                        if partial_path.read_text():
                            partial_path.write_text("")
                        continue
                    continue

                if muted_now:
                    # ミュート中の途中経過は残さない。確定は下でまとめて判定する。
                    if ev["type"] != "final":
                        if partial_path.read_text():
                            partial_path.write_text("")
                        continue

                if ev["type"] == "partial":
                    # 途中経過は別ファイルに上書き（プロンプトのログは汚さない）
                    partial_path.write_text(ev["text"])
                    continue
                if ev["type"] != "final":
                    continue

                partial_path.write_text("")

                # 発話が始まった時点から今までにミュートを挟んだか、
                # あるいは今なお切られているなら、その発話は送らない。
                started_at, speaking_since = speaking_since, None
                if muted_now or (started_at is not None and started_at != mute_generation):
                    print(f"(マイク切) {ev['text'].strip()[:40]}", file=sys.stderr, flush=True)
                    continue

                text = ev["text"].strip()
                if len(text) < args.min_chars:
                    continue

                # 辞書は毎回読む。Web UI で直した内容が次の発話から効くようにする。
                user_dict = load_dictionary()

                def drop(kind: str):
                    """送らなかったことを端末に残す（Claude には渡さない）。"""
                    print(f"({kind}) {text[:40]}", file=sys.stderr, flush=True)

                # 組み込みと辞書をまとめて判定する（辞書は毎回読むので即反映）
                if not args.keep_noise and is_noise(text, user_dict["ignore"]):
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
                if pause_path.exists():
                    with open(hold_path, "a") as h:
                        h.write(json.dumps({"time": stamp, "text": text},
                                           ensure_ascii=False) + "\n")
                    print(f"[{stamp}] (保留) {text}", file=sys.stderr, flush=True)
                    continue

                # Claude に渡る行は本文だけにする。時刻や言語は使わないので載せない。
                f.write(json.dumps({"text": text}, ensure_ascii=False) + "\n")
                print(f"[{stamp}] {text}", file=sys.stderr, flush=True)
    except KeyboardInterrupt:
        print("\n終了します。", file=sys.stderr)
    finally:
        PID_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
