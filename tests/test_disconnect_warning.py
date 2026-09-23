"""The x on a chip has to tell that session before it ends it.

SKILL.md promises one `system_warning` line saying listening was ended from
the screen, so the agent can tell being stopped on purpose from having
crashed. Live it did not arrive: the watch simply ended, with an empty output
file and the registration already swept away.

What it used to do was write the line into the log, sleep half a second and
send SIGTERM. On Windows that signal is a TerminateProcess, so the listen
shell went down where it stood. Its EXIT trap never ran, anything its tail had
not polled up by then went with it, and list_active_listeners cleared the
registration as a dead PID the next time it looked. Nothing was left for the
session to read.

Now the line itself ends that listen (listen_filter.py prints it and quits),
and the disconnect waits for the registration to go, which is that listen's
own trap saying the line is out.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/voice-shell/scripts"
sys.path.insert(0, str(SCRIPTS))

import voice_daemon as vd


class StopMarkerTest(unittest.TestCase):
    """listen_filter.py, fed by hand, with the input never closed.

    The old filter printed the line and read on forever, waiting for a signal
    that had to arrive from outside. Exiting itself is what makes printing and
    ending one thing.
    """

    def test_a_stop_warning_is_printed_and_then_ends_the_watch(self):
        # stdin is deliberately left open all the way through. Closing it is
        # the other thing that ends the filter, and it would hide exactly what
        # this is about: the line itself has to be what ends it.
        line = json.dumps({"system_warning": "stopped from the screen",
                           "to": "111", "stop": True})
        proc = subprocess.Popen(
            [sys.executable, "-u", str(SCRIPTS / "listen_filter.py"), "111"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        try:
            proc.stdin.write(line + "\n")
            proc.stdin.flush()
            self.assertEqual(proc.stdout.readline().strip(), line)
            try:
                code = proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.fail("the filter read on instead of ending with the line")
            self.assertEqual(code, 0)
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.stdin.close()
            proc.stdout.close()
            proc.wait()

    def test_a_stop_warning_for_someone_else_ends_nothing_here(self):
        # One session being disconnected must not take every other one down.
        line = json.dumps({"system_warning": "x", "to": "222", "stop": True})
        proc = subprocess.Popen(
            [sys.executable, "-u", str(SCRIPTS / "listen_filter.py"), "111"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        proc.stdin.write(line + "\n")
        proc.stdin.flush()
        time.sleep(1)
        still_here = proc.poll() is None
        proc.stdin.close()
        proc.communicate(timeout=10)
        self.assertTrue(still_here)

    def test_a_stop_addressed_to_an_older_pid_of_mine_ends_nothing(self):
        """A stop names one process, and an alias is not that process.

        On a re-arm this listen answers to its own earlier PIDs as well, so
        that what was said while nobody was reading still arrives. A stop left
        unread in the log (the x was pressed, the reader had already gone) is
        replayed the same way. Acted on, it ends a listen that is running
        perfectly well; printed, it tells that agent it was disconnected when
        it was not. Either way the line is somebody else's.
        """
        line = json.dumps({"system_warning": "x", "to": "111", "stop": True})
        env = dict(os.environ, VOICE_SHELL_ALIAS_UNTIL="999999",
                   VOICE_SHELL_START_OFFSET="0")
        env.pop("VOICE_SHELL_PROGRESS", None)
        env.pop("VOICE_SHELL_PARENT_PID", None)
        proc = subprocess.Popen(
            [sys.executable, "-u", str(SCRIPTS / "listen_filter.py"), "222", "111"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, env=env)
        proc.stdin.write(line + "\n")
        proc.stdin.flush()
        time.sleep(1)
        still_here = proc.poll() is None
        proc.stdin.close()
        out = proc.communicate(timeout=10)[0]
        self.assertTrue(still_here, "a predecessor's stop ended this listen")
        self.assertEqual(out.strip(), "", "and it must not be printed either")

    def test_an_utterance_to_an_older_pid_of_mine_still_arrives(self):
        """The alias itself has to go on working. Same line without "stop"."""
        line = json.dumps({"text": "hello", "to": "111"})
        env = dict(os.environ, VOICE_SHELL_ALIAS_UNTIL="999999",
                   VOICE_SHELL_START_OFFSET="0")
        env.pop("VOICE_SHELL_PROGRESS", None)
        env.pop("VOICE_SHELL_PARENT_PID", None)
        proc = subprocess.Popen(
            [sys.executable, "-u", str(SCRIPTS / "listen_filter.py"), "222", "111"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, env=env)
        proc.stdin.write(line + "\n")
        proc.stdin.flush()
        try:
            self.assertEqual(proc.stdout.readline().strip(), line)
        finally:
            proc.stdin.close()
            proc.communicate(timeout=10)


BASH = shutil.which("bash")


def _shell_env(env):
    """Put the shell's own tools on PATH.

    Started from Python on Windows, bash inherits the Windows PATH, which has
    none of readlink, cygpath or tail on it, and voice-shell.sh falls over at
    its first line. Started from a shell they are already there.
    """
    if not BASH:
        return env
    root = Path(BASH).resolve().parents[1]
    extra = [str(root / "usr" / "bin"), str(root / "bin")]
    env["PATH"] = os.pathsep.join(extra + [env.get("PATH", "")])
    return env


@unittest.skipUnless(BASH, "bash is not installed")
class DisconnectEndToEndTest(unittest.TestCase):
    """A real `voice-shell.sh listen` writing to a file, then the x pressed.

    Its own state directory, its own config and its own home, and it never
    goes near a port: nothing here touches a voice-shell anyone is using.
    """

    def setUp(self):
        # Whatever this listen left running can still be holding one of
        # these open when the folder goes; that is not a test failure.
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(self.tmp.name)
        self.state = root / "run" / "voice-shell"
        self.state.mkdir(parents=True)
        self.log = self.state / "utterances.jsonl"
        self.log.write_text("", encoding="utf-8")
        self.out = root / "out.txt"
        env = dict(os.environ)
        env.update({
            "XDG_RUNTIME_DIR": str(root / "run"),
            "XDG_CONFIG_HOME": str(root / "cfg"),
            "HOME": str(root / "home"),
            "CLAUDE_CODE_SESSION_ID": "disconnect-warning-test",
        })
        _shell_env(env)
        env.pop("VOICE_SHELL_NAME", None)
        self.handle = open(self.out, "w", encoding="utf-8")
        self.errors = open(root / "err.txt", "w", encoding="utf-8")
        self.listen = subprocess.Popen(
            [BASH, str(SCRIPTS / "voice-shell.sh"), "listen"],
            stdout=self.handle, stderr=self.errors, env=env)

    def tearDown(self):
        if self.listen.poll() is None:
            self.listen.kill()
        self.listen.wait()
        self.handle.close()
        self.errors.close()
        self.tmp.cleanup()

    def registered_pid(self, timeout=20):
        deadline = time.time() + timeout
        while time.time() < deadline:
            listeners = self.state / "listeners"
            names = sorted(f.name for f in listeners.iterdir()) if listeners.is_dir() else []
            if names:
                return names[0]
            time.sleep(0.1)
            self.assertIsNone(self.listen.poll(), "listen ended before registering")
        self.fail("listen never registered itself")

    def test_the_x_delivers_one_warning_before_the_watch_ends(self):
        pid = self.registered_pid()
        # Pressed the moment the chip appears, which is also the narrowest
        # window there is: the registration is what puts it on screen, and
        # for a while the listen measured where to start reading from only
        # after writing it, so a line written in between fell behind the
        # starting point and was never read.
        t0 = time.time()
        entry = vd.disconnect_listener(self.log, pid)
        elapsed = time.time() - t0
        self.assertIsNotNone(entry)
        # Came back on the listen letting go, not on the wait running out,
        # so no signal was needed to end it.
        self.assertLess(elapsed, vd.DISCONNECT_WAIT)
        # The call comes back only once that listen has really gone, which is
        # what says the line is out. Before, it came back after a fixed half
        # second with the registration still on disk and the line unread.
        self.assertFalse((self.state / "listeners" / pid).exists())
        self.assertEqual(self.listen.wait(timeout=10), 0)
        self.handle.flush()
        lines = [json.loads(x) for x in
                 self.out.read_text(encoding="utf-8").splitlines() if x.strip()]
        warnings = [x for x in lines if "system_warning" in x]
        self.assertEqual(len(warnings), 1, lines)
        self.assertEqual(str(warnings[0].get("to")), pid)
        self.assertIn("/voice-shell", warnings[0]["system_warning"])

    def test_it_leaves_no_place_for_a_re_arm_to_take_up(self):
        # The one re-arm the disconnect causes is turned away rather than
        # quietly listening again, which is the other half of the promise.
        pid = self.registered_pid()
        vd.disconnect_listener(self.log, pid)
        self.listen.wait(timeout=10)
        self.assertEqual(vd.adopt_tombstone(self.log, "disconnect-warning-test"),
                         "blocked")


@unittest.skipUnless(BASH, "bash is not installed")
class AliasWindowTest(unittest.TestCase):
    """A re-arm still hears what was said to it while the handover ran.

    Where tail starts reading and how far the old PID still counts as this
    session's own are two different questions. The first wants a measurement
    from before this registration exists, so an x pressed the instant the chip
    appears cannot land behind the starting point. The second wants one from
    after the destination has moved over, because right up to that moment the
    daemon was still tagging speech with the old PID. Measure the two together
    and one of them is wrong: taken early, every word said while the handover
    went through falls outside the window and is dropped, which is the one
    thing the replay exists to prevent.
    """

    SESSION = "alias-window-test"
    OLD_PID = "999001"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(self.tmp.name)
        self.state = root / "run" / "voice-shell"
        (self.state / "listeners-gone").mkdir(parents=True)
        self.log = self.state / "utterances.jsonl"
        # Something already in it, so an offset of 0 is plainly a replay from
        # the beginning rather than the end of an empty file.
        self.log.write_text(
            json.dumps({"text": "said before", "to": self.OLD_PID}) + "\n",
            encoding="utf-8")
        # The tombstone a Monitor deadline leaves behind. --adopt hands it to
        # the re-arm, which then replays from its offset and answers to its
        # PID as well.
        (self.state / "listeners-gone" / self.SESSION).write_text(json.dumps({
            "session": self.SESSION, "pid": self.OLD_PID, "left": time.time(),
            "offset": 0, "epoch": "-", "reg": {"order": time.time()}}),
            encoding="utf-8")
        self.env = _shell_env(dict(os.environ))
        self.env.update({
            "XDG_RUNTIME_DIR": str(root / "run"),
            "XDG_CONFIG_HOME": str(root / "cfg"),
            "HOME": str(root / "home"),
            "CLAUDE_CODE_SESSION_ID": self.SESSION,
        })
        self.env.pop("VOICE_SHELL_NAME", None)
        self.out = root / "out.txt"
        self.handle = open(self.out, "w", encoding="utf-8")
        self.errors = open(root / "err.txt", "w", encoding="utf-8")
        self.listen = None

    def tearDown(self):
        if self.listen and self.listen.poll() is None:
            self.listen.kill()
        if self.listen:
            self.listen.wait()
        self.handle.close()
        self.errors.close()
        self.tmp.cleanup()

    def test_a_word_said_during_the_handover_is_not_dropped(self):
        late = json.dumps({"text": "said during the handover", "to": self.OLD_PID})
        self.listen = subprocess.Popen(
            [BASH, str(SCRIPTS / "voice-shell.sh"), "listen"],
            stdout=self.handle, stderr=self.errors, env=self.env)
        # The registration appearing is the first thing after the starting
        # offset is measured, and the handover (the destination moving over,
        # the tombstone being forgotten) still has a way to run after it. So
        # this lands inside exactly the stretch in question.
        listeners = self.state / "listeners"
        deadline = time.time() + 20
        while time.time() < deadline:
            if listeners.is_dir() and any(listeners.iterdir()):
                break
            self.assertIsNone(self.listen.poll(), "listen ended before registering")
            time.sleep(0.002)
        else:
            self.fail("listen never registered itself")
        with open(self.log, "a", encoding="utf-8") as f:
            f.write(late + "\n")
            f.flush()
        deadline = time.time() + 20
        while time.time() < deadline:
            self.handle.flush()
            if late in self.out.read_text(encoding="utf-8"):
                return
            time.sleep(0.05)
        self.fail("what was said during the handover never arrived: "
                  + repr(self.out.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
