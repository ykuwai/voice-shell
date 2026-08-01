"""クラウドの音声認識 API を使うためのエンジン。

GPU が無い PC でも voice-shell を動かせるようにするためのもの。
`--engine deepgram` のように指定すると、ローカルの Qwen3-ASR の代わりに
その API へ音声を送る。

asr_mic.stream_utterances() と同じイベントを yield するので、
デーモンから見た振る舞いは local と変わらない:

    {"type": "level",   "rms": float, "speaking": bool}   毎ブロック
    {"type": "partial", "text": str, "language": str}     認識途中
    {"type": "final",   "text": str, "language": str}     発話確定

## 設計の理由

- **発話の区切りは常に手元の RMS で決める。** API 側の区切りに任せると、
  マイクを切った境界をまたいだ確定が届き、デーモンに捨てられて指示が消える。
  API の区切りは参考程度に扱う。
- **`level` イベントは必ず 100ms ごとに出す。** デーモンはこれで
  「発話がいつ始まったか」を追っており、途切れるとミュート判定が壊れる。
- **黙っている間は音声を送らない。** 接続している時間で課金する API が
  あるため（AssemblyAI は明記、Deepgram も同様とされる）、無音を送り続けると
  料金が無駄になる。喋り始めたら接続し、確定したら閉じる。

## 未検証

**この module は実際の API につないで動かしていない。** 手元に API キーが
無いため、各社のドキュメントに沿って書いてある。最初に使うときは短い発話で
試して、料金と認識結果を確かめてほしい。
"""
import json
import os
import queue
import sys
import threading
import time

import numpy as np

import asr_mic
from asr_mic import SAMPLE_RATE

# 各エンジンの既定モデルと、キーを読む環境変数
ENGINES = {
    "home-lan": {
        # 家の LAN にいる GPU 機（voice_daemon.py --remote）に繋ぐ。
        # ノート PC のように GPU が非力な端末で、認識だけ任せるための口。
        # 自前のサーバなので従量課金が無い。
        "env": "VOICE_SHELL_TOKEN",
        "model": "qwen3-asr",
        "note": "家の LAN にある GPU 機に認識だけ任せる（課金なし）",
        # 接続先は環境ごとに違うので既定値を置かない。
        # VOICE_SHELL_SERVER か --server で渡す。
        "url": None,
    },
    "deepgram": {
        "env": "DEEPGRAM_API_KEY",
        "model": "nova-3",
        "note": "音声認識専業。速い。日本語と英語の混在に対応（multi）",
    },
    "soniox": {
        "env": "SONIOX_API_KEY",
        "model": "stt-rt-v5",
        "note": "$0.12/時と安い。16kHz をそのまま受け取れる",
    },
    "assemblyai": {
        "env": "ASSEMBLYAI_API_KEY",
        "model": "universal-3-5-pro",
        "note": "日本語では使えない（英・西・独・仏・葡・伊のみ）。接続時間で課金",
        # リアルタイム認識が対応するのは上記6言語だけで、日本語は録音済みの
        # 音声にしか対応していない。日本語で選ぶと空の結果が返り続ける。
        "languages": {"en", "es", "de", "fr", "pt", "it"},
    },
    "openai": {
        "env": "OPENAI_API_KEY",
        "model": "gpt-4o-transcribe",
        "note": "課金は音声の長さのみ。24kHz を要求するので変換して送る",
    },
}


def _key(name: str) -> str:
    env = ENGINES[name]["env"]
    key = os.environ.get(env)
    if not key:
        sys.exit(
            f"{env} が設定されていません。\n"
            f"  export {env}=...\n"
            f"  を設定してから起動してください。"
        )
    return key


