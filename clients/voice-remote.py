#!/usr/bin/env python3
"""Windows などから母艦の GPU に音声を送る。

ブラウザ版（voice-remote.html）は HTTPS でないとマイクを使えないことが
あるので、確実に動くほうも用意した。

    pip install websockets sounddevice numpy
    python voice-remote.py --token <トークン>

喋り終わりは手元の音量で判断する。Ctrl-C で終了。
"""
import argparse
import base64
import os
import json
import queue
import sys
import threading
import time

try:
    import numpy as np
    import sounddevice as sd
    from websockets.sync.client import connect
except ImportError as e:
    sys.exit(f"{e.name} が要ります:  pip install websockets sounddevice numpy")

SR = 16000
BLOCK = 4096


def main():
    p = argparse.ArgumentParser(description="音声を母艦に送る")
    p.add_argument("--url", default=os.environ.get("VOICE_SHELL_SERVER"),
                   help="GPU 機の接続先。VOICE_SHELL_SERVER でも指定できる")
    # --list-devices だけ使いたいことがあるので必須にはしない
    p.add_argument("--token", help="remote.json のトークン")
    p.add_argument("--threshold", type=float, default=0.012,
                   help="これ未満を無音とみなす")
    p.add_argument("--tail", type=float, default=0.8,
                   help="無音がこれだけ続いたら区切る（秒）")
    p.add_argument("--list-devices", action="store_true")
    p.add_argument("--device", type=int, help="入力デバイスの番号")
    args = p.parse_args()

    if args.list_devices:
        print(sd.query_devices())
        return
    if not args.url:
        sys.exit("接続先が要ります:\n"
                 "  --url ws://<GPU機のIP>:8091/v1/realtime\n"
                 "  （VOICE_SHELL_SERVER でも指定できます）")
    if not args.token:
        sys.exit("--token が要ります（GPU 機の remote.json のトークン）")

    audio = queue.Queue()

    def on_audio(indata, frames, t, status):
        audio.put(indata[:, 0].copy())

    print(f"接続中… {args.url}")
    with connect(args.url,
                 additional_headers={"Authorization": f"Bearer {args.token}"}) as ws:
        ws.send(json.dumps({
            "type": "transcription_session.update",
            "session": {
                "input_audio_format": "pcm16",
                "input_audio_transcription": {"model": "qwen3-asr",
                                              "language": "ja"},
                "turn_detection": None,
            },
        }))
        ws.recv(timeout=10)
        print("繋がりました。喋ってください（Ctrl-C で終了）\n")

        stop = threading.Event()

        def listen():
            """返ってきた認識結果を出す。"""
            while not stop.is_set():
                try:
                    m = json.loads(ws.recv(timeout=1))
                except TimeoutError:
                    continue
                except Exception:
                    break
                if m.get("type", "").endswith("transcription.completed"):
                    text = m.get("transcript", "")
                    if text:
                        print(f"[{time.strftime('%H:%M:%S')}] {text}", flush=True)
                elif m.get("type") == "error":
                    print(f"  エラー: {m.get('error', {}).get('message')}",
                          file=sys.stderr)

        t = threading.Thread(target=listen, daemon=True)
        t.start()

        silent, spoke = 0.0, False
        try:
            with sd.InputStream(samplerate=SR, channels=1, dtype="float32",
                                blocksize=BLOCK, device=args.device,
                                callback=on_audio):
                while True:
                    block = audio.get()
                    pcm = (np.clip(block, -1, 1) * 32767).astype(np.int16)
                    ws.send(json.dumps({
                        "type": "input_audio_buffer.append",
                        "audio": base64.b64encode(pcm.tobytes()).decode(),
                    }))

                    rms = float(np.sqrt(block.dot(block) / block.size))
                    dur = len(block) / SR
                    if rms >= args.threshold:
                        spoke, silent = True, 0.0
                    elif spoke:
                        silent += dur
                        if silent >= args.tail:
                            ws.send(json.dumps(
                                {"type": "input_audio_buffer.commit"}))
                            spoke, silent = False, 0.0
        except KeyboardInterrupt:
            print("\n終了します。")
        finally:
            stop.set()


if __name__ == "__main__":
    main()
