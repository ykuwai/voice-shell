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
import json
import os
import re
import signal
import sys
import time
from pathlib import Path

import asr_mic

STATE_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "qwen-voice"

# ユーザー辞書。再起動をまたいで残したいので設定ディレクトリに置く。
# Web UI から編集でき、変更は次の発話からすぐ効く（デーモン再起動は不要）。
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME",
                                 Path.home() / ".config")) / "voice-shell"
DICT_FILE = CONFIG_DIR / "dictionary.json"
PID_FILE = STATE_DIR / "daemon.pid"
LOG_FILE = STATE_DIR / "utterances.jsonl"
# 認識途中のテキスト。上書きし続けるだけで履歴は残さない（ビューアの表示用）。
PARTIAL_FILE = STATE_DIR / "partial.txt"
# このファイルがあると発話を保留する。認識は続くが Claude には送らず、
# 保留トレイに溜めて手直ししてから送れる。
PAUSE_FILE = STATE_DIR / "paused"
# 保留中に確定した発話の置き場。
HOLD_FILE = STATE_DIR / "held.jsonl"
# このファイルがあるとマイクを切った扱い。認識結果をどこにも残さず捨てる。
# デーモンを止めると再起動に1〜2分かかるので、こちらで無視するだけにする。
MUTE_FILE = STATE_DIR / "muted"

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


_dict_cache = (None, None)   # (更新時刻, 中身)


def load_dictionary() -> dict:
    """ユーザー辞書を読む。壊れていても落とさず既定値で動かす。

    発話ごとに呼ばれるので、更新時刻が変わったときだけ読み直す。
    これにより Web UI での編集がデーモン再起動なしで反映される。
    """
    global _dict_cache
    try:
        mtime = DICT_FILE.stat().st_mtime
    except OSError:
        return DEFAULT_DICT

    if _dict_cache[0] == mtime:
        return _dict_cache[1]

    try:
        data = json.loads(DICT_FILE.read_text())
    except (json.JSONDecodeError, OSError) as e:
        print(f"辞書を読めませんでした ({e}) — 既定値で動かします", file=sys.stderr)
        return DEFAULT_DICT

    d = {
        "ignore": [s for s in data.get("ignore", []) if isinstance(s, str)],
        "replace": {k: v for k, v in data.get("replace", {}).items()
                    if isinstance(k, str) and isinstance(v, str)},
    }
    _dict_cache = (mtime, d)
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


def apply_replacements(text: str, replace: dict) -> str:
    """辞書の置換を適用する。長い語から当てて部分一致の取りこぼしを防ぐ。"""
    for src in sorted(replace, key=len, reverse=True):
        if src:
            text = text.replace(src, replace[src])
    return text


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
    p.add_argument("--min-chars", type=int, default=2,
                   help="この文字数未満の発話は無視する（相槌や雑音よけ）")
    p.add_argument("--keep-noise", action="store_true",
                   help="「はい」「うん」等の相槌も送る（既定では捨てる）")
    p.add_argument("--keep-kanji-numbers", action="store_true",
                   help="漢数字をそのまま送る（既定は「三十秒」→「30秒」に直す）")
    p.add_argument("--drop-non-japanese", action="store_true",
                   help="中国語・韓国語等を含む発話を捨てる（既定では送る。"
                        "意図して他言語を話すことがあるため既定は無効）")
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
    log_path = Path(args.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    # 起動のたびに空にする（前回の発話を拾わせない）
    log_path.write_text("")

    save_default_dictionary()

    print("モデルを読み込み中… (初回は数分かかります)", file=sys.stderr)
    model = asr_mic.load_model(args)

    PID_FILE.write_text(str(os.getpid()))
    print(f"\n  聞いています — 喋ると {log_path} に追記します"
          f"\n  Ctrl-C で終了\n", file=sys.stderr, flush=True)

    try:
        partial_path = log_path.parent / PARTIAL_FILE.name
        pause_path = log_path.parent / PAUSE_FILE.name
        hold_path = log_path.parent / HOLD_FILE.name
        mute_path = log_path.parent / MUTE_FILE.name
        partial_path.write_text("")
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

                text = apply_replacements(text, user_dict["replace"])
                if not args.keep_kanji_numbers:
                    text = kanji_numbers_to_arabic(text)
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
