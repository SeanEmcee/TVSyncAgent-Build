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
if ! printf '%s' "$dimensions" | grep -q '1920x1080'; then
  echo "::error::Android TV was not configured at 1920x1080."
  exit 1
fi

nohup "$binary" --serial emulator-5554 \
  --no-control --no-audio --fullscreen --window-borderless --always-on-top \
  --window-title="TV Sync Mirror" --background-color=000000 \
  --max-size=1920 --max-fps=60 --video-bit-rate=6M \
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
      echo "TV Sync Android mirror fills the desktop: ${width}x${height}."
      exit 0
    fi
  fi
  sleep 1
done
echo "::error::Android mirror did not fill the virtual 1920x1080 TV display."
echo "Window geometry: ${geo:-not found}"
tail -25 "$RUNNER_TEMP/tvsync-scrcpy.log" || true
exit 1
