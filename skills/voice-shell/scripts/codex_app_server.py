#!/usr/bin/env python3
"""Forward voice-shell utterances to one existing Codex App Server thread."""
import argparse
import asyncio
import json
import os
import shlex
import sys
from collections import deque


class AppServerError(RuntimeError):
    pass


class TurnError(AppServerError):
    pass


class AppServer:
    def __init__(self, command):
        self.command = command
        self.proc = None
        self.request_id = 0
        self.pending = {}
        self.turns = {}
        self.finished_turns = {}
        self.reader_task = None
        self.stderr_task = None
        self.stderr = deque(maxlen=20)
        self.closed = None

    async def start(self):
        try:
            self.proc = await asyncio.create_subprocess_exec(
                *self.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            raise AppServerError(f"Could not start Codex App Server: {exc}") from exc
        self.reader_task = asyncio.create_task(self.read_messages())
        self.stderr_task = asyncio.create_task(self.read_stderr())
        self.closed = asyncio.get_running_loop().create_future()

    async def read_stderr(self):
        while line := await self.proc.stderr.readline():
            self.stderr.append(line.decode("utf-8", "replace").rstrip())

    async def read_messages(self):
        failure = None
        try:
            while line := await self.proc.stdout.readline():
                try:
                    message = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise AppServerError("Codex App Server wrote invalid JSON-RPC") from exc
                if "method" in message and "id" in message:
                    await self.reject_server_request(message)
                    continue
                if "id" in message:
                    future = self.pending.pop(message["id"], None)
                    if future and not future.done():
                        if "error" in message:
                            error = message["error"]
                            future.set_exception(AppServerError(
                                f"Codex App Server rejected the request: {error.get('message', error)}"
                            ))
                        else:
                            future.set_result(message.get("result", {}))
                    continue
                if message.get("method") != "turn/completed":
                    continue
                turn = message.get("params", {}).get("turn", {})
                turn_id = turn.get("id")
                if not turn_id:
                    continue
                self.finished_turns[turn_id] = turn
                future = self.turns.pop(turn_id, None)
                if future and not future.done():
                    self.finish_turn(future, turn)
        except Exception as exc:
            failure = exc if isinstance(exc, AppServerError) else AppServerError(str(exc))
        finally:
            if failure is None:
                detail = "\n".join(self.stderr)
                failure = AppServerError(
                    "Codex App Server closed its output" + (f": {detail}" if detail else "")
                )
            for future in (*self.pending.values(), *self.turns.values()):
                if not future.done():
                    future.set_exception(failure)
            if not self.closed.done():
                self.closed.set_result(failure)

    async def reject_server_request(self, message):
        method = message["method"]
        if method in {
            "item/commandExecution/requestApproval",
            "item/fileChange/requestApproval",
        }:
            response = {"result": {"decision": "decline"}}
        elif method in {"execCommandApproval", "applyPatchApproval"}:
            response = {
                "result": {
                    "decision": {
                        "denied": {
                            "rejection": "Voice Shell does not auto-approve actions.",
                        }
                    }
                }
            }
        elif method == "item/permissions/requestApproval":
            response = {"result": {"permissions": {}}}
        elif method == "mcpServer/elicitation/request":
            response = {"result": {"action": "decline", "content": None}}
        else:
            response = {
                "error": {
                    "code": -32001,
                    "message": f"Voice Shell cannot answer server request: {method}",
                }
            }
        await self.send({"id": message["id"], **response})

    @staticmethod
    def finish_turn(future, turn):
        if turn.get("status") == "failed":
            error = turn.get("error") or {}
            future.set_exception(TurnError(
                f"Codex turn failed: {error.get('message', error or 'unknown error')}"
            ))
        else:
            future.set_result(turn)

    async def send(self, message):
        try:
            self.proc.stdin.write((json.dumps(message, ensure_ascii=False) + "\n").encode())
            await self.proc.stdin.drain()
        except (BrokenPipeError, ConnectionError, OSError) as exc:
            raise AppServerError("Codex App Server connection was lost") from exc

    async def request(self, method, params, timeout=30):
        self.request_id += 1
        request_id = self.request_id
        future = asyncio.get_running_loop().create_future()
        self.pending[request_id] = future
        try:
            await self.send({"method": method, "id": request_id, "params": params})
        except Exception:
            self.pending.pop(request_id, None)
            raise
        try:
            return await asyncio.wait_for(future, timeout)
        except asyncio.TimeoutError as exc:
            self.pending.pop(request_id, None)
            raise AppServerError(f"Timed out waiting for Codex App Server during {method}") from exc

    async def notify(self, method, params):
        await self.send({"method": method, "params": params})

    async def initialize(self, thread_id):
        await self.request("initialize", {
            "clientInfo": {
                "name": "voice_shell",
                "title": "Voice Shell",
                "version": "0.1.0",
            },
        })
        await self.notify("initialized", {})
        result = await self.request("thread/resume", {"threadId": thread_id})
        resumed = result.get("thread", {}).get("id")
        if resumed != thread_id:
            raise AppServerError("Codex App Server resumed a different thread")

    async def start_turn(self, thread_id, text):
        result = await self.request("turn/start", {
            "threadId": thread_id,
            "input": [{"type": "text", "text": text}],
        })
        turn = result.get("turn", {})
        turn_id = turn.get("id")
        if not turn_id:
            raise AppServerError("Codex App Server returned no turn id")
        if turn.get("status") in {"completed", "interrupted"}:
            return turn
        if turn.get("status") == "failed":
            error = turn.get("error") or {}
            raise TurnError(f"Codex turn failed: {error.get('message', error or 'unknown error')}")
        finished = self.finished_turns.pop(turn_id, None)
        if finished:
            future = asyncio.get_running_loop().create_future()
            self.finish_turn(future, finished)
            return await future
        future = asyncio.get_running_loop().create_future()
        self.turns[turn_id] = future
        try:
            return await future
        finally:
            self.turns.pop(turn_id, None)

    async def close(self):
        if not self.proc:
            return
        if self.proc.returncode is None:
            self.proc.terminate()
            try:
                await asyncio.wait_for(self.proc.wait(), 3)
            except asyncio.TimeoutError:
                self.proc.kill()
                await self.proc.wait()
        for task in (self.reader_task, self.stderr_task):
            if task:
                task.cancel()
        for task in (self.reader_task, self.stderr_task):
            if task:
                try:
                    await task
                except asyncio.CancelledError:
                    pass


def utterance_text(line, listener_pid, input_filtered):
    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(record, dict):
        return None
    target = record.get("to")
    if target is not None and not input_filtered:
        if not listener_pid or str(target) != listener_pid:
            return None
    text = record.get("text")
    if not isinstance(text, str):
        return None
    text = text.strip()
    return text or None


async def read_utterances(queue, listener_pid, input_filtered):
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    transport, _ = await loop.connect_read_pipe(lambda: protocol, sys.stdin)
    try:
        while line := await reader.readline():
            text = utterance_text(line.decode("utf-8", "replace"), listener_pid, input_filtered)
            if text:
                await queue.put(text)
    finally:
        transport.close()
        await queue.put(None)


async def forward(args):
    thread_id = os.environ.get("CODEX_THREAD_ID", "").strip()
    if not thread_id:
        raise AppServerError("CODEX_THREAD_ID is required for codex-forward")
    command = shlex.split(os.environ.get("CODEX_BIN", "codex"))
    if not command:
        raise AppServerError("CODEX_BIN is empty")
    server = AppServer(command + ["app-server"])
    queue = asyncio.Queue()
    input_task = None
    try:
        await server.start()
        await server.initialize(thread_id)
        input_task = asyncio.create_task(
            read_utterances(queue, args.listener_pid, args.input_filtered)
        )
        while True:
            next_text = asyncio.create_task(queue.get())
            done, _ = await asyncio.wait(
                (next_text, server.closed), return_when=asyncio.FIRST_COMPLETED
            )
            if server.closed in done:
                next_text.cancel()
                raise server.closed.result()
            text = next_text.result()
            if text is None:
                break
            try:
                await server.start_turn(thread_id, text)
            except TurnError as exc:
                print(f"codex-forward: {exc}", file=sys.stderr)
    finally:
        if input_task:
            input_task.cancel()
            try:
                await input_task
            except asyncio.CancelledError:
                pass
        await server.close()


def main():
    parser = argparse.ArgumentParser(description="Forward voice-shell JSONL to Codex App Server")
    parser.add_argument("--listener-pid", default="")
    parser.add_argument("--input-filtered", action="store_true")
    args = parser.parse_args()
    try:
        asyncio.run(forward(args))
    except (AppServerError, KeyboardInterrupt) as exc:
        if isinstance(exc, AppServerError):
            print(f"codex-forward: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
