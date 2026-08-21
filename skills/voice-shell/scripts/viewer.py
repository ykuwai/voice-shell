#!/usr/bin/env python3
"""Live viewer for voice prompts.

It only tails the JSONL voice_daemon.py writes out and pushes it to the browser.
It uses neither GPU nor mic, so it can run alongside voice mode.

    python viewer.py            # → http://127.0.0.1:8090
"""
import argparse
import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from aiohttp import web, WSCloseCode

# For the same reason as voice_daemon.py (the "/tmp" mismatch on Windows),
# a real path handed over by voice-shell.sh wins if there is one.
if os.environ.get("VOICE_SHELL_STATE_DIR"):
    DEFAULT_LOG = Path(os.environ["VOICE_SHELL_STATE_DIR"]) / "utterances.jsonl"
else:
    # The name changed from "qwen-voice". Same reason as voice_daemon.py, if the
    # old one is still around and the new one is not, keep using the old one.
    _base = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp"))
    _state = _base / "voice-shell"
    if not _state.exists() and (_base / "qwen-voice").exists():
        _state = _base / "qwen-voice"
    DEFAULT_LOG = _state / "utterances.jsonl"

# The user dictionary. Read and written in the same place as voice_daemon.py.
_CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "voice-shell"
DICT_FILE = _CONFIG / "dictionary.json"
# Mic sensitivity and the seconds of silence before settling. The daemon rereads
# them every 0.5 seconds, so writing them is enough, with no restart.
TUNING_FILE = _CONFIG / "tuning.json"
# The range it is safe to touch. A value outside it makes recognition look like
# it stopped dead, so the server always clamps it too (room noise sits around
# 0.003, the macOS default is 0.015).
TUNING_RANGE = {"silence_threshold": (0.003, 0.15),
                # the knob stops at 10 seconds, but leave room above for slow talkers
                "silence_duration": (0.3, 30.0),
                "min_chars": (1, 40),
                # in browser recognition, cut the mic once no voice for this long.
                # 0 never cuts. No reconnecting to Google through unused time.
                "idle_mute_min": (0, 30)}
# the ones held as on and off rather than a number
TUNING_FLAGS = {"strip_fillers"}
# the ones held as integers. Left as floats, comparing character counts reads badly.
TUNING_INT = {"min_chars", "idle_mute_min"}


def _builtin_noise() -> list:
    """Read the words voice_daemon.py ignores from the start (for display).

    They should show even with the daemon not running, so they are picked out
    of the source rather than imported.
    """
    try:
        import ast
        src = (Path(__file__).with_name("voice_daemon.py")).read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                    getattr(t, "id", None) == "NOISE_ONLY" for t in node.targets):
                return sorted(ast.literal_eval(node.value), key=lambda s: (len(s), s))
    except Exception:
        pass
    return []


def _read_dict(raw: bool = False, path: Path = None) -> dict:
    """Read the dictionary. Missing or broken, it comes back empty.

    raw=True gives it back as it is, internal keys (_seen) included.
    """
    try:
        data = json.loads((path or DICT_FILE).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"ignore": [], "unignore": [], "replace": {}}
    if raw:
        return data
    return {"ignore": data.get("ignore", []) or [],
            "unignore": data.get("unignore", []) or [],
            "replace": data.get("replace", {}) or {}}


def _keep_unignore(sent, prev: dict) -> list:
    """Gather the words taken out of the built-in list.

    The page can only put up chips for the words currently in the built-in
    list, so only that much ever comes back. Replacing everything with what
    arrives means that on a day a word leaves the built-in list, or when the
    list could not be read, a word the user took out quietly goes back to being
    ignored. Whatever could not become a chip stays as it was and is added on.
    """
    builtin = set(_builtin_noise())
    now = {s.strip() for s in sent if isinstance(s, str) and s.strip()}
    # Words that had a chip go by what arrives, since one pressed back in never
    # arrives. Words with no chip (gone from built-ins, list unreadable) stay.
    kept = {s.strip() for s in prev.get("unignore", []) or []
            if isinstance(s, str) and s.strip() and s.strip() not in builtin}
    return sorted(now | kept)


def parse_args():
    p = argparse.ArgumentParser(description="音声プロンプトのライブビューア")
    p.add_argument("--log-file", default=str(DEFAULT_LOG), help="追尾する JSONL")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8090)
    return p.parse_args()


