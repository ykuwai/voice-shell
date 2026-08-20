#!/usr/bin/env python3
"""発話ログの行を、自分宛てのものだけに絞って流す。

voice-shell.sh listen が tail の後ろに挟む。ビューアで送信先を選ぶと、
デーモンが各行に "to"（宛先の PID）を付ける。指定の無い行は全員宛て。

    tail -F utterances.jsonl | listen_filter.py <自分のPID>

行ごとに送り出す（-u と flush）。溜めると、話してから届くまでが延びる。

長い発話はここで複数行に割る。Monitor は1行が長すぎると末尾を落とすので、
そのまま流すと話の結びが AI に届かない。日本語は「〜してほしい」が最後に
来るため、依頼そのものが消える。割るのはこの経路だけで、utterances.jsonl
とビューアの履歴は1行1発話のまま残る。
"""
import json
import sys

# Monitor が1行で運べる長さ。実測すると、JSON にした行が 500 文字を超えた
# ところから先が落ちた。バイト数ではない（日本語もアスキーも同じ 490 文字目で
# 切れた）。上限そのものはどこにも書かれていないので、余裕を引いて割る。
SAFE_LINE = 450

# 割る位置を探す順。句点で切れれば読みやすく、無ければ読点、それも無ければ空白。
STRONG_BREAKS = "。！？"
WEAK_BREAKS = "、，,；;"
ASCII_STOPS = ".!?"


def _dump(rec, text):
    """text だけ差し替えて1行の JSON に戻す。

    "to" や "edited" を落とすと宛先の絞り込みや扱いが壊れるので、
    元の行のキーはそのまま持ち越す。ensure_ascii=False なのは、
    日本語を \\uXXXX に開くと1文字が6文字に膨らんで割った意味が消えるため。
    """
    return json.dumps(dict(rec, text=text), ensure_ascii=False)


def _fit(rec, text, budget):
    """JSON にしたときに収まるところまで budget を詰める。

    引用符や改行はエスケープで伸びるので、文字数の引き算だけでは足りない。
    はみ出した分をそのまま引くと、伸び方が大きいときに 1 文字まで削れて
    細切れの山になる。伸びた比で詰めて、必要な分だけ縮める。
    """
    room = SAFE_LINE - len(_dump(rec, ""))
    while budget > 1:
        used = len(_dump(rec, text[:budget])) - len(_dump(rec, ""))
        if used <= room:
            return budget
        budget = max(1, min(budget - 1, budget * room // used))
    return 1


def _last_break(text, limit, kind, floor):
    """limit より手前で、区切りに使える位置を後ろから探す。

    floor より手前は選ばない。前半が短すぎると残りが伸びて割る回数が増える。
    """
    for i in range(limit - 1, floor - 1, -1):
        ch = text[i]
        if kind == "strong":
            if ch in STRONG_BREAKS:
                return i + 1
            # 英語の句点。3.14 のような小数で切らないよう、直後が空白のときだけ
            if ch in ASCII_STOPS and (text[i + 1:i + 2] or " ") == " ":
                return i + 1
        elif kind == "weak":
            if ch in WEAK_BREAKS:
                return i + 1
        elif ch == " ":
            return i + 1
    return 0


def _cut_at(text, budget):
    """budget 文字以内で、どこで切るかを決める。

    句点、読点、空白の順に探す。どれも見つからなければ budget でそのまま切る。
    一息で続く発話には句点が1つも無いことがあるので、必ず切れる道を残す。
    """
    limit = min(budget, len(text))
    floor = max(1, limit // 2)
    for kind in ("strong", "weak", "space"):
        pos = _last_break(text, limit, kind, floor)
        if pos:
            return pos
    return budget


def split_line(rec, line):
    """1行を、Monitor が落とさない長さの複数行に割る。

    割る必要が無ければ元の行をそのまま返す。普段の短い発話は素通しで、
    余計な作り直しも待ち時間も挟まない。
    """
    text = rec.get("text")
    if not isinstance(text, str):
        return [line]           # 発話ではない行（system_warning など）は触らない
    base = SAFE_LINE - len(_dump(rec, ""))
    if base < 1 or len(_dump(rec, text)) <= SAFE_LINE:
        return [line]
    out = []
    rest = text
    while rest:
        budget = _fit(rec, rest, base)
        if len(rest) <= budget:
            out.append(_dump(rec, rest))
            break
        cut = _cut_at(rest, budget)
        piece = rest[:cut].rstrip()
        if piece:
            out.append(_dump(rec, piece))
        rest = rest[cut:].lstrip()
    return out or [line]


def main():
    me = sys.argv[1] if len(sys.argv) > 1 else ""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            rec = None
        if not isinstance(rec, dict):
            print(line, flush=True)   # 読めない行は落とさない（取りこぼしを作らない）
            continue
        to = rec.get("to")
        if to is not None and str(to) != me:
            continue
        # 割れた分は続けて書く。Monitor は近い時刻に出た行を1つの通知にまとめ、
        # まとめても行ごとに上限が掛かるだけなので、間を空ける必要は無い。
        # むしろ同じ通知に並ぶほうが、受け手が全部を見てから動ける。
        for out in split_line(rec, line):
            print(out, flush=True)


if __name__ == "__main__":
    main()
