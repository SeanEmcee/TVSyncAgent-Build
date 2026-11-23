#!/usr/bin/env python3
"""Measure real X11->VNC->Chromium update delay independent of Android rendering.

Changes an isolated test overlay only; never modifies device, accounts, or apps.
Browser checks use canvas pixels, not remote-input acknowledgments.
"""
import json
import os
import pathlib
import statistics
import tempfile
import time

from Xlib import X, display
from playwright.sync_api import sync_playwright

OUT = pathlib.Path("smoke-report")
OUT.mkdir(exist_ok=True)
URL = os.environ.get("TVSYNC_PROBE_URL", "http://127.0.0.1:6080/")
DISPLAY = os.environ.get("DISPLAY", ":99")
AUTH = pathlib.Path(tempfile.gettempdir()) / "tvsync-test-Xauthority"
AUTH.touch(exist_ok=True)
os.environ.setdefault("XAUTHORITY", str(AUTH))

def has_color(rgb, wanted):
    if rgb is None:
        return False
    r, g, b = rgb
    return (r > 160 and g < 100 and b < 100) if wanted == "red" else (
        b > 160 and r < 100 and g < 100)

def canvas_rgb(page):
    return page.evaluate("""() => {
      const canvas = document.querySelector('#screen canvas');
      if (!canvas || canvas.width < 10 || canvas.height < 10) return null;
      const {width, height} = canvas;
      const pixel = canvas.getContext('2d').getImageData(
        Math.floor(width / 2), Math.floor(height / 2), 1, 1).data;
      return [pixel[0], pixel[1], pixel[2]];
    }""")

def await_pixel(page, wanted, timeout=8):
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        if has_color(canvas_rgb(page), wanted):
            return round((time.monotonic() - start) * 1000, 1)
        time.sleep(.04)
    return None

d = display.Display(DISPLAY)
screen = d.screen()
colormap = screen.default_colormap
red = colormap.alloc_named_color("red").pixel
blue = colormap.alloc_named_color("blue").pixel
# Center of the 16:9 Xvfb stage and noVNC canvas.
width, height = 240, 180
left = max(0, (screen.width_in_pixels-width)//2)
top = max(0, (screen.height_in_pixels-height)//2)
overlay = screen.root.create_window(
    left, top, width, height, 0, screen.root_depth,
    X.InputOutput, X.CopyFromParent,
    background_pixel=blue, override_redirect=1)
measurements = []
try:
    overlay.map()
    overlay.configure(stack_mode=X.Above)
    d.sync()
    with sync_playwright() as play:
        browser = play.chromium.launch(
            channel="chrome", headless=True,
            args=["--no-sandbox","--disable-dev-shm-usage"])
        page = browser.new_page(viewport={"width":1280,"height":780})
        page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        page.locator("#status").get_by_text("Connected", exact=False).wait_for(timeout=30000)
        first = await_pixel(page, "blue", timeout=12)
        print("PIPELINE initial blue ms:", first, flush=True)
        if first is None:
            raise RuntimeError("VNC did not display direct-X11 overlay within 12s")
        for i in range(8):
            wanted = "red" if i % 2 == 0 else "blue"
            overlay.change_attributes(background_pixel=red if wanted=="red" else blue)
            overlay.clear_area(0, 0, width, height, False)
            d.flush()
            delay = await_pixel(page, wanted, timeout=5)
            measurements.append(delay)
            print(f"PIPELINE X11-to-Chromium {i} {wanted}: {delay}ms", flush=True)
        browser.close()
finally:
    overlay.destroy()
    d.flush()
    d.close()
results = {"x11_to_browser_ms":measurements, "missing_frames":sum(v is None for v in measurements)}
numeric = [v for v in measurements if v is not None]
if numeric:
    results.update(median_ms=statistics.median(numeric), maximum_ms=max(numeric))
(OUT/"x11-to-browser-metrics.json").write_text(json.dumps(results,indent=2))
print("PIPELINE_METRICS",json.dumps(results),flush=True)
if results["missing_frames"]:
    raise RuntimeError("VNC failed to deliver one or more changed frames within 5s")
# A delayed first wakeup is a failure even if later updates are quick.
if numeric and max(numeric) > 600:
    raise RuntimeError("X11-to-browser update exceeded 600ms after idle: " + str(results))
