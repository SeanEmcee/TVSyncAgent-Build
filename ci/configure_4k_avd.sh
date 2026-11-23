#!/usr/bin/env bash
# Executed after AVD creation but BEFORE emulator launch.
# Real guest LCD dimensions are set here, not merely overridden with 'wm size'.
set -euo pipefail

avd_home="$(printenv ANDROID_AVD_HOME || printf '%s/.android/avd' "$HOME")"
config="$avd_home/tvsync4k.avd/config.ini"
if [[ ! -s "$config" ]]; then
  echo "::error::4K AVD config missing: $config"
  exit 1
fi

# Strip inherited 1080p size and skin before writing authoritative 4K values.
sed -i -e '/^hw\.lcd\.width=/d' -e '/^hw\.lcd\.height=/d' \
  -e '/^hw\.lcd\.density=/d' -e '/^skin\.name=/d' \
  -e '/^skin\.path=/d' -e '/^showDeviceFrame=/d' \
  -e '/^hw\.initialOrientation=/d' "$config"
cat >> "$config" <<'AVD_DISPLAY'
hw.lcd.width=3840
hw.lcd.height=2160
hw.lcd.density=320
skin.name=3840x2160
skin.path=_no_skin
showDeviceFrame=no
hw.initialOrientation=landscape
AVD_DISPLAY

grep -qx 'hw.lcd.width=3840' "$config"
grep -qx 'hw.lcd.height=2160' "$config"
grep -qx 'skin.name=3840x2160' "$config"
echo "Native 3840x2160 TV framebuffer configured before emulator boot."
grep -E '^(hw.lcd.(width|height|density)|skin.name|skin.path)=' "$config"