class Tail:
    """Tail the JSONL and hand new lines out to the subscribers."""

    def __init__(self, path: Path):
        self.path = path
        self.clients: set[web.WebSocketResponse] = set()
        self.history: list[dict] = []

    def read_existing(self):
        """Read everything up to startup (open it later, the history is there)."""
        if not self.path.exists():
            return
        with open(self.path) as f:
            for line in f:
                rec = self._parse(line)
                if rec and "system_warning" not in rec:
                    self.history.append(rec)

    @staticmethod
    def _parse(line: str):
        line = line.strip()
        if not line:
            return None
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return None

    async def watch(self):
        """Keep following the end of the file. Not there yet, wait for it."""
        while not self.path.exists():
            await asyncio.sleep(1)

        with open(self.path) as f:
            f.seek(0, os.SEEK_END)
            while True:
                line = f.readline()
                if not line:
                    # follow along when a daemon restart rebuilt the file
                    try:
                        if self.path.stat().st_size < f.tell():
                            f.seek(0)
                    except FileNotFoundError:
                        pass
                    await asyncio.sleep(0.25)
                    continue

                rec = self._parse(line)
                # system_warning is addressed to Claude Code (the side watching
                # this log directly through Monitor). Mixed into the browser's
                # utterance list it looks broken, so it is not pushed.
                if rec and "system_warning" not in rec:
                    self.history.append(rec)
                    await self.broadcast(rec)

    async def broadcast(self, rec: dict):
        payload = json.dumps(rec, ensure_ascii=False)
        for ws in list(self.clients):
            try:
                await ws.send_str(payload)
            except Exception:
                self.clients.discard(ws)

    async def watch_partial(self):
        """Push the mid-recognition text (reading the file the daemon overwrites)."""
        path = self.path.parent / "partial.txt"
        last = None
        while True:
            try:
                text = path.read_text(encoding="utf-8")
            except (FileNotFoundError, OSError):
                text = ""
            if text != last:
                last = text
                await self.broadcast({"partial": text})
            await asyncio.sleep(0.2)

    async def watch_level(self):
        """Push the volume being picked up right now.

        When no text shows, you want to tell a dead mic from plain silence.
        The level.txt the daemon writes holds 2 numbers only, the volume and
        whether someone is speaking. The audio itself is never kept.
        """
        path = self.path.parent / "level.txt"
        last = None
        while True:
            try:
                rms, speaking = path.read_text(encoding="utf-8").split()
                cur = (round(float(rms), 3), speaking == "1")
            except (FileNotFoundError, OSError, ValueError):
                cur = (0.0, False)
            if cur != last:
                last = cur
                await self.broadcast({"level": cur[0], "speaking": cur[1]})
            await asyncio.sleep(0.1)      # about enough for the bar to look smooth

    async def watch_mic_active(self):
        """Push the mic the daemon side really finished switching to.

        The browser's "switched" message is optimistic, put up the moment the
        button is pressed, so this settles whether it really switched. The first
        one right after startup is sent too, but the browser toasts only the one
        that arrives after a switch was asked for.
        """
        path = self.path.parent / "mic_active"
        last = None
        while True:
            try:
                cur = path.read_text(encoding="utf-8").strip()
            except (FileNotFoundError, OSError):
                cur = None
            if cur and cur != last:
                last = cur
                await self.broadcast({"mic_active": cur})
            await asyncio.sleep(0.3)

    async def watch_muted(self):
        """Push the mic going on and off.

        It can be switched by voice (the daemon hears 「ミュート」 and makes the
        file), so changes happen that the page never pressed. Waiting on the
        /api/state that comes every 3 seconds means talking on without knowing
        whether it went off.
        """
        path = self.path.parent / "muted"
        last = None
        while True:
            cur = path.exists()
            if cur != last:
                await self.broadcast({"muted": cur})
                last = cur
            await asyncio.sleep(0.2)

    async def watch_paused(self):
        """Push whether it is holding things back.

        Like mute, this switches by voice too now, so waiting on the
        /api/state that comes every 3 seconds leaves the page behind.
        """
        path = self.path.parent / "paused"
        last = None
        while True:
            cur = path.exists()
            if cur != last:
                await self.broadcast({"paused": cur})
                last = cur
            await asyncio.sleep(0.2)

    async def watch_voice_cmd(self):
        """Push what happened to a voice signal.

        A signal is not sent as an utterance, so nothing on the page shows
        whether it went through. The voice_cmd.json the daemon writes goes
        along as it is, and the sound and the word are left to the browser.
        """
        path = self.path.parent / "voice_cmd.json"
        # Read once first to settle what was left over at the moment of opening.
        # Without this the first real signal to arrive counts as the first one
        # and gets skipped with no sound and no word.
        try:
            last = json.loads(path.read_text(encoding="utf-8")).get("at")
        except (OSError, ValueError, AttributeError):
            last = None
        while True:
            try:
                cur = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                cur = None
            at = cur.get("at") if isinstance(cur, dict) else None
            if at is not None and at != last:
                await self.broadcast({"voice_cmd": cur})
                last = at
            await asyncio.sleep(0.2)

    async def watch_held(self):
        """Push utterances settled while paused, only the ones newly added.

        The browser takes these and adds them to the end of the textarea. Send
        the whole text and it wrecks what is being edited, so only the
        difference goes.
        """
        path = self.path.parent / "held.jsonl"
        seen = 0
        while True:
            try:
                lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
            except (FileNotFoundError, OSError):
                lines = []

            if len(lines) < seen:        # reset by a send or a discard
                seen = 0
            for line in lines[seen:]:
                rec = self._parse(line)
                if rec:
                    await self.broadcast({"held": rec.get("text", "")})
            seen = len(lines)
            await asyncio.sleep(0.25)


