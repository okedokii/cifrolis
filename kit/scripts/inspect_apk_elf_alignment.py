#!/usr/bin/env python3
"""Inspect ELF PT_LOAD alignment in an APK without extracting or changing it."""

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import zipfile


PAGE_SIZE = 16384
ELF_HEADER = struct.Struct('<16sHHIQQQIHHHHHH')
PROGRAM_HEADER = struct.Struct('<IIQQQQQQ')


def inspect_library(apk, info):
    with apk.open(info) as stream:
        header = stream.read(ELF_HEADER.size)
        if len(header) != ELF_HEADER.size:
            raise ValueError('Truncated ELF header')
        fields = ELF_HEADER.unpack(header)
        if fields[0][:7] != b'\x7fELF\x02\x01\x01' or fields[2] != 183:
            raise ValueError('Expected little-endian ELF64 AArch64')
        if fields[1] != 3:
            raise ValueError('Expected ET_DYN shared object')
        phoff, phentsize, phnum = fields[5], fields[9], fields[10]
        if phnum == 0xffff:
            raise ValueError('Extended program-header numbering is not supported')
        if not phnum or phentsize < PROGRAM_HEADER.size:
            raise ValueError('Missing or invalid program-header table')
        if phoff + phentsize * phnum > info.file_size:
            raise ValueError('Program-header table exceeds ELF file size')
        stream.seek(phoff)
        table = stream.read(phentsize * phnum)
        if len(table) != phentsize * phnum:
            raise ValueError('Truncated program-header table')
    segments = []
    relro = []
    for index in range(phnum):
        kind, flags, offset, address, _, filesz, memsz, alignment = PROGRAM_HEADER.unpack_from(table, index * phentsize)
        if kind == 0x6474e552:
            relro.append({'index': index, 'virtual_address_hex': hex(address),
                          'memory_size_hex': hex(memsz),
                          'end_modulo_16k': (address + memsz) % PAGE_SIZE})
        if kind != 1:
            continue
        power_of_two = alignment > 0 and alignment & (alignment - 1) == 0
        size_ok = power_of_two and alignment >= PAGE_SIZE
        congruent_16k = (address - offset) % PAGE_SIZE == 0
        congruent_declared = power_of_two and (address - offset) % alignment == 0
        within_file = offset + filesz <= info.file_size
        segment_ok = size_ok and congruent_16k and congruent_declared and within_file and filesz <= memsz
        segments.append({
            'index': index, 'offset_hex': hex(offset), 'virtual_address_hex': hex(address),
            'file_size_hex': hex(filesz), 'memory_size_hex': hex(memsz),
            'alignment_hex': hex(alignment), 'flags': flags,
            'alignment_power_of_two_and_at_least_16k': size_ok,
            'virtual_address_and_offset_congruent_modulo_16k': congruent_16k,
            'congruent_modulo_declared_alignment': congruent_declared,
            'file_range_valid': within_file and filesz <= memsz,
            'pass': segment_ok,
        })
    return {'entry': info.filename, 'elf_class': 64, 'machine': 'AArch64',
            'load_segments': segments, 'gnu_relro_segments_observed': relro,
            'pass': bool(segments) and all(segment['pass'] for segment in segments)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    libraries = []
    with zipfile.ZipFile(args.apk) as apk:
        native = [item for item in apk.infolist() if item.filename.startswith('lib/') and item.filename.endswith('.so')]
        unexpected = [item.filename for item in native if not item.filename.startswith('lib/arm64-v8a/')]
        names = [item.filename for item in native]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        for info in native:
            if not info.filename.startswith('lib/arm64-v8a/'):
                continue
            try:
                libraries.append(inspect_library(apk, info))
            except (ValueError, struct.error, EOFError, zipfile.BadZipFile) as exc:
                libraries.append({'entry': info.filename, 'pass': False, 'error': str(exc)})
    with args.apk.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    passed = bool(libraries) and not unexpected and not duplicates and all(item['pass'] for item in libraries)
    report = {
        'apk': str(args.apk.resolve()), 'apk_sha256': digest, 'page_size_bytes': PAGE_SIZE,
        'arm64_library_count': len(libraries), 'unexpected_abi_entries': unexpected,
        'duplicate_native_entries': duplicates, 'libraries': libraries,
        'all_arm64_pt_load_checks_pass': passed,
        'scope': 'Read-only ELF structure inspection. Does not establish ZIP alignment, APK signature validity, installation, full RELRO compatibility, or runtime behavior on 16 KiB Android.',
        'reference': 'https://developer.android.com/guide/practices/page-sizes#elf-alignment',
    }
    encoded = json.dumps(report, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(encoded)
    print(encoded, end='')
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
