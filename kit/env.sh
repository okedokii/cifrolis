#!/usr/bin/env bash
FIREFOX_KIT_ROOT=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
export FIREFOX_KIT_ROOT
export FIREFOX_BUILD_ROOT="${FIREFOX_BUILD_ROOT:-$FIREFOX_KIT_ROOT/work}"
export FIREFOX_VERSION="${FIREFOX_VERSION:?Set FIREFOX_VERSION}"
export FIREFOX_SOURCE_DIR="$FIREFOX_BUILD_ROOT/firefox-$FIREFOX_VERSION"
export MOZBUILD_STATE_PATH="$FIREFOX_BUILD_ROOT/state"
export GRADLE_USER_HOME="$FIREFOX_BUILD_ROOT/gradle-home"
export CARGO_HOME="$FIREFOX_BUILD_ROOT/cargo-home"
export RUSTUP_HOME="$FIREFOX_BUILD_ROOT/rustup-home"
export RUSTUP_TOOLCHAIN=1.90.0
export PIP_CACHE_DIR="$FIREFOX_BUILD_ROOT/pip-cache"
export XDG_CACHE_HOME="$FIREFOX_BUILD_ROOT/cache"
export MOZCONFIG="$FIREFOX_SOURCE_DIR/mozconfig"
export ANDROID_HOME="$MOZBUILD_STATE_PATH/android-sdk-linux"
export ANDROID_NDK_HOME="$MOZBUILD_STATE_PATH/android-ndk-r30"
export ANDROID_AVD_HOME="$MOZBUILD_STATE_PATH/android-device/avd"
export CARGO_INCREMENTAL=0
export MOZ_DISABLE_TELEMETRY=1

if [[ -z "${JAVA_HOME:-}" ]]; then
    if command -v javac >/dev/null 2>&1; then
        JAVA_HOME=$(dirname -- "$(dirname -- "$(readlink -f -- "$(command -v javac)")")")
    else
        printf '%s\n' 'JDK 17 is required. Install a JDK or set JAVA_HOME.' >&2
        return 1
    fi
fi
export JAVA_HOME
if [[ ! -x "$JAVA_HOME/bin/javac" ]]; then
    printf '%s\n' 'JAVA_HOME must point to a JDK with javac, not just a JRE.' >&2
    return 1
fi

if [[ -n "${FIREFOX_CA_BUNDLE:-}" ]]; then
    export SSL_CERT_FILE="$FIREFOX_CA_BUNDLE"
elif [[ -r /etc/ssl/certs/ca-certificates.crt ]]; then
    export SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
fi
if [[ -n "${SSL_CERT_FILE:-}" ]]; then
    export REQUESTS_CA_BUNDLE="$SSL_CERT_FILE"
    export CURL_CA_BUNDLE="$SSL_CERT_FILE"
    export CARGO_HTTP_CAINFO="$SSL_CERT_FILE"
fi
if [[ -n "${FIREFOX_JAVA_TRUSTSTORE:-}" ]]; then
    export JAVA_TOOL_OPTIONS="${JAVA_TOOL_OPTIONS:-} -Djavax.net.ssl.trustStore=$FIREFOX_JAVA_TRUSTSTORE"
elif [[ -r /etc/ssl/certs/java/cacerts && "${JAVA_TOOL_OPTIONS:-}" != *javax.net.ssl.trustStore=* ]]; then
    export JAVA_TOOL_OPTIONS="${JAVA_TOOL_OPTIONS:-} -Djavax.net.ssl.trustStore=/etc/ssl/certs/java/cacerts"
fi
JAVA_TOOL_OPTIONS=$(python3 "$FIREFOX_KIT_ROOT/scripts/proxy_settings.py")
export JAVA_TOOL_OPTIONS
export PATH="$CARGO_HOME/bin:$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$PATH"
