#!/usr/bin/env python3
"""Embed the three explicitly supplied Russian CA certificates into Firefox.

Requires Python 3.10+ and cryptography 43+. Inputs are pinned by the SHA-256 of
the DER certificate, independent of PEM formatting. The root is trusted only
for TLS server authentication; the intermediate CAs are never trust anchors.

Generate standalone fragments and a certificate report:
  python inject_certificates.py --cert-dir /path/to/certs --output-dir out

Apply to a Firefox source tree and write a reproducible unified patch:
  python inject_certificates.py --cert-dir /path/to/certs --output-dir out \
      --source-root /path/to/firefox --apply

Check an already patched tree without modifying it:
  python inject_certificates.py --cert-dir /path/to/certs --source-root /path/to/firefox --check
"""

from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


BEGIN = "# BEGIN USER-SUPPLIED RUSSIAN CERTIFICATES v1"
END = "# END USER-SUPPLIED RUSSIAN CERTIFICATES v1"
VERSION_MARKER = "/* User-supplied Russian certificates: custom root-store revision. */"
CERTDATA = Path("security/nss/lib/ckfw/builtins/certdata.txt")
HEADER = Path("security/nss/lib/ckfw/builtins/nssckbi.h")
INTERMEDIATES = Path("security/manager/ssl/trust_anchors/bundled_intermediates.txt")
MUST_VERIFY = "CKT_NSS_MUST_VERIFY_TRUST"
TRUST_ANCHOR = "CKT_NSS_TRUSTED_DELEGATOR"
SPECS = (
    ("Russian_Trusted_Root_CA.cer", "Russian Trusted Root CA", True,
     "d26d2d0231b7c39f92cc738512ba54103519e4405d68b5bd703e9788ca8ecf31"),
    ("Russian_Trusted_Sub_CA.cer", "Russian Trusted Sub CA 2022", False,
     "bbbde2103e790b999ec62bd03cf625a5a2e7c316e10afe6a490eedead8b3fd9b"),
    ("Russian_Trusted_Sub_CA_2024.cer", "Russian Trusted Sub CA 2024", False,
     "2155785036c900dbb5f1bb2a1569c80c55595bd6bf94867a29bbddbc7d88a3f2"),
)


@dataclass(frozen=True)
class Certificate:
    filename: str
    label: str
    trust_anchor: bool
    der: bytes
    cert: x509.Certificate
    subject: bytes
    issuer: bytes
    serial: bytes


def tlv(data: bytes, offset: int) -> tuple[int, int, int]:
    """Return tag, content offset and end, preserving the original DER bytes."""
    if offset + 2 > len(data):
        raise ValueError("Truncated DER tag or length")
    tag = data[offset]
    length = data[offset + 1]
    cursor = offset + 2
    if tag & 31 == 31:
        raise ValueError("Unexpected high-tag-number DER")
    if length & 128:
        size = length & 127
        if not size or size > 4 or cursor + size > len(data):
            raise ValueError("Invalid DER length")
        if not data[cursor]:
            raise ValueError("Non-minimal DER length")
        length = int.from_bytes(data[cursor:cursor + size], "big")
        cursor += size
        if length < 128:
            raise ValueError("Non-minimal DER length")
    end = cursor + length
    if end > len(data):
        raise ValueError("Truncated DER value")
    return tag, cursor, end


def raw_fields(der: bytes) -> tuple[bytes, bytes, bytes]:
    outer_tag, outer_content, outer_end = tlv(der, 0)
    if outer_tag != 0x30 or outer_end != len(der):
        raise ValueError("Expected exactly one DER certificate sequence")
    tbs_tag, cursor, tbs_end = tlv(der, outer_content)
    if tbs_tag != 0x30:
        raise ValueError("Expected TBSCertificate sequence")
    fields = []
    while cursor < tbs_end:
        tag, content, end = tlv(der, cursor)
        if end > tbs_end:
            raise ValueError("DER child escapes TBSCertificate")
        fields.append((tag, der[cursor:end]))
        cursor = end
    if fields and fields[0][0] == 0xA0:
        fields.pop(0)
    if len(fields) < 6 or [x[0] for x in fields[:6]] != [2, 48, 48, 48, 48, 48]:
        raise ValueError("Unexpected X.509 TBSCertificate field ordering")
    serial, issuer, subject = fields[0][1], fields[2][1], fields[4][1]
    # Firefox's generated Rust root store uses u8 offsets and lengths here.
    for name, data in [("serial", serial), ("subject", subject)]:
        if len(data) > 255 or not 0 <= der.find(data) <= 255:
            raise ValueError(f"{name} does not fit Firefox's current root-store format")
    return subject, issuer, serial


