#!/usr/bin/env python3
"""LAN 内の端末から音声を受ける WebSocket サーバ。

OpenAI Realtime の transcription intent に合わせてある。engines.py の
`openai` クライアントは接続先を差し替えるだけでそのまま繋がる。

認識は make_session 引数に渡す。接続ごとに (feed, finish) を作らせる形で、
喋っている最中も feed が返したぶんを delta として流す。溜めてから一度に
認識すると、喋り終わるまで手元に何も返らず届いているか分からない。

デーモンに組み込むときはモデルを触る関数を渡し、単体で試すときは
省略すればオウム返しになる。

    python remote_server.py --port 8091        # スタブで起動
"""
import argparse
import base64
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional

import numpy as np

SAMPLE_RATE = 16000

_CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "voice-shell"
CONF_FILE = _CONFIG / "remote.json"

_STATE = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "voice-shell"
REMOTE_DIR = _STATE / "remote"

# 1接続あたりの音声の上限。悪意より事故（送りっぱなし）を想定した歯止め。
MAX_UTTERANCE_SEC = 120


def load_conf(path: Path = CONF_FILE) -> dict:
    """接続設定を読む。無ければ雛形を作って終わる。"""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "bind": "127.0.0.1",
            "port": 8091,
            "tokens": {},
        }, ensure_ascii=False, indent=2) + "\n")
        sys.exit(
            f"{path} を作りました。\n"
            "  tokens に「トークン: 名前」を足してから起動してください。\n"
            '  例:  "tokens": {"好きな文字列": "windows-pc"}\n'
            "  bind は LAN から使うなら自分の IP を書きます（0.0.0.0 は\n"
            "  VPN や別セグメントにも届くので既定にしていません）。"
        )
    conf = json.loads(path.read_text())
    if not conf.get("tokens"):
        sys.exit(f"{path} の tokens が空です。トークンを足してください。")
    return conf


def _token_from(ws) -> Optional[str]:
    """接続からトークンを取り出す。

    ブラウザの `new WebSocket(url)` はヘッダを付けられないので、
    ヘッダだけに頼ると繋げない。3つとも受ける。
    """
    # 1. Authorization: Bearer <token>   … CLI、engines.py
    auth = ws.request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()

    # 2. サブプロトコル                  … ブラウザ（OpenAI と同じ手）
    #    ["realtime", "openai-insecure-api-key.<token>"]
    for proto in ws.request.headers.get_all("Sec-WebSocket-Protocol"):
        for item in proto.split(","):
            item = item.strip()
            if item.startswith("openai-insecure-api-key."):
                return item[len("openai-insecure-api-key."):]

    # 3. クエリ ?token=<token>           … 上2つが使えないとき
    _, _, query = ws.request.path.partition("?")
    for pair in query.split("&"):
        k, _, v = pair.partition("=")
        if k == "token" and v:
            from urllib.parse import unquote
            return unquote(v)
    return None


def echo_session():
    """認識の代わり。受け取った長さを返して、配線が通っているか確かめる。

    デーモンから渡されるものと同じく (feed, finish) を返す。
    """
    got = [0]

    def feed(pcm):
        got[0] += len(pcm)
        return f"[{got[0] / SAMPLE_RATE:.1f}秒]"

    def finish():
        n = got[0]
        got[0] = 0
        return f"[{n / SAMPLE_RATE:.1f}秒 の音声を受け取りました]" if n else ""

    return feed, finish


class Session:
    """接続1本。話者ごとに音声を溜めて、commit で認識に回す。"""

    def __init__(self, name: str, make_session: Callable[[], tuple],
                 out_dir: Path):
        self.name = name
        # feed(pcm) -> 現時点のテキスト / finish() -> 確定テキスト
        self.feed, self.finish = make_session()
        self.buf: list = []
        self.said = ""            # ここまでに返した分（差分を出すため）
        self.out = out_dir / f"{name}.jsonl"
        self.out.parent.mkdir(parents=True, exist_ok=True)

    def append_pcm(self, raw: bytes) -> tuple:
        """16bit PCM を受けて認識を進める。

        戻り値は (伸びた分のテキスト, 音量)。喋っている最中に少しずつ
        返せるよう、届いたそばから認識に回す。溜めてから一度に投げると
        喋り終わるまで何も返せない。
        """
        pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        self.buf.append(pcm)
        rms = float(np.sqrt(pcm.dot(pcm) / pcm.size)) if pcm.size else 0.0

        text = self.feed(pcm)
        delta = ""
        if text and text != self.said:
            # 伸びた分だけ返す。認識は前を言い直すことがあるので、
            # 共通の頭を除いた残りを差分とする。
            delta = text[len(self.said):] if text.startswith(self.said) else text
            self.said = text
        return delta, rms

    def append(self, b64: str) -> tuple:
        """base64 に包まれた 16bit PCM を受ける。"""
        return self.append_pcm(base64.b64decode(b64))

    @property
    def seconds(self) -> float:
        return sum(len(b) for b in self.buf) / SAMPLE_RATE

    def commit(self) -> str:
        """発話の終わりを受けて確定させる。"""
        if not self.buf:
            return ""
        text = self.finish()
        self.buf.clear()
        self.said = ""
        return text

    def record(self, text: str) -> None:
        """認識結果を書き出す。ローカルの utterances.jsonl とは分ける。

        あちらは動作中の Claude Code セッションの入力そのものなので、
        別の端末の音声を混ぜると他人の発言がそのまま指示になる。
        """
        with open(self.out, "a") as f:
            f.write(json.dumps({"text": text}, ensure_ascii=False) + "\n")


