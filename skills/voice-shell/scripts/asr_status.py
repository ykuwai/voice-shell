#!/usr/bin/env python3
"""ブラウザ認識がいま実際に聞いているかを、人が読める形で出す。

voice-shell.sh status が使う。標準入力に /api/asr-status の応答を渡す。

これを見ないと、「画面を開いていない」「マイクを拒否された」状態と、
ちゃんと聞いている状態を外から区別できない。区別できないまま
「どうぞ話してください」と言うと、届かない先に話させることになる。
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