def load_certificates(cert_dir: Path) -> list[Certificate]:
    now = datetime.now(timezone.utc)
    result = []
    for filename, label, anchor, expected_sha256 in SPECS:
        raw = (cert_dir / filename).read_bytes()
        if b"-----BEGIN CERTIFICATE-----" in raw:
            match = re.fullmatch(
                rb"\s*-----BEGIN CERTIFICATE-----\s*([A-Za-z0-9+/=\s]+?)\s*"
                rb"-----END CERTIFICATE-----\s*", raw)
            if not match:
                raise ValueError(f"{filename}: expected a single PEM certificate")
            der = base64.b64decode(re.sub(rb"\s", b"", match[1]), validate=True)
        else:
            der = raw
        actual_sha256 = hashlib.sha256(der).hexdigest()
        if actual_sha256 != expected_sha256:
            raise ValueError(f"{filename}: SHA-256 mismatch: {actual_sha256}")
        cert = x509.load_der_x509_certificate(der)
        if cert.public_bytes(serialization.Encoding.DER) != der:
            raise ValueError(f"{filename}: DER did not round-trip unchanged")
        constraints = cert.extensions.get_extension_for_class(x509.BasicConstraints)
        usage = cert.extensions.get_extension_for_class(x509.KeyUsage)
        if not constraints.critical or not constraints.value.ca:
            raise ValueError(f"{filename}: missing critical CA constraints")
        if not usage.critical or not usage.value.key_cert_sign or not usage.value.crl_sign:
            raise ValueError(f"{filename}: missing critical CA signing usages")
        if not cert.not_valid_before_utc <= now <= cert.not_valid_after_utc:
            raise ValueError(f"{filename}: outside certificate validity at {now.isoformat()}")
        if not isinstance(cert.public_key(), rsa.RSAPublicKey) or cert.public_key().key_size != 4096:
            raise ValueError(f"{filename}: expected RSA-4096")
        if cert.signature_hash_algorithm.name != "sha256":
            raise ValueError(f"{filename}: expected SHA-256 signature")
        subject, issuer, serial = raw_fields(der)
        if (subject != cert.subject.public_bytes() or issuer != cert.issuer.public_bytes()):
            raise ValueError(f"{filename}: raw DER name mismatch")
        result.append(Certificate(filename, label, anchor, der, cert, subject, issuer, serial))
    root = result[0]
    if root.subject != root.issuer:
        raise ValueError("Root certificate is not self-issued")
    root.cert.verify_directly_issued_by(root.cert)
    root_ski = root.cert.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value.digest
    for entry in result[1:]:
        entry.cert.verify_directly_issued_by(root.cert)
        aki = entry.cert.extensions.get_extension_for_class(x509.AuthorityKeyIdentifier).value.key_identifier
        if aki != root_ski:
            raise ValueError(f"{entry.filename}: root SKI and intermediate AKI mismatch")
        if entry.cert.extensions.get_extension_for_class(x509.BasicConstraints).value.path_length != 0:
            raise ValueError(f"{entry.filename}: expected path length constraint zero")
    return result


def octal(name: str, value: bytes) -> str:
    lines = [name + " MULTILINE_OCTAL"]
    for offset in range(0, len(value), 16):
        lines.append("".join(f"\\{byte:03o}" for byte in value[offset:offset + 16]))
    return "\n".join(lines + ["END", ""])


def fingerprint(der: bytes, name: str = "sha256") -> str:
    digest = hashlib.new(name, der, usedforsecurity=False).digest()
    return ":".join(f"{byte:02X}" for byte in digest)


def comment(entry: Certificate) -> str:
    cert = entry.cert
    return (
        f"# Issuer: {cert.issuer.rfc4514_string()}\n"
        f"# Serial Number: {cert.serial_number} (0x{cert.serial_number:x})\n"
        f"# Subject: {cert.subject.rfc4514_string()}\n"
        f"# Not Valid Before: {cert.not_valid_before_utc.isoformat()}\n"
        f"# Not Valid After : {cert.not_valid_after_utc.isoformat()}\n"
        f"# Fingerprint (SHA-256): {fingerprint(entry.der)}\n"
        f"# Fingerprint (SHA1): {fingerprint(entry.der, 'sha1')}\n"
    )


def object_header(kind: str, label: str) -> str:
    return (
        f"CKA_CLASS CK_OBJECT_CLASS {kind}\n"
        "CKA_TOKEN CK_BBOOL CK_TRUE\n"
        "CKA_PRIVATE CK_BBOOL CK_FALSE\n"
        "CKA_MODIFIABLE CK_BBOOL CK_FALSE\n"
        f'CKA_LABEL UTF8 "{label}"\n'
    )


