#!/usr/bin/env bash
# Fullscreen read-only mirror of the Android display (not emulator window).
set -euo pipefail
: "${RUNNER_TEMP:?RUNNER_TEMP must be set}"
: "${DISPLAY:=:99}"
archive="$RUNNER_TEMP/scrcpy-linux-x86_64-v5.0.1.tar.gz"
extract_root="$RUNNER_TEMP/tvsync-scrcpy"
binary="$extract_root/scrcpy-linux-x86_64-v5.0.1/scrcpy"
sha256="9f969d30cc574816077edecda65719c1c70b0aee1df1ba5fa00779ac07b8fd6e"

if [[ ! -x "$binary" ]]; then
  curl --fail --show-error --silent --location --retry 3 \
    --output "$archive" \
    "https://github.com/Genymobile/scrcpy/releases/download/v5.0.1/scrcpy-linux-x86_64-v5.0.1.tar.gz"
  printf '%s  %s\n' "$sha256" "$archive" | sha256sum --check --status
  mkdir -p "$extract_root"
  tar -xzf "$archive" -C "$extract_root"
  test -x "$binary"
fi

adb -s emulator-5554 get-state | grep -qx device
dimensions="$(adb -s emulator-5554 shell wm size | tr -d '\r')"
printf 'Android display dimensions: %s\n' "$dimensions"
if ! printf '%s' "$dimensions" | grep -q 'Physical size: 3840x2160'; then
  echo "::error::Android must render at native 3840x2160 (4K), got: $dimensions"
  exit 1
fi
# Root cause of the failed 4K runs: the inherited tv_1080p Android profile
# retains a WindowManager override even after the AVD's physical LCD is 4K.
# Clear that stale override, without changing the physical display or lying
# to the screenshot check. Android must then report the hardware size only.
if printf '%s' "$dimensions" | grep -q 'Override size:'; then
  echo "Resetting inherited WindowManager resolution override to native 4K."
  adb -s emulator-5554 shell wm size reset
  dimensions="$(adb -s emulator-5554 shell wm size | tr -d '\r')"
  printf 'Effective Android display: %s\n' "$dimensions"
fi
if ! printf '%s' "$dimensions" | grep -qx 'Physical size: 3840x2160'; then
  echo "::error::4K hardware still has an active display-size override: $dimensions"
  exit 1
fi
# Confirm the Android framebuffer actually has 4K dimensions. An 'wm size'
# override alone is not reliable proof of 4K rendering.
adb -s emulator-5554 exec-out screencap -p > "$RUNNER_TEMP/tvsync-4k-check.png"
python3 - "$RUNNER_TEMP/tvsync-4k-check.png" <<'PY'
import struct,sys
with open(sys.argv[1],"rb") as f:
    header=f.read(24)
if header[:8]!=b"\x89PNG\r\n\x1a\n" or header[12:16]!=b"IHDR":
    raise SystemExit("Invalid Android screenshot; cannot verify 4K")
width,height=struct.unpack(">II",header[16:24])
if (width,height)!=(3840,2160):
    raise SystemExit(f"Expected native 3840x2160 screenshot, got {width}x{height}")
print(f"Native Android screenshot confirmed: {width}x{height}")
PY

nohup "$binary" --serial emulator-5554 \
  --no-control --no-audio --fullscreen --window-borderless --always-on-top \
  --window-title="TV Sync Mirror" --background-color=000000 \
  --max-size=1920 --max-fps=30 --video-bit-rate=3M --video-buffer=0 \
  > "$RUNNER_TEMP/tvsync-scrcpy.log" 2>&1 </dev/null &
mirror_pid=$!
echo "$mirror_pid" > "$RUNNER_TEMP/tvsync-scrcpy.pid"

matched=""
geo=""
for i in $(seq 1 50); do
  if ! kill -0 "$mirror_pid" 2>/dev/null; then
    echo "::error::Android fullscreen mirror exited unexpectedly."
    tail -25 "$RUNNER_TEMP/tvsync-scrcpy.log" || true
    exit 1
  fi
  matched="$(xdotool search --onlyvisible --name '^TV Sync Mirror$' 2>/dev/null | head -1 || true)"
  if [[ -n "$matched" ]]; then
    geo="$(xdotool getwindowgeometry --shell "$matched" 2>/dev/null || true)"
    width="$(printf '%s\n' "$geo" | sed -n 's/^WIDTH=//p')"
    height="$(printf '%s\n' "$geo" | sed -n 's/^HEIGHT=//p')"
    if [[ "${width:-0}" -ge 1850 && "${height:-0}" -ge 1020 ]]; then
      echo "4K Android framebuffer, low-latency 1080p browser preview: ${width}x${height}."
      exit 0
    fi
  fi
  sleep 1
done
echo "::error::4K Android downscaled mirror did not fill the low-latency 1080p virtual display."
echo "Window geometry: ${geo:-not found}"
tail -25 "$RUNNER_TEMP/tvsync-scrcpy.log" || true
exit 1
