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

# voice_daemon.py と同じ理由（Windows での "/tmp" の食い違い）で、
# voice-shell.sh から渡された実パスがあればそちらを優先する。
if os.environ.get("VOICE_SHELL_STATE_DIR"):
    DEFAULT_LOG = Path(os.environ["VOICE_SHELL_STATE_DIR"]) / "utterances.jsonl"
else:
    DEFAULT_LOG = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "qwen-voice" / "utterances.jsonl"

# ユーザー辞書。voice_daemon.py と同じ場所を読み書きする。
_CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "voice-shell"
DICT_FILE = _CONFIG / "dictionary.json"                  # 共有（リポジトリに反映できる）
PRIVATE_DICT_FILE = _CONFIG / "dictionary.private.json"  # 手元だけ
# マイク感度と確定までの無音秒数。デーモンが 0.5 秒おきに読み直すので、
# 書き換えるだけで再起動なしに効く。
TUNING_FILE = _CONFIG / "tuning.json"
# 触っていい範囲。外れた値を書くと認識が完全に止まったように見えるので、
# サーバ側でも必ず挟む（環境ノイズは 0.003 前後、macOS の既定は 0.015）。
TUNING_RANGE = {"silence_threshold": (0.003, 0.15),
                "silence_duration": (0.5, 3.0),
                "min_chars": (1, 40),
                # ひと続きの上限。0 は「区切らない」（asr_mic 側の絶対上限まで）
                "max_utterance_sec": (0, 180)}
