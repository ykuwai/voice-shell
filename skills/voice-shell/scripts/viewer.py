#!/usr/bin/env python3
"""音声プロンプトのライブビューア。

voice_daemon.py が書き出す JSONL を追尾してブラウザに流すだけ。
GPU も マイクも使わないので、音声モードと同時に動かせる。

    python viewer.py            # → http://127.0.0.1:8090
"""
import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from aiohttp import web, WSCloseCode

DEFAULT_LOG = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "qwen-voice" / "utterances.jsonl"

# ユーザー辞書。voice_daemon.py と同じ場所を読み書きする。
_CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "voice-shell"
DICT_FILE = _CONFIG / "dictionary.json"                  # 共有（リポジトリに反映できる）
PRIVATE_DICT_FILE = _CONFIG / "dictionary.private.json"  # 手元だけ


def _builtin_noise() -> list:
    """voice_daemon.py が最初から無視している語を読む（表示用）。

    デーモンを起動していなくても見せたいので、import せずソースから拾う。
    """
    try:
        import ast
        src = (Path(__file__).with_name("voice_daemon.py")).read_text()
        tree = ast.parse(src)
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                    getattr(t, "id", None) == "NOISE_ONLY" for t in node.targets):
                return sorted(ast.literal_eval(node.value), key=lambda s: (len(s), s))
    except Exception:
        pass
    return []


def _read_dict(raw: bool = False, path: Path = None) -> dict:
    """辞書を読む。無い・壊れている場合は空で返す。

    raw=True なら内部用のキー（_seen）も含めてそのまま返す。
    """
    try:
        data = json.loads((path or DICT_FILE).read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"ignore": [], "replace": {}}
    if raw:
        return data
    return {"ignore": data.get("ignore", []) or [],
            "replace": data.get("replace", {}) or {}}


def parse_args():
    p = argparse.ArgumentParser(description="音声プロンプトのライブビューア")
    p.add_argument("--log-file", default=str(DEFAULT_LOG), help="追尾する JSONL")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8090)
    return p.parse_args()


class Tail:
    """JSONL を追尾し、新しい行を購読者に配る。"""

    def __init__(self, path: Path):
        self.path = path
        self.clients: set[web.WebSocketResponse] = set()
        self.history: list[dict] = []

    def read_existing(self):
        """起動時点までの内容を読む（後から開いても経緯が見える）。"""
        if not self.path.exists():
            return
        with open(self.path) as f:
            for line in f:
                rec = self._parse(line)
                if rec:
                    self.history.append(rec)

    @staticmethod
    def _parse(line: str):
        line = line.strip()
        if not line:
            return None
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return None

    async def watch(self):
        """ファイル末尾を追い続ける。まだ無ければ現れるまで待つ。"""
        while not self.path.exists():
            await asyncio.sleep(1)

        with open(self.path) as f:
            f.seek(0, os.SEEK_END)
            while True:
                line = f.readline()
                if not line:
                    # デーモン再起動でファイルが作り直された場合に追従する
                    try:
                        if self.path.stat().st_size < f.tell():
                            f.seek(0)
                    except FileNotFoundError:
                        pass
                    await asyncio.sleep(0.25)
                    continue

                rec = self._parse(line)
                if rec:
                    self.history.append(rec)
                    await self.broadcast(rec)

    async def broadcast(self, rec: dict):
        payload = json.dumps(rec, ensure_ascii=False)
        for ws in list(self.clients):
            try:
                await ws.send_str(payload)
            except Exception:
                self.clients.discard(ws)

    async def watch_partial(self):
        """認識途中のテキストを流す（デーモンが上書きし続けるファイルを読む）。"""
        path = self.path.parent / "partial.txt"
        last = None
        while True:
            try:
                text = path.read_text()
            except (FileNotFoundError, OSError):
                text = ""
            if text != last:
                last = text
                await self.broadcast({"partial": text})
            await asyncio.sleep(0.2)

    async def watch_held(self):
        """一時停止中に確定した発話を、増えた分だけ流す。

        ブラウザ側はこれを受けてテキストエリアの末尾に足す。全文を送ると
        編集中の内容を壊してしまうため、差分だけを送る。
        """
        path = self.path.parent / "held.jsonl"
        seen = 0
        while True:
            try:
                lines = [l for l in path.read_text().splitlines() if l.strip()]
            except (FileNotFoundError, OSError):
                lines = []

            if len(lines) < seen:        # 送信・破棄でリセットされた
                seen = 0
            for line in lines[seen:]:
                rec = self._parse(line)
                if rec:
                    await self.broadcast({"held": rec.get("text", "")})
            seen = len(lines)
            await asyncio.sleep(0.25)


