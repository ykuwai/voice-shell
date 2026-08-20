"""Shared handling for mic input → streaming recognition.

The resident daemon (voice_daemon.py) and the viewer (viewer.py) share this.
Where it all goes is the caller's business, so this module takes care of
things as far as yielding recognition events and no further.
"""
import re
import os
import shutil
import queue
import subprocess
import sys
import threading
import time
from collections import deque
from typing import Iterator, Tuple

import numpy as np

# The sample rate the recognition engines expect. It is the same value however
# the engines are installed, so hold it fixed instead of asking a library.
SAMPLE_RATE = 16000

BLOCK_SEC = 0.1  # the unit the mic is read in
# Never break while someone keeps talking. Talking at length and getting the
# whole thought across matters more than arriving fast (a form that broke at
# 60 seconds went in once and was taken back out). The collected audio goes
# straight to inference, so only a last brake sits here.
HARD_UTTERANCE_CAP = 300.0

# How much of "just before the threshold is crossed" is glued to the head of
# an utterance. A consonant's onset has a low RMS, so handing audio over from
# the moment of crossing clips the start of a word (measured,
#  「反応がなかったので」 became 「なかったので」, 「Apple の認識が」 became
#  「の認識が」). 0.3 seconds was not enough, so 0.6. Extra silence gets handed
# over, but the recognizer ignores silence, so no real harm.
PREROLL_SEC = 0.6

# Once blocks whose contents are all zero run this long, count it as unplugged.
# A live device picks up room noise however quiet the room (measured around
# 0.0005, and 0.0022 even on the machine running right now). 16bit lined up as
# all zero bits happens only when the device is dead, so a quiet room is never
# mistaken for it. A few seconds is too short. Some devices put out zeros for
# the mic's own mute, so every silence would reopen it. Too long and it stays
# quiet until it comes back. Splitting the difference, 20 seconds.
DEAD_SEC = 20.0
# Fast reopening stops here. When the default input has moved to another device,
# say, no amount of reopening fixes it and each reopen only loses recording.
DEAD_TRIES = 3
# Interval for still trying after giving up. Stopping outright leaves no road
# back even when it is plugged in again. While zeros keep arriving the blocks
# never break and the STALL_SEC watch never once fires, so if this one stops
# too, nobody can notice.
DEAD_SLOW_SEC = 300.0

# Default RMS counted as silence. It differs per mic, so measure it and settle
# on a number, but carrying the dev machine's over gives "nothing responds at
# all" somewhere else. The 0.054 meant for Linux was too high for a USB
# condenser mic on macOS, and a normal voice never once crossed it (the room
# noise there was 0.003).
DEFAULT_SILENCE_THRESHOLD = 0.015 if sys.platform == "darwin" else 0.054

# The value that stands for "use the system default". Kept as one spelling
# across every OS, with mic_command resolving how it is actually named
# (":default" for avfoundation, a device name for dshow, "pipewire" for ALSA).
#
# It used to default to a different spelling per OS, but ":0" and "audio=default"
# matched nothing in the list list_mics() gives back. The dropdown on the page
# decides what is selected by matching against that list, so it landed on
# "nothing is selected" and looked blank.
SYSTEM_DEFAULT = "default"
DEFAULT_DEVICE = SYSTEM_DEFAULT


# The default when this module is hit directly. The usual path
# (voice-shell.sh start) never gets here, because voice_daemon.resolve_engine
# decides it as "what was asked > the last choice > this browser".
# browser cannot sit here. Browser recognition finishes inside the page and
# loads no model onto this machine. That is why the daemon has no branch for it.
# macOS gets apple, since the on-device recognition in the OS runs with nothing
# extra to set up. Everything else gets Whisper.
_DEFAULT_ENGINE = "apple" if sys.platform == "darwin" else "whisper"


