#!/usr/bin/env python3
"""Read and verify the manifest in the final Firefox ARM64 APK, without changing it.

Example:
  python verify_apk_manifest.py browser.apk --apkanalyzer /sdk/bin/apkanalyzer \
      --report verification/manifest-check.json

Run this on the final signed APK. The manifest is decoded from that same APK
using the Android SDK apkanalyzer; a separate XML file is never assumed to match.
This tool does not verify APK signatures, ELF alignment, or runtime behavior.
"""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile


ANDROID = "{http://schemas.android.com/apk/res/android}"


def verify(args):
    apk_path = args.apk.resolve()
    with apk_path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    with zipfile.ZipFile(apk_path) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        duplicates = sorted(name for name, count in Counter(names).items() if count > 1)
        if duplicates:
            raise ValueError("APK contains duplicate ZIP entries: " + ", ".join(duplicates))
        if names.count("AndroidManifest.xml") != 1:
            raise ValueError("APK must contain exactly one AndroidManifest.xml")
        libraries = [info for info in infos if info.filename.startswith("lib/") and info.filename.endswith(".so")]
        compressed_native = [info.filename for info in libraries if info.compress_type != zipfile.ZIP_STORED]
    analyzer = args.apkanalyzer or shutil.which("apkanalyzer")
    if not analyzer:
        raise ValueError("Pass --apkanalyzer with the Android SDK apkanalyzer executable")
    command = [str(analyzer), "manifest", "print", str(apk_path)]
    decoded = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
    if decoded.returncode != 0:
        raise ValueError("apkanalyzer manifest print failed: " + decoded.stderr.strip()[:2000])
    root = ET.fromstring(decoded.stdout)
    if root.tag != "manifest":
        raise ValueError("apkanalyzer did not return a manifest XML document")
    applications = root.findall("application")
    if len(applications) != 1:
        raise ValueError("Expected exactly one application element")
    app = applications[0]
    errors = []

    def require(condition, message):
        if not condition:
            errors.append(message)

    def boolean(element, name, default=None):
        value = element.get(ANDROID + name)
        if value is None:
            return default
        if value not in ("true", "false"):
            errors.append(f"Unresolved or invalid boolean {name} on {element.tag}: {value}")
            return None
        return value == "true"

    package = root.get("package")
    version = root.get(ANDROID + "versionName")
    version_code_text = root.get(ANDROID + "versionCode", "")
    require(package == args.expected_package, f"Unexpected package: {package}")
    require(version == args.expected_version, f"Unexpected versionName: {version}")
    require(version_code_text.isdecimal() and int(version_code_text) > 0,
            f"Invalid versionCode: {version_code_text}")
    require(ANDROID + "sharedUserId" not in root.attrib, "Private build declares sharedUserId")
    require(not root.get("split"), "APK is a split, not a standalone application")
    require(not root.findall("uses-split"), "APK declares required split dependencies")
    require(not root.findall("instrumentation"), "Release APK contains instrumentation")

    debuggable = boolean(app, "debuggable", False)
    test_only = boolean(app, "testOnly", False)
    enabled = boolean(app, "enabled", True)
    split_required = boolean(app, "isSplitRequired", False)
    extract_native = boolean(app, "extractNativeLibs", None)
    require(debuggable is False, "Application is debuggable")
    require(test_only is False, "Application is testOnly")
    require(enabled is True, "Application is disabled")
    require(split_required is False, "Application requires split APKs")
    require(not (extract_native is False and compressed_native),
            "extractNativeLibs=false conflicts with compressed native libraries")

    sdk_nodes = root.findall("uses-sdk")
    require(len(sdk_nodes) == 1, "Expected exactly one uses-sdk element")
    sdk = sdk_nodes[0] if sdk_nodes else ET.Element("uses-sdk")
    min_text = sdk.get(ANDROID + "minSdkVersion", "")
    target_text = sdk.get(ANDROID + "targetSdkVersion", "")
    min_sdk = int(min_text) if min_text.isdecimal() else None
    target_sdk = int(target_text) if target_text.isdecimal() else None
    require(min_sdk == args.expected_min_sdk, f"Unexpected minSdkVersion: {min_text}")
    require(target_sdk is not None and min_sdk is not None and target_sdk >= min_sdk,
            f"Invalid targetSdkVersion: {target_text}")
    if args.expected_target_sdk is not None:
        require(target_sdk == args.expected_target_sdk, f"Unexpected targetSdkVersion: {target_text}")

    providers = []
    authority_owners = {}
    for provider in app.findall("provider"):
        name = provider.get(ANDROID + "name", "")
        raw = provider.get(ANDROID + "authorities", "")
        authorities = raw.split(";")
        require(bool(name), "Provider without a class name")
        for authority in authorities:
            require(bool(authority) and authority == authority.strip(),
                    f"Empty or whitespace-padded authority on provider {name}")
            require(authority == args.expected_package or authority.startswith(args.expected_package + "."),
                    f"Provider authority is outside the private application namespace: {authority}")
            require(authority not in authority_owners, f"Duplicate provider authority: {authority}")
            authority_owners[authority] = name
        providers.append({"name": name, "authorities": authorities,
                          "exported": provider.get(ANDROID + "exported"),
                          "enabled": provider.get(ANDROID + "enabled", "true")})
    require(bool(providers), "No content providers found in the Firefox application manifest")

    launchers = []
    for element in list(app.findall("activity")) + list(app.findall("activity-alias")):
        for intent in element.findall("intent-filter"):
            actions = {item.get(ANDROID + "name") for item in intent.findall("action")}
            categories = {item.get(ANDROID + "name") for item in intent.findall("category")}
            if "android.intent.action.MAIN" in actions and "android.intent.category.LAUNCHER" in categories:
                if boolean(element, "enabled", True) is not True:
                    continue
                exported = boolean(element, "exported", target_sdk is not None and target_sdk < 31)
                require(exported is True, "Launcher component is not exported")
                launchers.append({"name": element.get(ANDROID + "name"),
                                  "target_activity": element.get(ANDROID + "targetActivity"),
                                  "exported": exported})
    require(bool(launchers), "No enabled MAIN/LAUNCHER component found")
    unresolved = sorted({value for element in root.iter() for value in element.attrib.values() if "${" in value})
    require(not unresolved, "Manifest still contains unresolved placeholders")
    return {
        "status": "passed" if not errors else "failed",
        "apk": str(apk_path), "apk_sha256": digest,
        "decoded_manifest_sha256": hashlib.sha256(decoded.stdout.encode()).hexdigest(),
        "decoded_from_this_apk": True,
        "package": package, "version_name": version, "version_code": version_code_text,
        "min_sdk": min_sdk, "target_sdk": target_sdk,
        "debuggable": debuggable, "test_only": test_only, "enabled": enabled,
        "shared_user_id_absent": ANDROID + "sharedUserId" not in root.attrib,
        "split_required": split_required, "extract_native_libs": extract_native,
        "provider_count": len(providers), "providers": providers, "launchers": launchers,
        "native_library_count": len(libraries), "compressed_native_libraries": compressed_native,
        "unresolved_placeholders": unresolved, "errors": errors,
        "scope": "Final APK manifest and packaging metadata. Does not prove provider Java classes load, APK signing validity, ELF/ZIP 16 KiB alignment, installation, or TLS behavior.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("apk", type=Path)
    parser.add_argument("--apkanalyzer", type=Path)
    parser.add_argument("--expected-package", default="org.mozilla.firefox.ruca")
    parser.add_argument("--expected-version", default="158.0")
    parser.add_argument("--expected-min-sdk", type=int, default=26)
    parser.add_argument("--expected-target-sdk", type=int)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        report = verify(args)
    except (ValueError, OSError, ET.ParseError, zipfile.BadZipFile, subprocess.SubprocessError) as exc:
        report = {"status": "failed", "apk": str(args.apk), "errors": [str(exc)]}
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