def load(args):
    """接続に必要な情報をまとめて返す（実際の接続は発話ごとに行う）。"""
    name = args.engine
    if name not in ENGINES:
        sys.exit(f"--engine は {' / '.join(['local'] + list(ENGINES))} のいずれかです")

    try:
        import websockets  # noqa: F401
    except ImportError:
        sys.exit("websockets が必要です:  pip install websockets")

    spec = ENGINES[name]
    lang = (args.language or "ja").lower()[:2]

    # 対応していない言語で始めると、つながるのに何も返ってこない。
    # 原因が分かりにくいので、起動の時点で止める。
    ok = spec.get("languages")
    if ok and lang not in ok:
        sys.exit(f"{name} は {args.language} に対応していません"
                 f"（対応: {' / '.join(sorted(ok))}）。"
                 f"\n  他のエンジンを使ってください。")

    url = getattr(args, "server", None) or spec.get("url")
    if name == "home-lan" and not url:
        sys.exit(
            "接続先が分かりません。GPU 機のアドレスを教えてください。\n"
            "  export VOICE_SHELL_SERVER=ws://192.168.0.10:8091/v1/realtime\n"
            "  （--server でも渡せます）\n"
            "\n"
            "  GPU 機側で `voice-shell.sh remote` を動かし、そこで出る\n"
            "  「待ち受け: ws://...」のアドレスをそのまま指定します。"
        )

    conf = {
        "name": name,
        "key": _key(name),
        "model": args.model or spec["model"],
        "language": lang,
        "url": url,
    }
    print(f"認識エンジン: {name}（{spec['note']}）", file=sys.stderr)
    if name == "home-lan":
        # 自分のサーバなので、外に出ていく話とは分けて書く
        print(f"  音声は {conf['url']} に送られます。", file=sys.stderr, flush=True)
    else:
        print("  音声はこの API に送られます。ローカルでは処理しません。",
              file=sys.stderr, flush=True)
    return conf


# ── 各社への接続 ─────────────────────────────
#
# どれも「16kHz の生 PCM を送ると、途中経過と確定テキストが返る」形に揃える。
# 返すのは (送る関数, 受け取るジェネレータ, 閉じる関数) の3つ。

def _connect(conf):
    """発話1つ分の接続を開く。戻り値: (send, results, close)

    send(bytes)  … 音声を送る
    results()    … (text, is_final) を yield する
    close()      … 閉じる
    """
    from websockets.sync.client import connect as ws_connect

    name = conf["name"]
    lang = conf["language"]
    out = queue.Queue()

    if name == "deepgram":
        url = ("wss://api.deepgram.com/v1/listen"
               f"?model={conf['model']}&language={lang}"
               "&encoding=linear16&sample_rate=16000&channels=1"
               "&interim_results=true&punctuate=true")
        ws = ws_connect(url, additional_headers={"Authorization": f"Token {conf['key']}"})

        def parse(msg):
            d = json.loads(msg)
            alt = d.get("channel", {}).get("alternatives", [{}])[0]
            return alt.get("transcript", ""), bool(d.get("is_final"))

        finish = lambda: ws.send(json.dumps({"type": "CloseStream"}))  # noqa: E731

    elif name == "soniox":
        ws = ws_connect("wss://stt-rt.soniox.com/transcribe-websocket")
        ws.send(json.dumps({
            "api_key": conf["key"],
            "model": conf["model"],
            "audio_format": "pcm_s16le",
            "sample_rate": SAMPLE_RATE,
            "num_channels": 1,
            "language_hints": [lang],
        }))

        def parse(msg):
            d = json.loads(msg)
            toks = d.get("tokens", [])
            text = "".join(t.get("text", "") for t in toks)
            final = any(t.get("is_final") for t in toks) or bool(d.get("finished"))
            return text, final

        finish = lambda: ws.send(json.dumps({"type": "finalize"}))  # noqa: E731

    elif name == "assemblyai":
        url = ("wss://streaming.assemblyai.com/v3/ws"
               f"?sample_rate={SAMPLE_RATE}&encoding=pcm_s16le"
               f"&speech_model={conf['model']}&format_turns=true")
        ws = ws_connect(url, additional_headers={"Authorization": conf["key"]})

        def parse(msg):
            d = json.loads(msg)
            if d.get("type") != "Turn":
                return "", False
            return d.get("transcript", ""), bool(d.get("end_of_turn"))

        finish = lambda: ws.send(json.dumps({"type": "Terminate"}))  # noqa: E731

    elif name == "home-lan":
        # 家の LAN の GPU 機（voice_daemon.py --remote）。OpenAI Realtime に
        # 合わせてあるので、下の openai とほぼ同じやりとりで済む。
        ws = ws_connect(conf["url"],
                        additional_headers={"Authorization": f"Bearer {conf['key']}"})
        ws.send(json.dumps({
            "type": "transcription_session.update",
            "session": {
                "input_audio_format": "pcm16",
                "input_audio_transcription": {"model": conf["model"],
                                              "language": lang},
                "turn_detection": None,
            },
        }))

        def parse(msg):
            d = json.loads(msg)
            t = d.get("type", "")
            if t.endswith("transcription.completed"):
                return d.get("transcript", ""), True
            return "", False

        finish = lambda: ws.send(json.dumps({"type": "input_audio_buffer.commit"}))  # noqa: E731

    elif name == "openai":
        ws = ws_connect(
            "wss://api.openai.com/v1/realtime?intent=transcription",
            additional_headers={"Authorization": f"Bearer {conf['key']}",
                                "OpenAI-Beta": "realtime=v1"})
        ws.send(json.dumps({
            "type": "transcription_session.update",
            "session": {
                "input_audio_format": "pcm16",
                "input_audio_transcription": {"model": conf["model"],
                                              "language": lang},
                # 区切りは手元の RMS で決めるので、API 側の判定は使わない
                "turn_detection": None,
            },
        }))

        def parse(msg):
            d = json.loads(msg)
            t = d.get("type", "")
            if t.endswith("transcription.delta"):
                return d.get("delta", ""), False
            if t.endswith("transcription.completed"):
                return d.get("transcript", ""), True
            return "", False

        finish = lambda: ws.send(json.dumps({"type": "input_audio_buffer.commit"}))  # noqa: E731

    else:
        raise ValueError(name)

    stop = threading.Event()

    def pump():
        try:
            for msg in ws:
                if stop.is_set():
                    break
                try:
                    text, final = parse(msg)
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
                if text or final:
                    out.put((text, final))
        except Exception:
            pass
        finally:
            out.put(None)

    threading.Thread(target=pump, daemon=True).start()

    def send(pcm_bytes):
        ws.send(pcm_bytes)

    def results():
        while True:
            item = out.get()
            if item is None:
                return
            yield item

    def close():
        stop.set()
        try:
            finish()
        except Exception:
            pass
        try:
            ws.close()
        except Exception:
            pass

    return send, results, close


