"""Apple Silicon で Qwen3-ASR をローカル実行するエンジン(MLX 版)。

CUDA が無い Mac 用。`--engine mlx` で使う(macOS では既定)。
vLLM 版の qwen_asr と同じ3メソッド(init_streaming_state /
streaming_transcribe / finish_streaming_transcribe)を持つアダプタを返すので、
asr_mic.stream_utterances() からは local と同じ経路で動く。
音声はこの Mac の中だけで処理される(クラウドには送らない)。

実装は mlx-qwen3-asr(https://github.com/moona3k/mlx-qwen3-asr)の
一括 transcribe だけを使う。

## 途中経過も確定も「発話全体の認識し直し」にしている

最初は同ライブラリの増分デコード(KV キャッシュ再利用)で partial を
出していたが、チャンク境界ごとに読点が入り語も割れる(実測で
「くだ。ください」)。vLLM 版の「毎秒すべてを認識し直す」表示と
比べて明らかに見劣りする。

そこで partial もワーカースレッドで発話全体を認識し直す方式にした。
1回の認識は RTF 約0.3 なので、更新間隔は発話長×0.3 で自然に伸びる
(5秒の発話なら約1.5秒ごと)。スレッドに逃がしたのはマイク読み取りを
止めないため — メインループで recognize すると、その間 ffmpeg のパイプが
詰まり、長い発話で録音を取りこぼす。確定も同じ一括認識(こちらは
メインスレッド。発話は終わっているので待たせてよい)。
"""
import os
import sys
import threading

import numpy as np

from asr_mic import SAMPLE_RATE

# 既定は精度重視の 1.7B(float16 で約3.4GB)。メモリが厳しければ
# `--model Qwen/Qwen3-ASR-0.6B` に変える。
DEFAULT_MODEL = "Qwen/Qwen3-ASR-1.7B"

# これ以上の新しい音声が溜まったら partial を認識し直す
_REFRESH_SEC = 0.8


def load(args):
    """モデルを読み込み、qwen_asr 互換のアダプタを返す。"""
    try:
        from mlx_qwen3_asr import load_model
    except ImportError:
        sys.exit("mlx-qwen3-asr が必要です:  pip install mlx-qwen3-asr")

    from huggingface_hub import snapshot_download

    repo = args.model or DEFAULT_MODEL
    # トークナイザはローカルパスしか受け付けないため、先に解決しておく
    path = repo if os.path.isdir(repo) else snapshot_download(repo)
    model, _ = load_model(path)

    adapter = _MLXModel(model)
    adapter.warmup()
    return adapter


class _State:
    """asr_mic が触る3つの属性(text / language / audio_accum)だけ持つ。"""

    __slots__ = ("text", "language", "audio_accum",
                 "_forced", "_decoded_upto", "_final")

    def __init__(self, language):
        self.text = ""
        self.language = language or "unknown"
        self.audio_accum = np.empty(0, dtype=np.float32)
        self._forced = language
        self._decoded_upto = 0   # 最後に認識を始めた時点のサンプル数
        self._final = False


class _MLXModel:
    """qwen_asr.Qwen3ASRModel と同じ顔をした MLX 版アダプタ。"""

    def __init__(self, model):
        self._model = model
        self._lock = threading.Lock()        # state の付け替えと追記を守る
        self._decode_mutex = threading.Lock()  # モデルは同時に1認識だけ
        self._wake = threading.Event()
        self._state = None
        threading.Thread(target=self._worker, daemon=True).start()

    # unfixed_chunk_num 等は vLLM 版の口を揃えるためだけに受け取り、使わない
    def init_streaming_state(self, language=None, **_ignored):
        st = _State(language)
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

        partial は途中の音声しか見ていないので、確定はここで出した
        全体の認識結果に必ず置き換える(発話長×0.3 秒ほどかかる)。
        """
        with self._lock:
            state._final = True
            self._state = None     # 以後ワーカーはこの state に書かない
        if len(state.audio_accum) == 0:
            return
        text, lang = self._transcribe(state.audio_accum, state._forced)
        state.text = text
        if lang:
            state.language = lang

    def warmup(self):
        """無音を一度流して Metal カーネルのコンパイルを済ませる。

        これをやらないと最初の発話だけ数秒余計にかかる。
        """
        self._transcribe(np.zeros(SAMPLE_RATE * 2, dtype=np.float32), "Japanese")

    # ── 内部 ─────────────────────────────

    def _transcribe(self, audio, language):
        from mlx_qwen3_asr import transcribe
        with self._decode_mutex:
            r = transcribe(audio=audio, model=self._model,
                           language=language, verbose=False)
        return (r.text or "").strip(), (r.language or "")

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
                    # clear はロック内で行う — 外だと「clear の直前に追記された
                    # 分」の起こし損ねが起きる(追記もロック内なので競合しない)
                    self._wake.clear()
                    continue
                audio = state.audio_accum          # 追記は配列を作り直すので
                state._decoded_upto = len(audio)   # この参照は不変で安全
            text, lang = self._transcribe(audio, state._forced)
            with self._lock:
                if state is self._state and not state._final and text:
                    state.text = text
                    if lang:
                        state.language = lang
