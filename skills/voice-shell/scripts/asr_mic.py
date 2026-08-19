"""マイク入力 → Qwen3-ASR ストリーミング認識の共通処理。

realtime.py（端末表示）と webapp.py（ブラウザ表示）が共有する。
両者の違いは「認識イベントをどう出力するか」だけなので、この module は
イベントを yield するところまでを受け持つ。
"""
import re
import os
import shutil
import subprocess
import sys
import time
from collections import deque
from typing import Iterator, Tuple

import numpy as np

# 音声認識モデルが期待するサンプルレート。クラウドの API を使うときは
# qwen_asr が入っていないので、その場合も動くよう固定値で持つ。
SAMPLE_RATE = 16000

BLOCK_SEC = 0.1  # マイクを読む単位

# 発話の頭に付ける「しきい値を超える直前」の長さ。
# 子音の立ち上がりは RMS が低く、超えた瞬間から渡すと語頭が欠ける
# （実測: 「反応がなかったので」が「なかったので」に、
#  「Apple の認識が」が「の認識が」になった）。0.3 秒では足りず 0.6 秒にした。
# 無音を余分に渡すことになるが、認識側は無音を無視するので実害はない。
PREROLL_SEC = 0.6

# 無音とみなす RMS の既定値。マイクごとに違うので実測して決める値だが、
# 開発機の値をそのまま持ってくると別の環境で「全く反応しない」になる。
# Linux 機の 0.054 は Mac の USB マイク（Samson Go Mic）には高すぎ、
# 普通の声量では一度も超えなかった（環境ノイズは 0.003 だった）。
DEFAULT_SILENCE_THRESHOLD = 0.015 if sys.platform == "darwin" else 0.054

# 「システムの既定を使う」を表す値。OS をまたいで同じ綴りにしておき、
# 実際の指定の仕方（avfoundation の ":default"、dshow のデバイス名、
# ALSA の "pipewire"）は mic_command が解決する。
#
# 以前は OS ごとに別々の綴りを既定にしていたが、":0" と "audio=default" は
# list_mics() が返す一覧のどれとも一致しなかった。画面のプルダウンは
# 一覧と突き合わせて選択状態を決めるため、「どれも選ばれていない」状態になり、
# 空欄に見えていた。
SYSTEM_DEFAULT = "default"
DEFAULT_DEVICE = SYSTEM_DEFAULT


# macOS には CUDA が無く vLLM 版は動かない。MLX 版(mlx)も動くが約4GB 積むので、
# OS 付属のオンデバイス認識(apple)を既定にする。
# 直接 asr_mic を叩いたときの既定。通常の経路（voice-shell.sh start）は
# voice_daemon.resolve_engine が「指定 > 前回の選択 > このブラウザ」で決めるので、
# ここには来ない。
_DEFAULT_ENGINE = "apple" if sys.platform == "darwin" else "local"


