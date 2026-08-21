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
        print("  Could not check the state of the screen")
        return

    if d.get("listening"):
        print(f"  Listening ({d['listening']} screens)")
    elif d.get("denied"):
        print("  The microphone was refused. Allow it again in Chrome.")
    elif d.get("tabs"):
        print("  The screen is open but it is not listening yet.")
    else:
        print("  The screen is not open. Open the URL above in Chrome.")
        print("  Until it is open, nothing arrives however much you speak.")


if __name__ == "__main__":
    main()
