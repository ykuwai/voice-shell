#!/usr/bin/env python3
"""Regenerate the README screenshots of the viewer, in every UI language.

This runs the real viewer (skills/voice-shell/scripts/viewer.py) against a
throwaway state directory and a throwaway config directory, fills them with
sample sessions, sent history and text being recognized, and photographs the
page with headless Chrome over the DevTools protocol. Nothing here belongs to
the shipped skill. It only ever touches what it created itself: its own temp
folders, its own viewer on its own port, its own dummy processes and its own
Chrome, all of which are torn down at the end, error or not.

    .venv/Scripts/python.exe docs/readme/tools/make_screenshots.py      (Windows)
    .venv/bin/python docs/readme/tools/make_screenshots.py              (macOS)

See README.md next to this file for the options.
"""
import argparse
import asyncio
import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

try:
    import aiohttp
except ImportError:
    sys.exit("aiohttp is missing. Run this with the repo's .venv python, the "
             "same one the viewer itself needs.")

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SCRIPTS = REPO / "skills" / "voice-shell" / "scripts"
OUT_DIR = REPO / "docs" / "readme" / "images"

# The port a real voice-shell listens on. Whatever else happens, this tool
# never binds, connects to or otherwise goes near it, since the person running
# this is quite possibly talking to that viewer at the same moment.
REAL_PORT = 47865

LANGS = ["en", "ja", "es", "fr", "de", "zh", "zh-TW", "ko"]

# The CSS size of the picture. A little taller than the old hand-made
# screenshot (355x470, which was a floating window) so the chips, the
# unsent card and a few sent cards all fit in one frame.
WIDTH, HEIGHT, SCALE = 380, 640, 2


# Sample content. Each language gets its own, written the way someone would
# actually talk to Claude Code in it, rather than a word-for-word copy of the
# English. "chips" are the listening sessions (the first one is the selected
# destination), "sent" goes oldest first as (time, chip index, edited, text),
# and "partial" is what is being recognized right now.
SAMPLES = {
    "en": {
        "chips": ["Fix login bug", "Write API docs"],
        "sent": [
            ("10:41:08", 1, False, "Add a short example request and response to every endpoint in the API docs."),
            ("10:44:52", 0, True, "Login fails when the password contains a plus sign. Find where it gets encoded and fix it."),
            ("10:46:30", 0, False, "Run the tests again and tell me what is still failing."),
        ],
        "partial": "And add a regression test for the plus sign case",
    },
    "ja": {
        "chips": ["ログインのバグ修正", "API ドキュメント作成"],
        "sent": [
            ("10:41:08", 1, False, "API ドキュメントの各エンドポイントに、短いリクエストとレスポンスの例を付けて。"),
            ("10:44:52", 0, True, "パスワードにプラスが入っているとログインに失敗する。どこでエンコードしているか探して直して。"),
            ("10:46:30", 0, False, "もう一度テストを回して、まだ落ちているものを教えて。"),
        ],
        "partial": "それとプラスのケースの回帰テストも追加して",
    },
    "es": {
        "chips": ["Arreglar bug de login", "Documentar la API"],
        "sent": [
            ("10:41:08", 1, False, "Añade un ejemplo corto de petición y respuesta a cada endpoint de la documentación."),
            ("10:44:52", 0, True, "El login falla si la contraseña lleva un signo más. Busca dónde se codifica y arréglalo."),
            ("10:46:30", 0, False, "Vuelve a pasar los tests y dime cuáles siguen fallando."),
        ],
        "partial": "Y añade un test de regresión para el caso del signo más",
    },
    "fr": {
        "chips": ["Bug de connexion", "Doc de l'API"],
        "sent": [
            ("10:41:08", 1, False, "Ajoute un court exemple de requête et de réponse à chaque endpoint de la doc de l'API."),
            ("10:44:52", 0, True, "La connexion échoue quand le mot de passe contient un plus. Trouve où il est encodé et corrige-le."),
            ("10:46:30", 0, False, "Relance les tests et dis-moi ce qui échoue encore."),
        ],
        "partial": "Et ajoute un test de non-régression pour le cas du plus",
    },
    "de": {
        "chips": ["Login-Bug beheben", "API-Doku schreiben"],
        "sent": [
            ("10:41:08", 1, False, "Füge in der API-Doku jedem Endpunkt ein kurzes Beispiel für Anfrage und Antwort hinzu."),
            ("10:44:52", 0, True, "Der Login schlägt fehl, wenn das Passwort ein Pluszeichen enthält. Finde die Stelle, wo es kodiert wird, und behebe das."),
            ("10:46:30", 0, False, "Lass die Tests noch mal laufen und sag mir, was noch fehlschlägt."),
        ],
        "partial": "Und schreib einen Regressionstest für das Pluszeichen",
    },
    "zh": {
        "chips": ["修复登录 bug", "编写 API 文档"],
        "sent": [
            ("10:41:08", 1, False, "给 API 文档里的每个接口都加一个简短的请求和响应示例。"),
            ("10:44:52", 0, True, "密码里带加号时登录会失败。找到编码的地方并修好它。"),
            ("10:46:30", 0, False, "再跑一遍测试，告诉我还有哪些没通过。"),
        ],
        "partial": "另外给加号的情况补一个回归测试",
    },
    # Written the way it is said in Taiwan, not the Simplified sample converted
    # (文件 and 端點 rather than 文档 and 接口).
    "zh-TW": {
        "chips": ["修正登入 bug", "撰寫 API 文件"],
        "sent": [
            ("10:41:08", 1, False, "幫 API 文件裡的每個端點都加上一個簡短的請求和回應範例。"),
            ("10:44:52", 0, True, "密碼裡有加號的時候登入會失敗。找出編碼的地方，然後把它修好。"),
            ("10:46:30", 0, False, "再跑一次測試，告訴我還有哪些沒過。"),
        ],
        "partial": "另外幫加號的情況補一個回歸測試",
    },
    "ko": {
        "chips": ["로그인 버그 수정", "API 문서 작성"],
        "sent": [
            ("10:41:08", 1, False, "API 문서의 모든 엔드포인트에 짧은 요청과 응답 예시를 추가해 줘."),
            ("10:44:52", 0, True, "비밀번호에 플러스 기호가 있으면 로그인이 실패해. 인코딩하는 곳을 찾아서 고쳐 줘."),
            ("10:46:30", 0, False, "테스트를 다시 돌리고 아직 실패하는 게 뭔지 알려 줘."),
        ],
        "partial": "그리고 플러스 기호 경우에 대한 회귀 테스트도 추가해 줘",
    },
}


