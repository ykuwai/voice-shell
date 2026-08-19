#!/usr/bin/env python3
"""発話ログの行を、自分宛てのものだけに絞って流す。

voice-shell.sh listen が tail の後ろに挟む。ビューアで送信先を選ぶと、
デーモンが各行に "to"（宛先の PID）を付ける。指定の無い行は全員宛て。

    tail -F utterances.jsonl | listen_filter.py <自分のPID>

行ごとに送り出す（-u と flush）。溜めると、話してから届くまでが延びる。
"""
import json
import sys


def main():
    me = sys.argv[1] if len(sys.argv) > 1 else ""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            to = json.loads(line).get("to")
        except ValueError:
            to = None          # 読めない行は落とさない（取りこぼしを作らない）
        if to is None or str(to) == me:
            print(line, flush=True)


if __name__ == "__main__":
    main()
