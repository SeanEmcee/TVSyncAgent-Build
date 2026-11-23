#!/usr/bin/env python3
"""Smoke-check the browser server without launching any emulator or tunnel."""
import asyncio
from pathlib import Path
from aiohttp.test_utils import TestClient, TestServer
from remote_server import make_app

async def check():
    here=Path(__file__).resolve().parent
    async with TestClient(TestServer(make_app(here/"missing-novnc",here/"live-emulator.html"))) as c:
        response=await c.get("/health")
        assert response.status==200 and (await response.json())["ready"]
        response=await c.get("/")
        assert response.status==200 and b"TV Sync" in await response.read()
        for req in (
            {"key":"bash"},
            {"key":"up","hold":True},
            {"key":"ok","hold":"yes"},
            {"key":"../../etc/passwd"},
            [1,2,3]
        ):
            response=await c.post("/api/key",json=req)
            assert response.status==400,(req,response.status)
        response=await c.get("/websockify")
        assert response.status in (400,503), response.status
    # Embedded endpoint is a separate process: no OTP login page inside the iframe,
    # but both the remote-control API and VNC feed require a secret query token.
    async with TestClient(TestServer(make_app(here/"missing-novnc",here/"live-emulator.html",session_token="test-session-secret"))) as c:
        response=await c.get("/health")
        assert response.status==200
        response=await c.post("/api/key",json={"key":"ok"})
        assert response.status==401
        response=await c.get("/websockify")
        assert response.status==401
        response=await c.post("/api/key?session=wrong",json={"key":"ok"})
        assert response.status==401
        response=await c.post("/api/key?session=test-session-secret",json={"key":"unsupported"})
        assert response.status==400
        # HTTP fallback must confirm processing through the persistent bridge.
        class FakeInput:
            async def send(self,code,hold=False):
                assert code==22 and hold is False
                future=asyncio.get_running_loop().create_future()
                future.set_result(12.3)
                return future
        c.server.app["input"]=FakeInput()
        response=await c.post("/api/key?session=test-session-secret",
                              json={"key":"right","hold":False})
        assert response.status==200,(response.status,await response.text())
        body=await response.json()
        assert body["ok"] is True and body["device_ms"]==12.3
        # The WebSocket path avoids HTTP round-trip serialization for each key.
        channel=await c.ws_connect("/remote-ws?session=test-session-secret")
        await channel.send_json({"id":1,"key":"right","hold":False})
        first=await channel.receive_json()
        second=await channel.receive_json()
        assert first=={"id":1,"queued":True},first
        assert second["delivered"] is True and second["device_ms"]==12.3,second
        await channel.close()
        response=await c.get("/")
        assert response.status==200
        assert response.headers.get("Referrer-Policy")=="no-referrer"
        assert response.headers.get("Cache-Control")=="no-store"
    print("PASS: authentication, fixed-key HTTP fallback and low-overhead WebSocket remote protocol")

asyncio.run(check())
