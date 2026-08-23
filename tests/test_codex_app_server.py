import json
import os
import shlex
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORWARD = ROOT / "skills/voice-shell/scripts/codex_app_server.py"


MOCK = r'''
import json
import os
import sys

mode = os.environ.get("MOCK_MODE", "normal")
log_path = os.environ["MOCK_LOG"]
turn_number = 0
waiting_turn = None

def emit(message):
    print(json.dumps(message), flush=True)

def record(value):
    with open(log_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(value) + "\n")

for line in sys.stdin:
    message = json.loads(line)
    method = message.get("method")
    record(message)
    if method == "initialize":
        if mode == "large-event":
            emit({"method": "turn/started", "params": {"payload": "x" * 100_000}})
        emit({"id": message["id"], "result": {}})
    elif method == "thread/resume":
        emit({"id": message["id"], "result": {"thread": {"id": message["params"]["threadId"]}}})
    elif method == "turn/start":
        turn_number += 1
        turn_id = f"turn-{turn_number}"
        emit({"id": message["id"], "result": {"turn": {"id": turn_id, "status": "inProgress"}}})
        if mode == "disconnect":
            sys.exit(7)
        if mode == "approval" and turn_number == 1:
            waiting_turn = turn_id
            emit({
                "id": "approval-1",
                "method": "item/commandExecution/requestApproval",
                "params": {"threadId": "thread-123", "turnId": turn_id, "itemId": "item-1"},
            })
        else:
            emit({"method": "turn/completed", "params": {"turn": {"id": turn_id, "status": "completed"}}})
    elif message.get("id") == "approval-1":
        emit({
            "method": "turn/completed",
            "params": {"turn": {"id": waiting_turn, "status": "failed", "error": {"message": "declined"}}},
        })
        waiting_turn = None
'''


class CodexForwardTest(unittest.TestCase):
    def make_env(self, temp_path, mode="normal"):
        mock = temp_path / "mock_server.py"
        log = temp_path / "server.jsonl"
        mock.write_text(textwrap.dedent(MOCK), encoding="utf-8")
        return os.environ | {
            "CODEX_THREAD_ID": "thread-123",
            "CODEX_BIN": f"{shlex.quote(sys.executable)} {shlex.quote(str(mock))}",
            "MOCK_LOG": str(log),
            "MOCK_MODE": mode,
        }, log

    def test_initializes_resumes_and_serializes_filtered_turns(self):
        with tempfile.TemporaryDirectory() as temp:
            env, log = self.make_env(Path(temp))
            payload = "\n".join([
                '{"text":" first "}',
                '{"text":""}',
                '{"text": 4}',
                '{"text":"not for this listener", "to":"other"}',
                '{"text":"second", "to":7}',
                "not json",
                "",
            ])
            result = subprocess.run(
                [sys.executable, str(FORWARD), "--listener-pid", "7"],
                input=payload,
                text=True,
                capture_output=True,
                env=env,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            messages = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(
                [message["method"] for message in messages if message.get("method") in {"initialize", "initialized", "thread/resume", "turn/start"}],
                ["initialize", "initialized", "thread/resume", "turn/start", "turn/start"],
            )
            turns = [message["params"]["input"][0]["text"] for message in messages if message.get("method") == "turn/start"]
            self.assertEqual(turns, ["first", "second"])

    def test_declines_approval_and_continues_fifo(self):
        with tempfile.TemporaryDirectory() as temp:
            env, log = self.make_env(Path(temp), "approval")
            result = subprocess.run(
                [sys.executable, str(FORWARD)],
                input='{"text":"first"}\n{"text":"second"}\n',
                text=True,
                capture_output=True,
                env=env,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            messages = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
            approval = next(message for message in messages if message.get("id") == "approval-1")
            self.assertEqual(approval["result"], {"decision": "decline"})
            turns = [message["params"]["input"][0]["text"] for message in messages if message.get("method") == "turn/start"]
            self.assertEqual(turns, ["first", "second"])
            self.assertIn("Codex turn failed: declined", result.stderr)

    def test_accepts_large_server_events(self):
        with tempfile.TemporaryDirectory() as temp:
            env, log = self.make_env(Path(temp), "large-event")
            result = subprocess.run(
                [sys.executable, str(FORWARD)],
                input='{"text":"large event"}\n',
                text=True,
                capture_output=True,
                env=env,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            messages = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(
                [message["method"] for message in messages if message.get("method") == "turn/start"],
                ["turn/start"],
            )

    def test_exits_when_server_disconnects_with_input_open(self):
        with tempfile.TemporaryDirectory() as temp:
            env, _ = self.make_env(Path(temp), "disconnect")
            process = subprocess.Popen(
                [sys.executable, str(FORWARD)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            try:
                process.stdin.write('{"text":"first"}\n')
                process.stdin.flush()
                self.assertNotEqual(process.wait(timeout=5), 0)
                self.assertIn("closed its output", process.stderr.read())
            finally:
                if process.stdin and not process.stdin.closed:
                    process.stdin.close()
                if process.poll() is None:
                    process.kill()
                    process.wait()
                if process.stdout:
                    process.stdout.close()
                if process.stderr:
                    process.stderr.close()


if __name__ == "__main__":
    unittest.main()