def add_common_args(p):
    """Register the arguments every script shares."""
    p.add_argument("--engine", default=os.environ.get("VOICE_SHELL_ENGINE", _DEFAULT_ENGINE),
                   help="認識エンジン。apple（macOS 26 付属のオンデバイス認識。軽い）、"
                        "whisper（faster-whisper。固有名詞に強い）。"
                        "どちらも音声はこの機械から出ない。"
                        "ブラウザ認識（browser）は画面の中で動くので、ここでは選べない。"
                        "VOICE_SHELL_ENGINE でも指定できる")
    p.add_argument("--whisper-compute", default=None,
                   help="Whisper の精度と VRAM の兼ね合い（float16 / int8）")
    p.add_argument("--whisper-device", default=None,
                   help="Whisper を動かす場所（cuda / cpu）")
    p.add_argument("--whisper-language", default=None,
                   help="Whisper の言語を固定する（ja / en）。既定は自動判定。"
                        "固定すると、その言語に訳されて出るので普段は指定しない")
    p.add_argument("--model", default=None,
                   help="Whisper のモデル。Hugging Face の名前でも、"
                        "手元に置いたフォルダの場所でも受ける。"
                        "省略すると large-v3-turbo を使う")
    p.add_argument("--language", default=None,
                   help="言語を固定する。Japanese のように書く。省略すると自動判定")
    p.add_argument("--device", default=DEFAULT_DEVICE,
                   help="録音デバイス。Linux は arecord の -D（pipewire, plughw:2,0）、"
                        "macOS は avfoundation の番号（:0）、Windows は dshow の名前"
                        "（audio=マイク名）")
    p.add_argument("--input-samplerate", type=int, default=44100,
                   help="マイクの録音レート。16kHz に変換して推論する")
    p.add_argument("--silence-threshold", type=float, default=DEFAULT_SILENCE_THRESHOLD,
                   help="この RMS 未満を無音とみなす（マイクのノイズフロアに合わせる）")
    p.add_argument("--silence-duration", type=float, default=1.5,
                   help="この秒数だけ無音が続いたら発話を確定する")
    return p


def load_model(args):
    """Get the recognition engine ready.

    apple is the on-device recognition that comes with macOS 26, and loads no
    model. whisper runs faster-whisper on this machine.
    With either of them, the audio never leaves this machine.
    """
    # Cleanup is needed whichever engine runs. The recording ffmpeg / arecord
    # runs as a child process regardless, so register before the branching.
    # (Back when this sat inside the per-engine branches, apple never reached
    #   the registration and every stop left the recording process orphaned)
    _kill_engine_on_exit()

    if args.engine == "apple":
        import engine_apple
        return engine_apple.load(args)

    if args.engine == "whisper":
        import whisper_engine
        return whisper_engine.load(args)

    # An unknown name stops here instead of quietly returning None. Return it
    # and it turns into an unrelated exception later in init_streaming_state,
    # about NoneType having no attribute, and the reason never gets through.
    sys.exit(f"「{args.engine}」はこの機械で動かせるエンジンではありません。\n"
             "  選べるのは apple と whisper です。\n"
             "  ブラウザ認識は voice-shell.sh start --engine browser から使えます。")


def _kill_engine_on_exit():
    """Make sure the child processes go down at exit.

    When Ctrl-C or kill ends the parent, children stay behind still holding
    resources. Two things stay behind.

    - the recording ffmpeg / arecord keeps the mic open (every engine)
    - the recognition helper stays (apple)

    SIGTERM does not go through atexit by default, so it is turned into
    sys.exit first, then the direct children are finished off. voice-shell.sh
    stop sends SIGTERM.
    """
    import atexit
    import os
    import signal as _signal

    def cleanup():
        try:
            out = subprocess.run(["pgrep", "-P", str(os.getpid())],
                                 capture_output=True, timeout=5).stdout.decode()
        except Exception:
            return
        for pid in (int(p) for p in out.split()):
            try:
                os.kill(pid, _signal.SIGKILL)
            except ProcessLookupError:
                pass

    atexit.register(cleanup)
    # make SIGTERM go through atexit as well (by default it does not)
    _signal.signal(_signal.SIGTERM, lambda *_: sys.exit(0))


# ── Engines available here ──────────────
#
# Browser recognition (Web Speech API) runs with nothing installed, so that is
# the default. For people who want it all local, or who pick by accuracy or by
# language, list what is installed so they can choose. What is not installed is
# left out, since listing it would only offer something unpickable.

ENGINE_LABELS = {
    "apple":    "Apple のオンデバイス認識（軽い・ローカル）",
    "whisper":  "Whisper（固有名詞に強い・ローカル）",
}


def _mac_version():
    try:
        return int(subprocess.run(["sw_vers", "-productVersion"],
                                  capture_output=True, timeout=5)
                   .stdout.decode().split(".")[0])
    except Exception:
        return 0


