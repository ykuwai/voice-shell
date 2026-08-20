#!/usr/bin/env python3
"""Say, in a form a person can read, whether browser recognition is listening.

voice-shell.sh status uses this. Feed it the /api/asr-status response on stdin.

Without this there is no way from outside to tell the "page never opened" and
"mic was denied" states apart from actually listening. Telling someone to go
ahead and speak while those look the same sends them talking into a void.
"""
import json
import sys


def main():
    try:
        d = json.load(sys.stdin)
    except (ValueError, OSError):
        print("  画面の状態を確認できませんでした")
        return

    if d.get("listening"):
        print(f"  聞いています（画面 {d['listening']} つ）")
    elif d.get("denied"):
        print("  マイクを拒否されています。Chrome の許可を出し直してください。")
    elif d.get("tabs"):
        print("  画面は開いていますが、まだ聞いていません。")
    else:
        print("  画面が開かれていません。Chrome で上の URL を開いてください。")
        print("  開くまでは、話しても何も届きません。")


if __name__ == "__main__":
    main()
