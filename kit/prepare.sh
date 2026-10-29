#!/usr/bin/env bash
set -euo pipefail
SCRIPT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
source "$SCRIPT_ROOT/env.sh"
[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]]
for command_name in python3 curl tar xz zstd patch make gcc g++ perl m4 nasm pkg-config node; do
    command -v "$command_name" >/dev/null
done
"$JAVA_HOME/bin/javac" -version 2>&1 | python3 -c 'import re,sys; value=sys.stdin.read(); print(value,end=""); assert re.search(r"javac 17[.]",value), "JDK 17 required"'
mkdir -p "$FIREFOX_BUILD_ROOT" "$MOZBUILD_STATE_PATH" "$GRADLE_USER_HOME" "$CARGO_HOME" "$RUSTUP_HOME" "$FIREFOX_BUILD_ROOT/logs"
python3 "$SCRIPT_ROOT/../ci/source_manifest.py"
python3 "$SCRIPT_ROOT/scripts/fetch-and-patch.py"
python3 "$SCRIPT_ROOT/scripts/install_branding.py" --source-root "$FIREFOX_SOURCE_DIR"
if [[ ! -x "$FIREFOX_BUILD_ROOT/verify-venv/bin/python" ]]; then
    python3 -m venv "$FIREFOX_BUILD_ROOT/verify-venv"
fi
"$FIREFOX_BUILD_ROOT/verify-venv/bin/python" -m pip install 'cryptography==50.0.2'
"$FIREFOX_BUILD_ROOT/verify-venv/bin/python" "$SCRIPT_ROOT/scripts/inject_certificates.py" \
    --cert-dir "$SCRIPT_ROOT/certs" --source-root "$FIREFOX_SOURCE_DIR" --apply \
    > "$FIREFOX_BUILD_ROOT/logs/source-certificates.json"
python3 "$SCRIPT_ROOT/../ci/versioning.py"
cp -- "$SCRIPT_ROOT/mozconfig" "$MOZCONFIG"
cd "$FIREFOX_SOURCE_DIR"
./mach python "$SCRIPT_ROOT/scripts/bootstrap-minimal.py"
if [[ ! -x "$MOZBUILD_STATE_PATH/cbindgen/bin/cbindgen" ]]; then
    cargo install cbindgen --version 0.29.4 --locked --jobs 2 --root "$MOZBUILD_STATE_PATH/cbindgen"
fi
"$MOZBUILD_STATE_PATH/cbindgen/bin/cbindgen" --version
./mach configure > "$FIREFOX_BUILD_ROOT/logs/configure.log" 2>&1
printf '%s\n' 'Preparation and configure completed. Next: ./build.sh'
