#!/usr/bin/env python3
"""Pass through only the utterance log lines addressed to me.

voice-shell.sh listen slots this in behind tail. When a destination is picked
in the viewer, the daemon tags every line with "to" (the PID it is for).
A line with no tag is for everyone.

    tail -F utterances.jsonl | listen_filter.py <my PID>

Write line by line (-u and flush). Buffering stretches the gap between
speaking and arriving.

Long utterances get split here. Monitor drops the end of a line that is too
long, so passing one through whole means the close of what was said never
reaches the AI. Japanese puts 「〜してほしい」 last, so the request itself is
what vanishes. Only this path splits. utterances.jsonl and the viewer history
keep one line per utterance.
"""
import json
import sys

# How much Monitor carries on one line. Measured, a JSON line was cut off past
# 500 characters. Not bytes (Japanese and ASCII both cut at the same 490th
# character). The limit itself is documented nowhere, so split with room left.
SAFE_LINE = 450

# Order to look for a split point. A full stop reads best, then a comma, then a space.
STRONG_BREAKS = "。！？"
WEAK_BREAKS = "、，,；;"
ASCII_STOPS = ".!?"


def _dump(rec, text):
    """Swap in a different text and rebuild the one-line JSON.

    Dropping "to" or "edited" would break the destination filter and how the
    line is treated, so every key of the original line is carried over.
    ensure_ascii=False because opening Japanese out into \\uXXXX blows one
    character up to six and defeats the point of splitting.
    """
    return json.dumps(dict(rec, text=text), ensure_ascii=False)


def _fit(rec, text, budget):
    """Squeeze budget down until the JSON form fits.

    Quotes and newlines grow when escaped, so subtracting character counts is
    not enough. Subtracting the overflow as it is cuts down to a single
    character when the growth is large, leaving a pile of scraps. Squeeze by
    the ratio it grew, only as far as needed.
    """
    room = SAFE_LINE - len(_dump(rec, ""))
    while budget > 1:
        used = len(_dump(rec, text[:budget])) - len(_dump(rec, ""))
        if used <= room:
            return budget
        budget = max(1, min(budget - 1, budget * room // used))
    return 1


def _last_break(text, limit, kind, floor):
    """Search backward from limit for a spot usable as a break.

    Nothing before floor is picked. Too short a first half leaves more behind
    and adds splits.
    """
    for i in range(limit - 1, floor - 1, -1):
        ch = text[i]
        if kind == "strong":
            if ch in STRONG_BREAKS:
                return i + 1
            # English full stop. Only when a space follows, so 3.14 stays whole.
            if ch in ASCII_STOPS and (text[i + 1:i + 2] or " ") == " ":
                return i + 1
        elif kind == "weak":
            if ch in WEAK_BREAKS:
                return i + 1
        elif ch == " ":
            return i + 1
    return 0


def _cut_at(text, budget):
    """Decide where to cut, inside budget characters.

    Look for a full stop, then a comma, then a space. If none turn up, cut at
    budget as it is. An utterance carried on one breath can hold no full stop
    at all, so always leave a way to cut.
    """
    limit = min(budget, len(text))
    floor = max(1, limit // 2)
    for kind in ("strong", "weak", "space"):
        pos = _last_break(text, limit, kind, floor)
        if pos:
            return pos
    return budget


def split_line(rec, line):
    """Split one line into lines short enough that Monitor keeps them.

    If no split is needed, the original line comes back as it is. Everyday
    short utterances pass straight through, with no rebuilding and no wait.
    """
    text = rec.get("text")
    if not isinstance(text, str):
        return [line]           # leave non-utterance lines (system_warning etc.) alone
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
            print(line, flush=True)   # keep unreadable lines, never drop one silently
            continue
        to = rec.get("to")
        if to is not None and str(to) != me:
            continue
        # Write the split pieces back to back. Monitor bundles lines emitted
        # close in time into one notification, and bundling only caps each
        # line, so no gap is needed. Landing in the same notification is
        # better anyway, the reader sees all of it before acting.
        for out in split_line(rec, line):
            print(out, flush=True)


if __name__ == "__main__":
    main()