async def main_async(args):
    page = Path(__file__).with_name("viewer.html")
    # The page is a skeleton and the rest of it lives beside it. They are named
    # one by one rather than served as a directory, so nothing outside this list
    # is ever reachable through the path in a request.
    ASSETS = {
        "/viewer.css": "text/css",
        "/viewer.js": "text/javascript",
        "/i18n.js": "text/javascript",
        "/icons.js": "text/javascript",
    }
    assets = {url: Path(__file__).with_name(url.lstrip("/")) for url in ASSETS}
    for f in [page, *assets.values()]:
        if not f.exists():
            sys.exit(f"{f} が見つかりません")

    tail = Tail(Path(args.log_file))
    tail.read_existing()

    async def handle_index(_req):
        # It gets edited during development, so let the browser cache nothing
        # (which heads off the accident where an old page's buttons do nothing)
        return web.FileResponse(page, headers={
            "Cache-Control": "no-store, must-revalidate",
        })

    def make_asset_handler(path, ctype):
        async def handle_asset(_req):
            # Same reasoning as the page. A cached stylesheet or script paired
            # with a fresh page is the same accident, only harder to spot.
            return web.FileResponse(path, headers={
                "Cache-Control": "no-store, must-revalidate",
                "Content-Type": f"{ctype}; charset=utf-8",
            })
        return handle_asset

    async def handle_ws(request):
        ws = web.WebSocketResponse(heartbeat=30)
        await ws.prepare(request)
        # Register as a subscriber first, then send the history. The other way
        # around, a line arriving while an await is open rides neither history
        # nor broadcast, and just that one goes missing.
        tail.clients.add(ws)
        for rec in list(tail.history):
            await ws.send_str(json.dumps(rec, ensure_ascii=False))
        try:
            async for _ in ws:
                pass
        finally:
            tail.clients.discard(ws)
        return ws

    state = Path(args.log_file).parent
    pause_file = state / "paused"
    hold_file = state / "held.jsonl"
    mute_file = state / "muted"

    pid_file = state / "daemon.pid"

    def _pid_alive(pid) -> bool:
        """Check it is alive without a signal (same reason as voice_daemon.py).
        os.kill(pid, 0) is unsupported on Windows and gives SystemError."""
        if sys.platform.startswith("win"):
            import ctypes
            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False

    def engine_running() -> bool:
        """Whether recognition is ready (the PID is written after loading)."""
        try:
            return _pid_alive(int(pid_file.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return False

    stopping = {"until": 0.0}   # right after a stop, do not misread it as loading
    starting = {"until": 0.0}   # right after a start, the process is not visible yet

    def engine_loading() -> bool:
        """Started but still getting ready.

        Even before a PID shows up, the daemon process itself is running.
        Without checking this, the page says stopped right after the press.

        Startup is detached though, so 0.1 to 0.3 seconds pass between the order
        and the process appearing in pgrep. The browser asks for state inside
        that window, so watching only for the process flips it back to stopped
        once. Remembering the order for a few seconds fills that window.

        The other way round, right after a stop the process can still be caught
        before it is fully gone, so the seconds after a stop never count as
        loading.
        """
        if engine_running() or time.monotonic() < stopping["until"]:
            return False
        if time.monotonic() < starting["until"]:
            return True
        # Where there is no pgrep (Windows) nothing can fill this momentary
        # window. Catching it during starting["until"] alone does little harm,
        # so give up and return False (far better than crashing /api/state).
        try:
            r = subprocess.run(["pgrep", "-f", "voice_daemon.py --language"],
                               capture_output=True)
        except (OSError, FileNotFoundError):
            return False
        return bool(r.stdout.strip())

    # Where it goes. Empty means everyone.
    route_path = state / "route"

    # Why Claude switched it. Shown on the page only, never mixed into speech.
    note_file = Path(args.log_file).parent / "pause-note.txt"

    async def handle_state(_req):
        """Give back the mic on/off, whether anything is held, and the held ones."""
        held = []
        if hold_file.exists():
            for line in hold_file.read_text(encoding="utf-8").splitlines():
                rec = Tail._parse(line)
                if rec:
                    held.append(rec)
        # Give back the page's mtime too. After an edit there is no way to
        # notice an open page is still the old one (a floating small window
        # especially is awkward to reload). The page is several files now, so it
        # is the newest of them all. Editing only the stylesheet or only the
        # wording has to raise the flag just the same.
        ui = 0
        for f in [page, *assets.values()]:
            try:
                ui = max(ui, int(f.stat().st_mtime))
            except OSError:
                pass    # a file that went missing is not a reason to lose the rest
        import voice_daemon as vd
        cfg = vd.read_config()
        return web.json_response({"muted": mute_file.exists(),
                                  "multiMachine": bool(cfg.get("multi_machine")),
                                  "machineName": cfg.get("machine_name") or "",
                                  "paused": pause_file.exists(),
                                  "engine": engine_running(),
                                  "loading": engine_loading(),
                                  "ui": ui, "held": held,
                                  "note": note_file.read_text(encoding="utf-8")
                                          if note_file.exists() else ""})

    async def handle_engine(req):
        """Stop recognition, or run it.

        Stopping frees the mic, and with Whisper the memory the model held
        comes back too. The viewer stays running, so it can be started again
        from here (Whisper takes 1 to 2 minutes to load its model).
        """
        body = await req.json()
        want = bool(body.get("running"))
        sh = str(Path(__file__).with_name("voice-shell.sh"))

        # Which engine to use. voice-shell.sh reads this file at startup.
        kind = (body.get("engine") or "").strip()
        if kind:
            import voice_daemon as vd
            vd.write_config(engine=kind)        # the next startup uses this too
            if kind != "browser":
                (state / "engine").write_text(kind, encoding="utf-8")

        # start_new_session cuts it loose from the viewer.
        # The daemon kills every one of its children when it exits, so hanging
        # it off the viewer's line drags the viewer down on a stop.
        if want and not engine_running():
            # Remember that a start was ordered. Startup is detached, so for a
            # moment before pgrep shows it, the process cannot be seen.
            stopping["until"] = 0.0
            starting["until"] = time.monotonic() + 10
            subprocess.Popen(["bash", sh, "engine-start"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
        elif not want and engine_running():
            # the process takes seconds to vanish, so do not call it loading then
            starting["until"] = 0.0
            stopping["until"] = time.monotonic() + 8
            subprocess.run(["bash", sh, "engine-stop"],
                           capture_output=True, timeout=30,
                           start_new_session=True)

        return web.json_response({"engine": engine_running()})

    async def handle_mute(req):
        """Cut the mic, or turn it on. Nothing said while cut is kept anywhere."""
        body = await req.json()
        if body.get("muted"):
            mute_file.touch()
        else:
            mute_file.unlink(missing_ok=True)
        return web.json_response({"muted": mute_file.exists()})

    async def handle_pause(req):
        """Hold utterances back, or go back to sending them straight.

        Claude itself sometimes switches this (when small talk or a phone call
        is going on). A mode change nobody pressed is only confusing without a
        reason, so a note can be attached and shown on the page.
        """
        body = await req.json()
        note = (body.get("note") or "").strip()[:200]
        if body.get("paused"):
            pause_file.touch()
            note_file.write_text(note, encoding="utf-8")
        else:
            pause_file.unlink(missing_ok=True)
            note_file.unlink(missing_ok=True)
        return web.json_response({"paused": pause_file.exists(), "note": note})

    async def handle_send(req):
        """Write the touched-up text to the log and send it to Claude."""
        body = await req.json()
        text = (body.get("text") or "").strip()
        if not text:
            return web.json_response({"error": "empty"}, status=400)

        # The line reaching Claude is the body alone. A mark goes on only when
        # it was edited. Hardcode it here and the mark lands on anything that
        # merely passed through the touch-up field. The mark means a sentence
        # the user deliberately shaped, so on a raw recognized sentence it stops
        # what needs rereading from being reread.
        # Only the page knows whether it was touched, so take it from the page.
        # The destination is set the way the daemon sets it. Forget it and the
        # line reaches sessions nobody picked (it really did wander into
        # other work).
        import voice_daemon as vd
        edited = bool(body.get("edited"))
        rec_out = {"text": text}
        if edited:
            rec_out["edited"] = True
        to = vd.resolve_target(args.log_file)
        if to:
            rec_out["to"] = to
        with open(args.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec_out, ensure_ascii=False) + "\n")
        rec = {"time": time.strftime("%H:%M:%S"), "text": text, "edited": edited}
        hold_file.write_text("", encoding="utf-8")     # sent, so empty the held list
        return web.json_response(rec)

    # Liveness check for browser recognition. An open page reports regularly
    # that it is listening right now. Without it, wait-ready answering READY
    # cannot be told apart from nobody actually listening (the page never
    # opened, the mic was denied), and someone told to go ahead and speak ends
    # up talking into a void.
    beat_file = state / "asr-heartbeat.json"
    BEAT_STALE = 15        # nothing heard for this long means that page is gone

    def read_beats() -> dict:
        try:
            d = json.loads(beat_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        now = time.time()
        return {k: v for k, v in d.items()
                if isinstance(v, dict) and now - v.get("t", 0) < BEAT_STALE}

    async def handle_heartbeat(req):
        body = await req.json()
        tab = str(body.get("tab") or "")[:40]
        st = str(body.get("state") or "")[:20]
        if not tab:
            return web.json_response({"error": "no tab"}, status=400)
        beats = read_beats()
        if st == "gone":
            beats.pop(tab, None)
        else:
            beats[tab] = {"t": time.time(), "state": st}
        beat_file.write_text(json.dumps(beats), encoding="utf-8")
        return web.json_response({"tabs": len(beats)})

    async def handle_asr_status(_req):
        """Whether browser recognition is really listening. voice-shell.sh status reads it."""
        beats = read_beats()
        states = [v.get("state") for v in beats.values()]
        return web.json_response({
            "tabs": len(beats),
            "listening": states.count("listening"),
            "denied": states.count("denied"),
        })

    async def handle_engines(_req):
        """The list of recognition engines to pick from.

        Browser recognition runs with nothing installed, so it is the default.
        For people who want it all local, only what is really installed is listed.
        """
        import asr_mic, voice_daemon as vd
        return web.json_response({
            "engines": asr_mic.available_engines(),
            # The remembered choice. This, not the browser's localStorage, is
            # the truth (differing per browser makes the startup branch useless).
            "chosen": vd.resolve_engine(""),
            "running": engine_running(),
        })

    async def handle_listeners(_req):
        """The sessions listening right now, and the destination that is picked."""
        import voice_daemon as vd
        try:
            chosen = route_path.read_text(encoding="utf-8").strip()
        except OSError:
            chosen = ""
        return web.json_response({
            "listeners": vd.list_active_listeners(args.log_file),
            "route": chosen,                                  # the one that is picked
            # Where it actually lands. With nothing picked, the later start wins.
            "target": vd.resolve_target(args.log_file) or "",
        })

    async def handle_machine(req):
        """This machine's name, and multi-machine mode on and off.

        With several machines listening at once, 「ミュート」 cuts them all.
        This is the setting that makes it take only signals with the name in
        front.
        """
        import voice_daemon as vd
        body = await req.json()
        name = str(body.get("name") or "").strip()[:24]
        multi = bool(body.get("multi"))
        vd.write_config(machine_name=name, multi_machine=multi)
        return web.json_response({"machineName": name, "multiMachine": multi})

    async def handle_disconnect(req):
        """Make that session stop listening.

        Only `voice-shell.sh listen` is stopped, the session itself does not
        end. Anything but a registered listener is refused.
        """
        import voice_daemon as vd
        body = await req.json()
        pid = str(body.get("pid") or "").strip()
        live = {str(l["pid"]): l for l in vd.list_active_listeners(args.log_file)}
        if pid not in live:
            return web.json_response({"error": "unknown"}, status=404)
        # Tell them first. Cut it quietly and that session sits there never
        # noticing that talking to it gets no response. Wait just long enough
        # for tail to read, then stop it.
        try:
            with open(args.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "system_warning":
                        "画面の操作で、このセッションは音声を聞くのをやめました。"
                        "もう一度使うには /voice-shell と入力してください。",
                    "to": pid,
                }, ensure_ascii=False) + "\n")
            await asyncio.sleep(0.5)
        except OSError:
            pass

        try:
            os.kill(int(pid), signal.SIGTERM)
        except (OSError, ValueError) as err:
            return web.json_response({"error": str(err)}, status=500)
        return web.json_response({"ok": True, "label": live[pid].get("label", pid)})

    async def handle_route(req):
        """Pick the destination. Empty means everyone."""
        body = await req.json()
        to = str(body.get("to") or "").strip()
        # Write under another name first, then replace. If the daemon reads
        # between the truncate and the write it gets a chopped PID, and one
        # utterance goes to somebody else.
        tmp = route_path.with_suffix(".tmp")
        tmp.write_text(to, encoding="utf-8")
        os.replace(tmp, route_path)
        return web.json_response({"route": to})

    async def handle_utterance(req):
        """Take in an utterance recognized on the browser side (Web Speech API).

        It goes down the same road as one the daemon recognized. Dictionary
        rewrites, utterances to ignore, minimum length, filler removal, holding
        while paused. Skip this road and the sentence that arrives changes with
        the way it was recognized.
        """
        body = await req.json()
        text = (body.get("text") or "").strip()
        if not text:
            return web.json_response({"error": "empty"}, status=400)

        import voice_daemon as vd

        # If the daemon is recognizing too, take nothing. Both write to the same
        # utterance log, so taking it sends one instruction to Claude twice.
        # The page side excludes it as well, but tabs can be opened more than
        # once, so it is stopped here too.
        if engine_running():
            return web.json_response({"dropped": "daemon_running"}, status=409)

        user_dict = vd.load_dictionary()

        # Voice-only signals. They go through the same function as the daemon,
        # so they bite the same however recognition is done (browser recognition
        # lets go of the audio itself when cut, though, so 「ミュート解除」 after
        # a cut is the one thing it cannot hear).
        kind = vd.apply_voice_command(text, args.log_file,
                                      mute_file.exists(), user_dict)
        if kind:
            return web.json_response({"command": kind})

        # while the mic is cut, keep it nowhere (the daemon does the same)
        if mute_file.exists():
            return web.json_response({"dropped": "muted"})

        # a trailing 「キャンセル」 or 「手直し」 gets the same treatment.
        # active_tail hands back nothing for a signal the user switched off, and
        # then the phrase travels on as ordinary speech, the same as in the daemon.
        if vd.take_tail(text, vd.active_tail("cancel_tail")) is not None:
            vd.note_voice_cmd(args.log_file, "cancelled", "", text)
            return web.json_response({"dropped": "cancelled"})
        body_text = vd.take_tail(text, vd.active_tail("hold_tail"))
        force_hold = body_text is not None
        if force_hold:
            if not body_text:
                vd.note_voice_cmd(args.log_file, "cancelled", "", text)
                return web.json_response({"dropped": "cancelled"})
            text = body_text

        try:
            tuning = json.loads(TUNING_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            tuning = {}

        # The order matches the daemon (minimum length → ignore words → polish).
        # polish changes the character count through dictionary rewrites, so a
        # different order makes the same utterance arrive or not depending on
        # how it was recognized.
        min_chars = tuning.get("min_chars", 15)
        if not force_hold and isinstance(min_chars, (int, float)) \
                and len(text) < int(min_chars) \
                and not vd.is_allowed_short(text, user_dict.get("unignore", ())):
            return web.json_response({"dropped": "too_short"})

        if not force_hold and vd.is_noise(text, user_dict["ignore"],
                                          user_dict.get("unignore", ())):
            return web.json_response({"dropped": "noise"})

        text = vd.polish(text, user_dict, False,
                         bool(tuning.get("strip_fillers")))

        stamp = time.strftime("%H:%M:%S")
        if force_hold or pause_file.exists():
            with open(hold_file, "a", encoding="utf-8") as h:
                h.write(json.dumps({"time": stamp, "text": text},
                                   ensure_ascii=False) + "\n")
            if force_hold:
                vd.note_voice_cmd(args.log_file, "held", "", text)
            return web.json_response({"held": text})

        # the destination is set the way the daemon sets it (browser too)
        rec_out = {"text": text}
        to = vd.resolve_target(args.log_file)
        if to:
            rec_out["to"] = to
        with open(args.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec_out, ensure_ascii=False) + "\n")
        return web.json_response({"time": stamp, "text": text})

    async def handle_drop_current(_req):
        """Throw away the line being recognized right now.

        Only the time of the press is left behind, and the recognition loop
        does the judging. Comparing that time with the moment the utterance
        began keeps a press landing after the settle from dragging in the next
        utterance. The loop reads this file and leaves it there, so nothing is
        deleted here either.
        """
        (state / "drop_at").write_text(str(time.time()), encoding="utf-8")
        return web.json_response({"ok": True})

    async def handle_discard(_req):
        """Throw away the held utterances."""
        hold_file.write_text("", encoding="utf-8")
        return web.json_response({"ok": True})

    app = web.Application()
    app.router.add_get("/", handle_index)
    for url, ctype in ASSETS.items():
        app.router.add_get(url, make_asset_handler(assets[url], ctype))
    app.router.add_get("/ws", handle_ws)
    app.router.add_get("/api/state", handle_state)
    async def handle_dict_get(req):
        """Give back the dictionary and the words the built-in rules ignore."""
        # ?scope=effective folds in the built-in ignore words too, so it is what
        # actually bites. The page uses it to apply replacements to
        # mid-recognition text (not for editing).
        if req.query.get("scope") == "effective":
            import voice_daemon as vd
            return web.json_response(vd.load_dictionary())
        d = _read_dict(path=DICT_FILE)
        d["builtin"] = _builtin_noise()
        return web.json_response(d)

    async def handle_dict_put(req):
        """Save the dictionary. The daemon rereads it per utterance, so it lands at once."""
        target = DICT_FILE

        body = await req.json()
        prev = _read_dict(raw=True, path=target)
        data = {
            "ignore": sorted({s.strip() for s in body.get("ignore", [])
                              if isinstance(s, str) and s.strip()}),
            "unignore": _keep_unignore(body.get("unignore", []), prev),
            "replace": {k.strip(): v.strip() for k, v in body.get("replace", {}).items()
                        if isinstance(k, str) and isinstance(v, str) and k.strip()},
        }
        # The record of added default entries is internal. Delete it and deleted
        # entries come back, so it stays. Rewrites and ignores are held apart,
        # since voice_daemon.py looks at them by kind.
        seen = set(prev.get("_seen", [])) | set(prev.get("replace", {}))
        data["_seen"] = sorted(seen | set(data["replace"]))
        seen_ignore = set(prev.get("_seen_ignore", [])) | set(prev.get("ignore", []) or [])
        data["_seen_ignore"] = sorted(seen_ignore | set(data["ignore"]))

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # Internal keys (the ones starting with _) are not given back. Hand them
        # to the page and they come straight back on the next save, letting the
        # page paint over the copy held here.
        return web.json_response({k: v for k, v in data.items() if not k.startswith("_")})

    async def handle_commands_get(req):
        """Give back the signals usable by voice and what the user did with them.

        The phrasings come from the table the daemon holds. A separate copy on
        the page would create words that are written down but do nothing. The
        explanation of what each does lives in the page's i18n. Phrasings and
        explanations translate into different things, so they are kept apart.

        off carries the names of the kinds switched off. Names, never wordings,
        so a wording leaving the built-in table cannot take the record with it.
        It rides at the top rather than inside groups because the page saves it
        back whole, and a flag scattered through the groups would have to be
        gathered up again on the way out.
        """
        import voice_daemon as vd
        saved = vd.user_command_phrases()
        return web.json_response({
            "groups": vd.command_catalog(req.query.get("lang") or "en"),
            "user": {k: saved[k] for k in vd.USER_COMMAND_KINDS},
            "off": saved[vd.OFF_KEY],
            "slot": vd.ROUTE_SLOT,
        })

    async def handle_commands_put(req):
        """Save added phrasings. The daemon rereads per utterance, so it lands at once.

        What comes in is cleaned by the same function the daemon uses. Unusable
        forms (too short, no slot for the number, a kind that cannot be added)
        drop out here, so what goes back is exactly what actually bites.
        """
        import voice_daemon as vd
        data = vd.clean_user_commands(await req.json())
        vd.COMMANDS_FILE.parent.mkdir(parents=True, exist_ok=True)
        vd.COMMANDS_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return web.json_response(data)

    mic_file = state / "mic"
    engine_active_file = state / "engine_active"

    async def handle_tuning_get(_req):
        """Give back the current sensitivity and seconds of silence before
        settling. The range comes with it, so the slider ends line up with the
        server's own limits."""
        try:
            cur = json.loads(TUNING_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cur = {}
        keys = list(TUNING_RANGE) + list(TUNING_FLAGS)
        return web.json_response({
            "tuning": {k: cur.get(k) for k in keys},
            "range": {k: {"min": lo, "max": hi}
                      for k, (lo, hi) in TUNING_RANGE.items()},
        })

    async def handle_tuning_put(req):
        """Rewrite the sensitivity and silence seconds. The daemon picks it up next cycle."""
        body = await req.json()
        try:
            cur = json.loads(TUNING_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cur = {}

        for key, (lo, hi) in TUNING_RANGE.items():
            if not isinstance(body.get(key), (int, float)):
                continue
            v = min(hi, max(lo, float(body[key])))
            cur[key] = int(round(v)) if key in TUNING_INT else v

        for key in TUNING_FLAGS:
            if isinstance(body.get(key), bool):
                cur[key] = body[key]

        if isinstance(body.get("language"), str):
            import whisper_engine
            code = body["language"]
            # take it only when empty (auto-detect) or a code already supported
            if code == "" or code in whisper_engine.LANGUAGE_NAMES:
                cur["language"] = code

        TUNING_FILE.parent.mkdir(parents=True, exist_ok=True)
        TUNING_FILE.write_text(json.dumps(cur, indent=2) + "\n", encoding="utf-8")
        return web.json_response({"tuning": cur})

    async def handle_languages(_req):
        """The list of recognition languages (only while Whisper is in use). Other
        engines get an empty list back, and the viewer hides the whole dropdown."""
        try:
            engine = engine_active_file.read_text(encoding="utf-8").strip()
        except OSError:
            engine = ""
        if engine != "whisper":
            return web.json_response({"engine": engine, "languages": [], "current": ""})
        import whisper_engine
        try:
            cur = json.loads(TUNING_FILE.read_text(encoding="utf-8")).get("language", "")
        except (OSError, ValueError):
            cur = ""
        return web.json_response({
            "engine": engine,
            "languages": whisper_engine.available_languages(),
            "current": cur,
        })

    async def handle_whisper_model_get(_req):
        """The Whisper model. Gives back the remembered one and the default name.

        Swapping it needs a reload, so it lives in config.json (the one read
        once at startup), not tuning.json. Mixed into the tuning.json that is
        reread every 0.5 seconds, whoever wrote it would think it had taken.
        """
        import voice_daemon as vd
        return web.json_response({
            "model": vd.read_config().get("whisper_model") or "",
            "default": "large-v3-turbo",
        })

    async def handle_whisper_model_put(req):
        """Remember the Whisper model. Send it empty to go back to the default.

        Whether the name is right is not checked here. It takes both a Hugging
        Face name and the path of a folder kept locally, so there is no telling
        until it is loaded.
        """
        import voice_daemon as vd
        body = await req.json()
        name = (body.get("model") or "").strip()
        vd.write_config(whisper_model=name)
        return web.json_response({"model": name})

    async def handle_mics(_req):
        """Give back the usable mics and the one picked right now."""
        import asr_mic
        try:
            current = mic_file.read_text(encoding="utf-8").strip()
        except OSError:
            current = ""
        return web.json_response({"current": current, "mics": asr_mic.list_mics()})

    async def handle_mic_put(req):
        """Change the mic in use. The daemon swaps only the recording process."""
        body = await req.json()
        dev = (body.get("device") or "").strip()
        if not dev:
            return web.json_response({"error": "empty"}, status=400)
        mic_file.write_text(dev, encoding="utf-8")
        return web.json_response({"current": dev})

    app.router.add_post("/api/engine", handle_engine)
    app.router.add_get("/api/mics", handle_mics)
    app.router.add_get("/api/tuning", handle_tuning_get)
    app.router.add_put("/api/tuning", handle_tuning_put)
    app.router.add_get("/api/languages", handle_languages)
    app.router.add_get("/api/whisper-model", handle_whisper_model_get)
    app.router.add_put("/api/whisper-model", handle_whisper_model_put)
    app.router.add_put("/api/mics", handle_mic_put)
    app.router.add_get("/api/dictionary", handle_dict_get)
    app.router.add_put("/api/dictionary", handle_dict_put)
    app.router.add_get("/api/commands", handle_commands_get)
    app.router.add_put("/api/commands", handle_commands_put)
    app.router.add_post("/api/mute", handle_mute)
    app.router.add_post("/api/pause", handle_pause)
    app.router.add_post("/api/send", handle_send)
    app.router.add_post("/api/utterance", handle_utterance)
    app.router.add_post("/api/asr-heartbeat", handle_heartbeat)
    app.router.add_get("/api/asr-status", handle_asr_status)
    app.router.add_get("/api/engines", handle_engines)
    app.router.add_get("/api/listeners", handle_listeners)
    app.router.add_put("/api/route", handle_route)
    app.router.add_post("/api/listeners/disconnect", handle_disconnect)
    app.router.add_put("/api/machine", handle_machine)
    app.router.add_post("/api/discard", handle_discard)
    app.router.add_post("/api/drop-current", handle_drop_current)

    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, args.host, args.port).start()

    print(f"\n  ブラウザで開いてください →  http://{args.host}:{args.port}"
          f"\n  追尾しているログは {args.log_file}\n", file=sys.stderr, flush=True)

    tasks = [asyncio.create_task(tail.watch()),
             asyncio.create_task(tail.watch_partial()),
             asyncio.create_task(tail.watch_level()),
             asyncio.create_task(tail.watch_held()),
             asyncio.create_task(tail.watch_mic_active()),
             asyncio.create_task(tail.watch_muted()),
             asyncio.create_task(tail.watch_voice_cmd()),
             asyncio.create_task(tail.watch_paused())]
    try:
        await asyncio.Event().wait()
    finally:
        for t in tasks:
            t.cancel()
        for ws in list(tail.clients):
            await ws.close(code=WSCloseCode.GOING_AWAY, message=b"shutdown")
        await runner.cleanup()


def main():
    try:
        asyncio.run(main_async(parse_args()))
    except KeyboardInterrupt:
        print("\n終了します。", file=sys.stderr)


if __name__ == "__main__":
    main()