def render_certificate(entry: Certificate) -> str:
    cert = f'#\n# Certificate "{entry.label}"\n#\n' + comment(entry)
    cert += object_header("CKO_CERTIFICATE", entry.label)
    cert += "CKA_CERTIFICATE_TYPE CK_CERTIFICATE_TYPE CKC_X_509\n"
    cert += octal("CKA_SUBJECT", entry.subject)
    cert += 'CKA_ID UTF8 "0"\n'
    cert += octal("CKA_ISSUER", entry.issuer)
    cert += octal("CKA_SERIAL_NUMBER", entry.serial)
    cert += octal("CKA_VALUE", entry.der)
    # Supplied custom trust is not represented as Mozilla Root Program approval.
    cert += "CKA_NSS_MOZILLA_CA_POLICY CK_BBOOL CK_FALSE\n"
    cert += "CKA_NSS_SERVER_DISTRUST_AFTER CK_BBOOL CK_FALSE\n"
    cert += "CKA_NSS_EMAIL_DISTRUST_AFTER CK_BBOOL CK_FALSE\n\n"
    cert += f'# Trust for "{entry.label}"\n' + comment(entry)
    cert += object_header("CKO_NSS_TRUST", entry.label)
    # These legacy hashes are NSS lookup attributes, never signature algorithms.
    cert += octal("CKA_CERT_SHA1_HASH", hashlib.sha1(entry.der, usedforsecurity=False).digest())
    cert += octal("CKA_CERT_MD5_HASH", hashlib.md5(entry.der, usedforsecurity=False).digest())
    cert += octal("CKA_ISSUER", entry.issuer)
    cert += octal("CKA_SERIAL_NUMBER", entry.serial)
    trust = TRUST_ANCHOR if entry.trust_anchor else MUST_VERIFY
    cert += f"CKA_TRUST_SERVER_AUTH CK_TRUST {trust}\n"
    cert += f"CKA_TRUST_EMAIL_PROTECTION CK_TRUST {MUST_VERIFY}\n"
    cert += f"CKA_TRUST_CODE_SIGNING CK_TRUST {MUST_VERIFY}\n"
    return cert + "CKA_TRUST_STEP_UP_APPROVED CK_BBOOL CK_FALSE\n"


def render_fragment(entries: list[Certificate]) -> str:
    return BEGIN + "\n" + "\n".join(map(render_certificate, entries)) + END + "\n"


def managed_update(original: str, fragment: str) -> str:
    if original.count(BEGIN) != original.count(END) or original.count(BEGIN) > 1:
        raise ValueError("Unbalanced or repeated managed-certificate markers")
    if BEGIN in original:
        start, end = original.index(BEGIN), original.index(END) + len(END)
        if end < start:
            raise ValueError("Reversed managed-certificate markers")
        end += int(original[end:end + 1] == "\n")
        outside = original[:start] + original[end:]
        updated = original[:start] + fragment + original[end:]
    else:
        outside = original
        updated = original + ("\n\n" if not original.endswith("\n") else "\n") + fragment
    for _, label, _, digest in SPECS:
        if f'CKA_LABEL UTF8 "{label}"' in outside:
            raise ValueError(f"Unmanaged certificate already uses label: {label}")
        if ":".join(digest[i:i + 2].upper() for i in range(0, len(digest), 2)) in outside:
            raise ValueError(f"Unmanaged copy of supplied certificate already exists: {label}")
    return updated


def custom_version(original: str) -> str:
    major_re = r"(?m)^#define NSS_BUILTINS_LIBRARY_VERSION_MAJOR (\d+)[ \t]*$"
    minor_re = r"(?m)^#define NSS_BUILTINS_LIBRARY_VERSION_MINOR (\d+)[ \t]*$"
    string_re = r'(?m)^#define NSS_BUILTINS_LIBRARY_VERSION "([0-9.]+)"[ \t]*$'
    major_match, minor_match, string_match = (re.search(p, original) for p in (major_re, minor_re, string_re))
    if not all((major_match, minor_match, string_match)):
        raise ValueError("Cannot find NSS builtin library version macros")
    major, minor = int(major_match[1]), int(minor_match[1])
    if string_match[1] != f"{major}.{minor}":
        raise ValueError("NSS builtin numeric and string versions disagree")
    if VERSION_MARKER in original:
        if original.count(VERSION_MARKER) != 1 or minor % 2 != 1:
            raise ValueError("Invalid custom NSS root-store version marker")
        return original
    # nssckbi.h reserves odd minors for a root store diverging from upstream.
    minor = minor + 1 if minor % 2 == 0 else minor + 2
    if minor > 99:
        major, minor = major + 1, 1
    changed = re.sub(major_re, f"#define NSS_BUILTINS_LIBRARY_VERSION_MAJOR {major}", original)
    changed = re.sub(minor_re, f"#define NSS_BUILTINS_LIBRARY_VERSION_MINOR {minor}", changed)
    changed = re.sub(string_re, f'{VERSION_MARKER}\n#define NSS_BUILTINS_LIBRARY_VERSION "{major}.{minor}"', changed)
    return changed