# Runs in the page before any of the viewer's own scripts. Everything here
# happens only inside this throwaway Chrome.
#
# The language and theme are the viewer's own per-browser settings
# (localStorage "vs.lang" and "vs.theme"), set the way picking them in the
# settings sheet would.
#
# Browser speech recognition is removed. With it present the viewer waits for
# a first click before it may open the mic, sits muted until then, and on that
# click starts Chrome's recognizer, which headless Chrome refuses outright and
# the page then reports as a denied microphone. Without it the viewer takes
# the path it already has for browsers that lack recognition: it relies on
# the daemon for recognition and shows whatever the server reports, which is
# exactly what the sample state below feeds it.
#
# The page also carries its unsent text and the mic state across a reload in
# the same tab (sessionStorage "vs.resume", issue #118). Every shot here reloads
# the same tab with new sample state, so without clearing it the previous
# language's text came back into the next one (Japanese text in the Korean shot).
PAGE_PRELUDE = """
try { sessionStorage.clear(); } catch (e) {}
try {
  localStorage.setItem('vs.lang', %(lang)s);
  localStorage.setItem('vs.theme', 'dark');
} catch (e) {}
try { delete window.SpeechRecognition; } catch (e) {}
try { delete window.webkitSpeechRecognition; } catch (e) {}
window.SpeechRecognition = undefined;
window.webkitSpeechRecognition = undefined;
"""


def find_chrome():
    """Where Chrome (or Chromium / Edge as a stand-in) lives on this machine."""
    if os.environ.get("CHROME_PATH"):
        return os.environ["CHROME_PATH"]
    candidates = []
    if sys.platform.startswith("win"):
        for base in (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"),
                     os.environ.get("LOCALAPPDATA")):
            if base:
                candidates += [Path(base) / "Google/Chrome/Application/chrome.exe",
                               Path(base) / "Chromium/Application/chrome.exe",
                               Path(base) / "Microsoft/Edge/Application/msedge.exe"]
    elif sys.platform == "darwin":
        for app in ("Google Chrome", "Chromium", "Microsoft Edge"):
            candidates += [Path("/Applications") / f"{app}.app/Contents/MacOS/{app}",
                           Path.home() / f"Applications/{app}.app/Contents/MacOS/{app}"]
    for c in candidates:
        if c.is_file():
            return str(c)
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
        hit = shutil.which(name)
        if hit:
            return hit
    sys.exit("Chrome was not found. Point CHROME_PATH at the browser's executable.")


