#!/usr/bin/env bash
set -euo pipefail
SCRIPT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
source "$SCRIPT_ROOT/env.sh"
LOG_DIR="$FIREFOX_BUILD_ROOT/logs"
mkdir -p "$LOG_DIR"
cd "$FIREFOX_SOURCE_DIR"
printf 'Compiling Gecko and GeckoView. Log: %s\n' "$LOG_DIR/native-build.log"
# Force top-level make targets: without -C ., "tools" resolves to the tools directory.
./mach build -C . pre-export export compile misc libs android-stage-package tools \
    > "$LOG_DIR/native-build.log" 2>&1
python3 "$SCRIPT_ROOT/../ci/verify_generated.py"
printf 'Assembling Fenix release. Log: %s\n' "$LOG_DIR/fenix-release.log"
./mach gradle fenix:assembleRelease -PdisableOptimization -PdisableDebugSigning \
    > "$LOG_DIR/fenix-release.log" 2>&1
python3 - "$FIREFOX_BUILD_ROOT" <<'PY'
from pathlib import Path
import shlex
import sys
work = Path(sys.argv[1])
folder = work / 'obj-arm64/gradle/build/mobile/android/fenix/app/outputs/apk/release'
apks = sorted(folder.rglob('*.apk'))
if len(apks) != 1:
    raise SystemExit(f'Expected one release APK under {folder}, found: {apks}')
(work / 'unsigned-apk.path').write_text(str(apks[0].resolve()) + '\n')
print(f'Unsigned ARM64 release APK: {apks[0]}')
print(f'Next: ./sign.sh {shlex.quote(str(apks[0].resolve()))}')
PY
