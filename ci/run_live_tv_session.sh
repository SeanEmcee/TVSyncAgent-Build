#!/usr/bin/env bash
# Disposable, interactive TV emulator test session; no physical device network.
set -euo pipefail
test -s apk/app-debug.apk

adb wait-for-device
adb shell wm size 1920x1080
adb shell wm density 240
adb install -r apk/app-debug.apk
adb shell appops set dev.tvsync.agent MANAGE_EXTERNAL_STORAGE allow || true
adb shell 'mkdir -p /sdcard/Download /sdcard/Movies /sdcard/Music /sdcard/Pictures'
adb shell 'touch /sdcard/demo.mp4 /sdcard/sample.txt /sdcard/sample-picture.jpg'
adb shell am start -W -n dev.tvsync.agent/.MainActivity

# The public link only appears AFTER email protection is requested.
# cloudflared refuses to create a public tunnel when --allowed-mail protection fails.
: "${TVSYNC_EMULATOR_EMAIL:?Protected emulator email secret is missing}"
cloud_log="$RUNNER_TEMP/tvsync-cloudflared.log"
cloudflared tunnel --url http://127.0.0.1:6080 \
  --allowed-mail "$TVSYNC_EMULATOR_EMAIL" --output json \
  >"$cloud_log" 2>&1 &
cloud_pid=$!

url=""
for i in $(seq 1 50); do
  if ! kill -0 "$cloud_pid" 2>/dev/null; then
    echo "::error::Protected Cloudflare Quick Tunnel failed to start."
    sed -E 's/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+/[redacted-email]/g' "$cloud_log" | tail -25
    exit 1
  fi
  url="$(grep -Eo 'https://[a-z0-9-]+[.]trycloudflare[.]com' "$cloud_log" | head -1 || true)"
  if [[ -n "$url" ]]; then break; fi
  sleep 2
done
if [[ -z "$url" ]]; then
  echo "::error::Protected tunnel did not produce an HTTPS URL."
  kill "$cloud_pid" || true
  exit 1
fi

echo "::notice title=TV Sync Live Emulator::$url"
echo "LIVE TV SYNC EMULATOR: $url"
echo "Access: OTP restricted to the email saved in TVSYNC_EMULATOR_EMAIL."
echo "NO physical Chromecast connection, no private source code in public runner."
{
  echo "## TV Sync — live interactive emulator"
  echo ""
  echo "[Open protected TV Sync emulator]($url)"
  echo ""
  echo "Authentication: one-time PIN sent to your approved email. Session is temporary."
  echo "GitHub Actions run: $GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID"
} >> "$GITHUB_STEP_SUMMARY"

# Update a stable public status document. The emulator itself still requires email OTP.
update_status() {
  local message="$1" body="$2" sha
  local payload
  payload="$(printf '%s' "$body" | base64 -w0)"
  sha="$(gh api "repos/$GITHUB_REPOSITORY/contents/LIVE_EMULATOR.md" --jq '.sha' 2>/dev/null || true)"
  if [[ -n "$sha" ]]; then
    gh api --method PUT "repos/$GITHUB_REPOSITORY/contents/LIVE_EMULATOR.md" \
      -f message="$message" -f content="$payload" -f sha="$sha" >/dev/null || true
  else
    gh api --method PUT "repos/$GITHUB_REPOSITORY/contents/LIVE_EMULATOR.md" \
      -f message="$message" -f content="$payload" >/dev/null || true
  fi
}
update_status "Mark TV Sync live emulator online" \
  "# TV Sync live emulator\n\n[**Open your protected interactive emulator**]($url)\n\nThis temporary Google TV instance is protected by an email one-time code.\n\n[Live build and logs]($GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID)\n"
cleanup() {
  update_status "Mark TV Sync emulator session offline" \
    "# TV Sync live emulator\n\n**Offline** — no active session confirmed.\n\nStart a new run from [TV Sync Live Emulator Actions](https://github.com/SeanEmcee/TVSyncAgent-Build/actions/workflows/live-emulator.yml).\n"
  kill "$cloud_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Keep this job tied to a bounded UI-testing session (not a general-purpose server).
# Workflows have a separate 120 minute hard job timeout.
echo "Interactive emulator session running; it will shut down automatically."
sleep 5400