def available_engines() -> list:
    """Give back the engines this environment can really use.

    Judged by whether the import works (loading for real is heavy, find_spec only).
    """
    import importlib.util as iu

    def have(mod):
        try:
            return iu.find_spec(mod) is not None
        except (ImportError, ValueError):
            return False

    out = []
    if sys.platform == "darwin" and _mac_version() >= 26:
        out.append("apple")
    if have("faster_whisper"):
        out.append("whisper")
    return [{"id": e, "label": ENGINE_LABELS.get(e, e)} for e in out]


def list_mics() -> list:
    """Give back the list of usable mics. [{"id": ..., "label": ...}, ...]

    How you get it differs per OS, and that difference is absorbed here.
    """
    # The head of the list is always the system default. Without it, the dropdown
    # for anyone still on the default matches nothing and looks blank.
    out = [{"id": SYSTEM_DEFAULT, "label": "システムの既定"}]
    try:
        if sys.platform == "darwin":
            # ffmpeg puts the device list on stderr, and exits with 1 as well
            r = subprocess.run(
                ["ffmpeg", "-hide_banner", "-f", "avfoundation",
                 "-list_devices", "true", "-i", ""],
                capture_output=True, timeout=10)
            audio = False
            for line in r.stderr.decode(errors="replace").splitlines():
                if "AVFoundation audio devices" in line:
                    audio = True
                    continue
                if audio:
                    m = re.search(r"\[(\d+)\]\s+(.+)$", line)
                    if m:
                        out.append({"id": f":{m.group(1)}", "label": m.group(2).strip()})

        elif sys.platform.startswith("win"):
            r = subprocess.run(
                ["ffmpeg", "-hide_banner", "-list_devices", "true",
                 "-f", "dshow", "-i", "dummy"],
                capture_output=True, timeout=10)
            for line in r.stderr.decode(errors="replace").splitlines():
                if "(audio)" in line:
                    m = re.search(r'"(.+?)"', line)
                    if m:
                        out.append({"id": f"audio={m.group(1)}", "label": m.group(1)})

        else:
            # arecord -L lines up a name and a description, alternating.
            # default / pulse / pipewire are separate routes to one sound server.
            # The system default is already at the head, so nothing is added here.

            r = subprocess.run(["arecord", "-L"], capture_output=True, timeout=10)
            name = None
            for line in r.stdout.decode(errors="replace").splitlines():
                if not line.startswith((" ", "\t")):
                    name = line.strip() if line.strip().startswith("plughw:") else None
                    if name:
                        out.append({"id": name, "label": name})
                elif name and out and out[-1]["id"] == name:
                    # the description reads more clearly, so use it as the name
                    out[-1]["label"] = line.strip()
                    name = None
    except (OSError, subprocess.SubprocessError):
        pass

    return out


def mic_command(device: str, in_sr: int) -> list:
    """Build the command that pours raw PCM onto stdout.

    Linux uses arecord (it still gets sound while PipeWire holds the mic).
    macOS and Windows use ffmpeg. Pass device anything other than "default"
    to name a device or its number.
    """
    if sys.platform == "darwin":
        if shutil.which("ffmpeg") is None:
            sys.exit("ffmpeg が見つかりません (brew install ffmpeg)")
        # avfoundation takes the ":<audio device number>" form. ":default" works
        # too (measured, it does record from the system default input).
        if device == SYSTEM_DEFAULT:
            src = ":default"
        else:
            src = device if device.startswith(":") else ":default"
        return ["ffmpeg", "-hide_banner", "-loglevel", "error",
                "-f", "avfoundation", "-i", src,
                "-ac", "1", "-ar", str(in_sr), "-f", "s16le", "-"]

    if sys.platform.startswith("win"):
        if shutil.which("ffmpeg") is None:
            sys.exit("ffmpeg が見つかりません (winget install ffmpeg)")
        # dshow names the device. The list comes out of the following command.
        #   ffmpeg -list_devices true -f dshow -i dummy
        # Unlike avfoundation there is no spelling that stands for the default,
        # so resolve to the head of the list (usually the system default).
        if device == SYSTEM_DEFAULT:
            # The head of list_mics() is the sentinel itself, so look only at
            # real devices. Miss this and "-i default" goes to dshow where no
            # such thing exists, and anyone still on the default never records.
            found = [m["id"] for m in list_mics() if m["id"] != SYSTEM_DEFAULT]
            if not found:
                sys.exit("マイクが見つかりません "
                         "(ffmpeg -list_devices true -f dshow -i dummy で確認してください)")
            src = found[0]
        else:
            src = device if device.startswith("audio=") else "audio=default"
        return ["ffmpeg", "-hide_banner", "-loglevel", "error",
                "-f", "dshow", "-i", src,
                "-ac", "1", "-ar", str(in_sr), "-f", "s16le", "-"]

    if shutil.which("arecord") is None:
        sys.exit("arecord が見つかりません (alsa-utils をインストールしてください)")
    # PipeWire and PulseAudio both resolve the default on the sound server side
    if device == SYSTEM_DEFAULT:
        device = "pipewire"
    return ["arecord", "-D", device, "-f", "S16_LE",
            "-r", str(in_sr), "-c", "1", "-t", "raw", "-q"]


