"""macOS 26 の音声認識(SpeechAnalyzer)を使うエンジン。

`--engine apple` で使う(macOS では既定)。OS 付属のオンデバイスモデルなので、
数 GB のモデルを落とす必要がなく、音声は端末の外に出ない。

実測では(Apple Silicon / macOS 26)、3.5 秒の日本語音声で認識 0.2 秒ほど、
句読点まで含めて正しく出る。

## Swift のヘルパ経由で呼んでいる

SpeechAnalyzer は Swift の API しかないので、speech_helper.swift を常駐させ、
WAV のパスを渡して結果を JSON で受け取る。ヘルパは初回に自動でビルドする
(swiftc は Xcode か Command Line Tools に付属)。

## 途中経過は「発話全体の認識し直し」

溜まった音声を頭から認識し直して state.text を差し替える。
1 回が速いので、更新間隔を詰めても追いつく。
認識をワーカースレッドに逃がしているのはマイク読み取りを止めないため
(メインループで待つと ffmpeg のパイプが詰まり、長い発話を取りこぼす)。
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

# これ以上の新しい音声が溜まったら途中経過を出し直す
_REFRESH_SEC = 0.5

# 認識が短すぎる音声で暴れないための下限
_MIN_SEC = 0.3

# voice-shell はどのエンジンにも言語を綴りで渡してくる。
# SpeechTranscriber は BCP 47 なので直す。
_LOCALE = {
    "japanese": "ja-JP", "english": "en-US", "chinese": "zh-CN",
    "korean": "ko-KR", "french": "fr-FR", "german": "de-DE",
    "spanish": "es-ES", "italian": "it-IT", "portuguese": "pt-BR",
}


def _locale_id(name):
    """「Japanese」「ja」「ja-JP」のどれで来ても BCP 47 にする。"""
    if not name:
        return "ja-JP"
    s = str(name).strip()
    if "-" in s:
        return s
    return _LOCALE.get(s.lower(), s)


def _ensure_binary():
    """ヘルパを必要ならビルドする。ソースより新しければそのまま使う。"""
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
    """ヘルパを起こして、asr_mic が扱える形のアダプタを返す。"""
    if sys.platform != "darwin":
        sys.exit("--engine apple は macOS 専用です")

    binary = _ensure_binary()
    locale = _locale_id(getattr(args, "language", None))
    print(f"認識エンジンは apple({locale} / OS 付属のオンデバイスモデル)",
          file=sys.stderr)
    print("  音声はこの Mac の中だけで処理されます。", file=sys.stderr, flush=True)
    return _AppleModel(binary, locale)


class _State:
    """asr_mic が触る3つの属性(text / language / audio_accum)だけ持つ。"""

    __slots__ = ("text", "language", "audio_accum", "_decoded_upto", "_final")

    def __init__(self, language):
        self.text = ""
        self.language = language
        self.audio_accum = np.empty(0, dtype=np.float32)
        self._decoded_upto = 0   # 最後に認識を始めた時点のサンプル数
        self._final = False


class _AppleModel:
    """asr_mic が呼ぶ 3 つのメソッドを備えた SpeechAnalyzer アダプタ。"""

    def __init__(self, binary, locale):
        self._locale = locale
        self._proc = subprocess.Popen(
            [binary, "--locale", locale],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, bufsize=1)
        # 起動完了(モデル資産の用意を含む)まで待つ。初回は数十秒かかる。
        first = self._proc.stdout.readline()
        try:
            ready = json.loads(first)
        except ValueError:
            sys.exit(f"speech_helper の応答が読めません。{first!r}")
        if "error" in ready:
            sys.exit(f"speech_helper でエラーが起きました。{ready['error']}")

        self._io_lock = threading.Lock()   # パイプは 1 往復ずつ
        self._lock = threading.Lock()      # state の付け替えと追記を守る
        self._wake = threading.Event()
        self._state = None
        self._tmpdir = tempfile.mkdtemp(prefix="voice-shell-apple-")
        self._seq = 0
        threading.Thread(target=self._worker, daemon=True).start()

    # 使わない引数は、他のエンジンと口を揃えるためだけに受け取る
    def init_streaming_state(self, language=None, **_ignored):
        st = _State(_locale_id(language) if language else self._locale)
        with self._lock:
            self._state = st
        return st

    def streaming_transcribe(self, block, state):
        """音声を溜めてワーカーを起こすだけ(認識はワーカーがやる)。"""
        with self._lock:
            state.audio_accum = np.concatenate(
                [state.audio_accum, np.asarray(block, dtype=np.float32)])
        self._wake.set()

    def finish_streaming_transcribe(self, state):
        """発話全体をまとめて認識し直して確定する。

        途中経過は最後まで聞き終える前の結果なので、確定はここで出し直す。
        """
        with self._lock:
            state._final = True
            self._state = None     # 以後ワーカーはこの state に書かない
        if len(state.audio_accum) < SAMPLE_RATE * _MIN_SEC:
            return
        text = self._transcribe(state.audio_accum)
        if text:
            state.text = text

    # ── 内部 ─────────────────────────────

    def _transcribe(self, audio):
        """WAV に書いてヘルパへ渡し、認識結果を受け取る。"""
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
        """溜まった音声を発話の頭から認識し直し、state.text を更新し続ける。"""
        while True:
            self._wake.wait()
            with self._lock:
                state = self._state
                if (state is None or state._final or
                        len(state.audio_accum) - state._decoded_upto
                        < SAMPLE_RATE * _REFRESH_SEC):
                    # いま起きる理由がない。次の追記まで眠る。
                    # clear はロック内で行う。外だと「clear の直前に追記された
                    # 分」の起こし損ねが起きる(追記もロック内なので競合しない)
                    self._wake.clear()
                    continue
                audio = state.audio_accum          # 追記は配列を作り直すので
                state._decoded_upto = len(audio)   # この参照は不変で安全
            if len(audio) < SAMPLE_RATE * _MIN_SEC:
                continue
            text = self._transcribe(audio)
            with self._lock:
                if state is self._state and not state._final and text:
                    state.text = text


def _write_wav(path, audio):
    """float32(-1..1) を 16bit モノラル 16kHz の WAV にする。"""
    pcm = np.clip(np.asarray(audio, dtype=np.float32), -1.0, 1.0)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes((pcm * 32767.0).astype("<i2").tobytes())
