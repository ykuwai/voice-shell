"""マイク入力 → Qwen3-ASR ストリーミング認識の共通処理。

realtime.py（端末表示）と webapp.py（ブラウザ表示）が共有する。
両者の違いは「認識イベントをどう出力するか」だけなので、この module は
イベントを yield するところまでを受け持つ。
"""
import shutil
import subprocess
import sys
from typing import Iterator, Tuple

import numpy as np
from qwen_asr.inference.utils import SAMPLE_RATE

BLOCK_SEC = 0.1  # マイクを読む単位

# 既定の録音デバイス。OS ごとに指定の仕方が違う。
if sys.platform == "darwin":
    DEFAULT_DEVICE = ":0"              # avfoundation の音声デバイス番号
elif sys.platform.startswith("win"):
    DEFAULT_DEVICE = "audio=default"   # dshow のデバイス名
else:
    DEFAULT_DEVICE = "pipewire"        # ALSA 経由（PipeWire プラグイン）


def add_common_args(p):
    """realtime.py / webapp.py で共通の引数を登録する。"""
    p.add_argument("--model", default="Qwen/Qwen3-ASR-1.7B", help="モデル名")
    p.add_argument("--language", default=None,
                   help="言語を固定 (例: Japanese)。省略で自動判定")
    p.add_argument("--device", default=DEFAULT_DEVICE,
                   help="録音デバイス。Linux は arecord の -D（pipewire, plughw:2,0）、"
                        "macOS は avfoundation の番号（:0）、Windows は dshow の名前"
                        "（audio=マイク名）")
    p.add_argument("--input-samplerate", type=int, default=44100,
                   help="マイクの録音レート。16kHz に変換して推論する")
    p.add_argument("--chunk-size-sec", type=float, default=1.0,
                   help="推論する音声チャンク長（秒）。小さいほど低遅延・高負荷")
    p.add_argument("--unfixed-chunk-num", type=int, default=2,
                   help="先頭 N チャンクは直前の認識結果を prompt に使わない")
    p.add_argument("--unfixed-token-num", type=int, default=5,
                   help="prompt 再利用時に末尾 K トークンを捨てて揺れを抑える")
    p.add_argument("--max-model-len", type=int, default=16384,
                   help="vLLM の最大シーケンス長。VRAM が少ない場合は下げる")
    p.add_argument("--gpu-memory-utilization", type=float, default=0.85,
                   help="vLLM が使う VRAM の割合")
    p.add_argument("--silence-threshold", type=float, default=0.054,
                   help="この RMS 未満を無音とみなす（マイクのノイズフロアに合わせる）")
    p.add_argument("--silence-duration", type=float, default=1.5,
                   help="この秒数だけ無音が続いたら発話を確定する")
    p.add_argument("--max-utterance-sec", type=float, default=30.0,
                   help="1発話の目安の上限。超えても喋っている間は切らず、"
                        "息継ぎを待って区切る（この2倍で強制確定）")
    p.add_argument("--pause-sec", type=float, default=0.4,
                   help="上限を超えたあと、この秒数の息継ぎがあれば区切る")
    return p


def load_model(args):
    """ストリーミング用に vLLM バックエンドでモデルを読み込む。

    max_model_len を明示しないと既定値 65536 が KV キャッシュに 7GiB 要求し、
    16GB GPU では起動に失敗する。
    """
    from qwen_asr import Qwen3ASRModel

    model = Qwen3ASRModel.LLM(
        model=args.model,
        gpu_memory_utilization=args.gpu_memory_utilization,
        max_model_len=args.max_model_len,
        max_new_tokens=64,
    )
    _kill_engine_on_exit()
    return model