def handle(ws, conf: dict, make_session: Callable[[], tuple],
           out_dir: Path) -> None:
    """接続1本を最後まで面倒みる。"""
    token = _token_from(ws)
    name = conf["tokens"].get(token or "")
    if not name:
        # どのトークンが弾かれたかは返さない
        ws.close(1008, "unauthorized")
        print("  認証されない接続を切りました", file=sys.stderr, flush=True)
        return

    sess = Session(name, make_session, out_dir)
    print(f"  {name} が接続しました", file=sys.stderr, flush=True)

    def send(obj: dict) -> None:
        ws.send(json.dumps(obj, ensure_ascii=False))

    last_level = [0.0]

    def emit(delta: str, rms: float) -> None:
        """認識が伸びた分と音量を返す。

        音量は喋るたびに変わるので、少しでも動いたときだけ送る。
        毎回送ると 1 秒に何十回も流れて帯域の無駄になる。
        """
        if delta:
            send({"type": "conversation.item.input_audio_transcription.delta",
                  "delta": delta})
        if abs(rms - last_level[0]) > 0.003:
            last_level[0] = rms
            send({"type": "input_audio_buffer.level", "rms": round(rms, 4)})

    try:
        for raw in ws:
            # 生の PCM がそのまま来ることがある（engines.py はこの形で送る）。
            # JSON に包むのはブラウザ向けの経路なので、両方受ける。
            if isinstance(raw, (bytes, bytearray)):
                if sess.seconds <= MAX_UTTERANCE_SEC:
                    delta, rms = sess.append_pcm(raw)
                    emit(delta, rms)
                continue

            try:
                msg = json.loads(raw)
            except (ValueError, TypeError):
                continue
            kind = msg.get("type", "")

            # 接続直後に来る。中身は使わないが、知らない type として
            # 弾くとクライアントが繋がらないので黙って受ける。
            if kind == "transcription_session.update":
                send({"type": "transcription_session.updated"})

            elif kind == "input_audio_buffer.append":
                if sess.seconds > MAX_UTTERANCE_SEC:
                    sess.buf.clear()
                    send({"type": "error",
                          "error": {"message": "音声が長すぎます"}})
                    continue
                delta, rms = sess.append(msg.get("audio", ""))
                emit(delta, rms)

            elif kind == "input_audio_buffer.commit":
                text = sess.commit()
                # 相槌でも空文字を返す。要求に対して黙るのは筋が悪い。
                send({"type": "conversation.item.input_audio_transcription."
                              "completed", "transcript": text})
                if text:
                    sess.record(text)
                    stamp = time.strftime("%H:%M:%S")
                    print(f"  [{stamp}] {name}: {text}",
                          file=sys.stderr, flush=True)

            elif kind == "input_audio_buffer.clear":
                sess.buf.clear()

    except Exception as e:                      # 切断は普通に起きる
        print(f"  {name} が切れました ({type(e).__name__})",
              file=sys.stderr, flush=True)
    else:
        print(f"  {name} が切れました", file=sys.stderr, flush=True)


def serve(conf: dict, make_session: Callable[[], tuple] = echo_session,
          out_dir: Path = REMOTE_DIR, ready: threading.Event = None):
    """サーバを立てて待ち受ける。デーモンからはスレッドで呼ぶ。"""
    from websockets.sync.server import serve as ws_serve

    host, port = conf.get("bind", "127.0.0.1"), conf.get("port", 8091)

    def select_subprotocol(ws, protos):
        # ブラウザがトークンをサブプロトコルに載せてくる。
        # OpenAI と同じく "realtime" を選んで返す。
        return "realtime" if "realtime" in protos else None

    with ws_serve(lambda ws: handle(ws, conf, make_session, out_dir),
                  host, port, select_subprotocol=select_subprotocol) as server:
        print(f"待ち受け: ws://{host}:{port}/v1/realtime", file=sys.stderr)
        print(f"  書き出し先: {out_dir}/<名前>.jsonl", file=sys.stderr)
        print(f"  登録済み: {', '.join(conf['tokens'].values())}",
              file=sys.stderr, flush=True)
        if ready:
            ready.set()
        server.serve_forever()


def main():
    p = argparse.ArgumentParser(description="音声を受ける WebSocket サーバ")
    p.add_argument("--conf", type=Path, default=CONF_FILE)
    p.add_argument("--out-dir", type=Path, default=REMOTE_DIR)
    p.add_argument("--port", type=int, help="設定より優先する")
    p.add_argument("--bind", help="設定より優先する")
    args = p.parse_args()

    conf = load_conf(args.conf)
    if args.port:
        conf["port"] = args.port
    if args.bind:
        conf["bind"] = args.bind

    print("認識はまだ繋いでいません（受け取った長さを返すだけ）",
          file=sys.stderr)
    try:
        serve(conf, out_dir=args.out_dir)
    except KeyboardInterrupt:
        print("\n終了します。", file=sys.stderr)


if __name__ == "__main__":
    main()
