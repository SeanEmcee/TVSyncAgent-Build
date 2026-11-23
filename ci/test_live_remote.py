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
    print("Live emulator server: health, page and input-denylist checks passed.")

asyncio.run(check())