def _kill_engine_on_exit():
    """終了時に vLLM のワーカープロセスを確実に落とす。

    Ctrl-C や kill で親が終わっても VLLM::EngineCore が残り、VRAM を
    12GB 掴んだままになることがあるため、自分の子プロセスを始末する。
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
    # SIGTERM でも atexit を通るようにする（既定では通らない）
    _signal.signal(_signal.SIGTERM, lambda *_: sys.exit(0))


def mic_command(device: str, in_sr: int) -> list:
    """生 PCM を標準出力に流すコマンドを組む。

    Linux は arecord（PipeWire がマイクを占有していても取れる）。
    macOS / Windows は ffmpeg を使う。device に "default" 以外を渡せば
    デバイス名・番号を指定できる。
    """
    if sys.platform == "darwin":
        if shutil.which("ffmpeg") is None:
            sys.exit("ffmpeg が見つかりません (brew install ffmpeg)")
        # avfoundation は ":<音声デバイス番号>" 形式。既定は ":0"
        src = device if device.startswith(":") else ":0"
        return ["ffmpeg", "-hide_banner", "-loglevel", "error",
                "-f", "avfoundation", "-i", src,
                "-ac", "1", "-ar", str(in_sr), "-f", "s16le", "-"]

    if sys.platform.startswith("win"):
        if shutil.which("ffmpeg") is None:
            sys.exit("ffmpeg が見つかりません (winget install ffmpeg)")
        # dshow はデバイス名指定。一覧は:
        #   ffmpeg -list_devices true -f dshow -i dummy
        src = device if device.startswith("audio=") else "audio=default"
        return ["ffmpeg", "-hide_banner", "-loglevel", "error",
                "-f", "dshow", "-i", src,
                "-ac", "1", "-ar", str(in_sr), "-f", "s16le", "-"]

    if shutil.which("arecord") is None:
        sys.exit("arecord が見つかりません (alsa-utils をインストールしてください)")
    return ["arecord", "-D", device, "-f", "S16_LE",
            "-r", str(in_sr), "-c", "1", "-t", "raw", "-q"]


def read_blocks(device: str, in_sr: int) -> Iterator[Tuple[np.ndarray, float, float]]:
    """マイクを読み続け、(16kHz PCM, 長さ秒, RMS) を yield する。

    PipeWire がマイクを占有していると PortAudio からは見えないため、
    arecord に生 PCM を吐かせてパイプで受け取る。
    """
    proc = subprocess.Popen(mic_command(device, in_sr), stdout=subprocess.PIPE)
    nbytes = int(in_sr * BLOCK_SEC) * 2  # 16bit モノラル

    if in_sr == SAMPLE_RATE:
        to_16k = lambda b: b  # noqa: E731
    else:
        import soxr
        print(f"マイクを {in_sr}Hz で録音し {SAMPLE_RATE}Hz に変換します", file=sys.stderr)
        # ストリーム用リサンプラを一度だけ構築する。ブロックごとに
        # soxr.resample() を呼ぶとフィルタの生成・破棄が毎回走り約4倍遅い。
        stream = soxr.ResampleStream(in_sr, SAMPLE_RATE, 1, dtype="float32")
        to_16k = stream.resample_chunk

    try:
        while True:
            raw = proc.stdout.read(nbytes)
            if not raw:
                return
            block = to_16k(np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0)
            # block.dot(block) は二乗の一時配列を作らない
            rms = float(np.sqrt(block.dot(block) / block.size)) if block.size else 0.0
            yield block, len(block) / SAMPLE_RATE, rms
    finally:
        proc.terminate()


def stream_utterances(model, args, should_stop=lambda: False):
    """マイクを読み、認識イベントを yield する。

    yield されるイベント（辞書）:
        {"type": "level",   "rms": float, "speaking": bool}   毎ブロック
        {"type": "partial", "text": str, "language": str}     認識途中
        {"type": "final",   "text": str, "language": str}     発話確定

    無音が silence_duration 続いたら確定する。max_utterance_sec を超えた場合も
    喋っている最中には切らず、息継ぎ（pause_sec）を待ってから区切る。
    ライブラリ側に発話区切り（VAD）は無いため、ここで RMS を見て判定している。
    """
    def new_state():
        return model.init_streaming_state(
            language=args.language,
            unfixed_chunk_num=args.unfixed_chunk_num,
            unfixed_token_num=args.unfixed_token_num,
            chunk_size_sec=args.chunk_size_sec,
        )

    state = new_state()
    silence_run = 0.0    # 連続無音の秒数
    speech_seen = False  # 現発話中に音声を検出したか
    last_text = ""

    def finish():
        model.finish_streaming_transcribe(state)
        return ({"type": "final", "text": state.text, "language": state.language}
                if state.text.strip() else None)

    for block, dur, rms in read_blocks(args.device, args.input_samplerate):
        if should_stop():
            break

        speaking = rms >= args.silence_threshold
        yield {"type": "level", "rms": rms, "speaking": speaking}

        if speaking:
            speech_seen = True
            silence_run = 0.0
        else:
            silence_run += dur

        # 発話が始まる前の無音は推論に回さない
        if not speech_seen:
            continue

        model.streaming_transcribe(block, state)

        if state.text != last_text:
            last_text = state.text
            if state.text.strip():
                yield {"type": "partial", "text": state.text, "language": state.language}

        accum_sec = len(state.audio_accum) / SAMPLE_RATE

        # 話し終わった（無音が続いた）なら確定する
        done_talking = silence_run >= args.silence_duration
        # 長すぎる発話は打ち切るが、喋っている最中には切らない。
        # 上限を超えたら、ごく短い息継ぎでも区切りとして扱う。
        too_long = accum_sec >= args.max_utterance_sec and silence_run >= args.pause_sec
        # それでも延び続けるときの歯止め（推論が重くなりすぎるのを防ぐ）
        way_too_long = accum_sec >= args.max_utterance_sec * 2

        if done_talking or too_long or way_too_long:
            done = finish()
            if done:
                yield done
            state, silence_run, speech_seen, last_text = new_state(), 0.0, False, ""

    # 中断時に途中の発話を捨てない
    if speech_seen:
        done = finish()
        if done:
            yield done
