#!/usr/bin/env bash
# Local-only GUI smoke test for public CI. No tunnel, no secrets, no physical devices.
set -euo pipefail
test -s apk/app-debug.apk
adb wait-for-device
# AVD hardware must already be 4K. Do not hide a 1080p physical
# framebuffer behind a late WindowManager resolution override.
adb -s emulator-5554 shell wm size
adb -s emulator-5554 shell wm density
adb install -r apk/app-debug.apk
adb shell appops set dev.tvsync.agent MANAGE_EXTERNAL_STORAGE allow || true
adb shell 'mkdir -p /sdcard/Download /sdcard/Pictures'
adb shell 'touch /sdcard/sample.txt /sdcard/demo.mp4'
adb shell am start -W -n dev.tvsync.agent/.MainActivity
bash ci/start_tv_mirror.sh
sleep 2
python3 - <<'PY'
import socket
with socket.create_connection(('127.0.0.1',5900),timeout=6) as conn:
    banner=conn.recv(12)
    if not banner.startswith(b'RFB '):
        raise SystemExit('VNC socket not serving RFB: '+repr(banner))
    print('Virtual-screen VNC handshake:',repr(banner))
PY
curl --fail --silent http://127.0.0.1:6080/health
echo
curl --fail --silent -H 'Content-Type: application/json' \
  -d '{"key":"down","hold":false}' http://127.0.0.1:6080/api/key
echo
mkdir -p smoke-report
python3 -m pip install --quiet playwright
python3 ci/test_live_browser.py
echo 'Scrcpy recorded throughput (requires active screen changes):'
grep -Ei '(fps|frames)' "$RUNNER_TEMP/tvsync-scrcpy.log" | tail -15 || true
adb -s emulator-5554 exec-out screencap -p > smoke-report/tvsync-gui-smoke-4k.png
cp "$RUNNER_TEMP/tvsync-4k-check.png" smoke-report/native-4k-framebuffer.png
test -s smoke-report/tvsync-gui-smoke-4k.png
adb shell pidof dev.tvsync.agent
echo 'Android TV GUI, VNC, and D-pad smoke tests passed.'