def stream(conf, args, should_stop=lambda: False):
    """マイクを読み、認識イベントを yield する（クラウド版）。

    黙っている間は接続しない。喋り始めたら開き、無音が続いたら閉じる。
    接続している時間で課金する API があるため。
    """
    # OpenAI だけ 24kHz を要求するので、送る直前に上げる
    up = None
    if conf["name"] == "openai":
        import soxr
        up = soxr.ResampleStream(SAMPLE_RATE, 24000, 1, dtype="float32")

    send = results = close = None
    reader = None            # 受信を回すスレッド
    silence_run = 0.0
    speaking_since = 0.0
    last_text = ""
    latest = {"text": "", "final": False}
    lock = threading.Lock()

    def drain():
        for text, final in results():
            with lock:
                if final:
                    latest["text"] = text or latest["text"]
                    latest["final"] = True
                elif text:
                    latest["text"] = text

    def open_stream():
        nonlocal send, results, close, reader
        send, results, close = _connect(conf)
        with lock:
            latest["text"] = ""
            latest["final"] = False
        reader = threading.Thread(target=drain, daemon=True)
        reader.start()

    def close_stream():
        nonlocal send, results, close
        if close:
            close()
        send = results = close = None

    def finish():
        """確定させて、テキストを取り出す。"""
        if not close:
            return None
        close_stream()
        # 受信スレッドが最後の確定を書き込むのを少し待つ
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            with lock:
                if latest["final"]:
                    break
            time.sleep(0.05)
        with lock:
            text = latest["text"].strip()
        return ({"type": "final", "text": text, "language": args.language or "Japanese"}
                if text else None)

    try:
        for block, dur, rms in asr_mic.read_blocks(
                args.device, args.input_samplerate,
                want_device=getattr(args, "want_device", None)):
            if should_stop():
                break

            speaking = rms >= args.silence_threshold
            yield {"type": "level", "rms": rms, "speaking": speaking}

            if speaking:
                if send is None:
                    open_stream()
                silence_run = 0.0
                speaking_since += dur
            else:
                silence_run += dur

            if send is None:
                continue          # まだ喋っていない

            # 音声を送る（無音でも、発話中なら途切れさせない）
            pcm = up.resample_chunk(block) if up is not None else block
            try:
                send((np.clip(pcm, -1, 1) * 32767).astype(np.int16).tobytes())
            except Exception as e:
                print(f"送信に失敗しました: {e}", file=sys.stderr, flush=True)
                close_stream()
                continue

            with lock:
                text = latest["text"]
            if text and text != last_text:
                last_text = text
                yield {"type": "partial", "text": text,
                       "language": args.language or "Japanese"}

            over = speaking_since >= args.max_utterance_sec
            if silence_run >= args.silence_duration or (over and silence_run >= args.pause_sec):
                done = finish()
                if done:
                    yield done
                silence_run = speaking_since = 0.0
                last_text = ""
    finally:
        if close:
            done = finish()
            if done:
                yield done
