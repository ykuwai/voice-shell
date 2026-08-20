"""マイク入力 → ストリーミング認識の共通処理。

常駐デーモン（voice_daemon.py）とビューア（viewer.py）が共有する。
どこへ出すかは呼ぶ側の都合なので、この module は認識イベントを
yield するところまでを受け持つ。
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

# 認識エンジンが期待するサンプルレート。どのエンジンが入っているかに
# よらず同じ値なので、ライブラリから引かずに固定値で持つ。
SAMPLE_RATE = 16000

BLOCK_SEC = 0.1  # マイクを読む単位
# 喋り続けている限り区切らない。長く話して考えを最後まで伝えることの方が、
# 早く届くことより大事だという判断（一度 60 秒で区切る形を入れたが戻した）。
# 溜めた音声をそのまま推論に渡すので、最後の歯止めだけ置く。
HARD_UTTERANCE_CAP = 300.0

# 発話の頭に付ける「しきい値を超える直前」の長さ。
# 子音の立ち上がりは RMS が低く、超えた瞬間から渡すと語頭が欠ける
# （実測では「反応がなかったので」が「なかったので」に、
#  「Apple の認識が」が「の認識が」になった）。0.3 秒では足りず 0.6 秒にした。
# 無音を余分に渡すことになるが、認識側は無音を無視するので実害はない。
PREROLL_SEC = 0.6

# 中身が全部ゼロのブロックが、これだけ続いたら繋がっていないとみなす。
# 生きている装置なら、どんなに静かな部屋でも暗騒音が乗る（実測で 0.0005 前後、
# いま動いている機械でも 0.0022 だった）。16bit が全ビットゼロで並ぶのは装置が
# 死んでいるときだけなので、静かな部屋と取り違えることはない。
# 数秒では短すぎる。マイク本体のミュートでもゼロを出す装置があり、黙るたびに
# 開き直すことになる。長すぎれば戻るまで黙り続ける。その間を取って 20 秒。
DEAD_SEC = 20.0
# 速い開き直しはここまで。既定の入力が別の装置へ移ってしまった場合などは
# 何度開き直しても直らず、開き直すたびに録音を欠くだけになる。
DEAD_TRIES = 3
# 諦めたあとに、それでも試し続ける間隔。完全にやめると挿し直しても戻る道が
# 無くなる。ゼロが届き続ける限りブロックは途切れず、STALL_SEC の見張りは
# 一度も働かないので、こちらが手を止めたら誰も気づけない。
DEAD_SLOW_SEC = 300.0

# 無音とみなす RMS の既定値。マイクごとに違うので実測して決める値だが、
# 開発機の値をそのまま持ってくると別の環境で「全く反応しない」になる。
# Linux 向けの 0.054 は、macOS に USB のコンデンサマイクを挿した環境には
# 高すぎ、普通の声量では一度も超えなかった（そのときの環境ノイズは 0.003）。
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


# この module を直接叩いたときの既定。通常の経路（voice-shell.sh start）は
# voice_daemon.resolve_engine が「指定 > 前回の選択 > このブラウザ」で決めるので、
# ここには来ない。
# ここに browser は置けない。ブラウザ認識は画面の中で完結していて、
# この機械にモデルを積まない。デーモンにその分岐が無いのはそのため。
# macOS は OS 付属のオンデバイス認識が追加の用意なしで動くので apple、
# それ以外は Whisper にする。
_DEFAULT_ENGINE = "apple" if sys.platform == "darwin" else "whisper"


def add_common_args(p):
    """各スクリプトで共通の引数を登録する。"""
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
    """認識エンジンを用意する。

    apple は macOS 26 付属のオンデバイス認識で、モデルを積まない。
    whisper は faster-whisper をこの機械で動かす。
    どちらも音声はこの機械から出ない。
    """
    # 後片付けはどのエンジンでも要る。録音の ffmpeg / arecord はエンジンに
    # 関係なく子プロセスとして走るため、分岐に入る前に登録する。
    # （ここがエンジン別の分岐の中にあった頃、apple は登録を通らず、
    #   stop のたびに録音プロセスだけが孤児として残り続けていた）
    _kill_engine_on_exit()

    if args.engine == "apple":
        import engine_apple
        return engine_apple.load(args)

    if args.engine == "whisper":
        import whisper_engine
        return whisper_engine.load(args)

    # 知らない名前は、ここで黙って None を返さずに止める。
    # 返してしまうと、この先の init_streaming_state で
    # 「NoneType に属性が無い」という無関係な例外になって理由が伝わらない。
    sys.exit(f"「{args.engine}」はこの機械で動かせるエンジンではありません。\n"
             "  選べるのは apple と whisper です。\n"
             "  ブラウザ認識は voice-shell.sh start --engine browser から使えます。")


def _kill_engine_on_exit():
    """終了時に子プロセスを確実に落とす。

    Ctrl-C や kill で親が終わっても、子が残って資源を掴んだままになる。
    残るのは次の2つ。

    - 録音の ffmpeg / arecord がマイクを開けっぱなしにする（全エンジン共通）
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
        # （実測でも、システムの既定入力から録れている）。
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
        # dshow はデバイス名指定。一覧は次のコマンドで出せる。
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

    マイクを切っている間も録音は続ける（voice_daemon.py が認識結果を捨てる）。
    録音ごと止める形も試したが、入切のたびに録音プロセスを起こし直すことに
    なり、切り替えが一拍遅れる。通話アプリと同じく「録ってはいるが送らない」
    に留める。

    on_switch(device) は実際に切り替えが完了した時点で呼ばれる。ビューアが
    「本当に切り替わったか」を確定情報として表示できるようにするため
    （ブラウザ側の楽観的な表示だけだと、実際に切り替わったかは分からない）。
    """
    nbytes = int(in_sr * BLOCK_SEC) * 2  # 16bit モノラル

    # 録音プロセスは、生きたまま音だけ来なくなることがある。USB マイクを
    # 抜き差しすると実測で起きた（avfoundation は開いた時点のデバイスに
    # 繋ぎっぱなしなので、既定が入れ替わると無音すら届かなくなる）。
    # このとき proc.stdout.read() は EOF も来ないので永久に待つ。実測では
    # そのまま2時間半、画面は「届いています」のまま何も起きなかった。
    #
    # 読む側を別スレッドへ移し、決めた時間だけ待って来なければ立て直す。
    # 静かな部屋と取り違えることはない。黙っていてもブロック自体は届き、
    # 届かなくなるのは配線が切れたときだけなので。
    # ただし「届くのに中身がゼロ」という切れ方もある（DEAD_SEC の方で見る）。
    def start(dev):
        p = subprocess.Popen(mic_command(dev, in_sr), stdout=subprocess.PIPE)
        q = queue.Queue(maxsize=100)          # 10秒分。溢れればパイプ側で待つ
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
                                return        # もう止めた録音。抱えた分は捨てる
                    if not b:                 # 空バイト列 ＝ 相手が終了した
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
        # ストリーム用リサンプラを一度だけ構築する。ブロックごとに
        # soxr.resample() を呼ぶとフィルタの生成・破棄が毎回走り約4倍遅い。
        return soxr.ResampleStream(in_sr, SAMPLE_RATE, 1, dtype="float32").resample_chunk

    current = device
    proc, blocks = start(current)
    to_16k = make_resampler()
    if in_sr != SAMPLE_RATE:
        print(f"マイクを {in_sr}Hz で録音し {SAMPLE_RATE}Hz に変換します", file=sys.stderr)

    # 録音は止まる。ffmpeg が理由もなく落ちることもあれば（Windows で稀に、
    # パイプへの書き込みが "Invalid argument" で失敗する現象を実測）、
    # プロセスは生きたまま音だけ来なくなることもある（USB マイクを抜いた
    # とき。avfoundation は開いた時点のデバイスに繋ぎっぱなしなので、
    # 抜けても気づかず、EOF すら返さないまま黙る）。
    #
    # どちらでも同じことをする。開き直して、また待つ。**諦めない。**
    # 「5回試して駄目でした」と言われても、できることは結局「挿し直す」
    # だけで、それは黙って待っていれば済む話なので。挿し直せば次の試行で
    # 開けて、そのまま何事も無かったように続く。
    #
    # 静かな部屋と取り違えることはない。黙っていてもブロック自体は届き
    # 続ける（マイク本体のミュートも同じで、無音のブロックが来る）。
    #
    # ただし「ブロックが来るかどうか」だけでは足りない。挿し直したあとに
    # 「ブロックは届くが中身は全部ゼロ」という三つ目の状態を実測した。
    # ffmpeg は :default を開き直せているのに、値は 0.0000 のまま 10 分経っても
    # 戻らず、この見張りは素通りしていた（届いてはいるので永久に満たされる）。
    # そちらは下でゼロそのものを数えて、同じく切れているものとして扱う。
    # 開き直しても直らないことがある切れ方なので、そちらだけは手を止める。
    #
    # 待ち時間だけは伸ばす。挿さっていない間ずっと ffmpeg を起こし続けて
    # も意味がない。上限は 5 秒なので、挿し直せば遅くとも 5 秒で戻る。
    STALL_SEC = 4.0           # これだけ音が来なければ、繋がっていない
    RETRY_MIN, RETRY_MAX = 0.5, 5.0
    retry_wait = RETRY_MIN
    lost = False              # いま繋がっていないか（ログを一度だけ出すため）
    dead_run = 0.0            # 中身が全部ゼロのブロックが続いている秒数
    dead_tries = 0            # ゼロを理由に開き直した回数
    gave_up = False           # 速い開き直しを諦めたか（ログを一度だけ出すため）

    try:
        while True:
            # 切り替えを頼まれていたら録音だけやり直す
            if want_device is not None:
                asked = want_device()
                if asked and asked != current:
                    stop(proc)
                    current = asked
                    proc, blocks = start(current)
                    to_16k = make_resampler()   # 履歴を持たせない
                    # 別の装置になったのだから、前の装置のゼロの数え方は捨てる。
                    # 持ち越すと、諦めたあとに選び直した装置がまた無音だったとき、
                    # 速い試行を一度もしないまま長い間隔で待つことになる。
                    dead_run, dead_tries, gave_up = 0.0, 0, False
                    print(f"マイクを {current} に切り替えました", file=sys.stderr, flush=True)
                    if on_switch is not None:
                        on_switch(current)

            def reopen():
                """録音プロセスだけ立て直す。モデルは載せたままにする。"""
                nonlocal proc, blocks, to_16k, retry_wait
                stop(proc)
                time.sleep(retry_wait)
                retry_wait = min(retry_wait * 2, RETRY_MAX)
                proc, blocks = start(current)
                to_16k = make_resampler()

            def relight(why: str):
                """録音を開き直す。繋がるまで何度でも。"""
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

            # 中身が全部ゼロなら、届いていても繋がっていない。rms を出す前に
            # バイト列をそのまま見る。割り算より安いうえ、丸めの余地が無い。
            if raw.count(0) == len(raw):
                dead_run += len(raw) / 2 / in_sr   # 16bit モノラル
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
                        # 既定の入力が別の装置へ移っていることがある。いま何が
                        # 見えているかを一度だけ出しておけば、選び直す手がかりになる。
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
                # 音が入ってきた時点で全部やり直す。数え途中を持ち越すと、
                # 前に切れたときの分だけ次の判定が早まってしまう。
                dead_run, dead_tries, gave_up = 0.0, 0, False
                if lost:
                    lost = False
                    print(f"マイクが戻りました（{current}）", file=sys.stderr, flush=True)
                retry_wait = RETRY_MIN

            block = to_16k(np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0)
            # block.dot(block) は二乗の一時配列を作らない
            rms = float(np.sqrt(block.dot(block) / block.size)) if block.size else 0.0
            yield block, len(block) / SAMPLE_RATE, rms
    finally:
        stop(proc)


def stream_utterances(model, args, should_stop=lambda: False):
    """マイクを読み、認識イベントを yield する。

    yield されるイベント（辞書）は次の3つ。
        {"type": "level",   "rms": float, "speaking": bool}   毎ブロック
        {"type": "partial", "text": str, "language": str}     認識途中
        {"type": "final",   "text": str, "language": str}     発話確定

    無音が silence_duration 続いたら確定する。喋り続けている間は区切らない
    （HARD_UTTERANCE_CAP だけが歯止め）。ライブラリ側に発話区切り（VAD）は
    無いため、ここで RMS を見て判定している。
    """
    # apple も whisper も同じ 3 メソッドを持つので、この下は共通で通る。
    # load_model が知らない名前で止めるので、ここまで来るのはこの 2 つだけ。
    def new_state():
        return model.init_streaming_state(language=args.language)

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

        # 話し終わった（無音が続いた）なら確定する。喋っている最中は切らない。
        # 一息で伝えたいのに途中で送られる方が困るため。
        done_talking = silence_run >= args.silence_duration
        way_too_long = accum_sec >= HARD_UTTERANCE_CAP

        if done_talking or way_too_long:
            done = finish()
            if done:
                yield done
            state, silence_run, speech_seen, last_text = new_state(), 0.0, False, ""

    # 中断時に途中の発話を捨てない
    if speech_seen:
        done = finish()
        if done:
            yield done
