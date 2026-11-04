#!/usr/bin/env python3
"""Resolve the official Android release tag; toolchain artifacts remain pinned."""
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def validate_version(version):
    # Follow stable Mozilla Android releases; do not accept beta, RC or nightly tags.
    if not re.fullmatch(r'[1-9][0-9]*\.(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*))?', version):
        raise ValueError('Expected a stable Firefox Android version')
    if int(version.split('.', 1)[0]) < 159:
        raise ValueError('Firefox Android versions older than the reviewed 159 baseline are not supported')
    return version


def main():
    version = validate_version(os.environ['FIREFOX_VERSION'])
    work = Path(os.environ['FIREFOX_BUILD_ROOT'])
    work.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((ROOT / 'kit/downloads.json').read_text())
    repo = 'https://github.com/mozilla-firefox/firefox.git'
    tag = 'FIREFOX-ANDROID_' + version.replace('.', '_') + '_RELEASE'
    result = subprocess.run(['git', 'ls-remote', repo, f'refs/tags/{tag}', f'refs/tags/{tag}^{{}}'],
                            capture_output=True, text=True, check=True)
    refs = dict((line.split()[1], line.split()[0]) for line in result.stdout.splitlines())
    commit = refs.get(f'refs/tags/{tag}^{{}}', refs.get(f'refs/tags/{tag}'))
    if not commit or not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('Official Android release tag is missing or invalid')
    pinned = manifest['source_git']
    if pinned['tag'] == tag and pinned['commit'] != commit:
        raise ValueError('Pinned official Android release tag changed')
    manifest['source_git'] = dict(repository=repo, tag=tag, commit=commit)
    manifest['firefox_version'] = version
    manifest['verification_note'] = 'Official Android tag resolved over HTTPS; commit checked after fetch; tag signature not independently verified.'
    (work / 'downloads.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'Android source {version}: {tag} -> {commit}')


if __name__ == '__main__':
    main()
