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
from fast_tv_input import FastInput, InputBusy, InputUnavailable

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

def parse_key(data):
    if not isinstance(data, dict):
        raise web.HTTPBadRequest(text="Invalid request")
    key=data.get("key")
    hold=data.get("hold",False)
    if key not in KEYS or type(hold) is not bool or (hold and key!="ok"):
        raise web.HTTPBadRequest(text="Unsupported TV remote action")
    return key,hold


async def remote_key(request):
    """HTTP fallback for diagnostics and clients without WebSockets."""
    check_session(request)
    try:
        data=await request.json()
    except (ValueError, json.JSONDecodeError):
        raise web.HTTPBadRequest(text="Invalid JSON")
    key,hold=parse_key(data)
    try:
        future=await request.app["input"].send(KEYS[key],hold)
        # Unlike a fast queued send, the diagnostic HTTP endpoint confirms
        # that Android processed the key before reporting success.
        delay=await asyncio.wait_for(asyncio.shield(future),timeout=4.0)
        return web.json_response({"ok":True,"key":key,"hold":hold,"device_ms":delay})
    except InputBusy:
        return web.json_response({"ok":False,"error":"input_queue_full"},status=429)
    except (InputUnavailable, asyncio.TimeoutError):
        return web.json_response({"ok":False,"error":"android_input_stalled"},status=503)


async def remote_ws(request):
    """Independent low-overhead, ordered D-pad channel; never exposes ADB shell."""
    check_session(request)
    ws=web.WebSocketResponse(heartbeat=20,max_msg_size=256)
    await ws.prepare(request)
    pending=set()

    async def acknowledge(future,identifier):
        try:
            delay=await asyncio.wait_for(asyncio.shield(future),timeout=4.0)
            if not ws.closed:
                await ws.send_json({"id":identifier,"delivered":True,"device_ms":delay})
        except (InputUnavailable, asyncio.TimeoutError, asyncio.CancelledError):
            if not ws.closed:
                await ws.send_json({"id":identifier,"error":"android_input_stalled"})

    try:
        async for msg in ws:
            if msg.type != WSMsgType.TEXT:
                continue
            try:
                data=json.loads(msg.data)
                key,hold=parse_key(data)
                identifier=data.get("id")
                if type(identifier) is not int or identifier<0 or identifier>2147483647:
                    raise ValueError("Invalid remote input ID")
                future=await request.app["input"].send(KEYS[key],hold)
                await ws.send_json({"id":identifier,"queued":True})
                task=asyncio.create_task(acknowledge(future,identifier))
                pending.add(task)
                task.add_done_callback(pending.discard)
            except (ValueError, web.HTTPBadRequest):
                await ws.send_json({"error":"invalid_remote_command"})
            except InputBusy:
                await ws.send_json({"error":"input_queue_full"})
            except InputUnavailable:
                await ws.send_json({"error":"android_input_stalled"})
    finally:
        for task in pending:
            task.cancel()
    return ws

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
    app["input"] = FastInput(serial="emulator-5554")
    app["index_file"]=index_file
    app.router.add_get("/",index)
    app.router.add_get("/health",health)
    app.router.add_post("/api/key",remote_key)
    app.router.add_get("/remote-ws",remote_ws)
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
