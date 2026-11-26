#!/usr/bin/env python3
"""Safely start a signed, published build from an explicit GitHub push request."""
import json
import os
from pathlib import Path
import subprocess

from source_manifest import validate_version
from mobile_versions import latest_stable


def main():
    request = json.loads(Path('ci/release-build-request.json').read_text())
    if set(request) != {'version', 'publish'} or request['publish'] is not True:
        raise ValueError('Expected an explicit published-release request')
    version = validate_version(request['version'])
    latest = latest_stable()
    if latest != version:
        raise ValueError(f'Requested {version}, but Mozilla latest is {latest}; do not start a stale build')
    subprocess.run(['gh', 'workflow', 'run', 'build.yml',
                    '--repo', os.environ['GH_REPO'], '--ref', 'main',
                    '-f', f'version={version}', '-f', 'publish=true',
                    '-f', 'unsigned=false'], check=True)
    print(f'Dispatched signed, tested, published Цифролис v{version} build')


if __name__ == '__main__':
    main()