def atomic_write(path: Path, content: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, str):
        content = content.encode("utf-8")
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    handle, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".tmp.")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(content)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def certificate_report(entries: list[Certificate]) -> dict:
    rows = []
    for entry in entries:
        cert = entry.cert
        rows.append({
            "filename": entry.filename,
            "builtin_label": entry.label,
            "sha256_der": hashlib.sha256(entry.der).hexdigest(),
            "der_bytes": len(entry.der),
            "subject": cert.subject.rfc4514_string(),
            "issuer": cert.issuer.rfc4514_string(),
            "serial_hex": hex(cert.serial_number),
            "not_before_utc": cert.not_valid_before_utc.isoformat(),
            "not_after_utc": cert.not_valid_after_utc.isoformat(),
            "public_key": "RSA-4096",
            "signature_hash": cert.signature_hash_algorithm.name,
            "ca_path_length": cert.extensions.get_extension_for_class(x509.BasicConstraints).value.path_length,
            "signature_verified_by_supplied_root": True,
            "trust_server_auth": TRUST_ANCHOR if entry.trust_anchor else MUST_VERIFY,
            "trust_email": MUST_VERIFY,
            "trust_code_signing": MUST_VERIFY,
            "mozilla_ca_policy": False,
            "subject_der_offset": entry.der.find(entry.subject),
            "subject_der_bytes": len(entry.subject),
            "serial_der_offset": entry.der.find(entry.serial),
            "serial_der_bytes": len(entry.serial),
        })
    return {"schema": 1, "certificates": rows,
            "notes": ["Certificate signatures verified, not a revocation check.",
                      "SHA-256 pins identify the exact user-supplied input files; no independent issuer provenance claim.",
                      "Only the self-signed root is an HTTPS trust anchor; intermediates still require a valid chain."]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cert-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--source-root", type=Path)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--apply", action="store_true")
    actions.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if (args.apply or args.check) and not args.source_root:
        parser.error("--apply/--check requires --source-root")
    entries = load_certificates(args.cert_dir)
    report = certificate_report(entries)
    fragments = {"root.certdata.txt": render_fragment(entries[:1]),
                 "intermediates.certdata.txt": render_fragment(entries[1:]),
                 "all.certdata.txt": render_fragment(entries)}
    changes = []
    if args.source_root:
        source = args.source_root.resolve()
        if not (source / CERTDATA).is_file() or not (source / HEADER).is_file():
            raise ValueError("Source tree is missing NSS certdata.txt or nssckbi.h")
        split = (source / INTERMEDIATES).is_file()
        if split:
            build_script = (source / INTERMEDIATES.parent / "build.rs").read_text()
            if "bundled_intermediates.txt" not in build_script:
                raise ValueError("Found intermediate store, but build.rs does not consume it")
        specs = [(CERTDATA, fragments["root.certdata.txt"] if split else fragments["all.certdata.txt"])]
        if split:
            specs.append((INTERMEDIATES, fragments["intermediates.certdata.txt"]))
        for relative, fragment in specs:
            old = (source / relative).read_text()
            changes.append((relative, old, managed_update(old, fragment)))
        old_header = (source / HEADER).read_text()
        changes.append((HEADER, old_header, custom_version(old_header)))
        report["source_integration"] = {"separate_intermediate_store": split,
                                        "files": [str(relative) for relative, _, _ in changes]}
        different = [str(relative) for relative, old, new in changes if old != new]
        if args.check and different:
            raise ValueError("Source tree does not contain exact expected integration: " + ", ".join(different))
        if args.apply:
            for relative, old, new in changes:
                if old != new:
                    atomic_write(source / relative, new)
        report["action"] = "check" if args.check else "apply" if args.apply else "preview"
        report["changed_files"] = different
    if args.output_dir:
        for name, data in fragments.items():
            atomic_write(args.output_dir / name, data)
        for entry in entries:
            atomic_write(args.output_dir / entry.filename.replace(".cer", ".der"), entry.der)
        if changes:
            patch = "".join("".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                              fromfile="a/" + str(relative), tofile="b/" + str(relative)))
                            for relative, old, new in changes)
            # Preserve a previously generated nonempty patch during an idempotence check.
            if patch or not (args.output_dir / "certificates.patch").exists():
                atomic_write(args.output_dir / "certificates.patch", patch)
        atomic_write(args.output_dir / "certificate-report.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"Certificate integration failed: {exc}", file=sys.stderr)
        sys.exit(1)
