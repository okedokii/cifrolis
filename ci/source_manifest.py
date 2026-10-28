#!/usr/bin/env python3
"""Resolve only the source archive dynamically; toolchains stay pinned and guarded."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]

def validate_version(version):
    if not re.fullmatch(r'[1-9][0-9]*\.[0-9]+(?:\.[0-9]+)?', version):
        raise ValueError('Only stable numeric Firefox versions are allowed')
    if version.split('.')[0] != '158':
        raise ValueError('Only 158.x is admitted. Review patches and toolchain profile before admitting another major.')
    return version

def main():
    version = validate_version(os.environ['FIREFOX_VERSION'])
    work = Path(os.environ['FIREFOX_BUILD_ROOT'])
    work.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((ROOT / 'kit/downloads.json').read_text())
    if version != '158.0':
        repo = 'https://github.com/mozilla-firefox/firefox.git'
        tag = 'FIREFOX-ANDROID_' + version.replace('.', '_') + '_RELEASE'
        result = subprocess.run(['git', 'ls-remote', repo, f'refs/tags/{tag}', f'refs/tags/{tag}^{{}}'],
                                capture_output=True, text=True, check=True)
        refs = dict((line.split()[1], line.split()[0]) for line in result.stdout.splitlines())
        commit = refs.get(f'refs/tags/{tag}^{{}}', refs.get(f'refs/tags/{tag}'))
        if not commit or not re.fullmatch('[0-9a-f]{40}', commit):
            raise ValueError('Official Android release tag missing or invalid')
        manifest['archives'] = [r for r in manifest['archives'] if r['name'] != 'source']
        manifest['source_git'] = dict(repository=repo, tag=tag, commit=commit)
        manifest['firefox_version'] = version
        manifest['verification_note'] = 'Official Android tag resolved over HTTPS; commit checked after fetch; tag signature not independently verified.'
        (work / 'downloads.json').write_text(json.dumps(manifest, indent=2) + '\n')
        print(f'Android source {version}: {tag} -> {commit}')
        return
    base = f'https://archive.mozilla.org/pub/firefox/releases/{version}'
    relative = f'source/firefox-{version}.source.tar.xz'
    with urllib.request.urlopen(base + '/SHA512SUMS', timeout=60) as response:
        sums = response.read()
    (work / 'SHA512SUMS').write_bytes(sums)
    matches = [line.split()[0] for line in sums.decode().splitlines()
               if len(line.split()) == 2 and line.split()[1].lstrip('*') == relative]
    if len(matches) != 1 or not re.fullmatch('[a-fA-F0-9]{128}', matches[0]):
        raise ValueError('Missing or ambiguous source checksum')
    request = urllib.request.Request(base + '/' + relative, method='HEAD')
    with urllib.request.urlopen(request, timeout=60) as response:
        size = int(response.headers['Content-Length'])
    original = manifest['archives'][0]
    if original['name'] != 'source':
        raise ValueError('Unexpected archive ordering')
    if version == '158.0' and matches[0].lower() != original['digest'].lower():
        raise ValueError('Original source hash changed')
    original.update(filename=relative.split('/')[-1], directory=f'firefox-{version}',
                    url=base + '/' + relative, digest=matches[0].lower(), size_bytes=size,
                    checksum_source=base + '/SHA512SUMS')
    manifest['firefox_version'] = version
    manifest['verification_note'] = 'Checksums retrieved over HTTPS; Mozilla OpenPGP signature not verified.'
    (work / 'downloads.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'Resolved source {version}, {size} bytes; SHA512SUMS sha256={hashlib.sha256(sums).hexdigest()}')

if __name__ == '__main__':
    main()
