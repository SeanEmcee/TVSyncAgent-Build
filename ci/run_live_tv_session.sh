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
  payload="$(printf '%b' "$body" | base64 -w0)"
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
# Optional private-link embed for clients that cannot frame Cloudflare's
# email-login page. This is a separate tunnel with independent strong bearer
# authentication, not an unauthenticated port to the TV.
embed_cloud_pid=""
embed_server_pid=""
embed_private_published=false
if [[ -n "${TVSYNC_PRIVATE_SOURCE_TOKEN:-}" ]]; then
  embed_token="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
  TVSYNC_EMBED_TOKEN="$embed_token" nohup python3 ci/remote_server.py --port 6081 \
    >"$RUNNER_TEMP/tvsync-embed-server.log" 2>&1 </dev/null &
  embed_server_pid=$!
  for i in $(seq 1 20); do
    if curl --silent --fail http://127.0.0.1:6081/health >/dev/null; then break; fi
    sleep 1
  done
  # Any attempt to invoke the emulator without the per-run token must fail.
  unauth_code="$(curl --silent --output /dev/null --write-out '%{http_code}' \
    -H 'Content-Type: application/json' --data '{"key":"ok"}' \
    http://127.0.0.1:6081/api/key || true)"
  if [[ "$unauth_code" == "401" ]]; then
    embed_log="$RUNNER_TEMP/tvsync-embed-cloudflared.log"
    cloudflared tunnel --url http://127.0.0.1:6081 --output json \
      >"$embed_log" 2>&1 &
    embed_cloud_pid=$!
    embed_base=""
    for i in $(seq 1 45); do
      if ! kill -0 "$embed_cloud_pid" 2>/dev/null; then break; fi
      embed_base="$(grep -Eo 'https://[a-z0-9-]+[.]trycloudflare[.]com' "$embed_log" | head -1 || true)"
      if [[ -n "$embed_base" ]]; then break; fi
      sleep 2
    done
    if [[ -n "$embed_base" ]]; then
      # Never print this URL or token to the public build log/repository.
      embed_url="$embed_base/?session=$embed_token"
      embed_body="# TV Sync — Private Chat Embed\n\n[Open the temporary secure embedded emulator]($embed_url)\n\nThis is a **bearer access link** for an isolated synthetic-data test emulator. Anyone with the link can control this temporary instance. Do not share it. It expires when the session ends. The standard Cloudflare email-protected link remains available separately.\n\n[Session run]($GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID)\n"
      embed_payload="$(printf '%b' "$embed_body" | base64 -w0)"
      private_path="repos/SeanEmcee/TVSyncAgent/contents/PRIVATE_EMULATOR_EMBED.md"
      previous_sha="$(GH_TOKEN="$TVSYNC_PRIVATE_SOURCE_TOKEN" gh api "$private_path" --jq '.sha' 2>/dev/null || true)"
      if [[ -n "$previous_sha" ]]; then
        if GH_TOKEN="$TVSYNC_PRIVATE_SOURCE_TOKEN" gh api --method PUT "$private_path" \
            -f message="Publish temporary private emulator embed session" \
            -f content="$embed_payload" -f sha="$previous_sha" >/dev/null 2>&1; then
          embed_private_published=true
        fi
      else
        if GH_TOKEN="$TVSYNC_PRIVATE_SOURCE_TOKEN" gh api --method PUT "$private_path" \
            -f message="Publish temporary private emulator embed session" \
            -f content="$embed_payload" >/dev/null 2>&1; then
          embed_private_published=true
        fi
      fi
    fi
  else
    echo "::warning::Private embed gate refused unauthenticated test incorrectly; embed tunnel disabled."
  fi
  if [[ "$embed_private_published" == true ]]; then
    echo "::notice title=TV Sync Secure Chat Embed::The short-lived embed link is in the PRIVATE TVSyncAgent repository's PRIVATE_EMULATOR_EMBED.md file."
  else
    echo "::warning::Private embed unavailable; the existing email-verified live viewer remains protected."
    if [[ -n "$embed_cloud_pid" ]]; then kill "$embed_cloud_pid" 2>/dev/null || true; fi
    if [[ -n "$embed_server_pid" ]]; then kill "$embed_server_pid" 2>/dev/null || true; fi
  fi
else
  echo "::warning::TVSYNC_PRIVATE_SOURCE_TOKEN not configured; email-protected viewer runs normally, private embed disabled."
fi

cleanup() {
  if [[ "$embed_private_published" == true ]]; then
    private_path="repos/SeanEmcee/TVSyncAgent/contents/PRIVATE_EMULATOR_EMBED.md"
    previous_sha="$(GH_TOKEN="$TVSYNC_PRIVATE_SOURCE_TOKEN" gh api "$private_path" --jq '.sha' 2>/dev/null || true)"
    offline_payload="$(printf '# TV Sync private embed\n\n**Offline.** Launch a new session from the public GitHub workflow.\n' | base64 -w0)"
    if [[ -n "$previous_sha" ]]; then
      GH_TOKEN="$TVSYNC_PRIVATE_SOURCE_TOKEN" gh api --method PUT "$private_path" \
        -f message="Expire private emulator embed link" \
        -f content="$offline_payload" -f sha="$previous_sha" >/dev/null 2>&1 || true
    fi
  fi
  if [[ -n "$embed_cloud_pid" ]]; then kill "$embed_cloud_pid" 2>/dev/null || true; fi
  if [[ -n "$embed_server_pid" ]]; then kill "$embed_server_pid" 2>/dev/null || true; fi
  update_status "Mark TV Sync emulator session offline" \
    "# TV Sync live emulator\n\n**Offline** — no active session confirmed.\n\nStart a new run from [TV Sync Live Emulator Actions](https://github.com/SeanEmcee/TVSyncAgent-Build/actions/workflows/live-emulator.yml).\n"
  kill "$cloud_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Keep this job tied to a bounded UI-testing session (not a general-purpose server).
# Workflows have a separate 120 minute hard job timeout.
echo "Interactive emulator session running; it will shut down automatically."
sleep 5400
