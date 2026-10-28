#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
source "$ROOT/kit/env.sh"
mkdir -p "$ROOT/dist" "$FIREFOX_BUILD_ROOT/verification"
INPUT_APK=$(cat "$FIREFOX_BUILD_ROOT/unsigned-apk.path")
SDK="$ANDROID_HOME/cmdline-tools/23.0/bin/apkanalyzer"
TOOLS="$ANDROID_HOME/build-tools/37.0.0"
OUTPUT="$ROOT/dist/firefox-$FIREFOX_VERSION-arm64-ruca-UNSIGNED.apk"
"$TOOLS/zipalign" -P 16 -f 4 "$INPUT_APK" "$OUTPUT"
"$TOOLS/zipalign" -c -P 16 4 "$OUTPUT"
python3 "$ROOT/kit/scripts/verify_apk_manifest.py" "$OUTPUT" --apkanalyzer "$SDK" \
  --expected-version "$FIREFOX_VERSION" --expected-target-sdk 37 \
  --report "$FIREFOX_BUILD_ROOT/verification/manifest-check.json"
python3 "$ROOT/kit/scripts/inspect_apk_elf_alignment.py" "$OUTPUT" \
  --report "$FIREFOX_BUILD_ROOT/verification/elf-alignment.json"
"$FIREFOX_BUILD_ROOT/verify-venv/bin/python" "$ROOT/kit/scripts/verify_apk_certificates.py" \
  "$OUTPUT" --der-dir "$ROOT/kit/certs/der" \
  --report "$FIREFOX_BUILD_ROOT/verification/embedded-certificates.json"
"$SDK" manifest version-code "$OUTPUT" > "$FIREFOX_BUILD_ROOT/verification/version-code.txt"
python3 - <<'PY'
import os
from pathlib import Path
value=int(Path(os.environ['FIREFOX_BUILD_ROOT'],'verification/version-code.txt').read_text())
if value != int(os.environ['RUCA_VERSION_CODE']):
    raise ValueError('Wrong versionCode')
PY
cp "$FIREFOX_BUILD_ROOT/downloads.json" "$FIREFOX_BUILD_ROOT/verification/"
cp "$FIREFOX_BUILD_ROOT/logs"/generated-builtins-*.json "$FIREFOX_BUILD_ROOT/verification/"
cp "$FIREFOX_BUILD_ROOT/logs/source-certificates.json" "$FIREFOX_BUILD_ROOT/verification/"
tar -czf "$ROOT/dist/verification.tar.gz" -C "$FIREFOX_BUILD_ROOT" verification
printf '%s\n' 'UNSIGNED TRIAL: not installable; no release and no signing key used.' > "$ROOT/dist/UNSIGNED.txt"
(cd "$ROOT/dist" && sha256sum -- "$(basename "$OUTPUT")" > "$(basename "$OUTPUT").sha256")