def free_port():
    """A port nobody is using, and never the real viewer's."""
    while True:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        if port != REAL_PORT:
            return port


def spawn_dummy():
    """A process of our own that does nothing but stay alive.

    The viewer only shows a listening session whose PID is alive (and started
    before it registered), so each sample chip needs a real, living PID behind
    it. These are ours, and they are killed at the end."""
    flags = subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(3600)"],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, creationflags=flags)


def write_jsonl(path, records):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
                    encoding="utf-8")


class Stage:
    """The throwaway world one run lives in: folders, dummies, the viewer."""

    def __init__(self, root: Path, python: str):
        self.root = root
        self.python = python
        self.state = root / "state"
        self.home = root / "home"
        self.config_home = self.home / ".config"
        self.config = self.config_home / "voice-shell"
        self.port = free_port()
        self.dummies = []
        self.viewer = None

    def setup(self):
        for d in (self.state / "listeners", self.config / "run"):
            d.mkdir(parents=True, exist_ok=True)
        # Two chips and one more for the pretend recognition engine.
        # Appended one at a time, so a failure partway still leaves the ones
        # already started where teardown can find them.
        for _ in range(3):
            self.dummies.append(spawn_dummy())
        # The viewer counts the engine as running when run/daemon.pid names a
        # live process. With browser recognition taken out of the page (see
        # PAGE_PRELUDE) that is what makes it show its normal listening
        # screen rather than "stopped".
        (self.config / "run" / "daemon.pid").write_text(str(self.dummies[2].pid), encoding="utf-8")

    def seed(self, lang):
        """Lay down everything the viewer reads, for one language.

        The listener registrations are written after their processes started,
        since one claiming to predate its own PID is treated as a recycled PID
        and cleared away."""
        sample = SAMPLES[lang]
        chip_pids = [p.pid for p in self.dummies[:2]]
        for f in (self.state / "listeners").iterdir():
            f.unlink()
        now = time.time()
        for i, (pid, name) in enumerate(zip(chip_pids, sample["chips"])):
            reg = {"started": time.strftime("%Y-%m-%d %H:%M:%S"), "since": now,
                   "order": now - 100 + i, "cwd": str(self.root / f"project{i + 1}"),
                   "agent": "claude", "session": str(uuid.uuid4()), "name": name}
            (self.state / "listeners" / str(pid)).write_text(
                json.dumps(reg, ensure_ascii=False), encoding="utf-8")
        # The first chip is the chosen destination.
        (self.state / "route").write_text(str(chip_pids[0]), encoding="utf-8")
        write_jsonl(self.state / "utterances.jsonl",
                    [{"time": at, "text": text, "to": chip_pids[chip], **({"edited": True} if edited else {})}
                     for at, chip, edited, text in sample["sent"]])
        (self.state / "partial.txt").write_text(sample["partial"], encoding="utf-8")
        for name in ("muted", "history_cleared_at", "draft_carry"):
            (self.state / name).unlink(missing_ok=True)

    def start_viewer(self):
        """Start (or restart) the viewer. It reads the sent history once, as it
        starts, so a fresh history for the next language means a fresh viewer."""
        self.stop_viewer()
        env = dict(os.environ)
        # Every place the viewer and voice_daemon.py look for state and
        # settings points into our temp folder: VOICE_SHELL_STATE_DIR for the
        # state, XDG_CONFIG_HOME for ~/.config/voice-shell, and the home
        # directory itself for the few lookups that go straight there.
        env.update({"VOICE_SHELL_STATE_DIR": str(self.state),
                    "XDG_CONFIG_HOME": str(self.config_home),
                    "XDG_RUNTIME_DIR": str(self.root),
                    "HOME": str(self.home), "USERPROFILE": str(self.home),
                    "VOICE_SHELL_PORT": str(self.port),
                    # The same as voice-shell.sh. The history is read with the
                    # platform's default encoding, which is not UTF-8 on Windows.
                    "PYTHONUTF8": "1"})
        env.pop("VOICE_SHELL_NAME", None)
        log = open(self.root / "viewer.log", "ab")
        self.viewer = subprocess.Popen(
            [self.python, str(SCRIPTS / "viewer.py"), "--log-file", str(self.state / "utterances.jsonl"),
             "--host", "127.0.0.1", "--port", str(self.port)],
            env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, cwd=str(self.root))
        log.close()

    def stop_viewer(self):
        if self.viewer and self.viewer.poll() is None:
            self.viewer.terminate()
            try:
                self.viewer.wait(10)
            except subprocess.TimeoutExpired:
                self.viewer.kill()
        self.viewer = None

    def teardown(self):
        self.stop_viewer()
        for p in self.dummies:
            if p.poll() is None:
                p.kill()
            try:
                p.wait(5)
            except subprocess.TimeoutExpired:
                pass


