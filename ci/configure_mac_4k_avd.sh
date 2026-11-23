#!/usr/bin/env bash
set -euo pipefail
avd_home="${ANDROID_AVD_HOME:-$HOME/.android/avd}"
config="$avd_home/tvsync4k.avd/config.ini"
test -s "$config" || { echo "::error::Missing $config"; exit 1; }
python3 - "$config" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]); lines=p.read_text().splitlines()
keys={'hw.lcd.width','hw.lcd.height','hw.lcd.density','skin.name','skin.path','showDeviceFrame','hw.initialOrientation'}
lines=[line for line in lines if line.split('=',1)[0].strip() not in keys]
lines += ['hw.lcd.width=3840','hw.lcd.height=2160','hw.lcd.density=640', 'skin.name=3840x2160','skin.path=_no_skin', 'showDeviceFrame=no','hw.initialOrientation=landscape']
p.write_text('\n'.join(lines)+'\n')
PY
for expected in 'hw.lcd.width=3840' 'hw.lcd.height=2160' 'hw.lcd.density=640'; do grep -qx "$expected" "$config"; done
echo 'PASS: 4K Android TV AVD configured before boot.'
