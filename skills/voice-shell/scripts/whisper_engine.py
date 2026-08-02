#!/usr/bin/env python3
"""Whisper をストリーミングとして使えるようにする。

Whisper は 30 秒の音声をまとめて処理する作りで、本来ストリーミング向き
ではない。そこで、溜まった音声を短い間隔で繰り返し認識し直す形にする。
Qwen3-ASR の streaming_transcribe と同じ顔にしてあるので、asr_mic.py 側は
どちらのモデルでも同じコードで扱える。

Qwen3-ASR との違い（実測とベンチマークより）:
  - 固有名詞に強い。人名・製品名の取りこぼしが少ない
  - 文字誤り率そのものは Qwen3-ASR がやや優れる
  - 騒がしい場所や複数人の声には Whisper のほうが崩れにくい
"""
import sys

import numpy as np

SAMPLE_RATE = 16000

# Whisper は "ja" のような 2 文字コードしか受け付けない。
# voice-shell は Qwen3-ASR に合わせて "Japanese" と綴りで渡してくるので、
# ここで直す（そのまま渡すと ValueError で落ちる）。
_LANG = {
    "japanese": "ja", "english": "en", "chinese": "zh", "korean": "ko",
    "french": "fr", "german": "de", "spanish": "es", "italian": "it",
    "portuguese": "pt", "russian": "ru",
}


def _lang_code(name):
    """「Japanese」「ja」「ja-JP」のどれで来ても "ja" にする。"""
    if not name:
        return None
    s = str(name).strip().lower()
    return _LANG.get(s, s.split("-")[0][:2])

# 認識をやり直す間隔。短いほど早く文字が出るが、そのぶん推論が増える。
# 溜まった音声を毎回まるごと読み直すので、長い発話ほど 1 回が重くなる。
REFRESH_SEC = 0.7

# ここを超えたら、それより前は確定したものとして切り離す。
# 際限なく伸ばすと 1 回の認識が遅くなっていく。
MAX_WINDOW_SEC = 28.0


class WhisperState:
    """発話 1 つ分の途中経過。Qwen3-ASR の ASRStreamingState に相当する。"""

    def __init__(self, language=None):
        # 名前は Qwen3-ASR の state に合わせる。asr_mic は発話の長さを
        # 測るのにこれを読む（属性が無いとそこで落ちる）。
        self.audio_accum = np.zeros(0, dtype=np.float32)
        self.text = ""
        self.language = language
        self.settled = ""      # 窓から押し出して確定させたぶん
        self._since_run = 0.0  # 前回の認識からの秒数


class WhisperModel:
    """faster-whisper を Qwen3-ASR と同じ呼び出し方で使えるようにする。"""

    def __init__(self, name="large-v3-turbo", device="cuda",
                 compute_type="float16", language=None):
        from faster_whisper import WhisperModel as FW

        print(f"Whisper ({name} / {compute_type}) を読み込んでいます…",
              file=sys.stderr, flush=True)
        self._m = FW(name, device=device, compute_type=compute_type)
        self._lang = _lang_code(language) or "ja"

    # ── Qwen3-ASR と同じ 3 つ ──────────────────────

    def init_streaming_state(self, language=None, **_ignored):
        """発話の始まり。使わない引数は Qwen3-ASR に合わせて受け流す。"""
        return WhisperState(_lang_code(language) or self._lang)

    def streaming_transcribe(self, pcm16k, state):
        """音を受けて、頃合いを見て認識し直す。"""
        state.audio_accum = np.concatenate([state.audio_accum, pcm16k])
        state._since_run += len(pcm16k) / SAMPLE_RATE

        if state._since_run < REFRESH_SEC:
            return state
        state._since_run = 0.0

        # 窓が長くなりすぎたら、前半を確定させて切り離す
        if len(state.audio_accum) / SAMPLE_RATE > MAX_WINDOW_SEC:
            keep = int(MAX_WINDOW_SEC * SAMPLE_RATE * 0.5)
            head, state.audio_accum = state.audio_accum[:-keep], state.audio_accum[-keep:]
            state.settled += self._run(head, state)

        state.text = state.settled + self._run(state.audio_accum, state)
        return state

    def finish_streaming_transcribe(self, state):
        """発話の終わり。最後にもう一度だけ通す。"""
        if state.audio_accum.size:
            state.text = state.settled + self._run(state.audio_accum, state)
        return state

    # ── 中身 ──────────────────────────────────

    def _run(self, audio, state) -> str:
        """溜まった音声を認識する。

        beam_size=1 と condition_on_previous_text=False は、途中経過が
        コロコロ変わるのを抑えるため。前の推測を引きずらせると、認識を
        やり直すたびに文が書き換わって読みにくい。
        """
        if audio.size < SAMPLE_RATE * 0.3:      # 短すぎると誤認識しやすい
            return ""
        segments, info = self._m.transcribe(
            audio,
            language=_lang_code(state.language) or self._lang,
            beam_size=1,
            condition_on_previous_text=False,
            vad_filter=True,                    # 無音を捨てて幻聴を減らす
            vad_parameters={"min_silence_duration_ms": 300},
        )
        state.language = info.language or state.language
        return "".join(s.text for s in segments).strip()


def load(args):
    """asr_mic.load_model から呼ばれる。"""
    return WhisperModel(
        name=getattr(args, "model", None) or "large-v3-turbo",
        device=getattr(args, "whisper_device", None) or "cuda",
        compute_type=getattr(args, "whisper_compute", None) or "float16",
        language=getattr(args, "language", None),
    )