async def main_async(args):
    page = Path(__file__).with_name("viewer.html")
    if not page.exists():
        sys.exit(f"{page} が見つかりません")

    tail = Tail(Path(args.log_file))
    tail.read_existing()

    async def handle_index(_req):
        # 開発中に手を入れるので、ブラウザにキャッシュさせない
        # （古い画面のままボタンが効かない事故を防ぐ）
        return web.FileResponse(page, headers={
            "Cache-Control": "no-store, must-revalidate",
        })

    async def handle_ws(request):
        ws = web.WebSocketResponse(heartbeat=30)
        await ws.prepare(request)
        # 接続時にこれまでの分をまとめて送る
        for rec in tail.history:
            await ws.send_str(json.dumps(rec, ensure_ascii=False))
        tail.clients.add(ws)
        try:
            async for _ in ws:
                pass
        finally:
            tail.clients.discard(ws)
        return ws

    state = Path(args.log_file).parent
    pause_file = state / "paused"
    hold_file = state / "held.jsonl"
    mute_file = state / "muted"

    pid_file = state / "daemon.pid"

    def engine_running() -> bool:
        """認識の準備ができているか（PID は読み込み完了後に書かれる）。"""
        try:
            os.kill(int(pid_file.read_text()), 0)
            return True
        except (OSError, ValueError):
            return False

    stopping = {"until": 0.0}   # 停止を指示した直後は「起動中」と誤判定しない

    def engine_loading() -> bool:
        """起動したがまだ準備中か。

        PID が出る前でも、デーモンのプロセス自体は動いている。
        これを見ないと、押した直後に「止まっている」と表示されてしまう。
        逆に停止直後はプロセスが消えきる前に拾えてしまうので、
        止めた直後の数秒は起動中とみなさない。
        """
        if engine_running() or time.monotonic() < stopping["until"]:
            return False
        r = subprocess.run(["pgrep", "-f", "voice_daemon.py --language"],
                           capture_output=True)
        return bool(r.stdout.strip())

    async def handle_state(_req):
        """マイクの入切、保留の有無、保留中の発話を返す。"""
        held = []
        if hold_file.exists():
            for line in hold_file.read_text().splitlines():
                rec = Tail._parse(line)
                if rec:
                    held.append(rec)
        return web.json_response({"muted": mute_file.exists(),
                                  "paused": pause_file.exists(),
                                  "engine": engine_running(),
                                  "loading": engine_loading(), "held": held})

    async def handle_engine(req):
        """認識を止める / 動かす。

        止めると GPU（約12GB）が解放される。ビューアは動いたままなので、
        ここから動かし直せる（モデル読み込みに1〜2分）。
        """
        body = await req.json()
        want = bool(body.get("running"))
        sh = str(Path(__file__).with_name("voice-shell.sh"))

        # start_new_session でビューアから切り離す。
        # デーモンは終了時に自分の子を全部 kill するので、ビューアの系統に
        # ぶら下げると停止のときビューアまで巻き込まれる。
        if want and not engine_running():
            subprocess.Popen(["bash", sh, "engine-start"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
        elif not want and engine_running():
            # プロセスが消えきるまで数秒あるので、その間は起動中と見なさない
            stopping["until"] = time.monotonic() + 8
            subprocess.run(["bash", sh, "engine-stop"],
                           capture_output=True, timeout=30,
                           start_new_session=True)

        return web.json_response({"engine": engine_running()})

    async def handle_mute(req):
        """マイクを切る / 入れる。切っている間の発話はどこにも残らない。"""
        body = await req.json()
        if body.get("muted"):
            mute_file.touch()
        else:
            mute_file.unlink(missing_ok=True)
        return web.json_response({"muted": mute_file.exists()})

    async def handle_pause(req):
        """発話を保留する / 直接送るのに戻す。"""
        body = await req.json()
        if body.get("paused"):
            pause_file.touch()
        else:
            pause_file.unlink(missing_ok=True)
        return web.json_response({"paused": pause_file.exists()})

    async def handle_send(req):
        """手直ししたテキストをログに書いて Claude に送る。"""
        body = await req.json()
        text = (body.get("text") or "").strip()
        if not text:
            return web.json_response({"error": "empty"}, status=400)

        # Claude に渡る行は本文だけ。手直し済みの印だけ添える。
        with open(args.log_file, "a") as f:
            f.write(json.dumps({"text": text, "edited": True},
                               ensure_ascii=False) + "\n")
        rec = {"time": time.strftime("%H:%M:%S"), "text": text, "edited": True}
        hold_file.write_text("")     # 送ったので保留は空にする
        return web.json_response(rec)

    async def handle_discard(_req):
        """保留中の発話を捨てる。"""
        hold_file.write_text("")
        return web.json_response({"ok": True})

    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/ws", handle_ws)
    app.router.add_get("/api/state", handle_state)
    async def handle_dict_get(req):
        """辞書と、組み込みで無視している語を返す。

        ?scope=private で手元だけの辞書を返す。
        """
        private = req.query.get("scope") == "private"
        d = _read_dict(path=PRIVATE_DICT_FILE if private else DICT_FILE)
        d["builtin"] = [] if private else _builtin_noise()
        return web.json_response(d)

    async def handle_dict_put(req):
        """辞書を保存する。デーモンは毎発話読み直すので即反映される。

        ?scope=private で手元だけの辞書に書く。
        """
        private = req.query.get("scope") == "private"
        target = PRIVATE_DICT_FILE if private else DICT_FILE

        body = await req.json()
        data = {
            "ignore": sorted({s.strip() for s in body.get("ignore", [])
                              if isinstance(s, str) and s.strip()}),
            "replace": {k.strip(): v.strip() for k, v in body.get("replace", {}).items()
                        if isinstance(k, str) and isinstance(v, str) and k.strip()},
        }
        if not private:
            # 既定項目の追加履歴は内部用。消すと消した項目が復活してしまうので残す。
            prev = _read_dict(raw=True, path=target)
            seen = set(prev.get("_seen", [])) | set(prev.get("replace", {}))
            data["_seen"] = sorted(seen | set(data["replace"]))

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        return web.json_response({k: v for k, v in data.items() if k != "_seen"})

    mic_file = state / "mic"

    async def handle_mics(_req):
        """使えるマイクの一覧と、いま選ばれているものを返す。"""
        sys.path.insert(0, str(Path(__file__).parent))
        import asr_mic
        try:
            current = mic_file.read_text().strip()
        except OSError:
            current = ""
        return web.json_response({"current": current, "mics": asr_mic.list_mics()})

    async def handle_mic_put(req):
        """使うマイクを変える。デーモンが録音プロセスだけ入れ替える。"""
        body = await req.json()
        dev = (body.get("device") or "").strip()
        if not dev:
            return web.json_response({"error": "empty"}, status=400)
        mic_file.write_text(dev)
        return web.json_response({"current": dev})

    app.router.add_post("/api/engine", handle_engine)
    app.router.add_get("/api/mics", handle_mics)
    app.router.add_put("/api/mics", handle_mic_put)
    app.router.add_get("/api/dictionary", handle_dict_get)
    app.router.add_put("/api/dictionary", handle_dict_put)
    app.router.add_post("/api/mute", handle_mute)
    app.router.add_post("/api/pause", handle_pause)
    app.router.add_post("/api/send", handle_send)
    app.router.add_post("/api/discard", handle_discard)

    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, args.host, args.port).start()

    print(f"\n  ブラウザで開いてください →  http://{args.host}:{args.port}"
          f"\n  追尾中: {args.log_file}\n", file=sys.stderr, flush=True)

    tasks = [asyncio.create_task(tail.watch()),
             asyncio.create_task(tail.watch_partial()),
             asyncio.create_task(tail.watch_held())]
    try:
        await asyncio.Event().wait()
    finally:
        for t in tasks:
            t.cancel()
        for ws in list(tail.clients):
            await ws.close(code=WSCloseCode.GOING_AWAY, message=b"shutdown")
        await runner.cleanup()


def main():
    try:
        asyncio.run(main_async(parse_args()))
    except KeyboardInterrupt:
        print("\n終了します。", file=sys.stderr)


if __name__ == "__main__":
    main()
