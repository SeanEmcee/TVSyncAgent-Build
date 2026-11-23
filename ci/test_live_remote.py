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
        response=await c.get("/")
        assert response.status==200
        assert response.headers.get("Referrer-Policy")=="no-referrer"
        assert response.headers.get("Cache-Control")=="no-store"
    print("Live emulator server: health, page, input safety, and embedded token-gate tests passed.")

asyncio.run(check())