def add_common_args(p):
    """各スクリプトで共通の引数を登録する。"""
    p.add_argument("--engine", default=os.environ.get("VOICE_SHELL_ENGINE", _DEFAULT_ENGINE),
                   help="認識エンジン。local（Qwen3-ASR を NVIDIA GPU + vLLM で動かす）、"
                        "apple（macOS 26 付属のオンデバイス認識。軽い）、"
                        "mlx（Qwen3-ASR を Apple Silicon の GPU で動かす）、"
                        "whisper（Whisper を GPU で動かす。固有名詞に強い）、"
                        "home-lan（家の LAN にある GPU 機に任せる）、"
                        "クラウドの API 名。macOS の既定は apple。"
                        "VOICE_SHELL_ENGINE でも指定できる")
    p.add_argument("--whisper-compute", default=None,
                   help="Whisper の精度と VRAM の兼ね合い（float16 / int8）")
    p.add_argument("--whisper-device", default=None,
                   help="Whisper を動かす場所（cuda / cpu）")
    p.add_argument("--whisper-language", default=None,
                   help="Whisper の言語を固定する（ja / en）。既定は自動判定。"
                        "固定すると、その言語に訳されて出るので普段は指定しない")
    p.add_argument("--server", default=os.environ.get("VOICE_SHELL_SERVER"),
                   help="--engine home-lan のときの接続先。"
                        "VOICE_SHELL_SERVER でも指定できる")
    p.add_argument("--model", default=None,
                   help="モデル名。省略するとエンジンごとの既定値を使う")
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
    p.add_argument("--silence-threshold", type=float, default=DEFAULT_SILENCE_THRESHOLD,
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
    """認識エンジンを用意する。

    local なら Qwen3-ASR を vLLM で、mlx なら Qwen3-ASR を MLX（Apple
    Silicon）で、whisper なら Whisper を、それぞれこの PC の GPU で動かす。
    apple は macOS 26 付属のオンデバイス認識（GPU メモリを積まない）。
    それ以外はクラウドの API か、家の GPU 機を使う。
    """
    # 後片付けはどのエンジンでも要る。録音の ffmpeg / arecord はエンジンに
    # 関係なく子プロセスとして走るため、分岐に入る前に登録する。
    # （ここが local の中にあった頃、macOS の apple / mlx は登録を通らず、
    #   stop のたびに録音プロセスだけが孤児として残り続けていた）
    _kill_engine_on_exit()

    if args.engine == "apple":
        import engine_apple
        return engine_apple.load(args)

    if args.engine == "whisper":
        import whisper_engine
        return whisper_engine.load(args)

    if args.engine == "mlx":
        import engine_mlx
        return engine_mlx.load(args)

    if args.engine != "local":
        import engines
        return engines.load(args)

    # max_model_len を明示しないと既定値 65536 が KV キャッシュに 7GiB 要求し、
    # 16GB GPU では起動に失敗する。
    from qwen_asr import Qwen3ASRModel

    model = Qwen3ASRModel.LLM(
        model=args.model or "Qwen/Qwen3-ASR-1.7B",
        gpu_memory_utilization=args.gpu_memory_utilization,
        max_model_len=args.max_model_len,
        max_new_tokens=64,
    )
    return model


def _kill_engine_on_exit():
    """終了時に子プロセスを確実に落とす。

    Ctrl-C や kill で親が終わっても、子が残って資源を掴んだままになる:

    - 録音の ffmpeg / arecord がマイクを開けっぱなしにする（全エンジン共通）
    - vLLM の VLLM::EngineCore が VRAM を 12GB 掴む（local）
    - 認識ヘルパが残る（apple）

    SIGTERM は既定で atexit を通らないため、sys.exit に変換してから
    自分の直接の子を始末する。voice-shell.sh stop は SIGTERM を送る。
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


# ── 使える認識エンジン ──────────────────
#
# ブラウザの認識（Web Speech API）は何も入れずに動くので、これを既定に置く。
# 手元で完結させたい人や、精度・言語で選びたい人のために、入っているものを
# 一覧して選べるようにする。入っていないものは並べても選べないだけなので出さない。

ENGINE_LABELS = {
    "apple":    "Apple のオンデバイス認識（軽い・手元だけ）",
    "whisper":  "Whisper（固有名詞に強い・手元だけ）",
    "mlx":      "Qwen3-ASR / MLX（手元だけ）",
    "local":    "Qwen3-ASR / GPU（手元だけ）",
    "home-lan": "LAN の GPU 機に任せる",
}


def _mac_version():
    try:
        return int(subprocess.run(["sw_vers", "-productVersion"],
                                  capture_output=True, timeout=5)
                   .stdout.decode().split(".")[0])
    except Exception:
        return 0


def available_engines() -> list:
    """この環境で実際に使えるエンジンを返す。

    import できるかどうかで見る（実際に読み込むと重いので find_spec だけ）。
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
    if sys.platform == "darwin" and have("mlx_qwen3_asr"):
        out.append("mlx")
    if have("qwen_asr"):
        out.append("local")
    import pathlib
    conf = pathlib.Path(os.environ.get("XDG_CONFIG_HOME",
                                       pathlib.Path.home() / ".config"))
    if (conf / "voice-shell" / "remote.json").exists():
        out.append("home-lan")
    return [{"id": e, "label": ENGINE_LABELS.get(e, e)} for e in out]


def list_mics() -> list:
    """使えるマイクの一覧を返す。[{"id": ..., "label": ...}, ...]

    OS ごとに取り方が違うので、ここで吸収する。
    """
    # 一覧の先頭は必ず「システムの既定」。ここが無いと、既定のまま使っている人の
    # プルダウンがどれとも一致せず、空欄に見える。
    out = [{"id": SYSTEM_DEFAULT, "label": "システムの既定"}]
    try:
        if sys.platform == "darwin":
            # ffmpeg はデバイス一覧を stderr に出し、終了コードも 1 になる
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
            # arecord -L は「名前」と「説明」が交互に並ぶ。
            # default / pulse / pipewire は同じサウンドサーバへの別経路。
            # 「システムの既定」は先頭に入れてあるので、ここでは足さない。

            r = subprocess.run(["arecord", "-L"], capture_output=True, timeout=10)
            name = None
            for line in r.stdout.decode(errors="replace").splitlines():
                if not line.startswith((" ", "\t")):
                    name = line.strip() if line.strip().startswith("plughw:") else None
                    if name:
                        out.append({"id": name, "label": name})
                elif name and out and out[-1]["id"] == name:
                    # 説明のほうが分かりやすいので、そちらを名前にする
                    out[-1]["label"] = line.strip()
                    name = None
    except (OSError, subprocess.SubprocessError):
        pass

    return out


def mic_command(device: str, in_sr: int) -> list:
    """生 PCM を標準出力に流すコマンドを組む。

    Linux は arecord（PipeWire がマイクを占有していても取れる）。
    macOS / Windows は ffmpeg を使う。device に "default" 以外を渡せば
    デバイス名・番号を指定できる。
    """
    if sys.platform == "darwin":
        if shutil.which("ffmpeg") is None:
            sys.exit("ffmpeg が見つかりません (brew install ffmpeg)")
        # avfoundation は ":<音声デバイス番号>" 形式。":default" も受け付ける
        # （実測: システムの既定入力から録れる）。
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
        # dshow はデバイス名指定。一覧は:
        #   ffmpeg -list_devices true -f dshow -i dummy
        # avfoundation と違い「既定」を表す綴りが無いので、
        # 一覧の先頭（通常はシステムの既定）に解決する。
        if device == SYSTEM_DEFAULT:
            # list_mics() の先頭はセンチネル自身なので、実デバイスだけを見る。
            # ここを外すと dshow に存在しない "-i default" が渡り、既定のまま
            # 使っている人は一度も録音できない。
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
    # PipeWire / PulseAudio はどちらもサウンドサーバ側で既定を解決してくれる
    if device == SYSTEM_DEFAULT:
        device = "pipewire"
    return ["arecord", "-D", device, "-f", "S16_LE",
            "-r", str(in_sr), "-c", "1", "-t", "raw", "-q"]


def read_blocks(device: str, in_sr: int,
                want_device=None, on_switch=None) -> Iterator[Tuple[np.ndarray, float, float]]:
    """マイクを読み続け、(16kHz PCM, 長さ秒, RMS) を yield する。

    PipeWire がマイクを占有していると PortAudio からは見えないため、
    arecord に生 PCM を吐かせてパイプで受け取る。

    want_device() が別のデバイス名を返したら、録音プロセスだけ差し替える。
    モデルは載せたままなので、マイクの切り替えは待たされない。

    on_switch(device) は実際に切り替えが完了した時点で呼ばれる。ビューアが
    「本当に切り替わったか」を確定情報として表示できるようにするため
    （ブラウザ側の楽観的な表示だけだと、実際に切り替わったかは分からない）。
    """
    def start(dev):
        return subprocess.Popen(mic_command(dev, in_sr), stdout=subprocess.PIPE)

    def make_resampler():
        if in_sr == SAMPLE_RATE:
            return lambda b: b
        import soxr
        # ストリーム用リサンプラを一度だけ構築する。ブロックごとに
        # soxr.resample() を呼ぶとフィルタの生成・破棄が毎回走り約4倍遅い。
        return soxr.ResampleStream(in_sr, SAMPLE_RATE, 1, dtype="float32").resample_chunk

    current = device
    proc = start(current)
    nbytes = int(in_sr * BLOCK_SEC) * 2  # 16bit モノラル
    to_16k = make_resampler()
    if in_sr != SAMPLE_RATE:
        print(f"マイクを {in_sr}Hz で録音し {SAMPLE_RATE}Hz に変換します", file=sys.stderr)

    # 録音の ffmpeg が理由もなく落ちることがある（Windows で稀に、パイプへの
    # 書き込みが "Invalid argument" で失敗する現象を実測。再現条件は不明）。
    # 頼んでもいない終了は「マイクが壊れた」ではなく「録音プロセスが死んだ」
    # だけなので、デーモンごと落とさず同じデバイスで立て直す。
    MAX_QUICK_CRASHES = 5     # これを超えたら本当に壊れているとみなして諦める
    crash_count = 0
    last_crash_at = 0.0

    try:
        while True:
            # 切り替えを頼まれていたら録音だけやり直す
            if want_device is not None:
                asked = want_device()
                if asked and asked != current:
                    proc.terminate()
                    current = asked
                    proc = start(current)
                    to_16k = make_resampler()   # 履歴を持たせない
                    print(f"マイクを切り替えました: {current}", file=sys.stderr, flush=True)
                    if on_switch is not None:
                        on_switch(current)

            raw = proc.stdout.read(nbytes)
            if not raw:
                now = time.monotonic()
                # 短時間に何度も落ちるなら、立て直しても無駄なので諦める
                if now - last_crash_at > 30:
                    crash_count = 0
                crash_count += 1
                last_crash_at = now
                if crash_count > MAX_QUICK_CRASHES:
                    print(f"録音プロセスが繰り返し落ちるため諦めます"
                          f"（{MAX_QUICK_CRASHES}回連続）。マイクの状態を確認してください。",
                          file=sys.stderr, flush=True)
                    return
                print(f"録音プロセスが予期せず終了したため、立て直します"
                      f"（{crash_count}/{MAX_QUICK_CRASHES}）: {current}",
                      file=sys.stderr, flush=True)
                time.sleep(0.5)   # 立て直し直後にまた即死するのを避ける
                proc = start(current)
                to_16k = make_resampler()
                continue
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
    # クラウドの API と家の GPU 機は自前でストリームを持つので、そちらに任せる。
    # local / apple / mlx / whisper はこの下の共通処理を通る（同じ 3 メソッドを持つ）。
    if args.engine not in ("local", "apple", "mlx", "whisper"):
        import engines
        yield from engines.stream(model, args, should_stop)
        return

    def new_state():
        return model.init_streaming_state(
            language=args.language,
            unfixed_chunk_num=args.unfixed_chunk_num,
            unfixed_token_num=args.unfixed_token_num,
            chunk_size_sec=args.chunk_size_sec,
        )

    state = new_state()
    # ビューアから変えられる調整値（感度・確定までの無音秒数）を読み直す。
    # 毎ブロック見るほど変わるものではないので 0.5 秒おきにする。
    want_tuning = getattr(args, "want_tuning", None)
    tuning_wait = 0
    silence_run = 0.0    # 連続無音の秒数
    speech_seen = False  # 現発話中に音声を検出したか
    last_text = ""
    # しきい値を超える直前のブロックを溜めておき、発話の頭に付け足す
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
                # 最小文字数とつなぎ言葉の除去は voice_daemon.py が
                # 同じ args を見るので、ここで入れておけばそちらにも効く
                if isinstance(tuned.get("min_chars"), (int, float)):
                    args.min_chars = int(tuned["min_chars"])
                if isinstance(tuned.get("strip_fillers"), bool):
                    args.strip_fillers = tuned["strip_fillers"]
                # 認識言語（Whisper 限定）。次の発話（次の new_state()）
                # から効く。他のエンジンは綴りが違うので触らない
                if args.engine == "whisper" and isinstance(tuned.get("language"), str):
                    args.language = tuned["language"] or None

        speaking = rms >= args.silence_threshold
        yield {"type": "level", "rms": rms, "speaking": speaking}

        if speaking:
            speech_seen = True
            silence_run = 0.0
        else:
            silence_run += dur

        # 発話が始まる前の無音は推論に回さない（ただし直前の分だけは取っておく）
        if not speech_seen:
            preroll.append(block)
            continue

        # 発話の1ブロック目なら、しきい値を超える直前の音も一緒に渡す
        while preroll:
            model.streaming_transcribe(preroll.popleft(), state)

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