def read_blocks(device: str, in_sr: int,
                want_device=None, on_switch=None) -> Iterator[Tuple[np.ndarray, float, float]]:
    """Keep reading the mic and yield (16kHz PCM, length in seconds, RMS).

    While PipeWire holds the mic, PortAudio cannot see it, so arecord is made
    to spit out raw PCM and it comes back through a pipe.

    If want_device() gives back a different device name, only the recording
    process is swapped. The model stays loaded, so switching mics never waits.

    Recording carries on even while the mic is off (voice_daemon.py throws the
    recognition away). Stopping the recording itself was tried too, but then
    the recording process has to be woken again on every on and off, and the
    switch falls a beat behind. Like a call app, it stays at recording without
    sending.

    on_switch(device) is called the moment a switch really finishes, so the
    viewer can show whether it really switched as settled fact (the browser
    side alone is optimistic and cannot tell whether the switch happened).
    """
    nbytes = int(in_sr * BLOCK_SEC) * 2  # 16bit mono

    # The recording process can stay alive while the sound alone stops coming.
    # Measured, it happens when a USB mic is unplugged and plugged back in
    # (avfoundation stays wired to the device it opened with, so once the
    # default swaps, not even silence arrives). proc.stdout.read() then gets no
    # EOF either and waits forever. Measured, it sat that way for two and a half
    # hours, the page still saying it was arriving and nothing happening.
    #
    # Move the reading onto another thread, wait a set time, rebuild if nothing
    # comes. A quiet room is never mistaken for it. Blocks themselves arrive
    # even in silence, and they stop only when the wiring is cut.
    # There is also a break where blocks arrive but hold zeros (DEAD_SEC has that).
    def start(dev):
        p = subprocess.Popen(mic_command(dev, in_sr), stdout=subprocess.PIPE)
        q = queue.Queue(maxsize=100)          # 10 seconds. Overflow waits on the pipe
        def pump():
            try:
                while True:
                    b = p.stdout.read(nbytes)
                    while True:
                        try:
                            q.put(b, timeout=1.0)
                            break
                        except queue.Full:
                            if p.poll() is not None:
                                return        # recording already stopped. Drop it
                    if not b:                 # empty bytes means the other end ended
                        return
            except (OSError, ValueError):
                pass
        threading.Thread(target=pump, daemon=True).start()
        return p, q

    def stop(p):
        try:
            p.terminate()
            p.wait(timeout=1.5)
        except (OSError, subprocess.SubprocessError):
            try:
                p.kill()
            except OSError:
                pass

    def make_resampler():
        if in_sr == SAMPLE_RATE:
            return lambda b: b
        import soxr
        # Build the streaming resampler just once. Calling soxr.resample() per
        # block builds and tears down the filter every time and runs 4x slower.
        return soxr.ResampleStream(in_sr, SAMPLE_RATE, 1, dtype="float32").resample_chunk

    current = device
    proc, blocks = start(current)
    to_16k = make_resampler()
    if in_sr != SAMPLE_RATE:
        print(f"マイクを {in_sr}Hz で録音し {SAMPLE_RATE}Hz に変換します", file=sys.stderr)

    # Recording stops. Sometimes ffmpeg dies for no reason (measured on Windows,
    # rarely, a write to the pipe failing with "Invalid argument"), and sometimes
    # the process stays alive while only the sound stops coming (when a USB mic
    # is unplugged. avfoundation stays wired to the device it opened with, so it
    # never notices the unplug and goes quiet without even returning EOF).
    #
    # Either way, do the same thing. Reopen and wait again. **Never give up.**
    # Being told "tried 5 times, no luck" helps nobody, since the only thing to
    # do is plug it back in, and waiting quietly covers that. Plug it in and the
    # next attempt opens it and carries on as if nothing had happened.
    #
    # A quiet room is never mistaken for this. Blocks themselves keep arriving
    # in silence (the mic's own mute is the same, silent blocks come).
    #
    # But "do blocks arrive" alone is not enough. After a replug, a third state
    # was measured, blocks arrive but their contents are all zero. ffmpeg had
    # managed to reopen :default, yet the value stayed 0.0000 and had not come
    # back 10 minutes later, and this watch sailed right past it (they do arrive,
    # so it is satisfied forever). That one is counted below as zeros themselves
    # and treated as cut off just the same. It is a break that reopening
    # sometimes cannot fix, so that one alone stays its hand.
    #
    # Only the wait grows. Keeping ffmpeg woken the whole time nothing is
    # plugged in is pointless. The cap is 5 seconds, so a replug is back in 5.
    STALL_SEC = 4.0           # no sound for this long means it is not connected
    RETRY_MIN, RETRY_MAX = 0.5, 5.0
    retry_wait = RETRY_MIN
    lost = False              # disconnected right now (to log it only once)
    dead_run = 0.0            # seconds that all-zero blocks have run
    dead_tries = 0            # times reopened because of zeros
    gave_up = False           # gave up fast reopening (to log it only once)

    try:
        while True:
            # if a switch was asked for, redo the recording and nothing else
            if want_device is not None:
                asked = want_device()
                if asked and asked != current:
                    stop(proc)
                    current = asked
                    proc, blocks = start(current)
                    to_16k = make_resampler()   # let it keep no history
                    # A different device now, so drop the old device's zero
                    # count. Carry it over and a device picked after giving up
                    # that is silent too waits long with no fast attempt.
                    dead_run, dead_tries, gave_up = 0.0, 0, False
                    print(f"マイクを {current} に切り替えました", file=sys.stderr, flush=True)
                    if on_switch is not None:
                        on_switch(current)

            def reopen():
                """Rebuild the recording process only. Leave the model loaded."""
                nonlocal proc, blocks, to_16k, retry_wait
                stop(proc)
                time.sleep(retry_wait)
                retry_wait = min(retry_wait * 2, RETRY_MAX)
                proc, blocks = start(current)
                to_16k = make_resampler()

            def relight(why: str):
                """Reopen the recording. As often as it takes to connect."""
                nonlocal lost
                if not lost:
                    lost = True
                    print(f"{why}（{current}）。開き直して待ちます"
                          "（挿し直せばそのまま戻ります）",
                          file=sys.stderr, flush=True)
                reopen()

            try:
                raw = blocks.get(timeout=STALL_SEC)
            except queue.Empty:
                relight(f"マイクから {STALL_SEC:.0f} 秒ぶん音が来ません")
                continue
            if not raw:
                relight("録音が終了しました")
                continue

            # All zeros means not connected even though it arrives. Look at the
            # bytes before working out rms. Cheaper than dividing, and there is
            # no room for rounding.
            if raw.count(0) == len(raw):
                dead_run += len(raw) / 2 / in_sr   # 16bit mono
                if dead_run >= (DEAD_SLOW_SEC if gave_up else DEAD_SEC):
                    dead_run = 0.0
                    dead_tries += 1
                    lost = True
                    if dead_tries == 1:
                        print("マイクから届く音が全部ゼロです。"
                              f"{current} を開き直します",
                              file=sys.stderr, flush=True)
                    if dead_tries > DEAD_TRIES and not gave_up:
                        gave_up = True
                        print("何度開き直しても、届く音は全部ゼロのままです。"
                              f"このあとは {DEAD_SLOW_SEC / 60:.0f} 分おきに試し続けます。"
                              "マイクを選び直すか、挿し直すと早く戻ります",
                              file=sys.stderr, flush=True)
                        # The default input may have moved to another device.
                        # Printing what is visible now, once, gives a handle for
                        # picking again.
                        try:
                            seen = "、".join(m["label"] for m in list_mics()
                                            if m["id"] != SYSTEM_DEFAULT)
                        except Exception:
                            seen = ""
                        if seen:
                            print(f"いま見えているマイクは {seen} です",
                                  file=sys.stderr, flush=True)
                    reopen()
                    continue
            else:
                # Start it all over the moment sound comes in. A count carried
                # over brings the next judgement forward by the previous outage.
                dead_run, dead_tries, gave_up = 0.0, 0, False
                if lost:
                    lost = False
                    print(f"マイクが戻りました（{current}）", file=sys.stderr, flush=True)
                retry_wait = RETRY_MIN

            block = to_16k(np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0)
            # block.dot(block) builds no temporary array of squares
            rms = float(np.sqrt(block.dot(block) / block.size)) if block.size else 0.0
            yield block, len(block) / SAMPLE_RATE, rms
    finally:
        stop(proc)


