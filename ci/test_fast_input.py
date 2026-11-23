#!/usr/bin/env python3
"""Test the fast remote shell without ADB or a real Android device."""
import asyncio
from unittest.mock import patch
from fast_tv_input import FastInput, InputBusy


class Reader:
    def __init__(self):
        self.queue = asyncio.Queue()
    async def readline(self):
        return await self.queue.get()


class Writer:
    def __init__(self, reader, ack=True):
        self.reader = reader
        self.ack = ack
        self.data = []
    def write(self, blob):
        command = blob.decode("ascii")
        self.data.append(command)
        if self.ack:
            marker = command.split("TVSYNC_ACK_")[1].split("\\n")[0]
            asyncio.get_running_loop().call_later(
                .005, self.reader.queue.put_nowait,
                ("TVSYNC_ACK_" + marker + "\n").encode("ascii")
            )
    async def drain(self): pass


class FakeProcess:
    def __init__(self, ack=True):
        self.stdout = Reader()
        self.stdin = Writer(self.stdout, ack)
        self.returncode = None
    def kill(self):
        self.returncode = -9
        self.stdout.queue.put_nowait(b"")


async def test():
    procs = []
    async def mock_adb(*args, **kwargs):
        assert args[:5] == ("adb", "-s", "emulator-5554", "shell", "-T"), args
        assert args[5] == "sh"
        proc = FakeProcess()
        procs.append(proc)
        return proc

    bridge = FastInput()
    with patch("fast_tv_input.asyncio.create_subprocess_exec", side_effect=mock_adb):
        ack_futures = []
        for key in [19,20,21,22,23,4]:
            ack_futures.append(await bridge.send(key))
        results = await asyncio.wait_for(asyncio.gather(*ack_futures), timeout=2)
        assert len(results) == 6
        assert len(procs) == 1, "Keys must share ONE persistent ADB shell"
        assert len(procs[0].stdin.data) == 6
        assert "input keyevent 19" in procs[0].stdin.data[0]
        assert "input keyevent 20" in procs[0].stdin.data[1]
        assert bridge.queued == 0
        assert all(t >= 0 for t in results)
        assert "TVSYNC_ACK_" in procs[0].stdin.data[0]
        try:
            await bridge.send(999)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid key codes must be blocked")
        await bridge.close()

    blocked = FastInput(max_pending=1)
    async def stall_adb(*args, **kwargs):
        return FakeProcess(ack=False)
    with patch("fast_tv_input.asyncio.create_subprocess_exec", side_effect=stall_adb):
        fut = await blocked.send(19)
        try:
            await blocked.send(20)
        except InputBusy:
            pass
        else:
            raise AssertionError("Backpressure must reject unbounded remote queues")
        await blocked.close()
        try:
            await fut
        except Exception:
            pass
    print("PASS: persistent ADB input, ordered keys, device acks, bounded backlog, safe key codes")

asyncio.run(test())
