#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
SDK_ROOT="${ANDROID_SDK_ROOT:-/usr/local/lib/android/sdk}"
SDKMANAGER="$SDK_ROOT/cmdline-tools/latest/bin/sdkmanager"
test -x "$SDKMANAGER"
# sdkmanager handles the official package metadata and downloads.
# GitHub-hosted images already accept the Android SDK licenses.
"$SDKMANAGER" --sdk_root="$SDK_ROOT" 'build-tools;37.0.0'
source "$ROOT/kit/env.sh"
mkdir -p "$ANDROID_HOME/cmdline-tools" "$ANDROID_HOME/build-tools"
ln -s "$SDK_ROOT/cmdline-tools/latest" "$ANDROID_HOME/cmdline-tools/23.0"
ln -s "$SDK_ROOT/build-tools/37.0.0" "$ANDROID_HOME/build-tools/37.0.0"
python3 -m venv "$FIREFOX_BUILD_ROOT/verify-venv"
"$FIREFOX_BUILD_ROOT/verify-venv/bin/python" -m pip install cryptography==50.0.2
