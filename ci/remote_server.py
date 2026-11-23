#!/usr/bin/env python3
"""Loopback-only noVNC + fixed D-pad commands for disposable Android TV testing.
All external access MUST go through cloudflared tunnel --allowed-mail.
"""
import argparse
import asyncio
import json
import hmac
import os
from pathlib import Path
from aiohttp import WSMsgType, web

KEYS = {"up":19,"down":20,"left":21,"right":22,"ok":23,"back":4,
        "home":3,"menu":82,"playpause":85}

def check_session(request):
    """Protect controls/screens with a per-run 256-bit bearer token for embedding.
    The ordinary email-verified viewer uses a separate, non-token server instance.
    """
    expected = request.app["session_token"]
    if expected and not hmac.compare_digest(request.query.get("session", ""), expected):
        raise web.HTTPUnauthorized(text="Private emulator session token required")

@web.middleware
async def security_headers(request, handler):
    response = await handler(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response

async def health(request):
    return web.json_response({"ready": True, "service": "tv-sync-live-emulator"})

async def index(request):
    return web.FileResponse(request.app["index_file"])

async def remote_key(request):
    check_session(request)
    try:
        data=await request.json()
    except (ValueError,json.JSONDecodeError):
        raise web.HTTPBadRequest(text="Invalid JSON")
    if not isinstance(data,dict):
        raise web.HTTPBadRequest(text="Invalid request")
    key=data.get("key")
    hold=data.get("hold",False)
    if key not in KEYS or type(hold) is not bool or (hold and key!="ok"):
        raise web.HTTPBadRequest(text="Unsupported TV remote action")
    # Target ONLY the disposable emulator, never an unrelated ADB device.
    # Serialize key events to preserve D-pad order across browser requests.
    command=["adb","-s","emulator-5554","shell","input","keyevent"]
    if hold: command.append("--longpress")
    command.append(str(KEYS[key]))
    async with request.app["remote_lock"]:
        for attempt in range(2):
            try:
                proc=await asyncio.create_subprocess_exec(
                    *command,stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE)
                try:
                    stdout,stderr=await asyncio.wait_for(proc.communicate(),timeout=8)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
                    return web.json_response(
                        {"ok":False,"error":"adb_timeout","retryable":True},status=503)
            except OSError:
                return web.json_response(
                    {"ok":False,"error":"adb_not_found","retryable":False},status=503)
            if proc.returncode == 0:
                return web.json_response({"ok":True,"key":key,"hold":hold})
            detail=stderr.decode("utf-8","replace")[:180].strip()
            print("TV Sync emulator input failed (code {}): {}".format(proc.returncode,detail),
                  flush=True)
            if attempt == 0 and ("offline" in detail.lower() or "not found" in detail.lower()
                                or "no devices" in detail.lower()):
                await asyncio.sleep(.2)
                continue
            return web.json_response(
                {"ok":False,"error":"adb_command_failed","retryable":True},status=503)
    return web.json_response({"ok":False,"error":"adb_unavailable"},status=503)

async def vnc_socket(request):
    """Bridge WebSocket RFB bytes only to localhost VNC, no general TCP proxy."""
    check_session(request)
    try:
        reader,writer=await asyncio.wait_for(
            asyncio.open_connection("127.0.0.1",5900),timeout=5)
    except (OSError,asyncio.TimeoutError):
        raise web.HTTPServiceUnavailable(text="VNC display unavailable")
    ws=web.WebSocketResponse(heartbeat=30,max_msg_size=32*1024*1024)
    await ws.prepare(request)
    async def from_browser():
        async for msg in ws:
            if msg.type == WSMsgType.BINARY:
                writer.write(msg.data)
                await writer.drain()
            elif msg.type == WSMsgType.TEXT:
                writer.write(msg.data.encode("latin-1"))
                await writer.drain()
            elif msg.type in (WSMsgType.CLOSE,WSMsgType.ERROR):
                break
    async def to_browser():
        while not reader.at_eof():
            chunk=await reader.read(65536)
            if not chunk:break
            await ws.send_bytes(chunk)
    tasks=[asyncio.create_task(from_browser()),asyncio.create_task(to_browser())]
    try:
        _,pending=await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
        for task in pending:task.cancel()
        await asyncio.gather(*pending,return_exceptions=True)
    finally:
        writer.close()
        await writer.wait_closed()
        await ws.close()
    return ws

def make_app(novnc_root:Path,index_file:Path,session_token=""):
    app=web.Application(client_max_size=4096,middlewares=[security_headers])
    app["session_token"] = session_token
    app["remote_lock"] = asyncio.Lock()
    app["index_file"]=index_file
    app.router.add_get("/",index)
    app.router.add_get("/health",health)
    app.router.add_post("/api/key",remote_key)
    app.router.add_get("/websockify",vnc_socket)
    for folder in ("core","vendor","app"):
        path=novnc_root/folder
        if path.is_dir():
            app.router.add_static("/"+folder+"/",str(path),show_index=False)
    return app

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--port",type=int,default=6080)
    p.add_argument("--no-vnc",default="/usr/share/novnc")
    p.add_argument("--session-token",default=os.getenv("TVSYNC_EMBED_TOKEN", ""))
    args=p.parse_args()
    app=make_app(Path(args.no_vnc),Path(__file__).with_name("live-emulator.html"),args.session_token)
    web.run_app(app,host="127.0.0.1",port=args.port,access_log=None)

if __name__ == "__main__":
    main()