def stream_utterances(model, args, should_stop=lambda: False):
    """Read the mic and yield recognition events.

    The events (dicts) yielded are these 3.
        {"type": "level",   "rms": float, "speaking": bool}   every block
        {"type": "partial", "text": str, "language": str}     mid-recognition
        {"type": "final",   "text": str, "language": str}     utterance settled

    Silence running as long as silence_duration settles it. Nothing is broken
    up while someone keeps talking (HARD_UTTERANCE_CAP is the only brake). The
    library has no utterance splitting (VAD), so RMS is watched here to judge.
    """
    # apple and whisper both carry the same 3 methods, so everything below is
    # shared. load_model stops on an unknown name, so only those 2 get here.
    def new_state():
        return model.init_streaming_state(language=args.language)

    state = new_state()
    # Reread the tuning the viewer can change (sensitivity, silence before
    # settling). It changes too rarely to check per block, so every 0.5 seconds.
    want_tuning = getattr(args, "want_tuning", None)
    tuning_wait = 0
    silence_run = 0.0    # seconds of unbroken silence
    speech_seen = False  # whether speech was heard in the current utterance
    last_text = ""
    # Hold the blocks from just before the threshold, glued to the utterance head
    preroll = deque(maxlen=max(1, round(PREROLL_SEC / BLOCK_SEC)))

    def finish():
        model.finish_streaming_transcribe(state)
        return ({"type": "final", "text": state.text, "language": state.language}
                if state.text.strip() else None)

    for block, dur, rms in read_blocks(args.device, args.input_samplerate,
                                       want_device=getattr(args, "want_device", None),
                                       on_switch=getattr(args, "on_switch", None)):
        if should_stop():
            break

        if want_tuning is not None:
            tuning_wait -= 1
            if tuning_wait <= 0:
                tuning_wait = max(1, round(0.5 / BLOCK_SEC))
                tuned = want_tuning() or {}
                for key in ("silence_threshold", "silence_duration"):
                    if isinstance(tuned.get(key), (int, float)):
                        setattr(args, key, float(tuned[key]))
                # voice_daemon.py reads the same args for minimum length and
                # filler removal, so putting them here reaches that side too
                if isinstance(tuned.get("min_chars"), (int, float)):
                    args.min_chars = int(tuned["min_chars"])
                if isinstance(tuned.get("strip_fillers"), bool):
                    args.strip_fillers = tuned["strip_fillers"]
                # Recognition language (Whisper only). It bites from the next
                # utterance (the next new_state()). Other engines spell it
                # differently, so they are left alone
                if args.engine == "whisper" and isinstance(tuned.get("language"), str):
                    args.language = tuned["language"] or None

        speaking = rms >= args.silence_threshold
        yield {"type": "level", "rms": rms, "speaking": speaking}

        if speaking:
            speech_seen = True
            silence_run = 0.0
        else:
            silence_run += dur

        # Silence before an utterance skips inference (the bit right before is kept)
        if not speech_seen:
            preroll.append(block)
            continue

        # First block of an utterance, so hand the pre-threshold sound over too
        while preroll:
            model.streaming_transcribe(preroll.popleft(), state)

        model.streaming_transcribe(block, state)

        if state.text != last_text:
            last_text = state.text
            if state.text.strip():
                yield {"type": "partial", "text": state.text, "language": state.language}

        accum_sec = len(state.audio_accum) / SAMPLE_RATE

        # Settle once the talking is done (silence ran on). Never cut mid-speech,
        # being sent partway through one breath is the worse problem.
        done_talking = silence_run >= args.silence_duration
        way_too_long = accum_sec >= HARD_UTTERANCE_CAP

        if done_talking or way_too_long:
            done = finish()
            if done:
                yield done
            state, silence_run, speech_seen, last_text = new_state(), 0.0, False, ""

    # Do not throw away an utterance in progress when interrupted
    if speech_seen:
        done = finish()
        if done:
            yield done
