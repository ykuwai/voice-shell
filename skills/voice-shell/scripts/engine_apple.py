"""Engine that uses the macOS 26 speech recognition (SpeechAnalyzer).

Picked with `--engine apple` (the default on macOS). It is the on-device model
that ships with the OS, so there is no multi-GB model to download and the audio
never leaves the machine.

Measured (Apple Silicon / macOS 26), 3.5 seconds of Japanese speech takes about
0.2 seconds to recognize, and comes out right down to the punctuation.

## Called through a Swift helper

SpeechAnalyzer only has a Swift API, so speech_helper.swift is kept resident,
handed a WAV path, and hands back the result as JSON. The helper builds itself
the first time (swiftc ships with Xcode or the Command Line Tools).

## A partial is "recognize the whole utterance again"

The audio collected so far is recognized from the top and state.text replaced.
One pass is fast, so it keeps up even at a tight refresh interval.
Recognition is pushed onto a worker thread to keep the mic read running
(waiting in the main loop clogs the ffmpeg pipe and long utterances get lost).
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import wave

import numpy as np

from asr_mic import SAMPLE_RATE

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(HERE, "speech_helper.swift")
BINARY = os.path.join(HERE, "build", "speech_helper")

# Put out a fresh partial once this much new audio has piled up
_REFRESH_SEC = 0.5

# Floor that keeps recognition from thrashing on audio that is too short
_MIN_SEC = 0.3

# voice-shell hands every engine the language spelled out.
# SpeechTranscriber wants BCP 47, so fix it up here.
_LOCALE = {
    "japanese": "ja-JP", "english": "en-US", "chinese": "zh-CN",
    "korean": "ko-KR", "french": "fr-FR", "german": "de-DE",
    "spanish": "es-ES", "italian": "it-IT", "portuguese": "pt-BR",
}


def _locale_id(name):
    """Turn "Japanese", "ja" or "ja-JP" into BCP 47, whichever one arrives."""
    if not name:
        return "ja-JP"
    s = str(name).strip()
    if "-" in s:
        return s
    return _LOCALE.get(s.lower(), s)


def _ensure_binary():
    """Build the helper if it is needed. Newer than the source, use it as is."""
    if (os.path.exists(BINARY) and
            os.path.getmtime(BINARY) >= os.path.getmtime(SOURCE)):
        return BINARY

    os.makedirs(os.path.dirname(BINARY), exist_ok=True)
    print("音声認識ヘルパをビルドしています(初回のみ)…", file=sys.stderr, flush=True)
    r = subprocess.run(["swiftc", "-O", "-parse-as-library", SOURCE, "-o", BINARY],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("speech_helper のビルドに失敗しました。\n"
                 "  Xcode か Command Line Tools(xcode-select --install)と\n"
                 "  macOS 26 以降が必要です。\n" + r.stderr.strip())
    return BINARY


def load(args):
    """Wake the helper and hand back an adapter in the shape asr_mic wants."""
    if sys.platform != "darwin":
        sys.exit("--engine apple は macOS 専用です")

    binary = _ensure_binary()
    locale = _locale_id(getattr(args, "language", None))
    print(f"認識エンジンは apple({locale} / OS 付属のオンデバイスモデル)",
          file=sys.stderr)
    print("  音声はこの Mac の中だけで処理されます。", file=sys.stderr, flush=True)
    return _AppleModel(binary, locale)


class _State:
    """Holds only the 3 attributes asr_mic touches (text / language / audio_accum)."""

    __slots__ = ("text", "language", "audio_accum", "_decoded_upto", "_final")

    def __init__(self, language):
        self.text = ""
        self.language = language
        self.audio_accum = np.empty(0, dtype=np.float32)
        self._decoded_upto = 0   # sample count when the last run started
        self._final = False


class _AppleModel:
    """SpeechAnalyzer adapter carrying the 3 methods asr_mic calls."""

    def __init__(self, binary, locale):
        self._locale = locale
        self._proc = subprocess.Popen(
            [binary, "--locale", locale],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, bufsize=1)
        # Wait for startup, model assets included. The first run takes tens of seconds.
        first = self._proc.stdout.readline()
        try:
            ready = json.loads(first)
        except ValueError:
            sys.exit(f"speech_helper の応答が読めません。{first!r}")
        if "error" in ready:
            sys.exit(f"speech_helper でエラーが起きました。{ready['error']}")

        self._io_lock = threading.Lock()   # one round trip on the pipe at a time
        self._lock = threading.Lock()      # guards swapping state and appending
        self._wake = threading.Event()
        self._state = None
        self._tmpdir = tempfile.mkdtemp(prefix="voice-shell-apple-")
        self._seq = 0
        threading.Thread(target=self._worker, daemon=True).start()

    # The unused arguments are taken only to match the other engines
    def init_streaming_state(self, language=None, **_ignored):
        st = _State(_locale_id(language) if language else self._locale)
        with self._lock:
            self._state = st
        return st

    def streaming_transcribe(self, block, state):
        """Just pile up audio and wake the worker (the worker recognizes)."""
        with self._lock:
            state.audio_accum = np.concatenate(
                [state.audio_accum, np.asarray(block, dtype=np.float32)])
        self._wake.set()

    def finish_streaming_transcribe(self, state):
        """Recognize the whole utterance again in one go and settle it.

        A partial is a result from before the end was heard, so the settled
        text is put out fresh here.
        """
        with self._lock:
            state._final = True
            self._state = None     # from here the worker writes no more here
        if len(state.audio_accum) < SAMPLE_RATE * _MIN_SEC:
            return
        text = self._transcribe(state.audio_accum)
        if text:
            state.text = text

    # ── Internals ────────────────────────

    def _transcribe(self, audio):
        """Write a WAV, hand it to the helper, take the recognized text back."""
        with self._io_lock:
            self._seq += 1
            path = os.path.join(self._tmpdir, f"{self._seq % 4}.wav")
            _write_wav(path, audio)
            try:
                self._proc.stdin.write(path + "\n")
                self._proc.stdin.flush()
                line = self._proc.stdout.readline()
            except (BrokenPipeError, ValueError):
                print("speech_helper が落ちました。", file=sys.stderr, flush=True)
                return ""
        if not line:
            return ""
        try:
            r = json.loads(line)
        except ValueError:
            return ""
        if "error" in r:
            print(f"speech_helper でエラーが起きました。{r['error']}", file=sys.stderr, flush=True)
            return ""
        return (r.get("text") or "").strip()

    def _worker(self):
        """Re-recognize the collected audio from the top, keeping state.text fresh."""
        while True:
            self._wake.wait()
            with self._lock:
                state = self._state
                if (state is None or state._final or
                        len(state.audio_accum) - state._decoded_upto
                        < SAMPLE_RATE * _REFRESH_SEC):
                    # No reason to be awake now. Sleep until the next append.
                    # clear runs inside the lock. Outside it, a chunk appended
                    # right before the clear misses its wakeup (appending is
                    # inside the lock too, so the two never race)
                    self._wake.clear()
                    continue
                audio = state.audio_accum          # appending rebuilds the array,
                state._decoded_upto = len(audio)   # so this reference is safe
            if len(audio) < SAMPLE_RATE * _MIN_SEC:
                continue
            text = self._transcribe(audio)
            with self._lock:
                if state is self._state and not state._final and text:
                    state.text = text


def _write_wav(path, audio):
    """Turn float32 (-1..1) into a 16bit mono 16kHz WAV."""
    pcm = np.clip(np.asarray(audio, dtype=np.float32), -1.0, 1.0)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes((pcm * 32767.0).astype("<i2").tobytes())