class Chrome:
    """A headless Chrome of our own, driven over the DevTools protocol."""

    def __init__(self, root: Path):
        self.profile = root / "chrome"
        self.proc = None
        self.http = None
        self.ws = None
        self.next_id = 0
        self.pending = {}
        self.events = asyncio.Queue()
        self.reader = None

    async def start(self):
        self.profile.mkdir(parents=True, exist_ok=True)
        self.proc = subprocess.Popen(
            [find_chrome(), "--headless=new", "--remote-debugging-port=0",
             f"--user-data-dir={self.profile}", "--no-first-run", "--no-default-browser-check",
             "--disable-extensions", "--disable-background-networking", "--disable-sync",
             "--hide-scrollbars", "--mute-audio", f"--window-size={WIDTH},{HEIGHT}", "about:blank"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # Chrome writes the port it actually took into its profile folder.
        port_file = self.profile / "DevToolsActivePort"
        for _ in range(150):
            if port_file.exists() and port_file.read_text().strip():
                break
            await asyncio.sleep(0.1)
        else:
            raise RuntimeError("Chrome did not open its DevTools port")
        port = int(port_file.read_text().splitlines()[0])
        self.http = aiohttp.ClientSession()
        targets = await (await self.http.get(f"http://127.0.0.1:{port}/json/list")).json()
        page = next(t for t in targets if t.get("type") == "page")
        self.ws = await self.http.ws_connect(page["webSocketDebuggerUrl"], max_msg_size=0)
        self.reader = asyncio.create_task(self._read())
        await self.send("Page.enable")
        await self.send("Runtime.enable")
        await self.send("Emulation.setDeviceMetricsOverride",
                        width=WIDTH, height=HEIGHT, deviceScaleFactor=SCALE, mobile=False)
        # The viewer asks for dark by name anyway, this just keeps any
        # "auto" styling on the same side.
        await self.send("Emulation.setEmulatedMedia",
                        features=[{"name": "prefers-color-scheme", "value": "dark"}])

    async def _read(self):
        async for msg in self.ws:
            if msg.type != aiohttp.WSMsgType.TEXT:
                break
            data = json.loads(msg.data)
            fut = self.pending.pop(data.get("id"), None)
            if fut and not fut.done():
                if "error" in data:
                    fut.set_exception(RuntimeError(f"CDP error: {data['error']}"))
                else:
                    fut.set_result(data.get("result", {}))
            elif "method" in data:
                self.events.put_nowait(data)

    async def send(self, method, **params):
        self.next_id += 1
        fut = asyncio.get_running_loop().create_future()
        self.pending[self.next_id] = fut
        await self.ws.send_json({"id": self.next_id, "method": method, "params": params})
        return await asyncio.wait_for(fut, 30)

    async def evaluate(self, expr):
        r = await self.send("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        return r.get("result", {}).get("value")

    async def open(self, url, prelude):
        """Load the page fresh with the prelude in place before its scripts run."""
        r = await self.send("Page.addScriptToEvaluateOnNewDocument", source=prelude)
        try:
            while not self.events.empty():
                self.events.get_nowait()
            await self.send("Page.navigate", url=url)
            while True:
                ev = await asyncio.wait_for(self.events.get(), 30)
                if ev["method"] == "Page.loadEventFired":
                    break
        finally:
            await self.send("Page.removeScriptToEvaluateOnNewDocument", identifier=r["identifier"])

    async def wait_for(self, expr, what, timeout=20):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if await self.evaluate(expr):
                return
            await asyncio.sleep(0.2)
        raise RuntimeError(f"Timed out waiting for {what}")

    async def screenshot(self, path: Path):
        r = await self.send("Page.captureScreenshot", format="png")
        path.write_bytes(base64.b64decode(r["data"]))

    async def close(self):
        try:
            if self.ws and not self.ws.closed:
                await asyncio.wait_for(self.send("Browser.close"), 5)
        except Exception:
            pass
        if self.reader:
            self.reader.cancel()
        if self.http:
            await self.http.close()
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                # Only ever the tree under the Chrome we started ourselves.
                if sys.platform.startswith("win"):
                    subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.proc.pid)],
                                   capture_output=True)
                else:
                    self.proc.kill()
                self.proc.wait(10)