# 数ではなく入切で持つもの
TUNING_FLAGS = {"strip_fillers"}
# 整数で持つもの。小数のまま渡すと文字数の比較が分かりにくくなる。
TUNING_INT = {"min_chars", "max_utterance_sec"}


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
                if rec and "system_warning" not in rec:
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
                # system_warning は Claude Code（Monitor でこのログを直接見ている側）
                # 宛てで、ブラウザの発話一覧に混ぜると壊れて見えるので流さない。
                if rec and "system_warning" not in rec:
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

    async def watch_level(self):
        """いま拾えている音量を流す。

        文字が出ないとき、マイクが死んでいるのか黙っているだけなのかを
        見分けたい。デーモンが書く level.txt は「音量 喋っているか」の
        2 つの数値だけで、音声そのものは残らない。
        """
        path = self.path.parent / "level.txt"
        last = None
        while True:
            try:
                rms, speaking = path.read_text().split()
                cur = (round(float(rms), 3), speaking == "1")
            except (FileNotFoundError, OSError, ValueError):
                cur = (0.0, False)
            if cur != last:
                last = cur
                await self.broadcast({"level": cur[0], "speaking": cur[1]})
            await asyncio.sleep(0.1)      # バーが滑らかに見える程度

    async def watch_mic_active(self):
        """デーモン側で実際に切り替えが完了したマイクを流す。

        ブラウザの「切り替えました」表示は押した瞬間の楽観的なものなので、
        本当に切り替わったかはこれで確定させる。起動直後の1回目も送るが、
        ブラウザ側は「切り替え要求後に来た1回」だけをトースト表示に使う。
        """
        path = self.path.parent / "mic_active"
        last = None
        while True:
            try:
                cur = path.read_text().strip()
            except (FileNotFoundError, OSError):
                cur = None
            if cur and cur != last:
                last = cur
                await self.broadcast({"mic_active": cur})
            await asyncio.sleep(0.3)

    async def watch_muted(self):
        """マイクの入切を流す。

        声で切り替えられる（デーモンが「ミュート」を聞いてファイルを作る）ので、
        画面が押していない変化が起きる。3秒おきの /api/state を待たせると、
        切れたのかどうか分からないまま喋り続けることになる。
        """
        path = self.path.parent / "muted"
        last = None
        while True:
            cur = path.exists()
            if cur != last:
                # 最初の1回は「変化」ではないので、状態だけ揃えて音は出させない。
                await self.broadcast({"muted": cur, "first": last is None})
                last = cur
            await asyncio.sleep(0.2)

    async def watch_voice_cmd(self):
        """声の合図に何が起きたかを流す。

        合図は発話として送らないので、通ったかどうかが画面に出ない。
        デーモンが書く voice_cmd.json をそのまま渡し、音と一言はブラウザに任せる。
        """
        path = self.path.parent / "voice_cmd.json"
        last = None
        while True:
            try:
                cur = json.loads(path.read_text())
            except (OSError, ValueError):
                cur = None
            at = cur.get("at") if isinstance(cur, dict) else None
            if at is not None and at != last:
                # 開いた時点で残っているものは、いま起きたことではない。
                await self.broadcast({"voice_cmd": cur, "first": last is None})
                last = at
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
        # 先にブロードキャスト対象へ登録してから履歴を送る。逆順だと、
        # ちょうど ws.prepare() / 履歴送信で await している隙に新しい行が
        # 届いた場合、「まだ history に無いので今回のスナップショットには
        # 含まれず、まだ clients にも入っていないのでブロードキャストも
        # 受け取れない」という二重の抜け穴ができ、その1件だけが永久に
        # 届かなくなる（実測: ブラウザ認識の最初の発話だけ抜けることがあった）。
        tail.clients.add(ws)
        for rec in list(tail.history):
            await ws.send_str(json.dumps(rec, ensure_ascii=False))
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

    def _pid_alive(pid) -> bool:
        """シグナルを送らずに生存確認する（voice_daemon.py と同じ理由）。
        os.kill(pid, 0) は Windows では未対応で SystemError になる。"""
        if sys.platform.startswith("win"):
            import ctypes
            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False

    def engine_running() -> bool:
        """認識の準備ができているか（PID は読み込み完了後に書かれる）。"""
        try:
            return _pid_alive(int(pid_file.read_text()))
        except (OSError, ValueError):
            return False

    stopping = {"until": 0.0}   # 停止を指示した直後は「起動中」と誤判定しない
    starting = {"until": 0.0}   # 開始を指示した直後はプロセスがまだ見えない

    def engine_loading() -> bool:
        """起動したがまだ準備中か。

        PID が出る前でも、デーモンのプロセス自体は動いている。
        これを見ないと、押した直後に「止まっている」と表示されてしまう。

        ただし起動は切り離して行うので、指示してから pgrep に映るまで
        0.1〜0.3秒ある。ブラウザはその窓で状態を訊きにくるため、
        プロセスの有無だけを見ていると一度「止まっている」に戻ってしまう。
        指示した事実を数秒だけ覚えておいて、この窓を埋める。

        逆に停止直後はプロセスが消えきる前に拾えてしまうので、
        止めた直後の数秒は起動中とみなさない。
        """
        if engine_running() or time.monotonic() < stopping["until"]:
            return False
        if time.monotonic() < starting["until"]:
            return True
        # pgrep が無い環境（Windows）では、この一瞬の窓を埋める術が無い。
        # starting["until"] の間だけ拾えれば実害は小さいので諦めて False にする
        # （クラッシュして /api/state 自体が壊れるよりずっとまし）。
        try:
            r = subprocess.run(["pgrep", "-f", "voice_daemon.py --language"],
                               capture_output=True)
        except (OSError, FileNotFoundError):
            return False
        return bool(r.stdout.strip())

    # 送信先。空なら全員へ。
    route_path = state / "route"

    # Claude が切り替えたときの理由。画面に出すだけで、発話には混ぜない。
    note_file = Path(args.log_file).parent / "pause-note.txt"

    async def handle_state(_req):
        """マイクの入切、保留の有無、保留中の発話を返す。"""
        held = []
        if hold_file.exists():
            for line in hold_file.read_text().splitlines():
                rec = Tail._parse(line)
                if rec:
                    held.append(rec)
        # 画面ファイルの更新時刻も返す。手を入れたときに、開いている
        # 画面が古いままだと気づけない（特に浮かせた小窓は再読み込みしにくい）。
        try:
            ui = int(page.stat().st_mtime)
        except OSError:
            ui = 0
        return web.json_response({"muted": mute_file.exists(),
                                  "paused": pause_file.exists(),
                                  "engine": engine_running(),
                                  "loading": engine_loading(),
                                  "ui": ui, "held": held,
                                  "note": note_file.read_text()
                                          if note_file.exists() else ""})

    async def handle_engine(req):
        """認識を止める / 動かす。

        止めると GPU（約12GB）が解放される。ビューアは動いたままなので、
        ここから動かし直せる（モデル読み込みに1〜2分）。
        """
        body = await req.json()
        want = bool(body.get("running"))
        sh = str(Path(__file__).with_name("voice-shell.sh"))

        # 使うエンジンの指定。voice-shell.sh は起動時にこのファイルを見る。
        kind = (body.get("engine") or "").strip()
        if kind:
            import voice_daemon as vd
            vd.write_config(engine=kind)        # 次回の起動もこれになる
            if kind != "browser":
                (state / "engine").write_text(kind)

        # start_new_session でビューアから切り離す。
        # デーモンは終了時に自分の子を全部 kill するので、ビューアの系統に
        # ぶら下げると停止のときビューアまで巻き込まれる。
        if want and not engine_running():
            # 起動を指示した事実を覚えておく。切り離して起動するので
            # pgrep に映るまでの一瞬、プロセスが見えない時間がある。
            stopping["until"] = 0.0
            starting["until"] = time.monotonic() + 10
            subprocess.Popen(["bash", sh, "engine-start"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
        elif not want and engine_running():
            # プロセスが消えきるまで数秒あるので、その間は起動中と見なさない
            starting["until"] = 0.0
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
        """発話を保留する / 直接送るのに戻す。

        Claude 自身が切り替えることもある（雑談や通話が続いているとき）。
        自分で押していないモード変更は理由が無いと戸惑うだけなので、
        note を添えられるようにして画面に出す。
        """
        body = await req.json()
        note = (body.get("note") or "").strip()[:200]
        if body.get("paused"):
            pause_file.touch()
            note_file.write_text(note)
        else:
            pause_file.unlink(missing_ok=True)
            note_file.unlink(missing_ok=True)
        return web.json_response({"paused": pause_file.exists(), "note": note})

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

    # ブラウザ認識の生存確認。開いている画面が「いま聞いている」ことを
    # 定期的に知らせてくる。これが無いと、wait-ready が READY を返しても
    # 実際には誰も聞いていない（画面が開かれていない・マイクを拒否された）
    # 状態と区別が付かず、「どうぞ話してください」と言った先で虚空に話させる。
    beat_file = state / "asr-heartbeat.json"
    BEAT_STALE = 15        # これだけ音沙汰が無ければ、その画面は居ないとみなす

    def read_beats() -> dict:
        try:
            d = json.loads(beat_file.read_text())
        except (OSError, ValueError):
            return {}
        now = time.time()
        return {k: v for k, v in d.items()
                if isinstance(v, dict) and now - v.get("t", 0) < BEAT_STALE}

    async def handle_heartbeat(req):
        body = await req.json()
        tab = str(body.get("tab") or "")[:40]
        st = str(body.get("state") or "")[:20]
        if not tab:
            return web.json_response({"error": "no tab"}, status=400)
        beats = read_beats()
        if st == "gone":
            beats.pop(tab, None)
        else:
            beats[tab] = {"t": time.time(), "state": st}
        beat_file.write_text(json.dumps(beats))
        return web.json_response({"tabs": len(beats)})

    async def handle_asr_status(_req):
        """ブラウザ認識がいま実際に聞いているか。voice-shell.sh status が読む。"""
        beats = read_beats()
        states = [v.get("state") for v in beats.values()]
        return web.json_response({
            "tabs": len(beats),
            "listening": states.count("listening"),
            "denied": states.count("denied"),
        })

    async def handle_engines(_req):
        """選べる認識エンジンの一覧。

        ブラウザの認識は何も入れずに動くので、これが既定。手元で完結させたい
        人のために、実際に入っているものだけを並べる。
        """
        import asr_mic, voice_daemon as vd
        return web.json_response({
            "engines": asr_mic.available_engines(),
            # 覚えている選択。ブラウザの localStorage ではなくこちらを正とする
            # （ブラウザごとに食い違うと、起動時の分岐が当てにならなくなる）。
            "chosen": vd.resolve_engine(""),
            "running": engine_running(),
        })

    async def handle_listeners(_req):
        """いま聞いているセッションの一覧と、選ばれている送信先。"""
        import voice_daemon as vd
        try:
            chosen = route_path.read_text().strip()
        except OSError:
            chosen = ""
        return web.json_response({
            "listeners": vd.list_active_listeners(args.log_file),
            "route": chosen,                                  # 選ばれているもの
            # 実際に届く先。未選択なら「あとで起動した方」に決まる。
            "target": vd.resolve_target(args.log_file) or "",
        })

    async def handle_route(req):
        """送信先を選ぶ。空なら全員へ。"""
        body = await req.json()
        to = str(body.get("to") or "").strip()
        route_path.write_text(to)
        return web.json_response({"route": to})

    async def handle_utterance(req):
        """ブラウザ側（Web Speech API）で認識した発話を受け取る。

        デーモンが認識したときと同じ道を通す — 辞書の言い換え、無視する発話、
        最小文字数、つなぎ言葉の除去、一時停止中の保留。ここを通さないと、
        認識のやり方によって届く文が変わってしまう。
        """
        body = await req.json()
        text = (body.get("text") or "").strip()
        if not text:
            return web.json_response({"error": "empty"}, status=400)

        import voice_daemon as vd

        # デーモンも認識しているなら受け取らない。同じ発話ログに両方が
        # 書くので、受けてしまうと同じ指示が2回 Claude に届く。
        # 画面側でも排他しているが、タブを複数開かれる場合もあるので
        # ここでも止める。
        if engine_running():
            return web.json_response({"dropped": "daemon_running"}, status=409)

        # マイクを切っているあいだは、どこにも残さない（デーモンと同じ扱い）
        if mute_file.exists():
            return web.json_response({"dropped": "muted"})

        try:
            tuning = json.loads(TUNING_FILE.read_text())
        except (OSError, ValueError):
            tuning = {}

        # 順序はデーモンに合わせる（最小文字数 → 無視語 → 整形）。
        # polish は辞書の言い換えで文字数が変わるので、順序が違うと
        # 同じ発話でも認識のやり方によって届く／届かないが変わる。
        min_chars = tuning.get("min_chars", 15)
        if isinstance(min_chars, (int, float)) and len(text) < int(min_chars):
            return web.json_response({"dropped": "too_short"})

        user_dict = vd.load_dictionary()
        if vd.is_noise(text, user_dict["ignore"]):
            return web.json_response({"dropped": "noise"})

        text = vd.polish(text, user_dict, False,
                         bool(tuning.get("strip_fillers")))

        stamp = time.strftime("%H:%M:%S")
        if pause_file.exists():
            with open(hold_file, "a", encoding="utf-8") as h:
                h.write(json.dumps({"time": stamp, "text": text},
                                   ensure_ascii=False) + "\n")
            return web.json_response({"held": text})

        with open(args.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps({"text": text}, ensure_ascii=False) + "\n")
        return web.json_response({"time": stamp, "text": text})

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
    engine_active_file = state / "engine_active"

    async def handle_tuning_get(_req):
        """いまの感度と確定までの無音秒数を返す。範囲も一緒に返して
        スライダの端をサーバ側の制限と揃える。"""
        try:
            cur = json.loads(TUNING_FILE.read_text())
        except (OSError, ValueError):
            cur = {}
        keys = list(TUNING_RANGE) + list(TUNING_FLAGS)
        return web.json_response({
            "tuning": {k: cur.get(k) for k in keys},
            "range": {k: {"min": lo, "max": hi}
                      for k, (lo, hi) in TUNING_RANGE.items()},
        })

    async def handle_tuning_put(req):
        """感度と無音秒数を書き換える。デーモンが次の周期で拾う。"""
        body = await req.json()
        try:
            cur = json.loads(TUNING_FILE.read_text())
        except (OSError, ValueError):
            cur = {}

        for key, (lo, hi) in TUNING_RANGE.items():
            if not isinstance(body.get(key), (int, float)):
                continue
            v = min(hi, max(lo, float(body[key])))
            cur[key] = int(round(v)) if key in TUNING_INT else v

        for key in TUNING_FLAGS:
            if isinstance(body.get(key), bool):
                cur[key] = body[key]

        if isinstance(body.get("language"), str):
            import whisper_engine
            code = body["language"]
            # 空文字（自動判定）か、対応済みコードのときだけ受け付ける
            if code == "" or code in whisper_engine.LANGUAGE_NAMES:
                cur["language"] = code

        TUNING_FILE.parent.mkdir(parents=True, exist_ok=True)
        TUNING_FILE.write_text(json.dumps(cur, indent=2) + "\n")
        return web.json_response({"tuning": cur})

    async def handle_languages(_req):
        """認識言語の一覧（Whisper 使用時のみ）。他のエンジンでは
        空リストを返し、ビューア側はプルダウンごと隠す。"""
        try:
            engine = engine_active_file.read_text().strip()
        except OSError:
            engine = ""
        if engine != "whisper":
            return web.json_response({"engine": engine, "languages": [], "current": ""})
        import whisper_engine
        try:
            cur = json.loads(TUNING_FILE.read_text()).get("language", "")
        except (OSError, ValueError):
            cur = ""
        return web.json_response({
            "engine": engine,
            "languages": whisper_engine.available_languages(),
            "current": cur,
        })

    async def handle_mics(_req):
        """使えるマイクの一覧と、いま選ばれているものを返す。"""
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
    app.router.add_get("/api/tuning", handle_tuning_get)
    app.router.add_put("/api/tuning", handle_tuning_put)
    app.router.add_get("/api/languages", handle_languages)
    app.router.add_put("/api/mics", handle_mic_put)
    app.router.add_get("/api/dictionary", handle_dict_get)
    app.router.add_put("/api/dictionary", handle_dict_put)
    app.router.add_post("/api/mute", handle_mute)
    app.router.add_post("/api/pause", handle_pause)
    app.router.add_post("/api/send", handle_send)
    app.router.add_post("/api/utterance", handle_utterance)
    app.router.add_post("/api/asr-heartbeat", handle_heartbeat)
    app.router.add_get("/api/asr-status", handle_asr_status)
    app.router.add_get("/api/engines", handle_engines)
    app.router.add_get("/api/listeners", handle_listeners)
    app.router.add_put("/api/route", handle_route)
    app.router.add_post("/api/discard", handle_discard)

    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, args.host, args.port).start()

    print(f"\n  ブラウザで開いてください →  http://{args.host}:{args.port}"
          f"\n  追尾中: {args.log_file}\n", file=sys.stderr, flush=True)

    tasks = [asyncio.create_task(tail.watch()),
             asyncio.create_task(tail.watch_partial()),
             asyncio.create_task(tail.watch_level()),
             asyncio.create_task(tail.watch_held()),
             asyncio.create_task(tail.watch_mic_active()),
             asyncio.create_task(tail.watch_muted()),
             asyncio.create_task(tail.watch_voice_cmd())]
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
