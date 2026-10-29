import os
import certifi
import subprocess
from pathlib import Path

from mozboot import android, rust
from mozboot.util import MINIMUM_RUST_VERSION, http_download_and_save
from proxy_settings import java_proxy_properties

if os.environ.get("SSL_CERT_FILE"):
    certifi.where = lambda: os.environ["SSL_CERT_FILE"]


state = Path(os.environ["MOZBUILD_STATE_PATH"])
gradle_home = Path(os.environ["GRADLE_USER_HOME"])
cargo_home = Path(os.environ["CARGO_HOME"])
assert android.NDK_VERSION == "r30"
assert android.CMDLINE_TOOLS_VERSION == "16111833"
assert MINIMUM_RUST_VERSION == "1.90.0"
assert rust.RUSTUP_VERSION == "1.29.0"

gradle_home.mkdir(parents=True, exist_ok=True)
properties = gradle_home / "gradle.properties"
values = {}
if properties.exists():
    for line in properties.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
values.update({
    "org.gradle.jvmargs": "-Xmx5g -Xms256m -XX:MaxMetaspaceSize=1g -XX:+UseParallelGC",
    "org.gradle.workers.max": "2",
    "org.gradle.parallel": "false",
    "org.gradle.tooling.parallel": "false",
    "org.gradle.daemon": "false",
    "kotlin.compiler.execution.strategy": "in-process",
})
properties.write_text("".join(f"{key}={value}\n" for key, value in values.items()))

rustup_bin = cargo_home / "bin" / "rustup"
if not rustup_bin.exists():
    platform = "x86_64-unknown-linux-gnu"
    rustup_init = state / "rustup-init-1.29.0"
    http_download_and_save(rust.rustup_url(platform), rustup_init, rust.rustup_hash(platform))
    rustup_init.chmod(0o700)
    subprocess.run([
        str(rustup_init), "-y", "--no-modify-path", "--profile", "minimal",
        "--default-toolchain", "none",
    ], check=True)
    rustup_init.unlink()
subprocess.run([
    str(rustup_bin), "toolchain", "install", MINIMUM_RUST_VERSION,
    "--profile", "minimal", "--target", "aarch64-linux-android",
], check=True)

java_bin = Path(os.environ["JAVA_HOME"]) / "bin"
subprocess.run([str(java_bin / "javac"), "-version"], check=True)
android.ensure_gradle_jdk_installations(java_bin.parent, gradle_props=properties)
android.ensure_android_ndk("linux")
android.ensure_android_sdk("linux", android.get_os_tag_for_android("linux", "x86_64"))
android.ensure_bundletool()
packages = android.get_android_packages(android.AndroidPackageList.ALL) - {"emulator"}
assert packages == {"platform-tools", "build-tools;37.0.0", "platforms;android-37.2"}
android.ensure_android_packages(
    "linux", "x86_64", packages=packages, avd_manifest=None, no_interactive=True,
)
proxy_values = {"systemProp." + key: value for key, value in java_proxy_properties().items()}
proxy_keys = {key.lower() for key in proxy_values}
values = {}
for line in properties.read_text().splitlines():
    if "=" in line and not line.lstrip().startswith("#"):
        key, value = line.split("=", 1)
        if key.strip().lower() not in proxy_keys:
            values[key.strip()] = value.strip()
values.update(proxy_values)
properties.write_text("".join(f"{key} = {value}\n" for key, value in values.items()))
print("Minimal Android/Rust bootstrap complete. No emulator or system image installed.")
print("Clang and WASI are installed separately from hash-pinned Mozilla archives.")