# The page is ready to photograph once the language took, both chips are in,
# every sent card is on screen with its destination named, the unsent card
# holds the recognized text, Instant mode is the one selected and the fonts
# are loaded.
READY = """
(async () => {
  const q = s => [...document.querySelectorAll(s)];
  if (document.documentElement.lang !== %(lang)s) return false;
  if (q('#routeChips > *').length < 2) return false;
  if (q('#log .entry').length !== %(sent)d) return false;
  if (!document.getElementById('stream').textContent.trim()) return false;
  if (document.getElementById('segLive').getAttribute('aria-checked') !== 'true') return false;
  await document.fonts.ready;
  return true;
})()
"""


async def capture_all(langs, out_dir, python, keep):
    root = Path(tempfile.mkdtemp(prefix="vs-screens-"))
    stage = Stage(root, python)
    chrome = Chrome(root)
    try:
        stage.setup()
        await chrome.start()
        for lang in langs:
            stage.seed(lang)
            stage.start_viewer()
            url = f"http://127.0.0.1:{stage.port}/"
            await wait_http(url, stage)
            await chrome.open(url, PAGE_PRELUDE % {"lang": json.dumps(lang)})
            await chrome.wait_for(READY % {"lang": json.dumps(lang), "sent": len(SAMPLES[lang]["sent"])},
                                  f"the {lang} screen")
            # An ordinary tab asks "Keep this window on top" in a bubble
            # every time it loads, and any click outside it puts it away.
            # Put it away the same way here, so it does not cover the
            # header in every picture.
            await chrome.evaluate("document.getElementById('floatAsk').hidden = true")
            # Let the chips, the log and the level meter settle their
            # transitions before the shutter.
            await asyncio.sleep(1.5)
            out = out_dir / f"screen-{lang}.png"
            await chrome.screenshot(out)
            print(f"wrote {out.relative_to(REPO) if out.is_relative_to(REPO) else out}")
    finally:
        # Chrome going down badly must not keep the viewer and the dummies
        # from being stopped after it.
        try:
            await chrome.close()
        except Exception as error:
            print(f"closing Chrome failed: {error}", file=sys.stderr)
        stage.teardown()
        if keep:
            print(f"kept {root}")
        else:
            # Chrome lets go of its profile a moment after it exits on Windows.
            for _ in range(20):
                shutil.rmtree(root, ignore_errors=True)
                if not root.exists():
                    break
                time.sleep(0.5)


async def wait_http(url, stage, timeout=30):
    deadline = time.monotonic() + timeout
    async with aiohttp.ClientSession() as http:
        while time.monotonic() < deadline:
            if stage.viewer.poll() is not None:
                log = (stage.root / "viewer.log").read_text(encoding="utf-8", errors="replace")
                raise RuntimeError(f"The viewer exited early:\n{log}")
            try:
                async with http.get(url + "api/state") as r:
                    if r.status == 200:
                        return
            except aiohttp.ClientError:
                pass
            await asyncio.sleep(0.2)
    raise RuntimeError("The viewer did not come up")


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--lang", action="append", choices=LANGS,
                   help="Only this language (repeatable). Default: all of them")
    p.add_argument("--out", default=str(OUT_DIR), help="Where the PNGs go")
    p.add_argument("--keep-temp", action="store_true",
                   help="Leave the temp folder (state, config, viewer.log) for a look afterwards")
    args = p.parse_args()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    asyncio.run(capture_all(args.lang or LANGS, out_dir, sys.executable, args.keep_temp))


if __name__ == "__main__":
    main()
