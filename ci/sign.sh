#!/usr/bin/env bash
set -euo pipefail
umask 077
ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
source "$ROOT/kit/env.sh"
export FIREFOX_SIGNING_DIR="$RUNNER_TEMP/ruca-signing"
trap 'rm -rf -- "$FIREFOX_SIGNING_DIR"' EXIT
mkdir -p "$FIREFOX_SIGNING_DIR" "$ROOT/dist"
python3 - <<'PY'
import base64,os
from pathlib import Path
p=Path(os.environ['FIREFOX_SIGNING_DIR'])
p.joinpath('firefox-ruca.p12').write_bytes(base64.b64decode(os.environ['RUCA_KEYSTORE_B64'],validate=True))
password=os.environ['RUCA_KEYSTORE_PASSWORD']
if not password or '\n' in password or '\r' in password:
    raise ValueError('Password must be a nonempty single line')
p.joinpath('keystore-password.txt').write_text(password+'\n')
PY
# Check the pinned new signing identity before signing. Never generate keys inside CI.
keytool -exportcert -alias firefox-ruca -keystore "$FIREFOX_SIGNING_DIR/firefox-ruca.p12" \
  -storepass:file "$FIREFOX_SIGNING_DIR/keystore-password.txt" \
  -file "$FIREFOX_SIGNING_DIR/public.der"
python3 - <<'PY'
import hashlib,os,json
from pathlib import Path
value=hashlib.sha256(Path(os.environ['FIREFOX_SIGNING_DIR'],'public.der').read_bytes()).hexdigest()
expected=json.loads(Path(os.environ['FIREFOX_KIT_ROOT'],'../ci/signing-identity.json').read_text())['signer_sha256']
if value != expected:
    raise ValueError('Signing certificate differs from ci/signing-identity.json')
print('Pinned signing identity confirmed')
PY
if [[ "${1:-}" == --check-key ]]; then
  exit 0
fi
OUTPUT="$ROOT/dist/firefox-$FIREFOX_VERSION-arm64-ruca.apk"
bash "$ROOT/kit/sign.sh" "$(cat "$FIREFOX_BUILD_ROOT/unsigned-apk.path")" "$OUTPUT"
"$ANDROID_HOME/cmdline-tools/23.0/bin/apkanalyzer" manifest version-code "$OUTPUT" > "$FIREFOX_BUILD_ROOT/verification/version-code.txt"
python3 - <<'PY'
import os
from pathlib import Path
actual=int(Path(os.environ['FIREFOX_BUILD_ROOT'],'verification/version-code.txt').read_text())
if actual != int(os.environ['RUCA_VERSION_CODE']):
    raise ValueError(f'Unexpected versionCode {actual}')
PY
cp "$FIREFOX_BUILD_ROOT/downloads.json" "$FIREFOX_BUILD_ROOT/verification/"
if [[ -f "$FIREFOX_BUILD_ROOT/SHA512SUMS" ]]; then
  cp "$FIREFOX_BUILD_ROOT/SHA512SUMS" "$FIREFOX_BUILD_ROOT/verification/"
fi
cp "$FIREFOX_BUILD_ROOT/logs"/generated-builtins-*.json "$FIREFOX_BUILD_ROOT/verification/"
cp "$FIREFOX_BUILD_ROOT/logs/source-certificates.json" "$FIREFOX_BUILD_ROOT/verification/"
tar -czf "$ROOT/dist/verification.tar.gz" -C "$FIREFOX_BUILD_ROOT" verification
