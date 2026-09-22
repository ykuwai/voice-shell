#!/usr/bin/env python3
"""Pass through only the utterance log lines addressed to me.

voice-shell.sh listen slots this in behind tail. The daemon tags every
utterance with "to" (the PID it is for). A line with no tag, or one addressed
to somebody else, is dropped here (#73, not arriving beats arriving at the
wrong desk). A system_warning carries "to" only when it is about one
particular session (a session being told it was just disconnected, say), and
is filtered the same as any other line then. Left off "to" altogether, a
system_warning is about the act of listening itself (two sessions listening
at once, say), and reaches every session regardless of who utterances are
being routed to.

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
import os
import sys
import threading
import time

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


# How the reader side's state reads back through NtQueryInformationFile
# (FilePipeLocalInformation). CLOSING means whoever was reading our stdout,
# Monitor, has gone away.
_FILE_PIPE_LOCAL_INFORMATION = 24
_FILE_PIPE_CLOSING_STATE = 4


def _exit_when_reader_gone(every=5.0):
    """On Windows, quit once nobody reads our stdout any more.

    When a Monitor watch expires on Windows, Claude Code does not always take
    down the whole listen tree. The part left behind never notices, because
    it only writes when an utterance is addressed to it, and one addressed to
    a session that has ended never comes. Meanwhile its heal loop keeps
    touching the registration, so the ended session sits in the destination
    row for good. Measured: a closed reader flips the pipe state from
    CONNECTED (3) to CLOSING (4), while an empty write still succeeds and a
    PeekNamedPipe on the write end is refused, so the pipe state is the one
    reliable signal. Exiting ends the pipeline `listen` waits on, and its
    EXIT trap removes the registration.

    POSIX needs none of this (a closed reader and SIGPIPE, or the process
    group going down with the watch, already take care of it).
    """
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        import msvcrt
        from ctypes import wintypes

        class _IoStatus(ctypes.Structure):
            _fields_ = [("Status", ctypes.c_void_p), ("Information", ctypes.c_void_p)]

        class _PipeLocalInfo(ctypes.Structure):
            _fields_ = [(n, wintypes.ULONG) for n in (
                "NamedPipeType", "NamedPipeConfiguration", "MaximumInstances",
                "CurrentInstances", "InboundQuota", "ReadDataAvailable",
                "OutboundQuota", "WriteQuotaAvailable", "NamedPipeState",
                "NamedPipeEnd")]

        handle = wintypes.HANDLE(msvcrt.get_osfhandle(sys.stdout.fileno()))
        query = ctypes.windll.ntdll.NtQueryInformationFile
    except Exception:
        return

    def state():
        io, info = _IoStatus(), _PipeLocalInfo()
        status = query(handle, ctypes.byref(io), ctypes.byref(info),
                       ctypes.sizeof(info), _FILE_PIPE_LOCAL_INFORMATION)
        return info.NamedPipeState if status == 0 else None

    # Not a pipe at all (a console, a file): there is no reader to lose.
    if state() is None:
        return

    def watch():
        while True:
            time.sleep(every)
            if state() == _FILE_PIPE_CLOSING_STATE:
                os._exit(0)

    threading.Thread(target=watch, daemon=True).start()


class _Progress:
    """How far into the log this listen has handled, in bytes.

    Written after every line that was either delivered or not meant for us,
    never after one whose write failed. When a Monitor watch expires, the
    next listen of this session starts reading from here, so an utterance
    that arrived while nobody was reading is handed on instead of lost.
    """

    def __init__(self):
        self.path = os.environ.get("VOICE_SHELL_PROGRESS") or None
        # The daemon empties the log each time it starts and writes a new
        # epoch next to it. An offset only means something within one epoch,
        # so the two are recorded together.
        self.epoch_file = os.environ.get("VOICE_SHELL_EPOCH_FILE") or None
        self.epoch = self._read_epoch()
        try:
            self.offset = int(os.environ.get("VOICE_SHELL_START_OFFSET", ""))
        except ValueError:
            self.path = None
            self.offset = 0
        self.advance(0)             # on record from the start, before any line

    def _read_epoch(self):
        if not self.epoch_file:
            return ""
        try:
            with open(self.epoch_file, encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            return ""

    def check(self):
        """The log was emptied under us (tail -F starts over from its top)."""
        now = self._read_epoch()
        if now != self.epoch:
            self.epoch, self.offset = now, 0

    def advance(self, n):
        self.offset += n
        if not self.path:
            return
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(f"{self.epoch or '-'} {self.offset}")
            os.replace(tmp, self.path)
        except OSError:
            pass


def _emit(lines):
    """Write the lines out. If the reader is already gone, stop here, with
    the progress left pointing at this line so the next listen replays it."""
    for out in lines:
        try:
            print(out, flush=True)
        except (OSError, ValueError):
            os._exit(0)


def main():
    # The first id is this listen's own. Any after it are earlier PIDs of the
    # same session, whose utterances it picks up on a re-arm. Those count only
    # for lines written before the handover (VOICE_SHELL_ALIAS_UNTIL): Windows
    # hands PIDs out again, and a later listen of some other session could get
    # the same number.
    me = sys.argv[1] if len(sys.argv) > 1 else ""
    aliases = set(sys.argv[2:])
    try:
        alias_until = int(os.environ.get("VOICE_SHELL_ALIAS_UNTIL", ""))
    except ValueError:
        alias_until = 0
    _exit_when_reader_gone()
    progress = _Progress()
    for raw in sys.stdin.buffer:
        progress.check()
        size = len(raw)
        if not raw.endswith(b"\n"):
            break                   # a half-written last line, read again next time
        line = raw.decode("utf-8", errors="replace").strip()
        if not line:
            progress.advance(size)
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            rec = None
        if not isinstance(rec, dict):
            _emit([line])   # keep unreadable lines, never drop one silently
            progress.advance(size)
            continue
        # A "to" on a system_warning means it is about one session in
        # particular, so it is filtered exactly like any other line. Left off,
        # it is a notice about the act of listening itself (two sessions
        # listening at once, say), and every session sees it.
        to = rec.get("to")
        mine = {me} | (aliases if progress.offset < alias_until else set())
        if to is not None:
            if str(to) not in mine:
                progress.advance(size)
                continue
        elif "system_warning" not in rec:
            progress.advance(size)
            continue
        # Write the split pieces back to back. Monitor bundles lines emitted
        # close in time into one notification, and bundling only caps each
        # line, so no gap is needed. Landing in the same notification is
        # better anyway, the reader sees all of it before acting.
        _emit(split_line(rec, line))
        progress.advance(size)


if __name__ == "__main__":
    main()
