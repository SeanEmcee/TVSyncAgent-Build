#!/usr/bin/env python3
"""Low-latency, ordered Android TV key input over ONE persistent ADB shell.

Only callers holding the allowlisted remote can pass integer Android key codes.
This module never exposes an arbitrary shell or device address to the network.
"""
import asyncio
import time


class InputUnavailable(Exception):
    pass


class InputBusy(Exception):
    pass


class FastInput:
    def __init__(self, serial="emulator-5554", max_pending=24):
        self.serial = serial
        self.max_pending = max_pending
        self._proc = None
        self._read_task = None
        self._lock = asyncio.Lock()
        self._pending = {}
        self._sequence = 0
        self.last_confirmed = 0.0
        self.last_delay_ms = None

    @property
    def queued(self):
        return len(self._pending)

    async def _start_locked(self):
        if self._proc is not None and self._proc.returncode is None:
            return
        self._proc = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                "adb", "-s", self.serial, "shell", "-T", "sh",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            ),
            timeout=4.0,
        )
        self._read_task = asyncio.create_task(self._read_acks(self._proc))

    async def _read_acks(self, proc):
        try:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                marker = line.strip()
                if not marker.startswith(b"TVSYNC_ACK_"):
                    continue
                try:
                    seq = int(marker[len(b"TVSYNC_ACK_"):])
                except ValueError:
                    continue
                item = self._pending.pop(seq, None)
                if item is None:
                    continue
                future, sent_at = item
                self.last_confirmed = time.monotonic()
                self.last_delay_ms = round((self.last_confirmed - sent_at) * 1000, 1)
                if not future.done():
                    future.set_result(self.last_delay_ms)
        except (asyncio.CancelledError, OSError):
            pass
        finally:
            for seq, (future, _) in list(self._pending.items()):
                if not future.done():
                    future.set_exception(InputUnavailable("ADB shell disconnected"))
                self._pending.pop(seq, None)

    async def send(self, key_code: int, hold: bool = False):
        if type(key_code) is not int or key_code < 1 or key_code > 300:
            raise ValueError("Key code must be an allowlisted integer")
        if type(hold) is not bool:
            raise ValueError("Invalid long-press argument")
        async with self._lock:
            if len(self._pending) >= self.max_pending:
                raise InputBusy("Android remote queue is full")
            if self._pending:
                oldest = min(item[1] for item in self._pending.values())
                if time.monotonic() - oldest > 7.0:
                    # A stalled emulator should never accumulate unbounded
                    # commands that get replayed after the app finally unfreezes.
                    await self._reset_locked()
                    raise InputUnavailable("Android stopped acknowledging inputs")
            try:
                await self._start_locked()
                self._sequence += 1
                seq = self._sequence
                future = asyncio.get_running_loop().create_future()
                self._pending[seq] = (future, time.monotonic())
                command = "input keyevent {}{}\nprintf 'TVSYNC_ACK_{}\\n'\n".format(
                    "--longpress " if hold else "", key_code, seq
                )
                self._proc.stdin.write(command.encode("ascii"))
                await asyncio.wait_for(self._proc.stdin.drain(), timeout=0.8)
                return future
            except (OSError, BrokenPipeError, asyncio.TimeoutError) as exc:
                await self._reset_locked()
                raise InputUnavailable("Android remote shell is unavailable") from exc

    async def _reset_locked(self):
        proc = self._proc
        self._proc = None
        if proc and proc.returncode is None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
        task = self._read_task
        self._read_task = None
        if task:
            task.cancel()
        for seq, (future, _) in list(self._pending.items()):
            if not future.done():
                future.set_exception(InputUnavailable("Remote shell reset"))
            self._pending.pop(seq, None)

    async def close(self):
        async with self._lock:
            await self._reset_locked()
