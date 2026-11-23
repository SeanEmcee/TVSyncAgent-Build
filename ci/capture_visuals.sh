#!/usr/bin/env bash
# Disposable Android TV emulator only. Does not connect to any physical device.
set -euo pipefail
mkdir -p report
test -s apk/app-debug.apk

adb wait-for-device
adb shell wm size 1672x941
adb shell wm density 240
adb install -r apk/app-debug.apk

# Only in the disposable emulator: allow browsing synthetic shared-storage fixtures.
adb shell appops set dev.tvsync.agent MANAGE_EXTERNAL_STORAGE allow
adb shell 'mkdir -p /sdcard/Alarms /sdcard/Android /sdcard/Movies /sdcard/Music /sdcard/Notifications /sdcard/Pictures /sdcard/Download'
adb shell 'touch /sdcard/demo.mp4 /sdcard/screenshot.png /sdcard/apps_backup.zip'
adb shell am force-stop dev.tvsync.agent || true
adb shell am start -W -n dev.tvsync.agent/.MainActivity
sleep 3

adb exec-out screencap -p > report/actual-browser.png

# D-pad long press on a focused file. Capture both positions to verify overlay geometry.
adb shell input keyevent --longpress 23 || true
sleep 1
adb exec-out screencap -p > report/actual-popup-left.png
adb shell input keyevent 4 || true
for i in 1 2 3 4 5; do adb shell input keyevent 22 || true; done
adb shell input keyevent --longpress 23 || true
sleep 1
adb exec-out screencap -p > report/actual-popup-right.png

adb shell dumpsys gfxinfo dev.tvsync.agent > report/gfxinfo.txt || true
adb shell dumpsys meminfo dev.tvsync.agent > report/meminfo.txt || true
adb shell getprop ro.build.version.release > report/android-version.txt || true
adb shell getprop ro.product.model > report/emulator-model.txt || true
echo "Captured actual screenshots from a disposable Android TV emulator."
