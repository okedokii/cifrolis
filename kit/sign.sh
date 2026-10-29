#!/usr/bin/env bash
set -euo pipefail
umask 077
SCRIPT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
source "$SCRIPT_ROOT/env.sh"
INPUT_APK=$(realpath -- "${1:?Supply the unsigned ARM64 release APK}")
CERTIFICATE_PYTHON="$FIREFOX_BUILD_ROOT/verify-venv/bin/python"
test -x "$CERTIFICATE_PYTHON"
OUTPUT_APK=${2:-"$FIREFOX_BUILD_ROOT/cifrolis-${FIREFOX_VERSION}-arm64.apk"}
SIGNING_DIR="${FIREFOX_SIGNING_DIR:-$FIREFOX_BUILD_ROOT/signing}"
VERIFY_DIR="$FIREFOX_BUILD_ROOT/verification"
BUILD_TOOLS="$ANDROID_HOME/build-tools/37.0.0"
APK_ANALYZER="$ANDROID_HOME/cmdline-tools/23.0/bin/apkanalyzer"
KEYSTORE="$SIGNING_DIR/firefox-ruca.p12"
PASSWORD_FILE="$SIGNING_DIR/keystore-password.txt"
ALIGNED_APK="$FIREFOX_BUILD_ROOT/cifrolis-${FIREFOX_VERSION}-arm64-aligned.apk"

mkdir -p "$SIGNING_DIR" "$VERIFY_DIR" "$(dirname -- "$OUTPUT_APK")"
test -x "$BUILD_TOOLS/apksigner"
test -x "$BUILD_TOOLS/zipalign"
test -x "$APK_ANALYZER"
"$APK_ANALYZER" manifest print "$INPUT_APK" > "$VERIFY_DIR/AndroidManifest.xml"
python3 - "$INPUT_APK" "$VERIFY_DIR/AndroidManifest.xml" <<'PY'
import struct
import sys
import xml.etree.ElementTree as ET
import zipfile

ns = "{http://schemas.android.com/apk/res/android}"
root = ET.parse(sys.argv[2]).getroot()
assert root.attrib["package"] == "io.github.okedokii.cifrolis", root.attrib
assert ns + "sharedUserId" not in root.attrib, "A private APK must not inherit Mozilla's shared UID"
app = root.find("application")
assert app is not None
assert app.get(ns + "debuggable", "false") == "false", "APK is debuggable"
with zipfile.ZipFile(sys.argv[1]) as apk:
    libraries = [n for n in apk.namelist() if n.startswith("lib/") and n.endswith(".so")]
    assert libraries and "lib/arm64-v8a/libxul.so" in libraries
    assert {n.split("/")[1] for n in libraries} == {"arm64-v8a"}, libraries
    for name in libraries:
        with apk.open(name) as stream:
            header = stream.read(20)
        assert header[:6] == b"\x7fELF\x02\x01", name
        assert struct.unpack_from("<H", header, 18)[0] == 183, name
print(f"Private release manifest and {len(libraries)} ARM64 ELF libraries verified.")
PY

test -s "$KEYSTORE"
test -s "$PASSWORD_FILE"

"$BUILD_TOOLS/zipalign" -P 16 -f -v 4 "$INPUT_APK" "$ALIGNED_APK" > "$VERIFY_DIR/zipalign-signing.log"
"$BUILD_TOOLS/apksigner" sign --ks "$KEYSTORE" --ks-key-alias firefox-ruca \
    --ks-pass "file:$PASSWORD_FILE" \
    --min-sdk-version 26 --v2-signing-enabled true --v3-signing-enabled true \
    --v4-signing-enabled false --out "$OUTPUT_APK" "$ALIGNED_APK"
"$BUILD_TOOLS/apksigner" verify --verbose --print-certs "$OUTPUT_APK" > "$VERIFY_DIR/apksigner.log"
"$BUILD_TOOLS/zipalign" -c -P 16 -v 4 "$OUTPUT_APK" > "$VERIFY_DIR/zipalign-verification.log"
python3 "$SCRIPT_ROOT/scripts/verify_apk_manifest.py" "$OUTPUT_APK" \
    --apkanalyzer "$APK_ANALYZER" --expected-version "$FIREFOX_VERSION" \
    --expected-target-sdk 37 \
    --report "$VERIFY_DIR/manifest-check.json" > "$VERIFY_DIR/manifest-check.log"
python3 "$SCRIPT_ROOT/scripts/inspect_apk_elf_alignment.py" "$OUTPUT_APK" \
    --report "$VERIFY_DIR/elf-alignment-16k.json" > "$VERIFY_DIR/elf-alignment-16k.log"
"$APK_ANALYZER" apk summary "$OUTPUT_APK" > "$VERIFY_DIR/apk-summary.txt"
"$APK_ANALYZER" manifest debuggable "$OUTPUT_APK" > "$VERIFY_DIR/debuggable.txt"
"$APK_ANALYZER" manifest min-sdk "$OUTPUT_APK" > "$VERIFY_DIR/min-sdk.txt"
"$APK_ANALYZER" manifest target-sdk "$OUTPUT_APK" > "$VERIFY_DIR/target-sdk.txt"
keytool -exportcert -rfc -alias firefox-ruca -keystore "$KEYSTORE" \
    -storepass:file "$PASSWORD_FILE" > "$SIGNING_DIR/signer-certificate.pem"
"$CERTIFICATE_PYTHON" "$SCRIPT_ROOT/scripts/verify_apk_certificates.py" "$OUTPUT_APK" \
    --der-dir "$SCRIPT_ROOT/certs/der" --report "$VERIFY_DIR/embedded-certificates.json" \
    > "$VERIFY_DIR/embedded-certificates.log"
(
    cd -- "$(dirname -- "$OUTPUT_APK")"
    sha256sum -- "$(basename -- "$OUTPUT_APK")"
) > "$OUTPUT_APK.sha256"
chmod 644 "$OUTPUT_APK" "$OUTPUT_APK.sha256"
cat "$VERIFY_DIR/apksigner.log" "$VERIFY_DIR/apk-summary.txt" "$OUTPUT_APK.sha256"
