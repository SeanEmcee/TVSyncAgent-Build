#!/usr/bin/env bash
# Temporary chat-embed compatibility test for user's own disposable TV emulator.
# Only VNC and allowlisted TV remote keys are exposed, behind a 256-bit bearer token.
# Token is never written to the public repo, logs, or workflow summary.
set -euo pipefail
: "${TVSYNC_PRIVATE_SOURCE_TOKEN:?Private repository write token is required}"
test -s apk/app-debug.apk
private_path="repos/SeanEmcee/TVSyncAgent/contents/PRIVATE_EMULATOR_EMBED.md"
embed_token="$(openssl rand -hex 32)"
server_pid=""
tunnel_pid=""
published=false
cleanup() {
  if [[ "$published" == true ]]; then
    sha="$(GH_TOKEN="$TVSYNC_PRIVATE_SOURCE_TOKEN" gh api "$private_path" --jq '.sha' 2>/dev/null || true)"
    if [[ -n "$sha" ]]; then
      content="$(printf '# TV Sync chat embed\n\n**Offline.** The temporary test session has ended.\n' | base64 -w0)"
      GH_TOKEN="$TVSYNC_PRIVATE_SOURCE_TOKEN" gh api --method PUT "$private_path" \
        -f message="Expire temporary chat-embed test" \
        -f content="$content" -f sha="$sha" >/dev/null 2>&1 || true
    fi
  fi
  if [[ -n "$tunnel_pid" ]]; then kill "$tunnel_pid" 2>/dev/null || true; fi
  if [[ -n "$server_pid" ]]; then kill "$server_pid" 2>/dev/null || true; fi
}
trap cleanup EXIT INT TERM

adb wait-for-device
# AVD hardware must already be 4K. Do not hide a 1080p physical
# framebuffer behind a late WindowManager resolution override.
adb -s emulator-5554 shell wm size
adb -s emulator-5554 shell wm density
adb install -r apk/app-debug.apk
adb shell appops set dev.tvsync.agent MANAGE_EXTERNAL_STORAGE allow || true
adb shell 'mkdir -p /sdcard/Download /sdcard/Movies /sdcard/Pictures'
adb shell 'touch /sdcard/demo.mp4 /sdcard/test-file.txt /sdcard/sample-picture.jpg'
adb shell am start -W -n dev.tvsync.agent/.MainActivity
bash ci/start_tv_mirror.sh

TVSYNC_EMBED_TOKEN="$embed_token" nohup python3 ci/remote_server.py --port 6081 \
  > "$RUNNER_TEMP/embed-server.log" 2>&1 </dev/null &
server_pid=$!
for i in $(seq 1 30); do
  if curl --silent --fail http://127.0.0.1:6081/health > /dev/null; then break; fi
  sleep 1
done
curl --silent --fail http://127.0.0.1:6081/health > /dev/null
unauthorized="$(curl --silent --output /dev/null --write-out '%{http_code}' \
  -H 'Content-Type: application/json' --data '{"key":"ok"}' \
  http://127.0.0.1:6081/api/key)"
authorized_reject="$(curl --silent --output /dev/null --write-out '%{http_code}' \
  -H 'Content-Type: application/json' --data '{"key":"not-allowed"}' \
  "http://127.0.0.1:6081/api/key?session=$embed_token")"
[[ "$unauthorized" == "401" && "$authorized_reject" == "400" ]] || {
  echo "::error::Emulator bearer-token access checks failed, no public tunnel created."
  exit 1
}
# Crucial end-to-end test: an authenticated D-pad request MUST succeed on the
# running Android emulator before we publish a live browser link.
auth_button="$(curl --fail --silent --show-error --max-time 12 \
  -H 'Content-Type: application/json' --data '{"key":"down","hold":false}' \
  "http://127.0.0.1:6081/api/key?session=$embed_token")" || {
  echo "::error::Authenticated Android TV D-pad request failed. No tunnel published."
  exit 1
}
if ! printf '%s' "$auth_button" | grep -q '"ok": true'; then
  echo "::error::Authenticated Android TV command was not accepted."
  exit 1
fi
echo "Authenticated D-pad command accepted by the running Android emulator."

cloudflared tunnel --url http://127.0.0.1:6081 --output json \
  > "$RUNNER_TEMP/embed-tunnel.log" 2>&1 &
tunnel_pid=$!
base=""
for i in $(seq 1 50); do
  if ! kill -0 "$tunnel_pid" 2>/dev/null; then break; fi
  base="$(grep -Eo 'https://[a-z0-9-]+[.]trycloudflare[.]com' "$RUNNER_TEMP/embed-tunnel.log" | head -1 || true)"
  [[ -n "$base" ]] && break
  sleep 2
done
if [[ -z "$base" ]]; then
  echo "::error::Private embed Quick Tunnel did not initialize."
  exit 1
fi

# Link is a temporary credential: store ONLY inside the user's PRIVATE repo.
private_url="$base/?session=$embed_token"
body="# TV Sync — Private Chat Embed\n\n[Open the temporary chat-compatible emulator]($private_url)\n\n**Confidential link:** It grants access to this disposable Android TV emulator until the test session ends. Do not share it. This session has no personal TV files or account credentials.\n\n[Build run]($GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID)\n"
payload="$(printf '%b' "$body" | base64 -w0)"
sha="$(GH_TOKEN="$TVSYNC_PRIVATE_SOURCE_TOKEN" gh api "$private_path" --jq '.sha' 2>/dev/null || true)"
if [[ -n "$sha" ]]; then
  GH_TOKEN="$TVSYNC_PRIVATE_SOURCE_TOKEN" gh api --method PUT "$private_path" \
    -f message="Publish short-lived private emulator embed test" \
    -f content="$payload" -f sha="$sha" > /dev/null
else
  GH_TOKEN="$TVSYNC_PRIVATE_SOURCE_TOKEN" gh api --method PUT "$private_path" \
    -f message="Publish short-lived private emulator embed test" \
    -f content="$payload" > /dev/null
fi
published=true
echo "::notice title=Private Chat Embed::Live protected link saved to PRIVATE TVSyncAgent/PRIVATE_EMULATOR_EMBED.md."
echo "No link or token has been written to public logs or artifacts."
echo "This temporary UI test uses only synthetic data. It does not connect to physical Chromecasts."
sleep 2400
