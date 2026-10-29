#!/usr/bin/env python3
"""Verify ARM64 ELF and exact embedded certificate bytes in a completed APK.

This is static artifact verification. It does not replace on-device TLS tests
or Android APK signature verification with apksigner.
"""

import argparse
import hashlib
import json
from pathlib import Path
import struct
import zipfile

from inject_certificates import SPECS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    parser.add_argument("--der-dir", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    certs = {}
    for filename, label, _, expected_hash in SPECS:
        der = (args.der_dir / filename.replace(".cer", ".der")).read_bytes()
        if hashlib.sha256(der).hexdigest() != expected_hash:
            raise ValueError(f"DER reference hash mismatch: {filename}")
        certs[label] = (der, expected_hash)
    with zipfile.ZipFile(args.apk) as apk:
        external_roots = [name for name in apk.namelist()
                          if name.rstrip('/').rsplit('/', 1)[-1].lower() == "libnssckbi.so"]
        if external_roots:
            raise ValueError("APK contains an external root-store module that could override libxul: "
                             + ", ".join(external_roots))
        native = [name for name in apk.namelist() if name.startswith("lib/") and name.endswith(".so")]
        if not native:
            raise ValueError("APK contains no native libraries")
        if any(not name.startswith("lib/arm64-v8a/") for name in native):
            raise ValueError("Expected an ARM64-only APK")
        xul_name = "lib/arm64-v8a/libxul.so"
        if xul_name not in native:
            raise ValueError("APK does not contain ARM64 libxul.so")
        elf_results = []
        for name in native:
            with apk.open(name) as library:
                header = library.read(20)
            if header[:6] != b"\x7fELF\x02\x01":
                raise ValueError(f"Expected ELF64 little-endian library: {name}")
            if struct.unpack_from("<H", header, 18)[0] != 183:
                raise ValueError(f"Expected AArch64 ELF machine: {name}")
            elf_results.append(name)
        xul = apk.read(xul_name)
        cert_results = []
        for label, (der, digest) in certs.items():
            offset = xul.find(der)
            if offset == -1:
                raise ValueError(f"Exact DER certificate is missing from libxul.so: {label}")
            if label.encode() + b"\x00" not in xul:
                raise ValueError(f"Builtin certificate label is missing from libxul.so: {label}")
            cert_results.append({"label": label, "sha256_der": digest,
                                 "libxul_der_offset": offset, "der_bytes": len(der)})
    with args.apk.open("rb") as stream:
        apk_sha256 = hashlib.file_digest(stream, "sha256").hexdigest()
    report = {"apk": str(args.apk), "apk_sha256": apk_sha256,
              "external_libnssckbi_absent": True,
              "external_root_store_libraries": external_roots,
              "native_libraries_verified_as_aarch64_elf64": elf_results,
              "certificates_found_in_libxul": cert_results,
              "scope": "Static APK inspection; does not assert installation, APK signature validity, or live TLS behavior."}
    encoded = json.dumps(report, indent=2) + "\n"
    if args.report:
        args.report.write_text(encoded)
    print(encoded, end="")


if __name__ == "__main__":
    main()
